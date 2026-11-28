# tools/pack_test.py
"""v0.12.0 内容包验收：纺织科技/地毯/软床、花盆/雕像美观度、猎弓、兽群迁徙、后期敌人。
用法： python -m tools.pack_test
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
from world.buildings import BUILDING_DEFS
from entities.enemy import Enemy
from entities.animal import Animal
from combat.weapons import WEAPONS, CRAFT_COST
FAILS = []
def check(n, ok, info=""):
    print(("  ✓ " if ok else "  ✗ ") + n + (f"  {info}" if info and not ok else ""))
    if not ok: FAILS.append(n)
f = pygame.font.Font(None, 16)
def mk(seed=11):
    g = GameWorld(f, f, f, f, 1280, 720, seed=seed); g.set_screen_size(1280, 720); g.animals.clear(); return g
def amount(g, kind): return sum(st.amount for st in g.items.stacks.values() if st.kind == kind)

# P1 科技门槛
g = mk(); rm = g.research_mgr
check("P1 纺织前：地毯/软床不可建", not rm.is_unlocked("floor", "wool") and not rm.is_unlocked("bed", "feather"))
rm.completed.add("tailoring")
check("P1 纺织后：地毯/软床可建", rm.is_unlocked("floor", "wool") and rm.is_unlocked("bed", "feather"))
check("P1 羊毛/羽毛都有物品定义", all(k in __import__("world.items", fromlist=["ITEM_DEFS"]).ITEM_DEFS for k in ("wool", "feather", "leather")))
check("P1 新建筑都在建筑表里", {"flower_pot", "statue"} <= set(BUILDING_DEFS))

# P2 软床恢复更快
def rest_gain(variant):
    g = mk(); g.research_mgr.completed.add("tailoring")
    b = D._place(g, "bed", variant, 3, 2); c = g.colonists[0]
    c.x, c.y = (b.tx + 0.5) * 32, (b.ty + 0.5) * 32; c.rest = 10; c.state = "sleeping"; c.path = []
    r0 = c.rest
    for _ in range(60): g._world_step()
    return c.rest - r0
a, b_ = rest_gain("wood"), rest_gain("feather")
check("P2 羽绒软床睡眠恢复快约 50%", b_ > a * 1.3, (a, b_))

# P3 美观度
for kind, mat in (("flower_pot", "wood"), ("statue", "stone"), ("floor", "wool")):
    g2 = mk(); g2.research_mgr.completed.update({"stone_masonry", "tailoring"})
    bld = D._place(g2, kind, mat, 1, 1)
    ts = [(bld.tx, bld.ty)] if bld else []
    b0 = g2.room_mgr._calc_beauty([(bld.tx + 50, bld.ty)]) if bld else 0
    b1 = g2.room_mgr._calc_beauty(ts) if bld else 0
    check(f"P3 {kind}/{mat} 提高美观度", bld is not None and b1 > b0, (b0, b1))

# P4 猎弓
g = mk(); b = D._place(g, "workbench", "wood", 2, 1)
D._stock(g, "wood", 3); D._stock(g, "leather", 2)
b.craft_queue = [{"item": "bow"}]; D._rclick(g, b)
ok = False
for t in range(12000):
    g.sim_step()
    if g.colonists[0].weapon_key == "bow": ok = True; break
check("P4 猎弓：3 木 2 皮革制作并装备", ok and CRAFT_COST["bow"] == {"wood": 3, "leather": 2}, t)
g = mk(); c = g.colonists[0]; c.equip_weapon("bow"); tx, ty = c.current_tile()
pos = next((tx + dx, ty + dy) for dx, dy in ((6, 0), (0, 6), (-6, 0), (0, -6)) if g.world.is_walkable(tx + dx, ty + dy))
a = Animal(*pos, "rabbit", ctx=g.ctx); a.speed = 0; g.animals.append(a)
c.rest = c.satiety = 100; c.enqueue_command({"type": "hunt", "animal": a})
t = None
for i in range(1800):
    g.sim_step()
    if a.hp <= 0: t = i; break
check("P4 用猎弓能打死兔子", t is not None and amount(g, "meat") >= 3, t)

# P5 兽群迁徙
g = mk(5); n0 = len(g.animals); g._spawn_herd()
check("P5 兽群迁徙：出现 5~8 只同种动物", 5 <= len(g.animals) - n0 <= 8 and g.herds_spawned == 1, len(g.animals) - n0)
check("P5 同一群是同一物种", len({x.species for x in g.animals[n0:]}) == 1)
g = mk(6); g.herd_timer = 0.01
for _ in range(5): g._world_step()
check("P5 定时器到点触发", g.herds_spawned == 1)

# P6 后期敌人
from world.game_world import GameWorld as GW
check("P6 波次武器表都存在于武器表", all(k in WEAPONS for pool in GW.WAVE_WEAPONS for k in pool) and len(GW.WAVE_WEAPONS) >= 10)
for wk in ("machete", "war_hammer", "shotgun", "smg", "sniper"):
    g = mk(); c = g.colonists[0]; c.hp = c.max_hp = 100000; tx, ty = c.current_tile()
    pos = next((tx + dx, ty + dy) for dx, dy in ((5, 0), (0, 5), (-5, 0), (0, -5)) if g.world.is_walkable(tx + dx, ty + dy))
    e = Enemy(*pos, wk, ctx=g.ctx); g.enemies.append(e)
    try:
        for _ in range(600): g.sim_step()
        ok = True
    except Exception as ex:                       # noqa: BLE001
        ok = False; print("   异常:", repr(ex))
    check(f"P6 持 {WEAPONS[wk]['name']} 的敌人能正常战斗（无异常）并伤到小人", ok and c.hp < 100000, c.hp)
print("FAILS:", FAILS); sys.exit(1 if FAILS else 0)
