"""Prepare five daily pediatric topics and one grounded script, without publishing."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from automation import editorial
from automation.sources import fetch_sources
from automation.state import GitHubJournal, LocalJournal, PipelineError

ROOT = Path(__file__).resolve().parent
HISTORY_NAME = 'daily-editorial-history'


class RunLock:
    """One local daily runner at a time; never wait behind a possible paid call."""
    def __init__(self, path):
        self.path = Path(path)
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            self.handle = os.fdopen(descriptor, 'a')
            fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if self.handle:
                self.handle.close()
                self.handle = None
            raise PipelineError('Başka bir günlük hazırlık çalışıyor; ikinci işlem başlatılmadı.') from None
        except OSError:
            if self.handle:
                self.handle.close()
                self.handle = None
            raise PipelineError('Günlük çalışma kilidi açılamadı; üretim başlatılmadı.') from None
        return self

    def __exit__(self, *unused):
        if self.handle:
            fcntl.flock(self.handle, fcntl.LOCK_UN)
            self.handle.close()
            self.handle = None


def today_in_turkey(now=None):
    now = now or datetime.now(timezone.utc)
    return now.astimezone(ZoneInfo('Europe/Istanbul')).date().isoformat()


def _history(journal):
    history = journal.load(HISTORY_NAME)
    entries = history.get('entries', [])
    if not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries):
        raise PipelineError('Kayıtlı günlük konu geçmişi geçersiz; yeni üretim başlatılmadı.')
    return entries


def _record_success(journal, day, batch):
    entries = _history(journal)
    selected = batch['selected_topic_ids']
    for item in entries:
        if item.get('date') == day:
            if item.get('selected_topic_ids') != selected:
                raise PipelineError('Bu tarihte farklı bir içerik kayıtlı; geçmişin üzerine yazılmadı.')
            return
    entries.append({'date': day, 'selected_topic_ids': selected})
    journal.save(HISTORY_NAME, {'version': 1, 'entries': sorted(entries, key=lambda item: item['date'])})


def _saved_batch(state, day):
    batch = state.get('batch')
    if (not isinstance(batch, dict) or batch.get('schema') != 'daily-editorial-v1'
            or batch.get('date') != day or batch.get('topics') != state.get('topics')
            or batch.get('provider') != state.get('provider') or batch.get('model') != state.get('model')
            or batch.get('selected_topic_ids') != [state['topics'][0]['id']]):
        raise PipelineError('Kaydedilmiş günlük içerik eşleşmiyor; otomatik yeniden satın alma yapılmadı.')
    editorial.validate_response({'scripts': batch.get('scripts')}, state['topics'], 1)
    return batch


def _write_batch(batch, output):
    """Restore verified draft artifacts without making another model request."""
    output.mkdir(parents=True, exist_ok=True)
    (output/'daily.json').write_text(json.dumps(batch, ensure_ascii=False, indent=2)+'\n')
    (output/'daily.md').write_text(editorial._markdown(batch))
    for script in batch['scripts']:
        (output/(script['topic_id']+'.editorial.json')).write_text(
            json.dumps(script, ensure_ascii=False, indent=2)+'\n')


def _preview(day, topics, directory):
    result = {'schema': 'daily-topics-preview-v1', 'date': day, 'topics': topics,
              'source_pages_fetched': False, 'script_generated': False,
              'video_not_created': True, 'status': 'topic_suggestions_only'}
    directory.mkdir(parents=True, exist_ok=True)
    (directory/'topics.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    lines = [f'# {day} — Beş konu önerisi', '',
             'Kayıtlı konu listesinden seçildi. Bu çalışmada kaynak sayfaları yenilenmedi; ses veya video üretilmedi.', '']
    for index, topic in enumerate(topics, 1):
        lines += [f'{index}. **{topic["title"]}** — {topic["age_group"]}']
    (directory/'topics.md').write_text('\n'.join(lines)+'\n')


def run_daily(day, output, provider='gemini', model=None, *, offline_topics=False,
              journal=None, catalog_path=ROOT/'editorial_catalog.json'):
    """Freeze the daily choice and evidence, then draft one script or restore it.

