from collections import defaultdict
from typing import Dict, List, Tuple

import numpy as np

from optimization.config.config import Config
from optimization.loaders.distance_loader import get_distance
from optimization.models.route import PolygonResults, RoutingDict
from optimization.preprocessing.matrices import create_distance_matrix_no_return, get_depot_point
from optimization.solvers.tsp.registry import solve_inner_tsp
from optimization.utils.logger import get_logger

logger = get_logger(__name__)


def init_routing_state(courier_ids: List[int]) -> RoutingDict:
    routing: RoutingDict = {}
    for courier_id in courier_ids:
        routing[courier_id] = {
            "New route": [0],
            "Travelling time": 0,
            "Polygonal service": 0,
            "Polygonal travelling": 0,
            "Total time": 0,
            "Total orders": 0,
            "last EP": 0,
        }
    return routing


def assign_polygon_to_courier(
    polygon: int,
    mpids_dict: Dict[int, List[int]],
    routing_dict: RoutingDict,
    each_polygon_opt_route: PolygonResults,
    new_couriers_dict: Dict[int, Dict[int, int]],
    unassigned_couriers: List[int],
    unassigned_polygons: List[int],
    distance_array: np.ndarray,
    idx_dict: dict,
    config: Config,
) -> Tuple[int, int]:
    polygon_orders = mpids_dict[polygon]
    order_count = len(polygon_orders)
    logger.info("Polygon %s: %s orders", polygon, order_count)

    preliminary_couriers = []
    for courier_id in unassigned_couriers:
        prev_point = routing_dict[courier_id]["last EP"]
        depot_idx = get_depot_point(polygon_orders, prev_point, distance_array, idx_dict)
        polygon_first_point = polygon_orders[depot_idx]
        service_time = order_count * new_couriers_dict[courier_id][polygon]
        travel_time_to_first = get_distance(
            distance_array, idx_dict, prev_point, polygon_first_point
        )
        polygon_tc = routing_dict[courier_id]["Total time"] + service_time + travel_time_to_first

        if polygon_tc <= config.max_courier_time_sec:
            preliminary_couriers.append((courier_id, polygon_tc, service_time, prev_point))

    if not preliminary_couriers:
        unassigned_polygons.remove(polygon)
        penalty = order_count * config.penalty_per_order_sec
        logger.warning("Polygon %s: no courier, penalty %s", polygon, penalty)
        return penalty, 0

    preliminary_couriers.sort(key=lambda x: x[1])
    top_candidates = preliminary_couriers[: config.top_courier_candidates]

    suitable_couriers = []
    for courier_id, _, service_time, prev_point in top_candidates:
        points = [prev_point] + polygon_orders
        matrix = create_distance_matrix_no_return(points, distance_array, idx_dict)
        tsp = solve_inner_tsp(
            points,
            matrix,
            config=config,
            fallback=config.inner_tsp_fallback_to_christofides,
        )
        best_route, travel_inside_total = tsp.route, tsp.distance

        travel_time_to_first = get_distance(
            distance_array, idx_dict, prev_point, best_route[1]
        )
        travel_time_inside = travel_inside_total - travel_time_to_first
        total_polygon_time_real = travel_time_to_first + travel_time_inside + service_time

        if routing_dict[courier_id]["Total time"] + total_polygon_time_real <= config.max_courier_time_sec:
            suitable_couriers.append(
                (
                    courier_id,
                    service_time,
                    travel_time_to_first,
                    travel_time_inside,
                    total_polygon_time_real,
                    best_route,
                )
            )

    if not suitable_couriers:
        unassigned_polygons.remove(polygon)
        penalty = order_count * config.penalty_per_order_sec
        logger.warning("Polygon %s: TSP exceeded limit, penalty %s", polygon, penalty)
        return penalty, 0

    (
        best_courier_id,
        best_service_time,
        best_polygonal_travelling,
        travel_time_inside,
        total_polygon_time,
        best_route,
    ) = min(suitable_couriers, key=lambda x: x[4])

    max_polygon_time = order_count * config.penalty_per_order_sec
    if total_polygon_time <= max_polygon_time:
        each_polygon_opt_route[polygon] = {
            "start_point": best_route[1],
            "end_point": best_route[-1],
            "total_distance": travel_time_inside,
            "route": best_route[1:],
        }
        routing_dict[best_courier_id]["New route"].append(polygon)
        routing_dict[best_courier_id]["Travelling time"] += best_polygonal_travelling
        routing_dict[best_courier_id]["Polygonal service"] += best_service_time
        routing_dict[best_courier_id]["Polygonal travelling"] += travel_time_inside
        routing_dict[best_courier_id]["Total time"] += total_polygon_time
        routing_dict[best_courier_id]["Total orders"] += order_count
        routing_dict[best_courier_id]["last EP"] = best_route[-1]
        unassigned_polygons.remove(polygon)
        logger.info(
            "Polygon %s assigned to courier %s (time %s)",
            polygon,
            best_courier_id,
            total_polygon_time,
        )
        return int(total_polygon_time), best_courier_id

    unassigned_polygons.remove(polygon)
    penalty = order_count * config.penalty_per_order_sec
    logger.warning("Polygon %s: exceeded max polygon time, penalty %s", polygon, penalty)
    return penalty, 0


def assign_polygons_to_couriers(
    mpids_dict: Dict[int, List[int]],
    mpids_list: List[int],
    routing_dict: RoutingDict,
    each_polygon_opt_route: PolygonResults,
    new_couriers_dict: Dict[int, Dict[int, int]],
    all_courier_ids: List[int],
    distance_array: np.ndarray,
    idx_dict: dict,
    config: Config,
) -> int:
    unassigned_polygons = list(mpids_list)
    total_time = 0

    for polygon in list(unassigned_polygons):
        if polygon == config.warehouse_point:
            continue
        ttime, _ = assign_polygon_to_courier(
            polygon=polygon,
            mpids_dict=mpids_dict,
            routing_dict=routing_dict,
            each_polygon_opt_route=each_polygon_opt_route,
            new_couriers_dict=new_couriers_dict,
            unassigned_couriers=all_courier_ids,
            unassigned_polygons=unassigned_polygons,
            distance_array=distance_array,
            idx_dict=idx_dict,
            config=config,
        )
        total_time += ttime

    return total_time
