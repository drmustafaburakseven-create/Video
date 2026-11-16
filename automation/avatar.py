"""Optional ElevenLabs Aurora avatar adapter using an existing portrait and voice.

The public Flows API currently requires Pro or above. Availability is checked
before a paid request. This adapter never substitutes a new face or narration.
"""
import base64
import hashlib
from io import BytesIO
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import urlsplit

from PIL import Image

from automation.render import probe
from automation.state import PipelineError, paid_once, request, session

BASE = 'https://api.elevenlabs.io/v1/flows/video'
MODEL = 'creatify-aurora'
VERSION = 1
MAX_INPUT_BYTES = 25 * 1024 * 1024
MAX_OUTPUT_BYTES = 128 * 1024 * 1024


def _client():
    key = os.environ.get('ELEVENLABS_API_KEY')
    if not key:
        raise PipelineError('Missing secure binding: ELEVENLABS_API_KEY')
    client = session()
    client.headers.update({'xi-api-key': key})
    return client


def ensure_available(client=None):
    """Read the account's video API access without submitting a generation."""
    owned = client is None
    client = client or _client()
    try:
        request(client, 'GET', BASE, params={'page_size': 1})
    except PipelineError as error:
        if 'HTTP 402' in str(error):
            raise PipelineError('ElevenLabs avatar API requires Pro or above; no avatar generation was submitted.') from None
        raise
    finally:
        if owned:
            client.close()
    return True


def _input_bytes(path, description):
    path = Path(path)
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_INPUT_BYTES:
        raise PipelineError(f'{description} must be an existing file of at most 25 MB.')
    data = path.read_bytes()
    if not 0 < len(data) <= MAX_INPUT_BYTES:
        raise PipelineError(f'{description} changed while being read.')
    return data


def _inputs(portrait, audio, metadata):
    portrait, audio = Path(portrait), Path(audio)
    picture = _input_bytes(portrait, 'User portrait')
    speech = _input_bytes(audio, 'Prepared avatar speech')
    try:
        with Image.open(BytesIO(picture)) as source:
            kind = source.format
            frames = getattr(source, 'n_frames', 1)
            if kind not in ['PNG', 'JPEG'] or frames != 1:
                raise PipelineError('Avatar portrait must be one real PNG or JPEG image.')
            source.verify()
    except PipelineError:
        raise
    except Exception:
        raise PipelineError('Unable to verify the user portrait image.') from None
    duration = metadata.get('duration')
    if (isinstance(duration, bool) or not isinstance(duration, (int, float))
            or not math.isfinite(duration) or duration <= 0):
        raise PipelineError('Avatar request duration must be a positive finite number.')
    speech_hash = hashlib.sha256(speech).hexdigest()
    if metadata.get('slice_sha256') != speech_hash:
        raise PipelineError('Avatar speech hash differs from the exact prepared slice.')
    try:
        media = probe(audio)
        audio_stream = next(s for s in media['streams'] if s['codec_type'] == 'audio')
        seconds = float(media['format']['duration'])
        container = media['format']['format_name']
    except Exception:
        raise PipelineError('Unable to verify prepared avatar speech.') from None
    if (not audio_stream or container not in ['wav', 'mp3'] or not math.isfinite(seconds)
            or abs(seconds-duration) > 0.05):
        raise PipelineError('Avatar speech must be the unmodified WAV/MP3 slice of the requested duration.')
    return picture, speech, ('image/png' if kind == 'PNG' else 'image/jpeg'), (
        'audio/wav' if container == 'wav' else 'audio/mpeg')


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value):
        raise PipelineError('ElevenLabs returned an invalid generation ID; automatic resubmission is blocked.')
    return value


def _download_url(value):
    if not isinstance(value, str) or any(c.isspace() for c in value):
        raise PipelineError('Avatar output URL is invalid.')
    try:
        parts = urlsplit(value)
        host = (parts.hostname or '').rstrip('.').lower()
        if (parts.scheme != 'https' or parts.username is not None or parts.password is not None
                or parts.port not in [None, 443] or parts.fragment or not host
                or host == 'localhost' or host.endswith(('.localhost', '.local', '.internal'))):
            raise ValueError
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if ('.' not in host or not re.fullmatch(r'[A-Za-z0-9.-]+', host)
                    or re.fullmatch(r'[0-9.]+', host)):
                raise ValueError
        else:
            if not address.is_global:
                raise ValueError
    except ValueError:
        raise PipelineError('Avatar output must use a public HTTPS URL without user credentials.') from None
    return value


def _check_video(path, duration):
    try:
        media = probe(path)
        video = next(s for s in media['streams'] if s['codec_type'] == 'video')
        seconds = float(video.get('duration', media['format']['duration']))
        container = media['format']['format_name'].split(',')
    except Exception:
        raise PipelineError('Downloaded avatar is not a readable video.') from None
    if (not math.isfinite(seconds) or seconds+0.001 < duration or 'mp4' not in container
            or int(video.get('width', 0)) <= 0 or int(video.get('height', 0)) <= 0):
        raise PipelineError('Downloaded avatar does not cover the requested speech interval.')


