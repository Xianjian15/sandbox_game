# tools/gen_creatures.py —— 动物（朝右，48×40）、小人 / 敌人（俯视，36×36，朝右）、农作物
import math, random
from PIL import Image
from tools.texlib import *
from tools import gen_terrain

AW, AH = 48, 40


def ground(img, cx=24, w=34):
    shadow(img, (cx - w / 2, 30, cx + w / 2, 38), 1.3, 90)


def eye(p, x, y, r=1.3, col=(20, 20, 24)):
    p.circ(x, y, r, fill=col); p.circ(x - r * 0.3, y - r * 0.3, r * 0.35, fill=(255, 255, 255))


def rabbit():
    img, p = new(AW, AH); ground(img, 24, 30)
    fur, belly, pink = (240, 232, 222), (255, 252, 246), (255, 176, 186)
    p.ell(30, 18, 41, 29, fill=fur, outline=(150, 138, 126), width=0.8)           # 后腿
    p.ell(8, 15, 36, 33, fill=fur, outline=(150, 138, 126), width=0.9)             # 身体
    p.ell(14, 25, 32, 33, fill=belly)
    p.circ(8, 24, 4.2, fill=(255, 255, 255), outline=(190, 186, 180), width=0.6)     # 尾巴
    p.ell(30, 28, 40, 33, fill=shade(fur, 0.95), outline=(150, 138, 126), width=0.6)
    p.circ(35, 15, 6.2, fill=fur, outline=(150, 138, 126), width=0.9)              # 头
    p.ell(36, 17, 44, 22, fill=fur, outline=(150, 138, 126), width=0.6)
    p.ell(30, 1, 34.6, 14, fill=fur, outline=(150, 138, 126), width=0.8)           # 耳朵
    p.ell(33.4, 2, 38, 14, fill=fur, outline=(150, 138, 126), width=0.8)
    p.ell(31, 3, 33.6, 12, fill=pink); p.ell(34.6, 4, 37, 12, fill=pink)
    eye(p, 37.5, 14, 1.5, (190, 40, 50)); p.circ(43, 18, 1.1, fill=(255, 150, 160))
    return finish(img)


def deer():
    img, p = new(AW, AH); ground(img, 24, 36)
    fur, dark, belly = (176, 108, 64), (112, 66, 38), (232, 210, 176)
    for x in (13, 17, 29, 33):                                                  # 腿
        p.line([(x, 25), (x - 0.4, 35)], dark, 2.2); p.rect(x - 1.5, 34, x + 0.8, 36, fill=(52, 34, 22))
    p.ell(8, 15, 38, 30, fill=fur, outline=dark, width=0.9)
    p.ell(11, 24, 35, 30, fill=belly)
    for x, y in ((16, 18), (22, 20), (28, 17), (19, 23), (25, 24), (31, 21)):
        p.circ(x, y, 1.1, fill=(240, 220, 190))
    p.poly([(32, 18), (36, 8), (41, 8), (38, 20)], fill=fur, outline=dark)         # 脖子
    p.ell(36, 3, 46, 12, fill=fur, outline=dark, width=0.9)                        # 头
    p.ell(41, 7, 47, 11, fill=(222, 190, 150), outline=dark, width=0.5)
    p.circ(46, 9, 0.9, fill=(30, 20, 20))
    p.ell(34, 3, 38, 8, fill=fur, outline=dark, width=0.6)                          # 耳
    eye(p, 41.2, 6, 1.1)
    for dx, h in ((0, 0), (3.6, 0)):                                                # 鹿角
        p.line([(38 + dx, 4), (36 + dx, -3), (33 + dx, -6)], (226, 206, 160), 1.2)
        p.line([(36.6 + dx, -1), (39.4 + dx, -4)], (226, 206, 160), 1.0)
        p.line([(35.2 + dx, -3.2), (32 + dx, -2)], (226, 206, 160), 1.0)
    p.ell(5, 17, 11, 23, fill=(240, 224, 196), outline=dark, width=0.5)
    return finish(img)


