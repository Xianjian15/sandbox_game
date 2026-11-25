# world/stockpile.py
import pygame
from settings import TILE_SIZE

class Stockpile:
    def __init__(self, rect_tiles, priority=0):
        x1, y1, x2, y2 = rect_tiles
        self.x1 = min(x1, x2)
        self.y1 = min(y1, y2)
        self.x2 = max(x1, x2)
        self.y2 = max(y1, y2)
        self.priority = priority

    def contains(self, tx, ty):
        return self.x1 <= tx <= self.x2 and self.y1 <= ty <= self.y2

    def tiles(self):
        for ty in range(self.y1, self.y2 + 1):
            for tx in range(self.x1, self.x2 + 1):
                yield tx, ty

    def draw(self, surface, camera):
        vx1, vy1, vx2, vy2 = camera.view_tiles()
        # 只画屏幕内的格子；半透明底色贴图只建一次（以前每格每帧都新建一张 Surface）
        for ty in range(max(self.y1, vy1), min(self.y2, vy2) + 1):
            for tx in range(max(self.x1, vx1), min(self.x2, vx2) + 1):
                self._draw_tile(surface, camera, tx, ty)

    _OVERLAY = None

    def _draw_tile(self, surface, camera, tx, ty):
        if True:
            sx, sy = camera.world_to_screen(tx * TILE_SIZE, ty * TILE_SIZE)
            rect = pygame.Rect(sx, sy, TILE_SIZE, TILE_SIZE)
            if Stockpile._OVERLAY is None:
                Stockpile._OVERLAY = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
                Stockpile._OVERLAY.fill((80, 140, 220, 40))
            surface.blit(Stockpile._OVERLAY, (sx, sy))
            pygame.draw.rect(surface, (100, 170, 255), rect, 1)


class StockpileManager:
    def __init__(self):
        self.stockpiles = []

    def add(self, rect_tiles):
        sp = Stockpile(rect_tiles)
        self.stockpiles.append(sp)
        return sp

    def find_stockpile_for(self, tx, ty):
        for sp in self.stockpiles:
            if sp.contains(tx, ty):
                return sp
        return None

    def all_tiles(self):
        for sp in self.stockpiles:
            for t in sp.tiles():
                yield t

    def remove_tiles(self, tx1, ty1, tx2, ty2):
        """删除框选范围内的库存区。为了简单，只要有重叠就删除整个区域"""
        new_sp = []
        for sp in self.stockpiles:
            # 矩形不相交的判断
            if not (sp.x2 < tx1 or sp.x1 > tx2 or sp.y2 < ty1 or sp.y1 > ty2):
                pass # 相交，丢弃
            else:
                new_sp.append(sp)
        self.stockpiles = new_sp

    def draw(self, surface, camera):
        for sp in self.stockpiles:
            sp.draw(surface, camera)