"""Import local, attributed moving footage into the reusable media catalog."""
import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlsplit

from automation.render import probe
from automation.state import PipelineError

ROOT = Path(__file__).resolve().parent
KINDS = {'stock', 'generated', 'avatar'}
VIDEO_SUFFIXES = {'.mp4', '.mov', '.m4v', '.webm', '.mkv', '.avi'}


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''):
            result.update(block)
    return result.hexdigest()


def _finite(value, *, positive=False):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and (value > 0 if positive else value >= 0))


def _video_duration(path):
    if path.suffix.lower() not in VIDEO_SUFFIXES:
        raise PipelineError('Import a moving video file, not a portrait or still image.')
    media = probe(path)
    video = next((s for s in media.get('streams', []) if s.get('codec_type') == 'video'), None)
    if not video:
        raise PipelineError('The imported file contains no video stream.')
    try:
        duration = float(video.get('duration', media.get('format', {}).get('duration', 0)))
        frames = video.get('nb_frames')
        if frames not in (None, 'N/A') and int(frames) < 2:
            raise PipelineError('The imported file must contain multiple video frames.')
    except (ValueError, TypeError):
        raise PipelineError('Unable to verify the imported video duration.') from None
    if not math.isfinite(duration) or duration <= 0:
        raise PipelineError('Unable to verify the imported video duration.')
    return duration


def _avatar_metadata(path, asset_id, available):
    if not path:
        raise PipelineError('Avatar imports need --avatar-requests from the prepared narration.')
    try:
        requests = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        raise PipelineError('Unable to read avatar-requests.json.') from None
    if not isinstance(requests, list):
        raise PipelineError('Avatar requests must be the list exported by hybrid.prepare.')
    matching = [item for item in requests if isinstance(item, dict) and item.get('asset_id') == asset_id]
    if len(matching) != 1:
        raise PipelineError('Avatar requests must contain exactly one matching asset_id.')
    request = matching[0]
    if not _finite(request.get('timeline_start')) or not _finite(request.get('duration'), positive=True):
        raise PipelineError('Avatar request timing is invalid.')
    if available+0.001 < request['duration']:
        raise PipelineError('Avatar video is shorter than the exported narration slice.')
    result = {key: request[key] for key in ('timeline_start', 'duration')}
    for key in ('narration_sha256', 'audio_sha256'):
        value = request.get(key)
        if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
            raise PipelineError('Avatar request must preserve its narration and audio hashes.')
        result[key] = value
    # Keep the exported slice identity when present; no provider or photo is invented.
    if 'slice_sha256' in request:
        if not isinstance(request['slice_sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', request['slice_sha256']):
            raise PipelineError('Avatar audio slice hash is invalid.')
        result['slice_sha256'] = request['slice_sha256']
    return result


def _safe_directory(path, root):
    if path.is_symlink():
        raise PipelineError('Media directories must not be symbolic links.')
    path.mkdir(parents=True, exist_ok=True)
    if not path.resolve().is_relative_to(root):
        raise PipelineError('Media paths must stay inside the automation directory.')


def _read_catalog(path):
    if path.is_symlink():
        raise PipelineError('The media catalog must not be a symbolic link.')
    try:
        data = json.loads(path.read_text()) if path.exists() else {'version': 1, 'assets': {}}
    except (OSError, ValueError):
        raise PipelineError('Unable to read the media catalog.') from None
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('assets'), dict):
        raise PipelineError('Invalid media catalog.')
    return data


