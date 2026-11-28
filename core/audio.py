# core/audio.py
"""音效与音乐（纯显示/播放，不参与模拟，不影响联机同步）。

AudioManager：本机音频。mixer 初始化失败（没有声卡/服务器环境）时自动静默，游戏照常运行。
NullAudio：什么都不做（测试 / 没接音频时用），接口与 AudioManager 相同。
音量（音乐 / 音效 / 静音）存在 audio.json，下次启动沿用。
"""
import json
import math
import os
import time

from core.app_paths import resource_path

SFX_NAMES = ("click", "shot_pistol", "shot_rifle", "shot_shotgun", "shot_smg", "shot_sniper", "shot_bow", "melee",
             "enemy_down", "colonist_down", "build_done", "harvest_done", "quest_new", "quest_done", "alarm", "meteor")
TRACKS = ("day", "night", "battle")
_SHOT = {"bow": "shot_bow", "crossbow": "shot_bow", "pistol": "shot_pistol", "rifle": "shot_rifle", "gun": "shot_rifle",
         "shotgun": "shot_shotgun", "smg": "shot_smg", "sniper": "shot_sniper"}
DEFAULTS = {"music": 0.5, "sfx": 0.8, "mute": False}
MIN_GAP = 0.06                     # 同一个音效最短间隔（秒）：高倍速时不会糊成一团


def weapon_sound(weapon_key, kind):
    """kind = recent_shot 的类型："shot" 远程 / "melee" 近战。"""
    if kind == "melee":
        return "melee"
    return _SHOT.get(weapon_key, "shot_pistol")


def clamp01(v):
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.5


class NullAudio:
    ok = False
    music_vol, sfx_vol, muted = DEFAULTS["music"], DEFAULTS["sfx"], False
    current = None

    def play(self, name, vol=1.0): pass
    def set_music(self, track): pass
    def update(self): pass
    def set_music_volume(self, v): self.music_vol = clamp01(v)
    def set_sfx_volume(self, v): self.sfx_vol = clamp01(v)
    def set_muted(self, m): self.muted = bool(m)
    def save(self): pass
    def stop(self): pass


class AudioManager(NullAudio):
    def __init__(self, path=None, mixer=None):
        self.path = path
        self.music_vol, self.sfx_vol, self.muted = DEFAULTS["music"], DEFAULTS["sfx"], DEFAULTS["mute"]
        self._load()
        self.mixer = mixer
        self.ok = False
        self._sounds = {}
        self._last = {}
        self.current = None            # 正在播（或即将播）的音乐曲目
        self._pending = None
        self._switch_at = 0.0
        self.played = []               # 最近播放的音效名（测试用）
        try:
            if self.mixer is None:
                import pygame
                pygame.mixer.init()
                self.mixer = pygame.mixer
            self.ok = True
        except Exception:               # noqa: BLE001  没有声卡等：静默
            self.ok = False

    # ---- 设置存取 ----
    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.music_vol = clamp01(d.get("music", DEFAULTS["music"]))
            self.sfx_vol = clamp01(d.get("sfx", DEFAULTS["sfx"]))
            self.muted = bool(d.get("mute", False))
        except Exception:               # noqa: BLE001
            pass

    def save(self):
        if not self.path:
            return
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"music": round(self.music_vol, 3), "sfx": round(self.sfx_vol, 3), "mute": self.muted}, f)
        except OSError:
            pass

    # ---- 音量 ----
    def _apply_music_volume(self):
        if self.ok:
            try:
                self.mixer.music.set_volume(0.0 if self.muted else self.music_vol)
            except Exception:           # noqa: BLE001
                pass

    def set_music_volume(self, v):
        self.music_vol = clamp01(v); self._apply_music_volume()

    def set_sfx_volume(self, v):
        self.sfx_vol = clamp01(v)

    def set_muted(self, m):
        self.muted = bool(m); self._apply_music_volume()

    # ---- 音效 ----
    def _sound(self, name):
        s = self._sounds.get(name)
        if s is None and name not in self._sounds:
            try:
                s = self.mixer.Sound(resource_path("assets", "audio", name + ".wav"))
            except Exception:           # noqa: BLE001
                s = None
            self._sounds[name] = s
        return s

    def play(self, name, vol=1.0):
        if self.muted or self.sfx_vol <= 0 or vol <= 0.02:
            return
        now = time.monotonic()
        if now - self._last.get(name, -9) < MIN_GAP:
            return
        self._last[name] = now
        self.played.append(name); del self.played[:-50]
        if not self.ok:
            return
        s = self._sound(name)
        if s is not None:
            try:
                s.set_volume(clamp01(vol * self.sfx_vol))
                s.play()
            except Exception:           # noqa: BLE001
                pass

    # ---- 音乐 ----
    def set_music(self, track):
        if track == self.current:
            return
        had = self.current is not None
        self.current = track
        self._pending = track
        self._switch_at = time.monotonic() + (0.7 if had and self.ok else 0.0)
        if had and self.ok:
            try:
                self.mixer.music.fadeout(600)
            except Exception:           # noqa: BLE001
                pass

    def update(self):
        """每帧调用：到点就切到待播的曲目。"""
        if self._pending is None or time.monotonic() < self._switch_at:
            return
        track, self._pending = self._pending, None
        if not self.ok or track is None:
            return
        for ext in (".ogg", ".wav"):
            path = resource_path("assets", "audio", f"music_{track}{ext}")
            if os.path.isfile(path):
                try:
                    self.mixer.music.load(path)
                    self.mixer.music.set_volume(0.0 if self.muted else self.music_vol)
                    self.mixer.music.play(loops=-1, fade_ms=1200)
                except Exception:       # noqa: BLE001
                    pass
                return

    def stop(self):
        self.current = None; self._pending = None
        if self.ok:
            try:
                self.mixer.music.fadeout(400)
            except Exception:           # noqa: BLE001
                pass


def distance_volume(dist_tiles):
    """离镜头中心越远声音越小（40 格以外听不见）。"""
    return max(0.0, 1.0 - dist_tiles / 40.0) ** 1.5 if dist_tiles is not None else 1.0
