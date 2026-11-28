# ui/menu.py
"""主菜单 + 联机大厅。

结构：
  MenuModel   纯逻辑（状态机、房间列表、文字输入、键鼠操作）。不依赖 pygame，可以在无窗口环境里完整测试。
  run_menu    pygame 外壳：把鼠标/键盘事件翻译成 MenuModel 的调用，并把 layout() 的结果画出来。

界面流程：
  主菜单 ─ 单人游戏 ───────────────────────────────→ 开始单机
         └ 多人游戏 → 联机大厅（房间列表，自动搜索）
                        ├ 点击某个房间 → 加入 → 开始联机
                        └ 创建房间 → 输入房间名 → 房间大厅（持续广播，最多 6 人；房主点「开始游戏」）→ 开始联机
                       加入房间后同样停在大厅，等房主开始
"""
import os
import socket
import time

from net.discovery import RoomBeacon, RoomFinder, DISC_PORT
from net.session import LockstepSession, DEFAULT_PORT, PROTO, MAX_PLAYERS, get_lan_ip
from core.version import GAME_VERSION, DISPLAY_NAME
from core.profile import Profile, sanitize_name, decode_avatar, PLAYER_COLORS, NAME_MAX as PNAME_MAX, GENDER_NAMES


def _default_picker():
    from ui.avatar import pick_avatar_file
    return pick_avatar_file()


def _default_loader(path):
    from ui.avatar import load_avatar_file
    return load_avatar_file(path)

NAME_MAX = 20


def friendly_join_error(err):
    """把底层网络报错翻译成玩家看得懂的话（系统原文因语言/系统而异，不适合直接展示）。"""
    err = err or ""
    if "版本" in err:
        return err if "v" in err else "游戏版本与房主不一致，请双方使用相同版本"
    if "没有响应" in err:
        return "主机没有响应，房间可能已满或已关闭"
    return "房间已满，或已被房主关闭"


class Widget:
    __slots__ = ("kind", "x", "y", "w", "h", "text", "action", "enabled", "data", "right")

    def __init__(self, kind, x, y, w, h, text="", action=None, enabled=True, data=None, right=""):
        self.kind, self.x, self.y, self.w, self.h = kind, x, y, w, h
        self.text, self.action, self.enabled, self.data, self.right = text, action, enabled, data, right

    def contains(self, pos):
        return self.x <= pos[0] < self.x + self.w and self.y <= pos[1] < self.y + self.h

    @property
    def selectable(self):
        return self.action is not None and self.enabled


