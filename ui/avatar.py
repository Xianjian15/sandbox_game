# ui/avatar.py
"""头像：读取图片文件 → 统一成 48×48 RGB 原始像素；原始像素 → pygame 图面；没有头像时生成默认头像。

选择图片的两种方式（菜单里都支持）：
  1. 点"选择头像…"：用系统自带的文件选择窗口（tkinter）。个别环境没有 tkinter 时会提示改用拖拽。
  2. 把图片文件直接拖进游戏窗口。
支持 pygame 能解码的常见格式（png / jpg / bmp / gif …）。非正方形图片居中裁成正方形再缩放。
"""
import os

import pygame

from core.profile import AVATAR_SIZE, AVATAR_BYTES

MAX_FILE_BYTES = 10 * 1024 * 1024        # 太大的文件不读（防止选错文件卡住）
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tga")


def load_avatar_file(path):
    """读取图片 → 原始 RGB 像素（AVATAR_BYTES 字节）。失败抛 ValueError（带给玩家看的中文原因）。"""
    path = str(path)
    if not os.path.isfile(path):
        raise ValueError("找不到这个文件")
    if os.path.getsize(path) > MAX_FILE_BYTES:
        raise ValueError("图片太大了（请选择 10MB 以内的图片）")
    if not path.lower().endswith(IMAGE_EXTS):
        raise ValueError("不是图片文件（支持 png / jpg / bmp / gif）")
    try:
        img = pygame.image.load(path)
    except (pygame.error, OSError):
        raise ValueError("无法读取这张图片，请换一张")
    w, h = img.get_size()
    if w < 1 or h < 1:
        raise ValueError("图片是空的")
    side = min(w, h)
    img = img.subsurface(((w - side) // 2, (h - side) // 2, side, side))      # 居中裁成正方形
    rgba = img.convert_alpha()
    bg = pygame.Surface((side, side))
    bg.fill((60, 64, 74))                                                     # 透明部分垫一层深灰
    bg.blit(rgba, (0, 0))
    small = pygame.transform.smoothscale(bg, (AVATAR_SIZE, AVATAR_SIZE))
    raw = pygame.image.tobytes(small, "RGB")
    if len(raw) != AVATAR_BYTES:
        raise ValueError("图片处理失败")
    return raw


def surface_from_raw(raw, size=None):
    surf = pygame.image.frombytes(bytes(raw), (AVATAR_SIZE, AVATAR_SIZE), "RGB").convert()
    if size and size != AVATAR_SIZE:
        surf = pygame.transform.smoothscale(surf, (size, size))
    return surf


def default_avatar(name, color, font, size=AVATAR_SIZE):
    """没有上传头像时：用玩家颜色做底，画名字的第一个字。"""
    surf = pygame.Surface((size, size))
    surf.fill(tuple(int(c * 0.45) for c in color))
    pygame.draw.circle(surf, color, (size // 2, size // 2), size // 2 - 3)
    ch = (name or "?")[:1]
    img = font.render(ch, True, (20, 22, 28))
    surf.blit(img, ((size - img.get_width()) // 2, (size - img.get_height()) // 2))
    return surf


def make_avatar_surface(raw, name, color, font, size=AVATAR_SIZE):
    """有头像用头像，没有就用默认头像。"""
    if raw:
        return surface_from_raw(raw, size)
    return default_avatar(name, color, font, size)


def pick_avatar_file():
    """弹出系统文件选择窗口。返回路径；玩家取消返回 None；没有 tkinter 抛 RuntimeError。"""
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
        path = filedialog.askopenfilename(
            title="选择头像图片",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tga"), ("所有文件", "*.*")])
        return path or None
    except Exception as e:                                                    # noqa: BLE001
        raise RuntimeError(f"文件选择窗口出错: {e}")
    finally:
        if root is not None:
            try:
                root.destroy()
            except Exception:                                                 # noqa: BLE001
                pass
