"""Recoverable short speaking proofs; no provider calls in this test suite."""
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
import requests

from automation import gemini_avatar as ga
from automation.state import LocalJournal, PipelineError


def response(value):
    result = Mock(status_code=200)
    result.json.return_value = value
    return result


def wav(path, level=2000, seconds=4):
    with wave.open(str(path), 'wb') as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(8000)
        file.writeframes(int(level).to_bytes(2, 'little', signed=True)*int(8000*seconds))


class SpeakingProofTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.portrait = self.root/'fixture.png'
        Image.new('RGB', (256, 256), 'navy').save(self.portrait)
        self.journal = LocalJournal(self.root/'journal')
        self.output = self.root/'output'
        self.api = Mock()
        self.api.headers = {}
        self.api.request.side_effect = [response({'id': 'saved-id'}), response({'status': 'completed'})]
        self.generator = Mock(client=self.api, base='https://generativelanguage.googleapis.com/v1beta')
        self.generator.download.side_effect = lambda receipt, path, timeout: Path(path).write_bytes(b'native-video')
        patches = [patch.dict(os.environ, {'GEMINI_API_KEY': 'test-google-key', 'ELEVENLABS_API_KEY': 'test-eleven-key'}, clear=True),
                   patch('automation.gemini_avatar.Omni', return_value=self.generator),
                   patch('automation.gemini_avatar._native_media', return_value=4.0),
                   patch('automation.voice_changer.extract_audio', side_effect=lambda video, target: wav(target)),
                   patch('automation.voice_changer.convert', side_effect=self.convert),
                   patch('automation.gemini_avatar.remux', side_effect=self.remux)]
        self.patches = [item.start() for item in patches]
        for item in patches:
            self.addCleanup(item.stop)
        self.converter = self.patches[4]

    def convert(self, source, voice, journal, output):
        output.write_bytes(('converted-'+voice).encode())
        return output

    def remux(self, video, audio, output):
        output.write_bytes(b'proof-'+Path(audio).read_bytes())
        return output

    def create(self, **kwargs):
        return ga.create(self.portrait, 'Ek gıdaya hazır mı?', kwargs.pop('voice', 'own-clone'),
                         self.journal, self.output, **kwargs)

    def test_one_paid_generation_and_conversion_then_cached_proof(self):
        self.api.request.side_effect = [response({'id': 'saved-id'}), response({'status': 'in_progress'})]
        final = self.create()
        self.assertEqual(self.create(), final)
        self.assertEqual(self.api.request.call_count, 2)
        self.converter.assert_called_once()
        sent = self.api.request.call_args_list[0].kwargs['json']
        self.assertEqual(sent['response_format']['duration'], '4s')
        self.assertEqual(sent['input'][0]['type'], 'image')
        self.assertNotIn('audio', {item['type'] for item in sent['input']})
        manifest = json.loads(final.with_name('proof-manifest.json').read_text())
        self.assertFalse(manifest['original_tts_used'])
        self.assertFalse(manifest['generated_speech_text_verified'])
        self.assertFalse(manifest['full_reels_created'])
        self.assertEqual(manifest['lip_sync_review'], 'required')
        provider_status = json.loads((final.parent.parent/'provider-status.json').read_text())
        self.assertEqual(provider_status, {'status': 'completed', 'provider_codes': []})
        for path in self.journal.root.glob('*.json'):
            self.assertEqual(json.loads(path.read_text())['operation_status'], provider_status)
            self.assertNotIn('test-google-key', path.read_text())
            self.assertNotIn('test-eleven-key', path.read_text())

    def test_failed_resource_exhausted_receipt_never_buys_replacement(self):
        failure = {'status': 'failed', 'errors': [{'code': 'RESOURCE_EXHAUSTED',
                                                 'message': 'private provider response'}]}
        self.api.request.side_effect = [response({'id': 'saved-id'}), response(failure), response(failure)]
        for _ in range(2):
            with self.assertRaisesRegex(PipelineError, 'RESOURCE_EXHAUSTED'):
                self.create()
        self.assertEqual([c.args[0] for c in self.api.request.call_args_list], ['POST', 'GET', 'GET'])
        self.generator.download.assert_not_called()
        self.converter.assert_not_called()
        report = next(self.output.glob('*/provider-status.json')).read_text()
        self.assertNotIn('private provider response', report)

    def test_uncertain_submission_preserves_intent_and_does_not_retry(self):
        self.api.request.side_effect = requests.Timeout('sensitive request content')
        with self.assertRaisesRegex(PipelineError, 'Network request failed'):
            self.create()
        with self.assertRaisesRegex(PipelineError, 'resubmission blocked'):
            self.create()
        self.api.request.assert_called_once()
        self.converter.assert_not_called()

    def test_explicit_named_attempt_does_not_overwrite_failed_original(self):
        failure = response({'status': 'failed', 'errors': [{'code': 'RESOURCE_EXHAUSTED'}]})
        self.api.request.side_effect = [response({'id': 'original'}), failure,
                                       response({'id': 'after-account-change'}), response({'status': 'completed'})]
        with self.assertRaises(PipelineError):
            self.create()
        final = self.create(attempt='after-billing-change')
        self.assertEqual(self.create(attempt='after-billing-change'), final)
        receipts = [json.loads(p.read_text())['clip']['response']['interaction_id']
                    for p in self.journal.root.glob('*.json')]
        self.assertCountEqual(receipts, ['original', 'after-account-change'])
        self.assertEqual([c.args[0] for c in self.api.request.call_args_list].count('POST'), 2)

    def test_voice_change_reuses_original_gemini_video(self):
        first = self.create()
        second = self.create(voice='second-owned-clone')
        self.assertNotEqual(first, second)
        self.assertEqual(self.api.request.call_count, 2)
        self.assertEqual(self.generator.download.call_count, 1)
        self.assertEqual(self.converter.call_count, 2)
        self.patches[3].assert_called_once()

    def test_conversion_failure_reuses_checkpointed_native_video_and_audio(self):
        self.converter.side_effect = PipelineError('Conversion stopped; saved source retained.')
        with self.assertRaisesRegex(PipelineError, 'Conversion stopped'):
            self.create()
        self.converter.side_effect = self.convert
        self.assertTrue(self.create().exists())
        self.assertEqual([c.args[0] for c in self.api.request.call_args_list], ['POST', 'GET'])
        self.generator.download.assert_called_once()
        self.patches[3].assert_called_once()

    def test_changed_prepared_audio_is_rejected_before_another_conversion(self):
        self.converter.side_effect = PipelineError('Stop before conversion')
        with self.assertRaises(PipelineError):
            self.create()
        original = next(self.output.glob('*/native-speech.wav'))
        original.write_bytes(b'changed')
        self.converter.reset_mock()
        with self.assertRaisesRegex(PipelineError, 'Prepared native audio differs'):
            self.create()
        self.converter.assert_not_called()

    def test_invalid_portrait_and_missing_voice_key_block_before_purchase(self):
        self.portrait.write_bytes(b'not-an-image')
        with self.assertRaises(PipelineError):
            self.create()
        self.api.request.assert_not_called()
        Image.new('RGB', (256, 256), 'navy').save(self.portrait)
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'available'}, clear=True):
            with self.assertRaisesRegex(PipelineError, 'ELEVENLABS_API_KEY'):
                self.create()
        self.api.request.assert_not_called()

    def test_silent_native_audio_stops_before_voice_conversion(self):
        self.patches[3].side_effect = lambda video, target: wav(target, level=0)
        with self.assertRaisesRegex(PipelineError, 'silent or too quiet'):
            self.create()
        self.converter.assert_not_called()

    def test_missing_native_audio_stops_before_voice_conversion(self):
        self.patches[2].side_effect = PipelineError('No native audio')
        with self.assertRaisesRegex(PipelineError, 'No native audio'):
            self.create()
        self.converter.assert_not_called()

    def test_output_tampering_is_not_silently_overwritten(self):
        final = self.create()
        final.write_bytes(b'edited-by-user')
        with self.assertRaisesRegex(PipelineError, 'differs from its saved receipt'):
            self.create()
        self.assertEqual(final.read_bytes(), b'edited-by-user')
        self.converter.assert_called_once()

    def test_bad_duration_model_and_retry_name_do_not_reach_provider(self):
        for kwargs in [{'duration': 0}, {'duration': True}, {'duration': 11},
                       {'model': '../escape'}, {'attempt': '../escape'}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(PipelineError):
                self.create(**kwargs)
        self.api.request.assert_not_called()


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg is required')
class NativeSpeakingMediaTests(unittest.TestCase):
    def test_audio_checks_and_remux_preserve_encoded_video(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            native, audio, final = directory/'native.mp4', directory/'converted.mp3', directory/'proof.mp4'
            # Synthetic moving test pattern and tone, never represented as a user avatar.
            subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-f', 'lavfi', '-i',
                            'testsrc2=size=128x224:rate=24:duration=3', '-f', 'lavfi', '-i',
                            'sine=frequency=440:sample_rate=44100:duration=3', '-c:v', 'libx264',
                            '-preset', 'ultrafast', '-threads', '1', '-pix_fmt', 'yuv420p',
                            '-c:a', 'aac', str(native)], check=True)
            subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(native), '-vn',
                            '-c:a', 'libmp3lame', '-b:a', '128k', str(audio)], check=True)
            self.assertEqual(ga._native_media(native, 3), 3)
            from automation.voice_changer import extract_audio
            original_wav = directory/'speech.wav'
            extract_audio(native, original_wav)
            self.assertGreater(ga._audible(original_wav), -50)
            source_hash = hashlib.sha256(native.read_bytes()).hexdigest()
            ga.remux(native, audio, final)
            self.assertEqual(ga._video_hash(native), ga._video_hash(final))
            self.assertEqual(hashlib.sha256(native.read_bytes()).hexdigest(), source_hash)
            short = directory/'short.wav'
            wav(short, seconds=1)
            with self.assertRaisesRegex(PipelineError, 'differs from video duration'):
                ga.remux(native, short, directory/'bad.mp4')
            self.assertFalse((directory/'bad.mp4').exists())


if __name__ == '__main__':
    unittest.main()
