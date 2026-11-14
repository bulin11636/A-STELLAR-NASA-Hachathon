"""Bounded deterministic A* on a rectangular metric grid. No geospatial imports."""
import heapq
import math
import time
from dataclasses import dataclass
import numpy as np
from app.api.errors import ApiProblem


@dataclass(frozen=True)
class SearchResult:
    cells: list[tuple[int, int]]
    cost: float
    expanded: int
    elapsed_ms: float


class SearchProblem(ApiProblem):
    """Retain consumed work so a wider retry shares the original search budget."""
    def __init__(self,status,code,message,expanded,elapsed_ms):
        super().__init__(status,code,message)
        self.expanded_nodes = expanded
        self.elapsed_ms = elapsed_ms


def astar(allowed, penalty, start, goal, dx, dy, max_nodes=200000, max_seconds=5.0):
    started = time.monotonic()
    if dx <= 0 or dy <= 0 or not np.isfinite([dx, dy]).all():
        raise ValueError('Positive finite metric spacing required')
    if penalty.shape != allowed.shape or not np.isfinite(penalty).all() or np.any(penalty < 1):
        raise ValueError('Finite penalties >= 1 required')
    h, w = allowed.shape
    for r, c in (start, goal):
        if not (0 <= r < h and 0 <= c < w and allowed[r, c]):
            raise ApiProblem(400, 'ENDPOINT_NOT_TRAVERSABLE', 'An endpoint is blocked or unknown.')
    def heuristic(cell):
        return math.hypot((cell[1]-goal[1])*dx, (cell[0]-goal[0])*dy)
    costs = {start: 0.0}
    parents = {}
    queue = [(heuristic(start), 0.0, start)]
    expanded = 0
    while queue:
        if expanded >= max_nodes or time.monotonic()-started > max_seconds:
            raise SearchProblem(503, 'PLANNING_LIMIT_EXCEEDED', 'The bounded search exhausted its node or time limit.',expanded,(time.monotonic()-started)*1000)
        _, cost, cell = heapq.heappop(queue)
        if cost != costs[cell]:
            continue
        expanded += 1
        if cell == goal:
            cells = [cell]
            while cell in parents:
                cell = parents[cell]
                cells.append(cell)
            return SearchResult(cells[::-1], cost, expanded, (time.monotonic()-started)*1000)
        r, c = cell
        for dr, dc in ((-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)):
            nr, nc = r+dr, c+dc
            if not (0 <= nr < h and 0 <= nc < w and allowed[nr,nc]):
                continue
            if dr and dc and not (allowed[r,nc] and allowed[nr,c]):
                continue
            nxt = nr, nc
            value = cost + math.hypot(dc*dx, dr*dy)*(penalty[cell]+penalty[nxt])/2
            if value < costs.get(nxt, math.inf):
                costs[nxt] = value
                parents[nxt] = cell
                heapq.heappush(queue, (value+heuristic(nxt), value, nxt))
    raise SearchProblem(422, 'NO_PATH', 'No connected route exists under the configured terrain policy.',expanded,(time.monotonic()-started)*1000)
