# combat/weapon_render.py
import math
import pygame


def draw_gun(surface, cx, cy, angle_rad, weapon_def, scale=1.0, flip_y=False):
    """
    在屏幕坐标 (cx, cy) 处，朝向 angle_rad 画一把枪。
    angle_rad = 0 表示朝右，PI/2 表示朝下（屏幕坐标 y 向下）。
    """
    draw = weapon_def.get("draw")
    if draw is None:
        return   # 拳头/匕首不画枪

    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    def rot(px, py):
        # px 沿枪管方向，py 垂直枪管方向（正为下）
        rx = px * cos_a - py * sin_a
        ry = px * sin_a + py * cos_a
        return (cx + rx * scale, cy + ry * scale)

    def fill_rot_rect(offset_x, offset_y, w, h, color, outline=True):
        # 计算旋转后的四个角
        x1, y1 = offset_x, offset_y
        x2, y2 = offset_x + w, offset_y
        x3, y3 = offset_x + w, offset_y + h
        x4, y4 = offset_x, offset_y + h
        pts = [rot(x1, y1), rot(x2, y2), rot(x3, y3), rot(x4, y4)]
        pts = [(int(x), int(y)) for (x, y) in pts]
        pygame.draw.polygon(surface, color, pts)
        if outline:
            pygame.draw.polygon(surface, (0, 0, 0), pts, 1)

    # ---- 画出各个部件 ----
    # 从后往前画：枪托 → 枪身 → 弹匣 → 枪管
    stock = draw.get("stock")
    body = draw.get("body")
    mag = draw.get("mag")
    barrel = draw.get("barrel")

    # 枪托（在枪身后面，向 -x 方向）
    if stock:
        sw, sh = stock
        fill_rot_rect(-sw, -sh / 2, sw, sh, (80, 55, 35))

    # 枪身
    if body:
        bw, bh = body
        fill_rot_rect(0, -bh / 2, bw, bh, (55, 55, 60))

    # 弹匣（枪身下方）
    if mag:
        mw, mh = mag
        fill_rot_rect(body[0] * 0.4, body[1] / 2, mw, mh, (40, 40, 45))

    # 枪管（枪身前端）
    if barrel:
        brw, brh = barrel
        fill_rot_rect(body[0], -brh / 2, brw, brh, (35, 35, 40))

    # 枪口小亮点
    if barrel:
        brw, brh = barrel
        tip_x = body[0] + brw
        tip_y = 0
        tip_screen = rot(tip_x, tip_y)
        pygame.draw.circle(surface, weapon_def["color"],
                           (int(tip_screen[0]), int(tip_screen[1])), 2)


def draw_knife(surface, cx, cy, angle_rad, weapon_def, scale=1.0):
    """匕首（如果要给敌人用）"""
    import math
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    # 刀身
    L = 14 * scale
    W = 3 * scale
    x1, y1 = 0, -W / 2
    x2, y2 = L, -W / 2
    x3, y3 = L, W / 2
    x4, y4 = 0, W / 2
    def rot(px, py):
        return (cx + px * cos_a - py * sin_a,
                cy + px * sin_a + py * cos_a)
    pts = [rot(x1, y1), rot(x2, y2), rot(x3, y3), rot(x4, y4)]
    pts = [(int(x), int(y)) for (x, y) in pts]
    pygame.draw.polygon(surface, (220, 220, 230), pts)
    pygame.draw.polygon(surface, (0, 0, 0), pts, 1)


def draw_weapon(surface, cx, cy, angle_rad, weapon_def, scale=1.0):
    d = weapon_def.get("draw")
    if d is None:
        return
    draw_gun(surface, cx, cy, angle_rad, weapon_def, scale)