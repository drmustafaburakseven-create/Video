"""Opt-in short speaking-photo proof: Gemini native speech -> own ElevenLabs voice.

This is not the existing-master-audio avatar route and does not create a
60-second Reels video. Generated wording, identity and lip sync need review.
"""
import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import wave
from array import array

from automation.daily import RunLock
from automation.pipeline import Omni, VEO_MODEL, VOICE_ID
from automation.produce import _portrait
from automation.render import probe
from automation.state import LocalJournal, PipelineError, paid_once, request


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def speaking_prompt(speech, duration, performance="calm"):
    if performance not in {"calm", "energetic"}:
        raise PipelineError("Unsupported speaking performance.")
    if (not isinstance(speech, str) or not 3 <= len(speech.strip()) <= 300
            or re.search(r'[\x00-\x1f<>]|https?://', speech)):
        raise PipelineError('Use a short plain Turkish sentence without links or instructions.')
    if type(duration) is not int or not 3 <= duration <= 10:
        raise PipelineError('A speaking-photo proof must be 3–10 whole seconds.')
    # Keep this prompt/identity compatible with the first recorded four-second
    # proof. Its failed receipt must not become an accidental new purchase.
    prompt = (f'Create a photorealistic {duration}-second portrait 9:16 video of the same adult man in the supplied photograph. '
            'Preserve his facial identity, age, hairstyle and white medical coat. '
            'Head and shoulders, fixed camera, subtle natural blinking. '
            f'He calmly speaks one short Turkish sentence, exactly: {json.dumps(speech.strip(), ensure_ascii=False)} '
            'Natural Turkish male voice with clear lip sync, no other speech, no music, no sound effects, '
            'no subtitles, no new people. Finish the sentence within the four-second shot. '
            'This adult supplied his own image for this educational video.').replace(
                'within the four-second shot.', f'within the {"four" if duration == 4 else duration}-second shot.')
    if performance == "energetic":
        prompt = prompt.replace('He calmly speaks', 'He speaks with warm, confident, lively pediatric educator energy')
        prompt += (' Begin speaking within the first half-second. Conversational Turkish, varied intonation, '
                   'clear key-word emphasis and natural short pauses. Friendly direct eye contact, '
                   'subtle eyebrow expression and one restrained hand gesture. No shouting, theatrical acting, '
                   'fearmongering or robotic cadence. Finish all words before the final half-second. '
                   'Keep the head and face stable enough for natural lip synchronization.')
    return prompt


def identity(portrait_bytes, prompt, model, duration, attempt=None):
    if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', model):
        raise PipelineError('Invalid Gemini model identifier.')
    data = {'model': model, 'image_sha256': hashlib.sha256(portrait_bytes).hexdigest(),
            'prompt': prompt, 'duration': duration}
    if attempt is not None:
        if not isinstance(attempt, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,39}', attempt):
            raise PipelineError('An explicit retry name must be a short lowercase slug.')
        # Only a deliberate caller-selected name creates another paid identity.
        # Reusing that name resumes the same receipt, including uncertain ones.
        data['attempt'] = attempt
    return 'gemini-speaking-'+hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:24]


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', value):
        raise PipelineError('Gemini returned an invalid interaction ID; automatic resubmission blocked.')
    return value


def _operation(generator, receipt, journal, name, state, directory):
    result = request(generator.client, 'GET', generator.base+'/interactions/'+
                     _identifier(receipt.get('interaction_id'))).json()
    status = result.get('status')
    if status not in ['in_progress', 'completed', 'failed', 'cancelled', 'canceled', 'requires_action']:
        status = 'unknown'
    codes = [error.get('code') for error in result.get('errors', []) if isinstance(error, dict)]
    codes = [code for code in codes if isinstance(code, str) and re.fullmatch(r'[A-Z_]{1,60}', code)]
    value = {'status': status, 'provider_codes': codes}
    # Provider messages, media URLs and request headers do not enter this report.
    state['operation_status'] = value
    journal.save(name, state)
    _write(directory/'provider-status.json', value)
    if status in ['failed', 'cancelled', 'canceled', 'requires_action', 'unknown']:
        detail = ': '+', '.join(codes) if codes else ''
        raise PipelineError('Gemini speaking-video generation did not complete'+detail+
                            '; the saved interaction will not be resubmitted automatically.')
    return value


def _native_media(path, expected_duration):
    data = probe(path)
    video = next((s for s in data.get('streams', []) if s.get('codec_type') == 'video'), None)
    audio = next((s for s in data.get('streams', []) if s.get('codec_type') == 'audio'), None)
    if not video or not audio:
        raise PipelineError('Gemini proof must contain both moving video and native audio; no voice conversion sent.')
    seconds = float(video.get('duration', data.get('format', {}).get('duration', 0)))
    if (not math.isfinite(seconds) or abs(seconds-expected_duration) > 0.15
            or int(video.get('width', 0)) <= 0 or int(video.get('height', 0)) <= 0
            or video.get('nb_frames') not in (None, 'N/A') and int(video['nb_frames']) < 2):
        raise PipelineError('Gemini proof duration or video frames do not match the requested short shot.')
    return seconds


