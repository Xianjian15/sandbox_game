# tools/bulk_carry_test.py
"""制作/烹饪/熔炼一次搬多个同类材料（而不是一个一个搬）。
  B1 工作台：队列 3 把石刀，地上 3 石 → 小人一趟手里最多拿到 3 个
  B2 熔炉：队列 3 份，6 粗铁 → 一趟最多拿 6，并炼出 3 份铁(6 个)
  B3 烹饪台：队列 3 份简单食物，6 肉 → 一趟最多拿 6，做出 3 份
  B4 材料不够时不会多拿/卡住（队列 3 把，只有 2 石 → 拿 2，不死循环）
用法： python -m tools.bulk_carry_test
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
from tools import determinism_test as D
from world.game_world import GameWorld
FAILS = []
def check(n, ok, info=""):
    print(("  ✓ " if ok else "  ✗ ") + n + (f"  {info}" if info and not ok else ""))
    if not ok: FAILS.append(n)
f = pygame.font.Font(None, 16)
def mk(seed=11):
    g = GameWorld(f, f, f, f, 1280, 720, seed=seed); g.set_screen_size(1280, 720); g.animals.clear(); return g
def amount(g, kind): return sum(st.amount for st in g.items.stacks.values() if st.kind == kind)
def run(g, kinds, done, ticks=15000):
    mx = {k: 0 for k in kinds}
    for t in range(ticks):
        g.sim_step()
        for c in g.colonists:
            if c.carrying and c.carrying["kind"] in mx: mx[c.carrying["kind"]] = max(mx[c.carrying["kind"]], c.carrying["amount"])
        if done(): return t, mx
    return None, mx

g = mk(); b = D._place(g, "workbench", "wood", 3, 1); D._stock(g, "stone", 3)
b.craft_queue = [{"item": "stone_knife"}] * 3; D._rclick(g, b)
t, mx = run(g, ["stone"], lambda: not b.craft_queue)
check("B1 工作台一趟拿 3 个石头", t is not None and mx["stone"] == 3, (t, mx))

g = mk(); b = D._place(g, "furnace", "stone", 3, 2); D._stock(g, "iron_ore", 6)
b.smelt_queue = [{"item": "iron"}] * 3; D._rclick(g, b)
t, mx = run(g, ["iron_ore"], lambda: not b.smelt_queue and amount(g, "iron") + sum((c.carrying or {}).get("amount", 0) for c in g.colonists if c.carrying and c.carrying["kind"] == "iron") >= 6, 30000)
check("B2 熔炉一趟拿 6 粗铁并炼出 6 铁", t is not None and mx["iron_ore"] == 6, (t, mx, b.smelt_queue, amount(g, "iron")))

g = mk(); b = D._place(g, "stove", "stone", 3, 1); D._stock(g, "meat", 6)
b.cook_queue = [{"meal": "meal_simple"}] * 3; D._rclick(g, b)
t, mx = run(g, ["meat"], lambda: not b.cook_queue and amount(g, "meal_simple") + sum((c.carrying or {}).get("amount", 0) for c in g.colonists if c.carrying and c.carrying["kind"] == "meal_simple") >= 3, 30000)
check("B3 烹饪台一趟拿 6 肉并做出 3 份", t is not None and mx["meat"] == 6, (t, mx, b.cook_queue))

g = mk(); b = D._place(g, "workbench", "wood", 3, 1); D._stock(g, "stone", 2)
b.craft_queue = [{"item": "stone_knife"}] * 3; D._rclick(g, b)
t, mx = run(g, ["stone"], lambda: len(b.craft_queue) == 1, 12000)
check("B4 材料只够 2 把：做完 2 把后停下，不死循环", t is not None and mx["stone"] == 2, (t, mx, len(b.craft_queue)))
g = mk(); b = D._place(g, "stove", "stone", 3, 1); D._stock(g, "meat", 2); D._stock(g, "food", 2)
b.cook_queue = [{"meal": "meal_fine"}]; D._rclick(g, b)
t, mx = run(g, ["meat", "food"], lambda: not b.cook_queue and amount(g, "meal_fine") + sum((c.carrying or {}).get("amount", 0) for c in g.colonists if c.carrying and c.carrying["kind"] == "meal_fine") >= 1, 20000)
check("B5 美味食物：一趟各拿 2 肉 / 2 浆果并做出", t is not None and mx["meat"] == 2 and mx["food"] == 2, (t, mx))
print("FAILS:", FAILS); sys.exit(1 if FAILS else 0)
