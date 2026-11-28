# tools/texlib.py —— 贴图生成用的小工具：4 倍超采样 + 缩小，边缘平滑
import math, random
from PIL import Image, ImageDraw, ImageFilter

S = 4          # 超采样倍数
T = 32         # 一格像素


def canvas(w, h):
    return Image.new("RGBA", (int(w * S), int(h * S)), (0, 0, 0, 0))


def finish(img, w=None, h=None):
    w = w or img.width // S; h = h or img.height // S
    return img.resize((int(w), int(h)), Image.LANCZOS)


def shade(c, f):
    """f>1 提亮，f<1 变暗"""
    if f >= 1:
        return tuple(min(255, int(v + (255 - v) * (f - 1))) for v in c[:3]) + tuple(c[3:])
    return tuple(int(v * f) for v in c[:3]) + tuple(c[3:])


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class Pen:
    """坐标用"格内像素"（0..32），内部自动 ×S。"""
    def __init__(self, img, k=1.0):
        self.img = img
        self.k = k
        self.s = S * k
        self.d = ImageDraw.Draw(img, "RGBA")

    def _p(self, pts):
        return [(x * self.s, y * self.s) for x, y in pts]

    def rect(self, x1, y1, x2, y2, fill=None, outline=None, width=1, r=0):
        box = (x1 * self.s, y1 * self.s, x2 * self.s - 1, y2 * self.s - 1)
        if r: self.d.rounded_rectangle(box, r * self.s, fill=fill, outline=outline, width=int(width * self.s))
        else: self.d.rectangle(box, fill=fill, outline=outline, width=int(width * self.s))

    def ell(self, x1, y1, x2, y2, fill=None, outline=None, width=1):
        self.d.ellipse((x1 * self.s, y1 * self.s, x2 * self.s - 1, y2 * self.s - 1), fill=fill, outline=outline, width=int(width * self.s))

    def circ(self, cx, cy, r, fill=None, outline=None, width=1):
        self.ell(cx - r, cy - r, cx + r, cy + r, fill, outline, width)

    def poly(self, pts, fill=None, outline=None):
        self.d.polygon(self._p(pts), fill=fill, outline=outline)

    def line(self, pts, fill, width=1):
        self.d.line(self._p(pts), fill=fill, width=max(1, int(width * self.s)), joint="curve")

    def arc(self, box, a0, a1, fill, width=1):
        x1, y1, x2, y2 = box
        self.d.arc((x1 * self.s, y1 * self.s, x2 * self.s, y2 * self.s), a0, a1, fill=fill, width=max(1, int(width * self.s)))


def new(w, h):
    img = canvas(w, h)
    return img, Pen(img)


def speckle(pen, w, h, rng, n, cols, rmin=0.3, rmax=0.9):
    for _ in range(n):
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        r = rng.uniform(rmin, rmax)
        pen.circ(x, y, r, fill=rng.choice(cols))


def shadow(img, box, blur=1.6, alpha=90):
    """给一个椭圆/矩形区域画柔和阴影（在 img 上叠加）。box 为格内像素。"""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse([v * S for v in box], fill=(0, 0, 0, alpha))
    layer = layer.filter(ImageFilter.GaussianBlur(blur * S))
    img.alpha_composite(layer)


def glow(img, cx, cy, r, color, alpha=140):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse(((cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S), fill=color + (alpha,))
    layer = layer.filter(ImageFilter.GaussianBlur(r * S * 0.5))
    img.alpha_composite(layer)
