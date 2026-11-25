# tools/station_ui_test.py
"""工作站面板验收（走真实 GameWorld 的鼠标/键盘/文字事件路径）：
  S1 烹饪台  点“简单食物/美味食物”数字框→输入数字→Enter：烹饪队列变成对应数量
  S2 工作台  点“石镐”按钮：制造队列增加；未研究的铁制品/枪械按钮不可点
  S3 柜子    点“取出”数量框→输入数字→点取出：发出取出指令（面板不关闭）
  S4 面板常驻 以上操作后面板（选中的建筑）仍然打开
用法： python -m tools.station_ui_test
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
def mk():
    g = GameWorld(f, f, f, f, W, H, seed=2); g.set_screen_size(W, H); return g
def put(g, kind, mat, x, y):
    b = Building(kind, mat, x, y); g.buildings.buildings[(x, y, b.layer) if False else (x, y)] = b; g.selected_building = b; return b
def draw(g):
    s = pygame.Surface((g.ui_w, g.ui_h)); g._draw_ui(s, g.ui_w, g.ui_h); g.set_screen_size(W, H)
def ev(g, t, **kw): g.handle_event(pygame.event.Event(t, **kw), W, H)
def click(g, p): ev(g, pygame.MOUSEBUTTONDOWN, pos=(int(p[0] * g.ui_scale), int(p[1] * g.ui_scale)), button=1)
def text(g, t): ev(g, pygame.TEXTINPUT, text=t)
def key(g, k): ev(g, pygame.KEYDOWN, key=k, mod=0, unicode="")
def step(g, n=3):
    for _ in range(n): g._world_step()

# S1
g = mk(); b = put(g, "stove", "stone", 30, 30); draw(g)
click(g, g.bhud.input_rects["meal_simple"].center)
check("S1a 点烹饪数字框进入编辑", g.wants_text_input())
g.bhud.edit_text = ""; text(g, "3"); key(g, pygame.K_RETURN); step(g)
n_simple = sum(1 for t in b.cook_queue if t["meal"] == "meal_simple")
check("S1b 简单食物 ×3 进入烹饪队列", n_simple == 3, b.cook_queue)
draw(g); click(g, g.bhud.input_rects["meal_fine"].center)
g.bhud.edit_text = ""; text(g, "2"); key(g, pygame.K_RETURN); step(g)
cnt = lambda m: sum(1 for t in b.cook_queue if t["meal"] == m)
check("S1c 美味食物 ×2，简单食物仍是 3", cnt("meal_fine") == 2 and cnt("meal_simple") == 3, b.cook_queue)
check("S4a 烹饪台面板仍打开", g.selected_building is b)

# S2
g = mk(); b = put(g, "workbench", "wood", 30, 30); draw(g)
check("S2a 未研究时铁制品/枪械按钮不可点", set(g.bhud.btn_rects) == {"craft_stone_pick"}, list(g.bhud.btn_rects))
click(g, g.bhud.btn_rects["craft_stone_pick"].center); step(g)
check("S2b 点石镐：制造队列 +1", len(b.craft_queue) == 1, b.craft_queue)
draw(g); click(g, g.bhud.btn_rects["craft_stone_pick"].center); step(g)
check("S2c 再点一次：队列 2", len(b.craft_queue) == 2)
g.research_mgr.completed.update({"stone_masonry", "smelting", "crafting", "gunsmithing"})
draw(g)
check("S2d 研究后铁制品/枪械按钮出现", {"craft_axe", "craft_pick", "craft_sword", "craft_pistol", "craft_rifle"} <= set(g.bhud.btn_rects), list(g.bhud.btn_rects))
click(g, g.bhud.btn_rects["craft_sword"].center); click(g, g.bhud.btn_rects["craft_rifle"].center); step(g)
items = [t["item"] for t in b.craft_queue]
check("S2e 长剑/步枪入队", "longsword" in items and "rifle" in items, items)
check("S4b 工作台面板仍打开", g.selected_building is b)

# S3
g = mk(); b = put(g, "small_cabinet", "wood", 30, 30); b.inventory = {"wood": 20}; draw(g)
cmds = []; orig = g.issue; g.issue = lambda c: (cmds.append(c), orig(c))[1]
ok_rects = bool(g.bhud.take_input_rects) and bool(g.bhud.take_btn_rects)
check("S3a 柜子面板有取出输入框和按钮", ok_rects, (g.bhud.take_input_rects, g.bhud.take_btn_rects))
if ok_rects:
    k = next(iter(g.bhud.take_input_rects))
    g.colonists[0].selected = True
    click(g, g.bhud.take_input_rects[k].center)
    check("S3b 点取出数量框进入编辑", g.wants_text_input())
    text(g, "5"); check("S3c 输入 5", g.bhud.edit_text == "5", g.bhud.edit_text)
    draw(g); click(g, g.bhud.take_btn_rects[k].center)
    tk = [c for c in cmds if c.get("t", c.get("type")) == "take"]
    check("S3d 点取出：发出 take 指令(数量 5)", bool(tk) and tk[0].get("amt") == 5, cmds)
    check("S4c 柜子面板仍打开", g.selected_building is b)
print("FAILS:", FAILS); sys.exit(1 if FAILS else 0)
