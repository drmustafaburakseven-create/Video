"""Render reviewed warm-office inputs; never silently fall back to the old layout.

The automatic generation/visual review of new avatar and B-roll inputs is NOT
implemented here. A ready.json binds the real media and mix to the exact script.
"""
import hashlib
import json
from pathlib import Path

from automation import publishing, reel_1080
from automation.render import probe
from automation.state import PipelineError


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def _file(root, item):
    if not isinstance(item, dict) or not isinstance(item.get('path'), str):
        raise PipelineError('Hazır kurgu dosya yolu ve SHA-256 özeti gerektiriyor.')
    path = root/item['path']
    if not path.is_file() or sha(path) != item.get('sha256'):
        raise PipelineError('Hazır kurgu dosyası eksik veya incelemeden sonra değişmiş.')
    return path.resolve()


def prepare(script, path):
    path = Path(path)
    if not path.is_file():
        raise PipelineError('Son kurgu biçimi için bu konuya ait hazır avatar, hareketli ara çekimler, '
                            'ölçülmüş ses ve altyazı paketi eksik. Eski kurguya dönülmedi.')
    data = json.loads(path.read_text())
    if (not isinstance(data, dict) or data.get('schema') != 'warm-ready-v1' or data.get('profile') != 'warm-office-60'
            or data.get('topic_id') != script['topic_id']
            or data.get('narration_sha256') != publishing.narration_hash(script)
            or data.get('visual_review') != 'approved'
            or data.get('speech_timing_review') != 'approved'):
        raise PipelineError('Hazır kurgu bu senaryoyla eşleşmiyor veya görüntü/ses incelemesi eksik.')
    root = path.parent
    segments = []
    body_sources = set()
    source_segments = data.get('segments')
    if not isinstance(source_segments, list) or len(source_segments) < 6:
        raise PipelineError('Giriş, en az dört farklı ara çekim ve kapanış gerekli.')
    for i, segment in enumerate(source_segments):
        expected = 'intro' if i == 0 else 'outro' if i == len(source_segments)-1 else 'body'
        if not isinstance(segment, dict) or segment.get('role') != expected:
            raise PipelineError('Doktor girişte ve kapanışta olmalı; ara sahneler ortada kalmalı.')
        if not all(key in segment for key in ('start', 'end')):
            raise PipelineError('Her sahnenin başlangıç ve bitiş zamanı gerekli.')
        source = _file(root, segment)
        if expected == 'body':
            # One file cut into four ranges is still one source.
            body_sources.add(segment['sha256'])
        segments.append({key: segment[key] for key in ('start', 'end', 'offset', 'entry') if key in segment})
        segments[-1]['path'] = str(source)
    if len(body_sources) < 4:
        raise PipelineError('En az dört farklı hareketli ara görüntü kaynağı gerekli.')
    reel_1080.validate_segments(segments)
    if not 8 <= segments[0]['end'] <= 16 or not 44 <= segments[-1]['start'] <= 50:
        raise PipelineError('Giriş/kapanış uzunluğu onaylanan sıcak ofis biçimine uymuyor.')
    audio = _file(root, data.get('audio'))
    ass = _file(root, data.get('captions'))
    if not ass.read_text(encoding='utf-8').strip().startswith('[Script Info]'):
        raise PipelineError('Kontrollü altyazı/grafik ASS paketi eksik.')
    fonts = data.get('fonts', [])
    if not isinstance(fonts, list) or len(fonts) < 2:
        raise PipelineError('Altyazı yazı tipleri ve bütünlük kayıtları gerekli.')
    font_paths = [_file(root, font) for font in fonts]
    if len({font.parent for font in font_paths}) != 1:
        raise PipelineError('Yazı tipleri aynı dizinde olmalı.')
    last_word = data.get('last_spoken_word')
    reel_1080.validate_audio_timeline(float(probe(audio)['format']['duration']), last_word)
    return {'segments': segments, 'audio': audio, 'ass': ass, 'fonts': font_paths[0].parent,
            'last_spoken_word': last_word, 'manifest_sha256': sha(path)}


def render(script, manifest, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    inputs = prepare(script, manifest)
    receipt_path = directory/'delivery.json'
    final = directory/'video.mp4'
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if (receipt.get('manifest_sha256') != inputs['manifest_sha256']
                or receipt.get('narration_sha256') != publishing.narration_hash(script)):
            raise PipelineError('Tamamlanmış kurgunun girdileri değişmiş; dosya üzerine yazılmadı.')
        if final.is_file() and sha(final) == receipt.get('video_sha256'):
            publishing.write(script, directory)
            return final
        raise PipelineError('Tamamlanmış video eksik veya değişmiş; otomatik üzerine yazılmadı.')
    reel_1080.render(inputs['segments'], inputs['audio'], final, directory/'render',
                     last_spoken_word=inputs['last_spoken_word'], ass=inputs['ass'], fonts=inputs['fonts'])
    metadata = probe(final)
    stream = next(s for s in metadata['streams'] if s['codec_type'] == 'video')
    if (abs(float(metadata['format']['duration'])-60) > .01
            or (stream['width'], stream['height'], stream['r_frame_rate']) != (1080, 1920, '30/1')
            or stream.get('nb_frames') != '1800'):
        raise PipelineError('Çıktı 60 saniye / 1080p / 30 fps profilini doğrulayamadı.')
    reel_1080.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(final), '-f', 'null', '-'], directory/'decode.log')
    publishing.write(script, directory)
    receipt_path.write_text(json.dumps({'profile': 'warm-office-60', 'manifest_sha256': inputs['manifest_sha256'],
                                       'narration_sha256': publishing.narration_hash(script),
                                       'video_sha256': sha(final), 'auto_published': False}, indent=2)+'\n')
    return final
