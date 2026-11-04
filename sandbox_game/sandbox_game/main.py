# main.py
import os
import pygame
import sys

from settings import INIT_W, INIT_H, FPS
from world.game_world import GameWorld


def load_font(size=18):
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            return pygame.font.Font(path, size)
    return pygame.font.Font(None, size)


def main():
    pygame.init()
    screen = pygame.display.set_mode((INIT_W, INIT_H), pygame.RESIZABLE)
    pygame.display.set_caption("RimWorld-like - 沙盒生存")
    clock = pygame.time.Clock()

    font = load_font(16)
    font_big = load_font(20)
    font_small = load_font(14)
    font_warn = load_font(28)

    game = GameWorld(font, font_big, font_small, font_warn,
                     INIT_W, INIT_H, seed=42)

    is_fullscreen = False
    running = True
    while running:
        dt_raw = clock.tick(FPS) / 1000.0
        dt = dt_raw * game.game_speed

        screen_w, screen_h = screen.get_size()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
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

        # 相机边缘滚动
        mouse_pos = pygame.mouse.get_pos()
        edge_margin = 20
        scroll_speed = 600 * dt_raw
        if not game.is_mouse_in_ui(mouse_pos):
            if mouse_pos[0] < edge_margin: game.camera.move_by(-scroll_speed, 0)
            elif mouse_pos[0] > screen_w - edge_margin: game.camera.move_by(scroll_speed, 0)
            if mouse_pos[1] < edge_margin: game.camera.move_by(0, -scroll_speed)
            elif mouse_pos[1] > screen_h - edge_margin: game.camera.move_by(0, scroll_speed)

        game.tick_ui(dt_raw)
        game.step(dt, dt_raw)
        if not hasattr(game, '_debug_timer'):
            game._debug_timer = 0.0
        game._debug_timer += dt_raw
        if game._debug_timer >= 1.0:
            game._debug_timer = 0.0
            for c in game.colonists:
                if not c.is_idle():  # 只抓"自认为在忙"但可能卡住的人
                    print(f"[忙碌中] {c.name} job={c.job.get('type') if c.job else None} "
                          f"stage={c.job.get('stage') if c.job else None} "
                          f"path={c.path} speed={c.speed:.1f} "
                          f"state={c.state} queue={c.queue} "
                          f"target_enemy={c.target_enemy} target_animal={c.target_animal} "
                          f"stuck={c.stuck_timer:.2f}")
        game.draw(screen, dt_raw)

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()