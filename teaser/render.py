"""Render the opening prototype using Pillow, NumPy and FFmpeg."""
import argparse
from functools import lru_cache
import json
import math
from pathlib import Path
import subprocess
import tempfile
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS, DURATION = 720, 1280, 30, 19.5
CYAN, WHITE, MUTED = "#6be8ff", "#f5faff", "#a2bacd"
BOLD = "/usr/share/fonts/truetype/open-sans/OpenSans-Bold.ttf"
REGULAR = "/usr/share/fonts/truetype/open-sans/OpenSans-Regular.ttf"
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
CAPTIONS = json.loads(Path(__file__).with_name("captions.json").read_text())
CUTS = (0, 4.08, 8.39, 12.1, 16.99, DURATION)


def ease(v):
    v = min(1, max(0, v))
    return v * v * (3 - 2 * v)


@lru_cache(maxsize=None)
def font(size, weight=BOLD):
    return ImageFont.truetype(weight, size)


def label(draw, xy, value, size, fill=WHITE, weight=BOLD, anchor="lt"):
    draw.text(xy, value, font=font(size, weight), fill=fill, anchor=anchor)


def lines(draw, x, y, values, size, step, fill=WHITE, weight=BOLD):
    for index, value in enumerate(values):
        label(draw, (x, y + step * index), value, size, fill, weight)


def panel(draw, box, radius=24, fill="#111e30"):
    x, y, r, b = map(round, box)
    draw.rounded_rectangle((x + 3, y + 8, r + 3, b + 8), radius, fill="#07111f")
    draw.rounded_rectangle((x, y, r, b), radius, fill=fill, outline="#456479", width=1)
    draw.line((x + radius, y, r - radius, y), fill="#789aac", width=1)


Y, X = np.ogrid[:H, :W]
GRAIN = np.random.default_rng(41).normal(0, .8, (H, W, 1)).astype("float32")


@lru_cache(maxsize=40)
def atmosphere(beat, position):
    x = .52 + .16 * math.sin(.32 * beat + position / 22)
    y = .46 + .08 * math.cos(beat)
    mist = np.exp(-(((X / W - x) / .52) ** 2 + ((Y / H - y) / .34) ** 2) * 1.7)
    violet = np.exp(-(((X / W - .87) / .38) ** 2 + ((Y / H - .72) / .40) ** 2) * 2)
    rgb = np.array([5, 9, 17], dtype="float32") + mist[..., None] * [8, 29, 46]
    rgb += violet[..., None] * [11, 7, 21]
    return Image.fromarray(np.uint8(np.clip(rgb + GRAIN, 0, 255)))


def field(draw, t):
    horizon = 607 - 75 * math.sin(t * .17)
    focus = 360 + 160 * math.sin(t * .26)
    for i in range(-11, 12):
        draw.line((focus, horizon, 360 + 110 * i + 70 * math.sin(t * .48), 1280),
                  fill="#17283a")
    for i in range(11):
        phase = (i + (t * .9) % 1) / 11
        y = horizon + 750 * phase ** 2.2
        draw.line((0, y, W, y), fill="#18283a")
    for y in (256, 959):
        draw.line((64, y, 640, y), fill="#283c50")
        for x in (64, 640):
            draw.line((x, y - 5, x, y + 5), fill="#6c8fa4")


