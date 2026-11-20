"""Render the 19.5-second cinematic review cut with the original studio logo."""
import argparse
from dataclasses import dataclass
from functools import lru_cache
import math
from pathlib import Path
import subprocess
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from render import CYAN, FPS, MONO, MUTED, REGULAR, WHITE, DURATION
from render import draw_cursor, ease, font, label, soundtrack, subtitle_layer

W, H = 720, 1280
ROOT = Path(__file__).resolve().parents[1]
CUTS = (3.85, 8.06, 12.14, 16.92)
BG = "#050a15"
EDGE = "#387589"
GAP = "Схематическая демонстрация"


def ramp(t, start, end):
    return ease((t - start) / (end - start))


def lerp(a, b, amount):
    return a + (b - a) * amount


@dataclass
class Plane:
    image: Image.Image
    x: float
    y: float
    z: float
    yaw: float = 0
    pitch: float = 0
    opacity: float = 1


@dataclass
class Camera:
    x: float
    y: float
    z: float
    roll: float = 0

    def project(self, x, y, z):
        depth = max(100, z - self.z)
        dx, dy = x - self.x, y - self.y
        c, s = math.cos(self.roll), math.sin(self.roll)
        return (360 + 890 * (dx * c - dy * s) / depth,
                660 + 890 * (dx * s + dy * c) / depth)


def place(canvas, plane, camera):
    """Project a textured quad and rasterize just its visible bounding rectangle."""
    w, h = plane.image.size
    c, s = math.cos(plane.yaw), math.sin(plane.yaw)
    cp, sp = math.cos(plane.pitch), math.sin(plane.pitch)
    quad = []
    for x, y in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)):
        depth = -x * s
        quad.append(camera.project(plane.x + x * c, plane.y + y * cp - depth * sp,
                                   plane.z + y * sp + depth * cp))
    left = max(0, math.floor(min(p[0] for p in quad)))
    top = max(0, math.floor(min(p[1] for p in quad)))
    right = min(W, math.ceil(max(p[0] for p in quad)))
    bottom = min(H, math.ceil(max(p[1] for p in quad)))
    if left >= right or top >= bottom or plane.opacity <= 0:
        return
    matrix, target = [], []
    for (x, y), (u, v) in zip(quad, ((0, 0), (w, 0), (w, h), (0, h))):
        x, y = x - left, y - top
        matrix.extend(((x, y, 1, 0, 0, 0, -u * x, -u * y),
                       (0, 0, 0, x, y, 1, -v * x, -v * y)))
        target.extend((u, v))
    try:
        coefficients = np.linalg.solve(matrix, target)
    except np.linalg.LinAlgError:
        return
    warp = plane.image.transform((right - left, bottom - top), Image.Transform.PERSPECTIVE,
                                 coefficients, Image.Resampling.BILINEAR)
    alpha = warp.getchannel("A")
    if plane.opacity < 1:
        alpha = alpha.point(lambda value: round(value * plane.opacity))
    canvas.paste(warp, (left, top), alpha)


@lru_cache(maxsize=32)
def atmosphere(index):
    y, x = np.ogrid[0:H, 0:W]
    phase = index / 10
    def gauss(cx, cy, sx, sy):
        return np.exp(-((x - cx) / sx) ** 2 - ((y - cy) / sy) ** 2)[..., None]
    img = np.full((H, W, 3), (4, 7, 14), dtype=np.float32)
    img += gauss(280 + 90 * math.sin(phase), 620, 380, 485) * (4, 22, 40)
    img += gauss(710, 430, 270, 560) * (17, 12, 32)
    img += gauss(130, 925, 340, 110) * (5, 17, 29)
    return Image.fromarray(img.astype("uint8"))


def environment(canvas, camera, t):
    draw = ImageDraw.Draw(canvas)
    for z in range(200, 2201, 160):
        a, b = (camera.project(x, 340, z) for x in (-1300, 1300))
        draw.line((a, b), fill="#12243a")
    for x in range(-1440, 1441, 90):
        draw.line((camera.project(x, 340, 180), camera.project(x, 340, 2400)), fill="#13273b")
    for side in (-1, 1):
        for offset in range(3):
            track = side * (280 + offset * 56)
            z = 500 + 1400 * ((t * .48 + .22 * offset) % 1)
            a = camera.project(track, 338, z)
            b = camera.project(track, 338, z + 180)
            draw.line((a, b), fill=("#4c9abe", "#2f597c", "#244364")[offset], width=2)


