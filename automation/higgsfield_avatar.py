"""Cost-bounded Higgsfield CLI avatar jobs with persistent, resumable receipts.

Uses the official CLI, not undocumented website endpoints. The caller selects a
model after inspecting its live schema. A web promotion is never treated as an
API/CLI entitlement. Credentials stay in the CLI's private OAuth store.
"""
import argparse
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import requests

from automation.gemini_avatar import remux
from automation.render import probe
from automation.state import LocalJournal, PipelineError, paid_once, request, session
from automation.voice_changer import convert


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise PipelineError('Kredi tutarı sayısal olmalı.')
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise PipelineError('Kredi tutarı okunamadı.') from None
    if not result.is_finite() or result < 0:
        raise PipelineError('Kredi tutarı sonlu ve sıfır veya üzeri olmalı.')
    return result


def quote_credits(value):
    """Fail closed for ambiguous or undocumented currencies/response shapes."""
    if not isinstance(value, dict):
        raise PipelineError('Higgsfield fiyat yanıtı incelenmeli; üretim başlatılmadı.')
    if value.get('currency', 'credits') not in ('credits', 'credit'):
        raise PipelineError('Fiyat kredi cinsinden değil; otomatik para birimi dönüşümü yapılmadı.')
    keys = [k for k in ('credits', 'total_credits', 'credits_cost') if k in value]
    if not keys and value.get('currency') in ('credits', 'credit') and 'cost' in value:
        keys = ['cost']
    if len(keys) != 1:
        raise PipelineError('Fiyat yanıtındaki kredi alanı belirsiz; kayıt incelenmeli.')
    return number(value[keys[0]])


class CLI:
    def __init__(self, binary=None):
        self.binary = binary or os.environ.get('HIGGSFIELD_CLI') or shutil.which('higgsfield')
        if not self.binary:
            raise PipelineError('Resmi Higgsfield CLI kurulumu veya HIGGSFIELD_CLI yolu eksik.')

    def call(self, *args, timeout=120):
        try:
            result = subprocess.run([self.binary, *args, '--json', '--no-color'],
                                    capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired):
            raise PipelineError('Higgsfield bağlantısı yanıt vermedi; kayıtlı üretim yeniden gönderilmez.') from None
        if result.returncode:
            # Never include unfiltered provider stderr, tokens, or signed media URLs.
            raw = (result.stdout+' '+result.stderr).lower()
            if any(x in raw for x in ('workspace', 'auth login', 'not authenticated', 'session expired')):
                raise PipelineError('Higgsfield hesabının bu bulutta oturumu/çalışma alanı bağlı değil.')
            raise PipelineError('Higgsfield komutu tamamlanamadı; model erişimi ve kayıt kontrol edilmeli.')
        try:
            return json.loads(result.stdout)
        except ValueError:
            raise PipelineError('Higgsfield JSON yanıtı okunamadı; işlem kaydı korundu.') from None


