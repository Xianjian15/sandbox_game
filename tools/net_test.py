# tools/net_test.py
"""联机层验收测试：真实的 TCP 连接（127.0.0.1），两个世界在同一个进程里，单线程轮流推进。

场景：
  A 正常联机        两端各操作一半指令（复用 command_test 的脚本），全程哈希一致
  B 随机卡顿        每端随机"卡住"若干帧，锁步必须自动等待、不分叉
  C 字节流碎片化    中间插一个代理，把数据切成 1~12 字节的小块转发，考验封包重组
  D 分叉检测        故意改掉一端的一点点状态，两端必须在下一个检查点报"失去同步"并停下
  E 掉线转单机      一端突然断开，另一端转为单机继续运行，已收到的指令不丢
  F 版本不一致      两端初始状态不同，必须拒绝联机
  G 非法数据        乱码长度、伪造玩家编号、错误回合号，必须被拒绝而不是崩溃/污染状态
用法：  python -m tools.net_test
退出码：0 = 全部通过。
"""
import os
import random
import socket
import sys
import threading
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame                                                    # noqa: E402
from net.framing import FrameBuffer, ProtocolError, pack         # noqa: E402
from net.session import LockstepSession                          # noqa: E402
from settings import INIT_W, INIT_H                              # noqa: E402
from world.game_world import GameWorld                           # noqa: E402
from tools import command_test as ct                             # noqa: E402

TURNS = 11000          # 足够让研究、农田等指令全部生效


# ---------------- 辅助 ----------------
class ChunkProxy(threading.Thread):
    """把字节流切成随机小块转发的代理。"""
    def __init__(self, target_port, seed=7):
        super().__init__(daemon=True)
        self.rng = random.Random(seed)
        self.srv = socket.socket(); self.srv.bind(("127.0.0.1", 0)); self.srv.listen(1)
        self.port = self.srv.getsockname()[1]
        self.target = target_port
        self.socks = []

    def run(self):
        try:
            a, _ = self.srv.accept()
            b = socket.create_connection(("127.0.0.1", self.target))
        except OSError:
            return
        self.socks += [a, b]
        for src, dst in ((a, b), (b, a)):
            threading.Thread(target=self._pump, args=(src, dst), daemon=True).start()

    def _pump(self, src, dst):
        try:
            while True:
                data = src.recv(4096)
                if not data:
                    break
                i = 0
                while i < len(data):
                    n = self.rng.randint(1, 12)
                    dst.sendall(data[i:i + n]); i += n
                    if self.rng.random() < 0.01:
                        time.sleep(0.001)
        except OSError:
            pass
        for s in (src, dst):
            try: s.close()
            except OSError: pass


def make_world(cfg, tweak=None):
    pygame.font.init()
    f = pygame.font.Font(None, 16)
    g = GameWorld(f, f, f, f, INIT_W, INIT_H, seed=cfg["seed"], map_seed=cfg["map_seed"],
                  cmd_delay=cfg["delay"], local_player=cfg["player"], num_players=2)
    s = ct.setup(g)
    if tweak: tweak(g)
    return g, s


def connect_pair(proxy=False, delay=4):
    host = LockstepSession.host(port=0, seed=42, delay=delay, bind="127.0.0.1")
    px = None
    port = host.port
    if proxy:
        px = ChunkProxy(host.port); px.start(); port = px.port
    client = LockstepSession.join("127.0.0.1", port)
    assert client.state == "handshake", client.error
    t0 = time.time()
    while not (host.state == "ready" and client.state == "ready"):
        host.pump(); client.pump()
        time.sleep(0.0005)
        if time.time() - t0 > 5: raise RuntimeError(f"握手超时 host={host.state} client={client.state}")
    return host, client, px


def build_game(sessions, tweaks=(None, None)):
    peers = []
    for sess, tw in zip(sessions, tweaks):
        g, s = make_world(sess.cfg, tw)
        sess.attach(g)
        peers.append((sess, g, s))
    return peers


def run_game(peers, turns=TURNS, lag=(0.0, 0.0), rng_seed=1, hook=None, stop_when=None):
    """单线程轮流推进两端。lag[i]：第 i 端每次迭代被"卡住"的概率。"""
    rng = random.Random(rng_seed)
    ops = sorted(ct.OPS, key=lambda o: o[0])
    env = dict(ct.ENV)
    done_env = [set(), set()]
    oi = [0, 0]
    guard = 0
    while True:
        progressed = False
        for i in rng.sample([0, 1], 2):
            sess, g, s = peers[i]
            if sess.state not in ("running", "verifying") or g.turn >= turns:
                sess.pump()
                continue
            if rng.random() < lag[i]:
                sess.pump(); continue
            while oi[i] < len(ops) and ops[oi[i]][0] <= g.turn:
                _, player, fn = ops[oi[i]]
                oi[i] += 1
                if player == i:
                    fn(g, s)
            for t, fn in env.items():
                if g.turn == t and t not in done_env[i]:
                    done_env[i].add(t); fn(g, s)
            if sess.try_turn():
                progressed = True
                if hook: hook(i, sess, g)
        if all(p[1].turn >= turns for p in peers): return True
        if stop_when and stop_when(peers): return True
        if all(p[0].state not in ("running", "verifying") for p in peers): return False
        if not progressed:
            time.sleep(0.0002)
        guard += 1
        if guard > 3_000_000: raise RuntimeError("循环超限，疑似死锁")


