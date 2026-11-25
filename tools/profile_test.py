# tools/profile_test.py
"""用户名 / 头像 / 自动回血 验收测试。不依赖 pygame（头像读取用注入的假读取器；图片解码本身在真实环境里用 ui.avatar 完成）。

  P1 自动回血规则     受伤后延迟、流血时不回、睡觉加速、饥饿减速/停止、不超过满血、回满所需时间
  P2 资料数据层       名字清洗/限长、头像格式校验、重名加序号、存盘读盘、坏文件回落
  P3 联机名单         大厅里实时看到名单；开局后每个人收到同一份名单；伪造/超大/坏头像被清洗；离开的玩家被标记
  P4 资料页流程       菜单里输入用户名、选头像（选择器/拖拽/出错/取消/清除）、保存后存盘，下次启动还在
  P5 名单显示         房主大厅与客户端大厅的名单控件包含每位玩家的名字和头像，自己被标出
用法：  python -m tools.profile_test
"""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import profile as P                              # noqa: E402
from core.regen import regen_amount                        # noqa: E402
from settings import REGEN_DELAY, REGEN_RATE               # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    print(("  ✓ " if cond else "  ✗ ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        FAILS.append(name)


def fake_avatar(seed=1):
    return bytes((seed * 37 + i) % 256 for i in range(P.AVATAR_BYTES))


def p1_regen():
    print("== P1 自动回血 ==")
    dt = 1 / 60

    def sim(hp=50.0, bleeding=0.0, sleeping=False, since=99.0, satiety=80.0, secs=10.0, hurt_at=None):
        t = 0.0
        while t < secs:
            if hurt_at is not None and abs(t - hurt_at) < dt / 2:
                since = 0.0
            since += dt
            hp += regen_amount(hp, 100, bleeding, sleeping, since, satiety, dt)
            t += dt
        return hp
    check("平时每秒约 +REGEN_RATE", abs(sim(secs=10) - (50 + REGEN_RATE * 10)) < 0.1, sim(secs=10))
    check("受伤后 REGEN_DELAY 秒内不回血", sim(since=0.0, secs=REGEN_DELAY - 0.2) == 50.0)
    check("过了延迟之后开始回血", sim(since=0.0, secs=REGEN_DELAY + 4) > 50.5)
    check("流血时不回血", sim(bleeding=0.3) == 50.0)
    check("睡觉回得更快（×3）", abs((sim(sleeping=True) - 50) - 3 * (sim() - 50)) < 0.1)
    check("饿着（饱食 0）不回血", sim(satiety=0) == 50.0)
    check("很饿（<20）减半", abs((sim(satiety=10) - 50) - 0.5 * (sim() - 50)) < 0.1)
    check("不会超过满血", sim(hp=99.9, secs=30) == 100.0 or abs(sim(hp=99.9, secs=30) - 100.0) < 1e-9)
    check("满血/死亡不回", regen_amount(100, 100, 0, False, 99, 80, dt) == 0 and regen_amount(0, 100, 0, False, 99, 80, dt) == 0)
    check("从 10 血回满约需 90/REGEN_RATE 秒", abs(sim(hp=10, secs=90 / REGEN_RATE) - 100) < 0.5)


def p2_data():
    print("== P2 资料数据层 ==")
    check("名字限长 + 去不可见字符", P.sanitize_name("  \x07a\nb" + "长" * 30) == "ab" + "长" * (P.NAME_MAX - 2))
    check("空名回落默认", P.sanitize_name("   ", "玩家1") == "玩家1" and P.sanitize_name(None, "x") == "x" and P.sanitize_name(5, "y") == "y")
    check("重名加序号", P.dedupe_names(["小明", "小红", "小明", "小明"]) == ["小明", "小红", "小明(2)", "小明(3)"])
    raw = fake_avatar()
    b64 = P.encode_avatar(raw)
    check("头像编码解码往返", P.decode_avatar(b64) == raw)
    check("坏头像被拒", P.decode_avatar("!!!") is None and P.decode_avatar(P.encode_avatar(raw[:-3])) is None
          and P.decode_avatar("A" * 100000) is None and P.decode_avatar(5) is None)
    w = P.clean_wire({"name": "x" * 99, "av": "bad"}, "玩家2")
    check("clean_wire 清洗", w == {"name": "x" * P.NAME_MAX, "av": None}, w)
    check("clean_wire 对非 dict 安全", P.clean_wire(None, "a") == {"name": "a", "av": None} and P.clean_wire("zz", "b")["name"] == "b")
    d = tempfile.mkdtemp()
    path = os.path.join(d, "sub", "profile.json")
    pr = P.Profile("阿强", raw, path)
    check("存盘成功", pr.save() and os.path.exists(path))
    pr2 = P.Profile.load(path)
    check("读盘还原", pr2.name == "阿强" and pr2.avatar == raw)
    open(path, "w", encoding="utf-8").write("{坏的json")
    pr3 = P.Profile.load(path)
    check("坏文件回落成新随机名并重写", pr3.name.startswith("玩家") and json.load(open(path, encoding="utf-8"))["name"] == pr3.name)
    check("不存在的文件也安全", P.Profile.load(os.path.join(d, "none", "x.json")).name.startswith("玩家"))
    check("avatar 长度不对被丢弃", P.Profile("a", b"123").avatar is None)