def load_job(path):
    path = Path(path).resolve()
    spec = json.loads(path.read_text())
    if (spec.get('schema') != 'higgsfield-avatar-v1'
            or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,80}', spec.get('episode', ''))
            or spec.get('role') not in ('intro', 'outro')
            or spec.get('mode') not in ('audio_driven', 'native_then_voice_changer')
            or spec.get('seconds') != 15):
        raise PipelineError('Higgsfield avatar isteği geçersiz; 15 saniye giriş/kapanış gerekli.')
    model = spec.get('model')
    if not isinstance(model, str) or not re.fullmatch(r'[a-z0-9_\-]{1,80}', model):
        raise PipelineError('Higgsfield modeli hesap kataloğu ve fiyatı kontrol edildikten sonra seçilmeli.')
    if 'gemini' in model or model.startswith('veo'):
        raise PipelineError('Bu üretimde Google/Gemini video yedeği kapalı.')
    params = spec.get('params', {})
    if not isinstance(params, dict) or not isinstance(params.get('prompt'), str):
        raise PipelineError('Higgsfield model parametreleri ve prompt eksik.')
    forbidden = {'wait', 'wait_timeout', 'wait_interval', 'json', 'no_color', 'batch_size',
                 'image', 'start_image', 'end_image', 'image_references',
                 'audio', 'audio_references', 'video', 'video_references'}
    for key, val in params.items():
        if (not re.fullmatch(r'[a-z][a-z0-9_]*', key) or key in forbidden
                or not isinstance(val, (str, int, float, bool))):
            raise PipelineError('Beklenmeyen CLI parametresi; medya yalnız doğrulanmış girdilerden alınır.')
    if params.get('duration') != 15 or params.get('aspect_ratio') != '9:16':
        raise PipelineError('Model parametreleri 15 saniye / 9:16 olmalı.')
    assets = {}
    for key in ('portrait', 'audio') if spec['mode'] == 'audio_driven' else ('portrait',):
        item = spec.get(key, {})
        f = path.parent/item.get('path', '')
        if not f.is_file() or f.is_symlink() or sha(f) != item.get('sha256'):
            raise PipelineError('Özgün fotoğraf/ses eksik veya istek hazırlandıktan sonra değişmiş.')
        assets[key] = f.resolve()
    if spec['mode'] == 'audio_driven':
        data = probe(assets['audio'])
        if abs(float(data['format']['duration'])-15) > .02:
            raise PipelineError('Dudak sürücü sesi tam 15 saniye olmalı; ses hızlandırılmaz.')
    elif not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}', spec.get('voice_id', '')):
        raise PipelineError('Voice Changer için kullanıcının doğrulanmış klon kimliği gerekli.')
    return spec, assets


def arguments(spec, assets):
    args = [spec['model']]
    for key, value in spec['params'].items():
        args.extend(['--'+key, str(value).lower() if isinstance(value, bool) else str(value)])
    image_flag = spec.get('image_flag', 'image')
    if image_flag not in ('image', 'start-image'):
        raise PipelineError('Fotoğraf giriş türü model şemasından seçilmeli.')
    args.extend(['--'+image_flag, str(assets['portrait'])])
    if spec['mode'] == 'audio_driven':
        args.extend(['--audio', str(assets['audio'])])
    return args


def job_id(value):
    if isinstance(value, dict):
        value = value.get('job_ids', value.get('job_id', value.get('id')))
    if isinstance(value, list) and len(value) == 1:
        value = value[0]
        if isinstance(value, dict):
            value = value.get('id', value.get('job_id'))
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,100}', value):
        raise PipelineError('Tek Higgsfield iş kimliği alınamadı; aynı ücretli istek tekrarlanmayacak.')
    return value


def reserve(journal, name, cost, per_clip, monthly, month=None):
    cost, per_clip, monthly = map(number, (cost, per_clip, monthly))
    if cost > per_clip:
        raise PipelineError('Klip için belirlenen kredi sınırı aşılıyor; üretim başlatılmadı.')
    month = month or datetime.now(ZoneInfo('Europe/Istanbul')).strftime('%Y-%m')
    ledger = 'higgsfield-credit-reservations'
    with journal.operation_lock(ledger):
        state = journal.load(ledger)
        jobs = state.setdefault(month, {})
        if name in jobs:
            if number(jobs[name]) != cost:
                raise PipelineError('Önceki rezervasyon farklı; belirsiz işlemi yeniden ücretlendirme.')
            return
        if sum((number(x) for x in jobs.values()), Decimal(0)) + cost > monthly:
            raise PipelineError('Aylık Higgsfield kredi sınırı doldu; üretim başlatılmadı.')
        jobs[name] = str(cost)
        journal.save(ledger, state)


def download_result(value, path):
    if isinstance(value, list) and len(value) == 1:
        value = value[0]
    if not isinstance(value, dict) or value.get('status') not in ('completed', 'succeeded'):
        raise PipelineError('Higgsfield işi henüz tamamlanmış değil; mevcut iş kaydı korundu.')
    url = value.get('result_url')
    if not isinstance(url, str) or urlsplit(url).scheme != 'https' or not urlsplit(url).hostname:
        raise PipelineError('Higgsfield sonuç bağlantısı yok; gerçek yanıt şeması incelenmeli.')
    partial = path.with_suffix('.part.mp4')
    try:
        with session() as c:
            response = request(c, 'GET', url, stream=True)
            size = 0
            with partial.open('wb') as f:
                for block in response.iter_content(65536):
                    size += len(block)
                    if size > 200_000_000:
                        raise PipelineError('Higgsfield klibi beklenen dosya boyutunu aştı.')
                    f.write(block)
        d = probe(partial)
        v = next(s for s in d['streams'] if s['codec_type'] == 'video')
        if (abs(float(v.get('duration', d['format']['duration']))-15) > .1
                or abs(v['width']/v['height']-9/16) > .01):
            raise PipelineError('Gelen klip 15 saniye / 9:16 değil; otomatik uzatma/kesme yapılmadı.')
        partial.replace(path)
    except requests.RequestException:
        raise PipelineError('Sonuç dosyası indirilemedi; kayıtlı Higgsfield işi yeniden üretilmez.') from None
    finally:
        partial.unlink(missing_ok=True)


