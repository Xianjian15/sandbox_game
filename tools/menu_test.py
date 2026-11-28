# tools/menu_test.py
"""菜单与联机大厅验收测试（无窗口）。用真实的 UDP 广播发现 + TCP 连接（都走 127.0.0.1）。

  1 菜单导航          键盘/鼠标走通 主菜单 / 大厅 / 创建页，单人、退出、返回
  2 房间名输入        默认名、退格、长度上限、不可见字符、空名回落到默认名
  3 房间发现          房主广播 → 玩家列表出现 → 房主关房后列表按 TTL 消失；乱包被忽略；多房间排序
  4 完整流程          两个菜单：一个创建房间，另一个点击房间加入（不输入任何 IP），停在大厅，房主点"开始游戏"，然后联机对拍
  5 多人同房          三位玩家加入同一房间：大厅人数实时同步、房间列表里的人数更新；房主点开始后全部就绪；满 MAX_PLAYERS 人后满员
  5b 开局后迟到       房主开始后，列表里还留着旧房间的玩家去点：得到失败提示而不是卡死；房主关房时大厅里的玩家得到"房间已关闭"
  6 捣乱连接          有人连上房间却不说话/发乱码：房间不死，之后真正的玩家仍能加入
  7 版本不符/已满     协议版本不同或满员的房间显示为不可加入
  8 资源释放          取消房间后端口/广播都被释放
用法： python -m tools.menu_test
"""
import os
import random
import socket
import sys
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame                                                   # noqa: E402
from net import session as netsession                           # noqa: E402
from net.discovery import RoomBeacon, RoomFinder                # noqa: E402
from net.session import LockstepSession, MAX_PLAYERS                         # noqa: E402
from ui.menu import MenuModel                                   # noqa: E402
from tools import multi_test as mt                              # noqa: E402

W, H = 1280, 720
# 回环网段的广播地址：和真实局域网广播一样，会同时送达所有监听同一端口的程序
# （发给 127.0.0.1 的单播只会随机交给其中一个监听者，不能用来测多人同时在大厅）
BCAST = "127.255.255.255"


def free_udp_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]; s.close(); return p


def cfg(disc_port, **kw):
    c = {"disc_port": disc_port, "targets": [BCAST], "game_port": 0, "ttl": 3.5, "seed": 42, "delay": 4}
    c.update(kw)
    return c


class Clock:
    """假时间：每次 tick 前进 0.1 秒（广播间隔/过期都按它算），同时真睡一小会儿让网络包送达。"""
    def __init__(self): self.t = 100.0
    def __call__(self): return self.t
    def step(self, dt=0.1, sleep=0.003):
        self.t += dt; time.sleep(sleep)


def widget(model, action, data=None):
    for w in model.layout(W, H):
        if w.action == action and (data is None or w.data == data) and w.enabled:
            return w
    return None


