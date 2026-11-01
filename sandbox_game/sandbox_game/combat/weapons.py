# combat/weapons.py
WEAPONS = {
    "fist": {"name": "拳头", "damage": 5, "range": 1, "cooldown": 1.0, "color": (200, 200, 200), "melee": True},
    "club": {"name": "木棒", "damage": 12, "range": 1, "cooldown": 1.2, "color": (139, 90, 43), "melee": True},
    "spear": {"name": "长矛", "damage": 18, "range": 1.5, "cooldown": 1.5, "color": (150, 150, 150), "melee": True},
    "axe": {"name": "铁斧", "damage": 25, "range": 1, "cooldown": 1.3, "color": (100, 100, 110), "melee": True, "chop_bonus": True},
    "stone_pickaxe": {"name": "石镐", "damage": 15, "range": 1, "cooldown": 1.2, "color": (130, 130, 135), "melee": True, "mine_bonus": True},
    "iron_pickaxe": {"name": "铁镐", "damage": 25, "range": 1, "cooldown": 1.0, "color": (150, 150, 160), "melee": True, "mine_bonus": True},
    "longsword": {"name": "长剑", "damage": 45, "range": 1.2, "cooldown": 1.0, "color": (220, 220, 220), "melee": True},
    "pistol": {"name": "手枪", "damage": 20, "range": 8, "cooldown": 0.8, "color": (100, 100, 100), "melee": False},
    "rifle": {"name": "步枪", "damage": 35, "range": 12, "cooldown": 1.5, "color": (80, 80, 80), "melee": False},
}

def get_weapon(key):
    return WEAPONS.get(key, WEAPONS["fist"])