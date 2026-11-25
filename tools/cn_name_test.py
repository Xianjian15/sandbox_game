# tools/cn_name_test.py
"""中文用户名 + 小人面板位置 验收。
  C1 数据层   中文名清洗/限长/重名/存盘读盘/联机传输(JSON帧)/大厅发现包
  C2 菜单输入 资料页：输入法组合文字(TEXTEDITING)只显示不入库、确认(TEXTINPUT)才写入；组合中退格不删已确认字；生僻字/emoji不崩
  C3 小人面板 在多种窗口大小、各模式下：位于左下角，且与底部工具栏/建造菜单不重叠，也不出屏幕
用法： python -m tools.cn_name_test
"""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
try:
    import pygame
    pygame.init(); pygame.display.set_mode((64, 64))
except ImportError:
    from tools import fake_pygame
    pygame = fake_pygame.install()
from core import profile as P
from net.framing import pack, FrameBuffer
FAILS = []
def check(n, ok, info=""):
    print(("  ✓ " if ok else "  ✗ ") + n + (f"  {info}" if info and not ok else ""))
    if not ok: FAILS.append(n)

# C1
check("C1a 中文名保留", P.sanitize_name("  小明同学 ") == "小明同学")
check("C1b 限长按字数", P.sanitize_name("一二三四五六七八九十甲乙丙丁") == "一二三四五六七八九十甲乙")
check("C1c 中英混合", P.sanitize_name("张三Bob_01") == "张三Bob_01")
check("C1d 重名加序号", P.dedupe_names(["小明", "小明"]) == ["小明", "小明(2)"])
d = tempfile.mkdtemp(); path = os.path.join(d, "p.json")
pr = P.Profile("李雷", None, path); pr.save()
check("C1e 存盘读盘", P.Profile.load(path).name == "李雷")
fb = FrameBuffer(); msgs = fb.feed(pack({"t": "hello", "prof": P.clean_wire({"name": "韩梅梅", "av": None}, "x")}))
check("C1f 联机帧往返", msgs and msgs[0]["prof"]["name"] == "韩梅梅")
check("C1g 生僻字/补充平面字往返", FrameBuffer().feed(pack({"n": "𠮷野家"}))[0]["n"] == "𠮷野家")

# C2
from ui.menu import MenuModel
class Clock:
    t = 0.0
    def __call__(self): return self.t
m = MenuModel({"seed": 1, "delay": 0, "profile": P.Profile("玩家111", None, None), "udp_port": 0}, clock=Clock()) if False else None
try:
    import tools.menu_test as MT
    m = MenuModel(MT.cfg(MT.free_udp_port()), clock=MT.Clock())
    MT.click(m, "multi"); MT.click(m, "profile")
    for _ in range(30): m.key("backspace")
    m.text_editing("xiao ming")
    check("C2a 组合文字不入库", m.text == "" and m.composition == "xiao ming")
    m.key("backspace")
    check("C2b 组合中退格不动已确认文字", m.text == "")
    m.text_input("小明")
    check("C2c 确认后写入并清空组合", m.text == "小明" and m.composition == "")
    m.text_editing("ba"); m.key("backspace")
    check("C2d 组合中退格保护", m.text == "小明")
    m.text_editing(""); m.key("backspace")
    check("C2e 无组合退格删字", m.text == "小")
    m.text_input("𠮷😀\x07"); check("C2f 特殊字符不崩/控制符被滤", "\x07" not in m.text)
    m.text_input("字" * 30); check("C2g 上限", len(m.text) <= P.NAME_MAX)
    m.text = "测试名"; m.key("enter")
    check("C2h 保存中文名", m.profile.name == "测试名", m.profile.name)
    m.close()
except Exception as e:                                                # noqa: BLE001
    import traceback; traceback.print_exc(); check("C2 菜单流程", False, repr(e))

# C3
from world.game_world import GameWorld
f = pygame.font.Font(None, 16)
for (w, h) in ((1280, 720), (1920, 1080), (800, 600), (2560, 1440)):
    g = GameWorld(f, f, f, f, w, h, seed=1)
    c = g.colonists[0]; c.selected = True
    for mode in (None, "build", "research"):
        g.mode = mode
        if mode == "build":
            g.build_menu.active_kind = None
        g._place_hud()
        r = g.hud.panel_rect; bh = g.get_bottom_ui_height()
        ok = r.x < 40 and r.bottom <= g.ui_h - bh and r.y >= 0
        check(f"C3 {w}x{h} 模式={mode} 左下角且不挡底栏", ok, f"rect={r} ui_h={g.ui_h} bottom={bh}")
    g.mode = None; g._place_hud()
    check(f"C3 {w}x{h} 面板内点击被界面吞掉", g.is_mouse_in_ui((int(g.hud.panel_rect.x + 5) * g.ui_scale, int(g.hud.panel_rect.y + 5) * g.ui_scale)))
print("FAILS:", FAILS); sys.exit(1 if FAILS else 0)
