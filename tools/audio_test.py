# tools/audio_test.py
"""音频与设置页验收（无声卡：用假 mixer 记录调用）：
  A1 音频管理器  音量存取/限幅、静音、同名音效限频、音乐切换（淡出→待播→播放）、没有声卡也不崩
  A2 音频文件    所有音效和曲目都存在且格式正确
  A3 游戏触发    开枪/击杀/建成/采完/任务/点击界面 都会放对应音效；音乐按 昼/夜/战斗 切换
  A4 设置面板    键盘/鼠标/拖动滑块；静音；操作模式；界面大小；返回；游戏内菜单进出设置页
  A5 不影响模拟  接上音频与不接音频，模拟状态哈希完全一致
用法： python -m tools.audio_test
"""
import os, sys, tempfile, wave
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
try:
    import pygame
    pygame.init(); pygame.display.set_mode((64, 64))
except ImportError:
    from tools import fake_pygame
    pygame = fake_pygame.install()
from core import audio as A
from core.state_hash import world_hash
from world.game_world import GameWorld
from entities.enemy import Enemy
FAILS = []
def check(n, ok, info=""):
    print(("  ✓ " if ok else "  ✗ ") + n + (f"  {info}" if info and not ok else ""))
    if not ok: FAILS.append(n)

class FakeSound:
    def __init__(self, path): self.path, self.vol, self.n = path, None, 0
    def set_volume(self, v): self.vol = v
    def play(self): self.n += 1
class FakeMusic:
    def __init__(self): self.log = []
    def load(self, p): self.log.append(("load", os.path.basename(p)))
    def play(self, loops=0, fade_ms=0): self.log.append(("play", loops))
    def fadeout(self, ms): self.log.append(("fadeout", ms))
    def set_volume(self, v): self.log.append(("vol", round(v, 3)))
class FakeMixer:
    def __init__(self): self.music = FakeMusic(); self.sounds = []
    def Sound(self, path):
        s = FakeSound(path); self.sounds.append(s); return s

# A1
path = os.path.join(tempfile.mkdtemp(), "audio.json")
a = A.AudioManager(path, mixer=FakeMixer())
check("A1 默认音量", (a.music_vol, a.sfx_vol, a.muted) == (0.5, 0.8, False))
a.set_music_volume(1.7); a.set_sfx_volume(-3)
check("A1 音量限幅在 0~1", a.music_vol == 1.0 and a.sfx_vol == 0.0)
a.set_music_volume(0.3); a.set_sfx_volume(0.6); a.set_muted(True); a.save()
b = A.AudioManager(path, mixer=FakeMixer())
check("A1 音量/静音存盘并读回", (b.music_vol, b.sfx_vol, b.muted) == (0.3, 0.6, True))
open(path, "w").write("坏文件{")
check("A1 坏存档不崩，用默认值", A.AudioManager(path, mixer=FakeMixer()).music_vol == 0.5)
m = FakeMixer(); a = A.AudioManager(None, mixer=m); a.set_sfx_volume(0.5)
a.play("click"); a.play("click")
check("A1 同名音效限频（连续两次只响一次）", len(a.played) == 1 and m.sounds[0].n == 1)
a.play("melee", 0.5)
check("A1 音量 = 距离系数 × 音效音量", abs(m.sounds[1].vol - 0.25) < 1e-6, m.sounds[1].vol)
a.set_muted(True); a.play("shot_pistol")
check("A1 静音时不播放", "shot_pistol" not in a.played)
a.set_muted(False); a.play("shot_bow", 0.0)
check("A1 距离太远（音量≈0）不播放", "shot_bow" not in a.played)
a.set_music("day"); a.update()
check("A1 音乐：首次直接播放并循环", ("load", "music_day.ogg") in m.music.log and ("play", -1) in m.music.log, m.music.log)
m.music.log.clear(); a.set_music("battle"); a.update()
check("A1 换曲先淡出，不立即切换", m.music.log == [("fadeout", 600)], m.music.log)
a._switch_at = 0; a.update()
check("A1 淡出之后播放新曲", ("load", "music_battle.ogg") in m.music.log)
a.set_music("battle"); n0 = len(m.music.log); a.update()
check("A1 同一首不重复加载", len(m.music.log) == n0)
bad = A.AudioManager(None)             # fake pygame 没有 mixer：应静默
check("A1 没有声卡/mixer 时静默不崩", bad.ok is False and bad.play("click") is None and bad.set_music("day") is None and bad.update() is None)
n = A.NullAudio(); n.play("x"); n.set_music("y"); n.update(); n.save()
check("A1 NullAudio 全是空操作", True)

# A2
root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "audio")
bad = []
for nme in A.SFX_NAMES:
    p = os.path.join(root, nme + ".wav")
    try:
        with wave.open(p) as w: ok = w.getnframes() > 100 and w.getframerate() > 8000
    except Exception: ok = False
    if not ok: bad.append(nme)
