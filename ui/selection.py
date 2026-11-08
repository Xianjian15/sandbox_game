# ui/selection.py
import pygame
from settings import TILE_SIZE

class Selection:
    def __init__(self):
        self.dragging = False
        self.start = (0, 0)
        self.end = (0, 0)
        self.selected_tiles = set()
        self.hover_tile = None

    def handle_event(self, event, camera, mouse_pos):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.dragging = True
            self.start = mouse_pos
            self.end = mouse_pos
        elif event.type == pygame.MOUSEMOTION:
            if self.dragging: self.end = mouse_pos
            self.hover_tile = camera.screen_to_tile(*mouse_pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.dragging:
                self.dragging = False
                x1, y1 = self.start
                x2, y2 = self.end
                rect = pygame.Rect(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
                self.selected_tiles.clear()
                t1 = camera.screen_to_tile(rect.left, rect.top)
                t2 = camera.screen_to_tile(rect.right, rect.bottom)
                for ty in range(t1[1], t2[1] + 1):
                    for tx in range(t1[0], t2[0] + 1):
                        self.selected_tiles.add((tx, ty))

    def clear(self):
        self.selected_tiles.clear()

    def draw(self, surface, camera):
        # 只画拖拽框，不再画地块高亮
        if self.dragging:
            x1, y1 = self.start
            x2, y2 = self.end
            r = pygame.Rect(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
            pygame.draw.rect(surface, (255, 255, 255), r, 1)