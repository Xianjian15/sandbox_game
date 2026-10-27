# ui/building_hud.py
import pygame
from settings import WHITE
from world.buildings import BUILDING_DEFS
from world.items import ITEM_DEFS


class BuildingHUD:
    def __init__(self, font):
        self.font = font
        self.panel_w = 300
        self.panel_h = 220
        self.panel_rect = pygame.Rect(10, 60, self.panel_w, self.panel_h)
        self.deconstruct_btn = pygame.Rect(0, 0, 0, 0)

        self.cook_simple_btn = pygame.Rect(0, 0, 0, 0)
        self.cook_fine_btn = pygame.Rect(0, 0, 0, 0)

    def draw(self, surface, selected_building, global_items):
        if not selected_building: return

        x, y = self.panel_rect.x, self.panel_rect.y
        w = self.panel_w

        if hasattr(selected_building, "hp"):
            if selected_building.kind == "stove":
                h = 300
            elif selected_building.kind == "small_cabinet":
                h = 340  # 拉长
            elif selected_building.kind == "large_cabinet":
                h = 440  # 拉长
            else:
                h = 220
        elif hasattr(selected_building, "work_done"):
            h = 240
        else:
            h = 220

        self.panel_rect.h = h

        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        panel.fill((20, 20, 25, 210))
        surface.blit(panel, (x, y))
        pygame.draw.rect(surface, (100, 100, 110), (x, y, w, h), 2)

        if hasattr(selected_building, "work_done"):
            v = BUILDING_DEFS[selected_building.kind]["variants"][selected_building.material]
            title = f"蓝图: {v['name']}"
        else:
            v = BUILDING_DEFS[selected_building.kind]["variants"][selected_building.material]
            title = v["name"]

        title_surf = self.font.render(title, True, (255, 220, 100))
        surface.blit(title_surf, (x + 10, y + 10))

        pos_surf = self.font.render(f"位置: ({selected_building.tx}, {selected_building.ty})", True, (150, 150, 150))
        surface.blit(pos_surf, (x + 10, y + 35))

        if hasattr(selected_building, "work_done"):
            ratio = selected_building.work_done / selected_building.work_needed
            prog_surf = self.font.render(f"建造进度: {int(ratio * 100)}%", True, WHITE)
            surface.blit(prog_surf, (x + 10, y + 60))
            pygame.draw.rect(surface, (40, 40, 40), (x + 10, y + 85, w - 20, 10))
            pygame.draw.rect(surface, (100, 200, 100), (x + 10, y + 85, int((w - 20) * ratio), 10))

            y_off = y + 110
            surface.blit(self.font.render("已送达材料:", True, (200, 200, 100)), (x + 10, y_off))
            y_off += 25
            cost = BUILDING_DEFS[selected_building.kind]["variants"][selected_building.material]["cost"]
            for k, v_need in cost.items():
                v_have = selected_building.delivered_materials.get(k, 0)
                name = ITEM_DEFS.get(k, {}).get("name", k)
                col = (100, 200, 100) if v_have >= v_need else (200, 100, 100)
                txt = self.font.render(f"{name}: {v_have} / {v_need}", True, col)
                surface.blit(txt, (x + 20, y_off))
                y_off += 20

        else:
            hp_surf = self.font.render(f"耐久: {int(selected_building.hp)} / {selected_building.max_hp}", True, WHITE)
            surface.blit(hp_surf, (x + 10, y + 60))
            ratio = selected_building.hp / selected_building.max_hp
            pygame.draw.rect(surface, (40, 20, 20), (x + 10, y + 85, w - 20, 10))
            pygame.draw.rect(surface, (200, 80, 80), (x + 10, y + 85, int((w - 20) * ratio), 10))

            if selected_building.kind == "stove":
                surface.blit(self.font.render("发布烹饪任务:", True, (200, 200, 100)), (x + 10, y + 105))

                self.cook_simple_btn = pygame.Rect(x + 10, y + 130, 130, 30)
                pygame.draw.rect(surface, (100, 200, 100), self.cook_simple_btn, border_radius=4)
                surface.blit(self.font.render("简单食物 (1食材)", True, (0, 0, 0)), (x + 15, y + 137))

                self.cook_fine_btn = pygame.Rect(x + 150, y + 130, 130, 30)
                pygame.draw.rect(surface, (80, 200, 200), self.cook_fine_btn, border_radius=4)
                surface.blit(self.font.render("美味食物 (1肉1素)", True, (0, 0, 0)), (x + 155, y + 137))

                surface.blit(self.font.render("当前队列:", True, WHITE), (x + 10, y + 170))
                y_q = y + 195
                if not selected_building.cook_queue:
                    surface.blit(self.font.render("（空）", True, (150, 150, 150)), (x + 20, y_q))
                else:
                    for i, task in enumerate(selected_building.cook_queue[:3]):
                        meal_name = "简单食物" if task["meal"] == "meal_simple" else "美味食物"
                        txt = self.font.render(f"{i + 1}. {meal_name}", True, WHITE)
                        surface.blit(txt, (x + 20, y_q))
                        y_q += 20
                    if len(selected_building.cook_queue) > 3:
                        txt = self.font.render(f"...等 {len(selected_building.cook_queue)} 个任务", True,
                                               (150, 150, 150))
                        surface.blit(txt, (x + 20, y_q))

                if not selected_building.marked_for_deconstruction:
                    self.deconstruct_btn = pygame.Rect(x + 10, y + 260, w - 20, 30)
                    pygame.draw.rect(surface, (180, 60, 60), self.deconstruct_btn, border_radius=4)
                    btn_txt = self.font.render("标记为拆除 (D)", True, WHITE)
                    surface.blit(btn_txt,
                                 (self.deconstruct_btn.centerx - btn_txt.get_width() // 2, self.deconstruct_btn.y + 6))
                else:
                    self.deconstruct_btn = pygame.Rect(0, 0, 0, 0)
                return

            elif selected_building.kind in ("small_cabinet", "large_cabinet"):
                surface.blit(self.font.render("内部物品:", True, (200, 200, 100)), (x + 10, y + 110))
                y_off = 140
                if not selected_building.inventory:
                    surface.blit(self.font.render("（空）", True, (150, 150, 150)), (x + 20, y_off))
                else:
                    for k, amt in selected_building.inventory.items():
                        name = ITEM_DEFS.get(k, {}).get("name", k)
                        txt = self.font.render(f"{name}: {amt}", True, WHITE)
                        surface.blit(txt, (x + 20, y_off))
                        y_off += 22
                        if y_off > y + h - 60: break

                types_used = len(selected_building.inventory)
                types_max = selected_building.max_types
                types_txt = self.font.render(f"种类: {types_used} / {types_max}", True, (150, 150, 150))
                surface.blit(types_txt, (x + 10, y + h - 50))

            if not selected_building.marked_for_deconstruction:
                self.deconstruct_btn = pygame.Rect(x + 10, y + h - 40, w - 20, 30)
                pygame.draw.rect(surface, (180, 60, 60), self.deconstruct_btn, border_radius=4)
                btn_txt = self.font.render("标记为拆除 (D)", True, WHITE)
                surface.blit(btn_txt,
                             (self.deconstruct_btn.centerx - btn_txt.get_width() // 2, self.deconstruct_btn.y + 6))
            else:
                self.deconstruct_btn = pygame.Rect(0, 0, 0, 0)
                cancel_surf = self.font.render("已在拆除队列中...", True, (200, 100, 100))
                surface.blit(cancel_surf, (x + 10, y + h - 30))

    def handle_click(self, mouse_pos, selected_building, global_items):
        if not selected_building: return False, None

        if self.panel_rect.collidepoint(mouse_pos):
            if hasattr(selected_building, "hp") and not selected_building.marked_for_deconstruction:
                if self.deconstruct_btn.collidepoint(mouse_pos):
                    selected_building.marked_for_deconstruction = True
                    return True, None

                if selected_building.kind == "stove":
                    if self.cook_simple_btn.collidepoint(mouse_pos):
                        selected_building.cook_queue.append({"meal": "meal_simple"})
                        return True, None
                    if self.cook_fine_btn.collidepoint(mouse_pos):
                        selected_building.cook_queue.append({"meal": "meal_fine"})
                        return True, None

            return True, None
        return False, None