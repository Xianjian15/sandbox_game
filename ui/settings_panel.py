# ui/settings_panel.py
"""设置面板：操作模式 / 音乐音量 / 音效音量 / 静音 / 界面大小 / 全屏。纯界面，坐标用逻辑坐标。

游戏中菜单（GameMenu）和主菜单都用它。面板自己改音量（通过 audio），其余动作以字符串返回，
由使用方处理："input"（切换操作模式）/ "ui_minus" / "ui_plus" / "fullscreen" / "back"。
使用方每帧给它更新：audio、input_text（"电脑"/"触屏"）、ui_text（"100%"）、has_fullscreen。
键盘：↑↓ 选行，←→ 调整，Enter 点击，Esc 返回。鼠标/触屏：点击、拖动滑块。
"""
import pygame
from core.audio import NullAudio

W = 480


class SettingsPanel:
    def __init__(self):
        self.audio = NullAudio()
        self.input_text = "电脑"
        self.ui_text = "100%"
        self.has_fullscreen = True
        self.sel = 0
        self.rects = {}                 # 名称 -> Rect（绘制时更新）
        self.dragging = None            # "music" / "sfx"

    def rows(self):
        r = ["input", "music", "sfx", "mute", "ui"]
        if self.has_fullscreen: r.append("fullscreen")
        r.append("back")
        return r

    # ---- 滑块 ----
    def _set_slider(self, name, v):
        v = max(0.0, min(1.0, v))
        (self.audio.set_music_volume if name == "music" else self.audio.set_sfx_volume)(v)

    def _slider_at(self, name, x):
        r = self.rects.get(name + "_bar")
        if r and r.w > 0:
            self._set_slider(name, (x - r.x) / r.w)

    def _step(self, name, d):
        cur = self.audio.music_vol if name == "music" else self.audio.sfx_vol
        self._set_slider(name, round(cur * 20 + d) / 20.0)          # 每次 5%

    # ---- 输入 ----
    def handle_key(self, key):
        rows = self.rows()
        self.sel = min(self.sel, len(rows) - 1)
        name = rows[self.sel]
        if key == pygame.K_ESCAPE:
            return "back"
        if key == pygame.K_UP:
            self.sel = (self.sel - 1) % len(rows)
        elif key == pygame.K_DOWN:
            self.sel = (self.sel + 1) % len(rows)
        elif key in (pygame.K_LEFT, pygame.K_RIGHT):
            d = -1 if key == pygame.K_LEFT else 1
            if name in ("music", "sfx"):
                self._step(name, d); self.audio.save()
                if name == "sfx": self.audio.play("click")
            elif name == "ui":
                return "ui_plus" if d > 0 else "ui_minus"
            elif name == "input":
                return "input"
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            return self._activate(name)
        return None

    def _activate(self, name):
        if name == "mute":
            self.audio.set_muted(not self.audio.muted); self.audio.save()
            return None
        if name in ("input", "fullscreen", "back"):
            return name
        return None

    def handle_motion(self, pos):
        if self.dragging:
            self._slider_at(self.dragging, pos[0])
            return
        for i, name in enumerate(self.rows()):
            r = self.rects.get(name)
            if r and r.collidepoint(pos):
                self.sel = i
                return

    def handle_click(self, pos):
        for name in ("ui_minus", "ui_plus"):
            r = self.rects.get(name)
            if r and r.collidepoint(pos):
                return name
        for name in ("music", "sfx"):
            bar = self.rects.get(name + "_bar")
            if bar and bar.inflate(14, 24).collidepoint(pos):
                self.dragging = name
                self._slider_at(name, pos[0])
                return None
        for i, name in enumerate(self.rows()):
            r = self.rects.get(name)
            if r and r.collidepoint(pos):
                self.sel = i
                return self._activate(name)
        return None

    def handle_release(self):
        if self.dragging:
            if self.dragging == "sfx":
                self.audio.play("click")
            self.audio.save()
            self.dragging = None

    # ---- 绘制 ----
    def draw(self, surface, w, h, font, font_big):
        rows = self.rows()
        row_h, gap = 46, 9
        ph = 70 + len(rows) * (row_h + gap) + 34
        x, y = w // 2 - W // 2, max(8, h // 2 - ph // 2)
        panel = pygame.Surface((W, ph), pygame.SRCALPHA)
        panel.fill((20, 22, 28, 248))
        surface.blit(panel, (x, y))
        pygame.draw.rect(surface, (100, 160, 220), (x, y, W, ph), 2, border_radius=8)
        t = font_big.render("设置", True, (120, 180, 240))
        surface.blit(t, (x + W // 2 - t.get_width() // 2, y + 16))
        self.rects = {}
        ry = y + 58
        self.sel = min(self.sel, len(rows) - 1)
        for i, name in enumerate(rows):
            r = pygame.Rect(x + 22, ry, W - 44, row_h)
            self.rects[name] = r
            sel = (i == self.sel)
            pygame.draw.rect(surface, (60, 80, 105) if sel else (40, 42, 50), r, border_radius=6)
            pygame.draw.rect(surface, (120, 180, 240) if sel else (90, 95, 110), r, 2, border_radius=6)
            txt = lambda s, col=(235, 235, 240): font.render(s, True, col)
            if name in ("music", "sfx"):
                label = "音乐音量" if name == "music" else "音效音量"
                v = self.audio.music_vol if name == "music" else self.audio.sfx_vol
                surface.blit(txt(label), (r.x + 14, r.centery - 9))
                bar = pygame.Rect(r.x + 110, r.centery - 4, r.w - 110 - 70, 8)
                self.rects[name + "_bar"] = bar
                pygame.draw.rect(surface, (55, 58, 70), bar, border_radius=4)
                pygame.draw.rect(surface, (110, 190, 130) if not self.audio.muted else (110, 110, 110),
                                 (bar.x, bar.y, int(bar.w * v), bar.h), border_radius=4)
                kx = bar.x + int(bar.w * v)
                pygame.draw.circle(surface, (240, 240, 245), (kx, bar.centery), 9)
                pygame.draw.circle(surface, (90, 150, 210), (kx, bar.centery), 9, 2)
                surface.blit(txt(f"{int(round(v * 100))}%"), (r.right - 56, r.centery - 9))
            elif name == "mute":
                on = self.audio.muted
                s = txt("静音：已开启（点击取消）" if on else "静音：关闭（点击开启）", (255, 200, 150) if on else (235, 235, 240))
                surface.blit(s, (r.centerx - s.get_width() // 2, r.centery - 9))
            elif name == "input":
                s = txt(f"操作模式：{self.input_text}（点击切换 电脑 / 触屏）")
                surface.blit(s, (r.centerx - s.get_width() // 2, r.centery - 9))
            elif name == "ui":
                surface.blit(txt(f"界面大小  {self.ui_text}"), (r.x + 14, r.centery - 9))
                for key, sym, bx in (("ui_minus", "-", r.right - 84), ("ui_plus", "+", r.right - 42)):
                    br = pygame.Rect(bx, r.y + 7, 34, r.h - 14)
                    self.rects[key] = br
                    pygame.draw.rect(surface, (55, 60, 75), br, border_radius=4)
                    pygame.draw.rect(surface, (150, 160, 180), br, 1, border_radius=4)
                    st = txt(sym)
                    surface.blit(st, (br.centerx - st.get_width() // 2, br.centery - st.get_height() // 2))
            elif name == "fullscreen":
                s = txt("全屏 / 窗口  (F11)")
                surface.blit(s, (r.centerx - s.get_width() // 2, r.centery - 9))
            else:
                s = txt("返回")
                surface.blit(s, (r.centerx - s.get_width() // 2, r.centery - 9))
            ry += row_h + gap
        note = font.render("↑↓ 选择 · ←→ 调整 · Esc 返回", True, (130, 135, 150))
        surface.blit(note, (x + W // 2 - note.get_width() // 2, y + ph - 26))
