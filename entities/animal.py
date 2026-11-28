# entities/animal.py
import pygame
from core import textures
from settings import TILE_SIZE
from core.pathfinding import astar


# 物种表：数值 + 掉落。新增物种只需在这里加一行并在 draw 里补外形
SPECIES = {
    "rabbit":  {"name": "兔子",   "hp": 20, "speed": 3.5, "radius": 1 / 3, "color": (240, 230, 220), "meat": 3},
    "deer":    {"name": "鹿",     "hp": 40, "speed": 4.0, "radius": 0.5 - 2 / TILE_SIZE, "color": (170, 100, 60), "meat": 5, "extra": {"leather": 3}},
    "chicken": {"name": "山鸡",   "hp": 10, "speed": 3.0, "radius": 0.28, "color": (200, 150, 90), "meat": 2, "extra": {"feather": 2}},
    "sheep":   {"name": "绵羊",   "hp": 32, "speed": 2.4, "radius": 0.42, "color": (235, 235, 225), "meat": 4, "extra": {"wool": 3}},
    "fox":     {"name": "狐狸",   "hp": 24, "speed": 4.6, "radius": 0.33, "color": (225, 120, 40), "meat": 2, "extra": {"leather": 2}},
    "boar":    {"name": "野猪",   "hp": 60, "speed": 3.3, "radius": 0.45, "color": (95, 70, 55), "meat": 7, "extra": {"leather": 2}, "bite": 6},
}
SPAWN_POOL = ["rabbit", "rabbit", "deer", "deer", "chicken", "chicken", "sheep", "sheep", "fox", "boar"]


def pick_species(rng):
    return rng.choice(SPAWN_POOL)


