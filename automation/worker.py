"""Portable 09:00 Türkiye scheduler; requires an always-on host, never deploys one."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from zoneinfo import ZoneInfo

from automation.daily import RunLock
from automation.batch_studio import settings as batch_settings
from automation.editorial import DEFAULT_MODELS, _day
from automation.state import PipelineError

TURKEY = ZoneInfo('Europe/Istanbul')
STUDIO_STATUSES = {'completed', 'editorial_ready', 'needs_inputs', 'blocked', 'partially_completed'}


def local_now(now=None):
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise PipelineError('Scheduler timestamps must include a timezone.')
    return value.astimezone(TURKEY)


def effective_date(now=None):
    return local_now(now).date().isoformat()


def due_date(now, attempts):
    """Catch up today's missed 09:00 once; do not backfill earlier days."""
    local = local_now(now)
    day = local.date().isoformat()
    if local.hour < 9 or day in attempts:
        return None
    return day


def next_due(now, attempts):
    local = local_now(now)
    day = local.date().isoformat()
    scheduled = local.replace(hour=9, minute=0, second=0, microsecond=0)
    if day in attempts:
        return scheduled+timedelta(days=1)
    return scheduled if local < scheduled else local


def load_state(output):
    path = Path(output)/'worker-state.json'
    if path.is_symlink():
        raise PipelineError('Scheduler state must not be a symbolic link.')
    if not path.exists():
        return {'version': 1, 'attempts': {}}
    try:
        value = json.loads(path.read_text())
        if value.get('version') != 1 or not isinstance(value.get('attempts'), dict):
            raise ValueError
        for day, attempt in value['attempts'].items():
            _day(day)
            if not isinstance(attempt, dict) or not isinstance(attempt.get('status'), str):
                raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise PipelineError('Scheduler state is invalid; no new attempt was started.') from None
    return value


def save_state(output, state):
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    target = root/'worker-state.json'
    if target.is_symlink():
        raise PipelineError('Scheduler state must not be a symbolic link.')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=root,
                                         prefix='.worker-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(state, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def schedule_status(now, state, *, check_only=False):
    return {'status': 'schedule_check' if check_only else 'scheduler_running',
            'timezone': 'Europe/Istanbul', 'schedule': '09:00 daily',
            'today': effective_date(now), 'due_today': due_date(now, state['attempts']) is not None,
            'next_due': next_due(now, state['attempts']).isoformat(),
            'daily_attempt_limit': 1, 'check_only': check_only,
            'videos_per_batch': batch_settings()['videos_per_day'],
            'production_profile': batch_settings()['production_profile'],
            'message': 'Zamanlayıcı yalnız bu süreç ve makine çalışırken işler. Bu komut sunucu kurmaz veya sosyal medyada yayın yapmaz.'}


def studio_command(day, output, provider, avatar_provider, portrait=None, model=None, editorial_only=False,
                   videos=3, ready_root=None):
    command = [sys.executable, '-m', 'automation.batch_studio', '--date', day,
               '--output', str(Path(output).resolve()), '--provider', provider, '--videos', str(videos)]
    if ready_root:
        command += ['--ready-root', str(ready_root)]
    if model:
        command += ['--model', model]
    if editorial_only:
        command.append('--editorial-only')
    return command


