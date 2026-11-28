# systems/quests.py
"""支线任务系统（v0.13.0）。

全部是确定性模拟状态：只用 world.rng，只在固定 tick 评估，所有字段都是内置类型，参与状态哈希。
任务分两类：
  · 任务链（CHAINS）：一环扣一环的故事线，到了指定天数自动开启，做完一步给下一步；
  · 随机任务：每隔一段时间从任务池里抽一个，按当前天数调整难度。
进度类型：
  have        — 全图该物品总数 ≥ 目标（收集；不消耗物品）
  kill_animal — 开始后猎杀的动物数
  kill_enemy  — 开始后击杀的敌人数
  build       — 已建成的该建筑数量 ≥ 目标
  research    — 开始后完成的研究项数
  survive     — 到达第 N 天
"""

MAX_RANDOM = 2          # 同时存在的随机任务上限（任务链任务另算）
FIRST_DELAY_SEC = 40.0  # 开局后多久出现第一个任务

# 任务链：(链名, 开启所需天数, [步骤…])；步骤 = (类型, 键, 目标, 奖励{物品:数量}, 标题)
CHAINS = [
    ("拓荒者", 1, [
        ("have", "wood", 40, {"stone": 15}, "备料：囤够木头"),
        ("build", "bed", 2, {"wood": 25}, "安家：建 2 张床"),
        ("have", "stone", 40, {"leather": 3}, "采石：囤够石头"),
        ("research", None, 1, {"bow": 1}, "求知：完成 1 项研究"),
    ]),
    ("猎人之路", 2, [
        ("kill_animal", None, 3, {"leather": 2}, "初猎：猎杀 3 只动物"),
        ("kill_animal", None, 6, {"bow": 1}, "熟练：再猎杀 6 只动物"),
        ("kill_animal", None, 10, {"crossbow": 1}, "猎王：再猎杀 10 只动物"),
    ]),
    ("匠人之心", 3, [
        ("build", "floor", 10, {"wood": 20}, "铺地：建 10 块地板"),
        ("build", "flower_pot", 2, {"wool": 4}, "点缀：摆 2 个花盆"),
        ("build", "bookshelf", 2, {"feather": 6}, "藏书：建 2 个书架"),
        ("build", "fountain", 1, {"iron": 10}, "盛景：建 1 座喷泉（需研究石工）"),
    ]),
    ("守卫者", 4, [
        ("kill_enemy", None, 3, {"iron": 6}, "迎击：击退 3 个入侵者"),
        ("kill_enemy", None, 8, {"rifle": 1}, "防线：再击退 8 个入侵者"),
        ("kill_enemy", None, 15, {"smg": 1}, "铁壁：再击退 15 个入侵者"),
    ]),
]

# 随机任务模板：(类型, 键, 基础目标, 每天增量, 奖励物品, 奖励基础量)
_POOL = [
    ("have", "wood", 30, 6, "iron_ore", 3),
    ("have", "stone", 30, 6, "wood", 20),
    ("have", "meat", 8, 2, "leather", 3),
    ("have", "food", 12, 2, "wood", 15),
    ("have", "iron", 6, 2, "stone", 25),
    ("have", "leather", 4, 1, "iron", 3),
    ("have", "meal_simple", 4, 1, "meat", 6),
    ("kill_animal", None, 2, 0.5, "leather", 3),
    ("kill_enemy", None, 2, 0.5, "iron", 4),
    ("survive", None, 2, 0, "wood", 25),
    ("build", "bed", 1, 0, "feather", 4),
]
_NAMES = {"wood": "木头", "stone": "石头", "meat": "生肉", "food": "浆果", "iron": "铁", "leather": "皮革",
          "meal_simple": "简单食物", "iron_ore": "粗铁", "bed": "床", "floor": "地板", "flower_pot": "花盆",
          "bookshelf": "书架", "fountain": "喷泉"}


def _name(k):
    return _NAMES.get(k, k)


