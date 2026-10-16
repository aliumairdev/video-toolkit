#!/usr/bin/env python3
"""
Step 2 - build the video from narration.wav + timeline.json (made by clone_voice.py).

  python build_video.py --preview     quick PNG of every slide -> previews/  (check this first)
  python build_video.py               full 1080p video -> video.mp4, captions.srt, thumbnail.jpg
  python build_video.py --draft       faster 720p render for checking timing
  python build_video.py --no-music    narration only

Needs: pip install pillow numpy   |   ffmpeg (brew install ffmpeg)   |   optional: pip install pygments
"""
import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import project

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------- your brand (edit me) ----------------
BRAND = "Ali Umair"
URL = "aliumair.dev"
COURSE = "AWS Solutions Architect – Associate"   # small label, top-left of every slide

# ---------------- look ----------------
W, H = 1920, 1080
MARGIN = 140
TAIL = 1.5                       # hold the last slide this long after the voice ends
VIDEO_FPS = 24                   # frames extracted per second for @video clips (screen recordings)
VIDEO_CACHE = ".video_cache"     # extracted clip frames are cached here between runs
MUSIC_VOLUME = 0.15              # background music level (0.10 quieter, 0.25 louder)
BG = (7, 10, 18)
CARD = (16, 22, 36)
CARD_LINE = (42, 54, 78)
TEXT = (240, 244, 250)
SOFT = (176, 188, 210)
MUTED = (112, 124, 148)
ACCENT = (96, 140, 255)          # blue
ACCENT2 = (190, 239, 222)        # mint
WARM = (255, 150, 120)
AMBER = (255, 196, 100)

FONT_FILES = {
    "regular": "Inter-Regular.otf", "medium": "Inter-Medium.otf", "semibold": "Inter-SemiBold.otf",
    "bold": "InterDisplay-Bold.otf", "display": "InterDisplay-Medium.otf", "mono": "JetBrainsMono-Regular.ttf",
}
_fonts = {}
_font_warned = [False]


def F(size, weight="regular"):
    size = int(size)
    key = (size, weight)
    if key not in _fonts:
        try:
            _fonts[key] = ImageFont.truetype(os.path.join(HERE, "fonts", FONT_FILES[weight]), size)
        except OSError:
            if not _font_warned[0]:
                print("Warning: fonts/ folder not found next to build_video.py - using a basic font.")
                _font_warned[0] = True
            _fonts[key] = ImageFont.load_default(size)
    return _fonts[key]


# ---------------- small helpers ----------------
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def prog(t, start, dur):
    return clamp((t - start) / dur) if dur > 0 else float(t >= start)


