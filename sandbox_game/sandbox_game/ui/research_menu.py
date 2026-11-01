# ui/research_menu.py
import pygame
from systems.research import TECHS


class ResearchMenu:
    def __init__(self, font):
        self.font = font
        self.rects = []

    def draw(self, surface, screen_w, screen_h, rm):
        num_techs = len(TECHS)
        w = 600
        h = min(screen_h - 80, 130 + num_techs * 70)
        x, y = screen_w // 2 - w // 2, screen_h // 2 - h // 2

        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        panel.fill((20, 20, 25, 240))
        surface.blit(panel, (x, y))
        pygame.draw.rect(surface, (100, 160, 220), (x, y, w, h), 2)

        title = self.font.render("科技研究 (R 关闭)", True, (100, 160, 220))
        surface.blit(title, (x + 20, y + 15))

        self.rects.clear()

        if rm.current_research:
            t = TECHS[rm.current_research]
            txt = f"正在研究: {t['name']}  ({int(rm.progress)}/{int(t['cost'])})"
            surface.blit(self.font.render(txt, True, (255, 220, 100)), (x + 20, y + 50))
            ratio = min(1.0, rm.progress / t["cost"])
            pygame.draw.rect(surface, (40, 40, 40), (x + 20, y + 75, 400, 10))
            pygame.draw.rect(surface, (100, 200, 100), (x + 20, y + 75, int(400 * ratio), 10))
        else:
            surface.blit(self.font.render("未选择研究项目", True, (150, 150, 150)), (x + 20, y + 50))

        start_y = y + 110
        for i, (tech_id, data) in enumerate(TECHS.items()):
            r = pygame.Rect(x + 20, start_y + i * 70, w - 40, 60)
            self.rects.append((r, tech_id))

            is_done = tech_id in rm.completed
            is_current = tech_id == rm.current_research

            # 检查前置是否满足
            req_met = all(req in rm.completed for req in data["requires"])

            if is_done:
                bg = (40, 60, 40)
            elif is_current:
                bg = (60, 80, 100)
            elif not req_met:
                bg = (30, 30, 30)
            else:
                bg = (45, 45, 50)

            pygame.draw.rect(surface, bg, r, border_radius=4)
            pygame.draw.rect(surface, (100, 100, 110), r, 1, border_radius=4)

            name_col = (100, 220, 100) if is_done else ((150, 150, 150) if not req_met else (255, 255, 255))
            surface.blit(self.font.render(f"{data['name']} ({int(data['cost'])} 点)", True, name_col),
                         (r.x + 10, r.y + 8))
            surface.blit(self.font.render(data["desc"], True, (180, 180, 180)), (r.x + 10, r.y + 32))

            if is_done:
                surface.blit(self.font.render("已完成", True, (100, 220, 100)), (r.right - 80, r.y + 20))
            elif not req_met:
                req_names = [TECHS[req]["name"] for req in data["requires"]]
                req_str = ", ".join(req_names)
                surf = self.font.render(f"需: {req_str}", True, (200, 100, 100))
                surface.blit(surf, (r.right - surf.get_width() - 10, r.y + 20))

    def handle_click(self, mouse_pos, rm):
        for r, tech_id in self.rects:
            if r.collidepoint(mouse_pos):
                rm.set_research(tech_id)
                return True
        return False