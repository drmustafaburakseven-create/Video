"""Attach an exported ElevenLabs take to a plan for reuse on another runner."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from automation.render import captions
from automation.state import PipelineError

ROOT = Path(__file__).resolve().parent


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _read(path, description):
    if path.is_symlink():
        raise PipelineError(f'{description} must not be a symbolic link.')
    try:
        return path.read_bytes()
    except OSError:
        raise PipelineError(f'Unable to read {description}.') from None


def _object(data, description):
    try:
        result = json.loads(data)
    except (ValueError, UnicodeError):
        raise PipelineError(f'Invalid {description} JSON.') from None
    if not isinstance(result, dict):
        raise PipelineError(f'{description} must be a JSON object.')
    return result


def _directory(path, root):
    if path.is_symlink():
        raise PipelineError('Voice asset directories must not be symbolic links.')
    path.mkdir(parents=True, exist_ok=True)
    if not path.resolve().is_relative_to(root):
        raise PipelineError('Voice assets must stay inside automation/assets.')


def _copy_once(destination, data):
    if destination.is_symlink():
        raise PipelineError('Voice assets must not be symbolic links.')
    if destination.exists():
        if not destination.is_file() or destination.read_bytes() != data:
            raise PipelineError('Existing voice asset differs; no file was overwritten.')
        return
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix='.voice-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def _write_plan(path, data, previous):
    if path.is_symlink() or path.read_bytes() != previous:
        raise PipelineError('The target plan changed during import; retry without overwriting concurrent edits.')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.voice-plan-', suffix='.json', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def attach_voice(from_output, plan, *, root=ROOT):
    """Copy verified audio/alignment and atomically attach prepared_voice metadata."""
    root = Path(root).resolve()
    target = Path(plan).absolute()
    if target.is_symlink() or target.parent.is_symlink():
        raise PipelineError('The target plan and its directory must not be symbolic links.')
    target = target.resolve()
    if target.parent not in (root/'plans', root/'drafts') or target.suffix != '.json':
        raise PipelineError('The target plan must be a JSON file in automation/plans or automation/drafts.')
    target_bytes = _read(target, 'target plan')
    target_plan = _object(target_bytes, 'target plan')
    directory = Path(from_output).resolve()
    source_plan = _object(_read(directory/'plan.json', 'exported plan'), 'exported plan')
    narration = source_plan.get('narration')
    if not isinstance(narration, str) or not narration or target_plan.get('narration') != narration:
        raise PipelineError('The target plan narration differs from the exported voice take.')
    manifest = _object(_read(directory/'voice-manifest.json', 'voice manifest'), 'voice manifest')
    voice_id = manifest.get('voice_id')
    if not isinstance(voice_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', voice_id):
        raise PipelineError('The voice manifest must identify the original ElevenLabs voice.')
    for key in ('narration_sha256', 'audio_sha256', 'alignment_sha256'):
        if not isinstance(manifest.get(key), str) or not re.fullmatch(r'[0-9a-f]{64}', manifest[key]):
            raise PipelineError('The voice manifest is missing valid integrity hashes.')
    audio = _read(directory/'voice.mp3', 'exported audio')
    alignment_bytes = _read(directory/'alignment.json', 'exported alignment')
    if (not audio or manifest['narration_sha256'] != _sha(narration.encode())
            or manifest['audio_sha256'] != _sha(audio)
            or manifest['alignment_sha256'] != _sha(alignment_bytes)):
        raise PipelineError('Exported voice integrity check failed; no plan was changed.')
    alignment = _object(alignment_bytes, 'exported alignment')
    with tempfile.TemporaryDirectory() as validation:
        captions(alignment, validation)
    requests_path = directory/'avatar-requests.json'
    if requests_path.exists() or requests_path.is_symlink():
        try:
            requests = json.loads(_read(requests_path, 'avatar requests'))
        except (ValueError, UnicodeError):
            raise PipelineError('Invalid avatar requests JSON.') from None
        if not isinstance(requests, list):
            raise PipelineError('Avatar requests must be a JSON list.')
        for request in requests:
            if (not isinstance(request, dict) or request.get('voice_id') != voice_id
                    or request.get('narration_sha256') != manifest['narration_sha256']
                    or request.get('audio_sha256') != manifest['audio_sha256']):
                raise PipelineError('Avatar requests belong to a different narration or voice take.')
    elif any(isinstance(shot, dict) and shot.get('kind') == 'avatar' for shot in source_plan.get('shots', [])):
        raise PipelineError('The exported avatar requests are missing.')
    bundle_hash = _sha((voice_id+'\n'+manifest['narration_sha256']+'\n'
                        +manifest['audio_sha256']+'\n'+manifest['alignment_sha256']).encode())[:24]
    assets = root/'assets'
    _directory(assets, root)
    folder = assets/('narration-'+bundle_hash)
    _directory(folder, assets)
    lock_path = assets/'.voice.lock'
    if lock_path.is_symlink():
        raise PipelineError('The voice import lock must not be a symbolic link.')
    with os.fdopen(os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600), 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        _copy_once(folder/'voice.mp3', audio)
        _copy_once(folder/'alignment.json', alignment_bytes)
        prepared = {'voice_id': voice_id, 'text_sha256': manifest['narration_sha256'],
                    'audio': (folder/'voice.mp3').relative_to(root).as_posix(),
                    'alignment': (folder/'alignment.json').relative_to(root).as_posix(),
                    'audio_sha256': manifest['audio_sha256'],
                    'alignment_sha256': manifest['alignment_sha256']}
        target_plan['prepared_voice'] = prepared
        _write_plan(target, target_plan, target_bytes)
    return prepared


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-output', required=True, type=Path)
    parser.add_argument('--plan', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        prepared = attach_voice(args.from_output, args.plan)
    except (PipelineError, OSError) as error:
        parser.exit(2, f'Voice import failed: {error}\n')
    print(f'Prepared voice attached to {args.plan}: {prepared["audio"]}')


if __name__ == '__main__':
    main()
