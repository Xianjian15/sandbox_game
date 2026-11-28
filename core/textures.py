# core/textures.py
"""贴图加载与缓存。assets/textures/*.png 由 tools/gen_textures.py 生成。

用法：textures.get("rock") → Surface 或 None（没有贴图/加载失败时返回 None，调用方回退到原来的程序化画法）。
所有贴图只在第一次用到时加载一次，之后走缓存。纯显示，不影响模拟。
"""
import math
import os

import pygame

from core.app_paths import resource_path

ENABLED = True            # 设为 False 可整体退回程序化画法
_cache = {}
_tint_cache = {}
_rot_cache = {}
_MISSING = object()


def get(name):
    if not ENABLED:
        return None
    s = _cache.get(name, _MISSING)
    if s is _MISSING:
        s = None
        try:
            path = resource_path("assets", "textures", name + ".png")
            if os.path.isfile(path):
                s = pygame.image.load(path)
                try:
                    s = s.convert() if name.split("_")[0] in _OPAQUE else s.convert_alpha()
                except Exception:           # 没有显示窗口时 convert 会失败，原图也能用
                    pass
        except Exception:
            s = None
        _cache[name] = s
    return s


def building(b):
    """建筑贴图：名字 = bld_<类型>_<材质>_<朝向>；尺寸和占地不符时放弃（回退）。"""
    rot = b.rotation % 2
    base = get(f"bld_{b.kind}_{b.material}_{rot}")
    if base is None and rot:
        base = get(f"bld_{b.kind}_{b.material}_0")
    if base is None:
        return None
    from settings import TILE_SIZE
    if base.get_size() != (b.w * TILE_SIZE, b.h * TILE_SIZE):
        return None
    return base


_variants = {}


def tile_variant(name, count, tx, ty):
    """同一种地面的几个花样，按格子坐标稳定地挑一个（不用随机数，渲染与模拟无关）。"""
    lst = _variants.get(name)
    if lst is None:
        lst = _variants[name] = [get(f"{name}_{i}") for i in range(count)]
    return lst[((tx * 73856093) ^ (ty * 19349663)) % count]


def tinted(name, color):
    """把贴图乘上颜色（用于小人衣服随个人颜色变化）。"""
    key = (name, tuple(color[:3]))
    s = _tint_cache.get(key)
    if s is None:
        base = get(name)
        if base is None:
            return None
        s = base.copy()
        # 先把任意颜色提亮一点，衣服不至于太暗
        c = tuple(min(255, int(v * 0.85 + 50)) for v in color[:3])
        s.fill(c + (255,), special_flags=pygame.BLEND_RGBA_MULT)
        _tint_cache[key] = s
    return s


def rotated(surf, key, angle_rad):
    """按朝向旋转（贴图原图朝右）。角度量化成 24 档，结果缓存。"""
    step = int(round(angle_rad / (math.tau / 24))) % 24
    k = (key, step)
    r = _rot_cache.get(k)
    if r is None:
        r = pygame.transform.rotate(surf, -math.degrees(step * math.tau / 24))
        _rot_cache[k] = r
    return r


def clear():
    _hold_cache.clear(); _variants.clear(); _icon_cache.clear(); _flip_cache.clear(); _person_cache.clear()
    _cache.clear(); _tint_cache.clear(); _rot_cache.clear()


_OPAQUE = ("grass", "dirt", "water")
_icon_cache = {}
_flip_cache = {}
_person_cache = {}


def icon(kind, size=26):
    """物品图标（缩放到 size 像素，缓存）。"""
    k = (kind, size)
    s = _icon_cache.get(k, _MISSING)
    if s is _MISSING:
        base = get("item_" + kind)
        s = None
        if base is not None:
            s = base if base.get_width() == size else pygame.transform.smoothscale(base, (size, size))
        _icon_cache[k] = s
    return s


def animal(species, right, flash):
    """动物贴图（原图朝右；朝左时水平翻转；受击时泛红）。"""
    k = (species, bool(right), bool(flash))
    s = _flip_cache.get(k, _MISSING)
    if s is _MISSING:
        base = get("animal_" + species)
        s = None
        if base is not None:
            s = base if right else pygame.transform.flip(base, True, False)
            if flash:
                s = s.copy()
                s.fill((255, 150, 150, 255), special_flags=pygame.BLEND_RGBA_MULT)
        _flip_cache[k] = s
    return s


def person(body_name, head_name, color, flash, angle):
    """小人/敌人：身体（可按个人颜色染色）+ 头手，按朝向旋转。"""
    step = int(round(angle / (math.tau / 24))) % 24
    k = (body_name, head_name, tuple(color[:3]) if color else None, bool(flash), step)
    s = _person_cache.get(k, _MISSING)
    if s is _MISSING:
        body = get(body_name); head = get(head_name)
        s = None
        if body is not None and head is not None:
            base = tinted(body_name, color) if color is not None else body
            comp = base.copy()
            if flash:
                comp.fill((255, 190, 150, 255), special_flags=pygame.BLEND_RGBA_MULT)
            comp.blit(head, (0, 0))
            s = pygame.transform.rotate(comp, -math.degrees(step * math.tau / 24))
        _person_cache[k] = s
    return s


# 手持武器贴图的“自然朝向”（图里武器指向哪个角度，屏幕坐标 y 向下）：斜放的工具指向右上 = -45°，枪/弓指向右 = 0°，弩指向上 = -90°
_HOLD_BASE = {"crossbow": -math.pi / 2, "bow": 0.0, "pistol": 0.0, "rifle": 0.0, "shotgun": 0.0, "smg": 0.0,
              "sniper": 0.0, "gun": 0.0}
_hold_cache = {}


def weapon(key, angle):
    """手持武器：按朝向旋转后的贴图（None = 没有贴图，调用方回退）。"""
    step = int(round(angle / (math.tau / 24))) % 24
    k = (key, step)
    s = _hold_cache.get(k, _MISSING)
    if s is _MISSING:
        base = get("hold_" + key)
        s = None
        if base is not None:
            nat = _HOLD_BASE.get(key, -math.pi / 4)
            rot = step * math.tau / 24 - nat                       # 需要顺时针转过的角度
            s = pygame.transform.rotate(base, -math.degrees(rot))
        _hold_cache[k] = s
    return s
