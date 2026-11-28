# tools/texture_test.py
"""贴图验收：
  X1 覆盖：每种物品/建筑(含材质、朝向)/动物/作物阶段/地形 都有对应 PNG，且建筑贴图尺寸 = 占地格数×32
  X2 贴图路径能跑通：开启贴图后画一帧完整游戏（地形、物品、动物、小人、敌人、建筑、农田），不报错且确实用了贴图
  X3 回退：关闭贴图后同样能画
用法： python -m tools.texture_test
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools import fake_pygame
pygame = fake_pygame.install(textures=True)
from core import textures
from world.game_world import GameWorld
from world.buildings import BUILDING_DEFS, Building
from world.items import ITEM_DEFS
from entities.animal import SPECIES, Animal
from entities.enemy import Enemy
from settings import TILE_SIZE
FAILS = []
def check(n, ok, info=""):
    print(("  ✓ " if ok else "  ✗ ") + n + (f"  {info}" if info and not ok else ""))
    if not ok: FAILS.append(n)

# X1 覆盖
miss = [k for k in ITEM_DEFS if textures.get("item_" + k) is None]
check("X1 所有物品都有图标", not miss, miss)
miss = [s for s in SPECIES if textures.get("animal_" + s) is None]
check("X1 所有动物都有贴图", not miss, miss)
bad = []
for kind, d in BUILDING_DEFS.items():
    for mat in d["variants"]:
        for rot in (0, 1):
            b = Building(kind, mat, 0, 0, rotation=rot)
            if textures.building(b) is None: bad.append((kind, mat, rot))
check("X1 所有建筑(材质×朝向)贴图齐全且尺寸正确", not bad, bad)
need = ["grass_0", "grass_3", "dirt_0", "dirt_1", "water_0", "water_1", "rock", "iron_rock", "meteor", "tree_0", "tree_2", "berry",
        "colonist_male_body", "colonist_female_body", "colonist_male_head_2", "colonist_female_head_2", "enemy_male_body",
        "enemy_female_body", "enemy_male_head_0", "enemy_female_head_0", "plant_berry_0", "plant_berry_2", "plant_berry_ripe",
        "plant_tree_0", "plant_tree_2", "plant_tree_ripe"]
miss = [n for n in need if textures.get(n) is None]
check("X1 地形/小人/作物贴图齐全", not miss, miss)
check("X1 草地等大块地面贴图是 32×32", all(textures.get(n).get_size() == (32, 32) for n in ("grass_0", "dirt_0", "water_0", "rock", "tree_0")))

# X2 开启贴图画一帧
f = pygame.font.Font(None, 16)
def frame(label):
    g = GameWorld(f, f, f, f, 1280, 720, seed=3); g.set_screen_size(1280, 720)
    tx, ty = g.colonists[0].current_tile()
    for i, (k, m) in enumerate((("bed", "wood"), ("stove", "stone"), ("furnace", "stone"), ("workbench", "wood"),
                                ("wall", "stone"), ("door", "iron"), ("fountain", "stone"), ("floor", "wool"))):
        b = Building(k, m, tx + 3 + i * 3, ty + 4, rotation=i % 2); g.buildings.buildings[(b.tx, b.ty, b.layer)] = b
        if k == "stove": b.cook_queue = [1]; b.cook_progress = 40
        if k == "furnace": b.smelt_queue = [1]; b.smelt_progress = 40
    g.buildings.add_blueprint("bed", "wood", tx, ty + 8)
    for i, kind in enumerate(("wood", "meat", "crossbow", "meal_fine")):
        g.items.add(kind, 5, tx + i, ty + 2)
    g.animals.clear()
    for i, sp in enumerate(SPECIES):
        g.animals.append(Animal(tx + i, ty - 3, sp, ctx=g.ctx))
    g.enemies.append(Enemy(tx + 6, ty - 5, "pistol", ctx=g.ctx))
    g.colonists[0].carrying = {"kind": "wood", "amount": 3}
    g.colonists[0].hit_flash = 0.2
    for pt, y0 in (("berry", ty + 12), ("tree", ty + 14)):
        fz = g.farms.add((tx, y0, tx + 3, y0), pt)
        for i, pl in enumerate(fz.plots.values()):
            pl["planted"] = True; pl["growth"] = (0.1, 0.5, 0.8, 1.0)[i]
    s = pygame.Surface((1280, 720))
    try:
        g.draw(s, 0.016); ok = True; err = ""
    except Exception as ex:                                  # noqa: BLE001
        import traceback; traceback.print_exc(); ok = False; err = repr(ex)
    return g, s, ok, err
g, s, ok, err = frame("tex")
check("X2 开启贴图时能画完整一帧", ok, err)
used = {getattr(src, "path", None) for src, pos in s.blits if getattr(src, "path", None)}
names = {os.path.basename(p)[:-4] for p in used}
check("X2 画面里确实用到了贴图（地形/动物/建筑）",
      any(n.startswith("grass") for n in names) and any(n.startswith("animal_") for n in names)
      and any(n.startswith("bld_") for n in names), sorted(names))
check("X2 农作物各阶段贴图被用到", {"plant_berry_0", "plant_berry_1", "plant_berry_ripe", "plant_tree_0", "plant_tree_1", "plant_tree_2", "plant_tree_ripe"} <= names, sorted(n for n in names if n.startswith("plant")))
check("X2 物品图标、小人/敌人贴图也被用到",
      any(v is not None for v in textures._icon_cache.values()) and
      {"colonist", "enemy"} <= {k[0].split("_")[0] for k, v in textures._person_cache.items() if v is not None},
      (list(textures._icon_cache)[:3], list(textures._person_cache)[:3]))
# X3 回退
textures.ENABLED = False; textures.clear()
g, s, ok, err = frame("fallback")
check("X3 关闭贴图后回退到程序化画法也能画", ok, err)
print("FAILS:", FAILS); sys.exit(1 if FAILS else 0)
