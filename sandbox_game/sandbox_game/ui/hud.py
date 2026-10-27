# ui/hud.py
import pygame
from settings import WHITE

PRIORITY_COLORS = {0: (80, 80, 80), 1: (100, 220, 100), 2: (180, 220, 80), 3: (240, 200, 80), 4: (240, 140, 80)}
JOB_LABELS = {"harvest": "采集", "haul": "搬运", "build": "建造", "research": "研究", "hunt": "狩猎", "farm": "农业",
              "cook": "烹饪"}


def _bar(surface, x, y, w, h, ratio, color, bg=(50, 20, 20)):
    pygame.draw.rect(surface, bg, (x, y, w, h))
    pygame.draw.rect(surface, color, (x, y, int(w * ratio), h))
    pygame.draw.rect(surface, (30, 30, 30), (x, y, w, h), 1)


class HUD:
    def __init__(self, font):
        self.font = font
        self.panel_w = 340
        self.panel_h = 490
        self.panel_rect = pygame.Rect(10, 60, self.panel_w, self.panel_h)

    def draw(self, surface, colonists, selected, camera):
        if not selected: return

        x, y = self.panel_rect.x, self.panel_rect.y
        w, h = self.panel_w, self.panel_h
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        panel.fill((20, 20, 25, 210))
        surface.blit(panel, (x, y))
        pygame.draw.rect(surface, (100, 100, 110), (x, y, w, h), 2)

        title = self.font.render(f"选中 {len(selected)} 个殖民者", True, WHITE)
        surface.blit(title, (x + 10, y + 8))

        c = selected[0]
        info_y = y + 36
        state_map = {"sleeping": "睡觉", "eating": "吃饭", "going_to_eat": "去吃饭", "going_to_sleep": "去睡觉"}
        state = state_map.get(c.state, None)
        if state is None:
            if c.target_enemy is not None:
                state = "战斗"
            elif c.target_animal is not None:
                state = "狩猎"
            elif c.job:
                labels = {"harvest": "采集", "haul": "搬运", "build": "建造", "deconstruct": "拆除", "research": "研究",
                          "cook": "烹饪", "farm": "种田"}
                state = labels.get(c.job["type"], "工作")
            elif c.path:
                state = "行走"
            else:
                state = "待命"

        surface.blit(self.font.render(f"{c.name}  HP {c.hp}/{c.max_hp}  [{state}]", True, WHITE), (x + 10, info_y))
        info_y += 24

        surface.blit(self.font.render("需求:", True, (200, 200, 100)), (x + 10, info_y))
        info_y += 20
        bar_w, bar_h = 120, 12

        # 饱食度
        surface.blit(self.font.render("饱", True, WHITE), (x + 10, info_y))
        _bar(surface, x + 30, info_y, bar_w, bar_h, c.satiety / 100, (220, 120, 60))
        surface.blit(self.font.render(f"{int(c.satiety)}", True, (220, 220, 220)), (x + 30 + bar_w + 8, info_y))
        info_y += 18

        # 精力
        surface.blit(self.font.render("精", True, WHITE), (x + 10, info_y))
        _bar(surface, x + 30, info_y, bar_w, bar_h, c.rest / 100, (100, 150, 240))
        surface.blit(self.font.render(f"{int(c.rest)}", True, (220, 220, 220)), (x + 30 + bar_w + 8, info_y))
        info_y += 18

        # 心情
        surface.blit(self.font.render("心", True, WHITE), (x + 10, info_y))
        _bar(surface, x + 30, info_y, bar_w, bar_h, c.mood / 100, (200, 200, 90))
        surface.blit(self.font.render(f"{int(c.mood)}", True, (220, 220, 220)), (x + 30 + bar_w + 8, info_y))
        info_y += 24

        surface.blit(self.font.render("工作优先级（点击切换）:", True, (200, 200, 100)), (x + 10, info_y))
        info_y += 24

        self._priority_buttons = []
        jobs = list(JOB_LABELS.items())

        col_width = 160
        row_height = 28
        start_y = info_y

        for i, (job_type, label) in enumerate(jobs):
            col = i % 2
            row = i // 2
            bx = x + 10 + col * col_width
            by = start_y + row * row_height

            p = c.priorities.get(job_type, 3)
            color = PRIORITY_COLORS.get(p, (150, 150, 150))
            btn_rect = pygame.Rect(bx, by, 60, 24)

            pygame.draw.rect(surface, color, btn_rect)
            pygame.draw.rect(surface, (0, 0, 0), btn_rect, 2)

            txt = self.font.render(label, True, (0, 0, 0))
            surface.blit(txt, (btn_rect.x + 10, btn_rect.y + 3))

            num = self.font.render(str(p), True, WHITE)
            surface.blit(num, (btn_rect.right + 8, btn_rect.y + 3))

            self._priority_buttons.append((btn_rect, job_type))

        rows_used = (len(jobs) + 1) // 2
        info_y = start_y + rows_used * row_height

        info_y += 5
        self.auto_harvest_rect = pygame.Rect(x + 10, info_y, 150, 28)
        self.auto_hunt_rect = pygame.Rect(x + 170, info_y, 150, 28)

        ah_count = sum(1 for c in selected if c.auto_harvest)
        if ah_count == 0:
            ah_col = (200, 100, 100);
            ah_txt = "自动采集 (G)"
        elif ah_count == len(selected):
            ah_col = (100, 200, 100);
            ah_txt = "自动采集 (G)"
        else:
            ah_col = (200, 200, 100);
            ah_txt = "采集 (混合)"

        pygame.draw.rect(surface, ah_col, self.auto_harvest_rect, border_radius=4)
        surface.blit(self.font.render(ah_txt, True, (0, 0, 0)), (x + 20, info_y + 5))

        ah_hunt_count = sum(1 for c in selected if c.auto_hunt)
        if ah_hunt_count == 0:
            ah_h_col = (200, 100, 100);
            ah_h_txt = "自动狩猎 (F)"
        elif ah_hunt_count == len(selected):
            ah_h_col = (100, 200, 100);
            ah_h_txt = "自动狩猎 (F)"
        else:
            ah_h_col = (200, 200, 100);
            ah_h_txt = "狩猎 (混合)"

        pygame.draw.rect(surface, ah_h_col, self.auto_hunt_rect, border_radius=4)
        surface.blit(self.font.render(ah_h_txt, True, (0, 0, 0)), (x + 180, info_y + 5))

    def handle_click(self, mouse_pos, selected):
        if not selected: return False

        if self.panel_rect.collidepoint(mouse_pos):
            if hasattr(self, "auto_harvest_rect") and self.auto_harvest_rect.collidepoint(mouse_pos):
                ah_count = sum(1 for c in selected if c.auto_harvest)
                new_state = not (ah_count == len(selected))
                for c in selected: c.auto_harvest = new_state
                return True

            if hasattr(self, "auto_hunt_rect") and self.auto_hunt_rect.collidepoint(mouse_pos):
                ah_count = sum(1 for c in selected if c.auto_hunt)
                new_state = not (ah_count == len(selected))
                for c in selected: c.auto_hunt = new_state
                return True

            if hasattr(self, "_priority_buttons"):
                for rect, job_type in self._priority_buttons:
                    if rect.collidepoint(mouse_pos):
                        for c in selected:
                            cur = c.priorities.get(job_type, 3)
                            c.priorities[job_type] = (cur + 1) % 5
                        return True
            return True
        return False