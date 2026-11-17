"""Replace one reviewed dialogue turn while preserving the other speaker's PCM."""
from array import array
import hashlib
import math
from pathlib import Path
import subprocess
import wave

from automation.state import PipelineError


def _read(path):
    try:
        with wave.open(str(path), 'rb') as stream:
            if (stream.getnchannels(), stream.getsampwidth(), stream.getcomptype()) != (1, 2, 'NONE'):
                raise ValueError
            return stream.getframerate(), stream.readframes(stream.getnframes())
    except (OSError, ValueError, wave.Error):
        raise PipelineError('Dialogue source must be mono PCM16 WAV.') from None


def _window(start, end, rate, data):
    if (any(type(x) not in (int, float) or not math.isfinite(x) for x in (start, end))
            or not 0 <= start < end <= len(data)/(rate*2)):
        raise PipelineError('Reviewed dialogue turn lies outside the source audio.')
    first, last = round(start*rate)*2, round(end*rate)*2
    if last-first < round(.2*rate)*2:
        raise PipelineError('Dialogue turn is too short for safe speech replacement.')
    return first, last


def _write(path, rate, data):
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise PipelineError('Preserve existing dialogue audio; choose a new output.')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as file, wave.open(file, 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(data)


def extract_turn(source, start, end, output):
    """Boundaries must be reviewed pauses surrounding only the doctor's reply."""
    rate, data = _read(source)
    first, last = _window(start, end, rate, data)
    _write(output, rate, data[first:last])
    return Path(output)


def _decode(path, rate):
    result = subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(path),
                             '-vn', '-ac', '1', '-ar', str(rate), '-f', 's16le', '-'],
                            capture_output=True)
    if result.returncode or not result.stdout:
        raise PipelineError('Converted dialogue turn is unreadable.')
    return result.stdout


def _quiet(data):
    samples = array('h', data)
    return math.sqrt(sum(x*x for x in samples)/max(1, len(samples))) < 100


def replace_turn(source, converted, start, end, output):
    """No retiming: reconcile <=50 ms quiet codec padding, then splice in place.

    Caller must verify wording and speaker boundaries before this operation.
    This is a timeline safeguard, not speaker recognition or a lip-sync model.
    """
    rate, original = _read(source)
    first, last = _window(start, end, rate, original)
    replacement = _decode(converted, rate)
    expected = last-first
    drift = (len(replacement)-expected)/(rate*2)
    if abs(drift) > .05:
        raise PipelineError('Converted turn timing differs; speech will not be stretched.')
    if len(replacement) > expected:
        if not _quiet(replacement[expected:]):
            raise PipelineError('Converted turn has an audible overrun; no speech was cut.')
        replacement = replacement[:expected]
    elif len(replacement) < expected:
        tail = original[first+len(replacement):last]
        if not _quiet(tail):
            raise PipelineError('Converted turn ends before audible source speech.')
        replacement += tail
    # Crossfades are confined to the reviewed turn's quiet margins. Outside
    # this interval the other speaker remains byte-for-byte identical.
    source_samples, voice = array('h', original[first:last]), array('h', replacement)
    fade = min(round(.012*rate), len(voice)//2)
    for i in range(fade):
        weight = i/max(1, fade-1)
        voice[i] = round(source_samples[i]*(1-weight)+voice[i]*weight)
        at = len(voice)-fade+i
        voice[at] = round(voice[at]*(1-weight)+source_samples[at]*weight)
    mixed = original[:first]+voice.tobytes()+original[last:]
    _write(output, rate, mixed)
    return {'source_sha256': hashlib.sha256(original).hexdigest(),
            'output_pcm_sha256': hashlib.sha256(mixed).hexdigest(),
            'turn_seconds': [first/(rate*2), last/(rate*2)],
            'duration_seconds': len(mixed)/(rate*2), 'voice_speed_changed': False,
            'quiet_padding_drift_seconds': drift, 'boundary_fade_ms': 12,
            'outside_turn_pcm_unchanged': mixed[:first] == original[:first]
                                          and mixed[last:] == original[last:]}
