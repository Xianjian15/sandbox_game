# tools/playlist_test.py
"""歌单验收（无声卡：假 mixer；链接用本机 http 服务）：
  P1 歌单数据   添加/复制/去重/格式与大小限制/删除后刷新不加回/坏存档/存取
  P2 文件夹     放进 music/ 的文件，刷新后出现；被删的文件从歌单消失
  P3 链接下载   直链 mp3/ogg 成功；网页(text/html)、伪装成音频的垃圾、过大、坏链接 都给出明确提示
  P4 播放控制   歌单模式下播放/暂停/上一首/下一首、放完自动下一首、单曲循环、随机、坏文件自动跳过
  P5 自动 ↔ 歌单 歌单模式忽略昼夜自动换曲；切回自动恢复；启动时按上次模式接着放
  P6 面板与拖放 面板按钮、输入框(键入/粘贴/回车)、拖入窗口的音频进歌单、工具栏/P 键
  P7 不影响模拟 有无歌单操作，模拟哈希一致
用法： python -m tools.playlist_test
"""
import os, sys, tempfile, threading, time, http.server, socketserver, struct, wave, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
try:
    import pygame
    pygame.init(); pygame.display.set_mode((64, 64))
except ImportError:
    from tools import fake_pygame
    pygame = fake_pygame.install()
from core import audio as A
from core.playlist import Playlist, sniff_ext
from core.state_hash import world_hash
from world.game_world import GameWorld
FAILS = []
def check(n, ok, info=""):
    print(("  ✓ " if ok else "  ✗ ") + n + (f"  {info}" if info and not ok else ""))
    if not ok: FAILS.append(n)

class FakeMusic:
    def __init__(self): self.log = []; self.busy = True; self.bad = set()
    def load(self, p):
        if os.path.basename(p) in self.bad: raise RuntimeError("坏文件")
        self.log.append(("load", os.path.basename(p)))
    def play(self, loops=0, fade_ms=0): self.log.append(("play", loops))
    def fadeout(self, ms): self.log.append(("fadeout", ms))
    def set_volume(self, v): pass
    def get_busy(self): return self.busy
    def pause(self): self.log.append(("pause",))
    def unpause(self): self.log.append(("unpause",))
class FakeMixer:
    def __init__(self): self.music = FakeMusic()
    def Sound(self, p): raise RuntimeError("no sound")
def loads(m): return [x[1] for x in m.music.log if x[0] == "load"]

