# core/time_system.py
import math


class GameTime:
    """游戏内时间：一天 = day_length_sec 秒真实时间"""
    def __init__(self, day_length_sec=120.0, start_hour=6.0):
        self.day_length_sec = day_length_sec
        self.start_hour = start_hour
        self.elapsed = 0.0

    @property
    def day(self):
        return int(self.elapsed // self.day_length_sec) + 1

    @property
    def hour(self):
        """返回 0.0 ~ 24.0 的小时"""
        frac = (self.elapsed % self.day_length_sec) / self.day_length_sec
        h = (self.start_hour + frac * 24) % 24
        return h

    @property
    def is_night(self):
        return self.hour < 6 or self.hour >= 20

    @property
    def is_day(self):
        return not self.is_night

    def get_light_level(self):
        """0.0(全黑) ~ 1.0(全亮)"""
        h = self.hour
        # 6 点开始亮，8 点全亮；18 点开始暗，20 点全黑
        if 8 <= h < 18:
            return 1.0
        if 6 <= h < 8:
            return 0.3 + (h - 6) / 2 * 0.7
        if 18 <= h < 20:
            return 1.0 - (h - 18) / 2 * 0.7
        # 20 ~ 6 全黑
        return 0.3

    def time_str(self):
        h = int(self.hour)
        m = int((self.hour - h) * 60)
        return f"第{self.day}天 {h:02d}:{m:02d}"

    def update(self, dt):
        self.elapsed += dt