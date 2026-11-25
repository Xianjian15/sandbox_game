# tools/multi_test.py
"""多人（3~4 人）锁步验收测试。不依赖 pygame：用一个极小的"假世界"代替 GameWorld，
但走的是真实的 TCP 连接和真实的 LockstepSession（星形中继、大厅、掉线、踢人、分叉检测）。

场景：
  M1 四人联机      每人随机发指令，加随机卡顿；全程一致，每人的指令都被所有人执行
  M2 中途掉线      三人局里一位客户端突然断开；其余两人继续运行并保持一致
  M3 玩家卡死      一位客户端不再响应；主机超时把他请出去，其余人继续
  M4 三人分叉检测  一位客户端偷偷改状态；三个人都要报告"失去同步"
  M5 房间已满      第 5 位玩家被拒绝，不影响房间
  M6 大厅进出      有人进大厅又离开，人数同步更新；没人时不能开局
  M7 越权指令      客户端伪造别人的玩家编号 → 被踢出，其余人不受影响
  M8 主机退出      三人局里主机退出，客户端转单机、不崩溃
用法：  python -m tools.multi_test
"""
import hashlib
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import commands as cmdlib                      # noqa: E402
from net import session as S                             # noqa: E402
from net.session import LockstepSession                  # noqa: E402


class FakeGame:
    """和 GameWorld 对会话层暴露的接口一致：issue / receive_command / flush_commands / sim_step / state_hash…"""
    def __init__(self, player=0, delay=4):
        self.cmd_delay, self.local_player = delay, player
        self.turn, self.cmd_seq = 0, 0
        self.cmd_buffer, self.cmd_outbox = {}, []
        self.net_status = ""
        self.gone_players = set()
        self.applied = []
        self.bias = 0

    def issue(self, cmd):
        cmd = dict(cmd)
        self.cmd_seq += 1
        cmd["p"], cmd["s"], cmd["tick"] = self.local_player, self.cmd_seq, self.turn + self.cmd_delay
        cmdlib.validate(cmd)
        if self.cmd_delay == 0:
            self.applied.append((self.turn, cmd["p"], cmd["s"]))
        else:
            self.cmd_outbox.append(cmd)
            self.receive_command(cmd)

    def receive_command(self, cmd):
        self.cmd_buffer.setdefault(cmd["tick"], []).append(cmd)

    def flush_commands(self, force=False):
        due = [t for t in self.cmd_buffer if force or t <= self.turn]
        cmds = []
        for t in due:
            cmds += self.cmd_buffer.pop(t)
        for c in sorted(cmds, key=lambda c: (c["tick"], c["p"], c["s"])):
            self.applied.append((self.turn, c["p"], c["s"]))

    def sim_step(self):
        self.flush_commands()
        self.turn += 1

    def state_hash(self):
        return hashlib.sha256(repr((self.turn, self.applied, self.bias)).encode()).hexdigest()[:16]

    def state_sections(self):
        return {"applied": hashlib.sha256(repr(self.applied).encode()).hexdigest()[:8], "bias": str(self.bias)}


def lobby(n, expect=None, delay=4, profiles=None):
    """建房 + n-1 位玩家加入 + 开局 + 绑定假世界。返回 [(session, game)]，下标 = 玩家编号。"""
    profiles = profiles or [None] * n
    host = LockstepSession.host(port=0, seed=1, delay=delay, bind="127.0.0.1", expect=expect, profile=profiles[0])
    clients = [LockstepSession.join("127.0.0.1", host.port, profile=profiles[i + 1]) for i in range(n - 1)]
    t0 = time.time()
    while any(c.state not in ("lobby", "ready") for c in clients) or host.player_count() < n:
        host.pump(); [c.pump() for c in clients]
        time.sleep(0.0005)
        if time.time() - t0 > 5: raise RuntimeError("大厅超时")
    if expect is None:
        assert host.start_game()
    t0 = time.time()
    while host.state != "ready" or any(c.state != "ready" for c in clients):
        host.pump(); [c.pump() for c in clients]
        time.sleep(0.0005)
        if time.time() - t0 > 5: raise RuntimeError("开局超时")
    peers = []
    for s in [host] + clients:
        g = FakeGame()
        s.attach(g)
        peers.append((s, g))
    # 玩家编号按加入顺序：校验 attach 已把 local_player 设对
    assert [g.local_player for _, g in peers] == list(range(n)), [g.local_player for _, g in peers]
    return peers


