# entities/colonist.py
import pygame
import random
import math
from settings import TILE_SIZE, WHITE, SELECT
from core.pathfinding import astar
from world.buildings import BUILDING_DEFS
from world.world import T_ROCK, T_TREE, T_BERRY, T_IRON_ROCK
from world.items import ITEM_DEFS
from combat.weapons import get_weapon, WEAPONS
from combat.weapon_render import draw_weapon

DEFAULT_PRIORITIES = {"harvest": 2, "haul": 3, "build": 3, "research": 1, "hunt": 3, "farm": 2, "cook": 3, "craft": 3,
                      "smelt": 3, "doctor": 3}


class Colonist:
    _id_counter = 0
    _reserved_harvests = set()
    _designated_harvests = set()  # 玩家框选的指定采集区
    _items_ref, _buildings_ref, _room_mgr_ref, _all_colonists = None, None, None, []

    def __init__(self, tx, ty, name=None, weapon_key="fist"):
        Colonist._id_counter += 1
        self.id = Colonist._id_counter
        self.x, self.y = tx * TILE_SIZE + TILE_SIZE / 2, ty * TILE_SIZE + TILE_SIZE / 2
        self.name = name or f"小人{self.id}"
        self.hp, self.max_hp = 100, 100
        self.base_speed, self.base_work_speed = 3.5 * TILE_SIZE, 30.0
        self.speed, self.work_speed = self.base_speed, self.base_work_speed

        self.radius = TILE_SIZE // 2 - 4
        self.path, self.selected, self.job = [], False, None
        self.work_progress = 0.0
        self.priorities = dict(DEFAULT_PRIORITIES)
        self.carry_limit, self.carrying = 20, None
        self.satiety, self.rest, self.mood = 100.0, 100.0, 100.0

        self.bleeding = 0.0
        self.is_patient = False
        self.doctor_target = None

        self.state, self.state_timer, self.bed_tile, self._eat_target = None, 0.0, None, None
        self.weapon_key = weapon_key
        w = get_weapon(weapon_key)
        self.attack_range, self.attack_damage, self.attack_cooldown = w["range"] * TILE_SIZE, w["damage"], w["cooldown"]
        self.cooldown_timer, self.target_enemy, self.target_animal = 0.0, None, None
        self.hit_flash, self.auto_retaliate, self.recent_shot = 0.0, True, None
        self.facing_angle, self.queue = 0.0, []

        self.stuck_timer = 0.0
        self.last_pos = (self.x, self.y)
        self.last_prog = self.work_progress

        rng = random.Random(self.id * 777)
        self.color = (rng.randint(80, 220), rng.randint(80, 220), rng.randint(80, 220))

        # 建造锁：防止 haul 任务抢走正在建造的蓝图材料
        self.build_lock = None
        self.build_lock_timer = 0.0

        # 战斗锁：玩家指定攻击目标后，直到目标死亡或超时才解锁
        self.combat_lock = None
        self.combat_lock_timer = 0.0

    def get_weapon_def(self):
        return get_weapon(self.weapon_key)

    def current_tile(self):
        return int(self.x // TILE_SIZE), int(self.y // TILE_SIZE)

    def is_idle(self):
        return (self.job is None and not self.path and not self.queue and self.target_enemy is None
                and self.target_animal is None and self.hp > 0 and self.state is None and not self.is_patient)

    def is_busy(self):
        return (self.job is not None or self.path or self.queue or self.target_enemy is not None
                or self.target_animal is not None or self.state is not None or self.is_patient)

    def equip_weapon(self, new_key):
        if new_key in WEAPONS:
            self.weapon_key = new_key
            w = get_weapon(new_key)
            self.attack_range, self.attack_damage, self.attack_cooldown = w["range"] * TILE_SIZE, w["damage"], w[
                "cooldown"]

    def take_damage(self, amount, attacker=None):
        self.hp -= amount
        self.hit_flash = 0.15
        self.bleeding += amount * 0.05
        if self.state == "sleeping": self._wake_up()
        # 自动反击只在没有 combat_lock 时才劫持目标
        if attacker is not None and self.auto_retaliate and self.target_enemy is None and self.combat_lock is None:
            self.target_enemy = attacker
        return self.hp <= 0

    def update_needs(self, dt, game_time):
        if self.hp <= 0: return

        beauty = 0
        is_sterile = False
        if Colonist._room_mgr_ref:
            beauty = Colonist._room_mgr_ref.get_beauty_at(*self.current_tile())
            is_sterile = Colonist._room_mgr_ref.is_in_sterile_room(*self.current_tile())

        if self.state == "sleeping":
            self.rest += 30.0 * dt
            self.satiety -= 0.05 * dt

            if self.is_patient and is_sterile:
                self.bleeding = max(0, self.bleeding - 5.0 * dt)
                self.hp = min(self.max_hp, self.hp + 5.0 * dt)

            if self.rest >= 100: self.rest = 100; self._wake_up()
        else:
            self.satiety -= 0.25 * dt
            self.rest -= 0.12 * dt * (3.0 if game_time.is_night else 1.0)
            if self.state == "eating":
                self.satiety += 80.0 * dt
                self.state_timer -= dt
                if self.satiety >= 100: self.satiety = 100
                if self.state_timer <= 0: self.state = None

        if self.bleeding > 0 and not (self.state == "sleeping" and self.is_patient and is_sterile):
            self.hp -= self.bleeding * dt
            self.bleeding -= 0.05 * dt
            if self.bleeding < 0: self.bleeding = 0
            if self.hp <= 0: return

        self.satiety, self.rest = max(0, min(100, self.satiety)), max(0, min(100, self.rest))

        mood_target = 100
        if self.satiety < 30: mood_target -= (30 - self.satiety) * 1.5
        if self.rest < 30: mood_target -= (30 - self.rest) * 1.5
        if self.hp < 50: mood_target -= (50 - self.hp) * 1.0
        if self.state == "eating": mood_target += 10
        mood_target = min(100, mood_target + beauty * 0.1)

        self.mood += (mood_target - self.mood) * dt * 0.5
        self.mood = max(0, min(100, self.mood))

        if self.satiety <= 0 or self.rest <= 0:
            self.speed = self.base_speed * 0.75
            self.work_speed = self.base_work_speed * 0.75
        elif self.mood > 80:
            boost = 1.0 + (self.mood - 80) / 100.0
            self.speed = self.base_speed * boost
            self.work_speed = self.base_work_speed * boost
        else:
            self.speed = self.base_speed
            self.work_speed = self.base_work_speed

    def check_urgent_needs(self, world, items, stockpiles, buildings):
        # 战斗锁期间不被打断
        if (self.target_enemy is not None or self.combat_lock is not None or self.hp <= 0
                or self.state is not None or self.is_patient):
            return False

        if self.hp < 40 and self.bleeding > 0:
            bed = buildings.find_free_medical_bed(self.id)
            if bed and self._go_sleep(world, buildings, bed, is_medical=True): return True

        if self.rest <= 30:
            bed = buildings.find_free_bed(self.id)
            if bed and self._go_sleep(world, buildings, bed): return True
        if self.satiety <= 40:
            if self.carrying and self.carrying["kind"] in ("meal_fine", "meal_simple"):
                self.carrying["amount"] -= 1
                if self.carrying["amount"] <= 0: self.carrying = None
                self.state, self.state_timer = "eating", 0.8
                return True
            food = self._find_food(items, stockpiles, buildings)
            if food and self._go_eat(world, items, food, buildings): return True
        return False

    def _find_food(self, items, stockpiles, buildings):
        cx, cy = self.current_tile()
        candidates = []
        seen_b = set()
        for b in buildings.buildings.values():
            if id(b) in seen_b: continue
            seen_b.add(id(b))
            if b.kind in ("small_cabinet",
                          "large_cabinet") and not b.marked_for_deconstruction and b.reserved_by is None:
                for k, amt in b.inventory.items():
                    if k in ("meal_fine", "meal_simple", "food", "meat") and amt > 0:
                        d = abs(b.tx - cx) + abs(b.ty - cy)
                        candidates.append((d, (b.tx, b.ty, b)))

        for (tx, ty, kind), stack in items.stacks.items():
            if kind in ("meal_fine", "meal_simple", "food", "meat") and stack.amount > 0:
                d = abs(tx - cx) + abs(ty - cy)
                candidates.append((d, (tx, ty, None)))

        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

    def _go_eat(self, world, items, food_info, buildings):
        tx, ty, b = food_info
        adj = (tx, ty) if world.is_walkable(tx, ty) else self._find_adjacent(world, self.current_tile(), tx, ty)
        if not adj: return False
        p = astar(world, self.current_tile(), adj)
        if not p: return False
        self.queue.clear()
        self._release_job()
        self.path, self.state, self.state_timer = p, "going_to_eat", 0.0
        self._eat_target = (tx, ty, b)
        return True

    def _go_sleep(self, world, buildings, bed_tile, is_medical=False):
        p = astar(world, self.current_tile(), bed_tile)
        if not p: return False
        self.queue.clear()
        self._release_job()
        self.path, self.state, self.bed_tile = p, "going_to_sleep", bed_tile
        b = buildings.get_building_at(bed_tile[0], bed_tile[1])
        if b:
            b.occupied_by = self.id
            if is_medical: self.is_patient = True
        return True

    def _wake_up(self):
        if self.bed_tile and Colonist._buildings_ref:
            b = Colonist._buildings_ref.get_building_at(self.bed_tile[0], self.bed_tile[1])
            if b and b.occupied_by == self.id: b.occupied_by = None
        self.bed_tile, self.state, self.is_patient = None, None, False

    def move_to(self, world, tx, ty):
        p = astar(world, self.current_tile(), (tx, ty))
        if p: self.path = p; return True
        return False

    def assign_doctor(self, world, items, stockpiles, buildings, patient):
        if not self._find_material_source(items, stockpiles, buildings, {"medicine": 1}): return False
        adj = self._find_adjacent(world, self.current_tile(), *patient.current_tile())
        if not adj: return False
        p = astar(world, self.current_tile(), adj)
        if not p: return False
        self._release_job()
        self.path = p
        self.job = {"type": "doctor", "patient": patient, "stage": "to_patient"}
        return True

    def assign_take_from_cabinet(self, world, items, stockpiles, buildings, cabinet, kind, amount):
        if cabinet.inventory.get(kind, 0) <= 0: return False
        adj = self._find_adjacent(world, self.current_tile(), cabinet.tx, cabinet.ty)
        if not adj: return False
        p = astar(world, self.current_tile(), adj)
        if not p: return False
        self._release_job()
        self.path = p
        self.job = {"type": "take_from_cabinet", "cabinet": cabinet, "kind": kind, "amount": amount, "stage": "to_cabinet"}
        return True

    def assign_equip_from_ground(self, world, items, tx, ty, kind):
        adj = self._find_adjacent(world, self.current_tile(), tx, ty)
        if not adj and world.is_walkable(tx, ty): adj = (tx, ty)
        if not adj: return False

        p = astar(world, self.current_tile(), adj)
        if not p: return False

        self._release_job()
        self.path = p
        self.job = {"type": "equip_from_ground", "tx": tx, "ty": ty, "kind": kind, "stage": "to_item"}
        return True

    def _find_material_source(self, items, stockpiles, buildings, need):
        cx, cy = self.current_tile()
        candidates = []

        for (tx, ty, k), stack in items.stacks.items():
            if k in need and stack.amount > 0:
                if getattr(stack, "reserved_by", None) is not None: continue
                d = abs(tx - cx) + abs(ty - cy)
                candidates.append((d, (tx, ty, k, None)))

        seen_b = set()
        for b in buildings.buildings.values():
            if id(b) in seen_b: continue
            seen_b.add(id(b))
            if b.kind in ("small_cabinet",
                          "large_cabinet") and not b.marked_for_deconstruction and b.reserved_by is None:
                for k, amt in b.inventory.items():
                    if k in need and amt > 0:
                        d = abs(b.tx - cx) + abs(b.ty - cy)
                        candidates.append((d, (b.tx, b.ty, k, b)))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

    def _find_food_ingredient(self, items, stockpiles, buildings, kind_list):
        cx, cy = self.current_tile()
        candidates = []

        seen_b = set()
        for b in buildings.buildings.values():
            if id(b) in seen_b: continue
            seen_b.add(id(b))
            if b.kind in ("small_cabinet",
                          "large_cabinet") and not b.marked_for_deconstruction and b.reserved_by is None:
                for k in kind_list:
                    if b.inventory.get(k, 0) > 0:
                        d = abs(b.tx - cx) + abs(b.ty - cy)
                        candidates.append((d, (b.tx, b.ty, k, b)))

        for (tx, ty, k), stack in items.stacks.items():
            if k in kind_list and stack.amount > 0:
                if getattr(stack, "reserved_by", None) is not None: continue
                d = abs(tx - cx) + abs(ty - cy)
                candidates.append((d, (tx, ty, k, None)))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

    def assign_harvest(self, world, tx, ty):
        if not world.is_harvestable(tx, ty): return False
        if world.get(tx, ty) == T_IRON_ROCK and self.weapon_key not in ("stone_pickaxe", "iron_pickaxe"): return False
        cands = self._find_adjacent_all(world, tx, ty)
        best_p, best_t = None, None
        for cand in cands:
            p = astar(world, self.current_tile(), cand)
            if p and (best_p is None or len(p) < len(best_p)): best_p, best_t = p, cand
        if not best_p: return False
        self._release_job()
        self.path, self.job = best_p, {"type": "harvest", "tx": tx, "ty": ty, "adjacent": best_t}
        self.work_progress = 0.0
        Colonist._reserved_harvests.add((tx, ty))
        return True

    def assign_deconstruct(self, world, buildings, tx, ty, layer):
        adj = self._find_adjacent(world, self.current_tile(), tx, ty)
        if not adj and world.is_walkable(tx, ty): adj = (tx, ty)
        if not adj: return False
        p = astar(world, self.current_tile(), adj)
        if not p: return False
        self._release_job()
        self.path, self.job, self.work_progress = p, {"type": "deconstruct", "tx": tx, "ty": ty, "layer": layer}, 0.0
        return True

    def assign_haul(self, world, items, stockpiles, src_tx, src_ty, dst_tx, dst_ty, kind, amount, cabinet=None):
        adj = self._find_adjacent(world, self.current_tile(), src_tx, src_ty)
        if not adj: return False
        p1 = astar(world, self.current_tile(), adj)
        if not p1: return False
        self._release_job()
        self.path = p1
        self.job = {"type": "haul", "src": (src_tx, src_ty), "dst": (dst_tx, dst_ty), "kind": kind, "amount": amount,
                    "stage": "to_src", "cabinet": cabinet}
        return True

    def assign_build(self, world, buildings, items, stockpiles, bp):
        if bp.reserved_by is not None and bp.reserved_by != self.id: return False

        if bp.has_all_materials():
            adj = self._find_adjacent_for_build(world, self.current_tile(), bp)
            if not adj: return False
            p = astar(world, self.current_tile(), adj)
            if not p: return False
            self._release_job()
            self.path = p
            bp.reserved_by = self.id
            self.job = {"type": "build", "bp": bp, "stage": "to_build"}
            return True
        else:
            missing = bp.missing_materials()
            need_kind = list(missing.keys())[0]

            if self.carrying and self.carrying["kind"] == need_kind:
                adj = self._find_adjacent_for_build(world, self.current_tile(), bp)
                if not adj: return False
                p = astar(world, self.current_tile(), adj)
                if not p: return False
                self._release_job()
                self.path = p
                bp.reserved_by = self.id
                self.job = {"type": "build", "bp": bp, "stage": "to_build"}
                return True

            src = self._find_material_source(items, stockpiles, buildings, {need_kind: 1})
            if not src: return False
            src_tx, src_ty, src_kind, cab = src
            adj = self._find_adjacent(world, self.current_tile(), src_tx, src_ty)
            if not adj and world.is_walkable(src_tx, src_ty): adj = (src_tx, src_ty)
            if not adj: return False
            p = astar(world, self.current_tile(), adj)
            if not p: return False
            self._release_job()
            self.path = p
            bp.reserved_by = self.id
            self.job = {"type": "build", "bp": bp, "stage": "to_material", "mat_src": (src_tx, src_ty),
                        "mat_kind": src_kind, "cabinet": cab}
            return True

    def assign_research(self, world, buildings, tx, ty, layer):
        adj = self._find_adjacent(world, self.current_tile(), tx, ty)
        if not adj and world.is_walkable(tx, ty): adj = (tx, ty)
        if not adj: return False
        p = astar(world, self.current_tile(), adj)
        if not p: return False
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
        if self.carrying and self.carrying["kind"] in ("meal_simple", "meal_fine"): return False
        if not stove.cook_queue: return False
        task = stove.cook_queue[0]
        meal = task["meal"]
        if not hasattr(stove, "delivered_ingredients"): stove.delivered_ingredients = {}
        need = []
        if meal == "meal_simple":
            if sum(stove.delivered_ingredients.values()) < 2: need = ["meat", "food"]
        elif meal == "meal_fine":
            if sum(stove.delivered_ingredients.values()) < 4:
                if stove.delivered_ingredients.get("meat", 0) < 2: need.append("meat")
                if stove.delivered_ingredients.get("food", 0) < 2: need.append("food")

        if self.carrying and self.carrying["kind"] in need:
            adj = self._find_adjacent(world, self.current_tile(), stove.tx, stove.ty)
            if adj:
                p = astar(world, self.current_tile(), adj)
                if p:
                    self._release_job()
                    self.path = p
                    self.job = {"type": "cook", "stove": stove, "stage": "deliver"}
                    stove.reserved_by = self.id
                    return True
        if need:
            src = self._find_food_ingredient(items, stockpiles, buildings, need)
            if src:
                src_tx, src_ty, src_kind, cab = src
                adj = self._find_adjacent(world, self.current_tile(), src_tx, src_ty)
                if adj:
                    p = astar(world, self.current_tile(), adj)
                    if p:
                        self._release_job()
                        self.path = p
                        self.job = {"type": "cook", "stove": stove, "stage": "to_material", "mat_src": (src_tx, src_ty),
                                    "mat_kind": src_kind, "cabinet": cab}
                        stove.reserved_by = self.id
                        return True
        else:
            adj = self._find_adjacent(world, self.current_tile(), stove.tx, stove.ty)
            if adj:
                p = astar(world, self.current_tile(), adj)
                if p:
                    self._release_job()
                    self.path = p
                    self.job = {"type": "cook", "stove": stove, "stage": "to_stove"}
                    stove.reserved_by = self.id
                    return True
        return False

    def assign_farm(self, world, farm, tx, ty):
        adj = self._find_adjacent(world, self.current_tile(), tx, ty)
        if not adj and world.is_walkable(tx, ty): adj = (tx, ty)
        if not adj: return False
        p = astar(world, self.current_tile(), adj)
        if not p: return False
        self._release_job()
        self.path = p
        self.job = {"type": "farm", "tx": tx, "ty": ty, "farm": farm}
        self.work_progress = 0.0
        return True

    def assign_craft(self, world, items, stockpiles, buildings, bench):
        if not bench.craft_queue: return False
        if bench.reserved_by is not None and bench.reserved_by != self.id: return False
        task = bench.craft_queue[0]["item"]
        need = {"iron": 5} if task == "gun" else (
            {"iron": 3} if task == "longsword" else ({"stone": 2} if task == "stone_pickaxe" else {"iron": 2}))

        for k, v in need.items():
            if bench.delivered_materials.get(k, 0) < v:
                if self.carrying and self.carrying["kind"] == k:
                    adj = self._find_adjacent(world, self.current_tile(), bench.tx, bench.ty)
                    if adj:
                        p = astar(world, self.current_tile(), adj)
                        if p:
                            self._release_job()
                            self.path = p
                            self.job = {"type": "craft", "bench": bench, "stage": "deliver"}
                            bench.reserved_by = self.id
                            return True
                src = self._find_material_source(items, stockpiles, buildings, {k: 1})
                if src:
                    src_tx, src_ty, src_kind, cab = src
                    adj = self._find_adjacent(world, self.current_tile(), src_tx, src_ty)
                    if adj:
                        p = astar(world, self.current_tile(), adj)
                        if p:
                            self._release_job()
                            self.path = p
                            self.job = {"type": "craft", "bench": bench, "stage": "to_material",
                                        "mat_src": (src_tx, src_ty), "mat_kind": src_kind, "cabinet": cab}
                            bench.reserved_by = self.id
                            return True
                return False
        adj = self._find_adjacent(world, self.current_tile(), bench.tx, bench.ty)
        if adj:
            p = astar(world, self.current_tile(), adj)
            if p:
                self._release_job()
                self.path = p
                self.job = {"type": "craft", "bench": bench, "stage": "to_bench"}
                bench.reserved_by = self.id
                return True
        return False

    def assign_smelt(self, world, items, stockpiles, buildings, furnace):
        if not furnace.smelt_queue: return False
        if furnace.reserved_by is not None and furnace.reserved_by != self.id: return False
        if furnace.inventory.get("iron_ore", 0) >= 2:
            adj = self._find_adjacent(world, self.current_tile(), furnace.tx, furnace.ty)
            if adj:
                p = astar(world, self.current_tile(), adj)
                if p:
                    self._release_job()
                    self.path = p
                    self.job = {"type": "smelt", "furnace": furnace}
                    furnace.reserved_by = self.id
                    return True
        src = self._find_material_source(items, stockpiles, buildings, {"iron_ore": 2})
        if src:
            src_tx, src_ty, src_kind, cab = src
            adj = self._find_adjacent(world, self.current_tile(), src_tx, src_ty)
            if adj:
                p = astar(world, self.current_tile(), adj)
                if p:
                    self._release_job()
                    self.path = p
                    self.job = {"type": "smelt", "furnace": furnace, "stage": "to_material",
                                "mat_src": (src_tx, src_ty), "cabinet": cab}
                    furnace.reserved_by = self.id
                    return True
        return False

    def _find_adjacent(self, world, start, tx, ty):
        cands = self._find_adjacent_all(world, tx, ty)
        if not cands: return (tx, ty) if world.is_walkable(tx, ty) else None
        return min(cands, key=lambda c: abs(c[0] - start[0]) + abs(c[1] - start[1]))

    def _find_adjacent_all(self, world, tx, ty):
        return [(tx + dx, ty + dy) for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
                if world.is_walkable(tx + dx, ty + dy)]

    def _find_adjacent_for_build(self, world, start, bp):
        cands = [(bp.tx + dx, bp.ty + dy) for dy in range(-1, bp.h + 1) for dx in range(-1, bp.w + 1) if
                 not (0 <= dx < bp.w and 0 <= dy < bp.h) and world.is_walkable(bp.tx + dx, bp.ty + dy)]
        if not cands: return None
        return min(cands, key=lambda c: abs(c[0] - start[0]) + abs(c[1] - start[1]))

    def _push_out_of_wall(self, world):
        cx, cy = self.current_tile()
        if world.is_walkable(cx, cy): return
        self.path = []
        for r in range(1, 10):
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if world.is_walkable(cx + dx, cy + dy):
                        self.x, self.y = (cx + dx) * TILE_SIZE + TILE_SIZE / 2, (cy + dy) * TILE_SIZE + TILE_SIZE / 2
                        return

    def try_find_job(self, world, items, stockpiles, buildings, research, animals, farms):
        # 战斗锁优先：只要有目标，就一直追着打，不接其他任务
        if self.combat_lock is not None:
            if self.combat_lock.hp > 0:
                self.target_enemy = self.combat_lock
                return False
            else:
                self.combat_lock = None
                self.combat_lock_timer = 0.0

        if self.is_busy(): return False

        # 防死锁：手里有东西却不干活，直接丢地上
        if self.carrying:
            self._drop_food(items)
            return False

        # 有建造锁时优先继续建造，避免被搬运任务拆台
        if self.build_lock is not None:
            if self._try_build(world, buildings, items, stockpiles):
                return True
            # 失败也保留锁，让后续 harvest 去补料；超时机制兜底

        job = buildings.find_deconstruct_job()
        if job and self.assign_deconstruct(world, buildings, *job): return True
        jobs = sorted(self.priorities.items(), key=lambda x: x[1])
        for job_type, priority in jobs:
            if priority == 0: continue

            if job_type == "doctor":
                for b in buildings.buildings.values():
                    if b.kind == "medical_bed" and b.occupied_by is not None:
                        patient = next((c for c in Colonist._all_colonists if c.id == b.occupied_by), None)
                        if patient and patient.bleeding > 0:
                            if self.assign_doctor(world, items, stockpiles, buildings, patient): return True

            elif job_type == "research" and research and research.current_research:
                r_job = buildings.find_research_job()
                if r_job and self.assign_research(world, buildings, *r_job): return True
            elif job_type == "hunt":
                hunted_animals = [a for a in animals if getattr(a, "is_hunted", False)]
                if hunted_animals:
                    self.assign_hunt(min(hunted_animals, key=lambda a: (a.x - self.x) ** 2 + (a.y - self.y) ** 2))
                    return True
            elif job_type == "farm":
                for f in farms:
                    for pos, data in f.plots.items():
                        if data["reserved_by"] is None and (not data["planted"] or data["growth"] >= 1.0):
                            if self.assign_farm(world, f, pos[0], pos[1]): data["reserved_by"] = self.id; return True
            elif job_type == "cook":
                for b in buildings.buildings.values():
                    if b.kind == "stove" and not b.marked_for_deconstruction and b.reserved_by is None and getattr(b,
                                                                                                                   'cook_queue',
                                                                                                                   None):
                        if self.assign_cook(world, items, stockpiles, buildings, b): return True
            elif job_type == "craft":
                for b in buildings.buildings.values():
                    if b.kind == "workbench" and not b.marked_for_deconstruction and b.reserved_by is None and getattr(
                            b, 'craft_queue', None):
                        if self.assign_craft(world, items, stockpiles, buildings, b): return True
            elif job_type == "smelt":
                for b in buildings.buildings.values():
                    if b.kind == "furnace" and not b.marked_for_deconstruction and b.reserved_by is None and getattr(b,
                                                                                                                     'smelt_queue',
                                                                                                                     None):
                        if self.assign_smelt(world, items, stockpiles, buildings, b): return True
            elif job_type == "harvest":
                if self._try_harvest(world, buildings): return True
            elif job_type == "haul":
                if self._try_haul(world, items, stockpiles, buildings): return True
            elif job_type == "build":
                if self._try_build(world, buildings, items, stockpiles): return True
        return False

    def _try_harvest(self, world, buildings):
        needed_kinds = set()
        for bp in buildings.blueprints.values():
            needed_kinds.update(bp.missing_materials().keys())

        best_pos, best_dist = None, 99999
        cur_x, cur_y = self.current_tile()
        has_pickaxe = self.weapon_key in ("stone_pickaxe", "iron_pickaxe")

        if Colonist._designated_harvests:
            for (x, y) in Colonist._designated_harvests:
                tile = world.get(x, y)
                if tile in (T_ROCK, T_TREE, T_BERRY, T_IRON_ROCK) and (x, y) not in Colonist._reserved_harvests:
                    if tile == T_IRON_ROCK and not has_pickaxe: continue
                    d = abs(x - cur_x) + abs(y - cur_y)
                    if d < best_dist: best_dist, best_pos = d, (x, y)
        else:
            if needed_kinds:
                for y in range(world.rows):
                    for x in range(world.cols):
                        tile = world.get(x, y)
                        if tile in (T_ROCK, T_TREE, T_BERRY, T_IRON_ROCK) and (x, y) not in Colonist._reserved_harvests:
                            if tile == T_IRON_ROCK and not has_pickaxe: continue
                            drop = None
                            if tile == T_ROCK:
                                drop = "stone"
                            elif tile == T_TREE:
                                drop = "wood"
                            elif tile == T_BERRY:
                                drop = "food"
                            elif tile == T_IRON_ROCK:
                                drop = "iron_ore"
                            if drop in needed_kinds:
                                d = abs(x - cur_x) + abs(y - cur_y)
                                if d < best_dist: best_dist, best_pos = d, (x, y)

        if best_pos and self.assign_harvest(world, best_pos[0], best_pos[1]): return True
        return False

    def _try_haul(self, world, items, stockpiles, buildings):
        if self.carrying: return False
        if self.build_lock is not None: return False
        target_stacks = []
        for (tx, ty, kind), stack in list(items.stacks.items()):
            if stack.amount <= 0 or stockpiles.find_stockpile_for(tx, ty) is not None or getattr(stack, "reserved_by",
                                                                                                 None) is not None: continue
            target_stacks.append((tx, ty, kind, stack))
        target_stacks.sort(key=lambda x: 0 if x[2] in ("food", "meat", "meal_simple", "meal_fine") else 1)
        for (tx, ty, kind, stack) in target_stacks:
            cabinet, take_amt = None, stack.amount
            seen_b = set()
            for b in buildings.buildings.values():
                if id(b) in seen_b: continue
                seen_b.add(id(b))
                if b.kind in ("small_cabinet",
                              "large_cabinet") and not b.marked_for_deconstruction and b.reserved_by is None:
                    if kind not in b.inventory and len(b.inventory.keys()) >= b.max_types: continue
                    space = b.capacity - b.inventory.get(kind, 0)
                    if space > 0: cabinet = b; take_amt = min(stack.amount, space); break
            dst = (0, 0)
            if cabinet:
                dst = (cabinet.tx, cabinet.ty)
            else:
                sp_dst = self._find_dst_slot(items, stockpiles)
                if not sp_dst: continue
                dst, take_amt = sp_dst, stack.amount
            if self.assign_haul(world, items, stockpiles, tx, ty, dst[0], dst[1], kind, take_amt, cabinet):
                if cabinet: cabinet.reserved_by = self.id
                return True
        return False

    def _try_build(self, world, buildings, items, stockpiles):
        unassigned_bps = set(bp for bp in buildings.blueprints.values() if bp.reserved_by is None)
        cur_x, cur_y = self.current_tile()
        for bp in sorted(list(unassigned_bps), key=lambda bp: abs(bp.tx - cur_x) + abs(bp.ty - cur_y)):
            if self.assign_build(world, buildings, items, stockpiles, bp):
                new_lock = (bp.tx, bp.ty, bp.layer)
                if self.build_lock != new_lock:
                    self.build_lock = new_lock
                    self.build_lock_timer = 0.0
                return True
        return False

    def _find_dst_slot(self, items, stockpiles):
        for sp in stockpiles.stockpiles:
            for (tx, ty) in sp.tiles():
                if not items.get_at(tx, ty): return (tx, ty)
        return None

    def assign_attack(self, enemy):
        self.target_enemy = enemy
        # 玩家指定的攻击目标 -> 上战斗锁
        self.combat_lock = enemy
        self.combat_lock_timer = 0.0
        return True

    def enqueue_command(self, cmd):
        self.queue.append(cmd)

    def _pop_next_command(self):
        while self.queue:
            cmd = self.queue.pop(0)
            if cmd["type"] == "move" and self.move_to(cmd.get("world"), cmd["tx"], cmd["ty"]):
                return True
            elif cmd["type"] == "harvest" and self.assign_harvest(cmd["world"], cmd["tx"], cmd["ty"]):
                return True
            elif cmd["type"] == "build" and self.assign_build(cmd["world"], cmd["buildings"], cmd["items"],
                                                              cmd["stockpiles"], cmd["bp"]):
                return True
            elif cmd["type"] == "attack":
                self.assign_attack(cmd["enemy"]); return True
            elif cmd["type"] == "hunt":
                self.assign_hunt(cmd["animal"]); return True
            elif cmd["type"] == "craft":
                if self.assign_craft(cmd["world"], cmd["items"], cmd["stockpiles"], cmd["buildings"],
                                     cmd["bench"]): return True
            elif cmd["type"] == "equip_from_ground":
                if self.assign_equip_from_ground(cmd["world"], cmd["items"], cmd["tx"], cmd["ty"],
                                                 cmd["kind"]): return True
        return False

    def update(self, dt, world=None, items=None, stockpiles=None, buildings=None, enemies=None, game_time=None,
               research=None):
        self.cooldown_timer = max(0, self.cooldown_timer - dt)
        self.hit_flash = max(0, self.hit_flash - dt)
        if self.hp <= 0: return

        # 战斗锁维护：目标死了/消失了就清锁；否则保持锁定
        if self.combat_lock is not None:
            if self.combat_lock.hp <= 0:
                self.combat_lock = None
                self.combat_lock_timer = 0.0
            else:
                self.combat_lock_timer += dt
                # 目标被意外清掉时，重新绑定
                if self.target_enemy is None or self.target_enemy.hp <= 0:
                    self.target_enemy = self.combat_lock
                # 30 秒都打不死（比如目标卡死无法到达），自动放弃
                if self.combat_lock_timer > 30.0:
                    self.combat_lock = None
                    self.combat_lock_timer = 0.0

        # 建造锁超时释放
        if self.build_lock is not None:
            self.build_lock_timer += dt
            if self.build_lock_timer > 30.0:
                self.build_lock = None
                self.build_lock_timer = 0.0
                print(f"[建造锁超时] {self.name} 释放建造锁")

        # 防卡死机制
        moved = abs(self.x - self.last_pos[0]) > 0.1 or abs(self.y - self.last_pos[1]) > 0.1
        worked = abs(self.work_progress - self.last_prog) > 0.1
        # 玩家指定战斗期间，不触发防卡死（攻击冷却不算“卡死”）
        if self.combat_lock is not None:
            self.stuck_timer = 0.0
        elif not moved and not worked and self.state not in ("sleeping", "eating") and self.is_busy():
            self.stuck_timer += dt
        else:
            self.stuck_timer = 0.0
            self.last_pos = (self.x, self.y)
            self.last_prog = self.work_progress

        if self.stuck_timer > 1.5:
            self.stuck_timer = 0.0
            self._release_job()
            self.queue.clear()
            self.target_enemy = None
            self.target_animal = None
            self.state = None
            self.build_lock = None
            self.build_lock_timer = 0.0
            if self.carrying: self._drop_food(items)
            print(f"[防卡死] {self.name} 被强制重置")

        if world: self._push_out_of_wall(world)

        if self.is_patient and self.state == "sleeping": return

        if self.target_enemy is not None:
            e = self.target_enemy
            if e.hp <= 0:
                self.target_enemy = None
                if self.combat_lock is e:
                    self.combat_lock = None
                    self.combat_lock_timer = 0.0
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
                            mx, my = self.x + math.cos(self.facing_angle) * (self.radius + 12), self.y + math.sin(
                                self.facing_angle) * (self.radius + 12)
                            self.recent_shot = ("shot", mx, my, e.x, e.y, wdef["color"])
                        dead = e.take_damage(self.attack_damage, attacker=self)
                        self.cooldown_timer = self.attack_cooldown
                        if dead:
                            self.target_enemy = None
                            if self.combat_lock is e:
                                self.combat_lock = None
                                self.combat_lock_timer = 0.0
                    return
                elif not self.path:
                    adj = self._find_adjacent(world, self.current_tile(), *e.current_tile())
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
                        mx, my = self.x + math.cos(self.facing_angle) * (self.radius + 12), self.y + math.sin(
                            self.facing_angle) * (self.radius + 12)
                        self.recent_shot = ("shot", mx, my, a.x, a.y, (255, 150, 100))
                        dead = a.take_damage(self.attack_damage, attacker=self)
                        self.cooldown_timer = self.attack_cooldown
                        if dead:
                            self.target_animal = None
                            if items:
                                items.add(a.drop_item, a.drop_amount, *a.current_tile())
                                if a.species == "deer": items.add("leather", 3, *a.current_tile())
                    return
                elif not self.path:
                    adj = self._find_adjacent(world, self.current_tile(), *a.current_tile())
                    if adj:
                        p = astar(world, self.current_tile(), adj)
                        if p is not None: self.path = p

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
                        food_kind = k
                        cab.remove_item(k, 1)
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
            if not food_kind: self.state = None; return
            self.state, self.state_timer = "eating", 0.8
            if food_kind == "meal_fine":
                self.satiety = min(100, self.satiety + 100);
                self.mood = min(100, self.mood + 15)
            elif food_kind == "meal_simple":
                self.satiety = min(100, self.satiety + 50);
                self.mood = min(100, self.mood + 5)
            elif food_kind == "meat":
                self.satiety = min(100, self.satiety + 15)
            else:
                self.satiety = min(100, self.satiety + 10)
            return
        if self.state == "going_to_sleep": self.state = "sleeping"

    def _update_job(self, dt, world, items, stockpiles, buildings, research):
        j = self.job
        jt = j["type"]

        if jt == "build":
            if j["bp"].reserved_by != self.id or (j["bp"].tx, j["bp"].ty, j["bp"].layer) not in buildings.blueprints:
                if self.build_lock == (j["bp"].tx, j["bp"].ty, j["bp"].layer):
                    self.build_lock = None
                    self.build_lock_timer = 0.0
                self._release_job()
                return

        if jt == "doctor":
            patient = j["patient"]
            if j["stage"] == "to_patient":
                if patient.hp <= 0 or patient.bleeding <= 0 or not patient.is_patient:
                    self._release_job()
                    return
                if self.current_tile() == patient.current_tile() or self._find_adjacent(world, self.current_tile(),
                                                                                        *patient.current_tile()):
                    self.work_progress += self.work_speed * dt
                    if self.work_progress >= 40.0:
                        src = self._find_material_source(items, stockpiles, buildings, {"medicine": 1})
                        if src:
                            src_tx, src_ty, src_kind, cab = src
                            if cab:
                                cab.remove_item("medicine", 1)
                            else:
                                for s in items.get_at(src_tx, src_ty):
                                    if s.kind == "medicine":
                                        s.amount -= 1
                                        if s.amount <= 0: items.remove_at(src_tx, src_ty)
                                        break
                            patient.hp = min(patient.max_hp, patient.hp + 30)
                            patient.bleeding = 0.0
                            patient.mood = min(100, patient.mood + 20)
                            if patient.is_patient:
                                patient._wake_up()
                                patient.is_patient = False
                        self._release_job()
                else:
                    self._release_job()

        elif jt == "equip_from_ground":
            if j["stage"] == "to_item":
                if self.current_tile() == (j["tx"], j["ty"]) or self._find_adjacent(world, self.current_tile(), j["tx"],
                                                                                    j["ty"]):
                    found = False
                    for s in items.get_at(j["tx"], j["ty"]):
                        if s.kind == j["kind"]:
                            s.amount -= 1
                            if s.amount <= 0: items.remove_at(j["tx"], j["ty"])
                            found = True
                            break
                    if found:
                        if self.weapon_key != "fist":
                            items.add(self.weapon_key, 1, *self.current_tile())
                        self.equip_weapon(j["kind"])
                    self._release_job()
                else:
                    self._release_job()
            return


        elif jt == "take_from_cabinet":
            cabinet = j["cabinet"]
            kind = j["kind"]
            want_amt = j.get("amount", 999)
            if cabinet.marked_for_deconstruction or cabinet.inventory.get(kind, 0) <= 0:
                self._release_job()
                return
            if j["stage"] == "to_cabinet":
                if self.current_tile() == (cabinet.tx, cabinet.ty) or self._find_adjacent(world, self.current_tile(),
                                                                                cabinet.tx, cabinet.ty):
                    avail = cabinet.inventory.get(kind, 0)
                    take_amt = min(avail, want_amt)
                    if cabinet.remove_item(kind, take_amt):
                        if kind in ("axe", "stone_pickaxe", "iron_pickaxe", "longsword", "gun"):
                            new_w = get_weapon(kind)
                            curr_w = self.get_weapon_def()
                            if new_w["damage"] > curr_w["damage"] or self.weapon_key == "fist":
                                if self.weapon_key != "fist":
                                    items.add(self.weapon_key, 1, *self.current_tile())
                                self.equip_weapon(kind)
                                if take_amt > 1:
                                    items.add(kind, take_amt - 1, *self.current_tile())
                                self._release_job()
                                return
                        self.carrying = {"kind": kind, "amount": take_amt}
                        j["stage"] = "storing"
                        self._find_storage_target(world, items, stockpiles, buildings, j)
                else:
                    self._release_job()
            elif j["stage"] == "storing":
                if not self.carrying: self._release_job(); return
                if j.get("target_kind") == "cabinet":
                    b = j["target_obj"]
                    if b and not b.marked_for_deconstruction:
                        space = b.capacity - b.inventory.get(self.carrying["kind"], 0)
                        put_amt = min(self.carrying["amount"], space)
                        if put_amt > 0: b.add_item(self.carrying["kind"], put_amt); self.carrying["amount"] -= put_amt
                        b.reserved_by = None
                        if self.carrying and self.carrying["amount"] > 0: self._drop_food(items)
                        self.carrying = None;
                        self._release_job()
                    else:
                        if b: b.reserved_by = None
                        self._find_storage_target(world, items, stockpiles, buildings, j)
                elif j.get("target_kind") == "ground":
                    tx, ty = j["target_pos"];
                    items.add(self.carrying["kind"], self.carrying["amount"], tx, ty)
                    self.carrying = None;
                    self._release_job()
                else:
                    self._drop_food(items); self._release_job()

        elif jt == "harvest":
            if not world.is_harvestable(j["tx"], j["ty"]): self._release_job(); return
            if world.get(j["tx"], j["ty"]) == T_IRON_ROCK and self.weapon_key not in ("stone_pickaxe", "iron_pickaxe"):
                self._release_job()
                return
            self.work_progress += self.work_speed * dt
            while self.work_progress >= 10.0:
                self.work_progress -= 10.0
                dmg = 10
                wdef = self.get_weapon_def()
                t = world.get(j["tx"], j["ty"])
                if t == T_TREE and wdef.get("chop_bonus"): dmg *= 2.5
                if t in (T_ROCK, T_IRON_ROCK) and wdef.get("mine_bonus"): dmg *= 2.5
                done, kind, amt = world.damage_resource(j["tx"], j["ty"], int(dmg))
                if done:
                    if (j["tx"], j["ty"]) in Colonist._designated_harvests:
                        Colonist._designated_harvests.remove((j["tx"], j["ty"]))
                    if items is not None and kind is not None: items.add(kind, amt, j["tx"], j["ty"])
                    self._release_job()
                    break
        elif jt == "farm":
            farm = j["farm"]
            tx, ty = j["tx"], j["ty"]
            if (tx, ty) not in farm.plots: self._release_job(); return
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
                    items.add("food" if farm.plant_type == "berry" else "wood", 3 if farm.plant_type == "berry" else 5,
                              tx, ty)
                    data["planted"], data["growth"] = False, 0.0
                    self._release_job()
        elif jt == "deconstruct":
            tx, ty, layer = j["tx"], j["ty"], j["layer"]
            b = buildings.get_building_at(tx, ty)
            if not b or not b.marked_for_deconstruction: self._release_job(); return
            self.work_progress += self.work_speed * dt
            b.deconstruct_progress += self.work_speed * dt
            if b.deconstruct_progress >= b.deconstruct_needed:
                for k, v in BUILDING_DEFS[b.kind]["variants"][b.material]["cost"].items():
                    items.add(k, max(1, v // 2), tx, ty)
                buildings.remove_building(tx, ty, layer)
                self._release_job()
        elif jt == "research":
            b = buildings.get_building_at(j["tx"], j["ty"])
            if not b or b.marked_for_deconstruction or not research or not research.current_research:
                self._release_job()
                return
            self.work_progress += self.work_speed * dt
            research.add_progress(self.work_speed * 0.1 * dt)

        elif jt == "cook":
            stove = j["stove"]
            if j["stage"] != "storing" and (not stove.cook_queue or stove.marked_for_deconstruction):
                self._release_job()
                return

            if j["stage"] == "to_material":
                self.work_progress += self.work_speed * dt * 2
                if self.work_progress >= 10.0:
                    self.work_progress = 0.0
                    tx, ty = j["mat_src"]
                    kind = j["mat_kind"]
                    found = j["cabinet"].remove_item(kind, 1) if j.get("cabinet") else False
                    if not j.get("cabinet"):
                        for s in items.get_at(tx, ty):
                            if s.kind == kind:
                                s.amount -= 1
                                if s.amount <= 0: items.remove_at(tx, ty)
                                found = True
                                break
                    if not found: self._release_job(); return
                    if not self.carrying:
                        self.carrying = {"kind": kind, "amount": 1}
                    elif self.carrying["kind"] == kind:
                        self.carrying["amount"] += 1
                    else:
                        self._release_job();
                        return
                    adj = self._find_adjacent(world, self.current_tile(), stove.tx, stove.ty)
                    if adj:
                        p = astar(world, self.current_tile(), adj)
                        if p: self.path = p; j["stage"] = "deliver"; return
                    self._release_job()
            elif j["stage"] == "deliver":
                if self.carrying and self.carrying["kind"] in ("meat", "food"):
                    stove.delivered_ingredients[self.carrying["kind"]] = stove.delivered_ingredients.get(
                        self.carrying["kind"], 0) + self.carrying["amount"]
                    self.carrying = None
                    task = stove.cook_queue[0]
                    meal = task["meal"]
                    is_enough = (meal == "meal_simple" and sum(stove.delivered_ingredients.values()) >= 2) or \
                                (meal == "meal_fine" and sum(stove.delivered_ingredients.values()) >= 4)
                    if is_enough:
                        j["stage"] = "cooking"
                        self.work_progress = 0.0
                    else:
                        j["stage"] = "to_material"
                        need = ["meat", "food"]
                        if meal == "meal_fine":
                            if stove.delivered_ingredients.get("meat", 0) >= 2:
                                need = ["food"]
                            elif stove.delivered_ingredients.get("food", 0) >= 2:
                                need = ["meat"]
                        src = self._find_food_ingredient(items, stockpiles, buildings, need)
                        if src:
                            src_tx, src_ty, src_kind, cab = src
                            adj = self._find_adjacent(world, self.current_tile(), src_tx, src_ty)
                            if adj:
                                p = astar(world, self.current_tile(), adj)
                                if p: self.path = p; j["mat_src"] = (src_tx, src_ty); j["mat_kind"] = src_kind; j[
                                    "cabinet"] = cab; return
                        self._release_job()
                else:
                    self._release_job()
            elif j["stage"] == "cooking":
                self.work_progress += self.work_speed * dt
                stove.cook_progress = self.work_progress
                if self.work_progress >= 100.0:
                    task = stove.cook_queue.pop(0)
                    meal_kind = "meal_simple" if task["meal"] == "meal_simple" else "meal_fine"
                    if task["meal"] == "meal_simple":
                        cnt = 0
                        for k in ["meat", "food"]:
                            while stove.delivered_ingredients.get(k, 0) > 0 and cnt < 2:
                                stove.delivered_ingredients[k] -= 1
                                cnt += 1
                            if cnt >= 2: break
                    else:
                        stove.delivered_ingredients["meat"] = max(0, stove.delivered_ingredients.get("meat", 0) - 2)
                        stove.delivered_ingredients["food"] = max(0, stove.delivered_ingredients.get("food", 0) - 2)

                    if not self.carrying:
                        self.carrying = {"kind": meal_kind, "amount": 1}
                    elif self.carrying["kind"] == meal_kind:
                        self.carrying["amount"] += 1
                    self.work_progress, stove.cook_progress = 0.0, 0.0
                    j["stage"] = "storing"
                    self._find_storage_target(world, items, stockpiles, buildings, j)
                    return
            elif j["stage"] == "storing":
                if not self.carrying: self._release_job(); return
                if j.get("target_kind") == "cabinet":
                    b = j["target_obj"]
                    if b and not b.marked_for_deconstruction:
                        space = b.capacity - b.inventory.get(self.carrying["kind"], 0)
                        put_amt = min(self.carrying["amount"], space)
                        if put_amt > 0: b.add_item(self.carrying["kind"], put_amt); self.carrying["amount"] -= put_amt
                        b.reserved_by = None
                        if self.carrying and self.carrying["amount"] > 0: self._drop_food(items)
                        self.carrying = None
                        self._release_job()
                    else:
                        if b: b.reserved_by = None
                        self._find_storage_target(world, items, stockpiles, buildings, j)
                elif j.get("target_kind") == "ground":
                    tx, ty = j["target_pos"]
                    items.add(self.carrying["kind"], self.carrying["amount"], tx, ty)
                    self.carrying = None
                    self._release_job()
                else:
                    self._drop_food(items)
                    self._release_job()

        elif jt == "craft":
            bench = j["bench"]
            if not bench.craft_queue or bench.marked_for_deconstruction: self._release_job(); return
            task = bench.craft_queue[0]["item"]
            need = {"iron": 5} if task == "gun" else (
                {"iron": 3} if task == "longsword" else ({"stone": 2} if task == "stone_pickaxe" else {"iron": 2}))

            if j["stage"] == "to_material":
                self.work_progress += self.work_speed * dt * 2
                if self.work_progress >= 10.0:
                    self.work_progress = 0.0
                    tx, ty = j["mat_src"]
                    kind = j["mat_kind"]
                    found = j["cabinet"].remove_item(kind, 1) if j.get("cabinet") else False
                    if not j.get("cabinet"):
                        for s in items.get_at(tx, ty):
                            if s.kind == kind:
                                s.amount -= 1
                                if s.amount <= 0: items.remove_at(tx, ty)
                                found = True
                                break
                    if not found: self._release_job(); return
                    if not self.carrying:
                        self.carrying = {"kind": kind, "amount": 1}
                    elif self.carrying["kind"] == kind:
                        self.carrying["amount"] += 1
                    adj = self._find_adjacent(world, self.current_tile(), bench.tx, bench.ty)
                    if adj:
                        p = astar(world, self.current_tile(), adj)
                        if p: self.path = p; j["stage"] = "deliver"; return
                    self._release_job()
            elif j["stage"] == "deliver":
                if self.carrying:
                    bench.delivered_materials[self.carrying["kind"]] = bench.delivered_materials.get(
                        self.carrying["kind"], 0) + self.carrying["amount"]
                    self.carrying = None
                is_enough = all(bench.delivered_materials.get(k, 0) >= v for k, v in need.items())
                if is_enough:
                    for k, v in need.items(): bench.delivered_materials[k] -= v
                    j["stage"] = "crafting"
                    self.work_progress = 0.0
                else:
                    j["stage"] = "to_material"
                    for k, v in need.items():
                        if bench.delivered_materials.get(k, 0) < v:
                            src = self._find_material_source(items, stockpiles, buildings, {k: 1})
                            if src:
                                src_tx, src_ty, src_kind, cab = src
                                adj = self._find_adjacent(world, self.current_tile(), src_tx, src_ty)
                                if adj:
                                    p = astar(world, self.current_tile(), adj)
                                    if p: self.path = p; j["mat_src"] = (src_tx, src_ty); j["mat_kind"] = src_kind; j[
                                        "cabinet"] = cab; return
                            self._release_job()
                            return
            elif j["stage"] == "crafting":
                self.work_progress += self.work_speed * dt
                bench.craft_progress = self.work_progress
                if self.work_progress >= 150.0:
                    bench.craft_queue.pop(0)
                    bench.craft_progress = 0.0
                    self.work_progress = 0.0
                    w_key = "axe" if task == "axe" else ("iron_pickaxe" if task == "iron_pickaxe" else (
                        "stone_pickaxe" if task == "stone_pickaxe" else (
                            "longsword" if task == "longsword" else "pistol")))

                    new_w = get_weapon(w_key)
                    curr_w = self.get_weapon_def()

                    if new_w["damage"] > curr_w["damage"] or self.weapon_key == "fist":
                        if self.weapon_key != "fist":
                            items.add(self.weapon_key, 1, *self.current_tile())
                        self.equip_weapon(w_key)
                    else:
                        items.add(w_key, 1, *self.current_tile())

                    if not bench.craft_queue or bench.marked_for_deconstruction:
                        self._release_job()
                    else:
                        j["stage"] = "to_material"
                        j["materials"] = {}
                        need = {"iron": 5} if bench.craft_queue[0]["item"] == "gun" else (
                            {"iron": 3} if bench.craft_queue[0]["item"] == "longsword" else (
                                {"stone": 2} if bench.craft_queue[0]["item"] == "stone_pickaxe" else {"iron": 2}))
                        src = self._find_material_source(items, stockpiles, buildings, need)
                        if src:
                            src_tx, src_ty, src_kind, cab = src
                            adj = self._find_adjacent(world, self.current_tile(), src_tx, src_ty)
                            if adj:
                                p = astar(world, self.current_tile(), adj)
                                if p: self.path = p; j["mat_src"] = (src_tx, src_ty); j["mat_kind"] = src_kind; j[
                                    "cabinet"] = cab; return
                        self._release_job()
            elif j["stage"] == "storing":
                if not self.carrying: self._release_job(); return
                if j.get("target_kind") == "cabinet":
                    b = j["target_obj"]
                    if b: b.add_item(self.carrying["kind"], self.carrying["amount"]); b.reserved_by = None
                    self.carrying = None
                    self._release_job()
                else:
                    self._drop_food(items)
                    self._release_job()

        elif jt == "smelt":
            furnace = j["furnace"]
            if not furnace.smelt_queue or furnace.marked_for_deconstruction: self._release_job(); return

            if j["stage"] == "to_material":
                self.work_progress += self.work_speed * dt * 2
                if self.work_progress >= 10.0:
                    self.work_progress = 0.0
                    tx, ty = j["mat_src"]
                    found = j["cabinet"].remove_item("iron_ore", 2) if j.get("cabinet") else False
                    if not j.get("cabinet"):
                        cnt = 0
                        for s in items.get_at(tx, ty):
                            if s.kind == "iron_ore" and cnt < 2:
                                take = min(s.amount, 2 - cnt)
                                s.amount -= take
                                cnt += take
                                if s.amount <= 0: items.remove_at(tx, ty)
                        found = cnt > 0
                    if not found: self._release_job(); return
                    if not self.carrying: self.carrying = {"kind": "iron_ore", "amount": 2}
                    adj = self._find_adjacent(world, self.current_tile(), furnace.tx, furnace.ty)
                    if adj:
                        p = astar(world, self.current_tile(), adj)
                        if p: self.path = p; j["stage"] = "deliver"; return
                    self._release_job()
            elif j["stage"] == "deliver":
                if self.carrying and self.carrying["kind"] == "iron_ore":
                    furnace.inventory["iron_ore"] = furnace.inventory.get("iron_ore", 0) + self.carrying["amount"]
                    self.carrying = None
                if furnace.inventory.get("iron_ore", 0) >= 2:
                    furnace.remove_item("iron_ore", 2)
                    j["stage"] = "smelting"
                    self.work_progress = 0.0
                else:
                    self._release_job()
            elif j["stage"] == "smelting":
                self.work_progress += self.work_speed * dt
                furnace.smelt_progress = self.work_progress
                if self.work_progress >= 150.0:
                    furnace.smelt_queue.pop(0)
                    furnace.smelt_progress = 0.0
                    self.work_progress = 0.0
                    if not self.carrying: self.carrying = {"kind": "iron", "amount": 2}
                    j["stage"] = "storing"
                    self._find_storage_target(world, items, stockpiles, buildings, j)

        elif jt == "haul":
            if j["stage"] == "to_src":
                self.work_progress += self.work_speed * dt * 2
                if self.work_progress >= 10.0:
                    self.work_progress = 0.0
                    tx, ty = j["src"]

                    if not self.carrying: self.carrying = {"kind": j["kind"], "amount": 0}

                    for s in items.get_at(tx, ty):
                        if s.kind == j["kind"]:
                            space = self.carry_limit - self.carrying["amount"]
                            take = min(s.amount, space)
                            if take > 0:
                                s.amount -= take
                                self.carrying["amount"] += take
                                if s.amount <= 0: items.remove_at(tx, ty)
                            if self.carrying["amount"] >= self.carry_limit: break

                    if self.carrying["amount"] == 0:
                        self._release_job()
                        return

                    if self.carrying["amount"] < self.carry_limit:
                        best_next = None
                        best_dist = 99999
                        cur_tile = self.current_tile()
                        for (ntx, nty, nkind), stack in items.stacks.items():
                            if nkind == j["kind"] and stack.amount > 0 and getattr(stack, "reserved_by", None) is None:
                                d = abs(ntx - cur_tile[0]) + abs(nty - cur_tile[1])
                                if d < best_dist:
                                    best_dist = d
                                    best_next = (ntx, nty)

                        if best_next:
                            j["src"] = best_next
                            stack = items.stacks[(best_next[0], best_next[1], j["kind"])]
                            stack.reserved_by = self.id
                            j["amount"] = min(stack.amount, self.carry_limit - self.carrying["amount"])
                            path = astar(world, self.current_tile(),
                                         self._find_adjacent(world, self.current_tile(), *best_next))
                            if path:
                                self.path = path
                                return

                    cab = j.get("cabinet")
                    path = astar(world, self.current_tile(),
                                 self._find_adjacent(world, self.current_tile(), cab.tx, cab.ty)) if cab else astar(
                        world, self.current_tile(), j["dst"])
                    if not path:
                        self._drop_food(items)
                        self._release_job()
                        return
                    self.path = path
                    j["stage"] = "to_dst"
            elif j["stage"] == "to_dst":
                self.work_progress += self.work_speed * dt * 2
                if self.work_progress >= 10.0:
                    self.work_progress = 0.0
                    cab = j.get("cabinet")
                    if cab:
                        space = cab.capacity - cab.inventory.get(j["kind"], 0)
                        put_amt = min(self.carrying["amount"], space)
                        if put_amt > 0:
                            cab.add_item(j["kind"], put_amt)
                            self.carrying["amount"] -= put_amt
                        cab.reserved_by = None
                        if self.carrying["amount"] > 0:
                            items.add(j["kind"], self.carrying["amount"], *self.current_tile())
                    else:
                        items.add(j["kind"], self.carrying["amount"], j["dst"][0], j["dst"][1])
                    self.carrying = None
                    self._release_job()
        elif jt == "build":
            bp = j["bp"]
            if j["stage"] == "to_material":
                self.work_progress += self.work_speed * dt * 2
                if self.work_progress >= 10.0:
                    self.work_progress = 0.0
                    tx, ty = j["mat_src"]
                    mat_kind = j["mat_kind"]
                    missing = bp.missing_materials().get(mat_kind, 0)
                    if missing <= 0: self._release_job(); return
                    target_take = min(missing, self.carry_limit)
                    if self.carrying: target_take -= self.carrying["amount"]
                    if target_take <= 0: self._release_job(); return
                    total_taken = 0
                    cab = j.get("cabinet")
                    if cab:
                        avail = cab.inventory.get(mat_kind, 0)
                        take = min(avail, target_take)
                        if take > 0: cab.remove_item(mat_kind, take); total_taken = take
                    else:
                        for s in items.get_at(tx, ty):
                            if s.kind == mat_kind:
                                take = min(s.amount, target_take - total_taken)
                                s.amount -= take
                                if s.amount <= 0: items.remove_at(tx, ty)
                                total_taken += take
                                if total_taken >= target_take: break
                    if total_taken == 0: self._release_job(); return
                    if not self.carrying: self.carrying = {"kind": mat_kind, "amount": 0}
                    self.carrying["amount"] += total_taken
                    adj = self._find_adjacent_for_build(world, self.current_tile(), bp)
                    if not adj: self._release_job(); return
                    path = astar(world, self.current_tile(), adj)
                    if not path: self._release_job(); return
                    self.path = path
                    j["stage"] = "to_build"
            elif j["stage"] == "to_build":
                if self.carrying:
                    bp.delivered_materials[self.carrying["kind"]] = bp.delivered_materials.get(self.carrying["kind"],
                                                                                               0) + self.carrying[
                                                                        "amount"]
                    self.carrying = None

                if j.get("cleared") != True:
                    all_clear = True
                    for dy in range(bp.h):
                        for dx in range(bp.w):
                            if world.is_harvestable(bp.tx + dx, bp.ty + dy):
                                all_clear = False
                                self.work_progress += self.work_speed * dt
                                while self.work_progress >= 10.0:
                                    self.work_progress -= 10.0
                                    done, kind, amt = world.damage_resource(bp.tx + dx, bp.ty + dy, 10)
                                    if done:
                                        if items is not None and kind is not None:
                                            items.add(kind, amt, bp.tx + dx, bp.ty + dy)
                                        break
                                return
                    if all_clear: j["cleared"] = True

                if bp.has_all_materials():
                    self.work_progress += self.work_speed * dt
                    bp.work_done += self.work_speed * dt
                    if bp.is_complete():
                        buildings.complete_blueprint(bp)
                        self.carrying = None
                        self.build_lock = None
                        self.build_lock_timer = 0.0
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
                            if p: self.path = p; j["stage"] = "to_material"; j["mat_src"] = (src_tx, src_ty); j[
                                "mat_kind"] = src_kind; j["cabinet"] = cab; return
                    self._release_job()

    def _find_storage_target(self, world, items, stockpiles, buildings, j):
        meal_kind = self.carrying["kind"]
        seen_b = set()
        for b in buildings.buildings.values():
            if id(b) in seen_b: continue
            seen_b.add(id(b))
            if b.kind in ("small_cabinet",
                          "large_cabinet") and not b.marked_for_deconstruction and b.reserved_by is None:
                if meal_kind not in b.inventory and len(b.inventory.keys()) >= b.max_types: continue
                space = b.capacity - b.inventory.get(meal_kind, 0)
                if space > 0:
                    adj = self._find_adjacent(world, self.current_tile(), b.tx, b.ty)
                    if adj:
                        p = astar(world, self.current_tile(), adj)
                        if p: self.path = p; b.reserved_by = self.id; j["target_kind"] = "cabinet"; j[
                            "target_obj"] = b; return
        sp_dst = self._find_dst_slot(items, stockpiles)
        if sp_dst:
            adj = self._find_adjacent(world, self.current_tile(), sp_dst[0], sp_dst[1])
            if not adj and world.is_walkable(sp_dst[0], sp_dst[1]): adj = sp_dst
            if adj:
                if adj == self.current_tile(): j["target_kind"] = "ground"; j["target_pos"] = sp_dst; return
                p = astar(world, self.current_tile(), adj)
                if p is not None: self.path = p; j["target_kind"] = "ground"; j["target_pos"] = sp_dst; return
        self._drop_food(items)

    def _drop_food(self, items):
        if self.carrying:
            tx, ty = self.current_tile()
            items.add(self.carrying["kind"], self.carrying["amount"], tx, ty)
            self.carrying = None

    def _release_job(self):
        if self.job:
            if self.job.get("type") == "build":
                bp = self.job.get("bp")
                if bp and bp.reserved_by == self.id: bp.reserved_by = None
            elif self.job.get("type") in ("cook", "craft", "smelt"):
                bldg_key = "stove" if self.job["type"] == "cook" else (
                    "bench" if self.job["type"] == "craft" else "furnace")
                bldg = self.job.get(bldg_key)
                if bldg and bldg.reserved_by == self.id: bldg.reserved_by = None
                if bldg and hasattr(bldg, "cook_progress"): bldg.cook_progress = 0.0
                if bldg and hasattr(bldg, "craft_progress"): bldg.craft_progress = 0.0
                if self.job.get("stage") == "storing":
                    b = self.job.get("target_obj")
                    if b and b.reserved_by == self.id: b.reserved_by = None
            elif self.job.get("type") == "farm":
                farm = self.job.get("farm")
                tx, ty = self.job["tx"], self.job["ty"]
                if farm and (tx, ty) in farm.plots: farm.plots[(tx, ty)]["reserved_by"] = None
            elif self.job.get("type") == "harvest":
                tx, ty = self.job.get("tx"), self.job.get("ty")
                if (tx, ty) in Colonist._reserved_harvests: Colonist._reserved_harvests.remove((tx, ty))
            elif self.job.get("type") == "haul":
                cab = self.job.get("cabinet")
                if cab: cab.reserved_by = None
            elif self.job.get("type") == "research":
                tx, ty = self.job["tx"], self.job["ty"]
                if Colonist._buildings_ref:
                    b = Colonist._buildings_ref.get_building_at(tx, ty)
                    if b and b.reserved_by == self.id: b.reserved_by = None
        self.job, self.work_progress, self.path = None, 0.0, []

        if self.carrying:
            self._drop_food(Colonist._items_ref)

        if self.state in ("going_to_eat", "going_to_sleep"):
            self.state = None

        # 玩家发起新任务时会先调 _release_job，同步清掉战斗锁定
        self.combat_lock = None
        self.combat_lock_timer = 0.0

    def draw(self, surface, camera, font):
        if self.hp <= 0: return
        sx, sy = camera.world_to_screen(self.x, self.y)
        if self.selected: pygame.draw.circle(surface, SELECT, (int(sx), int(sy)), self.radius + 6, 2)
        draw_weapon(surface, sx, sy, self.facing_angle, self.get_weapon_def(), 1.0)
        pygame.draw.circle(surface, (255, 200, 100) if self.hit_flash > 0 else self.color, (int(sx), int(sy)),
                           self.radius)
        pygame.draw.circle(surface, (0, 0, 0), (int(sx), int(sy)), self.radius, 2)
        pygame.draw.rect(surface, (60, 0, 0), (int(sx - self.radius), int(sy - self.radius - 10), self.radius * 2, 4))
        pygame.draw.rect(surface, (60, 200, 60), (int(sx - self.radius), int(sy - self.radius - 10),
                                                  int((self.radius * 2) * (self.hp / self.max_hp)), 4))
        surface.blit(font.render(self.name, True, WHITE), (sx - font.size(self.name)[0] / 2, sy + self.radius + 2))

        if self.carrying:
            c_kind = self.carrying["kind"]
            c_color = ITEM_DEFS.get(c_kind, {"color": (200, 200, 200)})["color"]
            pygame.draw.rect(surface, c_color, (sx + self.radius, sy - self.radius - 6, 14, 14))
            pygame.draw.rect(surface, (0, 0, 0), (sx + self.radius, sy - self.radius - 6, 14, 14), 1)
            surface.blit(font.render(str(self.carrying["amount"]), True, WHITE),
                         (sx + self.radius + 16, sy - self.radius - 10))

        label, color = None, (200, 200, 200)
        if self.is_patient:
            label, color = "病患", (255, 100, 100)
        elif self.state == "sleeping":
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
                      "cook": "烹饪", "farm": "农业", "craft": "制作", "smelt": "熔炼", "doctor": "医疗",
                      "take_from_cabinet": "取物", "equip_from_ground": "拾取装备"}
            label, color = labels.get(self.job["type"], "工作"), (255, 220, 100)
        if label: surface.blit(font.render(label, True, color), (sx - font.size(label)[0] / 2, sy + self.radius + 20))
        if self.state == "sleeping":
            for off in [(20, -20), (28, -32), (36, -44)]: surface.blit(font.render("Z", True, (200, 220, 255)),
                                                                       (sx + off[0], sy + off[1]))

    def draw_path(self, surface, camera, world):
        if not self.path and not self.queue and self.target_enemy is None and self.target_animal is None: return
        current_color = (255, 80, 80) if (self.target_enemy or self.target_animal) else (
            (255, 255, 80) if (self.job and self.job["type"] == "move") else (80, 255, 80))
        last_pt, last_tile = (self.x, self.y), self.current_tile()
        if self.path:
            pts = [last_pt] + [(tx * TILE_SIZE + TILE_SIZE / 2, ty * TILE_SIZE + TILE_SIZE / 2) for tx, ty in self.path]
            screen_pts = [camera.world_to_screen(x, y) for (x, y) in pts]
            if len(screen_pts) >= 2: pygame.draw.lines(surface, current_color, False, screen_pts, 2)
            last_pt, last_tile = pts[-1], self.path[-1]