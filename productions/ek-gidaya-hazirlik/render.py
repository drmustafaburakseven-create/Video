"""Reproduce the Turkish short with local artwork and MoneyPrinterTurbo's renderer.

Run from the repository root: .venv/bin/python productions/ek-gidaya-hazirlik/render.py
Existing narration is reused. No credentials, paid APIs or social publishing.
"""
from __future__ import annotations

import argparse
import asyncio
import html
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
BUILD = HERE / "build"
sys.path.insert(0, str(ROOT))
W, H, FPS = 1080, 1920, 30
CREAM, NAVY, PINK, YELLOW = "#FAF7F0", "#19324A", "#E9B7B7", "#F3D789"
SCENES = [
    {"tag": "EK GIDAYA HAZIRLIK", "title": "Ek gıdaya\nhazır mı?", "image": "seated", "speech": "Ek gıdaya hazır mı? Yaklaşık altıncı ayda üç işarete birlikte bakıyoruz."},
    {"tag": "1 / 3 · BAŞ KONTROLÜ", "title": "Dik oturuş.\nSabit baş.", "image": "seated", "speech": "Bir: Dik otururken başını sabit tutabiliyor mu?"},
    {"tag": "2 / 3 · EL–GÖZ–AĞIZ UYUMU", "title": "Bakıyor. Uzanıyor.\nAğzına götürüyor.", "image": "coordination", "speech": "İki: Gördüğü besine uzanıp ağzına götürebiliyor mu?"},
    {"tag": "3 / 3 · YUTABİLME", "title": "Dışarı itmek\nyerine yutma.", "image": "spoon", "speech": "Üç: Besini diliyle sürekli dışarı itmek yerine yutabiliyor mu?"},
    {"tag": "TEK BAŞINA YETERLİ DEĞİL", "title": "Elini emmesi\nhazır demek değil.", "image": "coordination", "speech": "Sadece elini emmesi ya da gece sık uyanması, hazır olduğu anlamına gelmez."},
    {"tag": "İLK DENEME", "title": "Sakin bir an.\nKüçük bir tadım.", "image": "spoon", "speech": "İlk denemede sakin bir zaman seçin. Dik otursun, yanında olun. Az miktarla başlayın; ağzını kapatırsa zorlamayın."},
    {"tag": "BESLENMEYE DEVAM", "title": "Anne sütü veya\nformül mama devam.", "image": "seated", "speech": "Anne sütü ya da formül mama devam."},
    {"tag": "ÜÇ İŞARETİ BİRLİKTE DÜŞÜNÜN", "title": "Baş. El–göz–ağız.\nYutma.", "image": "seated", "speech": "Bu üç işareti birlikte değerlendirmek için kaydedin."},
]


def probe(path):
    return json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]))


def normalized(text):
    return re.sub(r"[^\w]", "", text.casefold())


async def synthesize():
    import edge_tts
    import edge_tts.communicate
    ca = os.environ.get("SSL_CERT_FILE")
    if ca:
        # Add the host CA, retaining certificate and hostname verification.
        edge_tts.communicate._SSL_CTX.load_verify_locations(ca)
    script = " ".join(s["speech"] for s in SCENES)
    stream = edge_tts.Communicate(script, "tr-TR-AhmetNeural", rate="+2%", boundary="WordBoundary")
    words = []
    with (ASSETS / "narration.mp3").open("wb") as f:
        async for chunk in stream.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append({"text": html.unescape(chunk["text"]), "start": chunk["offset"] / 1e7, "end": (chunk["offset"] + chunk["duration"]) / 1e7})
    (ASSETS / "words.json").write_text(json.dumps(words, ensure_ascii=False, indent=2), encoding="utf-8")