def attempt_once(day, output, state, *, provider='gemini', avatar_provider='fal',
                 portrait=None, model=None, editorial_only=False, now=None, runner=None,
                 videos=3, ready_root=None):
    """Record intent before launch; a crash, timeout or failure still consumes today."""
    _day(day)
    if day in state['attempts']:
        return state['attempts'][day]
    started = local_now(now).isoformat()
    attempt = {'status': 'started', 'started_at': started, 'automatic_retry': False,
               'requested_videos': videos, 'profile': 'warm-office-60'}
    state['attempts'][day] = attempt
    save_state(output, state)  # If this fails, the child and all paid work remain unstarted.
    runner = runner or subprocess.run
    command = studio_command(day, output, provider, avatar_provider, portrait, model, editorial_only,
                             videos=videos, ready_root=ready_root)
    try:
        child = runner(command, capture_output=True, text=True, timeout=3*60*60,
                       cwd=Path(__file__).resolve().parent.parent)
        code = child.returncode
        studio_status = None
        completed_videos = 0
        try:
            result = json.loads((Path(output)/'status.json').read_text())
            if result.get('date') == day and result.get('status') in STUDIO_STATUSES:
                studio_status = result['status']
                completed_videos = result.get('completed_videos', 0)
        except (OSError, ValueError, AttributeError):
            pass
        success = code == 0 and studio_status in {'completed', 'editorial_ready'}
        attempt.update(status='finished' if success else 'blocked', exit_code=code,
                       studio_status=studio_status,
                       completed_videos=completed_videos,
                       video_created=completed_videos > 0)
    except subprocess.TimeoutExpired:
        attempt.update(status='timed_out', video_created=False)
    except OSError:
        attempt.update(status='launch_failed', video_created=False)
    # Do not save or echo child stdout/stderr: a provider error could contain credentials.
    attempt['finished_at'] = local_now().isoformat()
    save_state(output, state)
    return attempt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path(os.environ.get('VIDEO_OUTPUT_ROOT', 'video-output')))
    parser.add_argument('--provider', choices=sorted(DEFAULT_MODELS), default=os.environ.get('VIDEO_EDITORIAL_PROVIDER', 'gemini'))
    parser.add_argument('--avatar-provider', choices=['fal', 'elevenlabs'], default=os.environ.get('VIDEO_AVATAR_PROVIDER', 'fal'))
    parser.add_argument('--portrait', type=Path, default=os.environ.get('AVATAR_PORTRAIT_PATH'))
    parser.add_argument('--model', default=os.environ.get('VIDEO_EDITORIAL_MODEL'))
    parser.add_argument('--videos', type=int, choices=[1, 3], default=int(os.environ.get('VIDEO_DAILY_COUNT', '3')))
    parser.add_argument('--ready-root', type=Path, default=os.environ.get('VIDEO_READY_ROOT'))
    parser.add_argument('--editorial-only', action='store_true', default=os.environ.get('VIDEO_EDITORIAL_ONLY', '').lower() == 'true')
    parser.add_argument('--check-only', action='store_true', help='Inspect schedule only; no source, AI, speech or video calls.')
    parser.add_argument('--once', action='store_true', help='Run today once if due, then exit; may use provider credits.')
    args = parser.parse_args(argv)
    try:
        if args.provider not in DEFAULT_MODELS or args.avatar_provider not in ['fal', 'elevenlabs']:
            raise PipelineError('Invalid scheduler provider configuration.')
        args.output.mkdir(parents=True, exist_ok=True)
        state = load_state(args.output)
        if args.check_only:
            print(json.dumps(schedule_status(local_now(), state, check_only=True), ensure_ascii=False), flush=True)
            return 0
        with RunLock(args.output/'.worker.lock'):
            state = load_state(args.output)
            print(json.dumps(schedule_status(local_now(), state), ensure_ascii=False), flush=True)
            while True:
                now = local_now()
                day = due_date(now, state['attempts'])
                if day:
                    result = attempt_once(day, args.output, state, provider=args.provider,
                                          avatar_provider=args.avatar_provider, portrait=args.portrait,
                                          model=args.model, editorial_only=args.editorial_only, now=now,
                                          videos=args.videos, ready_root=args.ready_root)
                    print(json.dumps({'date': day, **result,
                                      'next_due': next_due(local_now(), state['attempts']).isoformat()}, ensure_ascii=False), flush=True)
                if args.once:
                    return 0 if not day or result['status'] == 'finished' else 2
                # A failed run is still in attempts; this poll cannot resubmit it.
                delay = (next_due(local_now(), state['attempts'])-local_now()).total_seconds()
                time.sleep(min(30, max(1, delay)))
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        message = str(error) if isinstance(error, PipelineError) else f'Scheduler stopped ({type(error).__name__}); no automatic retry in this process.'
        print(json.dumps({'status': 'blocked', 'message': message}, ensure_ascii=False), flush=True)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
