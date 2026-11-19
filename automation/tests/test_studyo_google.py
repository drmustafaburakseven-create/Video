"""The two-speaker studio submits once per role and resumes the saved Google job."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

STUDIO = Path(__file__).resolve().parents[2] / 'reels-studyosu'
sys.path.insert(0, str(STUDIO))
import doktor
import studyo


class GoogleStudioTest(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((STUDIO/'konular/uyku-rutini.json').read_text())

    def test_reuse_after_interrupted_download(self):
        prompts = studyo.google_prompts(self.plan)
        streams = {'streams': [{'codec_type': 'video', 'width': 1280, 'height': 720,
                                'duration': '10.0'}, {'codec_type': 'audio'}]}
        with tempfile.TemporaryDirectory() as temp, patch.object(doktor, 'Omni') as omni, \
                patch.object(doktor, '_portrait', return_value=(b'photo', 'hash', '.jpg')), \
                patch.object(doktor, 'request') as request, patch.object(doktor, 'probe', return_value=streams):
            root = Path(temp)
            request.return_value.json.return_value = {'id': 'saved-id'}
            download = omni.return_value.download
            download.side_effect = TimeoutError()
            with self.assertRaises(TimeoutError):
                doktor.generate(root, root/'portrait.jpg', prompts)
            download.side_effect = lambda receipt, path: path.write_bytes(path.name.encode())
            doktor.generate(root, root/'portrait.jpg', prompts)
            doktor.generate(root, root/'portrait.jpg', prompts)
            self.assertEqual(request.call_count, 2)
            for role, call in zip(('giris', 'cikis'), request.call_args_list):
                payload = call.kwargs['json']
                self.assertEqual(payload['response_format']['duration'], '10s')
                self.assertEqual(payload['response_format']['aspect_ratio'], '16:9')
                self.assertEqual(payload['input'][1]['text'], prompts[role])
                self.assertTrue((root/f'{role}.mp4').is_file())

    def test_only_full_forty_seconds_of_supported_shots(self):
        self.assertEqual(len(studyo.stock_names(studyo.script(self.plan))), 5)
        for lengths in ([5]*5, [4, 9, 10, 10, 7], [11, 6, 8, 8, 7]):
            with self.subTest(lengths=lengths), self.assertRaises(ValueError):
                studyo.script({**self.plan, 'stock_seconds': lengths})
