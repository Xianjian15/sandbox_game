# world/game_world.py
import random
import pygame

from core.profile import PLAYER_COLORS
from core.ui_scale import compute_scale, logical_size, to_logical, UiLayer, pref_text
from settings import MAP_WIDTH, MAP_HEIGHT, TILE_SIZE, BLACK, WHITE, TICK_DT, START_COLONISTS
from core.camera import Camera
from core.time_system import GameTime
from core.sim_context import SimContext
from core import commands as cmdlib
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
from world.command_exec import apply_command, EQUIP_KINDS

class GameWorld:
    def __init__(self, font, font_big, font_small, font_warn, screen_w, screen_h, seed=None, map_seed=None,
                 cmd_delay=0, local_player=0, num_players=1):
        self.font = font
        self.font_big = font_big
        self.font_small = font_small
        self.font_warn = font_warn

        self.seed = seed if seed is not None else 42
        self.ctx = SimContext(self.seed)     # 一局游戏的共享模拟状态（id、引用、采集占用集合）
        self.rng = self.ctx.rng

        self.game_time = GameTime(day_length_sec=120.0, start_hour=7.0)
        self.research_mgr = ResearchManager()

        # 地形生成使用独立的随机流（默认由游戏种子决定）。
        # 传 map_seed=7 可以精确复现旧版（硬编码 random.seed(7)）的地图。
        self.map_seed = map_seed if map_seed is not None else self.seed
        self.world = World(MAP_WIDTH, MAP_HEIGHT, random.Random(self.map_seed))
        self.items = ItemManager()
        self.ctx.items = self.items
        self.stockpiles = StockpileManager()
        self.farms = FarmManager()
        self.buildings = BuildingManager(self.research_mgr)
        self.ctx.buildings = self.buildings
        self.world.buildings = self.buildings

        self.room_mgr = RoomManager(self.world, self.buildings)
        self.ctx.room_mgr = self.room_mgr

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

        # ---- 界面自动缩放：界面画在"逻辑尺寸"画布上再整体缩放；地图仍按真实分辨率画 ----
        self.ui_pref = 1.0                 # 玩家偏好倍数（Ctrl +/-），main 读写
        self.ui_scale = 1.0
        self.ui_w, self.ui_h = screen_w, screen_h        # 界面逻辑尺寸（所有面板/点击判定都用它）
        self.native_size = (screen_w, screen_h)
        self.ui_layer = UiLayer(alpha=True)
        self.toast_text, self.toast_timer = "", 0.0
        self._update_ui_scale(screen_w, screen_h)

        # —— 指令系统：UI 不直接改模拟状态，一律 issue(指令) ——
        # cmd_delay == 0：单机，指令当场执行（行为与重构前完全一致）；
        # cmd_delay  > 0：联机，指令排到 当前tick+cmd_delay 再统一执行，并进入 cmd_outbox 等待网络层发送。
        self.cmd_delay = cmd_delay
        self.local_player = local_player
        self.num_players = max(1, int(num_players))   # 联机=2；每位玩家只能指挥 owner_id 等于自己的小人
        # 回合计数：指令的"时钟"。每调用一次 sim_step() 加 1，【与是否暂停无关】。
        # 暂停时世界不更新，但回合照走，这样"取消暂停"这条指令才能在联机时生效。
        self.turn = 0
        self.net_status = ""      # 联机状态文字（由 net.session 写入，只用于显示）
        self.player_profiles = []   # 玩家资料（用户名+头像图面），只用于显示，不参与模拟/哈希
        self.gone_players = set()   # 已离开的玩家编号（由 net.session 写入，只用于显示）
        self.cmd_seq = 0
        self.cmd_buffer = {}      # tick -> [cmd]
        self.cmd_outbox = []      # 本地新发出、待网络层发送的指令（仅 cmd_delay > 0 时记录）
        self.cmd_log = None       # 设为 [] 即可录制"实际被执行的指令序列"，用于回放测试
        self.bhud.emit = self.issue
        self.ihud.emit = self.issue
        self.research_menu.emit = self.issue
        self.log = CombatLog()

        # ---- 实体 ----
        self.colonists = []
        self.enemies = []
        self.animals = []
        self.effects = []

        base_x = MAP_WIDTH // 2
        base_y = MAP_HEIGHT // 2 - 5
        # 每位玩家开局 START_COLONISTS 个小人（owner_id = 玩家编号）。
        # 出生点按玩家错开：玩家 i 在基地中心左右各偏移 4 格；顺序固定 → id 分配两端一致。
        n = self.num_players
        for pl in range(n):
            for k in range(START_COLONISTS):
                off = (pl - (n - 1) / 2.0) * 4
                bx = base_x + int(round(off)) + k * 2
                found = None
                for dy in range(-2, 3):
                    for dx in range(-3, 4):
                        tx, ty = bx + dx, base_y + dy
                        if self.world.is_walkable(tx, ty) and not any(
                                c.current_tile() == (tx, ty) for c in self.colonists):
                            found = (tx, ty)
                            break
                    if found: break
                if not found: found = (bx, base_y)
                c = Colonist(*found, weapon_key="fist", ctx=self.ctx)
                c.owner_id = pl
                self.colonists.append(c)

        spawn_attempts = 0
        while len(self.animals) < 15 and spawn_attempts < 200:
            spawn_attempts += 1
            ax, ay = self.rng.randint(5, MAP_WIDTH - 5), self.rng.randint(5, MAP_HEIGHT - 5)
            if self.world.is_walkable(ax, ay):
                is_safe = True
                for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                    if not self.world.is_walkable(ax + dx, ay + dy):
                        is_safe = False; break
                if is_safe:
                    self.animals.append(Animal(ax, ay, self.rng.choice(["rabbit", "rabbit", "deer", "deer", "deer"]), ctx=self.ctx))

        self.animal_respawn_timer = 10.0
        self.MAX_ANIMALS = 20
        self.enemy_invasion_timer = self.game_time.day_length_sec * 3

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

    # ---------------- 指令系统 ----------------
    def issue(self, cmd):
        """UI 的唯一出口：给指令盖章（玩家、序号、计划 tick），然后执行或排期。"""
        cmd = dict(cmd)
        self.cmd_seq += 1
        cmd["p"] = self.local_player
        cmd["s"] = self.cmd_seq
        cmd["tick"] = self.turn + self.cmd_delay
        cmdlib.validate(cmd)
        if self.cmd_delay == 0:
            self._execute(cmd)
        else:
            self.cmd_outbox.append(cmd)
            self.receive_command(cmd)

    def receive_command(self, cmd):
        """收到一条指令（自己发的或对方发来的）：排进对应 tick。"""
        self.cmd_buffer.setdefault(cmd["tick"], []).append(cmd)

    def flush_commands(self, force=False):
        """执行所有已到期的指令。顺序固定为 (tick, 玩家, 序号)，两端一致。
        force=True：不管到没到期全部执行（断线转单机时用）。"""
        now = self.turn
        due = [t for t in self.cmd_buffer if force or t <= now]
        if not due:
            return
        cmds = []
        for t in due:
            cmds.extend(self.cmd_buffer.pop(t))
        cmds.sort(key=lambda c: (c["tick"], c["p"], c["s"]))
        for c in cmds:
            self._execute(c)

    def _execute(self, cmd):
        if self.cmd_log is not None:
            self.cmd_log.append((self.turn, dict(cmd)))
        apply_command(self, cmd)

    OWNER_COLORS = PLAYER_COLORS

    def set_profiles(self, roster):
        """联机开局后由 main 调用：roster = [{"name","av"(base64 或 None)}]，按玩家编号排列。"""
        from core.profile import decode_avatar
        from ui.avatar import make_avatar_surface
        self.player_profiles = []
        for i, r in enumerate(roster or []):
            col = self.OWNER_COLORS[i % len(self.OWNER_COLORS)]
            raw = decode_avatar(r.get("av"))
            name = r.get("name") or f"玩家{i + 1}"
            self.player_profiles.append({
                "name": name, "color": col,
                "big": make_avatar_surface(raw, name, col, self.font_big, 32),
                "small": make_avatar_surface(raw, name, col, self.font, 16)})

    def player_name(self, i):
        if 0 <= i < len(self.player_profiles):
            return self.player_profiles[i]["name"]
        return f"P{i + 1}"

    def _draw_player_bar(self, surface):
        """界面上方（时间信息行下面）列出所有玩家的头像和用户名；自己标"我"，已离开的变灰。"""
        x, y = 10, 40
        for i, pr in enumerate(self.player_profiles):
            gone = i in self.gone_players
            label = pr["name"] + (" (我)" if i == self.local_player else "") + (" (已离开)" if gone else "")
            txt = self.font.render(label, True, (150, 150, 150) if gone else (255, 255, 255))
            w = 32 + 10 + txt.get_width() + 12
            panel = pygame.Surface((w, 38), pygame.SRCALPHA)
            panel.fill((20, 20, 28, 170))
            surface.blit(panel, (x, y))
            av = pr["big"]
            if gone:
                av = av.copy(); av.set_alpha(100)
            surface.blit(av, (x + 3, y + 3))
            pygame.draw.rect(surface, pr["color"] if not gone else (90, 90, 90), (x + 2, y + 2, 34, 34), 2)
            surface.blit(txt, (x + 42, y + 19 - txt.get_height() // 2))
            x += w + 8

    def _draw_owner_mark(self, surface, c):
        """联机时在小人脚下画归属色环，头顶标出操控它的玩家用户名（和头像）。"""
        sx, sy = self.camera.world_to_screen(c.x, c.y)
        col = self.OWNER_COLORS[c.owner_id % len(self.OWNER_COLORS)]
        pygame.draw.circle(surface, col, (int(sx), int(sy)), c.radius + 3, 2)
        name = self.player_name(c.owner_id)
        txt = self.font.render(name, True, col)
        small = self.player_profiles[c.owner_id]["small"] if c.owner_id < len(self.player_profiles) else None
        w = txt.get_width() + (20 if small else 0)
        x0 = int(sx - w / 2)
        y0 = int(sy - c.radius - 30)
        bg = pygame.Surface((w + 6, 18), pygame.SRCALPHA)
        bg.fill((0, 0, 0, 120))
        surface.blit(bg, (x0 - 3, y0 - 1))
        if small:
            surface.blit(small, (x0, y0 + 1))
            x0 += 20
        surface.blit(txt, (x0, y0))

    def selected_colonists(self):
        return [c for c in self.colonists if c.selected and c.owner_id == self.local_player]

    # ---------------- 界面缩放 ----------------
    def _update_ui_scale(self, w, h):
        """窗口尺寸/偏好变了就重算缩放比例和界面逻辑尺寸（每帧调用，很便宜）。"""
        self.native_size = (w, h)
        s = compute_scale(w, h, self.ui_pref)
        lw, lh = logical_size(w, h, s)
        self.ui_scale = s
        if (lw, lh) != (self.ui_w, self.ui_h) or not hasattr(self, "_ui_inited"):
            self.ui_w, self.ui_h = lw, lh
            self._ui_inited = True
        self.bhud.panel_rect.x = lw - self.bhud.panel_w - 20       # 右侧面板贴着逻辑画面的右边

    def _L(self, pos):
        """窗口坐标 → 界面逻辑坐标。界面的点击判定一律用它；地图相关（相机/选择框）仍用窗口坐标。"""
        return to_logical(pos, self.ui_scale)

    def set_ui_pref(self, pref):
        self.ui_pref = pref
        self._update_ui_scale(*self.native_size)
        self.toast_text, self.toast_timer = pref_text(pref), 1.5

    def is_mouse_in_ui(self, mouse_pos):
        """mouse_pos 是窗口坐标（pygame.mouse.get_pos()）。"""
        mouse_pos = self._L(mouse_pos)
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
        self._update_ui_scale(w, h)

    def handle_event(self, event, screen_w, screen_h):
        self._update_ui_scale(screen_w, screen_h)
        lw, lh = self.ui_w, self.ui_h                       # 界面逻辑尺寸
        lpos = self._L(event.pos) if hasattr(event, "pos") else None     # 事件位置的界面逻辑坐标
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
            if self.bhud.handle_right_click(lpos, self.selected_building): return
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

        if event.type == pygame.MOUSEBUTTONUP and event.button == 3:
            if self.dragging_cam_right:
                self.dragging_cam_right = False
                dist = abs(event.pos[0] - self.right_down_pos[0]) + abs(event.pos[1] - self.right_down_pos[1])
                if dist < 15 and self.mode is None and not self.show_help and not mouse_in_ui:
                    self._handle_right_click(event.pos, shift_held)
            return

        if self.mode == "farm" and self.pending_farm_rect:
            self._handle_farm_popup(event, lpos, lw, lh)
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            selected_cols = self.selected_colonists()
            if self.hud.handle_click(lpos, selected_cols):
                self.left_down_pos = None; return

            consumed, action = self.bhud.handle_click(lpos, self.selected_building,
                                                      self.get_global_items(), self.research_mgr)
            if consumed:
                self._handle_building_hud_action(action)
                self.left_down_pos = None; return

            consumed_sp, delete_sp = self.shud.handle_click(lpos)
            if consumed_sp:
                if delete_sp and self.selected_stockpile in self.stockpiles.stockpiles:
                    sp = self.selected_stockpile
                    self.issue(cmdlib.make("stockpile_remove", x1=sp.x1, y1=sp.y1, x2=sp.x2, y2=sp.y2))
                    self.selected_stockpile = None
                self.left_down_pos = None; return

            if self.ihud.handle_click(lpos):
                self.left_down_pos = None; return

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if mouse_in_ui:
                self.left_down_pos = None; return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            clicked_mode = self.toolbar.handle_click(lpos)
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
            if self.mode == "build" and lpos[1] > lh - bottom_h:
                k, m, is_selected = self.build_menu.handle_click(lpos, self.research_mgr)
                if is_selected:
                    self.current_build_kind = k
                    self.current_build_mat = m
                    self.build_rotation = 0
                self.left_down_pos = None
                return
            if self.mode == "research":
                if self.research_menu.handle_click(lpos, self.research_mgr):
                    self.left_down_pos = None
                    return
                if self.research_menu.panel_rect.collidepoint(lpos):
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
            nxt = {0: 1, 1: 2, 2: 3}.get(int(self.game_speed), 0)
            self.issue(cmdlib.make("speed", v=nxt))
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

    def _command_station(self, selected, shift_held, station, cmd, assign, fail_msg):
        """对工作站类建筑（研究台 / 烹饪台 / 熔炉）下指令：
        普通右键 = 立刻去做（打断当前任务）；Shift+右键 = 排进队列。"""
        if shift_held:
            for c in selected: c.enqueue_command(cmd)
            return
        for c in selected:
            c._release_job(); c.queue.clear(); c.state = None
            c.target_enemy = None; c.target_animal = None
        # 设施还被别的小人占着：让对方放手，避免两人同时用
        if station.reserved_by is not None and station.reserved_by != selected[0].id:
            for c2 in self.colonists:
                if c2.id == station.reserved_by:
                    c2._release_job(); break
            station.reserved_by = None
        if not assign(selected[0]):
            self.log.add(fail_msg, (255, 100, 100))

    def _handle_right_click(self, pos, shift_held):
        """右键：这里只做"点到了什么"的判断（纯 UI），然后发出一条指令。
        真正的合法性校验与执行都在 world/command_exec.py。"""
        selected = [c for c in self.colonists
                    if c.selected and c.hp > 0 and c.owner_id == self.local_player]
        if not selected: return
        ids = [c.id for c in selected]
        q = bool(shift_held)
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

        building_here = self.buildings.get_building_at(tx, ty)
        blueprints_here = self.buildings.get_blueprints_at(tx, ty)
        station_of = {"workbench": "craft", "research_bench": "research", "stove": "cook", "furnace": "smelt"}

        if hit_enemy is not None:
            self.issue(cmdlib.make("attack", ids=ids, target=hit_enemy.id, q=q))

        elif hit_animal is not None:
            self.issue(cmdlib.make("hunt", ids=ids, target=hit_animal.id, q=q))

        elif building_here and building_here.kind in ("small_cabinet", "large_cabinet"):
            # 纯 UI：选中柜子，打开面板
            self.selected_building = building_here
            self.selected_item_stack = None
            self.selected_stockpile = None
            for c in self.colonists: c.selected = False
            for c in selected: c.selected = True

        elif building_here and building_here.kind in station_of:
            self.issue(cmdlib.make("station", ids=ids, kind=station_of[building_here.kind],
                                   tx=building_here.tx, ty=building_here.ty, q=q))

        # 【关键修复】蓝图优先于物品：站在地板上右键蓝图时，脚下的散落材料不该抢走指令
        elif blueprints_here:
            self.issue(cmdlib.make("build", ids=ids, tx=tx, ty=ty, q=q))

        elif hit_item is not None:
            equip_kinds = ["axe", "stone_pickaxe", "iron_pickaxe", "longsword",
                           "gun", "pistol", "rifle"]
            if hit_item.kind in equip_kinds:
                self.issue(cmdlib.make("equip", ids=ids, tx=tx, ty=ty, kind=hit_item.kind, q=q))
            else:
                self.issue(cmdlib.make("haul", ids=ids, tx=tx, ty=ty, kind=hit_item.kind, q=q))

        elif self.world.is_harvestable(tx, ty):
            self.issue(cmdlib.make("harvest", ids=ids, tx=tx, ty=ty, q=q))

        elif self.world.is_walkable(tx, ty):
            self.issue(cmdlib.make("move", ids=ids, tx=tx, ty=ty, q=q))

    def _handle_building_hud_action(self, action):
        if action and action[0] == "take":
            _, take_kind, take_amt = action
            b = self.selected_building
            if b is None: return
            ids = [c.id for c in self.selected_colonists()]
            self.issue(cmdlib.make("take", ids=ids, tx=b.tx, ty=b.ty, layer=b.layer,
                                   kind=take_kind, amt=int(take_amt)))

    def _handle_farm_popup(self, event, pos, screen_w, screen_h):
        """pos / screen_w / screen_h 都是界面逻辑坐标（弹窗是界面的一部分）。"""
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        r = self.pending_farm_rect
        if pygame.Rect(screen_w // 2 - 180, screen_h // 2 - 30, 160, 50).collidepoint(pos):
            if self.research_mgr.can_plant("berry"):
                self.issue(cmdlib.make("farm_add", x1=r[0], y1=r[1], x2=r[2], y2=r[3], plant="berry"))
                self.pending_farm_rect = None
                self.mode = None
        elif pygame.Rect(screen_w // 2 + 20, screen_h // 2 - 30, 160, 50).collidepoint(pos):
            if self.research_mgr.can_plant("tree"):
                self.issue(cmdlib.make("farm_add", x1=r[0], y1=r[1], x2=r[2], y2=r[3], plant="tree"))
                self.pending_farm_rect = None
                self.mode = None
        elif pygame.Rect(screen_w // 2 - 50, screen_h // 2 + 60, 100, 30).collidepoint(pos):
            self.pending_farm_rect = None

    def _handle_drag_mode(self, event, screen_w, screen_h):
        if self.pending_farm_rect: return
        bottom_h = self.get_bottom_ui_height()
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.mode == "build" and (self.current_build_kind is None or self.current_build_mat is None):
                return
            if self._L(event.pos)[1] < self.ui_h - bottom_h:        # 点在底部工具栏/菜单上不算框地图
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
                rect = dict(x1=tx1, y1=ty1, x2=tx2, y2=ty2)
                if self.mode == "stockpile":
                    self.issue(cmdlib.make("stockpile_add", **rect))
                    self.mode = None
                elif self.mode == "farm":
                    self.pending_farm_rect = (tx1, ty1, tx2, ty2)
                elif self.mode == "build" and self.current_build_kind and self.current_build_mat:
                    self.issue(cmdlib.make("build_area", kind=self.current_build_kind,
                                           mat=self.current_build_mat, rot=self.build_rotation, **rect))
                elif self.mode == "deconstruct":
                    self.issue(cmdlib.make("deconstruct_area", **rect))
                elif self.mode == "harvest_area":
                    self.issue(cmdlib.make("harvest_area", **rect))
                    self.mode = None
                elif self.mode == "hunt_area":
                    self.issue(cmdlib.make("hunt_area", **rect))
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
                self._handle_click_select(event.pos, shift_held, screen_w, screen_h)
            else:
                for c in self.colonists: c.selected = False
                self.selected_building = None
                self.selected_stockpile = None
                self.selected_item_stack = None
                for c in self.colonists:
                    if (c.hp > 0 and c.owner_id == self.local_player
                            and c.current_tile() in self.selection.selected_tiles):
                        c.selected = True
            self.left_down_pos = None
            self.left_drag_moved = False

    def _handle_click_select(self, pos, shift_held, screen_w, screen_h):
        wx, wy = self.camera.screen_to_world(*pos)
        tx, ty = self.camera.screen_to_tile(*pos)
        hit_col = None
        for c in self.colonists:
            if c.hp <= 0 or c.owner_id != self.local_player: continue   # 只能选中自己的小人
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
            self.shud.set_target(hit_sp, self._L(pos), self.ui_w, self.ui_h)
            return

        if not shift_held:
            for c in self.colonists: c.selected = False
            self.selected_building = None
            self.selected_stockpile = None
            self.selected_item_stack = None

    def tick_ui(self, dt_raw):
        if self.toast_timer > 0:
            self.toast_timer -= dt_raw
        if self.warning_timer > 0:
            self.warning_timer -= dt_raw
        else:
            attacked = [c for c in self.colonists if c.hp > 0 and c.hit_flash > 0.1]
            if attacked:
                names = ", ".join([c.name for c in attacked[:3]])
                if len(attacked) > 3: names += "..."
                self.warning_text = f"警告: {names} 正在遭受攻击！"
                self.warning_timer = 2.0

        # —— 以下原本在 step() 末尾：纯 UI / 渲染状态，用真实帧时间，不属于模拟 ——
        # 选中对象失效时清掉选择
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

        # 特效淡出、战斗日志淡出：渲染用，走真实时间
        self.effects = [ef for ef in self.effects if ef.update(dt_raw)]
        self.log.update(dt_raw)

    def state_hash(self):
        """整个模拟状态的短哈希：联机时两端定期比对，不一致即分叉。"""
        from core.state_hash import world_hash
        return world_hash(self)

    def state_sections(self):
        """分区摘要，用来定位分叉发生在哪一块（小人/动物/物品……）。"""
        from core.state_hash import world_sections
        return world_sections(self)

    def sim_step(self):
        """推进一个回合：先执行本回合到期的玩家指令；若没有暂停，再推进世界一个 tick。
        固定步长 TICK_DT，与帧率、倍速、渲染完全无关。
        由 main 的累加器循环（单机）或 net.session（联机）调用。"""
        self.flush_commands()
        if self.game_speed > 0:
            self._world_step()
        self.turn += 1

    def _world_step(self):
        """推进世界恰好一个 tick（纯模拟）。"""
        dt = TICK_DT

        self.game_time.update()
        self.farms.update(dt)
        self.room_mgr.update(dt)

        for c in self.colonists:
            c.update_needs(dt, self.game_time)
            c.check_urgent_needs(self.world, self.items, self.stockpiles, self.buildings)
            # 建造锁小人优先接回原建造任务
            if c.build_lock is not None:
                c._retry_build(self.world, self.buildings, self.items, self.stockpiles)
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
                ax, ay = self.rng.randint(5, MAP_WIDTH - 5), self.rng.randint(5, MAP_HEIGHT - 5)
                if self.world.is_walkable(ax, ay):
                    is_safe = True
                    for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                        if not self.world.is_walkable(ax + dx, ay + dy):
                            is_safe = False; break
                    if is_safe:
                        self.animals.append(Animal(ax, ay, self.rng.choice(["rabbit", "rabbit", "deer", "deer", "deer"]), ctx=self.ctx))
                        break

        self.enemy_invasion_timer -= dt
        if self.enemy_invasion_timer <= 0:
            self.enemy_invasion_timer = self.game_time.day_length_sec * 3
            if self.rng.random() < 0.5:
                count = self.rng.randint(1, 3)
                for _ in range(count):
                    side = self.rng.randint(0, 3)
                    if side == 0:
                        ex, ey = self.rng.randint(5, MAP_WIDTH - 5), 5
                    elif side == 1:
                        ex, ey = self.rng.randint(5, MAP_WIDTH - 5), MAP_HEIGHT - 5
                    elif side == 2:
                        ex, ey = 5, self.rng.randint(5, MAP_HEIGHT - 5)
                    else:
                        ex, ey = MAP_WIDTH - 5, self.rng.randint(5, MAP_HEIGHT - 5)
                    if self.world.is_walkable(ex, ey):
                        self.enemies.append(Enemy(ex, ey, self.rng.choice(["club", "spear", "longsword", "fist"]), ctx=self.ctx))
                self.log.add(f"警告：发现 {count} 名敌人入侵！", (255, 50, 50))
                self.warning_text = f"警告：发现 {count} 名敌人入侵！"
                self.warning_timer = 3.0

        # 每个 tick 都消费 recent_shot（一帧可能跑多个 tick，留到渲染时再取会丢弹道）
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
                c._release_job()      # 否则他占着的柜子/工作台/蓝图会永远被占用
                c.queue.clear()
                if c.bed_tile is not None:
                    b = self.buildings.get_building_at(c.bed_tile[0], c.bed_tile[1])
                    if b and b.occupied_by == c.id:
                        b.occupied_by = None
        self.colonists = [c for c in self.colonists if c.hp > 0]

        for e in self.enemies:
            if e.hp <= 0:
                self.log.add(f"{e.name} 被击杀", (100, 255, 100))
        self.enemies = [e for e in self.enemies if e.hp > 0]

    def draw(self, surface, dt_raw):
        screen_w, screen_h = surface.get_size()
        self._update_ui_scale(screen_w, screen_h)
        mouse_pos = pygame.mouse.get_pos()
        lmouse = self._L(mouse_pos)

        surface.fill(BLACK)
        self.world.draw(surface, self.camera)
        for (tx, ty) in self.ctx.designated_harvests:
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
            if lmouse[1] < self.ui_h - bottom_h:                     # 鼠标在底部界面上时不画建造预览
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
        for c in self.colonists:
            c.draw(surface, self.camera, self.font)
            if self.num_players > 1 and c.hp > 0:
                self._draw_owner_mark(surface, c)
        for e in self.enemies: e.draw(surface, self.camera, self.font)
        for ef in self.effects: ef.draw(surface, self.camera)
        self.selection.draw(surface, self.camera)

        light = self.game_time.get_light_level()
        if light < 1.0:
            shade = pygame.Surface((screen_w, screen_h))
            shade.fill((0, 0, 30))
            shade.set_alpha(int((1.0 - light) * 160))
            surface.blit(shade, (0, 0))

        # ---- 界面：画在逻辑尺寸画布上再缩放叠加（缩放为 1.0 时直接画在屏幕上）----
        ui = self.ui_layer.begin(surface, self.ui_scale)
        self._draw_ui(ui, self.ui_w, self.ui_h)
        self.ui_layer.end(surface)

    def _draw_ui(self, surface, screen_w, screen_h):
        """所有界面元素。surface / screen_w / screen_h 都是界面逻辑尺寸下的。"""
        speed_text = "暂停" if self.game_speed == 0 else f"{int(self.game_speed)}x"
        info = (f"{self.game_time.time_str()} | 速度 {speed_text} | 殖民者 {len(self.colonists)} | "
                f"敌人 {len(self.enemies)} | 动物 {len(self.animals)}")
        surface.blit(self.font_big.render(info, True, WHITE), (10, 10))
        if self.player_profiles:
            self._draw_player_bar(surface)
        if self.net_status:
            ns = self.font.render(self.net_status, True, (255, 220, 120))
            surface.blit(ns, (surface.get_width() - ns.get_width() - 12, 12))

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
                "Ctrl + / Ctrl - : 放大 / 缩小界面（Ctrl 0 复位）",
                "T : 切换 房间美观度 透视"
            ]
            for i, txt in enumerate(keys_text):
                line = self.font.render(txt, True, WHITE)
                help_surf.blit(line, (30, 60 + i * 26))
            surface.blit(help_surf, (screen_w // 2 - 300, screen_h // 2 - 240))

        if self.toast_timer > 0 and self.toast_text:
            t = self.font_big.render(self.toast_text, True, (255, 255, 255))
            bg = pygame.Surface((t.get_width() + 24, t.get_height() + 12), pygame.SRCALPHA)
            bg.fill((0, 0, 0, 190))
            x0, y0 = screen_w // 2 - bg.get_width() // 2, screen_h // 2 - 150
            surface.blit(bg, (x0, y0))
            surface.blit(t, (x0 + 12, y0 + 6))
