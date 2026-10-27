# systems/research.py
TECHS = {
    "stone_masonry": {
        "name": "石工技术", "cost": 100.0, "desc": "解锁石墙、石门、石窗、石地板。",
        "requires": [], "unlocks": ["stone_material"]
    },
    "agriculture": {
        "name": "基础农业", "cost": 80.0, "desc": "解锁农业种植区，可以种植浆果。",
        "requires": [], "unlocks": ["plant_berry"]
    },
    "fast_trees": {
        "name": "速生树种", "cost": 150.0, "desc": "解锁在农业区种植树木。",
        "requires": ["agriculture"], "unlocks": ["plant_tree"]
    },
    "better_berries": {
        "name": "改良浆果", "cost": 200.0, "desc": "种植的浆果不仅产量更高，还能提供更多饱食度。",
        "requires": ["agriculture"], "unlocks": []
    }
}


class ResearchManager:
    def __init__(self):
        self.completed = set()
        self.current_research = None
        self.progress = 0.0

    def set_research(self, tech_id):
        if tech_id in self.completed: return False
        for req in TECHS[tech_id]["requires"]:
            if req not in self.completed: return False
        self.current_research = tech_id
        self.progress = 0.0
        return True

    def add_progress(self, amount):
        if not self.current_research: return False
        self.progress += amount
        if self.progress >= TECHS[self.current_research]["cost"]:
            self.completed.add(self.current_research)
            self.current_research = None
            self.progress = 0.0
            return True
        return False

    def is_unlocked(self, kind, material=None):
        if kind == "floor" and material == "stone": return "stone_masonry" in self.completed
        if kind in ("wall", "door", "window") and material == "stone": return "stone_masonry" in self.completed
        return True

    def can_plant(self, plant_type):
        if plant_type == "berry": return "agriculture" in self.completed
        if plant_type == "tree": return "fast_trees" in self.completed
        return False