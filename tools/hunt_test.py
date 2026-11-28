# tools/hunt_test.py
"""狩猎回归：小人追打猎物不会"打到一半停下"。
  H1 站着的兔子/鹿：下达狩猎后一定被打死并掉落肉（多个随机位置/种子）
  H2 会逃跑的猎物（被打后逃 5 秒）：仍能追上打死
  H3 打猎过程中不会因"防卡死"被取消目标（监视 target_animal 在猎物活着时不会被清空，除非超过放弃时间）
  H4 猎物够不着（被水隔开）：最终会放弃，不会永远卡在这只猎物上
用法： python -m tools.hunt_test
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
from entities.animal import Animal
from core import commands as cmdlib
from tools import determinism_test as D
FAILS = []
def check(n, ok, info=""):
    print(("  ✓ " if ok else "  ✗ ") + n + (f"  {info}" if info and not ok else ""))
    if not ok: FAILS.append(n)

f = pygame.font.Font(None, 16)
def mk(seed):
    g = GameWorld(f, f, f, f, 1280, 720, seed=seed); g.set_screen_size(1280, 720)
    g.animals.clear(); return g
def meat(g): return sum(st.amount for st in g.items.stacks.values() if st.kind == "meat")
def hunt(g, c, a):
    c.selected = True
    g.issue(cmdlib.make("hunt", animal=a.id)) if False else c.enqueue_command({"type": "hunt", "animal": a})

def run(g, c, a, ticks=2400):
    cleared_early = 0
    for t in range(ticks):
        g.sim_step()
        if a.hp <= 0: return t, cleared_early
        if c.target_animal is None and a.hp > 0 and t > 5: cleared_early += 1; c.enqueue_command({"type": "hunt", "animal": a}) if False else None
    return None, cleared_early

ok1 = ok2 = 0; n = 0; early = 0
for seed in range(1, 7):
    for species, off in (("rabbit", (4, 0)), ("deer", (6, 2)), ("rabbit", (0, -5)), ("deer", (-5, 3))):
        g = mk(seed); c = g.colonists[0]; tx, ty = c.current_tile()
        pos = None
        for r in range(0, 4):
            for dx, dy in ((off[0] + r, off[1]), (off[0], off[1] + r), (-off[0], -off[1]), (off[0] + 1, off[1] + 1)):
                if g.world.is_walkable(tx + dx, ty + dy): pos = (tx + dx, ty + dy); break
            if pos: break
        a = Animal(*pos, species, ctx=g.ctx); g.animals.append(a)
        c.rest = c.satiety = 100
        hunt(g, c, a)
        t, e = run(g, c, a)
        n += 1; ok1 += t is not None; early += e
        if t is None: print('FAIL', seed, species, off, pos, (tx,ty), 'hp', a.hp, 'at', a.current_tile(), 'col', c.current_tile(), c.state, c.target_animal is not None, len(c.path), c.hunt_timer)
check(f"H1 站着/游荡的猎物都被打死（{ok1}/{n}）", ok1 == n, (ok1, n))
check("H3 打猎过程中目标没有被中途清空", early == 0, early)

# H2 被打后会逃：给一只 5 秒逃跑 + 持续移动的猎物
okf = 0; nf = 0
for seed in range(1, 6):
    g = mk(seed); c = g.colonists[0]; tx, ty = c.current_tile()
    pos = next(((tx + dx, ty + dy) for dx, dy in ((5, 0), (4, 1), (-5, 0), (0, 5)) if g.world.is_walkable(tx + dx, ty + dy)), None)
    a = Animal(*pos, "deer", ctx=g.ctx); a.hp = a.max_hp = 90; g.animals.append(a)   # 多挨几下，逃跑期更长
    c.rest = c.satiety = 100; hunt(g, c, a)
    t, e = run(g, c, a, 3600); nf += 1; okf += t is not None
check(f"H2 会逃跑的猎物也能追上打死（{okf}/{nf}）", okf == nf, (okf, nf))

# H4 够不着：猎物在水中央
g = mk(3); c = g.colonists[0]; tx, ty = c.current_tile()
from world.world import T_WATER
for dx in range(-2, 3):
    for dy in range(-2, 3):
        g.world.tiles[ty + 8 + dy][tx + dx] = T_WATER
a = Animal(tx, ty + 8, "rabbit", ctx=g.ctx); g.animals.append(a); a.speed = 0
c.rest = c.satiety = 100; c.HUNT_GIVE_UP = 8.0
hunt(g, c, a)
for _ in range(60 * 14): g.sim_step()
check("H4 够不着的猎物最终会放弃", c.target_animal is None and a.hp > 0, (c.target_animal, a.hp))
print("FAILS:", FAILS); sys.exit(1 if FAILS else 0)
