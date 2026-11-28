# world/game_world.py
import random
import pygame
from core.audio import weapon_sound

from ui.tutorial import Tutorial
from ui.game_menu import GameMenu
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
from entities.animal import Animal, pick_species
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
        from systems.zones import ZoneManager
        self.zones = ZoneManager()                       # 持续采集/狩猎区
        self._booting = True                             # 开局布置物资时不发落地声
        self._res_sound_seen = False
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
        self.pointer_pos = None            # 触屏模式：手指位置（代替真实鼠标位置）
        self.touch_shift = False           # 触屏"排队"开关：等价于按住 Shift
        from core.touch import TouchAdapter
        self.touch = TouchAdapter(self)
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
                c.gender = "male" if k % 2 == 0 else "female"        # 默认男女交替；玩家在资料页选了性别后由 apply_genders 覆盖
                self.colonists.append(c)

        spawn_attempts = 0
        while len(self.animals) < self.INITIAL_ANIMALS and spawn_attempts < 800:
            spawn_attempts += 1
            ax, ay = self.rng.randint(5, MAP_WIDTH - 5), self.rng.randint(5, MAP_HEIGHT - 5)
            if self.world.is_walkable(ax, ay):
                is_safe = True
                for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                    if not self.world.is_walkable(ax + dx, ay + dy):
                        is_safe = False; break
                if is_safe:
                    self.animals.append(Animal(ax, ay, pick_species(self.rng), ctx=self.ctx))

        self.animal_respawn_timer = 10.0
        self.meteor_timer = self.game_time.day_length_sec * 2.5       # 第 3 天前后第一次陨石
        self.meteors_spawned = 0
        from systems.quests import QuestManager
        self.quests = QuestManager(self.game_time.day_length_sec)    # 支线任务
        from ui.quest_menu import QuestMenu
        self.quest_menu = QuestMenu(font)
        from ui.music_panel import MusicPanel
        self.music_panel = MusicPanel(font)
        self.zone_erase = False                          # 采集/狩猎区：False=划定，True=擦除
        self.zone_btns = []                              # [(rect, id)] 区域工具条（界面逻辑坐标）
        self.herd_timer = self.game_time.day_length_sec * 1.5      # 兽群迁徙
        self.herds_spawned = 0
        self.MAX_ANIMALS = self.MAX_ANIMALS_CAP
        self.enemy_invasion_timer = self.game_time.day_length_sec * 3
        self.waves_spawned = 0

        self.mode = None
        self.current_build_kind = None
        self.current_build_mat = None
        self.build_rotation = 0
        self.show_help = False
        from core.audio import NullAudio
        self.audio = NullAudio()                         # 音频：main 会换成真正的 AudioManager（纯播放，不影响模拟）
        self._nb_prev, self._res_prev, self._battle_until = 0, len(self.world.resource_hp), 0.0
        self.menu = GameMenu()                           # 游戏中菜单（M）
        self.app_request = None                          # 需要 main 处理的请求：fullscreen/menu/quit/ui_plus/ui_minus
        self.tutorial = Tutorial()                       # 新手教程（F1 / 首次启动 / 主菜单）
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
        self.ctx.sfx_hook = self._sound_from_sim         # 模拟里的采集/脚步声（纯显示）
        self.items.on_drop = self._item_dropped          # 物品落地声（纯显示）
        self._booting = False

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

    def apply_genders(self, genders):
        """genders[i] = 玩家 i 选的性别（"male"/"female"）。该玩家第一个小人是他的角色，其余男女交替。
        只改外观（gender 不进状态哈希），所以各端即使不一致也不会造成不同步。"""
        for pl, g in enumerate(genders):
            mine = [c for c in self.colonists if c.owner_id == pl]
            other = "female" if g == "male" else "male"
            for i, c in enumerate(mine):
                c.gender = g if i % 2 == 0 else other

    def set_profiles(self, roster):
        """联机开局后由 main 调用：roster = [{"name","av"(base64 或 None)}]，按玩家编号排列。"""
        from core.profile import decode_avatar, gender_from_wire
        from ui.avatar import make_avatar_surface
        self.apply_genders([gender_from_wire(r.get("g")) for r in (roster or [])])
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
        limit = surface.get_width() - 190          # 右上角是资源显示，玩家栏不要伸过去；人多时自动换行
        for i, pr in enumerate(self.player_profiles):
            gone = i in self.gone_players
            label = pr["name"] + (" (我)" if i == self.local_player else "") + (" (已离开)" if gone else "")
            txt = self.font.render(label, True, (150, 150, 150) if gone else (255, 255, 255))
            w = 32 + 10 + txt.get_width() + 12
            if x > 10 and x + w > limit:
                x, y = 10, y + 42
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

    def _place_hud(self):
        """小人面板：左下角、在底部界面（工具栏/建造菜单）上方。底部界面高度随模式变化，所以每次都重新摆。"""
        n = len(self.selected_colonists())
        self.hud.layout(self.ui_h, self.get_bottom_ui_height(), n)

    def _L(self, pos):
        """窗口坐标 → 界面逻辑坐标。界面的点击判定一律用它；地图相关（相机/选择框）仍用窗口坐标。"""
        return to_logical(pos, self.ui_scale)

    def set_ui_pref(self, pref):
        self.ui_pref = pref
        self._update_ui_scale(*self.native_size)
        self.toast_text, self.toast_timer = pref_text(pref), 1.5

    _ITEM_SOUND = {"wood": "drop_wood", "stone": "drop_stone", "iron_ore": "drop_stone",
                   "iron": "drop_metal", "axe": "drop_metal", "stone_pickaxe": "drop_stone", "iron_pickaxe": "drop_metal",
                   "stone_axe": "drop_stone", "stone_spear": "drop_wood", "stone_hammer": "drop_stone",
                   "stone_knife": "drop_stone", "longsword": "drop_metal", "gun": "drop_metal", "club": "drop_wood",
                   "spear": "drop_wood", "dagger": "drop_metal", "iron_spear": "drop_metal", "machete": "drop_metal",
                   "war_hammer": "drop_metal", "bow": "drop_wood", "crossbow": "drop_wood", "pistol": "drop_metal",
                   "rifle": "drop_metal", "shotgun": "drop_metal", "smg": "drop_metal", "sniper": "drop_metal"}

    def _item_dropped(self, kind, tx, ty):
        """物品落到地上：按材质发出对应的落地声（木=咚咚，石=闷响碎石，金属=当啷，其余软物=噗）。"""
        if self._booting:
            return
        self.sfx(self._ITEM_SOUND.get(kind, "drop_soft"), tx * TILE_SIZE + TILE_SIZE / 2, ty * TILE_SIZE + TILE_SIZE / 2)

    def _sound_from_sim(self, name, x, y):
        if name.startswith("done_"):
            self._res_sound_seen = True
        self.sfx(name, x, y)

    def sfx(self, name, x=None, y=None):
        """播放音效。给了世界坐标 (x, y) 时按离镜头中心的距离减小音量。"""
        vol = 1.0
        if x is not None:
            from core.audio import distance_volume
            cx, cy = self.camera.x + self.camera.vw / 2, self.camera.y + self.camera.vh / 2
            vol = distance_volume(((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 / TILE_SIZE)
        self.audio.play(name, vol)

    def drop_file(self, path):
        """窗口被拖入文件：音频 → 加入歌单。返回是否处理。"""
        if self.music_panel.drop_file(path, self.audio):
            self.toast(self.audio.pl.status or "已加入歌单")
            return True
        return False

    def toast(self, text, secs=2.5):
        self.toast_text, self.toast_timer = text, secs

    def _mouse(self):
        """当前指针位置：触屏模式用手指位置，否则用真实鼠标。"""
        return self.pointer_pos if self.pointer_pos is not None else pygame.mouse.get_pos()

    def is_mouse_in_ui(self, mouse_pos):
        """mouse_pos 是窗口坐标（pygame.mouse.get_pos()）。"""
        mouse_pos = self._L(mouse_pos)
        if self.touch.over_toolbar(mouse_pos): return True
        if any(r.collidepoint(mouse_pos) for r, _ in self.zone_btns): return True
        if self.mode == "quests" and self.quest_menu.panel_rect.collidepoint(mouse_pos): return True
        if self.mode == "music" and self.music_panel.panel_rect.collidepoint(mouse_pos): return True
        selected_cols = self.selected_colonists()
        self._place_hud()
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
        """资源总数（只用于显示）。要遍历全部物品堆和建筑，所以按真实时间每 0.25 秒才重算一次（暂停时也会刷新）。"""
        key = (pygame.time.get_ticks() // 250, self.game_time.tick // 15)
        cache = getattr(self, "_totals_cache", None)
        if cache is not None and cache[0] == key:
            return cache[1]
        totals = self._compute_totals()
        self._totals_cache = (key, totals)
        return totals

    def _compute_totals(self):
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
        mouse_pos = self._mouse()
        shift_held = bool(pygame.key.get_mods() & pygame.KMOD_SHIFT) or self.touch_shift
        mouse_in_ui = self.is_mouse_in_ui(mouse_pos)

        if event.type == pygame.VIDEORESIZE:
            return

        if event.type == getattr(pygame, "DROPFILE", -2):       # 拖入音频文件：任何时候都加入歌单
            self.drop_file(event.file)
            return

        if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and getattr(event, "pos", None) is not None
                and (self.menu.active or self.is_mouse_in_ui(event.pos))):
            self.audio.play("click")                        # 点界面的"嗒"声

        if self.tutorial.active:                            # 教程打开时吞掉所有输入（不影响游戏运行）
            if event.type == pygame.KEYDOWN:
                self.tutorial.handle_key(event.key)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and lpos is not None:
                self.tutorial.handle_click(lpos)
            return

        if self.menu.active:                                # 菜单打开时：吞掉所有输入（含鼠标移动、滚屏、拖拽）
            self.menu.ui_pref_text = pref_text(self.ui_pref).replace("界面大小 ", "")
            self.menu.input_text = "触屏" if self.touch.enabled else "电脑"
            act = None
            if event.type == pygame.KEYDOWN:
                act = self.menu.handle_key(event.key)
            elif event.type == pygame.MOUSEMOTION and lpos is not None:
                self.menu.handle_motion(lpos)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and lpos is not None:
                act = self.menu.handle_click(lpos)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self.menu.handle_release()
            if act:
                self._menu_action(act)
            return

        if event.type == pygame.KEYDOWN and event.key == pygame.K_F1:
            self.tutorial.open()
            return

        if event.type == pygame.KEYDOWN:
            if self.mode == "music" and self.music_panel.handle_key(event, self.audio): return
            if self.bhud.handle_key(event, self.selected_building): return
            self._handle_keydown(event, mouse_pos, screen_w, screen_h)
            return

        if event.type == pygame.TEXTINPUT:
            if self.mode == "music" and self.music_panel.handle_text(event.text): return
            self.bhud.handle_text(event, self.selected_building)
            return

        if self.mode == "music" and lpos is not None and (
                event.type == getattr(pygame, "MOUSEWHEEL", -1)
                or (event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5))):
            dy = getattr(event, "y", 0) if event.type == getattr(pygame, "MOUSEWHEEL", -1) else (1 if event.button == 4 else -1)
            if self.music_panel.handle_wheel(self._L(self._mouse()), dy): return

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
                self.audio.play("click")
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
            if self._zone_kind() and self._zone_bar_click(lpos):
                self.left_down_pos = None
                return
            if self.mode == "music" and self.music_panel.handle_click(lpos, self.audio):
                self.left_down_pos = None
                return
            if self.mode == "quests" and self.quest_menu.handle_click(lpos):
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

    def wants_text_input(self):
        """当前是否有数字输入框（熔炉/烹饪台/柜子）处于编辑状态：main 据此开关系统文字输入。"""
        return self.bhud.active_input is not None or self.music_panel.editing

    def edge_scroll(self, mouse_pos, screen_w, screen_h, dt_raw, edge_margin=20):
        """鼠标贴着窗口边缘时滚动视角（纯 UI，用真实时间）。菜单/教程打开时不滚——移动鼠标不会让地图动。"""
        if self.touch.enabled or self.menu.active or self.tutorial.active or self.is_mouse_in_ui(mouse_pos):
            return                                          # 触屏模式没有鼠标，不做边缘滚屏
        v = 600 * dt_raw
        if mouse_pos[0] < edge_margin: self.camera.move_by(-v, 0)
        elif mouse_pos[0] > screen_w - edge_margin: self.camera.move_by(v, 0)
        if mouse_pos[1] < edge_margin: self.camera.move_by(0, -v)
        elif mouse_pos[1] > screen_h - edge_margin: self.camera.move_by(0, v)

    def _menu_action(self, act):
        if act == "resume":
            self.menu.close()
        elif act == "tutorial":
            self.menu.close(); self.tutorial.open()
        elif act == "help":
            self.menu.close(); self.show_help = True
        elif act == "input":
            self.touch.toggle()                 # 电脑 ↔ 触屏；菜单保持打开
        elif act == "settings":
            self.menu.page = "settings"
        else:
            self.app_request = act            # fullscreen / menu / quit / ui_plus / ui_minus：由 main 处理
            if act not in ("ui_plus", "ui_minus") and not (act == "fullscreen" and self.menu.page == "settings"):
                self.menu.close()

    def _handle_keydown(self, event, mouse_pos, screen_w, screen_h):
        if event.key == pygame.K_m:
            self.show_help = False
            self.dragging_cam_right = False                 # 打开菜单时中断拖拽，避免松开鼠标的事件被吞后一直"拖着"
            self.drag_start = self.drag_end = None
            self.left_down_pos = None
            self.menu.open()
            return
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
        if event.key == pygame.K_q:
            self.mode = "quests" if self.mode != "quests" else None; return
        if event.key == pygame.K_g:
            self.mode = "harvest_area" if self.mode != "harvest_area" else None; return
        if event.key == pygame.K_v:
            self.mode = "hunt_area" if self.mode != "hunt_area" else None; return
        if event.key == pygame.K_p:
            self.mode = "music" if self.mode != "music" else None; return
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
        # 单人模式（烹饪台/熔炉恒为单人；研究台/工作台可切换）：新指令抢占，让原来的人放手，避免两人同时用
        # 协作模式：不抢占，人数没满就加入（研究进度叠加 / 共同制造同一件），满员则拒绝
        if not station.team:
            holders = set(station.workers)
            if station.reserved_by is not None: holders.add(station.reserved_by)
            for c2 in self.colonists:
                if c2.id in holders and c2 not in selected: c2._release_job()
            station.reserved_by = None
        group = station.kind in ("research_bench", "workbench")
        ok = False
        for c in (selected if group else selected[:1]):
            ok = bool(assign(c)) or ok
        if not ok:
            self.log.add(fail_msg if not group or not station.team else "这个工作站已满员（可在它的面板里调整协作人数）",
                         (255, 100, 100))

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
            from combat.weapons import EQUIPPABLE
            equip_kinds = list(EQUIPPABLE) + ["stone_pickaxe", "iron_pickaxe"]
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

    def _shift_down(self):
        try:
            return bool(pygame.key.get_mods() & pygame.KMOD_SHIFT) or bool(self.touch_shift)
        except Exception:
            return bool(getattr(self, "touch_shift", False))

    def _zone_kind(self):
        return {"harvest_area": "harvest", "hunt_area": "hunt"}.get(self.mode)

    def _zone_bar_click(self, lpos):
        """采集/狩猎区模式下顶部的小工具条：划定 / 擦除 / 清空。返回是否吞掉点击。"""
        for r, bid in self.zone_btns:
            if r.collidepoint(lpos):
                if bid == "paint": self.zone_erase = False
                elif bid == "erase": self.zone_erase = True
                elif bid == "clear" and self._zone_kind():
                    self.issue(cmdlib.make("zone_clear", kind=self._zone_kind()))
                    self.toast("已清空该区域")
                return True
        return False

    def _draw_zone_bar(self, surface, lw):
        self.zone_btns = []
        kind = self._zone_kind()
        if kind is None:
            return
        name = "采集区" if kind == "harvest" else "狩猎区"
        labels = [("paint", "划定"), ("erase", "擦除"), ("clear", "清空")]
        bw, bh, gap = 84, 34, 8
        total = len(labels) * (bw + gap) + 330
        x = lw // 2 - total // 2
        y = 8
        bar = pygame.Surface((total, bh + 12), pygame.SRCALPHA)
        bar.fill((20, 20, 28, 210))
        surface.blit(bar, (x - 6, y - 6))
        tip = f"{name}：拖动框选{'擦除' if self.zone_erase else '划定'}（Shift=擦除）  共{self.zones.count(kind)}格"
        surface.blit(self.font.render(tip, True, (230, 230, 200)), (x, y + 8))
        bx = x + 330
        for bid, lab in labels:
            r = pygame.Rect(bx, y, bw, bh)
            on = (bid == "paint" and not self.zone_erase) or (bid == "erase" and self.zone_erase)
            pygame.draw.rect(surface, (60, 90, 70) if on else (45, 45, 50), r, border_radius=5)
            pygame.draw.rect(surface, (160, 220, 160) if on else (110, 110, 120), r, 2, border_radius=5)
            t = self.font.render(lab, True, (240, 240, 240))
            surface.blit(t, (r.centerx - t.get_width() // 2, r.centery - t.get_height() // 2))
            self.zone_btns.append((r, bid))
            bx += bw + gap

    def _draw_zones(self, surface):
        vx1, vy1, vx2, vy2 = self.camera.view_tiles()
        zone_mode = self._zone_kind()
        for kind, col in (("harvest", (180, 220, 100)), ("hunt", (220, 100, 150))):
            tiles = self.zones.tiles[kind]
            if not tiles:
                continue
            alpha = 70 if zone_mode == kind else 34
            s = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
            s.fill((*col, alpha))
            for (tx, ty) in tiles:
                if tx < vx1 or tx > vx2 or ty < vy1 or ty > vy2: continue
                sx, sy = self.camera.world_to_screen(tx * TILE_SIZE, ty * TILE_SIZE)
                surface.blit(s, (sx, sy))
                if zone_mode == kind:
                    pygame.draw.rect(surface, col, (sx, sy, TILE_SIZE, TILE_SIZE), 1)

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
                elif self.mode in ("harvest_area", "hunt_area"):
                    kind = "harvest" if self.mode == "harvest_area" else "hunt"
                    erase = self.zone_erase or self._shift_down()
                    self.issue(cmdlib.make("zone_set", kind=kind, on=0 if erase else 1, **rect))   # 留在模式里，可连续划
            self.drag_start = None
            self.drag_end = None

    def _handle_selection(self, event, screen_w, screen_h, shift_held):
        self.selection.handle_event(event, self.camera, self._mouse())
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

    # ---- 敌人入侵：数量/装备规则 ----
    SOLO_ENEMY_CAP = 3
    WAVE_WEAPONS = [
        ["fist", "club"],            # 威胁 0
        ["club", "spear"],           # 1
        ["spear", "axe"],            # 2
        ["axe", "pistol"],           # 3
        ["pistol", "longsword"],     # 4
        ["longsword", "rifle"],      # 5
        ["rifle", "machete"],        # 6
        ["machete", "shotgun", "war_hammer"],   # 7
        ["shotgun", "smg", "war_hammer"],       # 8
        ["smg", "sniper", "shotgun"],           # 9+
    ]

    def enemy_cap(self):
        """单波敌人数上限：联机=玩家总数；单人=3（装备另行削弱）。"""
        return max(1, self.num_players) if self.num_players > 1 else self.SOLO_ENEMY_CAP

    INITIAL_ANIMALS = 40
    MAX_ANIMALS_CAP = 55
    METEOR_MIN_DIST = 40            # 陨石落点距任何小人至少这么多格（取不到就取"最远的候选点"）

    def _spawn_meteor(self):
        """陨石坠落：在远离所有小人的地方生成一堆陨石（铁矿 + 石头）。只用 self.rng，两端一致。"""
        from world.world import T_METEOR, WALKABLE, RESOURCE_MAX_HP
        pts = [c.current_tile() for c in self.colonists if c.hp > 0] or [(MAP_WIDTH // 2, MAP_HEIGHT // 2)]
        best, bd = None, -1
        for _ in range(60):
            tx, ty = self.rng.randint(10, MAP_WIDTH - 10), self.rng.randint(10, MAP_HEIGHT - 10)
            if self.world.get(tx, ty) not in WALKABLE: continue
            d = min(abs(tx - px) + abs(ty - py) for px, py in pts)
            if d > bd: best, bd = (tx, ty), d
            if d >= self.METEOR_MIN_DIST * 1.5: break
        if best is None:
            self.meteor_timer = self.game_time.day_length_sec * 0.5
            return
        cx, cy = best
        n = 0
        for y in range(cy - 2, cy + 3):
            for x in range(cx - 2, cx + 3):
                if self.world.get(x, y) not in WALKABLE: continue
                if self.buildings.get_building_at(x, y) is not None: continue
                dd = (x - cx) ** 2 + (y - cy) ** 2
                if dd == 0 or (dd <= 5 and self.rng.random() < 0.75) or (dd <= 8 and self.rng.random() < 0.3):
                    self.world.tiles[y][x] = T_METEOR
                    self.world.resource_hp[(x, y)] = RESOURCE_MAX_HP[T_METEOR]
                    n += 1
        self.meteors_spawned += 1
        mx = sum(p[0] for p in pts) / len(pts); my = sum(p[1] for p in pts) / len(pts)
        ns = "北" if cy < my - 8 else "南" if cy > my + 8 else ""
        ew = "西" if cx < mx - 8 else "东" if cx > mx + 8 else ""
        msg = f"陨石坠落！在殖民地{ns}{ew or ''}方 ({cx},{cy}) 附近形成了陨石堆（需要镐才能采集）"
        self.log.add(msg, (255, 180, 80))
        self.warning_text = msg
        self.sfx("meteor")
        self.warning_timer = 4.0

    def _spawn_herd(self):
        """兽群迁徙：一群同种动物从地图边缘出现，给猎人送肉送皮。只用 self.rng。"""
        from entities.animal import SPECIES
        species = self.rng.choice(["rabbit", "deer", "sheep", "chicken", "boar", "fox", "deer", "sheep"])
        want = self.rng.randint(5, 8)
        side = self.rng.choice(["北", "南", "西", "东"])
        for _try in range(40):
            if side in ("北", "南"):
                bx, by = self.rng.randint(8, MAP_WIDTH - 9), (5 if side == "北" else MAP_HEIGHT - 6)
            else:
                bx, by = (5 if side == "西" else MAP_WIDTH - 6), self.rng.randint(8, MAP_HEIGHT - 9)
            if self.world.is_walkable(bx, by): break
        else:
            return
        n = 0
        for _ in range(want * 6):
            if n >= want: break
            x, y = bx + self.rng.randint(-3, 3), by + self.rng.randint(-3, 3)
            if self.world.is_walkable(x, y):
                self.animals.append(Animal(x, y, species, ctx=self.ctx)); n += 1
        if n:
            self.herds_spawned += 1
            self.log.add(f"兽群迁徙：{n} 只{SPECIES[species]['name']}出现在地图{side}侧（适合狩猎）", (200, 230, 150))

    def threat_level(self):
        lvl = (self.game_time.day - 1) // 2 + self.waves_spawned
        if self.num_players <= 1:
            lvl -= 1                      # 单人：武器更弱
        return max(0, lvl)

    def _spawn_wave(self):
        """实际生成一波敌人；只按"真正生成成功"的数量播报。"""
        if self.rng.random() >= 0.5:
            return
        lvl = self.threat_level()
        cap = self.enemy_cap()
        cap_by_level = min(cap, 1 + lvl // 2)
        want = self.rng.randint(max(1, cap_by_level - 1), cap_by_level)
        pool = self.WAVE_WEAPONS[min(lvl, len(self.WAVE_WEAPONS) - 1)]
        spawned = 0
        for _ in range(want):
            for _try in range(30):          # 边缘出生点可能不可走，多试几次
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
                    self.enemies.append(Enemy(ex, ey, self.rng.choice(pool), ctx=self.ctx))
                    spawned += 1
                    break
        if spawned == 0:
            self.enemy_invasion_timer = self.game_time.day_length_sec * 0.25   # 没生成成功：不报警，稍后重试
            return
        self.waves_spawned += 1
        msg = f"警告：发现 {spawned} 名敌人入侵！"
        self.log.add(msg, (255, 50, 50))
        self.warning_text = msg
        self.sfx("alarm")
        self.warning_timer = 3.0

    def _world_step(self):
        """推进世界恰好一个 tick（纯模拟）。"""
        dt = TICK_DT

        self.game_time.update()
        self.farms.update(dt)
        self.room_mgr.update(dt)
        self.zones.update(self)

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
        self.quests.animals_killed += sum(1 for a in self.animals if a.hp <= 0)
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
                        self.animals.append(Animal(ax, ay, pick_species(self.rng), ctx=self.ctx))
                        break

        self.meteor_timer -= dt
        if self.meteor_timer <= 0:
            self.meteor_timer = self.game_time.day_length_sec * self.rng.uniform(3.0, 5.0)
            self._spawn_meteor()

        self.herd_timer -= dt
        if self.herd_timer <= 0:
            self.herd_timer = self.game_time.day_length_sec * self.rng.uniform(2.5, 4.5)
            self._spawn_herd()

        self.enemy_invasion_timer -= dt
        if self.enemy_invasion_timer <= 0:
            self.enemy_invasion_timer = self.game_time.day_length_sec * 3
            self._spawn_wave()

        # 每个 tick 都消费 recent_shot（一帧可能跑多个 tick，留到渲染时再取会丢弹道）
        for c in self.colonists:
            if c.recent_shot is not None:
                kind, x1, y1, x2, y2, color = c.recent_shot
                if kind == "shot": self.effects.append(Shot(x1, y1, x2, y2, color))
                else: self.effects.append(MeleeHit(x2, y2, color))
                self.sfx(weapon_sound(c.weapon_key, kind), x1, y1)
                c.recent_shot = None
        for e in self.enemies:
            if e.recent_shot is not None:
                kind, x1, y1, x2, y2, color = e.recent_shot
                if kind == "shot": self.effects.append(Shot(x1, y1, x2, y2, color))
                else: self.effects.append(MeleeHit(x2, y2, color))
                self.sfx(weapon_sound(e.weapon_key, kind), x1, y1)
                e.recent_shot = None

        for c in self.colonists:
            if c.hp <= 0:
                self.log.add(f"{c.name} 倒下了！", (255, 80, 80))
                self.sfx("colonist_down")
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
                self.quests.enemies_killed += 1
                self.sfx("enemy_down", e.x, e.y)
        self.enemies = [e for e in self.enemies if e.hp > 0]
        self.quests.update(self)
        nb = len(self.buildings.buildings)
        if nb > self._nb_prev: self.sfx("build_done")
        self._nb_prev = nb
        nr = len(self.world.resource_hp)
        if nr < self._res_prev and not self._res_sound_seen:
            self.sfx("harvest_done")                 # 没有专属音效的资源被采完（小人采集走 colonist 里的分类音效）
        self._res_prev, self._res_sound_seen = nr, False

    def draw(self, surface, dt_raw):
        screen_w, screen_h = surface.get_size()
        self._update_ui_scale(screen_w, screen_h)
        mouse_pos = self._mouse()
        lmouse = self._L(mouse_pos)

        surface.fill(BLACK)
        self.world.draw(surface, self.camera)
        vx1, vy1, vx2, vy2 = self.camera.view_tiles()
        for (tx, ty) in self.ctx.designated_harvests:
            if tx < vx1 or tx > vx2 or ty < vy1 or ty > vy2: continue
            sx, sy = self.camera.world_to_screen(tx * TILE_SIZE, ty * TILE_SIZE)
            pygame.draw.rect(surface, (180, 220, 100),
                             (sx + 4, sy + 4, TILE_SIZE - 8, TILE_SIZE - 8), 2, border_radius=4)
            txt = self.font_small.render("采", True, (180, 220, 100))
            surface.blit(txt, (sx + TILE_SIZE // 2 - txt.get_width() // 2,
                               sy + TILE_SIZE // 2 - txt.get_height() // 2))

        self._draw_zones(surface)
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
        self._draw_zone_bar(surface, screen_w)

        if self.mode == "build":
            self.build_menu.draw(surface, screen_w, screen_h, screen_h - self.toolbar.height,
                                 self.current_build_kind, self.current_build_mat, totals,
                                 self.research_mgr, self.build_rotation)
        elif self.mode == "research":
            self.research_menu.draw(surface, screen_w, screen_h, self.research_mgr)
        elif self.mode == "quests":
            self.quest_menu.draw(surface, screen_w, screen_h, self)
        elif self.mode == "music":
            self.music_panel.draw(surface, screen_w, screen_h, self.audio)

        self.toolbar.draw(surface, screen_w, screen_h, self.mode)

        selected_cols = self.selected_colonists()
        if selected_cols:
            self._place_hud()
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
                "R : 建造时旋转 / 开启科技树   |   G : 采集区   |   V : 狩猎区",
                "Q : 支线任务面板   |   P : 音乐 / 歌单面板",
                "H / Esc : 打开/关闭此帮助面板   |   F1 : 新手教程   |   M : 游戏菜单",
                "F11 : 切换全屏模式",
                "Ctrl + / Ctrl - : 放大 / 缩小界面（Ctrl 0 复位）",
                "T : 切换 房间美观度 透视"
            ]
            for i, txt in enumerate(keys_text):
                line = self.font.render(txt, True, WHITE)
                help_surf.blit(line, (30, 60 + i * 26))
            surface.blit(help_surf, (screen_w // 2 - 300, screen_h // 2 - 240))

        self.menu.ui_pref_text = pref_text(self.ui_pref).replace("界面大小 ", "")
        self.menu.input_text = "触屏" if self.touch.enabled else "电脑"
        self.menu.panel.audio = self.audio
        import time as _t
        if self.enemies: self._battle_until = _t.monotonic() + 10.0         # 战斗曲：敌人消失后再持续 10 秒，避免来回切
        self.audio.set_music("battle" if _t.monotonic() < self._battle_until else "night" if self.game_time.is_night else "day")
        self.touch.draw(surface, screen_w, screen_h, self.font)
        self.menu.draw(surface, screen_w, screen_h, self.font, self.font_big)
        self.tutorial.draw(surface, screen_w, screen_h, self.font, self.font_big)

        if self.toast_timer > 0 and self.toast_text:
            t = self.font_big.render(self.toast_text, True, (255, 255, 255))
            bg = pygame.Surface((t.get_width() + 24, t.get_height() + 12), pygame.SRCALPHA)
            bg.fill((0, 0, 0, 190))
            x0, y0 = screen_w // 2 - bg.get_width() // 2, screen_h // 2 - 150
            surface.blit(bg, (x0, y0))
            surface.blit(t, (x0 + 12, y0 + 6))
