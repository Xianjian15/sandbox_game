# world/command_exec.py
"""指令执行器：把"纯数据指令"变成对模拟状态的修改。

这是 UI 与模拟之间唯一的通道。联机时两端对同一个 tick 的同一批指令，
用这里完全相同的代码执行，所以结果一致。

约定：
  * 执行器内部可以自由使用对象引用（小人、建筑……），因为它们是从 id/坐标当场解析出来的；
  * 找不到目标（已死亡/已被拆除/id 不存在）一律静默忽略，不报错——联机时延迟到达的指令可能面对已变化的世界；
  * 日志(log)只是界面反馈，不属于模拟状态，可以在这里写。
"""
from world.buildings import BUILDING_DEFS
from world.items import ITEM_DEFS
from systems.research import TECHS

# 装备类物品：默认不允许搬运（需在物品面板打开"允许搬运"）
EQUIP_KINDS = {"stone_pickaxe", "iron_pickaxe", "axe", "longsword",
               "pistol", "rifle", "gun", "club", "spear"}

CABINETS = ("small_cabinet", "large_cabinet")
STATION_KIND = {"craft": "workbench", "research": "research_bench", "cook": "stove", "smelt": "furnace"}
CRAFT_ITEMS = {"stone_pickaxe", "axe", "iron_pickaxe", "longsword", "gun", "pistol", "rifle"}


# ---------------- 辅助 ----------------
def _units(g, ids):
    """按 id 解析出存活小人；顺序固定为 g.colonists 的顺序（与旧的"选中列表"顺序一致）。"""
    idset = set(ids)
    return [c for c in g.colonists if c.id in idset and c.hp > 0]


def _reset(c, clear_targets=True):
    c._release_job()
    c.queue.clear()
    c.state = None
    if clear_targets:
        c.target_enemy = None
        c.target_animal = None


def _building(g, tx, ty, layer=None):
    if layer is not None:
        b = g.buildings.buildings.get((tx, ty, layer))
        if b is not None:
            return b
    return g.buildings.get_building_at(tx, ty)


def _rect(cmd):
    x1, y1, x2, y2 = cmd["x1"], cmd["y1"], cmd["x2"], cmd["y2"]
    return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)


# ---------------- 对小人的命令 ----------------
def _attack(g, cmd):
    sel = _units(g, cmd["ids"])
    e = next((e for e in g.enemies if e.id == cmd["target"] and e.hp > 0), None)
    if not sel or e is None:
        return
    if not cmd["q"]:
        for c in sel: _reset(c)
        for c in sel: c.assign_attack(e)
    else:
        for c in sel: c.enqueue_command({"type": "attack", "enemy": e})


def _hunt(g, cmd):
    sel = _units(g, cmd["ids"])
    a = next((a for a in g.animals if a.id == cmd["target"] and a.hp > 0), None)
    if not sel or a is None:
        return
    if not cmd["q"]:
        for c in sel: _reset(c)
        for c in sel: c.assign_hunt(a)
    else:
        for c in sel: c.enqueue_command({"type": "hunt", "animal": a})


