# entities/enemy.py
import pygame
import math
import random
from settings import TILE_SIZE, WHITE
from core.pathfinding import astar
from world.buildings import BUILDING_DEFS
from combat.weapons import get_weapon
from combat.weapon_render import draw_weapon


class Enemy:
    _id_counter = 0

    def __init__(self, tx, ty, weapon_key=None):
        Enemy._id_counter += 1
        self.id = Enemy._id_counter
        self.x, self.y = tx * TILE_SIZE + TILE_SIZE / 2, ty * TILE_SIZE + TILE_SIZE / 2
        self.name = f"敌人{self.id}"
        # 削弱：血量 80 -> 50
        self.hp, self.max_hp = 50, 50
        # 削弱：速度 3.0 -> 2.4（比小人 3.5 慢，能追上但不容易突脸）
        self.speed = 2.4 * TILE_SIZE
        self.radius = TILE_SIZE // 2 - 4

        # 默认用冷兵器
        if weapon_key is None:
            weapon_key = random.choice(["club", "spear", "longsword", "fist"])
        self.weapon_key = weapon_key
        w = get_weapon(weapon_key)
        self.attack_range = w["range"] * TILE_SIZE
        # 削弱：攻击力打 7 折，冷却延长 40%
        self.attack_damage = w["damage"] * 0.7
        self.attack_cooldown = w["cooldown"] * 1.4
        self.cooldown_timer = 0.0

        self.path = []
        self.target_enemy = None
        self.target_building = None
        self.hit_flash = 0.0
        self.facing_angle = 0.0
        self.recent_shot = None

    def current_tile(self):
        return int(self.x // TILE_SIZE), int(self.y // TILE_SIZE)

    def take_damage(self, amount, attacker=None):
        self.hp -= amount
        self.hit_flash = 0.15
        if attacker is not None and self.target_enemy is None:
            self.target_enemy = attacker
        return self.hp <= 0

    def update(self, dt, world, colonists, buildings):
        self.cooldown_timer = max(0, self.cooldown_timer - dt)
        self.hit_flash = max(0, self.hit_flash - dt)
        if self.hp <= 0: return

        if self.target_enemy is None or self.target_enemy.hp <= 0:
            alive_colonists = [c for c in colonists if c.hp > 0]
            if alive_colonists:
                self.target_enemy = min(alive_colonists, key=lambda c: (c.x - self.x) ** 2 + (c.y - self.y) ** 2)
            else:
                self.target_enemy = None

        if self.target_enemy is not None:
            e = self.target_enemy
            dx, dy = e.x - self.x, e.y - self.y
            self.facing_angle = math.atan2(dy, dx)
            d = (dx ** 2 + dy ** 2) ** 0.5

            if d <= self.attack_range:
                self.path = []
                if self.cooldown_timer <= 0:
                    wdef = get_weapon(self.weapon_key)
                    if wdef["melee"]:
                        self.recent_shot = ("melee", self.x, self.y, e.x, e.y, wdef["color"])
                    else:
                        mx, my = self.x + math.cos(self.facing_angle) * (self.radius + 12), self.y + math.sin(
                            self.facing_angle) * (self.radius + 12)
                        self.recent_shot = ("shot", mx, my, e.x, e.y, wdef["color"])
                    e.take_damage(self.attack_damage, attacker=self)
                    self.cooldown_timer = self.attack_cooldown
                return

            # 如果不在攻击范围，且没有路，重新寻路
            if not self.path:
                adj = self._find_adjacent(world, self.current_tile(), *e.current_tile())
                if adj:
                    p = astar(world, self.current_tile(), adj)
                    if p: self.path = p

                # 【防卡死】如果找不到去殖民者的路，就砸最近的门或墙
                if not self.path:
                    candidates = [b for b in buildings.buildings.values() if
                                  b.kind in ("wall", "window", "door") and not b.marked_for_deconstruction]
                    if candidates:
                        self.target_building = min(candidates, key=lambda b: (b.tx - self.x / TILE_SIZE) ** 2 + (
                                    b.ty - self.y / TILE_SIZE) ** 2)

        # 处理砸墙
        if self.target_building is not None and (not self.path or self.target_enemy is None):
            b = self.target_building
            adj = self._find_adjacent(world, self.current_tile(), b.tx, b.ty)
            if adj:
                dist_sq = (adj[0] * TILE_SIZE + TILE_SIZE / 2 - self.x) ** 2 + (
                            adj[1] * TILE_SIZE + TILE_SIZE / 2 - self.y) ** 2
                if dist_sq <= (self.attack_range) ** 2:
                    self.path = []
                    if self.cooldown_timer <= 0:
                        wdef = get_weapon(self.weapon_key)
                        self.recent_shot = ("melee", self.x, self.y, b.tx * TILE_SIZE + TILE_SIZE / 2,
                                            b.ty * TILE_SIZE + TILE_SIZE / 2, wdef["color"])
                        dead = b.take_damage(self.attack_damage)
                        self.cooldown_timer = self.attack_cooldown
                        if dead:
                            buildings.remove_building(b.tx, b.ty, b.layer)
                            self.target_building = None
                    return
                elif not self.path:
                    p = astar(world, self.current_tile(), adj)
                    if p: self.path = p
            else:
                self.target_building = None

        # 移动逻辑
        if self.path:
            target_tx, target_ty = self.path[0]
            tgx, tgy = target_tx * TILE_SIZE + TILE_SIZE / 2, target_ty * TILE_SIZE + TILE_SIZE / 2
            dx, dy = tgx - self.x, tgy - self.y
            dist = (dx ** 2 + dy ** 2) ** 0.5
            step = self.speed * dt
            if dist > 0.001: self.facing_angle = math.atan2(dy, dx)
            if dist <= step:
                self.x, self.y = tgx, tgy
                self.path.pop(0)
            else:
                self.x += dx / dist * step
                self.y += dy / dist * step
        else:
            # 【新增】防卡死：如果既没路又不动，强制重置目标
            self.target_enemy = None
            self.path = []

    def _find_adjacent(self, world, start, tx, ty):
        cands = [(tx + dx, ty + dy) for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
                 if world.is_walkable(tx + dx, ty + dy)]
        if not cands: return None
        return min(cands, key=lambda c: abs(c[0] - start[0]) + abs(c[1] - start[1]))

    def draw(self, surface, camera, font):
        if self.hp <= 0: return
        sx, sy = camera.world_to_screen(self.x, self.y)
        draw_weapon(surface, sx, sy, self.facing_angle, get_weapon(self.weapon_key), 1.0)
        pygame.draw.circle(surface, (255, 100, 100) if self.hit_flash > 0 else (200, 50, 50), (int(sx), int(sy)),
                           self.radius)
        pygame.draw.circle(surface, (0, 0, 0), (int(sx), int(sy)), self.radius, 2)
        pygame.draw.rect(surface, (60, 0, 0), (int(sx - self.radius), int(sy - self.radius - 10), self.radius * 2, 4))
        pygame.draw.rect(surface, (220, 60, 60), (int(sx - self.radius), int(sy - self.radius - 10),
                                                  int((self.radius * 2) * (self.hp / self.max_hp)), 4))
        surface.blit(font.render(self.name, True, WHITE), (sx - font.size(self.name)[0] / 2, sy + self.radius + 2))