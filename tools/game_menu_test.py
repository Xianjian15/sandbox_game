# tools/game_menu_test.py
"""游戏中菜单（M）验收：
  G1 打开/关闭   M 打开；M / Esc 关闭；打开时 H 面板被收起
  G2 不动地图   菜单打开时鼠标贴边：相机不滚动；关闭后恢复滚动；教程打开时同样不滚
  G3 吞输入     打开时空格/B 不起作用、点地图不选/不取消小人、拖拽状态被清掉
  G4 菜单动作   继续/教程/速查 在游戏内处理；全屏/返回主菜单/退出/界面大小 通过 app_request 交给 main
  G5 键盘鼠标   ↑↓ Enter；鼠标悬停高亮、点击；界面大小行的 ＋ － 按钮
  G6 绘制       多种窗口大小可绘制，所有按钮都在画面内
  G7 不影响模拟 打开/操作菜单不改变模拟状态哈希（菜单本身不暂停游戏）
用法： python -m tools.game_menu_test
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
try:
    import pygame
    pygame.init(); pygame.display.set_mode((64, 64))
except ImportError:
    from tools import fake_pygame
    pygame = fake_pygame.install()
from world.game_world import GameWorld
from ui.game_menu import ITEMS
from core.state_hash import world_hash
FAILS = []
def check(n, ok, info=""):
    print(("  ✓ " if ok else "  ✗ ") + n + (f"  {info}" if info and not ok else ""))
    if not ok: FAILS.append(n)

f = pygame.font.Font(None, 16)
W, H = 1280, 720
def mk():
    g = GameWorld(f, f, f, f, W, H, seed=9); g.set_screen_size(W, H); return g
def key(g, k): g.handle_event(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode=""), W, H)
def click(g, p): g.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=p, button=1), W, H)
def move(g, p): g.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=p, rel=(0, 0), buttons=(0, 0, 0)), W, H)
def draw(g):
    s = pygame.Surface((g.ui_w, g.ui_h)); g._draw_ui(s, g.ui_w, g.ui_h)
def center(g, name):
    r = g.menu.rects[name]; return (int(r.centerx * g.ui_scale), int(r.centery * g.ui_scale))

# G1
g = mk()
key(g, pygame.K_h); check("G1a H 打开速查", g.show_help)
key(g, pygame.K_m); check("G1b M 打开菜单并收起速查", g.menu.active and not g.show_help)
key(g, pygame.K_m); check("G1c M 关闭", not g.menu.active)
key(g, pygame.K_m); key(g, pygame.K_ESCAPE); check("G1d Esc 关闭", not g.menu.active)

# G2
g = mk(); g.camera.x, g.camera.y = 800.0, 800.0
x0 = (g.camera.x, g.camera.y)
for _ in range(30): g.edge_scroll((2, 300), W, H, 0.05)
check("G2a 无菜单：贴边会滚动", (g.camera.x, g.camera.y) != x0)
g.camera.x, g.camera.y = 800.0, 800.0; x0 = (g.camera.x, g.camera.y)
key(g, pygame.K_m)
for p in ((2, 300), (1279, 300), (600, 2), (600, 719)):
    for _ in range(30): g.edge_scroll(p, W, H, 0.05); move(g, p)
check("G2b 菜单打开：鼠标贴任意边相机不动", (g.camera.x, g.camera.y) == x0, (g.camera.x, g.camera.y))
key(g, pygame.K_m)
for _ in range(30): g.edge_scroll((2, 300), W, H, 0.05)
check("G2c 关闭后恢复滚动", (g.camera.x, g.camera.y) != x0)
g.camera.x, g.camera.y = 800.0, 800.0; x0 = (g.camera.x, g.camera.y)
g.tutorial.open()
for _ in range(30): g.edge_scroll((2, 300), W, H, 0.05)
check("G2d 教程打开时同样不滚", (g.camera.x, g.camera.y) == x0)

# G3
g = mk(); c = g.colonists[0]; c.selected = True
g.dragging_cam_right = True; g.drag_start = (1, 1)
key(g, pygame.K_m)
check("G3a 打开时清掉拖拽状态", not g.dragging_cam_right and g.drag_start is None)
sp, md = g.game_speed, g.mode
key(g, pygame.K_SPACE); key(g, pygame.K_b); key(g, pygame.K_s)
check("G3b 空格/B/S 被吞掉", g.game_speed == sp and g.mode == md)
draw(g)
click(g, (50, 360))   # 菜单面板外的地图位置
check("G3c 点面板外不取消小人选择、不穿透地图", c.selected and g.menu.active)

# G4
def act(name):
    g = mk(); key(g, pygame.K_m); draw(g); click(g, center(g, name)); return g
g = act("resume"); check("G4a 继续", not g.menu.active and g.app_request is None)
g = act("tutorial"); check("G4b 教程", not g.menu.active and g.tutorial.active)
g = act("help"); check("G4c 速查", not g.menu.active and g.show_help)
for n in ("fullscreen", "menu", "quit"):
    g = act(n); check(f"G4d {n} → app_request", g.app_request == n and not g.menu.active, g.app_request)
g = act("ui_plus"); check("G4e 界面＋：请求 main 处理且菜单保持打开", g.app_request == "ui_plus" and g.menu.active)
g = act("ui_minus"); check("G4f 界面－", g.app_request == "ui_minus" and g.menu.active)

# G5
g = mk(); key(g, pygame.K_m); draw(g)
key(g, pygame.K_DOWN); key(g, pygame.K_DOWN); check("G5a ↓ 移动选择", g.menu.sel == 2)
key(g, pygame.K_UP); check("G5b ↑", g.menu.sel == 1)
key(g, pygame.K_RETURN); check("G5c Enter 执行（教程）", g.tutorial.active and not g.menu.active)
g = mk(); key(g, pygame.K_m); draw(g)
move(g, center(g, "quit")); check("G5d 悬停高亮", ITEMS[g.menu.sel][0] == "quit")
g.menu.sel = [n for n, _ in ITEMS].index("ui"); key(g, pygame.K_RIGHT)
check("G5e 界面行 → 增大", g.app_request == "ui_plus")
g = mk(); key(g, pygame.K_m); g.menu.sel = len(ITEMS) - 1; key(g, pygame.K_DOWN); check("G5f 循环到第一项", g.menu.sel == 0)

# G6
for (w, h) in ((1280, 720), (800, 600), (1920, 1080), (1024, 500)):
    g = GameWorld(f, f, f, f, w, h, seed=1); g.set_screen_size(w, h); g.menu.open()
    s = pygame.Surface((g.ui_w, g.ui_h)); g._draw_ui(s, g.ui_w, g.ui_h)
    ok = all(r.x >= 0 and r.y >= 0 and r.right <= g.ui_w and r.bottom <= g.ui_h for r in g.menu.rects.values())
    check(f"G6 {w}x{h} 按钮全在画面内", ok, {k: tuple(r) for k, r in g.menu.rects.items() if r.bottom > g.ui_h})

# G7
g = mk(); h0 = world_hash(g)
key(g, pygame.K_m); draw(g); move(g, (5, 5)); key(g, pygame.K_DOWN); key(g, pygame.K_m)
check("G7a 打开/操作菜单不改变模拟状态", world_hash(g) == h0)
print("FAILS:", FAILS); sys.exit(1 if FAILS else 0)