@lru_cache(maxsize=24)
def glass(w, h, shine=0, active=False):
    y, x = np.ogrid[:h, :w]
    reflection = np.exp(-((x / w + .33 * y / h - shine / 8) / .17) ** 2)[..., None]
    top = np.exp(-y / (h * .29))[..., None]
    color = np.array([10, 26 if not active else 34, 43], dtype=np.float32)
    rgb = np.uint8(color + reflection * [9, 28, 34] + top * [7, 13, 18])
    panel = Image.fromarray(rgb).convert("RGBA")
    mask = Image.new("L", (w, h))
    ImageDraw.Draw(mask).rounded_rectangle((1, 1, w - 2, h - 2), 22, fill=246)
    panel.putalpha(mask)
    d = ImageDraw.Draw(panel)
    d.rounded_rectangle((1, 1, w - 2, h - 2), 22, outline=CYAN if active else EDGE, width=2)
    d.line((26, 2, w * .54, 2), fill="#beecf7", width=1)
    d.line((26, h - 3, w - 26, h - 3), fill="#192a3c")
    return panel


def scene_panel(w, h, t, active=False):
    return glass(w, h, int(t * 6) % 12, active).copy()


def typography(canvas, t, specs):
    for row, (word, y, size, color) in enumerate(specs):
        f = font(size)
        base = 63
        for n, char in enumerate(word):
            advance = f.getlength(word[:n])
            p = ramp(t, .035 * n + row * .128, .035 * n + row * .128 + .42)
            if p == 0 or char.isspace():
                continue
            x = base + advance + (1 - p) * 14
            ink = Image.new("RGBA", (size * 2, size * 2))
            d = ImageDraw.Draw(ink)
            d.text((10, 11), char, font=f, fill=color, anchor="lt", stroke_width=0)
            if p < .99:
                ink = ink.filter(ImageFilter.GaussianBlur((1 - p) * 2.5))
                ink.putalpha(ink.getchannel("A").point(lambda v: round(v * p)))
            canvas.paste(ink, (round(x - 10), round(y + 36 * (1 - p) - 11)), ink)


def heading(canvas, t, first, second, note=GAP):
    typography(canvas, t, ((first, 284, 60, WHITE), (second, 355, 66, CYAN)))
    if t > .29:
        label(ImageDraw.Draw(canvas), (65, 445), note, 19, MUTED, REGULAR)


@lru_cache(maxsize=1)
def circuit(w=322, h=172):
    panel = glass(w, h, 5).copy()
    d = ImageDraw.Draw(panel)
    for i in range(4):
        x, y = 36 + i * 20, 43 + 22 * i
        d.line(((x, y), (x + 42, y), (x + 61, y + 19), (w - 50, y + 19)), fill="#326176", width=2)
        d.ellipse((x-3, y-3, x+3, y+3), fill="#8de9fc")
    return panel


def link(draw, a, b, p, stroke=CYAN):
    elbow = (lerp(a[0], b[0], .59), a[1])
    elbow2 = (elbow[0], b[1])
    path = (a, elbow, elbow2, b)
    draw.line(path, fill="#22455b", width=2)
    lengths = [math.dist(c, d) for c, d in zip(path, path[1:])]
    cursor = p * sum(lengths)
    for c, d, length in zip(path, path[1:], lengths):
        if length > 0 and cursor <= length:
            x, y = (lerp(v, w, cursor / length) for v, w in zip(c, d))
            draw.ellipse((x-3, y-3, x+3, y+3), fill=stroke)
            break
        cursor -= length


