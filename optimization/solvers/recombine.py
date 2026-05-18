from typing import List

from optimization.models.route import RoutingDict
from optimization.config.config import Config
from optimization.solvers.tsp.registry import solve_outer_tsp


def recombine_all_routes(
    routes: RoutingDict,
    all_courier_ids: List[int],
    cross_mem,
    polygon_to_index: dict,
    warehouse_point: int = 0,
    config: Config | None = None,
) -> RoutingDict:
    config = config or Config()
    new_routing: RoutingDict = {}

    for courier in all_courier_ids:
        current_data = routes[courier]
        current_route = current_data["New route"]

        if len(current_route) <= 2:
            new_route = current_route.copy()
            interpolygonal_distance = current_data["Travelling time"]
        else:
            outer = solve_outer_tsp(current_route, cross_mem, polygon_to_index, config=config)
            new_route, interpolygonal_distance = outer.route, outer.distance

        total_service_time = current_data["Polygonal service"]
        total_inner_distances = current_data["Polygonal travelling"]
        total_orders = current_data["Total orders"]
        new_total_time = int(
            total_service_time + interpolygonal_distance + total_inner_distances
        )

        new_routing[courier] = {
            "New route": new_route,
            "Travelling time": interpolygonal_distance,
            "Polygonal service": total_service_time,
            "Polygonal travelling": total_inner_distances,
            "Total time": new_total_time,
            "Total orders": int(total_orders),
            "Avg service time": round(
                (new_total_time / total_orders if total_orders > 0 else 0), 2
            ),
        }

    return new_routing
