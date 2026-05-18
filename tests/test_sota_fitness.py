from optimization.SOTA.context import SotaContext
from optimization.SOTA.fitness import FitnessEvaluator


def test_fitness_evaluator_route_time():
    cross = __import__("numpy").zeros((3, 3), dtype=int)
    cross[0, 1], cross[1, 2], cross[0, 2] = 10, 20, 25

    ctx = SotaContext(
        mpids_dict={1: [101, 102], 2: [201]},
        mpids_list=[0, 1, 2],
        all_courier_ids=[1],
        new_couriers_dict={1: {1: 5, 2: 3}},
        each_polygon_opt_route={
            1: {"total_distance": 100, "route": [101, 102]},
            2: {"total_distance": 50, "route": [201]},
        },
        cross_mem=cross,
        polygon_to_index={0: 0, 1: 1, 2: 2},
        polygon_available_couriers={1: [1], 2: [1]},
        polygons_to_assign=[1, 2],
    )
    ev = FitnessEvaluator(ctx)
    t = ev.route_list_time([0, 1, 2], courier_id=1)
    assert t == 10 + 20 + 100 + 50 + (5 * 2 + 3 * 1)