def sculpture(draw, t, center, zoom, mode="stack"):
    """Project glass sheets through a rotating pinhole camera."""
    cx, cy = center
    angle = .36 * math.sin(t * .8) - .39
    tilt = -.20 + .15 * math.cos(t * .75)
    c, s = math.cos(angle), math.sin(angle)
    ct, st = math.cos(tilt), math.sin(tilt)

    def project(x, y, z):
        rx, rz = c * x + s * z, -s * x + c * z
        ry, depth = ct * y - st * rz, st * y + ct * rz
        k = zoom * 680 / (680 + depth)
        return cx + k * rx, cy + k * ry

    for layer in reversed(range(5)):
        z = (layer - 2) * (45 + 25 * math.sin(t * .8))
        if mode == "open":
            z *= .20 + .8 * ease(t / 1.45)
        offset = layer * 12
        x0, x1, y0, y1 = -174 + offset, 174 - offset, -94, 94
        contour = [(x0 + 20, y0), (x1 - 20, y0), (x1, y0 + 20),
                   (x1, y1 - 20), (x1 - 20, y1), (x0 + 20, y1),
                   (x0, y1 - 20), (x0, y0 + 20)]
        corners = [project(x, y, z) for x, y in contour]
        draw.polygon(corners, fill=("#163448", "#142941", "#17273b", "#172238", "#152436")[layer])
        draw.line(corners + corners[:1], fill=("#88edff", "#477c94", "#407c91", "#53748d", "#566a92")[layer], width=2)
        draw.line([corners[0], corners[1], corners[2]], fill="#b3e5ee", width=2)
        for n in range(1, 8):
            rib = y0 + n * (y1 - y0) / 8
            draw.line([project(x0 + 23, rib, z), project(x1 - 23, rib, z)], fill="#234859")
        spot = x0 + 37 + (x1 - x0 - 74) * (.5 + .48 * math.sin(t * 1.6 + layer))
        draw.line([project(spot, y0 + 5, z), project(spot, y1 - 5, z)], fill="#3689ab", width=2)
        for px in (x0 + 28, x1 - 29):
            q, r = project(px, y0 + 23, z)
            draw.ellipse((q - 3, r - 3, q + 3, r + 3), fill=CYAN)


def draw_cursor(draw, x, y, radius):
    if radius > 0:
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=CYAN, width=2)
    draw.polygon([(x, y), (x + 5, y + 32), (x + 13, y + 23),
                  (x + 24, y + 27), (x + 26, y + 22)], fill=WHITE, outline="#07121c")


def opening(draw, t):
    v = ease((t - .04) / .7)
    draw.line((360 - 280 * v, 681, 360 + 280 * v, 681), fill=CYAN, width=2)
    if t > .23:
        sculpture(draw, t, (360, 746 - 24 * v), .44 + .97 * ease(t / 2.15), "open")
    reveal = ease((t - .65) / .66)
    if reveal > 0:
        y = 303 + 25 * (1 - reveal)
        label(draw, (66, y), "РЕКЛАМА", 83)
        label(draw, (67, y + 88), "В CHATGPT", 79, CYAN)
        label(draw, (69, y + 189), "От регистрации до первого объявления", 25, MUTED, REGULAR)


def entry(draw, t):
    label(draw, (67, 316), "Рекламный", 67)
    label(draw, (67, 386), "кабинет OpenAI", 58, CYAN)
    sculpture(draw, t + 2.7, (371, 695), 1.5 + .17 * ease(t / 3.5))
    a = ease((t - .3) / .8)
    y = 624 + 75 * (1 - a)
    panel(draw, (82, y, 624, y + 132), 27)
    draw.rounded_rectangle((107, y + 46, 142, y + 77), 6, outline=CYAN, width=2)
    draw.arc((114, y + 33, 135, y + 59), 180, 360, fill=CYAN, width=2)
    label(draw, (167, y + 42), "ads.openai.com", 39)
    p = ease((t - 1.65) / 1.52)
    elapsed = t - 3.17
    draw_cursor(draw, 613 - 115 * p, 890 - (890 - y - 82) * p,
                (7 + elapsed * 73) if 0 <= elapsed <= .25 else 0)


def roadmap(draw, t):
    label(draw, (66, 315), "От входа", 66)
    label(draw, (66, 390), "до результата", 64, CYAN)
    for i, name in enumerate(("Кабинет", "Объявление", "Результаты")):
        progress = ease((t - i * .8) / .55)
        x = 100 + i * 44 + 42 * (1 - progress)
        y = 545 + i * 116
        active = min(2, int((t + .14) / 1.04))
        if i < 2:
            draw.line((x + 39, y + 84, x + 39, y + 101, x + 75, y + 101,
                       x + 75, y + 121), fill="#38778d", width=2)
        panel(draw, (x, y, x + 424, y + 84), 21, "#18384c" if i == active else "#111e30")
        draw.ellipse((x + 29, y + 31, x + 49, y + 51), fill=CYAN if i <= active else "#365367")
        label(draw, (x + 73, y + 24), name, 30)


