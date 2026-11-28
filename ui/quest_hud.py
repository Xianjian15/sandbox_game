# ui/quest_hud.py
"""左上角支线任务追踪面板。点标题栏或按 Q 收起/展开。"""
import pygame
from systems.quests import _name_item

X, Y, W = 10, 44, 300


def draw(surface, font, g):
    """画任务面板，并把占用的矩形记到 g.quest_rect（供点击/防穿透判断）。"""
    qm = g.quests
    head = pygame.Rect(X, Y, W, 24)
    if not qm.active and not g.show_quests:
        g.quest_rect = head
    lines = []
    cache = {}
    for q in qm.active:
        p = qm.progress(q, g, cache)
        lines.append((q, p))
    h = 24 + (len(lines) * 46 if g.show_quests else 0) + (22 if g.show_quests and not lines else 0)
    rect = pygame.Rect(X, Y, W, h)
    g.quest_rect = rect
    s = pygame.Surface((W, h), pygame.SRCALPHA)
    s.fill((20, 20, 28, 190))
    surface.blit(s, rect)
    pygame.draw.rect(surface, (200, 170, 80), rect, 1)
    surface.blit(font.render(f"支线任务 {len(lines)}  已完成 {qm.done}  [Q] {'收起' if g.show_quests else '展开'}",
                             True, (255, 220, 120)), (X + 8, Y + 4))
    if not g.show_quests:
        return
    y = Y + 28
    if not lines:
        surface.blit(font.render("暂无任务，稍后会有新的委托", True, (170, 170, 170)), (X + 8, y))
        return
    for q, p in lines:
        title = q["title"]
        surface.blit(font.render(title, True, (235, 235, 240)), (X + 8, y))
        ratio = p / max(1, q["target"])
        bar = pygame.Rect(X + 8, y + 18, W - 16, 8)
        pygame.draw.rect(surface, (50, 50, 55), bar)
        pygame.draw.rect(surface, (110, 200, 120), (bar.x, bar.y, int(bar.w * ratio), bar.h))
        rtxt = "、".join(f"{_name_item(k)}×{v}" for k, v in q["reward"].items())
        surface.blit(font.render(f"{p}/{q['target']}   奖励：{rtxt}", True, (190, 190, 150)), (X + 8, y + 27))
        y += 46