def chicken():
    img, p = new(AW, AH); ground(img, 24, 24)
    body, wing = (206, 150, 90), (164, 110, 62)
    p.line([(17, 33), (17, 36)], (230, 170, 50), 1.4); p.line([(26, 33), (26, 36)], (230, 170, 50), 1.4)
    p.line([(15, 36), (19, 36)], (230, 170, 50), 1.2); p.line([(24, 36), (28, 36)], (230, 170, 50), 1.2)
    for a, col in ((-40, (96, 150, 90)), (-15, (60, 110, 160)), (10, (150, 70, 60))):                   # 尾羽
        r = math.radians(a)
        p.poly([(11, 22), (11 + math.cos(r - 0.2 + math.pi) * 11, 22 + math.sin(r - 0.2 + math.pi) * 11 + 2),
                (11 + math.cos(r + 0.2 + math.pi) * 11, 22 + math.sin(r + 0.2 + math.pi) * 11 + 2)], fill=col, outline=shade(col, 0.6))
    p.ell(10, 15, 33, 34, fill=body, outline=(110, 70, 36), width=0.9)
    p.ell(14, 21, 28, 33, fill=wing, outline=(110, 70, 36), width=0.6)
    p.ell(16, 23, 26, 29, outline=shade(wing, 1.2), width=0.5)
    p.circ(32, 14, 5.4, fill=body, outline=(110, 70, 36), width=0.8)
    for cx in (30, 32.4, 34.8):
        p.circ(cx, 8.8, 1.9, fill=(222, 50, 56), outline=(130, 20, 30), width=0.4)
    p.poly([(36.5, 13), (42, 15), (36.5, 17)], fill=(244, 190, 60), outline=(150, 100, 20))
    p.ell(33.4, 18, 36, 22.6, fill=(222, 50, 56))
    eye(p, 33.8, 13, 1.1)
    return finish(img)


def sheep():
    img, p = new(AW, AH); ground(img, 24, 34)
    for x in (14, 19, 29, 34):
        p.rect(x - 1, 27, x + 1.3, 36, fill=(70, 62, 60)); p.rect(x - 1.4, 34.6, x + 1.7, 36.4, fill=(36, 32, 32))
    wool = (240, 240, 232)
    for cx, cy, r in ((14, 22, 7), (22, 18, 8), (30, 21, 7.5), (20, 25, 7.5), (28, 26, 6.5), (11, 27, 5.5), (33, 26, 5)):
        p.circ(cx, cy, r, fill=wool, outline=(176, 176, 166), width=0.7)
    for cx, cy, r in ((14, 20, 4), (23, 15, 4.4), (31, 19, 4), (21, 23, 4)):
        p.circ(cx, cy, r, fill=(255, 255, 250))
    p.ell(33, 12, 44, 24, fill=(66, 58, 56), outline=(30, 26, 26), width=0.8)
    p.ell(31, 13, 36, 19, fill=(56, 50, 48), outline=(30, 26, 26), width=0.6)
    p.circ(33, 12.5, 4.2, fill=wool, outline=(176, 176, 166), width=0.6)
    eye(p, 40, 16, 1.1, (230, 230, 230)); p.circ(40.2, 16, 0.55, fill=(10, 10, 10))
    p.circ(43.3, 20, 0.8, fill=(30, 26, 26))
    return finish(img)


def fox():
    img, p = new(AW, AH); ground(img, 24, 34)
    fur, dark, white = (226, 120, 44), (130, 62, 24), (252, 244, 232)
    p.poly([(10, 24), (2, 14), (3, 6), (9, 4), (14, 12), (14, 22)], fill=fur, outline=dark)   # 尾巴
    p.poly([(3, 8), (9, 4), (7, 11), (3, 14)], fill=white)
    for x in (14, 18, 28, 32):
        p.line([(x, 26), (x - 0.3, 35)], (52, 30, 20), 2.0)
    p.ell(10, 16, 36, 30, fill=fur, outline=dark, width=0.9)
    p.ell(12, 25, 34, 30, fill=white)
    p.poly([(31, 18), (37, 12), (40, 20), (34, 26)], fill=fur, outline=dark)
    p.poly([(34, 6), (46, 18), (36, 22)], fill=fur, outline=dark, )                             # 头
    p.circ(36, 14, 6.2, fill=fur, outline=dark, width=0.8)
    p.poly([(36, 17), (46, 19.5), (37, 23)], fill=fur, outline=dark)
    p.poly([(38, 19), (46, 19.6), (38, 23)], fill=white)
    p.poly([(32, 9), (31, 0), (37, 6)], fill=fur, outline=dark); p.poly([(33, 7.4), (32.4, 2.6), (35.6, 6)], fill=(60, 36, 28))
    p.poly([(38, 6), (41, -0.6), (42, 8)], fill=fur, outline=dark)
    eye(p, 40.4, 14, 1.1, (40, 30, 10)); p.circ(46, 19.6, 1.1, fill=(24, 20, 20))
    return finish(img)


