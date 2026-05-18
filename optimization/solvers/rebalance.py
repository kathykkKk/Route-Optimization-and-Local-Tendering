import copy
import time
from typing import Callable, Dict, List, Optional

import numpy as np

from optimization.config.config import Config
from optimization.models.route import PolygonResults, RoutingDict
from optimization.solvers.rebalancer import OptimizedRebalancer
from optimization.utils.logger import get_logger

logger = get_logger(__name__)


def batch_update_courier_metrics(
    solution: RoutingDict,
    courier_ids: List[int],
    polygon_results: PolygonResults,
    warehouse_point: int,
) -> None:
    for courier_id in courier_ids:
        route = solution[courier_id]["New route"]
        total_orders = sum(
            len(polygon_results[p]["route"])
            for p in route[1:]
            if p in polygon_results and p != warehouse_point
        )
        solution[courier_id]["Total orders"] = total_orders
        solution[courier_id]["Avg service time"] = (
            solution[courier_id]["Total time"] / total_orders if total_orders > 0 else 0
        )


def find_and_execute_swap_fast(
    solution, courier_a, courier_b, polygon_results, new_couriers_dict, max_time, optimizer
):
    route_a = solution[courier_a]["New route"]
    route_b = solution[courier_b]["New route"]
    polygons_a = [p for p in route_a[1:] if p != optimizer.warehouse_point]
    polygons_b = [p for p in route_b[1:] if p != optimizer.warehouse_point]

    if not polygons_a or not polygons_b:
        return 0

    best_delta = 0
    best_swap = None
    routes_to_optimize = []
    couriers_for_routes = []
    swap_candidates = []

    for poly_a in polygons_a[:5]:
        for poly_b in polygons_b[:5]:
            if poly_a == poly_b:
                continue
            new_route_a = [p for p in route_a if p != poly_a]
            if poly_b not in new_route_a:
                new_route_a.append(poly_b)
            else:
                continue

            new_route_b = [p for p in route_b if p != poly_b]
            if poly_a not in new_route_b:
                new_route_b.append(poly_a)
            else:
                continue

            if optimizer.warehouse_point not in new_route_a:
                new_route_a = [optimizer.warehouse_point] + new_route_a
            if optimizer.warehouse_point not in new_route_b:
                new_route_b = [optimizer.warehouse_point] + new_route_b

            routes_to_optimize.extend([new_route_a, new_route_b])
            couriers_for_routes.extend([courier_a, courier_b])
            swap_candidates.append((poly_a, poly_b, new_route_a, new_route_b))

    if not routes_to_optimize:
        return 0

    optimized_routes = []
    optimized_times = []
    for route, courier_id in zip(routes_to_optimize, couriers_for_routes):
        tsp_route, total_time = optimizer.get_cached_tsp_route(route, courier_id)
        optimized_routes.append(tsp_route)
        optimized_times.append(total_time)

    for i, (poly_a, poly_b, _, _) in enumerate(swap_candidates):
        idx_a, idx_b = i * 2, i * 2 + 1
        tsp_a, tsp_b = optimized_routes[idx_a], optimized_routes[idx_b]
        time_a, time_b = optimized_times[idx_a], optimized_times[idx_b]

        if tsp_a is not None and tsp_b is not None and time_a <= max_time and time_b <= max_time:
            original_time_a = solution[courier_a]["Total time"]
            original_time_b = solution[courier_b]["Total time"]
            delta = (original_time_a - time_a) + (original_time_b - time_b)
            if delta > best_delta:
                best_delta = delta
                best_swap = (poly_a, poly_b, tsp_a, tsp_b, time_a, time_b)

    if best_delta > 0 and best_swap:
        _, _, tsp_a, tsp_b, time_a, time_b = best_swap
        solution[courier_a]["New route"] = tsp_a
        solution[courier_b]["New route"] = tsp_b
        solution[courier_a]["Total time"] = time_a
        solution[courier_b]["Total time"] = time_b
        batch_update_courier_metrics(
            solution, [courier_a, courier_b], polygon_results, optimizer.warehouse_point
        )
        return best_delta
    return 0


def perform_optimized_swaps_fast(solution, overloaded, all_couriers, polygon_results, new_couriers_dict, max_time, optimizer):
    swap_count = 0
    checked_pairs = set()
    for over_courier in overloaded[:15]:
        for under_courier in [c for c in all_couriers if c != over_courier][:15]:
            pair_key = tuple(sorted([over_courier, under_courier]))
            if pair_key in checked_pairs:
                continue
            checked_pairs.add(pair_key)
            swap_count += find_and_execute_swap_fast(
                solution, over_courier, under_courier, polygon_results, new_couriers_dict, max_time, optimizer
            )
    return swap_count


