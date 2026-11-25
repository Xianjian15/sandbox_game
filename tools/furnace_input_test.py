# tools/furnace_input_test.py
"""熔炉/烹饪台/柜子的数字输入框验收（旧 bug：菜单结束时关闭了系统文字输入，进游戏后收不到数字）。
  N1 点输入框→进入编辑，GameWorld 声明需要文字输入（main 据此打开系统文字输入）
  N2 收到 TEXTINPUT 数字→写进输入框；非数字被忽略；最多 3 位；退格
  N3 Enter 提交：发出熔炼数量指令并退出编辑；退出编辑后不再需要文字输入
  N4 点面板外/Esc 也会退出编辑
  N5 main 的接线：进游戏时关闭文字输入，编辑数字框时才打开
用法： python -m tools.furnace_input_test
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
FAILS = []
def check(n, ok, info=""):
    print(("  ✓ " if ok else "  ✗ ") + n + (f"  {info}" if info and not ok else ""))
    if not ok: FAILS.append(n)

f = pygame.font.Font(None, 16)
W, H = 1280, 720
g = GameWorld(f, f, f, f, W, H, seed=2); g.set_screen_size(W, H)
cmds = []
orig = g.issue
g.bhud.emit = lambda c: (cmds.append(c), orig(c))[1]
b = Building("furnace", "stone", 30, 30)
g.buildings.buildings[(30, 30, b.layer)] = b
g.selected_building = b
s = pygame.Surface((g.ui_w, g.ui_h))
def draw(): g._draw_ui(s, g.ui_w, g.ui_h); g.set_screen_size(W, H)
def ev(t, **kw): g.handle_event(pygame.event.Event(t, **kw), W, H)
def click(p): ev(pygame.MOUSEBUTTONDOWN, pos=(int(p[0] * g.ui_scale), int(p[1] * g.ui_scale)), button=1)
def text(t): ev(pygame.TEXTINPUT, text=t)
def key(k): ev(pygame.KEYDOWN, key=k, mod=0, unicode="")

draw()
box = g.bhud.input_rects["iron"]
check("N0 编辑前不需要文字输入", not g.wants_text_input())
click(box.center)
check("N1 点输入框：进入编辑并要求文字输入", g.wants_text_input() and g.bhud.active_input == "iron")
g.bhud.edit_text = ""
text("5"); text("a"); text("é"); text("7")
check("N2a 数字写入、字母被忽略", g.bhud.edit_text == "57", g.bhud.edit_text)
text("123"); check("N2b 最多 3 位", len(g.bhud.edit_text) <= 3, g.bhud.edit_text)
key(pygame.K_BACKSPACE); check("N2c 退格", len(g.bhud.edit_text) == 2, g.bhud.edit_text)
g.bhud.edit_text = "8"
n0 = len(cmds)
key(pygame.K_RETURN)
sm = [c for c in cmds[n0:] if "smelt_set" in str(c) and "8" in str(c)]
check("N3a Enter 提交熔炼数量指令", bool(sm), cmds[n0:])
check("N3b 提交后退出编辑，不再需要文字输入", not g.wants_text_input())
draw(); click(box.center); check("N4a 再次点进编辑", g.wants_text_input())
key(pygame.K_ESCAPE); check("N4b Esc 退出编辑", not g.wants_text_input())
draw(); click(box.center); click((900, 20))
check("N4c 点面板外退出编辑", not g.wants_text_input())

src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py"), encoding="utf-8").read()
check("N5 main：进游戏关文字输入，编辑时才开", "wants_text_input()" in src and "start_text_input if want" in src and src.index("stop_text_input()") < src.index("while running"))
print("FAILS:", FAILS); sys.exit(1 if FAILS else 0)