def opening(canvas, t, logo):
    drive = ramp(t, 0, 1.22)
    cam = Camera(lerp(-155, 0, drive), lerp(48, 0, drive), lerp(-470, 90, drive),
                 lerp(-.24, .012, drive))
    environment(canvas, cam, t)
    nodes = []
    for i in range(8):
        p = ramp(t, .04 * i, 1.3 + .07 * i)
        side = (-1)**i
        x = lerp(side * (440 + i * 32), side * (125 + i * 23), p)
        y = lerp(-270 + i * 101, -130 + i * 35, p)
        z = lerp(160 + i * 170, 690 + i * 56, p)
        nodes.append(Plane(circuit(), x, y, z, side * lerp(.91, .21, p), lerp(-.33, .10, p)))
    d = ImageDraw.Draw(canvas)
    for i, (a, b) in enumerate(zip(nodes, nodes[1:])):
        if t > .12 + i * .08:
            link(d, cam.project(a.x, a.y, a.z), cam.project(b.x, b.y, b.z), (t * 1.4 - i * .1) % 1)
    for lo in sorted(nodes, key=lambda node: node.z, reverse=True):
        place(canvas, lo, cam)
    typography(canvas, t - .54, (("РЕКЛАМА", 273, 81, WHITE), ("В CHATGPT", 360, 78, CYAN)))
    if t > 1.05:
        label(ImageDraw.Draw(canvas), (67, 465), "От регистрации до первого объявления", 23, WHITE, REGULAR)
    if logo is not None and t >= 1.28:
        p = ramp(t, 1.28, 1.9)
        x, y = 360 - logo.width // 2, round(728 - logo.height / 2 + 33 * (1 - p))
        d = ImageDraw.Draw(canvas)
        extent = (logo.width * .5 + 16) * p
        for side in (-1, 1):
            start = 360 + side * extent
            d.line(((start, y + 12), (start + side * 24, y + 39),
                    (start + side * 84, y + 39)), fill=CYAN, width=2)
        if p > .05:
            canvas.paste(logo, (x, y), logo)


def button(draw, box, text, selected=False):
    draw.rounded_rectangle(box, 11, fill="#236275" if selected else "#112638", outline=CYAN if selected else EDGE)
    x, y, right, bottom = box
    label(draw, ((x + right) / 2, (y + bottom) / 2), text, 22,
          WHITE, anchor="mm")


def entry(canvas, t):
    cam = Camera(lerp(94, 0, ramp(t, 0, .95)), 3, lerp(-212, 39, ramp(t, 0, 1.15)),
                 lerp(.092, 0, ramp(t, 0, 1.0)))
    environment(canvas, cam, t + 4)
    for i in range(3):
        place(canvas, Plane(circuit(), (-1)**i * (320 + i * 17), 40 + 45*i, 850 + 85*i, (-1)**i * .44), cam)
    page = scene_panel(542, 266, t)
    d = ImageDraw.Draw(page)
    label(d, (26, 26), "OpenAI Ads Manager", 25)
    d.rounded_rectangle((22, 72, 520, 130), 12, fill=BG, outline=EDGE)
    url = "ads.openai.com"
    count = int(lerp(0, len(url), ramp(t, .48, 1.62)))
    label(d, (39, 88), url[:count] + ("|" if count < len(url) else ""), 25, WHITE, MONO)
    press = 2.65
    button(d, (27, 167, 210, 225), "Log in", t > press)
    button(d, (226, 167, 409, 225), "Sign up")
    place(canvas, Plane(page, 0, 58, 898, lerp(-.28, 0, ramp(t, 0, 1.15))), cam)
    p = ramp(t, 1.88, press)
    x, y = lerp(624, 210, p), lerp(882, 788, p)
    draw_cursor(ImageDraw.Draw(canvas), x, y, max(0, 8 + (t - press) * 94) if press <= t < press + .31 else 0)
    heading(canvas, t, "Рекламный", "кабинет OpenAI")


def workflow(canvas, t):
    cam = Camera(lerp(-96, 4, ramp(t, 0, 1.05)), -6, lerp(-172, 60, ramp(t, 0, 1.35)),
                 lerp(-.11, .006, ramp(t, 0, .92)))
    environment(canvas, cam, t + 8)
    titles = (("Кабинет", "Регистрация"), ("Объявление", "Карточка и ссылка"), ("Результаты", "Показы и переходы"))
    points = []
    for i, (title, detail) in enumerate(titles):
        p = ramp(t, i * .21, .73 + i * .21)
        selected = min(2, int((t + .15) / .97)) == i
        x = (i - 1) * 49 + lerp(260 * (-1)**i, 0, p)
        y = -57 + i * 117
        z = lerp(1800 - i * 165, 995 - i * 27, p)
        points.append((x, y, z, p, title, detail, selected))
    d = ImageDraw.Draw(canvas)
    for a, b in zip(points, points[1:]):
        link(d, cam.project(a[0] - 181, a[1] + 51, a[2]),
             cam.project(b[0] - 181, b[1] - 51, b[2]), (t * 1.3) % 1)
    for x, y, z, p, title, detail, selected in points:
        page = scene_panel(418, 100, t, selected)
        d = ImageDraw.Draw(page)
        d.ellipse((22, 25, 50, 53), outline=CYAN, width=2)
        if selected:
            d.ellipse((30, 33, 42, 45), fill=CYAN)
        label(d, (69, 15), title, 28)
        label(d, (70, 61), detail, 18, MUTED, REGULAR)
        place(canvas, Plane(page, x, y, z, lerp(.52, -.02, p)), cam)
    heading(canvas, t, "От входа", "до результата", "Маршрут урока")


