# tools/gen_items.py —— 物品图标（32×32，居中，带轻微投影）
import math, random
from PIL import Image
from tools.texlib import *

HANDLE = (128, 86, 46)
STEEL = (196, 202, 214)
STONEC = (150, 152, 160)


def icon():
    img, p = new(T, T)
    return img, p


SHADOW = True


def _shadow(img, box=(5, 25, 27, 31), a=70):
    if SHADOW: shadow(img, box, 1.0, a)


def wood():
    img, p = icon(); _shadow(img)
    for i, (cx, cy) in enumerate(((11, 21), (21, 21), (16, 12))):
        p.rect(cx - 9 if i < 2 else cx - 9, cy - 4, cx + 9, cy + 4, fill=(130, 88, 50), outline=(70, 44, 24), width=0.7, r=4)
        p.ell(cx + 5, cy - 4, cx + 11, cy + 4, fill=(214, 170, 112), outline=(90, 58, 32), width=0.6)
        p.ell(cx + 6.6, cy - 2, cx + 9.4, cy + 2, outline=(160, 118, 72), width=0.5)
        p.line([(cx - 7, cy - 1.5), (cx + 3, cy - 1.5)], (160, 112, 68), 0.6)
    return finish(img)


def stone():
    img, p = icon(); _shadow(img)
    rng = random.Random(3)
    from tools.gen_terrain import boulder
    boulder(img, p, 11, 21, 7.5, 5.5, (130, 132, 140), rng)
    boulder(img, p, 21, 19, 7, 6, (146, 148, 156), rng)
    boulder(img, p, 16, 12.5, 6, 5, (122, 124, 132), rng)
    return finish(img)


def iron_ore():
    img, p = icon(); _shadow(img)
    rng = random.Random(4)
    from tools.gen_terrain import boulder
    boulder(img, p, 12, 19, 9, 7, (112, 98, 108), rng)
    boulder(img, p, 21, 15, 7, 6, (124, 108, 118), rng)
    for cx, cy, r in ((9, 18, 1.8), (15, 22, 1.4), (20, 12, 1.7), (23, 17, 1.2)):
        p.poly([(cx, cy - r * 1.3), (cx + r, cy), (cx, cy + r * 1.2), (cx - r, cy)], fill=(210, 116, 80), outline=(120, 55, 40))
    return finish(img)


def iron():
    img, p = icon(); _shadow(img, (3, 24, 29, 31))
    for (x, y) in ((4, 18), (15, 18), (9.5, 9)):
        p.poly([(x, y + 7), (x + 3, y), (x + 13, y), (x + 12, y + 7)], fill=(170, 176, 192), outline=(70, 74, 88))
        p.poly([(x + 3, y), (x + 13, y), (x + 12.4, y + 2), (x + 2.4, y + 2)], fill=(236, 240, 248))
        p.poly([(x, y + 7), (x + 12, y + 7), (x + 12, y + 5.6), (x + 0.5, y + 5.6)], fill=(122, 128, 144))
    return finish(img)


def food():                       # 浆果
    img, p = icon(); _shadow(img)
    p.poly([(16, 10), (19, 6), (22, 9)], fill=(60, 140, 66), outline=(30, 90, 36))
    for cx, cy in ((11, 19), (20, 19), (15.5, 13), (24, 24), (9, 25)):
        p.circ(cx, cy, 4.2, fill=(214, 44, 64), outline=(110, 20, 36), width=0.6)
        p.circ(cx - 1.3, cy - 1.4, 1.2, fill=(255, 190, 196))
        p.circ(cx, cy - 3.4, 1.0, fill=(60, 130, 60))
    return finish(img)


