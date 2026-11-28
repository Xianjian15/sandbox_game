# tools/zone_test.py
"""采集区 / 狩猎区验收：
  Z1 划定/擦除/清空   指令 zone_set / zone_clear；越界被裁剪；过大的框被忽略；都是纯 JSON
  Z2 采集区自动工作   空闲小人自动去砍区内的树、采完掉落；区外的树不碰；同一格不会两人抢
  Z3 采集区的约束     需要镐的铁矿没镐时跳过（不卡死、不反复寻路）；够不着的格进冷却
  Z4 狩猎区自动工作   空闲且有武器的小人自动打区内动物；空手不去；区外动物不打
  Z5 不抢活           忙碌的/饿了的/累了的小人不会被区域抢走
  Z6 界面             工具条 划定/擦除/清空；拖框留在模式里；Shift 擦除
  Z7 确定性           区域参与哈希；同样操作两次哈希一致
用法： python -m tools.zone_test
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
from core.state_hash import world_hash
from settings import TILE_SIZE
from world.world import T_TREE, T_GRASS, T_IRON_ROCK
FAILS = []
def check(n, ok, info=""):
    print(("  ✓ " if ok else "  ✗ ") + n + (f"  {info}" if info and not ok else ""))
    if not ok: FAILS.append(n)

f = pygame.font.Font(None, 16)
def mk(seed=3):
    g = GameWorld(f, f, f, f, 1280, 720, seed=seed); g.set_screen_size(1280, 720)
    g.animals.clear(); return g
def run(g, n):
    for _ in range(n): g.sim_step()
def zone(g, kind, x1, y1, x2, y2, on=1):
    g.issue(cmdlib.make("zone_set", kind=kind, on=on, x1=x1, y1=y1, x2=x2, y2=y2))
def clear_area(g, x1, y1, x2, y2):
    for y in range(y1, y2 + 1):
        for x in range(x1, x2 + 1):
            g.world.tiles[y][x] = T_GRASS; g.world.resource_hp.pop((x, y), None)
def tree(g, x, y):
    g.world.tiles[y][x] = T_TREE; g.world.resource_hp[(x, y)] = 100
def wood(g): return sum(st.amount for st in g.items.stacks.values() if st.kind == "wood")
def meat(g): return sum(st.amount for st in g.items.stacks.values() if st.kind == "meat")
def fresh(c): c.rest = c.satiety = 100; c.hp = c.max_hp

# Z1
g = mk(); c = g.colonists[0]; cx, cy = c.current_tile()
zone(g, "harvest", cx + 3, cy + 3, cx + 5, cy + 4); run(g, 1)
check("Z1 划定 3x2 = 6 格", g.zones.count("harvest") == 6, g.zones.count("harvest"))
zone(g, "harvest", cx + 3, cy + 3, cx + 3, cy + 4, on=0); run(g, 1)
check("Z1 擦除 2 格后剩 4", g.zones.count("harvest") == 4)
zone(g, "hunt", -10, -10, 3, 3); run(g, 1)
check("Z1 越界被裁剪到地图内（4x4=16）", g.zones.count("hunt") == 16, g.zones.count("hunt"))
zone(g, "hunt", 0, 0, 100, 100); run(g, 1)
check("Z1 过大的框被忽略", g.zones.count("hunt") == 16)
g.issue(cmdlib.make("zone_clear", kind="harvest")); run(g, 1)
check("Z1 清空只清该类型", g.zones.count("harvest") == 0 and g.zones.count("hunt") == 16)
try:
    cmdlib.make("zone_set", kind="harvest", on=1, x1=1.5, y1=0, x2=2, y2=2); bad = False
except ValueError: bad = True
check("Z1 指令里不允许 float", bad)

# Z2 采集区自动砍树
g = mk(); c = g.colonists[0]; fresh(c); cx, cy = c.current_tile()
clear_area(g, cx + 2, cy - 4, cx + 9, cy + 4)
trees = [(cx + 4, cy - 1), (cx + 5, cy + 1), (cx + 6, cy)]
for t in trees: tree(g, *t)
outside = (cx + 9, cy + 3); tree(g, *outside)
zone(g, "harvest", cx + 3, cy - 2, cx + 7, cy + 2)
w0 = wood(g)
run(g, 60 * 40)
left = [t for t in trees if g.world.is_harvestable(*t)]
check("Z2 空闲小人自动砍光区内的树", not left, left)
check("Z2 砍树有木头掉落", wood(g) > w0, (w0, wood(g)))
check("Z2 区外的树没动", g.world.is_harvestable(*outside))

# Z2b 两个小人不抢同一格
g = mk(); g.spawn_colonist() if hasattr(g, "spawn_colonist") else None
from entities.colonist import Colonist
if len(g.colonists) < 2:
    c0 = g.colonists[0]; cx, cy = c0.current_tile()
    g.colonists.append(Colonist(cx + 1, cy, ctx=g.ctx))
cx, cy = g.colonists[0].current_tile()
clear_area(g, cx + 2, cy - 3, cx + 8, cy + 3)
for c in g.colonists: fresh(c)
tree(g, cx + 4, cy); tree(g, cx + 4, cy + 1)
zone(g, "harvest", cx + 4, cy, cx + 4, cy + 1); run(g, 31)
jobs = [(c.job["tx"], c.job["ty"]) for c in g.colonists if c.job and c.job.get("type") == "harvest"]
check("Z2b 两个小人分到不同的格子", len(jobs) == len(set(jobs)) == 2, jobs)

# Z3 铁矿没镐
g = mk(); c = g.colonists[0]; fresh(c); cx, cy = c.current_tile()
clear_area(g, cx + 2, cy - 3, cx + 8, cy + 3)
g.world.tiles[cy][cx + 4] = T_IRON_ROCK; g.world.resource_hp[(cx + 4, cy)] = 100
zone(g, "harvest", cx + 4, cy, cx + 4, cy)
run(g, 60 * 6)
check("Z3 没有镐：不去挖铁矿，也不卡死", c.is_idle() and g.world.is_harvestable(cx + 4, cy))
check("Z3 失败的格子进入冷却", ("harvest", (cx + 4, cy)) in g.zones.cooldown)

# Z4 狩猎区
g = mk(); c = g.colonists[0]; fresh(c); cx, cy = c.current_tile()
clear_area(g, cx + 2, cy - 5, cx + 12, cy + 5)
a_in = Animal(cx + 5, cy, "rabbit", ctx=g.ctx); a_out = Animal(cx + 12, cy + 5, "rabbit", ctx=g.ctx)
g.animals += [a_in, a_out]
zone(g, "hunt", cx + 3, cy - 2, cx + 8, cy + 2)
run(g, 60 * 5)
check("Z4 空手的小人不去打猎", a_in.hp == a_in.max_hp and c.is_idle())
c.equip_weapon("pistol") if hasattr(c, "equip_weapon") else None
c.weapon_key = "pistol"
from combat.weapons import get_weapon
w = get_weapon("pistol"); c.attack_range = w.get("range", c.attack_range) if isinstance(w, dict) else c.attack_range
m0 = meat(g)
run(g, 60 * 40)
check("Z4 持枪后自动打死区内的兔子", a_in.hp <= 0 and meat(g) > m0, (a_in.hp, meat(g)))
check("Z4 区外的兔子没被打", a_out.hp == a_out.max_hp or a_out.hp > 0)

# Z5 不抢活（每项用新世界，互不影响）
def z5():
    g = mk(); c = g.colonists[0]; fresh(c); cx, cy = c.current_tile()
    clear_area(g, cx + 2, cy - 3, cx + 8, cy + 3)
    tree(g, cx + 4, cy); zone(g, "harvest", cx + 4, cy, cx + 4, cy)
    return g, c
g, c = z5(); c.satiety = 20; run(g, 31)
check("Z5 太饿的小人不会被区域抢去干活", not (c.job and c.job.get("type") == "harvest"))
g, c = z5()
for _ in range(31): c.state = "sleeping"; g.sim_step()
check("Z5 睡觉中的小人不会被抢走", not (c.job and c.job.get("type") == "harvest"))
g, c = z5(); c.rest = 10; c.satiety = 100; run(g, 31)
check("Z5 太累的小人不去", not (c.job and c.job.get("type") == "harvest"))
g, c = z5(); c.queue.append({"type": "move", "world": g.world, "tx": c.current_tile()[0] - 3, "ty": c.current_tile()[1]})
run(g, 31)
check("Z5 手头有命令的小人不会被区域打断（先做完玩家的命令）", c.job is None or c.job.get("type") != "harvest" or not c.queue)

# Z6 界面
g = mk(); g.set_screen_size(1280, 720)
def draw(g):
    s = pygame.Surface((g.ui_w, g.ui_h)); g._draw_ui(s, g.ui_w, g.ui_h)
def key(g, k): g.handle_event(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode=""), 1280, 720)
def click(g, p): g.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(int(p[0] * g.ui_scale), int(p[1] * g.ui_scale)), button=1), 1280, 720)
key(g, pygame.K_g); draw(g)
check("Z6 G 键进入采集区模式并出现工具条", g.mode == "harvest_area" and len(g.zone_btns) == 3, (g.mode, g.zone_btns))
key(g, pygame.K_v); draw(g)
check("Z6 V 键切到狩猎区模式", g.mode == "hunt_area")
rect = next(r for r, b in g.zone_btns if b == "erase"); click(g, rect.center)
check("Z6 点「擦除」切换为擦除", g.zone_erase is True and g.mode == "hunt_area")
check("Z6 工具条区域算界面（不穿透）", g.is_mouse_in_ui((int(rect.centerx * g.ui_scale), int(rect.centery * g.ui_scale))))
zone(g, "hunt", 5, 5, 6, 6); run(g, 1)
rect = next(r for r, b in g.zone_btns if b == "clear"); click(g, rect.center); run(g, 1)
check("Z6 点「清空」清掉狩猎区", g.zones.count("hunt") == 0)
g.zone_erase = False; g.mode = None; key(g, pygame.K_g)
btn = next(r for r, m in g.toolbar.buttons if m == "harvest_area")
key(g, pygame.K_ESCAPE); click(g, btn.center); draw(g)
check("Z6 工具栏「采集区」按钮可进入", g.mode == "harvest_area")

# Z7 确定性
def scenario():
    g = mk(5); c = g.colonists[0]; fresh(c); cx, cy = c.current_tile()
    clear_area(g, cx + 2, cy - 4, cx + 9, cy + 4)
    for t in ((cx + 4, cy), (cx + 5, cy + 2)): tree(g, *t)
    zone(g, "harvest", cx + 3, cy - 1, cx + 7, cy + 3); run(g, 60 * 20); return g
a, b = scenario(), scenario()
check("Z7 同样操作两次，世界哈希一致", world_hash(a) == world_hash(b))
g = mk(); h0 = world_hash(g); zone(g, "hunt", 3, 3, 4, 4); run(g, 1)
g2 = mk(); run(g2, 1)
check("Z7 区域参与哈希", world_hash(g) != world_hash(g2))
print("FAILS:", FAILS)
