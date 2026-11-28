# tools/quest_test.py
"""v0.13.0 支线任务验收：任务链开启/推进/奖励、随机任务、击杀计数、哈希、面板绘制与点击收起、弩/书架/喷泉。
用法： python -m tools.quest_test
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
try:
    import pygame
    pygame.init(); pygame.display.set_mode((64, 64))
except ImportError:
    from tools import fake_pygame
    pygame = fake_pygame.install()
from tools import determinism_test as D
from world.game_world import GameWorld
from entities.animal import Animal
from entities.enemy import Enemy
from core.state_hash import world_hash
from systems.quests import CHAINS, _POOL
from combat.weapons import CRAFT_COST
FAILS = []
def check(n, ok, info=""):
    print(("  ✓ " if ok else "  ✗ ") + n + (f"  {info}" if info and not ok else ""))
    if not ok: FAILS.append(n)
f = pygame.font.Font(None, 16)
W, H = 1280, 720
def mk(seed=21):
    g = GameWorld(f, f, f, f, W, H, seed=seed); g.set_screen_size(W, H); g.animals.clear(); return g
def run(g, n):
    for _ in range(n): g.sim_step()
def amount(g, kind): return sum(st.amount for st in g.items.stacks.values() if st.kind == kind)
def titles(g): return [q["title"] for q in g.quests.active]
def stock_far(g, kind, n):          # 放在远处，避免被小人拿走影响计数
    g.items.add(kind, n, 3, 3)

# Q1 任务链开启
g = mk(); run(g, 60 * 25)
check("Q1 开局不久出现【拓荒者】第一步", any("拓荒者" in t for t in titles(g)), titles(g))

# Q2 收集完成 → 奖励 + 下一步
g = mk(); run(g, 60 * 25)
s0 = amount(g, "stone"); stock_far(g, "wood", 60); run(g, 31)
check("Q2 木头够数后任务完成", g.quests.done >= 1 and not any("备料" in t for t in titles(g)), titles(g))
check("Q2 奖励 15 石头入账", amount(g, "stone") >= s0 + 15, (s0, amount(g, "stone")))
check("Q2 自动开启下一步（建 2 张床）", any("安家" in t for t in titles(g)), titles(g))

# Q3 建造类
for _ in range(2): D._place(g, "bed", "wood", 1, 2)
run(g, 31)
check("Q3 建 2 张床后完成并进入第三步", any("采石" in t for t in titles(g)) and not any("安家" in t for t in titles(g)), titles(g))

# Q4 研究类 + 链尾奖励弓
stock_far(g, "stone", 60); run(g, 31)
check("Q4 采石完成，进入“求知”", any("求知" in t for t in titles(g)), titles(g))
g.research_mgr.completed.add("agriculture"); run(g, 31)
check("Q4 完成研究后任务链结束且奖励猎弓", amount(g, "bow") >= 1 and g.quests.chain_next[0] == 4, (amount(g, "bow"), g.quests.chain_next))

# Q5 狩猎链
g = mk(); g.quests.chain_on[1] = True; g.quests._chain_step(g, 1)
tx, ty = g.colonists[0].current_tile()
for i in range(3):
    a = Animal(tx + 2 + i, ty, "rabbit", ctx=g.ctx); a.hp = 0; g.animals.append(a)
run(g, 31)
check("Q5 击杀动物被计数并完成第一步", g.quests.animals_killed == 3 and g.quests.chain_next[1] == 1, (g.quests.animals_killed, g.quests.chain_next))
check("Q5 第二步从 0 开始计数（不重复算旧击杀）", g.quests.active and g.quests.progress(g.quests.active[-1], g, {}) == 0)

# Q6 守卫链
g = mk(); g.quests.chain_on[3] = True; g.quests._chain_step(g, 3)
c = g.colonists[0]; tx, ty = c.current_tile()
for i in range(3):
    e = Enemy(tx + 20, ty + i, "pistol", ctx=g.ctx); e.hp = 0; g.enemies.append(e)
iron0 = amount(g, "iron"); run(g, 31)
check("Q6 击杀入侵者被计数，奖励铁", g.quests.enemies_killed == 3 and amount(g, "iron") >= iron0 + 6, (g.quests.enemies_killed, amount(g, "iron")))

# Q7 随机任务：每种模板在多个天数下都能创建、计算进度、不报错
ok = True
for day in (1, 3, 8, 20):
    for idx in range(len(_POOL)):
        g = mk(day + idx); g.game_time.tick = int((day - 1) * g.game_time.day_length_sec * 60) + 5000
        try:
            qm = g.quests; qm.active.clear()
            import random
            g.rng = random.Random(idx * 7 + day)
            qm._random(g); cache = {}
            for q in qm.active: qm.progress(q, g, cache)
        except Exception as ex:                       # noqa: BLE001
            ok = False; print("   异常", day, idx, repr(ex))
check("Q7 随机任务模板在各天数下都能生成", ok)
g = mk(); g.quests.timer = 0.0; g.game_time.tick = 60 * 60 * 3
g.quests.update(g)
check("Q7 定时器到点会生成随机任务（有上限）", sum(1 for q in g.quests.active if q["chain"] < 0) <= 2)

# Q8 哈希
g = mk(); h0 = world_hash(g); g.quests.done += 1
check("Q8 任务状态参与哈希", world_hash(g) != h0)

# Q9 面板：绘制、点标题收起、Q 键
g = mk(); run(g, 60 * 25)
def draw(g):
    s = pygame.Surface((g.ui_w, g.ui_h)); g._draw_ui(s, g.ui_w, g.ui_h); g.set_screen_size(W, H)
draw(g)
check("Q9 面板能画出且占用了矩形", g.quest_rect is not None and g.quest_rect.h > 24, g.quest_rect)
r = g.quest_rect; p = (r.x + 20, r.y + 8)
g.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(int(p[0] * g.ui_scale), int(p[1] * g.ui_scale)), button=1), W, H)
draw(g)
check("Q9 点标题栏收起面板", g.show_quests is False and g.quest_rect.h == 24, (g.show_quests, g.quest_rect))
g.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_q, mod=0, unicode="q"), W, H)
check("Q9 按 Q 展开", g.show_quests is True)

# Q10 新内容：弩、书架、喷泉
g = mk(); b = D._place(g, "workbench", "wood", 2, 1)
check("Q10 弩的配方", CRAFT_COST["crossbow"] == {"wood": 4, "iron": 3, "leather": 1})
g.research_mgr.completed.add("stone_masonry")
for kind, mat in (("bookshelf", "wood"), ("fountain", "stone")):
    bld = D._place(g, kind, mat, 1, 1)
    check(f"Q10 {kind} 可建且提高美观", bld is not None and g.room_mgr._calc_beauty([(bld.tx, bld.ty)]) > g.room_mgr._calc_beauty([(bld.tx + 60, bld.ty)]))
g2 = mk(); check("Q10 未研究石工时喷泉不可建", not g2.research_mgr.is_unlocked("fountain", "stone"))
g = mk(); b = D._place(g, "workbench", "wood", 2, 1); g.research_mgr.completed.add("crafting")
D._stock(g, "wood", 4); D._stock(g, "iron", 3); D._stock(g, "leather", 1)
b.craft_queue = [{"item": "crossbow"}]; D._rclick(g, b)
got = False
for t in range(15000):
    g.sim_step()
    if g.colonists[0].weapon_key == "crossbow": got = True; break
check("Q10 工作台能造弩并装备", got, t)
print("FAILS:", FAILS); sys.exit(1 if FAILS else 0)