def perform_optimized_transfers_fast(solution, overloaded, couriers, max_time, optimizer):
    transfers_made = 0
    overloaded_sorted = sorted(
        overloaded, key=lambda cid: solution[cid]["Avg service time"], reverse=True
    )

    for courier_id in overloaded_sorted:
        route = solution[courier_id]["New route"]
        polygons = [p for p in route[1:] if p != optimizer.warehouse_point]
        if not polygons:
            continue

        sorted_polys = sorted(
            polygons,
            key=lambda p: optimizer.new_couriers_dict[courier_id].get(p, 0),
            reverse=True,
        )
        targets = sorted(
            [cid for cid in couriers if cid != courier_id],
            key=lambda cid: solution[cid]["Total time"],
        )

        for poly_id in sorted_polys:
            best_target = None
            best_delta = 0.0
            original_time_over = solution[courier_id]["Total time"]

            test_routes_over, test_routes_target, target_candidates = [], [], []
            for target_id in targets:
                target_route = solution[target_id]["New route"]
                test_route_over = [r for r in route if r != poly_id]
                test_route_target = target_route + [poly_id]
                if optimizer.warehouse_point not in test_route_over:
                    test_route_over = [optimizer.warehouse_point] + test_route_over
                if optimizer.warehouse_point not in test_route_target:
                    test_route_target = [optimizer.warehouse_point] + test_route_target
                test_routes_over.append(test_route_over)
                test_routes_target.append(test_route_target)
                target_candidates.append(target_id)

            if not test_routes_over:
                continue

            times_over, times_target = [], []
            tsp_routes_over, tsp_routes_target = [], []
            for route_over in test_routes_over:
                tsp_route, t = optimizer.get_cached_tsp_route(route_over, courier_id)
                tsp_routes_over.append(tsp_route)
                times_over.append(t)
            for route_target, target_id in zip(test_routes_target, target_candidates):
                tsp_route, t = optimizer.get_cached_tsp_route(route_target, target_id)
                tsp_routes_target.append(tsp_route)
                times_target.append(t)

            for i, target_id in enumerate(target_candidates):
                if (
                    tsp_routes_over[i] is not None
                    and tsp_routes_target[i] is not None
                    and times_over[i] <= max_time
                    and times_target[i] <= max_time
                ):
                    original_time_target = solution[target_id]["Total time"]
                    delta = (original_time_over - times_over[i]) - (
                        times_target[i] - original_time_target
                    )
                    if delta > best_delta:
                        best_delta = delta
                        best_target = (
                            target_id,
                            tsp_routes_over[i],
                            tsp_routes_target[i],
                            times_over[i],
                            times_target[i],
                        )

            if best_target and best_delta > 0:
                target_id, tsp_over, tsp_target, time_over, time_target = best_target
                solution[courier_id]["New route"] = tsp_over
                solution[target_id]["New route"] = tsp_target
                solution[courier_id]["Total time"] = time_over
                solution[target_id]["Total time"] = time_target
                batch_update_courier_metrics(
                    solution,
                    [courier_id, target_id],
                    optimizer.polygon_results,
                    optimizer.warehouse_point,
                )
                transfers_made += 1
                break

    return transfers_made


def update_threshold_optimized(solution, current_threshold, transfers_made):
    avg_times = [data["Avg service time"] for data in solution.values()]
    if not avg_times:
        return current_threshold

    mean_time = float(np.mean(avg_times))
    std_time = float(np.std(avg_times))
    calculated_threshold = mean_time + std_time

    logger.info(
        "Threshold %.1f -> %.1f (mean %.1f, std %.1f), transfers %s",
        current_threshold,
        calculated_threshold,
        mean_time,
        std_time,
        transfers_made,
    )

    if current_threshold > calculated_threshold:
        return calculated_threshold
    if current_threshold * 0.9 > 30:
        return current_threshold * 0.90
    return current_threshold


def rebalance_couriers_with_tsp_optimized(
    best_solution: RoutingDict,
    polygon_results: PolygonResults,
    new_couriers_dict: Dict[int, Dict[int, int]],
    cross_mem,
    polygon_to_index: dict,
    config: Config,
    initial_avg_threshold: float,
    time_history_callback: Optional[Callable[[float, float], None]] = None,
    elapsed_offset: float = 0.0,
) -> RoutingDict:
    start_time = time.time()
    optimizer = OptimizedRebalancer(
        polygon_results,
        new_couriers_dict,
        warehouse_point=config.warehouse_point,
        cross_mem=cross_mem,
        polygon_to_index=polygon_to_index,
        bitmask_max_points=config.sa_bitmask_max_points,
        config=config,
    )

    new_solution = copy.deepcopy(best_solution)
    couriers = list(new_solution.keys())
    avg_threshold = initial_avg_threshold

    for iteration in range(1, config.rebalance_max_iterations + 1):
        logger.info("Rebalance iteration %s", iteration)
        overloaded = [
            cid for cid, data in new_solution.items() if data["Avg service time"] > avg_threshold
        ]
        if not overloaded:
            logger.info("No overloaded couriers")
            break

        transfers_made = perform_optimized_swaps_fast(
            new_solution, overloaded, couriers, polygon_results, new_couriers_dict,
            config.max_courier_time_sec, optimizer,
        )
        transfers_made += perform_optimized_transfers_fast(
            new_solution, overloaded, couriers, config.max_courier_time_sec, optimizer
        )
        avg_threshold = update_threshold_optimized(new_solution, avg_threshold, transfers_made)

        total_time = sum(c["Total time"] for c in new_solution.values())
        if time_history_callback:
            elapsed = elapsed_offset + (time.time() - start_time)
            time_history_callback(elapsed, total_time)

    for courier_id in new_solution:
        route_data = new_solution[courier_id]
        route = route_data["New route"]
        travelling_time = sum(
            optimizer.get_distance(route[i], route[i + 1]) for i in range(len(route) - 1)
        )
        polygonal_service = 0
        for poly_id in route[1:]:
            if poly_id in new_couriers_dict.get(courier_id, {}) and poly_id in polygon_results:
                polygonal_service += (
                    new_couriers_dict[courier_id][poly_id]
                    * len(polygon_results[poly_id]["route"])
                )
        polygonal_travelling = sum(
            polygon_results[poly_id]["total_distance"]
            for poly_id in route[1:]
            if poly_id in polygon_results
        )
        route_data.update(
            {
                "Travelling time": travelling_time,
                "Polygonal service": polygonal_service,
                "Polygonal travelling": polygonal_travelling,
            }
        )

    return new_solution
