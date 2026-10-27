# world/items.py
import pygame
import math
from settings import TILE_SIZE

ITEM_DEFS = {
    "wood": {"name": "木头", "color": (139, 90, 43), "type": "material",
             "desc": "砍伐树木获得的材料。\n可用于建造墙壁和家具。"},
    "stone": {"name": "石头", "color": (130, 130, 135), "type": "material",
              "desc": "开采岩石获得的材料。\n非常坚固，适合建造防御工事。"},
    "food": {"name": "浆果", "color": (200, 80, 80), "type": "food", "food_type": "veg",
             "desc": "野外采集的浆果。\n【素类食材】\n可以直接食用，或用于烹饪。"},
    "meat": {"name": "生肉", "color": (180, 50, 50), "type": "food", "food_type": "meat",
             "desc": "狩猎动物获得的生肉。\n【肉类食材】\n直接食用有中毒风险，最好烹饪后再吃。"},
    "leather": {"name": "皮革", "color": (180, 140, 100), "type": "material",
                "desc": "从动物身上剥取的皮革。\n可用于制作衣物和高级家具。"},
    "meal_simple": {"name": "简单食物", "color": (200, 180, 100), "type": "food", "food_type": "meal",
                    "desc": "用简单食材烹饪的食物。\n【熟食】\n虽然不算美味，但能填饱肚子。"},
    "meal_fine": {"name": "美味食物", "color": (100, 200, 100), "type": "food", "food_type": "meal",
                  "desc": "精心烹饪的佳肴。\n【熟食】\n使用肉类和蔬菜混合烹饪，能极大地改善心情。"},
}


class ItemStack:
    def __init__(self, kind, amount, tx, ty):
        self.kind = kind
        self.amount = amount
        self.tx = tx
        self.ty = ty
        self.reserved_by = None
        self._jitter_x = (hash((tx, ty, kind)) % 10) - 5
        self._jitter_y = (hash((tx, ty, kind, 1)) % 10) - 5

    @property
    def x(self):
        return self.tx * TILE_SIZE + TILE_SIZE / 2 + self._jitter_x

    @property
    def y(self):
        return self.ty * TILE_SIZE + TILE_SIZE / 2 + self._jitter_y

    def draw(self, surface, camera, font):
        if self.amount <= 0: return
        sx, sy = camera.world_to_screen(self.x, self.y)

        if self.kind == "meat":
            pygame.draw.line(surface, (240, 240, 240), (sx - 8, sy - 6), (sx + 8, sy + 6), 4)
            pygame.draw.circle(surface, (240, 240, 240), (int(sx - 8), int(sy - 6)), 3)
            pygame.draw.circle(surface, (240, 240, 240), (int(sx + 8), int(sy + 6)), 3)
            pygame.draw.ellipse(surface, (180, 50, 50), (sx - 10, sy - 6, 16, 12))
            pygame.draw.ellipse(surface, (120, 30, 30), (sx - 10, sy - 6, 16, 12), 1)
        elif self.kind == "food":
            pygame.draw.circle(surface, (220, 60, 60), (int(sx - 4), int(sy - 4)), 4)
            pygame.draw.circle(surface, (200, 40, 40), (int(sx + 4), int(sy - 2)), 4)
            pygame.draw.circle(surface, (230, 70, 70), (int(sx), int(sy + 4)), 4)
            pygame.draw.ellipse(surface, (80, 180, 80), (sx - 2, sy - 10, 6, 4))
        elif self.kind == "leather":
            pts = [(sx - 8, sy - 4), (sx + 6, sy - 6), (sx + 10, sy + 4), (sx + 2, sy + 8), (sx - 10, sy + 2)]
            pygame.draw.polygon(surface, (180, 140, 100), pts)
            pygame.draw.polygon(surface, (120, 90, 60), pts, 1)
        elif self.kind == "stone":
            pygame.draw.rect(surface, (130, 130, 135), (sx - 6, sy - 6, 12, 12), border_radius=2)
            pygame.draw.rect(surface, (90, 90, 95), (sx - 6, sy - 6, 12, 12), 1, border_radius=2)
        elif self.kind == "wood":
            pygame.draw.rect(surface, (139, 90, 43), (sx - 10, sy - 4, 20, 8))
            pygame.draw.rect(surface, (100, 60, 30), (sx - 10, sy - 4, 20, 8), 1)
            pygame.draw.line(surface, (100, 60, 30), (sx - 5, sy - 4), (sx - 5, sy + 4), 1)
            pygame.draw.line(surface, (100, 60, 30), (sx + 5, sy - 4), (sx + 5, sy + 4), 1)
        elif self.kind == "meal_simple":
            pygame.draw.ellipse(surface, (200, 200, 210), (sx - 10, sy - 4, 20, 12))
            pygame.draw.ellipse(surface, (150, 150, 160), (sx - 10, sy - 4, 20, 12), 1)
            pygame.draw.ellipse(surface, (180, 160, 100), (sx - 8, sy - 2, 16, 8))
        elif self.kind == "meal_fine":
            pygame.draw.ellipse(surface, (220, 230, 240), (sx - 10, sy - 4, 20, 12))
            pygame.draw.ellipse(surface, (80, 100, 150), (sx - 10, sy - 4, 20, 12), 1)
            pygame.draw.ellipse(surface, (180, 80, 60), (sx - 6, sy - 2, 8, 6))
            pygame.draw.circle(surface, (80, 180, 80), (int(sx + 4), int(sy + 1)), 3)
        else:
            d = ITEM_DEFS.get(self.kind, {"color": (200, 200, 200)})
            pygame.draw.rect(surface, d["color"], (sx - 6, sy - 6, 12, 12))

        txt = font.render(str(self.amount), True, (255, 255, 255))
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            surface.blit(font.render(str(self.amount), True, (0, 0, 0)),
                         (sx - txt.get_width() / 2 + dx, sy - txt.get_height() / 2 + dy))
        surface.blit(txt, (sx - txt.get_width() / 2, sy - txt.get_height() / 2))


class ItemManager:
    def __init__(self):
        self.stacks = {}

    def add(self, kind, amount, tx, ty):
        if kind is None or amount <= 0: return
        key = (tx, ty, kind)
        if key in self.stacks:
            self.stacks[key].amount += amount
        else:
            self.stacks[key] = ItemStack(kind, amount, tx, ty)

    def remove_at(self, tx, ty):
        keys_to_del = [k for k in self.stacks if k[0] == tx and k[1] == ty]
        for k in keys_to_del:
            del self.stacks[k]

    def get_at(self, tx, ty):
        return [s for s in self.stacks.values() if s.tx == tx and s.ty == ty]

    def draw(self, surface, camera, font):
        for s in self.stacks.values():
            s.draw(surface, camera, font)