def timecode(t):
    ms = round(t * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def prepare():
    ASSETS.mkdir(exist_ok=True)
    BUILD.mkdir(exist_ok=True)
    (HERE / "narration.txt").write_text("\n\n".join(s["speech"] for s in SCENES) + "\n", encoding="utf-8")
    if not (ASSETS / "words.json").exists() or not (ASSETS / "narration.mp3").exists():
        asyncio.run(synthesize())
    words = json.loads((ASSETS / "words.json").read_text())
    written = " ".join(s["speech"] for s in SCENES).split()
    assert [normalized(w) for w in written] == [normalized(w["text"]) for w in words], "Speech word alignment differs from the script"
    duration = float(probe(ASSETS / "narration.mp3")["format"]["duration"])
    cursor, cues = 0, []
    for s in SCENES:
        count = len(s["speech"].split())
        s["start"] = 0 if cursor == 0 else words[cursor]["start"]
        s["end"] = words[cursor + count]["start"] if cursor + count < len(words) else duration + .7
        # Four-word maximum, ending sooner on punctuation; measured word timing.
        i = cursor
        while i < cursor + count:
            j = i + 1
            while j < min(i + 4, cursor + count) and not re.search(r"[.!?;]$", written[j-1]):
                j += 1
            start = words[i]["start"]
            end = min(words[j-1]["end"] + .12, words[j]["start"] if j < len(words) else duration)
            cues.append((start, end, " ".join(written[i:j])))
            i = j
        cursor += count
    (HERE / "captions.srt").write_text("\n\n".join(f"{i+1}\n{timecode(a)} --> {timecode(b)}\n{t}" for i,(a,b,t) in enumerate(cues))+"\n", encoding="utf-8")
    (HERE / "timeline.json").write_text(json.dumps({"duration": duration + .7, "fps": FPS, "width": W, "height": H, "voice": "tr-TR-AhmetNeural", "scenes": SCENES}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"NARRATION_READY duration={duration:.2f}s words={len(words)} cues={len(cues)}", flush=True)
    return duration + .7


def render_visuals(duration):
    from PIL import Image, ImageDraw, ImageFont
    fontfile = ROOT / "resource/fonts/BeVietnamPro-Bold.ttf"
    medium = ROOT / "resource/fonts/BeVietnamPro-Medium.ttf"
    font = lambda size, bold=True: ImageFont.truetype(str(fontfile if bold else medium), size)
    images = {s["image"]: Image.open(ASSETS / (s["image"]+".png")).convert("RGB") for s in SCENES}
    cards=[]
    for index,s in enumerate(SCENES):
        card=Image.new("RGB", (W,H), CREAM)
        d=ImageDraw.Draw(card)
        d.text((78,145), "ÇOCUKLU HAYATA 1 DAKİKA", font=font(27), fill=NAVY)
        d.rounded_rectangle((78,222,998,277), radius=12, fill=YELLOW if index in (0,7) else PINK)
        d.text((98,232), s["tag"], font=font(25), fill=NAVY)
        size=76
        while max(d.textlength(line,font=font(size)) for line in s["title"].splitlines())>900:
            size-=1
        d.multiline_text((78,321), s["title"], font=font(size), fill=NAVY, spacing=6)
        d.text((78,1407), "Yapay zekâ ile oluşturulmuş temsili görüntü", font=font(23,False), fill="#626A71")
        d.line((78,1686,998,1686), fill="#D8D9D4", width=2)
        d.text((78,1715), "Uzm. Dr. Mustafa Burak Seven", font=font(29), fill=NAVY)
        d.text((78,1762), "Çocuk Sağlığı ve Hastalıkları Uzmanı", font=font(24,False), fill="#626A71")
        d.text((78,1800), "bodrumcocuk.com", font=font(24,False), fill="#626A71")
        cards.append(card)
    # A slow continuous camera move on the photographs; labels remain fixed.
    out=BUILD / "visuals.mp4"
    proc=subprocess.Popen(["ffmpeg","-hide_banner","-loglevel","error","-y","-f","rawvideo","-pix_fmt","rgb24","-s",f"{W}x{H}","-r",str(FPS),"-i","-","-an","-c:v","libx264","-preset","veryfast","-crf","19","-pix_fmt","yuv420p","-movflags","+faststart",str(out)], stdin=subprocess.PIPE)
    photo_w,photo_h=920,850
    mask=Image.new("L",(photo_w,photo_h),0)
    ImageDraw.Draw(mask).rounded_rectangle((0,0,photo_w,photo_h),radius=28,fill=255)
    for frame in range(math.ceil(duration*FPS)):
        t=frame/FPS
        idx=next((i for i,s in enumerate(SCENES) if s["start"]<=t<s["end"]),len(SCENES)-1)
        s=SCENES[idx]
        p=max(0,min(1,(t-s["start"])/(s["end"]-s["start"])))
        im=cards[idx].copy()
        src=images[s["image"]]
        zoom=1.0+.035*(p if idx%2==0 else 1-p)
        crop_w=src.width/zoom
        crop_h=crop_w*photo_h/photo_w
        left=(src.width-crop_w)/2
        top=(src.height-crop_h)/2
        photo=src.transform((photo_w,photo_h),Image.Transform.EXTENT,(left,top,left+crop_w,top+crop_h),resample=Image.Resampling.BILINEAR)
        im.paste(photo,(78,530),mask)
        d=ImageDraw.Draw(im)
        for j in range(8):
            x=78+j*116
            d.rounded_rectangle((x,116,x+104,122),radius=3,fill="#DDDED6")
            if j<idx or (j==idx and p>0):
                d.rounded_rectangle((x,116,x+(104 if j<idx else max(2,104*p)),122),radius=3,fill=NAVY)
        if frame in [round(s["start"]*FPS)+15 for s in SCENES]:
            im.save(BUILD / f"scene-{idx+1}.jpg")
        proc.stdin.write(im.tobytes())
    proc.stdin.close()
    if proc.wait():
        raise RuntimeError("Background encode failed")
    print("VISUALS_READY",flush=True)


def finish():
    from app.models.schema import VideoParams
    from app.services.video import generate_video
    params=VideoParams(video_subject="Ek gıdaya hazırlık", video_aspect="9:16", voice_volume=1.0, bgm_type="", bgm_volume=0, subtitle_enabled=True, subtitle_position="custom", custom_position=82, font_name="BeVietnamPro-Bold.ttf", font_size=48, text_fore_color=NAVY, text_background_color=False, stroke_width=0, n_threads=4)
    output=HERE / "Ek-Gidaya-Hazirlik.mp4"
    generate_video(str(BUILD / "visuals.mp4"),str(ASSETS / "narration.mp3"),str(HERE / "captions.srt"),str(output),params)
    print(f"VIDEO_READY {output}",flush=True)


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--stage",choices=["all","prepare","render","finish"],default="all")
    stage=parser.parse_args().stage
    duration=prepare()
    if stage in ("all","render"):
        render_visuals(duration)
    if stage in ("all","finish"):
        finish()
