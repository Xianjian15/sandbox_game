# settings.py
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 60
TILE_SIZE = 32
MAP_WIDTH = 160
MAP_HEIGHT = 120
INIT_W, INIT_H = 1280, 720

# 颜色
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
DARK = (30, 30, 35)
GRASS = (78, 122, 62)
GRASS2 = (70, 112, 56)
DIRT = (120, 95, 65)
ROCK = (110, 110, 115)
WATER = (52, 90, 140)
TREE = (48, 88, 40)

SELECT = (255, 220, 80)
HOVER = (255, 255, 255)
RED = (200, 60, 60)
GREEN = (60, 200, 60)
YELLOW = (230, 200, 60)
GRAY = (120, 120, 120)

# ---- 固定步长模拟（锁步联机的基础）----
# 模拟永远以 TICK_DT 为单位推进，与帧率、倍速无关；倍速 = 每秒多跑几个 tick。
TICK_RATE = 60
TICK_DT = 1.0 / TICK_RATE
# 自动回血：受伤后 REGEN_DELAY 秒内没再受伤、且没有在流血，就每秒恢复 REGEN_RATE 点（睡觉 ×3，饥饿时减半/停止）
REGEN_DELAY = 5.0
REGEN_RATE = 0.5
START_COLONISTS = 1        # 每位玩家开局的小人数量
MAX_TICKS_PER_FRAME = 8   # 单帧最多补多少个 tick，防止卡顿后越补越卡