def _station(g, cmd):
    sel = _units(g, cmd["ids"])
    kind = cmd["kind"]
    b = _building(g, cmd["tx"], cmd["ty"])
    if not sel or b is None or b.kind != STATION_KIND.get(kind):
        return
    shift = cmd["q"]
    if kind == "craft":
        if not b.craft_queue:
            g.log.add("工作台没有制作任务：请先点选它，在面板里添加", (255, 200, 100))
            return
        qcmd = {"type": "craft", "world": g.world, "items": g.items,
                "stockpiles": g.stockpiles, "buildings": g.buildings, "bench": b}
        if not shift:
            for c in sel: _reset(c, clear_targets=False)
            sel[0].assign_craft(g.world, g.items, g.stockpiles, g.buildings, b)
        else:
            for c in sel: c.enqueue_command(qcmd)
    elif kind == "research":
        if not g.research_mgr.current_research:
            g.log.add("请先在科技菜单（R）选择研究项目", (255, 200, 100))
            return
        qcmd = {"type": "research", "world": g.world, "buildings": g.buildings,
                "tx": b.tx, "ty": b.ty, "layer": b.layer}
        g._command_station(sel, shift, b, qcmd,
                           lambda c: c.assign_research(g.world, g.buildings, b.tx, b.ty, b.layer),
                           "无法前往研究台（路被堵住了？）")
    elif kind == "cook":
        if not b.cook_queue:
            g.log.add("烹饪台没有任务：请先点选它，在面板里添加", (255, 200, 100))
            return
        qcmd = {"type": "cook", "world": g.world, "items": g.items,
                "stockpiles": g.stockpiles, "buildings": g.buildings, "stove": b}
        g._command_station(sel, shift, b, qcmd,
                           lambda c: c.assign_cook(g.world, g.items, g.stockpiles, g.buildings, b),
                           "无法开始烹饪：库存区/柜子里没有可用食材，或到不了烹饪台")
    elif kind == "smelt":
        if not b.smelt_queue:
            g.log.add("熔炉没有任务：请先点选它，在面板里添加", (255, 200, 100))
            return
        qcmd = {"type": "smelt", "world": g.world, "items": g.items,
                "stockpiles": g.stockpiles, "buildings": g.buildings, "furnace": b}
        g._command_station(sel, shift, b, qcmd,
                           lambda c: c.assign_smelt(g.world, g.items, g.stockpiles, g.buildings, b),
                           "无法开始熔炼：库存区/柜子里没有粗铁，或到不了熔炉")


def _build(g, cmd):
    sel = _units(g, cmd["ids"])
    bps = g.buildings.get_blueprints_at(cmd["tx"], cmd["ty"])
    if not sel or not bps:
        return
    bp = bps[0]
    if bp.reserved_by is not None:
        for c2 in g.colonists:
            if c2.id == bp.reserved_by:
                c2._release_job(); break
        bp.reserved_by = None
    qcmd = {"type": "build", "world": g.world, "buildings": g.buildings,
            "items": g.items, "stockpiles": g.stockpiles, "bp": bp}
    if not cmd["q"]:
        for c in sel: _reset(c)
        sel[0].assign_build(g.world, g.buildings, g.items, g.stockpiles, bp)
    else:
        for c in sel: c.enqueue_command(qcmd)


def _equip(g, cmd):
    sel = _units(g, cmd["ids"])
    tx, ty, kind = cmd["tx"], cmd["ty"], cmd["kind"]
    if not sel or (tx, ty, kind) not in g.items.stacks:
        return
    if not cmd["q"]:
        for c in sel: _reset(c, clear_targets=False)
        sel[0].assign_equip_from_ground(g.world, g.items, tx, ty, kind)
    else:
        qcmd = {"type": "equip_from_ground", "world": g.world, "items": g.items,
                "tx": tx, "ty": ty, "kind": kind}
        for c in sel: c.enqueue_command(qcmd)


def _haul(g, cmd):
    sel = _units(g, cmd["ids"])
    tx, ty, kind = cmd["tx"], cmd["ty"], cmd["kind"]
    stack = g.items.stacks.get((tx, ty, kind))
    if not sel or stack is None:
        return
    if kind in EQUIP_KINDS and not getattr(stack, "allow_haul", False):
        name = ITEM_DEFS.get(kind, {}).get("name", kind)
        g.log.add(f"{name} 未开启“允许搬运”（在物品面板里开关）", (255, 200, 100))
        return
    # 目的地：优先找有空位的柜子，否则库存区空位
    cabinet = None
    seen_b = set()
    for b in g.buildings.buildings.values():
        if id(b) in seen_b: continue
        seen_b.add(id(b))
        if b.kind in CABINETS and not b.marked_for_deconstruction and b.reserved_by is None:
            current_types = len(b.inventory.keys())
            if kind not in b.inventory and current_types >= b.max_types: continue
            space = b.capacity - b.inventory.get(kind, 0)
            if space > 0:
                cabinet = b; break
    target_pos = (0, 0)
    if cabinet:
        target_pos = (cabinet.tx, cabinet.ty)
    else:
        sp_dst = sel[0]._find_dst_slot(g.items, g.stockpiles)
        if sp_dst: target_pos = sp_dst
    if not (cabinet or target_pos != (0, 0)):
        return
    if not cmd["q"]:
        for c in sel: _reset(c, clear_targets=False)
        sel[0].assign_haul(g.world, g.items, g.stockpiles, tx, ty, target_pos[0], target_pos[1],
                           kind, sel[0].carry_limit, cabinet)
    else:
        qcmd = {"type": "haul", "world": g.world, "items": g.items, "stockpiles": g.stockpiles,
                "src": (tx, ty), "dst": target_pos, "kind": kind, "amount": sel[0].carry_limit,
                "cabinet": cabinet}
        for c in sel: c.enqueue_command(qcmd)


