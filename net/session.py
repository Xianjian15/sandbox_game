# net/session.py
"""局域网锁步会话（多人，最多 MAX_PLAYERS 人，星形中继）。

【锁步原理】
两端各自跑一份完全相同的模拟，只交换"玩家指令"。为了保证两端在同一个回合执行同一批指令：
  * 本地发出的指令带上 tick = 当前回合 + cmd_delay（输入延迟），不会立刻执行；
  * 每个回合 c，本端在推进之前先发一个 turn 包：{"c": c, "cmds": [这个回合里本端发出的所有指令]}，
    即使没有指令也要发（它同时是"我已经到第 c 回合、不会再有 tick<=c+delay 的新指令"的承诺）；
  * 推进回合 N 之前，必须已经收到对方的 turn 包 c = N - cmd_delay（更早的包按顺序必然已收到）。
    没收到就等（stall），哪怕等很久。
  * 两端对回合 N 看到的指令集合完全相同，执行顺序按 (tick, 玩家, 序号) 固定，所以结果相同。
  * 每 HASH_INTERVAL 个回合互相交换一次状态哈希（含分区摘要），不一致立刻报"失去同步"。

【多人拓扑】星形：所有客户端只连主机。客户端把自己的 turn 包发给主机，主机校验后原样转发给其他客户端（加上发包玩家编号 p）；
主机自己的 turn 包发给所有客户端。于是每个人都能收到"其他每个玩家"的逐回合包，锁步规则与两人时完全相同：
推进回合 N 之前，必须收齐所有（未离开的）其他玩家的 turn 包 c = N - cmd_delay。
玩家中途离开：主机广播 {"m":"drop","p":X,"c":L}（L = 主机收到的 X 的最后一个回合包）。因为主机转发 X 的包和发 drop 走同一条 TCP 连接，
每个人都是先收齐 X 的 ≤L 的包、再收到 drop，所以"X 从第 L+1 回合起不再发指令"在所有人那里一致，其余人继续游戏。
大厅：玩家加入后停在 lobby，房主点"开始"（start_game）才分配玩家编号并开局；开局后不再接受新玩家。
校验：每个人把初始状态哈希发给主机，主机比对全部一致后广播 go，才开始推进；之后每 HASH_INTERVAL 个回合两两比对状态哈希。

【状态机】 waiting → lobby → ready → verifying → running →（desync / mismatch / disconnected / failed）
"""
import json
import os
import socket
import time

from core import commands as cmdlib
from core.profile import clean_wire, dedupe_names
from core.version import GAME_VERSION
from net.framing import FrameBuffer, ProtocolError, pack

PROTO = 3
MAX_PLAYERS = 4               # 房间最多几人（含房主）；小人归属色也只准备了 4 种
DEFAULT_PORT = 47777
HASH_INTERVAL = 60            # 每 60 个回合比对一次状态哈希
STALL_WARN = 0.5              # 等对方超过这么多秒，界面提示"等待对方"
STALL_TIMEOUT = 20.0          # 主机等某位玩家超过这么久，把他请出游戏；客户端多等 10 秒（给主机先处理的时间）
HANDSHAKE_TIMEOUT = 5.0       # 握手（hello→cfg）超过这么久没完成，放弃这条连接


