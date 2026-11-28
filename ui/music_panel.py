# ui/music_panel.py
"""音乐 / 歌单面板（工具栏「音乐」或 P 键）。纯显示/播放，不影响模拟与联机。

功能：自动(昼/夜/战斗) ↔ 歌单 切换；播放/暂停/上一首/下一首；循环方式；音量/静音；
      添加本地音乐（文件选择窗口 / 直接把文件拖进窗口）、添加音频直链、打开 music 文件夹、刷新。
"""
import os
import subprocess
import sys

import pygame
from core.playlist import LOOP_NAMES, AUDIO_EXTS, is_audio_name

ROWS = 7
ROW_H = 28


def pick_audio_files():
    """系统文件选择窗口（可多选）。取消返回 []；没有 tkinter 抛 RuntimeError。"""
    try:
        import tkinter
        from tkinter import filedialog
    except Exception as e:                                                    # noqa: BLE001
        raise RuntimeError(f"没有可用的文件选择窗口: {e}")
    root = None
    try:
        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        pats = " ".join("*" + e for e in AUDIO_EXTS)
        return list(filedialog.askopenfilenames(title="选择音乐文件",
                                                filetypes=[("音频", pats), ("所有文件", "*.*")]) or [])
    except Exception as e:                                                    # noqa: BLE001
        raise RuntimeError(f"文件选择窗口出错: {e}")
    finally:
        if root is not None:
            try: root.destroy()
            except Exception: pass                                            # noqa: BLE001


def read_clipboard():
    try:
        import tkinter
        r = tkinter.Tk(); r.withdraw()
        try: return r.clipboard_get()
        finally: r.destroy()
    except Exception:                                                         # noqa: BLE001
        return ""


def open_folder(path):
    try:
        os.makedirs(path, exist_ok=True)
        if sys.platform.startswith("win"): os.startfile(path)                 # noqa: S606
        elif sys.platform == "darwin": subprocess.Popen(["open", path])
        else: subprocess.Popen(["xdg-open", path])
        return True
    except Exception:                                                         # noqa: BLE001
        return False


