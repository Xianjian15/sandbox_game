# core/touch.py
"""触屏操作模式：把手指手势翻译成游戏已有的"鼠标 + 键盘"事件，游戏逻辑一行都不用改（也不影响联机同步）。

两种操作模式
  电脑模式：鼠标 + 键盘（原样）。
  触屏模式：
    · 轻点          = 左键点击（选小人 / 点按钮 / 选建筑）
    · 长按 0.45 秒   = 右键点击（对选中的小人下指令：移动、采集、攻击、使用工作台…）
    · 单指拖动      = 平移视角（在"拖拽类模式"下——建造区域/库存区/采集/狩猎/农田/拆除，或打开"框选"开关时——
                       改为左键拖框）
    · 双指拖动      = 平移视角（任何时候）
    · 左侧工具栏     = 指令(轻点即右键) / 框选 / 排队(=Shift) / 取消(Esc) / 速度(空格) / 建造 B / 研究 R / 农业 F /
                       库存 S / 拆除 X / 菜单 M
自动切换：电脑模式下第一次检测到手指触摸，会自动进入触屏模式（菜单 M 里可以切回）。
"""
import pygame

LONG_PRESS_MS = 450
MOVE_SLOP = 14            # 手指移动超过这么多像素才算"拖动"
BTN = 54                  # 工具栏按钮边长（界面逻辑像素）
GAP = 6

# (id, 标签, 类型, 键)   类型：toggle 开关 / key 发一个按键
BUTTONS = [
    ("cmd", "指令", "toggle", None),
    ("box", "框选", "toggle", None),
    ("queue", "排队", "toggle", None),
    ("esc", "取消", "key", "K_ESCAPE"),
    ("speed", "速度", "key", "K_SPACE"),
    ("build", "建造", "key", "K_b"),
    ("research", "研究", "key", "K_r"),
    ("farm", "农业", "key", "K_f"),
    ("stock", "库存", "key", "K_s"),
    ("decon", "拆除", "key", "K_x"),
    ("menu", "菜单", "key", "K_m"),
]
DRAG_MODES = ("stockpile", "farm", "deconstruct", "harvest", "hunt", "build_area", "build")


