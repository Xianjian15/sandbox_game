# core/commands.py
"""玩家指令：锁步联机里两端之间唯一传输的东西。

规则（违反即在 validate 里报错，而不是等到联机时才分叉）：
  1. 指令是纯 JSON 数据：dict / list / str / int / bool / None。
  2. 不允许 float（不同机器上的 float 序列化/解析可能有差异）、不允许 tuple（JSON 往返后会变成 list）、
     不允许对象引用。需要指向实体时用 id，指向格子时用整数坐标。
  3. 指令只描述"玩家想做什么"，真正的合法性校验和执行都在模拟侧（world/command_exec.py）完成，
     两端用完全相同的代码、完全相同的状态执行，所以结果一致。

通用字段（由 GameWorld.issue 自动盖章）：
  t     指令类型（见 COMMAND_TYPES）
  p     发出指令的玩家编号
  s     该玩家的指令序号（递增）
  tick  计划执行的 tick
"""
import json

COMMAND_TYPES = {
    # —— 对小人下达的命令（ids = 小人 id 列表，q = 是否 Shift 排队）——
    "attack",      # target: 敌人 id
    "hunt",        # target: 动物 id
    "station",     # kind: craft/research/cook/smelt, tx, ty
    "build",       # tx, ty
    "equip",       # tx, ty, kind
    "haul",        # tx, ty, kind
    "harvest",     # tx, ty
    "move",        # tx, ty
    "take",        # tx, ty, layer, kind, amt（ids 可为空：表示任意存活小人）
    # —— 区域/设施类 ——
    "stockpile_add", "stockpile_remove", "farm_add",
    "build_area", "deconstruct_area", "harvest_area", "hunt_area",
    # —— 建筑面板 ——
    "bld_decon", "bld_craft_add", "bld_cook_set", "bld_cook_clear", "bld_smelt_set", "bld_smelt_clear",
    # —— 其他 ——
    "research_set", "toggle_haul", "speed",
}


def validate(v, path="cmd"):
    if isinstance(v, bool) or v is None or isinstance(v, (int, str)):
        return
    if isinstance(v, float):
        raise ValueError(f"{path}: 指令里不允许 float（{v!r}），请用整数")
    if isinstance(v, list):
        for i, x in enumerate(v):
            validate(x, f"{path}[{i}]")
        return
    if isinstance(v, dict):
        for k, x in v.items():
            if not isinstance(k, str):
                raise ValueError(f"{path}: 键必须是 str（{k!r}）")
            validate(x, f"{path}.{k}")
        return
    raise ValueError(f"{path}: 指令里不允许 {type(v).__name__}（{v!r}），请用 id/坐标代替对象引用")


def make(t, **fields):
    if t not in COMMAND_TYPES:
        raise ValueError(f"未知指令类型 {t!r}")
    cmd = {"t": t}
    cmd.update(fields)
    validate(cmd)
    return cmd


def encode(cmds):
    """指令列表 -> bytes（键排序、无空格：两端字节完全一致）。"""
    return json.dumps(cmds, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def decode(data):
    cmds = json.loads(data.decode("ascii") if isinstance(data, (bytes, bytearray)) else data)
    for c in cmds:
        validate(c)
    return cmds
