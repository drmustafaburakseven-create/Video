"""Compose moving clips, short dissolves and word-aligned subtitles using FFmpeg."""
import json
import math
from pathlib import Path
import re
import subprocess
import textwrap

from automation.state import PipelineError


def probe(path):
    return json.loads(subprocess.check_output(
        ['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))


def command(args):
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode:
        raise PipelineError('FFmpeg operation failed. Verify input media and installed filters.')


def timestamp(value, srt=False):
    units = 1000 if srt else 100
    n = round(value * units)
    return f'{n//(3600*units):02}:{n//(60*units)%60:02}:{n//units%60:02}' + (
        f',{n%units:03}' if srt else f'.{n%units:02}')


def captions(alignment, directory, delay=0.25):
    chars = alignment.get('characters', [])
    starts = alignment.get('character_start_times_seconds', [])
    ends = alignment.get('character_end_times_seconds', [])
    if not chars or len(chars) != len(starts) or len(chars) != len(ends):
        raise PipelineError('Missing/inconsistent voice alignment; saved audio will not be regenerated.')
    previous = -1
    for char, start, end in zip(chars, starts, ends):
        if (not isinstance(char, str) or not isinstance(start, (int, float))
                or not isinstance(end, (int, float)) or not math.isfinite(start)
                or not math.isfinite(end) or start < previous or end < start or start < 0):
            raise PipelineError('Invalid voice timestamps.')
        previous = start
    raw = ''.join(chars)
    # Alignment is character based; handle providers returning multi-character tokens.
    offsets = []
    for index, char in enumerate(chars):
        offsets.extend([index] * len(char))
    words = [(m.group(), starts[offsets[m.start()]], ends[offsets[m.end()-1]])
             for m in re.finditer(r'\S+', raw)]
    groups, group = [], []
    for word in words:
        candidate = ' '.join(w[0] for w in group + [word])
        if group and (len(candidate) > 58 or word[2] - group[0][1] > 3.1):
            groups.append(group)
            group = []
        group.append(word)
        if word[0][-1:] in '.!?;:':
            groups.append(group)
            group = []
    if group:
        groups.append(group)
    if not groups:
        raise PipelineError('No spoken words in alignment.')
    header = '''[Script Info]
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280
ScaledBorderAndShadow: yes
WrapStyle: 0
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Subtitle,DejaVu Sans,30,&H00FFFFFF,&H00FFFFFF,&H301B2B40,&H301B2B40,-1,0,0,0,100,100,0,0,3,5,0,2,56,70,170,1
Style: Brand,DejaVu Sans,22,&H00FFF7EE,&H00FFFFFF,&H801B2B40,&H801B2B40,-1,0,0,0,100,100,0,0,3,3,0,7,40,40,45,1
Style: Label,DejaVu Sans,15,&H00FFF7EE,&H00FFFFFF,&H801B2B40,&H801B2B40,0,0,0,0,100,100,0,0,3,3,0,7,40,40,82,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:01:00.00,Brand,,0,0,0,,Dr. Mustafa Burak Seven
Dialogue: 0,0:00:00.00,0:01:00.00,Label,,0,0,0,,Yapay zekâ ile oluşturulmuş temsili video
'''
    events, srt = [], []
    for i, group in enumerate(groups):
        start, end = group[0][1] + delay, group[-1][2] + delay
        text = '\n'.join(textwrap.wrap(' '.join(w[0] for w in group), 33, break_long_words=False))
        safe = text.replace('\\', '').replace('{', '').replace('}', '').replace('\n', r'\N')
        events.append(f'Dialogue: 1,{timestamp(start)},{timestamp(end)},Subtitle,,0,0,0,,{safe}')
        srt.append(f'{i+1}\n{timestamp(start, True)} --> {timestamp(end, True)}\n{text}\n')
    directory = Path(directory)
    (directory/'captions.ass').write_text(header + '\n'.join(events) + '\n')
    (directory/'captions.srt').write_text('\n'.join(srt))
    return ends[-1] + delay


def render(clips, audio, alignment, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if len(clips) != 8:
        raise PipelineError('A 60-second plan requires eight moving clips.')
    duration = float(probe(audio)['format']['duration'])
    last_word = captions(alignment, output)
    if duration > 59.5 or last_word > 59.75:
        raise PipelineError('Narration exceeds 60 seconds. Audio is preserved; shorten the plan explicitly.')
    if duration < 45:
        raise PipelineError('Narration is too short for the 60-second format.')
    args = ['ffmpeg', '-v', 'error', '-nostdin', '-y']
    filters = []
    for i, clip in enumerate(clips):
        media = probe(clip)
        video = next((s for s in media['streams'] if s['codec_type'] == 'video'), None)
        if not video or float(video.get('duration', media['format']['duration'])) < 7.9:
            raise PipelineError(f'Clip {i+1} must contain at least 8 seconds of video.')
        args += ['-i', str(clip)]
        filters.append(f'[{i}:v]trim=duration=8,setpts=PTS-STARTPTS,scale=720:1280:'
                       f'force_original_aspect_ratio=increase,crop=720:1280,setsar=1,fps=24,'
                       f'settb=AVTB,format=yuv420p[v{i}]')
    previous = 'v0'
    for i in range(1, 8):
        label = f'join{i}'
        filters.append(f'[{previous}][v{i}]xfade=transition=fade:duration=0.25:'
                       f'offset={i*7.75}[{label}]')
        previous = label
    # Controlled cwd keeps libass path parsing independent of user-provided paths.
    filters.append(f'[{previous}]trim=duration=60,ass=captions.ass[v]')
    filters.append('[8:a]adelay=250:all=1,apad,atrim=duration=60,'
                   'loudnorm=I=-16:TP=-1.5:LRA=9[a]')
    args += ['-i', str(Path(audio).resolve()), '-filter_complex_threads', '1',
             '-filter_complex', ';'.join(filters), '-map', '[v]', '-map', '[a]', '-t', '60',
             '-c:v', 'libx264', '-preset', 'fast', '-crf', '19', '-threads', '2',
             '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000',
             '-movflags', '+faststart', 'video.mp4']
    # Resolve clip paths before changing cwd.
    for i, arg in enumerate(args):
        if i and args[i-1] == '-i':
            args[i] = str(Path(arg).resolve())
    result = subprocess.run(args, cwd=output, capture_output=True, text=True)
    if result.returncode:
        raise PipelineError('Motion-video composition failed; original clips and audio are preserved.')
    final = output/'video.mp4'
    command(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(final), '-f', 'null', '-'])
    media = probe(final)
    streams = {s['codec_type']: s for s in media['streams']}
    if abs(float(media['format']['duration']) - 60) > 0.1:
        raise PipelineError('Final video duration validation failed.')
    if abs(float(streams['video']['duration']) - float(streams['audio']['duration'])) > 0.1:
        raise PipelineError('Audio/video duration mismatch.')
    report = {'duration_seconds': float(media['format']['duration']), 'full_decode': 'passed',
              'dimensions': [720, 1280], 'source': 'eight generated motion clips',
              'transition_seconds': 0.25, 'voice_speed_changed': False}
    (output/'validation.json').write_text(json.dumps(report, indent=2))
    return final
