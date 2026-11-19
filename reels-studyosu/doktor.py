"""Produce the two 720p speaking clips from the original portrait via Google."""
import base64
import hashlib
import json

from automation.daily import RunLock
from automation.pipeline import Omni, VEO_MODEL
from automation.gemini_avatar import _identifier
from automation.produce import _portrait
from automation.render import probe
from automation.state import LocalJournal, PipelineError, paid_once, request


def generate(root, portrait, prompts):
    picture, photo_hash, ext = _portrait(portrait)
    journal = LocalJournal(root/'makbuzlar')
    generator = Omni(VEO_MODEL)
    image = {'type': 'image', 'data': base64.b64encode(picture).decode(),
             'mime_type': 'image/png' if ext == '.png' else 'image/jpeg'}
    with RunLock(root/'.google.lock'):
        for role, prompt in prompts.items():
            target = root/f'{role}.mp4'
            identity = json.dumps([VEO_MODEL, photo_hash, prompt, '720p/16:9/10s'])
            key = 'google-'+hashlib.sha256(identity.encode()).hexdigest()
            state = journal.load(key)
            if target.exists():
                if state.get('sha256') == hashlib.sha256(target.read_bytes()).hexdigest():
                    continue
                raise PipelineError('Bu bölümde farklı bir klip var. Yeni sürüm için ayrı bölüm klasörü kullanın.')

            def submit():
                response = request(generator.client, 'POST', generator.base+'/interactions', json={
                    'model': VEO_MODEL, 'input': [image, {'type': 'text', 'text': prompt}],
                    'background': True, 'store': True,
                    'response_format': {'type': 'video', 'aspect_ratio': '16:9', 'duration': '10s',
                                        'resolution': '720p', 'delivery': 'uri'}}).json()
                return {'interaction_id': _identifier(response.get('id'))}

            receipt = paid_once(journal, key, state, 'video', submit)
            temporary = root/f'.{role}-google.mp4'
            generator.download(receipt, temporary)
            streams = probe(temporary)['streams']
            video = next((s for s in streams if s.get('codec_type') == 'video'), {})
            if ((video.get('width'), video.get('height')) != (1280, 720)
                    or abs(float(video.get('duration', 0))-10) > 1/60
                    or not any(s.get('codec_type') == 'audio' for s in streams)):
                raise PipelineError('Google klibinin sesi, 10 saniyelik süresi veya 720p yatay kadrajı doğrulanamadı.')
            state['sha256'] = hashlib.sha256(temporary.read_bytes()).hexdigest()
            journal.save(key, state)
            temporary.replace(target)
