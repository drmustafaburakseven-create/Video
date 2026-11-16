"""Fal queue/schema integration without any live paid requests."""
import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

from PIL import Image

from automation import avatar_fal
from automation.state import LocalJournal, PipelineError
from automation.tests.test_avatar import client, response


class FalAvatarTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.portrait, self.audio = self.root/'portrait.png', self.root/'slice.wav'
        Image.new('RGB', (64, 64), 'navy').save(self.portrait)
        with wave.open(str(self.audio), 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(48000)
            audio.writeframes(b'\x00' * (48000*4*2))
        self.meta = {'duration': 4, 'slice_sha256': hashlib.sha256(self.audio.read_bytes()).hexdigest()}
        self.journal = LocalJournal(self.root/'journal')
        self.output = self.root/'avatar.mp4'
        environment = patch.dict(os.environ, {'FAL_KEY': 'mock-fal-key'}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        probe = patch('automation.avatar.probe', side_effect=self.metadata)
        probe.start()
        self.addCleanup(probe.stop)

    def metadata(self, path):
        if Path(path) == self.audio:
            return {'format': {'duration': '4', 'format_name': 'wav'},
                    'streams': [{'codec_type': 'audio', 'duration': '4'}]}
        return {'format': {'duration': '4', 'format_name': 'mov,mp4,m4a'},
                'streams': [{'codec_type': 'video', 'duration': '4', 'width': 720, 'height': 1280}]}

    def create(self, **kwargs):
        return avatar_fal.create_avatar(self.portrait, self.audio, self.meta,
                                        self.journal, self.output, **kwargs)

    def accepted(self):
        return response(data={'status': 'IN_QUEUE', 'request_id': 'saved-request',
                              'status_url': 'https://untrusted.example/steal-key',
                              'response_url': 'https://untrusted.example/steal-key'})

    def completed(self, **extra):
        return response(data={'status': 'COMPLETED', 'request_id': 'saved-request', **extra})

    def video(self, url='https://v3.fal.media/files/test/video.mp4?signature=private-value', mime='video/mp4'):
        return response(data={'video': {'url': url, 'content_type': mime}})

    def test_missing_key_does_not_request_credit_or_generation(self):
        with patch.dict(os.environ, {}, clear=True), patch('automation.avatar_fal.session') as factory:
            with self.assertRaisesRegex(PipelineError, 'FAL_KEY'):
                avatar_fal.ensure_available()
            factory.assert_not_called()

    def test_presence_check_is_not_a_live_account_check(self):
        with patch('automation.avatar_fal.session') as factory:
            self.assertTrue(avatar_fal.ensure_available())
            factory.assert_not_called()

    def test_exact_data_uris_fixed_queue_routes_and_no_cdn_auth(self):
        api = client(self.accepted(), self.completed(), self.video())
        cdn = client(response())
        with patch('automation.avatar_fal.session', return_value=api), \
                patch('automation.avatar.session', return_value=cdn):
            self.assertEqual(self.create(), self.output)
        calls = api.request.call_args_list
        self.assertEqual([c.args[0] for c in calls], ['POST', 'GET', 'GET'])
        self.assertEqual(calls[0].args[1], 'https://queue.fal.run/fal-ai/creatify/aurora')
        self.assertEqual(calls[1].args[1], 'https://queue.fal.run/fal-ai/creatify/requests/saved-request/status')
        self.assertEqual(calls[2].args[1], 'https://queue.fal.run/fal-ai/creatify/requests/saved-request')
        payload = calls[0].kwargs['json']
        self.assertEqual(base64.b64decode(payload['image_url'].split(',', 1)[1]), self.portrait.read_bytes())
        self.assertEqual(base64.b64decode(payload['audio_url'].split(',', 1)[1]), self.audio.read_bytes())
        self.assertTrue(payload['enable_safety_checker'])
        self.assertEqual(payload['resolution'], '720p')
        self.assertEqual(api.headers['X-Fal-No-Retry'], '1')
        self.assertEqual(cdn.headers, {})
        self.assertNotIn('headers', cdn.request.call_args.kwargs)
        self.assertFalse(cdn.request.call_args.kwargs['allow_redirects'])
        saved = next((self.root/'journal').glob('*.json')).read_text()
        self.assertNotIn('signature', saved)
        self.assertNotIn('untrusted.example', saved)
        self.assertNotIn('mock-fal-key', saved)
        self.assertEqual(json.loads(saved)['generation']['response'], {'request_id': 'saved-request'})
        with patch.dict(os.environ, {}, clear=True), patch('automation.avatar_fal.session') as factory:
            self.assertEqual(self.create(), self.output)
            factory.assert_not_called()

    def test_resume_after_timeout_polls_without_another_submission(self):
        first = client(self.accepted())
        second = client(self.completed(), self.video())
        cdn = client(response())
        with patch('automation.avatar_fal.session', side_effect=[first, second]), \
                patch('automation.avatar.session', return_value=cdn):
            with self.assertRaisesRegex(PipelineError, 'still pending'):
                self.create(timeout=0)
            self.assertEqual(self.create(), self.output)
        self.assertEqual([c.args[0] for c in first.request.call_args_list], ['POST'])
        self.assertEqual([c.args[0] for c in second.request.call_args_list], ['GET', 'GET'])

    def test_failed_completed_status_never_gets_result_or_retries_generation(self):
        failed = self.completed(error='private-provider-message', error_type='sensitive-example')
        first, second = client(self.accepted(), failed), client(failed)
        with patch('automation.avatar_fal.session', side_effect=[first, second]), \
                patch('automation.avatar.session') as cdn:
            for _ in range(2):
                with self.assertRaisesRegex(PipelineError, 'generation failed') as caught:
                    self.create()
                self.assertNotIn('private-provider-message', str(caught.exception))
                self.assertNotIn('sensitive-example', str(caught.exception))
        self.assertEqual([c.args[0] for c in second.request.call_args_list], ['GET'])
        cdn.assert_not_called()

    def test_ambiguous_request_is_preserved_and_never_resubmitted(self):
        import requests
        first, second = client(requests.Timeout('private-url')), client()
        with patch('automation.avatar_fal.session', side_effect=[first, second]):
            with self.assertRaisesRegex(PipelineError, 'Network request failed'):
                self.create()
            with self.assertRaisesRegex(PipelineError, 'resubmission blocked'):
                self.create()
        second.request.assert_not_called()

    def test_wrong_speech_hash_fails_before_any_request(self):
        self.meta['slice_sha256'] = '0'*64
        with patch('automation.avatar_fal.session') as factory:
            with self.assertRaisesRegex(PipelineError, 'speech hash differs'):
                self.create()
            factory.assert_not_called()

    def test_private_or_credential_bearing_media_url_is_not_downloaded(self):
        for url in ['https://127.0.0.1/test', 'https://key:secret@example.com/test']:
            with self.subTest(url=url):
                api = client(self.accepted(), self.completed(), self.video(url))
                with patch('automation.avatar_fal.session', return_value=api), \
                        patch('automation.avatar.session') as cdn:
                    with self.assertRaises(PipelineError):
                        self.create()
                    cdn.assert_not_called()
                for path in (self.root/'journal').glob('*.json'):
                    path.unlink()  # Isolated unit fixtures only, never production recovery.

    def test_result_must_have_documented_video_and_mime_fields(self):
        for result in [response(data={'url': 'https://example.com/video.mp4'}), self.video(mime='text/html')]:
            api = client(self.accepted(), self.completed(), result)
            with patch('automation.avatar_fal.session', return_value=api), \
                    patch('automation.avatar.session') as cdn:
                with self.assertRaises(PipelineError):
                    self.create()
                cdn.assert_not_called()
            for path in (self.root/'journal').glob('*.json'):
                path.unlink()

    def test_status_cannot_substitute_another_request(self):
        api = client(self.accepted(), response(data={'status': 'COMPLETED', 'request_id': 'another-request'}))
        with patch('automation.avatar_fal.session', return_value=api):
            with self.assertRaisesRegex(PipelineError, 'does not match'):
                self.create()
        self.assertEqual(api.request.call_count, 2)


if __name__ == '__main__':
    unittest.main()
