# combat/weapons.py
WEAPONS = {
    "fist": {"name": "拳头", "damage": 5, "range": 1, "cooldown": 1.0, "color": (200, 200, 200), "melee": True},
    "club": {"name": "木棒", "damage": 12, "range": 1, "cooldown": 1.2, "color": (139, 90, 43), "melee": True},
    "spear": {"name": "长矛", "damage": 18, "range": 1.5, "cooldown": 1.5, "color": (150, 150, 150), "melee": True},
    "axe": {"name": "铁斧", "damage": 25, "range": 1, "cooldown": 1.3, "color": (100, 100, 110), "melee": True, "chop_bonus": True},
    "stone_pickaxe": {"name": "石镐", "damage": 15, "range": 1, "cooldown": 1.2, "color": (130, 130, 135), "melee": True, "mine_bonus": True},
    "iron_pickaxe": {"name": "铁镐", "damage": 25, "range": 1, "cooldown": 1.0, "color": (150, 150, 160), "melee": True, "mine_bonus": True},
    # 石器时代工具：石头就能做，伤害介于木棒和铁器之间
    "stone_axe": {"name": "石斧", "damage": 20, "range": 1, "cooldown": 1.3, "color": (125, 125, 130), "melee": True, "chop_bonus": True, "chop_mult": 1.8},
    "stone_spear": {"name": "石矛", "damage": 17, "range": 1.5, "cooldown": 1.3, "color": (140, 120, 100), "melee": True},
    "stone_hammer": {"name": "石锤", "damage": 28, "range": 1, "cooldown": 1.7, "color": (110, 110, 115), "melee": True},
    "stone_knife": {"name": "石刀", "damage": 9, "range": 1, "cooldown": 0.6, "color": (160, 160, 165), "melee": True},
    # 铁质新工具/武器
    "dagger": {"name": "匕首", "damage": 14, "range": 1, "cooldown": 0.55, "color": (190, 190, 200), "melee": True},
    "iron_spear": {"name": "铁矛", "damage": 30, "range": 1.5, "cooldown": 1.3, "color": (170, 170, 185), "melee": True},
    "machete": {"name": "砍刀", "damage": 34, "range": 1.1, "cooldown": 0.9, "color": (175, 180, 190), "melee": True, "chop_bonus": True, "chop_mult": 3.0},
    "war_hammer": {"name": "战锤", "damage": 60, "range": 1, "cooldown": 1.8, "color": (120, 120, 135), "melee": True},
    # 猎弓：不需要研究的早期远程武器（木头 + 狩猎得到的皮革），打猎时能远远射击
    "bow": {"name": "猎弓", "damage": 14, "range": 10, "cooldown": 1.1, "color": (150, 105, 60), "melee": False,
            "mag_size": 10, "reload_time": 2.2, "burst_count": 1, "burst_interval": 0.0},
    # 弩：威力大、射程远，但每发都要上弦（装填慢）
    "crossbow": {"name": "弩", "damage": 28, "range": 11, "cooldown": 0.6, "color": (110, 90, 70), "melee": False,
                 "mag_size": 1, "reload_time": 2.0, "burst_count": 1, "burst_interval": 0.0},
    "longsword": {"name": "长剑", "damage": 45, "range": 1.2, "cooldown": 1.0, "color": (220, 220, 220), "melee": True},

    # 手枪：8 发弹夹，单发，装填 1.5s
    "pistol": {
        "name": "手枪", "damage": 20, "range": 8, "cooldown": 0.8,
        "color": (100, 100, 100), "melee": False,
        "mag_size": 8, "reload_time": 1.5,
        "burst_count": 1, "burst_interval": 0.0,
    },
    # 突击步枪：30 发弹夹，6 连发，间隔 0.1s，装填 1.5s
    "rifle": {
        "name": "突击步枪", "damage": 20, "range": 12, "cooldown": 1.5,
        "color": (80, 80, 80), "melee": False,
        "mag_size": 30, "reload_time": 1.5,
        "burst_count": 6, "burst_interval": 0.1,
    },
}

WEAPONS.update({
    # 霰弹枪：近距离，一次扣扳机连射 3 粒弹丸
    "shotgun": {"name": "霰弹枪", "damage": 22, "range": 6, "cooldown": 1.6, "color": (110, 85, 60), "melee": False,
                "mag_size": 6, "reload_time": 2.5, "burst_count": 3, "burst_interval": 0.04},
    # 冲锋枪：射速快、单发伤害低
    "smg": {"name": "冲锋枪", "damage": 9, "range": 9, "cooldown": 0.6, "color": (70, 75, 85), "melee": False,
            "mag_size": 25, "reload_time": 1.8, "burst_count": 4, "burst_interval": 0.07},
    # 狙击枪：射程最远，单发高伤
    "sniper": {"name": "狙击枪", "damage": 70, "range": 16, "cooldown": 2.5, "color": (60, 70, 60), "melee": False,
               "mag_size": 5, "reload_time": 3.0, "burst_count": 1, "burst_interval": 0.0},
})


for _k, _v in WEAPONS.items():          # 每个武器记下自己的键名（手持贴图按键名找）
    _v.setdefault("key", _k)


def get_weapon(key):
    return WEAPONS.get(key, WEAPONS["fist"])

# 制造配方（集中在这里：小人取料、界面按钮、指令校验都读这一张表）
CRAFT_COST = {
    "stone_pickaxe": {"stone": 2}, "stone_axe": {"stone": 3}, "stone_spear": {"stone": 2, "wood": 1},
    "stone_hammer": {"stone": 4}, "stone_knife": {"stone": 1},
    "axe": {"iron": 2}, "iron_pickaxe": {"iron": 2}, "longsword": {"iron": 3},
    "gun": {"iron": 5}, "pistol": {"iron": 3}, "rifle": {"iron": 6},
    "bow": {"wood": 3, "leather": 2}, "crossbow": {"wood": 4, "iron": 3, "leather": 1},
    "dagger": {"iron": 1}, "iron_spear": {"iron": 2, "wood": 1}, "machete": {"iron": 3}, "war_hammer": {"iron": 4},
    "shotgun": {"iron": 5}, "smg": {"iron": 7}, "sniper": {"iron": 9},
}
# 工作台分类（界面按这个分组排按钮；tech 是解锁所需科技，None 表示工作台本身就够）
CRAFT_GROUPS = [
    ("石器", None, ["stone_pickaxe", "stone_axe", "stone_spear", "stone_hammer", "stone_knife"]),
    ("弓箭", None, ["bow"]),
    ("铁器", "crafting", ["axe", "iron_pickaxe", "longsword", "dagger", "iron_spear", "machete", "war_hammer", "crossbow"]),
    ("枪械", "gunsmithing", ["pistol", "rifle"]),
    ("高级枪械", "advanced_firearms", ["shotgun", "smg", "sniper"]),
]
EQUIPPABLE = tuple(k for k in WEAPONS if k != "fist") + ("gun",)   # 能装备/不默认搬运的武器工具类物品
TOOL_KEYS = ("stone_pickaxe", "iron_pickaxe")      # 进工具槽的物品（其余进武器槽）

def craft_need(task):
    return CRAFT_COST.get(task, {"iron": 2})
