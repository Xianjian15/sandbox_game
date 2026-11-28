# tools/gen_buildings.py —— 建筑贴图（原生尺寸 = 占地格数 × 32）
import math, random
from PIL import Image
from tools.texlib import *

WOOD = (168, 124, 76)
STONE = (140, 142, 150)
IRON = (160, 168, 182)
PAL = {"wood": WOOD, "stone": STONE, "iron": IRON}


def planks(p, x1, y1, x2, y2, base, rng, vertical=False, n=4):
    """木板：n 条，带纹理和钉子"""
    for i in range(n):
        if vertical:
            w = (x2 - x1) / n; a, b = x1 + i * w, x1 + (i + 1) * w
            c = shade(base, rng.uniform(0.9, 1.1))
            p.rect(a, y1, b, y2, fill=c)
            p.line([(a, y1), (a, y2)], shade(base, 0.62), 0.8)
            for _ in range(3):
                gx = rng.uniform(a + 0.6, b - 0.6); gy = rng.uniform(y1, y2 - 6)
                p.line([(gx, gy), (gx + rng.uniform(-0.4, 0.4), gy + rng.uniform(3, 7))], shade(base, 0.8), 0.5)
        else:
            h = (y2 - y1) / n; a, b = y1 + i * h, y1 + (i + 1) * h
            c = shade(base, rng.uniform(0.9, 1.1))
            p.rect(x1, a, x2, b, fill=c)
            p.line([(x1, a), (x2, a)], shade(base, 0.62), 0.8)
            p.line([(x1, a + 0.6), (x2, a + 0.6)], shade(base, 1.18), 0.5)
            for _ in range(3):
                gx = rng.uniform(x1, x2 - 8); gy = rng.uniform(a + 0.8, b - 0.8)
                p.line([(gx, gy), (gx + rng.uniform(3, 8), gy + rng.uniform(-0.3, 0.3))], shade(base, 0.8), 0.5)


def bricks(p, x1, y1, x2, y2, base, rng, rows=4, bw=10):
    h = (y2 - y1) / rows
    p.rect(x1, y1, x2, y2, fill=shade(base, 0.6))
    for r in range(rows):
        off = (bw / 2) if r % 2 else 0
        x = x1 - off
        while x < x2:
            a, b = max(x1, x + 0.6), min(x2, x + bw - 0.6)
            if b - a > 1:
                c = shade(base, rng.uniform(0.92, 1.1))
                p.rect(a, y1 + r * h + 0.6, b, y1 + (r + 1) * h - 0.6, fill=c)
                p.line([(a, y1 + r * h + 0.9), (b, y1 + r * h + 0.9)], shade(base, 1.22), 0.6)
            x += bw


def plates(p, x1, y1, x2, y2, base, rng, cols=1, rows=1):
    p.rect(x1, y1, x2, y2, fill=shade(base, 0.7))
    cw, ch = (x2 - x1) / cols, (y2 - y1) / rows
    for r in range(rows):
        for c in range(cols):
            a, b, cc, d = x1 + c * cw + 0.8, y1 + r * ch + 0.8, x1 + (c + 1) * cw - 0.8, y1 + (r + 1) * ch - 0.8
            p.rect(a, b, cc, d, fill=base, r=1)
            p.line([(a + 0.5, b + 0.6), (cc - 0.5, b + 0.6)], shade(base, 1.3), 0.7)
            p.line([(a + 0.5, d - 0.5), (cc - 0.5, d - 0.5)], shade(base, 0.75), 0.7)
            for rx, ry in ((a + 2, b + 2), (cc - 2, b + 2), (a + 2, d - 2), (cc - 2, d - 2)):
                p.circ(rx, ry, 0.9, fill=shade(base, 0.6)); p.circ(rx - 0.25, ry - 0.25, 0.4, fill=shade(base, 1.4))


