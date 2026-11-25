# tools/ui_scale_test.py
"""界面自动缩放验收测试。

有真 pygame 就用真的（SDL dummy 驱动）；没有就用 tools/fake_pygame（只在云端沙盒用）。游戏本体 GameWorld 是真的。

  U1 缩放计算      各种窗口尺寸的比例/逻辑尺寸；偏好档位；偏好存取（含坏文件）
  U2 1280×720      比例 1.0：界面直接画在屏幕上（不分配画布、不缩放），点击和以前完全一样
  U3 1920×1080     比例 1.5：界面画在 1280×720 逻辑画布上并整体缩放到窗口；点工具栏按钮（按窗口坐标）能正确切换模式
  U4 地图点击      缩放后点地图仍按真实窗口坐标选中小人；点在左上角状态面板上被界面吞掉，不会穿透去取消选择
  U5 底部界面      框选模式下点底部工具栏不会开始框地图，点地图才会
  U6 右侧面板      窗口变宽后，右侧建筑面板贴着逻辑画面右边（而不是窗口右边）
  U7 小窗口        800×600：比例缩小，界面整体缩小并仍可点击
  U8 偏好调整      Ctrl +/- 的偏好：比例随之变化，提示文字出现，最大/最小档位夹住
  U9 菜单          菜单在放大窗口里：按窗口坐标点按钮能触发；Ctrl+ 调整
  U10 对话框       退出确认/连接提示在缩放下画在逻辑画布上
  U11 全状态绘制   建造/研究/农田弹窗/帮助/警告/各种面板/联机玩家栏…在缩放下都能画，不抛异常
用法（项目根目录）：  python -m tools.ui_scale_test
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

FAKE = False
try:
    import pygame
    pygame.init()
    pygame.display.set_mode((64, 64))
except ImportError:
    from tools import fake_pygame
    pygame = fake_pygame.install()
    FAKE = True

from core import ui_scale as U                           # noqa: E402
from world.game_world import GameWorld                   # noqa: E402

FAILS = []
CALLS = []
_orig_smooth = pygame.transform.smoothscale
_POS = [(0, 0)]


def _smooth(src, size, dest=None):
    CALLS.append((src.get_size(), tuple(size)))
    return _orig_smooth(src, size, dest) if dest is not None else _orig_smooth(src, size)


pygame.transform.smoothscale = _smooth
pygame.mouse.get_pos = lambda: _POS[0]
pygame.key.get_mods = lambda: 0


def check(name, cond, extra=""):
    print(("  ✓ " if cond else "  ✗ ") + name + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        FAILS.append(name)


def mk(w=1280, h=720):
    f = pygame.font.Font(None, 16)
    g = GameWorld(f, f, f, f, 1280, 720, seed=42)
    g.set_screen_size(w, h)
    return g


def frame(g, w, h):
    s = pygame.Surface((w, h))
    CALLS.clear()
    g.draw(s, 0.016)
    return s


def mouse(g, kind, pos, w, h, button=1):
    _POS[0] = pos
    ev = pygame.event.Event(kind, pos=pos, button=button) if kind != pygame.MOUSEMOTION \
        else pygame.event.Event(kind, pos=pos, rel=(0, 0), buttons=(0, 0, 0))
    g.handle_event(ev, w, h)


def click(g, pos, w, h):
    mouse(g, pygame.MOUSEBUTTONDOWN, pos, w, h)
    mouse(g, pygame.MOUSEBUTTONUP, pos, w, h)


def to_native(p, s):
    return int(p[0] * s), int(p[1] * s)


def button_center(g, key):
    r = next(r for r, k in g.toolbar.buttons if k == key)
    return r.centerx, r.centery


def u1():
    print("== U1 缩放计算 ==")
    cases = {(1280, 720): (1.0, (1280, 720)), (1920, 1080): (1.5, (1280, 720)), (2560, 1440): (2.0, (1280, 720)),
             (3840, 2160): (3.0, (1280, 720)), (2560, 1080): (1.5, (1707, 720)), (800, 600): (0.6, (1334, 1000))}
    bad = {k: (U.compute_scale(*k), U.logical_size(*k, U.compute_scale(*k))) for k, v in cases.items()
           if (U.compute_scale(*k), U.logical_size(*k, U.compute_scale(*k))) != v}
    check("常见分辨率的比例与逻辑尺寸", not bad, bad)
    ok = all(abs(U.logical_size(w, h, U.compute_scale(w, h))[0] * U.compute_scale(w, h) - w) < 1 / 0.6 + 1
             for w, h in [(1366, 768), (1600, 900), (1000, 700), (2000, 900)])
    check("逻辑尺寸×比例 覆盖整个窗口（不留黑边）", ok)
    check("逻辑坐标换算", U.to_logical((1919, 1079), 1.5) == (1279, 719) and U.to_logical((10, 10), 1.0) == (10, 10))
    check("偏好档位：放大/缩小/复位/夹住", U.step_pref(1.0, 1) == 1.125 and U.step_pref(1.0, -1) == 0.875
          and U.step_pref(2.0, 1) == 2.0 and U.step_pref(0.75, -1) == 0.75 and U.step_pref(1.5, 0) == 1.0)
    check("偏好影响比例", U.compute_scale(1280, 720, 1.5) == 1.5 and U.compute_scale(1920, 1080, 0.75) == 1.1)
    d = tempfile.mkdtemp()
    path = os.path.join(d, "x", "ui.json")
    check("偏好存取", U.save_pref(path, 1.25) and U.load_pref(path) == 1.25)
    open(path, "w").write("{坏")
    check("坏文件/缺文件回落默认", U.load_pref(path) == 1.0 and U.load_pref(os.path.join(d, "none.json")) == 1.0)
    open(path, "w").write('{"ui_pref": 99}')
    check("越界偏好回落默认", U.load_pref(path) == 1.0)


def u2():
    print("== U2 1280×720 ==")
    g = mk(1280, 720)
    frame(g, 1280, 720)
    check("比例 1.0：不缩放、不建画布", g.ui_scale == 1.0 and not CALLS and g.ui_layer.surf is None, CALLS)
    frame(g, 1280, 720)
    click(g, button_center(g, "build"), 1280, 720)
    check("点工具栏：进入建造模式", g.mode == "build", g.mode)


def u3():
    print("== U3 1920×1080 ==")
    g = mk(1920, 1080)
    frame(g, 1920, 1080)
    check("比例 1.5，逻辑尺寸 1280×720", g.ui_scale == 1.5 and (g.ui_w, g.ui_h) == (1280, 720), (g.ui_scale, g.ui_w, g.ui_h))
    check("界面画在 1280×720 逻辑画布上", g.ui_layer.surf is not None and g.ui_layer.surf.get_size() == (1280, 720))
    check("整体缩放到窗口（smoothscale 1280×720 → 1920×1080）", ((1280, 720), (1920, 1080)) in CALLS, CALLS)
    lc = button_center(g, "build")
    right = (lc[0] * 1.5, lc[1] * 1.5)
    click(g, to_native(lc, 1.5), 1920, 1080)
    check("点工具栏按钮（窗口坐标 = 逻辑坐标×1.5）切换模式", g.mode == "build", (g.mode, lc))
    g.mode = None
    click(g, lc, 1920, 1080)       # 旧代码的坐标（不换算）不应命中同一个按钮
    check("不换算的坐标不会误触（旧行为已修正）", g.mode != "build" or lc == to_native(lc, 1.5), g.mode)
    close = None
    g.mode = "research"
    frame(g, 1920, 1080)
    cl = button_center(g, "close")
    click(g, to_native(cl, 1.5), 1920, 1080)
    check("右下角「关闭」按钮可点", g.mode is None, g.mode)


def u4():
    print("== U4 地图点击 / 面板吞点击 ==")
    W, H = 1920, 1080
    g = mk(W, H)
    c = g.colonists[0]
    g.camera.x, g.camera.y = c.x - W / 2, c.y - H / 2
    g.camera._clamp()
    frame(g, W, H)
    sx, sy = g.camera.world_to_screen(c.x, c.y)
    check("小人在窗口内", 0 <= sx < W and 0 <= sy < H - 100, (sx, sy))
    click(g, (int(sx), int(sy)), W, H)
    check("按真实窗口坐标点小人：选中", c.selected)
    frame(g, W, H)
    p = (200, 350)                 # 窗口坐标；换成逻辑坐标 (133,233) 落在状态面板(10,60,320,190)里
    check("is_mouse_in_ui 用窗口坐标：落在状态面板上", g.is_mouse_in_ui(p) is True)
    check("面板外不算", g.is_mouse_in_ui((1500, 500)) is False)
    click(g, p, W, H)
    check("点在状态面板上：小人保持选中（点击被界面吞掉）", c.selected)
    click(g, (1500, 300), W, H)
    check("点空地：取消选择", not c.selected)


def u5():
    print("== U5 底部界面不框地图 ==")
    W, H = 1920, 1080
    g = mk(W, H)
    g.mode = "stockpile"
    frame(g, W, H)
    mouse(g, pygame.MOUSEBUTTONDOWN, to_native((900, g.ui_h - 30), 1.5), W, H)
    check("按在底部工具栏空白处：不开始框选", g.drag_start is None, g.drag_start)
    mouse(g, pygame.MOUSEBUTTONUP, to_native((900, g.ui_h - 30), 1.5), W, H)
    mouse(g, pygame.MOUSEBUTTONDOWN, (800, 400), W, H)
    check("按在地图上：开始框选", g.drag_start is not None)
    mouse(g, pygame.MOUSEBUTTONUP, (800, 400), W, H)
    # 刚好在工具栏上沿附近：窗口坐标 1080-60*1.5=990
    g.drag_start = g.drag_end = None
    g.mode = "stockpile"          # 上一次框选完成后模式会自动退出
    mouse(g, pygame.MOUSEBUTTONDOWN, (800, 985), W, H)
    check("工具栏上沿以上 5 像素仍算地图", g.drag_start is not None)
    mouse(g, pygame.MOUSEBUTTONUP, (800, 985), W, H)
    g.drag_start = g.drag_end = None
    mouse(g, pygame.MOUSEBUTTONDOWN, (800, 995), W, H)
    check("工具栏上沿以下 5 像素算工具栏", g.drag_start is None)


def u6():
    print("== U6 右侧面板 ==")
    g = mk(2560, 1080)
    check("逻辑宽度 1707", g.ui_w == 1707, g.ui_w)
    check("建筑面板贴着逻辑画面右边", g.bhud.panel_rect.x == g.ui_w - g.bhud.panel_w - 20, (g.bhud.panel_rect.x, g.ui_w))
    g.set_screen_size(1280, 720)
    check("回到 1280×720 后面板回到原位", g.bhud.panel_rect.x == 1280 - g.bhud.panel_w - 20)


def u7():
    print("== U7 小窗口 ==")
    W, H = 800, 600
    g = mk(W, H)
    frame(g, W, H)
    check("比例缩小到 0.6，逻辑尺寸更大", g.ui_scale == 0.6 and g.ui_w > 1280, (g.ui_scale, g.ui_w))
    check("缩小也走平滑缩放", any(dst == (W, H) for _, dst in CALLS), CALLS)
    click(g, to_native(button_center(g, "farm"), 0.6), W, H)
    check("小窗口里按钮仍可点", g.mode == "farm", g.mode)


def u8():
    print("== U8 偏好调整 ==")
    g = mk(1280, 720)
    g.set_ui_pref(1.5)
    check("偏好 1.5 → 比例 1.5、逻辑尺寸变小", g.ui_scale == 1.5 and g.ui_w == 854 and g.toast_text == "界面大小 150%",
          (g.ui_scale, g.ui_w, g.toast_text))
    s = frame(g, 1280, 720)
    check("提示文字出现并会消失", g.toast_timer > 0)
    for _ in range(100): g.tick_ui(0.05)
    check("提示 1.5 秒后消失", g.toast_timer <= 0)
    g.set_ui_pref(U.step_pref(2.0, 1))
    check("最大档位夹住（2.0）", g.ui_pref == 2.0)
    g.set_ui_pref(1.0)
    frame(g, 1280, 720)
    check("复位后恢复直接绘制", g.ui_scale == 1.0 and not CALLS)


def u9():
    print("== U9 菜单 ==")
    from ui import menu as M
    W, H = 1920, 1080
    screen = pygame.Surface((W, H))
    f = pygame.font.Font(None, 16)
    fonts = {"normal": f, "big": f, "title": f, "small": f, "warn": f}
    model = M.MenuModel({})
    wd = next(w for w in model.layout(1280, 720) if w.action == "single")
    logical_center = (wd.x + wd.w // 2, wd.y + wd.h // 2)
    native = to_native(logical_center, 1.5)
    seq = [[pygame.event.Event(pygame.MOUSEMOTION, pos=native, rel=(0, 0), buttons=(0, 0, 0))],
           [pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=native, button=1)]]
    orig = pygame.event.get
    pygame.event.get = lambda: seq.pop(0) if seq else []
    prefs = []
    try:
        clock = type("C", (), {"tick": lambda self, fps=0: 16})()
        res = M.run_menu(screen, fonts, clock, {"on_ui_pref": lambda d: prefs.append(d) or 1.0})
    finally:
        pygame.event.get = orig
    check("放大窗口里按窗口坐标点「单人」：触发", res.get("mode") == "single", res)
    # 菜单真的画在逻辑画布上
    layer = U.UiLayer(alpha=False)
    CALLS.clear()
    ui = layer.begin(screen, 1.5)
    M.draw_menu(ui, fonts, M.MenuModel({}))
    layer.end(screen)
    check("菜单画在 1280×720 画布并缩放到 1920×1080", ui.get_size() == (1280, 720) and ((1280, 720), (1920, 1080)) in CALLS, CALLS)
    seq2 = [[pygame.event.Event(pygame.KEYDOWN, key=pygame.K_EQUALS, mod=pygame.KMOD_CTRL, unicode="")],
            [pygame.event.Event(pygame.QUIT)]]
    pygame.event.get = lambda: seq2.pop(0) if seq2 else []
    try:
        M.run_menu(screen, fonts, clock, {"on_ui_pref": lambda d: prefs.append(d) or 1.125})
    finally:
        pygame.event.get = orig
    check("菜单里 Ctrl + 调整界面大小（回调收到 +1）", prefs[-1:] == [1], prefs)


def u10():
    print("== U10 对话框 ==")
    import main as MAIN
    f = pygame.font.Font(None, 16)
    screen = pygame.Surface((1920, 1080))
    CALLS.clear()
    MAIN.draw_confirm(screen, f, True, 1.5)
    check("退出确认：文字画在逻辑画布并缩放", ((1280, 720), (1920, 1080)) in CALLS, CALLS)
    CALLS.clear()
    MAIN.UI_STATE["pref"] = 1.0
    MAIN.show_message(screen, f, ["正在连接主机…"])
    check("连接提示：缩放", ((1280, 720), (1920, 1080)) in CALLS, CALLS)
    CALLS.clear()
    MAIN.draw_confirm(pygame.Surface((1280, 720)), f, False, 1.0)
    check("1.0 比例：不缩放", not CALLS)


def u11():
    print("== U11 各种界面状态在缩放下都能画 ==")
    from core.profile import AVATAR_BYTES, encode_avatar
    W, H = 1920, 1080
    f = pygame.font.Font(None, 16)
    g = GameWorld(f, f, f, f, 1280, 720, seed=42, num_players=2, local_player=0)
    g.set_screen_size(W, H)
    g.set_profiles([{"name": "阿明", "av": encode_avatar(bytes(AVATAR_BYTES))},
                    {"name": "小红", "av": None}])
    errs, states = [], 0

    def draw_ok(label):
        nonlocal states
        try:
            frame(g, W, H)
            states += 1
        except Exception as e:                                           # noqa: BLE001
            errs.append((label, f"{type(e).__name__}: {e}"))
    draw_ok("默认")
    g.colonists[0].selected = True
    draw_ok("选中小人(HUD)")
    g.colonists[0].selected = False
    for mode in ("build", "research", "farm", "stockpile", "deconstruct", "harvest_area", "hunt_area"):
        g.mode = mode
        draw_ok(f"模式 {mode}")
    g.mode = "farm"; g.pending_farm_rect = (5, 5, 8, 8)
    draw_ok("农田作物弹窗")
    g.pending_farm_rect = None; g.mode = None
    g.show_help = True
    draw_ok("帮助面板")
    g.show_help = False
    g.warning_text, g.warning_timer = "警告: 测试", 2.0
    draw_ok("警告条")
    g.net_status = "等待玩家2… 3.0s"
    draw_ok("联机状态")
    g.gone_players.add(1)
    draw_ok("玩家离开")
    g.set_ui_pref(1.25)
    draw_ok("偏好 125%")
    b = next(iter(g.buildings.buildings.values()), None)
    if b is not None:
        g.selected_building = b
        draw_ok("建筑面板")
        g.selected_building = None
    try:
        g.stockpiles.add((2, 2, 4, 4))
        g.selected_stockpile = g.stockpiles.stockpiles[0]
        g.shud.set_target(g.selected_stockpile, (300, 300), g.ui_w, g.ui_h)
        draw_ok("库存区面板")
        g.selected_stockpile = None
    except Exception as e:                                               # noqa: BLE001
        errs.append(("库存区准备", repr(e)))
    check(f"{states} 种界面状态均无异常", not errs, errs)
    check("联机玩家栏/头顶用户名绘制路径可运行", len(g.player_profiles) == 2)


if __name__ == "__main__":
    print("(使用假 pygame)" if FAKE else "(使用真 pygame)")
    for fn in (u1, u2, u3, u4, u5, u6, u7, u8, u9, u10, u11):
        try:
            fn()
        except Exception as e:                                 # noqa: BLE001
            import traceback
            check(f"{fn.__name__} 不应抛异常", False, f"{type(e).__name__}: {e}\n{traceback.format_exc()[-600:]}")
    print("\n结果：", "全部通过 ✓" if not FAILS else f"失败 {len(FAILS)} 项: {FAILS}")
    sys.exit(1 if FAILS else 0)
