"""Low-cost 60-second stock/generated/avatar production with reusable media."""
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil

from automation.render import captions, command, probe
from automation.state import PipelineError, paid_once

ROOT = Path(__file__).resolve().parent


def positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def validate(plan):
    shots = plan.get('shots', [])
    if not isinstance(shots, list) or not 3 <= len(shots) <= 30:
        raise PipelineError('Hybrid plans need 3–30 short segments.')
    total = avatar = 0
    generations = {}
    for shot in shots:
        if not isinstance(shot, dict):
            raise PipelineError('Each hybrid segment must be an object.')
        duration = shot.get('duration')
        if not positive(duration) or duration > 12:
            raise PipelineError('Hybrid segment duration must be positive and at most 12 seconds.')
        total += duration
        offset = shot.get('source_start', 0)
        if isinstance(offset, bool) or not isinstance(offset, (int, float)) or not math.isfinite(offset) or offset < 0:
            raise PipelineError('Invalid source_start.')
        kind = shot.get('kind')
        if shot.get('transition', 'cut') not in ['cut', 'fade']:
            raise PipelineError('Supported transitions are cut or fade.')
        if kind not in ['stock', 'generated', 'avatar']:
            raise PipelineError('Hybrid kind must be stock, generated or avatar.')
        if kind == 'avatar':
            avatar += duration
            if offset != 0:
                raise PipelineError('Avatar clips use the exported speech slice from their first frame.')
        if kind != 'generated' or shot.get('asset_id'):
            if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', shot.get('asset_id', '')):
                raise PipelineError('Reusable clips need a valid media catalog asset_id.')
        else:
            name = shot.get('generation_id', '')
            seconds = shot.get('generation_seconds', 8)
            prompt = shot.get('prompt', '')
            if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', name):
                raise PipelineError('New Gemini clips need generation_id.')
            if type(seconds) is not int or not 3 <= seconds <= 15 or offset+duration > seconds:
                raise PipelineError('Gemini source duration must cover all selected frames (3–15 seconds).')
            if not isinstance(prompt, str) or not 40 <= len(prompt) <= 2500:
                raise PipelineError('New Gemini clips need a concrete motion prompt.')
            specification = (seconds, prompt)
            if name in generations and generations[name] != specification:
                raise PipelineError('Repeated generation_id must have identical duration and prompt.')
            generations[name] = specification
        if shot.get('asset_id') and shot.get('generation_id'):
            raise PipelineError('Choose a reusable asset or a new generation, not both.')
    if abs(total-60) > 0.001:
        raise PipelineError('Hybrid segment durations must total exactly 60 seconds.')
    if avatar > 12 or sum(v[0] for v in generations.values()) > 16:
        raise PipelineError('Cost cap: at most 12 avatar seconds and 16 newly generated seconds per video.')
    return {'generated_seconds': sum(v[0] for v in generations.values()),
            'avatar_seconds': avatar, 'new_clip_count': len(generations),
            'stock_seconds': sum(s['duration'] for s in shots if s['kind']=='stock')}


def catalog(root=ROOT):
    path = root/'media/catalog.json'
    data = json.loads(path.read_text()) if path.exists() else {'version': 1, 'assets': {}}
    if data.get('version') != 1 or not isinstance(data.get('assets'), dict):
        raise PipelineError('Invalid media catalog.')
    return data['assets']


def fingerprint(plan, root=ROOT):
    assets = catalog(root)
    selected = {s['asset_id']: assets.get(s['asset_id']) for s in plan['shots'] if s.get('asset_id')}
    return hashlib.sha256(json.dumps(selected, sort_keys=True).encode()).hexdigest()