def bevel(p, x1, y1, x2, y2, base, t=1.2):
    p.line([(x1, y1 + t / 2), (x2, y1 + t / 2)], shade(base, 1.35), t)
    p.line([(x1 + t / 2, y1), (x1 + t / 2, y2)], shade(base, 1.2), t)
    p.line([(x1, y2 - t / 2), (x2, y2 - t / 2)], shade(base, 0.55), t)
    p.line([(x2 - t / 2, y1), (x2 - t / 2, y2)], shade(base, 0.65), t)


# ---------------- 地板 ----------------
def floor(mat):
    rng = random.Random(hash(("floor", mat)) % 9999)
    img, p = new(T, T)
    if mat == "wood":
        planks(p, 0, 0, T, T, WOOD, rng, vertical=False, n=4)
        for y in (4, 12, 20, 28):
            p.circ(rng.choice([4, 28]), y - 2, 0.5, fill=shade(WOOD, 0.55))
    elif mat == "stone":
        p.rect(0, 0, T, T, fill=shade(STONE, 0.62))
        for a, b, c, d in ((0.8, 0.8, 15.4, 15.4), (16.6, 0.8, 31.2, 15.4), (0.8, 16.6, 15.4, 31.2), (16.6, 16.6, 31.2, 31.2)):
            p.rect(a, b, c, d, fill=shade(STONE, rng.uniform(0.95, 1.12)), r=1)
            p.line([(a + 0.5, b + 0.5), (c - 0.5, b + 0.5)], shade(STONE, 1.3), 0.7)
            speckle(p, T, T, rng, 0, [])
        speckle(p, T, T, rng, 30, [shade(STONE, 0.8), shade(STONE, 1.25)], 0.3, 0.7)
    elif mat == "iron":
        plates(p, 0, 0, T, T, IRON, rng, 1, 1)
        for i in range(4):
            p.line([(5 + i * 7, 5), (5 + i * 7, 27)], shade(IRON, 0.85), 0.6)
        p.line([(4, 16), (28, 16)], shade(IRON, 0.8), 0.6)
    elif mat == "wool":
        R = (168, 58, 66)
        p.rect(0, 0, T, T, fill=R)
        for yy in range(0, T, 2):
            for xx in range(0, T, 2):
                if (xx + yy) % 4 == 0: p.rect(xx, yy, xx + 1, yy + 1, fill=shade(R, 1.12))
        p.rect(3, 3, 29, 29, outline=(236, 196, 110), width=1.2)
        p.rect(5.5, 5.5, 26.5, 26.5, outline=shade(R, 0.7), width=0.8)
        for cx, cy in ((16, 16),):
            p.poly([(cx, cy - 6), (cx + 6, cy), (cx, cy + 6), (cx - 6, cy)], fill=(236, 196, 110), outline=shade(R, 0.6))
            p.poly([(cx, cy - 3), (cx + 3, cy), (cx, cy + 3), (cx - 3, cy)], fill=shade(R, 0.8))
    elif mat == "sterile":
        base = (214, 226, 234)
        p.rect(0, 0, T, T, fill=shade(base, 0.8))
        p.rect(0.8, 0.8, 15.4, 15.4, fill=base); p.rect(16.6, 16.6, 31.2, 31.2, fill=base)
        p.rect(16.6, 0.8, 31.2, 15.4, fill=shade(base, 0.96)); p.rect(0.8, 16.6, 15.4, 31.2, fill=shade(base, 0.96))
        p.line([(2, 2.5), (14, 2.5)], (255, 255, 255, 220), 0.8)
    bevel(p, 0, 0, T, T, {"wood": WOOD, "stone": STONE, "iron": IRON, "wool": (168, 58, 66), "sterile": (214, 226, 234)}[mat], 0.7)
    return finish(img)


