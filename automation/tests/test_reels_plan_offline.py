"""The topic and Google prompts must work on a bare Python installation."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

STUDIO = Path(__file__).resolve().parents[2] / 'reels-studyosu'


class OfflinePlanTests(unittest.TestCase):
    def test_bare_python_reproduces_the_example_and_preserves_speaker_turns(self):
        source = STUDIO / 'konular' / 'uyku-rutini.json'
        plan = json.loads(source.read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp)
            subprocess.run([sys.executable, '-I', '-S', STUDIO / 'studyo.py',
                            'plan', source, dest], check=True)
            for example in (STUDIO / 'ornek').iterdir():
                self.assertEqual((dest / example.name).read_bytes(), example.read_bytes())
            intro = (dest / 'google-giris.txt').read_text(encoding='utf-8')
            outro = (dest / 'google-cikis.txt').read_text(encoding='utf-8')
            self.assertLess(intro.index(plan['question']), intro.index(plan['answer']))
            self.assertIn(plan['outro'], outro)
            self.assertNotIn(plan['question'], outro)