def resolve(plan, root=ROOT):
    """All local footage must be ready before any paid generation request."""
    assets = catalog(root)
    narration_hash = hashlib.sha256(plan['narration'].encode()).hexdigest()
    segments, missing, start = [], [], 0
    for shot in plan['shots']:
        segment = dict(shot, start=start)
        start += shot['duration']
        asset_id = shot.get('asset_id')
        if asset_id:
            if asset_id not in assets:
                missing.append(asset_id)
                continue
            asset = assets[asset_id]
            path = (root/asset['path']).resolve()
            if not path.is_relative_to((root/'media').resolve()):
                raise PipelineError('Media paths must stay inside automation/media.')
            if not path.is_file():
                missing.append(asset_id)
                continue
            if asset.get('kind') != shot['kind']:
                raise PipelineError('Media provenance kind differs from the planned shot.')
            if hashlib.sha256(path.read_bytes()).hexdigest() != asset.get('sha256'):
                raise PipelineError('Media hash mismatch: '+asset_id)
            if shot['kind'] == 'stock' and (not asset.get('license') or not asset.get('source_url', '').startswith('https://')):
                raise PipelineError('Stock media needs its source URL and license: '+asset_id)
            if shot['kind'] == 'avatar':
                timestamp = asset.get('timeline_start')
                if (asset.get('narration_sha256') != narration_hash or
                        isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or
                        not math.isfinite(timestamp) or abs(timestamp-segment['start']) > 0.001 or
                        not re.fullmatch(r'[0-9a-f]{64}', asset.get('audio_sha256', ''))):
                    raise PipelineError('Avatar must match this narration and exact exported timeline slice: '+asset_id)
            media = probe(path)
            video = next((s for s in media['streams'] if s['codec_type']=='video'), None)
            if path.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'}:
                raise PipelineError('Reusable media must be moving video: '+asset_id)
            available = float(video.get('duration', media['format']['duration'])) if video else 0
            if not math.isfinite(available) or available+0.001 < shot.get('source_start', 0)+shot['duration']:
                raise PipelineError('Clip is shorter than the selected interval: '+asset_id)
            segment.update(path=path, asset=asset)
        segments.append(segment)
    if missing:
        raise PipelineError('Missing reusable media (no generation charged): '+', '.join(sorted(set(missing))))
    return segments


def voice_cache_name(plan, voice):
    identity = hashlib.sha256((voice+'\n'+plan['narration']).encode()).hexdigest()[:24]
    return 'narration-'+identity


def voice_result(plan, voice, journal):
    from automation.pipeline import prepared_voice, synthesize
    name = voice_cache_name(plan, voice)
    state = journal.load(name)
    prepared = prepared_voice(plan, voice)
    if not prepared and 'voice' not in state and not os.environ.get('ELEVENLABS_API_KEY'):
        raise PipelineError('Missing GitHub Actions secret: ELEVENLABS_API_KEY')
    return paid_once(journal, name, state, 'voice', lambda: prepared or synthesize(plan['narration'], voice))