def example(draw, t):
    label(draw, (65, 301), "Как выглядит", 63)
    label(draw, (65, 371), "объявление", 67, CYAN)
    label(draw, (69, 467), "Схематичная демонстрация", 22, MUTED, REGULAR)
    y = 518 + 35 * (1 - ease(t / .65))
    panel(draw, (75, y, 625, y + 140), 24)
    label(draw, (98, y + 24), "ОТВЕТ CHATGPT", 14, MUTED, MONO)
    lines(draw, 98, y + 54, ("Начните с задач, где команда", "может сама выбрать способ работы."), 23, 33, WHITE, REGULAR)
    a = ease((t - .25) / .94)
    x = 75 + 29 * (1 - a)
    y = 690 + 75 * (1 - a)
    draw.line((91, 677, 604, 677), fill="#45738a")
    panel(draw, (x, y, x + 550, y + 211), 25, "#142a3b")
    draw.rounded_rectangle((x + 22, y + 29, x + 145, y + 153), 17, fill="#163e52")
    for k in range(3):
        p = 11 * (1 - ease((t - .42 - k * .14) / .69))
        draw.rounded_rectangle((x + 48 + k * 9, y + 61 + k * 9 + p,
                                x + 100 + k * 9, y + 101 + k * 9 + p), 7,
                               outline=("#47758e", "#61a5b7", CYAN)[k], width=2)
    label(draw, (x + 169, y + 28), "РЕКЛАМА · ВИДЕОУРОК", 15, CYAN, MONO)
    lines(draw, x + 169, y + 62, ("Как делегировать", "задачи и сократить", "согласования"), 28, 37)
    draw.line((x + 489, y + 173, x + 513, y + 173, x + 513, y + 149), fill=CYAN, width=2)
    draw.line((x + 483, y + 179, x + 513, y + 149), fill=CYAN, width=2)


def campaign(draw, t):
    label(draw, (67, 315), "Настройка", 69)
    label(draw, (67, 394), "кампании", 75, CYAN)
    label(draw, (69, 490), "Схематичная демонстрация", 22, MUTED, REGULAR)
    sculpture(draw, 4 + t, (370, 744), 1.42 + .21 * ease(t / 2))
    y = 675 + 67 * (1 - ease(t / .54))
    panel(draw, (104, y, 600, y + 138), 28)
    label(draw, (139, y + 48), "Цель кампании", 27)
    draw.rounded_rectangle((400, y + 39, 570, y + 97), 15, fill="#184554", outline="#51b4c5")
    label(draw, (485, y + 68), "Clicks", 26, CYAN, anchor="mm")


DESIGNS = (opening, entry, roadmap, example, campaign)


def subtitle_layer(canvas, t):
    for start, end, rows, emphasis in CAPTIONS:
        if not start <= t < end:
            continue
        alpha = ease((t - start + .02) / .12)
        offset = 9 * (1 - alpha)
        layer = Image.new("RGBA", (W, 132))
        draw = ImageDraw.Draw(layer)
        f = font(31)
        width = max(f.getlength(line) for line in rows) + 45
        top = 20 if len(rows) == 1 else 2
        draw.rounded_rectangle((352 - width / 2, top, 352 + width / 2, top + 16 + 40 * len(rows)),
                               16, fill=(4, 11, 21, round(237 * alpha)),
                               outline=(50, 83, 100, round(220 * alpha)))
        for i, line in enumerate(rows):
            x = 352 - f.getlength(line) / 2
            for token in line.split():
                rgb = (107, 232, 255) if token == emphasis else (245, 250, 255)
                draw.text((x, top + 8 + 39 * i), token, font=f, fill=(*rgb, round(255 * alpha)))
                x += f.getlength(token + " ")
        canvas.paste(layer, (0, round(1002 + offset)), layer)
        return


