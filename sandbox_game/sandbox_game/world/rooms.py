# world/rooms.py
from world.buildings import BUILDING_DEFS
from collections import deque


class RoomManager:
    def __init__(self, world, buildings):
        self.world = world
        self.buildings = buildings
        self.rooms = {}  # {(tx, ty): room_id}
        self.room_beauty = {}  # {room_id: beauty_value}
        self.room_centers = {}  # {room_id: (center_tx, center_ty)}
        self.update_timer = 0.0

    def update(self, dt):
        self.update_timer += dt
        if self.update_timer >= 2.0:  # 每2秒扫描一次
            self.update_timer = 0.0
            self._recalculate()

    def _recalculate(self):
        self.rooms.clear()
        self.room_beauty.clear()
        self.room_centers.clear()
        rows, cols = self.world.rows, self.world.cols
        visited = set()
        room_id_counter = 1

        for y in range(rows):
            for x in range(cols):
                if (x, y) in visited: continue
                # 从没有建筑阻挡的地面开始
                b = self.buildings.get_building_at(x, y)
                if not b and self.world.is_terrain_walkable(x, y):
                    room_tiles = []
                    is_enclosed = self._flood_fill(x, y, visited, room_tiles)
                    if is_enclosed and room_tiles:
                        # 检查房间内是否铺了足够的地板（如果没有地板，就不显示）
                        floor_count = sum(1 for rx, ry in room_tiles if
                                          self.buildings.get_building_at(rx, ry) and self.buildings.get_building_at(rx,
                                                                                                                    ry).kind == "floor")

                        # 至少要有 60% 的地方铺了地板，才算有效房间
                        if floor_count < len(room_tiles) * 0.6:
                            continue

                        beauty = self._calc_beauty(room_tiles)
                        for rx, ry in room_tiles:
                            self.rooms[(rx, ry)] = room_id_counter

                        cx = sum(t[0] for t in room_tiles) // len(room_tiles)
                        cy = sum(t[1] for t in room_tiles) // len(room_tiles)
                        self.room_centers[room_id_counter] = (cx, cy)

                        self.room_beauty[room_id_counter] = beauty
                        room_id_counter += 1

    def _flood_fill(self, start_x, start_y, global_visited, room_tiles):
        q = deque([(start_x, start_y)])
        global_visited.add((start_x, start_y))
        local_visited = set([(start_x, start_y)])

        while q:
            cx, cy = q.popleft()
            room_tiles.append((cx, cy))

            # 碰到地图边缘，一定不是封闭房间
            if cx <= 0 or cy <= 0 or cx >= self.world.cols - 1 or cy >= self.world.rows - 1:
                return False

            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                nx, ny = cx + dx, cy + dy
                if (nx, ny) in local_visited: continue

                b = self.buildings.get_building_at(nx, ny)
                if b:
                    if b.kind in ("wall", "window", "door"):
                        continue  # 是墙/门/窗，挡住探索（视为边界）
                    elif not BUILDING_DEFS[b.kind]["walkable"]:
                        return False  # 遇到其他家具（如炉子），说明这里漏风，不是封闭房间
                else:
                    if not self.world.is_terrain_walkable(nx, ny):
                        return False  # 遇到山、水、树，说明是大自然，不算玩家居住区

                if (nx, ny) not in global_visited:
                    global_visited.add((nx, ny))
                    local_visited.add((nx, ny))
                    q.append((nx, ny))

        return True

    def _calc_beauty(self, tiles):
        score = 0
        for tx, ty in tiles:
            b = self.buildings.get_building_at(tx, ty)
            if b and b.kind == "floor":
                if b.material == "wood":
                    score += 2
                elif b.material == "stone":
                    score += 5
        return int(score / max(1, len(tiles)) * 10) if tiles else 0

    def get_beauty_at(self, tx, ty):
        rid = self.rooms.get((tx, ty))
        return self.room_beauty.get(rid, 0) if rid is not None else 0