def ease(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def rgba(c, a):
    return (int(c[0]), int(c[1]), int(c[2]), int(255 * clamp(a)))


def appear(t, start, dur=0.5, dist=24):
    p = ease(prog(t, start, dur))
    return p, (1 - p) * dist


def text(d, xy, s, font, color, a=1.0, anchor="la"):
    if a > 0.01 and s:
        d.text(xy, s, font=font, fill=rgba(color, a), anchor=anchor)


def wrap(s, font, maxw):
    lines, cur = [], ""
    for word in s.split():
        trial = (cur + " " + word).strip()
        if not cur or font.getlength(trial) <= maxw:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def fit(s, weight, size, maxw, max_lines, min_size):
    while size > min_size:
        lines = wrap(s, F(size, weight), maxw)
        if len(lines) <= max_lines:
            return F(size, weight), lines, size
        size -= 4
    return F(min_size, weight), wrap(s, F(min_size, weight), maxw), min_size


def initials(name):
    return "".join(w[0] for w in name.split()[:2]).lower() or "•"


# ---------------- background + chrome ----------------
def make_background():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.clip(np.sqrt(((xx - W * 0.5) / W) ** 2 + ((yy - H * 0.42) / H) ** 2) / 0.8, 0, 1)[..., None]
    base = np.array([14, 19, 34], np.float32) * (1 - r) + np.array(BG, np.float32) * r
    base[24::48, 24::48] += 8
    glow = Image.new("RGB", (W // 4, H // 4))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W // 4 * 0.62, -H // 4 * 0.3, W // 4 * 1.12, H // 4 * 0.45], fill=(22, 44, 120))
    gd.ellipse([-W // 4 * 0.12, H // 4 * 0.72, W // 4 * 0.3, H // 4 * 1.25], fill=(14, 56, 52))
    glow = glow.filter(ImageFilter.GaussianBlur(40)).resize((W, H), Image.BILINEAR)
    out = base + np.asarray(glow, np.float32)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def chrome(d, idx, n):
    text(d, (MARGIN, 84), COURSE.upper(), F(18, "mono"), MUTED)
    text(d, (W - MARGIN, 84), f"{idx + 1:02d} / {n:02d}", F(18, "mono"), MUTED, anchor="ra")
    bf = F(22, "semibold")
    text(d, (MARGIN, H - 64), BRAND, bf, SOFT, anchor="ls")
    text(d, (MARGIN + bf.getlength(BRAND) + 16, H - 64), URL, F(20), MUTED, anchor="ls")


def heading_height(s, size=80):
    font, lines, sz = fit(s, "bold", size, W - 2 * MARGIN, 2, 52)
    return len(lines) * int(sz * 1.1)


def block_top(total_h):
    """y where a block of this height should start so it sits centred between header and footer"""
    return max(160, (H - total_h) / 2 - 10)


def heading(d, s, lt, a, size=80, y=180):
    al, dy = appear(lt, 0.05, 0.6, 30)
    font, lines, sz = fit(s, "bold", size, W - 2 * MARGIN, 2, 52)
    for ln in lines:
        text(d, (MARGIN, y + dy), ln, font, TEXT, al * a)
        y += int(sz * 1.1)
    return y


# ---------------- slide kinds ----------------
def r_title(d, img, s, lt, a):
    f = s["fields"] + ["", "", ""]
    head, sub, label = f[0], f[1], f[2]
    font, lines, sz = fit(head, "bold", 124, W - 2 * MARGIN - 80, 3, 64)
    lh = int(sz * 1.08)
    y = H / 2 - (lh * len(lines) + (90 if sub else 0)) / 2 + 10
    al, dy = appear(lt, 0.1, 0.7, 40)
    d.rectangle([MARGIN, y + 6, MARGIN + 8, y + lh * len(lines) - 24], fill=rgba(ACCENT, al * a))
    for i, ln in enumerate(lines):
        text(d, (MARGIN + 44, y + i * lh + dy), ln, font, TEXT, al * a)
    if label:
        a3, _ = appear(lt, 0.7, 0.6, 0)
        text(d, (MARGIN + 46, y - 64), label.upper(), F(22, "mono"), ACCENT2, a3 * a)
    if sub:
        a2, dy2 = appear(lt, 0.45, 0.6)
        text(d, (MARGIN + 46, y + lh * len(lines) + 28 + dy2), sub, F(46, "display"), SOFT, a2 * a)


def r_bullets(d, img, s, lt, a):
    items = s["fields"][1:]
    head = s["fields"][0] if s["fields"] else ""
    hh = heading_height(head)
    room = H - 150 - 160 - hh - 50
    for size in (52, 48, 44, 40, 36, 32, 28, 26):
        ifont = F(size, "medium")
        lh, gap = int(size * 1.25), int(size * 0.8)
        wrapped = [wrap(it, ifont, W - 2 * MARGIN - 70) for it in items]
        items_h = sum(len(w) * lh + gap for w in wrapped) - gap
        if items_h <= room:
            break
    y0 = heading(d, head, lt, a, y=block_top(hh + 60 + items_h)) + 60
    latest = max([i for i, r in enumerate(s["reveals"]) if lt >= r], default=-1)
    y = y0
    for i, lines in enumerate(wrapped):
        ai, dyi = appear(lt, s["reveals"][i], 0.5, 24)
        if ai > 0:
            hot = i == latest
            cy = y + size * 0.62 + dyi
            d.ellipse([MARGIN + 4, cy - 8, MARGIN + 20, cy + 8], fill=rgba(ACCENT2 if hot else ACCENT, ai * a))
            for k, ln in enumerate(lines):
                text(d, (MARGIN + 60 - (1 - ai) * 20, y + k * lh + dyi), ln, ifont, TEXT if hot else SOFT, ai * a)
        y += len(lines) * lh + gap


def r_big(d, img, s, lt, a):
    f = s["fields"] + ["", ""]
    statement, cap = f[0], f[1]
    font, lines, sz = fit(statement, "bold", 112, W - 2 * MARGIN - 100, 4, 56)
    lh = int(sz * 1.12)
    y = H / 2 - lh * len(lines) / 2 - (30 if cap else 0)
    for i, ln in enumerate(lines):
        al, dy = appear(lt, 0.1 + i * 0.12, 0.6, 30)
        text(d, (W / 2, y + i * lh + dy), ln, font, TEXT, al * a, anchor="ma")
    if cap:
        a2, dy2 = appear(lt, 0.5, 0.6)
        text(d, (W / 2, y + lh * len(lines) + 40 + dy2), cap, F(38, "display"), SOFT, a2 * a, anchor="ma")


def r_grid(d, img, s, lt, a):
    tiles = s["fields"][1:]
    head = s["fields"][0] if s["fields"] else ""
    hh = heading_height(head, 72)
    n = max(len(tiles), 1)
    cols = 4 if n > 6 else 3 if n > 4 else n
    rows = math.ceil(n / cols)
    gap = 28
    tw = (W - 2 * MARGIN - gap * (cols - 1)) / cols
    th = min(210, (H - 150 - 160 - hh - 60 - gap * (rows - 1)) / rows)
    y0 = heading(d, head, lt, a, size=72, y=block_top(hh + 60 + rows * th + (rows - 1) * gap)) + 60
    for i, label in enumerate(tiles):
        r_, c_ = divmod(i, cols)
        ai, dyi = appear(lt, s["reveals"][i], 0.5, 20)
        if ai <= 0:
            continue
        x, y = MARGIN + c_ * (tw + gap), y0 + r_ * (th + gap) + dyi
        d.rounded_rectangle([x, y, x + tw, y + th], radius=18, fill=rgba(CARD, 0.95 * ai * a),
                            outline=rgba(CARD_LINE, ai * a), width=2)
        d.rectangle([x + 26, y + 24, x + 66, y + 28], fill=rgba(ACCENT, ai * a))
        tf, tl, ts = fit(label, "bold", 44, tw - 52, 2, 24)
        ty = y + th / 2 - len(tl) * ts * 0.55 + 14
        for k, ln in enumerate(tl):
            text(d, (x + 26, ty + k * ts * 1.1), ln, tf, TEXT, ai * a)


def _side(spec):
    title, _, rest = spec.partition(":")
    return title.strip(), [x.strip() for x in rest.split(";") if x.strip()]


def r_compare(d, img, s, lt, a):
    f = s["fields"] + ["", "", ""]
    hh = heading_height(f[0], 72)
    cw = (W - 2 * MARGIN - 40) / 2
    max_ch = H - 150 - 160 - hh - 60
    sides = [_side(spec) if spec else ("", []) for spec in (f[1], f[2])]
    for size in (40, 36, 32, 28, 24):
        ifont = F(size, "medium")
        wraps = [[wrap(it, ifont, cw - 110) for it in items] for _, items in sides]
        need = [130 + sum(len(w) * size * 1.3 + size * 0.7 for w in ws) + 20 for ws in wraps]
        if max(need) <= max_ch:
            break
    ch = min(max_ch, max(320, max(need)))
    y0 = heading(d, f[0], lt, a, size=72, y=block_top(hh + 60 + ch)) + 60
    for k, ((title, items), wrapped, col) in enumerate(zip(sides, wraps, (WARM, ACCENT2))):
        if not title and not items:
            continue
        ai, dyi = appear(lt, s["reveals"][k], 0.6, 30)
        if ai <= 0:
            continue
        x, y = MARGIN + k * (cw + 40), y0 + dyi
        d.rounded_rectangle([x, y, x + cw, y + ch], radius=22, fill=rgba(CARD, 0.95 * ai * a),
                            outline=rgba(CARD_LINE, ai * a), width=2)
        d.rectangle([x + 36, y + 2, x + 156, y + 5], fill=rgba(col, ai * a))
        text(d, (x + 36, y + 40), title, F(46, "bold"), col, ai * a)
        iy = y + 130
        for lines in wrapped:
            d.ellipse([x + 40, iy + size * 0.45, x + 52, iy + size * 0.45 + 12], fill=rgba(col, ai * a))
            for ln in lines:
                text(d, (x + 76, iy), ln, ifont, TEXT, ai * a)
                iy += size * 1.3
            iy += size * 0.7


def _token_color(tt):
    from pygments.token import Comment, Keyword, Name, Number, Operator, Punctuation, String
    if tt in Comment:
        return MUTED
    if tt in Keyword:
        return (150, 175, 255)
    if tt in String:
        return ACCENT2
    if tt in Number:
        return WARM
    if tt in Name.Function or tt in Name.Class:
        return AMBER
    if tt in Name.Builtin or tt in Name.Constant:
        return (120, 205, 255)
    if tt in Operator or tt in Punctuation:
        return SOFT
    return TEXT


def load_code(path):
    full = path if os.path.isabs(path) else os.path.join(HERE, path)
    try:
        src = open(full, encoding="utf-8").read().expandtabs(4).rstrip("\n").splitlines()
    except OSError:
        print(f"Warning: could not open code file {path}")
        return [[(WARM, f"# could not open {path}")]]
    try:
        from pygments.lexers import TextLexer, get_lexer_for_filename
        try:
            lexer = get_lexer_for_filename(full)
        except Exception:
            lexer = TextLexer()
        lines = [[]]
        for tt, val in lexer.get_tokens("\n".join(src)):
            col = _token_color(tt)
            for j, piece in enumerate(val.split("\n")):
                if j:
                    lines.append([])
                if piece:
                    lines[-1].append((col, piece))
        return (lines + [[]] * len(src))[:len(src)]
    except ImportError:
        return [[(TEXT, ln)] for ln in src]


def code_window(s):
    return min(max(1.0, s["dur"] * 0.6), 0.15 * len(s["_code"]) + 0.5)


def r_code(d, img, s, lt, a):
    y0 = heading(d, s["fields"][0] if s["fields"] else "", lt, a, size=64) + 36
    code = s["_code"]
    x0, x1, y1 = MARGIN, W - MARGIN, H - 130
    ac, _ = appear(lt, 0.2, 0.5, 0)
    d.rounded_rectangle([x0, y0, x1, y1], radius=18, fill=rgba((10, 14, 24), 0.97 * ac * a),
                        outline=rgba(CARD_LINE, ac * a), width=2)
    for i, c in enumerate(((255, 95, 87), (254, 188, 46), (40, 200, 64))):
        d.ellipse([x0 + 24 + i * 24, y0 + 20, x0 + 36 + i * 24, y0 + 32], fill=rgba(c, ac * a))
    if len(s["fields"]) > 1:
        text(d, ((x0 + x1) / 2, y0 + 16), os.path.basename(s["fields"][1]), F(18, "mono"), MUTED, ac * a, anchor="ma")
    avail = y1 - y0 - 80
    size = int(clamp(avail / (max(len(code), 1) * 1.35), 18, 32))
    lh = size * 1.35
    shown = code[: int(avail // lh)]
    mono = F(size, "mono")
    win = code_window(s)
    gutter = mono.getlength("000") + 30
    for i, toks in enumerate(shown):
        al = ease(prog(lt, 0.4 + i * win / max(len(shown), 1), 0.15))
        if al <= 0:
            break
        y = y0 + 60 + i * lh
        text(d, (x0 + 30, y), f"{i + 1:>3}", mono, (70, 82, 104), al * a)
        x = x0 + 30 + gutter
        for col, piece in toks:
            if x > x1 - 30:
                break
            text(d, (x, y), piece, mono, col, al * a)
            x += mono.getlength(piece)


def rounded(im, radius=18):
    """Add rounded-corner alpha to an RGB image, returning RGBA."""
    im = im.convert("RGB")
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, im.width - 1, im.height - 1], radius=radius, fill=255)
    im = im.convert("RGBA")
    im.putalpha(mask)
    return im


def load_image(path, maxw, maxh):
    full = path if os.path.isabs(path) else os.path.join(HERE, path)
    try:
        im = Image.open(full).convert("RGB")
    except OSError:
        print(f"Warning: could not open image {path}")
        im = Image.new("RGB", (800, 450), CARD)
    scale = min(maxw / im.width, maxh / im.height)
    im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.LANCZOS)
    return rounded(im)


class VideoClip:
    """A screen recording played over a slide. Frames are extracted once with ffmpeg
    (cached on disk), then served by local slide time. If the slide outlasts the clip,
    it freezes on the last frame; clip audio is ignored (your narration is the audio)."""

    def __init__(self, path, maxw, maxh):
        self.ok = False
        self.frames = []            # list of frame file paths, one per 1/VIDEO_FPS second
        self.box = (maxw, maxh)
        self._cache = (None, None)  # (index, RGBA image) — reused across duplicate render frames
        full = path if os.path.isabs(path) else os.path.join(HERE, path)
        if not path or not os.path.exists(full):
            print(f"Warning: could not open video {path}")
            return
        if not shutil.which("ffmpeg"):
            print("Warning: ffmpeg not found; @video clip will show a placeholder.")
            return
        sig = f"{os.path.abspath(full)}|{os.path.getmtime(full):.0f}|{os.path.getsize(full)}|{maxw}x{maxh}|{VIDEO_FPS}"
        key = hashlib.sha1(sig.encode("utf-8")).hexdigest()[:16]
        cdir = os.path.join(HERE, VIDEO_CACHE, key)
        done = os.path.join(cdir, "done")
        if not os.path.exists(done):
            os.makedirs(cdir, exist_ok=True)
            print(f"Extracting frames from {path} ...")
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", full,
                   "-vf", f"fps={VIDEO_FPS},scale={maxw}:{maxh}:force_original_aspect_ratio=decrease",
                   os.path.join(cdir, "f_%05d.jpg")]
            if subprocess.run(cmd).returncode != 0:
                print(f"Warning: ffmpeg could not read {path}; showing a placeholder.")
                return
            open(done, "w").close()
        self.frames = sorted(os.path.join(cdir, f) for f in os.listdir(cdir) if f.endswith(".jpg"))
        self.ok = len(self.frames) > 0

    def frame_at(self, lt):
        if not self.ok:
            ph = Image.new("RGB", (min(self.box), int(min(self.box) * 9 / 16)), CARD)
            return rounded(ph)
        idx = min(len(self.frames) - 1, max(0, int(round(lt * VIDEO_FPS))))
        if idx == self._cache[0]:
            return self._cache[1]
        im = rounded(Image.open(self.frames[idx]))
        self._cache = (idx, im)
        return im


def load_video(path, maxw, maxh):
    return VideoClip(path, maxw, maxh)


def r_image(d, img, s, lt, a):
    f = s["fields"] + ["", ""]
    sprite = s["_img"]
    ai, dyi = appear(lt, 0.15, 0.7, 30)
    x = (W - sprite.width) // 2
    y = int(150 + (H - 300 - sprite.height - (60 if f[1] else 0)) / 2 + dyi)
    alpha = ai * a
    if alpha > 0.01:
        sp = sprite
        if alpha < 0.999:
            sp = sprite.copy()
            sp.putalpha(sprite.getchannel("A").point(lambda v: int(v * alpha)))
        img.paste(sp, (x, y), sp)
    if f[1]:
        a2, _ = appear(lt, 0.5, 0.6, 0)
        text(d, (W / 2, y + sprite.height + 30), f[1], F(34, "display"), SOFT, a2 * a, anchor="ma")


def r_video(d, img, s, lt, a):
    f = s["fields"] + ["", ""]
    sprite = s["_video"].frame_at(lt)
    ai, dyi = appear(lt, 0.15, 0.7, 30)
    x = (W - sprite.width) // 2
    y = int(150 + (H - 300 - sprite.height - (60 if f[1] else 0)) / 2 + dyi)
    alpha = ai * a
    if alpha > 0.01:
        sp = sprite
        if alpha < 0.999:
            sp = sprite.copy()
            sp.putalpha(sprite.getchannel("A").point(lambda v: int(v * alpha)))
        img.paste(sp, (x, y), sp)
    if f[1]:
        a2, _ = appear(lt, 0.5, 0.6, 0)
        text(d, (W / 2, y + sprite.height + 30), f[1], F(34, "display"), SOFT, a2 * a, anchor="ma")


def r_end(d, img, s, lt, a):
    f = s["fields"] or ["Thanks for watching"]
    font, lines, sz = fit(f[0], "bold", 120, W - 2 * MARGIN, 2, 64)
    y = 300
    for i, ln in enumerate(lines):
        al, dy = appear(lt, 0.1 + i * 0.1, 0.7, 30)
        text(d, (W / 2, y + dy), ln, font, TEXT, al * a, anchor="ma")
        y += int(sz * 1.1)
    y += 20
    for i, ln in enumerate(f[1:]):
        al, dy = appear(lt, 0.45 + i * 0.12, 0.6)
        text(d, (W / 2, y + dy), ln, F(42, "display"), SOFT, al * a, anchor="ma")
        y += 62
    al, dy = appear(lt, 0.8, 0.7)
    uf = F(56, "display")
    tile = 80
    total = tile + 24 + uf.getlength(URL)
    x = W / 2 - total / 2
    ty = y + 70 + dy
    d.rounded_rectangle([x, ty, x + tile, ty + tile], radius=20, fill=rgba(ACCENT, al * a))
    text(d, (x + tile / 2, ty + tile / 2), initials(BRAND), F(40, "bold"), TEXT, al * a, anchor="mm")
    text(d, (x + tile + 24, ty + tile / 2), URL, uf, TEXT, al * a, anchor="lm")


RENDER = {"title": r_title, "bullets": r_bullets, "big": r_big, "grid": r_grid,
          "compare": r_compare, "code": r_code, "image": r_image, "video": r_video, "end": r_end}


# ---------------- timeline ----------------
def reveal_times(n, sents, dur):
    if n <= 0:
        return []
    if len(sents) >= n:
        times = [sents[int(i * len(sents) / n)][0] for i in range(n)]
    else:
        span = max(0.6, dur * 0.7)
        times = [0.35 + i * span / n for i in range(n)]
    return [max(t, 0.35 + 0.1 * i) for i, t in enumerate(times)]


def load_timeline(path):
    with open(path, encoding="utf-8") as fh:
        tl = json.load(fh)
    slides = tl["slides"]
    total = tl["duration"] + TAIL
    for i, s in enumerate(slides):
        kind, _, rest = s["directive"].partition(" ")
        kind = kind.lower()
        fields = [x.strip() for x in rest.split("|")] if rest.strip() else []
        if kind not in RENDER:
            first = s["sentences"][0]["text"] if s["sentences"] else ""
            kind, fields = "big", [s["directive"] or first]
        s["kind"], s["fields"] = kind, fields
        s["t0"] = 0.0 if i == 0 else s["start"]
        s["t1"] = slides[i + 1]["start"] if i + 1 < len(slides) else total
        s["dur"] = s["t1"] - s["t0"]
        s["sents"] = [(x["start"] - s["t0"], x["end"] - s["t0"]) for x in s["sentences"]]
        if kind == "bullets":
            s["reveals"] = reveal_times(len(fields) - 1, s["sents"], s["dur"])
        elif kind == "compare":
            s["reveals"] = reveal_times(2, s["sents"], s["dur"])
        elif kind == "grid":
            s["reveals"] = [0.5 + j * 0.15 for j in range(len(fields) - 1)]
        else:
            s["reveals"] = []
        if kind == "code":
            s["_code"] = load_code(fields[1] if len(fields) > 1 else "")
        if kind == "image":
            s["_img"] = load_image(fields[0] if fields else "", W - 2 * MARGIN, H - 380)
        if kind == "video":
            s["_video"] = load_video(fields[0] if fields else "", W - 2 * MARGIN, H - 380)
        busy = [(0.0, 1.0), (s["dur"] - 0.4, s["dur"] + 1)] + [(r, r + 0.65) for r in s["reveals"]]
        if kind == "code":
            busy.append((0.0, code_window(s) + 0.6))
        if kind == "video":
            busy = [(0.0, s["dur"] + 1)]   # a moving clip: never reuse a cached still frame
        s["busy"] = sorted(busy)
    return slides, total


# ---------------- frames ----------------
class Renderer:
    def __init__(self, slides, total):
        self.slides, self.total = slides, total
        self.bg = make_background()
        self.cache_key, self.cache_bytes = None, None

    def slide_at(self, t):
        for i, s in enumerate(self.slides):
            if t < s["t1"]:
                return i, s
        return len(self.slides) - 1, self.slides[-1]

    def draw(self, i, s, lt, fade=True):
        img = self.bg.copy()
        d = ImageDraw.Draw(img, "RGBA")
        chrome(d, i, len(self.slides))
        last = i == len(self.slides) - 1
        a = 1.0
        if fade:
            a = ease(prog(lt, 0, 0.35))
            if not last:
                a = min(a, ease(prog(s["dur"] - lt, 0, 0.3)))
        RENDER[s["kind"]](d, img, s, lt, a)
        return img

    def frame_bytes(self, t):
        i, s = self.slide_at(t)
        lt = t - s["t0"]
        busy = any(b0 <= lt < b1 for b0, b1 in s["busy"])
        g = min(clamp(t / 0.4), clamp((self.total - t) / 0.6))
        if not busy and g >= 1:
            epoch = max([b1 for b0, b1 in s["busy"] if b1 <= lt], default=-1)
            key = (i, epoch)
            if key == self.cache_key:
                return self.cache_bytes
        img = self.draw(i, s, lt)
        if g < 1:
            img = Image.fromarray((np.asarray(img, np.float32) * g).astype(np.uint8))
        data = img.tobytes()
        if not busy and g >= 1:
            self.cache_key, self.cache_bytes = key, data
        return data


# ---------------- music ----------------
def make_music(path, seconds, sr=24000):
    rng = np.random.default_rng(3)
    n = int(seconds * sr) + sr
    out = np.zeros(n, np.float32)
    chords = [[45, 52, 59, 60, 64], [41, 48, 57, 60, 64], [48, 55, 59, 64, 67], [43, 50, 57, 59, 62]]
    seg, xf = 8.0, 2.0
    t0, k = 0.0, 0
    while t0 < seconds:
        L = int((seg + xf) * sr)
        tt = np.arange(L, dtype=np.float32) / sr
        s = np.zeros(L, np.float32)
        for m in chords[k % len(chords)]:
            f0 = 440.0 * 2 ** ((m - 69) / 12)
            for det in (-0.15, 0.15):
                for h, amp in ((1, 1.0), (2, 0.3), (3, 0.1)):
                    s += amp * np.sin(2 * np.pi * (f0 * h + det) * tt + rng.uniform(0, 6.28)).astype(np.float32)
        ramp = int(xf * sr)
        env = np.ones(L, np.float32)
        env[:ramp] = np.sin(np.linspace(0, np.pi / 2, ramp)) ** 2
        env[-ramp:] = np.cos(np.linspace(0, np.pi / 2, ramp)) ** 2
        a0 = int(t0 * sr)
        a1 = min(n, a0 + L)
        out[a0:a1] += (s * env)[: a1 - a0]
        t0 += seg
        k += 1
    idx = np.arange(n, dtype=np.float32) / sr
    out *= 0.85 + 0.15 * np.sin(2 * np.pi * 0.07 * idx)
    fade = int(2 * sr)
    out[:fade] *= np.linspace(0, 1, fade)
    end = int(seconds * sr)
    out[max(0, end - fade):end] *= np.linspace(1, 0, end - max(0, end - fade))
    out[end:] = 0
    out *= 0.3 / (np.max(np.abs(out)) + 1e-9)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((out * 32767).astype("<i2").tobytes())


# ---------------- outputs ----------------
def write_srt(slides, path):
    cues = [(x["start"], x["end"], x["text"]) for s in slides for x in s["sentences"]]

    def ts(v):
        ms = int(round(v * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        sec, ms = divmod(ms, 1000)
        return f"{h:02}:{m:02}:{sec:02},{ms:03}"

    with open(path, "w", encoding="utf-8") as fh:
        for i, (a, b, t) in enumerate(cues, 1):
            nxt = cues[i][0] - 0.02 if i < len(cues) else b + 1.0
            fh.write(f"{i}\n{ts(a)} --> {ts(min(b + 0.25, nxt))}\n{t}\n\n")


def still(r, i):
    s = r.slides[i]
    return r.draw(i, s, max(0.1, min(s["dur"] - 0.45, 30.0)), fade=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preview", action="store_true", help="save a PNG of every slide to previews/ and stop")
    ap.add_argument("--draft", action="store_true", help="faster 720p render")
    ap.add_argument("--no-music", action="store_true")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--out", default="video.mp4")
    ap.add_argument("--script", default="script.txt", help="script, used to name the output folder")
    args = ap.parse_args()

    # everything for this script lives in output/<project name>/
    outdir = project.output_dir(os.path.join(HERE, args.script))
    tl_path = os.path.join(outdir, "timeline.json")
    narration = os.path.join(outdir, "narration.wav")
    out_path = args.out if os.path.isabs(args.out) else os.path.join(outdir, args.out)
    rel = os.path.relpath(outdir, HERE)
    if not os.path.exists(tl_path):
        sys.exit(f"timeline.json not found in {rel}/. Run the narration step first.")
    slides, total = load_timeline(tl_path)
    r = Renderer(slides, total)

    if args.preview:
        prev = os.path.join(outdir, "previews")
        os.makedirs(prev, exist_ok=True)
        thumbs = []
        for i in range(len(slides)):
            im = still(r, i).resize((960, 540), Image.LANCZOS)
            im.save(os.path.join(prev, f"slide_{i + 1:02d}.png"))
            thumbs.append(im)
        rows = math.ceil(len(thumbs) / 2)
        sheet = Image.new("RGB", (1920, 540 * rows), BG)
        for i, im in enumerate(thumbs):
            sheet.paste(im, ((i % 2) * 960, (i // 2) * 540))
        sheet.save(os.path.join(prev, "overview.jpg"), quality=88)
        print(f"Saved {len(thumbs)} slide previews to {rel}/previews/ (overview.jpg shows them all).")
        return

    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found. Install it with: brew install ffmpeg")
    if not os.path.exists(narration):
        sys.exit(f"narration.wav not found in {rel}/. Run the narration step first.")

    still(r, 0).convert("RGB").resize((1280, 720), Image.LANCZOS).save(os.path.join(outdir, "thumbnail.jpg"), quality=92)
    write_srt(slides, os.path.join(outdir, "captions.srt"))

    loud = "loudnorm=I=-14:TP=-1.5:LRA=11"
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(args.fps), "-i", "-",
           "-i", narration]
    if args.no_music:
        graph = f"[1:a]aresample=48000,{loud}[a]"
    else:
        music = os.path.join(outdir, ".music.wav")
        make_music(music, total)
        cmd += ["-i", music]
        graph = ("[1:a]aresample=48000,aformat=channel_layouts=mono,asplit=2[v1][v2];"
                 f"[2:a]aresample=48000,aformat=channel_layouts=mono,volume={MUSIC_VOLUME}[mu];"
                 "[mu][v2]sidechaincompress=threshold=0.02:ratio=10:attack=20:release=500[duck];"
                 f"[v1][duck]amix=inputs=2:duration=longest:normalize=0,{loud}[a]")
    cmd += ["-filter_complex", graph, "-map", "0:v", "-map", "[a]"]
    if args.draft:
        cmd += ["-vf", "scale=1280:720:flags=lanczos", "-preset", "veryfast", "-crf", "24"]
    else:
        cmd += ["-preset", "medium", "-crf", "19"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-ac", "2",   # stereo: mono tracks are silent in some players (QuickTime, VS Code preview)
            "-t", f"{total:.3f}", "-movflags", "+faststart", out_path]

    n = int(math.ceil(total * args.fps))
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    step = max(1, n // 20)
    try:
        for k in range(n):
            proc.stdin.write(r.frame_bytes(k / args.fps))
            if k % step == 0:
                print(f"\rRendering {100 * k // n:3d}%", end="", flush=True)
        proc.stdin.close()
    except BrokenPipeError:
        pass
    code = proc.wait()
    print("\rRendering 100%")
    if code != 0:
        sys.exit("ffmpeg failed - see the error above.")
    print(f"Done: {os.path.join(rel, os.path.basename(out_path))} ({total:.1f} s), "
          f"plus captions.srt + thumbnail.jpg in {rel}/")


if __name__ == "__main__":
    main()
