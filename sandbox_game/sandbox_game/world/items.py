# world/items.py (只需替换 ItemStack 的 draw 函数，为了保险，完整文件如下)
import pygame
import math
from settings import TILE_SIZE

ITEM_DEFS = {
    "wood": {"name": "木头", "color": (139, 90, 43), "type": "material"},
    "stone": {"name": "石头", "color": (130, 130, 135), "type": "material"},
    "iron_ore": {"name": "粗铁", "color": (180, 100, 80), "type": "material"},
    "iron": {"name": "铁", "color": (200, 200, 210), "type": "material"},
    "food": {"name": "浆果", "color": (200, 80, 80), "type": "food", "food_type": "veg"},
    "meat": {"name": "生肉", "color": (180, 50, 50), "type": "food", "food_type": "meat"},
    "leather": {"name": "皮革", "color": (180, 140, 100), "type": "material"},
    "meal_simple": {"name": "简单食物", "color": (200, 180, 100), "type": "food", "food_type": "meal"},
    "meal_fine": {"name": "美味食物", "color": (100, 200, 100), "type": "food", "food_type": "meal"},
    "medicine": {"name": "草药", "color": (100, 200, 150), "type": "material"},
    "axe": {"name": "铁斧", "color": (100, 100, 110), "type": "item"},
    "stone_pickaxe": {"name": "石镐", "color": (130, 130, 135), "type": "item"},
    "iron_pickaxe": {"name": "铁镐", "color": (150, 150, 160), "type": "item"},
    "longsword": {"name": "长剑", "color": (220, 220, 220), "type": "item"},
    "gun": {"name": "枪械", "color": (80, 80, 80), "type": "item"},
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
        elif self.kind == "medicine":
            pygame.draw.line(surface, (50, 120, 50), (sx, sy - 8), (sx, sy + 8), 3)
            pygame.draw.line(surface, (50, 120, 50), (sx - 6, sy - 2), (sx + 6, sy - 6), 2)
            pygame.draw.circle(surface, (100, 220, 100), (int(sx - 6), int(sy - 6)), 4)
            pygame.draw.circle(surface, (100, 220, 100), (int(sx + 4), int(sy + 6)), 3)
        elif self.kind == "leather":
            pts = [(sx - 8, sy - 4), (sx + 6, sy - 6), (sx + 10, sy + 4), (sx + 2, sy + 8), (sx - 10, sy + 2)]
            pygame.draw.polygon(surface, (180, 140, 100), pts);
            pygame.draw.polygon(surface, (120, 90, 60), pts, 1)
        elif self.kind == "stone":
            pygame.draw.rect(surface, (130, 130, 135), (sx - 6, sy - 6, 12, 12), border_radius=2)
            pygame.draw.rect(surface, (90, 90, 95), (sx - 6, sy - 6, 12, 12), 1, border_radius=2)
        elif self.kind == "iron_ore":
            pygame.draw.rect(surface, (120, 100, 110), (sx - 6, sy - 6, 12, 12), border_radius=3)
            pygame.draw.rect(surface, (80, 60, 70), (sx - 6, sy - 6, 12, 12), 1, border_radius=3)
            pygame.draw.circle(surface, (180, 100, 80), (int(sx - 2), int(sy - 2)), 2)
            pygame.draw.circle(surface, (180, 100, 80), (int(sx + 3), int(sy + 3)), 2)
        elif self.kind == "iron":
            pygame.draw.rect(surface, (180, 180, 190), (sx - 7, sy - 5, 14, 10), border_radius=2)
            pygame.draw.rect(surface, (130, 130, 140), (sx - 7, sy - 5, 14, 10), 1, border_radius=2)
            pygame.draw.line(surface, (220, 220, 230), (sx - 4, sy - 2), (sx + 4, sy - 2), 1)
        elif self.kind == "wood":
            pygame.draw.rect(surface, (139, 90, 43), (sx - 10, sy - 4, 20, 8))
            pygame.draw.rect(surface, (100, 60, 30), (sx - 10, sy - 4, 20, 8), 1)
            pygame.draw.line(surface, (100, 60, 30), (sx - 5, sy - 4), (sx - 5, sy + 4), 1)
            pygame.draw.line(surface, (100, 60, 30), (sx + 5, sy - 4), (sx + 5, sy + 4), 1)
        elif self.kind in ("meal_simple", "meal_fine"):
            col = (200, 200, 210) if self.kind == "meal_simple" else (220, 230, 240)
            pygame.draw.ellipse(surface, col, (sx - 10, sy - 4, 20, 12))
            pygame.draw.ellipse(surface, (150, 150, 160), (sx - 10, sy - 4, 20, 12), 1)
            pygame.draw.ellipse(surface, (180, 160, 100) if self.kind == "meal_simple" else (180, 80, 60),
                                (sx - 8, sy - 2, 16, 8))

        # 【新增】精细化的武器贴图
        elif self.kind == "axe":
            pygame.draw.line(surface, (139, 69, 19), (sx - 8, sy + 8), (sx + 4, sy - 4), 3)
            pts = [(sx + 2, sy - 8), (sx + 10, sy - 4), (sx + 6, sy + 2), (sx - 2, sy - 2)]
            pygame.draw.polygon(surface, (160, 160, 170), pts)
            pygame.draw.polygon(surface, (100, 100, 110), pts, 1)
        elif self.kind in ("stone_pickaxe", "iron_pickaxe"):
            pygame.draw.line(surface, (139, 69, 19), (sx - 8, sy + 8), (sx + 4, sy - 4), 3)
            color = (130, 130, 135) if self.kind == "stone_pickaxe" else (180, 180, 190)
            pygame.draw.lines(surface, color, False, [(sx - 4, sy - 10), (sx + 4, sy - 12), (sx + 10, sy - 4)], 4)
        elif self.kind == "longsword":
            pygame.draw.line(surface, (200, 200, 200), (sx - 6, sy + 6), (sx + 8, sy - 8), 3)
            pygame.draw.line(surface, (255, 255, 255), (sx - 4, sy + 4), (sx + 6, sy - 6), 1)
            pygame.draw.line(surface, (180, 140, 60), (sx - 8, sy + 8), (sx - 4, sy + 4), 2)
        elif self.kind == "gun":
            pygame.draw.rect(surface, (80, 80, 80), (sx - 10, sy - 4, 14, 6))
            pygame.draw.rect(surface, (60, 60, 60), (sx + 4, sy - 2, 6, 2))
            pygame.draw.rect(surface, (100, 80, 60), (sx - 6, sy + 2, 4, 6))

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
        for k in [k for k in self.stacks if k[0] == tx and k[1] == ty]: del self.stacks[k]

    def get_at(self, tx, ty):
        return [s for s in self.stacks.values() if s.tx == tx and s.ty == ty]

    def draw(self, surface, camera, font):
        for s in self.stacks.values(): s.draw(surface, camera, font)