def meat():
    img, p = icon(); _shadow(img)
    p.ell(7, 8, 27, 26, fill=(196, 62, 66), outline=(110, 30, 34), width=0.9)
    p.ell(10, 10, 24, 22, fill=(226, 96, 96))
    p.poly([(9, 14), (14, 11), (20, 13), (14, 16)], fill=(250, 190, 188, 200))
    p.line([(11, 21), (17, 15), (22, 18)], (250, 214, 210), 0.9)
    p.line([(6, 25), (13, 18)], (246, 244, 236), 2.2)
    p.circ(5.2, 25.6, 2.2, fill=(246, 244, 236), outline=(160, 156, 144), width=0.5)
    p.circ(7.2, 27.2, 2.2, fill=(246, 244, 236), outline=(160, 156, 144), width=0.5)
    return finish(img)


def leather():
    img, p = icon(); _shadow(img)
    pts = [(6, 10), (12, 7), (20, 8), (26, 6), (27, 14), (24, 18), (27, 24), (19, 26), (13, 24), (6, 26), (8, 18)]
    p.poly(pts, fill=(172, 112, 66), outline=(94, 56, 30))
    p.poly([(9, 11), (14, 9), (21, 10), (24, 9), (24, 14), (21, 17), (12, 18), (9, 17)], fill=(196, 138, 86))
    for x, y in ((9, 22), (22, 22), (22, 12)):
        p.circ(x, y, 0.8, fill=(110, 66, 36))
    p.line([(10, 20), (20, 21)], (130, 84, 48), 0.7)
    return finish(img)


def feather():
    img, p = icon(); _shadow(img)
    p.poly([(7, 27), (9, 17), (16, 8), (26, 5), (25, 14), (18, 22), (9, 26)], fill=(244, 240, 228), outline=(150, 142, 126))
    p.poly([(9, 17), (16, 8), (26, 5), (19, 12), (13, 20)], fill=(212, 220, 232))
    p.line([(6, 29), (24, 7)], (170, 160, 142), 1.2)
    for i in range(5):
        x = 10 + i * 3; y = 24 - i * 3.6
        p.line([(x, y), (x - 3, y - 2)], (176, 184, 198), 0.5)
    return finish(img)


def wool():
    img, p = icon(); _shadow(img)
    for cx, cy, r in ((11, 19, 6.5), (21, 19, 6.5), (16, 12, 7), (16, 20, 6.5)):
        p.circ(cx, cy, r, fill=(236, 236, 228), outline=(174, 174, 164), width=0.6)
    for cx, cy, r in ((10, 17, 3.4), (20, 10, 3.4), (22, 18, 3), (15, 22, 3)):
        p.circ(cx, cy, r, outline=(204, 204, 194), width=0.6)
    p.circ(14, 9, 2, fill=(255, 255, 255))
    return finish(img)


def bowl(fine):
    img, p = icon(); _shadow(img, (3, 24, 29, 31))
    if not fine:
        p.poly([(5, 15), (27, 15), (24, 26), (8, 26)], fill=(176, 120, 72), outline=(92, 58, 32))
        p.ell(5, 11, 27, 19, fill=(122, 80, 46), outline=(92, 58, 32), width=0.7)
        p.ell(7, 12, 25, 18, fill=(214, 140, 60))
        for x, y, c in ((11, 15, (110, 170, 80)), (17, 14, (190, 60, 60)), (21, 16, (240, 220, 140)), (14, 17, (240, 220, 140))):
            p.circ(x, y, 1.6, fill=c)
        p.line([(12, 9), (13, 5)], (240, 240, 240, 150), 1); p.line([(18, 9), (17, 4)], (240, 240, 240, 150), 1)
    else:
        p.circ(16, 16, 13, fill=(244, 244, 248), outline=(150, 150, 168), width=0.9)
        p.circ(16, 16, 9.5, outline=(205, 205, 220), width=0.7)
        p.ell(8, 11, 22, 22, fill=(168, 88, 40), outline=(100, 48, 20), width=0.7)
        p.ell(10, 12, 20, 18, fill=(214, 134, 66))
        for a in range(5):
            x = 9 + a * 3.5; p.circ(x, 24 - (a % 2) * 1.4, 1.5, fill=(80, 160, 76))
        p.circ(22, 13, 2.8, fill=(220, 54, 60)); p.circ(21.4, 12.4, 0.8, fill=(255, 200, 200))
        p.line([(24, 20), (26.5, 16)], (80, 160, 76), 1.2)
    return finish(img)