def wav_bytes():
    import io
    b = io.BytesIO(); w = wave.open(b, "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
    w.writeframes(b"\x00\x00" * 800); w.close(); return b.getvalue()
WAV = wav_bytes()
OGG = b"OggS" + b"\x00" * 60
MP3 = b"ID3\x03" + b"\x00" * 60

tmp = tempfile.mkdtemp()
src = os.path.join(tmp, "src"); os.makedirs(src)
def mkfile(name, data=WAV):
    p = os.path.join(src, name); open(p, "wb").write(data); return p

# P1
mdir = os.path.join(tmp, "m1"); pl = Playlist(os.path.join(tmp, "pl1.json"), mdir)
check("P1 初始为空、自动模式", pl.items == [] and pl.mode == "auto" and pl.loop == "all")
ok, msg = pl.add_file(mkfile("a.wav")); check("P1 添加本地文件", ok and len(pl.items) == 1 and os.path.isfile(os.path.join(mdir, "a.wav")), msg)
ok, msg = pl.add_file(mkfile("a.wav")); check("P1 同名文件自动改名而不是覆盖", ok and len(pl.items) == 2 and pl.items[1]["file"] == "a_2.wav", pl.items)
ok, msg = pl.add_file(mkfile("x.txt", b"hi")); check("P1 不支持的格式被拒绝", not ok and len(pl.items) == 2, msg)
ok, msg = pl.add_file(os.path.join(src, "不存在.mp3")); check("P1 找不到文件被拒绝", not ok)
big = os.path.join(src, "big.ogg")
with open(big, "wb") as f: f.truncate(61 * 1024 * 1024)
ok, msg = pl.add_file(big); check("P1 过大的文件被拒绝", not ok and "太大" in msg, msg); os.remove(big)
pl.add_file(mkfile("中文 歌:名?.mp3", MP3)); check("P1 文件名里的非法字符被替换", pl.items[-1]["file"] == "中文 歌_名_.mp3", pl.items[-1])
pl.mode, pl.loop = "list", "shuffle"; pl.save()
pl2 = Playlist(os.path.join(tmp, "pl1.json"), mdir)
check("P1 存盘并读回（歌曲/模式/循环）", [i["file"] for i in pl2.items] == [i["file"] for i in pl.items] and (pl2.mode, pl2.loop) == ("list", "shuffle"))
pl2.remove(0); pl2.refresh()
check("P1 删除后刷新不会自动加回", not any(i["file"] == "a.wav" for i in pl2.items))
open(os.path.join(tmp, "bad.json"), "w").write("坏{")
check("P1 坏存档不崩，当作空歌单", Playlist(os.path.join(tmp, "bad.json"), os.path.join(tmp, "m_bad")).items == [])
check("P1 文件头识别", (sniff_ext(OGG), sniff_ext(MP3), sniff_ext(WAV), sniff_ext(b"fLaC1234"), sniff_ext(b"<html>")) == (".ogg", ".mp3", ".wav", ".flac", None))

# P2
mdir = os.path.join(tmp, "m2"); os.makedirs(mdir)
shutil.copy(mkfile("one.ogg", OGG), mdir); shutil.copy(mkfile("two.wav"), mdir); open(os.path.join(mdir, "note.txt"), "w").write("x")
pl = Playlist(os.path.join(tmp, "pl2.json"), mdir)
check("P2 启动时自动扫描 music/（只收音频）", sorted(i["file"] for i in pl.items) == ["one.ogg", "two.wav"], pl.items)
shutil.copy(mkfile("three.mp3", MP3), mdir)
check("P2 刷新发现新放进去的文件", pl.refresh() == 1 and len(pl.items) == 3)
os.remove(os.path.join(mdir, "one.ogg")); pl.refresh()
check("P2 文件被删后从歌单消失", sorted(i["file"] for i in pl.items) == ["three.mp3", "two.wav"])

# P3 链接
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        routes = {"/song.mp3": ("audio/mpeg", MP3 + b"\x00" * 5000), "/s2.ogg": ("application/ogg", OGG),
                  "/page": ("text/html", b"<html>youtube</html>"), "/fake.mp3": ("audio/mpeg", b"this is not audio at all"),
                  "/noext": ("application/octet-stream", WAV)}
        if self.path == "/huge.mp3":
            self.send_response(200); self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Content-Length", str(200 * 1024 * 1024)); self.end_headers(); return
        if self.path in routes:
            ct, body = routes[self.path]
            self.send_response(200); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        else:
            self.send_response(404); self.end_headers()
srv = socketserver.TCPServer(("127.0.0.1", 0), H); port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{port}"
mdir = os.path.join(tmp, "m3"); pl = Playlist(os.path.join(tmp, "pl3.json"), mdir)
def dl(path):
    ok, msg = pl.add_url(base + path)
    t0 = time.time()
    while pl.busy and time.time() - t0 < 10: time.sleep(0.02)
    time.sleep(0.05); pl.poll(); return ok
check("P3 非 http 链接被拒绝", pl.add_url("ftp://x/y.mp3")[0] is False and pl.add_url("随便写写")[0] is False)
n0 = len(pl.items); dl("/song.mp3")
check("P3 mp3 直链下载并加入歌单", len(pl.items) == n0 + 1 and pl.items[-1]["file"] == "song.mp3" and pl.items[-1]["src"] == "url", (pl.items, pl.status))
dl("/s2.ogg"); check("P3 ogg 直链", pl.items[-1]["file"] == "s2.ogg")
dl("/noext"); check("P3 没有扩展名时按文件头识别（wav）", pl.items[-1]["file"].endswith(".wav"), pl.items[-1])
n = len(pl.items); dl("/page")
check("P3 网页链接给出明确提示（不支持 YouTube 之类）", len(pl.items) == n and "网页" in pl.status, pl.status)
n = len(pl.items); dl("/fake.mp3"); check("P3 伪装成音频的垃圾被拒绝", len(pl.items) == n and "不是支持的音频" in pl.status, pl.status)
dl("/huge.mp3"); check("P3 超大文件被拒绝", len(pl.items) == n and "太大" in pl.status, pl.status)
dl("/missing.mp3"); check("P3 404 给出失败提示", len(pl.items) == n and "失败" in pl.status, pl.status)
check("P3 下载没有留下半成品文件", not [f for f in os.listdir(mdir) if f.endswith(".part")], os.listdir(mdir))
pl.add_url("http://127.0.0.1:1/x.mp3"); t0 = time.time()
while pl.busy and time.time() - t0 < 10: time.sleep(0.02)
time.sleep(0.05); pl.poll()
check("P3 连不上的地址不会卡死，给出失败提示", not pl.busy and "失败" in pl.status, pl.status)
srv.shutdown()

# P4
def mkaudio(names, **kw):
    d = tempfile.mkdtemp(); md = os.path.join(d, "music"); os.makedirs(md)
    for n in names: open(os.path.join(md, n), "wb").write(WAV)
    m = FakeMixer(); a = A.AudioManager(os.path.join(d, "audio.json"), mixer=m); return a, m, d
a, m, d = mkaudio(["a.wav", "b.wav", "c.wav"])
check("P4 扫描到 3 首", len(a.pl.items) == 3)
a.set_mode("list")
check("P4 进入歌单模式立即播放第一首", loads(m) == ["a.wav"] and a.now_playing == "a", loads(m))
a.next_track(); a.next_track()
check("P4 下一首（顺序）", loads(m) == ["a.wav", "b.wav", "c.wav"])
a.next_track(); check("P4 列表循环：最后一首后回到第一首", loads(m)[-1] == "a.wav")
a.prev_track(); check("P4 上一首", loads(m)[-1] == "c.wav")
a.play_pause(); a.play_pause()
check("P4 暂停 / 继续", [x for x in m.music.log if x[0] in ("pause", "unpause")] == [("pause",), ("unpause",)] and a.paused is False)
a.play_pause(); m.music.busy = False; a._list_started = 0; n = len(loads(m)); a.update()
check("P4 暂停时放完也不会自动跳歌", len(loads(m)) == n)
a.play_pause(); a._list_started = 0; a.update()
check("P4 放完自动下一首", len(loads(m)) == n + 1 and loads(m)[-1] == "a.wav", loads(m))
a.cycle_loop(); check("P4 循环方式 全部→单曲", a.pl.loop == "one")
a.play_index(1); check("P4 单曲循环用 loops=-1", m.music.log[-1] == ("play", -1), m.music.log[-1])
a.cycle_loop(); check("P4 单曲→随机", a.pl.loop == "shuffle")
seen = set(); a.play_index(0)
for _ in range(30): a.next_track(); seen.add(a.pl.index)
check("P4 随机播放会换到别的曲子（不重复当前）", len(seen) >= 2 and a.pl.index in (0, 1, 2))
a.pl.loop = "all"; m.music.bad = {"b.wav"}; a.play_index(0); a.next_track()
check("P4 坏文件自动跳过", loads(m)[-1] == "c.wav" and a.now_playing == "c", (loads(m)[-3:], a.now_playing))
m.music.bad = {"a.wav", "b.wav", "c.wav"}; a.next_track()
check("P4 全是坏文件也不会死循环", a.now_playing is None)

# P5
a, m, d = mkaudio(["a.wav"]); a.set_music("day")
check("P5 自动模式放内置昼曲", a.current == "day")
a.set_mode("list"); n = len(m.music.log); a.set_music("night"); a.set_music("battle"); a.update()
check("P5 歌单模式忽略昼夜/战斗自动换曲", len(m.music.log) == n and a.now_playing == "a")
a.set_mode("auto"); check("P5 切回自动恢复最近的自动曲（battle）", a.current == "battle" and a.now_playing is None, a.current)
a.set_mode("list"); a.pl.save()
m2 = FakeMixer(); b = A.AudioManager(os.path.join(d, "audio.json"), mixer=m2)
check("P5 下次启动按上次的歌单模式接着放", b.pl.mode == "list" and loads(m2) == ["a.wav"], loads(m2))
e = A.NullAudio(); e.set_mode("list"); e.next_track(); e.play_pause()
check("P5 NullAudio 接口齐全不崩", True)
a2 = A.AudioManager(os.path.join(tempfile.mkdtemp(), "audio.json"), mixer=FakeMixer()); a2.set_mode("list")
check("P5 歌单为空时选歌单模式，自动曲照常", not a2.list_mode)

# P6
f = pygame.font.Font(None, 16)
def mkgame(files=()):
    g = GameWorld(f, f, f, f, 1280, 720, seed=1); g.set_screen_size(1280, 720)
    d = tempfile.mkdtemp(); md = os.path.join(d, "music"); os.makedirs(md)
    for n in files: open(os.path.join(md, n), "wb").write(WAV)
    mx = FakeMixer(); g.audio = A.AudioManager(os.path.join(d, "audio.json"), mixer=mx); return g, mx
def draw(g):
    s = pygame.Surface((g.ui_w, g.ui_h)); g._draw_ui(s, g.ui_w, g.ui_h)
def key(g, k, **kw): g.handle_event(pygame.event.Event(pygame.KEYDOWN, key=k, mod=kw.get("mod", 0), unicode=kw.get("u", "")), 1280, 720)
def click(g, p): g.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(int(p[0] * g.ui_scale), int(p[1] * g.ui_scale)), button=1), 1280, 720)
def btn(g, bid, data=None):
    return next(r for r, b, dd in g.music_panel.btns if b == bid and (data is None or dd == data))
