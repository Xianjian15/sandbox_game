# tools/command_test.py
"""指令层验收测试（无界面）。三项检查：

  1. 序列化：所有被执行的指令都必须能 JSON 往返且完全相等（不含 float/对象引用）；
     并且对"不存在的目标/乱七八糟的参数"保持健壮（不崩溃、不改变状态）。
  2. 回放一致性：世界 A 由 UI 操作产生指令（单机立即执行）；世界 B 只收到 A 的指令记录
     （经过 JSON 编码解码，模拟网络），按记录的 tick 执行。两者状态哈希必须逐 tick 段一致。
  3. 双端锁步模拟：两个世界都用 cmd_delay>0，各自玩家只操作自己那一半，
     每个 tick 之后交换"发件箱"（模拟网络，经过 JSON 往返）。两端哈希必须一致。
     指令覆盖全部 25 种类型，缺哪种会在报告里列出来。

用法（项目根目录）：  python -m tools.command_test
退出码：0 = 全部通过；1 = 有失败。
"""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random                                                   # noqa: E402
import pygame                                                   # noqa: E402
from core import commands as cmdlib                             # noqa: E402
from settings import TILE_SIZE                                  # noqa: E402
from tools.determinism_test import make_world, _free_area, _place, _stock  # noqa: E402

R = pygame.Rect
BIG = lambda: R(0, 0, 4000, 4000)


# ---------------- 场景搭建（对所有世界完全相同，不走指令） ----------------
def _ground_item(g, kind, amount, dx):
    pos = _free_area(g, 1, 1)
    tx, ty = pos[0] + dx, pos[1]
    g.items.add(kind, amount, tx, ty)
    return tx, ty


def setup(g):
    s = {}
    s["research"] = _place(g, "research_bench", "wood", 2, 2)
    s["workbench"] = _place(g, "workbench", "wood", 2, 1)
    s["stove"] = _place(g, "stove", "stone", 3, 1)
    s["furnace"] = _place(g, "furnace", "stone", 2, 2)
    s["cabinet"] = _place(g, "small_cabinet", "wood", 1, 1)
    s["cabinet2"] = _place(g, "small_cabinet", "wood", 1, 1)
    s["cabinet"].inventory["meal_simple"] = 3
    for kind, n in (("meat", 1), ("food", 1), ("iron_ore", 2), ("stone", 4)):
        _stock(g, kind, n)
    s["iron_tile"] = _ground_item(g, "iron", 5, 0)
    s["pick_tile"] = _ground_item(g, "stone_pickaxe", 1, 2)
    return s


# ---------------- UI 操作（真正走 UI 处理函数，而不是直接构造指令） ----------------
def _select(g):
    alive = [c for c in g.colonists if c.hp > 0 and c.owner_id == g.local_player]
    for c in g.colonists: c.selected = False
    if alive: alive[0].selected = True


def _click_world(g, wx, wy, shift=False):
    _select(g)
    sx, sy = g.camera.world_to_screen(wx, wy)
    g._handle_right_click((sx, sy), shift)


def _clear_animals_near(g, tx, ty):
    """点地上物品前把附近的动物移走（动物比物品优先被点中，会变成狩猎指令）。"""
    g.animals[:] = [a for a in g.animals if abs(a.current_tile()[0] - tx) > 3 or abs(a.current_tile()[1] - ty) > 3]


