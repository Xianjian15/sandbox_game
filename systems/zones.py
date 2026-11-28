# systems/zones.py
"""持续性的"采集区 / 狩猎区"。

玩家用工具栏的 采集 / 狩猎 在地图上划区（可反复划、可擦除）。区域是模拟状态（参与哈希）：
  * 采集区：空闲的小人会自动去砍区内的树、挖区内的石头 / 矿 / 陨石（需要合适工具的会跳过）。
  * 狩猎区：空闲且持有武器的小人会自动去打区内的动物（空手不去，免得送命）。
所有选择都是确定性的：按"距离、坐标"排序，没有随机数、没有浮点。
"""
KINDS = ("harvest", "hunt")
CHECK_EVERY = 30             # tick：每半秒分配一次
FAIL_COOLDOWN = 600          # tick：某格/某只动物够不着时，十秒内不再选它
MAX_TRIES = 5                # 每个小人每轮最多试几个候选（寻路有成本）
MIN_REST, MIN_SATIETY, MIN_HP = 35, 45, 50


class ZoneManager:
    def __init__(self):
        self.tiles = {"harvest": set(), "hunt": set()}
        self.cooldown = {}       # (kind, key) -> 解除冷却的 tick

    # ---------- 编辑 ----------
    def paint(self, kind, x1, y1, x2, y2, on, cols, rows):
        if kind not in KINDS:
            return
        x1, x2 = max(0, min(x1, x2)), min(cols - 1, max(x1, x2))
        y1, y2 = max(0, min(y1, y2)), min(rows - 1, max(y1, y2))
        s = self.tiles[kind]
        for ty in range(y1, y2 + 1):
            for tx in range(x1, x2 + 1):
                if on:
                    s.add((tx, ty))
                else:
                    s.discard((tx, ty))

    def clear(self, kind):
        if kind in KINDS:
            self.tiles[kind].clear()

    def count(self, kind):
        return len(self.tiles[kind])

    def snapshot(self):
        return (sorted(self.tiles["harvest"]), sorted(self.tiles["hunt"]), sorted(self.cooldown.items(), key=repr))

    # ---------- 自动分配 ----------
    def _ready(self, c):
        return (c.is_idle() and c.build_lock is None and c.combat_lock is None and c.carrying is None
                and c.rest > MIN_REST and c.satiety > MIN_SATIETY and c.hp >= MIN_HP)

    def update(self, g):
        tick = g.game_time.tick
        if tick % CHECK_EVERY != 0:
            return
        if self.cooldown:
            self.cooldown = {k: t for k, t in self.cooldown.items() if t > tick}
        if not self.tiles["harvest"] and not self.tiles["hunt"]:
            return
        for c in g.colonists:                       # g.colonists 顺序固定
            if not self._ready(c):
                continue
            if self.tiles["harvest"] and self._try_harvest(g, c, tick):
                continue
            if self.tiles["hunt"]:
                self._try_hunt(g, c, tick)

    def _try_harvest(self, g, c, tick):
        cx, cy = c.current_tile()
        res = g.ctx.reserved_harvests
        cands = []
        for (tx, ty) in self.tiles["harvest"]:
            if (tx, ty) in res or ("harvest", (tx, ty)) in self.cooldown:
                continue
            if not g.world.is_harvestable(tx, ty):
                continue
            cands.append((abs(tx - cx) + abs(ty - cy), tx, ty))
        if not cands:
            return False
        cands.sort()
        for _, tx, ty in cands[:MAX_TRIES]:
            if c.assign_harvest(g.world, tx, ty):
                return True
            self.cooldown[("harvest", (tx, ty))] = tick + FAIL_COOLDOWN
        return False

    def _try_hunt(self, g, c, tick):
        if c.weapon_key == "fist":
            return False
        zone = self.tiles["hunt"]
        taken = {o.target_animal.id for o in g.colonists if o.target_animal is not None}
        cx, cy = c.current_tile()
        cands = []
        for a in g.animals:
            if a.hp <= 0 or a.id in taken or ("hunt", a.id) in self.cooldown:
                continue
            at = a.current_tile()
            if at in zone:
                cands.append((abs(at[0] - cx) + abs(at[1] - cy), a.id, a))
        if not cands:
            return False
        cands.sort(key=lambda t: (t[0], t[1]))
        a = cands[0][2]
        c.assign_hunt(a)
        self.cooldown[("hunt", a.id)] = tick + 120      # 短冷却：别让所有人扎堆追同一只
        return True
