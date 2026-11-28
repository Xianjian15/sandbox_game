# tools/touch_test.py
"""触屏模式验收（手势 → 鼠标/键盘事件）。
  T1 自动切换：电脑模式下收到手指触摸 → 进入触屏模式
  T2 轻点选中小人；轻点空地取消选择
  T3 长按 → 对选中的小人下"移动"指令
  T4 单指拖动平移视角（不会下指令、不会框选）；双指拖动平移视角
  T5 库存区模式下单指拖动 = 拖框建库存区
  T6 "框选"开关：拖动框选小人
  T7 "指令"开关：轻点 = 右键下指令
  T8 工具栏：建造(B)/取消(Esc)/速度(空格)/菜单(M)；"排队"开关 = Shift
  T9 菜单里"操作模式"可切回电脑模式；触屏模式下系统合成的鼠标事件被 main 忽略（这里验证 enabled 状态）
用法： python -m tools.touch_test
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
from settings import TILE_SIZE
FAILS = []
def check(n, ok, info=""):
    print(("  ✓ " if ok else "  ✗ ") + n + (f"  {info}" if info and not ok else ""))
    if not ok: FAILS.append(n)
W, H = 1280, 720
f = pygame.font.Font(None, 16)
def mk():
    g = GameWorld(f, f, f, f, W, H, seed=11); g.set_screen_size(W, H); g.animals.clear(); g.cmd_log = []
    now = [0]; g.touch.clock = lambda: now[0]; g._now = now
    return g
def fe(t, fid, px, py): return pygame.event.Event(t, finger_id=fid, x=px[0] / W if False else px / W, y=py / H)
def finger(g, kind, fid, px, py):
    t = {"down": pygame.FINGERDOWN, "move": pygame.FINGERMOTION, "up": pygame.FINGERUP}[kind]
    g.touch.handle(pygame.event.Event(t, finger_id=fid, x=px / W, y=py / H), W, H)
def tap(g, px, py): finger(g, "down", 1, px, py); finger(g, "up", 1, px, py)
def screen_of(g, c): return g.camera.world_to_screen(c.x, c.y)
def types(g): return [x["t"] for x in g.cmd_log] if g.cmd_log else []
def last_cmds(g):
    out = []
    for item in getattr(g, "cmd_log", []): out.append(item[1]["t"] if isinstance(item, tuple) else item["t"])
    return out
def pos_on_screen(g, tx, ty): return g.camera.world_to_screen(tx * TILE_SIZE + TILE_SIZE // 2, ty * TILE_SIZE + TILE_SIZE // 2)
def free_target(g):
    c = g.colonists[0]; tx, ty = c.current_tile()
    for dx, dy in ((5, 0), (-5, 0), (0, 5), (0, -5), (4, 3), (-4, -3)):
        if g.world.is_walkable(tx + dx, ty + dy):
            sx, sy = pos_on_screen(g, tx + dx, ty + dy)
            if 150 < sx < W - 150 and 150 < sy < H - 250: return sx, sy
    return None

# T1
g = mk(); check("T1 初始是电脑模式", not g.touch.enabled)
finger(g, "down", 1, 600, 300); finger(g, "up", 1, 600, 300)
check("T1 收到触摸后自动进入触屏模式", g.touch.enabled)

# T2
g = mk(); g.touch.set_enabled(True, notify=False); c = g.colonists[0]
sx, sy = screen_of(g, c); tap(g, sx, sy)
check("T2 轻点小人：选中", c.selected)
tx, ty = free_target(g); tap(g, tx, ty)
check("T2 轻点空地：取消选择", not c.selected)

# T3
g = mk(); g.touch.set_enabled(True, notify=False); c = g.colonists[0]
sx, sy = screen_of(g, c); tap(g, sx, sy)
tx, ty = free_target(g)
finger(g, "down", 1, tx, ty); g._now[0] += 200; g.touch.update(W, H)
check("T3 没到 0.45 秒：还没下指令", "move" not in last_cmds(g))
g._now[0] += 400; g.touch.update(W, H)
check("T3 长按：对选中小人下 move 指令", "move" in last_cmds(g), last_cmds(g))
n0 = len(last_cmds(g)); finger(g, "up", 1, tx, ty)
check("T3 抬手不会再多发一条", len(last_cmds(g)) == n0)

# T4
g = mk(); g.touch.set_enabled(True, notify=False); c = g.colonists[0]
sx, sy = screen_of(g, c); tap(g, sx, sy)
cx0, cy0 = g.camera.x, g.camera.y
finger(g, "down", 1, 700, 360); finger(g, "move", 1, 650, 340); finger(g, "move", 1, 600, 320); finger(g, "up", 1, 600, 320)
check("T4 单指拖动：视角平移", abs(g.camera.x - cx0) > 20 or abs(g.camera.y - cy0) > 10, (g.camera.x - cx0, g.camera.y - cy0))
check("T4 拖动没有下指令，小人仍被选中", "move" not in last_cmds(g) and c.selected, last_cmds(g))
cx0, cy0 = g.camera.x, g.camera.y
finger(g, "down", 1, 600, 300); finger(g, "down", 2, 700, 300)
finger(g, "move", 1, 560, 300); finger(g, "move", 2, 660, 300); finger(g, "up", 1, 560, 300); finger(g, "up", 2, 660, 300)
check("T4 双指拖动：视角平移", abs(g.camera.x - cx0) > 20, g.camera.x - cx0)

# T5
g = mk(); g.touch.set_enabled(True, notify=False); g.mode = "stockpile"
a = pos_on_screen(g, *g.colonists[0].current_tile()); b = (a[0] + 90, a[1] + 60)
finger(g, "down", 1, *a); finger(g, "move", 1, a[0] + 40, a[1] + 30); finger(g, "move", 1, *b); finger(g, "up", 1, *b)
check("T5 库存区模式拖动：创建库存区", "stockpile_add" in last_cmds(g), last_cmds(g))

# T6
g = mk(); g.touch.set_enabled(True, notify=False); c = g.colonists[0]
sx, sy = screen_of(g, c)
for bid in ("box",): pass
g.touch.layout(g.ui_h)
r = g.touch.rects["box"]; px, py = r.centerx * g.ui_scale, r.centery * g.ui_scale
tap(g, px, py)
check("T6 点\"框选\"：开关打开", g.touch.flags["box"])
finger(g, "down", 1, sx - 50, sy - 50); finger(g, "move", 1, sx, sy); finger(g, "move", 1, sx + 60, sy + 60); finger(g, "up", 1, sx + 60, sy + 60)
check("T6 框选开启后拖动：框住小人", c.selected)

# T7
g = mk(); g.touch.set_enabled(True, notify=False); c = g.colonists[0]
sx, sy = screen_of(g, c); tap(g, sx, sy)
g.touch.layout(g.ui_h); r = g.touch.rects["cmd"]; tap(g, r.centerx * g.ui_scale, r.centery * g.ui_scale)
tx, ty = free_target(g); tap(g, tx, ty)
check("T7 指令开关：轻点 = 右键下指令", "move" in last_cmds(g), last_cmds(g))

# T8
g = mk(); g.touch.set_enabled(True, notify=False); g.touch.layout(g.ui_h)
def press(g, bid):
    g.touch.layout(g.ui_h); r = g.touch.rects[bid]; tap(g, r.centerx * g.ui_scale, r.centery * g.ui_scale)
press(g, "build"); check("T8 工具栏\"建造\"：进入建造模式", g.mode == "build")
press(g, "esc"); check("T8 工具栏\"取消\"：退出模式", g.mode is None)
v0 = g.game_speed; press(g, "speed")
check("T8 工具栏\"速度\"：发出 speed 指令", "speed" in last_cmds(g))
press(g, "queue"); check("T8 \"排队\"开关 = Shift", g.touch_shift is True)
press(g, "menu"); check("T8 工具栏\"菜单\"：打开游戏菜单", g.menu.active)

# T9
g.draw_rects = None
_s = pygame.Surface((g.ui_w, g.ui_h)); g._draw_ui(_s, g.ui_w, g.ui_h)
r = g.menu.rects["input"]
g.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(int(r.centerx * g.ui_scale), int(r.centery * g.ui_scale)), button=1), W, H)
check("T9 菜单\"操作模式\"：切回电脑模式", not g.touch.enabled and g.menu.active)
print("FAILS:", FAILS); sys.exit(1 if FAILS else 0)
