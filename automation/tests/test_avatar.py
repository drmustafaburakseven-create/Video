"""Avatar paid-once, input-integrity and credential-boundary regression tests."""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import wave

from PIL import Image

from automation import avatar
from automation.state import LocalJournal, PipelineError


def response(status=200, data=None, *, content_type='video/mp4', body=b'video-test'):
    result = Mock(status_code=status)
    result.json.return_value = data or {}
    result.headers = {'Content-Type': content_type, 'Content-Length': str(len(body))}
    result.iter_content.return_value = iter([body])
    return result


def client(*responses):
    value = Mock()
    value.headers = {}
    value.request.side_effect = list(responses)
    return value


def completed(url='https://storage.googleapis.com/test-output?signature=private-test-value'):
    return response(data={'id': 'saved-generation', 'status': 'completed',
                          'content_url': url, 'content_mime_type': 'video/mp4'})


class AvatarAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.portrait = self.root/'portrait.png'
        # A synthetic test image, never represented as the user's portrait.
        Image.new('RGB', (64, 64), 'navy').save(self.portrait)
        self.audio = self.root/'slice.wav'
        with wave.open(str(self.audio), 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(48000)
            audio.writeframes(b'\x00' * (48000*4*2))
        self.meta = {'duration': 4, 'slice_sha256': hashlib.sha256(self.audio.read_bytes()).hexdigest()}
        self.journal = LocalJournal(self.root/'journal')
        self.output = self.root/'avatar.mp4'
        self.environment_patch = patch.dict(os.environ, {'ELEVENLABS_API_KEY': 'mock-key-never-forward'}, clear=True)
        self.environment_patch.start()
        self.addCleanup(self.environment_patch.stop)
        self.probe_patch = patch('automation.avatar.probe', side_effect=self.metadata)
        self.probe = self.probe_patch.start()
        self.addCleanup(self.probe_patch.stop)

    def metadata(self, path):
        if Path(path) == self.audio:
            return {'format': {'duration': '4', 'format_name': 'wav'},
                    'streams': [{'codec_type': 'audio', 'duration': '4'}]}
        return {'format': {'duration': '4', 'format_name': 'mov,mp4,m4a,3gp,3g2,mj2'},
                'streams': [{'codec_type': 'video', 'duration': '4', 'width': 720, 'height': 1280}]}

    def create(self, **kwargs):
        return avatar.create_avatar(self.portrait, self.audio, self.meta, self.journal, self.output, **kwargs)

    def new_api(self, terminal=None):
        return client(response(data={'generations': []}),
                      response(data={'id': 'saved-generation', 'status': 'pending'}),
                      terminal or completed())

    def test_creator_gate_prevents_paid_post_and_receipt(self):
        api = client(response(402))
        with patch('automation.avatar.session', return_value=api):
            with self.assertRaisesRegex(PipelineError, 'requires Pro'):
                self.create()
        self.assertEqual(api.request.call_count, 1)
        self.assertEqual(api.request.call_args.args[0], 'GET')
        self.assertEqual(list((self.root/'journal').glob('*.json')), [])

    def test_exact_photo_and_audio_sent_once_and_download_has_no_auth(self):
        api, cdn = self.new_api(), client(response())
        with patch('automation.avatar.session', side_effect=[api, cdn]) as factory:
            self.assertEqual(self.create(), self.output)
            self.assertEqual(self.create(), self.output)
        self.assertEqual(factory.call_count, 2)
        posts = [call for call in api.request.call_args_list if call.args[0] == 'POST']
        self.assertEqual(len(posts), 1)
        payload = posts[0].kwargs['json']
        self.assertEqual(payload['model_id'], 'creatify-aurora')
        self.assertEqual(base64.b64decode(payload['audio']['content_base64']), self.audio.read_bytes())
        self.assertEqual(base64.b64decode(payload['image']['content_base64']), self.portrait.read_bytes())
        self.assertEqual(cdn.headers, {})
        self.assertNotIn('headers', cdn.request.call_args.kwargs)
        self.assertFalse(cdn.request.call_args.kwargs['allow_redirects'])
        state_text = next((self.root/'journal').glob('*.json')).read_text()
        self.assertNotIn('signature', state_text)
        self.assertNotIn('mock-key', state_text)
        state = json.loads(state_text)
        self.assertEqual(state['generation']['response'], {'id': 'saved-generation'})
        self.assertEqual(state['download']['sha256'], hashlib.sha256(self.output.read_bytes()).hexdigest())

    def test_timeout_resumes_paid_receipt_without_another_post(self):
        first = self.new_api()
        second, cdn = client(completed()), client(response())
        with patch('automation.avatar.session', side_effect=[first, second, cdn]):
            with self.assertRaisesRegex(PipelineError, 'still pending'):
                self.create(timeout=0)
            self.assertEqual(self.create(), self.output)
        self.assertEqual([c.args[0] for c in first.request.call_args_list], ['GET', 'POST'])
        self.assertEqual([c.args[0] for c in second.request.call_args_list], ['GET'])

    def test_ambiguous_submission_does_not_resubmit(self):
        import requests
        first = client(response(data={'generations': []}), requests.Timeout('private request data'))
        second = client()
        with patch('automation.avatar.session', side_effect=[first, second]):
            with self.assertRaisesRegex(PipelineError, 'Network request failed') as caught:
                self.create()
            self.assertNotIn('private request data', str(caught.exception))
            with self.assertRaisesRegex(PipelineError, 'resubmission blocked'):
                self.create()
        second.request.assert_not_called()

    def test_failed_generation_keeps_id_without_logging_provider_message(self):
        failed = response(data={'id': 'saved-generation', 'status': 'failed',
                                'failure_reason': 'moderated', 'error_message': 'private-provider-message'})
        first, second = self.new_api(failed), client(failed)
        with patch('automation.avatar.session', side_effect=[first, second]):
            for _ in range(2):
                with self.assertRaisesRegex(PipelineError, 'moderated') as caught:
                    self.create()
                self.assertNotIn('private-provider-message', str(caught.exception))
        self.assertEqual([c.args[0] for c in second.request.call_args_list], ['GET'])

    def test_wrong_speech_hash_prevents_all_network(self):
        self.meta['slice_sha256'] = '0'*64
        with patch('automation.avatar.session') as factory:
            with self.assertRaisesRegex(PipelineError, 'speech hash differs'):
                self.create()
            factory.assert_not_called()

    def test_nonimage_or_animated_portrait_is_rejected(self):
        self.portrait.write_bytes(b'not an image')
        with patch('automation.avatar.session') as factory:
            with self.assertRaisesRegex(PipelineError, 'verify the user portrait'):
                self.create()
            factory.assert_not_called()
        Image.new('RGB', (64, 64), 'navy').save(self.portrait, save_all=True,
            append_images=[Image.new('RGB', (64, 64), 'red')], duration=100, loop=0)
        with patch('automation.avatar.session') as factory:
            with self.assertRaisesRegex(PipelineError, 'one real PNG or JPEG'):
                self.create()
            factory.assert_not_called()

    def test_wrong_audio_duration_is_rejected_before_network(self):
        self.meta['duration'] = 5
        with patch('automation.avatar.session') as factory:
            with self.assertRaisesRegex(PipelineError, 'unmodified WAV/MP3'):
                self.create()
            factory.assert_not_called()

    def test_unsafe_output_urls_rejected_before_download(self):
        urls = ['http://example.com/a.mp4', 'https://user:password@example.com/a.mp4',
                'https://127.0.0.1/a.mp4', 'https://127.1/a.mp4', 'https://[::1]/a.mp4',
                'https://localhost./a.mp4', 'https://metadata.google.internal/a.mp4',
                'https://example.com:8443/a.mp4', 'https://example.com/a.mp4#fragment']
        for url in urls:
            with self.subTest(url=url), patch('automation.avatar.session') as factory:
                result = {'content_url': url, 'content_mime_type': 'video/mp4'}
                with self.assertRaises(PipelineError):
                    avatar._download(result, self.output, 4, self.journal, 'job', {})
                factory.assert_not_called()

    def test_cdn_redirect_is_not_followed_or_logged(self):
        api, cdn = self.new_api(), client(response(302))
        with patch('automation.avatar.session', side_effect=[api, cdn]):
            with self.assertRaisesRegex(PipelineError, 'HTTP 302') as caught:
                self.create()
        self.assertNotIn('signature', str(caught.exception))
        self.assertNotIn('private-test-value', str(caught.exception))
        self.assertFalse(cdn.request.call_args.kwargs['allow_redirects'])
        self.assertEqual(cdn.headers, {})

    def test_nonvideo_content_type_and_oversize_download_are_rejected(self):
        for invalid in [response(content_type='text/html'), response(body=b'x'*100)]:
            with self.subTest(content_type=invalid.headers['Content-Type']):
                api, cdn = self.new_api(), client(invalid)
                with patch('automation.avatar.session', side_effect=[api, cdn]), \
                        patch('automation.avatar.MAX_OUTPUT_BYTES', 50):
                    with self.assertRaises(PipelineError):
                        self.create()
                self.assertFalse(self.output.exists())
                self.assertEqual(list(self.root.glob('.avatar-*')), [])
                # Distinct test operation; never reset a real production journal.
                for p in (self.root/'journal').glob('*.json'):
                    p.unlink()

    def test_short_output_does_not_replace_or_mark_downloaded(self):
        api, cdn = self.new_api(), client(response())
        original = self.metadata
        def metadata(path):
            result = original(path)
            if Path(path) != self.audio:
                result['streams'][0]['duration'] = '3'
            return result
        self.probe.side_effect = metadata
        with patch('automation.avatar.session', side_effect=[api, cdn]):
            with self.assertRaisesRegex(PipelineError, 'does not cover'):
                self.create()
        self.assertFalse(self.output.exists())
        state = json.loads(next((self.root/'journal').glob('*.json')).read_text())
        self.assertNotIn('download', state)
        self.assertEqual(state['generation']['status'], 'received')

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
    def test_real_video_is_probed_after_credential_free_download(self):
        # Stop only the probe patch for a real container/duration verification.
        self.probe_patch.stop()
        clip = self.root/'moving-source.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=90x160:rate=24:duration=4', '-c:v', 'libx264',
                        '-threads', '1', '-preset', 'ultrafast', str(clip)], check=True)
        api, cdn = self.new_api(), client(response(body=clip.read_bytes()))
        with patch.dict(os.environ, {'ELEVENLABS_API_KEY': 'mock-key'}, clear=True), \
                patch('automation.avatar.session', side_effect=[api, cdn]):
            self.assertEqual(self.create(), self.output)
        self.assertEqual(self.output.read_bytes(), clip.read_bytes())


if __name__ == '__main__':
    unittest.main()
