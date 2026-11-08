# world/farm.py
import pygame
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

    def draw(self, surface, camera):
        for tx, ty in self.tiles():
            sx, sy = camera.world_to_screen(tx * TILE_SIZE, ty * TILE_SIZE)
            rect = pygame.Rect(sx, sy, TILE_SIZE, TILE_SIZE)

            # 画底色
            s = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
            s.fill((80, 60, 30, 40))
            surface.blit(s, (sx, sy))
            pygame.draw.rect(surface, (139, 90, 43), rect, 1)

            data = self.plots[(tx, ty)]
            if data["planted"]:
                growth = data["growth"]
                if self.plant_type == "berry":
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