def _audible(wav):
    try:
        with wave.open(str(wav), 'rb') as source:
            if source.getsampwidth() != 2 or source.getcomptype() != 'NONE':
                raise ValueError
            values = array('h', source.readframes(source.getnframes()))
        if not values:
            raise ValueError
        rms = math.sqrt(sum(value*value for value in values)/len(values))
        dbfs = 20*math.log10(rms/32768) if rms else -math.inf
    except (OSError, ValueError, wave.Error):
        raise PipelineError('Unable to measure native speech WAV; no conversion sent.') from None
    if dbfs < -50:
        raise PipelineError('Generated audio is silent or too quiet; no voice conversion sent.')
    # Energy is not speech recognition: wording still needs a human check.
    return round(dbfs, 3)


def _video_hash(path):
    result = subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(path),
                             '-map', '0:v:0', '-c', 'copy', '-f', 'hash', '-hash', 'sha256', '-'],
                            capture_output=True, text=True)
    if result.returncode or not re.fullmatch(r'SHA256=[0-9a-f]{64}\s*', result.stdout):
        raise PipelineError('Unable to verify unchanged video stream.')
    return result.stdout.strip().split('=', 1)[1]


def remux(native, converted, output, *, max_drift=0.15):
    """Copy video packets; never stretch, truncate, pad or replace narration."""
    native, converted, output = map(Path, [native, converted, output])
    original = probe(native)
    video = next(s for s in original['streams'] if s['codec_type'] == 'video')
    video_seconds = float(video.get('duration', original['format']['duration']))
    audio_seconds = float(probe(converted)['format']['duration'])
    if not all(map(math.isfinite, [video_seconds, audio_seconds])) or abs(audio_seconds-video_seconds) > max_drift:
        raise PipelineError('Converted speech differs from video duration; no retiming or truncation performed.')
    temporary = output.with_suffix('.part.mp4')
    if output.is_symlink() or temporary.is_symlink():
        raise PipelineError('Proof output must not be a symbolic link.')
    result = subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-i', str(native),
                             '-i', str(converted), '-map', '0:v:0', '-map', '1:a:0',
                             '-map_metadata', '-1', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
                             '-ar', '48000', '-movflags', '+faststart', str(temporary)],
                            capture_output=True, text=True)
    if result.returncode:
        raise PipelineError('Voice/video composition failed; both source files were preserved.')
    try:
        result = subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(temporary), '-f', 'null', '-'],
                                capture_output=True)
        data = probe(temporary)
        output_video = next(s for s in data['streams'] if s['codec_type'] == 'video')
        output_audio = next(s for s in data['streams'] if s['codec_type'] == 'audio')
        if (result.returncode or abs(float(output_video.get('duration', 0))-video_seconds) > 0.05
                or abs(float(output_audio.get('duration', 0))-video_seconds) > max_drift
                or _video_hash(native) != _video_hash(temporary)):
            raise PipelineError('Final proof timing or unchanged-video verification failed.')
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return output


