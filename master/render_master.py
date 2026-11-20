"""Build six resumable motion-design chapters and combine their original voiceovers."""
import argparse
from bisect import bisect_right
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "teaser"))
import cinematic as cine
import render as teaser

W, H, FPS = 720, 1280, 30
RATE = 48000
CYAN, WHITE, MUTED = teaser.CYAN, teaser.WHITE, teaser.MUTED
LABEL, FONT = teaser.label, teaser.font
SCENES = Path(__file__).with_name("scenes.txt")
CAPTIONS = Path(__file__).with_name("captions.json")


def read_scenes():
    chapters = []
    for line in SCENES.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            chapters.append([])
            continue
        start, style, headline, title, *fields = line.split("|")
        chapters[-1].append((float(start), style, headline.split(" / "), title,
                            fields[0].split("; ") if fields and fields[0] else []))
    return chapters


def fitted(draw, position, text, size, width, color=WHITE, weight=teaser.BOLD):
    while FONT(size, weight).getlength(text) > width:
        size -= 1
    LABEL(draw, position, text, size, color, weight)


def heading(canvas, local, title, number, scheme=True):
    first, *rest = title
    second = rest[0] if rest else ""
    def fit(text, start):
        while FONT(start).getlength(text) > 575:
            start -= 1
        return start
    cine.typography(canvas, local + .14, [(first, 278, fit(first, 62), WHITE),
                                         (second, 350, fit(second, 68), CYAN)])
    d = ImageDraw.Draw(canvas)
    chapters = ("Вступление", "Настройка аккаунта", "Кампания", "Контекст", "Объявление", "Модерация и результаты")
    LABEL(d, (65, 226), chapters[number], 19, MUTED, teaser.REGULAR)
    d.line((65, 259, 634, 259), fill="#335a78")
    if scheme:
        LABEL(d, (65, 430), cine.GAP, 18, MUTED, teaser.REGULAR)


def draw_fields(panel, rows, t, duration, title, hit):
    d = ImageDraw.Draw(panel)
    fitted(d, (25, 25), title, 25, 493)
    interval = min(.54, max(.21, duration / 11))
    selected_y = None
    for i, value in enumerate(rows):
        reveal = cine.ramp(t, .10 + i * interval, .44 + i * interval)
        if reveal < .05:
            continue
        y = 74 + 65 * i + round((1 - reveal) * 13)
        selected = value.startswith("*")
        typed = value.startswith("@")
        triggered = selected and t >= hit
        color = "#51cbdf" if triggered else "#355f73"
        d.rounded_rectangle((22, y, 515, y+48), 10, fill="#173d50" if triggered else "#0b1727", outline=color, width=2)
        value = value.lstrip("*@")
        if typed:
            typed_progress = cine.ramp(t, .28 + i * interval, min(duration - .08, 2.0 + i * interval))
            value = value[:int(len(value) * typed_progress)]
            if typed_progress < .98:
                value += "│"
        fitted(d, (38, y + 12), value, 22, 445, CYAN if triggered else WHITE,
               teaser.REGULAR if typed else teaser.BOLD)
        if selected:
            selected_y = y + 24
    return selected_y


