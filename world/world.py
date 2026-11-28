# world/world.py
import pygame
import math
from settings import *
from core import textures

T_GRASS, T_DIRT, T_ROCK, T_WATER, T_TREE, T_BERRY, T_IRON_ROCK, T_METEOR = 0, 1, 2, 3, 4, 5, 6, 7
WALKABLE = {T_GRASS, T_DIRT}
HARVESTABLE = {T_ROCK, T_TREE, T_BERRY, T_IRON_ROCK, T_METEOR}
RESOURCE_MAX_HP = {T_ROCK: 100, T_IRON_ROCK: 150, T_TREE: 60, T_BERRY: 30, T_METEOR: 180}


def _tile_tex(t, c, r):
    if t == T_GRASS: return textures.tile_variant("grass", 4, c, r)
    if t == T_DIRT: return textures.tile_variant("dirt", 2, c, r)
    if t == T_WATER: return textures.get(f"water_{(pygame.time.get_ticks() // 700) % 2}")
    if t == T_ROCK: return textures.get("rock")
    if t == T_IRON_ROCK: return textures.get("iron_rock")
    if t == T_METEOR: return textures.get("meteor")
    if t == T_TREE: return textures.tile_variant("tree", 3, c, r)
    if t == T_BERRY: return textures.get("berry")
    return None


class World:
    def __init__(self, cols, rows, rng):
        # rng：专用于地形生成的 random.Random 实例（由 GameWorld 按种子创建），
        # 不再使用全局 random，也不再 random.seed(7) 污染全局随机流。
        self.cols, self.rows = cols, rows
        self.rng = rng
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
        rng = self.rng
        # 随机地形和树、石头
        area = (self.cols * self.rows) / 4800.0      # 以 80x60 为基准按面积放大地物数量
        for _ in range(int(120 * area)):
            cx, cy = rng.randint(0, self.cols - 1), rng.randint(0, self.rows - 1)
            r, t = rng.randint(2, 5), rng.choice([T_ROCK, T_TREE, T_DIRT])
            for y in range(max(0, cy - r), min(self.rows, cy + r)):
                for x in range(max(0, cx - r), min(self.cols, cx + r)):
                    if (x - cx) ** 2 + (y - cy) ** 2 <= r * r and rng.random() < 0.75:
                        self.tiles[y][x] = t

        # 生成铁矿脉
        for _ in range(int(8 * area)):
            cx, cy = rng.randint(0, self.cols - 1), rng.randint(0, self.rows - 1)
            for y in range(max(0, cy - 1), min(self.rows, cy + 2)):  # 范围从 5 改成了 3x3 的区域
                for x in range(max(0, cx - 1), min(self.cols, cx + 2)):
                    if (x - cx) ** 2 + (y - cy) ** 2 <= 2 and rng.random() < 0.7:  # 密集度略微降低
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
                    if rng.random() < 0.1:
                        self.tiles[y][x] = T_TREE
                    elif rng.random() < 0.15:
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
            elif t == T_METEOR:
                self.tiles[ty][tx] = T_DIRT; drop = ("iron_ore", 4)      # 另有 3 石头由采集者掉落
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

                # 优先用贴图（assets/textures）；没有贴图时回退到下面的程序化画法
                tex = _tile_tex(t, c, r)
                if tex is not None:
                    surface.blit(tex, (sx, sy))
                elif t == T_GRASS:
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
                elif t == T_METEOR:
                    pygame.draw.rect(surface, DIRT, (sx, sy, TILE_SIZE, TILE_SIZE))
                    pygame.draw.rect(surface, (60, 55, 65), (sx + 2, sy + 4, TILE_SIZE - 5, TILE_SIZE - 8), border_radius=7)
                    pygame.draw.circle(surface, (200, 110, 60), (int(sx + 11), int(sy + 12)), 3)
                    pygame.draw.circle(surface, (230, 150, 70), (int(sx + 21), int(sy + 19)), 2)
                    pygame.draw.circle(surface, (150, 150, 160), (int(sx + 17), int(sy + 9)), 2)
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
                    hp, max_hp = self.resource_hp[key], RESOURCE_MAX_HP.get(t, 100)
                    if hp < max_hp and hp > 0:
                        pygame.draw.rect(surface, (40, 40, 40), (sx + 2, sy + TILE_SIZE - 6, TILE_SIZE - 4, 3))
                        pygame.draw.rect(surface, (255, 200, 60),
                                         (sx + 2, sy + TILE_SIZE - 6, int((TILE_SIZE - 4) * (hp / max_hp)), 3))