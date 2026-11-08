# world/buildings.py
import pygame
from settings import TILE_SIZE
from world.world import T_TREE, T_ROCK, T_IRON_ROCK, T_BERRY

BUILDING_DEFS = {
    "floor": {"name": "地板", "layer": 0, "walkable": True, "w": 1, "h": 1, "variants": {
        "wood": {"name": "木地板", "cost": {"wood": 2}, "hp": 50, "build_time": 30, "color": (170, 130, 80)},
        "stone": {"name": "石地板", "cost": {"stone": 2}, "hp": 100, "build_time": 50, "color": (140, 140, 145)}}},
    "wall": {"name": "墙", "layer": 1, "walkable": False, "w": 1, "h": 1, "variants": {
        "wood": {"name": "木墙", "cost": {"wood": 4}, "hp": 80, "build_time": 30, "color": (130, 90, 50)},
        "stone": {"name": "石墙", "cost": {"stone": 5}, "hp": 200, "build_time": 60, "color": (100, 100, 105)}}},
    "window": {"name": "窗", "layer": 1, "walkable": False, "w": 1, "h": 1, "variants": {
        "wood": {"name": "木窗", "cost": {"wood": 2}, "hp": 50, "build_time": 25, "color": (130, 90, 50)},
        "stone": {"name": "石窗", "cost": {"stone": 3}, "hp": 100, "build_time": 45, "color": (100, 100, 105)}}},
    "door": {"name": "门", "layer": 1, "walkable": True, "w": 1, "h": 1, "variants": {
        "wood": {"name": "木门", "cost": {"wood": 4}, "hp": 80, "build_time": 40, "color": (160, 110, 60)},
        "stone": {"name": "石门", "cost": {"stone": 6}, "hp": 150, "build_time": 80, "color": (120, 120, 125)}}},
    "bed": {"name": "床", "layer": 1, "walkable": True, "w": 1, "h": 2, "variants": {
        "wood": {"name": "灰白床", "cost": {"wood": 6}, "hp": 80, "build_time": 50, "color": (230, 230, 235)}}},
    "medical_bed": {"name": "医疗床", "layer": 1, "walkable": True, "w": 1, "h": 2, "variants": {
        "wood": {"name": "医疗床", "cost": {"wood": 8, "medicine": 2}, "hp": 80, "build_time": 60,
                 "color": (180, 220, 230)}}},
    "research_bench": {"name": "研究台", "layer": 1, "walkable": False, "w": 2, "h": 2, "variants": {
        "wood": {"name": "研究台", "cost": {"wood": 10}, "hp": 80, "build_time": 80, "color": (120, 90, 60)}}},
    "stove": {"name": "烹饪台", "layer": 1, "walkable": False, "w": 3, "h": 1, "variants": {
        "stone": {"name": "石炉", "cost": {"stone": 12}, "hp": 150, "build_time": 80, "color": (100, 100, 105)}}},
    "furnace": {"name": "熔炉", "layer": 1, "walkable": False, "w": 2, "h": 2, "variants": {
        "stone": {"name": "熔炉", "cost": {"stone": 20}, "hp": 200, "build_time": 120, "color": (80, 80, 85)}}},
    "workbench": {"name": "工作台", "layer": 1, "walkable": False, "w": 2, "h": 1, "variants": {
        "wood": {"name": "工作台", "cost": {"wood": 15, "stone": 5}, "hp": 120, "build_time": 90,
                 "color": (160, 120, 80)}}},
    "small_cabinet": {"name": "小柜子", "layer": 1, "walkable": False, "w": 1, "h": 1, "max_types": 5, "variants": {
        "wood": {"name": "小木柜", "cost": {"wood": 6}, "hp": 100, "build_time": 40, "color": (150, 110, 70)}}},
    "large_cabinet": {"name": "大柜子", "layer": 1, "walkable": False, "w": 1, "h": 2, "max_types": 10, "variants": {
        "wood": {"name": "大木柜", "cost": {"wood": 12}, "hp": 150, "build_time": 60, "color": (140, 100, 60)}}},

    # --- 新增：无菌设施 ---
    "sterile_floor": {"name": "无菌地面", "layer": 0, "walkable": True, "w": 1, "h": 1, "variants": {
        "iron": {"name": "无菌地面", "cost": {"iron": 2}, "hp": 100, "build_time": 40, "color": (200, 210, 220)}}},
    "sterile_wall": {"name": "无菌墙", "layer": 1, "walkable": False, "w": 1, "h": 1, "variants": {
        "iron": {"name": "无菌墙", "cost": {"iron": 3}, "hp": 150, "build_time": 50, "color": (180, 190, 200)}}}
}