def example(canvas, t):
    cam = Camera(lerp(-103, -1, ramp(t, 0, 1.04)), -10, lerp(-195, 51, ramp(t, 0, 1.21)),
                 lerp(-.113, 0, ramp(t, 0, 1.22)))
    environment(canvas, cam, t + 12)
    ans = scene_panel(546, 118, t)
    d = ImageDraw.Draw(ans)
    label(d, (24, 18), "ОТВЕТ CHATGPT", 16, MUTED, MONO)
    label(d, (24, 50), "Начните с задач, где команда", 23, WHITE, REGULAR)
    label(d, (24, 82), "может сама выбрать способ работы.", 23, WHITE, REGULAR)
    place(canvas, Plane(ans, 0, -71, 956, -.055), cam)
    p = ramp(t, .38, 1.38)
    ad = scene_panel(546, 210, t, True)
    d = ImageDraw.Draw(ad)
    d.rounded_rectangle((22, 35, 143, 160), 15, fill="#13394e", outline=EDGE)
    for i in range(3):
        delta = 10 * i
        d.rounded_rectangle((48 + delta, 63 + delta, 93 + delta, 108 + delta),
                            6, outline=("#357698", "#50adca", CYAN)[i], width=2)
    label(d, (166, 27), "РЕКЛАМА · ВИДЕОУРОК", 15, CYAN, MONO)
    label(d, (166, 70), "Как делегировать задачи", 26)
    label(d, (166, 109), "и сократить согласования", 25)
    label(d, (166, 158), "Оксана Грушевая", 20, MUTED, REGULAR)
    place(canvas, Plane(ad, lerp(273, 0, p), lerp(210, 111, p),
                        lerp(1351, 947, p), lerp(.9, 0, p), lerp(-.22, 0, p), p), cam)
    heading(canvas, t, "Как выглядит", "объявление")


def campaign(canvas, t):
    cam = Camera(lerp(116, 0, ramp(t, 0, .81)), 0, lerp(-255, 44, ramp(t, 0, .93)),
                 lerp(.13, 0, ramp(t, 0, .88)))
    environment(canvas, cam, t + 17)
    page = scene_panel(540, 288, t)
    d = ImageDraw.Draw(page)
    label(d, (23, 25), "Create", 25, CYAN)
    label(d, (102, 28), "›   Create campaign", 24)
    d.line((24, 66, 515, 66), fill=EDGE)
    if .18 < t < .66:
        button(d, (24, 76, 257, 124), "Create campaign", True)
    if t >= .66:
        label(d, (24, 88), "Цель кампании", 23)
        for i, value in enumerate(("Views", "Clicks", "Conversions")):
            button(d, (21 + 168*i, 132, 181 + 168*i, 187), value, i == 1 and t >= 1.64)
    if t > 1.64:
        d.line(((26, 235), (31, 241), (41, 227)), fill=CYAN, width=2)
        label(d, (50, 224), "Оптимизация на переходы", 22, CYAN, REGULAR)
    place(canvas, Plane(page, 0, 48, 924, lerp(.38, 0, ramp(t, 0, .9))), cam)
    p = ramp(t, .91, 1.64)
    draw_cursor(ImageDraw.Draw(canvas), lerp(625, 361, p), lerp(864, 727, p),
                min(33, (t - 1.64) * 105 + 7) if 1.64 <= t < 1.94 else 0)
    heading(canvas, t, "Настройка", "кампании")


def scene(index, t, logo):
    canvas = atmosphere(int(t * 2)).copy()
    if index == 0:
        opening(canvas, max(0, t), logo)
    else:
        (entry, workflow, example, campaign)[index - 1](canvas, max(0, t - CUTS[index - 1] + .22))
    return canvas


