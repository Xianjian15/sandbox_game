# core/sim_context.py
"""模拟上下文：一局游戏里所有"必须两端一致"的共享状态都放在这里。

原来这些东西散落在各个类的类变量里（Colonist._id_counter、_reserved_harvests ……）。
类变量是进程级全局的：重开一局、断线重连、同一进程里跑两个世界做对拍测试时都不会重置，
会直接造成分叉。现在统一挂在 SimContext 实例上，每个 GameWorld 一份。
"""
import random


class SimContext:
    def __init__(self, seed):
        self.seed = seed
        self.rng = random.Random(seed)      # 世界级随机流（生成、刷怪等）
        self._next_id = 0
        self._seq = {}

        # 由 GameWorld 在创建各管理器时填入
        self.items = None
        self.buildings = None
        self.room_mgr = None

        # 原 Colonist 的类级集合
        self.reserved_harvests = set()      # 已被某个小人占用的采集格
        self.designated_harvests = set()    # 玩家框选的指定采集区
        self.sfx_hook = None                # 纯显示：GameWorld 接上后，模拟里发生的事可以发声（不进哈希、不影响模拟）

    def sound(self, name, x, y):
        """在世界坐标 (x, y) 发声。没接音频（测试/联机无头）时什么都不做。"""
        if self.sfx_hook is not None:
            self.sfx_hook(name, x, y)

    def next_id(self):
        """全局唯一实体 id：小人、敌人、动物共用一个命名空间，
        这样以后指令里写 id 不会有歧义。"""
        self._next_id += 1
        return self._next_id

    def next_seq(self, kind):
        """按种类的显示序号（敌人1、敌人2……），只用于名字，不参与逻辑。"""
        self._seq[kind] = self._seq.get(kind, 0) + 1
        return self._seq[kind]

    def snapshot(self):
        """供状态哈希使用：id 计数、各种序号、随机流状态、占用集合。"""
        return {
            "next_id": self._next_id,
            "seq": sorted(self._seq.items()),
            "rng": self.rng.getstate(),
            "reserved_harvests": sorted(self.reserved_harvests),
            "designated_harvests": sorted(self.designated_harvests),
        }

    def entity_rng(self, entity_id):
        """实体私有随机流（第 3 步使用）：由 seed 和实体 id 派生，
        新增/删减别处的随机调用不会打乱它的序列。"""
        return random.Random(self.seed * 1000003 + entity_id)
