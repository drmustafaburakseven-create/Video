"""Protect exact timeline coverage and prevent freeze-padding missing footage."""
import hashlib
import json

import pytest

from automation.reel_1080 import validate_audio_timeline, validate_segments
from automation.state import PipelineError


def metadata(path):
    return {'streams': [{'codec_type': 'video', 'codec_name': 'h264', 'duration': '15'}],
            'format': {'duration': '15'}}


@pytest.fixture
def scenes(tmp_path):
    source = tmp_path/'source.mp4'
    source.write_bytes(b'reviewed test bytes')
    return [{'path': source, 'start': i*15, 'end': (i+1)*15} for i in range(4)]


def test_full_timeline(scenes):
    validate_segments(scenes, metadata=metadata)


@pytest.mark.parametrize('edit', [
    {'start': 15.1}, {'start': float('nan')}, {'end': 31}, {'offset': 1},
    {'end': 29.99}, {'offset': -1},
])
def test_reject_invalid_edit_or_missing_live_footage(scenes, edit):
    scenes[1].update(edit)
    with pytest.raises(PipelineError):
        validate_segments(scenes, metadata=metadata)


def test_clinical_rejection_cannot_be_rendered(scenes):
    source = scenes[0]['path']
    source.with_name(source.name+'.clinical-review.json').write_text(json.dumps({
        'status': 'rejected', 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}))
    with pytest.raises(PipelineError, match='rejected'):
        validate_segments(scenes, metadata=metadata)


def test_exact_final_duration_required(scenes):
    scenes[-1]['end'] = 59
    with pytest.raises(PipelineError, match='60 seconds'):
        validate_segments(scenes, metadata=metadata)


@pytest.mark.parametrize('duration,last', [(60.1, 58), (59, 58), (60, 58.51),
                                          (60, float('nan')), (float('inf'), 58)])
def test_prevent_speech_trimming_and_late_final_card(duration, last):
    with pytest.raises(PipelineError):
        validate_audio_timeline(duration, last)


def test_accept_reviewed_complete_audio():
    validate_audio_timeline(60, 58.3)
