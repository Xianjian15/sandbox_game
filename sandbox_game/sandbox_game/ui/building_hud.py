# ui/building_hud.py
import pygame
from settings import WHITE
from world.buildings import BUILDING_DEFS
from world.items import ITEM_DEFS


class BuildingHUD:
    def __init__(self, font, screen_w=None):
        self.font = font
        self.panel_w = 300
        self.panel_rect = pygame.Rect(10, 60, self.panel_w, 220)
        self.deconstruct_btn = pygame.Rect(0, 0, 0, 0)
        self.btn_rects = {}

        self.input_rects = {}
        self.name_rects = {}
        self.active_input = None
        self.edit_text = ""

        self.item_rects = {}
        self.last_action = None

        self.take_input_rects = {}
        self.take_btn_rects = {}

    def get_counts(self, selected_building):
        counts = {"meal_simple": 0, "meal_fine": 0}
        if hasattr(selected_building, "cook_queue"):
            for task in selected_building.cook_queue:
                if task["meal"] in counts: counts[task["meal"]] += 1
        return counts

    def apply_input(self, selected_building):
        if not selected_building or not self.active_input: return

        if selected_building.kind == "stove":
            counts = self.get_counts(selected_building)
            try:
                counts[self.active_input] = max(0, int(self.edit_text))
            except:
                pass
            self.edit_text = ""
            selected_building.cook_queue = []
            for k in ["meal_simple", "meal_fine"]:
                for _ in range(counts[k]): selected_building.cook_queue.append({"meal": k})

        elif selected_building.kind == "furnace":
            try:
                num = max(0, int(self.edit_text))
            except:
                num = 0
            self.edit_text = ""
            selected_building.smelt_queue = []
            for _ in range(num): selected_building.smelt_queue.append({"item": "iron"})

    def handle_key(self, event, selected_building):
        if self.active_input:
            if event.key == pygame.K_RETURN:
                if selected_building.kind not in ("small_cabinet", "large_cabinet"):
                    self.apply_input(selected_building)
                    self.active_input = None
                return True
            elif event.key == pygame.K_BACKSPACE:
                self.edit_text = self.edit_text[:-1];
                return True
            elif event.key == pygame.K_ESCAPE:
                self.active_input = None;
                return True
            return True
        return False

    def handle_text(self, event, selected_building):
        if self.active_input:
            if event.text.isdigit():
                self.edit_text += event.text
                if len(self.edit_text) > 3: self.edit_text = self.edit_text[:3]
            return True
        return False

    def handle_right_click(self, mouse_pos, selected_building):
        if not selected_building: return False
        if self.panel_rect.collidepoint(mouse_pos):
            if selected_building.kind == "stove":
                for meal, rect in self.name_rects.items():
                    if rect.collidepoint(mouse_pos):
                        selected_building.cook_queue = [t for t in selected_building.cook_queue if t["meal"] != meal]
                        return True
            elif selected_building.kind == "furnace":
                if "iron" in self.name_rects and self.name_rects["iron"].collidepoint(mouse_pos):
                    selected_building.smelt_queue.clear()
                    return True
            return True
        return False

    def handle_click(self, mouse_pos, selected_building, global_items, research):
        if not selected_building: return False, None
        self.last_action = None

        if self.panel_rect.collidepoint(mouse_pos):
            if hasattr(selected_building, "hp") and not selected_building.marked_for_deconstruction:
                if self.deconstruct_btn.collidepoint(mouse_pos):
                    selected_building.marked_for_deconstruction = True
                    return True, None

                # 处理柜子取出逻辑
                if selected_building.kind in ("small_cabinet", "large_cabinet"):
                    for kind, rect in self.take_input_rects.items():
                        if rect.collidepoint(mouse_pos):
                            self.active_input = f"take_{kind}"
                            self.edit_text = ""
                            return True, None

                    for kind, btn_rect in self.take_btn_rects.items():
                        if btn_rect.collidepoint(mouse_pos):
                            if self.active_input == f"take_{kind}" and self.edit_text.strip():
                                try:
                                    amt = int(self.edit_text)
                                    if amt > 0:
                                        self.last_action = ("take", kind, amt)
                                except:
                                    self.last_action = ("take", kind, selected_building.inventory.get(kind, 0))
                            else:
                                self.last_action = ("take", kind, selected_building.inventory.get(kind, 0))
                            self.active_input = None
                            return True, None

                for k, rect in self.input_rects.items():
                    if rect.collidepoint(mouse_pos):
                        self.apply_input(selected_building)
                        self.active_input = k
                        if selected_building.kind == "stove":
                            self.edit_text = str(self.get_counts(selected_building)[k])
                        elif selected_building.kind == "furnace":
                            self.edit_text = str(len(selected_building.smelt_queue))
                        return True, None

                self.apply_input(selected_building)
                self.active_input = None

                for action, rect in self.btn_rects.items():
                    if rect.collidepoint(mouse_pos):
                        if action == "craft_stone_pick":
                            selected_building.craft_queue.append({"item": "stone_pickaxe"})
                        elif action == "craft_axe":
                            selected_building.craft_queue.append({"item": "axe"})
                        elif action == "craft_pick":
                            selected_building.craft_queue.append({"item": "iron_pickaxe"})
                        elif action == "craft_sword":
                            selected_building.craft_queue.append({"item": "longsword"})
                        elif action == "craft_gun":
                            selected_building.craft_queue.append({"item": "gun"})
                        return True, None
            return True, None
        else:
            self.apply_input(selected_building)
            self.active_input = None
        return False, None

    def draw(self, surface, selected_building, global_items, research):
        if not selected_building: return

        screen_w = surface.get_width()
        if selected_building.kind in ("small_cabinet", "large_cabinet"):
            self.panel_rect.x = screen_w - self.panel_w - 20
        else:
            self.panel_rect.x = 10

        x, y, w = self.panel_rect.x, self.panel_rect.y, self.panel_w

        # 判断是否为蓝图（未完工）
        is_blueprint = not hasattr(selected_building, "hp")

        if selected_building.kind in ("stove", "furnace", "workbench"):
            h = 380
        elif selected_building.kind in ("small_cabinet", "large_cabinet"):
            h = 500
        elif is_blueprint:
            h = 320
        else:
            h = 300

        self.panel_rect.h = h
        self.btn_rects.clear()
        self.input_rects.clear()
        self.name_rects.clear()
        self.item_rects.clear()
        self.take_input_rects.clear()
        self.take_btn_rects.clear()

        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        panel.fill((20, 20, 25, 230))
        surface.blit(panel, (x, y))
        pygame.draw.rect(surface, (100, 100, 110), (x, y, w, h), 2)

        title = BUILDING_DEFS[selected_building.kind]["variants"][selected_building.material]["name"]
        if is_blueprint:
            title += " (蓝图)"
        surface.blit(self.font.render(title, True, (255, 220, 100)), (x + 10, y + 10))

        if is_blueprint:
            # ---- 蓝图：显示建造进度 + 缺料 ----
            work_done = getattr(selected_building, "work_done", 0)
            total_work = getattr(selected_building, "total_work", None)
            if total_work is None or total_work <= 0:
                bd = BUILDING_DEFS[selected_building.kind]["variants"][selected_building.material]
                total_work = bd.get("build_time", bd.get("work", 100))
            ratio = max(0.0, min(1.0, work_done / max(1, total_work)))
            surface.blit(self.font.render(f"建造进度: {int(ratio * 100)}%", True, WHITE), (x + 10, y + 40))
            pygame.draw.rect(surface, (40, 40, 20), (x + 10, y + 65, w - 20, 10))
            pygame.draw.rect(surface, (220, 200, 80), (x + 10, y + 65, int((w - 20) * ratio), 10))

            if hasattr(selected_building, "missing_materials"):
                missing = selected_building.missing_materials()
                if missing:
                    surface.blit(self.font.render("缺少材料:", True, (255, 150, 100)), (x + 10, y + 95))
                    yy = y + 115
                    for k, v in missing.items():
                        name = ITEM_DEFS.get(k, {}).get("name", k)
                        surface.blit(self.font.render(f"{name} x{v}", True, (255, 200, 100)), (x + 20, yy))
                        yy += 20
                else:
                    surface.blit(self.font.render("材料已齐，等待建造", True, (150, 255, 150)),
                                 (x + 10, y + 95))

            # 蓝图的拆除按钮（取消建造），单独用一个矩形
            self.deconstruct_btn = pygame.Rect(x + 10, y + h - 45, w - 20, 30)
            pygame.draw.rect(surface, (180, 60, 60), self.deconstruct_btn, border_radius=4)
            btn_txt = self.font.render("取消建造", True, WHITE)
            surface.blit(btn_txt, (self.deconstruct_btn.centerx - btn_txt.get_width() // 2,
                                   self.deconstruct_btn.y + 6))
            return

        # ---- 已完工建筑：原逻辑 ----
        surface.blit(self.font.render(f"耐久: {int(selected_building.hp)}/{selected_building.max_hp}", True, WHITE),
                     (x + 10, y + 40))
        pygame.draw.rect(surface, (40, 20, 20), (x + 10, y + 65, w - 20, 10))
        pygame.draw.rect(surface, (200, 80, 80),
                         (x + 10, y + 65, int((w - 20) * (selected_building.hp / selected_building.max_hp)), 10))

        if selected_building.kind == "stove":
            surface.blit(self.font.render("发布烹饪任务:", True, (200, 200, 100)), (x + 10, y + 95))
            surface.blit(self.font.render("(右键名称取消)", True, (150, 150, 150)), (x + 10, y + 115))
            counts = self.get_counts(selected_building)

            self.name_rects["meal_simple"] = pygame.Rect(x + 10, y + 145, 100, 30)
            surface.blit(self.font.render("简单食物", True, (200, 220, 100)), (x + 10, y + 150))
            surface.blit(self.font.render("(2食材)", True, (150, 150, 150)), (x + 85, y + 150))
            self.input_rects["meal_simple"] = pygame.Rect(x + 150, y + 145, 50, 30)
            pygame.draw.rect(surface, (50, 50, 50), self.input_rects["meal_simple"])
            if self.active_input == "meal_simple":
                pygame.draw.rect(surface, (255, 255, 255), self.input_rects["meal_simple"], 2)
                txt = self.edit_text + ("|" if pygame.time.get_ticks() % 1000 < 500 else "")
            else:
                pygame.draw.rect(surface, (100, 100, 150), self.input_rects["meal_simple"], 1)
                txt = str(counts["meal_simple"])
            surface.blit(self.font.render(txt, True, WHITE), (x + 165, y + 150))

            self.name_rects["meal_fine"] = pygame.Rect(x + 10, y + 185, 100, 30)
            surface.blit(self.font.render("美味食物", True, (100, 220, 220)), (x + 10, y + 190))
            surface.blit(self.font.render("(4食材)", True, (150, 150, 150)), (x + 85, y + 190))
            self.input_rects["meal_fine"] = pygame.Rect(x + 150, y + 185, 50, 30)
            pygame.draw.rect(surface, (50, 50, 50), self.input_rects["meal_fine"])
            if self.active_input == "meal_fine":
                pygame.draw.rect(surface, (255, 255, 255), self.input_rects["meal_fine"], 2)
                txt = self.edit_text + ("|" if pygame.time.get_ticks() % 1000 < 500 else "")
            else:
                pygame.draw.rect(surface, (100, 100, 150), self.input_rects["meal_fine"], 1)
                txt = str(counts["meal_fine"])
            surface.blit(self.font.render(txt, True, WHITE), (x + 165, y + 190))

            surface.blit(self.font.render("当前队列总数:", True, WHITE), (x + 10, y + 225))
            y_q = y + 250
            if not selected_building.cook_queue:
                surface.blit(self.font.render("（空）", True, (150, 150, 150)), (x + 20, y_q))
            else:
                total = sum(counts.values())
                surface.blit(self.font.render(f"{total} 个任务待完成", True, (200, 200, 100)), (x + 20, y_q))
                if selected_building.cook_progress > 0:
                    prog_ratio = min(1.0, selected_building.cook_progress / 100.0)
                    pygame.draw.rect(surface, (40, 40, 40), (x + 10, y + 280, w - 20, 10))
                    pygame.draw.rect(surface, (255, 200, 60), (x + 10, y + 280, int((w - 20) * prog_ratio), 10))
                    surface.blit(self.font.render("正在烹饪...", True, (255, 200, 60)), (x + 10, y + 295))

        elif selected_building.kind == "furnace":
            surface.blit(self.font.render("发布熔炼任务:", True, (200, 200, 100)), (x + 10, y + 95))
            surface.blit(self.font.render("(右键名称取消)", True, (150, 150, 150)), (x + 10, y + 115))

            self.name_rects["iron"] = pygame.Rect(x + 10, y + 145, 100, 30)
            surface.blit(self.font.render("粗铁 -> 铁", True, (200, 220, 100)), (x + 10, y + 150))
            surface.blit(self.font.render("(2粗铁)", True, (150, 150, 150)), (x + 85, y + 150))

            self.input_rects["iron"] = pygame.Rect(x + 150, y + 145, 50, 30)
            pygame.draw.rect(surface, (50, 50, 50), self.input_rects["iron"])
            if self.active_input == "iron":
                pygame.draw.rect(surface, (255, 255, 255), self.input_rects["iron"], 2)
                txt = self.edit_text + ("|" if pygame.time.get_ticks() % 1000 < 500 else "")
            else:
                pygame.draw.rect(surface, (100, 100, 150), self.input_rects["iron"], 1)
                txt = str(len(selected_building.smelt_queue))
            surface.blit(self.font.render(txt, True, WHITE), (x + 165, y + 150))

            surface.blit(
                self.font.render(f"仓库存量: 粗铁 {selected_building.inventory.get('iron_ore', 0)}", True, WHITE),
                (x + 10, y + 195))
            surface.blit(self.font.render("当前队列总数:", True, WHITE), (x + 10, y + 225))
            y_q = y + 250
            if not selected_building.smelt_queue:
                surface.blit(self.font.render("（空）", True, (150, 150, 150)), (x + 20, y_q))
            else:
                surface.blit(
                    self.font.render(f"{len(selected_building.smelt_queue)} 个熔炼任务排队中", True, (200, 200, 100)),
                    (x + 20, y_q))
                if selected_building.smelt_progress > 0:
                    prog_ratio = min(1.0, selected_building.smelt_progress / 150.0)
                    pygame.draw.rect(surface, (40, 40, 40), (x + 10, y + 280, w - 20, 10))
                    pygame.draw.rect(surface, (255, 150, 50), (x + 10, y + 280, int((w - 20) * prog_ratio), 10))
                    surface.blit(self.font.render("正在熔炼...", True, (255, 150, 50)), (x + 10, y + 295))

        elif selected_building.kind == "workbench":
            surface.blit(self.font.render("制造装备:", True, (200, 200, 100)), (x + 10, y + 100))
            r1 = pygame.Rect(x + 10, y + 130, 80, 30)
            r2 = pygame.Rect(x + 100, y + 130, 80, 30)
            r3 = pygame.Rect(x + 190, y + 130, 80, 30)
            r4 = pygame.Rect(x + 10, y + 170, 80, 30)
            r5 = pygame.Rect(x + 100, y + 170, 80, 30)

            can_iron = research and "crafting" in research.completed
            can_gun = research and "gunsmithing" in research.completed

            col2 = (150, 150, 150) if can_iron else (60, 60, 60)
            col3 = (150, 150, 150) if can_iron else (60, 60, 60)
            col4 = (200, 200, 210) if can_iron else (60, 60, 60)
            col5 = (100, 120, 180) if can_gun else (60, 60, 60)

            pygame.draw.rect(surface, (130, 130, 135), r1, border_radius=4)
            surface.blit(self.font.render("石镐(2石)", True, (0, 0, 0)), (x + 15, y + 137))
            pygame.draw.rect(surface, col2, r2, border_radius=4)
            surface.blit(self.font.render("铁斧(2铁)", True, (0, 0, 0)), (x + 105, y + 137))
            pygame.draw.rect(surface, col3, r3, border_radius=4)
            surface.blit(self.font.render("铁镐(2铁)", True, (0, 0, 0)), (x + 195, y + 137))
            pygame.draw.rect(surface, col4, r4, border_radius=4)
            surface.blit(self.font.render("长剑(3铁)", True, (0, 0, 0)), (x + 15, y + 177))
            pygame.draw.rect(surface, col5, r5, border_radius=4)
            surface.blit(self.font.render("枪械(5铁)", True, (255, 255, 255)), (x + 105, y + 177))

            self.btn_rects["craft_stone_pick"] = r1
            if can_iron:
                self.btn_rects["craft_axe"] = r2
                self.btn_rects["craft_pick"] = r3
                self.btn_rects["craft_sword"] = r4
            if can_gun:
                self.btn_rects["craft_gun"] = r5

            surface.blit(self.font.render(f"制造队列: {len(selected_building.craft_queue)}", True, WHITE),
                         (x + 10, y + 215))

        elif selected_building.kind in ("small_cabinet", "large_cabinet"):
            pygame.draw.line(surface, (80, 80, 80), (x + 10, y + 85), (x + w - 10, y + 85), 1)
            surface.blit(self.font.render("内部物品 (输入数量后点击取出):", True, (200, 200, 100)), (x + 10, y + 95))

            y_off = y + 125
            sorted_items = list(selected_building.inventory.items())

            for idx in range(10):
                if idx < len(sorted_items):
                    kind, amt = sorted_items[idx]
                    name = ITEM_DEFS.get(kind, {}).get("name", kind)
                    txt = self.font.render(f"{name} ({amt})", True, WHITE)
                    surface.blit(txt, (x + 15, y_off))

                    take_inp_rect = pygame.Rect(x + 140, y_off - 4, 50, 24)
                    self.take_input_rects[kind] = take_inp_rect
                    pygame.draw.rect(surface, (40, 40, 40), take_inp_rect)
                    if self.active_input == f"take_{kind}":
                        pygame.draw.rect(surface, (255, 255, 255), take_inp_rect, 1)
                        inp_txt = self.edit_text + ("|" if pygame.time.get_ticks() % 1000 < 500 else "")
                    else:
                        pygame.draw.rect(surface, (80, 80, 100), take_inp_rect, 1)
                        inp_txt = ""
                    surface.blit(self.font.render(inp_txt, True, WHITE), (x + 145, y_off - 2))

                    take_btn_rect = pygame.Rect(x + 195, y_off - 4, 50, 24)
                    self.take_btn_rects[kind] = take_btn_rect
                    pygame.draw.rect(surface, (100, 150, 100), take_btn_rect, border_radius=4)
                    btn_txt = self.font.render("取出", True, WHITE)
                    surface.blit(btn_txt, (take_btn_rect.centerx - btn_txt.get_width() // 2,
                                           take_btn_rect.centery - btn_txt.get_height() // 2))
                y_off += 32

            pygame.draw.line(surface, (80, 80, 80), (x + 10, y + h - 75), (x + w - 10, y + h - 75), 1)
            types_used = len(selected_building.inventory)
            types_max = selected_building.max_types
            surface.blit(self.font.render(f"种类: {types_used} / {types_max}", True, (150, 150, 150)),
                         (x + 10, y + h - 65))

        if not getattr(selected_building, "marked_for_deconstruction", False):
            self.deconstruct_btn = pygame.Rect(x + 10, y + h - 45, w - 20, 30)
            pygame.draw.rect(surface, (180, 60, 60), self.deconstruct_btn, border_radius=4)
            btn_txt = self.font.render("标记为拆除", True, WHITE)
            surface.blit(btn_txt, (self.deconstruct_btn.centerx - btn_txt.get_width() // 2, self.deconstruct_btn.y + 6))
        else:
            self.deconstruct_btn = pygame.Rect(0, 0, 0, 0)