class Animal:
    def __init__(self, tx, ty, species="rabbit", *, ctx):
        self.ctx = ctx
        self.id = ctx.next_id()
        self.species = species
        self.x = tx * TILE_SIZE + TILE_SIZE / 2
        self.y = ty * TILE_SIZE + TILE_SIZE / 2

        sp = SPECIES.get(species, SPECIES["rabbit"])
        self.name, self.hp, self.max_hp = sp["name"], sp["hp"], sp["hp"]
        self.speed = sp["speed"] * TILE_SIZE
        self.radius = int(sp["radius"] * TILE_SIZE)
        self.color = sp["color"]
        self.drop_item, self.drop_amount = "meat", sp["meat"]
        self.extra_drops = dict(sp.get("extra", {}))      # 例如 {"leather": 2}
        self.bite = sp.get("bite", 0)                     # >0：被打后会反击
        self.bite_cd = 0.0
        self.revenge = 0.0

        self.path = []
        # 实体私有随机流：由世界种子和实体 id 派生，别处增减随机调用不会打乱它
        self.rng = ctx.entity_rng(self.id)
        self.idle_timer = self.rng.uniform(1.0, 3.0)
        self.hit_flash = 0.0
        self.fleeing_timer = 0.0

    def current_tile(self):
        return int(self.x // TILE_SIZE), int(self.y // TILE_SIZE)

    def take_damage(self, amount, attacker=None):
        self.hp -= amount
        self.hit_flash = 0.15
        self.fleeing_timer = 5.0
        self.path = []
        if self.bite > 0 and self.hp > 0:
            self.revenge = 6.0                  # 野猪：挨打后 6 秒内反击
            self.fleeing_timer = 0.0
        return self.hp <= 0

    def update(self, dt, world, colonists):
        self.hit_flash = max(0, self.hit_flash - dt)
        if self.hp <= 0: return

        if self.revenge > 0:
            self._revenge_step(dt, world, colonists)
            return
        for c in colonists:
            if c.hp <= 0: continue
            d = ((c.x - self.x) ** 2 + (c.y - self.y) ** 2) ** 0.5
            if d < 5 * TILE_SIZE and self.bite <= 0:
                self.fleeing_timer = max(self.fleeing_timer, 1.0)

        if self.fleeing_timer > 0:
            self.fleeing_timer -= dt
            if not self.path and self.rng.random() < 0.1:
                cx, cy = self.current_tile()
                dx, dy = self.rng.choice([(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)])
                target = (cx + dx * 10, cy + dy * 10)
                p = astar(world, (cx, cy), target, max_iter=500)
                if p: self.path = p
        else:
            self.idle_timer -= dt
            if self.idle_timer <= 0 and not self.path:
                self.idle_timer = self.rng.uniform(2.0, 5.0)
                cx, cy = self.current_tile()
                dx, dy = self.rng.choice([(-2, 0), (2, 0), (0, -2), (0, 2)])
                p = astar(world, (cx, cy), (cx + dx, cy + dy), max_iter=100)
                if p: self.path = p

        if self.path:
            target_tx, target_ty = self.path[0]
            tgx = target_tx * TILE_SIZE + TILE_SIZE / 2
            tgy = target_ty * TILE_SIZE + TILE_SIZE / 2
            dx, dy = tgx - self.x, tgy - self.y
            dist = (dx * dx + dy * dy) ** 0.5
            step = self.speed * dt
            if dist <= step:
                self.x, self.y = tgx, tgy
                self.path.pop(0)
            else:
                self.x += dx / dist * step
                self.y += dy / dist * step

    def _draw_new(self, surface, sx, sy, col, outline, right):
        f = 1 if right else -1
        sp = self.species
        if sp == "chicken":
            pygame.draw.ellipse(surface, col, (sx - 8, sy - 5, 16, 12)); pygame.draw.ellipse(surface, outline, (sx - 8, sy - 5, 16, 12), 1)
            pygame.draw.circle(surface, col, (int(sx + 8 * f), int(sy - 8)), 4)
            pygame.draw.polygon(surface, (240, 190, 50), [(sx + 11 * f, sy - 9), (sx + 15 * f, sy - 7), (sx + 11 * f, sy - 6)])
            pygame.draw.circle(surface, (220, 40, 40), (int(sx + 8 * f), int(sy - 12)), 2)
            pygame.draw.line(surface, (240, 190, 50), (sx - 2, sy + 7), (sx - 2, sy + 12), 2)
            pygame.draw.line(surface, (240, 190, 50), (sx + 3, sy + 7), (sx + 3, sy + 12), 2)
        elif sp == "sheep":
            for ox, oy in ((-8, -4), (0, -7), (8, -4), (-6, 3), (4, 3)):
                pygame.draw.circle(surface, col, (int(sx + ox), int(sy + oy)), 7)
            pygame.draw.circle(surface, (60, 55, 55), (int(sx + 13 * f), int(sy - 2)), 5)
            for ox in (-6, 5):
                pygame.draw.line(surface, (60, 55, 55), (sx + ox, sy + 8), (sx + ox, sy + 15), 3)
        elif sp == "fox":
            pygame.draw.ellipse(surface, col, (sx - 11, sy - 5, 22, 11)); pygame.draw.ellipse(surface, outline, (sx - 11, sy - 5, 22, 11), 1)
            pygame.draw.polygon(surface, col, [(sx + 9 * f, sy - 9), (sx + 17 * f, sy - 2), (sx + 9 * f, sy + 2)])
            pygame.draw.polygon(surface, (245, 245, 240), [(sx - 11 * f, sy - 2), (sx - 20 * f, sy - 8), (sx - 18 * f, sy + 3)])
            pygame.draw.circle(surface, (20, 20, 20), (int(sx + 14 * f), int(sy - 2)), 1)
        else:   # boar
            pygame.draw.ellipse(surface, col, (sx - 14, sy - 9, 28, 18)); pygame.draw.ellipse(surface, outline, (sx - 14, sy - 9, 28, 18), 1)
            pygame.draw.circle(surface, col, (int(sx + 14 * f), int(sy - 1)), 7)
            pygame.draw.line(surface, (235, 230, 200), (sx + 18 * f, sy + 1), (sx + 21 * f, sy - 4), 2)
            for ox in (-9, -3, 4, 10):
                pygame.draw.line(surface, (60, 45, 35), (sx + ox, sy + 7), (sx + ox, sy + 14), 3)
            if self.revenge > 0:
                pygame.draw.circle(surface, (255, 60, 60), (int(sx + 15 * f), int(sy - 5)), 2)

    def _revenge_step(self, dt, world, colonists):
        """被打的野猪冲向最近的小人并撕咬。"""
        self.revenge -= dt
        self.bite_cd = max(0.0, self.bite_cd - dt)
        best, bd = None, 1e18
        for c in colonists:
            if c.hp <= 0: continue
            d = (c.x - self.x) ** 2 + (c.y - self.y) ** 2
            if d < bd: best, bd = c, d
        if best is None or bd > (9 * TILE_SIZE) ** 2:
            self.revenge = 0.0
            return
        if bd <= (TILE_SIZE * 1.1) ** 2:
            self.path = []
            if self.bite_cd <= 0:
                self.bite_cd = 1.5
                best.take_damage(self.bite, self)
            return
        if not self.path or self.rng.random() < 0.05:
            p = astar(world, self.current_tile(), best.current_tile(), max_iter=300)
            if p: self.path = p[:6]
        self._follow_path(dt)

    def _follow_path(self, dt):
        if self.path:
            target_tx, target_ty = self.path[0]
            tgx = target_tx * TILE_SIZE + TILE_SIZE / 2
            tgy = target_ty * TILE_SIZE + TILE_SIZE / 2
            dx, dy = tgx - self.x, tgy - self.y
            dist = (dx * dx + dy * dy) ** 0.5
            step = self.speed * dt
            if dist <= step:
                self.x, self.y = tgx, tgy
                self.path.pop(0)
            else:
                self.x += dx / dist * step
                self.y += dy / dist * step

    def draw(self, surface, camera, font):
        if self.hp <= 0: return
        sx, sy = camera.world_to_screen(self.x, self.y)

        if self.hit_flash > 0:
            body_color = (255, 200, 200)
            outline_col = (255, 0, 0)
        else:
            body_color = self.color
            outline_col = (0, 0, 0)

        facing_right = True
        if self.path:
            target_tx, _ = self.path[0]
            if target_tx * TILE_SIZE + TILE_SIZE / 2 < self.x: facing_right = False

        tex = textures.animal(self.species, facing_right, self.hit_flash > 0)
        if tex is not None:
            surface.blit(tex, (int(sx - tex.get_width() / 2), int(sy - 24)))
        elif self.species == "rabbit":
            body_rect = (sx - 10, sy - 6, 20, 14)
            pygame.draw.ellipse(surface, body_color, body_rect)
            pygame.draw.ellipse(surface, outline_col, body_rect, 1)

            ear_offset = 4 if facing_right else -4
            pygame.draw.ellipse(surface, body_color, (sx + ear_offset - 3, sy - 16, 4, 12))
            pygame.draw.ellipse(surface, (255, 180, 180), (sx + ear_offset - 2, sy - 14, 2, 8))
            pygame.draw.ellipse(surface, body_color, (sx + ear_offset + 2, sy - 14, 4, 10))
            pygame.draw.ellipse(surface, (255, 180, 180), (sx + ear_offset + 3, sy - 12, 2, 6))

            tail_x = sx - 12 if facing_right else sx + 12
            pygame.draw.circle(surface, (255, 255, 255), (int(tail_x), int(sy + 2)), 3)

            eye_x = sx + 6 if facing_right else sx - 6
            pygame.draw.circle(surface, (220, 50, 50), (int(eye_x), int(sy - 4)), 2)

        elif self.species in ("chicken", "fox", "sheep", "boar"):
            self._draw_new(surface, sx, sy, body_color, outline_col, facing_right)

        else:
            pygame.draw.line(surface, (100, 60, 30), (sx - 8, sy + 6), (sx - 8, sy + 16), 3)
            pygame.draw.line(surface, (100, 60, 30), (sx - 2, sy + 6), (sx - 2, sy + 16), 3)
            pygame.draw.line(surface, (100, 60, 30), (sx + 4, sy + 6), (sx + 4, sy + 16), 3)
            pygame.draw.line(surface, (100, 60, 30), (sx + 10, sy + 6), (sx + 10, sy + 16), 3)

            body_rect = (sx - 14, sy - 8, 28, 16)
            pygame.draw.ellipse(surface, body_color, body_rect)
            pygame.draw.ellipse(surface, outline_col, body_rect, 1)

            head_x = sx + 14 if facing_right else sx - 14
            pygame.draw.line(surface, body_color, (sx, sy - 6), (head_x, sy - 14), 6)
            pygame.draw.circle(surface, body_color, (int(head_x), int(sy - 14)), 6)
            pygame.draw.circle(surface, outline_col, (int(head_x), int(sy - 14)), 6, 1)

            horn_x = head_x
            horn_y = sy - 18
            pygame.draw.line(surface, (220, 200, 150), (horn_x, horn_y), (horn_x - 6, horn_y - 12), 2)
            pygame.draw.line(surface, (220, 200, 150), (horn_x, horn_y), (horn_x + 6, horn_y - 12), 2)
            pygame.draw.line(surface, (220, 200, 150), (horn_x - 6, horn_y - 12), (horn_x - 10, horn_y - 10), 2)
            pygame.draw.line(surface, (220, 200, 150), (horn_x + 6, horn_y - 12), (horn_x + 10, horn_y - 10), 2)

            eye_x = head_x + (2 if facing_right else -2)
            pygame.draw.circle(surface, (0, 0, 0), (int(eye_x), int(sy - 15)), 1.5)

        if self.hp < self.max_hp:
            bw, bh = 24, 3
            hx, hy = int(sx - 12), int(sy - 24)
            pygame.draw.rect(surface, (60, 0, 0), (hx, hy, bw, bh))
            pygame.draw.rect(surface, (220, 60, 60), (hx, hy, int(bw * self.hp / self.max_hp), bh))

        name_surf = font.render(self.name, True, (220, 220, 220))
        surface.blit(name_surf, (sx - name_surf.get_width() / 2, sy + 18))