def final_equal(peers):
    (_, g0, _), (_, g1, _) = peers
    return g0.turn == g1.turn and g0.state_hash() == g1.state_hash()


def close_all(*sessions):
    for s in sessions:
        s.close()


# ---------------- 场景 ----------------
def sc_framing():
    rng = random.Random(3)
    msgs = [{"m": "turn", "c": i, "cmds": [{"t": "move", "ids": [1], "tx": i, "ty": 2, "q": False,
                                           "p": 0, "s": i, "tick": i + 4}] * (i % 3)} for i in range(400)]
    wire = b"".join(pack(m) for m in msgs)
    fb = FrameBuffer(); out = []; i = 0
    while i < len(wire):
        n = rng.randint(1, 40); out += fb.feed(wire[i:i + n]); i += n
    ok = out == msgs
    bad = 0
    for junk in (b"\xff\xff\xff\xff" + b"x" * 10, (5).to_bytes(4, "big") + b"notjs"):
        try: FrameBuffer().feed(junk)
        except ProtocolError: bad += 1
    return ok and bad == 2, f"400 条消息随机切块重组一致={ok}；乱码被拒绝 {bad}/2"


def sc_normal(lag=(0.0, 0.0), proxy=False, delay=4, turns=TURNS):
    host, client, px = connect_pair(proxy=proxy, delay=delay)
    peers = build_game([host, client])
    ok = run_game(peers, turns=turns, lag=lag)
    same = final_equal(peers)
    st = (host.state, client.state)
    info = f"turn={peers[0][1].turn} 状态={st} 哈希一致={same} 实际推进 host={host.turns_run} client={client.turns_run}"
    eff_ok = True
    if turns >= TURNS:            # 跑够长时，核对两端的指令都真的生效了（不是"什么都没发生所以一致"）
        e0, e1 = ct.effects(peers[0][1]), ct.effects(peers[1][1])
        eff_ok = all(e0.values()) and e0 == e1
        info += "  生效核对: " + " ".join(f"{k}={'✓' if v else '✗'}" for k, v in e0.items())
    close_all(host, client)
    return ok and same and eff_ok and st == ("running", "running"), info


def sc_desync():
    host, client, _ = connect_pair()
    peers = build_game([host, client])
    flag = {"done": False}

    def hook(i, sess, g):
        if i == 1 and g.turn == 1500 and not flag["done"]:
            flag["done"] = True
            g.animals[0].x += 0.5          # 悄悄让客户端的一只动物偏移半个像素
    run_game(peers, hook=hook, stop_when=lambda ps: all(p[0].state == "desync" for p in ps))
    st = (host.state, client.state)
    sec = host.desync_info["sections"] if host.desync_info else None
    t = host.desync_info["turn"] if host.desync_info else None
    stopped = host.try_turn() is False and client.try_turn() is False
    ok = st == ("desync", "desync") and sec == ["animals"] and t is not None and 1500 <= t < 1500 + 120 and stopped
    info = f"状态={st} 报告的回合={t} 分叉分区={sec} 之后不再推进={stopped}"
    close_all(host, client)
    return ok, info


def sc_disconnect():
    host, client, _ = connect_pair()
    peers = build_game([host, client])
    flag = {"done": False}

    def hook(i, sess, g):
        if i == 0 and g.turn == 2500 and not flag["done"]:
            flag["done"] = True
            client.sock.close()            # 客户端突然断开
    run_game(peers, hook=hook, stop_when=lambda ps: ps[0][0].state == "disconnected")
    # 主机继续单机运行 600 个回合
    g = peers[0][1]
    t0 = g.turn
    err = None
    try:
        for _ in range(600): g.sim_step()
    except Exception as e:                  # noqa: BLE001
        err = e
    ok = host.state == "disconnected" and g.cmd_delay == 0 and err is None and g.turn == t0 + 600 and "单机" in g.net_status
    info = f"主机状态={host.state}（{host.error}）转单机 cmd_delay={g.cmd_delay} 继续运行 600 回合 异常={err}"
    close_all(host, client)
    return ok, info


