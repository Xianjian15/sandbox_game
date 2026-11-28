# world/farm.py
import pygame
from core import textures
from settings import TILE_SIZE


class FarmZone:
    def __init__(self, rect_tiles, plant_type):
        x1, y1, x2, y2 = rect_tiles
        self.x1, self.y1 = min(x1, x2), min(y1, y2)
        self.x2, self.y2 = max(x1, x2), max(y1, y2)
        self.plant_type = plant_type  # "berry" 或 "tree"
        # 记录每一格的生长度 (0.0 ~ 1.0)，以及是否已播种
        self.plots = {}
        for ty in range(self.y1, self.y2 + 1):
            for tx in range(self.x1, self.x2 + 1):
                self.plots[(tx, ty)] = {"planted": False, "growth": 0.0, "reserved_by": None}

    def contains(self, tx, ty):
        return self.x1 <= tx <= self.x2 and self.y1 <= ty <= self.y2

    def tiles(self):
        for ty in range(self.y1, self.y2 + 1):
            for tx in range(self.x1, self.x2 + 1):
                yield tx, ty

    def update(self, dt):
        for pos, data in self.plots.items():
            if data["planted"] and data["growth"] < 1.0:
                # 树木生长慢，浆果生长快
                speed = 0.005 if self.plant_type == "tree" else 0.02
                data["growth"] = min(1.0, data["growth"] + speed * dt)

    _OVERLAY = None

    def draw(self, surface, camera):
        vx1, vy1, vx2, vy2 = camera.view_tiles()      # 只画屏幕内的格子；底色贴图只建一次
        for tx, ty in self.tiles():
            if tx < vx1 or tx > vx2 or ty < vy1 or ty > vy2:
                continue
            sx, sy = camera.world_to_screen(tx * TILE_SIZE, ty * TILE_SIZE)
            rect = pygame.Rect(sx, sy, TILE_SIZE, TILE_SIZE)

            # 画底色
            if FarmZone._OVERLAY is None:
                FarmZone._OVERLAY = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
                FarmZone._OVERLAY.fill((80, 60, 30, 40))
            surface.blit(FarmZone._OVERLAY, (sx, sy))
            pygame.draw.rect(surface, (139, 90, 43), rect, 1)

            data = self.plots[(tx, ty)]
            if data["planted"]:
                growth = data["growth"]
                ptex = textures.get(f"plant_{self.plant_type}_ripe" if growth >= 1.0
                                    else f"plant_{self.plant_type}_{min(2, int(growth * 3))}")
                if ptex is not None:
                    surface.blit(ptex, (sx, sy))
                elif self.plant_type == "berry":
                    if growth < 1.0:
                        pygame.draw.circle(surface, (80, 180, 80), (int(sx + TILE_SIZE / 2), int(sy + TILE_SIZE / 2)),
                                           int(TILE_SIZE / 4 * growth + 2))
                    else:
                        pygame.draw.circle(surface, (40, 120, 40), (int(sx + TILE_SIZE / 2), int(sy + TILE_SIZE / 2)),
                                           TILE_SIZE // 3)
                        pygame.draw.circle(surface, (220, 60, 60), (int(sx + TILE_SIZE / 2), int(sy + TILE_SIZE / 2)),
                                           3)  # 成熟的红点
                else:  # tree
                    if growth < 1.0:
                        pygame.draw.line(surface, (100, 70, 30), (sx + TILE_SIZE / 2, sy + TILE_SIZE),
                                         (sx + TILE_SIZE / 2, sy + TILE_SIZE - int(TILE_SIZE * growth)), 2)
                    else:
                        pygame.draw.circle(surface, (40, 100, 40), (int(sx + TILE_SIZE / 2), int(sy + TILE_SIZE / 2)),
                                           TILE_SIZE // 2 - 2)


class FarmManager:
    def __init__(self):
        self.farms = []

    def add(self, rect_tiles, plant_type):
        farm = FarmZone(rect_tiles, plant_type)
        self.farms.append(farm)
        return farm

    def find_farm_for(self, tx, ty):
        for f in self.farms:
            if f.contains(tx, ty):
                return f
        return None

    def update(self, dt):
        for f in self.farms:
            f.update(dt)

    def draw(self, surface, camera):
        for f in self.farms:
            f.draw(surface, camera)

    def remove_tiles(self, tx1, ty1, tx2, ty2):
        new_farms = []
        for f in self.farms:
            if not (f.x2 < tx1 or f.x1 > tx2 or f.y2 < ty1 or f.y1 > ty2):
                pass  # 相交则删除
            else:
                new_farms.append(f)
        self.farms = new_farms