# world/buildings.py
import pygame
from settings import TILE_SIZE

BUILDING_DEFS = {
    "floor": {"name": "地板", "layer": 0, "walkable": True, "w": 1, "h": 1, "variants": {
        "wood": {"name": "木地板", "cost": {"wood": 2}, "hp": 50, "build_time": 30, "color": (170, 130, 80)},
        "stone": {"name": "石地板", "cost": {"stone": 2}, "hp": 100, "build_time": 50, "color": (140, 140, 145)}
    }},
    "wall": {"name": "墙", "layer": 1, "walkable": False, "w": 1, "h": 1, "variants": {
        "wood": {"name": "木墙", "cost": {"wood": 4}, "hp": 80, "build_time": 30, "color": (130, 90, 50)},
        "stone": {"name": "石墙", "cost": {"stone": 5}, "hp": 200, "build_time": 60, "color": (100, 100, 105)}
    }},
    "window": {"name": "窗", "layer": 1, "walkable": False, "w": 1, "h": 1, "variants": {
        "wood": {"name": "木窗", "cost": {"wood": 2}, "hp": 50, "build_time": 25, "color": (130, 90, 50)},
        "stone": {"name": "石窗", "cost": {"stone": 3}, "hp": 100, "build_time": 45, "color": (100, 100, 105)}
    }},
    "door": {"name": "门", "layer": 1, "walkable": True, "w": 1, "h": 1, "variants": {
        "wood": {"name": "木门", "cost": {"wood": 4}, "hp": 80, "build_time": 40, "color": (160, 110, 60)},
        "stone": {"name": "石门", "cost": {"stone": 6}, "hp": 150, "build_time": 80, "color": (120, 120, 125)}
    }},
    "bed": {"name": "床", "layer": 1, "walkable": True, "w": 1, "h": 2, "variants": {
        "wood": {"name": "灰白床", "cost": {"wood": 6}, "hp": 80, "build_time": 50, "color": (230, 230, 235)}
    }},
    "research_bench": {"name": "研究台", "layer": 1, "walkable": False, "w": 2, "h": 2, "variants": {
        "wood": {"name": "研究台", "cost": {"wood": 10}, "hp": 80, "build_time": 80, "color": (120, 90, 60)}
    }},
    "stove": {"name": "烹饪台", "layer": 1, "walkable": False, "w": 3, "h": 1, "variants": {
        "stone": {"name": "石炉", "cost": {"stone": 12}, "hp": 150, "build_time": 80, "color": (100, 100, 105)}
    }},
    "small_cabinet": {"name": "小柜子", "layer": 1, "walkable": False, "w": 1, "h": 1, "max_types": 5, "variants": {
        "wood": {"name": "小木柜", "cost": {"wood": 6}, "hp": 100, "build_time": 40, "color": (150, 110, 70)}
    }},
    "large_cabinet": {"name": "大柜子", "layer": 1, "walkable": False, "w": 1, "h": 2, "max_types": 10, "variants": {
        "wood": {"name": "大木柜", "cost": {"wood": 12}, "hp": 150, "build_time": 60, "color": (140, 100, 60)}
    }}
}


class Blueprint:
    def __init__(self, kind, material, tx, ty, rotation=0):
        self.kind = kind
        self.material = material
        self.tx = tx
        self.ty = ty
        self.rotation = rotation
        self.layer = BUILDING_DEFS[kind]["layer"]

        w, h = BUILDING_DEFS[kind]["w"], BUILDING_DEFS[kind]["h"]
        self.w, self.h = (h, w) if rotation % 2 == 1 else (w, h)

        v = BUILDING_DEFS[kind]["variants"][material]
        self.work_done = 0.0
        self.work_needed = v["build_time"]
        self.reserved_by = None

        self.delivered_materials = {}
        for k in v["cost"].keys():
            self.delivered_materials[k] = 0

    def is_complete(self):
        return self.work_done >= self.work_needed

    def missing_materials(self):
        cost = BUILDING_DEFS[self.kind]["variants"][self.material]["cost"]
        missing = {}
        for k, v in cost.items():
            need = v - self.delivered_materials.get(k, 0)
            if need > 0:
                missing[k] = need
        return missing

    def has_all_materials(self):
        return len(self.missing_materials()) == 0

    def draw(self, surface, camera, font):
        sx, sy = camera.world_to_screen(self.tx * TILE_SIZE, self.ty * TILE_SIZE)
        rect = pygame.Rect(sx, sy, TILE_SIZE * self.w, TILE_SIZE * self.h)
        s = pygame.Surface(rect.size, pygame.SRCALPHA)
        if self.has_all_materials():
            s.fill((100, 160, 220, 120))
        else:
            s.fill((220, 100, 100, 60))
        surface.blit(s, (sx, sy))
        pygame.draw.rect(surface, (255, 220, 100), rect, 1)

        if self.work_done > 0:
            ratio = self.work_done / self.work_needed
            bw = int((TILE_SIZE * self.w - 4) * ratio)
            pygame.draw.rect(surface, (40, 40, 40), (sx + 2, sy + TILE_SIZE * self.h - 6, TILE_SIZE * self.w - 4, 3))
            pygame.draw.rect(surface, (255, 200, 60), (sx + 2, sy + TILE_SIZE * self.h - 6, bw, 3))


