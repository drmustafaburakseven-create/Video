"""Pexels review candidates and attributed local imports for hybrid videos.

Search results are footage candidates, not medical suitability decisions.
Only the Pexels API receives PEXELS_API_KEY; public video downloads use a
separate unauthenticated session and the exact videos.pexels.com hostname.
"""
import fcntl
import math
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit

import requests

from automation.media import _read_catalog, _write_catalog, digest, import_media
from automation.render import probe
from automation.state import PipelineError, request, session

ROOT = Path(__file__).resolve().parent
API = 'https://api.pexels.com/videos/search'
LICENSE = 'https://www.pexels.com/license/'
MAX_BYTES = 100_000_000


def _positive(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value > 0)


def _url(value, hosts, *, mp4=False):
    if not isinstance(value, str) or any(c.isspace() for c in value):
        raise PipelineError('Invalid Pexels media URL.')
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme == 'https' and parsed.hostname in hosts
                 and parsed.port in (None, 443) and not parsed.username
                 and not parsed.password and not parsed.fragment
                 and (not mp4 or parsed.path.lower().endswith('.mp4')))
    except ValueError:
        valid = False
    # An exact public provider hostname allowlist also excludes IP literals,
    # localhost, lookalike subdomains and user-controlled download hosts.
    if not valid:
        raise PipelineError('Pexels media must use an approved HTTPS provider hostname.')
    return value


def _fits(width, height, orientation):
    if type(width) is not int or type(height) is not int:
        return False
    if orientation == 'landscape':
        return width > height >= 720
    return orientation == 'portrait' and height > width >= 720


def _candidate(value):
    if not isinstance(value, dict):
        raise PipelineError('Invalid Pexels candidate.')
    identifier = value.get('provider_id')
    if type(identifier) is not int or not 0 < identifier < 10**19:
        raise PipelineError('Invalid Pexels video identity.')
    asset_id = f'pexels-{identifier}'
    if value.get('asset_id') != asset_id or value.get('provider') != 'pexels':
        raise PipelineError('Pexels candidate identity does not match its asset ID.')
    source = _url(value.get('source_url'), {'www.pexels.com', 'pexels.com'})
    if not re.fullmatch(r'/video/(?:[^/]+-)?'+str(identifier)+r'/?', urlsplit(source).path):
        raise PipelineError('The Pexels source page must match its video ID.')
    _url(value.get('download_url'), {'videos.pexels.com'}, mp4=True)
    creator = value.get('creator')
    if (not isinstance(creator, dict) or not isinstance(creator.get('name'), str)
            or not creator['name'].strip() or len(creator['name']) > 200):
        raise PipelineError('Pexels candidates need their original creator attribution.')
    if creator.get('url'):
        _url(creator['url'], {'www.pexels.com', 'pexels.com'})
    if value.get('license_url') != LICENSE:
        raise PipelineError('Pexels candidates must preserve the provider license reference.')
    minimum = value.get('minimum_duration', 4)
    if not _positive(minimum) or not _positive(value.get('duration')) or value['duration'] < minimum:
        raise PipelineError('Pexels candidate is shorter than the requested interval.')
    width, height = value.get('width'), value.get('height')
    if not _fits(width, height, value.get('orientation', 'portrait')):
        raise PipelineError('Pexels dimensions must match the requested orientation with at least 720p.')
    return asset_id


def search_clips(query, min_duration=4, *, orientation='portrait'):
    """Return up to ten attributed candidates in the requested orientation; never auto-approve them."""
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 200:
        raise PipelineError('Provide a short stock footage search query.')
    if not _positive(min_duration) or min_duration > 60:
        raise PipelineError('Stock minimum duration must be between zero and 60 seconds.')
    if orientation not in ('portrait', 'landscape'):
        raise PipelineError('Unsupported stock orientation.')
    key = os.environ.get('PEXELS_API_KEY', '').strip()
    if not key:
        raise PipelineError('Missing secure binding: PEXELS_API_KEY')
    client = session()
    try:
        response = request(client, 'GET', API, headers={'Authorization': key},
                           params={'query': query.strip(), 'orientation': orientation, 'per_page': 10})
        try:
            body = response.json()
        except ValueError:
            raise PipelineError('Pexels returned invalid search data.') from None
        finally:
            response.close()
    finally:
        client.close()
    if not isinstance(body, dict) or not isinstance(body.get('videos'), list):
        raise PipelineError('Pexels returned invalid search data.')
    candidates = []
    for video in body['videos'][:10]:
        if not isinstance(video, dict) or not _positive(video.get('duration')) or video['duration'] < min_duration:
            continue
        files = video.get('video_files', [])
        if not isinstance(files, list):
            continue
        options = []
        for media in files:
            if not isinstance(media, dict) or media.get('file_type') != 'video/mp4':
                continue
            width, height = media.get('width'), media.get('height')
            if not _fits(width, height, orientation):
                continue
            try:
                _url(media.get('link'), {'videos.pexels.com'}, mp4=True)
            except PipelineError:
                continue
            options.append(media)
        if not options:
            continue
        # Prefer 1080p, then 720p, before larger files needing more bandwidth.
        selected = min(options, key=lambda f: (f['width'] > 1080, abs(f['width']-1080), f['height']))
        user = video.get('user') if isinstance(video.get('user'), dict) else {}
        candidate = {'asset_id': f'pexels-{video.get("id")}', 'provider': 'pexels',
                     'provider_id': video.get('id'), 'source_url': video.get('url'),
                     'creator': {'name': user.get('name'), 'url': user.get('url')},
                     'license_url': LICENSE, 'duration': video['duration'],
                     'width': selected['width'], 'height': selected['height'],
                     'download_url': selected['link'], 'minimum_duration': min_duration,
                     'requires_review': True}
        if orientation == 'landscape':
            candidate['orientation'] = orientation
        try:
            _candidate(candidate)
        except PipelineError:
            continue
        candidates.append(candidate)
    return candidates


