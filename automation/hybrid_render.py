"""Assemble real stock, generated and lip-synced avatar clips on a fixed timeline.

The narrator is never retimed. Cuts are the default; adjacent B-roll clips may
request four-frame in-clip fades, which do not move speech or extend the
timeline. There is no image animation, frame padding, looping or slow-motion.
"""
import json
import math
from pathlib import Path
import subprocess

from automation.render import captions, command, probe, timestamp
from automation.state import PipelineError

FPS = 24
TOTAL_SECONDS = 60
KINDS = {'stock', 'generated', 'avatar'}
LABELS = {
    'generated': 'Yapay zekâ ile oluşturulmuş temsili görüntü',
    'avatar': 'Yapay zekâ ile oluşturulmuş konuşan avatar',
}


def _number(value, description):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise PipelineError(f'{description} must be a finite number.')
    return float(value)


def validate_segments(segments):
    """Validate timeline and available footage before starting an encode."""
    if not isinstance(segments, list) or not segments:
        raise PipelineError('At least one moving-video segment is required.')
    validated, cursor = [], 0.0
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict) or segment.get('kind') not in KINDS:
            raise PipelineError(f'Segment {index+1} has an invalid media kind.')
        duration = _number(segment.get('duration'), f'Segment {index+1} duration')
        start = _number(segment.get('start', cursor), f'Segment {index+1} start')
        source_start = _number(segment.get('source_start', 0), f'Segment {index+1} source offset')
        if duration <= 0 or source_start < 0 or abs(start-cursor) > 0.001:
            raise PipelineError('Segments must be positive, contiguous and ordered from time zero.')
        frames = round((cursor+duration)*FPS)-round(cursor*FPS)
        if frames < 1:
            raise PipelineError('Each segment must contain at least one output frame.')
        try:
            path = Path(segment['path']).resolve(strict=True)
        except (KeyError, TypeError, OSError):
            raise PipelineError(f'Segment {index+1} video file is missing.') from None
        if path.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.tiff'}:
            raise PipelineError('Hybrid rendering requires moving video, not still images.')
        media = probe(path)
        video = next((s for s in media.get('streams', []) if s.get('codec_type') == 'video'), None)
        if not video:
            raise PipelineError(f'Segment {index+1} contains no video stream.')
        available = float(video.get('duration', media.get('format', {}).get('duration', 0)))
        if not math.isfinite(available) or available+0.001 < source_start+duration:
            raise PipelineError(f'Segment {index+1} has insufficient source duration; padding and looping are disabled.')
        if video.get('nb_frames') is not None and video['nb_frames'] != 'N/A' and int(video['nb_frames']) < 2:
            raise PipelineError(f'Segment {index+1} has no moving video frames.')
        validated.append({**segment, 'path': path, 'start': cursor, 'duration': duration,
                          'source_start': source_start, 'frames': frames})
        cursor += duration
    if abs(cursor-TOTAL_SECONDS) > 0.001:
        raise PipelineError('Hybrid segments must total exactly 60 seconds.')
    return validated


def source_labels(ass_path, segments):
    """Replace the legacy global AI label with labels only over synthetic media."""
    path = Path(ass_path)
    lines = []
    for line in path.read_text().splitlines():
        if line.startswith('Dialogue:'):
            fields = line.split(',', 9)
            if len(fields) >= 4 and fields[3] == 'Label':
                continue
        lines.append(line)
    for segment in segments:
        label = LABELS.get(segment['kind'])
        if label:
            start = round(segment['start']*FPS)/FPS
            end = round((segment['start']+segment['duration'])*FPS)/FPS
            lines.append(f'Dialogue: 0,{timestamp(start)},{timestamp(end)},Label,,0,0,0,,{label}')
    path.write_text('\n'.join(lines)+'\n')


