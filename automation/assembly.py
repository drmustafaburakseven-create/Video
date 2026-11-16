"""Compile an editorial draft using only explicitly curated local footage.

This module does not search, download, inspect files or call a paid provider.
The production preflight remains responsible for actual files and hashes.
"""
from collections import Counter
from datetime import date
import hashlib
import math
from pathlib import PurePosixPath
import re
import unicodedata
from urllib.parse import urlsplit

from automation import hybrid
from automation.state import PipelineError

_SLUG = re.compile(r'[a-z0-9][a-z0-9-]{0,63}')
_STOP = {'a', 'an', 'and', 'the', 'with', 'in', 'on', 'of', 'to', 'for', 'video',
         'portrait', 'natural', 'light', 'camera', 'bir', 've', 'ile', 'icin', 'bu', 'da', 'de'}
_PREFIX = ('Photorealistic continuous eight-second 9:16 portrait B-roll. '
           'Natural subject movement, stable anatomy and age-appropriate safe behaviour. '
           'No readable text, logos, dialogue, real patient details, photo pans or frozen frames. ')


def _positive(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value > 0)


def _text(value, minimum=1, maximum=1500):
    return isinstance(value, str) and minimum <= len(value.strip()) <= maximum


def _sources(value):
    if not isinstance(value, list) or not value:
        return False
    for source in value:
        if not isinstance(source, str) or any(c.isspace() for c in source):
            return False
        try:
            parts = urlsplit(source)
            if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password:
                return False
        except ValueError:
            return False
    return True


def _validate_script(script, day):
    if not isinstance(day, str):
        raise PipelineError('Gün YYYY-MM-DD biçiminde olmalı.')
    try:
        if date.fromisoformat(day).isoformat() != day:
            raise ValueError
    except ValueError:
        raise PipelineError('Gün YYYY-MM-DD biçiminde geçerli bir tarih olmalı.') from None
    if not isinstance(script, dict) or script.get('schema') != 'editorial-script-v1':
        raise PipelineError('Kurgu için doğrulanmış editorial-script-v1 taslağı gerekiyor.')
    topic = script.get('topic_id')
    if not isinstance(topic, str) or not _SLUG.fullmatch(topic):
        raise PipelineError('Konu kimliği geçersiz.')
    if not _text(script.get('title'), maximum=180) or not _text(script.get('narration'), 400, 1400):
        raise PipelineError('Başlık ve 400–1400 karakterlik konuşma metni gerekiyor.')
    if not _sources(script.get('sources')):
        raise PipelineError('Konuşmanın HTTPS kaynak bağlantıları eksik veya geçersiz.')
    scenes = script.get('scenes')
    if script.get('duration_seconds') != 60 or not isinstance(scenes, list) or len(scenes) != 15:
        raise PipelineError('Taslak 60 saniye ve 15 adet dört saniyelik sahne içermeli.')
    for index, scene in enumerate(scenes):
        if (not isinstance(scene, dict) or type(scene.get('start')) not in (int, float)
                or scene['start'] != index*4 or type(scene.get('duration')) not in (int, float)
                or scene['duration'] != 4 or scene.get('kind') not in ('stock', 'generated', 'avatar')):
            raise PipelineError('Sahneler boşluksuz olarak 0–60 saniyeyi doldurmalı.')
        if not _text(scene.get('visual'), maximum=1000) or not _text(scene.get('motion_prompt'), 20):
            raise PipelineError('Her sahnenin görüntü ve hareket açıklaması gerekiyor.')
        if any(key in scene for key in ('asset_id', 'generation_id', 'path')):
            raise PipelineError('Editoryal taslakta hazırmış gibi medya kimliği kullanılmamalı.')
    counts = Counter(s['kind'] for s in scenes)
    if counts != {'avatar': 2, 'generated': 2, 'stock': 11}:
        raise PipelineError('Kurgu dağılımı 44 saniye stok, 8 saniye yeni görüntü ve 8 saniye avatar olmalı.')
    return topic, scenes


def _tokens(value):
    plain = unicodedata.normalize('NFKD', value.casefold().replace('ı', 'i'))
    plain = ''.join(c for c in plain if not unicodedata.combining(c))
    return {word for word in re.findall(r'[a-z0-9]+', plain) if len(word) > 1 and word not in _STOP}


