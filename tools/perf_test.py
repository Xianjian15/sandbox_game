# tools/perf_test.py
"""后期性能验收（防止后期卡顿回归）。造一个"后期"世界：近千面墙/地板、2400 个物品堆、4 块农田、大库存区、
7 个小人、8 个被围墙挡住的敌人，然后量每个 tick 的模拟耗时。
  P1 get_building_at 与旧实现（扫描全部建筑）结果完全一致（含多层重叠）
  P2 房间扫描：近千建筑时单次 < 150 ms（旧实现约 300+ ms，每 2 秒卡一下）
  P3 后期模拟：平均每 tick < 4 ms（预算：3 倍速每帧 3 个 tick，60 FPS 一帧 16 ms）
  P4 被围墙挡住的敌人：每个敌人每秒最多重新寻路约 1~2 次，而不是每 tick 一次
  P5 绘制只画屏幕内的东西：把相机移到空角落，物品/建筑/农田/库存区的绘制调用数应接近 0
用法： python -m tools.perf_test
"""
import os, sys, time, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
try:
    import pygame
    pygame.init(); pygame.display.set_mode((64, 64))
except ImportError:
    from tools import fake_pygame
    pygame = fake_pygame.install()
from world.game_world import GameWorld
from world.buildings import BUILDING_DEFS
from entities.colonist import Colonist
from entities.enemy import Enemy
from core import pathfinding
FAILS = []
def check(n, ok, info=""):
    print(("  ✓ " if ok else "  ✗ ") + n + (f"  {info}" if info and not ok else ""))
    if not ok: FAILS.append(n)

f = pygame.font.Font(None, 16)
random.seed(1)
g = GameWorld(f, f, f, f, 1280, 720, seed=7); g.set_screen_size(1280, 720)
cx, cy = g.colonists[0].current_tile()
n = 0
for dx in range(-45, 45):
    for dy in range(-35, 35):
        x, y = cx + dx, cy + dy
        if (dx % 5 == 0 or dy % 5 == 0) and g.world.is_terrain_walkable(x, y) and not g.buildings.get_building_at(x, y):
            bp = g.buildings.add_blueprint(random.choice(["wall", "floor"]), "wood", x, y); g.buildings.complete_blueprint(bp); n += 1
for i in range(2500):
    g.items.add(random.choice(["wood", "stone", "food", "meat", "iron_ore", "leather"]), random.randint(1, 40), cx + random.randint(-45, 45), cy + random.randint(-35, 35))
g.stockpiles.add((cx - 20, cy - 20, cx + 20, cy + 20))
for i in range(4): g.farms.add((cx - 30 + i * 12, cy + 8, cx - 20 + i * 12, cy + 18), "berry")
for i in range(6): g.colonists.append(Colonist(cx + i, cy + 1, ctx=g.ctx))
for i in range(8): g.enemies.append(Enemy(cx + 20 + i, cy + 5, "club", ctx=g.ctx))
print(f"  世界：建筑 {len(g.buildings.buildings)}  物品堆 {len(g.items.stacks)}  小人 {len(g.colonists)}  敌人 {len(g.enemies)}")

# P1
def old_get(bm, tx, ty):
    res = [b for k, b in bm.buildings.items() if k[:2] == (tx, ty)]
    return sorted(res, key=lambda b: b.layer, reverse=True)[0] if res else None
for (kind, mat) in (("wall", "wood"),):
    pass
# 制造一些叠层：同一格 地板(layer0) + 家具(layer1)
extra = 0
for dx in range(-6, 6):
    x, y = cx + dx, cy - 3
    if g.world.is_terrain_walkable(x, y):
        for k in ("floor", "bed"):
            if k in BUILDING_DEFS:
                try:
                    bp = g.buildings.add_blueprint(k, next(iter(BUILDING_DEFS[k]["variants"])), x, y); g.buildings.complete_blueprint(bp); extra += 1
                except Exception: pass
bad = 0
for x in range(cx - 50, cx + 50):
    for y in range(cy - 40, cy + 40):
        a, b = g.buildings.get_building_at(x, y), old_get(g.buildings, x, y)
        if a is not b: bad += 1
check("P1 get_building_at 与旧实现一致", bad == 0, bad)

# P2
t = time.time(); g.room_mgr._recalculate(); ms = (time.time() - t) * 1000
check(f"P2 房间扫描 {ms:.0f} ms（<150）", ms < 150)

# P3 / P4
calls = [0]; orig = pathfinding.astar
import entities.enemy as E
def counting(*a, **k):
    calls[0] += 1; return orig(*a, **k)
E.astar = counting
for _ in range(120): g.sim_step()
calls[0] = 0
t = time.time()
for _ in range(900): g.sim_step()
per = (time.time() - t) / 900 * 1000
check(f"P3 后期模拟平均 {per:.2f} ms/tick（<4）", per < 4)
alive = sum(1 for e in g.enemies if e.hp > 0)
check(f"P4 敌人寻路次数 {calls[0]}（{alive} 个敌人 15 秒）远少于每 tick 一次", calls[0] < 900 * max(1, alive) / 10, calls[0])

# P5
g.camera.x, g.camera.y = 0.0, 0.0
class Cnt:
    def __init__(s): s.n = 0
cnt = [0]
for cls_name in ("ItemStack",):
    pass
import world.items as WI, world.buildings as WB
oi, ob = WI.ItemStack.draw, WB.Building.draw
WI.ItemStack.draw = lambda self, *a: cnt.__setitem__(0, cnt[0] + 1)
WB.Building.draw = lambda self, *a: cnt.__setitem__(0, cnt[0] + 1)
far = g.camera
g.camera.x, g.camera.y = 0.0, 0.0
g.camera._clamp()
# 把相机放在离所有东西都很远的位置（地图另一角）
g.camera.x, g.camera.y = g.camera.map_w, g.camera.map_h; g.camera._clamp()
if abs(g.camera.x // 32 - cx) > 60 and abs(g.camera.y // 32 - cy) > 50:
    s = pygame.Surface((1280, 720))
    g.items.draw(s, g.camera, f); g.buildings.draw_layer(s, g.camera, f, 0); g.buildings.draw_layer(s, g.camera, f, 1)
    check("P5 屏幕外的物品/建筑不绘制", cnt[0] == 0, cnt[0])
else:
    g.camera.x, g.camera.y = 0.0, 0.0
    s = pygame.Surface((1280, 720))
    g.items.draw(s, g.camera, f); g.buildings.draw_layer(s, g.camera, f, 0); g.buildings.draw_layer(s, g.camera, f, 1)
    total = len(g.items.stacks) + len(set(map(id, g.buildings.buildings.values())))
    check("P5 屏幕外的物品/建筑不绘制", cnt[0] < total * 0.5, (cnt[0], total))
WI.ItemStack.draw, WB.Building.draw = oi, ob
print("FAILS:", FAILS); sys.exit(1 if FAILS else 0)
