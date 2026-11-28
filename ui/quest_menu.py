# ui/quest_menu.py
"""支线任务面板：和科技面板一样是"打开才出现"的界面（工具栏「任务」/ Q 键），不再常驻遮挡其他面板。"""
import pygame
from systems.quests import CHAINS, _name_item


class QuestMenu:
    ROW = 62

    def __init__(self, font):
        self.font = font
        self.panel_rect = pygame.Rect(0, 0, 0, 0)

    def draw(self, surface, screen_w, screen_h, g):
        qm = g.quests
        cache = {}
        rows = [(q, qm.progress(q, g, cache)) for q in qm.active]
        w = 600
        h = min(screen_h - 120, 110 + max(1, len(rows)) * self.ROW + 60)
        x, y = screen_w // 2 - w // 2, max(10, (screen_h - 60) // 2 - h // 2)
        self.panel_rect = pygame.Rect(x, y, w, h)
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        panel.fill((20, 20, 25, 240))
        surface.blit(panel, (x, y))
        pygame.draw.rect(surface, (200, 170, 80), (x, y, w, h), 2)
        surface.blit(self.font.render("支线任务 (Q 关闭)", True, (255, 220, 120)), (x + 20, y + 15))
        surface.blit(self.font.render(f"进行中 {len(rows)}    已完成 {qm.done}", True, (190, 190, 170)),
                     (x + 20, y + 42))
        ty = y + 76
        if not rows:
            surface.blit(self.font.render("暂无任务，稍后会有新的委托", True, (170, 170, 170)), (x + 20, ty))
            ty += self.ROW
        for q, p in rows:
            r = pygame.Rect(x + 20, ty, w - 40, self.ROW - 6)
            pygame.draw.rect(surface, (45, 45, 50), r, border_radius=4)
            pygame.draw.rect(surface, (100, 100, 110), r, 1, border_radius=4)
            tag = ""
            if q["chain"] >= 0:
                name, _, steps = CHAINS[q["chain"]]
                tag = f"【{name} {q['step'] + 1}/{len(steps)}】"
            surface.blit(self.font.render(tag + q["title"], True, (235, 235, 240)), (r.x + 10, r.y + 6))
            ratio = min(1.0, p / max(1, q["target"]))
            bar = pygame.Rect(r.x + 10, r.y + 28, r.w - 20, 8)
            pygame.draw.rect(surface, (50, 50, 55), bar)
            pygame.draw.rect(surface, (110, 200, 120), (bar.x, bar.y, int(bar.w * ratio), bar.h))
            rtxt = "、".join(f"{_name_item(k)}×{v}" for k, v in q["reward"].items())
            surface.blit(self.font.render(f"{min(p, q['target'])}/{q['target']}   奖励：{rtxt}", True,
                                          (190, 190, 150)), (r.x + 10, r.y + 38))
            ty += self.ROW
        recent = qm.completed_titles[-3:]
        if recent:
            surface.blit(self.font.render("最近完成：" + "、".join(recent), True, (120, 190, 130)),
                         (x + 20, y + h - 28))

    def handle_click(self, pos):
        return self.panel_rect.collidepoint(pos)       # 面板内的点击一律吞掉
