# tools/determinism_test.py
"""无界面双实例对拍：确定性重构是否成功的"判决书"。

在同一个进程里创建两个同 seed 的 GameWorld，施加完全相同的操作脚本，
交错推进，并故意往全局 random 里灌不同数量的随机数（模拟"两端环境不同"）。
每隔 --check 个 tick 比较一次状态哈希；一旦不一致，立刻报告是哪个 tick、哪几块状态分叉。

用法（在项目根目录）：
    python -m tools.determinism_test                 # 默认跑 5 分钟游戏时间
    python -m tools.determinism_test --ticks 36000   # 跑得更久
    python -m tools.determinism_test --inject-desync 3000   # 自检：故意制造分叉，看能不能抓到
退出码：0 = 全程一致；1 = 发现分叉。
"""
import argparse
import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame                                   # noqa: E402
from settings import INIT_W, INIT_H, TILE_SIZE  # noqa: E402
from world.game_world import GameWorld          # noqa: E402


# ---------------- 操作脚本（两端完全相同） ----------------
def _free_area(g, w, h):
    c = g.colonists[0]
    cx, cy = c.current_tile()
    best = None
    for ty in range(cy - 12, cy + 12):
        for tx in range(cx - 12, cx + 12):
            ok = True
            for yy in range(ty - 1, ty + h + 1):
                for xx in range(tx - 1, tx + w + 1):
                    if not g.world.is_terrain_walkable(xx, yy) or g.buildings.get_building_at(xx, yy):
                        ok = False
                        break
                if not ok:
                    break
            if ok:
                d = abs(tx - cx) + abs(ty - cy)
                if d >= 3 and (best is None or d < best[0]):
                    best = (d, tx, ty)
    return (best[1], best[2]) if best else None


def _place(g, kind, mat, w, h):
    pos = _free_area(g, w, h)
    if pos is None:
        return None
    bp = g.buildings.add_blueprint(kind, mat, *pos)
    g.buildings.complete_blueprint(bp)
    return g.buildings.get_building_at(*pos)


def _stock(g, kind, amount):
    pos = _free_area(g, 1, 1)
    if pos:
        g.stockpiles.add((pos[0], pos[1], pos[0], pos[1]))
        g.items.add(kind, amount, *pos)


def _rclick(g, b):
    if not g.colonists:
        return
    c = g.colonists[0]
    c.selected = True
    sx, sy = g.camera.world_to_screen(b.tx * TILE_SIZE + TILE_SIZE // 2, b.ty * TILE_SIZE + TILE_SIZE // 2)
    g._handle_right_click((sx, sy), False)


def step_research(g):
    b = _place(g, "research_bench", "wood", 2, 2)
    if b and g.research_mgr.set_research("agriculture"):
        _rclick(g, b)


def step_cook(g):
    b = _place(g, "stove", "stone", 3, 1)
    if b:
        _stock(g, "meat", 1)
        _stock(g, "food", 1)
        b.cook_queue = [{"meal": "meal_simple"}]
        _rclick(g, b)


def step_smelt(g):
    b = _place(g, "furnace", "stone", 2, 2)
    if b:
        _stock(g, "iron_ore", 2)
        b.smelt_queue = [{"item": "iron"}]
        _rclick(g, b)


def step_invasion(g):
    g.enemy_invasion_timer = 0.0      # 立刻触发一次敌人入侵（会用到世界 rng）


def step_raid(g):
    """在小人附近直接刷两名敌人，确保战斗/寻路/受伤这些路径一定被走到。
    （上面的随机入侵只有 50% 概率刷怪，不能保证覆盖。）"""
    from entities.enemy import Enemy
    if not g.colonists:
        return
    cx, cy = g.colonists[0].current_tile()
    n = 0
    for dx, dy in [(10, 0), (-10, 0), (0, 10), (0, -10), (8, 8), (-8, -8)]:
        if g.world.is_walkable(cx + dx, cy + dy):
            g.enemies.append(Enemy(cx + dx, cy + dy, ("club", "spear")[n % 2], ctx=g.ctx))
            n += 1
        if n == 2:
            break


SCRIPT = [(60, step_research), (2400, step_cook), (5400, step_smelt),
          (9000, step_invasion), (9600, step_raid)]


# ---------------- 主流程 ----------------
def make_world(seed):
    font = pygame.font.Font(None, 16)
    return GameWorld(font, font, font, font, INIT_W, INIT_H, seed=seed)


def run(ticks, seed, check, inject_at):
    pygame.init()
    pygame.font.init()
    a, b = make_world(seed), make_world(seed)
    random.seed()                                  # 全局随机流用系统熵：完全不可预测
    script = dict(SCRIPT)
    print(f"seed={seed}  ticks={ticks}  每 {check} tick 比对一次  初始哈希 A={a.state_hash()} B={b.state_hash()}")
    for t in range(ticks):
        if t in script:
            script[t](a)
            script[t](b)
        if inject_at is not None and t == inject_at:
            tgt = b.animals[0] if b.animals else b.colonists[0]
            tgt.x += 0.5                           # 故意让 B 悄悄偏移半个像素
            print(f"[自检] tick {t}: 已故意给 B 制造分叉（{type(tgt).__name__} id={tgt.id} 的 x += 0.5）")
        for _ in range(random.randint(0, 7)): random.random()   # 往全局流里灌不同数量
        a.sim_step()
        for _ in range(random.randint(0, 7)): random.random()
        b.sim_step()
        if (t + 1) % check == 0:
            if a.state_hash() != b.state_hash():
                sa, sb = a.state_sections(), b.state_sections()
                bad = [k for k in sa if sa[k] != sb[k]]
                print(f"✗ 分叉！tick {t + 1}（距上次一致不超过 {check} tick）  分叉的分区: {', '.join(bad)}")
                return 1
    print(f"✓ 全程一致：{ticks} tick，A == B  最终哈希 {a.state_hash()}")
    print(f"  小人 {len(a.colonists)}  敌人 {len(a.enemies)}  动物 {len(a.animals)}  物品堆 {len(a.items.stacks)}"
          f"  已分配实体 id 数 {a.ctx._next_id}  研究完成 {sorted(a.research_mgr.completed)}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="双实例确定性对拍")
    ap.add_argument("--ticks", type=int, default=18000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--check", type=int, default=60)
    ap.add_argument("--inject-desync", type=int, default=None, metavar="TICK")
    args = ap.parse_args(argv)
    return run(args.ticks, args.seed, args.check, args.inject_desync)


if __name__ == "__main__":
    sys.exit(main())
