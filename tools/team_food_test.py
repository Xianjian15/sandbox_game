# tools/team_food_test.py
"""v0.10.0 验收：工作站多人规则 / 食物营养 / 新铁器与枪械。
  K1 研究台 单人模式：两人下令 → 只有 1 人在岗；协作模式 → 两人都在岗，研究进度≈2 倍
  K2 工作台 协作模式：两人共同做同一件，材料只扣一份，成品只出一件，用时更短
  K3 协作人数上限生效（上限 2，三人下令 → 在岗 ≤2）
  K4 小人死亡/放手后从在岗名单移除
  F1 食物营养：浆果 < 生肉 < 简单食物 < 美味食物，吃下去恢复的数值等于物品表
  F2 地上同时有生肉和美味食物：先吃营养最高的；不再有"吃什么都 +64"的固定增益
  W1 新铁器/枪械：配方、科技门槛、制作完成并装备；霰弹枪能打伤敌人
用法： python -m tools.team_food_test
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
from world.items import ITEM_DEFS
from entities.enemy import Enemy
from combat.weapons import WEAPONS, CRAFT_COST, CRAFT_GROUPS
from core import commands as cmdlib
FAILS = []
def check(n, ok, info=""):
    print(("  ✓ " if ok else "  ✗ ") + n + (f"  {info}" if info and not ok else ""))
    if not ok: FAILS.append(n)
f = pygame.font.Font(None, 16)
def mk(seed=11):
    g = GameWorld(f, f, f, f, 1280, 720, seed=seed); g.set_screen_size(1280, 720)
    g.animals.clear()
    return g
def amount(g, kind): return sum(st.amount for st in g.items.stacks.values() if st.kind == kind)
def add_colonists(g, n):
    from entities.colonist import Colonist
    while len(g.colonists) < n:
        c0 = g.colonists[0]; tx, ty = c0.current_tile()
        pos = next((tx + dx, ty + dy) for dx in range(-3, 4) for dy in range(-3, 4)
                   if g.world.is_walkable(tx + dx, ty + dy) and all(c.current_tile() != (tx + dx, ty + dy) for c in g.colonists))
        c = Colonist(*pos, weapon_key="fist", ctx=g.ctx); c.owner_id = 0; g.colonists.append(c)
    for c in g.colonists: c.selected = True; c.rest = c.satiety = 100
def station_cmd(g, b, kind):
    g.issue(cmdlib.make("station", ids=[c.id for c in g.colonists], kind=kind, tx=b.tx, ty=b.ty, q=False))

# K1 研究台
def research_progress(team):
    g = mk(); add_colonists(g, 2)
    b = D._place(g, "research_bench", "wood", 3, 1); b.team = team
    g.research_mgr.set_research("agriculture")
    station_cmd(g, b, "research")
    n_workers = None
    for t in range(900):
        g.sim_step()
        if t == 600: n_workers = len(b.workers)
    return n_workers, g.research_mgr.progress + (80.0 if "agriculture" in g.research_mgr.completed else 0)
w1, p1 = research_progress(False); w2, p2 = research_progress(True)
check("K1 单人模式只有 1 人在岗", w1 == 1, w1)
check("K1 协作模式 2 人在岗", w2 == 2, w2)
check("K1 协作研究进度明显更快（≥1.6 倍）", p2 >= p1 * 1.6, (p1, p2))

# K2 工作台
def craft_run(team):
    g = mk(); add_colonists(g, 2)
    b = D._place(g, "workbench", "wood", 3, 1); b.team = team
    D._stock(g, "stone", 4); b.craft_queue = [{"item": "stone_hammer"}]
    station_cmd(g, b, "craft")
    done_t = None
    for t in range(9000):
        g.sim_step()
        if not b.craft_queue and done_t is None: done_t = t
        if done_t is not None and t > done_t + 200: break
    got = amount(g, "stone_hammer") + sum(1 for c in g.colonists if c.weapon_key == "stone_hammer")
    return done_t, got, amount(g, "stone") + b.delivered_materials.get("stone", 0) + sum((c.carrying or {}).get("amount", 0) for c in g.colonists if c.carrying and c.carrying["kind"] == "stone")
t_solo, got_solo, left_solo = craft_run(False)
t_team, got_team, left_team = craft_run(True)
check("K2 单人模式做出 1 件", t_solo is not None and got_solo == 1, (t_solo, got_solo))
check("K2 协作模式做出 1 件且材料没有多扣", t_team is not None and got_team == 1 and left_team == 0, (t_team, got_team, left_team))
check("K2 协作比单人更快", t_solo is not None and t_team is not None and t_team < t_solo, (t_solo, t_team))

# K3 / K4
g = mk(); add_colonists(g, 3)
b = D._place(g, "research_bench", "wood", 3, 1); b.team = True; b.team_cap = 2
g.research_mgr.set_research("agriculture"); station_cmd(g, b, "research")
for _ in range(300): g.sim_step()
check("K3 上限 2：三人下令只有 2 人在岗", len(b.workers) == 2, b.workers)
victim = next(c for c in g.colonists if c.id in b.workers)
victim.hp = 0
for _ in range(5): g.sim_step()
check("K4 在岗小人死亡后从名单移除", victim.id not in b.workers, b.workers)
g.issue(cmdlib.make("bld_station_mode", team=False, cap=2, tx=b.tx, ty=b.ty))
check("K4 切换模式指令生效", b.team is False)

# F1
g = mk(); c = g.colonists[0]
vals = []
for k in ("food", "meat", "meal_simple", "meal_fine"):
    c.satiety = 0; c.mood = 50; c._apply_food_effect(k); vals.append(round(c.satiety))
check("F1 营养递增且等于物品表", vals == sorted(vals) and len(set(vals)) == 4 and vals == [min(100, ITEM_DEFS[k]["nutrition"]) for k in ("food", "meat", "meal_simple", "meal_fine")], vals)

# F2
g = mk(); c = g.colonists[0]; tx, ty = c.current_tile()
c.satiety = 30; g.items.add("meat", 1, tx, ty); g.items.add("meal_fine", 1, tx, ty)
for _ in range(240): g.sim_step()
check("F2 先吃了美味食物，生肉留着（够饱了）", amount(g, "meal_fine") == 0 and amount(g, "meat") == 1, (amount(g, "meal_fine"), amount(g, "meat")))
g = mk(); c = g.colonists[0]; tx, ty = c.current_tile()
c.satiety = 20; g.items.add("food", 1, tx, ty)
for _ in range(30): g.sim_step()
check("F2 只吃 1 个浆果只恢复一点点（没有固定 +64）", c.satiety < 50, c.satiety)

# W1
names = [k for _, _, ks in CRAFT_GROUPS for k in ks]
check("W1 新武器都有配方和数值", all(k in CRAFT_COST and k in WEAPONS for k in names) and {"dagger", "iron_spear", "machete", "war_hammer", "shotgun", "smg", "sniper"} <= set(names))
g = mk(); b = D._place(g, "workbench", "wood", 2, 1); g.research_mgr.completed.update({"stone_masonry", "smelting", "crafting", "gunsmithing"})
g.selected_building = b
_s = pygame.Surface((g.ui_w, g.ui_h)); g._draw_ui(_s, g.ui_w, g.ui_h)
keys = set(g.bhud.btn_rects)
check("W1 未研究高级枪械时霰弹枪按钮不可点", "craft:shotgun" not in keys and "craft:pistol" in keys, sorted(keys))
for item in ("dagger", "shotgun"):
    g = mk(); b = D._place(g, "workbench", "wood", 2, 1)
    for k, v in CRAFT_COST[item].items(): D._stock(g, k, v)
    b.craft_queue = [{"item": item}]
    D._rclick(g, b)
    ok = False
    for t in range(12000):
        g.sim_step()
        if g.colonists[0].weapon_key == item: ok = True; break
    check(f"W1 {WEAPONS[item]['name']} 制作完成并装备", ok, (b.craft_queue, [c.weapon_key for c in g.colonists]))
g = mk(); c = g.colonists[0]; c.equip_weapon("shotgun"); c.hp = 500
tx, ty = c.current_tile()
pos = next((tx + dx, ty + dy) for dx, dy in ((4, 0), (0, 4), (-4, 0), (0, -4)) if g.world.is_walkable(tx + dx, ty + dy))
e = Enemy(*pos, "fist", ctx=g.ctx); e.hp = e.max_hp = 200; g.enemies.append(e)
c.assign_attack(e)
for _ in range(400): g.sim_step()
check("W1 霰弹枪能打伤敌人", e.hp < 200, e.hp)
print("FAILS:", FAILS); sys.exit(1 if FAILS else 0)