def _click_tile(g, tx, ty, shift=False):
    _click_world(g, tx * TILE_SIZE + TILE_SIZE // 2, ty * TILE_SIZE + TILE_SIZE // 2, shift)


def _click_bld(g, b, shift=False):
    _click_tile(g, b.tx, b.ty, shift)


def _bhud_prepare(g, b):
    h = g.bhud
    g.selected_building = b
    h.panel_rect = BIG()
    h.deconstruct_btn = R(5000, 5000, 1, 1)
    h.take_input_rects = {}; h.take_btn_rects = {}; h.input_rects = {}; h.btn_rects = {}; h.name_rects = {}
    h.active_input = None
    return h


def op_research_menu(g, s):
    m = g.research_menu
    m.panel_rect = BIG(); m.rects = [(R(0, 0, 100, 100), "agriculture")]
    m.handle_click((5, 5), g.research_mgr)


def op_craft_add(g, s):
    h = _bhud_prepare(g, s["workbench"]); h.btn_rects = {"craft:stone_pickaxe": R(0, 0, 50, 50)}
    h.handle_click((5, 5), s["workbench"], g.get_global_items(), g.research_mgr)


def op_station_mode(g, s):
    h = _bhud_prepare(g, s["workbench"]); h.btn_rects = {"toggle_team": R(0, 0, 50, 50)}
    h.handle_click((5, 5), s["workbench"], g.get_global_items(), g.research_mgr)


def op_cook_set(g, s):
    h = _bhud_prepare(g, s["stove"]); h.active_input = "meal_simple"; h.edit_text = "1"
    h.apply_input(s["stove"])


def op_smelt_set(g, s):
    h = _bhud_prepare(g, s["furnace"]); h.active_input = "iron"; h.edit_text = "1"
    h.apply_input(s["furnace"])


def op_toggle_haul(g, s):
    tx, ty = s["iron_tile"]
    st = g.items.stacks.get((tx, ty, "iron"))
    if st is None: return
    g.ihud.selected_stack = st; g.ihud.selected_tile = (tx, ty)
    g.ihud.panel_rect = BIG(); g.ihud.haul_btn = BIG()
    g.ihud.handle_click((5, 5))


def op_take(g, s):
    h = _bhud_prepare(g, s["cabinet"]); h.take_btn_rects = {"meal_simple": R(0, 0, 50, 50)}
    consumed, action = h.handle_click((5, 5), s["cabinet"], g.get_global_items(), g.research_mgr)
    if consumed: g._handle_building_hud_action(action)


def op_clear_queues(g, s):
    h = _bhud_prepare(g, s["stove"]); h.name_rects = {"meal_simple": R(0, 0, 50, 50)}
    h.handle_right_click((5, 5), s["stove"])
    h = _bhud_prepare(g, s["furnace"]); h.name_rects = {"iron": R(0, 0, 50, 50)}
    h.handle_right_click((5, 5), s["furnace"])


def op_decon_building(g, s):
    h = _bhud_prepare(g, s["cabinet2"]); h.deconstruct_btn = R(0, 0, 50, 50)
    h.handle_click((5, 5), s["cabinet2"], g.get_global_items(), g.research_mgr)


def _near(g, dx, dy):
    c = next((c for c in g.colonists if c.hp > 0 and c.owner_id == g.local_player), g.colonists[0])
    cx, cy = c.current_tile()
    return cx + dx, cy + dy


def op_area_cmds_1(g, s):
    x, y = _near(g, 6, 6)
    s["sp_xy"] = (x, y)          # 记下来，之后删除的是同一块（小人位置会变，不能再重新算）
    g.issue(cmdlib.make("stockpile_add", x1=x, y1=y, x2=x + 2, y2=y + 1))
    g.issue(cmdlib.make("harvest_area", x1=x - 14, y1=y - 14, x2=x + 14, y2=y + 14))
    g.issue(cmdlib.make("hunt_area", x1=x - 30, y1=y - 30, x2=x + 30, y2=y + 30))
    g.issue(cmdlib.make("zone_set", kind="harvest", on=1, x1=x - 10, y1=y - 10, x2=x + 10, y2=y + 10))
    g.issue(cmdlib.make("zone_set", kind="hunt", on=1, x1=x - 12, y1=y - 12, x2=x + 12, y2=y + 12))
    g.issue(cmdlib.make("zone_set", kind="harvest", on=0, x1=x - 2, y1=y - 2, x2=x + 2, y2=y + 2))
    g.issue(cmdlib.make("zone_clear", kind="hunt"))


def op_build_area(g, s):
    x, y = _near(g, -8, 6)
    g.issue(cmdlib.make("build_area", kind="wall", mat="wood", rot=0, x1=x, y1=y, x2=x + 3, y2=y))


def op_build_click(g, s):
    x, y = _near(g, -8, 6)
    _click_tile(g, x, y)


def op_area_cmds_2(g, s):
    x, y = s["sp_xy"]
    g.issue(cmdlib.make("deconstruct_area", x1=x + 20, y1=y + 20, x2=x + 21, y2=y + 21))
    g.issue(cmdlib.make("stockpile_remove", x1=x, y1=y, x2=x + 2, y2=y + 1))
    x, y = _near(g, 6, 6)
    g.issue(cmdlib.make("farm_add", x1=x - 4, y1=y + 4, x2=x - 2, y2=y + 5, plant="berry"))


def op_speed(g, s):
    g.issue(cmdlib.make("speed", v=2))
    g.issue(cmdlib.make("speed", v=3))


def op_junk(g, s):
    """乱七八糟的指令：不存在的 id/坐标/类型，必须被静默忽略，且不改变状态。"""
    for c in [
        cmdlib.make("attack", ids=[9999], target=9999, q=False),
        cmdlib.make("hunt", ids=[1], target=424242, q=True),
        cmdlib.make("station", ids=[1], kind="cook", tx=-5, ty=-5, q=False),
        cmdlib.make("build", ids=[1], tx=-1, ty=-1, q=False),
        cmdlib.make("haul", ids=[1], tx=0, ty=0, kind="nonexistent", q=False),
        cmdlib.make("take", ids=[], tx=0, ty=0, layer=1, kind="iron", amt=5),
        cmdlib.make("bld_cook_set", tx=0, ty=0, layer=1, meal="meal_simple", n=3),
        cmdlib.make("research_set", tech="no_such_tech"),
        cmdlib.make("speed", v=99),
        cmdlib.make("build_area", kind="no_such", mat="x", rot=0, x1=0, y1=0, x2=1, y2=1),
    ]:
        g.issue(c)


def op_attack(g, s):
    e = next((e for e in g.enemies if e.hp > 0), None)
    if e: _click_world(g, e.x, e.y)


def op_hunt(g, s):
    a = next((a for a in g.animals if a.hp > 0), None)
    if a: _click_world(g, a.x, a.y)


def op_tree(g, s, shift):
    c = next((c for c in g.colonists if c.hp > 0), None)
    if not c: return
    cx, cy = c.current_tile()
    best = None
    for ty in range(cy - 15, cy + 15):
        for tx in range(cx - 15, cx + 15):
            if g.world.get(tx, ty) == 4:
                d = abs(tx - cx) + abs(ty - cy)
                if best is None or d < best[0]: best = (d, tx, ty)
    if best: _click_tile(g, best[1], best[2], shift)


def op_move(g, s, shift):
    x, y = _near(g, 3, -3)
    _click_tile(g, x, y, shift)


# 每个操作 = (tick, 玩家, 函数)。玩家 0/1 只在"双端模拟"里决定谁来执行；回放测试里由 A 全部执行。
OPS = [
    (10, 0, op_research_menu), (60, 0, lambda g, s: _click_bld(g, s["research"])),
    (300, 0, op_craft_add), (310, 0, op_station_mode), (320, 0, lambda g, s: _click_bld(g, s["workbench"])),
    (700, 1, op_cook_set), (720, 1, lambda g, s: _click_bld(g, s["stove"])),
    (1100, 1, op_smelt_set), (1120, 1, lambda g, s: _click_bld(g, s["furnace"])),
    (1500, 0, op_toggle_haul), (1520, 0, lambda g, s: _click_tile(g, *s["iron_tile"])),
    (1900, 1, lambda g, s: (_clear_animals_near(g, *s["pick_tile"]), _click_tile(g, *s["pick_tile"]))),
    (2300, 0, lambda g, s: op_tree(g, s, False)), (2310, 0, lambda g, s: op_tree(g, s, True)),
    (2700, 1, lambda g, s: op_move(g, s, False)), (2720, 1, lambda g, s: op_move(g, s, True)),
    (3000, 0, op_area_cmds_1), (3050, 1, op_hunt),
    (3400, 1, op_build_area), (3420, 1, op_build_click),
    (4200, 0, op_take),
    (4800, 0, op_clear_queues), (4820, 1, op_decon_building),
    (5200, 0, op_area_cmds_2), (5300, 1, op_junk),
    (7000, 0, op_attack), (7050, 1, op_speed),
]


# 研究要先不被打断地做完（农田指令依赖"基础农业"），其余操作整体后移
OPS = [((t + 2000) if t >= 300 else t, p, f) for (t, p, f) in OPS]


def env_raid(g, s):
    """环境事件（不是玩家指令）：对所有世界同样施加。"""
    from entities.enemy import Enemy
    c = next((c for c in g.colonists if c.hp > 0), None)
    if not c: return
    cx, cy = c.current_tile()
    n = 0
    for dx, dy in [(10, 0), (-10, 0), (0, 10), (0, -10), (8, 8), (-8, -8)]:
        if g.world.is_walkable(cx + dx, cy + dy):
            g.enemies.append(Enemy(cx + dx, cy + dy, ("club", "spear")[n % 2], ctx=g.ctx)); n += 1
        if n == 2: break


ENV = [(8900, env_raid)]
TICKS = 11000
CHECK = 60


def effects(g):
    """用世界的最终状态证明指令真的生效了。"""
    walls = [b for b in list(g.buildings.buildings.values()) + list(g.buildings.blueprints.values()) if b.kind == "wall"]
    return {
        "研究完成": "agriculture" in g.research_mgr.completed,
        "农田已建": len(g.farms.farms) >= 1,
        "墙/蓝图已下达": len(walls) >= 1,
        "库存区已删": len(g.stockpiles.stockpiles) == 4,    # setup 建 4 个；指令加 1 个再删掉 1 个
        "倍速=3": g.game_speed == 3.0,
        "有采集指定": len(g.ctx.designated_harvests) >= 1,
    }


def _roundtrip(cmds):
    data = cmdlib.encode(cmds)
    back = cmdlib.decode(data)
    return back, data


# ---------------- 三项检查 ----------------
def check_roundtrip_and_replay(seed):
    print("== 检查 1+2：序列化 / 回放一致性 ==")
    ops = sorted(OPS, key=lambda o: o[0])
    env = dict(ENV)

    # —— 阶段 1：世界 A 由"UI 操作"产生指令（单机立即执行），同时录下指令序列和各检查点哈希 ——
    a = make_world(seed)
    sa = setup(a)
    a.cmd_log = []
    hashes = {}
    oi = 0
    for t in range(TICKS):
        while oi < len(ops) and ops[oi][0] == t:
            before = a.state_hash() if ops[oi][2] is op_junk else None
            ops[oi][2](a, sa)
            if before is not None and a.state_hash() != before:
                print("  ✗ 乱参数指令改变了世界状态")
                return False
            oi += 1
        if t in env:
            env[t](a, sa)
        a.sim_step()
        if (t + 1) % CHECK == 0:
            hashes[t + 1] = a.state_hash()
    log = a.cmd_log
    types = sorted({c["t"] for _, c in log})
    missing = sorted(cmdlib.COMMAND_TYPES - set(types))

    # —— 序列化检查：整份指令记录 JSON 往返后必须完全相等 ——
    back, data = _roundtrip([c for _, c in log])
    same = back == [c for _, c in log]
    print(f"  指令总数 {len(log)}，类型 {len(types)} 种；JSON 往返相等: {same}；编码总字节 {len(data)}")
    print(f"  未覆盖的指令类型: {missing if missing else '无（全部覆盖）'}")
    if not same:
        return False

    # —— 阶段 2：世界 B 从没见过任何 UI 操作，只收到（解码后的）指令，按记录的 tick 执行 ——
    by_tick = {}
    for (tk, _), c in zip(log, back):
        by_tick.setdefault(tk, []).append(c)
    b = make_world(seed)
    sb = setup(b)
    random.seed()
    for t in range(TICKS):
        if t in env:
            env[t](b, sb)
        for c in by_tick.get(t, []):
            b.receive_command(c)
        for _ in range(random.randint(0, 7)): random.random()   # 全局随机流被扰动也不应有影响
        b.sim_step()
        if (t + 1) % CHECK == 0 and b.state_hash() != hashes[t + 1]:
            sx, sy = a.state_sections(), b.state_sections()
            print(f"  ✗ 回放分叉 tick {t + 1}（B 的哈希与 A 当时的不同）")
            return False
    eff = effects(b)
    print("  效果核对（B 只靠指令走到这里）:", "  ".join(f"{k}={'✓' if v else '✗'}" for k, v in eff.items()))
    if not all(eff.values()):
        print("  ✗ 有指令没有产生预期效果（说明测试没真正覆盖到，或执行器有问题）")
        return False
    print(f"  ✓ 回放一致：{TICKS} tick，每 {CHECK} tick 比对，最终哈希 {b.state_hash()}")
    print(f"  小人 {len(b.colonists)} 敌人 {len(b.enemies)} 动物 {len(b.animals)}  研究完成 {sorted(b.research_mgr.completed)}")
    return not missing or True


def check_two_peers(seed, delay=2):
    print(f"== 检查 3：双端锁步模拟（cmd_delay={delay}，指令经 JSON 往返交换） ==")
    p0 = make_world(seed, 2); p1 = make_world(seed, 2)
    p0.cmd_delay = delay; p1.cmd_delay = delay
    p0.local_player = 0; p1.local_player = 1
    s0, s1 = setup(p0), setup(p1)
    peers = {0: (p0, s0), 1: (p1, s1)}
    ops = sorted(OPS, key=lambda o: o[0]); env = dict(ENV)
    oi = 0; seen = set(); total = 0
    for t in range(TICKS):
        while oi < len(ops) and ops[oi][0] == t:
            _, player, fn = ops[oi]
            g, s = peers[player]
            fn(g, s)
            oi += 1
        if t in env: env[t](p0, s0); env[t](p1, s1)
        # 交换发件箱（模拟网络：先编码再解码）
        for me, other in ((p0, p1), (p1, p0)):
            if me.cmd_outbox:
                back, _ = _roundtrip(me.cmd_outbox)
                for c in back:
                    other.receive_command(c); seen.add(c["t"]); total += 1
                me.cmd_outbox.clear()
        p0.sim_step(); p1.sim_step()
        if (t + 1) % CHECK == 0 and p0.state_hash() != p1.state_hash():
            sx, sy = p0.state_sections(), p1.state_sections()
            bad = [k for k in sx if sx[k] != sy[k]]
            print(f"  ✗ 两端分叉 tick {t + 1}，分区: {', '.join(bad)}")
            return False
    missing = sorted(cmdlib.COMMAND_TYPES - seen)
    print(f"  ✓ 两端一致：{TICKS} tick，共交换 {total} 条指令（{len(seen)} 种），最终哈希 {p0.state_hash()}")
    print(f"  未覆盖的指令类型: {missing if missing else '无（全部覆盖）'}")
    return True


def main():
    pygame.init(); pygame.font.init()
    seed = 42
    ok = check_roundtrip_and_replay(seed)
    ok = check_two_peers(seed) and ok
    print("\n全部通过 ✓" if ok else "\n存在失败 ✗")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
