import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from automation.pipeline import prepared_voice
from automation.state import PipelineError
from automation.voice import attach_voice


def sha(data):
    return hashlib.sha256(data).hexdigest()


class VoiceImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'automation'
        (self.root/'drafts').mkdir(parents=True)
        self.target = self.root/'drafts/ek-gida.json'
        self.plan = {'id': 'ek-gida', 'narration': 'Ek gıdaya başlangıç.', 'enabled': False,
                     'shots': [{'kind': 'avatar', 'duration': 4, 'asset_id': 'doctor-intro'}]}
        self.target.write_text(json.dumps(self.plan))
        self.output = Path(self.temp.name)/'video-output/job'
        self.output.mkdir(parents=True)
        (self.output/'plan.json').write_text(json.dumps(self.plan))
        self.audio = b'original paid ElevenLabs audio take'
        (self.output/'voice.mp3').write_bytes(self.audio)
        self.alignment = {'characters': ['E', 'k', '.'],
                          'character_start_times_seconds': [0, 0.1, 0.2],
                          'character_end_times_seconds': [0.1, 0.2, 0.3]}
        self.alignment_bytes = json.dumps(self.alignment).encode()
        (self.output/'alignment.json').write_bytes(self.alignment_bytes)
        self.manifest = {'voice_id': 'doctor-voice', 'narration_sha256': sha(self.plan['narration'].encode()),
                         'audio_sha256': sha(self.audio), 'alignment_sha256': sha(self.alignment_bytes)}
        (self.output/'voice-manifest.json').write_text(json.dumps(self.manifest))
        request = {key: self.manifest[key] for key in ('voice_id', 'narration_sha256', 'audio_sha256')}
        (self.output/'avatar-requests.json').write_text(json.dumps([request]))

    def attach(self):
        return attach_voice(self.output, self.target, root=self.root)

    def test_import_is_portable_for_pipeline_and_preserves_plan(self):
        prepared = self.attach()
        plan = json.loads(self.target.read_text())
        self.assertEqual({k: v for k, v in plan.items() if k != 'prepared_voice'}, self.plan)
        self.assertEqual((self.root/prepared['audio']).read_bytes(), self.audio)
        self.assertEqual((self.root/prepared['alignment']).read_bytes(), self.alignment_bytes)
        with patch('automation.pipeline.ROOT', self.root):
            result = prepared_voice(plan, 'doctor-voice')
        self.assertEqual(base64.b64decode(result['audio_base64']), self.audio)
        self.assertEqual(result['alignment'], self.alignment)
        self.assertEqual(self.attach(), prepared)

    def test_empty_avatar_requests_uses_voice_manifest(self):
        (self.output/'avatar-requests.json').write_text('[]')
        self.assertEqual(self.attach()['voice_id'], 'doctor-voice')

    def test_narration_mismatch_cannot_attach_paid_take(self):
        self.plan['narration'] = 'Başka bir konu.'
        self.target.write_text(json.dumps(self.plan))
        before = self.target.read_bytes()
        with self.assertRaisesRegex(PipelineError, 'narration differs'):
            self.attach()
        self.assertEqual(self.target.read_bytes(), before)
        self.assertFalse((self.root/'assets').exists())

    def test_audio_and_alignment_hashes_are_checked_before_copy(self):
        for name in ('voice.mp3', 'alignment.json'):
            path = self.output/name
            original = path.read_bytes()
            with self.subTest(file=name):
                path.write_bytes(original+b'changed')
                with self.assertRaisesRegex(PipelineError, 'integrity check failed'):
                    self.attach()
                self.assertFalse((self.root/'assets').exists())
                path.write_bytes(original)

    def test_avatar_voice_must_match_manifest(self):
        path = self.output/'avatar-requests.json'
        requests = json.loads(path.read_text())
        requests[0]['voice_id'] = 'another-voice'
        path.write_text(json.dumps(requests))
        with self.assertRaisesRegex(PipelineError, 'different narration or voice'):
            self.attach()

    def test_manifest_is_required_even_with_avatar_requests(self):
        (self.output/'voice-manifest.json').unlink()
        with self.assertRaisesRegex(PipelineError, 'voice manifest'):
            self.attach()

    def test_target_must_be_inside_plans_or_drafts(self):
        outside = self.root/'not-a-plan.json'
        outside.write_text(json.dumps(self.plan))
        with self.assertRaisesRegex(PipelineError, 'automation/plans or automation/drafts'):
            attach_voice(self.output, outside, root=self.root)

    def test_target_symlink_is_rejected(self):
        linked = self.root/'drafts/link.json'
        linked.symlink_to(self.target)
        with self.assertRaisesRegex(PipelineError, 'symbolic links'):
            attach_voice(self.output, linked, root=self.root)

    def test_assets_symlink_cannot_write_outside_repository(self):
        outside = Path(self.temp.name)/'outside'
        outside.mkdir()
        (self.root/'assets').symlink_to(outside)
        with self.assertRaisesRegex(PipelineError, 'symbolic links'):
            self.attach()
        self.assertEqual(list(outside.iterdir()), [])

    def test_existing_different_asset_is_not_overwritten(self):
        prepared = self.attach()
        audio = self.root/prepared['audio']
        audio.write_bytes(b'manually altered')
        before = self.target.read_bytes()
        with self.assertRaisesRegex(PipelineError, 'differs'):
            self.attach()
        self.assertEqual(audio.read_bytes(), b'manually altered')
        self.assertEqual(self.target.read_bytes(), before)

    def test_asset_file_symlink_is_rejected(self):
        prepared = self.attach()
        audio = self.root/prepared['audio']
        audio.unlink()
        audio.symlink_to(self.output/'voice.mp3')
        with self.assertRaisesRegex(PipelineError, 'symbolic links'):
            self.attach()

    def test_failed_atomic_update_keeps_original_plan(self):
        before = self.target.read_bytes()
        with patch('automation.voice.os.replace', side_effect=OSError('simulated disk failure')):
            with self.assertRaises(OSError):
                self.attach()
        self.assertEqual(self.target.read_bytes(), before)
        self.assertEqual(list(self.target.parent.glob('.voice-plan-*')), [])


if __name__ == '__main__':
    unittest.main()
