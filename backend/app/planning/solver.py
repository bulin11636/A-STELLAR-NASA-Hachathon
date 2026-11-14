"""Solve ordered route legs under one explicit search budget."""
from dataclasses import dataclass
from time import monotonic
from types import SimpleNamespace

import numpy as np

from app.planning.search import astar, SearchProblem
from app.planning.validation import validate_polyline


@dataclass
class RouteSolution:
    points: list
    route: list
    search: SimpleNamespace
    distance: float
    touched: list


def solve_route(grid, request, max_nodes, max_seconds):
    penalty = grid.arrays()[request.mode+'_cost']
    dx,dy = grid.metadata.planning_resolution_m
    stops = [request.start,*request.waypoints,request.goal]
    points,route,cells = [],[],[]
    started = monotonic()
    objective,expanded,elapsed = 0.0,0,0.0
    allowed = grid.allowed
    for first,last in zip(stops,stops[1:]):
        start,goal = grid.cell(first),grid.cell(last)
        remaining = max_seconds-(monotonic()-started)
        if remaining <= 0 or expanded >= max_nodes:
            raise SearchProblem(503,'PLANNING_LIMIT_EXCEEDED','The ordered route exhausted its shared search budget.',expanded,(monotonic()-started)*1000)
        try:
            leg = astar(allowed,penalty,start,goal,dx,dy,max_nodes-expanded,remaining)
        except SearchProblem as error:
            error.expanded_nodes += expanded
            error.elapsed_ms += elapsed
            raise
        local = [grid.xy(first),*(grid.center(cell) for cell in leg.cells),grid.xy(last)] if start != goal else [grid.xy(first),grid.xy(last)]
        leg_distance,_ = validate_polyline(grid,local,grid.source_hash)
        connectors = sum(np.linalg.norm(np.subtract(a,b))*penalty[cell] for a,b,cell in
            [(local[0],local[1],start),(local[-2],local[-1],goal)]) if start != goal else leg_distance*penalty[start]
        objective += leg.cost+connectors if start != goal else connectors
        expanded += leg.expanded
        elapsed += leg.elapsed_ms
        wire = [first,*(grid.wire(*xy) for xy in local[1:-1]),last]
        points.extend(local if not points else local[1:])
        route.extend(wire if not route else wire[1:])
        cells.extend(leg.cells if not cells else leg.cells[1:])
    distance,touched = validate_polyline(grid,points,grid.source_hash)
    emitted_distance,_ = validate_polyline(grid,[grid.xy(p) for p in route],grid.source_hash)
    if abs(distance-emitted_distance) > 1e-5:
        raise ValueError('Wire transform changed route length')
    return RouteSolution(points,route,SimpleNamespace(cells=cells,cost=objective,expanded=expanded,elapsed_ms=elapsed),distance,touched)
