"""Export and verify the 30 fps phone profile of the reference reel."""
import json
import subprocess

from automation.iphone_export import fast_start
from automation.media import digest
from automation.render import probe
from automation.state import PipelineError


def phone_copy(master, target):
    """30 fps lightweight iPhone copy; preserve speech speed and exactly 60 s."""
    record = target.with_suffix('.validation.json')
    if target.exists():
        if record.is_file():
            saved = json.loads(record.read_text())
            if (saved.get('source_sha256') == digest(master)
                    and saved.get('output_sha256') == digest(target)):
                return target
        raise PipelineError('Mevcut telefon kopyası bu videoyla eşleşmiyor; üzerine yazılmadı.')
    temporary = target.with_suffix('.part.mp4')
    r = subprocess.run([
        'ffmpeg', '-v', 'error', '-nostdin', '-y', '-i', str(master),
        '-map', '0:v:0', '-map', '0:a:0', '-vf', 'scale=720:1280,setsar=1,fps=30',
        '-c:v', 'libx264', '-preset', 'fast', '-profile:v', 'baseline', '-level:v', '3.1',
        '-pix_fmt', 'yuv420p', '-b:v', '1800k', '-maxrate', '2500k', '-bufsize', '5000k',
        '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709',
        '-bsf:v', 'h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1',
        '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-ac', '2', '-t', '60',
        '-video_track_timescale', '30000', '-movflags', '+faststart', str(temporary)],
        capture_output=True)
    if r.returncode:
        raise PipelineError('Telefon kopyası hazırlanamadı; asıl video korundu.')
    d = probe(temporary)
    v = next(s for s in d['streams'] if s['codec_type'] == 'video')
    a = next(s for s in d['streams'] if s['codec_type'] == 'audio')
    if (abs(float(d['format']['duration'])-60) > .001 or v.get('nb_frames') != '1800'
            or v.get('avg_frame_rate') != '30/1' or not fast_start(temporary)
            or (v.get('width'), v.get('height')) != (720, 1280)
            or v.get('codec_name') != 'h264' or v.get('pix_fmt') != 'yuv420p'
            or v.get('color_space') != 'bt709' or a.get('codec_name') != 'aac'
            or a.get('sample_rate') != '48000' or a.get('channels') != 2):
        raise PipelineError('Telefon kopyası süre/kare doğrulamasını geçemedi.')
    r = subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(temporary),
                        '-f', 'null', '-'], capture_output=True)
    if r.returncode:
        raise PipelineError('Telefon kopyası tam çözümleme kontrolünü geçemedi.')
    temporary.replace(target)
    record.write_text(json.dumps({'source_sha256': digest(master),
                                 'output_sha256': digest(target),
                                 'seconds': 60, 'full_decode': 'passed', 'fps': 30,
                                 'fast_start': True, 'physical_iphone_tested': False}, indent=2)+'\n')
    return target
