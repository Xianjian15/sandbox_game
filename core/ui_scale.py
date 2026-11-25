# core/ui_scale.py
"""界面自动缩放。

思路：界面代码（工具栏、面板、菜单…）里的像素值都是按 1280×720 设计的。窗口变大/变小时，
不去改每个控件的坐标，而是让界面画在一块"逻辑尺寸"的画布上（窗口尺寸 ÷ 缩放比例），
再整体平滑缩放到窗口大小；鼠标坐标反过来除以缩放比例交给界面。地图本身仍按真实分辨率绘制——
窗口越大看到的地图越多，只有界面跟着放大。

  缩放比例 = min(窗口宽/1280, 窗口高/720) × 玩家偏好，限制在 [MIN_SCALE, MAX_SCALE]，按 1/20 取整
  （取整是为了拖动窗口边缘时逻辑尺寸不会每个像素都在变，也让 1280×720 / 1920×1080 恰好是 1.0 / 1.5）。

玩家偏好：Ctrl + "+" / Ctrl + "-" 调整界面大小，Ctrl + 0 恢复，保存在用户数据目录的 ui.json。
缩放比例恰好为 1.0 时直接画在屏幕上，零额外开销。
"""
import json
import math
import os

BASE_W, BASE_H = 1280, 720
MIN_SCALE, MAX_SCALE = 0.6, 3.0
PREF_STEPS = (0.75, 0.875, 1.0, 1.125, 1.25, 1.5, 1.75, 2.0)
DEFAULT_PREF = 1.0


def compute_scale(w, h, pref=DEFAULT_PREF):
    base = min(max(1, w) / BASE_W, max(1, h) / BASE_H)
    s = max(MIN_SCALE, min(MAX_SCALE, base * pref))
    return round(s * 20) / 20.0


def logical_size(w, h, scale):
    return max(1, int(math.ceil(w / scale))), max(1, int(math.ceil(h / scale)))


def to_logical(pos, scale):
    """窗口坐标 → 界面逻辑坐标（鼠标点击/移动用）。"""
    return int(pos[0] / scale), int(pos[1] / scale)


def step_pref(pref, direction):
    """direction=+1 放大一档，-1 缩小一档，0 恢复默认。返回新的偏好值。"""
    if direction == 0:
        return DEFAULT_PREF
    cur = min(range(len(PREF_STEPS)), key=lambda i: abs(PREF_STEPS[i] - pref))
    cur = max(0, min(len(PREF_STEPS) - 1, cur + (1 if direction > 0 else -1)))
    return PREF_STEPS[cur]


def pref_delta_for_key(key, mods):
    """Ctrl + "+" / "-" / "0" → +1 / -1 / 0；不是这组快捷键返回 None。"""
    import pygame
    if not (mods & pygame.KMOD_CTRL):
        return None
    if key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
        return 1
    if key in (pygame.K_MINUS, pygame.K_KP_MINUS):
        return -1
    if key in (pygame.K_0, pygame.K_KP_0):
        return 0
    return None


def load_pref(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            v = float(json.load(f).get("ui_pref", DEFAULT_PREF))
        return v if PREF_STEPS[0] <= v <= PREF_STEPS[-1] else DEFAULT_PREF
    except (OSError, ValueError, TypeError, AttributeError):
        return DEFAULT_PREF


def save_pref(path, pref):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"ui_pref": pref}, f)
        return True
    except OSError:
        return False


def pref_text(pref):
    return f"界面大小 {int(round(pref * 100))}%"


class UiLayer:
    """一块可缩放的界面画布。用法：

        ui = layer.begin(screen, scale)        # 拿到可以画的 surface（缩放为 1.0 时就是 screen 本身）
        ...把界面画在 ui 上，尺寸 = layer.size...
        layer.end(screen)                      # 缩放并叠加到 screen 上

    alpha=True：透明画布，叠在已经画好的地图上（游戏内）；alpha=False：不透明画布，整屏替换（菜单/对话框）。
    画布和缩放目标都缓存起来，窗口尺寸不变时每帧不分配内存。
    """
    def __init__(self, alpha=True):
        self.alpha = alpha
        self.surf = None
        self.dest = None
        self.scale = 1.0
        self.size = (0, 0)
        self._direct = True

    def begin(self, screen, scale):
        import pygame
        sw, sh = screen.get_size()
        self.scale = scale
        self.size = logical_size(sw, sh, scale)
        self._direct = abs(scale - 1.0) < 1e-9
        if self._direct:
            return screen
        if self.surf is None or self.surf.get_size() != self.size:
            self.surf = pygame.Surface(self.size, pygame.SRCALPHA) if self.alpha else pygame.Surface(self.size)
            self.surf = self.surf.convert_alpha() if self.alpha else self.surf.convert()
            self.dest = None
        if self.alpha:
            self.surf.fill((0, 0, 0, 0))
        return self.surf

    def end(self, screen):
        if self._direct or self.surf is None:
            return
        import pygame
        size = screen.get_size()
        try:
            if self.dest is None or self.dest.get_size() != size:
                self.dest = pygame.Surface(size, pygame.SRCALPHA) if self.alpha else pygame.Surface(size)
                self.dest = self.dest.convert_alpha() if self.alpha else self.dest.convert()
            pygame.transform.smoothscale(self.surf, size, self.dest)
            screen.blit(self.dest, (0, 0))
        except (ValueError, TypeError, pygame.error):
            # 某些显示格式下 smoothscale 不接受目标面：退回普通缩放（边缘略粗糙，但一定能显示）
            screen.blit(pygame.transform.scale(self.surf, size), (0, 0))
