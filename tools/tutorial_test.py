# tools/tutorial_test.py
"""新手教程验收：
  T1 内容    每页有标题和内容；行格式合法；每页高度放得进面板（不溢出）；提到的快捷键都是游戏里真有的
  T2 导航    下一页/上一页/圆点跳页/最后一页点“开始游戏”关闭；键盘 ← → Enter Esc F1
  T3 游戏内  F1 打开；打开时空格/B 等按键被吞掉（不改变速度/模式）；点击不穿透到地图；关闭后恢复正常
  T4 首次    看过标记文件：没有→弹出，on_close 后写入→下次不弹
  T5 绘制    多种窗口大小下绘制不抛异常
  T6 菜单    主菜单有“新手教程”，点击返回 {"mode":"single","tutorial":True}
用法： python -m tools.tutorial_test
"""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
try:
    import pygame
    pygame.init(); pygame.display.set_mode((64, 64))
except ImportError:
    from tools import fake_pygame
    pygame = fake_pygame.install()
from ui import tutorial as T
from world.game_world import GameWorld
FAILS = []
def check(n, ok, info=""):
    print(("  ✓ " if ok else "  ✗ ") + n + (f"  {info}" if info and not ok else ""))
    if not ok: FAILS.append(n)

# T1
H = {"h": 28, "t": 25, "k": 26, "s": 10}
bad = []
for i, (title, rows) in enumerate(T.PAGES):
    if not title or not rows: bad.append((i, "空"))
    for r in rows:
        if r[0] not in H or (r[0] == "k" and len(r) != 3) or (r[0] in ("h", "t") and len(r) != 2): bad.append((i, r))
    if 64 + sum(H[r[0]] for r in rows) > T.Tutorial.H - 62: bad.append((i, "超高", 64 + sum(H[r[0]] for r in rows)))
check("T1a 页面结构合法且不溢出", not bad, bad)
check("T1b 页数合理", 6 <= len(T.PAGES) <= 14, len(T.PAGES))
alltext = "".join("".join(r[1:]) for _, rows in T.PAGES for r in rows)
src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "world", "game_world.py"), encoding="utf-8").read()
for k, const in (("B", "K_b"), ("F", "K_f"), ("S", "K_s"), ("X", "K_x"), ("R", "K_r"), ("T", "K_t"), ("H", "K_h"), ("空格", "K_SPACE")):
    check(f"T1c 教程提到的快捷键 {k} 游戏里真实存在", const in src and k in alltext)
check("T1d F1/F10/F11 存在", "K_F1" in src and "K_F10" in open("main.py", encoding="utf-8").read() and "K_F11" in open("main.py", encoding="utf-8").read())

# T2
closed = []
t = T.Tutorial(on_close=lambda: closed.append(1))
t.open(); check("T2a 打开在第 1 页", t.active and t.page == 0)
t.prev(); check("T2b 第一页上一页不动", t.page == 0)
t.next(); t.next(); check("T2c 下一页", t.page == 2)
t.handle_key(pygame.K_LEFT); check("T2d ← 上一页", t.page == 1)
t.handle_key(pygame.K_RIGHT); t.handle_key(pygame.K_RETURN); check("T2e → / Enter 下一页", t.page == 3)
t.page = len(T.PAGES) - 1; t.next()
check("T2f 最后一页再下一页=关闭并回调", not t.active and closed == [1])
t.open(); t.handle_key(pygame.K_ESCAPE); check("T2g Esc 关闭", not t.active and len(closed) == 2)
t.open(); t.handle_key(pygame.K_F1); check("T2h F1 关闭", not t.active)

# T3
f = pygame.font.Font(None, 16)
g = GameWorld(f, f, f, f, 1280, 720, seed=5); g.set_screen_size(1280, 720)
def key(k): g.handle_event(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode=""), 1280, 720)
def click(p): g.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=p, button=1), 1280, 720)
check("T3a 初始不显示", not g.tutorial.active)
key(pygame.K_F1); check("T3b F1 打开", g.tutorial.active)
sp, md = g.game_speed, g.mode
key(pygame.K_SPACE); key(pygame.K_b)
check("T3c 教程打开时空格/B 被吞掉", g.game_speed == sp and g.mode == md)
surf = pygame.Surface((g.ui_w, g.ui_h)); g._draw_ui(surf, g.ui_w, g.ui_h)
nr = g.tutorial.rects["next"]
click((int((nr.centerx) * g.ui_scale), int(nr.centery * g.ui_scale)))
check("T3d 点“下一页”翻页", g.tutorial.page == 1, g.tutorial.page)
key(pygame.K_ESCAPE); check("T3e Esc 关闭", not g.tutorial.active)
key(pygame.K_b); check("T3f 关闭后 B 恢复正常", g.mode == "build", g.mode)

# T4
d = tempfile.mkdtemp(); df = lambda n: os.path.join(d, n)
check("T4a 首次：没看过", not T.has_seen(df))
t2 = T.Tutorial(on_close=lambda: T.mark_seen(df)); t2.open(); t2.close()
check("T4b 关闭后记录，之后不再自动弹", T.has_seen(df))

# T5
for (w, h) in ((1280, 720), (800, 600), (1920, 1080), (1024, 500)):
    g2 = GameWorld(f, f, f, f, w, h, seed=1); g2.set_screen_size(w, h)
    ok = True
    for p in range(len(T.PAGES)):
        g2.tutorial.open(p)
        try:
            s2 = pygame.Surface((g2.ui_w, g2.ui_h)); g2._draw_ui(s2, g2.ui_w, g2.ui_h)
        except Exception as e:                                          # noqa: BLE001
            ok = False; print("   ", w, h, p, repr(e))
    check(f"T5 {w}x{h} 全部页面可绘制", ok)

# T6
import tools.menu_test as MT
from ui.menu import MenuModel
m = MenuModel(MT.cfg(MT.free_udp_port()), clock=MT.Clock())
check("T6a 主菜单有新手教程按钮", MT.widget(m, "tutorial") is not None)
MT.click(m, "tutorial")
check("T6b 点击后开单人并打开教程", m.result == {"mode": "single", "tutorial": True}, m.result)
m.close()
print("FAILS:", FAILS); sys.exit(1 if FAILS else 0)
