# tools/enemy_wave_test.py
"""敌人入侵验收：
  E1 播报数 == 实际新增敌人数（多种子、多次触发）；一个都没生成时不播报
  E2 单波数量 ≤ 上限：联机=玩家总数；单人=3
  E3 装备随天数/波数提升；单人比同条件联机更弱
  E4 同种子两个世界生成完全一致（确定性）
用法： python -m tools.enemy_wave_test
"""
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
try:
    import pygame
    pygame.init(); pygame.display.set_mode((64, 64))
except ImportError:
    from tools import fake_pygame
    pygame = fake_pygame.install()
from world.game_world import GameWorld
from core.state_hash import world_hash

FAILS = []
def check(name, ok, info=""):
    print(("PASS " if ok else "FAIL ") + name + (" " + str(info) if info else ""))
    if not ok: FAILS.append(name)

def mk(seed, n):
    f = pygame.font.Font(None, 20)
    return GameWorld(f, f, f, f, 1280, 720, seed=seed, num_players=n)

def set_day(g, day):
    g.game_time.tick = int((day - 1) * g.game_time.day_length_sec * 60) + 5

def trigger(g):
    before = len(g.enemies); g.warning_text = ""
    g.enemy_invasion_timer = 0.0
    g._world_step()
    return len(g.enemies) - before

# E1/E2
bad1 = bad2 = 0; zero_alert = 0; waves = 0
for n in (1, 2, 3, 4):
    cap = 3 if n == 1 else n
    for seed in range(6):
        g = mk(seed, n)
        for day in range(1, 25, 2):
            set_day(g, day)
            new = trigger(g)
            m = re.search(r"(\d+) 名敌人", g.warning_text or "")
            if m:
                waves += 1
                if int(m.group(1)) != new: bad1 += 1
            elif new != 0: bad1 += 1
            if new == 0 and g.warning_text: zero_alert += 1
            if new > cap: bad2 += 1
check("E1 播报数==实际数", bad1 == 0 and zero_alert == 0, f"波数={waves} 不符={bad1}")
check("E2 数量不超上限", bad2 == 0, bad2)

# E3 装备
from world.game_world import GameWorld as GW
tiers = {w: i for i, pool in enumerate(GW.WAVE_WEAPONS) for w in pool}
g = mk(0, 3); set_day(g, 1); l_early = g.threat_level()
set_day(g, 21); l_late = g.threat_level()
check("E3a 威胁随天数升高", l_late > l_early, (l_early, l_late))
g.waves_spawned = 5; check("E3b 威胁随波数升高", g.threat_level() > l_late)
s = mk(0, 1); set_day(s, 9); m = mk(0, 2); set_day(m, 9)
check("E3c 单人更弱", s.threat_level() < m.threat_level(), (s.threat_level(), m.threat_level()))
check("E3d 单人上限3/联机=人数", s.enemy_cap() == 3 and mk(0, 4).enemy_cap() == 4 and mk(0, 2).enemy_cap() == 2)
check("E3e 单人最弱不出枪", all(w not in ("rifle", "pistol") for w in GW.WAVE_WEAPONS[0]))

# E4 确定性
a, b = mk(7, 3), mk(7, 3)
for g in (a, b):
    set_day(g, 11)
    for _ in range(4): trigger(g)
check("E4 确定性", world_hash(a) == world_hash(b) and len(a.enemies) == len(b.enemies))
print("FAILS:", FAILS); sys.exit(1 if FAILS else 0)
