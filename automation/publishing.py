"""Platform-specific copy bundled with a video, without posting to any service."""
import hashlib
import json
from pathlib import Path
import re

from automation.errors import PipelineError

HANDLE = '@Drmustafaburakseven'


def narration_hash(script):
    return hashlib.sha256(script['narration'].encode('utf-8')).hexdigest()


def _title(text, limit):
    text = ' '.join(text.split())
    return text if len(text) <= limit else text[:limit-1].rsplit(' ', 1)[0]+'…'


def _hashtags(script):
    text = (script.get('topic_id', '')+' '+script['title']).casefold()
    tags = ['#ÇocukSağlığı', '#Ebeveynlik']
    for words, tag in [('besin|sebze|beslenme|vitamin', '#ÇocukBeslenmesi'),
                       ('ek-gida|ek gıda', '#EkGıda'), ('uyku', '#BebekUykusu'),
                       ('burun|kanama', '#BurunKanaması'), ('gelişim|gelisim', '#ÇocukGelişimi')]:
        if any(word in text for word in words.split('|')):
            tags.append(tag)
    return list(dict.fromkeys(tags))[:4]+['#DrMustafaBurakSeven']


def package(script, supplied=None):
    """Legacy drafts use their exact narration; never invent an extra medical claim."""
    sources = script.get('sources', [])
    if supplied is None:
        tags = _hashtags(script)
        supplied = {
            'reels': {'title': _title(script['title'], 150),
                      'caption': script['narration'], 'hashtags': tags},
            'youtube_shorts': {'title': _title(script['title'], 100),
                               'description': script['narration'],
                               'hashtags': ['#Shorts']+tags[:3]}}
    if not isinstance(supplied, dict):
        raise PipelineError('Paylaşım metinleri bir nesne olmalı.')
    result = {'schema': 'social-copy-v1', 'handle': HANDLE,
              'narration_sha256': narration_hash(script), 'sources': sources,
              'auto_published': False}
    for platform, field, title_limit, text_limit in (
            ('reels', 'caption', 150, 1800), ('youtube_shorts', 'description', 100, 3800)):
        item = supplied.get(platform)
        if not isinstance(item, dict):
            raise PipelineError('Reels ve YouTube Shorts için ayrı paylaşım metinleri gerekli.')
        for name, limit in [('title', title_limit), (field, text_limit)]:
            value = item.get(name)
            if (not isinstance(value, str) or not 1 <= len(value.strip()) <= limit
                    or re.search(r'<[^>]+>|```|@kullaniciadin', value, re.I)):
                raise PipelineError('Paylaşım başlığı/açıklaması boş, çok uzun veya yer tutucu içeriyor.')
            # Source URLs are appended by code. Model-authored links are forbidden.
            if re.search(r'https?://', value):
                raise PipelineError('Paylaşım metninde bağlantı yerine ayrı doğrulanmış kaynak alanını kullanın.')
        tags = item.get('hashtags')
        if (not isinstance(tags, list) or not 1 <= len(tags) <= 5
                or any(not isinstance(tag, str) or not re.fullmatch(r'#[\w]{2,50}', tag) for tag in tags)
                or len({tag.casefold() for tag in tags}) != len(tags)):
            raise PipelineError('Her platform için 1–5 farklı, geçerli hashtag gerekli.')
        result[platform] = {'title': item['title'].strip(), field: item[field].strip(), 'hashtags': tags}
    return result


def write(script, directory):
    """Restore copy beside each output even when the video itself is resumed."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    value = package(script, script.get('social_copy'))
    reels = value['reels']
    shorts = value['youtube_shorts']
    instagram = reels['title']+'\n\n'+reels['caption']+'\n\n'+' '.join(reels['hashtags'])+'\n'
    youtube = shorts['title']+'\n\n'+shorts['description']+'\n\n'+HANDLE+'\n\n'+' '.join(shorts['hashtags'])+'\n'
    if value['sources']:
        youtube += '\nKaynaklar:\n'+'\n'.join(value['sources'])+'\n'
    if len(instagram) > 2200 or len(youtube) > 5000:
        raise PipelineError('Paylaşım paketi platform açıklama sınırını aşıyor.')
    (directory/'social.json').write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (directory/'reels.txt').write_text(instagram, encoding='utf-8')
    (directory/'shorts.txt').write_text(youtube, encoding='utf-8')
    (directory/'paylasim.md').write_text('# Instagram Reels\n\n'+instagram+'\n# YouTube Shorts\n\n'+youtube, encoding='utf-8')
    return value