def transition(left, right, amount, index):
    """A moving lit edge reveals the next camera angle on a diagonal."""
    p = ease(amount)
    reverse = index % 2 == 1
    if reverse:
        left, right = (im.transpose(Image.Transpose.FLIP_LEFT_RIGHT) for im in (left, right))
    wave = math.sin(math.pi * p)
    dx = int(34 * wave)
    a = left.transform((W, H), Image.Transform.AFFINE, (1, 0, dx, 0, 1, -dx // 4))
    b = right.transform((W, H), Image.Transform.AFFINE, (1, 0, -dx, 0, 1, dx // 5))
    mask = Image.new("L", (W, H))
    layer = ImageDraw.Draw(mask)
    edge = lerp(-220, W + 230, p)
    layer.polygon(((0, 0), (edge + 208, 0), (edge - 200, H), (0, H)),
                  fill=255)
    a.paste(b, mask=mask.filter(ImageFilter.GaussianBlur(17)))
    glow = Image.new("RGBA", (W, H))
    d = ImageDraw.Draw(glow)
    d.line(((edge + 208, 0), (edge - 200, H)), fill=(89, 193, 247, 128), width=11)
    glow = glow.filter(ImageFilter.GaussianBlur(8))
    a.paste(glow, mask=glow.getchannel("A"))
    if reverse:
        a = a.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    # The outgoing glass carrier folds and stretches along the camera move.
    traveling_glass = scene_panel(round(215 + 180 * wave), round(59 + 95 * wave), p)
    camera = Camera(0, 0, 0)
    direction = -1 if reverse else 1
    for lag, opacity in ((.12, .12), (.06, .22), (0, .72)):
        at = min(1, max(0, p - lag))
        place(a, Plane(traveling_glass, direction * lerp(-495, 495, at),
                       lerp(135, -130, at), lerp(810, 350, at),
                       direction * lerp(-.5, 1.02, at), -.18, opacity * wave), camera)
    return a


def frame(t, logo):
    index = sum(t >= cut for cut in CUTS)
    for i, cut in enumerate(CUTS):
        if cut - .19 < t < cut + .19:
            image = transition(scene(i, t, logo), scene(i + 1, t, logo), (t - cut + .19) / .38, i)
            break
    else:
        image = scene(index, t, logo)
    subtitle_layer(image, t)
    return image


def read_logo(path):
    if path.suffix.lower() == ".svg":
        import cairosvg
        from io import BytesIO
        image = Image.open(BytesIO(cairosvg.svg2png(url=str(path))))
    else:
        image = Image.open(path)
    image = image.convert("RGBA")
    image.thumbnail((314, 314), Image.Resampling.LANCZOS)
    return image


def export(voice, output, logo):
    with tempfile.TemporaryDirectory() as tmp:
        score = Path(tmp) / "score.wav"
        soundtrack(score)
        args = [
            "ffmpeg", "-v", "warning", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", str(voice), "-i", str(score),
            "-filter_complex", "[1:a]aresample=48000,aformat=channel_layouts=stereo,volume=0.93[v];"
            "[v][2:a]amix=inputs=2:normalize=0,alimiter=limit=0.96:level=0[a]",
            "-map", "0:v", "-map", "[a]", "-vf", "scale=1080:1920:flags=lanczos,setsar=1",
            "-c:v", "libx264", "-threads", "5", "-preset", "fast", "-crf", "16",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-t", str(DURATION), "-movflags", "+faststart", str(output)
        ]
        with subprocess.Popen(args, stdin=subprocess.PIPE) as encoder:
            for n in range(round(DURATION * FPS)):
                encoder.stdin.write(frame(n / FPS, logo).tobytes())
            encoder.stdin.close()
            if encoder.wait():
                raise SystemExit("FFmpeg export failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voice", type=Path)
    parser.add_argument("--logo", type=Path)
    parser.add_argument("--stills", type=Path, help="Render inspection frames without producing an MP4")
    parser.add_argument("output", type=Path, nargs="?")
    args = parser.parse_args()
    if args.logo is not None:
        if not args.logo.is_file() or (ROOT / "assets/branding") not in args.logo.resolve().parents:
            parser.error("Pass the original logo file from assets/branding.")
        logo = read_logo(args.logo)
    else:
        logo = None
    if args.stills:
        args.stills.mkdir(parents=True, exist_ok=True)
        for t in (.48, 1.4, 2.7, 3.86, 6.84, 9.7, 14.21, 18.7, 19.43):
            frame(t, logo).save(args.stills / f"{t:05.2f}.png")
    else:
        if logo is None or args.voice is None or args.output is None:
            parser.error("Video export requires --logo, --voice and an output path.")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        export(args.voice, args.output, logo)


if __name__ == "__main__":
    main()
