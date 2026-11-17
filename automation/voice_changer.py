"""Convert existing speech to the user's ElevenLabs clone without retiming it.

This is speech-to-speech, not TTS. A successful duration check does not establish
perceptual voice similarity or lip sync; those require viewing the result.
"""
import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

import requests

from automation.pipeline import VOICE_ID
from automation.render import command, probe
from automation.state import LocalJournal, PipelineError, paid_once, request, session

MODEL = 'eleven_multilingual_sts_v2'
OUTPUT_FORMAT = 'mp3_44100_128'
VERSION = 1
MAX_INPUT_BYTES = 50_000_000
MAX_OUTPUT_BYTES = 20_000_000
DEFAULT_SETTINGS = {'stability': 0.5, 'similarity_boost': 0.75}


def _sha(content):
    return hashlib.sha256(content).hexdigest()


def _audio_info(path, formats=('wav', 'mp3'), max_seconds=300):
    try:
        media = probe(path)
        streams = media.get('streams', [])
        audio = next(s for s in streams if s.get('codec_type') == 'audio')
        seconds = float(audio.get('duration', media['format']['duration']))
        container = media['format']['format_name']
        if (container not in formats or any(s.get('codec_type') == 'video' for s in streams)
                or not math.isfinite(seconds) or not 0.1 <= seconds <= max_seconds):
            raise ValueError
    except Exception:
        raise PipelineError('Speech must be readable WAV/MP3 audio within the supported duration.') from None
    return {'duration': seconds, 'format': container}


def inspect_audio(path):
    """Validate and snapshot the actual uploaded bytes before any paid request."""
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_INPUT_BYTES:
        raise PipelineError('Speech must be a regular WAV/MP3 file of at most 50 MB.')
    content = path.read_bytes()
    if not 0 < len(content) <= MAX_INPUT_BYTES:
        raise PipelineError('Speech file changed during validation.')
    # Probe these immutable bytes, not a potentially changed original path.
    with tempfile.TemporaryDirectory(prefix='voice-inspect-') as directory:
        snapshot = Path(directory)/'speech.audio'
        snapshot.write_bytes(content)
        info = _audio_info(snapshot)
    return content, info


def _settings(value):
    value = dict(DEFAULT_SETTINGS) if value is None else value
    if not isinstance(value, dict) or not value or set(value)-{'stability', 'similarity_boost', 'style', 'use_speaker_boost'}:
        raise PipelineError('Voice settings contain unsupported fields.')
    for key, setting in value.items():
        if key == 'use_speaker_boost':
            if type(setting) is not bool:
                raise PipelineError('use_speaker_boost must be boolean.')
        elif (type(setting) not in (int, float) or not math.isfinite(setting)
              or not 0 <= setting <= 1):
            raise PipelineError('Voice setting values must be between zero and one.')
    return dict(value)


def _write_once(path, content):
    if path.is_symlink() or path.parent.is_symlink():
        raise PipelineError('Converted audio paths must not be symbolic links.')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not path.is_file() or path.read_bytes() != content:
            raise PipelineError('Existing converted audio differs; use another output path.')
        return
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.mp3', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink() or path.read_bytes() != content:
                raise PipelineError('Converted output changed concurrently; it was not overwritten.') from None
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def _manifest(path, value):
    if path.is_symlink():
        raise PipelineError('Voice manifest must not be a symbolic link.')
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, suffix='.json', delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _submit(content, info, voice, settings):
    key = os.environ.get('ELEVENLABS_API_KEY')
    if not key:
        raise PipelineError('Missing secure binding: ELEVENLABS_API_KEY.')
    client = session()
    response = None
    try:
        mime = 'audio/wav' if info['format'] == 'wav' else 'audio/mpeg'
        response = request(client, 'POST', f'https://api.elevenlabs.io/v1/speech-to-speech/{voice}',
                           headers={'xi-api-key': key}, params={'output_format': OUTPUT_FORMAT},
                           files={'audio': ('speech.'+info['format'], content, mime)},
                           data={'model_id': MODEL, 'voice_settings': json.dumps(settings),
                                 'remove_background_noise': 'false'}, stream=True)
        if response.headers.get('Content-Type', '').split(';', 1)[0].lower() not in ('audio/mpeg', 'audio/mp3'):
            raise PipelineError('Voice Changer returned non-MP3 data; the uncertain request will not be repeated.')
        output = bytearray()
        for block in response.iter_content(65536):
            output.extend(block)
            if len(output) > MAX_OUTPUT_BYTES:
                raise PipelineError('Voice Changer response exceeded 20 MB; saved request retained.')
        if not output:
            raise PipelineError('Voice Changer returned empty audio; saved request retained.')
        return {'audio_base64': base64.b64encode(output).decode(), 'audio_sha256': _sha(output)}
    except requests.RequestException:
        raise PipelineError('Voice Changer transfer failed; inspect the saved receipt before retrying.') from None
    finally:
        if response is not None:
            response.close()
        client.close()


