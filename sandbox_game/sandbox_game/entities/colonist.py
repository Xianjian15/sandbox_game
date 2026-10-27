# entities/colonist.py
import pygame
import random
import math
from settings import TILE_SIZE, WHITE, SELECT
from core.pathfinding import astar
from world.buildings import BUILDING_DEFS
from world.world import T_ROCK, T_TREE, T_BERRY
from world.items import ITEM_DEFS
from combat.weapons import get_weapon
from combat.weapon_render import draw_weapon

DEFAULT_PRIORITIES = {"harvest": 2, "haul": 3, "build": 3, "research": 1, "hunt": 3, "farm": 2, "cook": 3}


class Colonist:
    _id_counter = 0
    _reserved_harvests = set()
    _items_ref = None
    _buildings_ref = None

    def __init__(self, tx, ty, name=None, weapon_key="pistol"):
        Colonist._id_counter += 1
        self.id = Colonist._id_counter
        self.x = tx * TILE_SIZE + TILE_SIZE / 2
        self.y = ty * TILE_SIZE + TILE_SIZE / 2
        self.name = name or f"小人{self.id}"
        self.hp = 100
        self.max_hp = 100
        self.speed = 3.5 * TILE_SIZE
        self.radius = TILE_SIZE // 2 - 4

        self.path = []
        self.selected = False
        self.job = None
        self.work_progress = 0.0
        self.work_speed = 30.0
        self.priorities = dict(DEFAULT_PRIORITIES)
        self.auto_harvest = False
        self.auto_hunt = False

        self.carry_limit = 20
        self.carrying = None

        self.satiety = 100.0
        self.rest = 100.0
        self.mood = 100.0

        self.state = None
        self.state_timer = 0.0
        self.bed_tile = None
        self._eat_target = None

        self.weapon_key = weapon_key
        w = get_weapon(weapon_key)
        self.attack_range = w["range"] * TILE_SIZE
        self.attack_damage = w["damage"]
        self.attack_cooldown = w["cooldown"]
        self.cooldown_timer = 0.0
        self.target_enemy = None
        self.target_animal = None
        self.hit_flash = 0.0
        self.auto_retaliate = True
        self.recent_shot = None
        self.facing_angle = 0.0
        self.queue = []

        rng = random.Random(self.id * 777)
        self.color = (rng.randint(80, 220), rng.randint(80, 220), rng.randint(80, 220))

    def get_weapon_def(self):
        return get_weapon(self.weapon_key)

    def current_tile(self):
        return int(self.x // TILE_SIZE), int(self.y // TILE_SIZE)

    def is_idle(self):
        return (self.job is None and not self.path and not self.queue
                and self.target_enemy is None and self.target_animal is None
                and self.hp > 0 and self.state is None)

    def is_busy(self):
        return (self.job is not None or self.path or self.queue
                or self.target_enemy is not None or self.target_animal is not None
                or self.state is not None)

    def take_damage(self, amount, attacker=None):
        self.hp -= amount
        self.hit_flash = 0.15
        if self.state == "sleeping": self._wake_up()
        if attacker is not None and self.auto_retaliate and self.target_enemy is None:
            self.target_enemy = attacker
        return self.hp <= 0

    def update_needs(self, dt, game_time):
        if self.hp <= 0: return

        if self.state == "sleeping":
            self.rest += 30.0 * dt
            self.satiety -= 0.05 * dt
            if self.rest >= 100:
                self.rest = 100
                self._wake_up()
        else:
            self.satiety -= 0.25 * dt
            night_mul = 3.0 if game_time.is_night else 1.0
            self.rest -= 0.12 * dt * night_mul

            if self.state == "eating":
                self.satiety += 80.0 * dt
                self.state_timer -= dt
                if self.satiety >= 100: self.satiety = 100
                if self.state_timer <= 0: self.state = None

        self.satiety = max(0, min(100, self.satiety))
        self.rest = max(0, min(100, self.rest))

        mood_target = 100
        if self.satiety < 30: mood_target -= (30 - self.satiety) * 1.5
        if self.rest < 30: mood_target -= (30 - self.rest) * 1.5
        if self.state == "eating": mood_target += 10
        self.mood += (mood_target - self.mood) * dt * 0.5
        self.mood = max(0, min(100, self.mood))

    def check_urgent_needs(self, world, items, stockpiles, buildings):
        if self.target_enemy is not None or self.hp <= 0 or self.state is not None: return False

        if self.rest <= 30:
            bed_tile = buildings.find_free_bed(exclude_colonist=self.id)
            if bed_tile is not None:
                if self._go_sleep(world, buildings, bed_tile): return True

        if self.satiety <= 40:
            if self.carrying and self.carrying["kind"] in ("meal_fine", "meal_simple"):
                food_kind = self.carrying["kind"]
                self.carrying["amount"] -= 1
                if self.carrying["amount"] <= 0: self.carrying = None
                self.state = "eating"
                self.state_timer = 0.8
                return True

            food_pos = self._find_food(items, stockpiles, buildings)
            if food_pos is not None:
                if self._go_eat(world, items, food_pos, buildings): return True
        return False

    def _find_food(self, items, stockpiles, buildings):
        for b in buildings.buildings.values():
            if b.kind in ("small_cabinet", "large_cabinet") and not b.marked_for_deconstruction:
                for k, amt in b.inventory.items():
                    if k in ("meal_fine", "meal_simple", "food", "meat") and amt > 0:
                        return (b.tx, b.ty, b)
        for sp in stockpiles.stockpiles:
            for (tx, ty) in sp.tiles():
                for s in items.get_at(tx, ty):
                    if s.kind in ("meal_fine", "meal_simple", "food", "meat") and s.amount > 0:
                        return (tx, ty, None)
        for (tx, ty, kind), stack in items.stacks.items():
            if kind in ("meal_fine", "meal_simple", "food", "meat") and stack.amount > 0:
                return (tx, ty, None)
        return None

    def _go_eat(self, world, items, food_info, buildings):
        tx, ty, b = food_info
        cur = self.current_tile()
        adj = (tx, ty) if world.is_walkable(tx, ty) else self._find_adjacent(world, cur, tx, ty)
        if adj is None: return False
        p = astar(world, cur, adj)
        if p is None: return False
        self.queue.clear()
        self._release_job()
        self.path = p
        self.state = "going_to_eat"
        self.state_timer = 0.0
        self._eat_target = (tx, ty, b)
        return True

    def _go_sleep(self, world, buildings, bed_tile):
        cur = self.current_tile()
        p = astar(world, cur, bed_tile)
        if p is None: return False
        self.queue.clear()
        self._release_job()
        self.path = p
        self.state = "going_to_sleep"
        self.bed_tile = bed_tile
        b = buildings.get_building_at(bed_tile[0], bed_tile[1])
        if b is not None: b.occupied_by = self.id
        return True

    def _wake_up(self):
        if self.bed_tile is not None:
            b = Colonist._buildings_ref.get_building_at(self.bed_tile[0],
                                                        self.bed_tile[1]) if Colonist._buildings_ref else None
            if b is not None and b.occupied_by == self.id: b.occupied_by = None
        self.bed_tile = None
        self.state = None

    def move_to(self, world, tx, ty):
        cur = self.current_tile()
        path = astar(world, cur, (tx, ty))
        if path is not None:
            self.path = path
            return True
        return False

    def assign_harvest(self, world, tx, ty):
        if not world.is_harvestable(tx, ty): return False
        candidates = self._find_adjacent_all(world, tx, ty)
        if not candidates: return False
        cur = self.current_tile()
        best_path, best_target = None, None
        for cand in candidates:
            p = astar(world, cur, cand)
            if p is not None and (best_path is None or len(p) < len(best_path)):
                best_path, best_target = p, cand
        if best_path is None: return False
        self._release_job()
        self.path = best_path
        self.job = {"type": "harvest", "tx": tx, "ty": ty, "adjacent": best_target}
        self.work_progress = 0.0
        Colonist._reserved_harvests.add((tx, ty))
        return True

    def assign_deconstruct(self, world, buildings, tx, ty, layer):
        cur = self.current_tile()
        adj = self._find_adjacent(world, cur, tx, ty)
        if adj is None:
            if world.is_walkable(tx, ty):
                adj = (tx, ty)
            else:
                return False
        p = astar(world, cur, adj)
        if p is None: return False
        self._release_job()
        self.path = p
        self.job = {"type": "deconstruct", "tx": tx, "ty": ty, "layer": layer}
        self.work_progress = 0.0
        return True

    def assign_haul(self, world, items, stockpiles, src_tx, src_ty, dst_tx, dst_ty, kind, amount, cabinet=None):
        cur = self.current_tile()
        adj = self._find_adjacent(world, cur, src_tx, src_ty)
        if adj is None: return False
        path1 = astar(world, cur, adj)
        if path1 is None: return False
        self._release_job()
        self.path = path1
        self.job = {"type": "haul", "src": (src_tx, src_ty), "dst": (dst_tx, dst_ty),
                    "kind": kind, "amount": amount, "stage": "to_src", "cabinet": cabinet}
        return True

    def _find_material_source(self, items, stockpiles, buildings, need):
        for (tx, ty, k), stack in items.stacks.items():
            if k in need and stack.amount > 0: return (tx, ty, k, None)
        for b in buildings.buildings.values():
            if b.kind in ("small_cabinet", "large_cabinet") and not b.marked_for_deconstruction:
                for k, amt in b.inventory.items():
                    if k in need and amt > 0: return (b.tx, b.ty, k, b)
        return None

    def _find_food_ingredient(self, items, stockpiles, buildings, kind_list):
        for b in buildings.buildings.values():
            if b.kind in ("small_cabinet", "large_cabinet") and not b.marked_for_deconstruction:
                for k in kind_list:
                    if b.inventory.get(k, 0) > 0: return (b.tx, b.ty, k, b)
        for sp in stockpiles.stockpiles:
            for (tx, ty) in sp.tiles():
                for s in items.get_at(tx, ty):
                    if s.kind in kind_list and s.amount > 0: return (tx, ty, s.kind, None)
        for (tx, ty, k), stack in items.stacks.items():
            if k in kind_list and stack.amount > 0: return (tx, ty, k, None)
        return None

    def assign_build(self, world, buildings, items, stockpiles, bp):
        cur = self.current_tile()

        if bp.has_all_materials():
            adj = self._find_adjacent_for_build(world, cur, bp)
            if adj is None: return False
            p = astar(world, cur, adj)
            if p is None: return False
            self._release_job()
            self.path = p
            bp.reserved_by = self.id
            self.job = {"type": "build", "bp": bp, "stage": "to_build"}
            return True
        else:
            missing = bp.missing_materials()
            need_kind = list(missing.keys())[0]

            if self.carrying and self.carrying["kind"] == need_kind:
                adj = self._find_adjacent_for_build(world, cur, bp)
                if adj is None: return False
                p = astar(world, cur, adj)
                if p is None: return False
                self._release_job()
                self.path = p
                bp.reserved_by = self.id
                self.job = {"type": "build", "bp": bp, "stage": "to_build"}
                return True

            src = self._find_material_source(items, stockpiles, buildings, {need_kind: 1})
            if src is None: return False
            src_tx, src_ty, src_kind, cab = src

            adj = self._find_adjacent(world, cur, src_tx, src_ty)
            if adj is None:
                if world.is_walkable(src_tx, src_ty):
                    adj = (src_tx, src_ty)
                else:
                    return False
            p = astar(world, cur, adj)
            if p is None: return False

            self._release_job()
            self.path = p
            bp.reserved_by = self.id
            self.job = {"type": "build", "bp": bp, "stage": "to_material",
                        "mat_src": (src_tx, src_ty), "mat_kind": src_kind, "cabinet": cab}
            return True

    def assign_research(self, world, buildings, tx, ty, layer):
        cur = self.current_tile()
        adj = self._find_adjacent(world, cur, tx, ty)
        if adj is None:
            if world.is_walkable(tx, ty):
                adj = (tx, ty)
            else:
                return False
        p = astar(world, cur, adj)
        if p is None: return False
        self._release_job()
        self.path = p
        self.job = {"type": "research", "tx": tx, "ty": ty, "layer": layer}
        self.work_progress = 0.0
        b = buildings.get_building_at(tx, ty)
        if b: b.reserved_by = self.id
        return True

    def assign_hunt(self, animal):
        self.target_animal = animal
        return True

    def assign_cook(self, world, items, stockpiles, buildings, stove):
        cur = self.current_tile()
        task = stove.cook_queue[0]
        meal = task["meal"]

        need = []
        if meal == "meal_simple":
            need = ["meat", "food"]
        else:
            need = ["meat", "food"]

        src = self._find_food_ingredient(items, stockpiles, buildings, need)
        if src:
            src_tx, src_ty, src_kind, cab = src
            adj = self._find_adjacent(world, cur, src_tx, src_ty)
            if adj:
                p = astar(world, cur, adj)
                if p:
                    self._release_job()
                    self.path = p
                    self.job = {"type": "cook", "stove": stove, "stage": "to_material",
                                "mat_src": (src_tx, src_ty), "mat_kind": src_kind, "cabinet": cab}
                    stove.reserved_by = self.id
                    stove.cook_progress = 0.0
                    return True
        return False

    def assign_farm(self, world, farm, tx, ty):
        cur = self.current_tile()
        adj = self._find_adjacent(world, cur, tx, ty)
        if adj is None:
            if world.is_walkable(tx, ty):
                adj = (tx, ty)
            else:
                return False
        p = astar(world, cur, adj)
        if p is None: return False
        self._release_job()
        self.path = p
        self.job = {"type": "farm", "tx": tx, "ty": ty, "farm": farm}
        self.work_progress = 0.0
        return True

    def _find_adjacent(self, world, start, tx, ty):
        candidates = self._find_adjacent_all(world, tx, ty)
        if not candidates: return (tx, ty) if world.is_walkable(tx, ty) else None
        best, best_d = None, None
        for c in candidates:
            d = abs(c[0] - start[0]) + abs(c[1] - start[1])
            if best_d is None or d < best_d: best, best_d = c, d
        return best

    def _find_adjacent_all(self, world, tx, ty):
        return [(tx + dx, ty + dy) for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
                if world.is_walkable(tx + dx, ty + dy)]

    def _find_adjacent_for_build(self, world, start, bp):
        candidates = []
        for dy in range(-1, bp.h + 1):
            for dx in range(-1, bp.w + 1):
                if 0 <= dx < bp.w and 0 <= dy < bp.h:
                    continue
                nx, ny = bp.tx + dx, bp.ty + dy
                if world.is_walkable(nx, ny):
                    candidates.append((nx, ny))

        if not candidates: return None
        best, best_d = None, None
        for c in candidates:
            d = abs(c[0] - start[0]) + abs(c[1] - start[1])
            if best_d is None or d < best_d:
                best, best_d = c, d
        return best

    def _push_out_of_wall(self, world):
        cx, cy = self.current_tile()
        if world.is_walkable(cx, cy): return

        self.path = []
        self.state = None

        for r in range(1, 10):
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    tx, ty = cx + dx, cy + dy
                    if world.is_walkable(tx, ty):
                        self.x = tx * TILE_SIZE + TILE_SIZE / 2
                        self.y = ty * TILE_SIZE + TILE_SIZE / 2
                        return

    def try_find_job(self, world, items, stockpiles, buildings, research, animals, farms):
        if self.is_busy(): return False

        job = buildings.find_deconstruct_job()
        if job:
            tx, ty, layer = job
            if self.assign_deconstruct(world, buildings, tx, ty, layer): return True

        jobs = sorted(self.priorities.items(), key=lambda x: x[1])
        for job_type, priority in jobs:
            if priority == 0: continue
            if job_type == "research" and research and research.current_research:
                r_job = buildings.find_research_job()
                if r_job:
                    tx, ty, layer = r_job
                    if self.assign_research(world, buildings, tx, ty, layer): return True
            elif job_type == "hunt" and self.auto_hunt:
                if animals:
                    nearest = min(animals, key=lambda a: (a.x - self.x) ** 2 + (a.y - self.y) ** 2)
                    self.assign_hunt(nearest)
                    return True
            elif job_type == "farm":
                for f in farms:
                    for pos, data in f.plots.items():
                        if data["reserved_by"] is None:
                            if not data["planted"] or data["growth"] >= 1.0:
                                if self.assign_farm(world, f, pos[0], pos[1]):
                                    data["reserved_by"] = self.id
                                    return True
            elif job_type == "cook":
                for b in buildings.buildings.values():
                    if b.kind == "stove" and not b.marked_for_deconstruction and b.reserved_by is None:
                        if hasattr(b, 'cook_queue') and b.cook_queue:
                            if self.assign_cook(world, items, stockpiles, buildings, b): return True
            elif job_type == "harvest" and self.auto_harvest:
                if self._try_harvest(world): return True
            elif job_type == "haul":
                if self._try_haul(world, items, stockpiles, buildings): return True
            elif job_type == "build":
                if self._try_build(world, buildings, items, stockpiles): return True
        return False

    def _try_harvest(self, world):
        best_pos, best_dist = None, 99999
        cur_x, cur_y = self.current_tile()
        for y in range(world.rows):
            for x in range(world.cols):
                t = world.get(x, y)
                if t in (T_ROCK, T_TREE, T_BERRY) and (x, y) not in Colonist._reserved_harvests:
                    d = abs(x - cur_x) + abs(y - cur_y)
                    if d < best_dist: best_dist, best_pos = d, (x, y)
        if best_pos:
            if self.assign_harvest(world, best_pos[0], best_pos[1]): return True
        return False

    def _try_haul(self, world, items, stockpiles, buildings):
        if self.carrying: return False

        target_stacks = []
        for (tx, ty, kind), stack in list(items.stacks.items()):
            if stack.amount <= 0 or stockpiles.find_stockpile_for(tx, ty) is not None: continue
            if getattr(stack, "reserved_by", None) is not None: continue
            target_stacks.append((tx, ty, kind, stack))

        target_stacks.sort(key=lambda x: 0 if x[2] in ("food", "meat", "meal_simple", "meal_fine") else 1)

        for (tx, ty, kind, stack) in target_stacks:
            cabinet = None
            take_amt = stack.amount
            for b in buildings.buildings.values():
                if b.kind in ("small_cabinet",
                              "large_cabinet") and not b.marked_for_deconstruction and b.reserved_by is None:
                    current_types = len(b.inventory.keys())
                    if kind not in b.inventory and current_types >= b.max_types:
                        continue
                    cur_amt = b.inventory.get(kind, 0)
                    space = b.capacity - cur_amt
                    if space > 0:
                        cabinet = b
                        take_amt = min(stack.amount, space)
                        break

            dst = (0, 0)
            if cabinet:
                dst = (cabinet.tx, cabinet.ty)
            else:
                sp_dst = self._find_dst_slot(items, stockpiles)
                if not sp_dst: continue
                dst = sp_dst
                take_amt = stack.amount

            if self.assign_haul(world, items, stockpiles, tx, ty, dst[0], dst[1], kind, take_amt, cabinet):
                if cabinet: cabinet.reserved_by = self.id
                return True
        return False

    def _try_build(self, world, buildings, items, stockpiles):
        unassigned_bps = set()
        for bp in buildings.blueprints.values():
            if bp.reserved_by is None:
                unassigned_bps.add(bp)

        cur_x, cur_y = self.current_tile()
        sorted_bps = sorted(list(unassigned_bps), key=lambda bp: abs(bp.tx - cur_x) + abs(bp.ty - cur_y))

        for bp in sorted_bps:
            if self.assign_build(world, buildings, items, stockpiles, bp):
                return True
        return False

    def _find_dst_slot(self, items, stockpiles):
        for sp in stockpiles.stockpiles:
            for (tx, ty) in sp.tiles():
                if not items.get_at(tx, ty): return (tx, ty)
        return None

    def assign_attack(self, enemy):
        self.target_enemy = enemy
        return True

    def enqueue_command(self, cmd):
        self.queue.append(cmd)

    def _pop_next_command(self):
        while self.queue:
            cmd = self.queue.pop(0)
            t = cmd["type"]
            if t == "move":
                if self.move_to(cmd.get("world"), cmd["tx"], cmd["ty"]): return True
            elif t == "harvest":
                if self.assign_harvest(cmd["world"], cmd["tx"], cmd["ty"]): return True
            elif t == "build":
                if self.assign_build(cmd["world"], cmd["buildings"], cmd["items"], cmd["stockpiles"],
                                     cmd["bp"]): return True
            elif t == "attack":
                self.assign_attack(cmd["enemy"])
                return True
            elif t == "hunt":
                self.assign_hunt(cmd["animal"])
                return True
        return False

    def update(self, dt, world=None, items=None, stockpiles=None, buildings=None, enemies=None, game_time=None,
               research=None):
        self.cooldown_timer = max(0, self.cooldown_timer - dt)
        self.hit_flash = max(0, self.hit_flash - dt)
        if self.hp <= 0: return

        if world is not None:
            self._push_out_of_wall(world)

        if self.target_enemy is not None:
            e = self.target_enemy
            if e.hp <= 0:
                self.target_enemy = None
            else:
                dx, dy = e.x - self.x, e.y - self.y
                self.facing_angle = math.atan2(dy, dx)
                d = (dx ** 2 + dy ** 2) ** 0.5
                if d <= self.attack_range:
                    self.path = []
                    if self.cooldown_timer <= 0:
                        wdef = self.get_weapon_def()
                        if wdef["melee"]:
                            self.recent_shot = ("melee", self.x, self.y, e.x, e.y, wdef["color"])
                        else:
                            muzzle_d = self.radius + 12
                            mx = self.x + math.cos(self.facing_angle) * muzzle_d
                            my = self.y + math.sin(self.facing_angle) * muzzle_d
                            self.recent_shot = ("shot", mx, my, e.x, e.y, wdef["color"])
                        dead = e.take_damage(self.attack_damage, attacker=self)
                        self.cooldown_timer = self.attack_cooldown
                        if dead: self.target_enemy = None
                    return
                else:
                    if not self.path:
                        t_tile = e.current_tile()
                        adj = self._find_adjacent(world, self.current_tile(), *t_tile)
                        if adj:
                            p = astar(world, self.current_tile(), adj)
                            if p is not None: self.path = p

        if self.target_animal is not None:
            a = self.target_animal
            if a.hp <= 0:
                self.target_animal = None
            else:
                dx, dy = a.x - self.x, a.y - self.y
                self.facing_angle = math.atan2(dy, dx)
                d = (dx ** 2 + dy ** 2) ** 0.5
                if d <= self.attack_range:
                    self.path = []
                    if self.cooldown_timer <= 0:
                        wdef = self.get_weapon_def()
                        muzzle_d = self.radius + 12
                        mx = self.x + math.cos(self.facing_angle) * muzzle_d
                        my = self.y + math.sin(self.facing_angle) * muzzle_d
                        self.recent_shot = ("shot", mx, my, a.x, a.y, (255, 150, 100))
                        dead = a.take_damage(self.attack_damage, attacker=self)
                        self.cooldown_timer = self.attack_cooldown
                        if dead:
                            self.target_animal = None
                            if items:
                                items.add(a.drop_item, a.drop_amount, *a.current_tile())
                                if a.species == "deer":
                                    items.add("leather", 3, *a.current_tile())
                    return
                else:
                    if not self.path:
                        t_tile = a.current_tile()
                        adj = self._find_adjacent(world, self.current_tile(), *t_tile)
                        if adj:
                            p = astar(world, self.current_tile(), adj)
                            if p is not None: self.path = p

        if self.path:
            target_tx, target_ty = self.path[0]
            tgx = target_tx * TILE_SIZE + TILE_SIZE / 2
            tgy = target_ty * TILE_SIZE + TILE_SIZE / 2
            dx, dy = tgx - self.x, tgy - self.y
            dist = (dx ** 2 + dy ** 2) ** 0.5
            step = self.speed * dt
            if dist > 0.001: self.facing_angle = math.atan2(dy, dx)
            if dist <= step:
                self.x, self.y = tgx, tgy
                self.path.pop(0)
                if not self.path: self._on_arrive(world, items, buildings)
            else:
                self.x += dx / dist * step
                self.y += dy / dist * step
            return

        if self.state in ("sleeping", "eating"): return
        if self.job and world is not None:
            self._update_job(dt, world, items, stockpiles, buildings, research)
            return
        if not self.job and not self.path and self.target_enemy is None and self.target_animal is None and self.queue:
            self._pop_next_command()

    def _on_arrive(self, world, items, buildings):
        if self.state == "going_to_eat":
            tx, ty, cab = self._eat_target
            food_kind = None
            if cab:
                for k, amt in cab.inventory.items():
                    if k in ("meal_fine", "meal_simple", "food", "meat") and amt > 0:
                        food_kind = k;
                        cab.remove_item(k, 1);
                        break
            else:
                stacks = items.get_at(tx, ty) if items else []
                food_stack = next(
                    (s for s in stacks if s.kind in ("food", "meat", "meal_simple", "meal_fine") and s.amount > 0),
                    None)
                if food_stack:
                    food_kind = food_stack.kind
                    food_stack.amount -= 1
                    if food_stack.amount <= 0: items.remove_at(tx, ty)

            if not food_kind:
                self.state = None
                return
            self.state = "eating"
            self.state_timer = 0.8
            if food_kind == "meal_fine":
                self.satiety = min(100, self.satiety + 80);
                self.mood = min(100, self.mood + 15)
            elif food_kind == "meal_simple":
                self.satiety = min(100, self.satiety + 50);
                self.mood = min(100, self.mood + 5)
            else:
                self.satiety = min(100, self.satiety + 30)
            return
        if self.state == "going_to_sleep": self.state = "sleeping"

    def _update_job(self, dt, world, items, stockpiles, buildings, research):
        j = self.job
        jt = j["type"]

        if jt == "harvest":
            if not world.is_harvestable(j["tx"], j["ty"]):
                self._release_job()
                return
            self.work_progress += self.work_speed * dt
            while self.work_progress >= 10.0:
                self.work_progress -= 10.0
                done, kind, amt = world.damage_resource(j["tx"], j["ty"], 10)
                if done:
                    if items is not None and kind is not None: items.add(kind, amt, j["tx"], j["ty"])
                    self._release_job()
                    break
        elif jt == "farm":
            farm = j["farm"]
            tx, ty = j["tx"], j["ty"]
            if (tx, ty) not in farm.plots:
                self._release_job()
                return
            data = farm.plots[(tx, ty)]
            if not data["planted"]:
                self.work_progress += self.work_speed * dt
                if self.work_progress >= 20.0:
                    data["planted"] = True
                    data["growth"] = 0.0
                    self._release_job()
            elif data["growth"] >= 1.0:
                self.work_progress += self.work_speed * dt
                if self.work_progress >= 20.0:
                    if farm.plant_type == "berry":
                        items.add("food", 3, tx, ty)
                    else:
                        items.add("wood", 5, tx, ty)
                    data["planted"] = False
                    data["growth"] = 0.0
                    self._release_job()
        elif jt == "deconstruct":
            tx, ty, layer = j["tx"], j["ty"], j["layer"]
            b = buildings.get_building_at(tx, ty)
            if not b or not b.marked_for_deconstruction:
                self._release_job()
                return
            self.work_progress += self.work_speed * dt
            b.deconstruct_progress += self.work_speed * dt
            if b.deconstruct_progress >= b.deconstruct_needed:
                cost = BUILDING_DEFS[b.kind]["variants"][b.material]["cost"]
                for k, v in cost.items():
                    refund = max(1, v // 2)
                    items.add(k, refund, tx, ty)
                buildings.remove_building(tx, ty, layer)
                self._release_job()
        elif jt == "research":
            b = buildings.get_building_at(j["tx"], j["ty"])
            if not b or b.marked_for_deconstruction or not research or not research.current_research:
                self._release_job()
                return
            research.add_progress(self.work_speed * 0.1 * dt)

        elif jt == "cook":
            stove = j["stove"]
            if not stove.cook_queue or stove.marked_for_deconstruction:
                self._release_job()
                return

            if j["stage"] == "to_material":
                self.work_progress += self.work_speed * dt * 2
                if self.work_progress >= 10.0:
                    self.work_progress = 0.0
                    tx, ty = j["mat_src"]
                    kind = j["mat_kind"]

                    found = False
                    if j.get("cabinet"):
                        found = j["cabinet"].remove_item(kind, 1)
                    else:
                        for s in items.get_at(tx, ty):
                            if s.kind == kind:
                                s.amount -= 1
                                if s.amount <= 0: items.remove_at(tx, ty)
                                found = True
                                break

                    if not found:
                        self._release_job()
                        return

                    if "materials" not in j: j["materials"] = {}
                    j["materials"][kind] = j["materials"].get(kind, 0) + 1

                    task = stove.cook_queue[0]
                    meal = task["meal"]

                    got_enough = False
                    if meal == "meal_simple":
                        if len(j["materials"]) > 0: got_enough = True
                    elif meal == "meal_fine":
                        if j["materials"].get("meat", 0) >= 1 and j["materials"].get("food", 0) >= 1:
                            got_enough = True

                    if got_enough:
                        adj = self._find_adjacent(world, self.current_tile(), stove.tx, stove.ty)
                        if adj:
                            p = astar(world, self.current_tile(), adj)
                            if p:
                                self.path = p
                                j["stage"] = "to_stove"
                                return
                        self._release_job()
                    else:
                        need = ["meat", "food"]
                        if meal == "meal_fine":
                            if j["materials"].get("meat", 0) > 0:
                                need = ["food"]
                            elif j["materials"].get("food", 0) > 0:
                                need = ["meat"]

                        src = self._find_food_ingredient(items, stockpiles, buildings, need)
                        if src:
                            src_tx, src_ty, src_kind, cab = src
                            adj = self._find_adjacent(world, self.current_tile(), src_tx, src_ty)
                            if adj:
                                p = astar(world, self.current_tile(), adj)
                                if p:
                                    self.path = p
                                    j["mat_src"] = (src_tx, src_ty)
                                    j["mat_kind"] = src_kind
                                    j["cabinet"] = cab
                                    return
                        self._release_job()

            elif j["stage"] == "to_stove":
                self.work_progress += self.work_speed * dt * 2
                if self.work_progress >= 10.0:
                    self.work_progress = 0.0
                    j["stage"] = "cooking"
                    return

            elif j["stage"] == "cooking":
                # 核心修改：烹饪速度极大幅降低 (需要 100 进度)
                self.work_progress += self.work_speed * dt
                stove.cook_progress = self.work_progress

                if self.work_progress >= 100.0:
                    self.work_progress = 0.0
                    stove.cook_progress = 0.0
                    task = stove.cook_queue.pop(0)
                    meal_kind = "meal_simple" if task["meal"] == "meal_simple" else "meal_fine"

                    if not self.carrying:
                        self.carrying = {"kind": meal_kind, "amount": 1}
                    elif self.carrying["kind"] == meal_kind:
                        self.carrying["amount"] += 1
                    else:
                        items.add(meal_kind, 1, stove.tx, stove.ty)

                    if not stove.cook_queue or (self.carrying and self.carrying["amount"] >= self.carry_limit):
                        j["stage"] = "storing"
                        self._find_storage_target(world, items, stockpiles, buildings, j)
                        return
                    else:
                        j["stage"] = "to_material"
                        j["materials"] = {}
                        need = ["meat", "food"]
                        src = self._find_food_ingredient(items, stockpiles, buildings, need)
                        if src:
                            src_tx, src_ty, src_kind, cab = src
                            adj = self._find_adjacent(world, self.current_tile(), src_tx, src_ty)
                            if adj:
                                p = astar(world, self.current_tile(), adj)
                                if p:
                                    self.path = p
                                    j["mat_src"] = (src_tx, src_ty)
                                    j["mat_kind"] = src_kind
                                    j["cabinet"] = cab
                                    return
                        self._release_job()

            elif j["stage"] == "storing":
                if j.get("target_kind") == "cabinet":
                    b = j["target_obj"]
                    if b:
                        space = b.capacity - b.inventory.get(self.carrying["kind"], 0)
                        put_amt = min(self.carrying["amount"], space)
                        if put_amt > 0:
                            b.add_item(self.carrying["kind"], put_amt)
                            self.carrying["amount"] -= put_amt

                        b.reserved_by = None

                        if self.carrying and self.carrying["amount"] > 0:
                            self._drop_food(items)

                        self.carrying = None
                        self._release_job()
                elif j.get("target_kind") == "ground":
                    tx, ty = j["target_pos"]
                    items.add(self.carrying["kind"], self.carrying["amount"], tx, ty)
                    self.carrying = None
                    self._release_job()
                else:
                    self._drop_food(items)
                    self._release_job()

        elif jt == "haul":
            stage = j["stage"]
            if stage == "to_src":
                self.work_progress += self.work_speed * dt * 2
                if self.work_progress >= 10.0:
                    self.work_progress = 0.0
                    tx, ty = j["src"]
                    want_amt = j["amount"]

                    take_amt = 0
                    for s in items.get_at(tx, ty):
                        if s.kind == j["kind"]:
                            take = min(s.amount, want_amt)
                            s.amount -= take
                            take_amt += take
                            if s.amount <= 0: items.remove_at(tx, ty)
                            if take_amt >= want_amt: break

                    if take_amt == 0:
                        self._release_job()
                        return

                    j["amount"] = take_amt

                    cab = j.get("cabinet")
                    if cab:
                        path = astar(world, self.current_tile(),
                                     self._find_adjacent(world, self.current_tile(), cab.tx, cab.ty))
                    else:
                        path = astar(world, self.current_tile(), j["dst"])

                    if path is None:
                        items.add(j["kind"], take_amt, tx, ty)
                        self._release_job()
                        return
                    self.path = path
                    j["stage"] = "to_dst"
            elif stage == "to_dst":
                self.work_progress += self.work_speed * dt * 2
                if self.work_progress >= 10.0:
                    self.work_progress = 0.0
                    cab = j.get("cabinet")
                    if cab:
                        cab.add_item(j["kind"], j["amount"])
                        cab.reserved_by = None
                    else:
                        dx, dy = j["dst"]
                        items.add(j["kind"], j["amount"], dx, dy)
                    self._release_job()
        elif jt == "build":
            bp = j["bp"]
            stage = j["stage"]
            if stage == "to_material":
                self.work_progress += self.work_speed * dt * 2
                if self.work_progress >= 10.0:
                    self.work_progress = 0.0
                    tx, ty = j["mat_src"]
                    mat_kind = j["mat_kind"]

                    missing = bp.missing_materials().get(mat_kind, 0)
                    if missing <= 0:
                        self._release_job()
                        return

                    target_take = min(missing, self.carry_limit)
                    if self.carrying:
                        target_take -= self.carrying["amount"]

                    if target_take <= 0:
                        self._release_job()
                        return

                    total_taken = 0
                    cab = j.get("cabinet")
                    if cab:
                        avail = cab.inventory.get(mat_kind, 0)
                        take = min(avail, target_take)
                        if take > 0:
                            cab.remove_item(mat_kind, take)
                            total_taken = take
                    else:
                        stacks = items.get_at(tx, ty)
                        for s in stacks:
                            if s.kind == mat_kind:
                                take = min(s.amount, target_take - total_taken)
                                s.amount -= take
                                if s.amount <= 0: items.remove_at(tx, ty)
                                total_taken += take
                                if total_taken >= target_take: break

                    if total_taken == 0:
                        self._release_job()
                        return

                    if not self.carrying: self.carrying = {"kind": mat_kind, "amount": 0}
                    self.carrying["amount"] += total_taken

                    adj = self._find_adjacent_for_build(world, self.current_tile(), bp)
                    if adj is None:
                        self._release_job()
                        return
                    path = astar(world, self.current_tile(), adj)
                    if path is None:
                        self._release_job()
                        return
                    self.path = path
                    j["stage"] = "to_build"
            elif stage == "to_build":
                if self.carrying:
                    bp.delivered_materials[self.carrying["kind"]] = bp.delivered_materials.get(self.carrying["kind"],
                                                                                               0) + self.carrying[
                                                                        "amount"]
                    self.carrying = None

                if bp.has_all_materials():
                    if world.is_harvestable(bp.tx, bp.ty):
                        self.work_progress += self.work_speed * dt
                        while self.work_progress >= 10.0:
                            self.work_progress -= 10.0
                            done, kind, amt = world.damage_resource(bp.tx, bp.ty, 10)
                            if done:
                                if items is not None and kind is not None:
                                    items.add(kind, amt, bp.tx, bp.ty)
                                break
                        return

                    self.work_progress += self.work_speed * dt
                    bp.work_done += self.work_speed * dt
                    if bp.is_complete():
                        if buildings is not None: buildings.complete_blueprint(bp)
                        self.carrying = None
                        self._release_job()
                        self._push_out_of_wall(world)
                else:
                    missing = bp.missing_materials()
                    need_kind = list(missing.keys())[0]
                    src = self._find_material_source(items, stockpiles, buildings, {need_kind: 1})
                    if src:
                        src_tx, src_ty, src_kind, cab = src
                        adj = self._find_adjacent(world, self.current_tile(), src_tx, src_ty)
                        if adj:
                            p = astar(world, self.current_tile(), adj)
                            if p:
                                self.path = p
                                j["stage"] = "to_material"
                                j["mat_src"] = (src_tx, src_ty)
                                j["mat_kind"] = src_kind
                                j["cabinet"] = cab
                                return
                    self._release_job()

    def _find_storage_target(self, world, items, stockpiles, buildings, j):
        meal_kind = self.carrying["kind"]
        meal_amt = self.carrying["amount"]

        for b in buildings.buildings.values():
            if b.kind in ("small_cabinet", "large_cabinet") and not b.marked_for_deconstruction:
                current_types = len(b.inventory.keys())
                if meal_kind not in b.inventory and current_types >= b.max_types:
                    continue
                space = b.capacity - b.inventory.get(meal_kind, 0)
                if space > 0 and b.reserved_by is None:
                    adj = self._find_adjacent(world, self.current_tile(), b.tx, b.ty)
                    if adj:
                        p = astar(world, self.current_tile(), adj)
                        if p:
                            self.path = p
                            b.reserved_by = self.id
                            j["target_kind"] = "cabinet"
                            j["target_obj"] = b
                            return

        self._drop_food(items)

    def _drop_food(self, items):
        if self.carrying:
            tx, ty = self.current_tile()
            items.add(self.carrying["kind"], self.carrying["amount"], tx, ty)
            self.carrying = None

    def _take_from(self, items, tx, ty):
        if items is None: return None, 0
        stacks = items.get_at(tx, ty)
        if not stacks: return None, 0
        s = stacks[0]
        kind, amount = s.kind, s.amount
        items.remove_at(tx, ty)
        return kind, amount

    def _release_job(self):
        if self.job:
            if self.job.get("type") == "build":
                bp = self.job.get("bp")
                if bp is not None: bp.reserved_by = None
            elif self.job.get("type") == "cook":
                stove = self.job.get("stove")
                if stove and stove.reserved_by == self.id: stove.reserved_by = None
                if stove: stove.cook_progress = 0.0
                if self.job.get("stage") == "storing":
                    b = self.job.get("target_obj")
                    if b and b.reserved_by == self.id: b.reserved_by = None
                if self.carrying:
                    self._drop_food(Colonist._items_ref)
            elif self.job.get("type") == "farm":
                farm = self.job.get("farm")
                tx, ty = self.job["tx"], self.job["ty"]
                if farm and (tx, ty) in farm.plots:
                    farm.plots[(tx, ty)]["reserved_by"] = None
            elif self.job.get("type") == "harvest":
                tx, ty = self.job.get("tx"), self.job.get("ty")
                if (tx, ty) in Colonist._reserved_harvests: Colonist._reserved_harvests.remove((tx, ty))
            elif self.job.get("type") == "haul":
                key = self.job.get("reserved_stack_key")
                if key and Colonist._items_ref and key in Colonist._items_ref.stacks: Colonist._items_ref.stacks[
                    key].reserved_by = None
                cab = self.job.get("cabinet")
                if cab: cab.reserved_by = None
            elif self.job.get("type") == "research":
                tx, ty = self.job["tx"], self.job["ty"]
                if Colonist._buildings_ref:
                    b = Colonist._buildings_ref.get_building_at(tx, ty)
                    if b and b.reserved_by == self.id: b.reserved_by = None
        self.job = None
        self.work_progress = 0.0
        self.path = []

    def draw(self, surface, camera, font):
        if self.hp <= 0: return
        sx, sy = camera.world_to_screen(self.x, self.y)
        if self.selected: pygame.draw.circle(surface, SELECT, (int(sx), int(sy)), self.radius + 6, 2)
        wdef = self.get_weapon_def()
        draw_weapon(surface, sx, sy, self.facing_angle, wdef, 1.0)
        body_color = (255, 200, 100) if self.hit_flash > 0 else self.color
        pygame.draw.circle(surface, body_color, (int(sx), int(sy)), self.radius)
        pygame.draw.circle(surface, (0, 0, 0), (int(sx), int(sy)), self.radius, 2)
        bw, bh = self.radius * 2, 4
        hx, hy = int(sx - self.radius), int(sy - self.radius - 10)
        pygame.draw.rect(surface, (60, 0, 0), (hx, hy, bw, bh))
        pygame.draw.rect(surface, (60, 200, 60), (hx, hy, int(bw * self.hp / self.max_hp), bh))

        name_surf = font.render(self.name, True, WHITE)
        surface.blit(name_surf, (sx - name_surf.get_width() / 2, sy + self.radius + 2))

        if self.carrying:
            c_kind = self.carrying["kind"]
            c_color = ITEM_DEFS.get(c_kind, {"color": (200, 200, 200)})["color"]
            rect = pygame.Rect(sx + self.radius, sy - self.radius - 6, 14, 14)
            pygame.draw.rect(surface, c_color, rect)
            pygame.draw.rect(surface, (0, 0, 0), rect, 1)

            txt = font.render(str(self.carrying["amount"]), True, WHITE)
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                surface.blit(font.render(str(self.carrying["amount"]), True, (0, 0, 0)),
                             (sx + self.radius + 16 + dx, sy - self.radius - 10 + dy))
            surface.blit(txt, (sx + self.radius + 16, sy - self.radius - 10))

        label, color = None, (200, 200, 200)
        if self.state == "sleeping":
            label, color = "Zzz...", (180, 200, 255)
        elif self.state == "eating":
            label, color = "吃饭", (255, 220, 120)
        elif self.state in ("going_to_eat", "going_to_sleep"):
            label, color = ("去吃饭" if self.state == "going_to_eat" else "去睡觉"), (200, 220, 255)
        elif self.target_enemy is not None:
            label, color = "战斗", (255, 100, 100)
        elif self.target_animal is not None:
            label, color = "狩猎", (255, 150, 100)
        elif self.job:
            labels = {"harvest": "采集", "haul": "搬运", "build": "建造", "deconstruct": "拆除", "research": "研究",
                      "cook": "烹饪", "farm": "农业"}
            label, color = labels.get(self.job["type"], "工作"), (255, 220, 100)
        elif self.queue:
            label, color = f"待命({len(self.queue)})", (150, 200, 255)
        if label:
            job_surf = font.render(label, True, color)
            surface.blit(job_surf, (sx - job_surf.get_width() / 2, sy + self.radius + 20))
        if self.state == "sleeping":
            for off in [(20, -20), (28, -32), (36, -44)]:
                surface.blit(font.render("Z", True, (200, 220, 255)), (sx + off[0], sy + off[1]))

    def draw_path(self, surface, camera, world):
        if not self.path and not self.queue and self.target_enemy is None and self.target_animal is None: return

        current_color = (255, 255, 80)
        if self.target_enemy is not None or self.target_animal is not None:
            current_color = (255, 80, 80)
        elif self.job:
            if self.job["type"] == "move":
                current_color = (255, 255, 80)
            else:
                current_color = (80, 255, 80)

        last_pt = (self.x, self.y)
        last_tile = self.current_tile()

        if self.path:
            pts = [last_pt] + [(tx * TILE_SIZE + TILE_SIZE / 2, ty * TILE_SIZE + TILE_SIZE / 2) for tx, ty in self.path]
            screen_pts = [camera.world_to_screen(x, y) for (x, y) in pts]
            if len(screen_pts) >= 2:
                pygame.draw.lines(surface, current_color, False, screen_pts, 2)
            last_pt = pts[-1]
            last_tile = self.path[-1]

        if self.queue:
            for i, cmd in enumerate(self.queue):
                cmd_color = (255, 255, 80)
                if cmd["type"] == "attack":
                    cmd_color = (255, 80, 80)
                    if cmd["enemy"].hp > 0:
                        target_tx, target_ty = cmd["enemy"].current_tile()
                    else:
                        continue
                elif cmd["type"] == "hunt":
                    cmd_color = (255, 80, 80)
                    if cmd["animal"].hp > 0:
                        target_tx, target_ty = cmd["animal"].current_tile()
                    else:
                        continue
                elif cmd["type"] == "build":
                    cmd_color = (80, 255, 80)
                    bp = cmd.get("bp")
                    if bp:
                        target_tx, target_ty = bp.tx, bp.ty
                    else:
                        continue
                elif cmd["type"] in ("harvest", "deconstruct"):
                    cmd_color = (80, 255, 80)
                    target_tx, target_ty = cmd["tx"], cmd["ty"]
                else:
                    target_tx, target_ty = cmd["tx"], cmd["ty"]

                if i < 3:
                    p = astar(world, last_tile, (target_tx, target_ty))
                    if p:
                        pts = [(last_pt[0], last_pt[1])] + [
                            (tx * TILE_SIZE + TILE_SIZE / 2, ty * TILE_SIZE + TILE_SIZE / 2) for tx, ty in p]
                        screen_pts = [camera.world_to_screen(x, y) for (x, y) in pts]
                        if len(screen_pts) >= 2:
                            pygame.draw.lines(surface, cmd_color, False, screen_pts, 2)
                        last_pt = pts[-1]
                        last_tile = p[-1]
                    else:
                        sx, sy = camera.world_to_screen(target_tx * TILE_SIZE + TILE_SIZE / 2,
                                                        target_ty * TILE_SIZE + TILE_SIZE / 2)
                        pygame.draw.circle(surface, cmd_color, (int(sx), int(sy)), 5, 2)
                else:
                    sx, sy = camera.world_to_screen(target_tx * TILE_SIZE + TILE_SIZE / 2,
                                                    target_ty * TILE_SIZE + TILE_SIZE / 2)
                    pygame.draw.circle(surface, cmd_color, (int(sx), int(sy)), 5, 2)