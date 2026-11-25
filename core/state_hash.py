# core/state_hash.py
"""模拟状态哈希：锁步联机里发现"分叉"的唯一可靠手段。

用法：
    sections = world_sections(game)     # {分区名: 摘要}，用于定位是哪一块分叉
    digest   = world_hash(game)         # 整体摘要（短十六进制串）

联机时每隔 N 个 tick 两端互相发送 digest，不一致就说明已经分叉。
只哈希"模拟状态"，不碰任何纯 UI/渲染字段（选中、闪烁、特效、朝向角度等）。
"""
import hashlib
import zlib

# 纯显示/UI 字段，或依赖 libm 的派生量，不参与哈希
SKIP_ATTRS = {
    "selected", "hit_flash", "recent_shot", "facing_angle", "color", "colors",
    "rng", "ctx", "radius", "font", "surface",
}
FLOAT_DIGITS = 4


def canon(v, depth=0):
    """把任意值规范成可重复 repr 的内置结构。对象只取"身份"，不递归展开。"""
    if depth > 6:
        return "…"
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return round(v, FLOAT_DIGITS)
    if isinstance(v, (tuple, list)):
        return [canon(x, depth + 1) for x in v]
    if isinstance(v, (set, frozenset)):
        return sorted((canon(x, depth + 1) for x in v), key=repr)
    if isinstance(v, dict):
        return sorted(((canon(k, depth + 1), canon(x, depth + 1)) for k, x in v.items()), key=repr)
    # 对象：只记类名 + 能唯一标识它的字段
    name = type(v).__name__
    if isinstance(getattr(v, "id", None), int):
        return ("obj", name, v.id)
    if hasattr(v, "tx") and hasattr(v, "ty"):
        return ("obj", name, v.tx, v.ty, getattr(v, "layer", None), getattr(v, "kind", None))
    return ("obj", name)


def obj_state(o):
    return sorted(((k, canon(val)) for k, val in vars(o).items() if k not in SKIP_ATTRS), key=repr)


def _digest(x):
    return hashlib.sha256(repr(x).encode("utf-8")).hexdigest()[:16]


def world_sections(g):
    s = {}
    s["time"] = _digest((g.game_time.tick, g.turn, canon(g.game_speed),
                         canon(g.animal_respawn_timer), canon(g.enemy_invasion_timer), g.waves_spawned))
    s["ctx"] = _digest(g.ctx.snapshot())
    s["colonists"] = _digest([obj_state(c) for c in sorted(g.colonists, key=lambda e: e.id)])
    s["enemies"] = _digest([obj_state(e) for e in sorted(g.enemies, key=lambda e: e.id)])
    s["animals"] = _digest([(obj_state(a), a.rng.getstate()) for a in sorted(g.animals, key=lambda e: e.id)])
    s["items"] = _digest(sorted((k, st.amount, st.reserved_by, st.allow_haul) for k, st in g.items.stacks.items()))
    s["buildings"] = _digest(sorted(
        ((k, obj_state(b)) for k, b in g.buildings.buildings.items()), key=repr))
    s["blueprints"] = _digest(sorted(
        ((k, obj_state(b)) for k, b in g.buildings.blueprints.items()), key=repr))
    s["farms"] = _digest([(f.x1, f.y1, f.x2, f.y2, f.plant_type, canon(f.plots)) for f in g.farms.farms])
    s["stockpiles"] = _digest([(sp.x1, sp.y1, sp.x2, sp.y2, sp.priority) for sp in g.stockpiles.stockpiles])
    s["research"] = _digest((sorted(g.research_mgr.completed), g.research_mgr.current_research,
                             canon(g.research_mgr.progress)))
    s["terrain"] = _digest((zlib.crc32(repr(g.world.tiles).encode()), sorted(g.world.resource_hp.items())))
    return s


def world_hash(g):
    return _digest(sorted(world_sections(g).items()))
