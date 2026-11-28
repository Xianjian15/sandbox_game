# tools/fake_pygame.py
"""无头"假 pygame"：只在没有安装真 pygame 的环境（比如云端沙盒）里，让游戏本体能被实例化并测试逻辑。
不画任何像素，但会记录 Surface 的 blit / fill / smoothscale 调用，供测试检查"界面是不是画在了该画的画布上"。
真实的 pygame 存在时，测试脚本直接用真的（SDL dummy 驱动），不会用到这个文件。
"""
import sys
import types


class Rect:
    def __init__(self, *a):
        if len(a) == 1:
            a = tuple(a[0])
        if len(a) == 2:
            a = (a[0][0], a[0][1], a[1][0], a[1][1]) if isinstance(a[0], (tuple, list)) else (a[0], a[1], 0, 0)
        self.x, self.y, self.w, self.h = a

    width = property(lambda s: s.w, lambda s, v: setattr(s, "w", v))
    height = property(lambda s: s.h, lambda s, v: setattr(s, "h", v))
    left = property(lambda s: s.x, lambda s, v: setattr(s, "x", v))
    top = property(lambda s: s.y, lambda s, v: setattr(s, "y", v))
    right = property(lambda s: s.x + s.w, lambda s, v: setattr(s, "x", v - s.w))
    bottom = property(lambda s: s.y + s.h, lambda s, v: setattr(s, "y", v - s.h))
    centerx = property(lambda s: s.x + s.w // 2, lambda s, v: setattr(s, "x", v - s.w // 2))
    centery = property(lambda s: s.y + s.h // 2, lambda s, v: setattr(s, "y", v - s.h // 2))

    @property
    def center(self):
        return (self.centerx, self.centery)

    @center.setter
    def center(self, v):
        self.centerx, self.centery = v

    @property
    def topleft(self):
        return (self.x, self.y)

    @property
    def size(self):
        return (self.w, self.h)

    def collidepoint(self, *p):
        if len(p) == 1:
            p = p[0]
        return self.x <= p[0] < self.x + self.w and self.y <= p[1] < self.y + self.h

    def colliderect(self, o):
        return self.x < o.x + o.w and o.x < self.x + self.w and self.y < o.y + o.h and o.y < self.y + self.h

    def copy(self):
        return Rect(self.x, self.y, self.w, self.h)

    def move(self, dx, dy):
        return Rect(self.x + dx, self.y + dy, self.w, self.h)

    def inflate(self, dx, dy):
        return Rect(self.x - dx // 2, self.y - dy // 2, self.w + dx, self.h + dy)

    def __iter__(self):
        return iter((self.x, self.y, self.w, self.h))

    def __repr__(self):
        return f"Rect({self.x},{self.y},{self.w},{self.h})"


class Surface:
    LOG = []                                    # 全局记录：("smoothscale", src_size, dst_size) 等

    def __init__(self, size=(0, 0), flags=0, *a):
        self.size = (int(size[0]), int(size[1]))
        self.flags = flags
        self.blits = []
        self.fills = []

    def get_size(self): return self.size
    def get_width(self): return self.size[0]
    def get_height(self): return self.size[1]
    def get_rect(self, **kw):
        r = Rect(0, 0, *self.size)
        for k, v in kw.items(): setattr(r, k, v)
        return r
    def fill(self, c, *a, **k): self.fills.append(c)
    def blit(self, src, pos, *a): self.blits.append((src, pos))
    def set_alpha(self, v): pass
    def set_clip(self, r=None): self._clip = r
    def get_clip(self): return getattr(self, '_clip', None)
    def set_colorkey(self, *a): pass
    def copy(self): return Surface(self.size, self.flags)
    def convert(self): return self
    def convert_alpha(self): return self
    def subsurface(self, r): return Surface((r[2], r[3]))
    def get_bitsize(self): return 32


class Font:
    def __init__(self, path=None, size=16):
        self.sz = size or 16

    def render(self, text, aa, color, *a):
        return Surface((max(1, len(str(text))) * self.sz // 2, self.sz))

    def size(self, text): return (max(1, len(str(text))) * self.sz // 2, self.sz)
    def get_height(self): return self.sz
    def get_linesize(self): return self.sz + 2


class Event:
    def __init__(self, type, **kw):
        self.type = type
        self.__dict__.update(kw)


class _Noop(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: None


def install(textures=False):
    pg = types.ModuleType("pygame")
    pg.Rect, pg.Surface, pg.Color = Rect, Surface, lambda *a: a
    pg.error = type("error", (Exception,), {})
    pg.SRCALPHA, pg.RESIZABLE, pg.FULLSCREEN = 0x10000, 0x10, 0x80000000
    names = ["QUIT", "KEYDOWN", "KEYUP", "MOUSEBUTTONDOWN", "MOUSEBUTTONUP", "MOUSEMOTION", "VIDEORESIZE",
             "TEXTINPUT", "DROPFILE", "TEXTEDITING", "FINGERDOWN", "FINGERUP", "FINGERMOTION"]
    for i, n in enumerate(names):
        setattr(pg, n, 100 + i)
    keys = "ESCAPE RETURN KP_ENTER BACKSPACE UP DOWN SPACE EQUALS PLUS MINUS KP_PLUS KP_MINUS KP_0 TAB F10 F11 LEFT RIGHT DELETE".split()
    for i, n in enumerate(keys): setattr(pg, "K_" + n, 1000 + i)
    for i, ch in enumerate("abcdefghijklmnopqrstuvwxyz0123456789"): setattr(pg, "K_" + ch, 2000 + i)
    for i in range(1, 13): setattr(pg, f"K_F{i}", 3000 + i)
    pg.KMOD_SHIFT, pg.KMOD_CTRL = 1, 64
    pg.init = pg.quit = lambda *a: None
    pg.event = types.SimpleNamespace(Event=Event, get=lambda: [], post=lambda e: None)
    pg.mouse = types.SimpleNamespace(_pos=(0, 0), get_pos=lambda: pg.mouse._pos)
    pg.key = types.SimpleNamespace(_mods=0, get_mods=lambda: pg.key._mods, start_text_input=lambda: None, set_text_input_rect=lambda r: None,
                                   stop_text_input=lambda: None)
    pg.time = types.SimpleNamespace(get_ticks=lambda: 0, wait=lambda ms: None,
                                    Clock=lambda: types.SimpleNamespace(tick=lambda fps=0: 16))
    pg.display = types.SimpleNamespace(set_mode=lambda size, *a: Surface(size), flip=lambda: None,
                                       set_caption=lambda *a: None, set_icon=lambda *a: None)
    pg.draw = _Noop("pygame.draw")
    pg.font = types.SimpleNamespace(Font=Font, match_font=lambda *a, **k: None, init=lambda: None)
    def _load(p):
        if not textures:
            raise pg.error("no image")
        from PIL import Image                      # 只读尺寸：让“贴图路径”也能在无窗口环境下跑一遍
        s_ = Surface(Image.open(p).size); s_.path = p
        return s_
    pg.BLEND_RGBA_MULT = 8
    pg.image = types.SimpleNamespace(load=_load,
                                     tobytes=lambda s, f: b"", frombytes=lambda b, size, f: Surface(size))

    def smoothscale(src, size, dest=None):
        Surface.LOG.append(("smoothscale", src.get_size(), tuple(size)))
        if dest is not None:
            return dest
        return Surface(size)

    def scale(src, size, dest=None):
        Surface.LOG.append(("scale", src.get_size(), tuple(size)))
        return dest if dest is not None else Surface(size)
    pg.transform = types.SimpleNamespace(
        smoothscale=smoothscale, scale=scale,
        rotate=lambda src, ang: Surface((src.get_width() + 2, src.get_height() + 2)),
        flip=lambda src, fx, fy: Surface(src.get_size()))
    sys.modules["pygame"] = pg
    return pg