def sc_mismatch():
    host, client, _ = connect_pair()

    def tweak(g):
        g.items.add("wood", 7, 1, 1)       # 只有一端多了一堆木头
    peers = build_game([host, client], tweaks=(None, tweak))
    t0 = time.time()
    while time.time() - t0 < 2 and not all(s.state == "mismatch" for s in (host, client)):
        host.pump(); client.pump(); time.sleep(0.0005)
    ok = (host.state, client.state) == ("mismatch", "mismatch")
    info = f"状态=({host.state}, {client.state}) 提示={host.error}"
    close_all(host, client)
    return ok, info


def sc_illegal():
    results = []
    for name, mk in [
        ("伪造玩家编号", lambda cl: {"m": "turn", "c": 0, "cmds": [{"t": "speed", "v": 3, "p": 0, "s": 1, "tick": 4}]}),
        ("错误执行回合", lambda cl: {"m": "turn", "c": 0, "cmds": [{"t": "speed", "v": 3, "p": 1, "s": 1, "tick": 99}]}),
        ("回合号跳跃", lambda cl: {"m": "turn", "c": 5, "cmds": []}),
        ("含 float 的指令", lambda cl: {"m": "turn", "c": 0, "cmds": [{"t": "move", "ids": [1], "tx": 1.5, "ty": 2, "q": False, "p": 1, "s": 1, "tick": 4}]}),
        ("未知指令类型", lambda cl: {"m": "turn", "c": 0, "cmds": [{"t": "format_disk", "p": 1, "s": 1, "tick": 4}]}),
    ]:
        host, client, _ = connect_pair()
        peers = build_game([host, client])
        for _ in range(200):
            host.pump(); client.pump()
        before = peers[0][1].state_hash()
        client._send(mk(client))           # 客户端发一个恶意/错误的包
        for _ in range(200):
            host.pump(); time.sleep(0.0005)
            if host.state in ("failed", "disconnected"): break
        clean = peers[0][1].state_hash() == before and not peers[0][1].cmd_buffer
        results.append((name, host.state == "failed" and clean))
        close_all(host, client)
    ok = all(r for _, r in results)
    return ok, "；".join(f"{n}:{'拒绝✓' if r else '未拒绝✗'}" for n, r in results)


def sc_version():
    """游戏版本号不同的玩家必须被拒绝（并告诉他双方版本），而且房间不受影响，正确版本的玩家仍能加入。"""
    from net import session as netsession
    host = LockstepSession.host(port=0, seed=42, delay=4, bind="127.0.0.1")
    orig = netsession.GAME_VERSION
    netsession.GAME_VERSION = "9.9.9"                 # 只在"客户端发 hello"这一刻伪装成另一个版本
    try:
        bad = LockstepSession.join("127.0.0.1", host.port)
    finally:
        netsession.GAME_VERSION = orig
    t0 = time.time()
    while bad.state != "failed" and time.time() - t0 < 3:
        host.pump(); bad.pump(); time.sleep(0.001)
    rejected = bad.state == "failed" and "9.9.9" in bad.error and orig in bad.error
    still_open = host.state == "waiting" and host.listen_sock is not None
    good = LockstepSession.join("127.0.0.1", host.port)
    t0 = time.time()
    while not (host.state == "ready" and good.state == "ready") and time.time() - t0 < 3:
        host.pump(); good.pump(); time.sleep(0.001)
    joined = host.state == "ready" and good.state == "ready"
    info = f"错误版本被拒绝={rejected}（提示：{bad.error}）；房间仍开着={still_open}；正确版本随后加入={joined}"
    close_all(host, bad, good)
    return rejected and still_open and joined, info


def main():
    pygame.init(); pygame.font.init()
    plan = [
        ("封包重组/乱码", sc_framing),
        ("A 正常联机", lambda: sc_normal()),
        ("B 随机卡顿(一端 30%/另一端 60%)", lambda: sc_normal(lag=(0.3, 0.6))),
        ("B2 极小输入延迟(delay=1)+卡顿", lambda: sc_normal(lag=(0.2, 0.5), delay=1)),
        ("C 字节流碎片化代理(2500 回合)", lambda: sc_normal(proxy=True, turns=2500)),
        ("D 分叉检测", sc_desync),
        ("E 掉线转单机", sc_disconnect),
        ("F 版本不一致", sc_mismatch),
        ("G 非法数据", sc_illegal),
        ("H 游戏版本号不同", sc_version),
    ]
    allok = True
    for name, fn in plan:
        t0 = time.time()
        try:
            ok, info = fn()
        except Exception as e:                                   # noqa: BLE001
            import traceback
            ok, info = False, f"异常 {type(e).__name__}: {e}\n" + traceback.format_exc()[-600:]
        allok = allok and ok
        print(f"{'✓' if ok else '✗'} {name}  ({time.time() - t0:.1f}s)\n    {info}")
    print("\n全部通过 ✓" if allok else "\n存在失败 ✗")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