The caller must serialize remote GitHub runners with workflow concurrency;
the file lock below protects local callers sharing this output directory.
"""
    editorial._day(day)
    if provider not in editorial.DEFAULT_MODELS:
        raise PipelineError('Geçersiz içerik sağlayıcısı.')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with RunLock(output/'.daily.lock'):
        journal = journal or LocalJournal(output/'journal')
        name = 'daily-'+day
        state = journal.load(name)
        directory = output/day
        if offline_topics:
            if state.get('topics'):
                topics = state['topics']
            else:
                catalog = json.loads(Path(catalog_path).read_text())
                topics = editorial.propose_topics(day, catalog, _history(journal))
            _preview(day, topics, directory)
            return {'status': 'topic_suggestions_only', 'date': day, 'topics': len(topics),
                    'scripts': 0, 'directory': str(directory), 'video_not_created': True,
                    'message': 'Beş konu önerisi hazır; kaynak taraması, yapay zekâ çağrısı ve video üretimi yapılmadı.'}
        if state.get('complete'):
            batch = _saved_batch(state, day)
            _write_batch(batch, directory)
            # Recover a crash after saving the completed batch but before history.
            _record_success(journal, day, batch)
            reused = True
        else:
            if 'topics' not in state:
                catalog = json.loads(Path(catalog_path).read_text())
                topics = editorial.propose_topics(day, catalog, _history(journal))
                state.update(version=1, date=day, topics=topics, provider=provider,
                             model=model or editorial.DEFAULT_MODELS[provider], videos=1,
                             created_at=datetime.now(timezone.utc).isoformat())
                journal.save(name, state)  # Freeze the choice before any paid request.
            if (state.get('date') != day or state.get('provider') not in editorial.DEFAULT_MODELS
                    or not isinstance(state.get('topics'), list) or len(state['topics']) != 5
                    or state.get('videos') != 1):
                raise PipelineError('Günlük hazırlık kaydı geçersiz; yeni üretim başlatılmadı.')
            if 'sources' not in state:
                urls = {url for topic in state['topics'] for url in topic['sources']}
                state['sources'] = fetch_sources(urls, output/'research')
                journal.save(name, state)  # Keep receipt identity stable if the live pages change.
            batch = editorial.create_daily(day, state['topics'], state['sources'], journal, directory,
                                           provider=state['provider'], model=state['model'], videos=1)
            # Do not mark a failed or partially validated model response complete.
            state['batch'] = batch
            _saved_batch(state, day)
            state['complete'] = True
            journal.save(name, state)
            _record_success(journal, day, batch)
            reused = False
        return {'status': 'editorial_ready', 'date': day, 'topics': 5, 'scripts': 1,
                'directory': str(directory), 'provider': batch['provider'], 'model': batch['model'],
                'reused': reused, 'video_not_created': True,
                'message': 'Beş konu ve bir video senaryosu hazır. Ses ölçümü, gerçek görüntüler ve avatar tamamlanmadan bitmiş video oluşmaz.'}


def _journal(output, offline=False):
    if os.environ.get('GITHUB_ACTIONS') == 'true' and not offline:
        needed = ['GITHUB_REPOSITORY', 'GITHUB_TOKEN', 'GITHUB_SHA']
        missing = [name for name in needed if not os.environ.get(name)]
        if missing:
            raise PipelineError('GitHub çalışma bilgileri eksik: '+', '.join(missing))
        return GitHubJournal(os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_TOKEN'], os.environ['GITHUB_SHA'])
    return LocalJournal(output/'journal')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', default=today_in_turkey(), help='YYYY-MM-DD; default is today in Türkiye.')
    parser.add_argument('--output', type=Path, default=Path('video-output/daily'))
    parser.add_argument('--provider', choices=sorted(editorial.DEFAULT_MODELS), default='gemini',
                        help='Used when starting a new day; saved days preserve their original provider.')
    parser.add_argument('--model', help='Optional model for a new day; saved days preserve their original model.')
    parser.add_argument('--offline-topics', action='store_true', help='Five curated suggestions only, without network or paid calls.')
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        journal = _journal(args.output, offline=args.offline_topics)
        summary = run_daily(args.date, args.output, args.provider, args.model,
                            offline_topics=args.offline_topics, journal=journal)
        code = 0
    except Exception as error:
        message = str(error) if isinstance(error, PipelineError) else f'Hazırlık durdu ({type(error).__name__}); işlem kaydı korundu.'
        summary = {'status': 'blocked', 'date': args.date, 'video_not_created': True, 'message': message}
        code = 2
    (args.output/'status.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(summary, ensure_ascii=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