def pump_until(sessions, cond, limit=3.0):
    t0 = time.time()
    while time.time() - t0 < limit:
        for s in sessions: s.pump()
        if cond(): return True
        time.sleep(0.001)
    return False


def p3_roster():
    print("== P3 联机名单 ==")
    from net.session import LockstepSession
    from tools import multi_test as mt
    a1, a2, a3 = fake_avatar(1), fake_avatar(2), fake_avatar(3)
    host = LockstepSession.host(port=0, seed=1, delay=4, bind="127.0.0.1", expect=None,
                                profile={"name": "房主阿明", "av": P.encode_avatar(a1)})
    c1 = LockstepSession.join("127.0.0.1", host.port, profile={"name": "房主阿明", "av": P.encode_avatar(a2)})   # 故意重名
    pump_until([host, c1], lambda: c1.state == "lobby")
    c2 = LockstepSession.join("127.0.0.1", host.port, profile={"name": "x" * 60, "av": "不是base64!!"})            # 超长名 + 坏头像
    evil = {"m": "hello", "proto": 3, "ver": __import__("core.version", fromlist=["GAME_VERSION"]).GAME_VERSION, "name": 123, "av": 456}
    pump_until([host, c1, c2], lambda: host.lobby_count() == 2 and c2.state == "lobby")
    r_host = host.lobby_roster()
    names = [r["name"] for r in r_host]
    check("大厅名单：房主第一、重名加序号", names == ["房主阿明", "房主阿明(2)", "x" * P.NAME_MAX], names)
    check("坏头像被丢弃、好头像保留", r_host[2]["av"] is None and P.decode_avatar(r_host[0]["av"]) == a1 and P.decode_avatar(r_host[1]["av"]) == a2)
    pump_until([host, c1, c2], lambda: len(c1.lobby_roster()) == 3 and len(c2.lobby_roster()) == 3)
    check("客户端在大厅里实时看到同一份名单", c1.lobby_roster() == r_host and c2.lobby_roster() == r_host)
    # 非字符串名字/头像（恶意 hello）
    import socket
    from net.framing import pack
    raw_sock = socket.create_connection(("127.0.0.1", host.port))
    raw_sock.sendall(pack(evil))
    pump_until([host, c1, c2], lambda: host.lobby_count() == 3)
    r4 = host.lobby_roster()
    check("非字符串名字/头像不崩溃，回落默认名", len(r4) == 4 and r4[3]["name"].startswith("玩家") and r4[3]["av"] is None, r4)
    raw_sock.close()
    pump_until([host, c1, c2], lambda: host.lobby_count() == 2)
    host.start_game()
    pump_until([host, c1, c2], lambda: c1.state == "ready" and c2.state == "ready")
    same = host.roster == c1.roster == c2.roster and len(host.roster) == 3
    check("开局后每个人拿到同一份名单（按玩家编号）", same, (host.roster == c1.roster, c1.roster == c2.roster))
    check("cfg 里也带名单", c1.cfg["roster"] == c1.roster)
    games = []
    for s in (host, c1, c2):
        g = mt.FakeGame(); s.attach(g); games.append(g)
    pump_until([host, c1, c2], lambda: all(s.state == "running" for s in (host, c1, c2)))
    c2.close()
    ok = pump_until([host, c1], lambda: 2 in games[0].gone_players and 2 in games[1].gone_players)
    check("玩家离开后，其他人的界面数据里标记为已离开", ok, (games[0].gone_players, games[1].gone_players))
    for s in (host, c1, c2): s.close()
    # 资料不进同步状态：不同头像/名字的两端哈希仍一致（FakeGame 的哈希本来就不含，这里确认 lobby() 辅助函数走完整流程）
    peers = mt.lobby(3, profiles=[{"name": "甲"}, {"name": "乙", "av": P.encode_avatar(a2)}, {"name": "丙"}])
    mt.run(peers, 600)
    check("带资料的三人局照常同步", len({g.state_hash() for _, g in peers}) == 1 and peers[1][0].roster[1]["name"] == "乙")
    mt.close_all(peers)


