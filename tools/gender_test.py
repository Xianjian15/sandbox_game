# tools/gender_test.py
"""性别验收：资料页选性别→存盘→联机名单同步→游戏里小人按性别出贴图；性别不进状态哈希；手持武器贴图。
用法： python -m tools.gender_test
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools import fake_pygame
pygame = fake_pygame.install(textures=True)
from core import profile as P, textures
from core.state_hash import world_hash
from world.game_world import GameWorld
from entities.enemy import Enemy
from ui.menu import MenuModel
FAILS = []
def check(n, ok, info=""):
    print(("  ✓ " if ok else "  ✗ ") + n + (f"  {info}" if info and not ok else ""))
    if not ok: FAILS.append(n)
f = pygame.font.Font(None, 16)
def mk(num=1, seed=4):
    g = GameWorld(f, f, f, f, 1280, 720, seed=seed, num_players=num); g.set_screen_size(1280, 720); return g

# G1 资料数据
p = P.Profile("阿明", None, None, "female")
check("G1 性别随资料导出/清洗", p.to_wire()["g"] == "f" and P.clean_wire(p.to_wire(), "x")["g"] == "f")
check("G1 非法性别回落成男", P.clean_wire({"name": "a", "g": "zzz"}, "x")["g"] == "m" and P.Profile("a", None, None, "???").gender == "male")
import tempfile
path = os.path.join(tempfile.mkdtemp(), "profile.json")
q = P.Profile("小红", None, path, "female"); q.save()
check("G1 性别能存盘并读回", P.Profile.load(path).gender == "female")
old = os.path.join(tempfile.mkdtemp(), "old.json"); open(old, "w", encoding="utf-8").write('{"name": "旧档"}')
check("G1 旧存档（没有性别字段）读出来默认男", P.Profile.load(old).gender == "male")

# G2 菜单：主菜单进入角色设置，选女性，保存回主菜单
class Clock:
    def __call__(self): return 0.0
cfgd = {"profile": P.Profile("测试", None, None), "clock": Clock()}
m = MenuModel(dict(cfgd, disc_port=0), clock=Clock())
def click(m, action):
    w = [w for w in m.layout(1280, 720) if w.kind == "button" and w.action == action]
    assert w, action
    m.click((w[0].x + w[0].w // 2, w[0].y + w[0].h // 2), 1280, 720)
click(m, "profile_main")
check("G2 主菜单能进入资料页", m.screen == "profile")
click(m, "gender_female"); check("G2 选女性后界面显示已选", m.edit_gender == "female"
      and any("已选" in w.text for w in m.layout(1280, 720) if w.action == "gender_female"))
check("G2 未保存前资料不变", m.profile.gender == "male")
click(m, "save_profile")
check("G2 保存后性别生效并回到主菜单", m.profile.gender == "female" and m.screen == "main"
      and any("女性" in w.text for w in m.layout(1280, 720) if w.action == "profile_main"))
click(m, "profile_main"); click(m, "gender_male"); click(m, "cancel_profile")
check("G2 取消不改变性别", m.profile.gender == "female" and m.screen == "main")
m.close()

# G3 游戏里：单人
g = mk(); g.apply_genders(["female"])
gs = [c.gender for c in sorted(g.colonists, key=lambda c: c.id)]
check("G3 单人：第一个小人是自己选的性别（其余男女交替）", gs[0] == "female" and all(gs[i] != gs[i + 1] for i in range(len(gs) - 1)), gs)
g = mk(); gs = [c.gender for c in sorted(g.colonists, key=lambda c: c.id)]
check("G3 没选性别时默认是男性", gs[0] == "male", gs)
# 联机：两位玩家各自的性别
g = mk(2); g.set_profiles([{"name": "甲", "av": None, "g": "f"}, {"name": "乙", "av": None, "g": "m"}])
by = {pl: [c.gender for c in sorted(g.colonists, key=lambda c: c.id) if c.owner_id == pl] for pl in (0, 1)}
check("G3 联机：每位玩家的第一个小人按各自选择", by[0][0] == "female" and by[1][0] == "male", by)
# 哈希不受影响
g1 = mk(seed=9); g2 = mk(seed=9); g2.apply_genders(["female"]); g1.apply_genders(["male"])
check("G3 性别只是外观：不同性别的两局状态哈希相同", world_hash(g1) == world_hash(g2))

# G4 贴图
g = mk(); g.apply_genders(["female"])
from entities.colonist import Colonist
c2 = Colonist(30, 30, ctx=g.ctx); c2.gender = "male"; g.colonists.append(c2)        # 再来一个男性小人（以后有招募时的情形）
g.apply_genders(["female"])
check("G3 之后加入的小人按男女交替", [c.gender for c in sorted(g.colonists, key=lambda c: c.id)] == ["female", "male"])
g.enemies.append(Enemy(10, 10, "pistol", ctx=g.ctx)); g.enemies.append(Enemy(12, 10, "rifle", ctx=g.ctx))
g.colonists[0].weapon_key = "crossbow"
s = pygame.Surface((1280, 720)); g.draw(s, 0.016)
used = {k[0] for k, v in textures._person_cache.items() if v is not None}
check("G4 女性小人用女性贴图、男性用男性贴图", "colonist_female_body" in used and "colonist_male_body" in used, used)
check("G4 敌人男女贴图都有", {"enemy_male_body", "enemy_female_body"} <= used, used)
check("G4 手持武器用了贴图", any(v is not None for v in textures._hold_cache.values()), list(textures._hold_cache))
for key in ("pistol", "rifle", "crossbow", "bow", "longsword", "war_hammer", "stone_axe", "sniper"):
    if textures.get("hold_" + key) is None: check(f"G4 手持贴图 {key}", False)
check("G4 所有武器手持贴图齐全", all(textures.get("hold_" + k) is not None for k in
      ("stone_pickaxe", "iron_pickaxe", "stone_axe", "axe", "stone_spear", "spear", "iron_spear", "stone_hammer", "war_hammer",
       "stone_knife", "dagger", "machete", "longsword", "club", "bow", "crossbow", "pistol", "rifle", "shotgun", "smg", "sniper", "gun")))
print("FAILS:", FAILS); sys.exit(1 if FAILS else 0)
