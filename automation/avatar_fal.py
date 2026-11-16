"""Pay-per-use Fal Aurora avatar adapter; requires a separately supplied FAL_KEY.

Verified contract: https://fal.ai/models/fal-ai/creatify/aurora/api?platform=http
Files accept data URIs. Queue polling uses the owner/app path, not the model's
endpoint suffix. Availability checks here establish local key presence only.
"""
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import time

from automation.avatar import _check_video, _download, _identifier, _inputs
from automation.state import PipelineError, paid_once, request, session

MODEL = 'fal-ai/creatify/aurora'
BASE = 'https://queue.fal.run'
REQUESTS = BASE+'/fal-ai/creatify/requests/'
VERSION = 1
PROMPT = ('A natural seated presenter speaking the supplied audio. Preserve the person\'s facial '
          'identity, appearance and background. Natural subtle blinking and small head movements; '
          'hands below frame, stable camera, no added text.')


def ensure_available():
    """Check FAL_KEY presence only; this does not verify credit or API entitlement."""
    if not os.environ.get('FAL_KEY', '').strip():
        raise PipelineError('Missing secure binding: FAL_KEY. Fal account access and credits are not configured.')
    return True


def _client():
    ensure_available()
    client = session()
    client.headers.update({'Authorization': 'Key '+os.environ['FAL_KEY'], 'X-Fal-No-Retry': '1'})
    return client


def _json(response):
    try:
        value = response.json()
    except (ValueError, TypeError):
        raise PipelineError('Fal returned invalid JSON; the saved operation must not be resubmitted.') from None
    if not isinstance(value, dict):
        raise PipelineError('Fal returned an unexpected response shape; saved receipt retained.')
    return value


def create_avatar(portrait, audio, requestmeta, journal, output, *, timeout=1800, poll_seconds=10):
    """Generate one exact portrait/speech combination, or resume its saved ID.

    ``output`` is the desired MP4 path. ``requestmeta`` is the matching entry
    from avatar-requests.json. The provider is never switched automatically.
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
                           hashlib.sha256(speech).hexdigest(), '720p', PROMPT])
    name = 'avatar-fal-'+hashlib.sha256(identity.encode()).hexdigest()[:24]
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
        def submit():
            result = _json(request(client, 'POST', BASE+'/'+MODEL, json={
                'image_url': 'data:'+picture_mime+';base64,'+base64.b64encode(picture).decode(),
                'audio_url': 'data:'+audio_mime+';base64,'+base64.b64encode(speech).decode(),
                'resolution': '720p', 'prompt': PROMPT, 'enable_safety_checker': True,
            }))
            if result.get('status') not in ['IN_QUEUE', 'IN_PROGRESS', 'COMPLETED']:
                raise PipelineError('Unexpected Fal submission status; automatic resubmission is blocked.')
            # Response convenience URLs are not followed. The documented fixed
            # owner/app route prevents sending the API key to an arbitrary URL.
            return {'request_id': _identifier(result.get('request_id'))}

        receipt = paid_once(journal, name, state, 'generation', submit)
        identifier = _identifier(receipt.get('request_id'))
        result_url = REQUESTS+identifier
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            status = _json(request(client, 'GET', result_url+'/status'))
            if status.get('request_id') != identifier:
                raise PipelineError('Fal status does not match the saved request ID.')
            value = status.get('status')
            if value == 'COMPLETED':
                if status.get('error') or status.get('error_type'):
                    raise PipelineError('Fal avatar generation failed; saved receipt retained, no automatic replacement.')
                result = _json(request(client, 'GET', result_url))
                video = result.get('video')
                if not isinstance(video, dict):
                    raise PipelineError('Fal returned no video object; saved receipt retained.')
                # The model documents VideoFile.url/content_type. Validate this
                # metadata and the actual CDN MIME/container; do not guess URLs.
                _download({'content_url': video.get('url'), 'content_mime_type': video.get('content_type')},
                          output, requestmeta['duration'], journal, name, state)
                return output
            if value not in ['IN_QUEUE', 'IN_PROGRESS']:
                raise PipelineError('Fal returned an unknown queue status; saved receipt retained.')
            time.sleep(min(poll_seconds, max(0, deadline-time.monotonic())))
        raise PipelineError('Fal avatar is still pending; rerun to poll its saved ID without resubmitting.')
    finally:
        client.close()