def boar():
    img, p = new(AW, AH); ground(img, 24, 38)
    fur, dark = (104, 76, 58), (56, 38, 28)
    for x in (13, 17, 31, 35):
        p.line([(x, 26), (x, 35)], dark, 2.6); p.rect(x - 1.7, 34, x + 1.7, 36, fill=(30, 22, 18))
    p.ell(5, 12, 40, 31, fill=fur, outline=dark, width=1)
    for x in range(10, 36, 3):                                             # 背鬃
        p.poly([(x, 14), (x + 1.5, 9), (x + 3, 14)], fill=dark)
    p.ell(8, 22, 36, 31, fill=shade(fur, 0.86))
    p.poly([(5, 20), (1, 17), (4, 24)], fill=dark)                           # 尾巴
    p.ell(32, 12, 46, 28, fill=fur, outline=dark, width=0.9)                 # 头
    p.ell(40, 17, 48, 26, fill=(176, 126, 110), outline=dark, width=0.7)     # 猪鼻
    p.circ(45, 20.5, 0.8, fill=dark); p.circ(45, 24, 0.8, fill=dark)
    p.poly([(41, 25), (45, 22), (44, 27)], fill=(248, 244, 226), outline=(150, 140, 120), )   # 獠牙
    p.poly([(33, 13), (36, 7), (39, 14)], fill=dark)
    eye(p, 38, 18, 1.1, (250, 220, 120))
    return finish(img)


# ---------------- 小人 / 敌人（俯视，朝右；男 / 女两套） ----------------
CW = 44
K = CW / 36.0
SKINS = [(238, 190, 150), (226, 170, 128), (198, 140, 100)]
HAIRS_M = [(84, 56, 36), (36, 30, 30), (176, 128, 58)]
HAIRS_F = [(110, 66, 40), (34, 28, 30), (206, 150, 70)]


def person_body(gender, shirt):
    """身体层（单色白衬衫，运行时按个人颜色染色）。男：肩宽；女：肩窄、腰收。"""
    img = canvas(CW, CW); p = Pen(img, K)
    shadow(img, tuple(v * K for v in (5, 8, 31, 31)), 1.2, 80)
    if gender == "male":
        p.ell(8.4, 7.6, 27.6, 28.4, fill=shirt, outline=shade(shirt, 0.5), width=0.9)       # 宽肩
        p.ell(11.5, 10, 25, 19.5, fill=shade(shirt, 1.18))
        p.line([(14, 24.5), (23, 24.5)], shade(shirt, 0.78), 0.8)
        p.line([(18.2, 9), (18.2, 27)], shade(shirt, 0.82), 0.7)                            # 衣襟缝
    else:
        p.ell(9.6, 9, 26.4, 27, fill=shirt, outline=shade(shirt, 0.5), width=0.9)           # 较窄的肩
        p.ell(12, 11, 24, 19, fill=shade(shirt, 1.2))
        p.poly([(9.5, 19), (12.5, 27.5), (17.5, 29.5), (17.5, 24.5)], fill=shade(shirt, 0.92), outline=shade(shirt, 0.5))  # 下摆外扩
        p.line([(12.5, 21.6), (24, 21.6)], shade(shirt, 0.68), 1.3)                         # 腰带
        p.poly([(21.6, 9.6), (24.6, 13), (20, 13)], fill=shade(shirt, 0.82))                # 领口
    return finish(img)


def person_head(gender, skin, hair, bandana=None):
    """头手层。朝右：脸朝右，头发在后脑；女性有长发披在背后并扎一小束马尾。"""
    img = canvas(CW, CW); p = Pen(img, K)
    sh = 3 if gender == "male" else 2.6
    p.circ(19.5, 6.4 if gender == "male" else 7.2, sh, fill=skin, outline=shade(skin, 0.55), width=0.6)      # 双手
    p.circ(19.5, 29.6 if gender == "male" else 28.8, sh, fill=skin, outline=shade(skin, 0.55), width=0.6)
    if gender == "female":
        p.ell(3.5, 10, 17, 26, fill=hair, outline=shade(hair, 0.5), width=0.7)              # 背后长发
        p.ell(5, 12, 14.5, 22, fill=shade(hair, 1.15))
        p.poly([(5, 15), (0.8, 16.6), (1.4, 20.6), (5, 21.8)], fill=shade(hair, 0.9), outline=shade(hair, 0.5))   # 发梢
        p.circ(7.6, 18, 2.2, fill=(226, 90, 130), outline=(140, 40, 70), width=0.5)          # 发圈
    p.circ(18, 18, 7.4 if gender == "male" else 7.0, fill=skin, outline=shade(skin, 0.5), width=0.8)       # 头
    if gender == "male":
        p.ell(10.4, 10.8, 21, 25.2, fill=hair, outline=shade(hair, 0.5), width=0.6)         # 短发
        p.ell(12.4, 12.6, 18.4, 23.4, fill=shade(hair, 1.2))
    else:
        p.ell(10.6, 10.8, 22.4, 25.2, fill=hair, outline=shade(hair, 0.5), width=0.6)       # 头顶的发 + 刘海
        p.ell(12.4, 12.6, 18.6, 23.4, fill=shade(hair, 1.2))
        p.poly([(19, 11.4), (23.6, 13.4), (22, 15), (19, 14)], fill=hair)
        p.poly([(19, 24.6), (23.6, 22.6), (22, 21), (19, 22)], fill=hair)
    p.circ(22.6, 15.4, 0.9, fill=(40, 30, 28)); p.circ(22.6, 20.6, 0.9, fill=(40, 30, 28))
    if gender == "female":
        p.line([(21.6, 14.3), (23.4, 13.6)], (40, 30, 28), 0.5); p.line([(21.6, 21.7), (23.4, 22.4)], (40, 30, 28), 0.5)  # 睫毛
        p.circ(22.4, 17.5, 0.5, fill=(236, 120, 130, 200)); p.circ(22.4, 18.6, 0.5, fill=(236, 120, 130, 200))
    p.poly([(24.6, 17.3), (26.2, 18), (24.6, 18.8)], fill=shade(skin, 0.82))
    if bandana:
        p.poly([(10, 12), (22, 12.5), (22, 15), (10, 15.5)], fill=bandana)
        p.poly([(10, 21), (22, 20.5), (22, 23.5), (10, 24)], fill=bandana)
        p.poly([(10, 15), (6.5, 18), (10, 21)], fill=shade(bandana, 0.8))
    return finish(img)