# ----------------- 以下部分保持原样，直接复制 -----------------
class Blueprint:
    def __init__(self, kind, material, tx, ty, rotation=0):
        self.kind, self.material, self.tx, self.ty, self.rotation = kind, material, tx, ty, rotation
        self.layer = BUILDING_DEFS[kind]["layer"]
        w, h = BUILDING_DEFS[kind]["w"], BUILDING_DEFS[kind]["h"]
        self.w, self.h = (h, w) if rotation % 2 == 1 else (w, h)
        v = BUILDING_DEFS[kind]["variants"][material]
        self.work_done, self.work_needed, self.reserved_by = 0.0, v["build_time"], None
        self.delivered_materials = {k: 0 for k in v["cost"].keys()}

    def is_complete(self):
        return self.work_done >= self.work_needed

    def missing_materials(self):
        cost = BUILDING_DEFS[self.kind]["variants"][self.material]["cost"]
        return {k: v - self.delivered_materials.get(k, 0) for k, v in cost.items() if
                v - self.delivered_materials.get(k, 0) > 0}

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
        self.kind, self.material, self.tx, self.ty, self.rotation = kind, material, tx, ty, rotation
        self.layer = BUILDING_DEFS[kind]["layer"]
        w, h = BUILDING_DEFS[kind]["w"], BUILDING_DEFS[kind]["h"]
        self.w, self.h = (h, w) if rotation % 2 == 1 else (w, h)
        v = BUILDING_DEFS[kind]["variants"][material]
        self.color, self.max_hp, self.hp = v["color"], v["hp"], v["hp"]
        self.occupied_by, self.reserved_by = None, None
        self.marked_for_deconstruction, self.deconstruct_progress = False, 0.0
        self.deconstruct_needed = v["build_time"] * 0.5
        self.max_types, self.capacity, self.inventory = BUILDING_DEFS[kind].get("max_types", 0), 100, {}
        self.cook_queue, self.cook_progress = [], 0.0
        self.craft_queue, self.craft_progress = [], 0.0
        self.smelt_queue, self.smelt_progress = [], 0.0
        self.delivered_ingredients = {}
        self.delivered_materials = {}

    def take_damage(self, amount):
        self.hp -= amount
        return self.hp <= 0

    def add_item(self, kind, amount):
        if kind not in self.inventory and len(self.inventory.keys()) >= self.max_types: return False
        if self.inventory.get(kind, 0) + amount > self.capacity: return False
        self.inventory[kind] = self.inventory.get(kind, 0) + amount
        return True

    def remove_item(self, kind, amount):
        if self.inventory.get(kind, 0) >= amount:
            self.inventory[kind] -= amount
            if self.inventory[kind] <= 0: del self.inventory[kind]
            return True
        return False

    def draw(self, surface, camera):
        sx, sy = camera.world_to_screen(self.tx * TILE_SIZE, self.ty * TILE_SIZE)
        W, H = TILE_SIZE * self.w, TILE_SIZE * self.h
        rect = pygame.Rect(sx, sy, W, H)

        color = self.color
        if self.hp < self.max_hp * 0.4:
            if int(pygame.time.get_ticks() / 200) % 2 == 0: color = (200, 50, 50)

        if self.kind == "floor":
            pygame.draw.rect(surface, color, rect);
            pygame.draw.rect(surface, (130, 95, 55), rect, 1)
        elif self.kind == "sterile_floor":
            pygame.draw.rect(surface, color, rect)
            pygame.draw.rect(surface, (150, 160, 170), rect, 1)
            pygame.draw.line(surface, (150, 160, 170), (sx, sy), (sx + W, sy + H), 1)
            pygame.draw.line(surface, (150, 160, 170), (sx + W, sy), (sx, sy + H), 1)
        elif self.kind == "wall":
            pygame.draw.rect(surface, color, rect)
            line_col = (70, 70, 75) if self.material == "stone" else (90, 60, 30)
            pygame.draw.rect(surface, line_col, rect, 2)
            for i in range(1, self.h * 3):
                yy = sy + i * TILE_SIZE // 3
                if yy < sy + H: pygame.draw.line(surface, line_col, (sx, yy), (sx + W, yy), 1)
        elif self.kind == "sterile_wall":
            pygame.draw.rect(surface, color, rect)
            pygame.draw.rect(surface, (120, 130, 140), rect, 2)
            for i in range(1, self.h * 3):
                yy = sy + i * TILE_SIZE // 3
                if yy < sy + H: pygame.draw.line(surface, (120, 130, 140), (sx, yy), (sx + W, yy), 1)
        elif self.kind == "window":
            frame = (100, 100, 105) if self.material == "stone" else (130, 90, 50)
            pygame.draw.rect(surface, frame, rect)
            s = pygame.Surface((TILE_SIZE - 8, TILE_SIZE - 8), pygame.SRCALPHA)
            s.fill((150, 200, 220, 120));
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
        elif self.kind in ("bed", "medical_bed"):
            pygame.draw.rect(surface, color, rect);
            pygame.draw.rect(surface, (180, 180, 190), rect, 2)
            if self.rotation % 2 == 0:
                pygame.draw.rect(surface, (250, 250, 255), (sx + 4, sy + 4, W - 8, 12))
                pygame.draw.rect(surface, (200, 200, 210), (sx + 4, sy + 20, W - 8, H - 24), 1)
            else:
                pygame.draw.rect(surface, (250, 250, 255), (sx + 4, sy + 4, 12, H - 8))
                pygame.draw.rect(surface, (200, 200, 210), (sx + 20, sy + 4, W - 24, H - 8), 1)
            if self.kind == "medical_bed":
                pygame.draw.line(surface, (100, 200, 150), (sx + W // 2, sy + H // 4), (sx + W // 2, sy + H * 3 // 4),
                                 2)
                pygame.draw.line(surface, (100, 200, 150), (sx + W // 4, sy + H // 2), (sx + W * 3 // 4, sy + H // 2),
                                 2)
        elif self.kind == "research_bench":
            pygame.draw.rect(surface, (80, 60, 40), rect, border_radius=8);
            pygame.draw.rect(surface, (50, 40, 30), rect, 3, border_radius=8)
            pygame.draw.rect(surface, (200, 200, 220), (sx + 10, sy + 10, W - 20, 20))
            pygame.draw.circle(surface, (100, 200, 200), (sx + W // 2, sy + H - 20), 8)
        elif self.kind == "stove":
            pygame.draw.rect(surface, (100, 100, 105), rect, border_radius=4);
            pygame.draw.rect(surface, (60, 60, 65), rect, 3, border_radius=4)
            if self.rotation % 2 == 0:
                for i in range(3): pygame.draw.circle(surface, (30, 30, 30),
                                                      (sx + TILE_SIZE // 2 + i * TILE_SIZE, sy + TILE_SIZE // 2),
                                                      TILE_SIZE // 3)
            else:
                for i in range(3): pygame.draw.circle(surface, (30, 30, 30),
                                                      (sx + TILE_SIZE // 2, sy + TILE_SIZE // 2 + i * TILE_SIZE),
                                                      TILE_SIZE // 3)
            if self.cook_queue: pygame.draw.circle(surface, (255, 100, 50), (int(sx + W // 2), int(sy + H // 2)), 6)
            if self.cook_progress > 0:
                ratio = min(1.0, self.cook_progress / 100.0);
                bw = int((W - 8) * ratio)
                pygame.draw.rect(surface, (40, 40, 40), (sx + 4, sy - 12, W - 8, 6));
                pygame.draw.rect(surface, (255, 200, 60), (sx + 4, sy - 12, bw, 6));
                pygame.draw.rect(surface, (0, 0, 0), (sx + 4, sy - 12, W - 8, 6), 1)
        elif self.kind == "furnace":
            pygame.draw.rect(surface, (70, 70, 75), rect, border_radius=4);
            pygame.draw.rect(surface, (40, 40, 45), rect, 3, border_radius=4)
            pygame.draw.rect(surface, (20, 20, 20), (sx + W // 4, sy + H // 2, W // 2, H // 3), border_radius=4)
            if self.smelt_queue: pygame.draw.rect(surface, (255, 100, 50),
                                                  (sx + W // 4 + 4, sy + H // 2 + 4, W // 2 - 8, H // 3 - 8),
                                                  border_radius=2)
            if self.smelt_progress > 0:
                ratio = min(1.0, self.smelt_progress / 150.0);
                bw = int((W - 8) * ratio)
                pygame.draw.rect(surface, (40, 40, 40), (sx + 4, sy - 12, W - 8, 6));
                pygame.draw.rect(surface, (255, 150, 50), (sx + 4, sy - 12, bw, 6));
                pygame.draw.rect(surface, (0, 0, 0), (sx + 4, sy - 12, W - 8, 6), 1)
        elif self.kind == "workbench":
            pygame.draw.rect(surface, (160, 120, 80), rect);
            pygame.draw.rect(surface, (100, 70, 40), rect, 2)
            pygame.draw.rect(surface, (80, 60, 40), (sx + 8, sy + 8, W - 16, H - 16))
            pygame.draw.line(surface, (200, 200, 200), (sx + 15, sy + H // 2), (sx + W - 15, sy + H // 2), 2)
            if self.craft_progress > 0:
                ratio = min(1.0, self.craft_progress / 150.0);
                bw = int((W - 8) * ratio)
                pygame.draw.rect(surface, (40, 40, 40), (sx + 4, sy - 12, W - 8, 6));
                pygame.draw.rect(surface, (100, 150, 255), (sx + 4, sy - 12, bw, 6));
                pygame.draw.rect(surface, (0, 0, 0), (sx + 4, sy - 12, W - 8, 6), 1)
        elif self.kind == "small_cabinet":
            pygame.draw.rect(surface, (150, 110, 70), rect);
            pygame.draw.rect(surface, (100, 70, 40), rect, 2)
            pygame.draw.circle(surface, (220, 200, 100), (sx + TILE_SIZE // 2, sy + TILE_SIZE // 2), 2)
        elif self.kind == "large_cabinet":
            pygame.draw.rect(surface, (140, 100, 60), rect);
            pygame.draw.rect(surface, (90, 60, 30), rect, 2)
            if self.rotation % 2 == 0:
                pygame.draw.line(surface, (90, 60, 30), (sx + 5, sy + TILE_SIZE), (sx + W - 5, sy + TILE_SIZE), 2)
                for yy in [sy + TILE_SIZE // 2, sy + TILE_SIZE + TILE_SIZE // 2]: pygame.draw.circle(surface,
                                                                                                     (220, 200, 100),
                                                                                                     (sx + W // 2,
                                                                                                      int(yy)), 2)
            else:
                pygame.draw.line(surface, (90, 60, 30), (sx + TILE_SIZE, sy + 5), (sx + TILE_SIZE, sy + H - 5), 2)
                for xx in [sx + TILE_SIZE // 2, sx + TILE_SIZE + TILE_SIZE // 2]: pygame.draw.circle(surface,
                                                                                                     (220, 200, 100),
                                                                                                     (int(xx),
                                                                                                      sy + H // 2), 2)
        else:
            pygame.draw.rect(surface, color, rect, border_radius=4);
            pygame.draw.rect(surface, (0, 0, 0), rect, 2, border_radius=4)

        if self.marked_for_deconstruction:
            pygame.draw.line(surface, (255, 0, 0), (sx, sy), (sx + W, sy + H), 2);
            pygame.draw.line(surface, (255, 0, 0), (sx + W, sy), (sx, sy + H), 2)
        if self.hp < self.max_hp:
            pygame.draw.rect(surface, (60, 0, 0), (sx + 2, sy - 6, W - 4, 4))
            pygame.draw.rect(surface, (220, 60, 60), (sx + 2, sy - 6, int((W - 4) * (self.hp / self.max_hp)), 4))


class BuildingManager:
    def __init__(self, research=None):
        self.blueprints, self.buildings, self.research = {}, {}, research

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
                if t is None or t == 3: return False
        return True

    def get_blueprints_at(self, tx, ty):
        return [b for k, b in self.blueprints.items() if k[:2] == (tx, ty)]

    def get_building_at(self, tx, ty):
        res = [b for k, b in self.buildings.items() if k[:2] == (tx, ty)]
        return sorted(res, key=lambda b: b.layer, reverse=True)[0] if res else None

    def add_blueprint(self, kind, material, tx, ty, rotation=0):
        layer = BUILDING_DEFS[kind]["layer"]
        w, h = BUILDING_DEFS[kind]["w"], BUILDING_DEFS[kind]["h"]
        if rotation % 2 == 1: w, h = h, w
        bp = Blueprint(kind, material, tx, ty, rotation)
        for dy in range(h):
            for dx in range(w): self.blueprints[(tx + dx, ty + dy, layer)] = bp
        return bp

    def complete_blueprint(self, bp):
        for dy in range(bp.h):
            for dx in range(bp.w): self.blueprints.pop((bp.tx + dx, bp.ty + dy, bp.layer), None)
        b = Building(bp.kind, bp.material, bp.tx, bp.ty, bp.rotation)
        for dy in range(bp.h):
            for dx in range(bp.w): self.buildings[(bp.tx + dx, bp.ty + dy, bp.layer)] = b

    def remove_building(self, tx, ty, layer):
        b = self.get_building_at(tx, ty)
        if b:
            for dy in range(b.h):
                for dx in range(b.w): self.buildings.pop((b.tx + dx, b.ty + dy, layer), None)

    def remove_area(self, tx1, ty1, tx2, ty2):
        for bp in set(b for k, b in self.blueprints.items() if tx1 <= k[0] <= tx2 and ty1 <= k[1] <= ty2):
            for dy in range(bp.h):
                for dx in range(bp.w): self.blueprints.pop((bp.tx + dx, bp.ty + dy, bp.layer), None)
        for b in set(b for k, b in self.buildings.items() if tx1 <= k[0] <= tx2 and ty1 <= k[1] <= ty2):
            b.marked_for_deconstruction = True

    def find_deconstruct_job(self):
        for k, b in self.buildings.items():
            if b.marked_for_deconstruction: return (b.tx, b.ty, b.layer)

    def find_research_job(self):
        for k, b in self.buildings.items():
            if b.kind == "research_bench" and b.reserved_by is None and not b.marked_for_deconstruction: return (b.tx,
                                                                                                                 b.ty,
                                                                                                                 b.layer)

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
            if layer == 1 and b.kind == "bed" and not b.marked_for_deconstruction and (
                    b.occupied_by is None or b.occupied_by == exclude_colonist):
                if b.tx == tx and b.ty == ty: return (tx, ty)

    def find_free_medical_bed(self, exclude_colonist=None):
        for (tx, ty, layer), b in self.buildings.items():
            if layer == 1 and b.kind == "medical_bed" and not b.marked_for_deconstruction and (
                    b.occupied_by is None or b.occupied_by == exclude_colonist):
                if b.tx == tx and b.ty == ty: return (tx, ty)

    def draw_layer(self, surface, camera, font, layer):
        drawn_bp, drawn_b = set(), set()
        for bp in self.blueprints.values():
            if bp.layer == layer and bp not in drawn_bp: bp.draw(surface, camera, font); drawn_bp.add(bp)
        for b in self.buildings.values():
            if b.layer == layer and b not in drawn_b: b.draw(surface, camera); drawn_b.add(b)