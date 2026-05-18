def test_package_imports():
    from optimization.config.config import Config
    from optimization.loaders.distance_loader import get_distance
    from optimization.solvers.tsp_solver import solve_tsp_christofides_inner

    cfg = Config()
    assert cfg.warehouse_point == 0
    assert solve_tsp_christofides_inner([1, 2], [[0, 1], [1, 0]])[1] == 1