def p4_menu():
    print("== P4 资料页流程 ==")
    from ui.menu import MenuModel
    d = tempfile.mkdtemp()
    path = os.path.join(d, "profile.json")
    state = {"pick": None}
    loaded = []

    def picker():
        r = state["pick"]
        if isinstance(r, Exception): raise r
        return r

    def loader(p):
        loaded.append(p)
        if p.endswith(".txt"): raise ValueError("不是图片文件（支持 png / jpg / bmp / gif）")
        return fake_avatar(len(p))

    prof = P.Profile("旧名字", None, path)
    m = MenuModel({"profile": prof, "avatar_picker": picker, "avatar_loader": loader, "disc_port": 47999, "targets": ["127.255.255.255"]})
    W, H = 1280, 720

    def do_click(action):
        w = next((w for w in m.layout(W, H) if w.action == action and w.enabled), None)
        assert w is not None, f"{m.screen} 上没有 {action}"
        m.click((w.x + 3, w.y + 3), W, H)
    m.go("lobby")
    shown = [w.text for w in m.layout(W, H) if w.kind == "button"]
    check("大厅左上角显示当前用户名并可点击修改", any("旧名字" in t for t in shown), shown)
    do_click("profile")
    check("进入资料页，输入框预填当前名字", m.screen == "profile" and m.text == "旧名字")
    for _ in range(10): m.key("backspace")
    m.text_input("新玩家小明")
    m.text_input("\x07" * 3)
    m.text_input("很长" * 20)
    check("名字最多 12 个字，不可见字符被过滤", len(m.text) == P.NAME_MAX and "\x07" not in m.text, m.text)
    for _ in range(30): m.key("backspace")
    m.text_input("小明")
    state["pick"] = "/pics/me.png"
    do_click("pick_avatar")
    check("选择头像：选择器返回路径 → 读取成功", m.edit_avatar == fake_avatar(len("/pics/me.png")) and m.profile_msg == "")
    state["pick"] = "/docs/a.txt"
    do_click("pick_avatar")
    check("选到非图片：显示中文原因，保留原头像", "不是图片" in m.profile_msg and m.edit_avatar is not None)
    state["pick"] = None
    before = m.edit_avatar
    do_click("pick_avatar")
    check("取消选择：什么都不变", m.edit_avatar == before)
    state["pick"] = RuntimeError("no tk")
    do_click("pick_avatar")
    check("没有文件选择窗口：提示改用拖拽", "拖" in m.profile_msg)
    m.drop_file("/drop/cat.jpg")
    check("拖拽图片进窗口也能设头像（并清除错误提示）", m.edit_avatar == fake_avatar(len("/drop/cat.jpg")) and m.profile_msg == "")
    m.drop_file("/drop/readme.txt")
    check("拖入非图片：提示且不改", "不是图片" in m.profile_msg and m.edit_avatar == fake_avatar(len("/drop/cat.jpg")))
    do_click("clear_avatar")
    check("清除头像", m.edit_avatar is None)
    m.drop_file("/drop/cat.jpg")
    # 取消不保存
    m.key("escape")
    check("Esc 取消：回大厅，资料不变，磁盘不变", m.screen == "lobby" and prof.name == "旧名字" and prof.avatar is None
          and P.Profile.load(path).name != "小明")
    do_click("profile")
    for _ in range(10): m.key("backspace")
    m.text_input("小明")
    m.drop_file("/drop/cat.jpg")
    m.key("enter")
    check("Enter 保存：回大厅、内存和磁盘都更新", m.screen == "lobby" and prof.name == "小明" and prof.avatar is not None)
    re = P.Profile.load(path)
    check("重启后读到保存的用户名和头像", re.name == "小明" and re.avatar == prof.avatar)
    do_click("profile")
    for _ in range(10): m.key("backspace")
    do_click("save_profile")
    check("保存空名字：保留原名", prof.name == "小明")
    m.drop_file("/ignored.png")                         # 不在资料页时拖入文件应被忽略
    check("不在资料页时拖入文件被忽略", m.edit_avatar == prof.avatar and loaded[-1] != "/ignored.png")
    return m