def _write_catalog(path, data):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.catalog-', suffix='.json', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def import_media(file, asset_id, kind, *, source_url=None, license_text=None,
                 avatar_requests=None, root=ROOT):
    """Validate and import footage without downloads or paid service requests."""
    if not isinstance(asset_id, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', asset_id):
        raise PipelineError('Media ID must contain only lowercase letters, digits and hyphens (1–64 characters).')
    if kind not in KINDS:
        raise PipelineError('Media kind must be stock, generated or avatar.')
    source_url = source_url.strip() if isinstance(source_url, str) else ''
    license_text = license_text.strip() if isinstance(license_text, str) else ''
    if kind == 'stock':
        try:
            url = urlsplit(source_url)
            valid_url = (url.scheme == 'https' and url.hostname and not url.username
                         and not url.password and not any(c.isspace() for c in source_url))
        except ValueError:
            valid_url = False
        if not valid_url or not license_text:
            raise PipelineError('Stock footage needs an HTTPS source URL and its license.')
    if avatar_requests and kind != 'avatar':
        raise PipelineError('--avatar-requests applies only to avatar footage.')
    try:
        source = Path(file).resolve(strict=True)
    except (OSError, TypeError):
        raise PipelineError('The source video file does not exist.') from None
    if not source.is_file():
        raise PipelineError('The source must be a local video file.')
    duration = _video_duration(source)
    metadata = _avatar_metadata(avatar_requests, asset_id, duration) if kind == 'avatar' else {}
    file_hash = digest(source)
    root = Path(root).resolve()
    media_root, library = root/'media', root/'media/library'
    _safe_directory(media_root, root)
    _safe_directory(library, root)
    catalog_path, lock_path = media_root/'catalog.json', media_root/'.catalog.lock'
    if lock_path.is_symlink():
        raise PipelineError('The media lock must not be a symbolic link.')
    with os.fdopen(os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600), 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = _read_catalog(catalog_path)
        previous = data['assets'].get(asset_id)
        if previous is not None:
            if not isinstance(previous, dict) or previous.get('sha256') != file_hash:
                raise PipelineError('This media ID already belongs to different footage; choose another ID.')
            if previous.get('kind') != kind:
                raise PipelineError('An existing media ID cannot change its provenance kind.')
            old_path = previous.get('path')
            if not isinstance(old_path, str):
                raise PipelineError('Existing catalog media path is invalid.')
            destination = root/old_path
        else:
            destination = library/(asset_id+source.suffix.lower())
        if destination.is_symlink() or destination.parent.resolve() != library.resolve():
            raise PipelineError('Imported media must stay directly inside media/library without symbolic links.')
        if destination.exists() and (not destination.is_file() or digest(destination) != file_hash):
            raise PipelineError('The destination contains different footage; no existing file was overwritten.')
        if not destination.exists():
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=library, prefix='.import-', delete=False) as stream:
                    temporary = Path(stream.name)
                    with source.open('rb') as original:
                        shutil.copyfileobj(original, stream)
                if digest(temporary) != file_hash:
                    raise PipelineError('The source video changed during import; retry with a stable file.')
                # link fails if another writer creates the destination; never replace footage.
                os.link(temporary, destination)
            finally:
                if temporary:
                    temporary.unlink(missing_ok=True)
        entry = {'path': destination.relative_to(root).as_posix(), 'kind': kind,
                 'sha256': file_hash, 'duration': duration, 'source_duration': duration, **metadata}
        if source_url:
            entry['source_url'] = source_url
        if license_text:
            entry['license'] = license_text
        data['assets'][asset_id] = entry
        _write_catalog(catalog_path, data)
        return entry


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', required=True, type=Path)
    parser.add_argument('--id', required=True, dest='asset_id')
    parser.add_argument('--kind', required=True, choices=sorted(KINDS))
    parser.add_argument('--source-url')
    parser.add_argument('--license', dest='license_text')
    parser.add_argument('--avatar-requests', type=Path)
    args = parser.parse_args(argv)
    try:
        entry = import_media(args.file, args.asset_id, args.kind, source_url=args.source_url,
                             license_text=args.license_text, avatar_requests=args.avatar_requests)
    except (PipelineError, OSError) as error:
        parser.exit(2, f'Media import failed: {error}\n')
    print(f'Imported {args.asset_id}: {entry["path"]}')


if __name__ == '__main__':
    main()
