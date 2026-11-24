# net/discovery.py
"""局域网房间发现（UDP 广播）。

房主：RoomBeacon 每隔约 1 秒向局域网广播一条"我这里有个房间"的小消息。
玩家：RoomFinder 监听这个 UDP 端口，把收到的房间攒成列表；超过 TTL 没再收到就当房间已关闭。
玩家不需要输入 IP：IP 取自广播包的来源地址，端口（TCP）由房间消息告知。

注意：UDP 广播只能在同一个局域网内传播，不会穿过路由器；有些公司/学校 Wi-Fi 会隔离客户端，
那种网络里房间列表是空的（此时仍可用命令行 --join IP 直连）。
"""
import json
import socket
import time

from core.version import GAME_VERSION
from net.session import PROTO, get_lan_ip

DISC_PORT = 47778
MAGIC = "RWLAN1"
BEACON_INTERVAL = 1.0
ROOM_TTL = 3.5            # 超过这么久没收到房间的广播，就从列表里移除


def broadcast_targets():
    """默认广播目标：全局广播 + 本机所在 /24 网段的广播地址（有些系统不转发 255.255.255.255）。"""
    targets = ["255.255.255.255"]
    ip = get_lan_ip()
    parts = ip.split(".")
    if len(parts) == 4 and ip not in ("127.0.0.1", "0.0.0.0"):
        targets.append(".".join(parts[:3] + ["255"]))
    return targets


class RoomBeacon:
    """房主端：定时广播房间信息。"""
    def __init__(self, room_id, name, tcp_port, players=1, max_players=2,
                 port=DISC_PORT, targets=None, interval=BEACON_INTERVAL):
        self.info = {"magic": MAGIC, "proto": PROTO, "ver": GAME_VERSION, "id": room_id, "name": name,
                     "port": tcp_port, "players": players, "max": max_players}
        self.port = port
        self.targets = targets if targets is not None else broadcast_targets()
        self.interval = interval
        self._next = 0.0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.setblocking(False)
        self.sent = 0

    def update(self, now=None):
        now = time.monotonic() if now is None else now
        if now < self._next or self.sock is None:
            return
        self._next = now + self.interval
        data = json.dumps(self.info, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        for t in self.targets:
            try:
                self.sock.sendto(data, (t, self.port))
                self.sent += 1
            except OSError:
                pass                      # 没有网络/无路由：忽略，下次再试

    def close(self):
        if self.sock is not None:
            self.sock.close()
            self.sock = None


class RoomFinder:
    """玩家端：监听广播，维护房间列表。"""
    def __init__(self, port=DISC_PORT, bind="", ttl=ROOM_TTL):
        self.ttl = ttl
        self.rooms = {}                   # id -> {"id","name","ip","port","players","max","proto","seen"}
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)   # 同机多开时都能收到
            except OSError:
                pass
        self.error = ""
        try:
            self.sock.bind((bind, port))
        except OSError as e:
            self.error = f"无法监听房间广播（端口 {port} 被占用？）: {e}"
            self.sock.close()
            self.sock = None
            return
        self.sock.setblocking(False)

    def update(self, now=None):
        now = time.monotonic() if now is None else now
        if self.sock is not None:
            for _ in range(200):          # 每帧最多处理这么多包，防止被刷屏
                try:
                    data, addr = self.sock.recvfrom(2048)
                except (BlockingIOError, InterruptedError):
                    break
                except OSError:
                    break
                self._ingest(data, addr, now)
        for rid in [r for r, v in self.rooms.items() if now - v["seen"] > self.ttl]:
            del self.rooms[rid]

    def _ingest(self, data, addr, now):
        try:
            info = json.loads(data.decode("ascii"))
            if info.get("magic") != MAGIC:
                return
            rid = str(info["id"])
            self.rooms[rid] = {
                "id": rid, "name": str(info.get("name", "房间"))[:40], "ip": addr[0],
                "port": int(info["port"]), "players": int(info.get("players", 1)),
                "max": int(info.get("max", 2)), "proto": info.get("proto"),
                "ver": str(info.get("ver", ""))[:16], "seen": now,
            }
        except (ValueError, KeyError, TypeError, UnicodeDecodeError):
            return                        # 别的程序发来的乱包：忽略

    def room_list(self):
        return sorted(self.rooms.values(), key=lambda r: (r["name"], r["id"]))

    def close(self):
        if self.sock is not None:
            self.sock.close()
            self.sock = None