def medicine():
    img, p = icon(); _shadow(img)
    for ang, ln in ((-50, 13), (-20, 15), (10, 15), (40, 13)):
        r = math.radians(ang - 90)
        ex, ey = 16 + math.cos(r) * ln, 28 + math.sin(r) * ln
        p.line([(16, 28), (ex, ey)], (60, 130, 64), 1.2)
        p.ell(ex - 3.4, ey - 5, ex + 3.4, ey + 5, fill=(88, 176, 92), outline=(40, 100, 48), width=0.6)
        p.line([(ex, ey - 4), (ex, ey + 4)], (150, 220, 150), 0.5)
    p.circ(16, 28, 1.6, fill=(50, 110, 56))
    return finish(img)


# ---------------- 工具 / 武器：斜放，柄左下 → 头右上 ----------------
def _handle(p, x1=6, y1=27, x2=22, y2=11, w=2.6, col=HANDLE):
    p.line([(x1, y1), (x2, y2)], shade(col, 0.55), w + 1.0)
    p.line([(x1, y1), (x2, y2)], col, w)
    p.line([(x1 + 0.2, y1 - 0.8), (x2 + 0.2, y2 - 0.8)], shade(col, 1.3), 0.7)


def pickaxe(iron):
    img, p = icon(); _shadow(img)
    _handle(p, 6, 27, 23, 10)
    head = (206, 212, 224) if iron else (150, 152, 160)
    ed = (84, 88, 100) if iron else (80, 82, 90)
    p.poly([(8, 8), (18, 6), (27, 12), (27, 15), (20, 11), (12, 11), (9, 14), (6, 14)], fill=head, outline=ed)
    p.poly([(10, 8.5), (18, 6.8), (24, 10.5), (18, 9), (12, 9.6)], fill=shade(head, 1.28))
    return finish(img)


def axe(iron):
    img, p = icon(); _shadow(img)
    _handle(p, 6, 27, 22, 9)
    head = (210, 216, 228) if iron else (148, 150, 158)
    ed = (84, 88, 100) if iron else (80, 82, 90)
    p.poly([(16, 5), (28, 6), (28, 16), (24, 13), (19, 14), (17, 12)], fill=head, outline=ed)
    p.poly([(17, 5.6), (27, 6.4), (27, 9), (19, 8.6)], fill=shade(head, 1.28))
    p.line([(26.5, 7), (26.5, 15)], shade(head, 1.4), 0.8)
    if not iron:
        p.line([(16, 12), (22, 12)], (180, 140, 90), 1.4)
    return finish(img)


def spear(kind):
    img, p = icon(); _shadow(img)
    _handle(p, 4, 29, 22, 11, 2.0, (150, 104, 60) if kind != "iron" else (140, 98, 56))
    if kind == "iron":
        p.poly([(21, 12), (25, 4), (28, 3), (27, 7), (23, 14)], fill=STEEL, outline=(80, 84, 98))
        p.line([(22.5, 11), (26.5, 4.5)], (255, 255, 255), 0.7)
    else:
        p.poly([(20, 13), (23, 4), (28, 3), (26, 9), (23, 15)], fill=(150, 152, 160), outline=(80, 82, 90))
        p.line([(21, 14), (25, 6)], (200, 202, 210), 0.7)
    p.line([(20, 14), (24, 16)], (196, 150, 90), 1.4)
    return finish(img)


def hammer(iron):
    img, p = icon(); _shadow(img)
    _handle(p, 6, 27, 20, 12)
    head = (130, 132, 146) if iron else (150, 152, 160)
    ed = (60, 62, 74)
    p.poly([(12, 8), (24, 4), (29, 10), (17, 15)], fill=head, outline=ed)
    p.poly([(13, 8.4), (24, 4.6), (26, 6.5), (15, 10.4)], fill=shade(head, 1.3))
    if iron:
        p.poly([(24, 4), (29, 10), (27, 11.4), (22, 5.8)], fill=shade(head, 0.8))
    return finish(img)