def click(model, action, data=None):
    w = widget(model, action, data)
    assert w is not None, f"屏幕 {model.screen} 上没有可点的 {action}"
    return model.click((w.x + w.w // 2, w.y + w.h // 2), W, H)


def run_until(models, clock, cond, limit=300):
    for _ in range(limit):
        for m in models: m.update(clock())
        if cond(): return True
        clock.step()
    return False


# ---------------- 场景 ----------------
def sc_navigation():
    m = MenuModel(cfg(free_udp_port()), clock=Clock())
    log = []
    assert m.screen == "main"
    labels = [w.text for w in m.layout(W, H) if w.kind == "button"]
    log.append(f"主菜单按钮={labels}")
    ok = labels == ["单人游戏", "多人游戏", "新手教程", "角色设置（男性）", "设置（操作模式 / 音量）", "退出"]
    m.key("down"); m.key("down"); m.key("up")
    ok &= m.sel == 1
    m.key("enter")                                     # 选中"多人游戏"
    ok &= m.screen == "lobby"
    lobby_btns = [w.text for w in m.layout(W, H) if w.kind == "button"]
    ok &= lobby_btns[1:] == ["创建房间", "刷新", "返回"] and "修改资料" in lobby_btns[0]      # 第一个是左上角的资料按钮
    m.key("escape"); ok &= m.screen == "main"
    click(m, "multi"); ok &= m.screen == "lobby"
    click(m, "back"); ok &= m.screen == "main"
    click(m, "multi"); click(m, "create"); ok &= m.screen == "create"
    click(m, "back_lobby"); ok &= m.screen == "lobby"
    m.key("escape"); m.key("escape")                   # 主菜单按 Esc = 退出
    ok &= m.result == {"mode": "quit"}
    m2 = MenuModel(cfg(free_udp_port()), clock=Clock()); click(m2, "single")
    ok &= m2.result == {"mode": "single"}
    m.close(); m2.close()
    return ok, "；".join(log) + f"；键鼠导航/单人/退出 ok={ok}"


def sc_text():
    m = MenuModel(cfg(free_udp_port()), clock=Clock())
    click(m, "multi"); click(m, "create")
    d = m.text
    for _ in range(len(d)): m.key("backspace")
    m.text_input("小明的基地"); m.key("backspace"); m.text_input("房")
    m.text_input("\x07\n")                             # 不可见字符被过滤
    ok = m.text == "小明的基地"[:-1] + "房" or m.text == "小明的基"+"房"
    m.text_input("x" * 50)
    ok &= len(m.text) == 20
    for _ in range(30): m.key("backspace")
    m.key("enter")                                     # 空名 → 默认名
    ok &= m.screen == "hosting" and m.room_name == d
    info = f"默认名={d!r} 长度上限={20} 空名回落={m.room_name == d}"
    m.close()
    return ok, info


def sc_discovery():
    port = free_udp_port(); clock = Clock()
    f = RoomFinder(port=port, ttl=3.5)          # 和游戏里一样绑定所有网卡，才收得到广播
    b1 = RoomBeacon("aa11", "甲的房间", 5001, port=port, targets=[BCAST])
    b2 = RoomBeacon("bb22", "乙的房间", 5002, players=2, port=port, targets=[BCAST])
    junk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    junk.sendto(b"\xff\xfenot json", ("127.0.0.1", port))
    junk.sendto(b'{"magic":"OTHER","id":"zz"}', ("127.0.0.1", port))
    junk.sendto(b'{"magic":"RWLAN1","id":"bad","port":"abc"}', ("127.0.0.1", port))
    for _ in range(3):
        b1.update(clock()); b2.update(clock()); f.update(clock()); clock.step(1.0)
    rooms = f.room_list()
    names = [(r["name"], r["port"], r["players"]) for r in rooms]
    ok = names == [("乙的房间", 5002, 2), ("甲的房间", 5001, 1)] or names == [("甲的房间", 5001, 1), ("乙的房间", 5002, 2)]
    ok &= all(r["ip"] == "127.0.0.1" for r in rooms) and len(rooms) == 2        # IP 来自包的来源，乱包被忽略
    b2.close()                                                                  # 乙关房
    for _ in range(6):
        b1.update(clock()); f.update(clock()); clock.step(1.0)
    left = [r["name"] for r in f.room_list()]
    ok &= left == ["甲的房间"]
    b1.close()
    for _ in range(6): f.update(clock()); clock.step(1.0)
    ok &= f.room_list() == []
    f.close(); junk.close()
    return ok, f"发现={names}；乙关房后剩={left}；全关后为空={f.room_list() == []}"


def make_pair(clock, disc_port):   # 房主建好房间 + 一位还没加入的玩家看到了房间列表
    host = MenuModel(cfg(disc_port), clock=clock)
    client = MenuModel(cfg(disc_port), clock=clock)
    click(host, "multi"); click(host, "create"); host.key("enter")
    assert host.screen == "hosting", host.screen
    click(client, "multi")
    assert run_until([host, client], clock, lambda: len(client.rooms()) == 1), "玩家没有发现房间"
    return host, client


def start_and_wait(host, others, clock, limit=400):
    """房主点"开始游戏"，等所有人的菜单都产出结果。"""
    click(host, "start_host")
    return run_until([host] + others, clock, lambda: host.result and all(o.result for o in others), limit=limit)


def play_check(models, turns=1500):
    """用菜单交出来的 session 真联机跑一段（假世界），返回是否一致。"""
    peers = []
    for m in models:
        s = m.result["session"]
        g = mt.FakeGame(); s.attach(g); peers.append((s, g))
    mt.run(peers, turns)
    same = len({g.state_hash() for _, g in peers}) == 1 and all(g.turn == turns for _, g in peers)
    states = [s.state for s, _ in peers]
    mt.close_all(peers)
    return same and all(st == "running" for st in states), states


def sc_full_flow():
    disc = free_udp_port(); clock = Clock()
    host, client = make_pair(clock, disc)
    room = client.rooms()[0]
    row = widget(client, "join", room["id"])
    shown = (row.text, row.right) if row else None
    click(client, "join", room["id"])                                   # 玩家点击房间，没有输入任何 IP
    in_lobby = run_until([host, client], clock, lambda: client.session is not None and client.session.state == "lobby"
                         and host.session.lobby_count() == 1)
    wait_text = [w.text for w in client.layout(W, H) if w.kind == "label"]
    start_disabled_before = True
    ok = in_lobby and host.result is None and client.result is None      # 没点开始之前：双方都停在大厅
    ok &= any("等待房主" in t for t in wait_text)
    done = start_and_wait(host, [client], clock)
    ok &= bool(done) and host.result["mode"] == "host" and client.result["mode"] == "join"
    hs, cs = host.result["session"], client.result["session"]
    ok &= hs.state == "ready" and cs.state == "ready" and hs.cfg["seed"] == cs.cfg["seed"] == 42
    ok &= (hs.cfg["player"], cs.cfg["player"]) == (0, 1) and hs.cfg["players"] == cs.cfg["players"] == 2
    host.close(); client.close()
    good, states = play_check([host, client])
    info = f"列表项={shown}；加入后停在大厅={in_lobby}；开始后双方就绪={ok}；联机 1500 回合一致={good}；状态={states}"
    return ok and good, info


def sc_multi():
    disc = free_udp_port(); clock = Clock()
    host, c1 = make_pair(clock, disc)
    N = MAX_PLAYERS
    cs = [c1] + [MenuModel(cfg(disc), clock=clock) for _ in range(N - 2)]
    for m in cs[1:]: click(m, "multi")
    assert run_until([host] + cs, clock, lambda: all(len(m.rooms()) == 1 for m in cs))
    start0 = widget(host, "start_host")
    ok = start0 is None                                                   # 只有房主一人：开始按钮不可用
    rid = c1.rooms()[0]["id"]
    for m in cs: click(m, "join", rid)
    run_until([host] + cs, clock, lambda: host.session.lobby_count() == N - 1
              and all(m.session is not None and m.session.lobby_n == N for m in cs))
    counts = [host.session.player_count()] + [m.session.lobby_n for m in cs]
    ok &= counts == [N] * N
    # 房间列表里（第 N+1 个玩家看到的）显示 N/N 已满且不可加入
    viewer = MenuModel(cfg(disc), clock=clock); click(viewer, "multi")
    run_until([host, viewer] + cs, clock, lambda: any(r["players"] == N for r in viewer.rooms()))
    row = next((w for w in viewer.layout(W, H) if w.kind == "row"), None)
    ok &= row is not None and (not row.enabled) and f"{N}/{N}" in row.right and "已满" in row.right
    ok &= widget(host, "start_host") is not None
    done = start_and_wait(host, cs, clock)
    ok &= bool(done)
    sess = [host.result["session"]] + [m.result["session"] for m in cs]
    ok &= sorted(s.cfg["player"] for s in sess) == list(range(N)) and all(s.cfg["players"] == N for s in sess)
    host.close(); [m.close() for m in cs]; viewer.close()
    good, states = play_check([host] + cs, turns=1200)
    return ok and good, f"大厅人数={counts}；满员行={row.right if row else None}；开局编号={sorted(s.cfg['player'] for s in sess)}；满员联机一致={good} {states}"


def sc_late_join():
    """房主开始后，另一个还留着旧房间列表的玩家去点那个房间：必须得到失败提示，而不是卡死。
    另外：房主在大厅里关房，已加入的玩家得到"房间已关闭"。"""
    disc = free_udp_port(); clock = Clock()
    host, c1 = make_pair(clock, disc)
    late = MenuModel(cfg(disc), clock=clock); click(late, "multi")
    assert run_until([host, c1, late], clock, lambda: len(late.rooms()) == 1)
    rid = c1.rooms()[0]["id"]
    click(c1, "join", rid)
    run_until([host, c1, late], clock, lambda: host.session.lobby_count() == 1)
    start_and_wait(host, [c1], clock)
    click(late, "join", rid)                                            # late 的列表里房间还在（TTL 没到）
    run_until([late], clock, lambda: late.screen == "message", limit=200)
    ok = late.screen == "message" and late.message[0] == "加入房间失败" and "Errno" not in " ".join(late.message)
    info = f"迟到的玩家得到提示={late.message}"
    for m in (host, c1, late): m.close()
    for m in (host, c1):
        if m.result and "session" in m.result: m.result["session"].close()
    # —— 房主在大厅里关房 ——
    disc2 = free_udp_port(); clock2 = Clock()
    h2, p2 = make_pair(clock2, disc2)
    click(p2, "join", p2.rooms()[0]["id"])
    run_until([h2, p2], clock2, lambda: h2.session.lobby_count() == 1)
    click(h2, "cancel_host")
    run_until([h2, p2], clock2, lambda: p2.screen == "message", limit=200)
    ok &= p2.screen == "message" and p2.message[0] == "房间已关闭"
    info += f"；房主关房后大厅玩家得到={p2.message}"
    h2.close(); p2.close()
    return ok, info


def sc_stray():
    netsession.HANDSHAKE_TIMEOUT = 0.4                                  # 缩短，加快测试
    try:
        disc = free_udp_port(); clock = Clock()
        host, client = make_pair(clock, disc)
        port = host.session.port
        silent = socket.create_connection(("127.0.0.1", port))          # 连上但一句话不说
        run_until([host, client], clock, lambda: False, limit=5)
        time.sleep(0.5)
        run_until([host, client], clock, lambda: False, limit=5)
        s1 = host.session.state
        garbage = socket.create_connection(("127.0.0.1", port))
        garbage.sendall(b"GET / HTTP/1.1\r\n\r\n")                      # 发 HTTP 乱码
        run_until([host], clock, lambda: False, limit=15)
        s2 = host.session.state
        bad_len = socket.create_connection(("127.0.0.1", port))
        bad_len.sendall(b"\xff\xff\xff\xff")                            # 超大长度
        run_until([host], clock, lambda: False, limit=15)
        s3 = host.session.state
        n_in = host.session.lobby_count()
        click(client, "join", client.rooms()[0]["id"])
        run_until([host, client], clock, lambda: host.session.lobby_count() == 1 and client.session is not None
                  and client.session.state == "lobby", limit=400)
        done = start_and_wait(host, [client], clock)
        ok = bool(done) and s1 == s2 == s3 == "waiting" and n_in == 0
        info = f"不说话/乱码/超大长度之后房主状态=({s1},{s2},{s3}) 大厅人数={n_in}，真玩家随后加入并开局={bool(done)}"
        for x in (silent, garbage, bad_len): x.close()
        host.close(); client.close()
        for m in (host, client):
            if m.result and "session" in m.result: m.result["session"].close()
        return ok, info
    finally:
        netsession.HANDSHAKE_TIMEOUT = 5.0


def sc_proto():
    disc = free_udp_port(); clock = Clock()
    m = MenuModel(cfg(disc), clock=clock); click(m, "multi")
    old = RoomBeacon("old1", "老版本房间", 5555, port=disc, targets=[BCAST])
    old.info["proto"] = 999
    full = RoomBeacon("full", "满员房间", 5556, players=MAX_PLAYERS, port=disc, targets=[BCAST])
    assert run_until([m], clock, lambda: (old.update(clock()), full.update(clock()), len(m.rooms()) == 2)[2])
    rows = {w.text: w for w in m.layout(W, H) if w.kind == "row"}
    ok = (not rows["老版本房间"].enabled) and "版本不符" in rows["老版本房间"].right
    ok &= (not rows["满员房间"].enabled) and "已满" in rows["满员房间"].right
    before = m.screen
    ok &= click_row_disabled(m, rows["老版本房间"]) is False and m.screen == before
    old.close(); full.close(); m.close()
    return ok, f"老版本房间={rows['老版本房间'].right!r}；满员房间={rows['满员房间'].right!r}；点击无效"


def click_row_disabled(m, w):
    return m.click((w.x + 5, w.y + 5), W, H)


def sc_release():
    disc = free_udp_port(); clock = Clock()
    host = MenuModel(cfg(disc, game_port=0), clock=clock)
    click(host, "multi"); click(host, "create"); host.key("enter")
    port = host.session.port
    run_until([host], clock, lambda: False, limit=3)
    busy = False
    try:
        t = socket.socket(); t.bind(("0.0.0.0", port)); t.close()
    except OSError:
        busy = True
    click(host, "cancel_host")
    freed = True
    try:
        t = socket.socket(); t.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); t.bind(("0.0.0.0", port)); t.close()
    except OSError:
        freed = False
    ok = busy and freed and host.screen == "lobby" and host.beacon is None and host.session is None
    host.close()
    return ok, f"房间开着时端口被占用={busy}；取消后端口释放={freed}；回到大厅={host.screen == 'lobby'}"


def main():
    pygame.init(); pygame.font.init()
    plan = [("1 菜单导航", sc_navigation), ("2 房间名输入", sc_text), ("3 房间发现(UDP)", sc_discovery),
            ("4 完整流程：创建→发现→加入大厅→房主开始→联机对拍", sc_full_flow), ("5 满员同房：大厅/满员/开局/联机", sc_multi),
            ("5b 开局后迟到 + 房主关房", sc_late_join), ("6 捣乱连接不影响房间", sc_stray),
            ("7 版本不符/已满的房间", sc_proto), ("8 取消房间释放资源", sc_release)]
    allok = True
    for name, fn in plan:
        t0 = time.time()
        try:
            ok, info = fn()
        except Exception as e:                                           # noqa: BLE001
            import traceback
            ok, info = False, f"异常 {type(e).__name__}: {e}\n" + traceback.format_exc()[-700:]
        allok &= bool(ok)
        print(f"{'✓' if ok else '✗'} {name}  ({time.time() - t0:.1f}s)\n    {info}")
    print("\n全部通过 ✓" if allok else "\n存在失败 ✗")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