def prepare(plan, voice, journal, directory):
    """Export the SAME narration's exact audio intervals for external lip syncing."""
    if not all(shutil.which(cmd) for cmd in ['ffmpeg', 'ffprobe']):
        raise PipelineError('Install ffmpeg and ffprobe before preparing narration.')
    directory.mkdir(parents=True, exist_ok=True)
    result = voice_result(plan, voice, journal)
    audio = directory/'voice.mp3'
    try:
        data = base64.b64decode(result['audio_base64'], validate=True)
    except (KeyError, ValueError, TypeError):
        raise PipelineError('Invalid saved voice response; it will not be recharged automatically.') from None
    audio.write_bytes(data)
    alignment = result.get('alignment')
    if not alignment:
        raise PipelineError('Voice alignment is missing; preserve the original audio.')
    last = captions(alignment, directory)
    if not 45 <= float(probe(audio)['format']['duration']) <= 59.5 or last > 59.75:
        raise PipelineError('Narration must fit 45–59.5 seconds without speeding it up.')
    voice_hash = hashlib.sha256(data).hexdigest()
    alignment_path = directory/'alignment.json'
    alignment_path.write_text(json.dumps(alignment, ensure_ascii=False))
    (directory/'voice-manifest.json').write_text(json.dumps({
        'voice_id': voice, 'narration_sha256': hashlib.sha256(plan['narration'].encode()).hexdigest(),
        'audio_sha256': voice_hash,
        'alignment_sha256': hashlib.sha256(alignment_path.read_bytes()).hexdigest()}, indent=2))
    requests, start = [], 0
    for i, shot in enumerate(plan['shots']):
        if shot['kind']=='avatar':
            target = directory/f'avatar-{i+1:02}-speech.wav'
            command(['ffmpeg','-v','error','-nostdin','-y','-i',str(audio),'-af',
                     f'adelay=250:all=1,apad,atrim=start={start}:duration={shot["duration"]},asetpts=PTS-STARTPTS',
                     '-ar','48000','-c:a','pcm_s16le',str(target)])
            requests.append({'asset_id':shot['asset_id'],'timeline_start':start,'duration':shot['duration'],
                             'audio_file':target.name,'slice_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
                             'audio_sha256':voice_hash,'voice_id':voice,
                             'narration_sha256':hashlib.sha256(plan['narration'].encode()).hexdigest(),
                             'portrait_required':True,'instruction':'Use the supplied audio verbatim with the user-provided portrait; do not generate another voice.'})
        start += shot['duration']
    (directory/'avatar-requests.json').write_text(json.dumps(requests, ensure_ascii=False, indent=2))
    (directory/'narration.txt').write_text(plan['narration'])
    (directory/'sources.txt').write_text('\n'.join(plan['sources']))
    (directory/'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    return audio, alignment, voice_hash


def make(plan, name, state, journal, directory, model, voice):
    from automation.pipeline import Omni, prepared_voice
    from automation.hybrid_render import render_hybrid
    budget = validate(plan)
    segments = resolve(plan)
    if any(s['kind']=='avatar' for s in segments):
        saved = journal.load(voice_cache_name(plan, voice)).get('voice', {})
        if not prepared_voice(plan, voice) and saved.get('status') != 'received':
            raise PipelineError('Avatar narration is missing in this environment. Import the original voice package; no new TTS charged.')
    if budget['new_clip_count'] and not os.environ.get('GEMINI_API_KEY'):
        raise PipelineError('Missing GitHub Actions secret: GEMINI_API_KEY')
    audio, alignment, audio_hash = prepare(plan, voice, journal, directory)
    for segment in segments:
        if segment['kind']=='avatar' and segment['asset']['audio_sha256'] != audio_hash:
            raise PipelineError('Avatar was made for another audio take; use the exported speech slices.')
    generator = Omni(model) if budget['new_clip_count'] else None
    generated = {}
    for segment in segments:
        if segment.get('path'):
            continue
        gid = segment['generation_id']
        path = directory/f'generated-{gid}.mp4'
        if gid not in generated:
            specification = json.dumps([model, segment['prompt'], segment.get('generation_seconds', 8)])
            cache_name = 'generated-'+hashlib.sha256(specification.encode()).hexdigest()[:24]
            cache = journal.load(cache_name)
            receipt = paid_once(journal, cache_name, cache, 'clip',
                               lambda s=segment: generator.submit(s['prompt'], duration=s.get('generation_seconds', 8)))
            if not path.exists():
                generator.download(receipt, path)
            generated[gid] = path
        segment['path'] = generated[gid]
    render_hybrid(segments, audio, alignment, directory)
    (directory/'budget.json').write_text(json.dumps(budget, indent=2))
    # One file is compatible with both Shorts and Reels; avoid duplicate encoding.
    (directory/'delivery.json').write_text(json.dumps({'file':'video.mp4','platforms':['YouTube Shorts','Instagram Reels'],
        'auto_published':False,'synthetic_disclosure':'Only generated and avatar intervals are labelled.'}, indent=2))
    state.update(complete=True, voice_id=voice, actions_run_id=os.environ.get('GITHUB_RUN_ID'),
                 video_sha256=hashlib.sha256((directory/'video.mp4').read_bytes()).hexdigest())
    journal.save(name, state)