class MusicPanel:
    def __init__(self, font):
        self.font = font
        self.panel_rect = pygame.Rect(0, 0, 0, 0)
        self.btns = []                  # [(rect, id, data)]
        self.scroll = 0
        self.editing = False            # 正在输入链接
        self.text = ""
        self.msg = ""
        self.picker = pick_audio_files  # 可注入（测试用）
        self.clipboard = read_clipboard
        self.folder_opener = open_folder

    # ---------- 绘制 ----------
    def draw(self, surface, w, h, audio):
        pl = audio.pl
        pw, ph = 680, 96 + 96 + ROWS * ROW_H + 110
        x, y = w // 2 - pw // 2, max(8, (h - 60) // 2 - ph // 2)
        self.panel_rect = pygame.Rect(x, y, pw, ph)
        self.btns = []
        n = len(pl.items)
        self.scroll = max(0, min(self.scroll, max(0, n - ROWS)))
        bg = pygame.Surface((pw, ph), pygame.SRCALPHA)
        bg.fill((20, 20, 25, 240))
        surface.blit(bg, (x, y))
        pygame.draw.rect(surface, (200, 140, 240), (x, y, pw, ph), 2)
        surface.blit(self.font.render("音乐 / 歌单 (P 关闭)", True, (210, 160, 250)), (x + 20, y + 14))

        def button(rect, label, bid, data=None, on=False, col=(200, 200, 210)):
            pygame.draw.rect(surface, (60, 80, 100) if on else (45, 45, 52), rect, border_radius=5)
            pygame.draw.rect(surface, (140, 200, 255) if on else (100, 100, 112), rect, 2 if on else 1, border_radius=5)
            t = self.font.render(label, True, col)
            surface.blit(t, (rect.centerx - t.get_width() // 2, rect.centery - t.get_height() // 2))
            self.btns.append((rect, bid, data))

        # 模式行
        ry = y + 48
        button(pygame.Rect(x + 20, ry, 200, 32), "自动（昼 / 夜 / 战斗）", "mode", "auto", on=pl.mode == "auto")
        button(pygame.Rect(x + 228, ry, 110, 32), "我的歌单", "mode", "list", on=pl.mode == "list")
        button(pygame.Rect(x + 350, ry, 110, 32), LOOP_NAMES[pl.loop], "loop")
        button(pygame.Rect(x + 476, ry, 48, 32), "上首", "prev")
        button(pygame.Rect(x + 530, ry, 60, 32), "继续" if audio.paused else ("暂停" if audio.now_playing else "播放"), "pp")
        button(pygame.Rect(x + 596, ry, 60, 32), "下首", "next")
        # 音量行
        vy = y + 90
        surface.blit(self.font.render(f"音乐音量 {int(audio.music_vol * 100)}%", True, (200, 200, 200)), (x + 20, vy + 6))
        button(pygame.Rect(x + 170, vy, 36, 30), "-", "vol", -0.1)
        button(pygame.Rect(x + 212, vy, 36, 30), "+", "vol", 0.1)
        button(pygame.Rect(x + 262, vy, 70, 30), "取消静音" if audio.muted else "静音", "mute", on=audio.muted)
        if pl.mode == "list" and audio.now_playing:
            np = f"正在播放：{audio.now_playing}" + ("（已暂停）" if audio.paused else "")
        elif pl.mode == "list":
            np = "歌单模式：点下面的歌曲开始播放" if n else "歌单是空的：先添加音乐"
        else:
            np = "自动模式：随昼夜与战斗换曲（想听自己的音乐请切到「我的歌单」）"
        surface.blit(self.font.render(np[:48], True, (150, 220, 170)), (x + 350, vy + 6))
        # 列表
        ly = y + 132
        lr = pygame.Rect(x + 20, ly, pw - 40, ROWS * ROW_H)
        pygame.draw.rect(surface, (32, 32, 38), lr)
        pygame.draw.rect(surface, (80, 80, 90), lr, 1)
        if not n:
            surface.blit(self.font.render("（空）把音乐文件拖进窗口，或点下方按钮添加", True, (140, 140, 150)),
                         (lr.x + 12, lr.y + 8))
        for k in range(ROWS):
            i = self.scroll + k
            if i >= n: break
            r = pygame.Rect(lr.x, lr.y + k * ROW_H, lr.w, ROW_H)
            cur = (pl.mode == "list" and audio.now_playing is not None and i == pl.index)
            if cur:
                pygame.draw.rect(surface, (50, 70, 60), r)
            mark = "♪ " if cur else "   "
            name = pl.items[i]["name"]
            tag = "（链接）" if pl.items[i].get("src") == "url" else ""
            surface.blit(self.font.render(f"{mark}{i + 1}. {name}{tag}"[:60], True,
                                          (230, 240, 230) if cur else (200, 200, 205)), (r.x + 8, r.y + 4))
            self.btns.append((pygame.Rect(r.x, r.y, r.w - 36, r.h), "play", i))
            xr = pygame.Rect(r.right - 30, r.y + 2, 26, r.h - 4)
            pygame.draw.rect(surface, (80, 40, 40), xr, border_radius=3)
            t = self.font.render("×", True, (240, 160, 160))
            surface.blit(t, (xr.centerx - t.get_width() // 2, xr.centery - t.get_height() // 2))
            self.btns.append((xr, "del", i))
        if n > ROWS:
            surface.blit(self.font.render(f"{self.scroll + 1}-{min(n, self.scroll + ROWS)} / {n}", True, (150, 150, 160)),
                         (lr.right - 100, lr.bottom + 4))
            button(pygame.Rect(lr.right - 190, lr.bottom + 2, 36, 22), "▲", "scroll", -ROWS)
            button(pygame.Rect(lr.right - 148, lr.bottom + 2, 36, 22), "▼", "scroll", ROWS)
        # 底部按钮
        by = lr.bottom + 30
        button(pygame.Rect(x + 20, by, 150, 32), "添加本地音乐…", "add_file")
        button(pygame.Rect(x + 178, by, 110, 32), "添加链接", "add_url", on=self.editing)
        button(pygame.Rect(x + 296, by, 70, 32), "刷新", "refresh")
        button(pygame.Rect(x + 374, by, 150, 32), "打开音乐文件夹", "folder")
        if self.editing:
            tr = pygame.Rect(x + 20, by + 40, pw - 40, 30)
            pygame.draw.rect(surface, (15, 15, 20), tr)
            pygame.draw.rect(surface, (140, 200, 255), tr, 2)
            shown = self.text[-64:]
            surface.blit(self.font.render(shown + "_", True, (240, 240, 240)), (tr.x + 8, tr.y + 5))
            surface.blit(self.font.render("粘贴音频直链(.mp3/.ogg/.wav/.flac)，Enter 确认，Esc 取消", True, (150, 150, 160)),
                         (x + 20, by + 74))
        else:
            status = pl.status or self.msg or "提示：把 mp3/ogg/wav/flac 拖进游戏窗口即可加入歌单"
            surface.blit(self.font.render(status[:70], True, (190, 190, 150)), (x + 20, by + 44))

    # ---------- 输入 ----------
    def handle_click(self, pos, audio):
        """返回 True 表示点击落在面板内（吞掉）。"""
        if not self.panel_rect.collidepoint(pos):
            return False
        for r, bid, data in self.btns:
            if r.collidepoint(pos):
                self._act(bid, data, audio)
                break
        return True

    def _act(self, bid, data, audio):
        pl = audio.pl
        if bid == "mode":
            if data == "list" and not pl.items:
                self.msg = "歌单是空的：先添加音乐"
                pl.mode = "list"; pl.save()          # 仍然进入歌单模式，空歌单时自动曲照常
                return
            audio.set_mode(data)
        elif bid == "loop": audio.cycle_loop()
        elif bid == "prev": audio.prev_track() if audio.list_mode else None
        elif bid == "next": audio.next_track() if audio.list_mode else None
        elif bid == "pp":
            if not audio.list_mode and pl.items: audio.set_mode("list")
            else: audio.play_pause()
        elif bid == "vol": audio.set_music_volume(audio.music_vol + data); audio.save()
        elif bid == "mute": audio.set_muted(not audio.muted); audio.save()
        elif bid == "play":
            if pl.mode != "list": pl.mode = "list"; pl.save()
            audio.play_index(data)
        elif bid == "del":
            was_playing = (pl.mode == "list" and audio.now_playing is not None and data == pl.index)
            pl.remove(data)
            if was_playing:
                audio.stop(); audio.now_playing = None; audio.current = None
        elif bid == "scroll": self.scroll += data
        elif bid == "refresh":
            self.msg = f"刷新完成，新增 {pl.refresh()} 首"
        elif bid == "folder":
            ok = self.folder_opener(audio.music_dir) if audio.music_dir else False
            self.msg = "已打开音乐文件夹，放入音乐后点「刷新」" if ok else "无法打开文件夹"
        elif bid == "add_file":
            try:
                paths = self.picker()
            except RuntimeError as e:
                self.msg = str(e)
                return
            self.add_paths(paths, audio)
        elif bid == "add_url":
            self.editing = not self.editing
            self.text = ""

    def add_paths(self, paths, audio):
        ok_n, last = 0, ""
        for p in paths:
            ok, info = audio.pl.add_file(p)
            ok_n += 1 if ok else 0
            last = info
        self.msg = f"已添加 {ok_n} 首" if ok_n and len(paths) > 1 else last

    def drop_file(self, path, audio):
        """窗口被拖入文件：是音频就加入歌单（任何界面下都行）。返回是否处理。"""
        if not is_audio_name(path):
            return False
        ok, info = audio.pl.add_file(path)
        self.msg = info
        audio.pl.status = info
        return True

    def handle_key(self, event, audio):
        """输入框打开时吞掉按键。返回是否处理。"""
        if not self.editing:
            return False
        k = event.key
        if k == pygame.K_ESCAPE:
            self.editing = False
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
            ok, info = audio.pl.add_url(self.text)
            self.msg = info
            if ok: self.editing = False
        elif k == pygame.K_BACKSPACE:
            self.text = self.text[:-1]
        elif k == pygame.K_v and (getattr(event, "mod", 0) & pygame.KMOD_CTRL):
            clip = (self.clipboard() or "").strip()
            if clip:
                self.text = (self.text + clip.splitlines()[0])[:400]
        return True

    def handle_text(self, text):
        if self.editing:
            self.text = (self.text + text)[:400]
            return True
        return False

    def handle_wheel(self, pos, dy):
        if self.panel_rect.collidepoint(pos):
            self.scroll -= dy
            return True
        return False