class QuestManager:
    def __init__(self, day_length_sec=120.0):
        self.active = []                    # 任务字典列表
        self.next_id = 1
        self.done = 0
        self.animals_killed = 0
        self.enemies_killed = 0
        self.timer = FIRST_DELAY_SEC
        self.chain_next = [0] * len(CHAINS)  # 每条链下一步的序号
        self.chain_on = [False] * len(CHAINS)
        self.day_length = day_length_sec
        self.completed_titles = []          # 只保留最近几条，给界面看

    # ---- 状态摘要（进哈希） ----
    def snapshot(self):
        return (self.next_id, self.done, self.animals_killed, self.enemies_killed, round(self.timer, 3),
                tuple(self.chain_next), tuple(self.chain_on),
                tuple((q["id"], q["type"], q["key"], q["target"], q["base"], tuple(sorted(q["reward"].items())),
                       q["chain"]) for q in self.active))

    # ---- 进度 ----
    @staticmethod
    def _count_buildings(g, kind):
        seen = set()
        for b in g.buildings.buildings.values():
            if b.kind == kind:
                seen.add((b.tx, b.ty, b.layer))
        return len(seen)

    def progress(self, q, g, cache):
        t = q["type"]
        if t == "have":
            if "items" not in cache:
                tot = {}
                for st in g.items.stacks.values():
                    tot[st.kind] = tot.get(st.kind, 0) + st.amount
                cache["items"] = tot
            return min(q["target"], cache["items"].get(q["key"], 0))
        if t == "kill_animal":
            return min(q["target"], self.animals_killed - q["base"])
        if t == "kill_enemy":
            return min(q["target"], self.enemies_killed - q["base"])
        if t == "build":
            return min(q["target"], self._count_buildings(g, q["key"]))
        if t == "research":
            return min(q["target"], len(g.research_mgr.completed) - q["base"])
        if t == "survive":
            return min(q["target"], g.game_time.day)
        return 0

    # ---- 创建 ----
    def _new(self, g, typ, key, target, reward, title, chain=-1, step=0):
        base = 0
        if typ == "kill_animal": base = self.animals_killed
        elif typ == "kill_enemy": base = self.enemies_killed
        elif typ == "research": base = len(g.research_mgr.completed)
        q = {"id": self.next_id, "type": typ, "key": key, "target": int(target), "base": base,
             "reward": dict(reward), "title": title, "chain": chain, "step": step}
        self.next_id += 1
        self.active.append(q)
        g.log.add(f"新支线任务：{title}", (255, 220, 100))
        g.toast(f"新支线任务：{title}（Q 查看）", 3.0)
        return q

    def _chain_step(self, g, ci):
        name, _, steps = CHAINS[ci]
        i = self.chain_next[ci]
        if i >= len(steps): return
        typ, key, target, reward, title = steps[i]
        self._new(g, typ, key, target, reward, f"【{name}】{title}", chain=ci, step=i)

    def _random(self, g):
        day = g.game_time.day
        have_keys = {(q["type"], q["key"]) for q in self.active}
        pool = [p for p in _POOL if (p[0], p[1]) not in have_keys
                and not (p[0] == "kill_enemy" and day < 3)
                and not (p[0] == "survive" and any(q["type"] == "survive" for q in self.active))]
        if not pool: return
        typ, key, base, inc, rkind, ramt = pool[g.rng.randrange(len(pool))]
        target = int(base + inc * (day - 1))
        if typ == "build":
            target = self._count_buildings(g, key) + 1
        elif typ == "survive":
            target = day + 2
        scale = 1.0 + 0.15 * (day - 1)
        amt = max(1, int(ramt * scale))
        if typ == "have":
            title = f"收集 {target} 个{_name(key)}"
        elif typ == "kill_animal":
            title = f"猎杀 {target} 只动物"
        elif typ == "kill_enemy":
            title = f"击退 {target} 个入侵者"
        elif typ == "survive":
            title = f"撑到第 {target} 天"
        else:
            title = f"建成 {target} 个{_name(key)}"
        self._new(g, typ, key, target, {rkind: amt}, title)

    # ---- 每 tick 调用（内部节流） ----
    def update(self, g):
        tick = g.game_time.tick
        if tick % 30 != 0:
            return
        dt = 0.5
        day = g.game_time.day
        # 任务链开启
        for ci, (name, day_req, steps) in enumerate(CHAINS):
            if not self.chain_on[ci] and day >= day_req and g.game_time.elapsed >= FIRST_DELAY_SEC * 0.5:
                self.chain_on[ci] = True
                self._chain_step(g, ci)
        # 随机任务
        self.timer -= dt
        if self.timer <= 0:
            self.timer = self.day_length * (0.6 + 0.4 * g.rng.random())
            if sum(1 for q in self.active if q["chain"] < 0) < MAX_RANDOM and g.game_time.elapsed >= FIRST_DELAY_SEC:
                self._random(g)
        # 完成判定
        cache = {}
        for q in list(self.active):
            if self.progress(q, g, cache) >= q["target"]:
                self._finish(g, q)
                cache = {}

    def _finish(self, g, q):
        self.active.remove(q)
        self.done += 1
        self._give(g, q["reward"])
        rtxt = "、".join(f"{_name_item(k)}×{v}" for k, v in q["reward"].items())
        g.log.add(f"任务完成：{q['title']}  奖励：{rtxt}", (120, 255, 140))
        g.warning_text = f"任务完成：{q['title']}  奖励：{rtxt}"
        g.warning_timer = 3.5
        self.completed_titles.append(q["title"])
        del self.completed_titles[:-5]
        if q["chain"] >= 0:
            self.chain_next[q["chain"]] = q["step"] + 1
            self._chain_step(g, q["chain"])

    def _give(self, g, reward):
        """奖励掉在第一个小人脚下，由搬运工自行入库。"""
        if not g.colonists: return
        tx, ty = g.colonists[0].current_tile()
        for k, v in reward.items():
            g.items.add(k, v, tx, ty)


def _name_item(k):
    from world.items import ITEM_DEFS
    return ITEM_DEFS.get(k, {"name": k})["name"]
