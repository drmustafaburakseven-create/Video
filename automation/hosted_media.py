"""Resume dated daily slots from the studio's existing encrypted GitHub release format."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from automation import publishing
from automation.state import PipelineError, session

STUDIO = Path(__file__).resolve().parents[1] / 'reels-studyosu'


def run_studio(tool, *args):
    subprocess.run([sys.executable, str(STUDIO / tool), *map(str, args)], check=True)


def render_release(day, script, directory):
    topic = script['topic_id']
    tag = f'reels-{day}-{topic}'
    repo = os.environ['GITHUB_REPOSITORY']
    with session() as client:
        response = client.get(f'https://api.github.com/repos/{repo}/releases/tags/{tag}',
                              headers={'Authorization': 'Bearer ' + os.environ['GITHUB_TOKEN']},
                              timeout=30)
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise PipelineError(f'Medya paketi kontrol edilemedi (HTTP {response.status_code}).')
        assets = response.json()['assets']
    if not any(asset['name'] == 'girdi.gpg' for asset in assets):
        raise PipelineError(f'{tag} sürümünde girdi.gpg eksik.')
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        media, output = root/'media', root/'output'
        subprocess.run(['gh', 'release', 'download', tag, '--repo', repo, '--pattern',
                        'girdi.gpg', '--dir', str(root)], check=True)
        run_studio('paket.py', 'ac', 'girdi', root/'girdi.gpg', media)
        plan = json.loads((media/'bolum.json').read_text())
        spoken = ' '.join(plan[key].strip() for key in ('question', 'answer', 'body', 'outro'))
        if spoken.split() != script['narration'].split():
            raise PipelineError('Şifreli medya paketindeki konuşma günlük senaryoyla eşleşmiyor.')
        review = json.loads((media/'zamanlar.json').read_text())
        if any(review.get(key) != 'approved' for key in ('visual_review', 'speech_timing_review')):
            raise PipelineError('Görüntü ve konuşma zamanlaması incelemesi eksik.')
        run_studio('studyo.py', 'montaj', media, output)
        from automation.render import probe
        master = output/'Video-1080p.mp4'
        meta = probe(master)
        video = next(s for s in meta['streams'] if s['codec_type'] == 'video')
        if ((video['width'], video['height'], video['r_frame_rate']) != (1080, 1920, '30/1')
                or int(video['nb_frames']) != 1800 or abs(float(meta['format']['duration'])-60) > .01
                or not any(s['codec_type'] == 'audio' for s in meta['streams'])):
            raise PipelineError('Ana video 60 saniye, ses ve 1080p/30 fps denetimini geçemedi.')
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-i', str(master), '-f', 'null', '-'], check=True)
        # Only the encrypted delivery leaves the runner.
        publishing.write(script, output)
        target = directory/'sonuc.gpg'
        run_studio('paket.py', 'kilitle', 'sonuc', output, target)
        return target
