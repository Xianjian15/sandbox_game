# net/framing.py
"""TCP 是字节流，没有"消息边界"：一次 recv 可能只收到半条消息，也可能一口气收到好几条。
所以每条消息前面加 4 字节长度（大端），接收端把收到的字节攒起来，凑够一条才交出去。
消息内容是 JSON（ASCII，键排序、无空格）。"""
import json

MAX_FRAME = 1 << 20          # 单条消息上限 1MB；超过就是协议错误（防止乱码把内存吃光）


class ProtocolError(Exception):
    pass


def pack(msg):
    payload = json.dumps(msg, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    if len(payload) > MAX_FRAME:
        raise ProtocolError("消息过大")
    return len(payload).to_bytes(4, "big") + payload


class FrameBuffer:
    def __init__(self):
        self.buf = bytearray()

    def feed(self, data):
        """喂入新收到的字节，返回已凑齐的消息列表（可能为空）。"""
        self.buf += data
        out = []
        while len(self.buf) >= 4:
            n = int.from_bytes(self.buf[:4], "big")
            if n > MAX_FRAME:
                raise ProtocolError(f"消息长度异常: {n}")
            if len(self.buf) < 4 + n:
                break
            payload = bytes(self.buf[4:4 + n])
            del self.buf[:4 + n]
            try:
                out.append(json.loads(payload.decode("ascii")))
            except (ValueError, UnicodeDecodeError) as e:
                raise ProtocolError(f"消息不是合法 JSON: {e}")
        return out