class MenuModel:
    def __init__(self, cfg=None, clock=time.monotonic):
        cfg = cfg or {}
        self.disc_port = int(os.environ.get("RW_DISC_PORT", cfg.get("disc_port", DISC_PORT)))
        env_t = os.environ.get("RW_DISC_TARGETS")
        self.targets = env_t.split(",") if env_t else cfg.get("targets")      # None = 自动（广播）
        self.ttl = cfg.get("ttl", 3.5)
        self.game_port = cfg.get("game_port", DEFAULT_PORT)
        self.delay = cfg.get("delay", 4)
        self.seed = cfg.get("seed", 42)
        self.clock = clock
        self.profile = cfg.get("profile") or Profile()              # 本机玩家资料（用户名 + 头像）
        self.avatar_picker = cfg.get("avatar_picker") or _default_picker     # 可注入（测试用）
        self.avatar_loader = cfg.get("avatar_loader") or _default_loader
        self.edit_avatar = None                                      # 资料页里"尚未保存"的头像
        self.edit_gender = self.profile.gender
        self.profile_msg = ""
        self._raw_cache = {}
        self.screen = "main"
        self.sel = 0
        self.result = None
        self.text = ""                    # 房间名输入框
        self.composition = ""             # 输入法正在组合、尚未确认的文字（拼音等），只用于显示
        self.message = []                 # message 页的文字
        self.message_back = "main"
        self.finder = None
        self.beacon = None
        self.session = None
        self.room_name = ""
        self.room_id = ""
        self._join_room = None
        self._was_in_room = False
        self._entered_lobby = 0.0
        self._lobby_error = ""
        self._last_widgets = []
        try:
            host = socket.gethostname()
        except OSError:
            host = "玩家"
        self.default_name = f"{host}的房间"[:NAME_MAX]

    # ---------------- 页面切换 ----------------
    def go(self, screen):
        if screen != "lobby":
            self._close_finder()
        self.screen = screen
        self.sel = 0
        if screen == "lobby":
            self._open_finder()
        elif screen == "create":
            self.text = self.default_name
        elif screen == "profile":
            self.text = self.profile.name
            self.edit_avatar = self.profile.avatar
            self.edit_gender = self.profile.gender
            self.profile_msg = ""

    def _open_finder(self):
        self._close_finder()
        self.finder = RoomFinder(port=self.disc_port, ttl=self.ttl)
        self._lobby_error = self.finder.error
        self._entered_lobby = self.clock()

    def _close_finder(self):
        if self.finder is not None:
            self.finder.close()
            self.finder = None

    def _close_hosting(self):
        if self.beacon is not None:
            self.beacon.close()
            self.beacon = None
        if self.session is not None and self.result is None:
            self.session.close()
        self.session = None

    def show_message(self, lines, back="main"):
        self._close_hosting()
        self.message = list(lines)
        self.message_back = back
        self.go("message")

    def close(self):
        """菜单退出时清理：关掉搜索、广播。如果已经选定了联机，会话交给游戏，不在这里关。"""
        self._close_finder()
        if self.beacon is not None:
            self.beacon.close()
            self.beacon = None
        if self.session is not None and (self.result is None or self.result.get("mode") not in ("host", "join")):
            self.session.close()

    # ---------------- 布局（也是点击/选择的依据） ----------------
    def rooms(self):
        return self.finder.room_list() if self.finder is not None else []

    def layout(self, w, h):
        cx = w // 2
        ws = []

        def label(text, y, big=False, color="normal"):
            ws.append(Widget("title" if big else "label", cx, y, 0, 0, text, data=color))

        def button(text, y, action, bw=320, bh=52, enabled=True, x=None):
            ws.append(Widget("button", (cx - bw // 2) if x is None else x, y, bw, bh, text, action, enabled))

        if self.screen == "main":
            label(DISPLAY_NAME, h // 2 - 190, big=True)
            label(f"殖民地建设 · 手动指挥 · 局域网多人联机（最多 {MAX_PLAYERS} 人）", h // 2 - 130, color="dim")
            button("单人游戏", h // 2 - 70, "single")
            button("多人游戏", h // 2 + 2, "multi")
            button("新手教程", h // 2 + 74, "tutorial")
            button(f"角色设置（{GENDER_NAMES[self.profile.gender]}）", h // 2 + 146, "profile_main")
            button("退出", h // 2 + 218, "quit")

        elif self.screen == "lobby":
            label("多人游戏 · 局域网房间", 60, big=True)
            rooms = self.rooms()
            top, row_h, row_w = 130, 50, 680
            max_rows = max(1, (h - top - 140) // row_h)
            if not rooms:
                searching = self.clock() - self._entered_lobby
                label("正在搜索房间…" if searching < 3 else "没有找到房间", top + 40, color="dim")
                if self._lobby_error:
                    label(self._lobby_error, top + 80, color="bad")
                elif searching >= 3:
                    label("可以点「创建房间」自己开一个；", top + 80, color="dim")
                    label("找不到朋友的房间？请确认两台电脑在同一个网络，并放行 UDP 47778 / TCP 47777", top + 108, color="dim")
            for i, r in enumerate(rooms[:max_rows]):
                full = r["players"] >= r["max"]
                bad_ver = r["proto"] != PROTO or r.get("ver") != GAME_VERSION
                tag = "已满" if full else (f"版本不符 v{r.get('ver') or '?'}" if bad_ver else "加入")
                ws.append(Widget("row", cx - row_w // 2, top + i * row_h, row_w, row_h - 6, r["name"],
                                 "join", not (full or bad_ver), r["id"],
                                 f"{r['ip']}   {r['players']}/{r['max']}   {tag}"))
            if len(rooms) > max_rows:
                label(f"还有 {len(rooms) - max_rows} 个房间未显示", top + max_rows * row_h + 6, color="dim")
            ws.append(Widget("avatar", 24, 16, 44, 44, "", None, True, (self.profile.avatar, self.profile.name, None)))
            button(f"{self.profile.name}（点击修改资料）", 16, "profile", bw=330, bh=44, x=76)
            by = h - 90
            button("创建房间", by, "create", bw=200, x=cx - 330)
            button("刷新", by, "refresh", bw=200, x=cx - 100)
            button("返回", by, "back", bw=200, x=cx + 130)

        elif self.screen == "create":
            label("创建房间", h // 2 - 150, big=True)
            label("给你的房间起个名字，别人会在列表里看到它：", h // 2 - 90, color="dim")
            ws.append(Widget("input", cx - 260, h // 2 - 55, 520, 52, self.text, None, True, NAME_MAX))
            button("创建", h // 2 + 30, "confirm_create", bw=250, x=cx - 265)
            button("取消", h // 2 + 30, "back_lobby", bw=250, x=cx + 15)

        elif self.screen == "hosting":
            top = max(30, h // 2 - 290)
            n = self.session.player_count() if self.session is not None else 1
            label(f"房间「{self.room_name}」已创建", top, big=True)
            label(f"房间里现在有 {n} / {MAX_PLAYERS} 人" + ("" if n > 1 else "，正在等待其他玩家加入…"), top + 52)
            roster = self.session.lobby_roster() if self.session is not None else [self.profile.to_wire()]
            y = self._roster_rows(ws, roster, cx - 210, top + 100, 420, me=0)
            if self.session is not None:
                label(f"同一局域网的玩家会在房间列表里看到你；也可以直连  {get_lan_ip()}:{self.session.port}",
                      y + 6, color="dim")
            button("开始游戏" if n > 1 else "开始游戏（至少需要 2 人）", y + 44, "start_host", bw=360, enabled=n > 1)
            button("关闭房间", y + 112, "cancel_host")

        elif self.screen == "joining":
            name = self._join_room["name"] if self._join_room else ""
            if self.session is not None and self.session.state == "lobby":
                top = max(30, h // 2 - 250)
                label(f"已加入「{name}」", top, big=True)
                label(f"房间里现在有 {self.session.lobby_n} / {MAX_PLAYERS} 人，等待房主开始游戏…", top + 52)
                roster = self.session.lobby_roster()
                y = self._roster_rows(ws, roster, cx - 210, top + 100, 420, me=self.session.lobby_me)
                button("离开房间", y + 30, "cancel_join")
            else:
                label(f"正在加入「{name}」…", h // 2 - 60, big=True)
                button("取消", h // 2 + 10, "cancel_join")

        elif self.screen == "profile":
            top = max(10, h // 2 - 290)
            label("个人资料", top, big=True)
            label(f"用户名（最多 {PNAME_MAX} 个字）：", top + 60, color="dim")
            ws.append(Widget("input", cx - 200, top + 90, 400, 52, self.text, None, True, PNAME_MAX))
            ws.append(Widget("avatar", cx - 48, top + 165, 96, 96, "", None, True,
                             (self.edit_avatar, self.text or self.profile.name, None)))
            button("选择头像…", top + 285, "pick_avatar", bw=240, x=cx - 260)
            button("清除头像", top + 285, "clear_avatar", bw=240, x=cx + 20)
            label("角色性别（决定你的小人的外观）：", top + 350, color="dim")
            for g, x in (("male", cx - 260), ("female", cx + 20)):
                sel_ = (self.edit_gender == g)
                button(("● " if sel_ else "○ ") + GENDER_NAMES[g] + ("（已选）" if sel_ else ""), top + 378,
                       "gender_" + g, bw=240, x=x)
            label("也可以把图片文件直接拖进这个窗口（png / jpg / bmp / gif）", top + 440, color="dim")
            if self.profile_msg:
                label(self.profile_msg, top + 468, color="bad")
            button("保存", top + 500, "save_profile", bw=240, x=cx - 260)
            button("取消", top + 500, "cancel_profile", bw=240, x=cx + 20)

        elif self.screen == "message":
            for i, line in enumerate(self.message):
                label(line, h // 2 - 70 + i * 32, big=(i == 0))
            button("确定", h // 2 - 70 + len(self.message) * 32 + 30, "ok", bw=200)

        self._last_widgets = ws
        sel = [i for i, x in enumerate(ws) if x.selectable]
        if sel:
            self.sel = min(self.sel, len(sel) - 1)
        return ws

    def _raw(self, b64):
        """名单里的 base64 头像 → 原始像素（带缓存，名单每帧都会重画）。"""
        if not b64:
            return None
        if b64 not in self._raw_cache:
            self._raw_cache[b64] = decode_avatar(b64)
        return self._raw_cache[b64]

    def _roster_rows(self, ws, roster, x, y, w, me=None):
        for i, r in enumerate(roster):
            ws.append(Widget("player", x, y + i * 50, w, 44, r["name"], None, True,
                             (self._raw(r.get("av")), i, i == me), "房主" if i == 0 else ""))
        return y + len(roster) * 50

    def avatar_surface(self, raw, name, idx, size):
        """菜单绘制用：头像图面（带缓存）。没有头像时画默认头像。只在有 pygame 窗口时调用。"""
        from ui.avatar import make_avatar_surface
        key = (bytes(raw) if raw else None, name[:1], idx, size)
        cache = self.__dict__.setdefault("_surf_cache", {})
        if key not in cache:
            import pygame
            font = pygame.font.Font(None, max(12, size))
            try:
                from ui.fonts import load_font
                font = load_font(max(12, int(size * 0.6)))
            except Exception:                                                    # noqa: BLE001
                pass
            cache[key] = make_avatar_surface(raw, name, PLAYER_COLORS[idx % len(PLAYER_COLORS)], font, size)
        return cache[key]

    def _selectable(self):
        return [x for x in self._last_widgets if x.selectable]

    # ---------------- 输入 ----------------
    def click(self, pos, w, h):
        for wd in self.layout(w, h):
            if wd.selectable and wd.contains(pos):
                self.activate(wd)
                return True
        return False

    def hover(self, pos, w, h):
        sel = [x for x in self.layout(w, h) if x.selectable]
        for i, wd in enumerate(sel):
            if wd.contains(pos):
                self.sel = i
                return

    def key(self, name):
        sel = self._selectable()
        if name == "down" and sel:
            self.sel = (self.sel + 1) % len(sel)
        elif name == "up" and sel:
            self.sel = (self.sel - 1) % len(sel)
        elif name == "enter":
            if self.screen == "create":
                self.do("confirm_create")
            elif self.screen == "profile":
                self.do("save_profile")
            elif sel:
                self.activate(sel[min(self.sel, len(sel) - 1)])
        elif name == "escape":
            self.do({"main": "quit", "lobby": "back", "create": "back_lobby", "hosting": "cancel_host",
                     "joining": "cancel_join", "message": "ok", "profile": "cancel_profile"}.get(self.screen, "back"))
        elif name == "backspace" and self.screen in ("create", "profile"):
            if not self.composition:            # 输入法组合中，退格属于输入法，不删已确认的字
                self.text = self.text[:-1]

    def text_editing(self, s):
        """输入法组合中的文字（如拼音）：显示在输入框里，确认后会以 TEXTINPUT 送达。"""
        self.composition = "".join(ch for ch in (s or "") if ch.isprintable()) if self.screen in ("create", "profile") else ""

    def text_input(self, s):
        self.composition = ""
        if self.screen in ("create", "profile"):
            limit = NAME_MAX if self.screen == "create" else PNAME_MAX
            self.text = (self.text + "".join(ch for ch in s if ch.isprintable()))[:limit]

    def drop_file(self, path):
        """玩家把文件拖进窗口：在资料页里当作头像图片。"""
        if self.screen == "profile":
            self._load_avatar(path)

    def _load_avatar(self, path):
        try:
            self.edit_avatar = self.avatar_loader(path)
            self.profile_msg = ""
        except ValueError as e:
            self.profile_msg = str(e)

    def activate(self, wd):
        self.do(wd.action, wd.data)

    # ---------------- 动作 ----------------
    def do(self, action, data=None):
        if action == "single":
            self.result = {"mode": "single"}
        elif action == "tutorial":
            self.result = {"mode": "single", "tutorial": True}      # 开一局单人游戏并直接打开教程
        elif action == "quit":
            self.result = {"mode": "quit"}
        elif action == "multi":
            self.go("lobby")
        elif action == "back":
            self.go("main")
        elif action == "refresh":
            self._open_finder()
        elif action == "create":
            self.go("create")
        elif action == "back_lobby":
            self.go("lobby")
        elif action == "confirm_create":
            self._create_room()
        elif action in ("profile", "profile_main"):
            self.profile_from = "main" if action == "profile_main" else "lobby"
            self.go("profile")
        elif action in ("gender_male", "gender_female"):
            self.edit_gender = action[len("gender_"):]
        elif action == "pick_avatar":
            try:
                path = self.avatar_picker()
            except RuntimeError:
                self.profile_msg = "打不开文件选择窗口，请把图片文件直接拖进这个窗口"
            else:
                if path:
                    self._load_avatar(path)
        elif action == "clear_avatar":
            self.edit_avatar = None
            self.profile_msg = ""
        elif action == "save_profile":
            self.profile.name = sanitize_name(self.text, self.profile.name)
            self.profile.avatar = self.edit_avatar
            self.profile.gender = self.edit_gender
            self.profile.save()
            self.go(getattr(self, "profile_from", "lobby"))
        elif action == "cancel_profile":
            self.go(getattr(self, "profile_from", "lobby"))
        elif action == "start_host":
            if self.session is not None:
                self.session.start_game()
        elif action == "cancel_host":
            self._close_hosting()
            self.go("lobby")
        elif action == "join":
            room = next((r for r in self.rooms() if r["id"] == data), None)
            if room is not None:
                self._join_room = room
                self._was_in_room = False
                self.go("joining")
        elif action == "cancel_join":
            self._close_hosting()
            self._join_room = None
            self.go("lobby")
        elif action == "ok":
            self.go(self.message_back)

    def _create_room(self):
        name = self.text.strip() or self.default_name
        try:
            try:
                self.session = LockstepSession.host(port=self.game_port, seed=self.seed, delay=self.delay, expect=None,
                                                   profile=self.profile.to_wire())
            except OSError:                                           # 默认端口被占用：换一个空闲端口
                self.session = LockstepSession.host(port=0, seed=self.seed, delay=self.delay, expect=None,
                                                   profile=self.profile.to_wire())
        except OSError as e:
            self.show_message(["创建房间失败", str(e)], back="lobby")
            return
        self.room_name = name
        self.room_id = os.urandom(4).hex()
        self.beacon = RoomBeacon(self.room_id, name, self.session.port, max_players=MAX_PLAYERS,
                                 port=self.disc_port, targets=self.targets)
        self.go("hosting")

    # ---------------- 每帧更新 ----------------
    def update(self, now=None):
        now = self.clock() if now is None else now
        if self.screen == "lobby" and self.finder is not None:
            self.finder.update(now)
        elif self.screen == "hosting":
            self.session.pump()
            self.beacon.info["players"] = self.session.player_count()      # 房间列表里实时显示人数
            self.beacon.update(now)
            if self.session.state == "ready":
                self.beacon.close(); self.beacon = None
                self.result = {"mode": "host", "session": self.session}
            elif self.session.state in ("failed", "disconnected"):
                self.show_message(["房间出错了", "网络出现问题，请重新创建房间"], back="lobby")
        elif self.screen == "joining":
            if self.session is None:
                room = self._join_room
                self.session = LockstepSession.join(room["ip"], room["port"], timeout=3.0,
                                              profile=self.profile.to_wire())   # 局域网内很快；这一步会短暂阻塞
            self.session.pump()
            if self.session.state == "lobby":
                self._was_in_room = True
            if self.session.state == "ready":
                self.result = {"mode": "join", "session": self.session}
            elif self.session.state in ("failed", "disconnected"):
                if self._was_in_room:
                    self.show_message(["房间已关闭", "房主离开了房间，请重新加入或自己创建"], back="lobby")
                else:
                    self.show_message(["加入房间失败", friendly_join_error(self.session.error)], back="lobby")


# =====================================================================
# pygame 外壳
# =====================================================================
COLORS = {"normal": (230, 230, 235), "dim": (150, 155, 165), "bad": (230, 110, 100)}


def draw_menu(screen, fonts, model):
    import pygame
    w, h = screen.get_size()
    screen.fill((18, 20, 26))
    for i in range(0, h, 4):                                   # 简单的竖向渐变
        c = 18 + int(14 * i / max(1, h))
        pygame.draw.line(screen, (c, c + 2, c + 8), (0, i), (w, i), 4)
    widgets = model.layout(w, h)
    sel_widgets = [x for x in widgets if x.selectable]
    selected = sel_widgets[model.sel] if sel_widgets and model.sel < len(sel_widgets) else None
    font, big, title = fonts["normal"], fonts["big"], fonts["title"]
    for wd in widgets:
        if wd.kind in ("label", "title"):
            f = title if wd.kind == "title" else big
            surf = f.render(wd.text, True, COLORS.get(wd.data or "normal", COLORS["normal"]))
            screen.blit(surf, (wd.x - surf.get_width() // 2, wd.y))
        elif wd.kind == "button":
            hot = wd is selected
            col = (70, 110, 170) if hot else (45, 50, 62)
            if not wd.enabled: col = (35, 37, 42)
            pygame.draw.rect(screen, col, (wd.x, wd.y, wd.w, wd.h), border_radius=8)
            pygame.draw.rect(screen, (140, 170, 220) if hot else (90, 96, 110), (wd.x, wd.y, wd.w, wd.h), 2, border_radius=8)
            surf = big.render(wd.text, True, (255, 255, 255) if wd.enabled else (110, 110, 115))
            screen.blit(surf, (wd.x + (wd.w - surf.get_width()) // 2, wd.y + (wd.h - surf.get_height()) // 2))
        elif wd.kind == "row":
            hot = wd is selected
            col = (60, 95, 150) if hot else (38, 42, 54)
            if not wd.enabled: col = (30, 32, 38)
            pygame.draw.rect(screen, col, (wd.x, wd.y, wd.w, wd.h), border_radius=6)
            pygame.draw.rect(screen, (120, 150, 200) if hot else (70, 76, 90), (wd.x, wd.y, wd.w, wd.h), 1, border_radius=6)
            tcol = (255, 255, 255) if wd.enabled else (120, 120, 125)
            n = big.render(wd.text, True, tcol)
            screen.blit(n, (wd.x + 14, wd.y + (wd.h - n.get_height()) // 2))
            r = font.render(wd.right, True, (200, 210, 160) if wd.enabled else (120, 120, 125))
            screen.blit(r, (wd.x + wd.w - r.get_width() - 14, wd.y + (wd.h - r.get_height()) // 2))
        elif wd.kind == "avatar":
            raw, nm, _ = wd.data
            surf = model.avatar_surface(raw, nm, 0, wd.w)
            screen.blit(surf, (wd.x, wd.y))
            pygame.draw.rect(screen, (140, 170, 220), (wd.x, wd.y, wd.w, wd.h), 2)
        elif wd.kind == "player":
            raw, idx, is_me = wd.data
            col = PLAYER_COLORS[idx % len(PLAYER_COLORS)]
            pygame.draw.rect(screen, (38, 42, 54), (wd.x, wd.y, wd.w, wd.h), border_radius=6)
            pygame.draw.rect(screen, col, (wd.x, wd.y, wd.w, wd.h), 2, border_radius=6)
            size = wd.h - 8
            screen.blit(model.avatar_surface(raw, wd.text, idx, size), (wd.x + 4, wd.y + 4))
            n = big.render(wd.text + ("（我）" if is_me else ""), True, (255, 255, 255))
            screen.blit(n, (wd.x + size + 16, wd.y + (wd.h - n.get_height()) // 2))
            if wd.right:
                r = font.render(wd.right, True, (200, 210, 160))
                screen.blit(r, (wd.x + wd.w - r.get_width() - 12, wd.y + (wd.h - r.get_height()) // 2))
        elif wd.kind == "input":
            pygame.draw.rect(screen, (30, 33, 42), (wd.x, wd.y, wd.w, wd.h), border_radius=6)
            pygame.draw.rect(screen, (140, 170, 220), (wd.x, wd.y, wd.w, wd.h), 2, border_radius=6)
            cursor = "|" if int(time.monotonic() * 2) % 2 == 0 else ""
            comp = getattr(model, "composition", "")
            head = big.render(wd.text, True, (255, 255, 255)) if wd.text else None
            tail = big.render(comp, True, (255, 220, 120)) if comp else None
            cur = big.render(cursor, True, (255, 255, 255)) if cursor else None
            parts = [x for x in (head, tail, cur) if x is not None]
            total = sum(x.get_width() for x in parts)
            inner = wd.w - 28
            ty = wd.y + (wd.h - big.get_height()) // 2
            ox = wd.x + 14 - max(0, total - inner)          # 文字太长时只显示末尾，光标始终可见
            clip = screen.get_clip()
            screen.set_clip(pygame.Rect(wd.x + 8, wd.y + 2, wd.w - 16, wd.h - 4))
            cx_ = ox
            for x in parts:
                screen.blit(x, (cx_, ty))
                if x is tail:                                # 组合中的文字加下划线
                    pygame.draw.line(screen, (255, 220, 120), (cx_, ty + big.get_height() - 2),
                                     (cx_ + x.get_width(), ty + big.get_height() - 2), 2)
                cx_ += x.get_width()
            screen.set_clip(clip)
    ver = font.render(f"v{GAME_VERSION}", True, (90, 95, 105))
    screen.blit(ver, (w - ver.get_width() - 12, h - 28))
    foot = {"main": "↑↓ 选择   Enter 确认   Esc 退出", "lobby": "点击房间加入   Esc 返回",
            "create": "输入名字后按 Enter 创建   Esc 取消", "hosting": "人齐后点「开始游戏」   Esc 关闭房间", "profile": "输入用户名后按 Enter 保存   Esc 取消",
            "joining": "Esc 离开", "message": "Enter 确定"}.get(model.screen, "")
    if foot:
        surf = font.render(foot, True, (110, 115, 125))
        screen.blit(surf, (w // 2 - surf.get_width() // 2, h - 28))


def _place_ime(screen, model, scale):
    """把输入法候选窗口放到输入框旁边（中文输入必需，否则候选框飘在屏幕角落）。"""
    try:
        import pygame
        for wd in model._last_widgets:
            if wd.kind == "input":
                pygame.key.set_text_input_rect(pygame.Rect(int(wd.x * scale), int(wd.y * scale),
                                                           int(wd.w * scale), int(wd.h * scale)))
                return
    except Exception:                                                    # noqa: BLE001
        pass


def run_menu(screen, fonts, clock, cfg=None):
    """显示菜单直到玩家做出选择，返回 {"mode": "single"/"host"/"join"/"quit", ["session": ...]}。"""
    import pygame
    from core import ui_scale as uis
    cfg = cfg or {}
    model = MenuModel(cfg)
    pref = cfg.get("ui_pref", uis.DEFAULT_PREF)
    on_pref = cfg.get("on_ui_pref")
    layer = uis.UiLayer(alpha=False)
    try:
        pygame.key.start_text_input()
    except Exception:                                                    # noqa: BLE001
        pass
    keymap = {pygame.K_UP: "up", pygame.K_DOWN: "down", pygame.K_RETURN: "enter",
              pygame.K_KP_ENTER: "enter", pygame.K_ESCAPE: "escape", pygame.K_BACKSPACE: "backspace"}
    try:
        while model.result is None:
            for event in pygame.event.get():
                # 菜单画在"逻辑尺寸"画布上再缩放：点击坐标要换算回逻辑坐标
                scale = uis.compute_scale(*screen.get_size(), pref)
                w, h = uis.logical_size(*screen.get_size(), scale)
                if event.type == pygame.KEYDOWN and uis.pref_delta_for_key(event.key, event.mod) is not None:
                    delta = uis.pref_delta_for_key(event.key, event.mod)
                    pref = on_pref(delta) if on_pref else uis.step_pref(pref, delta)
                    continue
                if event.type == pygame.QUIT:
                    model.result = {"mode": "quit"}
                elif event.type == pygame.VIDEORESIZE:
                    screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                elif event.type == pygame.MOUSEMOTION:
                    model.hover(uis.to_logical(event.pos, scale), w, h)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    model.click(uis.to_logical(event.pos, scale), w, h)
                elif event.type == pygame.KEYDOWN and event.key in keymap:
                    model.key(keymap[event.key])
                elif event.type == pygame.TEXTEDITING:
                    model.text_editing(event.text)
                elif event.type == pygame.TEXTINPUT:
                    model.text_input(event.text)
                elif event.type == pygame.DROPFILE:
                    model.drop_file(event.file)
            model.update()
            scale = uis.compute_scale(*screen.get_size(), pref)
            draw_menu(layer.begin(screen, scale), fonts, model)
            layer.end(screen)
            _place_ime(screen, model, scale)
            pygame.display.flip()
            clock.tick(30)
    finally:
        try:
            pygame.key.stop_text_input()
        except Exception:                                                # noqa: BLE001
            pass
        model.close()
    return model.result
