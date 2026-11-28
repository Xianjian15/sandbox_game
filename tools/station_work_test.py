# tools/station_work_test.py
"""工作站"端到端"验收：真实世界里下指令 → 小人自己搬材料、加工 → 产物出现。
  W1 烹饪台   备好食材 + 队列 1 份简单食物 + 小人右键烹饪台 → 烹饪队列清空、出现饭菜（或已被吃掉）
  W2 熔炉     粗铁 2 + 队列 1 → 出现铁
  W3 工作台   石头 2 + 队列石镐 → 出现石镐
  W4 拖框模式 库存区 / 采集 / 狩猎 / 农业：用真实鼠标事件在地图上拖框，指令生效
用法： python -m tools.station_work_test
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
from settings import TILE_SIZE
FAILS = []
def check(n, ok, info=""):
    print(("  ✓ " if ok else "  ✗ ") + n + (f"  {info}" if info and not ok else ""))
    if not ok: FAILS.append(n)

f = pygame.font.Font(None, 16)
def mk(seed=11):
    g = GameWorld(f, f, f, f, 1280, 720, seed=seed); g.set_screen_size(1280, 720); return g
def amount(g, kind):
    return sum(st.amount for st in g.items.stacks.values() if st.kind == kind)
def run_until(g, cond, ticks=9000):
    for t in range(ticks):
        g.sim_step()
        if cond(): return t
    return None

# W1
g = mk(); b = D._place(g, "stove", "stone", 3, 1)
D._stock(g, "meat", 1); D._stock(g, "food", 1)
b.cook_queue = [{"meal": "meal_simple"}]
D._rclick(g, b)
t = run_until(g, lambda: not b.cook_queue and (amount(g, "meal_simple") > 0 or any(c.carrying and c.carrying["kind"] == "meal_simple" for c in g.colonists)))
check("W1 烹饪：队列完成并产出简单食物", t is not None, (b.cook_queue, amount(g, "meal_simple"), dict((k.kind if hasattr(k,'kind') else k, v.amount) for k, v in g.items.stacks.items())))

# W2
g = mk(); b = D._place(g, "furnace", "stone", 2, 2)
D._stock(g, "iron_ore", 2); b.smelt_queue = [{"item": "iron"}]
D._rclick(g, b)
t = run_until(g, lambda: amount(g, "iron") > 0 or any(c.carrying and c.carrying["kind"] == "iron" for c in g.colonists), 12000)
check("W2 熔炉：粗铁炼成铁", t is not None, (b.smelt_queue, b.inventory))

# W3
g = mk(); b = D._place(g, "workbench", "wood", 2, 1)
D._stock(g, "stone", 2); b.craft_queue = [{"item": "stone_pickaxe"}]
D._rclick(g, b)
t = run_until(g, lambda: amount(g, "stone_pickaxe") > 0 or any(c.weapon_key == "stone_pickaxe" or getattr(c, "tool_key", None) == "stone_pickaxe" for c in g.colonists), 12000)
check("W3 工作台：做出石镐", t is not None, (b.craft_queue, b.inventory, amount(g, "stone")))

# W4 拖框
def ev(g, t, **kw): g.handle_event(pygame.event.Event(t, **kw), 1280, 720)
def drag(g, t1, t2):
    p1 = g.camera.world_to_screen(t1[0] * TILE_SIZE + 4, t1[1] * TILE_SIZE + 4)
    p2 = g.camera.world_to_screen(t2[0] * TILE_SIZE + 4, t2[1] * TILE_SIZE + 4)
    p1 = (int(p1[0]), int(p1[1])); p2 = (int(p2[0]), int(p2[1]))
    pygame.mouse.get_pos = lambda: p1
    ev(g, pygame.MOUSEBUTTONDOWN, pos=p1, button=1)
    pygame.mouse.get_pos = lambda: p2
    ev(g, pygame.MOUSEMOTION, pos=p2, rel=(0, 0), buttons=(1, 0, 0))
    ev(g, pygame.MOUSEBUTTONUP, pos=p2, button=1)
g = mk(); cx, cy = g.colonists[0].current_tile()
g.camera.x, g.camera.y = cx * TILE_SIZE - 600, cy * TILE_SIZE - 300; g.camera._clamp()
cmds = []; orig = g.issue; g.issue = lambda c: (cmds.append(c), orig(c))[1]
def kinds(): return [c.get("t", c.get("type")) for c in cmds]
g.mode = "stockpile"; drag(g, (cx + 2, cy + 2), (cx + 4, cy + 4)); g.sim_step()
check("W4a 库存区：拖框创建", "stockpile_add" in kinds() and len(g.stockpiles.stockpiles) >= 1, kinds())
g.mode = "harvest_area"; drag(g, (cx - 8, cy - 8), (cx + 8, cy + 8)); g.sim_step()
check("W4b 采集区：拖框划定，留在模式里可继续划", "zone_set" in kinds() and g.mode == "harvest_area" and g.zones.count("harvest") > 100, (kinds(), g.mode))
g.mode = "hunt_area"; drag(g, (cx - 8, cy - 8), (cx + 8, cy + 8)); g.sim_step()
check("W4c 狩猎区：拖框划定，留在模式里", g.mode == "hunt_area" and g.zones.count("hunt") > 100, (kinds(), g.mode))
g.research_mgr.completed.add("agriculture")
g.mode = "farm"; drag(g, (cx + 6, cy + 6), (cx + 8, cy + 8))
check("W4d 农业：拖框后出现种类选择", g.pending_farm_rect is not None)
# W5 建造：build_area 指令 → 蓝图 → 小人右键 → 建成
g = mk(); cx, cy = g.colonists[0].current_tile()
D._stock(g, "wood", 20)
from core import commands as cmdlib
pos = D._free_area(g, 3, 1)
g.issue(cmdlib.make("build_area", kind="floor", mat="wood", rot=0, x1=pos[0], y1=pos[1], x2=pos[0] + 1, y2=pos[1]))
g.sim_step(); g.sim_step()
bps = g.buildings.get_blueprints_at(*pos)
check("W5a 建造：生成蓝图", bool(bps), pos)
c = g.colonists[0]; c.selected = True
sx, sy = g.camera.world_to_screen(pos[0] * TILE_SIZE + TILE_SIZE // 2, pos[1] * TILE_SIZE + TILE_SIZE // 2)
g.camera.x, g.camera.y = pos[0] * TILE_SIZE - 600, pos[1] * TILE_SIZE - 300; g.camera._clamp()
sx, sy = g.camera.world_to_screen(pos[0] * TILE_SIZE + TILE_SIZE // 2, pos[1] * TILE_SIZE + TILE_SIZE // 2)
g._handle_right_click((sx, sy), False)
t = run_until(g, lambda: g.buildings.get_building_at(*pos) is not None, 9000)
check("W5b 建造：小人把蓝图建成建筑", t is not None, (pos, amount(g, "wood")))
print("FAILS:", FAILS); sys.exit(1 if FAILS else 0)