# ---------------- 墙 / 窗 / 门 ----------------
def wall(mat, sterile=False):
    rng = random.Random(hash(("wall", mat, sterile)) % 9999)
    img, p = new(T, T)
    if sterile:
        base = (226, 234, 240)
        plates(p, 0, 0, T, T, base, rng, 1, 2)
        p.rect(4, 5, 28, 8, fill=(150, 205, 190)); p.rect(4, 21, 28, 24, fill=(150, 205, 190))
    elif mat == "wood":
        planks(p, 0, 0, T, T, shade(WOOD, 0.85), rng, vertical=True, n=4)
        p.rect(0, 0, T, 3.5, fill=shade(WOOD, 1.05)); p.rect(0, T - 3.5, T, T, fill=shade(WOOD, 0.8))
    elif mat == "stone":
        bricks(p, 0, 0, T, T, STONE, rng, rows=4, bw=10.67)
    else:
        plates(p, 0, 0, T, T, IRON, rng, 2, 2)
    # 顶面高光 + 底部阴影，立体感
    p.line([(0, 0.6), (T, 0.6)], (255, 255, 255, 110), 1.1)
    p.line([(0, T - 0.7), (T, T - 0.7)], (0, 0, 0, 120), 1.4)
    p.rect(0, 0, T, T, outline=(0, 0, 0, 90), width=0.9)
    return finish(img)


def window(mat):
    rng = random.Random(hash(("win", mat)) % 9999)
    img, p = new(T, T)
    base = PAL[mat]
    if mat == "wood": planks(p, 0, 0, T, T, shade(WOOD, 0.85), rng, vertical=True, n=4)
    elif mat == "stone": bricks(p, 0, 0, T, T, STONE, rng, rows=4, bw=10.67)
    else: plates(p, 0, 0, T, T, IRON, rng, 1, 1)
    p.rect(5, 5, 27, 27, fill=shade(base, 0.45))
    p.rect(6.5, 6.5, 25.5, 25.5, fill=(150, 205, 230))
    p.rect(6.5, 6.5, 25.5, 16, fill=(185, 225, 245))
    p.poly([(8, 24), (14, 8), (17, 8), (11, 24)], fill=(255, 255, 255, 120))
    p.poly([(16, 24), (21, 12), (22.5, 12), (18, 24)], fill=(255, 255, 255, 80))
    p.line([(16, 6.5), (16, 25.5)], shade(base, 0.6), 1.5)
    p.line([(6.5, 16), (25.5, 16)], shade(base, 0.6), 1.5)
    p.rect(5, 5, 27, 27, outline=shade(base, 0.4), width=1)
    p.line([(0, T - 0.7), (T, T - 0.7)], (0, 0, 0, 110), 1.3)
    return finish(img)


def door(mat):
    rng = random.Random(hash(("door", mat)) % 9999)
    img, p = new(T, T)
    base = {"wood": (162, 112, 62), "stone": (124, 126, 134), "iron": (164, 170, 184)}[mat]
    frame = shade(base, 0.55)
    p.rect(0, 0, T, T, fill=frame)
    if mat == "wood": planks(p, 3, 3, 29, 29, base, rng, vertical=True, n=4)
    elif mat == "stone": bricks(p, 3, 3, 29, 29, STONE, rng, rows=4, bw=8.7)
    else: plates(p, 3, 3, 29, 29, IRON, rng, 1, 2)
    p.rect(8, 7, 24, 14, outline=shade(base, 0.6), width=0.8)
    p.rect(8, 18, 24, 26, outline=shade(base, 0.6), width=0.8)
    p.circ(25, 16, 2.2, fill=(240, 200, 80), outline=(140, 100, 30), width=0.6)
    p.circ(24.4, 15.4, 0.7, fill=(255, 240, 170))
    p.rect(0, 0, T, T, outline=(0, 0, 0, 120), width=0.9)
    return finish(img)


