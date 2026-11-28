# tools/gen_terrain.py —— 地形 / 资源格贴图
import math, random
from PIL import Image, ImageDraw
import numpy as np
from tools.texlib import *

GRASS = (96, 158, 72)
DIRT = (150, 112, 74)
WATERC = (58, 120, 188)


def tiled_base(base, seed, amp=7, grid=4):
    """无缝的低频明暗噪声底色（32×32 → 超采样尺寸）。"""
    rng = np.random.RandomState(seed)
    g = rng.rand(grid, grid)
    big = np.tile(g, (3, 3))
    im = Image.fromarray((big * 255).astype("uint8")).resize((grid * 3 * 16, grid * 3 * 16), Image.BICUBIC)
    c = grid * 16
    im = im.crop((c, c, c * 2, c * 2)).resize((T * S, T * S), Image.BICUBIC)
    n = (np.asarray(im).astype("float32") / 255.0 - 0.5) * 2 * amp
    arr = np.zeros((T * S, T * S, 4), dtype="float32")
    for i in range(3):
        arr[..., i] = base[i] + n
    arr[..., 3] = 255
    return Image.fromarray(np.clip(arr, 0, 255).astype("uint8"), "RGBA")


def grass(v):
    rng = random.Random(100 + v)
    img = tiled_base(GRASS, 10 + v, amp=8)
    p = Pen(img)
    for _ in range(26):
        x, y = rng.uniform(2, 30), rng.uniform(3, 30)
        h = rng.uniform(2.2, 4.2); lean = rng.uniform(-1.4, 1.4)
        c = rng.choice([shade(GRASS, 1.25), shade(GRASS, 0.78), shade(GRASS, 1.1), (120, 178, 84)])
        p.line([(x, y), (x + lean, y - h)], c, 0.8)
    if v in (1, 3):                       # 点缀小花
        for _ in range(2 + v // 2):
            x, y = rng.uniform(5, 27), rng.uniform(5, 27)
            col = rng.choice([(250, 235, 120), (245, 245, 245), (240, 150, 190)])
            p.circ(x, y, 0.9, fill=col); p.circ(x, y, 0.35, fill=(230, 170, 60))
    return finish(img)


def dirt(v):
    rng = random.Random(200 + v)
    img = tiled_base(DIRT, 30 + v, amp=9)
    p = Pen(img)
    speckle(p, T, T, rng, 70, [shade(DIRT, 0.82), shade(DIRT, 1.18), shade(DIRT, 0.7)], 0.3, 0.8)
    for _ in range(4 + v * 2):
        x, y = rng.uniform(3, 29), rng.uniform(3, 29); r = rng.uniform(0.9, 1.7)
        p.ell(x - r, y - r * 0.7, x + r, y + r * 0.7, fill=shade(DIRT, 0.7))
        p.ell(x - r * 0.8, y - r * 0.8, x + r * 0.6, y + r * 0.3, fill=shade(DIRT, 1.25))
    return finish(img)


def water(frame):
    rng = random.Random(300)
    img = tiled_base(WATERC, 50, amp=7)
    p = Pen(img)
    off = frame * 5
    for i in range(5):
        y = 4 + i * 6.5
        x = (i * 9 + off) % 32
        for dx in (-32, 0, 32):
            p.arc((x + dx - 8, y - 2.5, x + dx + 8, y + 2.5), 200, 340, (170, 215, 245), 0.9)
    for _ in range(8):
        x, y = rng.uniform(0, 32), rng.uniform(0, 32)
        p.circ((x + off) % 32, y, 0.5, fill=(210, 235, 255, 200))
    return finish(img)


def under(kind_base):
    return tiled_base(kind_base, 70, amp=7)


def boulder(img, p, cx, cy, rx, ry, base, rng, hi=1.35, lo=0.65):
    shadow(img, (cx - rx * 1.05, cy + ry * 0.35, cx + rx * 1.15, cy + ry * 1.2), 1.2, 100)
    pts = []
    n = 11
    for i in range(n):
        a = i / n * math.tau
        k = rng.uniform(0.86, 1.05)
        pts.append((cx + math.cos(a) * rx * k, cy + math.sin(a) * ry * k))
    p.poly(pts, fill=base, outline=shade(base, 0.45))
    # 受光面
    top = [(cx + (px - cx) * 0.78 - 0.8, cy + (py - cy) * 0.74 - 1.3) for px, py in pts[-3:] + pts[:4]]
    p.poly(top + [(cx, cy)], fill=shade(base, hi))
    low = [(cx + (px - cx) * 0.9 + 0.6, cy + (py - cy) * 0.9 + 0.8) for px, py in pts[3:8]]
    p.poly(low + [(cx, cy + ry * 0.3)], fill=shade(base, lo))
    for _ in range(3):
        x1, y1 = cx + rng.uniform(-rx, rx) * 0.6, cy + rng.uniform(-ry, ry) * 0.6
        p.line([(x1, y1), (x1 + rng.uniform(-3, 3), y1 + rng.uniform(1, 3.5))], shade(base, 0.5), 0.6)


def rock():
    rng = random.Random(401)
    img = under(DIRT); p = Pen(img)
    boulder(img, p, 11, 20, 8, 6.5, (128, 130, 138), rng)
    boulder(img, p, 21, 14, 8.5, 7, (140, 142, 150), rng)
    boulder(img, p, 16, 23, 6, 5, (118, 120, 128), rng)
    return finish(img)


def iron_rock():
    rng = random.Random(402)
    img = under(DIRT); p = Pen(img)
    boulder(img, p, 12, 18, 9, 7.5, (112, 98, 108), rng)
    boulder(img, p, 21, 14, 8, 6.5, (124, 108, 118), rng)
    for cx, cy, r in ((9, 17, 1.7), (14, 21, 1.4), (20, 12, 1.8), (24, 17, 1.3), (17, 15, 1.2)):
        p.poly([(cx, cy - r * 1.3), (cx + r, cy), (cx, cy + r * 1.2), (cx - r, cy)], fill=(206, 112, 78), outline=(120, 55, 40))
        p.poly([(cx, cy - r * 1.3), (cx + r * 0.4, cy - 0.2), (cx - 0.3, cy)], fill=(244, 170, 120))
    return finish(img)


def meteor():
    rng = random.Random(403)
    img = under(DIRT); p = Pen(img)
    glow(img, 16, 17, 14, (255, 120, 40), 70)
    p.ell(2, 7, 30, 29, fill=(95, 72, 60, 120))                         # 撞击坑
    boulder(img, p, 16, 17, 11.5, 9.5, (88, 80, 92), rng, hi=1.3, lo=0.7)
    for pts in ([(9, 14), (13, 17), (12, 21)], [(20, 10), (19, 15), (23, 18)], [(14, 12), (17, 13)], [(15, 20), (20, 22)]):
        p.line(pts, (255, 150, 60), 1.4); p.line(pts, (255, 220, 140), 0.5)
    for _ in range(6):
        x, y = rng.uniform(7, 25), rng.uniform(9, 25)
        p.circ(x, y, 0.8, fill=(190, 195, 205))
    return finish(img)


def tree(v, bg=True):
    rng = random.Random(500 + v)
    img = under(GRASS) if bg else canvas(T, T); p = Pen(img)
    shadow(img, (5, 21, 29, 30), 1.6, 110)
    p.rect(14.2, 19, 17.8, 27, fill=(98, 66, 38), outline=(60, 38, 20), width=0.6)
    greens = [(46, 112, 52), (58, 132, 62), (72, 150, 74), (92, 170, 88)]
    blobs = [(10, 15, 8), (22, 15, 8), (16, 9, 9), (16, 17, 9)] if v == 0 else \
            [(9, 16, 7.5), (23, 14, 8.5), (15, 8, 8), (17, 18, 8.5)] if v == 1 else \
            [(11, 13, 8), (21, 17, 8), (17, 8.5, 8.5), (14, 19, 7.5)]
    for k, col in enumerate(greens[:2]):
        for cx, cy, r in blobs:
            p.circ(cx, cy + 1.5 - k, r - k * 0.6, fill=col)
    for cx, cy, r in blobs:
        p.circ(cx - 1.2, cy - 1.8, r * 0.62, fill=greens[2])
    for cx, cy, r in blobs[:3]:
        p.circ(cx - 2.2, cy - 3, r * 0.3, fill=greens[3])
    for _ in range(14):
        x, y = rng.uniform(5, 27), rng.uniform(4, 22)
        p.circ(x, y, 0.7, fill=rng.choice([greens[0], greens[3]]))
    return finish(img)


def berry(bg=True):
    rng = random.Random(600)
    img = under(GRASS) if bg else canvas(T, T); p = Pen(img)
    shadow(img, (5, 19, 27, 29), 1.4, 100)
    for cx, cy, r in ((11, 19, 7), (21, 19, 7), (16, 14, 8.5)):
        p.circ(cx, cy, r, fill=(40, 104, 48), outline=(28, 74, 34), width=0.5)
    for cx, cy, r in ((11, 18, 5), (21, 18, 5), (16, 12.5, 6.5)):
        p.circ(cx - 0.6, cy - 0.8, r, fill=(62, 134, 62))
    for _ in range(9):
        x, y = rng.uniform(7, 25), rng.uniform(8, 25)
        p.circ(x, y, 1.9, fill=(206, 40, 56), outline=(120, 20, 34), width=0.4)
        p.circ(x - 0.5, y - 0.6, 0.55, fill=(255, 190, 190))
    return finish(img)


def build():
    out = {}
    for v in range(4): out[f"grass_{v}"] = grass(v)
    for v in range(2): out[f"dirt_{v}"] = dirt(v)
    for f in range(2): out[f"water_{f}"] = water(f)
    out["rock"] = rock(); out["iron_rock"] = iron_rock(); out["meteor"] = meteor()
    for v in range(3): out[f"tree_{v}"] = tree(v)
    out["berry"] = berry()
    return out
