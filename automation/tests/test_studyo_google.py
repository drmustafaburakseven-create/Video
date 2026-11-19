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
        streams = {'streams': [{'codec_type': 'video', 'width': 720, 'height': 1280,
                                'duration': '10.0'}, {'codec_type': 'audio'}]}
        with tempfile.TemporaryDirectory() as temp, patch.object(doktor, 'Omni') as omni, \
                patch.object(doktor, '_portrait', return_value=(b'photo', 'hash', '.jpg')), \
                patch.object(doktor, 'request') as request, patch.object(doktor, 'probe', return_value=streams):
            root = Path(temp)
            request.return_value.json.return_value = {'id': 'saved-id'}
            download = omni.return_value.download
            download.side_effect = TimeoutError()
            with self.assertRaises(TimeoutError):
                doktor.generate(root, root/'portrait.jpg', prompts, aspect_ratio=self.plan['aspect_ratio'])
            download.side_effect = lambda receipt, path: path.write_bytes(path.name.encode())
            doktor.generate(root, root/'portrait.jpg', prompts, aspect_ratio=self.plan['aspect_ratio'])
            doktor.generate(root, root/'portrait.jpg', prompts, aspect_ratio=self.plan['aspect_ratio'])
            self.assertEqual(request.call_count, 2)
            for role, call in zip(('giris', 'cikis'), request.call_args_list):
                payload = call.kwargs['json']
                self.assertEqual(payload['model'], doktor.STUDIO_MODEL)
                self.assertEqual(payload['response_format']['duration'], '10s')
                self.assertEqual(payload['response_format']['aspect_ratio'], '9:16')
                self.assertEqual(payload['input'][1]['text'], prompts[role])
                self.assertTrue((root/f'{role}.mp4').is_file())

    def test_saved_old_model_receipt_is_polled_without_new_purchase(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(doktor, 'Omni') as omni, \
                patch.object(doktor, '_portrait', return_value=(b'picture', 'hash', '.jpg')), \
                patch.object(doktor, 'request') as submit:
            root = Path(temp)
            key = doktor.receipt_key(doktor.VEO_MODEL, 'hash', 'my prompt')
            receipt = {'interaction_id': 'original'}
            doktor.LocalJournal(root/'makbuzlar').save(key, {'video': {'status': 'received', 'response': receipt}})
            omni.return_value.download.side_effect = TimeoutError()
            with self.assertRaises(TimeoutError):
                doktor.generate(root, root/'photo.jpg', {'giris': 'my prompt'})
            omni.assert_called_once_with(doktor.VEO_MODEL)
            submit.assert_not_called()

    def test_voice_directions_are_hidden_without_retiming_spoken_characters(self):
        text = '[warm] Bir soru. [firm] Arayın.'
        alignment = {'characters': list(text), 'character_start_times_seconds': list(range(len(text))),
                     'character_end_times_seconds': list(range(1, len(text)+1))}
        clean = studyo.spoken_alignment(alignment, 'Bir soru. Arayın.')
        self.assertEqual(''.join(clean['characters']), 'Bir soru. Arayın.')
        self.assertEqual(clean['character_start_times_seconds'][10], text.index('Arayın'))
        with self.assertRaises(ValueError):
            studyo.spoken_alignment(alignment, 'Başka bir cümle.')

    def test_only_full_forty_seconds_of_supported_shots(self):
        self.assertEqual(len(studyo.stock_names(studyo.script(self.plan))), 5)
        for lengths in ([5]*5, [4, 9, 10, 10, 7], [11, 6, 8, 8, 7]):
            with self.subTest(lengths=lengths), self.assertRaises(ValueError):
                studyo.script({**self.plan, 'stock_seconds': lengths})