def knife(kind):
    img, p = icon(); _shadow(img)
    long_ = kind in ("machete",)
    hx, hy = (6, 27)
    p.line([(hx, hy), (hx + 5, hy - 5)], shade(HANDLE, 0.5), 3.6)
    p.line([(hx, hy), (hx + 5, hy - 5)], HANDLE, 2.6)
    p.line([(hx + 4, hy - 7), (hx + 8, hy - 3)], (210, 170, 70), 1.4)
    if kind == "stone":
        p.poly([(hx + 5, hy - 6), (hx + 8, hy - 3), (24, 9), (22, 5)], fill=(150, 152, 160), outline=(80, 82, 90))
        p.line([(hx + 7, hy - 6), (22, 6.4)], (210, 212, 220), 0.7)
    elif kind == "machete":
        p.poly([(hx + 5, hy - 7), (hx + 8, hy - 4), (27, 6), (28, 3), (22, 2.5)], fill=STEEL, outline=(80, 84, 98))
        p.line([(hx + 7, hy - 7), (26, 3.4)], (255, 255, 255), 0.8)
    else:
        p.poly([(hx + 5, hy - 6), (hx + 8, hy - 3), (22, 8), (24, 5)], fill=STEEL, outline=(80, 84, 98))
        p.line([(hx + 7, hy - 6), (23, 5.6)], (255, 255, 255), 0.7)
    return finish(img)


def sword():
    img, p = icon(); _shadow(img)
    p.poly([(11, 21), (23, 5), (28, 4), (27, 9), (13, 23)], fill=STEEL, outline=(80, 84, 98))
    p.line([(13, 20), (26, 5.5)], (255, 255, 255), 0.9)
    p.line([(9, 19), (15, 25)], (214, 170, 66), 2.2)
    p.line([(6, 28), (11, 23)], HANDLE, 2.6)
    p.circ(5.4, 28.6, 1.6, fill=(214, 170, 66))
    return finish(img)


def club():
    img, p = icon(); _shadow(img)
    p.poly([(5, 28), (7, 24), (20, 11), (27, 5), (28, 10), (22, 17), (9, 29)], fill=(150, 102, 58), outline=(78, 50, 26))
    p.line([(8, 25), (24, 8)], (190, 142, 90), 1)
    for x, y in ((24, 8), (21, 12)):
        p.circ(x, y, 0.8, fill=(100, 66, 36))
    return finish(img)


def bow(cross=False):
    img, p = icon(); _shadow(img)
    if not cross:
        p.arc((5, 3, 25, 29), -75, 75, (0, 0, 0, 100), 3.6)
        p.arc((4, 3, 24, 29), -75, 75, (150, 102, 58), 2.6)
        p.arc((4.4, 3, 24.4, 29), -60, -20, (200, 154, 100), 0.8)
        p.line([(14.5, 5.5), (21, 16), (14.5, 26.5)], (240, 236, 220), 0.8)
        p.line([(6, 16), (24, 16)], (150, 102, 58), 1.2)
        p.poly([(24, 16), (20, 13.4), (20, 18.6)], fill=(190, 196, 208))
    else:
        p.rect(14, 7, 18, 28, fill=(120, 86, 52), outline=(62, 42, 24), width=0.7, r=1.4)
        p.arc((3, 6, 29, 22), 200, 340, (110, 110, 118), 3.2)
        p.arc((3.4, 6, 29, 21), 205, 335, (170, 174, 186), 1.4)
        p.line([(4, 13), (16, 18), (28, 13)], (240, 236, 220), 0.8)
        p.rect(14.6, 8, 17.4, 16, fill=(90, 94, 106))
        p.poly([(16, 3), (14, 9), (18, 9)], fill=(200, 204, 214), outline=(70, 74, 86))
    return finish(img)


