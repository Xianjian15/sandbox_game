# tools/eat_test.py
"""吃饭卡住 回归：
  E1 食物就在小人脚下（刚取出/丢下/站在食物上）：饿了应当立刻吃上，而不是反复"去吃饭→卡住→放弃"
  E2 食物在相邻格 / 远处 / 柜子里（站在柜子旁边）：都能吃上
  E3 饿着肚子、身边有多种食物：长时间运行后饱食度回升，状态不会长期停在 going_to_eat
用法： python -m tools.eat_test
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
def mk(seed=21):
    g = GameWorld(f, f, f, f, 1280, 720, seed=seed); g.set_screen_size(1280, 720); return g

def hungry(g, c, sat=20.0):
    c.satiety = sat; c.rest = 100; c.mood = 80
    for o in g.colonists:
        if o is not c: o.satiety = 100; o.rest = 100

def run_eat(g, c, ticks=900):
    """返回 (吃上所用 tick 或 None, 过程中 going_to_eat 连续最长 tick 数)"""
    s0 = c.satiety; worst = cur = 0
    for t in range(ticks):
        g.sim_step()
        cur = cur + 1 if c.state == "going_to_eat" else 0
        worst = max(worst, cur)
        if c.satiety > s0 + 20: return t, worst
    return None, worst

for kind in ("food", "meat", "meal_simple"):
    # E1 脚下
    g = mk(); c = g.colonists[0]; hungry(g, c)
    tx, ty = c.current_tile(); g.items.add(kind, 3, tx, ty)
    t, worst = run_eat(g, c)
    check(f"E1 脚下有 {kind}：能吃上", t is not None and worst < 120, (t, worst, c.state, c.satiety))

# E2 相邻 / 远处
for name, off in (("相邻格", (1, 0)), ("远处 8 格", (8, 0)), ("斜对角", (1, 1))):
    g = mk(); c = g.colonists[0]; hungry(g, c)
    tx, ty = c.current_tile()
    pos = None
    for dx, dy in (off, (-off[0], -off[1]), (0, off[0] or 1)):
        if g.world.is_walkable(tx + dx, ty + dy): pos = (tx + dx, ty + dy); break
    g.items.add("meal_simple", 2, *pos)
    t, worst = run_eat(g, c, 1500)
    check(f"E2 食物在{name}：能吃上", t is not None, (t, worst, c.state, c.satiety))

# 柜子里的食物（小人正站在柜子的相邻格 / 柜子格不可走）
g = mk(); c = g.colonists[0]; hungry(g, c)
cab = D._place(g, "small_cabinet", "wood", 1, 1)
cab.inventory = {"meal_simple": 3}
t, worst = run_eat(g, c, 2000)
check("E2 柜子里的食物：能吃上", t is not None, (t, worst, c.state, c.satiety, cab.inventory))
# 站在柜子旁边
g = mk(); c = g.colonists[0]; hungry(g, c)
cab = D._place(g, "small_cabinet", "wood", 1, 1); cab.inventory = {"meal_simple": 3}
for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
    ax, ay = cab.tx + dx, cab.ty + dy
    if g.world.is_walkable(ax, ay):
        c.x, c.y = ax * 32 + 16, ay * 32 + 16
        break
from settings import TILE_SIZE
c.x, c.y = ax * TILE_SIZE + TILE_SIZE / 2, ay * TILE_SIZE + TILE_SIZE / 2
t, worst = run_eat(g, c, 900)
check("E2 站在柜子旁：能吃上", t is not None and worst < 120, (t, worst, c.state, c.satiety, cab.inventory))

# E3 长跑
g = mk(33); c = g.colonists[0]; hungry(g, c, 30)
tx, ty = c.current_tile()
for i, k in enumerate(("food", "meat", "meal_simple", "meal_fine")):
    g.items.add(k, 2, tx + (i % 2), ty + (i // 2))
mn = 100; longest = cur = 0
for t in range(3600):
    g.sim_step()
    cur = cur + 1 if c.state == "going_to_eat" else 0; longest = max(longest, cur)
    mn = min(mn, c.satiety)
check("E3 长时间运行不再卡：going_to_eat 不会持续很久", longest < 300 and c.satiety > 30, (longest, c.satiety))
# E4 站在床上累了：能直接躺下睡觉
g = mk(44); c = g.colonists[0]; hungry(g, c, 100)
bed = D._place(g, "bed", "wood", 1, 2)
if bed:
    c.x, c.y = bed.tx * TILE_SIZE + TILE_SIZE / 2, bed.ty * TILE_SIZE + TILE_SIZE / 2
    c.rest = 20
    slept = False
    for t in range(600):
        g.sim_step()
        if c.state == "sleeping": slept = True; break
    check("E4 站在床上累了：直接睡下", slept, (c.state, c.rest))
else:
    print("  - E4 跳过：没找到放床的位置")
print("FAILS:", FAILS); sys.exit(1 if FAILS else 0)
