# ui/build_menu.py
import pygame
from world.buildings import BUILDING_DEFS


class BuildMenu:
    def __init__(self, font):
        self.font = font
        self.buttons = []
        self.sub_buttons = []
        self.height = 80
        self.sub_height = 60
        self.active_kind = None

    def draw(self, surface, screen_w, screen_h, base_y, current_kind, current_mat, totals, research, rotation):
        menu_y = base_y - self.height
        panel = pygame.Surface((screen_w, self.height), pygame.SRCALPHA)
        panel.fill((20, 20, 25, 230))
        surface.blit(panel, (0, menu_y))
        pygame.draw.line(surface, (100, 100, 110), (0, menu_y), (screen_w, menu_y), 2)

        self.buttons.clear()
        start_x = screen_w // 2 - (len(BUILDING_DEFS) * 120) // 2
        for i, (kind, data) in enumerate(BUILDING_DEFS.items()):
            rect = pygame.Rect(start_x + i * 120, menu_y + 10, 100, 60)
            self.buttons.append((rect, kind))

            variants = data["variants"]
            unlocked_mats = [m for m in variants if research.is_unlocked(kind, m)]
            is_unlocked = len(unlocked_mats) > 0
            is_active = (kind == self.active_kind) or (kind == current_kind)

            if is_active:
                pygame.draw.rect(surface, (100, 160, 220), rect)
            elif not is_unlocked:
                pygame.draw.rect(surface, (30, 30, 30), rect)
            else:
                pygame.draw.rect(surface, (50, 50, 60), rect)
            pygame.draw.rect(surface, (150, 150, 160), rect, 2)

            name_col = (255, 255, 255) if is_unlocked else (100, 100, 100)
            name_surf = self.font.render(data["name"], True, name_col)
            surface.blit(name_surf, (rect.centerx - name_surf.get_width() // 2, rect.y + 8))

            if not is_unlocked:
                lock_surf = self.font.render("未解锁", True, (200, 100, 100))
                surface.blit(lock_surf, (rect.centerx - lock_surf.get_width() // 2, rect.y + 34))
            else:
                mat_data = variants[unlocked_mats[0]]
                cost_strs = [f"{k}:{v}" for k, v in mat_data["cost"].items()]
                cost_text = " ".join(cost_strs)
                cost_surf = self.font.render(cost_text, True, (200, 200, 100))
                surface.blit(cost_surf, (rect.centerx - cost_surf.get_width() // 2, rect.y + 34))

                if data["w"] != data["h"] and kind == current_kind:
                    rot_txt = "横" if rotation % 2 == 0 else "竖"
                    rot_surf = self.font.render(f"按R: {rot_txt}", True, (100, 200, 255))
                    surface.blit(rot_surf, (rect.right - 35, rect.bottom - 18))

        if self.active_kind:
            sub_y = menu_y - self.sub_height
            sub_panel = pygame.Surface((screen_w, self.sub_height), pygame.SRCALPHA)
            sub_panel.fill((30, 40, 50, 230))
            surface.blit(sub_panel, (0, sub_y))
            pygame.draw.line(surface, (100, 160, 220), (0, sub_y), (screen_w, sub_y), 2)

            self.sub_buttons.clear()
            variants = BUILDING_DEFS[self.active_kind]["variants"]
            unlocked_mats = [(m, d) for m, d in variants.items() if research.is_unlocked(self.active_kind, m)]

            start_sx = screen_w // 2 - (len(unlocked_mats) * 120) // 2
            for i, (mat_key, mat_data) in enumerate(unlocked_mats):
                r = pygame.Rect(start_sx + i * 120, sub_y + 10, 100, 40)
                self.sub_buttons.append((r, self.active_kind, mat_key))

                is_selected = (current_kind == self.active_kind and current_mat == mat_key)
                if is_selected:
                    pygame.draw.rect(surface, (100, 160, 220), r)
                else:
                    pygame.draw.rect(surface, (50, 50, 60), r)
                pygame.draw.rect(surface, (200, 200, 210), r, 2)

                txt = self.font.render(mat_data["name"], True, (255, 255, 255))
                surface.blit(txt, (r.centerx - txt.get_width() // 2, r.y + 4))

                cost_strs = [f"{k}:{v}" for k, v in mat_data["cost"].items()]
                cost_text = ", ".join(cost_strs)
                cost_surf = self.font.render(cost_text, True, (200, 200, 100))
                surface.blit(cost_surf, (r.centerx - cost_surf.get_width() // 2, r.y + 22))

    def handle_click(self, mouse_pos, research):
        if self.active_kind:
            for rect, kind, mat in self.sub_buttons:
                if rect.collidepoint(mouse_pos):
                    self.active_kind = None
                    return kind, mat, True

        for rect, kind in self.buttons:
            if rect.collidepoint(mouse_pos):
                variants = BUILDING_DEFS[kind]["variants"]
                unlocked_mats = [m for m in variants if research.is_unlocked(kind, m)]
                if not unlocked_mats: return None, None, False

                if len(unlocked_mats) == 1:
                    self.active_kind = None
                    return kind, unlocked_mats[0], True
                else:
                    self.active_kind = kind
                    return None, None, False
        return None, None, False