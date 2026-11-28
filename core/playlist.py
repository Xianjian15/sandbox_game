# core/playlist.py
"""玩家自己的歌单（纯显示/播放，不参与模拟，不影响联机同步）。

* 音乐文件统一放在用户数据目录的 music/ 文件夹里：玩家可以直接把 .ogg/.mp3/.wav/.flac 丢进去，
  界面里点「刷新」就会出现在歌单里。
* 「添加本地音乐」会把所选文件复制到 music/（原文件被移动/删除也不影响歌单）。
* 「添加链接」只支持"直接指向音频文件"的链接（.mp3/.ogg/.wav/.flac），会在后台线程下载到 music/；
  YouTube / B站 / 网易云 这类播放页面不是音频文件，无法下载，会给出明确提示。
* 歌单设置存在 playlist.json：播放模式（自动/歌单）、循环方式、歌曲列表。
"""
import json
import os
import random
import re
import shutil
import threading

AUDIO_EXTS = (".ogg", ".mp3", ".wav", ".flac")
MAX_FILE_MB = 60
MAX_ITEMS = 200
LOOPS = ("all", "one", "shuffle")
LOOP_NAMES = {"all": "列表循环", "one": "单曲循环", "shuffle": "随机播放"}
_CT_EXT = {"audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/ogg": ".ogg", "application/ogg": ".ogg",
           "audio/vorbis": ".ogg", "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/wave": ".wav",
           "audio/flac": ".flac", "audio/x-flac": ".flac"}


def is_audio_name(name):
    return os.path.splitext(str(name))[1].lower() in AUDIO_EXTS


def sniff_ext(head):
    """按文件头判断真实格式，返回扩展名或 None。"""
    if head[:4] == b"OggS": return ".ogg"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE": return ".wav"
    if head[:4] == b"fLaC": return ".flac"
    if head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0): return ".mp3"
    return None


def _safe_name(name):
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip(" .")
    return name[:80] or "music"


