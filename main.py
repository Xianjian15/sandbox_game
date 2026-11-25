# main.py
import argparse
import json
import os
import pygame
import sys

from settings import INIT_W, INIT_H, FPS, TICK_DT, MAX_TICKS_PER_FRAME
from world.game_world import GameWorld
from net.session import LockstepSession, DEFAULT_PORT, get_lan_ip
from ui.menu import run_menu
from ui.fonts import load_font, font_source
from core.app_paths import setup_logging, report_crash, data_file, resource_path
from core.version import GAME_VERSION, DISPLAY_NAME
from core.profile import Profile, sanitize_name
from core import ui_scale as uis

UI_STATE = {"pref": uis.DEFAULT_PREF}        # 玩家的界面大小偏好（Ctrl +/- 调整，存 ui.json）
_MSG_LAYER = uis.UiLayer(alpha=False)
_CONFIRM_LAYER = uis.UiLayer(alpha=True)


def change_ui_pref(delta):
    """调整并保存界面大小偏好，返回新的偏好值。"""
    UI_STATE["pref"] = uis.step_pref(UI_STATE["pref"], delta)
    uis.save_pref(data_file("ui.json"), UI_STATE["pref"])
    return UI_STATE["pref"]

# 调试：每秒打印一次"自认为在忙"的小人状态（排查卡死用）
DEBUG_BUSY = os.environ.get("RW_DEBUG") == "1"      # 设环境变量 RW_DEBUG=1 打开调试输出


def parse_args():
    ap = argparse.ArgumentParser(description="RimWorld-like 沙盒（支持局域网 2~4 人联机）")
    ap.add_argument("--host", nargs="?", const=DEFAULT_PORT, type=int, metavar="PORT",
                    help=f"作为主机开一局联机游戏（默认端口 {DEFAULT_PORT}）")
    ap.add_argument("--join", metavar="IP[:PORT]", help="加入主机的联机游戏，例如 192.168.1.5 或 192.168.1.5:47777")
    ap.add_argument("--players", type=int, default=2, choices=range(2, 5), metavar="N",
                    help="（主机，配合 --host）凑够 N 人（2~4，含自己）自动开始，默认 2")
    ap.add_argument("--name", metavar="用户名", help="（命令行直连时）临时使用的用户名；平时在菜单「个人资料」里设置")
    ap.add_argument("--delay", type=int, default=4, help="联机输入延迟（回合数，默认 4；网络差就调大）")
    ap.add_argument("--seed", type=int, default=42, help="（主机）地图/随机种子")
    return ap.parse_args()


