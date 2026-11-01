# systems/research.py
TECHS = {
    "stone_masonry": {"name": "石工技术", "cost": 100.0, "desc": "解锁石墙、门、窗、地板、石镐，以及工作台。", "requires": [], "unlocks": ["stone_material", "workbench"]},
    "agriculture": {"name": "基础农业", "cost": 80.0, "desc": "解锁农业种植区，可以种植浆果。", "requires": [], "unlocks": ["plant_berry"]},
    "herbal_medicine": {"name": "草药学", "cost": 120.0, "desc": "解锁医疗床、无菌医疗设施，以及种植草药。", "requires": ["agriculture"], "unlocks": ["medical_bed", "sterile_material", "plant_medicine"]},
    "smelting": {"name": "粗铁精炼", "cost": 200.0, "desc": "解锁熔炉，可以将粗铁精炼为铁。", "requires": ["stone_masonry"], "unlocks": ["furnace"]},
    "crafting": {"name": "基础锻造", "cost": 250.0, "desc": "解锁铁斧、铁镐、长剑的制作。", "requires": ["smelting"], "unlocks": ["iron_gear"]},
    "gunsmithing": {"name": "枪械制造", "cost": 400.0, "desc": "解锁枪械制作。", "requires": ["crafting"], "unlocks": ["guns"]}
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
        if kind in ("furnace",) and "smelting" not in self.completed: return False
        if kind in ("workbench",) and "stone_masonry" not in self.completed: return False
        if kind in ("medical_bed", "sterile_floor", "sterile_wall") and "herbal_medicine" not in self.completed: return False
        if kind == "floor" and material == "stone" and "stone_masonry" not in self.completed: return False
        if kind in ("wall", "door", "window") and material == "stone" and "stone_masonry" not in self.completed: return False
        return True

    def can_plant(self, plant_type):
        if plant_type == "berry": return "agriculture" in self.completed
        if plant_type == "tree": return "fast_trees" in self.completed
        if plant_type == "medicine": return "herbal_medicine" in self.completed
        return False