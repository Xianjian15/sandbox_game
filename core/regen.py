# core/regen.py
"""小人自动回血规则（纯函数，不依赖 pygame，便于单独测试）。

规则：
  - 满血、已死亡、正在流血、或受伤后不足 REGEN_DELAY 秒：不回血
  - 否则每秒恢复 REGEN_RATE 点；睡觉时 ×3
  - 饱食度为 0（饿着）：不回血；低于 20：速度减半
  - 单步不会超过最大血量
全部是 dt 的确定性函数，联机两端结果一致。
"""
from settings import REGEN_DELAY, REGEN_RATE


def regen_amount(hp, max_hp, bleeding, sleeping, since_hurt, satiety, dt):
    if hp <= 0 or hp >= max_hp or bleeding > 0 or since_hurt < REGEN_DELAY or satiety <= 0:
        return 0.0
    rate = REGEN_RATE * (3.0 if sleeping else 1.0) * (0.5 if satiety < 20 else 1.0)
    return min(rate * dt, max_hp - hp)