def _harvest(g, cmd):
    sel = _units(g, cmd["ids"])
    tx, ty = cmd["tx"], cmd["ty"]
    if not sel or not g.world.is_harvestable(tx, ty):
        return
    if not cmd["q"]:
        for c in sel: _reset(c)
        sel[0].assign_harvest(g.world, tx, ty)
    else:
        for c in sel: c.enqueue_command({"type": "harvest", "world": g.world, "tx": tx, "ty": ty})


def _move(g, cmd):
    sel = _units(g, cmd["ids"])
    tx, ty = cmd["tx"], cmd["ty"]
    if not sel or not g.world.is_walkable(tx, ty):
        return
    offsets = [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)]
    for i, c in enumerate(sel):
        ox, oy = offsets[i % len(offsets)]
        gx, gy = tx + ox, ty + oy
        if not g.world.is_walkable(gx, gy):
            gx, gy = tx, ty
        if not cmd["q"]:
            _reset(c)
            c.move_to(g.world, gx, gy)
        else:
            c.enqueue_command({"type": "move", "world": g.world, "tx": gx, "ty": gy})


def _take(g, cmd):
    cab = _building(g, cmd["tx"], cmd["ty"], cmd.get("layer"))
    if cab is None or cab.kind not in CABINETS:
        return
    sel = _units(g, cmd["ids"])
    candidates = sel if sel else [c for c in g.colonists if c.hp > 0]
    for c in candidates:
        if c.assign_take_from_cabinet(g.world, g.items, g.stockpiles, g.buildings,
                                      cab, cmd["kind"], cmd["amt"]):
            return
    g.log.add("指派取物失败：小人无法到达柜子！", (255, 100, 100))


# ---------------- 区域/设施 ----------------
def _stockpile_add(g, cmd):
    x1, y1, x2, y2 = _rect(cmd)
    g.stockpiles.add((x1, y1, x2, y2))


def _stockpile_remove(g, cmd):
    x1, y1, x2, y2 = _rect(cmd)
    for sp in g.stockpiles.stockpiles:
        if (sp.x1, sp.y1, sp.x2, sp.y2) == (x1, y1, x2, y2):
            g.stockpiles.stockpiles.remove(sp)
            return


def _farm_add(g, cmd):
    plant = cmd["plant"]
    if plant in ("berry", "tree") and g.research_mgr.can_plant(plant):
        g.farms.add(_rect(cmd), plant)


def _build_area(g, cmd):
    kind, mat, rot = cmd["kind"], cmd["mat"], cmd["rot"]
    if kind not in BUILDING_DEFS or mat not in BUILDING_DEFS[kind]["variants"]:
        return
    if not g.research_mgr.is_unlocked(kind, mat):
        return
    x1, y1, x2, y2 = _rect(cmd)
    w, h = BUILDING_DEFS[kind]["w"], BUILDING_DEFS[kind]["h"]
    if rot % 2 == 1:
        w, h = h, w
    for ty in range(y1, y2 + 1, h):
        for tx in range(x1, x2 + 1, w):
            if g.buildings.can_place(g.world, tx, ty, kind, mat, rot):
                g.buildings.add_blueprint(kind, mat, tx, ty, rot)


def _deconstruct_area(g, cmd):
    x1, y1, x2, y2 = _rect(cmd)
    g.stockpiles.remove_tiles(x1, y1, x2, y2)
    g.farms.remove_tiles(x1, y1, x2, y2)
    g.buildings.remove_area(x1, y1, x2, y2)