def _existing(root, asset_id, candidate):
    for directory in (root/'media', root/'media/library'):
        if directory.is_symlink():
            raise PipelineError('The stock media directories must not be symbolic links.')
    entry = _read_catalog(root/'media/catalog.json')['assets'].get(asset_id)
    if entry is None:
        return False
    if (not isinstance(entry, dict) or entry.get('kind') != 'stock'
            or entry.get('source_url') != candidate['source_url'] or not isinstance(entry.get('path'), str)):
        raise PipelineError('This stock media ID belongs to different source metadata.')
    path = root/entry['path']
    if path.is_symlink() or path.resolve().parent != (root/'media/library').resolve():
        raise PipelineError('Stock media must stay directly inside media/library.')
    if not path.is_file() or digest(path) != entry.get('sha256'):
        raise PipelineError('Existing stock media is missing or changed; no automatic replacement download.')
    if not _positive(entry.get('source_duration')) or entry['source_duration'] < candidate.get('minimum_duration', 4):
        raise PipelineError('Existing stock media is shorter than the requested interval.')
    return True


def _attribution(root, asset_id, candidate):
    media = root/'media'
    lock_path = media/'.catalog.lock'
    if lock_path.is_symlink():
        raise PipelineError('The stock media lock must not be a symbolic link.')
    with os.fdopen(os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600), 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = _read_catalog(media/'catalog.json')
        entry = data['assets'][asset_id]
        if entry.get('kind') != 'stock' or entry.get('source_url') != candidate['source_url']:
            raise PipelineError('Stock catalog changed during attribution update.')
        entry.update(provider='pexels', provider_id=candidate['provider_id'],
                     creator=candidate['creator'], license_url=LICENSE, requires_review=True)
        _write_catalog(media/'catalog.json', data)


def import_clip(candidate, root=ROOT):
    """Import an explicitly chosen candidate; this does not approve medical use."""
    asset_id = _candidate(candidate)
    root = Path(root).resolve()
    if _existing(root, asset_id, candidate):
        _attribution(root, asset_id, candidate)
        return asset_id
    client = session()
    # This is a new session, not the authenticated API search session.
    client.headers.pop('Authorization', None)
    client.auth = None
    response = None
    try:
        response = request(client, 'GET', candidate['download_url'], stream=True)
        length = response.headers.get('Content-Length')
        if length is not None:
            try:
                declared = int(length)
            except (TypeError, ValueError):
                raise PipelineError('Invalid stock download length.') from None
            if not 0 < declared <= MAX_BYTES:
                raise PipelineError('Stock download exceeds the 100 MB limit or is empty.')
        media_type = response.headers.get('Content-Type', '').split(';')[0].strip().lower()
        if media_type and media_type not in {'video/mp4', 'application/octet-stream'}:
            raise PipelineError('Pexels download did not return a video file.')
        with tempfile.TemporaryDirectory(prefix='pexels-stock-') as temporary:
            path = Path(temporary)/f'{asset_id}.mp4'
            received = 0
            with path.open('wb') as stream:
                try:
                    for chunk in response.iter_content(chunk_size=64*1024):
                        if not chunk:
                            continue
                        received += len(chunk)
                        if received > MAX_BYTES:
                            raise PipelineError('Stock download exceeds the 100 MB limit.')
                        stream.write(chunk)
                except requests.RequestException:
                    raise PipelineError('Stock download interrupted; partial file removed.') from None
            if not received or (length is not None and received != declared):
                raise PipelineError('Stock download was empty or incomplete.')
            info = probe(path)
            video = next((s for s in info.get('streams', []) if s.get('codec_type') == 'video'), {})
            available = float(video.get('duration', info.get('format', {}).get('duration', 0)))
            if (not math.isfinite(available) or available+0.001 < candidate.get('minimum_duration', 4)
                    or not _fits(video.get('width'), video.get('height'), candidate.get('orientation', 'portrait'))):
                raise PipelineError('Downloaded stock video does not match the selected orientation or interval.')
            import_media(path, asset_id, 'stock', root=root, source_url=candidate['source_url'],
                         license_text=f'Pexels License: {LICENSE} Creator: {candidate["creator"]["name"]}')
            _attribution(root, asset_id, candidate)
    finally:
        if response is not None:
            response.close()
        client.close()
    return asset_id