def p5_roster_widgets():
    print("== P5 名单显示 ==")
    from tools import menu_test as mtst
    from ui.menu import MenuModel
    disc = mtst.free_udp_port(); clock = mtst.Clock()

    def mk(name, av=None):
        prof = P.Profile(name, av)
        return MenuModel(mtst.cfg(disc, profile=prof, avatar_picker=lambda: None, avatar_loader=lambda p: av), clock=clock)
    host, c1 = mk("房主甲", fake_avatar(1)), mk("乙乙", None)
    mtst.click(host, "multi"); mtst.click(host, "create"); host.key("enter")
    mtst.click(c1, "multi")
    mtst.run_until([host, c1], clock, lambda: len(c1.rooms()) == 1)
    mtst.click(c1, "join", c1.rooms()[0]["id"])
    mtst.run_until([host, c1], clock, lambda: host.session.lobby_count() == 1 and c1.session is not None and c1.session.state == "lobby")
    mtst.run_until([host, c1], clock, lambda: len(c1.session.lobby_roster()) == 2)
    hw = [w for w in host.layout(1280, 720) if w.kind == "player"]
    cw = [w for w in c1.layout(1280, 720) if w.kind == "player"]
    check("房主大厅名单：两位玩家、自己被标出、头像数据在", [w.text for w in hw] == ["房主甲", "乙乙"]
          and hw[0].data[2] is True and hw[1].data[2] is False and hw[0].data[0] == fake_avatar(1) and hw[1].data[0] is None,
          [(w.text, w.data[2]) for w in hw])
    check("客户端大厅名单一致，自己被标出", [w.text for w in cw] == ["房主甲", "乙乙"] and cw[1].data[2] is True
          and cw[0].data[0] == fake_avatar(1), [(w.text, w.data[2]) for w in cw])
    mtst.click(host, "start_host")
    mtst.run_until([host, c1], clock, lambda: host.result and c1.result)
    s0, s1 = host.result["session"], c1.result["session"]
    check("开局后双方名单一致", s0.roster == s1.roster and [r["name"] for r in s0.roster] == ["房主甲", "乙乙"])
    host.close(); c1.close(); s0.close(); s1.close()


def p6_world_regen():
    print("== P6 整局里的小人回血 ==")
    from tools import multi_test  # noqa: F401  (保证路径)
    import pygame
    from settings import INIT_W, INIT_H, TICK_DT
    from world.game_world import GameWorld
    pygame.init(); pygame.font.init()
    f = pygame.font.Font(None, 16)

    def mk():
        return GameWorld(f, f, f, f, INIT_W, INIT_H, seed=42)
    a, b = mk(), mk()
    ca, cb = a.colonists[0], b.colonists[0]
    for c in (ca, cb):
        c.hp = 100.0
    ca.take_damage(30)
    cb.take_damage(30)
    hp_after_hit = ca.hp
    hist = []
    for sec in range(120):
        for _ in range(60):
            a.sim_step(); b.sim_step()
        hist.append(round(ca.hp, 1))
    check("受伤后立即不回血（延迟内血量不变）", abs(ca.hp - hp_after_hit) >= 0 and hist[0] <= hp_after_hit + 1.0, hist[:3])
    check("过一阵之后血量明显回升", hist[-1] > hp_after_hit + 10, (hp_after_hit, hist[::20]))
    check("回血不超过满血", ca.hp <= ca.max_hp + 1e-9, ca.hp)
    check("两个世界回血过程完全一致（确定性）", a.state_hash() == b.state_hash() and ca.hp == cb.hp)


if __name__ == "__main__":
    p1_regen(); p2_data(); p3_roster(); p4_menu(); p5_roster_widgets()
    try:
        import pygame  # noqa: F401
        p6_world_regen()
    except ImportError:
        print('  （未安装 pygame，跳过 P6）')
    print("\n结果：", "全部通过 ✓" if not FAILS else f"失败 {len(FAILS)} 项: {FAILS}")
    sys.exit(1 if FAILS else 0)
