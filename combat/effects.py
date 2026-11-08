# combat/effects.py
import pygame
from settings import TILE_SIZE


class Shot:
    """一条弹道特效"""
    def __init__(self, x1, y1, x2, y2, color):
        self.x1, self.y1 = x1, y1
        self.x2, self.y2 = x2, y2
        self.color = color
        self.ttl = 0.15
        self.max_ttl = 0.15

    def update(self, dt):
        self.ttl -= dt
        return self.ttl > 0

    def draw(self, surface, camera):
        if self.ttl <= 0:
            return
        # 透明度
        alpha = self.ttl / self.max_ttl
        sx1, sy1 = camera.world_to_screen(self.x1, self.y1)
        sx2, sy2 = camera.world_to_screen(self.x2, self.y2)
        # 外层粗线（发光感）
        w = max(1, int(4 * alpha))
        c_outer = tuple(int(v * alpha) for v in self.color)
        pygame.draw.line(surface, c_outer, (sx1, sy1), (sx2, sy2), w)
        # 内层亮线
        pygame.draw.line(surface, (255, 255, 255),
                         (int(sx1), int(sy1)), (int(sx2), int(sy2)), 1)


class MeleeHit:
    """近战撞击闪光"""
    def __init__(self, x, y, color=(255, 200, 100)):
        self.x, self.y = x, y
        self.color = color
        self.ttl = 0.2
        self.max_ttl = 0.2

    def update(self, dt):
        self.ttl -= dt
        return self.ttl > 0

    def draw(self, surface, camera):
        if self.ttl <= 0:
            return
        alpha = self.ttl / self.max_ttl
        sx, sy = camera.world_to_screen(self.x, self.y)
        radius = int(20 * (1 - alpha) + 8)
        c = tuple(int(v * alpha) for v in self.color)
        # 画一个扩散环
        pygame.draw.circle(surface, c, (int(sx), int(sy)), radius, 2)
        pygame.draw.circle(surface, (255, 255, 255), (int(sx), int(sy)),
                           max(2, int(radius * 0.4)))


class CombatLog:
    """屏幕底部的战斗日志"""
    def __init__(self):
        self.events = []   # [[text, color, ttl], ...]

    def add(self, text, color=(255, 255, 255)):
        self.events.append([text, color, 4.0])
        if len(self.events) > 6:
            self.events.pop(0)

    def update(self, dt):
        for e in self.events:
            e[2] -= dt
        self.events = [e for e in self.events if e[2] > 0]

    def draw(self, surface, font, screen_w, screen_h):
        y0 = screen_h - 30
        for text, color, ttl in reversed(self.events):
            alpha = min(1.0, ttl)
            c = tuple(int(v * alpha) for v in color)
            surf = font.render(text, True, c)
            surface.blit(surf, (screen_w - surf.get_width() - 12, y0))
            y0 -= 20