def frame(t):
    beat = next(i for i in range(len(DESIGNS)) if t < CUTS[i + 1])
    local = t - CUTS[beat]
    end = CUTS[beat + 1] - t
    base = atmosphere(beat, int(local * 3)).copy()
    draw = ImageDraw.Draw(base)
    field(draw, t)
    DESIGNS[beat](draw, local)
    # A moving reflection marks the matched cuts.
    proximity = min(local if beat else 1, end if beat < 4 else 1)
    if proximity < .17:
        a = 1 - ease(proximity / .17)
        reflection = Image.new("RGB", (W, H), "#70c3db")
        base = Image.blend(base, reflection, .17 * a)
    if beat == 0 and t < .51:
        base = Image.blend(Image.new("RGB", (W, H), "#020408"), base, ease(t / .51))
        d = ImageDraw.Draw(base)
        span = 245 * ease(t / .49)
        if t > 0:
            d.line((360 - span, 681, 360 + span, 681), fill=CYAN, width=2)
    subtitle_layer(base, t)
    if end < .26 and beat == 4:
        base = Image.blend(base, Image.new("RGB", (W, H), "#08111d"), .8 * (1 - ease(end / .26)))
    return base


def soundtrack(path):
    rate = 48000
    t = np.arange(round(rate * DURATION)) / rate
    notes = (55, 82.407, 110, 130.813, 164.814, 195.998, 261.626, 329.628)
    envelope = np.minimum(t / .75, 1) * np.clip((DURATION - t) / .33, 0, 1)
    left, right = np.zeros_like(t), np.zeros_like(t)
    for i, hz in enumerate(notes):
        color = 1 + .34 * np.sin(2 * np.pi * (.09 + .017 * i) * t + i)
        tone = .009 * color * np.sin(2 * np.pi * hz * t + .18 * np.sin(2 * np.pi * .14 * t))
        left += tone * (.9 + .1 * (-1) ** i)
        right += tone * (.9 - .1 * (-1) ** i)
    pulse = np.exp(-(t % .64) * 8) * np.sin(2 * np.pi * 61 * t) * .025
    left += pulse
    right += pulse
    for shift in (*CUTS[1:-1], 7.25, 19.06):
        u = np.maximum(t - shift + .12, 0)
        sweep = (u > 0) * np.exp(-u * 17) * np.sin(2 * np.pi * (180 * u + 3900 * u * u))
        left += .023 * sweep
        right += .018 * sweep
    with wave.open(str(path), "wb") as out:
        out.setparams((2, 2, rate, 0, "NONE", "not compressed"))
        out.writeframes(np.int16(np.stack((left, right), axis=-1) * envelope[:, None] * 32767).tobytes())


def stamp(value):
    ms = round(1000 * value)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("voice", type=Path)
    parser.add_argument("video", type=Path)
    args = parser.parse_args()
    args.video.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        score = Path(temp) / "score.wav"
        soundtrack(score)
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y", "-f", "rawvideo",
            "-pixel_format", "rgb24", "-video_size", f"{W}x{H}", "-framerate", str(FPS),
            "-i", "-", "-i", str(args.voice), "-i", str(score), "-filter_complex",
            "[1:a]aresample=48000,aformat=channel_layouts=stereo,volume=0.93[v];"
            "[v][2:a]amix=inputs=2:normalize=0,alimiter=limit=0.96:level=0[a]",
            "-map", "0:v", "-map", "[a]", "-vf", "scale=1080:1920:flags=lanczos,setsar=1",
            "-c:v", "libx264", "-threads", "5", "-preset", "fast", "-crf", "16",
            "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709",
            "-color_trc", "bt709", "-c:a", "aac", "-b:a", "192k", "-t", str(DURATION),
            "-movflags", "+faststart", str(args.video)
        ]
        with subprocess.Popen(command, stdin=subprocess.PIPE) as encoder:
            for n in range(round(FPS * DURATION)):
                encoder.stdin.write(frame(n / FPS).tobytes())
            encoder.stdin.close()
            if encoder.wait():
                raise SystemExit("FFmpeg export failed")
    srt = args.video.with_suffix(".srt")
    srt.write_text("\n\n".join(
        f"{i}\n{stamp(start)} --> {stamp(end)}\n" + "\n".join(rows)
        for i, (start, end, rows, _) in enumerate(CAPTIONS, 1)
    ) + "\n")


if __name__ == "__main__":
    main()