class Building:
    def __init__(self, kind, material, tx, ty, rotation=0):
        self.kind = kind
        self.material = material
        self.tx = tx
        self.ty = ty
        self.rotation = rotation
        self.layer = BUILDING_DEFS[kind]["layer"]

        w, h = BUILDING_DEFS[kind]["w"], BUILDING_DEFS[kind]["h"]
        self.w, self.h = (h, w) if rotation % 2 == 1 else (w, h)

        v = BUILDING_DEFS[kind]["variants"][material]
        self.color = v["color"]
        self.max_hp = v["hp"]
        self.hp = self.max_hp

        self.occupied_by = None
        self.reserved_by = None
        self.marked_for_deconstruction = False
        self.deconstruct_progress = 0.0
        self.deconstruct_needed = v["build_time"] * 0.5

        self.max_types = BUILDING_DEFS[kind].get("max_types", 0)
        self.capacity = 100
        self.inventory = {}

        self.cook_queue = []
        self.cook_progress = 0.0  # 新增：烹饪进度

    def take_damage(self, amount):
        self.hp -= amount
        return self.hp <= 0

    def get_total_items(self):
        return sum(self.inventory.values())

    def add_item(self, kind, amount):
        current_types = len(self.inventory.keys())
        if kind not in self.inventory and current_types >= self.max_types:
            return False
        current_amt = self.inventory.get(kind, 0)
        if current_amt + amount > self.capacity:
            return False
        self.inventory[kind] = current_amt + amount
        return True

    def remove_item(self, kind, amount):
        if self.inventory.get(kind, 0) >= amount:
            self.inventory[kind] -= amount
            if self.inventory[kind] <= 0: del self.inventory[kind]
            return True
        return False

    def draw(self, surface, camera):
        sx, sy = camera.world_to_screen(self.tx * TILE_SIZE, self.ty * TILE_SIZE)
        W = TILE_SIZE * self.w
        H = TILE_SIZE * self.h
        rect = pygame.Rect(sx, sy, W, H)

        color = self.color
        if self.hp < self.max_hp * 0.4:
            import time
            if int(time.time() * 5) % 2 == 0: color = (200, 50, 50)

        if self.kind == "floor":
            pygame.draw.rect(surface, color, rect)
            pygame.draw.rect(surface, (130, 95, 55), rect, 1)
        elif self.kind == "wall":
            pygame.draw.rect(surface, color, rect)
            line_col = (70, 70, 75) if self.material == "stone" else (90, 60, 30)
            pygame.draw.rect(surface, line_col, rect, 2)
            for i in range(1, self.h * 3):
                yy = sy + i * TILE_SIZE // 3
                if yy < sy + H: pygame.draw.line(surface, line_col, (sx, yy), (sx + W, yy), 1)
        elif self.kind == "window":
            frame = (100, 100, 105) if self.material == "stone" else (130, 90, 50)
            pygame.draw.rect(surface, frame, rect)
            s = pygame.Surface((TILE_SIZE - 8, TILE_SIZE - 8), pygame.SRCALPHA)
            s.fill((150, 200, 220, 120))
            surface.blit(s, (sx + 4, sy + 4))
            pygame.draw.rect(surface, frame, (sx + 4, sy + 4, TILE_SIZE - 8, TILE_SIZE - 8), 2)
            pygame.draw.line(surface, frame, (sx + TILE_SIZE // 2, sy + 4), (sx + TILE_SIZE // 2, sy + TILE_SIZE - 4),
                             2)
            pygame.draw.line(surface, frame, (sx + 4, sy + TILE_SIZE // 2), (sx + TILE_SIZE - 4, sy + TILE_SIZE // 2),
                             2)
        elif self.kind == "door":
            pygame.draw.rect(surface, color, rect)
            frame_col = (110, 70, 40) if self.material == "wood" else (70, 70, 75)
            pygame.draw.rect(surface, frame_col, rect, 2)
            pygame.draw.circle(surface, (255, 220, 100), (int(sx + TILE_SIZE - 6), int(sy + TILE_SIZE // 2)), 2)
        elif self.kind == "bed":
            pygame.draw.rect(surface, color, rect)
            pygame.draw.rect(surface, (180, 180, 190), rect, 2)
            if self.rotation % 2 == 0:
                pygame.draw.rect(surface, (250, 250, 255), (sx + 4, sy + 4, W - 8, 12))
                pygame.draw.rect(surface, (200, 200, 210), (sx + 4, sy + 20, W - 8, H - 24), 1)
            else:
                pygame.draw.rect(surface, (250, 250, 255), (sx + 4, sy + 4, 12, H - 8))
                pygame.draw.rect(surface, (200, 200, 210), (sx + 20, sy + 4, W - 24, H - 8), 1)
        elif self.kind == "research_bench":
            pygame.draw.rect(surface, (80, 60, 40), rect, border_radius=8)
            pygame.draw.rect(surface, (50, 40, 30), rect, 3, border_radius=8)
            pygame.draw.rect(surface, (200, 200, 220), (sx + 10, sy + 10, W - 20, 20))
            pygame.draw.circle(surface, (100, 200, 200), (sx + W // 2, sy + H - 20), 8)
        elif self.kind == "stove":
            pygame.draw.rect(surface, (100, 100, 105), rect, border_radius=4)
            pygame.draw.rect(surface, (60, 60, 65), rect, 3, border_radius=4)
            if self.rotation % 2 == 0:
                for i in range(3):
                    pygame.draw.circle(surface, (30, 30, 30),
                                       (sx + TILE_SIZE // 2 + i * TILE_SIZE, sy + TILE_SIZE // 2), TILE_SIZE // 3)
            else:
                for i in range(3):
                    pygame.draw.circle(surface, (30, 30, 30),
                                       (sx + TILE_SIZE // 2, sy + TILE_SIZE // 2 + i * TILE_SIZE), TILE_SIZE // 3)
            if self.cook_queue:
                pygame.draw.circle(surface, (255, 100, 50), (int(sx + W // 2), int(sy + H // 2)), 6)

            # 新增：绘制烹饪进度条
            if self.cook_progress > 0:
                ratio = min(1.0, self.cook_progress / 100.0)
                bw = int((W - 8) * ratio)
                pygame.draw.rect(surface, (40, 40, 40), (sx + 4, sy - 12, W - 8, 6))
                pygame.draw.rect(surface, (255, 200, 60), (sx + 4, sy - 12, bw, 6))
                pygame.draw.rect(surface, (0, 0, 0), (sx + 4, sy - 12, W - 8, 6), 1)
        elif self.kind == "small_cabinet":
            pygame.draw.rect(surface, (150, 110, 70), rect)
            pygame.draw.rect(surface, (100, 70, 40), rect, 2)
            pygame.draw.circle(surface, (220, 200, 100), (sx + TILE_SIZE // 2, sy + TILE_SIZE // 2), 2)
        elif self.kind == "large_cabinet":
            pygame.draw.rect(surface, (140, 100, 60), rect)
            pygame.draw.rect(surface, (90, 60, 30), rect, 2)
            if self.rotation % 2 == 0:
                pygame.draw.line(surface, (90, 60, 30), (sx + 5, sy + TILE_SIZE), (sx + W - 5, sy + TILE_SIZE), 2)
                for yy in [sy + TILE_SIZE // 2, sy + TILE_SIZE + TILE_SIZE // 2]:
                    pygame.draw.circle(surface, (220, 200, 100), (sx + W // 2, int(yy)), 2)
            else:
                pygame.draw.line(surface, (90, 60, 30), (sx + TILE_SIZE, sy + 5), (sx + TILE_SIZE, sy + H - 5), 2)
                for xx in [sx + TILE_SIZE // 2, sx + TILE_SIZE + TILE_SIZE // 2]:
                    pygame.draw.circle(surface, (220, 200, 100), (int(xx), sy + H // 2), 2)

        if self.marked_for_deconstruction:
            pygame.draw.line(surface, (255, 0, 0), (sx, sy), (sx + W, sy + H), 2)
            pygame.draw.line(surface, (255, 0, 0), (sx + W, sy), (sx, sy + H), 2)

        if self.hp < self.max_hp:
            ratio = self.hp / self.max_hp
            bw = int((W - 4) * ratio)
            pygame.draw.rect(surface, (60, 0, 0), (sx + 2, sy - 6, W - 4, 4))
            pygame.draw.rect(surface, (220, 60, 60), (sx + 2, sy - 6, bw, 4))


class BuildingManager:
    def __init__(self, research=None):
        self.blueprints = {}
        self.buildings = {}
        self.research = research

    def can_place(self, world, tx, ty, kind, material, rotation=0):
        if self.research and not self.research.is_unlocked(kind, material): return False
        w, h = BUILDING_DEFS[kind]["w"], BUILDING_DEFS[kind]["h"]
        if rotation % 2 == 1: w, h = h, w
        layer = BUILDING_DEFS[kind]["layer"]
        for dy in range(h):
            for dx in range(w):
                cx, cy = tx + dx, ty + dy
                if (cx, cy, layer) in self.blueprints or (cx, cy, layer) in self.buildings: return False
                t = world.get(cx, cy)
                if t is None: return False
                from world.world import T_WATER
                if t == T_WATER: return False
        return True

    def get_blueprints_at(self, tx, ty):
        res = []
        for k, bp in self.blueprints.items():
            if k[0] == tx and k[1] == ty:
                res.append(bp)
        if not res: return []
        res.sort(key=lambda b: b.layer, reverse=True)
        return [res[0]]

    def get_building_at(self, tx, ty):
        res = []
        for k, b in self.buildings.items():
            if k[0] == tx and k[1] == ty:
                res.append(b)
        if not res: return None
        res.sort(key=lambda b: b.layer, reverse=True)
        return res[0]

    def add_blueprint(self, kind, material, tx, ty, rotation=0):
        layer = BUILDING_DEFS[kind]["layer"]
        w, h = BUILDING_DEFS[kind]["w"], BUILDING_DEFS[kind]["h"]
        if rotation % 2 == 1: w, h = h, w

        for dy in range(h):
            for dx in range(w):
                if (tx + dx, ty + dy, layer) in self.blueprints: return None
        bp = Blueprint(kind, material, tx, ty, rotation)
        for dy in range(h):
            for dx in range(w):
                self.blueprints[(tx + dx, ty + dy, layer)] = bp
        return bp

    def complete_blueprint(self, bp):
        layer = bp.layer
        w, h = bp.w, bp.h
        for dy in range(h):
            for dx in range(w):
                if (bp.tx + dx, bp.ty + dy, layer) in self.blueprints:
                    del self.blueprints[(bp.tx + dx, bp.ty + dy, layer)]
        b = Building(bp.kind, bp.material, bp.tx, bp.ty, bp.rotation)
        for dy in range(h):
            for dx in range(w):
                self.buildings[(bp.tx + dx, bp.ty + dy, layer)] = b

    def remove_building(self, tx, ty, layer):
        b = self.get_building_at(tx, ty)
        if not b: return
        for dy in range(b.h):
            for dx in range(b.w):
                key = (b.tx + dx, b.ty + dy, layer)
                if key in self.buildings: del self.buildings[key]

    def remove_area(self, tx1, ty1, tx2, ty2):
        bp_to_del = set()
        for k, bp in self.blueprints.items():
            if tx1 <= k[0] <= tx2 and ty1 <= k[1] <= ty2: bp_to_del.add(bp)
        for bp in bp_to_del:
            for dy in range(bp.h):
                for dx in range(bp.w):
                    key = (bp.tx + dx, bp.ty + dy, bp.layer)
                    if key in self.blueprints: del self.blueprints[key]

        marked = set()
        for k, b in self.buildings.items():
            if tx1 <= k[0] <= tx2 and ty1 <= k[1] <= ty2: marked.add(b)
        for b in marked: b.marked_for_deconstruction = True

    def find_deconstruct_job(self):
        for k, b in self.buildings.items():
            if b.marked_for_deconstruction: return (b.tx, b.ty, b.layer)
        return None

    def find_research_job(self):
        for k, b in self.buildings.items():
            if b.kind == "research_bench" and b.reserved_by is None and not b.marked_for_deconstruction:
                return (b.tx, b.ty, b.layer)
        return None

    def find_nearest_door(self, tx, ty, max_dist=20):
        best_door = None
        best_dist = max_dist
        for k, b in self.buildings.items():
            if b.kind == "door" and not b.marked_for_deconstruction:
                d = abs(k[0] - tx) + abs(k[1] - ty)
                if d < best_dist:
                    best_dist = d
                    best_door = (b.tx, b.ty)
        return best_door

    def is_walkable(self, world, tx, ty):
        if (tx, ty, 1) in self.buildings:
            b = self.buildings[(tx, ty, 1)]
            if b.marked_for_deconstruction: return True
            return BUILDING_DEFS[b.kind]["walkable"]
        return world.is_terrain_walkable(tx, ty)

    def find_free_bed(self, exclude_colonist=None):
        for (tx, ty, layer), b in self.buildings.items():
            if layer == 1 and b.kind == "bed" and not b.marked_for_deconstruction:
                if b.occupied_by is not None and b.occupied_by != exclude_colonist: continue
                if b.tx == tx and b.ty == ty: return (tx, ty)
        return None

    def draw_layer(self, surface, camera, font, layer):
        drawn_bp = set()
        for key, bp in self.blueprints.items():
            if bp.layer == layer and bp not in drawn_bp:
                bp.draw(surface, camera, font)
                drawn_bp.add(bp)

        drawn_b = set()
        for key, b in self.buildings.items():
            if b.layer == layer and b not in drawn_b:
                b.draw(surface, camera)
                drawn_b.add(b)