def render_hybrid(segments, audio, alignment, output):
    """Return a verified 60-second MP4, preserving the original narration timing."""
    segments = validate_segments(segments)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    audio = Path(audio).resolve()
    duration = float(probe(audio)['format']['duration'])
    last_word = captions(alignment, output)
    if not 45 <= duration <= 59.5 or last_word > 59.75:
        raise PipelineError('Narration must fit 45–59.5 seconds; the voice will not be stretched or truncated.')
    source_labels(output/'captions.ass', segments)
    args = ['ffmpeg', '-v', 'error', '-nostdin', '-y']
    filters = []
    for i, segment in enumerate(segments):
        args += ['-i', str(segment['path'])]
        vf = (f'[{i}:v]trim=start={segment["source_start"]}:duration={segment["duration"]},'
              f'setpts=PTS-STARTPTS,scale=720:1280:force_original_aspect_ratio=increase,'
              f'crop=720:1280,setsar=1,fps={FPS},trim=end_frame={segment["frames"]},'
              f'setpts=N/({FPS}*TB),format=yuv420p')
        if segment['kind'] != 'avatar' and segment['frames'] >= 12:
            if i > 0 and segments[i-1]['kind'] != 'avatar' and segment.get('transition') == 'fade':
                vf += ',fade=t=in:start_frame=0:nb_frames=4'
            if i+1 < len(segments) and segments[i+1]['kind'] != 'avatar' and segments[i+1].get('transition') == 'fade':
                vf += f',fade=t=out:start_frame={segment["frames"]-4}:nb_frames=4'
        filters.append(vf+f'[v{i}]')
    joined = ''.join(f'[v{i}]' for i in range(len(segments)))
    filters.append(joined+f'concat=n={len(segments)}:v=1:a=0,ass=captions.ass[v]')
    filters.append(f'[{len(segments)}:a]adelay=250:all=1,apad,atrim=duration=60,'
                   'loudnorm=I=-16:TP=-1.5:LRA=9[a]')
    args += ['-i', str(audio), '-filter_complex_threads', '1', '-filter_complex', ';'.join(filters),
             '-map', '[v]', '-map', '[a]', '-t', '60', '-c:v', 'libx264', '-preset', 'fast',
             '-crf', '19', '-threads', '2', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
             '-b:a', '192k', '-ar', '48000', '-movflags', '+faststart', 'video.mp4']
    result = subprocess.run(args, cwd=output, capture_output=True, text=True)
    if result.returncode:
        raise PipelineError('Hybrid video composition failed; original footage and narration are preserved.')
    final = output/'video.mp4'
    command(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(final), '-f', 'null', '-'])
    media = probe(final)
    streams = {s['codec_type']: s for s in media['streams']}
    if not {'video', 'audio'}.issubset(streams):
        raise PipelineError('Final hybrid file is missing video or audio.')
    if abs(float(media['format']['duration'])-TOTAL_SECONDS) > 0.05:
        raise PipelineError('Final hybrid duration is not 60 seconds.')
    if abs(float(streams['video']['duration'])-float(streams['audio']['duration'])) > 0.1:
        raise PipelineError('Hybrid audio/video duration mismatch.')
    if (streams['video']['width'], streams['video']['height']) != (720, 1280):
        raise PipelineError('Final hybrid dimensions are invalid.')
    if int(streams['video'].get('nb_frames', 0)) != TOTAL_SECONDS*FPS:
        raise PipelineError('Hybrid output frame count does not match the fixed timeline.')
    report = {'duration_seconds': float(media['format']['duration']), 'full_decode': 'passed',
              'dimensions': [720, 1280], 'frames': TOTAL_SECONDS*FPS,
              'source': 'mixed moving stock, generated and provided lip-synced avatar clips',
              'media_seconds': {kind: round(sum(s['duration'] for s in segments if s['kind']==kind), 6)
                                for kind in sorted(KINDS)},
              'transitions': 'clean cuts by default; optional four-frame B-roll fades; hard cuts at avatar boundaries',
              'voice_speed_changed': False, 'narration_delay_seconds': 0.25,
              'synthetic_labels': 'generated/avatar intervals only',
              'avatar_lip_sync': 'source footage required; no face animation or lip-sync fabricated by compositor'}
    (output/'validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return final
