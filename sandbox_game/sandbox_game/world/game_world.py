# world/game_world.py
import random
import pygame

from settings import MAP_WIDTH, MAP_HEIGHT, TILE_SIZE, BLACK, WHITE
from core.camera import Camera
from core.time_system import GameTime
from world.world import World
from world.items import ItemManager, ITEM_DEFS
from world.stockpile import StockpileManager
from world.farm import FarmManager
from world.buildings import BuildingManager, BUILDING_DEFS
from ui.selection import Selection
from ui.hud import HUD
from ui.building_hud import BuildingHUD
from ui.stockpile_hud import StockpileHUD
from ui.item_hud import ItemHUD
from ui.build_menu import BuildMenu
from ui.toolbar import Toolbar
from ui.research_menu import ResearchMenu
from entities.colonist import Colonist
from entities.enemy import Enemy
from entities.animal import Animal
from combat.effects import Shot, MeleeHit, CombatLog
from systems.research import ResearchManager
from world.rooms import RoomManager


class GameWorld:
    def __init__(self, font, font_big, font_small, font_warn, screen_w, screen_h, seed=None):
        self.font = font
        self.font_big = font_big
        self.font_small = font_small
        self.font_warn = font_warn

        self.rng = random.Random(seed if seed is not None else 42)
        self.seed = seed

        self.game_time = GameTime(day_length_sec=120.0, start_hour=7.0)
        self.research_mgr = ResearchManager()

        self.world = World(MAP_WIDTH, MAP_HEIGHT)
        self.items = ItemManager()
        self.stockpiles = StockpileManager()
        self.farms = FarmManager()
        self.buildings = BuildingManager(self.research_mgr)
        self.world.buildings = self.buildings

        self.room_mgr = RoomManager(self.world, self.buildings)
        Colonist._room_mgr_ref = self.room_mgr

        self.camera = Camera(screen_w, screen_h, MAP_WIDTH * TILE_SIZE, MAP_HEIGHT * TILE_SIZE)
        self.camera.x = (MAP_WIDTH * TILE_SIZE - screen_w) / 2
        self.camera.y = (MAP_HEIGHT * TILE_SIZE - screen_h) / 2

        # ---- UI ----
        self.selection = Selection()
        self.hud = HUD(font)
        self.bhud = BuildingHUD(font, screen_w)
        self.shud = StockpileHUD(font)
        self.ihud = ItemHUD(font)
        self.build_menu = BuildMenu(font)
        self.toolbar = Toolbar(font)
        self.research_menu = ResearchMenu(font)
        self.log = CombatLog()

        # ---- 实体 ----
        self.colonists = []
        self.enemies = []
        self.animals = []
        self.effects = []

        base_x = MAP_WIDTH // 2
        base_y = MAP_HEIGHT // 2 - 5
        for i in range(3):
            found = None
            for dy in range(-2, 3):
                for dx in range(-3, 4):
                    tx, ty = base_x + i * 2 + dx, base_y + dy
                    if self.world.is_walkable(tx, ty):
                        found = (tx, ty)
                        break
                if found: break
            if not found: found = (base_x, base_y)
            self.colonists.append(Colonist(*found, weapon_key="fist"))

        Colonist._all_colonists = self.colonists
        Colonist._items_ref = self.items
        Colonist._buildings_ref = self.buildings

        spawn_attempts = 0
        while len(self.animals) < 15 and spawn_attempts < 200:
            spawn_attempts += 1
            ax, ay = random.randint(5, MAP_WIDTH - 5), random.randint(5, MAP_HEIGHT - 5)
            if self.world.is_walkable(ax, ay):
                is_safe = True
                for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                    if not self.world.is_walkable(ax + dx, ay + dy):
                        is_safe = False; break
                if is_safe:
                    self.animals.append(Animal(ax, ay, random.choice(["rabbit", "rabbit", "deer", "deer", "deer"])))

        # ---- 计时器 ----
        self.animal_respawn_timer = 10.0
        self.MAX_ANIMALS = 20
        self.enemy_invasion_timer = self.game_time.day_length_sec * 3

        # ---- 游戏状态 ----
        self.mode = None
        self.current_build_kind = None
        self.current_build_mat = None
        self.build_rotation = 0
        self.show_help = False
        self.show_beauty = False

        self.pending_farm_rect = None
        self.selected_building = None
        self.selected_stockpile = None
        self.selected_item_stack = None

        self.drag_start = None
        self.drag_end = None
        self.dragging_cam_right = False
        self.right_down_pos = (0, 0)
        self.last_mouse = (0, 0)
        self.left_down_pos = None
        self.left_drag_moved = False
        self.game_speed = 1.0
        self.warning_timer = 0.0
        self.warning_text = ""

    def selected_colonists(self):
        return [c for c in self.colonists if c.selected]

    def is_mouse_in_ui(self, mouse_pos):
        selected_cols = self.selected_colonists()
        if self.hud.panel_rect.collidepoint(mouse_pos) and selected_cols: return True
        if self.bhud.panel_rect.collidepoint(mouse_pos) and self.selected_building: return True
        if self.shud.panel_rect.collidepoint(mouse_pos) and self.selected_stockpile: return True
        if self.ihud.panel_rect.collidepoint(mouse_pos) and self.selected_item_stack: return True
        return False

    def get_global_items(self):
        out = {}
        for s in self.items.stacks.values():
            out[s.kind] = out.get(s.kind, 0) + s.amount
        seen = set()
        for b in self.buildings.buildings.values():
            if id(b) in seen: continue
            seen.add(id(b))
            if b.kind in ("small_cabinet", "large_cabinet"):
                for k, amt in b.inventory.items():
                    out[k] = out.get(k, 0) + amt
        return out

    def get_totals(self):
        totals = {}
        for s in self.items.stacks.values():
            totals[s.kind] = totals.get(s.kind, 0) + s.amount
        seen = set()
        for b in self.buildings.buildings.values():
            if id(b) in seen: continue
            seen.add(id(b))
            if b.kind in ("small_cabinet", "large_cabinet"):
                for k, amt in b.inventory.items():
                    totals[k] = totals.get(k, 0) + amt
        return totals

    def get_bottom_ui_height(self):
        h = self.toolbar.height
        if self.mode == "build":
            h += self.build_menu.height
            if self.build_menu.active_kind:
                h += self.build_menu.sub_height
        return h

    def clear_selection(self):
        for c in self.colonists: c.selected = False
        self.selected_building = None
        self.selected_stockpile = None
        self.selected_item_stack = None
        self.selection.clear()

    def set_screen_size(self, w, h):
        self.camera.resize(w, h)
        self.bhud.panel_rect.x = w - self.bhud.panel_w - 20

    def handle_event(self, event, screen_w, screen_h):
        mouse_pos = pygame.mouse.get_pos()
        shift_held = bool(pygame.key.get_mods() & pygame.KMOD_SHIFT)
        mouse_in_ui = self.is_mouse_in_ui(mouse_pos)

        if event.type == pygame.VIDEORESIZE:
            return

        if event.type == pygame.KEYDOWN:
            if self.bhud.handle_key(event, self.selected_building): return
            self._handle_keydown(event, mouse_pos, screen_w, screen_h)
            return

        if event.type == pygame.TEXTINPUT:
            self.bhud.handle_text(event, self.selected_building)
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            if self.bhud.handle_right_click(event.pos, self.selected_building): return
            if not mouse_in_ui:
                self.dragging_cam_right = True
                self.right_down_pos = event.pos
                self.last_mouse = event.pos
            return

        if event.type == pygame.MOUSEMOTION:
            if self.dragging_cam_right:
                dx, dy = event.pos[0] - self.last_mouse[0], event.pos[1] - self.last_mouse[1]
                self.camera.move_by(-dx, -dy)
                self.last_mouse = event.pos
                return
            # 注意这里去掉了 return，让后面的代码能处理鼠标移动（框选拖拽等）

        if event.type == pygame.MOUSEBUTTONUP and event.button == 3:
            if self.dragging_cam_right:
                self.dragging_cam_right = False
                dist = abs(event.pos[0] - self.right_down_pos[0]) + abs(event.pos[1] - self.right_down_pos[1])
                if dist < 15 and self.mode is None and not self.show_help and not mouse_in_ui:
                    self._handle_right_click(event.pos, shift_held)
            return

        if self.mode == "farm" and self.pending_farm_rect:
            self._handle_farm_popup(event, screen_w, screen_h)
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            selected_cols = self.selected_colonists()
            if self.hud.handle_click(event.pos, selected_cols):
                self.left_down_pos = None; return

            consumed, action = self.bhud.handle_click(event.pos, self.selected_building,
                                                      self.get_global_items(), self.research_mgr)
            if consumed:
                self._handle_building_hud_action(action)
                self.left_down_pos = None; return

            consumed_sp, delete_sp = self.shud.handle_click(event.pos)
            if consumed_sp:
                if delete_sp and self.selected_stockpile in self.stockpiles.stockpiles:
                    self.stockpiles.stockpiles.remove(self.selected_stockpile)
                    self.selected_stockpile = None
                self.left_down_pos = None; return

            if self.ihud.handle_click(event.pos):
                self.left_down_pos = None; return

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if mouse_in_ui:
                self.left_down_pos = None; return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            clicked_mode = self.toolbar.handle_click(event.pos)
            if clicked_mode != "NOT_CLICKED":
                if clicked_mode == "close":
                    self.mode = None
                    self.current_build_kind = None
                    self.current_build_mat = None
                    self.build_menu.active_kind = None
                elif self.mode == clicked_mode:
                    self.mode = None
                else:
                    self.mode = clicked_mode
                    self.current_build_kind = None
                    self.current_build_mat = None
                self.drag_start = None
                self.drag_end = None
                self.left_down_pos = None
                return
            bottom_h = self.get_bottom_ui_height()
            if self.mode == "build" and event.pos[1] > screen_h - bottom_h:
                k, m, is_selected = self.build_menu.handle_click(event.pos, self.research_mgr)
                if is_selected:
                    self.current_build_kind = k
                    self.current_build_mat = m
                    self.build_rotation = 0
                self.left_down_pos = None
                return
            if self.mode == "research":
                panel_w, panel_h = 600, 400
                rx, ry = screen_w // 2 - panel_w // 2, screen_h // 2 - panel_h // 2
                if rx <= event.pos[0] <= rx + panel_w and ry <= event.pos[1] <= ry + panel_h:
                    self.research_menu.handle_click(event.pos, self.research_mgr)
                    self.left_down_pos = None
                    return

        if self.show_help:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.show_help = False
            return

        if self.mode in ("stockpile", "build", "deconstruct", "farm", "harvest_area", "hunt_area"):
            self._handle_drag_mode(event, screen_w, screen_h)
            return

        if not self.dragging_cam_right:
            self._handle_selection(event, screen_w, screen_h, shift_held)

    def _handle_keydown(self, event, mouse_pos, screen_w, screen_h):
        if event.key == pygame.K_SPACE:
            if self.game_speed == 0.0: self.game_speed = 1.0
            elif self.game_speed == 1.0: self.game_speed = 2.0
            elif self.game_speed == 2.0: self.game_speed = 3.0
            else: self.game_speed = 0.0
            return
        if event.key == pygame.K_ESCAPE:
            if self.show_help:
                self.show_help = False
            elif self.mode is not None:
                self.mode = None
                self.current_build_kind = None
                self.current_build_mat = None
                self.build_menu.active_kind = None
                self.pending_farm_rect = None
            else:
                self.clear_selection()
            return
        if event.key == pygame.K_h:
            self.show_help = not self.show_help; return
        if event.key == pygame.K_t:
            self.show_beauty = not self.show_beauty; return
        if event.key == pygame.K_b:
            self.mode = "build" if self.mode != "build" else None
            self.current_build_kind = None
            self.current_build_mat = None
            self.build_menu.active_kind = None
            return
        if event.key == pygame.K_s:
            self.mode = "stockpile" if self.mode != "stockpile" else None; return
        if event.key == pygame.K_f:
            self.mode = "farm" if self.mode != "farm" else None
            self.pending_farm_rect = None; return
        if event.key == pygame.K_x:
            self.mode = "deconstruct" if self.mode != "deconstruct" else None; return
        if event.key == pygame.K_r:
            if self.mode == "build" and self.current_build_kind:
                data = BUILDING_DEFS[self.current_build_kind]
                if data["w"] != data["h"]:
                    self.build_rotation = (self.build_rotation + 1) % 2
            else:
                self.mode = "research" if self.mode != "research" else None
            return

    def _handle_right_click(self, pos, shift_held):
        selected = [c for c in self.colonists if c.selected and c.hp > 0]
        if not selected: return
        wx, wy = self.camera.screen_to_world(*pos)
        tx, ty = self.camera.screen_to_tile(*pos)

        hit_enemy = None
        for e in self.enemies:
            if (e.x - wx) ** 2 + (e.y - wy) ** 2 <= (e.radius + 12) ** 2:
                hit_enemy = e; break
        hit_animal = None
        for a in self.animals:
            if (a.x - wx) ** 2 + (a.y - wy) ** 2 <= (a.radius + 10) ** 2:
                hit_animal = a; break

        hit_item = None
        stacks_at_tile = self.items.get_at(tx, ty)
        if stacks_at_tile:
            hit_item = min(stacks_at_tile, key=lambda s: (s.x - wx) ** 2 + (s.y - wy) ** 2)

        if hit_enemy is not None:
            cmd = {"type": "attack", "enemy": hit_enemy}
            if not shift_held:
                for c in selected:
                    c._release_job(); c.queue.clear(); c.state = None
                    c.target_enemy = None; c.target_animal = None
                for c in selected: c.assign_attack(hit_enemy)
            else:
                for c in selected: c.enqueue_command(cmd)
        elif hit_animal is not None:
            cmd = {"type": "hunt", "animal": hit_animal}
            if not shift_held:
                for c in selected:
                    c._release_job(); c.queue.clear(); c.state = None
                    c.target_enemy = None; c.target_animal = None
                for c in selected: c.assign_hunt(hit_animal)
            else:
                for c in selected: c.enqueue_command(cmd)
        elif (self.buildings.get_building_at(tx, ty) and
              self.buildings.get_building_at(tx, ty).kind in ("small_cabinet", "large_cabinet")):
            cabinet = self.buildings.get_building_at(tx, ty)
            self.selected_building = cabinet
            self.selected_item_stack = None
            self.selected_stockpile = None
            for c in self.colonists: c.selected = False
            for c in selected: c.selected = True
        elif (self.buildings.get_building_at(tx, ty) and
              self.buildings.get_building_at(tx, ty).kind == "workbench"):
            bench = self.buildings.get_building_at(tx, ty)
            if bench.craft_queue:
                cmd = {"type": "craft", "world": self.world, "items": self.items,
                       "stockpiles": self.stockpiles, "buildings": self.buildings, "bench": bench}
                if not shift_held:
                    for c in selected:
                        c._release_job(); c.queue.clear(); c.state = None
                    selected[0].assign_craft(self.world, self.items, self.stockpiles, self.buildings, bench)
                else:
                    for c in selected: c.enqueue_command(cmd)
        elif hit_item is not None:
            equip_kinds = ["axe", "stone_pickaxe", "iron_pickaxe", "longsword", "gun", "pistol"]
            if hit_item.kind in equip_kinds:
                cmd = {"type": "equip_from_ground", "world": self.world, "items": self.items,
                       "tx": tx, "ty": ty, "kind": hit_item.kind}
                if not shift_held:
                    for c in selected:
                        c._release_job(); c.queue.clear(); c.state = None
                    selected[0].assign_equip_from_ground(self.world, self.items, tx, ty, hit_item.kind)
                else:
                    for c in selected: c.enqueue_command(cmd)
            else:
                cabinet = None
                seen_b = set()
                for b in self.buildings.buildings.values():
                    if id(b) in seen_b: continue
                    seen_b.add(id(b))
                    if b.kind in ("small_cabinet", "large_cabinet") and \
                       not b.marked_for_deconstruction and b.reserved_by is None:
                        current_types = len(b.inventory.keys())
                        if hit_item.kind not in b.inventory and current_types >= b.max_types: continue
                        space = b.capacity - b.inventory.get(hit_item.kind, 0)
                        if space > 0:
                            cabinet = b; break
                target_pos = (0, 0)
                if cabinet:
                    target_pos = (cabinet.tx, cabinet.ty)
                else:
                    sp_dst = selected[0]._find_dst_slot(self.items, self.stockpiles)
                    if sp_dst: target_pos = sp_dst
                if cabinet or target_pos != (0, 0):
                    cmd = {"type": "haul", "world": self.world, "items": self.items,
                           "stockpiles": self.stockpiles, "src": (tx, ty), "dst": target_pos,
                           "kind": hit_item.kind, "amount": selected[0].carry_limit, "cabinet": cabinet}
                    if not shift_held:
                        for c in selected:
                            c._release_job(); c.queue.clear(); c.state = None
                        selected[0].assign_haul(self.world, self.items, self.stockpiles,
                                                tx, ty, target_pos[0], target_pos[1],
                                                hit_item.kind, selected[0].carry_limit, cabinet)
                    else:
                        for c in selected: c.enqueue_command(cmd)
        elif self.buildings.get_blueprints_at(tx, ty):
            bp = self.buildings.get_blueprints_at(tx, ty)[0]
            cmd = {"type": "build", "world": self.world, "buildings": self.buildings,
                   "items": self.items, "stockpiles": self.stockpiles, "bp": bp}
            if not shift_held:
                for c in selected:
                    c._release_job(); c.queue.clear(); c.state = None
                    c.target_enemy = None; c.target_animal = None
                selected[0].assign_build(self.world, self.buildings, self.items, self.stockpiles, bp)
            else:
                for c in selected: c.enqueue_command(cmd)
        elif self.world.is_harvestable(tx, ty):
            cmd = {"type": "harvest", "world": self.world, "tx": tx, "ty": ty}
            if not shift_held:
                for c in selected:
                    c._release_job(); c.queue.clear(); c.state = None
                    c.target_enemy = None; c.target_animal = None
                selected[0].assign_harvest(self.world, tx, ty)
            else:
                for c in selected: c.enqueue_command(cmd)
        elif self.world.is_walkable(tx, ty):
            offsets = [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)]
            for i, c in enumerate(selected):
                ox, oy = offsets[i % len(offsets)]
                gx, gy = tx + ox, ty + oy
                if not self.world.is_walkable(gx, gy):
                    gx, gy = tx, ty
                cmd = {"type": "move", "world": self.world, "tx": gx, "ty": gy}
                if not shift_held:
                    c._release_job()
                    c.queue.clear()
                    c.state = None
                    c.target_enemy = None
                    c.target_animal = None
                    c.move_to(self.world, gx, gy)
                else:
                    c.enqueue_command(cmd)

    def _handle_building_hud_action(self, action):
        if action and action[0] == "take":
            _, take_kind, take_amt = action
            selected = self.selected_colonists()
            success = False
            candidates = selected if selected else [c for c in self.colonists if c.hp > 0]
            for c in candidates:
                if c.hp > 0:
                    if c.assign_take_from_cabinet(self.world, self.items, self.stockpiles,
                                                   self.buildings, self.selected_building,
                                                   take_kind, take_amt):
                        success = True; break
            if not success:
                self.log.add("指派取物失败：小人无法到达柜子！", (255, 100, 100))

    def _handle_farm_popup(self, event, screen_w, screen_h):
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        if pygame.Rect(screen_w // 2 - 180, screen_h // 2 - 30, 160, 50).collidepoint(event.pos):
            if self.research_mgr.can_plant("berry"):
                self.farms.add(self.pending_farm_rect, "berry")
                self.pending_farm_rect = None
                self.mode = None
        elif pygame.Rect(screen_w // 2 + 20, screen_h // 2 - 30, 160, 50).collidepoint(event.pos):
            if self.research_mgr.can_plant("tree"):
                self.farms.add(self.pending_farm_rect, "tree")
                self.pending_farm_rect = None
                self.mode = None
        elif pygame.Rect(screen_w // 2 - 50, screen_h // 2 + 60, 100, 30).collidepoint(event.pos):
            self.pending_farm_rect = None

    def _handle_drag_mode(self, event, screen_w, screen_h):
        if self.pending_farm_rect: return
        bottom_h = self.get_bottom_ui_height()
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.mode == "build" and (self.current_build_kind is None or self.current_build_mat is None):
                return
            if event.pos[1] < screen_h - bottom_h:
                self.drag_start = self.camera.screen_to_tile(*event.pos)
                self.drag_end = self.drag_start
        elif event.type == pygame.MOUSEMOTION and self.drag_start:
            self.drag_end = self.camera.screen_to_tile(*event.pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.drag_start and self.drag_end:
                x1, y1 = self.drag_start
                x2, y2 = self.drag_end
                tx1, tx2 = min(x1, x2), max(x1, x2)
                ty1, ty2 = min(y1, y2), max(y1, y2)
                if self.mode == "stockpile":
                    self.stockpiles.add((tx1, ty1, tx2, ty2))
                    self.mode = None
                elif self.mode == "farm":
                    self.pending_farm_rect = (tx1, ty1, tx2, ty2)
                elif self.mode == "build" and self.current_build_kind and self.current_build_mat:
                    w, h = (BUILDING_DEFS[self.current_build_kind]["w"],
                            BUILDING_DEFS[self.current_build_kind]["h"])
                    if self.build_rotation % 2 == 1: w, h = h, w
                    for ty in range(ty1, ty2 + 1, h):
                        for tx in range(tx1, tx2 + 1, w):
                            if self.buildings.can_place(self.world, tx, ty,
                                                        self.current_build_kind, self.current_build_mat,
                                                        self.build_rotation):
                                self.buildings.add_blueprint(self.current_build_kind,
                                                             self.current_build_mat, tx, ty,
                                                             self.build_rotation)
                elif self.mode == "deconstruct":
                    self.stockpiles.remove_tiles(tx1, ty1, tx2, ty2)
                    self.farms.remove_tiles(tx1, ty1, tx2, ty2)
                    self.buildings.remove_area(tx1, ty1, tx2, ty2)
                elif self.mode == "harvest_area":
                    for ty in range(ty1, ty2 + 1):
                        for tx in range(tx1, tx2 + 1):
                            if self.world.is_harvestable(tx, ty):
                                Colonist._designated_harvests.add((tx, ty))
                    self.mode = None
                elif self.mode == "hunt_area":
                    for a in self.animals:
                        atx, aty = a.current_tile()
                        if tx1 <= atx <= tx2 and ty1 <= aty <= ty2:
                            a.is_hunted = True
                    self.mode = None
            self.drag_start = None
            self.drag_end = None

    def _handle_selection(self, event, screen_w, screen_h, shift_held):
        self.selection.handle_event(event, self.camera, pygame.mouse.get_pos())
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.left_down_pos = event.pos
            self.left_drag_moved = False
        elif event.type == pygame.MOUSEMOTION and self.left_down_pos is not None:
            if (abs(event.pos[0] - self.left_down_pos[0]) > 8 or
                abs(event.pos[1] - self.left_down_pos[1]) > 8):
                self.left_drag_moved = True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if not self.left_drag_moved and self.left_down_pos is not None:
                self._handle_click_select(event.pos, shift_held)
            else:
                for c in self.colonists: c.selected = False
                self.selected_building = None
                self.selected_stockpile = None
                self.selected_item_stack = None
                for c in self.colonists:
                    if c.hp > 0 and c.current_tile() in self.selection.selected_tiles:
                        c.selected = True
            self.left_down_pos = None
            self.left_drag_moved = False

    def _handle_click_select(self, pos, shift_held):
        wx, wy = self.camera.screen_to_world(*pos)
        tx, ty = self.camera.screen_to_tile(*pos)
        hit_col = None
        for c in self.colonists:
            if c.hp <= 0: continue
            if (c.x - wx) ** 2 + (c.y - wy) ** 2 <= (c.radius + 15) ** 2:
                hit_col = c; break
        if hit_col:
            if not shift_held:
                for c in self.colonists: c.selected = False
            hit_col.selected = True
            self.selected_building = None
            self.selected_stockpile = None
            self.selected_item_stack = None
            if not shift_held: self.selection.selected_tiles.clear()
            return

        hit_item = None
        for s in self.items.get_at(tx, ty):
            if (s.x - wx) ** 2 + (s.y - wy) ** 2 <= (TILE_SIZE // 2) ** 2:
                hit_item = s; break
        if hit_item:
            self.selected_building = None
            self.selected_stockpile = None
            self.selected_item_stack = hit_item
            self.ihud.set_target(hit_item, tx, ty)
            self.ihud.in_cabinet = False
            self.selection.selected_tiles.clear()
            return

        hit_building = self.buildings.get_building_at(tx, ty)
        if not hit_building:
            bps = self.buildings.get_blueprints_at(tx, ty)
            if bps: hit_building = bps[0]
        if hit_building and hit_building.kind == "floor":
            hit_building = None
        if hit_building:
            for c in self.colonists: c.selected = False
            self.selected_building = hit_building
            self.selected_stockpile = None
            self.selected_item_stack = None
            self.selection.selected_tiles.clear()
            return

        hit_sp = self.stockpiles.find_stockpile_for(tx, ty)
        if hit_sp:
            self.selected_building = None
            self.selected_stockpile = hit_sp
            self.selected_item_stack = None
            self.shud.set_target(hit_sp, pos, self.camera.screen_w if hasattr(self.camera, 'screen_w') else 1280, 720)
            return

        if not shift_held:
            for c in self.colonists: c.selected = False
            self.selected_building = None
            self.selected_stockpile = None
            self.selected_item_stack = None

    def tick_ui(self, dt_raw):
        if self.warning_timer > 0:
            self.warning_timer -= dt_raw
        else:
            attacked = [c for c in self.colonists if c.hp > 0 and c.hit_flash > 0.1]
            if attacked:
                names = ", ".join([c.name for c in attacked[:3]])
                if len(attacked) > 3: names += "..."
                self.warning_text = f"警告: {names} 正在遭受攻击！"
                self.warning_timer = 2.0

    def step(self, dt, dt_raw):
        if self.game_speed <= 0:
            self.log.update(dt_raw)
            return

        self.game_time.update(dt)
        self.farms.update(dt)
        self.room_mgr.update(dt)

        for c in self.colonists:
            c.update_needs(dt, self.game_time)
            c.check_urgent_needs(self.world, self.items, self.stockpiles, self.buildings)
            c.update(dt, self.world, self.items, self.stockpiles, self.buildings,
                     self.enemies, self.game_time, self.research_mgr)

        for e in self.enemies:
            e.update(dt, self.world, self.colonists, self.buildings)
        for a in self.animals:
            a.update(dt, self.world, self.colonists)
        self.animals = [a for a in self.animals if a.hp > 0]

        self.animal_respawn_timer -= dt
        if self.animal_respawn_timer <= 0 and len(self.animals) < self.MAX_ANIMALS:
            self.animal_respawn_timer = 15.0
            for _ in range(20):
                ax, ay = random.randint(5, MAP_WIDTH - 5), random.randint(5, MAP_HEIGHT - 5)
                if self.world.is_walkable(ax, ay):
                    is_safe = True
                    for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                        if not self.world.is_walkable(ax + dx, ay + dy):
                            is_safe = False; break
                    if is_safe:
                        self.animals.append(Animal(ax, ay, random.choice(["rabbit", "rabbit", "deer", "deer", "deer"])))
                        break

        self.enemy_invasion_timer -= dt
        if self.enemy_invasion_timer <= 0:
            self.enemy_invasion_timer = self.game_time.day_length_sec * 3
            if random.random() < 0.5:
                count = random.randint(1, 3)
                for _ in range(count):
                    side = random.randint(0, 3)
                    if side == 0:
                        ex, ey = random.randint(5, MAP_WIDTH - 5), 5
                    elif side == 1:
                        ex, ey = random.randint(5, MAP_WIDTH - 5), MAP_HEIGHT - 5
                    elif side == 2:
                        ex, ey = 5, random.randint(5, MAP_HEIGHT - 5)
                    else:
                        ex, ey = MAP_WIDTH - 5, random.randint(5, MAP_HEIGHT - 5)
                    if self.world.is_walkable(ex, ey):
                        self.enemies.append(Enemy(ex, ey, random.choice(["club", "spear", "longsword", "fist"])))
                self.log.add(f"警告：发现 {count} 名敌人入侵！", (255, 50, 50))
                self.warning_text = f"警告：发现 {count} 名敌人入侵！"
                self.warning_timer = 3.0

        for c in self.colonists:
            if c.recent_shot is not None:
                kind, x1, y1, x2, y2, color = c.recent_shot
                if kind == "shot": self.effects.append(Shot(x1, y1, x2, y2, color))
                else: self.effects.append(MeleeHit(x2, y2, color))
                c.recent_shot = None
        for e in self.enemies:
            if e.recent_shot is not None:
                kind, x1, y1, x2, y2, color = e.recent_shot
                if kind == "shot": self.effects.append(Shot(x1, y1, x2, y2, color))
                else: self.effects.append(MeleeHit(x2, y2, color))
                e.recent_shot = None

        for c in self.colonists:
            if c.hp <= 0:
                self.log.add(f"{c.name} 倒下了！", (255, 80, 80))
                if c.bed_tile is not None:
                    b = self.buildings.get_building_at(c.bed_tile[0], c.bed_tile[1])
                    if b and b.occupied_by == c.id:
                        b.occupied_by = None
        self.colonists = [c for c in self.colonists if c.hp > 0]
        Colonist._all_colonists = self.colonists

        for e in self.enemies:
            if e.hp <= 0:
                self.log.add(f"{e.name} 被击杀", (100, 255, 100))
        self.enemies = [e for e in self.enemies if e.hp > 0]

        if self.selected_building:
            if hasattr(self.selected_building, "work_done"):
                if (self.selected_building.tx, self.selected_building.ty,
                    self.selected_building.layer) not in self.buildings.blueprints:
                    self.selected_building = None
            else:
                if (self.selected_building.tx, self.selected_building.ty,
                    self.selected_building.layer) not in self.buildings.buildings:
                    self.selected_building = None
        if self.selected_item_stack:
            if self.selected_item_stack.amount <= 0 or \
               self.selected_item_stack not in self.items.stacks.values():
                self.selected_item_stack = None

        for c in self.colonists:
            if c.is_idle():
                c.try_find_job(self.world, self.items, self.stockpiles, self.buildings,
                               self.research_mgr, self.animals, self.farms.farms)

        self.effects = [ef for ef in self.effects if ef.update(dt)]
        self.log.update(dt_raw)

    def draw(self, surface, dt_raw):
        screen_w, screen_h = surface.get_size()
        mouse_pos = pygame.mouse.get_pos()

        surface.fill(BLACK)
        self.world.draw(surface, self.camera)
        for (tx, ty) in Colonist._designated_harvests:
            sx, sy = self.camera.world_to_screen(tx * TILE_SIZE, ty * TILE_SIZE)
            pygame.draw.rect(surface, (180, 220, 100),
                             (sx + 4, sy + 4, TILE_SIZE - 8, TILE_SIZE - 8), 2, border_radius=4)
            txt = self.font_small.render("采", True, (180, 220, 100))
            surface.blit(txt, (sx + TILE_SIZE // 2 - txt.get_width() // 2,
                               sy + TILE_SIZE // 2 - txt.get_height() // 2))

        self.stockpiles.draw(surface, self.camera)
        self.farms.draw(surface, self.camera)
        self.buildings.draw_layer(surface, self.camera, self.font_small, 0)
        self.items.draw(surface, self.camera, self.font)
        self.buildings.draw_layer(surface, self.camera, self.font_small, 1)

        for a in self.animals:
            a.draw(surface, self.camera, self.font)
            if getattr(a, "is_hunted", False):
                sx, sy = self.camera.world_to_screen(a.x, a.y)
                pygame.draw.circle(surface, (255, 60, 60), (int(sx), int(sy)), a.radius + 6, 2)
                txt = self.font_small.render("猎物", True, (255, 60, 60))
                bg = pygame.Surface((txt.get_width() + 4, txt.get_height() + 2), pygame.SRCALPHA)
                bg.fill((0, 0, 0, 150))
                surface.blit(bg, (sx - txt.get_width() // 2 - 2, sy - a.radius - 26))
                surface.blit(txt, (sx - txt.get_width() // 2, sy - a.radius - 25))

        if self.selected_building:
            sx, sy = self.camera.world_to_screen(self.selected_building.tx * TILE_SIZE,
                                                 self.selected_building.ty * TILE_SIZE)
            rect = pygame.Rect(sx, sy, TILE_SIZE * self.selected_building.w,
                               TILE_SIZE * self.selected_building.h)
            pygame.draw.rect(surface, (255, 255, 255), rect, 2)

        if self.selected_item_stack:
            sx, sy = self.camera.world_to_screen(self.selected_item_stack.x, self.selected_item_stack.y)
            pygame.draw.circle(surface, (255, 255, 255), (int(sx), int(sy)), TILE_SIZE // 2, 2)

        if self.mode in ("stockpile", "build", "deconstruct", "farm", "harvest_area",
                         "hunt_area") and self.drag_start and self.drag_end and not self.pending_farm_rect:
            x1, y1 = self.drag_start
            x2, y2 = self.drag_end
            tx1, tx2 = min(x1, x2), max(x1, x2)
            ty1, ty2 = min(y1, y2), max(y1, y2)
            for ty in range(ty1, ty2 + 1):
                for tx in range(tx1, tx2 + 1):
                    sx, sy = self.camera.world_to_screen(tx * TILE_SIZE, ty * TILE_SIZE)
                    s = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
                    if self.mode == "stockpile": s.fill((80, 140, 220, 80))
                    elif self.mode == "build": s.fill((100, 200, 100, 100))
                    elif self.mode == "farm": s.fill((60, 180, 60, 100))
                    elif self.mode == "harvest_area": s.fill((180, 220, 100, 80))
                    elif self.mode == "hunt_area": s.fill((220, 100, 150, 80))
                    else: s.fill((255, 50, 50, 80))
                    surface.blit(s, (sx, sy))
                    pygame.draw.rect(surface, (255, 255, 255), (sx, sy, TILE_SIZE, TILE_SIZE), 1)

        if self.show_beauty:
            for rid, (cx, cy) in self.room_mgr.room_centers.items():
                beauty = self.room_mgr.room_beauty.get(rid, 0)
                sx, sy = self.camera.world_to_screen(cx * TILE_SIZE + TILE_SIZE / 2,
                                                      cy * TILE_SIZE + TILE_SIZE / 2)
                txt = self.font_big.render(f"美:{beauty}", True, (255, 100, 255))
                bg = pygame.Surface((txt.get_width() + 4, txt.get_height() + 4), pygame.SRCALPHA)
                bg.fill((0, 0, 0, 150))
                surface.blit(bg, (sx - txt.get_width() // 2 - 2, sy - txt.get_height() // 2 - 2))
                surface.blit(txt, (sx - txt.get_width() // 2, sy - txt.get_height() // 2))

        bottom_h = self.get_bottom_ui_height()
        if self.mode == "build" and self.current_build_kind and self.current_build_mat and not self.drag_start:
            if mouse_pos[1] < screen_h - bottom_h:
                tx, ty = self.camera.screen_to_tile(*mouse_pos)
                if self.buildings.can_place(self.world, tx, ty,
                                            self.current_build_kind, self.current_build_mat,
                                            self.build_rotation):
                    w, h = (BUILDING_DEFS[self.current_build_kind]["w"],
                            BUILDING_DEFS[self.current_build_kind]["h"])
                    if self.build_rotation % 2 == 1: w, h = h, w
                    sx, sy = self.camera.world_to_screen(tx * TILE_SIZE, ty * TILE_SIZE)
                    s = pygame.Surface((TILE_SIZE * w, TILE_SIZE * h), pygame.SRCALPHA)
                    s.fill((100, 200, 100, 100))
                    surface.blit(s, (sx, sy))
                    pygame.draw.rect(surface, (255, 255, 255), (sx, sy, TILE_SIZE * w, TILE_SIZE * h), 1)

        for c in self.colonists:
            if c.selected: c.draw_path(surface, self.camera, self.world)
        for c in self.colonists: c.draw(surface, self.camera, self.font)
        for e in self.enemies: e.draw(surface, self.camera, self.font)
        for ef in self.effects: ef.draw(surface, self.camera)
        self.selection.draw(surface, self.camera)

        light = self.game_time.get_light_level()
        if light < 1.0:
            shade = pygame.Surface((screen_w, screen_h))
            shade.fill((0, 0, 30))
            shade.set_alpha(int((1.0 - light) * 160))
            surface.blit(shade, (0, 0))

        speed_text = "暂停" if self.game_speed == 0 else f"{int(self.game_speed)}x"
        info = (f"{self.game_time.time_str()} | 速度 {speed_text} | 殖民者 {len(self.colonists)} | "
                f"敌人 {len(self.enemies)} | 动物 {len(self.animals)}")
        surface.blit(self.font_big.render(info, True, WHITE), (10, 10))

        totals = self.get_totals()
        y0 = 10
        for kind, amt in totals.items():
            d = ITEM_DEFS.get(kind, {"name": kind})
            surf = self.font_big.render(f"{d['name']}: {amt}", True, (255, 240, 180))
            surface.blit(surf, (screen_w - surf.get_width() - 10, y0))
            y0 += 24

        self.log.draw(surface, self.font, screen_w, screen_h)

        if self.mode == "build":
            self.build_menu.draw(surface, screen_w, screen_h, screen_h - self.toolbar.height,
                                 self.current_build_kind, self.current_build_mat, totals,
                                 self.research_mgr, self.build_rotation)
        elif self.mode == "research":
            self.research_menu.draw(surface, screen_w, screen_h, self.research_mgr)

        self.toolbar.draw(surface, screen_w, screen_h, self.mode)

        selected_cols = self.selected_colonists()
        if selected_cols:
            self.hud.draw(surface, self.colonists, selected_cols, self.camera)
        elif self.selected_building:
            self.bhud.draw(surface, self.selected_building, totals, self.research_mgr)
        elif self.selected_stockpile:
            self.shud.draw(surface)
        elif self.selected_item_stack:
            self.ihud.draw(surface, self.buildings)

        if self.pending_farm_rect:
            popup_rect = pygame.Rect(screen_w // 2 - 200, screen_h // 2 - 100, 400, 200)
            pygame.draw.rect(surface, (20, 20, 25), popup_rect, border_radius=8)
            pygame.draw.rect(surface, (100, 200, 100), popup_rect, 2, border_radius=8)
            title = self.font_big.render("选择种植作物", True, (100, 200, 100))
            surface.blit(title, (popup_rect.centerx - title.get_width() // 2, popup_rect.y + 15))
            b_rect = pygame.Rect(screen_w // 2 - 180, screen_h // 2 - 30, 160, 50)
            b_ok = self.research_mgr.can_plant("berry")
            col = (80, 160, 80) if b_ok else (50, 50, 50)
            pygame.draw.rect(surface, col, b_rect, border_radius=6)
            txt = self.font.render("浆果 (已解锁)" if b_ok else "浆果 (需基础农业)", True, WHITE)
            surface.blit(txt, (b_rect.centerx - txt.get_width() // 2, b_rect.y + 15))
            t_rect = pygame.Rect(screen_w // 2 + 20, screen_h // 2 - 30, 160, 50)
            t_ok = self.research_mgr.can_plant("tree")
            col = (80, 160, 80) if t_ok else (50, 50, 50)
            pygame.draw.rect(surface, col, t_rect, border_radius=6)
            txt = self.font.render("树木 (已解锁)" if t_ok else "树木 (需速生树种)", True, WHITE)
            surface.blit(txt, (t_rect.centerx - txt.get_width() // 2, t_rect.y + 15))
            c_rect = pygame.Rect(screen_w // 2 - 50, screen_h // 2 + 60, 100, 30)
            pygame.draw.rect(surface, (180, 60, 60), c_rect, border_radius=4)
            txt = self.font.render("取消", True, WHITE)
            surface.blit(txt, (c_rect.centerx - txt.get_width() // 2, c_rect.y + 5))

        if self.warning_timer > 0:
            warn_surf = self.font_warn.render(self.warning_text, True, (255, 80, 80))
            bg_rect = pygame.Rect(0, 0, warn_surf.get_width() + 20, warn_surf.get_height() + 10)
            bg_rect.center = (screen_w // 2, 80)
            s = pygame.Surface((bg_rect.width, bg_rect.height), pygame.SRCALPHA)
            s.fill((40, 0, 0, 200))
            surface.blit(s, bg_rect)
            surface.blit(warn_surf, (bg_rect.x + 10, bg_rect.y + 5))

        if self.show_help:
            help_surf = pygame.Surface((600, 480), pygame.SRCALPHA)
            help_surf.fill((20, 20, 25, 240))
            pygame.draw.rect(help_surf, (100, 160, 220), help_surf.get_rect(), 2)
            title = self.font_big.render("操作说明", True, (100, 160, 220))
            help_surf.blit(title, (20, 20))
            keys_text = [
                "边缘/右键拖拽 : 移动视角",
                "左键点击 / 框选 : 选中",
                "右键单击 : 命令 (建造/采集/攻击/狩猎/移动/搬运)",
                "Shift + 右键 : 加入队列",
                "空格键 : 切换时间流速 (暂停/1x/2x/3x)",
                "B : 建造菜单   |   F : 划定农业区",
                "S : 划定库存   |   X : 拆除/删除模式",
                "R : 建造时旋转 / 开启科技树",
                "H / Esc : 打开/关闭此帮助面板",
                "F11 : 切换全屏模式",
                "T : 切换 房间美观度 透视"
            ]
            for i, txt in enumerate(keys_text):
                line = self.font.render(txt, True, WHITE)
                help_surf.blit(line, (30, 60 + i * 26))
            surface.blit(help_surf, (screen_w // 2 - 300, screen_h // 2 - 240))