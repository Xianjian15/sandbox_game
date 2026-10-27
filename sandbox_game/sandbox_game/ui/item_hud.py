# ui/item_hud.py
import pygame
from settings import WHITE
from world.items import ITEM_DEFS


class ItemHUD:
    def __init__(self, font):
        self.font = font
        self.panel_w = 260
        self.panel_h = 200
        self.panel_rect = pygame.Rect(10, 60, self.panel_w, self.panel_h)
        self.selected_stack = None
        self.selected_tile = None

    def set_target(self, stack, tx, ty):
        self.selected_stack = stack
        self.selected_tile = (tx, ty)

    def draw(self, surface, buildings):
        if not self.selected_stack: return

        x, y = self.panel_rect.x, self.panel_rect.y
        w, h = self.panel_w, self.panel_h
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        panel.fill((20, 20, 25, 210))
        surface.blit(panel, (x, y))
        pygame.draw.rect(surface, (100, 100, 110), (x, y, w, h), 2)

        kind = self.selected_stack.kind
        amt = self.selected_stack.amount
        d = ITEM_DEFS.get(kind, {"name": kind, "desc": ""})

        title = self.font.render(f"{d['name']} x{amt}", True, (255, 220, 100))
        surface.blit(title, (x + 10, y + 10))

        # 描述
        desc_lines = d.get("desc", "").split('\n')
        y_off = y + 40
        for line in desc_lines:
            surface.blit(self.font.render(line, True, (180, 180, 180)), (x + 10, y_off))
            y_off += 20

        y_off += 10

        if kind in ("meal_simple", "meal_fine"):
            # 计算洁净度
            tx, ty = self.selected_tile
            b = buildings.get_building_at(tx, ty)

            cleanliness = 50
            loc_name = "地面"

            # 检查是否在柜子里（由于物品在地图数据结构上，这里只计算地面上的情况，如果是柜子内部点击，则特殊处理）
            # 实际上点击柜子里的物品时，tx, ty是柜子坐标，我们要判断是不是在柜子内部

            # 判断地板
            floor = buildings.get_building_at(tx, ty)
            if floor and floor.kind == "floor":
                cleanliness = 80
                loc_name = "地板上"

            # 判断是否在库存区（略，仅作为加成选项之一，这里按地板算）

            # 因为是地图上的物品，不在柜子内部，所以最高80%
            # 如果是点击柜子里的物品，通过传入不同的数据来处理
            if getattr(self, "in_cabinet", False):
                cleanliness = 100
                loc_name = "柜子内"

            surface.blit(self.font.render(f"洁净度: {cleanliness}% ({loc_name})", True,
                                          (100, 200, 100) if cleanliness >= 80 else (200, 100, 100)), (x + 10, y_off))
            y_off += 20

            if cleanliness == 100:
                surface.blit(self.font.render("食用效果: 饱食度+100% 心情+20", True, WHITE), (x + 10, y_off))
            elif cleanliness == 80:
                surface.blit(self.font.render("食用效果: 饱食度+80% 心情+10", True, WHITE), (x + 10, y_off))
            else:
                surface.blit(self.font.render("食用效果: 饱食度+50% 生病风险+20%", True, (200, 80, 80)),
                             (x + 10, y_off))

        elif d.get("type") == "material":
            surface.blit(self.font.render("基础建造材料", True, (150, 150, 150)), (x + 10, y_off))

    def handle_click(self, mouse_pos):
        if not self.selected_stack: return False
        if self.panel_rect.collidepoint(mouse_pos):
            return True
        return False