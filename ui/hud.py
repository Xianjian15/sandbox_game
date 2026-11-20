# ui/hud.py
import pygame
from settings import WHITE
from combat.weapons import get_weapon


class HUD:
    def __init__(self, font):
        self.font = font
        self.panel_rect = pygame.Rect(10, 60, 320, 190)

    def draw(self, surface, colonists, selected_colonists, camera):
        if not selected_colonists: return

        c = selected_colonists[0]
        x, y, w = self.panel_rect.x, self.panel_rect.y, self.panel_rect.w

        panel = pygame.Surface((w, self.panel_rect.h), pygame.SRCALPHA)
        panel.fill((20, 20, 25, 210))
        surface.blit(panel, (x, y))
        pygame.draw.rect(surface, (100, 100, 110), self.panel_rect, 2)

        title = f"{c.name}"
        surface.blit(self.font.render(title, True, (255, 220, 100)), (x + 10, y + 10))

        if len(selected_colonists) > 1:
            surface.blit(self.font.render(f"等 {len(selected_colonists)} 人", True, (150, 200, 255)), (x + 10, y + 35))
            y += 20

        self._draw_bar(surface, x + 10, y + 40, 120, "饱食", c.satiety, (200, 180, 80))
        self._draw_bar(surface, x + 10, y + 65, 120, "精力", c.rest, (80, 150, 200))
        self._draw_bar(surface, x + 170, y + 40, 120, "心情", c.mood, (150, 200, 100))

        if getattr(c, "bleeding", 0) > 0:
            surface.blit(self.font.render(f"流血: {c.bleeding:.1f}/s", True, (255, 80, 80)), (x + 170, y + 65))

        # 双槽装备栏
        weapon = get_weapon(c.weapon_key)
        tool_key = getattr(c, "tool_key", None)
        tool_def = get_weapon(tool_key) if tool_key else None

        wy = y + 105
        surface.blit(self.font.render("武器槽:", True, (200, 200, 200)), (x + 10, wy))
        wx, ww, wh = x + 80, 220, 26
        pygame.draw.rect(surface, (40, 50, 40), (wx, wy - 2, ww, wh), border_radius=4)
        pygame.draw.rect(surface, (100, 150, 100), (wx, wy - 2, ww, wh), 1, border_radius=4)
        surface.blit(self.font.render(f"{weapon['name']}", True, (200, 255, 200)), (wx + 10, wy + 2))
        surface.blit(self.font.render(f"伤害: {weapon['damage']}", True, (150, 200, 150)), (wx + 120, wy + 2))

        wy += 30
        surface.blit(self.font.render("工具槽:", True, (200, 200, 200)), (x + 10, wy))
        pygame.draw.rect(surface, (40, 50, 40), (wx, wy - 2, ww, wh), border_radius=4)
        pygame.draw.rect(surface, (100, 150, 100), (wx, wy - 2, ww, wh), 1, border_radius=4)
        if tool_def:
            surface.blit(self.font.render(f"{tool_def['name']}", True, (200, 255, 200)), (wx + 10, wy + 2))
            surface.blit(self.font.render(f"伤害: {tool_def['damage']}", True, (150, 200, 150)), (wx + 120, wy + 2))
        else:
            surface.blit(self.font.render("(空)", True, (120, 120, 120)), (wx + 10, wy + 2))

    def _draw_bar(self, surface, x, y, w, label, value, color):
        surface.blit(self.font.render(label, True, WHITE), (x, y))
        pygame.draw.rect(surface, (40, 40, 40), (x + 35, y + 4, w - 35, 12))
        pygame.draw.rect(surface, color, (x + 35, y + 4, int((w - 35) * (value / 100.0)), 12))
        surface.blit(self.font.render(str(int(value)), True, WHITE), (x + w + 5, y))

    def handle_click(self, mouse_pos, selected_colonists):
        """面板只做展示；点击落在面板内时吞掉，避免穿透到地图。"""
        if not selected_colonists: return False
        return self.panel_rect.collidepoint(mouse_pos)