def _harvest_area(g, cmd):
    x1, y1, x2, y2 = _rect(cmd)
    for ty in range(y1, y2 + 1):
        for tx in range(x1, x2 + 1):
            if g.world.is_harvestable(tx, ty):
                g.ctx.designated_harvests.add((tx, ty))


def _hunt_area(g, cmd):
    x1, y1, x2, y2 = _rect(cmd)
    for a in g.animals:
        atx, aty = a.current_tile()
        if x1 <= atx <= x2 and y1 <= aty <= y2:
            a.is_hunted = True


# ---------------- 建筑面板 ----------------
def _bld_decon(g, cmd):
    b = _building(g, cmd["tx"], cmd["ty"], cmd.get("layer"))
    if b is not None and hasattr(b, "hp") and not b.marked_for_deconstruction:
        b.marked_for_deconstruction = True


def _bld_craft_add(g, cmd):
    b = _building(g, cmd["tx"], cmd["ty"], cmd.get("layer"))
    if b is not None and b.kind == "workbench" and cmd["item"] in CRAFT_ITEMS:
        b.craft_queue.append({"item": cmd["item"]})


def _bld_cook_set(g, cmd):
    b = _building(g, cmd["tx"], cmd["ty"], cmd.get("layer"))
    if b is None or b.kind != "stove" or cmd["meal"] not in ("meal_simple", "meal_fine"):
        return
    counts = {"meal_simple": 0, "meal_fine": 0}
    for task in b.cook_queue:
        if task["meal"] in counts: counts[task["meal"]] += 1
    counts[cmd["meal"]] = max(0, cmd["n"])
    b.cook_queue = []
    for k in ("meal_simple", "meal_fine"):
        for _ in range(counts[k]): b.cook_queue.append({"meal": k})


def _bld_cook_clear(g, cmd):
    b = _building(g, cmd["tx"], cmd["ty"], cmd.get("layer"))
    if b is not None and b.kind == "stove":
        b.cook_queue = [t for t in b.cook_queue if t["meal"] != cmd["meal"]]


def _bld_smelt_set(g, cmd):
    b = _building(g, cmd["tx"], cmd["ty"], cmd.get("layer"))
    if b is not None and b.kind == "furnace":
        b.smelt_queue = []
        for _ in range(max(0, cmd["n"])): b.smelt_queue.append({"item": "iron"})


def _bld_smelt_clear(g, cmd):
    b = _building(g, cmd["tx"], cmd["ty"], cmd.get("layer"))
    if b is not None and b.kind == "furnace":
        b.smelt_queue.clear()


# ---------------- 其他 ----------------
def _research_set(g, cmd):
    if cmd["tech"] in TECHS:
        g.research_mgr.set_research(cmd["tech"])


def _toggle_haul(g, cmd):
    st = g.items.stacks.get((cmd["tx"], cmd["ty"], cmd["kind"]))
    if st is not None:
        st.allow_haul = not getattr(st, "allow_haul", False)


def _speed(g, cmd):
    if cmd["v"] in (0, 1, 2, 3):
        g.game_speed = float(cmd["v"])


HANDLERS = {
    "attack": _attack, "hunt": _hunt, "station": _station, "build": _build, "equip": _equip,
    "haul": _haul, "harvest": _harvest, "move": _move, "take": _take,
    "stockpile_add": _stockpile_add, "stockpile_remove": _stockpile_remove, "farm_add": _farm_add,
    "build_area": _build_area, "deconstruct_area": _deconstruct_area,
    "harvest_area": _harvest_area, "hunt_area": _hunt_area,
    "bld_decon": _bld_decon, "bld_craft_add": _bld_craft_add, "bld_cook_set": _bld_cook_set,
    "bld_cook_clear": _bld_cook_clear, "bld_smelt_set": _bld_smelt_set, "bld_smelt_clear": _bld_smelt_clear,
    "research_set": _research_set, "toggle_haul": _toggle_haul, "speed": _speed,
}


def apply_command(g, cmd):
    handler = HANDLERS.get(cmd.get("t"))
    if handler is not None:
        handler(g, cmd)
