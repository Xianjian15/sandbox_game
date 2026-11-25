# tools/ownership_test.py
"""所有权测试：每位玩家只能指挥自己的小人。

A. 执行器层（纯逻辑，不需要 pygame）：越权指令被忽略，自己的指令正常，无 p 的旧指令不过滤。
B. 整局层（需要 pygame）：两人世界的出生、选中、右键下令、锁步双端哈希一致。

用法（项目根目录）：  python -m tools.ownership_test
"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

FAILS = []


def check(name, cond, extra=""):
    print(("  ✓ " if cond else "  ✗ ") + name + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        FAILS.append(name)


def part_a():
    print("== A. 执行器层：_units 过滤 ==")
    from world import command_exec as ce

    def col(i, owner, hp=100):
        return types.SimpleNamespace(id=i, owner_id=owner, hp=hp)
    g = types.SimpleNamespace(colonists=[col(1, 0), col(2, 1), col(3, 0), col(4, 1, hp=0)])
    ids = [1, 2, 3, 4]
    check("玩家0 只拿到自己的小人", [c.id for c in ce._units(g, {"ids": ids, "p": 0})] == [1, 3])
    check("玩家1 只拿到自己的活小人", [c.id for c in ce._units(g, {"ids": ids, "p": 1})] == [2])
    check("越权：玩家0 点名对方 id → 空", ce._units(g, {"ids": [2], "p": 0}) == [])
    check("无 p 的旧指令不过滤", len(ce._units(g, {"ids": ids})) == 3)


def part_b():
    print("== B. 整局层：两人世界 ==")
    import pygame
    from settings import INIT_W, INIT_H, TILE_SIZE
    from world.game_world import GameWorld
    from core import commands as cmdlib
    pygame.init(); pygame.font.init()
    f = pygame.font.Font(None, 16)

    def mk(player):
        return GameWorld(f, f, f, f, INIT_W, INIT_H, seed=42, map_seed=42, cmd_delay=2,
                         local_player=player, num_players=2)
    p0, p1 = mk(0), mk(1)
    check("每人开局各有小人", sorted(c.owner_id for c in p0.colonists) == [0, 1])
    check("两端小人 id/归属一致", [(c.id, c.owner_id) for c in p0.colonists] == [(c.id, c.owner_id) for c in p1.colonists])
    check("开局哈希一致", p0.state_hash() == p1.state_hash())
    mine0 = [c for c in p0.colonists if c.owner_id == 0][0]
    theirs0 = [c for c in p0.colonists if c.owner_id == 1][0]

    # 选中：全选后 selected_colonists 只含自己的
    for c in p0.colonists: c.selected = True
    check("selected_colonists 只返回自己的", [c.id for c in p0.selected_colonists()] == [mine0.id])

    # 右键移动：UI 路径只会带自己的 id
    p0.camera.center_on(mine0.x, mine0.y) if hasattr(p0.camera, "center_on") else None
    tx, ty = mine0.current_tile()[0] + 5, mine0.current_tile()[1]
    sx, sy = p0.camera.world_to_screen(tx * TILE_SIZE + 16, ty * TILE_SIZE + 16)
    p0._handle_right_click((sx, sy), False)
    moves = [c for c in p0.cmd_outbox if c["t"] == "move"]
    check("右键只发给自己的小人", moves and moves[-1]["ids"] == [mine0.id])
    for cmd in p0.cmd_outbox:                       # 把玩家0 发出的指令转交给玩家1 的世界（模拟网络）
        p1.receive_command(cmd)
    p0.cmd_outbox.clear()

    # 伪造越权指令：玩家0 的指令点名玩家1 的小人，两端执行后都不应动
    for g in (p0, p1):
        g.receive_command(dict(cmdlib.make("move", ids=[theirs0.id], tx=tx, ty=ty, q=False), p=0, s=99, tick=g.turn + 2))
    before = (p0.state_hash(), p1.state_hash())
    for _ in range(3):
        p0.sim_step(); p1.sim_step()
    t0 = [c for c in p0.colonists if c.id == theirs0.id][0]
    check("越权移动指令被忽略（对方小人无路径）", not t0.path and t0.is_idle())
    check("越权后两端仍一致", p0.state_hash() == p1.state_hash())


if __name__ == "__main__":
    part_a()
    try:
        import pygame  # noqa: F401
        part_b()
    except ImportError:
        print("  （未安装 pygame，跳过 B 部分）")
    print("\n结果：", "全部通过" if not FAILS else f"失败 {len(FAILS)} 项: {FAILS}")
    sys.exit(1 if FAILS else 0)