check("A2 所有音效 wav 存在且可读", not bad, bad)
miss = [t for t in A.TRACKS if not (os.path.isfile(os.path.join(root, f"music_{t}.ogg")) or os.path.isfile(os.path.join(root, f"music_{t}.wav")))]
check("A2 所有曲目存在", not miss, miss)
check("A2 音频总大小合理（< 4MB）", sum(os.path.getsize(os.path.join(root, f)) for f in os.listdir(root)) < 4_000_000)
check("A2 武器 → 音效映射", A.weapon_sound("sniper", "shot") == "shot_sniper" and A.weapon_sound("crossbow", "shot") == "shot_bow"
      and A.weapon_sound("longsword", "melee") == "melee" and A.weapon_sound("fist", "shot") == "shot_pistol")

# A3
f = pygame.font.Font(None, 16); W, H = 1280, 720
class Rec(A.NullAudio):
    def __init__(self): self.calls = []; self.track = None
    def play(self, name, vol=1.0): self.calls.append((name, round(vol, 2)))
    def set_music(self, t): self.track = t
def mk(seed=5):
    g = GameWorld(f, f, f, f, W, H, seed=seed); g.set_screen_size(W, H); g.animals.clear(); return g
def names(g): return [n for n, v in g.audio.calls]
def frame(g):
    s = pygame.Surface((W, H)); g.draw(s, 0.016)
g = mk(); g.audio = Rec(); c = g.colonists[0]
c.recent_shot = ("shot", c.x, c.y, c.x + 50, c.y, (255, 255, 0)); c.weapon_key = "rifle"; g.sim_step()
check("A3 小人开枪 → 步枪声（镜头附近音量大）", any(n == "shot_rifle" and v > 0.3 for n, v in g.audio.calls), g.audio.calls[:4])
g.audio.calls.clear(); c.recent_shot = ("shot", c.x + 99999, c.y, 0, 0, (255, 255, 0)); c.weapon_key = "pistol"; g.sim_step()
check("A3 很远的枪声音量被衰减为 0", all(v == 0 for n, v in g.audio.calls if n == "shot_pistol"), g.audio.calls)
g.audio.calls.clear(); e = Enemy(int(c.x // 32) + 3, int(c.y // 32), "pistol", ctx=g.ctx); e.hp = 0; g.enemies.append(e); g.sim_step()
check("A3 击杀敌人 → enemy_down", "enemy_down" in names(g), g.audio.calls)
g.audio.calls.clear(); bp = g.buildings.add_blueprint("wall", "wood", 70, 70); g.buildings.complete_blueprint(bp); g.sim_step()
check("A3 建成建筑 → build_done", "build_done" in names(g), g.audio.calls)
g.audio.calls.clear(); k = next(iter(g.world.resource_hp)); del g.world.resource_hp[k]; g.sim_step()
check("A3 资源被采完 → harvest_done", "harvest_done" in names(g), g.audio.calls)
g.audio.calls.clear(); g.quests._new(g, "have", "wood", 5, {"stone": 1}, "测试任务"); g.sfx("click")
check("A3 新任务 → quest_new", "quest_new" in names(g))
g.audio.calls.clear(); g.quests.active[-1]["target"] = 0; g.quests.timer = 99; g.game_time.tick = 30; g.quests.update(g)
check("A3 完成任务 → quest_done", "quest_done" in names(g), g.audio.calls)
g.audio.calls.clear(); g.colonists[0].hp = 0; g.sim_step()
check("A3 小人倒下 → colonist_down", "colonist_down" in names(g))
g = mk(); g.audio = Rec(); frame(g); tb = g.toolbar.buttons[0][0].center
g.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(int(tb[0] * g.ui_scale), int(tb[1] * g.ui_scale)), button=1), W, H)
check("A3 点工具栏/界面 → click", "click" in names(g), g.audio.calls)
g = mk(); g.audio = Rec(); g.enemies.clear(); g.game_time.tick = 60 * 20; frame(g)
check("A3 白天 → 日间曲", g.audio.track == "day", g.audio.track)
g.game_time.tick = int(60 * g.game_time.day_length_sec * 0.9); frame(g)
check("A3 夜晚 → 夜间曲", g.game_time.is_night and g.audio.track == "night", (g.game_time.is_night, g.audio.track))
g.enemies.append(Enemy(10, 10, "pistol", ctx=g.ctx)); frame(g)
check("A3 有敌人 → 战斗曲", g.audio.track == "battle")
g.enemies.clear(); frame(g)
check("A3 敌人消失后战斗曲还会持续一阵（不来回切）", g.audio.track == "battle")