def create(portrait, speech, voice, journal, output, *, duration=4, model=VEO_MODEL, timeout=1800, attempt=None, performance="calm"):
    """Create one inspectable proof; no claim of verified words or perfect lip sync."""
    from automation.voice_changer import convert, extract_audio
    prompt = speaking_prompt(speech, duration, performance)
    if not isinstance(voice, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', voice):
        raise PipelineError('Invalid ElevenLabs voice identifier.')
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or timeout < 0):
        raise PipelineError('Polling timeout must be finite and nonnegative.')
    if not all(shutil.which(tool) for tool in ['ffmpeg', 'ffprobe']):
        raise PipelineError('Install FFmpeg and FFprobe before any speaking-photo request.')
    picture, picture_hash, extension = _portrait(portrait)
    name = identity(picture, prompt, model, duration, attempt)
    directory = Path(output).resolve()/name
    directory.mkdir(parents=True, exist_ok=True)
    with RunLock(directory/'.proof.lock'):
        state = journal.load(name)
        native = directory/'native.mp4'
        # Gemini's expensive generation is shared across output-voice choices.
        voice_directory = directory/('voice-'+hashlib.sha256(voice.encode()).hexdigest()[:16])
        voice_directory.mkdir(exist_ok=True)
        final = voice_directory/'proof.mp4'
        saved = state.get('conversions', {}).get(voice, {})
        if final.exists():
            if final.is_symlink() or _sha(final) != saved.get('output_sha256'):
                raise PipelineError('Existing proof differs from its saved receipt; no file overwritten.')
            return final
        if native.exists():
            if native.is_symlink() or _sha(native) != state.get('native_sha256'):
                raise PipelineError('Native video differs from its saved receipt; no conversion started.')
        else:
            if not os.environ.get('GEMINI_API_KEY'):
                raise PipelineError('Missing secure binding: GEMINI_API_KEY')
            if 'clip' not in state and not os.environ.get('ELEVENLABS_API_KEY'):
                raise PipelineError('Missing secure binding: ELEVENLABS_API_KEY; no video purchase started.')
            generator = Omni(model)
            try:
                def submit():
                    result = request(generator.client, 'POST', generator.base+'/interactions', json={
                        'model': model,
                        'input': [{'type': 'image', 'data': base64.b64encode(picture).decode(),
                                   'mime_type': 'image/png' if extension == '.png' else 'image/jpeg'},
                                  {'type': 'text', 'text': prompt}],
                        'background': True, 'store': True,
                        'response_format': {'type': 'video', 'aspect_ratio': '9:16', 'duration': f'{duration}s',
                                            'resolution': '720p', 'delivery': 'uri'}}).json()
                    return {'interaction_id': _identifier(result.get('id'))}
                receipt = paid_once(journal, name, state, 'clip', submit)
                _write(directory/'request.json', {'journal': name, 'receipt': receipt, 'model': model,
                                                  'portrait_sha256': picture_hash, 'requested_speech': speech,
                                                  'duration_seconds': duration, 'attempt': attempt,
                                                  'original_tts_used': False})
                _operation(generator, receipt, journal, name, state, directory)
                try:
                    generator.download(receipt, native, timeout=timeout)
                except PipelineError:
                    # Poll once to retain a terminal status reached while the
                    # downloader was waiting; never submit a replacement.
                    try:
                        _operation(generator, receipt, journal, name, state, directory)
                    except PipelineError:
                        pass
                    raise
                state['native_sha256'] = _sha(native)
                # Omni.download returns only after the saved operation completes.
                # Do not leave the earlier polling snapshot marked in progress.
                state['operation_status'] = {'status': 'completed', 'provider_codes': []}
                journal.save(name, state)
                _write(directory/'provider-status.json', state['operation_status'])
            finally:
                generator.client.close()
        actual_duration = _native_media(native, duration)
        original_audio = directory/'native-speech.wav'
        if original_audio.exists():
            if original_audio.is_symlink() or _sha(original_audio) != state.get('native_audio_sha256'):
                raise PipelineError('Prepared native audio differs or lacks its checkpoint; preserve it before recovery.')
        else:
            extract_audio(native, original_audio)
            # Commit the exact source audio before a possibly paid conversion.
            state['native_audio_sha256'] = _sha(original_audio)
            journal.save(name, state)
        level = _audible(original_audio)
        converted = convert(original_audio, voice, journal, voice_directory/'converted.mp3')
        remux(native, converted, final)
        manifest = {'schema': 'gemini-speaking-proof-v1', 'model': model, 'voice_id': voice,
                    'portrait_sha256': picture_hash, 'requested_speech': speech,
                    'duration_seconds': actual_duration, 'native_audio_rms_dbfs': level,
                    'native_video_sha256': _sha(native), 'converted_audio_sha256': _sha(converted),
                    'output_sha256': _sha(final), 'original_tts_used': False,
                    'generated_speech_text_verified': False, 'face_identity_review': 'required',
                    'lip_sync_review': 'required', 'clinical_review': 'required',
                    'voice_speed_changed': False, 'video_retimed': False,
                    'synthetic_media': True, 'full_reels_created': False, 'auto_published': False}
        _write(voice_directory/'proof-manifest.json', manifest)
        state.setdefault('conversions', {})[voice] = {'output_sha256': manifest['output_sha256']}
        journal.save(name, state)
        return final


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--portrait', required=True, type=Path)
    parser.add_argument('--speech', required=True, help='One short Turkish sentence to be generated, then reviewed.')
    parser.add_argument('--voice', default=VOICE_ID)
    parser.add_argument('--duration', type=int, default=4)
    parser.add_argument('--performance', choices=['calm', 'energetic'], default='calm')
    parser.add_argument('--model', default=VEO_MODEL)
    parser.add_argument('--output', type=Path, default=Path('video-output/gemini-avatar'))
    parser.add_argument('--journal', type=Path, default=Path('video-output/journal'))
    parser.add_argument('--timeout', type=float, default=1800)
    parser.add_argument('--attempt', help='Explicit new paid attempt name after an account/access change; reuse the same name to resume.')
    args = parser.parse_args(argv)
    try:
        final = create(args.portrait, args.speech, args.voice, LocalJournal(args.journal), args.output,
                       duration=args.duration, model=args.model, timeout=args.timeout, attempt=args.attempt, performance=args.performance)
        print(json.dumps({'status': 'proof_ready', 'file': str(final), 'full_reels_created': False,
                          'lip_sync_review': 'required', 'speech_text_review': 'required'}, ensure_ascii=False))
        return 0
    except Exception as error:
        message = str(error) if isinstance(error, PipelineError) else f'Proof stopped ({type(error).__name__}); receipts preserved.'
        print(json.dumps({'status': 'blocked', 'message': message}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
