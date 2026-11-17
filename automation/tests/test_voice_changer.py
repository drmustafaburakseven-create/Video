"""Speech-to-speech recovery and timing checks without live provider requests."""
import base64
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import wave

import requests

from automation import voice_changer
from automation.state import LocalJournal, PipelineError


def response(body=b'converted-mp3', status=200, mime='audio/mpeg'):
    value = Mock(status_code=status)
    value.headers = {'Content-Type': mime}
    value.iter_content.return_value = iter([body])
    return value


class VoiceChangerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.audio = self.root/'native.wav'
        with wave.open(str(self.audio), 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(b'\x01\x00' * 64000)
        self.output = self.root/'converted.mp3'
        self.journal = LocalJournal(self.root/'journal')
        self.key = 'must-never-appear-in-errors-or-receipts'
        environment = patch.dict(os.environ, {'ELEVENLABS_API_KEY': self.key}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.output_duration = 4.04
        self.source_duration = 4
        probe = patch('automation.voice_changer.probe', side_effect=self.metadata)
        self.probe = probe.start()
        self.addCleanup(probe.stop)

    def metadata(self, path):
        suffix = Path(path).suffix
        duration, container = (self.output_duration, 'mp3') if suffix == '.mp3' else (self.source_duration, 'wav')
        return {'streams': [{'codec_type': 'audio', 'duration': str(duration)}],
                'format': {'duration': str(duration), 'format_name': container}}

    def convert(self, **kwargs):
        return voice_changer.convert(self.audio, 'own-clone', self.journal, self.output, **kwargs)

    def api(self, result=None):
        client = Mock()
        client.request.return_value = result if result is not None else response()
        return client

    def test_multipart_uses_original_audio_clone_and_non_pro_output(self):
        client = self.api()
        with patch('automation.voice_changer.session', return_value=client):
            self.assertEqual(self.convert(), self.output)
        call = client.request.call_args
        self.assertEqual(call.args, ('POST', 'https://api.elevenlabs.io/v1/speech-to-speech/own-clone'))
        self.assertEqual(call.kwargs['files']['audio'], ('speech.wav', self.audio.read_bytes(), 'audio/wav'))
        self.assertEqual(call.kwargs['data']['model_id'], 'eleven_multilingual_sts_v2')
        self.assertEqual(call.kwargs['data']['remove_background_noise'], 'false')
        self.assertEqual(call.kwargs['params'], {'output_format': 'mp3_44100_128'})
        self.assertFalse(call.kwargs['allow_redirects'])
        manifest = json.loads(self.output.with_suffix('.manifest.json').read_text())
        self.assertEqual(manifest['timing_check'], 'passed')
        self.assertAlmostEqual(manifest['duration_drift_seconds'], 0.04)
        self.assertFalse(manifest['voice_speed_changed'])
        self.assertEqual(manifest['lip_sync_review'], 'required')
        self.assertNotIn(self.key, next(self.journal.root.glob('*.json')).read_text())
        client.close.assert_called_once()

    def test_completed_response_restores_without_key_or_second_request(self):
        client = self.api()
        with patch('automation.voice_changer.session', return_value=client):
            self.convert()
        self.output.unlink()
        with patch.dict(os.environ, {}, clear=True), patch('automation.voice_changer.session') as factory:
            self.assertEqual(self.convert(), self.output)
        self.assertEqual(self.output.read_bytes(), b'converted-mp3')
        factory.assert_not_called()
        self.assertEqual(client.request.call_count, 1)

    def test_invalid_input_or_missing_key_prevents_submission_and_intent(self):
        with patch('automation.voice_changer.session') as factory:
            with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(PipelineError, 'ELEVENLABS_API_KEY'):
                self.convert()
            self.audio.unlink()
            with self.assertRaisesRegex(PipelineError, 'regular WAV/MP3'):
                self.convert()
        factory.assert_not_called()
        self.assertFalse(list(self.journal.root.glob('*.json')))

    def test_uncertain_request_is_never_repeated_and_error_hides_key(self):
        client = self.api()
        client.request.side_effect = requests.ConnectionError('secret='+self.key)
        with patch('automation.voice_changer.session', return_value=client):
            with self.assertRaises(PipelineError) as first:
                self.convert()
            with self.assertRaisesRegex(PipelineError, 'uncertain'):
                self.convert()
        self.assertNotIn(self.key, str(first.exception))
        self.assertEqual(client.request.call_count, 1)

    def test_provider_rejection_never_echoes_body_or_headers(self):
        denied = response(status=401)
        denied.text = self.key
        denied.headers['Secret'] = self.key
        with patch('automation.voice_changer.session', return_value=self.api(denied)):
            with self.assertRaisesRegex(PipelineError, 'HTTP 401') as error:
                self.convert()
        self.assertNotIn(self.key, str(error.exception))

    def test_drift_failure_keeps_audio_and_receipt_and_does_not_recharge(self):
        self.output_duration = 4.5
        client = self.api()
        with patch('automation.voice_changer.session', return_value=client):
            for _ in range(2):
                with self.assertRaisesRegex(PipelineError, 'timing differs'):
                    self.convert()
        self.assertEqual(client.request.call_count, 1)
        self.assertEqual(self.output.read_bytes(), b'converted-mp3')
        manifest = json.loads(self.output.with_suffix('.manifest.json').read_text())
        self.assertEqual(manifest['timing_check'], 'failed')
        self.assertEqual(manifest['duration_drift_seconds'], 0.5)
        self.assertEqual(next(iter(self.journal.load(manifest['receipt']).values()))['status'], 'received')

    def test_five_minute_input_allows_small_output_encoder_padding(self):
        self.source_duration, self.output_duration = 300, 300.04
        with patch('automation.voice_changer.session', return_value=self.api()):
            self.assertEqual(self.convert(), self.output)
        manifest = json.loads(self.output.with_suffix('.manifest.json').read_text())
        self.assertEqual(manifest['timing_check'], 'passed')

    def test_changed_voice_or_audio_needs_distinct_receipts(self):
        with patch('automation.voice_changer.session', side_effect=[self.api(), self.api(), self.api()]):
            self.convert()
            voice_changer.convert(self.audio, 'second-clone', self.journal, self.root/'second.mp3')
            self.audio.write_bytes(self.audio.read_bytes()+b'new-source')
            voice_changer.convert(self.audio, 'own-clone', self.journal, self.root/'third.mp3')
        self.assertEqual(len(list(self.journal.root.glob('*.json'))), 3)

    def test_changed_settings_use_new_identity_but_no_overwrite_charge(self):
        client = self.api()
        with patch('automation.voice_changer.session', return_value=client):
            self.convert()
            with self.assertRaisesRegex(PipelineError, 'no matching conversion receipt'):
                self.convert(voice_settings={'similarity_boost': 0.9})
        self.assertEqual(client.request.call_count, 1)
        self.assertEqual(self.output.read_bytes(), b'converted-mp3')

    def test_changed_existing_audio_is_not_overwritten(self):
        with patch('automation.voice_changer.session', return_value=self.api()):
            self.convert()
        self.output.write_bytes(b'user-edit')
        with patch('automation.voice_changer.session') as factory, self.assertRaisesRegex(PipelineError, 'differs'):
            self.convert()
        factory.assert_not_called()
        self.assertEqual(self.output.read_bytes(), b'user-edit')

    def test_corrupted_saved_response_is_not_replaced_by_paid_request(self):
        with patch('automation.voice_changer.session', return_value=self.api()):
            self.convert()
        path = next(self.journal.root.glob('*.json'))
        state = json.loads(path.read_text())
        state['conversion']['response']['audio_base64'] = base64.b64encode(b'corrupt').decode()
        path.write_text(json.dumps(state))
        with patch('automation.voice_changer.session') as factory, self.assertRaisesRegex(PipelineError, 'invalid'):
            self.convert()
        factory.assert_not_called()

    def test_invalid_voice_settings_duration_and_paths_block_without_paid_call(self):
        cases = [{'voice_settings': {'similarity_boost': float('nan')}}, {'max_drift': float('inf')},
                 {'voice_settings': {'unrecognized_setting': True}}]
        with patch('automation.voice_changer.session') as factory:
            for kwargs in cases:
                with self.subTest(kwargs=kwargs), self.assertRaises(PipelineError):
                    self.convert(**kwargs)
            self.probe.side_effect = None
            self.probe.return_value = {'streams': [{'codec_type': 'audio'}],
                                       'format': {'duration': '301', 'format_name': 'wav'}}
            with self.assertRaises(PipelineError):
                self.convert()
        factory.assert_not_called()

    def test_check_only_does_not_claim_provider_access(self):
        output = io.StringIO()
        with patch('automation.voice_changer.session') as factory, redirect_stdout(output):
            code = voice_changer.main(['--audio', str(self.audio), '--check-only'])
        self.assertEqual(code, 0)
        self.assertFalse(json.loads(output.getvalue())['provider_access_verified'])
        factory.assert_not_called()


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class NativeVoiceConversionTests(unittest.TestCase):
    def test_real_video_audio_extract_and_mock_conversion_preserve_timing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video, audio, encoded = root/'native.mp4', root/'source.wav', root/'provider.mp3'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=32x32:r=24:d=1',
                            '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1:sample_rate=44100',
                            '-c:v', 'libx264', '-c:a', 'aac', '-t', '1', str(video)], check=True)
            self.assertEqual(voice_changer.extract_audio(video, audio), audio)
            with wave.open(str(audio), 'rb') as source:
                self.assertEqual(source.getsampwidth(), 2)
            original_hash = hashlib.sha256(audio.read_bytes()).hexdigest()
            subprocess.run(['ffmpeg', '-v', 'error', '-i', str(audio), '-c:a', 'libmp3lame', '-b:a', '128k',
                            str(encoded)], check=True)
            client = Mock()
            client.request.return_value = response(encoded.read_bytes())
            with patch.dict(os.environ, {'ELEVENLABS_API_KEY': 'mock-key'}, clear=True), \
                    patch('automation.voice_changer.session', return_value=client):
                final = voice_changer.convert(audio, 'own-clone', LocalJournal(root/'journal'), root/'converted.mp3')
            manifest = json.loads(final.with_suffix('.manifest.json').read_text())
            self.assertEqual(manifest['timing_check'], 'passed')
            self.assertEqual(hashlib.sha256(audio.read_bytes()).hexdigest(), original_hash)
            with self.assertRaisesRegex(PipelineError, 'already exists'):
                voice_changer.extract_audio(video, audio)


if __name__ == '__main__':
    unittest.main()
