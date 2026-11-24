# tools/make_icon.py
"""生成游戏图标（assets/icon.png / icon.ico / icon.icns）。开发者工具，玩家不需要运行。
图案用游戏自己的画风：草地格子 + 一块石头 + 红色小人。想换成自己设计的图标：
直接用你的 icon.png(512x512) / icon.ico / icon.icns 覆盖 assets/ 里的同名文件即可。
需要： pip install pillow
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets")


def draw(size=512):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = size // 8
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=r * 2, fill=(30, 33, 42, 255))
    pad = size // 14
    grid = 4
    cell = (size - 2 * pad) // grid
    grass = [(78, 122, 62), (70, 112, 56)]
    for gy in range(grid):
        for gx in range(grid):
            x0, y0 = pad + gx * cell, pad + gy * cell
            d.rectangle((x0, y0, x0 + cell - 1, y0 + cell - 1), fill=grass[(gx + gy) % 2] + (255,))
    # 河（一条蓝色的横带）
    d.rectangle((pad, pad + 3 * cell, size - pad - 1, pad + 3 * cell + cell // 2), fill=(52, 90, 140, 255))
    # 石头
    sx, sy = pad + int(0.6 * cell), pad + int(0.5 * cell)
    d.rounded_rectangle((sx, sy, sx + int(1.1 * cell), sy + int(1.0 * cell)), radius=cell // 6,
                        fill=(120, 95, 65, 255))
    d.rounded_rectangle((sx + cell // 10, sy + cell // 10, sx + int(1.0 * cell), sy + int(0.9 * cell)),
                        radius=cell // 6, fill=(110, 110, 115, 255))
    # 树
    tx, ty = pad + int(2.7 * cell), pad + int(0.7 * cell)
    d.ellipse((tx, ty, tx + int(1.1 * cell), ty + int(1.1 * cell)), fill=(48, 88, 40, 255),
              outline=(30, 60, 28, 255), width=max(2, size // 128))
    # 小人（红色圆 + 黑边）
    cx, cy, cr = pad + int(1.9 * cell), pad + int(2.0 * cell), int(0.55 * cell)
    d.ellipse((cx - cr, cy - cr, cx + cr, cy + cr), fill=(200, 60, 60, 255), outline=(0, 0, 0, 255),
              width=max(3, size // 96))
    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    img = draw(512)
    img.save(os.path.join(OUT, "icon.png"))
    img.save(os.path.join(OUT, "icon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    try:
        img.save(os.path.join(OUT, "icon.icns"))
    except Exception as e:                                                  # noqa: BLE001
        print("生成 icon.icns 失败（只影响 macOS 打包的图标）:", e)
    for n in ("icon.png", "icon.ico", "icon.icns"):
        p = os.path.join(OUT, n)
        print(n, f"{os.path.getsize(p) / 1024:.0f} KB" if os.path.exists(p) else "缺失")
    return 0


if __name__ == "__main__":
    sys.exit(main())
