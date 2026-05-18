import copy
import time
from typing import Dict, List, Tuple

import numpy as np

from optimization.loaders.distance_loader import get_distance
from optimization.models.route import PolygonResults, RoutingDict
from optimization.preprocessing.matrices import create_distance_matrix_no_return
from optimization.config.config import Config
from optimization.solvers.tsp.registry import solve_polish_tsp
from optimization.utils.logger import get_logger

logger = get_logger(__name__)


def calculate_total_distance(
    route: List[int],
    distance_array: np.ndarray,
    idx_dict: dict,
    order_to_mpid: Dict[int, int],
) -> Tuple[int, int, Dict[int, int]]:
    travelling_time = 0
    polygonal_travelling_dict: Dict[int, int] = {}

    for point in route[1:]:
        poly = order_to_mpid[point]
        if poly != 0 and poly not in polygonal_travelling_dict:
            polygonal_travelling_dict[poly] = 0

    previous_point = route[0]
    prev_polygon = 0
    visited_polygons_in_order: List[int] = []

    for current_point in route[1:]:
        current_polygon = order_to_mpid[current_point]
        if current_polygon != 0 and current_polygon != prev_polygon:
            if current_polygon in visited_polygons_in_order:
                logger.warning("Polygon %s visited twice", current_polygon)
            else:
                visited_polygons_in_order.append(current_polygon)

        distance = get_distance(distance_array, idx_dict, previous_point, current_point)
        if current_polygon != prev_polygon:
            travelling_time += distance
        else:
            polygonal_travelling_dict[current_polygon] += distance

        previous_point = current_point
        prev_polygon = current_polygon

    total_distance = travelling_time + sum(polygonal_travelling_dict.values())
    return total_distance, travelling_time, polygonal_travelling_dict


def polish_courier_routes(
    solution: RoutingDict,
    each_polygon_opt_route: PolygonResults,
    distance_array: np.ndarray,
    idx_dict: dict,
    poly_mapping: Dict[int, int],
    order_to_mpid: Dict[int, int],
    config: Config | None = None,
) -> Tuple[RoutingDict, PolygonResults]:
    config = config or Config()
    final_solution = copy.deepcopy(solution)
    final_polygon_routes = copy.deepcopy(each_polygon_opt_route)
    start = time.time()

    for courier_id, data in final_solution.items():
        if data["New route"] == [0]:
            continue

        original_route = [0] + [
            node
            for poly in data["New route"]
            if poly != 0
            for node in each_polygon_opt_route[poly]["route"]
        ]

        matrix = create_distance_matrix_no_return(
            original_route, distance_array, idx_dict, poly_mapping
        )
        tsp = solve_polish_tsp(
            original_route,
            np.array(matrix),
            config=config,
            fallback=config.polish_tsp_fallback_to_christofides,
        )
        polished_route = tsp.route

        total_distance, travelling_time, polygonal_travelling_dict = calculate_total_distance(
            polished_route, distance_array, idx_dict, order_to_mpid
        )

        budget = data["Total time"] - data["Polygonal service"]
        if total_distance > budget:
            continue

        current_polygon = None
        current_route: List[int] = []
        for point in polished_route[1:]:
            point_polygon = order_to_mpid[point]
            if point_polygon != current_polygon:
                if current_polygon is not None:
                    final_polygon_routes[current_polygon].update(
                        {
                            "route": current_route,
                            "start_point": current_route[0],
                            "end_point": current_route[-1],
                            "total_distance": polygonal_travelling_dict.get(current_polygon, 0),
                        }
                    )
                current_polygon = point_polygon
                current_route = [point]
            else:
                current_route.append(point)

        if current_polygon is not None:
            final_polygon_routes[current_polygon].update(
                {
                    "route": current_route,
                    "start_point": current_route[0],
                    "end_point": current_route[-1],
                    "total_distance": polygonal_travelling_dict.get(current_polygon, 0),
                }
            )

        polygonal_travelling_total = sum(polygonal_travelling_dict.values())
        data.update(
            {
                "Travelling time": np.int32(travelling_time),
                "Polygonal travelling": polygonal_travelling_total,
                "Total time": travelling_time + data["Polygonal service"] + polygonal_travelling_total,
            }
        )

    logger.info("Local polish finished in %.2f s", time.time() - start)
    return final_solution, final_polygon_routes