def run(job_path, output, journal, *, cli=None, quote_only=True,
        max_credits=0, monthly_credits=0):
    spec, assets = load_job(job_path)
    cli = cli or CLI()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    name = 'higgsfield-'+hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:24]
    state = journal.load(name)
    args = arguments(spec, assets)
    if not state.get('generation'):
        schema = cli.call('model', 'get', spec['model'])
        raw_quote = cli.call('generate', 'cost', *args)
        (output/'model-schema.json').write_text(json.dumps(schema, ensure_ascii=False, indent=2))
        (output/'price-quote.json').write_text(json.dumps(raw_quote, ensure_ascii=False, indent=2))
        cost = quote_credits(raw_quote)
        if quote_only:
            return {'status': 'quote_only', 'credits': str(cost), 'video_created': False}
        reserve(journal, name, cost, max_credits, monthly_credits)
        state['quoted_credits'] = str(cost)
    elif quote_only:
        return {'status': 'existing_submission', 'video_created': False}
    # No --wait here: persist the returned job id before polling. A process loss
    # must not make a second paid generation necessary.
    receipt = paid_once(journal, name, state, 'generation',
                        lambda: cli.call('generate', 'create', *args))
    identifier = job_id(receipt)
    native = output/'higgsfield-native.mp4'
    with journal.operation_lock(name+'-download'):
        current = journal.load(name)
        if native.exists():
            if current.get('native_sha256') != sha(native):
                raise PipelineError('Kaydedilmiş Higgsfield klibi değişmiş; otomatik tekrar üretim yok.')
        else:
            final = cli.call('generate', 'wait', identifier, '--timeout', '20m', '--interval', '10s', timeout=1230)
            (output/'provider-result.json').write_text(json.dumps(final, ensure_ascii=False, indent=2))
            download_result(final, native)
            current['native_sha256'] = sha(native)
            journal.save(name, current)
    if spec['mode'] == 'audio_driven':
        audio = assets['audio']
    else:
        wav = output/'native-speech.wav'
        r = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(native), '-vn',
                            '-ar', '48000', '-ac', '1', str(wav)], capture_output=True)
        if r.returncode:
            raise PipelineError('Higgsfield konuşma sesi alınamadı; yeni ücretli üretim yapılmadı.')
        audio = convert(wav, spec['voice_id'], journal, output/'own-voice.mp3')
    final = remux(native, audio, output/'avatar-proof.mp4')
    result = {'status': 'needs_visual_and_lipsync_review', 'video_created': True,
              'provider': 'higgsfield', 'mode': spec['mode'], 'journal': name,
              'file': str(final), 'sha256': sha(final), 'reference_sha256': sha(assets['portrait']),
              'audio_sha256': sha(audio), 'retimed': False, 'perfect_lipsync_verified': False}
    (output/'avatar-receipt.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--job', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--journal', type=Path, default=Path('video-output/journal'))
    p.add_argument('--generate', action='store_true', help='Submit within the configured credit limits; default only quotes.')
    p.add_argument('--max-credits', type=number, default=Decimal(0))
    p.add_argument('--monthly-credits', type=number, default=Decimal(0))
    a = p.parse_args()
    try:
        result = run(a.job, a.output, LocalJournal(a.journal), quote_only=not a.generate,
                     max_credits=a.max_credits, monthly_credits=a.monthly_credits)
    except (PipelineError, OSError, ValueError) as e:
        result = {'status': 'blocked', 'video_created': False,
                  'message': str(e) if isinstance(e, PipelineError) else 'Yerel girdi okunamadı.'}
        print(json.dumps(result, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
