# net/session.py
"""局域网锁步会话（两人）。

【锁步原理】
两端各自跑一份完全相同的模拟，只交换"玩家指令"。为了保证两端在同一个回合执行同一批指令：
  * 本地发出的指令带上 tick = 当前回合 + cmd_delay（输入延迟），不会立刻执行；
  * 每个回合 c，本端在推进之前先发一个 turn 包：{"c": c, "cmds": [这个回合里本端发出的所有指令]}，
    即使没有指令也要发（它同时是"我已经到第 c 回合、不会再有 tick<=c+delay 的新指令"的承诺）；
  * 推进回合 N 之前，必须已经收到对方的 turn 包 c = N - cmd_delay（更早的包按顺序必然已收到）。
    没收到就等（stall），哪怕等很久。
  * 两端对回合 N 看到的指令集合完全相同，执行顺序按 (tick, 玩家, 序号) 固定，所以结果相同。
  * 每 HASH_INTERVAL 个回合互相交换一次状态哈希（含分区摘要），不一致立刻报"失去同步"。

【状态机】 waiting → ready → verifying → running →（desync / mismatch / disconnected）
"""
import json
import os
import socket
import time

from core import commands as cmdlib
from core.version import GAME_VERSION
from net.framing import FrameBuffer, ProtocolError, pack

PROTO = 1
DEFAULT_PORT = 47777
HASH_INTERVAL = 60            # 每 60 个回合比对一次状态哈希
STALL_WARN = 0.5              # 等对方超过这么多秒，界面提示"等待对方"
STALL_TIMEOUT = 20.0          # 等超过这么久，当作断线
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


