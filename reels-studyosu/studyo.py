"""Prepare a user-selected episode, voice its reviewed turns, and render offline."""
import argparse
import base64
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from automation import clinical_review, dialogue_audio, publishing, reel_1080, reels_captions, stock, voice_changer
from automation.media import digest
from automation.higgsfield_episode import phone_copy
from automation.pipeline import synthesize
from automation.render import probe, timestamp
from automation.state import LocalJournal, paid_once

STOCK = [f'stok-{i}.mp4' for i in range(1, 5)]
CLIPS = ['giris.mp4', *STOCK, 'cikis.mp4']
ROLES = ('question', 'answer', 'body', 'outro')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def script(plan):
    if not all(isinstance(plan[k], str) and plan[k].strip() for k in (*ROLES, 'title', 'hook')):
        raise ValueError('Senaryoda boş replik veya başlık var.')
    if len(plan['cards']) != 4 or len(plan['stocks']) != 4 or not plan['sources']:
        raise ValueError('Dört ara görüntü, dört kart ve tıbbi kaynak gerekli.')
    return {**plan, 'narration': ' '.join(plan[k] for k in ROLES)}


def prepare(plan, dest):
    plan = script(plan)
    dest.mkdir(parents=True, exist_ok=True)
    common = ('Eklediğim özgün fotoğrafı referans al. Dikey 9:16, sesli, tek ve sabit çekim. '
              'Yüzümü, kıyafetimi, ışığı ve arka planı koru. Fotoğraftaki kadrajı koru. '
              'Ellerim görünüyorsa doğal konumunda tut. Hafif bir gülümseme, doğal nefes ve göz kırpma olsun. '
              'Görüntüye yazı, müzik veya başka ses ekleme. Replikleri doğal İstanbul Türkçesiyle aynen söyle. ')
    intro = (f'Kamera arkasındaki kadın merakla sorar: “{plan["question"]}” '
             f'Kadın görünmez. Ben dudaklarım kapalı dinlerim. Kısa bir duraktan sonra '
             f'kameraya bakıp sıcak bir sesle cevap veririm: “{plan["answer"]}”')
    ending = (f'Bu kez yalnız ben konuşuyorum: “{plan["outro"]}” '
              'Son kelimeden sonra en az bir buçuk saniye göz temasını koru.')
    for name, prompt in [('giris', intro), ('cikis', ending)]:
        (dest/f'google-{name}.txt').write_text(common + prompt + '\nHedef 10 saniye. '
            'Araç 8 saniye sunuyorsa kısa repliği kesmeden doğal hızda tamamla.\n')
    (dest/'konusma.txt').write_text('\n\n'.join(plan[k] for k in ROLES)+'\n')
    (dest/'ara-sahneler.txt').write_text('\n'.join(plan['stocks'])+'\n')
    publishing.write(plan, dest)


def ff(args):
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', *map(str, args)], check=True)


def seconds(path, kind):
    info = probe(path)
    stream = next(x for x in info['streams'] if x['codec_type'] == kind)
    return float(stream.get('duration') or info['format']['duration'])


def voice(root, plan):
    """Run only on explicit local invocation; keep paid receipts outside CI."""
    speaker = os.environ['DOKTOR_VOICE_ID']
    review = read(root/'zamanlar.json')
    journal = LocalJournal(root/'makbuzlar')
    with tempfile.TemporaryDirectory(dir=root) as temp:
        tmp = Path(temp)
        for name, key in [('giris', 'answer'), ('cikis', 'outro')]:
            original, turn = tmp/f'{name}.wav', tmp/f'{name}-turn.wav'
            ff(['-i', root/f'{name}.mp4', '-vn', '-ar', '48000', '-ac', '1', original])
            start, end = review[key]
            dialogue_audio.extract_turn(original, start, end, turn)
            converted = voice_changer.convert(turn, speaker, journal, tmp/f'{name}.mp3')
            mixed = tmp/f'{name}-mix.wav'
            dialogue_audio.replace_turn(original, converted, start, end, mixed)
            mixed.replace(root/f'{name}.wav')
        identity = json.dumps([speaker, plan['body'], 'multilingual-v2/v1'], ensure_ascii=False)
        key = 'body-'+hashlib.sha256(identity.encode()).hexdigest()
        saved = paid_once(journal, key, journal.load(key), 'tts', lambda: synthesize(plan['body'], speaker))
        narration = tmp/'anlatim.mp3'
        narration.write_bytes(base64.b64decode(saved['audio_base64'], validate=True))
        ff(['-i', narration, '-ar', '48000', '-ac', '1', tmp/'anlatim.wav'])
        (tmp/'anlatim.wav').replace(root/'anlatim.wav')
        (root/'hizalama.json').write_text(json.dumps(saved['alignment'], ensure_ascii=False))