def _download(result, output, duration, journal, name, state):
    if result.get('content_mime_type') != 'video/mp4':
        raise PipelineError('ElevenLabs avatar output is not an MP4 video.')
    url = _download_url(result.get('content_url'))
    # Do not forward the ElevenLabs client, xi-api-key, cookies or Authorization.
    download = session()
    response = temporary = None
    try:
        response = request(download, 'GET', url, stream=True)
        if response.headers.get('Content-Type', '').split(';', 1)[0].lower().strip() != 'video/mp4':
            raise PipelineError('Avatar download returned an unexpected content type.')
        length = response.headers.get('Content-Length')
        if length is not None:
            try:
                if not 0 < int(length) <= MAX_OUTPUT_BYTES:
                    raise ValueError
            except ValueError:
                raise PipelineError('Avatar download has an invalid or excessive size.') from None
        total = 0
        with tempfile.NamedTemporaryFile(dir=output.parent, suffix='.mp4', prefix='.avatar-', delete=False) as target:
            temporary = Path(target.name)
            for chunk in response.iter_content(chunk_size=1024*1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_OUTPUT_BYTES:
                    raise PipelineError('Avatar download exceeded its size limit.')
                target.write(chunk)
        if total == 0:
            raise PipelineError('Avatar download was empty.')
        _check_video(temporary, duration)
        state['download'] = {'sha256': hashlib.sha256(temporary.read_bytes()).hexdigest()}
        journal.save(name, state)
        temporary.replace(output)
    except PipelineError:
        raise
    except Exception:
        raise PipelineError('Avatar download failed; the saved generation can be resumed without resubmission.') from None
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
        if response is not None:
            response.close()
        download.close()


def create_avatar(portrait, audio, requestmeta, journal, output, *, timeout=1800, poll_seconds=10):
    """Return a verified MP4, or preserve its paid receipt for a later resume.

    ``output`` is the desired MP4 path. ``requestmeta`` is the corresponding
    entry from avatar-requests.json. No face/speech synthesis fallback is used.
    """
    if not isinstance(requestmeta, dict):
        raise PipelineError('Use the prepared avatar request metadata.')
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or timeout < 0
            or isinstance(poll_seconds, bool) or not isinstance(poll_seconds, (int, float))
            or not math.isfinite(poll_seconds) or not 0 < poll_seconds <= 30):
        raise PipelineError('Avatar polling needs a finite timeout and a 1–30 second polling interval.')
    picture, speech, picture_mime, audio_mime = _inputs(portrait, audio, requestmeta)
    identity = json.dumps([MODEL, VERSION, hashlib.sha256(picture).hexdigest(),
                           hashlib.sha256(speech).hexdigest(), '720p'])
    name = 'avatar-'+hashlib.sha256(identity.encode()).hexdigest()[:24]
    state = journal.load(name)
    output = Path(output)
    if output.suffix.lower() != '.mp4' or output.is_symlink():
        raise PipelineError('Avatar output must be a regular MP4 path.')
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        if (not output.is_file() or hashlib.sha256(output.read_bytes()).hexdigest()
                != state.get('download', {}).get('sha256')):
            raise PipelineError('Existing avatar output does not match this portrait and speech; use another output path.')
        _check_video(output, requestmeta['duration'])
        return output
    client = _client()
    try:
        if 'generation' not in state:
            ensure_available(client)

        def submit():
            result = request(client, 'POST', BASE, json={
                'model_id': MODEL, 'resolution': '720p',
                'image': {'type': 'inline_base64', 'content_base64': base64.b64encode(picture).decode(), 'mime_type': picture_mime},
                'audio': {'type': 'inline_base64', 'content_base64': base64.b64encode(speech).decode(), 'mime_type': audio_mime},
            }).json()
            if result.get('status') != 'pending':
                raise PipelineError('Unexpected avatar submission response; automatic resubmission is blocked.')
            return {'id': _identifier(result.get('id'))}

        receipt = paid_once(journal, name, state, 'generation', submit)
        identifier = _identifier(receipt.get('id'))
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            result = request(client, 'GET', BASE+'/'+identifier).json()
            if result.get('id') != identifier:
                raise PipelineError('Avatar status response does not match the saved generation.')
            status = result.get('status')
            if status == 'completed':
                _download(result, output, requestmeta['duration'], journal, name, state)
                return output
            if status == 'failed':
                reason = result.get('failure_reason')
                if reason not in ['timeout', 'model_error', 'moderated', 'invalid_parameters',
                                  'dependency_failed', 'charging_failed', 'internal_error']:
                    reason = 'unspecified'
                raise PipelineError(f'Avatar generation failed ({reason}); saved receipt retained, no automatic replacement.')
            if status not in ['pending', 'generating']:
                raise PipelineError('Avatar generation returned an unknown status; saved receipt retained.')
            time.sleep(min(poll_seconds, max(0, deadline-time.monotonic())))
        raise PipelineError('Avatar generation is still pending; rerun to poll its saved ID without resubmitting.')
    finally:
        client.close()