def visual(canvas, item, t, duration, number, logo, scene_index):
    _, style, title, note, rows = item
    if style == "intro":
        return cine.frame(t, logo)
    phase = cine.ramp(t, 0, .84)
    direction = (-1) ** (scene_index + number)
    drift = 13 * math.sin(t * .65)
    camera = cine.Camera(direction * (88 * (1 - phase) + drift), 0,
                         cine.lerp(-246, 36, phase) + 10 * math.sin(t * .75),
                         direction * .085 * (1 - phase))
    cine.environment(canvas, camera, t + scene_index * .51)
    if style == "outro":
        for side in (-1, 1):
            cine.place(canvas, cine.Plane(cine.circuit(), side * (235 + 55 * (1 - phase)), -15,
                                         880, side * .42), camera)
        canvas.paste(logo, (360 - logo.width // 2, 540), logo)
        heading(canvas, t, title, number, False)
        d = ImageDraw.Draw(canvas)
        fitted(d, (65, 879), "Видеоуроки · Интерактивные курсы · AI-решения", 22, 580, WHITE, teaser.REGULAR)
        LABEL(d, (65, 925), "soul-of-the-system.kz", 29, CYAN)
        return canvas

    if style == "assembly":
        compose = cine.ramp(t, 1.05, 2.35)
        shell = cine.scene_panel(535, 326, t, True)
        d = ImageDraw.Draw(shell)
        fitted(d, (25, 23), note, 25, 473)
        cine.place(canvas, cine.Plane(shell, 0, 42, 933, -.08*(1-phase), 0, compose), camera)
        for i, text in enumerate(rows):
            side = -1 if i % 2 == 0 else 1
            x = side * cine.lerp(280, 124, compose)
            y = (-1 if i < 2 else 1) * cine.lerp(145, 63, compose) + 56
            part = cine.scene_panel(230, 97, t, text.startswith("*"))
            d = ImageDraw.Draw(part)
            if i == 2:
                d.rectangle((19, 22, 53, 53), outline=CYAN, width=2)
                d.line(((20, 49), (30, 37), (38, 44), (45, 35), (52, 49)), fill=CYAN, width=2)
            else:
                for line in range(3):
                    d.line((19, 25+10*line, 54-4*line, 25+10*line), fill=CYAN, width=2)
            fitted(d, (66, 31), text.lstrip("*"), 21, 151)
            cine.place(canvas, cine.Plane(part, x, y, cine.lerp(720+100*i, 905, compose),
                                         side*.67*(1-compose), -.15*(1-compose)), camera)
    elif style == "network":
        nodes = []
        for idx, text in enumerate(rows):
            settle = cine.ramp(t, .19 + idx * .32, .85 + idx * .32)
            x = ((idx % 2) * 2 - 1) * (50 + direction * 12)
            y = -95 + idx * 98
            z = cine.lerp(1330 + idx * 57, 925 - idx * 13, settle)
            nodes.append((x, y, z, settle, text.lstrip("*"), text.startswith("*")))
        d = ImageDraw.Draw(canvas)
        for idx, (a, b) in enumerate(zip(nodes, nodes[1:])):
            cine.link(d, camera.project(a[0] - 158, a[1] + 40, a[2]),
                      camera.project(b[0] - 158, b[1] - 40, b[2]), (t * .8 - idx * .18) % 1)
        for idx, (x, y, z, settle, text, marked) in enumerate(nodes):
            active = marked or idx == min(len(nodes) - 1, int(t / max(.6, duration / len(nodes))))
            page = cine.scene_panel(434, 80, t, active)
            d = ImageDraw.Draw(page)
            d.ellipse((23, 29, 42, 48), outline=CYAN, width=2)
            if active:
                d.ellipse((28, 34, 37, 43), fill=CYAN)
            fitted(d, (60, 27), text, 23, 353)
            cine.place(canvas, cine.Plane(page, x, y, z, direction * .40 * (1 - settle)), camera)
        LABEL(ImageDraw.Draw(canvas), (66, 475), note, 21, WHITE, teaser.REGULAR)
    elif style == "chart":
        chart = cine.scene_panel(542, 394, t)
        d = ImageDraw.Draw(chart)
        fitted(d, (25, 24), note, 25, 493, WHITE)
        for i, field in enumerate(rows):
            fitted(d, (25, 73 + i * 50), field, 39 if i == 0 else 21, 493, CYAN if i == 0 else MUTED)
        graph = [36, 61, 49, 81, 104, 89, 130, 148, 117, 163, 142, 179]
        for y in (205, 250, 295, 340):
            d.line((28, y, 514, y), fill="#25425b")
        for i, value in enumerate(graph):
            height = value * cine.ramp(t, i * .075, .7 + i * .075)
            x = 31 + i * 40
            d.polygon(((x, 347-height), (x+7, 341-height), (x+30, 341-height),
                       (x+30, 340), (x+23, 347), (x, 347)), fill="#216381")
            d.rectangle((x, 347-height, x+23, 347), fill="#359db8", outline="#62d9ea")
        LABEL(d, (27, 365), "ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ", 14, MUTED, teaser.MONO)
        cine.place(canvas, cine.Plane(chart, 0, 52, 939, direction * .30 * (1-phase)), camera)
    elif style == "player":
        page = cine.scene_panel(538, 365, t)
        d = ImageDraw.Draw(page)
        LABEL(d, (24, 23), rows[0], 23)
        d.rounded_rectangle((23, 66, 516, 294), 12, fill="#061220", outline="#387589")
        d.ellipse((229, 138, 305, 214), outline=CYAN, width=3)
        d.polygon(((257, 154), (257, 199), (281, 176)), fill=WHITE)
        progress = cine.ramp(t, .95, max(1.1, duration))
        d.line((46, 278, 491, 278), fill="#30536d", width=4)
        d.line((46, 278, 46+445*progress, 278), fill=CYAN, width=4)
        LABEL(d, (25, 318), rows[1], 22, MUTED, teaser.REGULAR)
        cine.place(canvas, cine.Plane(page, 0, 62, 925, direction * .22 * (1-phase)), camera)
    else:
        page = cine.scene_panel(538, 147 + 65 * len(rows), t, style == "ad")
        cue_hits = {(2, 2.84): 1.52, (2, 9.25): 1.79, (1, 16.04): .44}
        hit = cue_hits.get((number, item[0]), min(1.25, duration * .41))
        selected_y = draw_fields(page, rows, t, duration, note, hit)
        if style == "budget":
            d = ImageDraw.Draw(page)
            q = cine.ramp(t, 2.64, 4.84)
            fitted(d, (41, 219), f"{round(q * 1375):,} тенге".replace(",", " "), 40, 440, CYAN)
        if style == "ad":
            d = ImageDraw.Draw(page)
            LABEL(d, (25, page.height - 51), "РЕКЛАМА · УЧЕБНЫЙ ПРИМЕР", 18, CYAN, teaser.MONO)
        camera_y = 62
        cine.place(canvas, cine.Plane(page, 0, camera_y, 918, direction * .40 * (1-phase)), camera)
        if selected_y is not None:
            p = cine.ramp(t, .27, hit)
            target = camera.project(-96, camera_y - page.height / 2 + selected_y, 918)
            x, y = cine.lerp(620, target[0], p), cine.lerp(920, target[1], p)
            ripple = (8 + (t-hit)*112) if hit <= t < hit+.24 else 0
            teaser.draw_cursor(ImageDraw.Draw(canvas), x, y, ripple)
    heading(canvas, t, title, number)
    return canvas


def chapter_frame(chapter, items, times, t, length, logo, captions):
    scene = max(0, bisect_right(times, t)-1)
    start = times[scene]
    stop = times[scene+1] if scene+1 < len(times) else length
    if scene == 0 and chapter == 0:
        canvas = cine.frame(min(t, 19.49), logo)
    else:
        canvas = cine.atmosphere(int(t*2)).copy()
        if scene > 0 and t-start < .31:
            old = cine.atmosphere(int(t*2)).copy()
            previous = times[scene-1]
            old = visual(old, items[scene-1], start-previous, start-previous,
                         chapter, logo, scene-1)
            new = visual(canvas, items[scene], t-start, stop-start,
                         chapter, logo, scene)
            canvas = cine.transition(old, new, (t-start)/.31, scene)
        else:
            canvas = visual(canvas, items[scene], t-start, stop-start,
                            chapter, logo, scene)
        teaser.subtitle_layer(canvas, t)
    return canvas


def run(args, **kwargs):
    return subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
                         check=True, **kwargs)


def synthesize_score(chunks, events, work):
    import wave
    samples = sum(len(chunk) for chunk in chunks)
    t = np.arange(samples, dtype=np.float32) / RATE
    music = np.zeros(samples, dtype=np.float32)
    for i, note in enumerate((55, 82.407, 110, 130.813, 164.814, 195.998, 261.626)):
        music += .006 * np.sin(2*np.pi*note*t + .27*np.sin(t*(.21 + i*.055)))
    music += .012 * np.sin(2*np.pi*60*t) * np.exp(-7*(t % .64))
    music *= np.minimum(t/.8, 1) * np.clip((samples/RATE-t)/1.5, 0, 1)
    delay = np.arange(RATE//6, dtype=np.float32) / RATE
    click = .023*np.sin(2*np.pi*(480*delay+2700*delay**2))*np.exp(-27*delay)
    for position in events:
        end = min(samples, position + len(click))
        music[position:end] += click[:end-position]
    voice = np.concatenate(chunks, axis=0)
    mixed = voice*.94 + music[:, None]
    with wave.open(str(work / "mix.wav"), "wb") as dest:
        dest.setparams((2, 2, RATE, 0, "NONE", "not compressed"))
        dest.writeframes((np.clip(mixed, -.985, .985)*32767).astype("<i2").tobytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, default=ROOT / "work/audio")
    parser.add_argument("--work", type=Path, default=ROOT / "work/v3")
    parser.add_argument("--output", type=Path, default=ROOT / "work/v3-delivery")
    parser.add_argument("--stills", action="store_true")
    args = parser.parse_args()
    audio = sorted(args.audio.glob("0[1-6]_*.mp3"))
    if len(audio) != 6:
        parser.error("Expected six original MP3 files in --audio.")
    logo_path, = (ROOT / "assets/branding").glob("WhatsApp Image*")
    logo = cine.read_logo(logo_path)
    chapters = read_scenes()
    cues = json.loads(CAPTIONS.read_text())
    chunks = []
    for path in audio:
        pcm = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(path), "-ar", str(RATE),
                                       "-ac", "2", "-f", "f32le", "-"])
        chunks.append(np.frombuffer(pcm, dtype="<f4").reshape(-1, 2))
    boundaries = np.cumsum([0, *(len(chunk) for chunk in chunks)]).tolist()
    frames = [math.ceil(samples*FPS/RATE) for samples in boundaries]
    args.work.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    signature = hashlib.sha256(b"".join(p.read_bytes() for p in
        [Path(__file__), SCENES, CAPTIONS, Path(cine.__file__), Path(teaser.__file__), logo_path, *audio])).hexdigest()
    videos, srt, events = [], [], []
    for chapter, items in enumerate(chapters):
        offset = boundaries[chapter] / RATE
        length = len(chunks[chapter]) / RATE
        times = [item[0] for item in items]
        teaser.CAPTIONS = cues[chapter]
        for start, end, rows, _ in cues[chapter]:
            srt.append(f"{len(srt)+1}\n{teaser.stamp(start+offset)} --> {teaser.stamp(end+offset)}\n" + "\n".join(rows))
        events.extend(round((offset+t+.35)*RATE) for t in times[1:])
        if args.stills:
            for scene, t in enumerate(times):
                img = chapter_frame(chapter, items, times, t + .9, length, logo, cues[chapter])
                img.resize((270, 480)).save(args.work / f"still-{chapter+1}-{scene:02}.jpg")
            continue
        video = args.work / f"chapter-{chapter+1}-{signature[:12]}.mp4"
        videos.append(video)
        if video.exists():
            print(f"Resume chapter {chapter+1}", flush=True)
            continue
        temp = video.with_suffix(".partial.mp4")
        print(f"Render chapter {chapter+1}: {length:.3f}s", flush=True)
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
               "-r", str(FPS), "-i", "-", "-vf", "scale=1080:1920:flags=lanczos,setsar=1",
               "-c:v", "libx264", "-threads", "3", "-preset", "veryfast", "-crf", "18",
               "-pix_fmt", "yuv420p", "-video_track_timescale", "30000", str(temp)]
        with subprocess.Popen(cmd, stdin=subprocess.PIPE) as process:
            for index in range(frames[chapter], frames[chapter+1]):
                t = index/FPS - offset
                img = chapter_frame(chapter, items, times, t, length, logo, cues[chapter])
                process.stdin.write(img.tobytes())
            process.stdin.close()
            if process.wait():
                raise RuntimeError(f"Chapter {chapter+1} failed")
        temp.replace(video)
    if args.stills:
        return
    stem = "SOS_ChatGPT_Ads_FULL_REELS_V3"
    (args.output / f"{stem}.srt").write_text("\n\n".join(srt) + "\n")
    (args.work / "concat.txt").write_text("".join(f"file '{video.resolve()}'\n" for video in videos))
    synthesize_score(chunks, events, args.work)
    run(["-f", "concat", "-safe", "0", "-i", str(args.work/"concat.txt"), "-i", str(args.work/"mix.wav"),
         "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", str(args.output / f"{stem}.mp4")])
    print("Source samples:", boundaries, flush=True)


if __name__ == "__main__":
    main()