# ---------------- 家具 ----------------
def bed(kind):
    """竖向 32×64，枕头在上"""
    rng = random.Random(5)
    img, p = new(T, 2 * T)
    shadow(img, (1, 4, 31, 63), 1.2, 60)
    frame = (120, 84, 50)
    if kind == "feather":
        frame = (150, 100, 56)
    p.rect(1, 1, 31, 63, fill=frame, r=3)
    p.rect(2, 2, 30, 62, fill=shade(frame, 1.2), r=2.5)
    if kind == "medical":
        sheet, edge, pillow = (200, 232, 238), (150, 196, 208), (240, 248, 250)
    elif kind == "feather":
        sheet, edge, pillow = (246, 232, 206), (222, 190, 120), (255, 252, 242)
    else:
        sheet, edge, pillow = (226, 228, 234), (186, 188, 200), (250, 250, 255)
    p.rect(3.5, 3.5, 28.5, 60.5, fill=sheet, r=2)
    p.rect(4, 22, 28, 60, fill=shade(sheet, 0.96), r=1.5)
    p.line([(4, 22), (28, 22)], edge, 1.2)
    p.rect(5, 6, 27, 18, fill=pillow, outline=shade(pillow, 0.75), width=0.8, r=3)
    p.line([(8, 9), (24, 9)], (255, 255, 255, 200), 0.8)
    for x in range(6, 28, 4):
        p.line([(x, 28), (x + 1.2, 58)], shade(sheet, 0.9), 0.5)
    if kind == "feather":
        p.rect(4, 22, 28, 25, fill=(222, 190, 120))
        for x in range(6, 28, 5):
            p.poly([(x, 30), (x + 1.4, 36), (x, 41), (x - 1.4, 36)], fill=(250, 240, 220), outline=(222, 190, 120))
    if kind == "medical":
        p.rect(14, 31, 18, 51, fill=(70, 190, 130)); p.rect(8, 38, 24, 44, fill=(70, 190, 130))
        p.rect(14.6, 31.6, 17.4, 50.4, fill=(120, 225, 170)); p.rect(8.6, 38.6, 23.4, 43.4, fill=(120, 225, 170))
    p.rect(1, 1, 31, 63, outline=shade(frame, 0.5), width=1, r=3)
    return finish(img)


def research_bench():
    rng = random.Random(7)
    img, p = new(2 * T, 2 * T)
    shadow(img, (2, 5, 62, 63), 1.4, 70)
    p.rect(2, 4, 62, 60, fill=(116, 82, 50), outline=(60, 40, 24), width=1.2, r=5)
    planks(p, 4, 6, 60, 58, (146, 104, 64), rng, vertical=False, n=7)
    p.rect(4, 6, 60, 58, outline=(80, 54, 32), width=1)
    # 纸张 / 图纸
    p.poly([(7, 12), (33, 9), (35, 30), (9, 33)], fill=(236, 226, 196), outline=(150, 130, 90))
    for i in range(5):
        p.line([(11, 16 + i * 3.4), (31, 14 + i * 3.4)], (110, 100, 80), 0.6)
    p.poly([(36, 14), (56, 13), (57, 27), (37, 28)], fill=(150, 200, 235), outline=(60, 100, 150))
    p.line([(40, 24), (44, 18), (48, 22), (53, 16)], (255, 255, 255), 0.9)
    # 显微镜
    p.circ(14, 46, 6.5, fill=(90, 96, 108), outline=(50, 54, 64), width=0.8)
    p.circ(14, 46, 3.4, fill=(160, 215, 235), outline=(60, 90, 110), width=0.6)
    p.circ(13, 45, 1.1, fill=(255, 255, 255))
    p.rect(19, 44, 29, 48, fill=(70, 76, 88), outline=(40, 44, 52), width=0.6)
    # 烧瓶 / 发光球
    glow(img, 44, 46, 9, (110, 235, 235), 120)
    p.circ(44, 47, 6.2, fill=(110, 215, 225), outline=(40, 120, 130), width=0.9)
    p.circ(42, 44.5, 1.8, fill=(235, 255, 255, 230))
    p.rect(42, 36, 46, 41, fill=(190, 225, 235), outline=(60, 120, 130), width=0.7)
    p.rect(52, 40, 58, 56, fill=(230, 80, 90), outline=(120, 30, 40), width=0.7)
    p.rect(52, 40, 58, 45, fill=(250, 150, 155))
    return finish(img)