def stock_materials(root, plan, save_selection):
    """Find candidates first. Preserve license and provenance for the selected shots."""
    if not save_selection:
        candidates = [stock.search_clips(query, min_duration=11) for query in plan['queries']]
        (root/'adaylar.json').write_text(json.dumps(candidates, ensure_ascii=False, indent=2))
        return
    choices = read(root/'secimler.json')
    if len(choices) != 4 or len(set(choices)) != 4:
        raise ValueError('Dört ayrı Pexels çekimi seçin.')
    catalog = root/'stok-arsivi'
    catalog.mkdir(exist_ok=True)
    for name, choice, candidates in zip(STOCK, choices, read(root/'adaylar.json'), strict=True):
        selected = next(c for c in candidates if c['asset_id'] == choice)
        key = stock.import_clip(selected, catalog)
        item = read(catalog/'media/catalog.json')['assets'][key]
        source = catalog/item['path']
        clinical_review.check(source)
        shutil.copyfile(source, root/name)


def timing(plan, root):
    review = read(root/'zamanlar.json')
    clips = [root/name for name in CLIPS]
    hashes = {digest(p) for p in clips[1:-1]}
    if len(hashes) != 4:
        raise ValueError('Dört farklı stok çekim gerekli.')
    frames = [round(seconds(clips[i], 'video')*30) for i in (0, -1)]
    if any(n < 239 or n > 300 for n in frames):
        raise ValueError('Giriş ve kapanış 8–10 saniyelik canlı çekimler olmalı.')
    intro, outro = (n/30 for n in frames)
    q, a, o = (review[k] for k in ('question', 'answer', 'outro'))
    if not (0 <= q[0] < q[1] <= a[0] < a[1] <= intro and
            0 <= o[0] < o[1] <= outro-1.5):
        raise ValueError('Gerçek konuşma aralıklarını ve kapanıştaki beklemeyi kontrol edin.')
    middle_frames = 1800-sum(frames)
    boundaries = [0, frames[0], *[frames[0]+round(middle_frames*i/4) for i in (1,2,3,4)], 1800]
    segments = [dict(path=p, start=start/30, end=end/30)
                for p, start, end in zip(clips, boundaries, boundaries[1:])]
    reel_1080.validate_segments(segments)
    return segments, review, 60-outro


