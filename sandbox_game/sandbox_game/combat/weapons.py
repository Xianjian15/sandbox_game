# combat/weapons.py

WEAPONS = {
    "fist": {
        "name": "拳头", "range": 1.2, "damage": 8,
        "cooldown": 1.0, "melee": True, "color": (220, 220, 220),
        "draw": None,
    },
    "knife": {
        "name": "匕首", "range": 1.4, "damage": 18,
        "cooldown": 0.9, "melee": True, "color": (230, 230, 240),
        "draw": None,
    },
    "pistol": {
        "name": "手枪", "range": 5.0, "damage": 14,
        "cooldown": 1.0, "melee": False, "color": (255, 230, 100),
        # 形状参数: (枪身长, 枪身高, 枪管长, 枪管高)
        "draw": {"body": (10, 5), "barrel": (8, 2), "stock": None,
                 "mag": None},
    },
    "smg": {
        "name": "冲锋枪", "range": 4.0, "damage": 10,
        "cooldown": 0.4, "melee": False, "color": (255, 220, 120),
        "draw": {"body": (12, 6), "barrel": (6, 2), "stock": (4, 4),
                 "mag": (3, 6)},
    },
    "rifle": {
        "name": "步枪", "range": 8.0, "damage": 22,
        "cooldown": 1.5, "melee": False, "color": (255, 180, 80),
        "draw": {"body": (14, 4), "barrel": (14, 2), "stock": (6, 5),
                 "mag": (2, 4)},
    },
}


def get_weapon(key):
    return WEAPONS.get(key, WEAPONS["fist"])