def stove():
    """横向 96×32：石炉 + 3 个灶眼"""
    rng = random.Random(11)
    img, p = new(3 * T, T)
    p.rect(0, 0, 3 * T, T, fill=(92, 94, 100), outline=(44, 46, 52), width=1.2, r=4)
    bricks(p, 2, 2, 3 * T - 2, T - 2, (112, 114, 122), rng, rows=4, bw=12)
    p.rect(2, 2, 3 * T - 2, T - 2, outline=(60, 62, 68), width=1)
    for i in range(3):
        cx = T * i + 16
        p.circ(cx, 15, 11, fill=(40, 40, 44), outline=(20, 20, 24), width=0.8)
        p.circ(cx, 15, 9, fill=(58, 58, 64))
        for r in (7, 4.5, 2):
            p.circ(cx, 15, r, outline=(82, 82, 90), width=0.8)
        p.circ(cx, 15, 1.2, fill=(30, 30, 34))
        p.circ(cx, 29, 1.7, fill=(190, 190, 200), outline=(80, 80, 90), width=0.5)
    p.line([(2, 2.6), (3 * T - 2, 2.6)], (255, 255, 255, 90), 1)
    return finish(img)


def furnace():
    rng = random.Random(13)
    img, p = new(2 * T, 2 * T)
    shadow(img, (3, 6, 63, 63), 1.4, 70)
    p.rect(1, 1, 63, 63, fill=(64, 64, 70), outline=(30, 30, 34), width=1.2, r=6)
    bricks(p, 3, 3, 61, 61, (96, 94, 102), rng, rows=8, bw=14)
    p.rect(3, 3, 61, 61, outline=(40, 40, 46), width=1.2)
    p.circ(32, 20, 10, fill=(36, 36, 40), outline=(18, 18, 20), width=1)           # 烟囱口
    p.circ(32, 20, 7, fill=(22, 22, 24))
    p.circ(30.5, 18.5, 2.2, fill=(60, 60, 66))
    p.rect(14, 36, 50, 56, fill=(26, 24, 26), outline=(14, 12, 14), width=1, r=5)   # 炉口
    p.rect(17, 40, 47, 53, fill=(44, 26, 20), r=3)
    for x in (20, 28, 36, 43):
        p.rect(x, 52, x + 2.5, 56, fill=(78, 76, 84))
    p.line([(14, 36), (50, 36)], (130, 128, 140), 1.4)
    return finish(img)


def workbench():
    rng = random.Random(17)
    img, p = new(2 * T, T)
    shadow(img, (2, 6, 62, 31), 1.2, 70)
    p.rect(1, 2, 63, 30, fill=(96, 66, 40), outline=(52, 34, 20), width=1.2, r=3)
    planks(p, 3, 4, 61, 28, (172, 128, 82), rng, vertical=False, n=4)
    p.rect(3, 4, 61, 28, outline=(90, 62, 36), width=0.8)
    # 台钳
    p.rect(50, 7, 59, 17, fill=(98, 102, 114), outline=(48, 50, 58), width=0.8, r=1)
    p.rect(52, 9, 57, 15, fill=(60, 64, 74))
    p.line([(54.5, 17), (54.5, 24)], (150, 154, 168), 1.4); p.circ(54.5, 25, 1.7, fill=(190, 194, 206))
    # 锤子
    p.line([(8, 22), (22, 12)], (118, 78, 40), 2.2)
    p.rect(19, 8, 27, 14, fill=(150, 154, 168), outline=(70, 72, 82), width=0.7)
    # 锯
    p.poly([(28, 20), (46, 14), (46, 19), (28, 24)], fill=(196, 200, 212), outline=(90, 92, 104))
    for x in range(30, 46, 2):
        p.poly([(x, 24 - (x - 28) * 0.3), (x + 1, 25.4 - (x - 28) * 0.3), (x + 2, 24 - (x - 28) * 0.3)], fill=(150, 154, 166))
    p.rect(24, 19, 29, 26, fill=(140, 92, 48), outline=(70, 44, 22), width=0.6, r=1)
    return finish(img)


