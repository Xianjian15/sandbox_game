# core/camera.py
import pygame
from settings import TILE_SIZE

class Camera:
    def __init__(self, vw, vh, map_w_px, map_h_px):
        self.x = 0.0
        self.y = 0.0
        self.vw = vw
        self.vh = vh
        self.map_w = map_w_px
        self.map_h = map_h_px

    def move_by(self, dx, dy):
        self.x += dx
        self.y += dy
        self._clamp()

    def _clamp(self):
        self.x = max(0, min(self.x, self.map_w - self.vw))
        self.y = max(0, min(self.y, self.map_h - self.vh))

    def resize(self, vw, vh):
        self.vw = vw
        self.vh = vh
        self._clamp()

    def world_to_screen(self, wx, wy):
        return wx - self.x, wy - self.y

    def screen_to_world(self, sx, sy):
        return sx + self.x, sy + self.y

    def screen_to_tile(self, sx, sy):
        wx, wy = self.screen_to_world(sx, sy)
        return int(wx // TILE_SIZE), int(wy // TILE_SIZE)

    def view_tiles(self, margin=1):
        """当前画面覆盖的格子范围 (x1, y1, x2, y2)（含边缘 margin 格）。绘制时只画这个范围里的东西——
        后期建筑/物品/农田/库存区很多，全画一遍（哪怕在屏幕外）每帧都很耗时。"""
        x1 = int(self.x // TILE_SIZE) - margin
        y1 = int(self.y // TILE_SIZE) - margin
        x2 = int((self.x + self.vw) // TILE_SIZE) + margin
        y2 = int((self.y + self.vh) // TILE_SIZE) + margin
        return x1, y1, x2, y2

    def rect_visible(self, tx, ty, w=1, h=1, margin=1):
        x1, y1, x2, y2 = self.view_tiles(margin)
        return not (tx + w - 1 < x1 or tx > x2 or ty + h - 1 < y1 or ty > y2)
