"""Three daily video slots and separate Reels/Shorts copy in the approved profile.

New avatar/media generation remains a preparation step; missing packages are
reported explicitly. This queue never substitutes the legacy eight-second avatar.
"""
import argparse
import json
from pathlib import Path

from automation import daily, editorial, publishing, ready_reel
from automation.state import PipelineError

SETTINGS = Path(__file__).parent/'profiles/daily-three.json'


def settings():
    return json.loads(SETTINGS.read_text())


def _save(value, output):
    output.mkdir(parents=True, exist_ok=True)
    body = json.dumps(value, ensure_ascii=False, indent=2)+'\n'
    (output/'status.json').write_text(body, encoding='utf-8')
    if 'date' in value:
        directory = output/'warm-studio'/value['date']
        directory.mkdir(parents=True, exist_ok=True)
        (directory/'status.json').write_text(body, encoding='utf-8')
    return value


def run(day, output, *, provider='gemini', model=None, videos=3, ready_root=None,
        editorial_only=False, journal=None):
    editorial._day(day)
    if type(videos) is not int or videos not in (1, 3):
        raise PipelineError('Bu günlük kuyruk 1 veya 3 video destekler.')
    output = Path(output).resolve()
    with daily.RunLock(output/'.studio.lock'):
        journal = journal if journal is not None else daily._journal(output)
        summary = daily.run_daily(day, output/'studio', provider, model, videos=videos,
                                  profile='warm-office-60', journal=journal)
        batch = daily._saved_batch(journal.load('daily-'+day), day)
        ready_root = Path(ready_root) if ready_root else output/'ready-reels'
        result = {'schema': 'warm-daily-batch-v1', 'date': day, 'topics': 5,
                  'requested_videos': videos, 'scripts': len(batch['scripts']),
                  'avatar_provider_preference': settings().get('avatar_provider', 'unspecified'),
                  'profile': 'warm-office-60', 'editorial_reused': summary['reused'],
                  'completed_videos': 0, 'items': [], 'auto_published': False,
                  'status': 'in_progress', 'video_not_created': True}
        _save(result, output)
        for script in batch['scripts']:
            directory = output/'warm-studio'/day/script['topic_id']
            publishing.write(script, directory)
            item = {'topic_id': script['topic_id'], 'title': script['title'],
                    'directory': str(directory), 'status': 'editorial_ready'}
            result['items'].append(item)
            if not editorial_only:
                try:
                    manifest = ready_root/day/script['topic_id']/'ready.json'
                    # Preflight every source before invoking the renderer.
                    ready_reel.prepare(script, manifest)
                except (PipelineError, OSError, ValueError) as error:
                    item.update(status='needs_inputs', message=str(error) if isinstance(error, PipelineError)
                                else 'Hazır kurgu paketi okunamadı; ücretli işlem başlatılmadı.')
                else:
                    try:
                        final = ready_reel.render(script, manifest, directory)
                        item.update(status='completed', video=str(final))
                        result['completed_videos'] += 1
                    except Exception as error:
                        item.update(status='blocked', message=str(error) if isinstance(error, PipelineError)
                                    else 'Kurgu tamamlanamadı; mevcut dosyalar korundu.')
            result['video_not_created'] = result['completed_videos'] == 0
            _save(result, output)  # A later slot failure cannot erase earlier successes.
        completed = result['completed_videos']
        result['status'] = ('editorial_ready' if editorial_only else 'completed' if completed == videos
                            else 'partially_completed' if completed else 'needs_inputs')
        result['message'] = (f'{completed}/{videos} video dosyası hazır. Her konu için Reels/Shorts metinleri ayrı kaydedildi. '
                             'Yeni avatar, ara çekimler ve ses/grafik paketlerinin hazırlanması ayrı adımdır; '
                             'eksik girdiler tamamlanmadan otomatik bitmiş video oluşmaz.')
        return _save(result, output)


def main(argv=None):
    defaults = settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', default=daily.today_in_turkey())
    parser.add_argument('--videos', type=int, choices=[1, 3], default=defaults['videos_per_day'])
    parser.add_argument('--output', type=Path, default=Path('video-output'))
    parser.add_argument('--ready-root', type=Path)
    parser.add_argument('--provider', choices=sorted(editorial.DEFAULT_MODELS), default='gemini')
    parser.add_argument('--model')
    parser.add_argument('--editorial-only', action='store_true')
    parser.add_argument('--check-only', action='store_true', help='Inspect configuration only; no source/provider/media calls.')
    args = parser.parse_args(argv)
    if args.check_only:
        print(json.dumps({'status': 'configuration_ready', **defaults,
                          'live_scheduler_verified': False, 'generation_integration': 'reviewed_ready_packages_only'}, ensure_ascii=False))
        return 0
    try:
        result = run(args.date, args.output, provider=args.provider, model=args.model,
                     videos=args.videos, ready_root=args.ready_root, editorial_only=args.editorial_only)
    except Exception as error:
        result = {'status': 'blocked', 'auto_published': False, 'video_not_created': True,
                  'message': str(error) if isinstance(error, PipelineError) else
                             'Üretim durdu ('+type(error).__name__+'); mevcut kayıtlar korundu.'}
        _save(result, args.output)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['status'] in ('completed', 'editorial_ready') else 2


if __name__ == '__main__':
    raise SystemExit(main())