def gun(kind):
    img, p = icon(); _shadow(img, (3, 24, 29, 30))
    dark = (58, 62, 74); mid = (96, 102, 118)
    if kind == "pistol":
        p.rect(7, 9, 24, 15, fill=mid, outline=(30, 32, 40), width=0.8, r=1.4)
        p.poly([(9, 15), (15, 15), (13, 26), (7, 26)], fill=(110, 76, 44), outline=(52, 34, 20))
        p.line([(15, 15.4), (18, 19)], dark, 1.1)
        p.rect(7, 9, 24, 11, fill=(150, 156, 172))
        p.circ(24.5, 12, 1, fill=(20, 20, 24))
    elif kind == "smg":
        p.rect(4, 10, 27, 16, fill=mid, outline=(30, 32, 40), width=0.8, r=1.4)
        p.rect(17, 16, 21, 28, fill=dark, outline=(24, 26, 32), width=0.6)
        p.poly([(6, 16), (11, 16), (10, 24), (5, 24)], fill=(110, 76, 44), outline=(52, 34, 20))
        p.rect(4, 10, 27, 12, fill=(150, 156, 172))
        p.rect(26, 11, 31, 14, fill=dark)
    elif kind in ("rifle", "gun"):
        p.rect(2, 11, 30, 17, fill=mid, outline=(30, 32, 40), width=0.8, r=1.2)
        p.poly([(2, 10), (10, 10), (10, 20), (3, 22)], fill=(124, 86, 50), outline=(58, 38, 22))
        p.rect(14, 17, 18, 26, fill=dark, outline=(24, 26, 32), width=0.6)
        p.rect(2, 11, 30, 13, fill=(150, 156, 172))
        p.rect(18, 8, 24, 11, fill=(70, 74, 88), outline=(30, 32, 40), width=0.5)
    elif kind == "shotgun":
        p.rect(8, 9, 31, 13, fill=(110, 116, 132), outline=(30, 32, 40), width=0.7, r=1)
        p.rect(8, 13, 31, 17, fill=(92, 98, 112), outline=(30, 32, 40), width=0.7, r=1)
        p.poly([(2, 10), (10, 10), (10, 19), (3, 22)], fill=(132, 90, 50), outline=(58, 38, 22))
        p.rect(16, 17, 24, 21, fill=(120, 84, 48), outline=(52, 34, 20), width=0.6, r=1)
    else:                                       # sniper
        p.rect(2, 12, 31, 16, fill=mid, outline=(30, 32, 40), width=0.8, r=1)
        p.poly([(2, 11), (9, 11), (9, 21), (3, 22)], fill=(104, 78, 50), outline=(52, 34, 20))
        p.rect(11, 6, 23, 10, fill=(60, 64, 78), outline=(24, 26, 32), width=0.6, r=1.4)
        p.circ(11, 8, 2.4, fill=(120, 190, 230), outline=(24, 26, 32), width=0.6)
        p.line([(26, 16), (24, 22)], dark, 1); p.line([(28, 16), (30, 22)], dark, 1)
        p.rect(2, 12, 31, 13.6, fill=(150, 156, 172))
    return finish(img)


def build(prefix="item_"):
    o = {
        "wood": wood(), "stone": stone(), "iron_ore": iron_ore(), "iron": iron(), "food": food(), "meat": meat(),
        "leather": leather(), "feather": feather(), "wool": wool(), "meal_simple": bowl(False), "meal_fine": bowl(True),
        "medicine": medicine(),
        "stone_pickaxe": pickaxe(False), "iron_pickaxe": pickaxe(True),
        "stone_axe": axe(False), "axe": axe(True),
        "stone_spear": spear("stone"), "spear": spear("wood"), "iron_spear": spear("iron"),
        "stone_hammer": hammer(False), "war_hammer": hammer(True),
        "stone_knife": knife("stone"), "dagger": knife("iron"), "machete": knife("machete"),
        "longsword": sword(), "club": club(), "bow": bow(), "crossbow": bow(True),
        "pistol": gun("pistol"), "rifle": gun("rifle"), "shotgun": gun("shotgun"), "smg": gun("smg"),
        "sniper": gun("sniper"), "gun": gun("gun"),
    }
    return {f"{prefix}{k}": v for k, v in o.items()}
