# core/profile.py
"""玩家资料：用户名 + 头像（纯数据，不依赖 pygame，联机传输与存盘都走这里）。

头像统一成 AVATAR_SIZE×AVATAR_SIZE 的 RGB 原始像素（约 7 KB），联机时 base64 后放进 JSON（约 9 KB）。
为什么不直接传 PNG：不同机器/版本解码 PNG 的行为不完全相同，原始像素最简单也最安全——收到后只需要校验长度。
资料只用于显示，不参与模拟，也不进状态哈希，所以不会影响联机同步。

对外来数据（对方发来的名字/头像）一律经过 clean_wire 清洗：名字限长、去掉不可见字符，头像长度不对就丢弃。
"""
import base64
import binascii
import json
import os
import random

AVATAR_SIZE = 48
AVATAR_BYTES = AVATAR_SIZE * AVATAR_SIZE * 3
NAME_MAX = 12
# 玩家 1~4 的代表色（小人脚下的环、顶部玩家栏、默认头像都用它）
PLAYER_COLORS = ((90, 160, 255), (255, 150, 60), (120, 220, 120), (220, 100, 220))


def sanitize_name(s, default=""):
    """去掉不可见字符/首尾空白，限长。结果为空则返回 default。"""
    if not isinstance(s, str):
        return default
    s = "".join(ch for ch in s if ch.isprintable()).strip()[:NAME_MAX].strip()
    return s or default


def random_name(rng=random):
    return f"玩家{rng.randint(100, 999)}"


def encode_avatar(raw):
    return base64.b64encode(raw).decode("ascii") if raw else None


def decode_avatar(b64):
    """base64 → 原始像素；格式或长度不对返回 None（不抛异常）。"""
    if not isinstance(b64, str) or len(b64) > AVATAR_BYTES * 2:
        return None
    try:
        raw = base64.b64decode(b64.encode("ascii"), validate=True)
    except (binascii.Error, ValueError, UnicodeEncodeError):
        return None
    return raw if len(raw) == AVATAR_BYTES else None


def clean_wire(d, fallback_name):
    """清洗对方发来的资料：返回 {"name": str, "av": base64 或 None}（一定合法）。"""
    d = d if isinstance(d, dict) else {}
    name = sanitize_name(d.get("name"), fallback_name)
    av = d.get("av")
    return {"name": name, "av": av if decode_avatar(av) is not None else None}


def dedupe_names(names):
    """重名时给后来的加序号：['小明','小明'] → ['小明','小明(2)']。保持顺序，确定性。"""
    seen, out = {}, []
    for n in names:
        k = seen.get(n, 0) + 1
        seen[n] = k
        if k == 1:
            out.append(n)
        else:
            cand = f"{n}({k})"
            while cand in seen:
                k += 1
                cand = f"{n}({k})"
            seen[cand] = 1
            out.append(cand)
    return out


class Profile:
    """本机玩家资料。path 为 None 时不存盘（测试用）。"""
    def __init__(self, name=None, avatar=None, path=None):
        self.name = sanitize_name(name, "") or random_name()
        self.avatar = avatar if (avatar is None or len(avatar) == AVATAR_BYTES) else None
        self.path = path

    def to_wire(self):
        return {"name": self.name, "av": encode_avatar(self.avatar)}

    def save(self):
        if not self.path:
            return False
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.to_wire(), f, ensure_ascii=False)
            os.replace(tmp, self.path)                      # 先写临时文件再替换：中途崩溃不会留下半个文件
            return True
        except OSError:
            return False

    @classmethod
    def load(cls, path):
        """读取存档；文件不存在/损坏就生成一个新的随机名字并存下来。"""
        d = None
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            d = None
        if isinstance(d, dict) and sanitize_name(d.get("name")):
            return cls(d.get("name"), decode_avatar(d.get("av")), path)
        p = cls(None, None, path)
        p.save()
        return p
