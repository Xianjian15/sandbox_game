# tools/content_test.py
"""v0.9.0 新内容验收：石器、铁建材、陨石、新动物、大地图。
  C1 石斧/石矛(含木头)/石锤/石刀 都能在工作台做出并装备
  C2 铁地板/墙/窗/门：研究"钢铁建筑"前不可建，研究后可建；cost 用铁
  C3 陨石事件：落点远离所有小人，生成陨石堆；采集得到粗铁+石头（需镐）
  C4 新动物：6 个物种都能生成/狩猎掉落正确；野猪被打会反击
  C5 大地图 160x120 的初始化耗时、铁矿/石头数量合理，出生点可走
用法： python -m tools.content_test
"""
import os, sys, time
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
from world.world import T_METEOR, T_IRON_ROCK, T_ROCK, T_DIRT
from entities.animal import Animal, SPECIES
from combat.weapons import WEAPONS, CRAFT_COST
from settings import TILE_SIZE, MAP_WIDTH, MAP_HEIGHT
FAILS = []
def check(n, ok, info=""):
    print(("  ✓ " if ok else "  ✗ ") + n + (f"  {info}" if info and not ok else ""))
    if not ok: FAILS.append(n)
f = pygame.font.Font(None, 16)
def mk(seed=11):
    g = GameWorld(f, f, f, f, 1280, 720, seed=seed); g.set_screen_size(1280, 720); return g
def amount(g, kind): return sum(st.amount for st in g.items.stacks.values() if st.kind == kind)
def run_until(g, cond, ticks=12000):
    for t in range(ticks):
        g.sim_step()
        if cond(): return t
    return None

# C1
for item, stock in (("stone_axe", {"stone": 3}), ("stone_spear", {"stone": 2, "wood": 1}),
                    ("stone_hammer", {"stone": 4}), ("stone_knife", {"stone": 1})):
    g = mk(); b = D._place(g, "workbench", "wood", 2, 1)
    for k, v in stock.items(): D._stock(g, k, v)
    b.craft_queue = [{"item": item}]; D._rclick(g, b)
    t = run_until(g, lambda: not b.craft_queue and (amount(g, item) > 0 or any(c.weapon_key == item for c in g.colonists)))
    check(f"C1 {WEAPONS[item]['name']} 制作完成", t is not None, (b.craft_queue, b.delivered_materials))
check("C1 配方表覆盖所有可制造物品", all(k in WEAPONS for k in CRAFT_COST if k != "gun"))

# C2
g = mk(); rm = g.research_mgr
check("C2 研究前铁墙不可建", not rm.is_unlocked("wall", "iron"))
rm.completed.update({"stone_masonry", "smelting", "iron_construction"})
check("C2 研究后铁地板/墙/窗/门可建", all(rm.is_unlocked(k, "iron") for k in ("floor", "wall", "window", "door")))
from world.buildings import BUILDING_DEFS
check("C2 铁建材消耗铁", all(BUILDING_DEFS[k]["variants"]["iron"]["cost"].get("iron") for k in ("floor", "wall", "window", "door")))
D._stock(g, "iron", 4)
b = D._place(g, "wall", "iron", 3, 3)
check("C2 铁墙可放置并有更高耐久", b is not None and b.max_hp > BUILDING_DEFS["wall"]["variants"]["stone"]["hp"], getattr(b, "max_hp", None))

# C3
g = mk(5)
before = g.meteors_spawned
g._spawn_meteor()
tiles = [(x, y) for y in range(MAP_HEIGHT) for x in range(MAP_WIDTH) if g.world.tiles[y][x] == T_METEOR]
check("C3 生成了陨石堆", g.meteors_spawned == before + 1 and len(tiles) >= 3, len(tiles))
cols = [c.current_tile() for c in g.colonists]
cx, cy = tiles[0]
dist = min(abs(cx - px) + abs(cy - py) for px, py in cols)
check("C3 落点远离小人(≥30格)", dist >= 30, dist)
c = g.colonists[0]; c.tool_key = "stone_pickaxe"
tx, ty = tiles[0]
check("C3 陨石堆可采集", g.world.is_harvestable(tx, ty))
c.x, c.y = (tx + 1) * TILE_SIZE + 16, ty * TILE_SIZE + 16
c.job = {"type": "harvest", "tx": tx, "ty": ty}; c.work_progress = 0
for _ in range(60 * 60):
    g._world_step()
    if g.world.tiles[ty][tx] != T_METEOR: break
