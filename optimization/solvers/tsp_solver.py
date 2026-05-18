"""Deprecated facade — import from optimization.solvers.tsp instead."""

from optimization.solvers.tsp.christofides_inner import solve_christofides_inner
from optimization.solvers.tsp.christofides_outer import solve_christofides_outer
from optimization.solvers.tsp.registry import solve_inner_tsp, solve_outer_tsp, solve_polish_tsp


def solve_tsp_christofides_inner(points, matrix_to_solve):
    sol = solve_christofides_inner(points, matrix_to_solve)
    return sol.route, sol.distance


def solve_tsp_christofides_outer(points, cross_mem, polygon_to_index, warehouse_point=0):
    sol = solve_christofides_outer(points, cross_mem, polygon_to_index)
    return sol.route, sol.distance
