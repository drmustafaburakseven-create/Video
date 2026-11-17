"""Make a verified portrait MP4 for iPhone Photos, Reels and Shorts."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from automation.clinical_review import check
from automation.render import command, probe
from automation.state import PipelineError


def fast_start(path):
    boxes = []
    with Path(path).open('rb') as stream:
        while True:
            offset = stream.tell()
            header = stream.read(8)
            if len(header) != 8:
                break
            size, kind = struct.unpack('>I4s', header)
            if size == 1:
                size = struct.unpack('>Q', stream.read(8))[0]
            if not size:
                break
            if size < stream.tell()-offset:
                return False
            boxes.append(kind)
            stream.seek(offset+size)
    return b'moov' in boxes and b'mdat' in boxes and boxes.index(b'moov') < boxes.index(b'mdat')


def export(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or output.exists() or output.suffix.lower() != '.mp4':
        raise PipelineError('Use a new MP4 destination; preserve the original video.')
    check(source)
    original = probe(source)
    video = next((s for s in original['streams'] if s['codec_type'] == 'video'), None)
    if not video or video['width']*16 != video['height']*9:
        raise PipelineError('Social export requires an already composed 9:16 video.')
    output.parent.mkdir(parents=True, exist_ok=True)
    unknown = any(video.get(key) in (None, 'unknown', 'reserved')
                  for key in ['color_space', 'color_transfer', 'color_primaries'])
    color = 'colorspace=all=bt709:format=yuv420p'+(':iall=bt709' if unknown else '')
    filters = 'fps=24,'+color+',scale=720:1280:flags=lanczos,setsar=1'
    result = subprocess.run([
        'ffmpeg', '-v', 'error', '-nostdin', '-n', '-i', str(source),
        '-map', '0:v:0', '-map', '0:a:0', '-map_metadata', '-1', '-vf', filters,
        '-c:v', 'libx264', '-profile:v', 'main', '-level:v', '3.1', '-preset', 'medium',
        '-crf', '18', '-maxrate', '5M', '-bufsize', '10M', '-pix_fmt', 'yuv420p',
        '-tag:v', 'avc1', '-video_track_timescale', '24000', '-fps_mode', 'cfr',
        '-c:a', 'aac', '-profile:a', 'aac_low', '-b:a', '192k', '-ar', '48000',
        '-ac', '2', '-movflags', '+faststart', str(output)], capture_output=True, text=True)
    if result.returncode:
        raise PipelineError('iPhone export failed; original media was preserved.')
    media = probe(output)
    streams = {s['codec_type']: s for s in media['streams']}
    v, a = streams.get('video', {}), streams.get('audio', {})
    valid = (set(streams) == {'video', 'audio'} and v.get('codec_name') == 'h264'
             and v.get('profile') == 'Main' and v.get('level') == 31
             and v.get('pix_fmt') == 'yuv420p' and v.get('avg_frame_rate') == '24/1'
             and (v.get('width'), v.get('height')) == (720, 1280)
             and v.get('codec_tag_string') == 'avc1' and v.get('color_space') == 'bt709'
             and a.get('codec_name') == 'aac' and a.get('profile') == 'LC'
             and a.get('channels') == 2 and a.get('sample_rate') == '48000'
             and abs(float(media['format']['duration'])-float(original['format']['duration'])) < .1
             and fast_start(output))
    if not valid:
        raise PipelineError('Export did not pass iPhone/social format checks.')
    command(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(output), '-f', 'null', '-'])
    report = {'file': str(output), 'duration': float(media['format']['duration']),
              'video': 'H.264 Main Level 3.1, 720x1280, CFR 24, BT.709',
              'audio': 'AAC-LC, 48kHz, stereo', 'fast_start': True,
              'full_decode': 'passed', 'subtitle_streams': 0,
              'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'output_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
              'physical_iphone_tested': False, 'social_upload_performed': False}
    output.with_suffix('.validation.json').write_text(json.dumps(report, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(json.dumps(export(args.source, args.output)))


if __name__ == '__main__':
    main()