g, mx = mkgame(["a.wav", "b.wav"])
key(g, pygame.K_p); draw(g)
check("P6 P 键打开音乐面板", g.mode == "music" and len(g.music_panel.btns) > 5)
check("P6 面板内点击不穿透", g.is_mouse_in_ui((int(g.music_panel.panel_rect.centerx * g.ui_scale), int(g.music_panel.panel_rect.centery * g.ui_scale))))
click(g, btn(g, "mode", "list").center); draw(g)
check("P6 点「我的歌单」进入歌单模式并开始播放", g.audio.pl.mode == "list" and g.audio.now_playing == "a")
click(g, btn(g, "next").center); draw(g)
check("P6 点「下首」", g.audio.now_playing == "b")
click(g, btn(g, "loop").center); check("P6 点循环按钮切换", g.audio.pl.loop == "one"); draw(g)
click(g, btn(g, "play", 0).center); draw(g)
check("P6 点列表里的歌曲播放", g.audio.now_playing == "a")
v0 = g.audio.music_vol; click(g, btn(g, "vol", -0.1).center); draw(g)
check("P6 音量 -", g.audio.music_vol < v0)
click(g, btn(g, "mute").center); check("P6 静音按钮", g.audio.muted); draw(g)
sv = g.audio.sfx_vol; click(g, btn(g, "sfxvol", -0.1).center); check("P6 音乐面板里也能调音效音量", g.audio.sfx_vol < sv); draw(g)
click(g, btn(g, "del", 0).center); draw(g)
check("P6 点 × 删除正在播的歌：停止且从列表消失", len(g.audio.pl.items) == 1 and g.audio.now_playing is None)
# 输入框
click(g, btn(g, "add_url").center); draw(g)
check("P6 点「添加链接」打开输入框，并接管文字输入", g.music_panel.editing and g.wants_text_input())
g.handle_event(pygame.event.Event(pygame.TEXTINPUT, text="http://127.0.0.1:1/q.mp3"), 1280, 720)
check("P6 输入框收到文字（不触发快捷键）", g.music_panel.text == "http://127.0.0.1:1/q.mp3" and g.mode == "music")
key(g, pygame.K_BACKSPACE); check("P6 退格", g.music_panel.text.endswith("q.mp"))
g.music_panel.clipboard = lambda: "  http://x/y.mp3\nsecond line"; g.music_panel.text = ""
key(g, pygame.K_v, mod=pygame.KMOD_CTRL); check("P6 Ctrl+V 粘贴（取第一行）", g.music_panel.text == "http://x/y.mp3", g.music_panel.text)
key(g, pygame.K_ESCAPE); check("P6 Esc 只关输入框，不关面板", not g.music_panel.editing and g.mode == "music")
click(g, btn(g, "add_url").center); g.music_panel.text = "不是链接"; key(g, pygame.K_RETURN)
check("P6 回车提交非法链接给出提示且不崩", "http" in g.music_panel.msg, g.music_panel.msg)
key(g, pygame.K_ESCAPE)
# 选文件
p1 = mkfile("pick1.ogg", OGG); p2 = mkfile("pick2.mp3", MP3)
g.music_panel.picker = lambda: [p1, p2, os.path.join(src, "bad.txt")]
n = len(g.audio.pl.items); click(g, btn(g, "add_file").center)
check("P6 文件选择窗口：多选添加（坏的被跳过）", len(g.audio.pl.items) == n + 2, g.music_panel.msg)
g.music_panel.picker = lambda: (_ for _ in ()).throw(RuntimeError("没有可用的文件选择窗口"))
click(g, btn(g, "add_file").center); check("P6 没有 tkinter 时给提示不崩", "文件选择" in g.music_panel.msg)
opened = []; g.music_panel.folder_opener = lambda p: opened.append(p) or True
click(g, btn(g, "folder").center); check("P6 打开音乐文件夹", opened == [g.audio.music_dir])
# 拖放
g2, _ = mkgame(); n = len(g2.audio.pl.items)
g2.handle_event(pygame.event.Event(pygame.DROPFILE, file=mkfile("dropped.flac", b"fLaC" + b"\x00" * 40)), 1280, 720)
check("P6 把音频拖进窗口：任何界面下都加入歌单", len(g2.audio.pl.items) == n + 1 and g2.mode is None)
g2.handle_event(pygame.event.Event(pygame.DROPFILE, file=mkfile("pic.png", b"x")), 1280, 720)
check("P6 拖入非音频被忽略", len(g2.audio.pl.items) == n + 1)
# 工具栏
g3, _ = mkgame(); draw(g3)
tb = next(r for r, mm in g3.toolbar.buttons if mm == "music"); click(g3, tb.center)
check("P6 工具栏「音乐」按钮可打开", g3.mode == "music")
key(g3, pygame.K_ESCAPE); check("P6 Esc 关闭面板", g3.mode is None)
# 滚动
g4, _ = mkgame([f"t{i:02d}.wav" for i in range(12)]); key(g4, pygame.K_p); draw(g4)
click(g4, btn(g4, "scroll", 7).center); draw(g4)
check("P6 列表过长可翻页", g4.music_panel.scroll == 5, g4.music_panel.scroll)

# P7
def sim(touch):
    g = GameWorld(f, f, f, f, 1280, 720, seed=9); g.set_screen_size(1280, 720)
    d = tempfile.mkdtemp(); md = os.path.join(d, "music"); os.makedirs(md); open(os.path.join(md, "a.wav"), "wb").write(WAV)
    g.audio = A.AudioManager(os.path.join(d, "audio.json"), mixer=FakeMixer())
    if touch: g.audio.set_mode("list"); g.audio.next_track(); g.mode = "music"; draw(g)
    for _ in range(300): g.sim_step()
    return world_hash(g)
check("P7 歌单/音乐面板对模拟哈希零影响", sim(False) == sim(True))
print("FAILS:", FAILS)
