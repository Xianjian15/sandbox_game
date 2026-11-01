# world/world.py
import pygame
import random
import math
from settings import *

T_GRASS, T_DIRT, T_ROCK, T_WATER, T_TREE, T_BERRY, T_IRON_ROCK = 0, 1, 2, 3, 4, 5, 6
WALKABLE = {T_GRASS, T_DIRT}
HARVESTABLE = {T_ROCK, T_TREE, T_BERRY, T_IRON_ROCK}


class World:
    def __init__(self, cols, rows):
        self.cols, self.rows = cols, rows
        self.tiles = [[T_GRASS for _ in range(cols)] for _ in range(rows)]
        self.buildings = None
        self._generate()
        self.resource_hp = {}
        for r in range(rows):
            for c in range(cols):
                t = self.tiles[r][c]
                if t == T_ROCK:
                    self.resource_hp[(c, r)] = 100
                elif t == T_IRON_ROCK:
                    self.resource_hp[(c, r)] = 150
                elif t == T_TREE:
                    self.resource_hp[(c, r)] = 60
                elif t == T_BERRY:
                    self.resource_hp[(c, r)] = 30

    def _generate(self):
        random.seed(7)
        # 随机地形和树、石头
        for _ in range(120):
            cx, cy = random.randint(0, self.cols - 1), random.randint(0, self.rows - 1)
            r, t = random.randint(2, 5), random.choice([T_ROCK, T_TREE, T_DIRT])
            for y in range(max(0, cy - r), min(self.rows, cy + r)):
                for x in range(max(0, cx - r), min(self.cols, cx + r)):
                    if (x - cx) ** 2 + (y - cy) ** 2 <= r * r and random.random() < 0.75:
                        self.tiles[y][x] = t

        # 生成铁矿脉
        for _ in range(8):
            cx, cy = random.randint(0, self.cols - 1), random.randint(0, self.rows - 1)
            for y in range(max(0, cy - 1), min(self.rows, cy + 2)):  # 范围从 5 改成了 3x3 的区域
                for x in range(max(0, cx - 1), min(self.cols, cx + 2)):
                    if (x - cx) ** 2 + (y - cy) ** 2 <= 2 and random.random() < 0.7:  # 密集度略微降低
                        self.tiles[y][x] = T_IRON_ROCK

        # 河流
        river_y = self.rows // 2
        for x in range(self.cols):
            off = int(3 * math.sin(x * 0.15))
            for dy in range(-1, 2):
                yy = river_y + off + dy
                if 0 <= yy < self.rows: self.tiles[yy][x] = T_WATER

        # 【修复】出生点清空，并恢复浆果和树木的生成！
        spawn_cx, spawn_cy = self.cols // 2, self.rows // 2 - 5
        for y in range(max(0, spawn_cy - 8), min(self.rows, spawn_cy + 9)):
            for x in range(max(0, spawn_cx - 8), min(self.cols, spawn_cx + 9)):
                if (x - spawn_cx) ** 2 + (y - spawn_cy) ** 2 <= 64:
                    if random.random() < 0.1:
                        self.tiles[y][x] = T_TREE
                    elif random.random() < 0.15:
                        self.tiles[y][x] = T_BERRY
                    else:
                        self.tiles[y][x] = T_GRASS

    def get(self, tx, ty):
        return self.tiles[ty][tx] if 0 <= tx < self.cols and 0 <= ty < self.rows else None

    def is_terrain_walkable(self, tx, ty):
        return self.get(tx, ty) in WALKABLE

    def is_walkable(self, tx, ty):
        return self.buildings.is_walkable(self, tx, ty) if self.buildings else self.is_terrain_walkable(tx, ty)

    def is_harvestable(self, tx, ty):
        return self.get(tx, ty) in HARVESTABLE

    def damage_resource(self, tx, ty, amount):
        if not self.is_harvestable(tx, ty): return False, None, 0
        key = (tx, ty)
        if key not in self.resource_hp: return False, None, 0
        self.resource_hp[key] -= amount
        if self.resource_hp[key] <= 0:
            t = self.tiles[ty][tx]
            if t == T_ROCK:
                self.tiles[ty][tx] = T_DIRT; drop = ("stone", 5)
            elif t == T_IRON_ROCK:
                self.tiles[ty][tx] = T_DIRT; drop = ("iron_ore", 3)
            elif t == T_TREE:
                self.tiles[ty][tx] = T_GRASS; drop = ("wood", 5)
            elif t == T_BERRY:
                self.tiles[ty][tx] = T_GRASS; drop = ("food", 3)
            else:
                drop = (None, 0)
            del self.resource_hp[key]
            return True, drop[0], drop[1]
        return False, None, 0

    def draw(self, surface, camera):
        start_c, end_c = max(0, int(camera.x // TILE_SIZE)), min(self.cols,
                                                                 int((camera.x + camera.vw) // TILE_SIZE) + 2)
        start_r, end_r = max(0, int(camera.y // TILE_SIZE)), min(self.rows,
                                                                 int((camera.y + camera.vh) // TILE_SIZE) + 2)

        for r in range(start_r, end_r):
            for c in range(start_c, end_c):
                sx, sy = camera.world_to_screen(c * TILE_SIZE, r * TILE_SIZE)
                t = self.tiles[r][c]

                # 恢复精细绘制
                if t == T_GRASS:
                    pygame.draw.rect(surface, GRASS if (r + c) % 2 == 0 else GRASS2, (sx, sy, TILE_SIZE, TILE_SIZE))
                elif t == T_DIRT:
                    pygame.draw.rect(surface, DIRT, (sx, sy, TILE_SIZE, TILE_SIZE))
                elif t == T_ROCK:
                    pygame.draw.rect(surface, DIRT, (sx, sy, TILE_SIZE, TILE_SIZE))
                    pygame.draw.rect(surface, ROCK, (sx + 3, sy + 3, TILE_SIZE - 6, TILE_SIZE - 6), border_radius=4)
                elif t == T_IRON_ROCK:
                    pygame.draw.rect(surface, DIRT, (sx, sy, TILE_SIZE, TILE_SIZE))
                    pygame.draw.rect(surface, (120, 100, 110), (sx + 3, sy + 3, TILE_SIZE - 6, TILE_SIZE - 6),
                                     border_radius=4)
                    pygame.draw.circle(surface, (180, 100, 80), (int(sx + 10), int(sy + 10)), 3)
                    pygame.draw.circle(surface, (180, 100, 80), (int(sx + 20), int(sy + 18)), 4)
                elif t == T_WATER:
                    pygame.draw.rect(surface, WATER, (sx, sy, TILE_SIZE, TILE_SIZE))
                elif t == T_TREE:
                    pygame.draw.rect(surface, GRASS, (sx, sy, TILE_SIZE, TILE_SIZE))
                    pygame.draw.circle(surface, TREE, (int(sx + TILE_SIZE / 2), int(sy + TILE_SIZE / 2)),
                                       TILE_SIZE // 2 - 3)
                elif t == T_BERRY:
                    pygame.draw.rect(surface, GRASS, (sx, sy, TILE_SIZE, TILE_SIZE))
                    cx_px, cy_px = int(sx + TILE_SIZE / 2), int(sy + TILE_SIZE / 2)
                    pygame.draw.circle(surface, (40, 100, 40), (cx_px, cy_px), TILE_SIZE // 3)
                    for i in range(4):
                        a = i * 1.57
                        pygame.draw.circle(surface, (220, 60, 60),
                                           (cx_px + int(math.cos(a) * 6), cy_px + int(math.sin(a) * 6)), 2)

                key = (c, r)
                if key in self.resource_hp:
                    hp, max_hp = self.resource_hp[key], {T_ROCK: 100, T_IRON_ROCK: 150, T_TREE: 60, T_BERRY: 30}.get(t,
                                                                                                                     100)
                    if hp < max_hp and hp > 0:
                        pygame.draw.rect(surface, (40, 40, 40), (sx + 2, sy + TILE_SIZE - 6, TILE_SIZE - 4, 3))
                        pygame.draw.rect(surface, (255, 200, 60),
                                         (sx + 2, sy + TILE_SIZE - 6, int((TILE_SIZE - 4) * (hp / max_hp)), 3))