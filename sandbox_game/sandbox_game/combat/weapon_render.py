# combat/weapon_render.py
import math
import pygame

def draw_gun(surface, cx, cy, angle_rad, weapon_def, scale=1.0):
    draw = weapon_def.get("draw")
    if draw is None:
        return

    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    def rot(px, py):
        rx = px * cos_a - py * sin_a
        ry = px * sin_a + py * cos_a
        return (cx + rx * scale, cy + ry * scale)

    def fill_rot_rect(offset_x, offset_y, w, h, color, outline=True):
        x1, y1 = offset_x, offset_y
        x2, y2 = offset_x + w, offset_y
        x3, y3 = offset_x + w, offset_y + h
        x4, y4 = offset_x, offset_y + h
        pts = [rot(x1, y1), rot(x2, y2), rot(x3, y3), rot(x4, y4)]
        pts = [(int(x), int(y)) for (x, y) in pts]
        pygame.draw.polygon(surface, color, pts)
        if outline:
            pygame.draw.polygon(surface, (0, 0, 0), pts, 1)

    stock = draw.get("stock")
    body = draw.get("body")
    mag = draw.get("mag")
    barrel = draw.get("barrel")

    if stock:
        sw, sh = stock
        fill_rot_rect(-sw, -sh / 2, sw, sh, (80, 55, 35))
    if body:
        bw, bh = body
        fill_rot_rect(0, -bh / 2, bw, bh, (55, 55, 60))
    if mag:
        mw, mh = mag
        fill_rot_rect(body[0] * 0.4, body[1] / 2, mw, mh, (40, 40, 45))
    if barrel:
        brw, brh = barrel
        fill_rot_rect(body[0], -brh / 2, brw, brh, (35, 35, 40))
        tip_x = body[0] + brw
        tip_screen = rot(tip_x, 0)
        pygame.draw.circle(surface, weapon_def.get("color", (200,200,200)), (int(tip_screen[0]), int(tip_screen[1])), 2)


def draw_weapon(surface, cx, cy, angle_rad, weapon_def, scale=1.0):
    # 如果是拳头，不画
    if weapon_def.get("name") == "拳头": return

    # 如果定义了 draw 字典（原版枪械），优先使用原版逻辑
    if weapon_def.get("draw") is not None:
        draw_gun(surface, cx, cy, angle_rad, weapon_def, scale)
        return

    # 以下是新增加的近战武器和简易枪械绘制逻辑
    offset_dist = 12 * scale
    wx = cx + math.cos(angle_rad) * offset_dist
    wy = cy + math.sin(angle_rad) * offset_dist
    perp_x = math.cos(angle_rad + math.pi / 2)
    perp_y = math.sin(angle_rad + math.pi / 2)
    w_key = weapon_def.get("name", "")
    color = weapon_def.get("color", (200, 200, 200))

    if w_key == "铁斧":
        hx = wx - math.cos(angle_rad) * 8
        hy = wy - math.sin(angle_rad) * 8
        pygame.draw.line(surface, (139, 69, 19), (hx, hy), (wx, wy), int(3 * scale))
        pts = [
            (wx, wy),
            (wx + perp_x * 6 * scale, wy + perp_y * 6 * scale),
            (wx + math.cos(angle_rad) * 6 * scale + perp_x * 6 * scale, wy + math.sin(angle_rad) * 6 * scale + perp_y * 6 * scale),
            (wx + math.cos(angle_rad) * 6 * scale, wy + math.sin(angle_rad) * 6 * scale)
        ]
        pygame.draw.polygon(surface, color, pts)
        pygame.draw.polygon(surface, (50, 50, 60), pts, 1)
    elif w_key in ("石镐", "铁镐"):
        hx = wx - math.cos(angle_rad) * 8
        hy = wy - math.sin(angle_rad) * 8
        pygame.draw.line(surface, (139, 69, 19), (hx, hy), (wx, wy), int(3 * scale))
        p1 = (wx - perp_x * 8 * scale, wy - perp_y * 8 * scale)
        p2 = (wx + math.cos(angle_rad) * 4 * scale, wy + math.sin(angle_rad) * 4 * scale)
        p3 = (wx + perp_x * 8 * scale, wy + perp_y * 8 * scale)
        pygame.draw.lines(surface, color, False, [p1, p2, p3], int(4 * scale))
    elif w_key == "长剑":
        bx = wx + math.cos(angle_rad) * 10 * scale
        by = wy + math.sin(angle_rad) * 10 * scale
        pygame.draw.line(surface, color, (wx, wy), (bx, by), int(4 * scale))
        hx = wx - math.cos(angle_rad) * 4
        hy = wy - math.sin(angle_rad) * 4
        pygame.draw.line(surface, (180, 140, 60), (wx, wy), (hx, hy), int(3 * scale))
        pygame.draw.line(surface, (200, 200, 0), (wx - perp_x * 5, wy - perp_y * 5), (wx + perp_x * 5, wy + perp_y * 5), int(2 * scale))
    else:
        bx = wx + math.cos(angle_rad) * 10 * scale
        by = wy + math.sin(angle_rad) * 10 * scale
        pygame.draw.line(surface, color, (wx, wy), (bx, by), int(3 * scale))