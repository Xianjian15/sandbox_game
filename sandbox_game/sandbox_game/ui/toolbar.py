# ui/toolbar.py
import pygame


class Toolbar:
    def __init__(self, font):
        self.font = font
        self.height = 60
        self.buttons = []

    def draw(self, surface, screen_w, screen_h, current_mode):
        self.buttons.clear()
        y = screen_h - self.height

        pygame.draw.rect(surface, (25, 25, 30), (0, y, screen_w, self.height))
        pygame.draw.line(surface, (100, 100, 110), (0, y), (screen_w, y), 2)

        tools = [
            ("build", "建造 (B)", (255, 200, 100)),
            ("farm", "农业 (F)", (100, 200, 100)),
            ("stockpile", "库存 (S)", (100, 150, 220)),
            ("deconstruct", "拆除 (X)", (220, 100, 100)),
            ("research", "科技 (R)", (100, 220, 180))
        ]

        start_x = 20
        for i, (mode_key, label, color) in enumerate(tools):
            rect = pygame.Rect(start_x + i * 115, y + 8, 105, 44)
            self.buttons.append((rect, mode_key))

            is_selected = (current_mode == mode_key)
            bg_color = (60, 80, 100) if is_selected else (45, 45, 50)

            pygame.draw.rect(surface, bg_color, rect, border_radius=6)
            pygame.draw.rect(surface, color, rect, 2, border_radius=6)

            txt = self.font.render(label, True, color)
            surface.blit(txt, (rect.centerx - txt.get_width() // 2, rect.centery - txt.get_height() // 2))

        if current_mode is not None:
            close_rect = pygame.Rect(screen_w - 120, y + 8, 100, 44)
            self.buttons.append((close_rect, "close"))
            pygame.draw.rect(surface, (80, 40, 40), close_rect, border_radius=6)
            pygame.draw.rect(surface, (220, 100, 100), close_rect, 2, border_radius=6)
            txt = self.font.render("关闭 (Esc)", True, (220, 100, 100))
            surface.blit(txt, (close_rect.centerx - txt.get_width() // 2, close_rect.centery - txt.get_height() // 2))

    def handle_click(self, mouse_pos):
        for rect, mode_key in self.buttons:
            if rect.collidepoint(mouse_pos):
                return mode_key
        return "NOT_CLICKED"