# A4
from ui.settings_panel import SettingsPanel
p = SettingsPanel(); p.audio = A.AudioManager(None, mixer=FakeMixer())
s = pygame.Surface((W, H)); p.draw(s, W, H, f, f)
check("A4 面板能绘制，所有行都有区域", all(k in p.rects for k in ("input", "music", "sfx", "mute", "ui", "fullscreen", "back", "music_bar", "ui_plus")), list(p.rects))
bar = p.rects["music_bar"]
p.handle_click((bar.x + bar.w * 0.8, bar.centery)); p.draw(s, W, H, f, f)
check("A4 点击滑块条设置音乐音量", abs(p.audio.music_vol - 0.8) < 0.03 and p.dragging == "music", p.audio.music_vol)
p.handle_motion((bar.x + bar.w * 0.2, bar.centery))
check("A4 拖动滑块", abs(p.audio.music_vol - 0.2) < 0.03)
p.handle_motion((bar.x - 500, 0)); check("A4 拖出范围时钳在 0", p.audio.music_vol == 0.0)
p.handle_release(); check("A4 松手结束拖动", p.dragging is None)
p.sel = 2; p.handle_key(pygame.K_RIGHT); check("A4 键盘 → 加 5% 音效", abs(p.audio.sfx_vol - 0.85) < 1e-6, p.audio.sfx_vol)
p.sel = 3; p.handle_key(pygame.K_RETURN); check("A4 回车切换静音", p.audio.muted is True)
p.draw(s, W, H, f, f); p.handle_click((p.rects["mute"].centerx, p.rects["mute"].centery)); check("A4 点击再切回", p.audio.muted is False)
p.sel = 0; check("A4 操作模式行 → 返回 input 动作", p.handle_key(pygame.K_RETURN) == "input")
check("A4 点 ＋/－ → 界面大小动作", p.handle_click(p.rects["ui_plus"].center) == "ui_plus" and p.handle_click(p.rects["ui_minus"].center) == "ui_minus")
check("A4 Esc → back", p.handle_key(pygame.K_ESCAPE) == "back")
p.has_fullscreen = False; check("A4 主菜单里不显示全屏行", "fullscreen" not in p.rows())
for (w, h) in ((800, 600), (1280, 720), (1920, 1080)):
    p.draw(pygame.Surface((w, h)), w, h, f, f)
check("A4 多种窗口尺寸都能画", True)

g = mk(); g.audio = A.AudioManager(None, mixer=FakeMixer())
def key(k): g.handle_event(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode=""), W, H)
def draw_ui(): s = pygame.Surface((g.ui_w, g.ui_h)); g._draw_ui(s, g.ui_w, g.ui_h)
key(pygame.K_m); check("A4 游戏菜单里有「设置」行", any(n == "settings" for n, _ in __import__("ui.game_menu", fromlist=["ITEMS"]).ITEMS))
draw_ui()
r = g.menu.rects["settings"]
g.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(int(r.centerx * g.ui_scale), int(r.centery * g.ui_scale)), button=1), W, H)
check("A4 点「设置」进入设置页", g.menu.active and g.menu.page == "settings")
draw_ui(); ir = g.menu.panel.rects["input"]
t0 = g.touch.enabled
g.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(int(ir.centerx * g.ui_scale), int(ir.centery * g.ui_scale)), button=1), W, H)
check("A4 设置页里点「操作模式」切换电脑/触屏", g.touch.enabled != t0 and g.menu.page == "settings")
draw_ui(); br = g.menu.panel.rects["music_bar"]
for typ, x in ((pygame.MOUSEBUTTONDOWN, br.x + br.w * 0.6), (pygame.MOUSEMOTION, br.x + br.w * 0.3), (pygame.MOUSEBUTTONUP, br.x + br.w * 0.3)):
    ev = pygame.event.Event(typ, pos=(int(x * g.ui_scale), int(br.centery * g.ui_scale)), button=1, rel=(0, 0), buttons=(1, 0, 0))
    g.handle_event(ev, W, H)
check("A4 游戏内拖动音乐滑块有效", abs(g.audio.music_vol - 0.3) < 0.04, g.audio.music_vol)
x0 = g.camera.x
key(pygame.K_ESCAPE); check("A4 Esc 先回到菜单主页（不是关掉）", g.menu.active and g.menu.page == "main")
key(pygame.K_ESCAPE); check("A4 再 Esc 关闭菜单", not g.menu.active)
key(pygame.K_m); g.menu.page = "settings"; key(pygame.K_m); check("A4 设置页里按 M 直接关闭菜单", not g.menu.active)

# A5
def run(audio):
    g = mk(seed=12); g.audio = audio
    for _ in range(900):
        if _ == 300: g.colonists[0].recent_shot = ("shot", g.colonists[0].x, g.colonists[0].y, 0, 0, (255, 255, 0))
        g.sim_step()
        if _ % 50 == 0: frame(g)
    return world_hash(g)
check("A5 接音频 / 不接音频，状态哈希完全一致", run(Rec()) == run(A.NullAudio()))
print("FAILS:", FAILS); sys.exit(1 if FAILS else 0)
