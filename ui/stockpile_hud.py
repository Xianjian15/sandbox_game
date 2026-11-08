# ui/stockpile_hud.py
import pygame
from settings import WHITE


class StockpileHUD:
    def __init__(self, font):
        self.font = font
        self.panel_w = 200
        self.panel_h = 100
        self.panel_rect = pygame.Rect(0, 0, self.panel_w, self.panel_h)
        self.delete_btn = pygame.Rect(0, 0, 0, 0)
        self.target_sp = None

    def set_target(self, sp, mouse_pos, screen_w, screen_h):
        self.target_sp = sp
        if sp:
            x = min(mouse_pos[0], screen_w - self.panel_w - 10)
            y = min(mouse_pos[1], screen_h - self.panel_h - 10)
            self.panel_rect.x = x
            self.panel_rect.y = y

    def draw(self, surface):
        if not self.target_sp: return
        x, y = self.panel_rect.x, self.panel_rect.y
        w, h = self.panel_w, self.panel_h
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        panel.fill((20, 20, 25, 230))
        surface.blit(panel, (x, y))
        pygame.draw.rect(surface, (100, 100, 110), (x, y, w, h), 2)

        title = self.font.render("库存区属性", True, (100, 200, 255))
        surface.blit(title, (x + 10, y + 10))

        self.delete_btn = pygame.Rect(x + 10, y + 50, w - 20, 40)
        pygame.draw.rect(surface, (180, 60, 60), self.delete_btn, border_radius=4)
        pygame.draw.rect(surface, (220, 100, 100), self.delete_btn, 2, border_radius=4)
        btn_txt = self.font.render("删除此区域", True, WHITE)
        surface.blit(btn_txt, (self.delete_btn.centerx - btn_txt.get_width() // 2, self.delete_btn.y + 10))

    def handle_click(self, mouse_pos):
        if not self.target_sp: return False, False
        if self.panel_rect.collidepoint(mouse_pos):
            if self.delete_btn.collidepoint(mouse_pos):
                return True, True
            return True, False
        return False, False