def flower_pot():
    img, p = new(T, T)
    shadow(img, (7, 22, 25, 30), 1.0, 90)
    for cx, cy, col in ((10, 14, (232, 90, 124)), (22, 13, (250, 212, 84)), (16, 8, (190, 120, 232)), (16, 15, (255, 140, 90))):
        p.line([(16, 20), (cx, cy + 2)], (62, 140, 66), 1.2)
        p.circ(cx, cy, 4, fill=col, outline=shade(col, 0.6), width=0.5)
        for a in range(5):
            ang = a / 5 * math.tau
            p.circ(cx + math.cos(ang) * 2.6, cy + math.sin(ang) * 2.6, 1.9, fill=shade(col, 1.12))
        p.circ(cx, cy, 1.3, fill=(250, 232, 120))
    p.poly([(9, 19), (23, 19), (21, 29), (11, 29)], fill=(184, 104, 70), outline=(110, 58, 38))
    p.rect(8, 17.5, 24, 21, fill=(204, 124, 88), outline=(110, 58, 38), width=0.6)
    p.rect(9, 18, 23, 19.4, fill=(150, 100, 60))
    return finish(img)


def statue():
    rng = random.Random(23)
    img, p = new(T, T)
    shadow(img, (4, 21, 28, 31), 1.1, 110)
    p.rect(5, 23, 27, 30, fill=(132, 134, 142), outline=(70, 72, 80), width=0.8, r=1)
    p.rect(7, 20, 25, 25, fill=(150, 152, 160), outline=(80, 82, 90), width=0.6)
    stone = (190, 192, 198)
    p.poly([(11, 21), (13, 11), (19, 11), (21, 21)], fill=stone, outline=(100, 102, 110))
    p.poly([(11, 13), (6, 20), (8, 21), (13, 15)], fill=shade(stone, 0.9), outline=(100, 102, 110))
    p.poly([(21, 13), (26, 7), (28, 8), (22, 16)], fill=shade(stone, 0.9), outline=(100, 102, 110))
    p.circ(16, 7.5, 4.2, fill=stone, outline=(100, 102, 110), width=0.7)
    p.poly([(13, 12), (14, 20), (17, 14)], fill=shade(stone, 0.78))
    p.circ(15, 6.3, 1.2, fill=shade(stone, 1.25))
    return finish(img)


def bookshelf():
    rng = random.Random(29)
    img, p = new(T, T)
    p.rect(0, 0, T, T, fill=(118, 80, 48), outline=(62, 40, 24), width=1.2)
    for row in range(3):
        y1 = 2 + row * 10
        p.rect(2, y1, 30, y1 + 8.6, fill=(70, 46, 28))
        x = 2.8
        while x < 28.5:
            w = rng.uniform(2.1, 3.4); h = rng.uniform(5.4, 8.2)
            c = rng.choice([(196, 68, 70), (70, 118, 196), (222, 186, 70), (86, 168, 100), (150, 90, 190), (230, 130, 60)])
            p.rect(x, y1 + 8.6 - h, x + w, y1 + 8.6, fill=c, outline=shade(c, 0.55), width=0.4)
            p.line([(x + 0.5, y1 + 9 - h + 1.3), (x + w - 0.5, y1 + 9 - h + 1.3)], (255, 255, 255, 120), 0.4)
            x += w + 0.25
        p.rect(1.5, y1 + 8.6, 30.5, y1 + 10, fill=(150, 104, 64))
    return finish(img)