check("C3 采完得到粗铁和石头", amount(g, "iron_ore") >= 4 and amount(g, "stone") >= 3, (amount(g, "iron_ore"), amount(g, "stone")))
# 定时器触发
g = mk(6); g.meteor_timer = 0.01
for _ in range(5): g._world_step()
check("C3 定时器到点触发事件", g.meteors_spawned == 1)
# 无镐不能采
g = mk(5); g._spawn_meteor()
tx, ty = next((x, y) for y in range(MAP_HEIGHT) for x in range(MAP_WIDTH) if g.world.tiles[y][x] == T_METEOR)
c = g.colonists[0]; c.tool_key = None
c.x, c.y = (tx + 1) * TILE_SIZE + 16, ty * TILE_SIZE + 16
c.job = {"type": "harvest", "tx": tx, "ty": ty}
for _ in range(120): g._world_step()
check("C3 没有镐采不了陨石", g.world.tiles[ty][tx] == T_METEOR)

# C4
g = mk(); c = g.colonists[0]
species_seen = {a.species for a in g.animals}
check("C4 初始动物≥35 且至少 4 个物种", len(g.animals) >= 35 and len(species_seen) >= 4, (len(g.animals), species_seen))
for sp in SPECIES:
    g = mk(); g.animals.clear(); c = g.colonists[0]; tx, ty = c.current_tile()
    pos = next((tx + dx, ty + dy) for dx, dy in ((3, 0), (0, 3), (-3, 0), (0, -3)) if g.world.is_walkable(tx + dx, ty + dy))
    a = Animal(*pos, sp, ctx=g.ctx); g.animals.append(a); a.speed = 0
    c.weapon_key = "longsword"; c.equip_weapon("longsword"); c.hp = 1000
    c.enqueue_command({"type": "hunt", "animal": a})
    t = run_until(g, lambda: a.hp <= 0, 3000)
    ok = t is not None and amount(g, "meat") >= SPECIES[sp]["meat"] and all(amount(g, k) >= v for k, v in SPECIES[sp].get("extra", {}).items())
    check(f"C4 {SPECIES[sp]['name']} 可狩猎并掉落正确", ok, (t, amount(g, "meat")))
g = mk(); g.animals.clear(); c = g.colonists[0]; tx, ty = c.current_tile(); c.hp = 100
bx, by = next((tx + dx, ty + dy) for dx, dy in ((2, 0), (0, 2), (-2, 0), (0, -2), (2, 1)) if g.world.is_walkable(tx + dx, ty + dy))
b = Animal(bx, by, "boar", ctx=g.ctx); g.animals.append(b); b.take_damage(1)
for _ in range(180): g._world_step()
check("C4 野猪被打后反击（小人掉血）", c.hp < 100, c.hp)

# C5
t0 = time.time(); g = mk(3); t_init = time.time() - t0
n_iron = sum(r.count(T_IRON_ROCK) for r in g.world.tiles); n_rock = sum(r.count(T_ROCK) for r in g.world.tiles)
check("C5 地图尺寸 ≥ 160x120", MAP_WIDTH >= 160 and MAP_HEIGHT >= 120 and g.world.cols == MAP_WIDTH)
check("C5 铁矿和石头数量合理", n_iron >= 40 and n_rock >= 800, (n_iron, n_rock))
check("C5 初始化 < 8 秒", t_init < 8, round(t_init, 2))
check("C5 小人出生点可走", all(g.world.is_walkable(*c.current_tile()) for c in g.colonists))
print("FAILS:", FAILS); sys.exit(1 if FAILS else 0)
