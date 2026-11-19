"""Run the two Higgsfield avatar jobs, then assemble a reviewed 60-second Reel.

Episode inputs (photo, ElevenLabs stems, stocks, graphics and hashes) live in
private storage. No stock generation, posting or subscription purchase occurs.
"""
import argparse
import json
from pathlib import Path
import subprocess

from automation import higgsfield_avatar, ready_reel, publishing
from automation.iphone_export import fast_start
from automation.render import probe
from automation.state import LocalJournal, PipelineError


def asset(root, item):
    p = (root/item['path']).resolve()
    if not p.is_file() or higgsfield_avatar.sha(p) != item['sha256']:
        raise PipelineError('Bölüm girdisi eksik veya değişmiş; üretim/kurgu durdu.')
    return p


def phone_copy(master, target):
    """30 fps lightweight iPhone copy; preserve speech speed and exactly 60 s."""
    record = target.with_suffix('.validation.json')
    if target.exists():
        if record.is_file():
            saved = json.loads(record.read_text())
            if (saved.get('source_sha256') == higgsfield_avatar.sha(master)
                    and saved.get('output_sha256') == higgsfield_avatar.sha(target)):
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
    record.write_text(json.dumps({'source_sha256': higgsfield_avatar.sha(master),
                                 'output_sha256': higgsfield_avatar.sha(target),
                                 'seconds': 60, 'full_decode': 'passed', 'fps': 30,
                                 'fast_start': True, 'physical_iphone_tested': False}, indent=2)+'\n')
    return target


def assemble(root, package, output):
    script = json.loads(asset(root, package['script']).read_text())
    template = json.loads(asset(root, package['ready_template']).read_text())
    review_path = root/'avatar-reviews.json'
    if not review_path.is_file():
        raise PipelineError('İki yeni avatarın yüz, mimik ve dudak incelemesi henüz tamamlanmadı.')
    reviews = json.loads(review_path.read_text())
    avatars = {}
    for role in ('intro', 'outro'):
        receipt = json.loads((root/'avatars'/role/'avatar-receipt.json').read_text())
        job, assets = higgsfield_avatar.load_job(root/package['jobs'][role])
        expected = (root/'avatars'/role/'avatar-proof.mp4').resolve()
        if (receipt.get('provider') != 'higgsfield' or receipt.get('reference_sha256') != higgsfield_avatar.sha(assets['portrait'])
                or receipt.get('retimed') is not False or Path(receipt.get('file', '')).resolve() != expected
                or not expected.is_file() or higgsfield_avatar.sha(expected) != receipt.get('sha256')):
            raise PipelineError('Avatar üretim kaydı bu fotoğrafla ve gerçek dosyayla eşleşmiyor.')
        if job['mode'] == 'audio_driven' and receipt.get('audio_sha256') != higgsfield_avatar.sha(assets['audio']):
            raise PipelineError('Avatar farklı sesle üretilmiş; dudak zamanlaması yeniden incelenmeli.')
        review = reviews.get(role, {})
        if (review.get('status') != 'approved' or review.get('sha256') != receipt['sha256']
                or not review.get('identity_checked') or not review.get('lipsync_checked')
                or not review.get('hands_checked')):
            raise PipelineError('Avatar incelemesi eksik veya incelenen dosya değişmiş.')
        avatars[role] = {'path': str(expected), 'sha256': receipt['sha256']}
    for seg in template['segments']:
        if seg['role'] in avatars:
            seg.update(avatars[seg['role']])
        else:
            seg['path'] = str(asset(root, seg))
    for name in ('audio', 'captions'):
        template[name]['path'] = str(asset(root, template[name]))
    for font in template['fonts']:
        font['path'] = str(asset(root, font))
    template.update(visual_review='approved', speech_timing_review='approved')
    final_manifest = root/'ready.json'
    final_manifest.write_text(json.dumps(template, ensure_ascii=False, indent=2)+'\n')
    master = ready_reel.render(script, final_manifest, output)
    phone = phone_copy(master, output/'video-telefon.mp4')
    return {'status': 'completed', 'video': str(master), 'phone': str(phone),
            'auto_published': False, 'physical_iphone_tested': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--stage', choices=['quote', 'avatars', 'assemble'], default='quote')
    parser.add_argument('--max-credits', type=higgsfield_avatar.number, default=0)
    parser.add_argument('--monthly-credits', type=higgsfield_avatar.number, default=0)
    parser.add_argument('--journal', type=Path, default=Path('video-output/journal'))
    args = parser.parse_args(argv)
    root = args.package.resolve().parent
    try:
        package = json.loads(args.package.read_text())
        if package.get('schema') != 'higgsfield-episode-v1':
            raise PipelineError('Higgsfield bölüm paketi geçersiz.')
        if args.stage == 'assemble':
            result = assemble(root, package, root/'final')
        else:
            journal = LocalJournal(args.journal)
            # Quote both clips before a paid submission. Model/schema/price errors
            # for the closing clip must not leave a newly purchased intro behind.
            items = {}
            for role in ('intro', 'outro'):
                items[role] = higgsfield_avatar.run(root/package['jobs'][role], root/'avatars'/role,
                                                   journal, quote_only=True)
            if args.stage == 'avatars':
                for role in ('intro', 'outro'):
                    job, _ = higgsfield_avatar.load_job(root/package['jobs'][role])
                    if items[role]['status'] == 'quote_only':
                        import hashlib
                        name = 'higgsfield-'+hashlib.sha256(json.dumps(job, sort_keys=True).encode()).hexdigest()[:24]
                        higgsfield_avatar.reserve(journal, name, items[role]['credits'],
                                                  args.max_credits, args.monthly_credits)
                for role in ('intro', 'outro'):
                    items[role] = higgsfield_avatar.run(root/package['jobs'][role], root/'avatars'/role,
                                                       journal, quote_only=False,
                                                       max_credits=args.max_credits, monthly_credits=args.monthly_credits)
            result = {'status': 'quote_only' if args.stage == 'quote' else 'needs_visual_and_lipsync_review',
                      'items': items, 'finished_reel_created': False, 'auto_published': False}
    except (PipelineError, OSError, ValueError, KeyError) as e:
        result = {'status': 'blocked', 'finished_reel_created': False, 'auto_published': False,
                  'message': str(e) if isinstance(e, PipelineError) else 'Bölüm dosyaları okunamadı.'}
    if root.is_dir():
        (root/'automation-status.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result, ensure_ascii=False))
    return 2 if result['status'] == 'blocked' else 0


if __name__ == '__main__':
    raise SystemExit(main())
