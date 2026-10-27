# entities/enemy.py
import pygame
import math
import random
from settings import TILE_SIZE
from core.pathfinding import astar
from combat.weapons import get_weapon


class EnemyPathWorld:
    def __init__(self, real_world, buildings):
        self.w = real_world
        self.b = buildings

    def is_walkable(self, tx, ty):
        b = self.b.get_building_at(tx, ty)
        if b and b.kind == "door": return False
        return self.w.is_walkable(tx, ty)

    def get(self, tx, ty):
        return self.w.get(tx, ty)


class Enemy:
    _id_counter = 0

    def __init__(self, tx, ty, weapon_key=None):
        Enemy._id_counter += 1
        self.id = Enemy._id_counter
        self.x = tx * TILE_SIZE + TILE_SIZE / 2
        self.y = ty * TILE_SIZE + TILE_SIZE / 2
        self.name = f"敌人{self.id}"
        self.hp = 60
        self.max_hp = 60
        self.speed = 3.0 * TILE_SIZE
        self.radius = TILE_SIZE // 2 - 4
        self.color = (200, 60, 60)

        # 随机武器
        if weapon_key is None:
            weapon_key = random.choice(["knife", "pistol", "smg"])
        self.weapon_key = weapon_key
        w = get_weapon(weapon_key)
        self.attack_range = w["range"] * TILE_SIZE
        self.attack_damage = w["damage"]
        self.attack_cooldown = w["cooldown"]
        self.cooldown_timer = 0.0

        self.path = []
        self.target = None
        self.target_building = None
        self.path_recalc_timer = 0.0
        self.path_recalc_interval = 0.6
        self.hit_flash = 0.0
        self.recent_shot = None

    def get_weapon_def(self):
        return get_weapon(self.weapon_key)

    def current_tile(self):
        return int(self.x // TILE_SIZE), int(self.y // TILE_SIZE)

    def take_damage(self, amount, attacker=None):
        self.hp -= amount
        self.hit_flash = 0.15
        if attacker is not None: self.target = attacker
        return self.hp <= 0

    def update(self, dt, world, colonists, buildings):
        self.cooldown_timer = max(0, self.cooldown_timer - dt)
        self.hit_flash = max(0, self.hit_flash - dt)
        self.path_recalc_timer -= dt

        alive = [c for c in colonists if c.hp > 0]
        if not alive:
            self.target = None
        else:
            if self.target not in alive:
                self.target = min(alive, key=lambda c: (c.x - self.x) ** 2 + (c.y - self.y) ** 2)

        if self.target_building is not None:
            b = self.target_building
            if b.hp <= 0 or buildings.get_building_at(b.tx, b.ty) != b:
                self.target_building = None
            else:
                d = ((b.tx * TILE_SIZE + TILE_SIZE / 2 - self.x) ** 2 + (
                            b.ty * TILE_SIZE + TILE_SIZE / 2 - self.y) ** 2) ** 0.5
                if d <= self.attack_range:
                    self.path = []
                    if self.cooldown_timer <= 0:
                        b.take_damage(self.attack_damage)
                        self.cooldown_timer = self.attack_cooldown
                        self.recent_shot = ("melee", self.x, self.y, b.tx * TILE_SIZE + TILE_SIZE / 2,
                                            b.ty * TILE_SIZE + TILE_SIZE / 2, (255, 120, 120))
                        if b.hp <= 0:
                            buildings.remove_building(b.tx, b.ty, b.layer)
                            self.target_building = None
                    return
                else:
                    if self.path_recalc_timer <= 0 and not self.path:
                        self.path_recalc_timer = self.path_recalc_interval
                        p = astar(world, self.current_tile(), (b.tx, b.ty))
                        if p is not None: self.path = p

        elif self.target is not None:
            t = self.target
            d = ((t.x - self.x) ** 2 + (t.y - self.y) ** 2) ** 0.5
            if d <= self.attack_range:
                self.path = []
                if self.cooldown_timer <= 0:
                    wdef = self.get_weapon_def()
                    if wdef["melee"]:
                        self.recent_shot = ("melee", self.x, self.y, t.x, t.y, (255, 120, 120))
                    else:
                        # 远程特效
                        self.recent_shot = ("shot", self.x, self.y, t.x, t.y, (255, 120, 120))
                    t.take_damage(self.attack_damage, attacker=self)
                    self.cooldown_timer = self.attack_cooldown
                return

            if self.path_recalc_timer <= 0:
                self.path_recalc_timer = self.path_recalc_interval
                enemy_world = EnemyPathWorld(world, buildings)
                t_tile = t.current_tile()

                best = None
                for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                    nx, ny = t_tile[0] + dx, t_tile[1] + dy
                    if enemy_world.is_walkable(nx, ny):
                        best = (nx, ny)
                        break

                if best:
                    p = astar(enemy_world, self.current_tile(), best)
                    if p is not None:
                        self.path = p
                    else:
                        door_pos = buildings.find_nearest_door(self.current_tile()[0], self.current_tile()[1])
                        if door_pos:
                            self.target_building = buildings.buildings.get((door_pos[0], door_pos[1], 1))
                        else:
                            self.path = []

        if self.path:
            target_tx, target_ty = self.path[0]
            tgx = target_tx * TILE_SIZE + TILE_SIZE / 2
            tgy = target_ty * TILE_SIZE + TILE_SIZE / 2
            dx = tgx - self.x
            dy = tgy - self.y
            dist = (dx * dx + dy * dy) ** 0.5
            step = self.speed * dt
            if dist <= step:
                self.x = tgx
                self.y = tgy
                self.path.pop(0)
            else:
                self.x += dx / dist * step
                self.y += dy / dist * step

    def draw(self, surface, camera, font):
        sx, sy = camera.world_to_screen(self.x, self.y)
        color = (255, 200, 100) if self.hit_flash > 0 else self.color
        pygame.draw.circle(surface, color, (int(sx), int(sy)), self.radius)
        pygame.draw.circle(surface, (0, 0, 0), (int(sx), int(sy)), self.radius, 2)

        bw = self.radius * 2
        bh = 4
        hx = int(sx - self.radius)
        hy = int(sy - self.radius - 10)
        pygame.draw.rect(surface, (60, 0, 0), (hx, hy, bw, bh))
        pygame.draw.rect(surface, (220, 60, 60), (hx, hy, int(bw * self.hp / self.max_hp), bh))

        # 名字后面带上武器名
        wname = self.get_weapon_def()["name"]
        name_surf = font.render(f"{self.name}({wname})", True, (255, 200, 200))
        surface.blit(name_surf, (sx - name_surf.get_width() / 2, sy + self.radius + 2))