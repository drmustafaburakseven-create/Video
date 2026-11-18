"""Compose one ready hybrid plan with the user's portrait and exact cloned voice."""
import argparse
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re

from PIL import Image

from automation import avatar, avatar_fal, hybrid, media, pipeline
from automation.state import GitHubJournal, LocalJournal, PipelineError

ROOT = Path(__file__).resolve().parent
MAX_PORTRAIT_BYTES = 25 * 1024 * 1024


def _plan_path(value):
    candidate = Path(value)
    if candidate.parent == Path('.'):
        if not re.fullmatch(r'[a-z0-9-]+\.json', candidate.name):
            raise PipelineError('Plan must be a JSON filename from automation/plans or automation/drafts.')
        candidate = ROOT/'plans'/candidate.name
        if not candidate.exists():
            candidate = ROOT/'drafts'/candidate.name
    resolved = candidate.resolve()
    if (candidate.is_symlink() or not resolved.is_file() or resolved.suffix != '.json'
            or resolved.parent not in [(ROOT/'plans').resolve(), (ROOT/'drafts').resolve()]):
        raise PipelineError('Plan must stay inside automation/plans or automation/drafts.')
    return resolved


def _portrait(path):
    path = Path(path)
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_PORTRAIT_BYTES:
        raise PipelineError('Upload your portrait as a PNG/JPEG file of at most 25 MB.')
    content = path.read_bytes()
    if not 0 < len(content) <= MAX_PORTRAIT_BYTES:
        raise PipelineError('Portrait changed during validation.')
    try:
        with Image.open(BytesIO(content)) as image:
            kind = image.format
            width, height = image.size
            if (kind not in ['PNG', 'JPEG'] or getattr(image, 'n_frames', 1) != 1
                    or min(width, height) < 256 or width*height > 20_000_000):
                raise PipelineError('Portrait must be one PNG/JPEG image, at least 256 pixels per side and at most 20 megapixels.')
            image.verify()
    except PipelineError:
        raise
    except Exception:
        raise PipelineError('Unable to read the portrait as a PNG/JPEG image.') from None
    return content, hashlib.sha256(content).hexdigest(), '.png' if kind == 'PNG' else '.jpg'


def _avatar_ids(plan, picture_hash, voice, provider):
    plan = deepcopy(plan)
    narration_hash = hashlib.sha256(plan['narration'].encode()).hexdigest()
    start = 0
    for index, shot in enumerate(plan['shots']):
        if shot['kind'] == 'avatar':
            identity = json.dumps([narration_hash, picture_hash, voice, provider,
                                   index, start, shot['duration']], sort_keys=True)
            shot['asset_id'] = 'doctor-'+hashlib.sha256(identity.encode()).hexdigest()[:32]
        start += shot['duration']
    return plan


def _preflight_media(plan):
    """Check every available file at its true timeline, before any generation."""
    assets = hybrid.catalog(ROOT)
    check = deepcopy(plan)
    missing = []
    for shot in check['shots']:
        if shot['kind'] == 'avatar' and shot['asset_id'] not in assets:
            missing.append(shot['asset_id'])
            # Resolution-only placeholder preserves the timeline. This temporary
            # object is never passed to make(), a provider, or a paid operation.
            shot.pop('asset_id')
            shot['kind'] = 'generated'
    resolved = hybrid.resolve(check, root=ROOT)
    existing = [segment for segment in resolved if segment['kind'] == 'avatar']
    return missing, existing


