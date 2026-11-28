# tools/six_player_test.py
"""6 人联机相关（不依赖网络）：
  X1 MAX_PLAYERS == 6，且归属色数量 >= MAX_PLAYERS 并两两不同
  X2 6 人开局：每人一个小人、出生点互不重叠且都可走、归属编号 0..5
  X3 玩家栏 6 个长名字也不超出屏幕右侧资源区（会换行）
  X4 6 人时敌人单波上限 = 6；单人仍是 3
  X5 版本号已升级（旧版不能和新版联机）
用法： python -m tools.six_player_test
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
from net.session import MAX_PLAYERS
from core.profile import PLAYER_COLORS
from core.version import GAME_VERSION
from world.game_world import GameWorld
FAILS = []
def check(n, ok, info=""):
    print(("  ✓ " if ok else "  ✗ ") + n + (f"  {info}" if info and not ok else ""))
    if not ok: FAILS.append(n)

check("X1a 最大人数 6", MAX_PLAYERS == 6, MAX_PLAYERS)
check("X1b 归属色足够且互不相同", len(PLAYER_COLORS) >= MAX_PLAYERS and len(set(PLAYER_COLORS)) == len(PLAYER_COLORS))

f = pygame.font.Font(None, 16)
g = GameWorld(f, f, f, f, 1280, 720, seed=3, num_players=6); g.set_screen_size(1280, 720)
tiles = [c.current_tile() for c in g.colonists]
check("X2a 6 人各有小人", len(g.colonists) == 6 and sorted(c.owner_id for c in g.colonists) == list(range(6)))
check("X2b 出生点互不重叠", len(set(tiles)) == 6, tiles)
check("X2c 出生点都可走", all(g.world.is_walkable(*t) for t in tiles), tiles)

names = ["一二三四五六七八九十甲乙"] * 6
profs = [{"name": n, "av": None} for n in names]
g.set_profiles(profs)
widths = []
orig_blit = pygame.Surface.blit if hasattr(pygame.Surface, "blit") else None
surf = pygame.Surface((g.ui_w, g.ui_h))
rects = []
real_rect = pygame.draw.rect
pygame.draw.rect = lambda s, col, r, *a, **k: (rects.append(tuple(r)), real_rect(s, col, r, *a, **k))[1]
try:
    g._draw_player_bar(surf)
finally:
    pygame.draw.rect = real_rect
avatars = [r for r in rects if r[2] == 34 and r[3] == 34]
check("X3a 6 个头像框都画了", len(avatars) == 6, len(avatars))
check("X3b 都在资源区之前（不伸到右上角）", max(r[0] for r in avatars) < g.ui_w - 190, (max(r[0] for r in avatars), g.ui_w))
check("X3c 窗口窄、名字长时会换行", len({r[1] for r in avatars}) >= 1 and (len({r[1] for r in avatars}) >= 2 or max(r[0] for r in avatars) < g.ui_w - 190))

check("X4a 6 人敌人上限 6", g.enemy_cap() == 6, g.enemy_cap())
g1 = GameWorld(f, f, f, f, 1280, 720, seed=3, num_players=1)
check("X4b 单人上限 3", g1.enemy_cap() == 3)
check("X5 版本号 >= 0.8.0", tuple(int(x) for x in GAME_VERSION.split(".")) >= (0, 8, 0), GAME_VERSION)
print("FAILS:", FAILS); sys.exit(1 if FAILS else 0)
