"""Prepare five daily topics, then assemble one 60-second draft with a cloned voice."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path

from automation import assembly, daily, editorial, hybrid, produce
from automation.state import PipelineError

ROOT = Path(__file__).resolve().parent


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)+'\n'


def _write_plan(path, plan):
    """A generated disabled draft must never overwrite an edited draft."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = _json(plan)
    if path.is_symlink():
        raise PipelineError('Derlenmiş taslak sembolik bağlantı olamaz; üzerine yazılmadı.')
    try:
        with path.open('x', encoding='utf-8') as handle:
            handle.write(content)
    except FileExistsError:
        if not path.is_file() or path.read_text(encoding='utf-8') != content:
            raise PipelineError('Bu günün derlenmiş taslağı değiştirilmiş; üzerine yazılmadı.') from None


def _status(result, output):
    directory = output/'studio'/result['date']
    directory.mkdir(parents=True, exist_ok=True)
    text = _json(result)
    (directory/'status.json').write_text(text, encoding='utf-8')
    (output/'status.json').write_text(text, encoding='utf-8')
    return result


def run_studio(day, output, portrait=None, avatar_provider='fal', *, editorial_only=False,
               provider='gemini', model=None, journal=None):
    """Freeze one day's choices and produce only when every input is ready.

    A completed render remains a clinical/visual review draft. This module does
    not approve medical claims or publish to a social network.
    """
    editorial._day(day)
    if avatar_provider not in ('fal', 'elevenlabs'):
        raise PipelineError('Avatar sağlayıcısı fal veya elevenlabs olmalı.')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    with daily.RunLock(output/'.studio.lock'):
        journal = journal if journal is not None else daily._journal(output)
        summary = daily.run_daily(day, output/'studio', provider, model, journal=journal)
        # Read the verified frozen receipt, not an editable draft file.
        batch = daily._saved_batch(journal.load('daily-'+day), day)
        script = batch['scripts'][0]
        result = {'schema': 'daily-studio-v1', 'date': day, 'topics': 5, 'scripts': 1,
                  'topic_id': script['topic_id'], 'directory': summary['directory'],
                  'editorial_provider': summary['provider'], 'editorial_reused': summary['reused'],
                  'avatar_provider': avatar_provider, 'auto_published': False,
                  'clinical_review': 'required', 'visual_review': 'required',
                  'video_not_created': True}
        if editorial_only:
            return _status({**result, 'status': 'editorial_ready',
                            'message': 'Beş konu ve bir senaryo taslağı hazır; ses/video üretilmedi. '
                                       'Tıbbi içerik ve yayın öncesi inceleme gerekiyor.'}, output)

        missing = []
        portrait = portrait or os.environ.get('AVATAR_PORTRAIT_PATH')
        if not portrait:
            missing.append({'name': 'portrait', 'message': 'Kendi net, önden çekilmiş PNG/JPEG fotoğrafınızı '
                            '--portrait ile seçin. GitHub için AVATAR_PORTRAIT_BASE64 gizli bilgisi '
                            'en fazla 48 KiB kodlanmış metin (yaklaşık 36 KiB fotoğraf) içerebilir.'})
        else:
            try:
                produce._portrait(portrait)
            except (PipelineError, OSError):
                missing.append({'name': 'portrait', 'message': 'Portre dosyası okunamadı. Tek kare PNG/JPEG, '
                                'her kenarı en az 256 piksel, en fazla 20 megapiksel ve 25 MB olmalı.'})

        name = 'studio-'+day
        state = journal.load(name)
        script_hash = hashlib.sha256(_json(script).encode()).hexdigest()
        if state and state.get('script_sha256') != script_hash:
            raise PipelineError('Kaydedilmiş günlük senaryo değişmiş; ikinci bir ücretli üretim başlatılmadı.')
        plan = state.get('plan')
        if plan is not None:
            if (not isinstance(plan, dict) or not isinstance(plan.get('id'), str)
                    or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', plan['id'])
                    or plan.get('format') != 'hybrid-v1' or plan.get('date') != day
                    or plan.get('topic_id') != script['topic_id']
                    or plan.get('sources') != script['sources']
                    or plan.get('narration') != script['narration'] or plan.get('enabled') is not False):
                raise PipelineError('Kaydedilmiş günlük kurgu eşleşmiyor; üretim başlatılmadı.')
            hybrid.validate(plan)
        try:
            if plan is None:
                plan = assembly.compile_plan(script, hybrid.catalog(ROOT), day)
            # Verify actual hashes, duration, licenses and paths before any TTS,
            # video generation or avatar request; catalog metadata is not enough.
            produce._preflight_media(plan)
        except PipelineError as error:
            missing.append({'name': 'approved_footage', 'message': str(error)})
            plan = None
        if plan is not None:
            if not state:
                state = {'version': 1, 'date': day, 'script_sha256': script_hash, 'plan': plan}
                journal.save(name, state)
            directory = output/'studio'/day
            _write_plan(directory/'compiled-plan.json', plan)
            # produce deliberately accepts only trusted plans/drafts. The local
            # mirror is ignored by Git and stays disabled in the normal queue.
            draft = ROOT/'drafts'/('studio-'+plan['id']+'.json')
            _write_plan(draft, plan)
            result['compiled_plan'] = str(directory/'compiled-plan.json')
        if missing:
            return _status({**result, 'status': 'needs_inputs', 'inputs': missing,
                            'message': 'Senaryo taslağı saklandı. Eksik girdiler tamamlanana kadar '
                                       'ses, avatar ve video üretimi başlatılmadı.'}, output)

        final = produce.produce(draft, portrait, avatar_provider, output, journal=journal)
        return _status({**result, 'status': 'completed', 'video': str(final),
                        'video_not_created': False,
                        'message': '60 saniyelik video taslağı hazır. Yayın öncesi tıbbi içerik, '
                                   'görüntüler ve dudak uyumu kontrol edilmeli; otomatik yayın yapılmadı.'}, output)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', default=daily.today_in_turkey(), help='YYYY-MM-DD; today in Türkiye by default.')
    parser.add_argument('--portrait', type=Path, help='Own PNG/JPEG portrait; or AVATAR_PORTRAIT_PATH.')
    parser.add_argument('--avatar-provider', choices=['fal', 'elevenlabs'], default='fal')
    parser.add_argument('--output', type=Path, default=Path('video-output'))
    parser.add_argument('--editorial-only', action='store_true', help='Five suggestions and one script; no TTS/video calls.')
    parser.add_argument('--provider', choices=sorted(editorial.DEFAULT_MODELS), default='gemini')
    parser.add_argument('--model', help='Model for a new day; existing days reuse the frozen provider/model.')
    args = parser.parse_args(argv)
    try:
        result = run_studio(args.date, args.output, args.portrait, args.avatar_provider,
                            editorial_only=args.editorial_only, provider=args.provider, model=args.model)
    except Exception as error:
        message = str(error) if isinstance(error, PipelineError) else f'Üretim durdu ({type(error).__name__}); işlem kaydı korundu.'
        result = {'status': 'blocked', 'date': args.date, 'video_not_created': True,
                  'auto_published': False, 'message': message}
        # An invalid date must never become a filesystem path.
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output/'status.json').write_text(_json(result), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['status'] in ('completed', 'editorial_ready') else 2


if __name__ == '__main__':
    raise SystemExit(main())