def render(root, dest):
    plan = script(read(root/'bolum.json'))
    segments, review, closing = timing(plan, root)
    for name, limit in [('giris', segments[0]['end']), ('anlatim', 40), ('cikis', 60-closing)]:
        duration = seconds(root/f'{name}.wav', 'audio')
        if duration > limit+.025 or (name != 'anlatim' and abs(duration-limit) > .05):
            raise ValueError(f'{name} sesi görüntüye sığmıyor.')
    align = read(root/'hizalama.json')
    if ' '.join(''.join(align['characters']).split()) != ' '.join(plan['body'].split()):
        raise ValueError('Altyazı zamanları bu anlatım metnine ait olmalı.')
    dest.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest) as temp:
        tmp = Path(temp)
        cards = [dict(start=s['start']+.25, end=s['start']+2.25, text=text)
                 for s, text in zip(segments[1:-1], plan['cards'])]
        end = reels_captions.write(align, tmp, 10, beats=cards)
        if end > 50 or end > 10+seconds(root/'anlatim.wav','audio')+.05:
            raise ValueError('Anlatımın gerçek kelime zamanlarını kontrol edin.')
        sub = tmp/'captions.ass'
        lines = [line for line in sub.read_text().splitlines()
                 if not (line.startswith('Dialogue:') and (',Brand,' in line or ',Label,' in line))]
        # Reference layout: cream question pill, small corner handle, warm subtitles.
        lines = [line.replace(',3,5,0,2,56,70,170,1', ',1,2,1,2,58,72,260,1')
                 for line in lines]
        pill = r'{\an7\pos(100,220)\bord0\shad0\1c&HEDF6FF&\p1}m 23 0 l 497 0 b 527 0 527 48 497 48 l 23 48 b -7 48 -7 0 23 0'
        lines += [f'Dialogue: 4,0:00:00.00,0:00:02.00,Subtitle,,0,0,0,,{pill}',
                  r'Dialogue: 5,0:00:00.00,0:00:02.00,Subtitle,,0,0,0,,{\an5\pos(360,244)\fs25\bord0\shad0\1c&H30251C&}'
                  +reels_captions.safe(plan['hook']),
                  r'Dialogue: 1,0:00:02.00,0:00:59.00,Subtitle,,0,0,0,,{\an9\pos(653,155)\fs14\alpha&H55&}'
                  +publishing.HANDLE]
        lines = [line.replace('pos(340,1080)', 'pos(360,850)') for line in lines]
        for role in ('question', 'answer', 'outro'):
            offset = closing if role == 'outro' else 0
            start, stop = (timestamp(offset+t) for t in review[role])
            lines.append(f'Dialogue: 2,{start},{stop},Subtitle,,0,0,0,,{reels_captions.safe(plan[role])}')
        # Fade the complete scene, including typography, after the last spoken word.
        lines.append(r'Dialogue: 9,0:00:59.00,0:01:00.00,Subtitle,,0,0,0,,{\an7\pos(0,0)\bord0\shad0\1c&H000000&\fad(980,0)\p1}m 0 0 l 720 0 720 1280 0 1280')
        sub.write_text('\n'.join(lines)+'\n')
        mix = tmp/'mix.wav'
        args = []
        for name in ('giris', 'anlatim', 'cikis'):
            args += ['-i',root/f'{name}.wav']
        tracks = '[0:a]adelay=0:all=1[a];[1:a]adelay=10000:all=1[b];'
        tracks += f'[2:a]adelay={round(closing*1000)}:all=1[c];'
        inputs = '[a][b][c]'
        count = 3
        if (root/'muzik.wav').is_file():
            args += ['-stream_loop','-1','-i',root/'muzik.wav']
            tracks += '[3:a]atrim=duration=60,volume=0.065[m];'
            inputs += '[m]'
            count += 1
        tracks += f'{inputs}amix=inputs={count}:normalize=0,apad,atrim=duration=60,afade=t=out:st=59:d=1'
        ff([*args,'-filter_complex',tracks,'-ar','48000','-ac','2',mix])
        master = tmp/'Video-1080p.mp4'
        reel_1080.render(segments, mix, master, tmp, last_spoken_word=closing+review['outro'][1], ass=sub)
        phone_copy(master, tmp/'Video-Telefon.mp4')
        publishing.write(plan, tmp)
        for file in ('Video-1080p.mp4', 'Video-Telefon.mp4', 'paylasim.md'):
            (tmp/file).replace(dest/file)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('step', choices=['plan','stok-ara','stok-al','ses','montaj'])
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path, nargs='?')
    args = parser.parse_args()
    if args.step in ('stok-ara','stok-al'):
        stock_materials(args.input, read(args.input/'bolum.json'), args.step == 'stok-al')
    elif args.step == 'ses':
        voice(args.input, script(read(args.input/'bolum.json')))
    elif args.output is None:
        parser.error('Çıktı klasörü gerekli.')
    elif args.step == 'plan':
        prepare(read(args.input), args.output)
    else:
        render(args.input, args.output)
