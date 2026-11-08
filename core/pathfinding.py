# core/pathfinding.py
import heapq


def astar(world, start, goal, max_iter=500, debug=False):
    sx, sy = start
    gx, gy = goal

    if start == goal: return []
    if not world.is_walkable(sx, sy): return None
    if not world.is_walkable(gx, gy): return None

    dirs = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
            (-1, -1, 1.414), (-1, 1, 1.414), (1, -1, 1.414), (1, 1, 1.414)]

    def heuristic(a, b):
        return max(abs(a[0] - b[0]), abs(a[1] - b[1]))

    counter = 0
    open_heap = [(heuristic(start, goal), 0, counter, start)]
    came_from = {}
    g_score = {start: 0.0}
    closed = set()
    iters = 0

    while open_heap:
        iters += 1
        if iters > max_iter: return None

        _, g, _, current = heapq.heappop(open_heap)

        if current in closed: continue
        closed.add(current)

        if current == goal:
            path = []
            while current in came_from:
                path.append(current)
                current = came_from[current]
            path.reverse()
            return path

        cx, cy = current
        for dx, dy, cost in dirs:
            nx, ny = cx + dx, cy + dy
            neighbor = (nx, ny)
            if not world.is_walkable(nx, ny): continue

            if dx != 0 and dy != 0:
                if not (world.is_walkable(cx + dx, cy) and world.is_walkable(cx, cy + dy)): continue

            tentative = g + cost
            if tentative < g_score.get(neighbor, 1e18):
                g_score[neighbor] = tentative
                came_from[neighbor] = current
                counter += 1
                f = tentative + heuristic(neighbor, goal)
                heapq.heappush(open_heap, (f, tentative, counter, neighbor))

    return None