@contextmanager
def _production_lock(output):
    output.mkdir(parents=True, exist_ok=True)
    handle = None
    try:
        fd = os.open(output/'.production.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        handle = os.fdopen(fd, 'a')
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError):
        if handle:
            handle.close()
        raise PipelineError('Another production is running or the production lock is unavailable; no new request was sent.') from None
    try:
        yield
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def _journal(output):
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        return GitHubJournal(os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_TOKEN'], os.environ['GITHUB_SHA'])
    return LocalJournal(output/'journal')


def produce(plan_path, portrait, provider, output, journal=None):
    """Return the final MP4; never choose unreviewed stock or switch providers.

    Portrait validation checks file integrity/dimensions. Human identity and
    visual lip-sync quality still require inspection of the supplied/result media.
    """
    if provider not in ['fal', 'elevenlabs']:
        raise PipelineError('Choose exactly one avatar provider: fal or elevenlabs.')
    output = Path(output).resolve()
    with _production_lock(output):
        source = _plan_path(plan_path)
        plan = pipeline.load_plan(source)
        if plan.get('format') != 'hybrid-v1':
            raise PipelineError('Portrait production requires a hybrid-v1 plan.')
        hybrid.validate(plan)
        picture, picture_hash, extension = _portrait(portrait)
        voice = os.environ.get('ELEVENLABS_VOICE_ID') or pipeline.VOICE_ID
        if not re.fullmatch(r'[A-Za-z0-9_-]+', voice):
            raise PipelineError('Invalid ElevenLabs voice selection.')
        plan = _avatar_ids(plan, picture_hash, voice, provider)
        if not any(s['kind'] == 'avatar' for s in plan['shots']):
            raise PipelineError('The selected plan has no avatar segment; use automation.pipeline for stock-only production.')
        missing, existing = _preflight_media(plan)
        model = os.environ.get('VEO_MODEL') or pipeline.VEO_MODEL
        journal = journal if journal is not None else _journal(output)
        name = pipeline.job_name(plan, model, voice, False)
        state = journal.load(name)
        from automation.publishing import write as write_social_copy
        write_social_copy(plan, output/name)
        final = output/name/'video.mp4'
        if state.get('complete') and final.is_file():
            if hashlib.sha256(final.read_bytes()).hexdigest() != state.get('video_sha256'):
                raise PipelineError('Completed video was changed; the existing file was not overwritten.')
            return final
        if hybrid.validate(plan)['new_clip_count'] and not os.environ.get('GEMINI_API_KEY', '').strip():
            raise PipelineError('Missing secure binding: GEMINI_API_KEY for the planned new clips.')
        # Existing lip-synced clips must never trigger a different voice take.
        saved = journal.load(hybrid.voice_cache_name(plan, voice)).get('voice', {})
        prepared = pipeline.prepared_voice(plan, voice)
        if existing and not prepared and saved.get('status') != 'received':
            raise PipelineError('The original narration for existing avatar clips is missing; import its voice package before production.')
        adapter = avatar_fal if provider == 'fal' else avatar
        if missing:
            adapter.ensure_available()  # Fal checks key presence only, not credits.
        identity = json.dumps([plan, picture_hash, voice, provider], sort_keys=True, ensure_ascii=False)
        work = output/('production-'+hashlib.sha256(identity.encode()).hexdigest()[:24])
        if work.is_symlink():
            raise PipelineError('Production directory must not be a symbolic link.')
        work.mkdir(parents=True, exist_ok=True)
        snapshot = work/('portrait'+extension)
        if snapshot.is_symlink() or (snapshot.exists() and snapshot.read_bytes() != picture):
            raise PipelineError('Prepared portrait snapshot differs; existing file was not overwritten.')
        if not snapshot.exists():
            snapshot.write_bytes(picture)
        audio, alignment, audio_hash = hybrid.prepare(plan, voice, journal, work)
        del audio, alignment
        if any(segment['asset']['audio_sha256'] != audio_hash for segment in existing):
            raise PipelineError('An existing avatar belongs to a different voice take; no avatar request was sent.')
        requests_path = work/'avatar-requests.json'
        requests = json.loads(requests_path.read_text())
        for item in requests:
            if item['asset_id'] not in missing:
                continue
            target = work/(item['asset_id']+'.mp4')
            created = adapter.create_avatar(snapshot, work/item['audio_file'], item, journal, target)
            media.import_media(created, item['asset_id'], 'avatar', avatar_requests=requests_path, root=ROOT)
        # Catalog fingerprints change after import. Final receipts must use the
        # finished catalog, while narration/provider receipts remain reusable.
        name = pipeline.job_name(plan, model, voice, False)
        state = journal.load(name)
        directory = output/name
        previous = directory/'video.mp4'
        if state.get('complete') and previous.is_file():
            if hashlib.sha256(previous.read_bytes()).hexdigest() != state.get('video_sha256'):
                raise PipelineError('Completed video was changed; the existing file was not overwritten.')
            return previous
        hybrid.make(plan, name, state, journal, directory, model, voice)
        final = directory/'video.mp4'
        if not final.is_file():
            raise PipelineError('Production did not create its final video.')
        (directory/'production.json').write_text(json.dumps({
            'avatar_provider': provider, 'portrait_sha256': picture_hash,
            'prepared_inputs': work.name, 'auto_published': False}, indent=2))
        return final


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--portrait', required=True, type=Path)
    parser.add_argument('--avatar-provider', choices=['fal', 'elevenlabs'], required=True)
    parser.add_argument('--output', type=Path, default=Path('video-output'))
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        path = produce(args.plan, args.portrait, args.avatar_provider, args.output)
        status = {'status': 'completed', 'directory': path.parent.name, 'video': path.name,
                  'auto_published': False}
        code = 0
    except Exception as error:
        message = str(error) if isinstance(error, PipelineError) else f'Production stopped ({type(error).__name__}); receipts preserved.'
        status = {'status': 'blocked', 'message': message}
        code = 2
    (args.output/'production-status.json').write_text(json.dumps(status, ensure_ascii=False, indent=2))
    print(json.dumps(status, ensure_ascii=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
