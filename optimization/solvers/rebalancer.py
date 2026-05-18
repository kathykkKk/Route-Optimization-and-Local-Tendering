from typing import Dict, List, Optional, Tuple

import numpy as np
from numba import njit

from optimization.config.config import Config
from optimization.solvers.tsp.registry import solve_outer_tsp

tsp_travelling_cache: Dict[tuple, Tuple[int, List[int]]] = {}


@njit(nogil=True, cache=True, fastmath=True)
def _numba_tsp_dp(n, distance_matrix, start_distances):
    size = 1 << n
    inf = 1e20

    dp = np.full((size, n), inf)
    prev = np.full((size, n), -1, dtype=np.int32)

    for i in range(n):
        dp[1 << i, i] = start_distances[i]

    for mask in range(size):
        for i in range(n):
            current_cost = dp[mask, i]
            if current_cost >= inf:
                continue
            for j in range(n):
                if (mask >> j) & 1:
                    continue
                new_mask = mask | (1 << j)
                new_cost = current_cost + distance_matrix[i, j]
                if new_cost < dp[new_mask, j]:
                    dp[new_mask, j] = new_cost
                    prev[new_mask, j] = i

    full_mask = size - 1
    min_cost = inf
    best_end = -1
    for i in range(n):
        if dp[full_mask, i] < min_cost:
            min_cost = dp[full_mask, i]
            best_end = i

    return min_cost, best_end, prev


class OptimizedRebalancer:
    def __init__(
        self,
        polygon_results,
        new_couriers_dict,
        warehouse_point: int = 0,
        cross_mem=None,
        polygon_to_index=None,
        bitmask_max_points: int = 13,
        config: Config | None = None,
    ):
        self.config = config or Config()
        self.polygon_results = polygon_results
        self.new_couriers_dict = new_couriers_dict
        self.warehouse_point = warehouse_point
        self.cross_mem = cross_mem
        self.polygon_to_index = polygon_to_index
        self.bitmask_max_points = bitmask_max_points

    def get_tsp_route_bitmask(self, points: List[int], courier_id: int):
        if not points:
            return [self.warehouse_point], 0

        n = len(points)
        points_tuple = tuple(sorted(points))
        total_service = self._get_total_service_time(courier_id, points)
        if total_service >= 10**9:
            return None, 10**9

        if points_tuple in tsp_travelling_cache:
            base_cost, optimal_route = tsp_travelling_cache[points_tuple]
            return optimal_route, base_cost + total_service

        if n == 1:
            point = points[0]
            travelling = self.get_distance(self.warehouse_point, point)
            internal = self._get_internal_travel(point)
            total_time = travelling + total_service + internal
            route = [self.warehouse_point, point]
            tsp_travelling_cache[points_tuple] = (travelling + internal, route)
            return route, total_time

        indices = [self.polygon_to_index[pid] for pid in points]
        distance_matrix = self.cross_mem[np.ix_(indices, indices)].copy()
        np.fill_diagonal(distance_matrix, 0)

        warehouse_idx = self.polygon_to_index[self.warehouse_point]
        start_distances = self.cross_mem[warehouse_idx, indices].astype(np.float64)

        min_travelling_cost, best_end, prev_matrix = _numba_tsp_dp(
            n, distance_matrix, start_distances
        )
        route = self._reconstruct_route_numba(prev_matrix, best_end, points)
        total_internal = self._get_total_internal_travel(points)
        base_cost = min_travelling_cost + total_internal
        tsp_travelling_cache[points_tuple] = (base_cost, route)
        return route, base_cost + total_service

    def get_cached_tsp_route(self, route: List[int], courier_id: int):
        filtered_route = [p for p in route if p != self.warehouse_point]
        if len(filtered_route) <= self.bitmask_max_points:
            return self.get_tsp_route_bitmask(filtered_route, courier_id)
        return self.get_tsp_route_christofides(route, courier_id)

    def get_tsp_route_christofides(self, route: List[int], courier_id: int):
        filtered_route = [p for p in route if p != self.warehouse_point]
        points_tuple = tuple(sorted(filtered_route))

        total_service = self._get_total_service_time(courier_id, filtered_route)
        if total_service >= 10**9:
            return None, 10**9

        if points_tuple in tsp_travelling_cache:
            base_cost, optimal_route = tsp_travelling_cache[points_tuple]
            return optimal_route, base_cost + total_service

        outer = solve_outer_tsp(route, self.cross_mem, self.polygon_to_index, config=self.config)
        christofides_route, route_distance = outer.route, outer.distance
        total_internal = self._get_total_internal_travel(filtered_route)
        base_cost = route_distance + total_internal
        tsp_travelling_cache[points_tuple] = (base_cost, christofides_route)
        return christofides_route, base_cost + total_service

    def _get_service_time(self, courier_id, point):
        if point in self.new_couriers_dict.get(courier_id, {}):
            return self.new_couriers_dict[courier_id][point] * len(
                self.polygon_results[point]["route"]
            )
        return 10**9

    def _get_internal_travel(self, point):
        return self.polygon_results[point]["total_distance"]

    def _get_total_service_time(self, courier_id, points):
        return sum(self._get_service_time(courier_id, p) for p in points)

    def _get_total_internal_travel(self, points):
        return sum(self._get_internal_travel(p) for p in points)

    def get_distance(self, point_a, point_b):
        i = self.polygon_to_index[point_a]
        j = self.polygon_to_index[point_b]
        return int(self.cross_mem[i, j])

    def _reconstruct_route_numba(self, prev_matrix, best_end, points):
        n = len(points)
        current_mask = (1 << n) - 1
        current_idx = best_end
        path = []
        while current_mask != 0:
            path.append(points[current_idx])
            next_idx = prev_matrix[current_mask, current_idx]
            if next_idx == -1:
                break
            current_mask = current_mask & ~(1 << current_idx)
            current_idx = next_idx
        path.reverse()
        return [self.warehouse_point] + path