def run(peers, turns, lag=None, rng_seed=5, cmd_rate=0.03, hook=None, stop=None, skip=()):
    rng = random.Random(rng_seed)
    lag = lag or {}
    guard = 0
    while True:
        order = list(range(len(peers)))
        rng.shuffle(order)
        progressed = False
        for i in order:
            if i in skip:
                continue
            s, g = peers[i]
            if s.state not in ("running", "verifying") or g.turn >= turns:
                s.pump(); continue
            if rng.random() < lag.get(i, 0.0):
                s.pump(); continue
            if s.state == "running" and rng.random() < cmd_rate:
                g.issue(cmdlib.make("move", ids=[i], tx=rng.randint(0, 50), ty=rng.randint(0, 50), q=False))
            if s.try_turn():
                progressed = True
                if hook: hook(i, s, g)
        live = [p for k, p in enumerate(peers) if k not in skip and p[0].state in ("running", "verifying")]
        if live and all(p[1].turn >= turns for p in live): return True
        if stop and stop(peers): return True
        if not live: return False
        if not progressed: time.sleep(0.0002)
        guard += 1
        if guard > 2_000_000: raise RuntimeError("循环超限，疑似死锁")


def close_all(peers):
    for s, _ in peers:
        s.close()


# ---------------- 场景 ----------------
def m1_four():
    peers = lobby(4)
    run(peers, 1500, lag={1: 0.3, 2: 0.5, 3: 0.1})
    hs = {g.state_hash() for _, g in peers}
    states = [s.state for s, _ in peers]
    who = {p for _, p, _ in peers[0][1].applied}
    ok = len(hs) == 1 and states == ["running"] * 4 and who == {0, 1, 2, 3} and all(g.turn == 1500 for _, g in peers)
    info = f"状态={states} 哈希种类={len(hs)} 被执行指令数={len(peers[0][1].applied)} 发令玩家={sorted(who)}"
    close_all(peers); return ok, info


def m2_drop():
    peers = lobby(3)
    flag = {}

    def hook(i, s, g):
        if i == 0 and g.turn == 600 and not flag:
            flag["x"] = 1
            peers[2][0].conns[0].sock.close()                 # 玩家 2 突然断线
    run(peers, 1800, hook=hook, skip=())
    (s0, g0), (s1, g1) = peers[0], peers[1]
    ok = (s0.state, s1.state) == ("running", "running") and g0.turn == g1.turn == 1800 \
        and g0.state_hash() == g1.state_hash() and 2 in s0.dropped and 2 in s1.dropped \
        and s0.dropped[2] == s1.dropped[2]
    late = [x for x in g0.applied if x[1] == 2 and x[0] > s0.dropped[2] + 4 + 1]
    info = f"主机={s0.state} 玩家1={s1.state} dropped={s0.dropped}/{s1.dropped} 离开后仍有他的指令={len(late)} 哈希一致={g0.state_hash() == g1.state_hash()}"
    close_all(peers); return ok and not late, info


def m3_stall():
    old = S.STALL_TIMEOUT
    S.STALL_TIMEOUT = 0.6
    try:
        peers = lobby(3)
        run(peers, 3000, skip=(2,), cmd_rate=0.02)
        (s0, g0), (s1, g1) = peers[0], peers[1]
        ok = (s0.state, s1.state) == ("running", "running") and g0.turn == g1.turn == 3000 \
            and 2 in s0.dropped and g0.state_hash() == g1.state_hash()
        info = f"主机={s0.state} 玩家1={s1.state} 玩家2 被踢出={2 in s0.dropped} 回合={g0.turn}/{g1.turn}"
        close_all(peers); return ok, info
    finally:
        S.STALL_TIMEOUT = old


def m4_desync():
    peers = lobby(3)
    flag = {}

    def hook(i, s, g):
        if i == 2 and g.turn == 300 and not flag:
            flag["x"] = 1
            g.bias += 1
    run(peers, 2000, hook=hook, stop=lambda ps: all(p[0].state == "desync" for p in ps))
    st = [s.state for s, _ in peers]
    secs = [s.desync_info["sections"] for s, _ in peers if s.desync_info]
    ok = st == ["desync"] * 3 and all(x == ["applied", "bias"] or x == ["bias"] or x == ["applied"] for x in secs)
    info = f"状态={st} 分叉分区={secs}"
    close_all(peers); return ok, info


