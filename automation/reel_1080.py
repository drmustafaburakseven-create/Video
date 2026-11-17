"""Explicit 1080p/30 Reel profile; preserve source speech and reject unsafe cuts.

This does not change the older 720p production path. Audio must already be
reviewed and mixed at its intended absolute timestamps. No paid API calls.
"""
import json
import math
from pathlib import Path
import subprocess

from automation.clinical_review import check
from automation.render import probe
from automation.state import PipelineError


PROFILE = {"width": 1080, "height": 1920, "fps": 30, "seconds": 60,
           "video_bitrate": "14M", "audio_bitrate": "320k", "lufs": -14,
           "true_peak": -1, "safe_area": {"left": 60, "right": 140,
                                         "top": 220, "bottom": 380}}


def validate_segments(segments, *, metadata=probe):
    """Require full coverage, source motion, available frames and reviewed media."""
    previous = 0
    for segment in segments:
        start, end = segment['start'], segment['end']
        offset = segment.get('offset', 0)
        if not all(type(v) in (int, float) and math.isfinite(v)
                   for v in (start, end, offset)):
            raise PipelineError('Scene times must be finite numbers.')
        if abs(start-previous) > 1e-6 or end <= start or offset < 0:
            raise PipelineError('Scenes must cover the timeline without gaps or overlaps.')
        if any(abs(v*30-round(v*30)) > 1e-5 for v in (start, end)):
            raise PipelineError('Scene boundaries must lie on 30 fps frame boundaries.')
        source = Path(segment['path'])
        check(source)
        info = metadata(source)
        videos = [s for s in info['streams'] if s.get('codec_type') == 'video']
        if not videos or videos[0].get('codec_name') in ('png', 'mjpeg'):
            raise PipelineError('This profile requires moving video sources.')
        available = float(videos[0].get('duration', info['format']['duration']))
        if offset+end-start > available+1/60:
            raise PipelineError('Scene exceeds available live footage; no freeze padding allowed.')
        previous = end
    if abs(previous-60) > 1e-6:
        raise PipelineError('The profile requires exactly 60 seconds of scenes.')


def run(args, log):
    with Path(log).open('w') as stream:
        result = subprocess.run(args, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise PipelineError('Media processing failed; inspect the saved local render log.')


def normalize_audio(source, output, directory):
    """Two-pass loudness normalization, with a little AAC true-peak headroom."""
    directory = Path(directory)
    first = directory/'loudness-pass1.log'
    run(['ffmpeg', '-hide_banner', '-nostdin', '-i', str(source), '-af',
         'loudnorm=I=-14:TP=-1.3:LRA=9:print_format=json', '-f', 'null', '-'], first)
    text = first.read_text()
    measured = json.loads(text[text.rfind('{'):text.rfind('}')+1])
    values = ':'.join(f'{key}={measured[value]}' for key, value in (
        ('measured_I', 'input_i'), ('measured_TP', 'input_tp'),
        ('measured_LRA', 'input_lra'), ('measured_thresh', 'input_thresh'),
        ('offset', 'target_offset')))
    run(['ffmpeg', '-v', 'warning', '-nostdin', '-y', '-i', str(source), '-af',
         'loudnorm=I=-14:TP=-1.3:LRA=9:'+values+':linear=true', '-ar', '48000',
         '-ac', '2', '-t', '60', '-c:a', 'pcm_s24le', str(output)],
        directory/'loudness-pass2.log')
    return measured


def validate_audio_timeline(audio_seconds, last_spoken_word):
    """Fail before encoding if a speech cut or missing quiet ending is possible."""
    if not all(type(v) in (int, float) and math.isfinite(v)
               for v in (audio_seconds, last_spoken_word)):
        raise PipelineError('Audio review times must be finite numbers.')
    if abs(audio_seconds-60) > 1/48000:
        raise PipelineError('Supply an exact 60-second PCM mix; speech is never auto-trimmed.')
    if not 0 < last_spoken_word <= 58.5:
        raise PipelineError('Reviewed speech must finish before the final 1.5-second card.')


def render(segments, audio, output, directory, *, last_spoken_word, ass=None, fonts=None):
    """Render exact-time scenes and optional reviewed ASS typography at 1080p30."""
    validate_segments(segments)
    validate_audio_timeline(float(probe(audio)['format']['duration']), last_spoken_word)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    normalized = directory/'normalized-master.wav'
    normalize_audio(audio, normalized, directory)
    prepared = []
    for index, segment in enumerate(segments):
        path = directory/f'scene-{index:02}.mp4'
        duration = segment['end']-segment['start']
        filters = ('scale=1080:1920:force_original_aspect_ratio=increase,'
                   'crop=1080:1920,setsar=1,fps=30,format=yuv420p')
        # Brief zoom entry is entirely spatial: it never changes speech speed.
        if segment.get('entry') == 'zoom':
            filters += (",scale=w='trunc(1080*(1.02+0.06*max(0,1-t/0.3))/2)*2'"
                        ':h=-2:eval=frame,crop=1080:1920')
        if segment.get('entry') in ('slide', 'whip'):
            # Spatial pan and short blur: original frame time remains unchanged.
            filters += (",scale=1166:2072,crop=1080:1920:x='43+43*max(0,1-t/0.3)':y=76,"
                        "boxblur=lr=12:lp=1:cr=6:cp=1:enable='lt(t,0.1)'")
        run(['ffmpeg', '-v', 'warning', '-nostdin', '-y', '-ss',
             str(segment.get('offset', 0)), '-i', str(segment['path']), '-an',
             '-vf', filters, '-frames:v', str(round(duration*30)),
             '-c:v', 'libx264', '-preset', 'fast', '-crf', '17', '-threads', '2',
             '-profile:v', 'high', '-level:v', '4.1', '-video_track_timescale', '30000',
             str(path)], directory/f'scene-{index:02}.log')
        prepared.append(path.resolve())
    listing = directory/'concat.txt'
    # All prepared paths are generated here, never interpolated through a shell.
    listing.write_text(''.join("file '"+str(p).replace("'", "'\\''")+"'\n" for p in prepared))
    vf = 'format=yuv420p'
    if ass:
        # FFmpeg filter strings have their own escaping rules, separate from argv.
        def escape(value):
            return str(Path(value).resolve()).replace('\\', '\\\\').replace(':', '\\:').replace("'", "'\\''")
        vf += ",ass=filename='"+escape(ass)+"'"
        if fonts:
            vf += ":fontsdir='"+escape(fonts)+"'"
    run(['ffmpeg', '-v', 'warning', '-nostdin', '-y', '-f', 'concat', '-safe', '0',
         '-i', str(listing), '-i', str(normalized), '-map', '0:v:0', '-map', '1:a:0',
         '-vf', vf, '-t', '60', '-r', '30', '-fps_mode', 'cfr', '-c:v', 'libx264',
         '-preset', 'slow', '-threads', '4', '-b:v', '14M', '-minrate', '14M',
         '-maxrate', '14M', '-bufsize', '28M', '-x264-params', 'nal-hrd=cbr:force-cfr=1',
         '-pix_fmt', 'yuv420p',
         '-profile:v', 'high', '-level:v', '4.1', '-tag:v', 'avc1',
         '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709',
         '-c:a', 'aac', '-b:a', '320k', '-ar', '48000', '-ac', '2',
         '-video_track_timescale', '30000', '-movflags', '+faststart', str(output)],
        directory/'export.log')
    return Path(output)