class LockstepSession:
    def __init__(self, role):
        self.role = role                  # "host" / "client"
        self.state = "waiting"
        self.error = ""
        self.cfg = None                   # {"seed", "map_seed", "delay", "player"}
        self.game = None
        self.sock = None
        self.listen_sock = None
        self.port = None
        self.rx = FrameBuffer()
        self.outbuf = bytearray()
        self.peer_turn = -1               # 已收到的对方最大回合号
        self.sent_turn = -1               # 已发出的本端最大回合号
        self.my_init = None
        self.peer_init = None
        self.local_hashes = {}
        self.peer_hashes = {}
        self.desync_info = None
        self.stall_since = None
        self.turns_run = 0
        self._pending_cfg = None
        self._hs_deadline = None
        self._closed_reason = None        # 读到连接断开时先记下来，等本批消息处理完再处理断开

    # ---------------- 建立连接 ----------------
    @classmethod
    def host(cls, port=DEFAULT_PORT, seed=42, map_seed=None, delay=4, bind="0.0.0.0"):
        s = cls("host")
        s.listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.listen_sock.bind((bind, port))
        s.listen_sock.listen(1)
        s.listen_sock.setblocking(False)
        s.port = s.listen_sock.getsockname()[1]
        s._pending_cfg = {"seed": seed, "map_seed": seed if map_seed is None else map_seed,
                          "delay": delay, "player": 0}
        return s

    @classmethod
    def join(cls, host, port=DEFAULT_PORT, timeout=5.0):
        s = cls("client")
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
        except OSError as e:
            s.state, s.error = "failed", f"连接失败: {e}"
            return s
        s._adopt(sock)
        s._send({"m": "hello", "proto": PROTO, "ver": GAME_VERSION})
        s.state = "handshake"
        s._hs_deadline = time.monotonic() + HANDSHAKE_TIMEOUT
        return s

    def _adopt(self, sock):
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)   # 小包不要攒着发
        sock.setblocking(False)
        self.sock = sock

    # ---------------- 收发 ----------------
    def _send(self, msg):
        self.outbuf += pack(msg)
        self._flush()

    def _flush(self):
        if self.sock is None or not self.outbuf:
            return
        try:
            n = self.sock.send(self.outbuf)
            del self.outbuf[:n]
        except (BlockingIOError, InterruptedError):
            pass
        except OSError as e:
            self._lost(f"发送失败: {e}")

    def _recv(self):
        if self.sock is None:
            return []
        msgs = []
        try:
            while True:
                data = self.sock.recv(65536)
                if not data:
                    self._closed_reason = "对方关闭了连接"
                    break
                msgs += self.rx.feed(data)
        except (BlockingIOError, InterruptedError):
            pass
        except OSError as e:
            self._closed_reason = f"接收失败: {e}"
        except ProtocolError as e:
            self._fail(f"协议错误: {e}")
        return msgs

    def pump(self):
        """每帧调用：收发数据并处理收到的消息。"""
        if self.state in ("failed", "disconnected"):
            return
        if self.listen_sock is not None and self.sock is None:
            try:
                conn, _ = self.listen_sock.accept()
                self._adopt(conn)
                self.state = "handshake"
                self._hs_deadline = time.monotonic() + HANDSHAKE_TIMEOUT
            except (BlockingIOError, InterruptedError):
                return
            except OSError as e:
                self._fail(f"接受连接失败: {e}")
                return
        if self.state == "handshake" and self._hs_deadline is not None and time.monotonic() > self._hs_deadline:
            if self.role == "host":
                self._drop_pending()             # 房间继续开着，等下一位
            else:
                self._fail("主机没有响应（房间可能已满或已关闭）")
            return
        self._flush()
        for msg in self._recv():
            if self.state in ("failed", "disconnected"):
                break
            self._handle(msg)
        # 对方"发完话立刻关连接"时，话和断开会在同一次读取里一起到：先处理话（拒绝原因、最后几个回合包、bye），再处理断开
        if self._closed_reason is not None:
            reason, self._closed_reason = self._closed_reason, None
            if self.state not in ("failed", "disconnected"):
                self._lost(reason)
        self._flush()

    # ---------------- 消息处理 ----------------
    def _handle(self, msg):
        m = msg.get("m")
        if self.role == "host" and self.cfg is None and m != "hello":
            self._drop_pending()                        # 第一条不是 hello：不是我们的客户端，丢掉
            return
        if m == "hello" and self.role == "host":
            if msg.get("proto") != PROTO or msg.get("ver") != GAME_VERSION:
                self._send({"m": "reject", "why": f"游戏版本不一致（房主 v{GAME_VERSION}，你 v{msg.get('ver') or '?'}），请双方使用相同版本"})
                self._flush()
                self._drop_pending()                    # 房间继续开着，等下一位
                return
            cfg = dict(self._pending_cfg)
            cfg["player"] = 1
            self._send({"m": "cfg", **cfg})
            self.cfg = dict(self._pending_cfg)          # 主机自己是玩家 0
            self._hs_deadline = None
            self.state = "ready"
            if self.listen_sock is not None:            # 房间满员：关掉监听口，后来的人直接被拒绝
                try:
                    self.listen_sock.close()
                except OSError:
                    pass
                self.listen_sock = None
        elif m == "cfg" and self.role == "client":
            self.cfg = {k: msg[k] for k in ("seed", "map_seed", "delay", "player")}
            self._hs_deadline = None
            self.state = "ready"
        elif m == "reject":
            self._fail(msg.get("why", "被拒绝"))
        elif m == "init":
            self.peer_init = msg.get("h")
            self._check_init()
        elif m == "turn":
            self._on_turn(msg)
        elif m == "hash":
            self.peer_hashes[msg["c"]] = (msg["h"], msg.get("s", {}))
            self._compare_hash(msg["c"])
        elif m == "bye":
            self._lost("对方已退出")

    def _on_turn(self, msg):
        if self.game is None:
            self._fail("对方在校验完成前就发来了回合包")
            return
        c = msg.get("c")
        if c != self.peer_turn + 1:
            self._fail(f"回合包不连续（期望 {self.peer_turn + 1}，收到 {c}）")
            return
        delay = self.cfg["delay"]
        peer_player = 1 - self.cfg["player"]
        try:
            cmds = msg.get("cmds", [])
            for cmd in cmds:
                cmdlib.validate(cmd)
                # 防止对方伪造/写错：玩家编号和执行回合必须符合协议
                if cmd.get("p") != peer_player or cmd.get("tick") != c + delay or cmd.get("t") not in cmdlib.COMMAND_TYPES:
                    raise ValueError(f"非法指令 {cmd!r}")
        except ValueError as e:
            self._fail(f"收到非法指令: {e}")
            return
        for cmd in cmds:
            self.game.receive_command(cmd)
        self.peer_turn = c

    def _check_init(self):
        if self.my_init is None or self.peer_init is None or self.state != "verifying":
            return
        if self.my_init == self.peer_init:
            self.state = "running"
            self.game.net_status = ""
        else:
            self.state = "mismatch"
            self.error = "两端初始状态不一致：游戏版本/数据不同，无法联机"
            self.game.net_status = self.error

    def _compare_hash(self, c):
        if c not in self.local_hashes or c not in self.peer_hashes:
            return
        (lh, ls), (ph, ps) = self.local_hashes.pop(c), self.peer_hashes.pop(c)
        if lh != ph:
            bad = sorted(k for k in set(ls) | set(ps) if ls.get(k) != ps.get(k))
            self.desync_info = {"turn": c, "local": lh, "peer": ph, "sections": bad,
                                "local_sections": ls, "peer_sections": ps}
            self.state = "desync"
            self.error = f"失去同步！回合 {c}，分叉分区: {', '.join(bad)}"
            if self.game is not None:
                self.game.net_status = self.error

    # ---------------- 失败 / 断线 ----------------
    def _drop_pending(self):
        """主机：丢弃一条还没完成握手的连接（乱码、超时、版本不符、中途断开），回到"等待加入"。"""
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None
        self.rx = FrameBuffer()
        self.outbuf = bytearray()
        self._hs_deadline = None
        self._closed_reason = None
        self.state = "waiting"

    def _fail(self, why):
        if self.role == "host" and self.cfg is None and self.state in ("waiting", "handshake"):
            self._drop_pending()
            return
        self.state, self.error = "failed", why
        self._close()
        self._to_local_mode()

    def _lost(self, why):
        if self.state in ("failed", "disconnected"):
            return
        if self.role == "host" and self.cfg is None:
            self._drop_pending()
            return
        self.state, self.error = "disconnected", why
        self._close()
        self._to_local_mode()

    def _to_local_mode(self):
        """断线后转为单机继续：两端在断线时刻的状态一致，把已收到的未执行指令全部执行掉，
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
        for s in (self.sock, self.listen_sock):
            if s is not None:
                try:
                    s.close()
                except OSError:
                    pass
        self.sock = None
        self.listen_sock = None

    def close(self):
        if self.sock is not None and self.state == "running":
            try:
                self.sock.send(pack({"m": "bye"}))
            except OSError:
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
        self._send({"m": "init", "h": self.my_init})
        self._check_init()

    @property
    def active(self):
        """联机推进是否在进行中（main 用它决定走哪条循环）。"""
        return self.state in ("verifying", "running")

    def try_turn(self):
        """尝试推进一个回合。成功返回 True；需要等待对方或已停止则返回 False。"""
        self.pump()
        if self.state == "verifying":
            return False
        if self.state != "running":
            return False
        g = self.game
        c = g.turn
        need = c - g.cmd_delay
        if need >= 0 and self.peer_turn < need:
            now = time.monotonic()
            if self.stall_since is None:
                self.stall_since = now
            waited = now - self.stall_since
            if waited > STALL_TIMEOUT:
                self._lost(f"等待对方超过 {STALL_TIMEOUT:.0f} 秒")
            elif waited > STALL_WARN:
                g.net_status = f"等待对方… {waited:.1f}s"
            return False
        self.stall_since = None
        if g.net_status.startswith("等待对方"):
            g.net_status = ""
        # 先把本回合发出的指令发给对方，再推进
        cmds = g.cmd_outbox[:]
        g.cmd_outbox.clear()
        self._send({"m": "turn", "c": c, "cmds": cmds})
        self.sent_turn = c
        g.sim_step()
        self.turns_run += 1
        if g.turn % HASH_INTERVAL == 0:
            tag = g.turn - 1
            h = g.state_hash()
            sections = g.state_sections()
            self.local_hashes[tag] = (h, sections)
            self._send({"m": "hash", "c": tag, "h": h, "s": sections})
            self._compare_hash(tag)
        return True

    def status_text(self):
        names = {"waiting": "等待对方加入…", "handshake": "握手中…", "ready": "已连接",
                 "verifying": "校验中…", "running": "联机中", "desync": self.error,
                 "mismatch": self.error, "disconnected": self.error, "failed": self.error}
        return names.get(self.state, self.state)
