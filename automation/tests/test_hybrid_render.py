from array import array
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

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


class HybridNarrationDelayTests(unittest.TestCase):
    def test_invalid_delay_is_rejected_before_media_or_encoding(self):
        for delay in [True, False, float('nan'), float('inf'), -0.01, 1.001, '0']:
            with self.subTest(delay=delay), patch('automation.hybrid_render.probe') as inspect, \
                    patch('automation.hybrid_render.subprocess.run') as encode:
                with self.assertRaises(PipelineError):
                    render_hybrid([], 'voice.wav', alignment(), 'unused', narration_delay=delay)
                inspect.assert_not_called()
                encode.assert_not_called()

    def test_zero_delay_keeps_native_avatar_audio_and_captions_at_time_zero(self):
        self._check_delay(0, '00:00:00,000', 0)

    def test_existing_callers_keep_the_quarter_second_delay(self):
        self._check_delay(None, '00:00:00,250', 250)

    def test_complete_last_word_is_kept_in_zero_delay_sixty_second_master(self):
        self._check_delay(0, '00:00:00,000', 0, audio_duration=60, last_word=59.78)

    def test_overrun_or_alignment_past_audio_is_blocked_before_encoding(self):
        for duration, last_word, delay in [(60.1, 59.78, 0), (60, 60, 0),
                                          (59, 59.78, 0), (60, 59.78, 0.25)]:
            with self.subTest(duration=duration, last_word=last_word, delay=delay), \
                    tempfile.TemporaryDirectory() as directory, \
                    patch('automation.hybrid_render.validate_segments', return_value=[]), \
                    patch('automation.hybrid_render.probe', return_value={'format': {'duration': duration}}), \
                    patch('automation.hybrid_render.captions', return_value=last_word), \
                    patch('automation.hybrid_render.subprocess.run') as encode:
                with self.assertRaisesRegex(PipelineError, 'without stretching or truncation'):
                    render_hybrid([], 'voice.wav', alignment(), directory, narration_delay=delay)
                encode.assert_not_called()

    def _check_delay(self, delay, expected_caption_start, delay_ms, audio_duration=58, last_word=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            segments = [{'path': root/'clip.mp4', 'kind': 'avatar', 'start': 0,
                         'duration': 60, 'source_start': 0, 'frames': 1440}]
            final_probe = {'format': {'duration': '60'}, 'streams': [
                {'codec_type': 'video', 'duration': '60', 'width': 720,
                 'height': 1280, 'nb_frames': '1440'},
                {'codec_type': 'audio', 'duration': '60'},
            ]}
            kwargs = {} if delay is None else {'narration_delay': delay}
            timed_text = alignment()
            if last_word is not None:
                timed_text['character_end_times_seconds'][-1] = last_word
            with patch('automation.hybrid_render.validate_segments', return_value=segments), \
                    patch('automation.hybrid_render.probe', side_effect=[
                        {'format': {'duration': str(audio_duration)}}, final_probe]), \
                    patch('automation.hybrid_render.subprocess.run', return_value=Mock(returncode=0)) as encode, \
                    patch('automation.hybrid_render.command'):
                render_hybrid(segments, root/'voice.wav', timed_text, root/'output', **kwargs)
            # Captions are written by the actual alignment implementation.
            first_timing = (root/'output/captions.srt').read_text().splitlines()[1]
            self.assertTrue(first_timing.startswith(expected_caption_start+' --> '))
            args = encode.call_args.args[0]
            filters = args[args.index('-filter_complex')+1]
            self.assertIn(f'[1:a]adelay={delay_ms}:all=1,', filters)
            report = json.loads((root/'output/validation.json').read_text())
            self.assertEqual(report['narration_delay_seconds'], delay_ms/1000)


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