class TouchAdapter:
    def __init__(self, game, clock=None):
        self.game = game
        self.enabled = False
        self.on_change = None                 # main 注入：保存偏好
        self.clock = clock or (lambda: pygame.time.get_ticks())
        self.flags = {"cmd": False, "box": False, "queue": False}
        self.rects = {}                       # 按钮 id -> Rect（界面逻辑坐标，绘制时更新）
        self.fingers = {}                     # finger_id -> {"start","pos","t0","moved"}
        self.g = None                         # 当前一指手势 {"kind": None/"pan"/"box"/"pressed_ui", "long": bool}
        self.two = None                       # 双指平移：上一帧中点
        self.btn_press = None                 # 按下的工具栏按钮 id

    # ---------- 开关 ----------
    def set_enabled(self, on, notify=True):
        on = bool(on)
        if on == self.enabled: return
        self.enabled = on
        self._reset()
        self.game.touch_shift = False
        self.game.pointer_pos = None
        if not on:
            self.flags = {"cmd": False, "box": False, "queue": False}
        if notify and self.on_change: self.on_change(on)

    def toggle(self):
        self.set_enabled(not self.enabled)
        self.game.toast(("已切换到触屏模式：轻点=选择，长按=下指令，拖动=移动视角" if self.enabled
                         else "已切换到电脑模式（鼠标 + 键盘）"))

    def _reset(self):
        self.fingers.clear(); self.g = None; self.two = None; self.btn_press = None

    # ---------- 工具栏布局/绘制（界面逻辑坐标） ----------
    def layout(self, ui_h):
        self.rects = {}
        x, y0 = 6, 96
        y = y0
        for bid, *_ in BUTTONS:
            if y + BTN > ui_h - 120:               # 放不下就另起一列
                x += BTN + GAP; y = y0
            self.rects[bid] = pygame.Rect(x, y, BTN, BTN)
            y += BTN + GAP

    def toolbar_hit(self, lpos):
        for bid, r in self.rects.items():
            if r.collidepoint(lpos): return bid
        return None

    def over_toolbar(self, lpos):
        return self.enabled and self.toolbar_hit(lpos) is not None

    def draw(self, surface, ui_w, ui_h, font):
        if not self.enabled: return
        self.layout(ui_h)
        g = self.game
        for bid, label, kind, _ in BUTTONS:
            r = self.rects[bid]
            on = self.flags.get(bid, False) if kind == "toggle" else False
            if bid == "build": on = g.mode == "build"
            elif bid == "research": on = g.mode == "research"
            elif bid == "farm": on = g.mode == "farm"
            elif bid == "stock": on = g.mode == "stockpile"
            elif bid == "decon": on = g.mode == "deconstruct"
            s = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
            s.fill((70, 130, 90, 215) if on else (30, 34, 44, 200))
            surface.blit(s, r.topleft)
            pygame.draw.rect(surface, (140, 220, 160) if on else (110, 120, 140), r, 2, border_radius=6)
            txt = label if bid != "speed" else ("暂停" if g.game_speed == 0 else f"{int(g.game_speed)}x")
            t = font.render(txt, True, (240, 240, 245))
            surface.blit(t, (r.centerx - t.get_width() // 2, r.centery - t.get_height() // 2))

    # ---------- 事件入口 ----------
    def handle(self, event, screen_w, screen_h):
        """处理一个 FINGER* 事件。返回 True 表示已消费。"""
        T = pygame
        if event.type == T.FINGERDOWN and not self.enabled:
            self.set_enabled(True)
            self.game.toast("检测到触摸：已切换到触屏模式（菜单 M 里可切回电脑模式）")
        if not self.enabled:
            return False
        px = (event.x * screen_w, event.y * screen_h)
        fid = getattr(event, "finger_id", 0)
        game = self.game
        game._update_ui_scale(screen_w, screen_h)
        game.pointer_pos = (int(px[0]), int(px[1]))
        if event.type == T.FINGERDOWN: self._down(fid, px, screen_w, screen_h)
        elif event.type == T.FINGERMOTION: self._move(fid, px, screen_w, screen_h)
        elif event.type == T.FINGERUP: self._up(fid, px, screen_w, screen_h)
        return True

    # ---------- 合成鼠标/键盘事件 ----------
    def _send(self, type_, screen_w, screen_h, **kw):
        self.game.handle_event(pygame.event.Event(type_, **kw), screen_w, screen_h)

    def _mouse(self, name, pos, sw, sh, button=None):
        pos = (int(pos[0]), int(pos[1]))
        self.game.pointer_pos = pos
        if name == "motion":
            self._send(pygame.MOUSEMOTION, sw, sh, pos=pos, rel=(0, 0), buttons=(0, 0, 0))
        else:
            self._send(pygame.MOUSEBUTTONDOWN if name == "down" else pygame.MOUSEBUTTONUP, sw, sh, pos=pos, button=button)

    def _key(self, keyname, sw, sh):
        key = getattr(pygame, keyname)
        self._send(pygame.KEYDOWN, sw, sh, key=key, mod=0, unicode="")

    def _click(self, button, pos, sw, sh):
        self._mouse("motion", pos, sw, sh)
        self._mouse("down", pos, sw, sh, button)
        self._mouse("up", pos, sw, sh, button)

    # ---------- 手势 ----------
    def _down(self, fid, px, sw, sh):
        lpos = self.game._L(px)
        self.layout(self.game.ui_h)
        if not self.fingers and self.toolbar_hit(lpos) and not self._blocking_overlay():
            self.btn_press = self.toolbar_hit(lpos)
            self.fingers[fid] = {"start": px, "pos": px, "t0": self.clock(), "moved": False}
            return
        self.fingers[fid] = {"start": px, "pos": px, "t0": self.clock(), "moved": False}
        if len(self.fingers) >= 2:
            self._end_one_finger(sw, sh)
            self.btn_press = None
            pts = [f["pos"] for f in self.fingers.values()]
            self.two = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
            return
        self.g = {"kind": None, "long": False}

    def _blocking_overlay(self):
        g = self.game
        return g.menu.active or g.tutorial.active

    def _move(self, fid, px, sw, sh):
        f = self.fingers.get(fid)
        if f is None: return
        f["pos"] = px
        if abs(px[0] - f["start"][0]) + abs(px[1] - f["start"][1]) > MOVE_SLOP: f["moved"] = True
        if self.btn_press is not None: return
        if self.two is not None:                              # 双指平移
            pts = [ff["pos"] for ff in self.fingers.values()]
            mid = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
            self.game.camera.move_by(-(mid[0] - self.two[0]), -(mid[1] - self.two[1]))
            self.two = mid
            return
        g = self.g
        if g is None or g["long"] or not f["moved"]: return
        if g["kind"] is None:                                 # 刚判定为拖动：决定是平移还是框选
            g["kind"] = "box" if (self.game.mode in DRAG_MODES or self.flags["box"]) and not self._blocking_overlay() else "pan"
            if g["kind"] == "box":
                self._mouse("motion", f["start"], sw, sh)
                self._mouse("down", f["start"], sw, sh, 1)
            else:
                self._mouse("down", f["start"], sw, sh, 3)
        self._mouse("motion", px, sw, sh)

    def _end_one_finger(self, sw, sh):
        g, self.g = self.g, None
        if not g or g["kind"] is None: return
        pos = next(iter(self.fingers.values()))["pos"]
        self._mouse("up", pos, sw, sh, 1 if g["kind"] == "box" else 3)

    def _up(self, fid, px, sw, sh):
        f = self.fingers.pop(fid, None)
        if f is None: return
        if self.btn_press is not None:
            bid, self.btn_press = self.btn_press, None
            lpos = self.game._L(px)
            if self.toolbar_hit(lpos) == bid: self._press_button(bid, sw, sh)
            return
        if self.two is not None:
            if not self.fingers: self.two = None
            return
        g, self.g = self.g, None
        if g is None: return
        if g["long"]: return
        if g["kind"] == "box": self._mouse("up", px, sw, sh, 1); return
        if g["kind"] == "pan": self._mouse("up", px, sw, sh, 3); return
        # 轻点
        if self.flags["cmd"] and not self._blocking_overlay():
            self._fire_right(px, sw, sh)
        else:
            self._click(1, px, sw, sh)

    def _fire_right(self, px, sw, sh):
        self._click(3, px, sw, sh)

    def _press_button(self, bid, sw, sh):
        kind, keyname = next((k, n) for b, _, k, n in BUTTONS if b == bid)
        if kind == "toggle":
            self.flags[bid] = not self.flags[bid]
            if bid == "queue": self.game.touch_shift = self.flags["queue"]
            if bid == "cmd" and self.flags["cmd"]: self.flags["box"] = False
            if bid == "box" and self.flags["box"]: self.flags["cmd"] = False
        else:
            self._key(keyname, sw, sh)

    def update(self, screen_w, screen_h):
        """每帧调用：判定长按。"""
        if not self.enabled or self.g is None or self.two is not None or self.btn_press is not None: return
        if len(self.fingers) != 1: return
        f = next(iter(self.fingers.values()))
        g = self.g
        if g["kind"] is None and not g["long"] and not f["moved"] and self.clock() - f["t0"] >= LONG_PRESS_MS \
                and not self._blocking_overlay():
            g["long"] = True
            self._fire_right(f["pos"], screen_w, screen_h)
