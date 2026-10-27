# core/camera.py
import pygame
from settings import TILE_SIZE

class Camera:
    def __init__(self, vw, vh, map_w_px, map_h_px):
        self.x = 0.0
        self.y = 0.0
        self.vw = vw
        self.vh = vh
        self.map_w = map_w_px
        self.map_h = map_h_px

    def move_by(self, dx, dy):
        self.x += dx
        self.y += dy
        self._clamp()

    def _clamp(self):
        self.x = max(0, min(self.x, self.map_w - self.vw))
        self.y = max(0, min(self.y, self.map_h - self.vh))

    def resize(self, vw, vh):
        self.vw = vw
        self.vh = vh
        self._clamp()

    def world_to_screen(self, wx, wy):
        return wx - self.x, wy - self.y

    def screen_to_world(self, sx, sy):
        return sx + self.x, sy + self.y

    def screen_to_tile(self, sx, sy):
        wx, wy = self.screen_to_world(sx, sy)
        return int(wx // TILE_SIZE), int(wy // TILE_SIZE)