def show_message(screen, font, lines):
    scale = uis.compute_scale(*screen.get_size(), UI_STATE["pref"])
    ui = _MSG_LAYER.begin(screen, scale)               # 文字随窗口大小缩放
    ui.fill((20, 20, 25))
    y = ui.get_height() // 2 - 20 * len(lines) // 2
    for text in lines:
        surf = font.render(text, True, (230, 230, 230))
        ui.blit(surf, (ui.get_width() // 2 - surf.get_width() // 2, y))
        y += 30
    _MSG_LAYER.end(screen)
    pygame.display.flip()


def wait_for_connection(screen, font, clock, session, lines_fn):
    """联机握手界面：等到会话 ready（或失败 / 玩家按 ESC 取消）。"""
    while session.state not in ("ready", "failed"):
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                session.close()
                return False
        session.pump()
        show_message(screen, font, lines_fn() + ["", "按 ESC 取消"])
        clock.tick(30)
    if session.state == "failed":
        show_message(screen, font, [session.error, "", "3 秒后退出"])
        pygame.time.wait(3000)
        return False
    return True


def draw_confirm(screen, font, online, scale=1.0):
    w, h = screen.get_size()
    veil = pygame.Surface((w, h), pygame.SRCALPHA)
    veil.fill((0, 0, 0, 150))
    screen.blit(veil, (0, 0))
    screen_real, screen = screen, _CONFIRM_LAYER.begin(screen, scale)       # 文字部分按界面缩放
    w, h = screen.get_size()
    lines = ["返回主菜单？", "联机中返回会断开与对方的连接" if online else "当前进度不会保存", "Y / Enter 确认      N / Esc 取消"]
    y = h // 2 - 50
    for i, text in enumerate(lines):
        surf = font.render(text, True, (255, 255, 255) if i != 1 else (255, 200, 120))
        screen.blit(surf, (w // 2 - surf.get_width() // 2, y))
        y += 34
    _CONFIRM_LAYER.end(screen_real)


def play(screen, clock, fonts, session, seed):
    """开一局游戏（单机或联机），直到玩家关窗口或选择返回主菜单。返回 ("quit"/"menu", screen)。"""
    font, font_big, font_small, font_warn = fonts["normal"], fonts["big"], fonts["small"], fonts["warn"]
    if session is not None:
        cfg = session.cfg
        game = GameWorld(font, font_big, font_small, font_warn, INIT_W, INIT_H,
                         seed=cfg["seed"], map_seed=cfg["map_seed"],
                         cmd_delay=cfg["delay"], local_player=cfg["player"],
                         num_players=cfg.get("players", 2))
        session.attach(game)
        game.set_profiles(session.roster)          # 顶部玩家栏 + 小人头顶的用户名
    else:
        game = GameWorld(font, font_big, font_small, font_warn, INIT_W, INIT_H, seed=seed)
    game.ui_pref = UI_STATE["pref"]
    game.set_screen_size(*screen.get_size())          # 按当前窗口大小初始化相机和界面缩放
    desync_dumped = False
    is_fullscreen = False
    running = True
    acc = 0.0            # 模拟时间累加器（单位：秒）
    debug_timer = 0.0
    confirm_exit = False
    leave = "quit"       # 循环结束后返回给 main 的去向："quit" 退出程序 / "menu" 回到主菜单
    while running:
        dt_raw = clock.tick(FPS) / 1000.0       # 真实帧时间：只用于渲染/UI/相机

        screen_w, screen_h = screen.get_size()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                continue

            if confirm_exit:                    # "返回主菜单？"确认框打开时，按键只用来回答它
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_y, pygame.K_RETURN, pygame.K_KP_ENTER):
                        leave, running = "menu", False
                    elif event.key in (pygame.K_n, pygame.K_ESCAPE, pygame.K_F10):
                        confirm_exit = False
                continue

            if event.type == pygame.KEYDOWN and event.key == pygame.K_F10:
                confirm_exit = True
                continue

            if event.type == pygame.KEYDOWN:                # Ctrl + / Ctrl - / Ctrl 0：调整界面大小
                delta = uis.pref_delta_for_key(event.key, event.mod)
                if delta is not None:
                    game.set_ui_pref(change_ui_pref(delta))
                    continue

            if event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                is_fullscreen = not is_fullscreen
                if is_fullscreen:
                    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                else:
                    screen = pygame.display.set_mode((INIT_W, INIT_H), pygame.RESIZABLE)
                screen_w, screen_h = screen.get_size()
                game.set_screen_size(screen_w, screen_h)
                continue

            if event.type == pygame.VIDEORESIZE:
                screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                screen_w, screen_h = event.w, event.h
                game.set_screen_size(screen_w, screen_h)

            game.handle_event(event, screen_w, screen_h)

        # 相机边缘滚动（纯 UI，用真实时间）
        mouse_pos = pygame.mouse.get_pos()
        edge_margin = 20
        scroll_speed = 600 * dt_raw
        if not game.is_mouse_in_ui(mouse_pos):
            if mouse_pos[0] < edge_margin: game.camera.move_by(-scroll_speed, 0)
            elif mouse_pos[0] > screen_w - edge_margin: game.camera.move_by(scroll_speed, 0)
            if mouse_pos[1] < edge_margin: game.camera.move_by(0, -scroll_speed)
            elif mouse_pos[1] > screen_h - edge_margin: game.camera.move_by(0, scroll_speed)

        game.tick_ui(dt_raw)

        # ---- 固定步长模拟 ----
        # 倍速只改变"每秒跑多少个 tick"，每个 tick 的步长永远是 TICK_DT。
        if session is not None and session.active:
            # 联机：回合时钟照走（暂停时按 1 倍速率，保证"取消暂停"指令能生效）；
            # 等不到对方的包就停在原地，不囤积时间。
            acc += dt_raw * max(1.0, game.game_speed)
            ticks = 0
            while acc >= TICK_DT and ticks < MAX_TICKS_PER_FRAME:
                if not session.try_turn():
                    break
                acc -= TICK_DT
                ticks += 1
            acc = min(acc, TICK_DT * MAX_TICKS_PER_FRAME)
            if ticks == 0:
                session.pump()
        elif session is not None and session.state in ("desync", "mismatch"):
            session.pump()          # 失去同步：世界冻结，保留现场（状态文字已显示在右上角）
            if session.state == "desync" and not desync_dumped:
                desync_dumped = True
                try:
                    with open(data_file("desync_report.json"), "w", encoding="utf-8") as f:
                        json.dump(session.desync_info, f, ensure_ascii=False, indent=2)
                except OSError:
                    pass
        elif game.game_speed > 0:
            acc += dt_raw * game.game_speed
            ticks = 0
            while acc >= TICK_DT and ticks < MAX_TICKS_PER_FRAME:
                game.sim_step()
                acc -= TICK_DT
                ticks += 1
            if acc >= TICK_DT:      # 落后太多（卡顿），丢弃积压，避免越补越卡
                acc = 0.0
        else:
            acc = 0.0               # 暂停
            game.flush_commands()   # 暂停时已到期的指令也要生效（联机模式 cmd_delay>0 时才有意义）

        if DEBUG_BUSY:
            debug_timer += dt_raw
            if debug_timer >= 1.0:
                debug_timer = 0.0
                for c in game.colonists:
                    if not c.is_idle():
                        print(f"[忙碌中] {c.name} job={c.job.get('type') if c.job else None} "
                              f"stage={c.job.get('stage') if c.job else None} "
                              f"path={c.path} speed={c.speed:.1f} "
                              f"state={c.state} queue={c.queue} "
                              f"target_enemy={c.target_enemy} target_animal={c.target_animal} "
                              f"stuck={c.stuck_timer:.2f}")

        game.draw(screen, dt_raw)
        if confirm_exit:
            draw_confirm(screen, fonts["big"], session is not None, game.ui_scale)
        pygame.display.flip()

    if session is not None:
        session.close()
    return leave, screen


def set_window_icon():
    """窗口/任务栏图标。找不到图标文件就算了，不影响游戏。"""
    try:
        pygame.display.set_icon(pygame.image.load(resource_path("assets", "icon.png")))
    except Exception:                                                      # noqa: BLE001
        pass


def window_title():
    return f"{DISPLAY_NAME} v{GAME_VERSION}"


def main():
    args = parse_args()
    pygame.init()
    set_window_icon()                      # 要在 set_mode 之前，部分系统才会生效
    screen = pygame.display.set_mode((INIT_W, INIT_H), pygame.RESIZABLE)
    pygame.display.set_caption(window_title())
    clock = pygame.time.Clock()
    fonts = {"normal": load_font(16), "big": load_font(20), "small": load_font(14),
             "warn": load_font(28), "title": load_font(44)}

    UI_STATE["pref"] = uis.load_pref(data_file("ui.json"))
    profile = Profile.load(data_file("profile.json"))        # 本机玩家资料（用户名 + 头像），菜单里可修改
    if args.name:
        profile.name = sanitize_name(args.name, profile.name)

    # ---- 命令行直连（保留）：--host / --join 跳过菜单 ----
    if args.host is not None or args.join:
        session = None
        if args.host is not None:
            session = LockstepSession.host(port=args.host, seed=args.seed, delay=args.delay,
                                           expect=max(1, args.players - 1), profile=profile.to_wire())
            ip = get_lan_ip()
            ok = wait_for_connection(screen, fonts["big"], clock, session, lambda: [
                f"你是主机，等待其他玩家加入（凑够 {args.players} 人自动开始）…", f"让其他人运行:  python main.py --join {ip}:{session.port}"])
        else:
            host, _, port = args.join.partition(":")
            session = LockstepSession.join(host, int(port) if port else DEFAULT_PORT, profile=profile.to_wire())
            ok = wait_for_connection(screen, fonts["big"], clock, session, lambda: ["正在连接主机…"])
        if ok:
            play(screen, clock, fonts, session, args.seed)
        pygame.quit()
        sys.exit()

    # ---- 主菜单循环 ----
    while True:
        choice = run_menu(screen, fonts, clock, {"seed": args.seed, "delay": args.delay, "profile": profile,
                                                    "ui_pref": UI_STATE["pref"], "on_ui_pref": change_ui_pref})
        if choice["mode"] == "quit":
            break
        session = choice.get("session")             # 单机为 None
        leave, screen = play(screen, clock, fonts, session, args.seed)
        if leave == "quit":
            break
        pygame.display.set_caption(window_title())
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    setup_logging()                        # 打包成无控制台程序时，把输出接到日志文件
    try:
        main()
    except (SystemExit, KeyboardInterrupt):
        raise
    except Exception:                      # noqa: BLE001  # 任何未捕获的错误：写崩溃日志并提示玩家
        report_crash()
        sys.exit(1)
