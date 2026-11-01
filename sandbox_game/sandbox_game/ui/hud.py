# ui/hud.py
import pygame
from settings import WHITE
from combat.weapons import get_weapon


class HUD:
    def __init__(self, font):
        self.font = font
        self.panel_rect = pygame.Rect(10, 60, 320, 440)
        self.rects = {}

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

        surface.blit(self.font.render("工作优先级 (点击调整):", True, (200, 200, 100)), (x + 10, y + 100))

        self.rects.clear()
        job_names = {
            "harvest": "采集", "haul": "搬运", "build": "建造", "research": "研究",
            "hunt": "狩猎", "farm": "农业", "cook": "烹饪", "craft": "制作",
            "smelt": "熔炼", "doctor": "医疗"
        }

        row = 0
        for job_key, job_name in job_names.items():
            col = row % 3
            line = row // 3
            bx = x + 10 + col * 100
            by = y + 125 + line * 30

            prio = c.priorities.get(job_key, 0)
            if prio == 0:
                color = (120, 120, 120)
            elif prio == 1:
                color = (50, 200, 50)
            elif prio == 2:
                color = (100, 255, 100)
            elif prio == 3:
                color = (255, 200, 80)
            else:
                color = (255, 80, 80)

            txt = self.font.render(f"{job_name}: {prio}", True, color)
            surface.blit(txt, (bx, by))

            self.rects[(bx - 5, by - 2, 90, 24)] = (job_key, selected_colonists)
            row += 1

        # 装备栏
        weapon = get_weapon(c.weapon_key)
        wy = y + 260
        surface.blit(self.font.render("当前装备:", True, (200, 200, 200)), (x + 10, wy))

        wx, ww, wh = x + 80, 220, 26
        pygame.draw.rect(surface, (40, 50, 40), (wx, wy - 2, ww, wh), border_radius=4)
        pygame.draw.rect(surface, (100, 150, 100), (wx, wy - 2, ww, wh), 1, border_radius=4)

        surface.blit(self.font.render(f"{weapon['name']}", True, (200, 255, 200)), (wx + 10, wy + 2))
        surface.blit(self.font.render(f"伤害: {weapon['damage']}", True, (150, 200, 150)), (wx + 120, wy + 2))

    def _draw_bar(self, surface, x, y, w, label, value, color):
        surface.blit(self.font.render(label, True, WHITE), (x, y))
        pygame.draw.rect(surface, (40, 40, 40), (x + 35, y + 4, w - 35, 12))
        pygame.draw.rect(surface, color, (x + 35, y + 4, int((w - 35) * (value / 100.0)), 12))
        surface.blit(self.font.render(str(int(value)), True, WHITE), (x + w + 5, y))

    def handle_click(self, mouse_pos, selected_colonists):
        if not selected_colonists: return False
        if self.panel_rect.collidepoint(mouse_pos):
            for rect, (job_key, targets) in self.rects.items():
                if pygame.Rect(rect).collidepoint(mouse_pos):
                    current = targets[0].priorities.get(job_key, 0)
                    new_prio = (current + 1) % 5
                    for c in targets: c.priorities[job_key] = new_prio
                    return True
            return True
        return False