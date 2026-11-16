from array import array
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from automation.hybrid_render import render_hybrid, source_labels, validate_segments
from automation.render import captions, probe
from automation.state import PipelineError


def alignment():
    text = 'Ek gıdaya güvenli başlangıç.'
    return {'characters': list(text),
            'character_start_times_seconds': [i*0.1 for i in range(len(text))],
            'character_end_times_seconds': [(i+1)*0.1 for i in range(len(text))]}


class HybridLabelsTests(unittest.TestCase):
    def test_ai_disclosure_only_covers_generated_and_avatar_intervals(self):
        with tempfile.TemporaryDirectory() as directory:
            captions(alignment(), directory)
            path = Path(directory)/'captions.ass'
            source_labels(path, [
                {'start': 0, 'duration': 4, 'kind': 'avatar'},
                {'start': 4, 'duration': 48, 'kind': 'stock'},
                {'start': 52, 'duration': 8, 'kind': 'generated'},
            ])
            labels = [line for line in path.read_text().splitlines()
                      if line.startswith('Dialogue:') and ',Label,' in line]
            self.assertEqual(len(labels), 2)
            self.assertIn('00:00:00.00,00:00:04.00', labels[0])
            self.assertIn('00:00:52.00,00:01:00.00', labels[1])
            self.assertIn('konuşan avatar', labels[0])
            self.assertNotIn('0:00:00.00,0:01:00.00,Label', path.read_text())

    def test_short_source_is_rejected_before_encoding(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'short.mp4'
            path.write_bytes(b'placeholder')
            metadata = {'format': {'duration': '3'},
                        'streams': [{'codec_type': 'video', 'duration': '3', 'nb_frames': '72'}]}
            with patch('automation.hybrid_render.probe', return_value=metadata):
                with self.assertRaisesRegex(PipelineError, 'insufficient source duration'):
                    validate_segments([{'path': path, 'kind': 'stock', 'start': 0,
                                        'duration': 60, 'source_start': 1}])

    def test_gap_cannot_shift_avatar_relative_to_voice(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'clip.mp4'
            path.write_bytes(b'placeholder')
            metadata = {'format': {'duration': '60'},
                        'streams': [{'codec_type': 'video', 'duration': '60', 'nb_frames': '1440'}]}
            with patch('automation.hybrid_render.probe', return_value=metadata):
                with self.assertRaisesRegex(PipelineError, 'contiguous'):
                    validate_segments([{'path': path, 'kind': 'stock', 'start': 0, 'duration': 30},
                                       {'path': path, 'kind': 'avatar', 'start': 31, 'duration': 30}])

    def test_images_are_not_accepted_as_motion(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'still.png'
            path.write_bytes(b'placeholder')
            with self.assertRaisesRegex(PipelineError, 'not still images'):
                validate_segments([{'path': path, 'kind': 'stock', 'duration': 60}])


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class HybridNativeRenderTests(unittest.TestCase):
    def test_mixed_timeline_preserves_sixty_seconds_and_narration(self):
        # A moving test pattern stands in for licensed/provided footage; it is not
        # a generated avatar or a user-facing completed educational video.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clip, audio = root/'moving.mp4', root/'narration.wav'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                            'testsrc2=size=90x160:rate=24:duration=10', '-c:v', 'libx264',
                            '-preset', 'ultrafast', '-threads', '1', str(clip)], check=True)
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                            'sine=frequency=230:sample_rate=24000:duration=58', str(audio)], check=True)
            kinds = ['avatar', 'stock', 'generated', 'stock', 'stock', 'avatar']
            segments = [{'path': clip, 'kind': kind, 'start': i*10,
                         'duration': 10, 'source_start': 0} for i, kind in enumerate(kinds)]
            output = render_hybrid(segments, audio, alignment(), root/'output')
            result = probe(output)
            self.assertAlmostEqual(float(result['format']['duration']), 60, places=2)
            video = next(s for s in result['streams'] if s['codec_type']=='video')
            self.assertEqual(int(video['nb_frames']), 1440)
            self.assertEqual([video['width'], video['height']], [720, 1280])
            report = json.loads((root/'output/validation.json').read_text())
            self.assertEqual(report['media_seconds'], {'stock': 30, 'generated': 10, 'avatar': 20})
            self.assertFalse(report['voice_speed_changed'])
            self.assertEqual(report['full_decode'], 'passed')
            self.assertIn('Ek gıdaya güvenli başlangıç.', (root/'output/captions.srt').read_text())
            # Inspect the encoded signal, rather than only trusting report flags:
            # narration begins after the caption offset and retains its pitch.
            raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(output), '-t', '1',
                                  '-map', '0:a:0', '-f', 's16le', '-ar', '24000', '-ac', '1', '-'],
                                 check=True, capture_output=True).stdout
            samples = array('h', raw)
            silent, speaking = samples[:4800], samples[7200:21600]
            self.assertLess(sum(abs(s) for s in silent)/len(silent),
                            sum(abs(s) for s in speaking)/len(speaking)*0.01)
            crossings = sum(a <= 0 < b for a, b in zip(speaking, speaking[1:]))
            self.assertAlmostEqual(crossings, 230*0.6, delta=2)


if __name__ == '__main__':
    unittest.main()