def m5_full():
    host = LockstepSession.host(port=0, seed=1, delay=4, bind="127.0.0.1", expect=None)
    cl = [LockstepSession.join("127.0.0.1", host.port) for _ in range(S.MAX_PLAYERS - 1)]
    t0 = time.time()
    while host.lobby_count() < S.MAX_PLAYERS - 1 and time.time() - t0 < 3:
        host.pump(); [c.pump() for c in cl]; time.sleep(0.001)
    extra = LockstepSession.join("127.0.0.1", host.port)
    t0 = time.time()
    while extra.state != "failed" and time.time() - t0 < 3:
        host.pump(); [c.pump() for c in cl]; extra.pump(); time.sleep(0.001)
    ok = extra.state == "failed" and "已满" in extra.error and host.lobby_count() == S.MAX_PLAYERS - 1 \
        and all(c.state == "lobby" and c.lobby_n == S.MAX_PLAYERS for c in cl)
    info = f"多出的玩家={extra.state}（{extra.error}） 大厅人数={host.player_count()} 各客户端看到人数={[c.lobby_n for c in cl]}"
    for s in [host, extra] + cl: s.close()
    return ok, info


def m6_lobby():
    host = LockstepSession.host(port=0, seed=1, delay=4, bind="127.0.0.1", expect=None)
    no_start = host.start_game() is False
    a = LockstepSession.join("127.0.0.1", host.port)
    b = LockstepSession.join("127.0.0.1", host.port)
    t0 = time.time()
    while host.lobby_count() < 2 and time.time() - t0 < 3:
        host.pump(); a.pump(); b.pump(); time.sleep(0.001)
    n2 = (host.player_count(), a.lobby_n, b.lobby_n)
    b.close()
    t0 = time.time()
    while host.lobby_count() > 1 and time.time() - t0 < 3:
        host.pump(); a.pump(); time.sleep(0.001)
    for _ in range(50): host.pump(); a.pump(); time.sleep(0.001)
    n1 = (host.player_count(), a.lobby_n, host.state)
    started = host.start_game()
    cfg_ok = False
    t0 = time.time()
    while a.state != "ready" and time.time() - t0 < 3:
        host.pump(); a.pump(); time.sleep(0.001)
    cfg_ok = a.state == "ready" and a.cfg["players"] == 2 and a.cfg["player"] == 1
    late = LockstepSession.join("127.0.0.1", host.port)       # 开局后监听口已关
    ok = no_start and n2 == (3, 3, 3) and n1 == (2, 2, "lobby") and started and cfg_ok and late.state == "failed"
    info = f"没人不能开局={no_start} 3人时={n2} b离开后={n1} 开局={started} 客户端cfg={a.cfg} 开局后加入={late.state}"
    for s in (host, a, b, late): s.close()
    return ok, info


def m7_illegal():
    peers = lobby(3)
    run(peers, 400)
    bad = peers[1][0]
    bad._send({"m": "turn", "c": bad.sent_turn + 1, "cmds": [{"t": "speed", "v": 3, "p": 2, "s": 1, "tick": bad.sent_turn + 5}]})
    run(peers, 900)
    (s0, g0), (s2, g2) = peers[0], peers[2]
    ok = 1 in s0.dropped and s0.state == "running" and s2.state == "running" and 1 in s2.dropped \
        and g0.turn == g2.turn == 900 and g0.state_hash() == g2.state_hash() and bad.state in ("failed", "disconnected")
    info = f"主机={s0.state} 玩家2={s2.state} 作弊者={bad.state}（{bad.error}） dropped={s0.dropped}"
    close_all(peers); return ok, info


def m8_host_quits():
    peers = lobby(3)
    run(peers, 300)
    peers[0][0].close()
    for _ in range(300):
        for s, _ in peers[1:]: s.pump()
        time.sleep(0.001)
    st = [s.state for s, _ in peers[1:]]
    g = peers[1][1]
    err = None
    try:
        for _ in range(200): g.sim_step()
    except Exception as e:                      # noqa: BLE001
        err = e
    ok = st == ["disconnected", "disconnected"] and g.cmd_delay == 0 and err is None
    info = f"客户端状态={st} cmd_delay={g.cmd_delay} 提示={g.net_status} 异常={err}"
    close_all(peers); return ok, info


def main():
    plan = [("M1 四人联机(随机卡顿)", m1_four), ("M2 中途掉线", m2_drop), ("M3 玩家卡死被踢", m3_stall),
            ("M4 三人分叉检测", m4_desync), ("M5 房间已满", m5_full), ("M6 大厅进出/开局", m6_lobby),
            ("M7 越权指令被踢", m7_illegal), ("M8 主机退出", m8_host_quits)]
    allok = True
    for name, fn in plan:
        t0 = time.time()
        try:
            ok, info = fn()
        except Exception as e:                  # noqa: BLE001
            import traceback
            ok, info = False, f"异常 {type(e).__name__}: {e}\n" + traceback.format_exc()[-700:]
        allok = allok and ok
        print(f"{'✓' if ok else '✗'} {name}  ({time.time() - t0:.1f}s)\n    {info}")
    print("\n全部通过 ✓" if allok else "\n存在失败 ✗")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