def _approved_assets(assets, topic):
    if not isinstance(assets, dict):
        raise PipelineError('Medya kataloğu geçerli bir nesne olmalı.')
    if 'version' in assets and 'assets' in assets:
        if assets['version'] != 1 or not isinstance(assets['assets'], dict):
            raise PipelineError('Medya kataloğu biçimi geçersiz.')
        assets = assets['assets']
    pool = []
    for identifier, asset in assets.items():
        if (not isinstance(identifier, str) or not _SLUG.fullmatch(identifier)
                or not isinstance(asset, dict) or asset.get('kind') not in ('stock', 'generated')):
            continue
        approved = asset.get('approved_topics')
        if not isinstance(approved, list) or topic not in approved:
            continue
        available = asset.get('source_duration', asset.get('duration'))
        path, digest = asset.get('path'), asset.get('sha256')
        if (not _positive(available) or available < 4 or not isinstance(path, str)
                or not path.startswith('media/') or '..' in PurePosixPath(path).parts
                or not isinstance(digest, str) or not re.fullmatch(r'[a-f0-9]{64}', digest)):
            continue
        tags = asset.get('tags', [])
        if isinstance(tags, list):
            tags = ' '.join(t for t in tags if isinstance(t, str))
        if not isinstance(tags, str):
            tags = ''
        description = asset.get('description', '')
        if not isinstance(description, str):
            description = ''
        pool.append({'id': identifier, 'kind': asset['kind'], 'duration': available,
                     'source_identity': digest, 'tokens': _tokens(tags+' '+description)})
    return pool


def compile_plan(script, assets, day):
    """Return a disabled hybrid plan; only approved_topics grants footage use."""
    topic, scenes = _validate_script(script, day)
    pool = _approved_assets(assets, topic)
    base = f'{day}-{topic}'
    plan_id = base if len(base) <= 64 else base[:55].rstrip('-')+'-'+hashlib.sha256(base.encode()).hexdigest()[:8]
    selected_shots, offsets = {}, {}

    def select(scene, cursors):
        keywords = _tokens(scene['visual']+' '+scene['motion_prompt'])
        choices = [a for a in pool if cursors.get(a['source_identity'], 0)+4 <= a['duration']+0.001]
        if not choices:
            return None
        selected = min(choices, key=lambda a: (-len(keywords & a['tokens']), a['id']))
        start = cursors.get(selected['source_identity'], 0)
        # Aliases of one file share the cursor; distinct IDs cannot repeat frames.
        cursors[selected['source_identity']] = start+4
        return {'kind': selected['kind'], 'asset_id': selected['id'],
                'duration': 4, 'source_start': start}

    # Reserve the required 44 seconds before considering optional AI slots.
    for index, scene in enumerate(scenes):
        if scene['kind'] != 'stock':
            continue
        shot = select(scene, offsets)
        if shot is None:
            raise PipelineError(
                f'“{topic}” konusu için tekrar etmeyen 44 saniyelik onaylı ara çekim gerekiyor; '
                f'yalnız {len(selected_shots)*4} saniye eşleştirilebildi. Katalogdaki approved_topics alanına '
                'bu konu için uygunluğu kontrol edilmiş daha fazla hareketli video ekleyin. '
                'Ücretli üretim başlatılmadı.')
        selected_shots[index] = shot
    generated_indices = [i for i, scene in enumerate(scenes) if scene['kind'] == 'generated']
    extra_offsets = dict(offsets)
    replacements = {i: select(scenes[i], extra_offsets) for i in generated_indices}
    if all(replacements.values()):
        # Existing reviewed footage is cheapest. Preserve synthetic provenance
        # when the reusable asset happens to be AI-generated.
        selected_shots.update(replacements)
    else:
        first_generated = scenes[generated_indices[0]]
        prompt = _PREFIX+first_generated['motion_prompt'].strip()
        generation = 'broll-'+hashlib.sha256((topic+'\n'+prompt).encode()).hexdigest()[:20]
        for position, index in enumerate(generated_indices):
            selected_shots[index] = {'kind': 'generated', 'generation_id': generation,
                                     'generation_seconds': 8, 'duration': 4,
                                     'source_start': position*4, 'prompt': prompt}
    for index, scene in enumerate(scenes):
        if scene['kind'] == 'avatar':
            identifier = f'avatar-{hashlib.sha256(plan_id.encode()).hexdigest()[:20]}-{index+1:02}'
            selected_shots[index] = {'kind': 'avatar', 'asset_id': identifier, 'duration': 4, 'source_start': 0}
    shots = [selected_shots[index] for index in range(len(scenes))]
    plan = {'format': 'hybrid-v1', 'id': plan_id, 'title': script['title'],
            'topic_id': topic, 'date': day, 'enabled': False, 'duration_seconds': 60,
            'narration': script['narration'], 'sources': list(script['sources']), 'shots': shots,
            'production_note': 'Onaylı kütüphaneden derlendi; gerçek dosyalar, özgün ses ve portre üretim öncesinde doğrulanmalı.'}
    hybrid.validate(plan)
    return plan
