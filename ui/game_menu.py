# ui/game_menu.py
"""游戏中的菜单（按 M 打开）。纯界面，不参与模拟，不影响联机同步。

打开时 GameWorld 会吞掉所有输入、main 会停掉边缘滚屏——移动鼠标不会让地图动。
点按钮或用 ↑↓ + Enter 选择；M / Esc 关闭。
动作：resume 继续 / tutorial 教程 / help 快捷键速查 / input 切换 电脑·触屏 操作模式 / ui_minus、ui_plus 界面大小 / fullscreen / menu 返回主菜单 / quit 退出。
resume/tutorial/help 由 GameWorld 自己处理，其余通过 game.app_request 交给 main（只有 main 能改窗口、退出）。
"""
from ui.settings_panel import SettingsPanel

ITEMS = [
    ("resume", "继续游戏  (M / Esc)"),
    ("tutorial", "新手教程  (F1)"),
    ("help", "快捷键速查  (H)"),
    ("music_vol", "音乐音量"),            # 特殊行：中间显示百分比，左右两个小按钮（← → 键每次 5%）
    ("sfx_vol", "音效音量"),
    ("mute", "静音"),                     # 点一下开关（文字里显示当前状态）
    ("settings", "设置（操作模式 / 更多选项）"),
    ("ui", "界面大小"),                 # 特殊行：中间显示百分比，左右两个小按钮
    ("input", "操作模式"),               # 点一下在 电脑 / 触屏 之间切换（文字里显示当前模式）
    ("fullscreen", "全屏 / 窗口  (F11)"),
    ("menu", "返回主菜单  (F10)"),
    ("quit", "退出游戏"),
]


STEP_ROWS = ("ui", "music_vol", "sfx_vol")        # 带 - / + 小按钮的行
VOL_KIND = {"music_vol": "music", "sfx_vol": "sfx"}