# ---------------- 农作物（透明底，与农田底色叠加） ----------------
def sprout(stage):
    img, p = new(T, T)
    shadow(img, (9, 22, 23, 29), 0.9, 70)
    s = 1 + stage
    for dx in (-1, 1):
        p.line([(16, 26), (16 + dx * 3 * s, 26 - 5 * s)], (62, 150, 66), 1.3)
        p.ell(16 + dx * 3 * s - 2.5 * s, 26 - 5 * s - 1.6 * s, 16 + dx * 3 * s + 2.5 * s, 26 - 5 * s + 1.6 * s,
              fill=(96, 188, 88), outline=(46, 110, 50), width=0.5)
    if stage >= 1:
        p.line([(16, 26), (16, 26 - 8 * s * 0.8)], (62, 150, 66), 1.3)
        p.ell(13, 26 - 8 * s * 0.8 - 3, 19, 26 - 8 * s * 0.8 + 2, fill=(110, 200, 100), outline=(46, 110, 50), width=0.5)
    return finish(img)


def sapling(stage):
    img, p = new(T, T)
    shadow(img, (9, 24, 23, 30), 0.9, 80)
    h = 6 + stage * 6
    p.line([(16, 28), (16, 28 - h)], (110, 76, 42), 1.8 + stage * 0.5)
    if stage == 0:
        p.ell(11.5, 28 - h - 3, 16, 28 - h + 1, fill=(98, 188, 88), outline=(44, 108, 50), width=0.5)
        p.ell(16, 28 - h - 4, 20.5, 28 - h, fill=(120, 205, 100), outline=(44, 108, 50), width=0.5)
    else:
        for cx, cy, r in ((16, 28 - h - 2, 3.5 + stage * 2.2), (12.5, 28 - h + 1, 2.6 + stage * 1.6), (19.5, 28 - h + 1, 2.6 + stage * 1.6)):
            p.circ(cx, cy, r, fill=(70, 150, 72), outline=(40, 100, 46), width=0.5)
            p.circ(cx - 0.8, cy - 0.8, r * 0.6, fill=(104, 184, 94))
    return finish(img)


def build():
    o = {"animal_rabbit": rabbit(), "animal_deer": deer(), "animal_chicken": chicken(),
         "animal_sheep": sheep(), "animal_fox": fox(), "animal_boar": boar()}
    for g in ("male", "female"):
        o[f"colonist_{g}_body"] = person_body(g, (236, 236, 240))
        o[f"enemy_{g}_body"] = person_body(g, (176, 48, 44))
        hairs = HAIRS_M if g == "male" else HAIRS_F
        for v in range(3):
            o[f"colonist_{g}_head_{v}"] = person_head(g, SKINS[v], hairs[v])
        o[f"enemy_{g}_head_0"] = person_head(g, (222, 176, 138), (30, 24, 24), bandana=(120, 24, 28))
    for s in range(3): o[f"plant_berry_{s}"] = sprout(s)
    o["plant_berry_ripe"] = gen_terrain.berry(bg=False)
    for s in range(3): o[f"plant_tree_{s}"] = sapling(s)
    o["plant_tree_ripe"] = gen_terrain.tree(0, bg=False)
    return o