class Playlist:
    def __init__(self, path=None, music_dir=None):
        self.path, self.music_dir = path, music_dir
        self.items = []              # [{"name","file","src"}]   file = music_dir 里的文件名
        self.ignored = []            # 玩家从歌单里删掉的文件名：刷新时不再自动加回
        self.mode = "auto"           # auto = 按 昼/夜/战斗 自动换曲；list = 播放歌单
        self.loop = "all"
        self.index = 0
        self.status = ""             # 给界面看的一行提示（下载进度/错误）
        self._lock = threading.Lock()
        self._done = []              # 后台线程的结果，主线程 poll() 时处理
        self._busy = False
        self._rng = random.Random()
        self._load()
        if self.music_dir:
            self.refresh()

    # ---------- 存取 ----------
    def _load(self):
        if not self.path: return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.mode = d.get("mode") if d.get("mode") in ("auto", "list") else "auto"
            self.loop = d.get("loop") if d.get("loop") in LOOPS else "all"
            self.ignored = [str(x) for x in d.get("ignored", [])][:500]
            for it in d.get("items", [])[:MAX_ITEMS]:
                if isinstance(it, dict) and isinstance(it.get("file"), str):
                    self.items.append({"name": str(it.get("name") or it["file"])[:80], "file": it["file"],
                                       "src": it.get("src", "file")})
            self.index = int(d.get("index", 0)) if isinstance(d.get("index", 0), int) else 0
        except Exception:        # noqa: BLE001  坏存档：当作空歌单
            self.items, self.mode, self.loop, self.index = [], "auto", "all", 0

    def save(self):
        if not self.path: return
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"mode": self.mode, "loop": self.loop, "index": self.index, "ignored": self.ignored,
                           "items": self.items}, f, ensure_ascii=False)
        except OSError:
            pass

    # ---------- 基本操作 ----------
    def full_path(self, i):
        if not (0 <= i < len(self.items)) or not self.music_dir: return None
        return os.path.join(self.music_dir, self.items[i]["file"])

    def _has(self, fname):
        return any(it["file"] == fname for it in self.items)

    def refresh(self):
        """去掉已不存在的文件，并把 music/ 里新放进去的音频加进来。返回新增数量。"""
        if not self.music_dir: return 0
        os.makedirs(self.music_dir, exist_ok=True)
        cur = self.items[self.index]["file"] if 0 <= self.index < len(self.items) else None
        self.items = [it for it in self.items if os.path.isfile(os.path.join(self.music_dir, it["file"]))]
        added = 0
        for fn in sorted(os.listdir(self.music_dir)):
            if is_audio_name(fn) and not self._has(fn) and fn not in self.ignored and len(self.items) < MAX_ITEMS:
                self.items.append({"name": os.path.splitext(fn)[0], "file": fn, "src": "file"})
                added += 1
        self.index = next((i for i, it in enumerate(self.items) if it["file"] == cur), 0) if cur else min(self.index, max(0, len(self.items) - 1))
        if added: self.save()
        return added

    def _unique(self, fname):
        base, ext = os.path.splitext(fname)
        n, out = 1, fname
        while os.path.exists(os.path.join(self.music_dir, out)):
            n += 1; out = f"{base}_{n}{ext}"
        return out

    def add_file(self, src_path):
        """加入一个本地音频文件（复制进 music/）。返回 (成功?, 提示)。"""
        if not self.music_dir: return False, "没有可用的音乐文件夹"
        src_path = str(src_path)
        if not os.path.isfile(src_path): return False, "找不到这个文件"
        if not is_audio_name(src_path):
            return False, "不支持的格式（支持 " + " ".join(AUDIO_EXTS) + "）"
        if os.path.getsize(src_path) > MAX_FILE_MB * 1024 * 1024:
            return False, f"文件太大（上限 {MAX_FILE_MB} MB）"
        if len(self.items) >= MAX_ITEMS: return False, "歌单已满"
        os.makedirs(self.music_dir, exist_ok=True)
        fname = _safe_name(os.path.basename(src_path))
        try:
            if os.path.dirname(os.path.abspath(src_path)) == os.path.abspath(self.music_dir):
                fname = os.path.basename(src_path)           # 本来就在 music/ 里：不用复制
                if self._has(fname): return False, "已经在歌单里了"
            else:
                fname = self._unique(fname)
                shutil.copyfile(src_path, os.path.join(self.music_dir, fname))
        except OSError as e:
            return False, f"复制失败：{e}"
        if fname in self.ignored: self.ignored.remove(fname)
        self.items.append({"name": os.path.splitext(fname)[0], "file": fname, "src": "file"})
        self.save()
        return True, f"已添加：{os.path.splitext(fname)[0]}"

    def remove(self, i):
        if not (0 <= i < len(self.items)): return
        fn = self.items.pop(i)["file"]
        if fn not in self.ignored: self.ignored.append(fn)
        if self.index > i or self.index >= len(self.items): self.index = max(0, min(self.index - (1 if self.index > i else 0), len(self.items) - 1))
        self.save()

    def cycle_loop(self):
        self.loop = LOOPS[(LOOPS.index(self.loop) + 1) % len(LOOPS)]
        self.save()

    def next_index(self, step=1):
        n = len(self.items)
        if n == 0: return None
        if self.loop == "shuffle" and n > 1:
            j = self.index
            while j == self.index: j = self._rng.randrange(n)
            return j
        return (self.index + step) % n

    # ---------- 链接下载（后台线程） ----------
    def add_url(self, url, opener=None):
        """开始下载一个音频直链。立即返回 (是否开始, 提示)；结果由 poll() 在主线程收尾。"""
        url = (url or "").strip()
        if not self.music_dir: return False, "没有可用的音乐文件夹"
        if not re.match(r"^https?://[^\s]+$", url, re.I):
            return False, "请输入以 http:// 或 https:// 开头的链接"
        with self._lock:
            if self._busy: return False, "上一个下载还没完成"
            self._busy = True
        self.status = "正在连接…"
        threading.Thread(target=self._download, args=(url, opener), daemon=True).start()
        return True, "开始下载…"

    def _download(self, url, opener):
        import urllib.request
        from urllib.parse import urlparse, unquote
        tmp = None
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 SandboxGame"})
            with (opener or urllib.request.urlopen)(req, timeout=15) as r:
                ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                if ctype.startswith("text/"):
                    raise ValueError("这是一个网页，不是音频文件。需要直接指向 .mp3/.ogg/.wav/.flac 的链接"
                                     "（YouTube、B站、网易云等播放页面不支持）")
                clen = r.headers.get("Content-Length")
                if clen and clen.isdigit() and int(clen) > MAX_FILE_MB * 1024 * 1024:
                    raise ValueError(f"文件太大（上限 {MAX_FILE_MB} MB）")
                name = unquote(os.path.basename(urlparse(url).path)) or "online"
                os.makedirs(self.music_dir, exist_ok=True)
                tmp = os.path.join(self.music_dir, f".dl_{os.getpid()}_{id(self)}.part")
                size, head = 0, b""
                with open(tmp, "wb") as f:
                    while True:
                        chunk = r.read(65536)
                        if not chunk: break
                        if not head: head = chunk[:16]
                        size += len(chunk)
                        if size > MAX_FILE_MB * 1024 * 1024:
                            raise ValueError(f"文件太大（上限 {MAX_FILE_MB} MB）")
                        f.write(chunk)
                        self.status = f"下载中… {size / 1048576:.1f} MB"
            ext = sniff_ext(head)
            if ext is None:
                raise ValueError("下载到的内容不是支持的音频（支持 mp3/ogg/wav/flac）")
            stem = _safe_name(os.path.splitext(name)[0])
            fname = self._unique(stem + ext)
            os.replace(tmp, os.path.join(self.music_dir, fname))
            tmp = None
            result = (True, fname)
        except Exception as e:          # noqa: BLE001
            msg = str(e) if isinstance(e, ValueError) else f"下载失败：{type(e).__name__} {e}"
            result = (False, msg)
        finally:
            if tmp and os.path.exists(tmp):
                try: os.remove(tmp)
                except OSError: pass
        with self._lock:
            self._done.append(result)
            self._busy = False

    def poll(self):
        """主线程每帧调用：收下后台下载的结果。返回新加入的曲目下标列表。"""
        with self._lock:
            done, self._done = self._done, []
        added = []
        for ok, info in done:
            if ok and len(self.items) < MAX_ITEMS:
                if info in self.ignored: self.ignored.remove(info)
                if not self._has(info):
                    self.items.append({"name": os.path.splitext(info)[0], "file": info, "src": "url"})
                added.append(len(self.items) - 1)
                self.status = f"已添加：{os.path.splitext(info)[0]}"
                self.save()
            elif not ok:
                self.status = info
        return added

    @property
    def busy(self):
        return self._busy
