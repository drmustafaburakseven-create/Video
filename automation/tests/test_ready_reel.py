"""A ready render must match the script, reviewed files and four real sources."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from automation import publishing, ready_reel
from automation.state import PipelineError
from automation.tests.test_editorial import script


class ReadyReelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.script = script()
        def file(name, content):
            p = self.root/name
            p.write_bytes(content)
            return {'path': name, 'sha256': ready_reel.sha(p)}
        segments = []
        for i, (start, end, role) in enumerate([(0, 15, 'intro'), (15, 22.5, 'body'),
                                                (22.5, 30, 'body'), (30, 37.5, 'body'),
                                                (37.5, 45, 'body'), (45, 60, 'outro')]):
            segments.append({**file(f'{i}.mp4', str(i).encode()), 'start': start, 'end': end, 'role': role})
        self.manifest = {'schema': 'warm-ready-v1', 'profile': 'warm-office-60',
                         'topic_id': self.script['topic_id'], 'narration_sha256': publishing.narration_hash(self.script),
                         'visual_review': 'approved', 'speech_timing_review': 'approved',
                         'segments': segments, 'audio': file('mix.wav', b'mix'),
                         'captions': file('graphics.ass', b'[Script Info]\n'),
                         'fonts': [file('normal.ttf', b'font1'), file('emphasis.ttf', b'font2')],
                         'last_spoken_word': 58.1}
        self.path = self.root/'ready.json'

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self):
        self.path.write_text(json.dumps(self.manifest))
        with patch.object(ready_reel.reel_1080, 'validate_segments'), \
                patch.object(ready_reel, 'probe', return_value={'format': {'duration': '60.0'}}):
            return ready_reel.prepare(self.script, self.path)

    def test_valid_manifest_preserves_absolute_timing(self):
        inputs = self.prepare()
        self.assertEqual(inputs['last_spoken_word'], 58.1)
        self.assertEqual(inputs['segments'][-1]['start'], 45)

    def test_same_file_in_four_body_slots_does_not_count_as_four_sources(self):
        for segment in self.manifest['segments'][2:5]:
            segment.update({key: self.manifest['segments'][1][key] for key in ('path', 'sha256')})
        with self.assertRaisesRegex(PipelineError, 'dört farklı'):
            self.prepare()

    def test_changed_audio_or_caption_bytes_invalidate_review(self):
        for filename in ('mix.wav', 'graphics.ass'):
            path = self.root/filename
            original = path.read_bytes()
            path.write_bytes(original+b'changed')
            with self.subTest(filename=filename), self.assertRaisesRegex(PipelineError, 'değişmiş'):
                self.prepare()
            path.write_bytes(original)

    def test_other_script_unreviewed_inputs_and_cut_ending_are_rejected(self):
        original = copy.deepcopy(self.manifest)
        for field, value in [('narration_sha256', '0'*64), ('visual_review', 'pending'),
                             ('speech_timing_review', 'pending'), ('last_spoken_word', 59.2)]:
            self.manifest = {**copy.deepcopy(original), field: value}
            with self.subTest(field=field), self.assertRaises(PipelineError):
                self.prepare()


if __name__ == '__main__':
    unittest.main()