class GameMenu:
    W = 360

    def __init__(self):
        self.active = False
        self.sel = 0
        self.rects = {}            # 名称 -> Rect（逻辑坐标，绘制时更新）
        self.ui_pref_text = ""
        self.input_text = "电脑"
        self.page = "main"                  # "main" 菜单 / "settings" 设置页
        self.panel = SettingsPanel()

    def open(self):
        self.active = True
        self.sel = 0
        self.page = "main"

    def close(self):
        self.active = False

    def toggle(self):
        self.close() if self.active else self.open()

    # 返回动作名（或 None）
    def _from_panel(self, act):
        if act == "back":
            self.page = "main"
            return None
        return act

    # ---- 音量（直接改音频管理器，立即存盘；纯显示，不影响模拟）----
    def _vol_pct(self, name):
        a = self.panel.audio
        return int(round((a.music_vol if VOL_KIND[name] == "music" else a.sfx_vol) * 100))

    def _vol_step(self, name, d):
        a = self.panel.audio
        cur = a.music_vol if VOL_KIND[name] == "music" else a.sfx_vol
        v = max(0.0, min(1.0, round(cur * 20 + d) / 20.0))            # 每次 5%
        (a.set_music_volume if VOL_KIND[name] == "music" else a.set_sfx_volume)(v)
        a.save()
        if VOL_KIND[name] == "sfx":
            a.play("click")                                           # 调音效音量时放一声给你听

    def _toggle_mute(self):
        a = self.panel.audio
        a.set_muted(not a.muted)
        a.save()

    def handle_key(self, key):
        import pygame
        if self.page == "settings":
            if key == pygame.K_m:
                self.close()
                return "resume"
            return self._from_panel(self.panel.handle_key(key))
        if key in (pygame.K_ESCAPE, pygame.K_m):
            self.close()
            return "resume"
        if key == pygame.K_UP:
            self.sel = (self.sel - 1) % len(ITEMS)
        elif key == pygame.K_DOWN:
            self.sel = (self.sel + 1) % len(ITEMS)
        elif key == pygame.K_LEFT and ITEMS[self.sel][0] == "ui":
            return "ui_minus"
        elif key == pygame.K_RIGHT and ITEMS[self.sel][0] == "ui":
            return "ui_plus"
        elif key in (pygame.K_LEFT, pygame.K_RIGHT) and ITEMS[self.sel][0] in VOL_KIND:
            self._vol_step(ITEMS[self.sel][0], -1 if key == pygame.K_LEFT else 1)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            name = ITEMS[self.sel][0]
            if name == "mute":
                self._toggle_mute()
                return None
            return None if name in STEP_ROWS else name
        return None

    def handle_release(self):
        if self.page == "settings":
            self.panel.handle_release()

    def handle_motion(self, pos):
        if self.page == "settings":
            self.panel.handle_motion(pos)
            return
        for i, (name, _) in enumerate(ITEMS):
            r = self.rects.get(name)
            if r and r.collidepoint(pos):
                self.sel = i
                return

    def handle_click(self, pos):
        if self.page == "settings":
            return self._from_panel(self.panel.handle_click(pos))
        for name in ("ui_minus", "ui_plus"):
            r = self.rects.get(name)
            if r and r.collidepoint(pos):
                return name
        for vn in VOL_KIND:
            for suffix, d in (("_minus", -1), ("_plus", 1)):
                r = self.rects.get(vn + suffix)
                if r and r.collidepoint(pos):
                    self._vol_step(vn, d)
                    return None
        for name, _ in ITEMS:
            r = self.rects.get(name)
            if r and r.collidepoint(pos) and name not in STEP_ROWS:
                if name == "mute":
                    self._toggle_mute()
                    return None
                return name
        return None

    def draw(self, surface, w, h, font, font_big):
        if not self.active:
            return
        import pygame
        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 140))
        surface.blit(dim, (0, 0))
        if self.page == "settings":
            self.panel.input_text, self.panel.ui_text = self.input_text, self.ui_pref_text
            self.panel.draw(surface, w, h, font, font_big)
            return
        row_h, gap = 40, 8
        ph = 70 + len(ITEMS) * (row_h + gap) + 36
        pw = self.W
        x, y = w // 2 - pw // 2, max(10, h // 2 - ph // 2)
        panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
        panel.fill((20, 22, 28, 245))
        surface.blit(panel, (x, y))
        pygame.draw.rect(surface, (100, 160, 220), (x, y, pw, ph), 2, border_radius=8)
        t = font_big.render("游戏菜单", True, (120, 180, 240))
        surface.blit(t, (x + pw // 2 - t.get_width() // 2, y + 18))
        self.rects = {}
        ry = y + 60
        for i, (name, label) in enumerate(ITEMS):
            r = pygame.Rect(x + 24, ry, pw - 48, row_h)
            self.rects[name] = r
            sel = (i == self.sel)
            danger = name in ("quit", "menu")
            col = (230, 120, 120) if danger else (120, 180, 240)
            pygame.draw.rect(surface, (60, 80, 105) if sel else (40, 42, 50), r, border_radius=6)
            pygame.draw.rect(surface, col if sel else (90, 95, 110), r, 2, border_radius=6)
            if name in STEP_ROWS:
                val = self.ui_pref_text if name == "ui" else f"{self._vol_pct(name)}%"
                lt = font.render(f"{label}  {val}", True, (235, 235, 240))
                surface.blit(lt, (r.x + 14, r.centery - lt.get_height() // 2))
                base = "ui" if name == "ui" else name
                for key, sym, bx in ((base + "_minus", "-", r.right - 84), (base + "_plus", "+", r.right - 42)):
                    br = pygame.Rect(bx, r.y + 6, 34, r.h - 12)
                    self.rects[key] = br
                    pygame.draw.rect(surface, (55, 60, 75), br, border_radius=4)
                    pygame.draw.rect(surface, (150, 160, 180), br, 1, border_radius=4)
                    st = font.render(sym, True, (235, 235, 240))
                    surface.blit(st, (br.centerx - st.get_width() // 2, br.centery - st.get_height() // 2))
            else:
                if name == "input": label = f"操作模式：{self.input_text}（点击切换）"
                if name == "mute": label = "静音：已开启（点击取消）" if self.panel.audio.muted else "静音：关闭（点击开启）"
                lt = font.render(label, True, (255, 200, 200) if danger else (235, 235, 240))
                surface.blit(lt, (r.centerx - lt.get_width() // 2, r.centery - lt.get_height() // 2))
            ry += row_h + gap
        note = font.render("↑↓ Enter 选择 · M/Esc 关闭 · 不暂停游戏", True, (130, 135, 150))
        surface.blit(note, (x + pw // 2 - note.get_width() // 2, y + ph - 28))
