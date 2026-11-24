# ui/menu.py
"""主菜单 + 联机大厅。

结构：
  MenuModel   纯逻辑（状态机、房间列表、文字输入、键鼠操作）。不依赖 pygame，可以在无窗口环境里完整测试。
  run_menu    pygame 外壳：把鼠标/键盘事件翻译成 MenuModel 的调用，并把 layout() 的结果画出来。

界面流程：
  主菜单 ─ 单人游戏 ───────────────────────────────→ 开始单机
         └ 多人游戏 → 联机大厅（房间列表，自动搜索）
                        ├ 点击某个房间 → 加入 → 开始联机
                        └ 创建房间 → 输入房间名 → 等待玩家加入（持续广播）→ 开始联机
"""
import os
import socket
import time

from net.discovery import RoomBeacon, RoomFinder, DISC_PORT
from net.session import LockstepSession, DEFAULT_PORT, PROTO, get_lan_ip
from core.version import GAME_VERSION, DISPLAY_NAME

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
        self.screen = "main"
        self.sel = 0
        self.result = None
        self.text = ""                    # 房间名输入框
        self.message = []                 # message 页的文字
        self.message_back = "main"
        self.finder = None
        self.beacon = None
        self.session = None
        self.room_name = ""
        self.room_id = ""
        self._join_room = None
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
            label("殖民地建设 · 手动指挥 · 局域网双人联机", h // 2 - 130, color="dim")
            button("单人游戏", h // 2 - 70, "single")
            button("多人游戏", h // 2 + 2, "multi")
            button("退出", h // 2 + 74, "quit")

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
            label(f"房间「{self.room_name}」已创建", h // 2 - 130, big=True)
            label("正在等待其他玩家加入…", h // 2 - 70)
            if self.session is not None:
                label(f"同一局域网的玩家会在房间列表里看到你；也可以直连  {get_lan_ip()}:{self.session.port}",
                      h // 2 - 30, color="dim")
            button("关闭房间", h // 2 + 30, "cancel_host")

        elif self.screen == "joining":
            name = self._join_room["name"] if self._join_room else ""
            label(f"正在加入「{name}」…", h // 2 - 60, big=True)
            button("取消", h // 2 + 10, "cancel_join")

        elif self.screen == "message":
            for i, line in enumerate(self.message):
                label(line, h // 2 - 70 + i * 32, big=(i == 0))
            button("确定", h // 2 - 70 + len(self.message) * 32 + 30, "ok", bw=200)

        self._last_widgets = ws
        sel = [i for i, x in enumerate(ws) if x.selectable]
        if sel:
            self.sel = min(self.sel, len(sel) - 1)
        return ws

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
            elif sel:
                self.activate(sel[min(self.sel, len(sel) - 1)])
        elif name == "escape":
            self.do({"main": "quit", "lobby": "back", "create": "back_lobby", "hosting": "cancel_host",
                     "joining": "cancel_join", "message": "ok"}.get(self.screen, "back"))
        elif name == "backspace" and self.screen == "create":
            self.text = self.text[:-1]

    def text_input(self, s):
        if self.screen == "create":
            self.text = (self.text + "".join(ch for ch in s if ch.isprintable()))[:NAME_MAX]

    def activate(self, wd):
        self.do(wd.action, wd.data)

    # ---------------- 动作 ----------------
    def do(self, action, data=None):
        if action == "single":
            self.result = {"mode": "single"}
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
        elif action == "cancel_host":
            self._close_hosting()
            self.go("lobby")
        elif action == "join":
            room = next((r for r in self.rooms() if r["id"] == data), None)
            if room is not None:
                self._join_room = room
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
                self.session = LockstepSession.host(port=self.game_port, seed=self.seed, delay=self.delay)
            except OSError:                                           # 默认端口被占用：换一个空闲端口
                self.session = LockstepSession.host(port=0, seed=self.seed, delay=self.delay)
        except OSError as e:
            self.show_message(["创建房间失败", str(e)], back="lobby")
            return
        self.room_name = name
        self.room_id = os.urandom(4).hex()
        self.beacon = RoomBeacon(self.room_id, name, self.session.port, port=self.disc_port, targets=self.targets)
        self.go("hosting")

    # ---------------- 每帧更新 ----------------
    def update(self, now=None):
        now = self.clock() if now is None else now
        if self.screen == "lobby" and self.finder is not None:
            self.finder.update(now)
        elif self.screen == "hosting":
            self.beacon.update(now)
            self.session.pump()
            if self.session.state == "ready":
                self.beacon.close(); self.beacon = None
                self.result = {"mode": "host", "session": self.session}
            elif self.session.state in ("failed", "disconnected"):
                self.show_message(["房间出错了", "与玩家的连接中断了，请重新创建房间"], back="lobby")
        elif self.screen == "joining":
            if self.session is None:
                room = self._join_room
                self.session = LockstepSession.join(room["ip"], room["port"], timeout=3.0)   # 局域网内很快；这一步会短暂阻塞
            self.session.pump()
            if self.session.state == "ready":
                self.result = {"mode": "join", "session": self.session}
            elif self.session.state in ("failed", "disconnected"):
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
        elif wd.kind == "input":
            pygame.draw.rect(screen, (30, 33, 42), (wd.x, wd.y, wd.w, wd.h), border_radius=6)
            pygame.draw.rect(screen, (140, 170, 220), (wd.x, wd.y, wd.w, wd.h), 2, border_radius=6)
            cursor = "|" if int(time.monotonic() * 2) % 2 == 0 else ""
            surf = big.render(wd.text + cursor, True, (255, 255, 255))
            screen.blit(surf, (wd.x + 14, wd.y + (wd.h - surf.get_height()) // 2))
    ver = font.render(f"v{GAME_VERSION}", True, (90, 95, 105))
    screen.blit(ver, (w - ver.get_width() - 12, h - 28))
    foot = {"main": "↑↓ 选择   Enter 确认   Esc 退出", "lobby": "点击房间加入   Esc 返回",
            "create": "输入名字后按 Enter 创建   Esc 取消", "hosting": "Esc 关闭房间",
            "joining": "Esc 取消", "message": "Enter 确定"}.get(model.screen, "")
    if foot:
        surf = font.render(foot, True, (110, 115, 125))
        screen.blit(surf, (w // 2 - surf.get_width() // 2, h - 28))


def run_menu(screen, fonts, clock, cfg=None):
    """显示菜单直到玩家做出选择，返回 {"mode": "single"/"host"/"join"/"quit", ["session": ...]}。"""
    import pygame
    model = MenuModel(cfg)
    try:
        pygame.key.start_text_input()
    except Exception:                                                    # noqa: BLE001
        pass
    keymap = {pygame.K_UP: "up", pygame.K_DOWN: "down", pygame.K_RETURN: "enter",
              pygame.K_KP_ENTER: "enter", pygame.K_ESCAPE: "escape", pygame.K_BACKSPACE: "backspace"}
    try:
        while model.result is None:
            for event in pygame.event.get():
                w, h = screen.get_size()
                if event.type == pygame.QUIT:
                    model.result = {"mode": "quit"}
                elif event.type == pygame.VIDEORESIZE:
                    screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                elif event.type == pygame.MOUSEMOTION:
                    model.hover(event.pos, w, h)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    model.click(event.pos, w, h)
                elif event.type == pygame.KEYDOWN and event.key in keymap:
                    model.key(keymap[event.key])
                elif event.type == pygame.TEXTINPUT:
                    model.text_input(event.text)
            model.update()
            draw_menu(screen, fonts, model)
            pygame.display.flip()
            clock.tick(30)
    finally:
        try:
            pygame.key.stop_text_input()
        except Exception:                                                # noqa: BLE001
            pass
        model.close()
    return model.result