def convert(audio, voice, journal, output, *, max_drift=0.15, voice_settings=None):
    """Return an MP3 path, or keep its receipt/audio on failed timing review.

    ``output.with_suffix('.manifest.json')`` contains source/output durations,
    signed drift and review status. No audio stretching, padding or trimming is
    performed. The same input/model/settings/voice reuse the original paid take.
    """
    if not isinstance(voice, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', voice):
        raise PipelineError('Invalid cloned voice identifier.')
    if type(max_drift) not in (int, float) or not math.isfinite(max_drift) or not 0 <= max_drift <= 1:
        raise PipelineError('Timing tolerance must be between zero and one second.')
    settings = _settings(voice_settings)
    output = Path(output)
    if output.suffix.lower() != '.mp3' or output.is_symlink() or output.parent.is_symlink():
        raise PipelineError('Converted speech requires a regular .mp3 output path.')
    manifest_path = output.with_suffix('.manifest.json')
    if manifest_path.is_symlink():
        raise PipelineError('Voice manifest must not be a symbolic link.')
    content, info = inspect_audio(audio)
    identity = {'version': VERSION, 'source_audio_sha256': _sha(content), 'voice_id': voice,
                'model': MODEL, 'output_format': OUTPUT_FORMAT, 'voice_settings': settings,
                'remove_background_noise': False}
    name = 'voice-change-'+_sha(json.dumps(identity, sort_keys=True).encode())[:24]
    state = journal.load(name)
    if output.exists() and state.get('conversion', {}).get('status') != 'received':
        raise PipelineError('Existing output has no matching conversion receipt; it was not overwritten.')
    if 'conversion' not in state and not os.environ.get('ELEVENLABS_API_KEY'):
        raise PipelineError('Missing secure binding: ELEVENLABS_API_KEY.')
    receipt = paid_once(journal, name, state, 'conversion', lambda: _submit(content, info, voice, settings))
    try:
        converted = base64.b64decode(receipt['audio_base64'], validate=True)
        if not converted or len(converted) > MAX_OUTPUT_BYTES or _sha(converted) != receipt['audio_sha256']:
            raise ValueError
    except (ValueError, TypeError, KeyError):
        raise PipelineError('Saved Voice Changer audio is invalid; it will not be purchased again automatically.') from None
    _write_once(output, converted)
    manifest = {**identity, 'receipt': name, 'source_duration_seconds': info['duration'],
                'output_audio_sha256': _sha(converted), 'max_drift_seconds': max_drift,
                'voice_speed_changed': False, 'lip_sync_review': 'required',
                'voice_similarity_review': 'required', 'timing_check': 'failed'}
    try:
        # MP3 encoder padding may put a valid five-minute input just over 300s.
        # The explicit drift check below still enforces the caller's tolerance.
        converted_info = _audio_info(output, ('mp3',), max_seconds=301)
    except PipelineError:
        manifest['failure'] = 'unreadable_converted_audio'
        _manifest(manifest_path, manifest)
        raise
    drift = converted_info['duration']-info['duration']
    manifest.update(output_duration_seconds=converted_info['duration'], duration_drift_seconds=drift,
                    timing_check='passed' if abs(drift) <= max_drift+1e-9 else 'failed')
    _manifest(manifest_path, manifest)
    if manifest['timing_check'] != 'passed':
        raise PipelineError('Converted speech timing differs from the source; audio and paid receipt are preserved for review.')
    return output


def extract_audio(video, output):
    """Extract a generated video's first audio track to WAV, with no retiming."""
    video, output = Path(video), Path(output)
    if video.is_symlink() or not video.is_file() or output.suffix.lower() != '.wav' or output.is_symlink():
        raise PipelineError('Audio extraction needs a regular source video and .wav destination.')
    if output.exists():
        raise PipelineError('Extraction output already exists; preserve it or choose a new destination.')
    try:
        metadata = probe(video)
        kinds = {s.get('codec_type') for s in metadata['streams']}
        if not {'video', 'audio'}.issubset(kinds):
            raise ValueError
        duration = float(metadata['format']['duration'])
        if not math.isfinite(duration) or not 0.1 <= duration <= 300:
            raise ValueError
    except Exception:
        raise PipelineError('Generated video needs a readable audio track and duration of 0.1–300 seconds.') from None
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix='.speech-extract-') as directory:
        temporary = Path(directory)/'speech.wav'
        command(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(video), '-map', '0:a:0',
                 '-vn', '-c:a', 'pcm_s16le', str(temporary)])
        inspect_audio(temporary)
        try:
            os.link(temporary, output)
        except FileExistsError:
            raise PipelineError('Extraction output appeared concurrently; it was not overwritten.') from None
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio', required=True, type=Path)
    parser.add_argument('--outputdir', type=Path, default=Path('video-output/voice-changer'))
    parser.add_argument('--voice', default=os.environ.get('ELEVENLABS_VOICE_ID') or VOICE_ID)
    parser.add_argument('--check-only', action='store_true', help='Validate source audio only; no provider request.')
    args = parser.parse_args(argv)
    try:
        if args.check_only:
            _, info = inspect_audio(args.audio)
            result = {'status': 'input_validated', 'duration_seconds': info['duration'],
                      'provider_access_verified': False, 'paid_requests': 0}
        else:
            output = convert(args.audio, args.voice, LocalJournal(args.outputdir/'journal'), args.outputdir/'converted.mp3')
            result = {'status': 'converted', 'audio': str(output), 'lip_sync_review': 'required'}
        code = 0
    except Exception as error:
        message = str(error) if isinstance(error, PipelineError) else f'Voice conversion stopped ({type(error).__name__}); receipts preserved.'
        result = {'status': 'blocked', 'message': message}
        code = 2
    print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
