import pytest

from optimization.config.config import Config
from optimization.solvers.tsp.base import InnerTspSolverName, normalize_inner_solver
from optimization.solvers.tsp.registry import solve_inner_tsp

MATRIX_3 = [[0, 1, 2], [1, 0, 3], [2, 3, 0]]
POINTS_3 = [10, 20, 30]


def test_normalize_inner_solver_aliases():
    assert normalize_inner_solver("cbc_open") == InnerTspSolverName.BRANCH_AND_CUT
    assert normalize_inner_solver("gurobi_ampl") == InnerTspSolverName.BRANCH_AND_CUT_GUROBI


@pytest.mark.parametrize(
    "solver_name",
    [InnerTspSolverName.CHRISTOFIDES, InnerTspSolverName.BRANCH_AND_CUT],
)
def test_inner_tsp_small(solver_name):
    cfg = Config(inner_tsp_solver=solver_name.value, inner_tsp_fallback_to_christofides=False)
    sol = solve_inner_tsp(POINTS_3, MATRIX_3, config=cfg, solver=solver_name, fallback=False)
    assert len(sol.route) == 3
    assert sol.distance > 0


def test_christofides_legacy_facade():
    from optimization.solvers.tsp_solver import solve_tsp_christofides_inner

    route, dist = solve_tsp_christofides_inner([1, 2], [[0, 1], [1, 0]])
    assert dist == 1
    assert route == [1, 2]
