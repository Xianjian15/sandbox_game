# entities/animal.py
import pygame
import random
from settings import TILE_SIZE
from core.pathfinding import astar


class Animal:
    _id_counter = 0

    def __init__(self, tx, ty, species="rabbit"):
        Animal._id_counter += 1
        self.id = Animal._id_counter
        self.species = species
        self.x = tx * TILE_SIZE + TILE_SIZE / 2
        self.y = ty * TILE_SIZE + TILE_SIZE / 2

        if species == "rabbit":
            self.name = "兔子"
            self.hp = 20
            self.max_hp = 20
            self.speed = 3.5 * TILE_SIZE
            self.radius = TILE_SIZE // 3
            self.color = (240, 230, 220)
            self.drop_item = "meat"
            self.drop_amount = 3  # 提高掉落量
        else:
            self.name = "鹿"
            self.hp = 40
            self.max_hp = 40
            self.speed = 4.0 * TILE_SIZE
            self.radius = TILE_SIZE // 2 - 2
            self.color = (170, 100, 60)
            self.drop_item = "meat"
            self.drop_amount = 5  # 提高掉落量

        self.path = []
        self.idle_timer = random.uniform(1.0, 3.0)
        self.hit_flash = 0.0
        self.fleeing_timer = 0.0

    def current_tile(self):
        return int(self.x // TILE_SIZE), int(self.y // TILE_SIZE)

    def take_damage(self, amount, attacker=None):
        self.hp -= amount
        self.hit_flash = 0.15
        self.fleeing_timer = 5.0
        self.path = []
        return self.hp <= 0

    def update(self, dt, world, colonists):
        self.hit_flash = max(0, self.hit_flash - dt)
        if self.hp <= 0: return

        for c in colonists:
            if c.hp <= 0: continue
            d = ((c.x - self.x) ** 2 + (c.y - self.y) ** 2) ** 0.5
            if d < 5 * TILE_SIZE:
                self.fleeing_timer = max(self.fleeing_timer, 1.0)

        if self.fleeing_timer > 0:
            self.fleeing_timer -= dt
            if not self.path and random.random() < 0.1:
                cx, cy = self.current_tile()
                dx, dy = random.choice([(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)])
                target = (cx + dx * 10, cy + dy * 10)
                p = astar(world, (cx, cy), target, max_iter=500)
                if p: self.path = p
        else:
            self.idle_timer -= dt
            if self.idle_timer <= 0 and not self.path:
                self.idle_timer = random.uniform(2.0, 5.0)
                cx, cy = self.current_tile()
                dx, dy = random.choice([(-2, 0), (2, 0), (0, -2), (0, 2)])
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

        if self.species == "rabbit":
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