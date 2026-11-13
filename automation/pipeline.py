"""Gemini/Veo motion clips + existing ElevenLabs voice, scheduled by GitHub Actions."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import time

from automation.render import render
from automation.state import GitHubJournal, LocalJournal, PipelineError, paid_once, request, session

ROOT = Path(__file__).resolve().parent
VEO_MODEL = 'veo-3.1-fast-generate-preview'
VOICE_ID = 'allzfJXSadaum3SM2UFr'


def load_plan(path):
    plan = json.loads(Path(path).read_text())
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', plan.get('id', '')):
        raise PipelineError('Plan id must be a short lowercase slug.')
    narration = plan.get('narration', '')
    if not isinstance(narration, str) or not 400 <= len(narration) <= 1400:
        raise PipelineError('A 60-second Turkish narration must contain 400–1400 characters.')
    if plan.get('duration_seconds') != 60 or len(plan.get('shots', [])) != 8:
        raise PipelineError('Plan must specify 60 seconds and exactly eight shots.')
    if not plan.get('sources') or not all(isinstance(s, str) and s.startswith('https://')
                                        for s in plan['sources']):
        raise PipelineError('Plan must include medical source links outside the narration.')
    for shot in plan['shots']:
        if not isinstance(shot.get('prompt'), str) or not 40 <= len(shot['prompt']) <= 2500:
            raise PipelineError('Each shot needs a descriptive motion prompt.')
    return plan


def job_name(plan, model, voice, director):
    data = json.dumps({'plan': plan, 'model': model, 'voice': voice, 'director': director},
                      sort_keys=True, ensure_ascii=False)
    return plan['id'] + '-' + hashlib.sha256(data.encode()).hexdigest()[:16]


def required_keys(director):
    keys = ['GEMINI_API_KEY', 'ELEVENLABS_API_KEY']
    if director:
        keys.append('ANTHROPIC_API_KEY')
    return [key for key in keys if not os.environ.get(key, '').strip()]


def direct_shots(plan):
    """Claude may refine visual motion, never the medical narration."""
    payload = {'model': os.environ.get('CLAUDE_MODEL') or 'claude-sonnet-4-6', 'max_tokens': 3200,
               'system': 'You are a film director for pediatric education. Return only a JSON '
                         'array of exactly 8 English video prompts. Refine the provided visual '
                         'actions into photorealistic 8-second portrait single-take videos. '
                         'Real subject movement is mandatory. No still-image pans, forced feeding, '
                         'unsafe infant posture, on-screen text or generated speech. Do not change '
                         'the narration or invent medical claims. Preserve each shot meaning.',
               'messages': [{'role': 'user', 'content': json.dumps(plan, ensure_ascii=False)}]}
    response = request(session(), 'POST', 'https://api.anthropic.com/v1/messages',
                       headers={'x-api-key': os.environ['ANTHROPIC_API_KEY'],
                                'anthropic-version': '2023-06-01'}, json=payload).json()
    text = ''.join(c.get('text', '') for c in response.get('content', []) if c.get('type') == 'text')
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip())
    prompts = json.loads(text)
    if (not isinstance(prompts, list) or len(prompts) != 8
            or any(not isinstance(p, str) or not 40 <= len(p) <= 2500 for p in prompts)):
        raise PipelineError('Claude returned an invalid shot plan; no video requests were sent.')
    return prompts


def synthesize(text, voice):
    response = request(session(), 'POST',
                       f'https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps',
                       headers={'xi-api-key': os.environ['ELEVENLABS_API_KEY']},
                       params={'output_format': 'mp3_44100_128'},
                       json={'text': text, 'model_id': 'eleven_multilingual_v2', 'language_code': 'tr',
                             'voice_settings': {'stability': 0.5, 'similarity_boost': 0.75}}).json()
    # This complete response is persisted once, so a later runner can recover the paid audio.
    return {'audio_base64': response.get('audio_base64'),
            'alignment': response.get('alignment') or response.get('normalized_alignment')}


class Veo:
    def __init__(self, model):
        from google import genai
        from google.genai import types
        self.types = types
        self.model = model
        self.client = genai.Client(api_key=os.environ['GEMINI_API_KEY'],
                                   http_options=types.HttpOptions(
                                       timeout=120_000,
                                       retry_options=types.HttpRetryOptions(attempts=1)))

    def submit(self, prompt):
        op = self.client.models.generate_videos(
            model=self.model, prompt=prompt,
            config=self.types.GenerateVideosConfig(number_of_videos=1, duration_seconds=8,
                                                   aspect_ratio='9:16', resolution='720p'))
        if not op.name:
            raise PipelineError('Veo returned no operation id; automatic retry blocked.')
        return {'name': op.name}

    def download(self, receipt, path, timeout=1800):
        # Polling an existing operation is read-only and can be resumed after interruption.
        op = self.types.GenerateVideosOperation(name=receipt['name'])
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            op = self.client.operations.get(op)
            if op.done:
                break
            time.sleep(15)
        if not op.done:
            raise PipelineError('Veo is still processing. Rerun to poll the saved operation, not resubmit.')
        if op.error:
            raise PipelineError('Veo generation failed; operation saved. No automatic replacement was charged.')
        response = op.response or op.result
        videos = response.generated_videos if response else None
        if not videos:
            raise PipelineError('Veo returned no video (possibly provider filtering). No automatic replacement.')
        self.client.files.download(file=videos[0].video)
        temporary = path.with_suffix('.part.mp4')
        videos[0].video.save(str(temporary))
        temporary.replace(path)


def make_video(plan, name, state, journal, directory, model, voice, director):
    from automation.render import captions, probe
    directory.mkdir(parents=True, exist_ok=True)
    if director:
        prompts = paid_once(journal, name, state, 'director', lambda: direct_shots(plan))
    else:
        prompts = [shot['prompt'] for shot in plan['shots']]
    result = paid_once(journal, name, state, 'voice', lambda: synthesize(plan['narration'], voice))
    try:
        content = base64.b64decode(result['audio_base64'], validate=True)
    except (KeyError, ValueError, TypeError):
        raise PipelineError('Saved voice response is invalid; it will not be generated twice.') from None
    if not content:
        raise PipelineError('Saved voice audio is empty.')
    audio = directory/'voice.mp3'
    audio.write_bytes(content)
    if not result.get('alignment'):
        raise PipelineError('Saved audio has no alignment; manual recovery is required.')
    last_word = captions(result['alignment'], directory)
    if not 45 <= float(probe(audio)['format']['duration']) <= 59.5 or last_word > 59.75:
        raise PipelineError('Narration must fit 45–59.5 seconds; no video generation was started.')
    (directory/'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    (directory/'narration.txt').write_text(plan['narration'])
    (directory/'sources.txt').write_text('\n'.join(plan['sources']) + '\n')
    veo = Veo(model)
    clips = []
    for i, prompt in enumerate(prompts):
        slot = f'shot-{i+1:02}'
        path = directory/(slot + '.mp4')
        receipt = paid_once(journal, name, state, slot, lambda p=prompt: veo.submit(p))
        if not path.exists():
            veo.download(receipt, path)
        if path.stat().st_size < 1024:
            raise PipelineError('Downloaded video is empty or incomplete.')
        clips.append(path)
        print(f'Moving clip {i+1}/8 ready.', flush=True)
    render(clips, audio, result['alignment'], directory)
    state['complete'] = True
    state['voice_id'] = voice
    state['video_sha256'] = hashlib.sha256((directory/'video.mp4').read_bytes()).hexdigest()
    state['actions_run_id'] = os.environ.get('GITHUB_RUN_ID')
    journal.save(name, state)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', help='Optional filename from automation/plans; otherwise use the queue.')
    parser.add_argument('--validate', action='store_true', help='Validate plans without network or credentials.')
    parser.add_argument('--output', type=Path, default=Path('video-output'))
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        if args.plan and not re.fullmatch(r'[a-z0-9-]+\.json', args.plan):
            raise PipelineError('Plan must be a filename from automation/plans.')
        paths = [ROOT/'plans'/args.plan] if args.plan else sorted((ROOT/'plans').glob('*.json'))
        plans = [load_plan(path) for path in paths]
        if not plans:
            raise PipelineError('No video plans found.')
        if args.validate:
            print(json.dumps({'valid_plans': [p['id'] for p in plans]}))
            return 0
        model = os.environ.get('VEO_MODEL') or VEO_MODEL
        voice = os.environ.get('ELEVENLABS_VOICE_ID') or VOICE_ID
        if not re.fullmatch(r'[A-Za-z0-9_-]+', voice):
            raise PipelineError('Invalid ElevenLabs voice id.')
        director = os.environ.get('USE_CLAUDE_DIRECTOR', '').lower() == 'true'
        director_key = (os.environ.get('CLAUDE_MODEL') or 'claude-sonnet-4-6') if director else False
        if os.environ.get('GITHUB_ACTIONS') == 'true':
            journal = GitHubJournal(os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_TOKEN'],
                                    os.environ['GITHUB_SHA'])
        else:
            journal = LocalJournal(args.output/'journal')
        for plan in plans:
            name = job_name(plan, model, voice, director_key)
            state = journal.load(name)
            if state.get('complete'):
                continue
            missing = required_keys(director)
            if missing:
                raise PipelineError('Missing GitHub Actions secrets: ' + ', '.join(missing))
            if not all(shutil.which(cmd) for cmd in ['ffmpeg', 'ffprobe']):
                raise PipelineError('Install ffmpeg and ffprobe before generation.')
            make_video(plan, name, state, journal, args.output/name, model, voice, director)
            summary = {'status': 'completed', 'plan': plan['id'], 'directory': name}
            break  # At most one plan / eight video submissions in a scheduled run.
        else:
            summary = {'status': 'queue_empty', 'message': 'All plans already completed; no paid requests.'}
        (args.output/'status.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    except Exception as exc:
        # SDK exception strings may contain credentials, signed URLs or request bodies.
        message = str(exc) if isinstance(exc, PipelineError) else f'Operation failed ({type(exc).__name__}); journal preserved.'
        (args.output/'status.json').write_text(json.dumps({'status': 'blocked', 'message': message}))
        print(message)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
