from array import array
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

from automation.dialogue_audio import extract_turn, replace_turn
from automation.state import PipelineError


def write(path, values):
    with wave.open(str(path), 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8000)
        stream.writeframes(array('h', values).tobytes())


def read(path):
    with wave.open(str(path), 'rb') as stream:
        return array('h', stream.readframes(stream.getnframes()))


class DialogueAudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'native.wav'
        self.output = self.root/'mixed.wav'
        self.samples = [1000]*8000+[0]*800+[2000]*6400+[0]*800+[3000]*8000
        write(self.source, self.samples)

    def test_replaces_only_doctor_and_preserves_guest_and_timeline(self):
        reply = self.root/'reply.wav'
        extract_turn(self.source, 1, 2, reply)
        self.assertEqual(list(read(reply)), self.samples[8000:16000])
        converted = array('h', [0]*800+[4000]*6400+[0]*800).tobytes()
        with patch('automation.dialogue_audio._decode', return_value=converted):
            report = replace_turn(self.source, 'clone.mp3', 1, 2, self.output)
        result = list(read(self.output))
        self.assertEqual(result[:8000], self.samples[:8000])
        self.assertEqual(result[16000:], self.samples[16000:])
        self.assertEqual(result[9000:15000], [4000]*6000)
        self.assertEqual(len(result), len(self.samples))
        self.assertTrue(report['outside_turn_pcm_unchanged'])

    def test_audible_overrun_is_not_trimmed(self):
        data = array('h', [0]*8000+[2500]*100).tobytes()
        with patch('automation.dialogue_audio._decode', return_value=data):
            with self.assertRaisesRegex(PipelineError, 'audible overrun'):
                replace_turn(self.source, 'clone.mp3', 1, 2, self.output)
        self.assertFalse(self.output.exists())

    def test_only_short_quiet_codec_padding_may_be_reconciled(self):
        data = array('h', [4000]*8000+[0]*100).tobytes()
        with patch('automation.dialogue_audio._decode', return_value=data):
            report = replace_turn(self.source, 'clone.mp3', 1, 2, self.output)
        self.assertEqual(len(read(self.output)), len(self.samples))
        self.assertAlmostEqual(report['quiet_padding_drift_seconds'], .0125)

    def test_invalid_ranges_and_existing_output_are_preserved(self):
        for start, end in [(-1, 1), (2, 4), (2, 1), (True, 2), (0, float('nan'))]:
            with self.subTest(start=start, end=end), self.assertRaises(PipelineError):
                extract_turn(self.source, start, end, self.output)
        self.output.write_bytes(b'keep existing')
        with self.assertRaisesRegex(PipelineError, 'Preserve existing'):
            extract_turn(self.source, 1, 2, self.output)
        self.assertEqual(self.output.read_bytes(), b'keep existing')
