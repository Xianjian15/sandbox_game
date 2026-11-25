# tools/ui_fix_test.py
"""界面修复验收：
  F1 建造栏：各种窗口大小、各模式下，所有建筑按钮都在屏幕内（不再超出）
  F2 制作面板：选中工作台后，点面板里的按钮不会让面板关闭（旧 bug：面板点击区域被缩放逻辑挪到右侧）
  F3 窗口变大：界面（按钮）大小不变，只有窗口小于设计尺寸才缩小
用法： python -m tools.ui_fix_test
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
from world.buildings import Building
from core import ui_scale as U
FAILS = []
def check(n, ok, info=""):
    print(("  ✓ " if ok else "  ✗ ") + n + (f"  {info}" if info and not ok else ""))
    if not ok: FAILS.append(n)

f = pygame.font.Font(None, 16)
def mk(w, h):
    g = GameWorld(f, f, f, f, w, h, seed=3); g.set_screen_size(w, h); return g

def frame(g, w, h):
    s = pygame.Surface((w, h)); g.draw(s) if hasattr(g, "draw") else None

# F1
for (w, h) in ((1280, 720), (1366, 768), (1920, 1080), (1024, 600)):
    g = mk(w, h)
    g.mode = "build"
    surf = pygame.Surface((g.ui_w, g.ui_h))
    g._draw_ui(surf, g.ui_w, g.ui_h)
    rects = [r for r, _ in g.build_menu.buttons]
    ok = rects and all(r.x >= 0 and r.right <= g.ui_w for r in rects)
    check(f"F1 {w}x{h} 建造栏 {len(rects)} 个按钮全部在屏幕内", ok, (min(r.x for r in rects), max(r.right for r in rects), g.ui_w))

# F2
g = mk(1920, 1080)
b = Building("workbench", "wood", 20, 20)
g.buildings.buildings[(20, 20, b.layer)] = b
g.selected_building = b
surf = pygame.Surface((g.ui_w, g.ui_h))
for _ in range(3):
    g._draw_ui(surf, g.ui_w, g.ui_h)
    g.set_screen_size(1920, 1080)            # 每帧都会重新计算缩放（旧代码在这里把面板挪到右边）
r = g.bhud.panel_rect
pos = (int((r.x + 30) * g.ui_scale), int((r.y + 30) * g.ui_scale))
check("F2 工作台面板在左侧", r.x == 10, r)
ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1)
g.handle_event(ev, 1920, 1080)
check("F2 点面板内部：面板仍然打开", g.selected_building is b)
g._draw_ui(surf, g.ui_w, g.ui_h); g.set_screen_size(1920, 1080)
btn = next(iter(g.bhud.btn_rects.values()), None)
if btn:
    pos = (int(btn.centerx * g.ui_scale), int(btn.centery * g.ui_scale))
    g.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1), 1920, 1080)
    check("F2 点制作按钮：面板仍然打开", g.selected_building is b)
else:
    check("F2 工作台有制作按钮", False)

# F3
check("F3 窗口变大界面不变", U.compute_scale(1280, 720) == U.compute_scale(2560, 1440) == U.compute_scale(3840, 2160) == U.DEFAULT_PREF)
check("F3 小窗口缩小", U.compute_scale(900, 500) < U.DEFAULT_PREF)
print("FAILS:", FAILS); sys.exit(1 if FAILS else 0)