def get_lan_ip():
    """尽力找出本机局域网 IP，用于告诉另一位玩家连哪里。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))          # UDP connect 不会真的发包
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"


class Conn:
    """一条 TCP 连接 + 收发缓冲。主机有多条（每位玩家一条），客户端只有一条（连主机）。"""
    def __init__(self, sock):
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)   # 小包不要攒着发
        sock.setblocking(False)
        self.sock = sock
        self.rx = FrameBuffer()
        self.outbuf = bytearray()
        self.state = "handshake"          # handshake / lobby / playing / dead
        self.profile = None               # 主机：这位玩家的 {"name","av"}（已清洗）
        self.player = None
        self.peer_turn = -1               # 这位玩家的回合包已收到哪个回合（主机用）
        self.init_h = None
        self.deadline = time.monotonic() + HANDSHAKE_TIMEOUT
        self.closed_reason = None         # 读到断开时先记下，等本批消息处理完再处理断开
        self.error = None                 # 协议错误（乱码）

    def send(self, msg):
        self.outbuf += pack(msg)
        self.flush()

    def flush(self):
        if self.sock is None or not self.outbuf:
            return
        try:
            n = self.sock.send(self.outbuf)
            del self.outbuf[:n]
        except (BlockingIOError, InterruptedError):
            pass
        except OSError as e:
            self.closed_reason = self.closed_reason or f"发送失败: {e}"

    def recv(self):
        if self.sock is None:
            return []
        msgs = []
        try:
            while True:
                data = self.sock.recv(65536)
                if not data:
                    self.closed_reason = self.closed_reason or "对方关闭了连接"
                    break
                msgs += self.rx.feed(data)
        except (BlockingIOError, InterruptedError):
            pass
        except OSError as e:
            self.closed_reason = self.closed_reason or f"接收失败: {e}"
        except ProtocolError as e:
            self.error = f"协议错误: {e}"
        return msgs

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None


class LockstepSession:
    def __init__(self, role):
        self.role = role                  # "host" / "client"
        self.state = "waiting"
        self.error = ""
        self.cfg = None                   # {"seed","map_seed","delay","player","players"}
        self.game = None
        self.listen_sock = None
        self.port = None
        self.conns = []                   # 主机：所有已接受的连接；客户端：只有连主机的那一条
        self.expect = None                # 主机：凑够这么多个加入者就自动开局（None = 等房主手动点开始）
        self.lobby_n = 1                  # 客户端：大厅里当前人数（含房主）
        self.peer_turn = {}               # 玩家编号 -> 已收到的该玩家最大回合号（不含自己）
        self.dropped = {}                 # 已离开的玩家 -> 他的最后一个回合包
        self.sent_turn = -1
        self.my_init = None
        self.host_init = None             # 客户端：主机的初始哈希
        self.init_match = False
        self.go = False
        self.local_hashes = {}            # 回合 -> (哈希, 分区摘要)
        self.peer_hashes = {}             # (回合, 玩家) -> (哈希, 分区摘要)
        self.desync_info = None
        self.stall_since = None
        self.turns_run = 0
        self._base_cfg = None
        self.my_profile = {"name": "房主", "av": None}
        self.roster = []                  # 开局后：按玩家编号排列的 [{"name","av"}]
        self._lobby_roster = []           # 客户端：大厅里最近一次收到的名单
        self.lobby_me = None              # 客户端：我在大厅名单里的位置（主机告知，用来在名单里标出"我"）

    # ---------------- 建立连接 ----------------
    @classmethod
    def host(cls, port=DEFAULT_PORT, seed=42, map_seed=None, delay=4, bind="0.0.0.0", expect=1, profile=None):
        """expect=1：有 1 位玩家加入就自动开局（两人，命令行 / 测试用）；expect=None：停在大厅，等房主调用 start_game()。"""
        s = cls("host")
        s.expect = expect
        s.my_profile = clean_wire(profile, "房主")
        s.listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.listen_sock.bind((bind, port))
        s.listen_sock.listen(MAX_PLAYERS)
        s.listen_sock.setblocking(False)
        s.port = s.listen_sock.getsockname()[1]
        s._base_cfg = {"seed": seed, "map_seed": seed if map_seed is None else map_seed, "delay": delay}
        return s

    @classmethod
    def join(cls, host, port=DEFAULT_PORT, timeout=5.0, profile=None):
        s = cls("client")
        prof = clean_wire(profile, "玩家")
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
        except OSError as e:
            s.state, s.error = "failed", f"连接失败: {e}"
            return s
        conn = Conn(sock)
        s.conns = [conn]
        conn.send({"m": "hello", "proto": PROTO, "ver": GAME_VERSION, "name": prof["name"], "av": prof["av"]})
        s.state = "handshake"
        return s

    @property
    def sock(self):
        """客户端连主机的 socket（测试里用来模拟突然断线）。"""
        return self.conns[0].sock if self.role == "client" and self.conns else None

    def _send(self, msg):
        """客户端 → 主机。"""
        if self.conns:
            self.conns[0].send(msg)

    def _playing(self):
        return [c for c in self.conns if c.state == "playing"]

    def lobby_count(self):
        return sum(1 for c in self.conns if c.state == "lobby")

    def player_count(self):
        """房间里当前有几人（含房主）。"""
        if self.role == "host":
            return 1 + self.lobby_count() + len(self._playing())
        return self.lobby_n

    def lobby_roster(self):
        """大厅里当前的名单（按加入顺序，房主第一；重名已加序号）。每项 {"name","av"}。"""
        if self.role == "host":
            raw = [self.my_profile] + [c.profile for c in self.conns if c.state == "lobby"]
            names = dedupe_names([r["name"] for r in raw])
            return [{"name": n, "av": r["av"]} for n, r in zip(names, raw)]
        return self._lobby_roster

    def _lobby_index(self, conn):
        """这位玩家在大厅名单里的位置（房主 0，之后按加入顺序）。"""
        lobby = [c for c in self.conns if c.state == "lobby"]
        return 1 + lobby.index(conn) if conn in lobby else None

    def _mark_gone(self, p):
        if self.game is not None and hasattr(self.game, "gone_players"):
            self.game.gone_players.add(p)

    def _note(self, text):
        if self.game is not None:
            self.game.net_status = text

    # ---------------- 每帧泵 ----------------
    def pump(self):
        """每帧调用：收发数据并处理收到的消息。"""
        if self.state in ("failed", "disconnected"):
            return
        if self.role == "host":
            self._host_pump()
        else:
            self._client_pump()

    # ================= 主机 =================
    def _host_pump(self):
        if self.listen_sock is not None:
            for _ in range(8):
                try:
                    s, _ = self.listen_sock.accept()
                except (BlockingIOError, InterruptedError):
                    break
                except OSError:
                    break
                self.conns.append(Conn(s))
        now = time.monotonic()
        for conn in list(self.conns):
            if conn.state == "dead":
                continue
            if conn.state == "handshake" and now > conn.deadline:
                self._discard(conn)
                continue
            conn.flush()
            for msg in conn.recv():
                if conn.state == "dead" or self.state in ("failed", "disconnected"):
                    break
                self._host_handle(conn, msg)
            if conn.state == "dead":
                continue
            # 对方"发完话立刻关连接"时，话和断开会在同一次读取里一起到：先处理话，再处理断开
            if conn.error:
                self._kick(conn, conn.error)
            elif conn.closed_reason:
                self._conn_gone(conn, conn.closed_reason)
            conn.flush()
        self.conns = [c for c in self.conns if c.state != "dead"]

    def _discard(self, conn):
        """丢弃一条还没进大厅的连接（乱码、超时、版本不符…），房间继续开着。"""
        conn.state = "dead"
        conn.close()

    def _kick(self, conn, why):
        """把一位玩家请出去（违反协议/超时）。其余玩家继续；没人剩下时本会话 failed。"""
        if conn.state == "dead":
            return
        conn.send({"m": "reject", "why": why})
        self._conn_gone(conn, why, fatal=True)

    def _refresh_lobby_state(self):
        if self.state in ("waiting", "lobby"):
            self.state = "lobby" if self.lobby_count() > 0 else "waiting"

    def _broadcast_lobby(self):
        n = self.player_count()
        roster = self.lobby_roster()
        for c in self.conns:
            if c.state == "lobby":
                c.send({"m": "lobby", "n": n, "roster": roster, "me": self._lobby_index(c)})

    def _conn_gone(self, conn, reason, fatal=False):
        prev = conn.state
        if prev == "dead":
            return
        conn.state = "dead"
        conn.close()
        if prev == "handshake":
            return
        if prev == "lobby":
            self._broadcast_lobby()
            self._refresh_lobby_state()
            return
        p = conn.player
        last = self.peer_turn.get(p, -1)
        self.dropped[p] = last
        self._mark_gone(p)
        alive = self._playing()
        for c in alive:
            c.send({"m": "drop", "p": p, "c": last, "why": reason})
        if alive:
            self._note(f"玩家{p + 1} 已离开（{reason}）")
            if self.state == "verifying":
                self._check_inits()
        else:
            self.state = "failed" if fatal else "disconnected"
            self.error = reason
            self._to_local_mode()

    def _host_handle(self, conn, msg):
        m = msg.get("m")
        if conn.state == "handshake":
            if m != "hello":
                self._discard(conn)                      # 第一条不是 hello：不是我们的客户端
                return
            if msg.get("proto") != PROTO or msg.get("ver") != GAME_VERSION:
                conn.send({"m": "reject", "why": f"游戏版本不一致（房主 v{GAME_VERSION}，你 v{msg.get('ver') or '?'}），请双方使用相同版本"})
                conn.flush()
                self._discard(conn)                      # 房间继续开着，等下一位
                return
            if self.listen_sock is None or self.lobby_count() >= MAX_PLAYERS - 1:
                conn.send({"m": "reject", "why": "房间已满"})
                conn.flush()
                self._discard(conn)
                return
            conn.state = "lobby"
            conn.profile = clean_wire(msg, f"玩家{self.player_count() + 1}")
            self._refresh_lobby_state()
            conn.send({"m": "welcome", "n": self.player_count(), "roster": self.lobby_roster(), "me": self._lobby_index(conn)})
            self._broadcast_lobby()
            if self.expect is not None and self.lobby_count() >= self.expect:
                self.start_game()
            return
        if conn.state == "lobby":
            if m == "bye":
                self._conn_gone(conn, "玩家离开了房间")
            return
        # —— 已在游戏中 ——
        if m == "bye":
            self._conn_gone(conn, "对方已退出")
        elif m == "init":
            conn.init_h = msg.get("h")
            self._check_inits()
        elif m == "turn":
            self._host_turn(conn, msg)
        elif m == "hash":
            if self.state in ("desync", "mismatch"):
                return
            c, h, sec = msg.get("c"), msg.get("h"), msg.get("s", {})
            if not isinstance(c, int) or not isinstance(h, str) or not isinstance(sec, dict):
                self._kick(conn, "哈希包格式错误")
                return
            self.peer_hashes[(c, conn.player)] = (h, sec)
            for o in self._playing():
                if o is not conn:
                    o.send({"m": "hash", "c": c, "p": conn.player, "h": h, "s": sec})
            self._compare(c, conn.player)

    def start_game(self):
        """房主：大厅里人齐了，开局。分配玩家编号（按加入顺序 1,2,…），发配置，关闭监听口。"""
        if self.role != "host" or self.state != "lobby":
            return False
        lobby = [c for c in self.conns if c.state == "lobby"]
        if not lobby:
            return False
        n = 1 + len(lobby)
        self.roster = self.lobby_roster()
        self.cfg = dict(self._base_cfg, player=0, players=n, roster=self.roster)
        for i, c in enumerate(lobby, start=1):
            c.player = i
            c.state = "playing"
            c.send({"m": "cfg", **self.cfg, "player": i})
        self.peer_turn = {p: -1 for p in range(1, n)}
        if self.listen_sock is not None:
            try:
                self.listen_sock.close()
            except OSError:
                pass
            self.listen_sock = None
        self.state = "ready"
        return True

    def _check_inits(self):
        if self.state != "verifying" or self.my_init is None:
            return
        alive = self._playing()
        if any(c.init_h is not None and c.init_h != self.my_init for c in alive):
            for c in alive:
                c.send({"m": "abort", "why": "初始状态不一致"})
            self._set_mismatch()
        elif alive and all(c.init_h == self.my_init for c in alive):
            self.state = "running"
            self._note("")
            for c in alive:
                c.send({"m": "go"})

    def _host_turn(self, conn, msg):
        if self.state in ("desync", "mismatch"):
            return
        if self.state != "running":
            self._kick(conn, "在校验完成前就发来了回合包")
            return
        c = msg.get("c")
        if c != conn.peer_turn + 1:
            self._kick(conn, f"回合包不连续（期望 {conn.peer_turn + 1}，收到 {c}）")
            return
        delay = self.cfg["delay"]
        try:
            cmds = msg.get("cmds", [])
            for cmd in cmds:
                cmdlib.validate(cmd)
                # 防止对方伪造/写错：玩家编号和执行回合必须符合协议
                if cmd.get("p") != conn.player or cmd.get("tick") != c + delay or cmd.get("t") not in cmdlib.COMMAND_TYPES:
                    raise ValueError(f"非法指令 {cmd!r}")
        except ValueError as e:
            self._kick(conn, f"收到非法指令: {e}")
            return
        for cmd in cmds:
            self.game.receive_command(cmd)
        conn.peer_turn = c
        self.peer_turn[conn.player] = c
        for o in self._playing():
            if o is not conn:
                o.send({"m": "turn", "c": c, "p": conn.player, "cmds": cmds})

    # ================= 客户端 =================
    def _client_pump(self):
        conn = self.conns[0] if self.conns else None
        if conn is None:
            return
        if self.state == "handshake" and time.monotonic() > conn.deadline:
            self._fail("主机没有响应（房间可能已满或已关闭）")
            return
        conn.flush()
        for msg in conn.recv():
            if self.state in ("failed", "disconnected"):
                break
            try:
                self._client_handle(msg)
            except (ValueError, TypeError, KeyError, AttributeError) as e:
                self._fail(f"收到格式错误的消息: {e}")
                break
        if self.state in ("failed", "disconnected"):
            return
        if conn.error:
            self._fail(conn.error)
        elif conn.closed_reason:
            self._lost(conn.closed_reason)
        conn.flush()

    def _client_handle(self, msg):
        m = msg.get("m")
        conn = self.conns[0]
        if m == "welcome":
            self.state = "lobby"
            self.lobby_n = int(msg.get("n", 2))
            self._lobby_roster = self._clean_roster(msg.get("roster"), self.lobby_n)
            self.lobby_me = msg.get("me") if isinstance(msg.get("me"), int) else None
            conn.deadline = None
        elif m == "lobby":
            self.lobby_n = int(msg.get("n", self.lobby_n))
            self._lobby_roster = self._clean_roster(msg.get("roster"), self.lobby_n)
            self.lobby_me = msg.get("me") if isinstance(msg.get("me"), int) else self.lobby_me
        elif m == "cfg":
            try:
                self.cfg = {k: msg[k] for k in ("seed", "map_seed", "delay", "player", "players")}
            except KeyError as e:
                self._fail(f"配置包缺少字段 {e}")
                return
            self.peer_turn = {p: -1 for p in range(self.cfg["players"]) if p != self.cfg["player"]}
            self.roster = self._clean_roster(msg.get("roster"), self.cfg["players"])
            self.cfg["roster"] = self.roster
            self.state = "ready"
        elif m == "reject":
            self._fail(msg.get("why", "被拒绝"))
        elif m == "init":
            self.host_init = msg.get("h")
            self._client_check_init()
        elif m == "go":
            self.go = True
            self._client_try_run()
        elif m == "abort":
            self._set_mismatch()
        elif m == "turn":
            self._on_turn(msg)
        elif m == "hash":
            p, c, h, sec = msg.get("p"), msg.get("c"), msg.get("h"), msg.get("s", {})
            if p not in self.peer_turn or not isinstance(c, int) or not isinstance(h, str) or not isinstance(sec, dict):
                self._fail("哈希包格式错误")
                return
            self.peer_hashes[(c, p)] = (h, sec)
            self._compare(c, p)
        elif m == "drop":
            p = msg.get("p")
            if p in self.peer_turn:
                self.dropped[p] = msg.get("c", self.peer_turn[p])
                self._mark_gone(p)
                self._note(f"玩家{p + 1} 已离开（{msg.get('why', '')}）")
        elif m == "bye":
            self._lost("房主已退出")

    @staticmethod
    def _clean_roster(raw, n):
        """清洗主机发来的名单：长度不对就补默认名（只影响显示，不影响同步）。"""
        raw = raw if isinstance(raw, list) else []
        return [clean_wire(raw[i] if i < len(raw) else None, f"玩家{i + 1}") for i in range(max(0, int(n)))]

    def _on_turn(self, msg):
        if self.game is None:
            self._fail("对方在校验完成前就发来了回合包")
            return
        p, c = msg.get("p"), msg.get("c")
        if p not in self.peer_turn or p in self.dropped:
            self._fail(f"收到未知玩家 {p} 的回合包")
            return
        if c != self.peer_turn[p] + 1:
            self._fail(f"玩家{p + 1} 的回合包不连续（期望 {self.peer_turn[p] + 1}，收到 {c}）")
            return
        delay = self.cfg["delay"]
        try:
            cmds = msg.get("cmds", [])
            for cmd in cmds:
                cmdlib.validate(cmd)
                if cmd.get("p") != p or cmd.get("tick") != c + delay or cmd.get("t") not in cmdlib.COMMAND_TYPES:
                    raise ValueError(f"非法指令 {cmd!r}")
        except ValueError as e:
            self._fail(f"收到非法指令: {e}")
            return
        for cmd in cmds:
            self.game.receive_command(cmd)
        self.peer_turn[p] = c

    def _client_check_init(self):
        if self.my_init is None or self.host_init is None or self.state != "verifying":
            return
        if self.my_init == self.host_init:
            self.init_match = True
            self._client_try_run()
        else:
            self._set_mismatch()

    def _client_try_run(self):
        if self.state == "verifying" and self.init_match and self.go:
            self.state = "running"
            self._note("")

    def _set_mismatch(self):
        if self.state in ("mismatch", "failed", "disconnected"):
            return
        self.state = "mismatch"
        self.error = "各端初始状态不一致：游戏版本/数据不同，无法联机"
        self._note(self.error)

    # ================= 公共：哈希比对 / 失败 / 断线 =================
    def _compare(self, c, p):
        if c not in self.local_hashes or (c, p) not in self.peer_hashes:
            return
        (lh, ls) = self.local_hashes[c]
        (ph, ps) = self.peer_hashes.pop((c, p))
        if lh != ph and self.state not in ("desync",):
            bad = sorted(k for k in set(ls) | set(ps) if ls.get(k) != ps.get(k))
            self.desync_info = {"turn": c, "local": lh, "peer": ph, "peer_player": p, "sections": bad,
                                "local_sections": ls, "peer_sections": ps}
            self.state = "desync"
            self.error = f"失去同步！回合 {c}，与玩家{p + 1} 分叉分区: {', '.join(bad)}"
            self._note(self.error)

    def _fail(self, why):
        """客户端：致命错误（连不上、被拒、协议错误）。"""
        self.state, self.error = "failed", why
        self._close()
        self._to_local_mode()

    def _lost(self, why):
        """客户端：与主机的连接断了。"""
        if self.state in ("failed", "disconnected"):
            return
        self.state, self.error = "disconnected", why
        self._close()
        self._to_local_mode()

    def _to_local_mode(self):
        """会话结束后转为单机继续：各端在断线时刻的状态一致，把已收到的未执行指令全部执行掉，
        之后指令立即执行（cmd_delay=0）。"""
        g = self.game
        if g is None:
            return
        g.cmd_delay = 0
        g.flush_commands(force=True)
        g.cmd_outbox.clear()
        g.net_status = f"联机已断开（{self.error}），已转为单机继续" if self.state != "failed" else \
            f"联机失败：{self.error}"

    def _close(self):
        for c in self.conns:
            c.close()
        if self.listen_sock is not None:
            try:
                self.listen_sock.close()
            except OSError:
                pass
        self.listen_sock = None

    def close(self):
        for c in self.conns:
            if c.state in ("lobby", "playing") or (self.role == "client" and c.sock is not None and self.state in (
                    "lobby", "ready", "verifying", "running")):
                try:
                    c.sock.send(pack({"m": "bye"}))
                except (OSError, AttributeError):
                    pass
        self._close()

    # ---------------- 绑定游戏 & 推进 ----------------
    def attach(self, game):
        """世界创建完成后调用：把会话和游戏绑定，并交换初始状态哈希（版本/数据一致性校验）。"""
        self.game = game
        game.cmd_delay = self.cfg["delay"]
        game.local_player = self.cfg["player"]
        self.my_init = game.state_hash()
        self.state = "verifying"
        game.net_status = "校验中…"
        if self.role == "host":
            for c in self._playing():
                c.send({"m": "init", "h": self.my_init})
            self._check_inits()
        else:
            self._send({"m": "init", "h": self.my_init})
            self._client_check_init()

    @property
    def active(self):
        """联机推进是否在进行中（main 用它决定走哪条循环）。"""
        return self.state in ("verifying", "running")

    def try_turn(self):
        """尝试推进一个回合。成功返回 True；需要等待其他玩家或已停止则返回 False。"""
        self.pump()
        if self.state != "running":
            return False
        g = self.game
        c = g.turn
        need = c - g.cmd_delay
        if need >= 0:
            lagging = [p for p, t in self.peer_turn.items() if p not in self.dropped and t < need]
            if lagging:
                now = time.monotonic()
                if self.stall_since is None:
                    self.stall_since = now
                waited = now - self.stall_since
                if self.role == "host":
                    if waited > STALL_TIMEOUT:
                        for conn in self._playing():
                            if conn.player in lagging:
                                self._kick(conn, f"等待超过 {STALL_TIMEOUT:.0f} 秒没有响应")
                        self.stall_since = None
                        self.conns = [x for x in self.conns if x.state != "dead"]
                        return False
                elif waited > STALL_TIMEOUT + 10:
                    self._lost(f"等待玩家超过 {STALL_TIMEOUT + 10:.0f} 秒")
                    return False
                if waited > STALL_WARN:
                    g.net_status = f"等待玩家{lagging[0] + 1}… {waited:.1f}s"
                return False
        self.stall_since = None
        if g.net_status.startswith("等待玩家"):
            g.net_status = ""
        # 先把本回合发出的指令发出去，再推进
        cmds = g.cmd_outbox[:]
        g.cmd_outbox.clear()
        if self.role == "host":
            for conn in self._playing():
                conn.send({"m": "turn", "c": c, "p": 0, "cmds": cmds})
        else:
            self._send({"m": "turn", "c": c, "cmds": cmds})
        self.sent_turn = c
        g.sim_step()
        self.turns_run += 1
        if g.turn % HASH_INTERVAL == 0:
            tag = g.turn - 1
            h = g.state_hash()
            sections = g.state_sections()
            self.local_hashes[tag] = (h, sections)
            for old in [t for t in self.local_hashes if t < tag - 20 * HASH_INTERVAL]:
                del self.local_hashes[old]
            for old in [k for k in self.peer_hashes if k[0] < tag - 20 * HASH_INTERVAL]:
                del self.peer_hashes[old]
            if self.role == "host":
                for conn in self._playing():
                    conn.send({"m": "hash", "c": tag, "p": 0, "h": h, "s": sections})
            else:
                self._send({"m": "hash", "c": tag, "h": h, "s": sections})
            for p in list(self.peer_turn):
                self._compare(tag, p)
        return True

    def status_text(self):
        names = {"waiting": "等待玩家加入…", "lobby": f"大厅 {self.player_count()} 人", "ready": "已连接",
                 "verifying": "校验中…", "running": "联机中", "desync": self.error,
                 "mismatch": self.error, "disconnected": self.error, "failed": self.error}
        return names.get(self.state, self.state)