def fountain():
    img, p = new(T, T)
    shadow(img, (2, 5, 30, 31), 1.1, 70)
    p.circ(16, 16, 14.5, fill=(150, 154, 164), outline=(72, 76, 86), width=1)
    p.circ(16, 16, 12.2, fill=(196, 200, 208))
    p.circ(16, 16, 10.5, fill=(80, 150, 215))
    for r, a in ((9, 190), (7, 120)):
        p.circ(16, 16, r, outline=(170, 215, 245, a), width=0.7)
    p.circ(16, 16, 4.2, fill=(176, 180, 190), outline=(84, 88, 98), width=0.7)
    for ang in range(0, 360, 45):
        x = 16 + math.cos(math.radians(ang)) * 6
        y = 16 + math.sin(math.radians(ang)) * 6
        p.circ(x, y, 1.1, fill=(225, 242, 255))
    p.circ(16, 16, 2.4, fill=(235, 248, 255))
    p.circ(15.3, 15.3, 0.9, fill=(255, 255, 255))
    return finish(img)


def small_cabinet():
    rng = random.Random(31)
    img, p = new(T, T)
    p.rect(0, 0, T, T, fill=(110, 76, 46), outline=(58, 38, 22), width=1.2, r=2)
    planks(p, 2, 2, 30, 30, (156, 112, 70), rng, vertical=True, n=2)
    p.rect(3, 3, 29, 29, outline=(96, 66, 40), width=1)
    p.line([(16, 3), (16, 29)], (84, 56, 34), 1.2)
    for x in (12.5, 19.5):
        p.circ(x, 16, 1.6, fill=(236, 204, 100), outline=(130, 96, 30), width=0.5)
    p.line([(3, 3.6), (29, 3.6)], (255, 255, 255, 80), 1)
    return finish(img)


def large_cabinet():
    rng = random.Random(37)
    img, p = new(T, 2 * T)
    p.rect(0, 0, T, 2 * T, fill=(100, 68, 40), outline=(52, 34, 20), width=1.2, r=2)
    planks(p, 2, 2, 30, 62, (148, 104, 62), rng, vertical=True, n=2)
    p.rect(3, 3, 29, 61, outline=(88, 60, 36), width=1)
    p.line([(3, 32), (29, 32)], (78, 52, 30), 1.4)
    p.line([(16, 3), (16, 61)], (78, 52, 30), 1)
    for y in (17, 47):
        for x in (12.5, 19.5):
            p.circ(x, y, 1.6, fill=(236, 204, 100), outline=(130, 96, 30), width=0.5)
    p.line([(3, 3.6), (29, 3.6)], (255, 255, 255, 80), 1)
    return finish(img)


def build(defs):
    """返回 {贴图名: Image}。贴图名：bld_<kind>_<材质>_<朝向0/1>"""
    base = {}
    for m in ("wood", "stone", "iron", "wool"): base[("floor", m)] = floor(m)
    base[("sterile_floor", "iron")] = floor("sterile")
    for m in ("wood", "stone", "iron"):
        base[("wall", m)] = wall(m); base[("window", m)] = window(m); base[("door", m)] = door(m)
    base[("sterile_wall", "iron")] = wall("iron", True)
    base[("bed", "wood")] = bed("plain"); base[("bed", "feather")] = bed("feather")
    base[("medical_bed", "wood")] = bed("medical")
    base[("research_bench", "wood")] = research_bench()
    base[("stove", "stone")] = stove()
    base[("furnace", "stone")] = furnace()
    base[("workbench", "wood")] = workbench()
    base[("flower_pot", "wood")] = flower_pot()
    base[("statue", "stone")] = statue()
    base[("bookshelf", "wood")] = bookshelf()
    base[("fountain", "stone")] = fountain()
    base[("small_cabinet", "wood")] = small_cabinet()
    base[("large_cabinet", "wood")] = large_cabinet()
    out = {}
    for (kind, mat), im in base.items():
        d = defs[kind]
        out[f"bld_{kind}_{mat}_0"] = im
        if d["w"] != d["h"]:
            out[f"bld_{kind}_{mat}_1"] = im.rotate(-90, expand=True)
    return out
