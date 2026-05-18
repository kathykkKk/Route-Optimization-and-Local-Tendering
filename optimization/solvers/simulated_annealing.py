import copy
import math
import random
import time
from typing import Callable, Dict, List, Optional, Tuple

from optimization.config.config import Config
from optimization.models.route import PolygonResults, RoutingDict
from optimization.solvers.rebalancer import OptimizedRebalancer
from optimization.utils.logger import get_logger

logger = get_logger(__name__)


class CourierRoutingSA:
    def __init__(
        self,
        initial_solution: RoutingDict,
        polygon_results: PolygonResults,
        new_couriers_dict: Dict[int, Dict[int, int]],
        cross_mem,
        polygon_to_index: dict,
        config: Config,
        time_history_callback: Optional[Callable[[float, float], None]] = None,
        elapsed_offset: float = 0.0,
    ):
        self.initial_solution = initial_solution
        self.polygon_results = polygon_results
        self.new_couriers_dict = new_couriers_dict
        self.max_time = config.max_courier_time_sec
        self.cross_mem = cross_mem
        self.polygon_to_index = polygon_to_index
        self.config = config
        self.time_history_callback = time_history_callback
        self.elapsed_offset = elapsed_offset
        self._sa_start = 0.0

        self.optimizer = OptimizedRebalancer(
            polygon_results,
            new_couriers_dict,
            warehouse_point=config.warehouse_point,
            cross_mem=cross_mem,
            polygon_to_index=polygon_to_index,
            bitmask_max_points=config.sa_bitmask_max_points,
            config=config,
        )

    def total_solution_time(self, solution: RoutingDict) -> float:
        return float(sum(route_data["Total time"] for route_data in solution.values()))

    def has_duplicate_polygons(self, solution: RoutingDict) -> bool:
        all_polygons = set()
        for data in solution.values():
            for poly_id in data["New route"]:
                if poly_id != 0 and poly_id in all_polygons:
                    return True
                all_polygons.add(poly_id)
        return False

    def generate_neighbor(self, solution: RoutingDict) -> RoutingDict:
        courier_ids = list(solution.keys())
        operation = random.choices(["swap", "move"], weights=[0.6, 0.4])[0]

        if operation == "swap" and len(courier_ids) >= 2:
            i, j = random.sample(courier_ids, 2)
            route_i = solution[i]["New route"][:]
            route_j = solution[j]["New route"][:]

            if len(route_i) > 2 and len(route_j) > 2:
                idx_i = random.randint(1, len(route_i) - 1)
                idx_j = random.randint(1, len(route_j) - 1)
                poly_i, poly_j = route_i[idx_i], route_j[idx_j]

                if poly_j not in route_i and poly_i not in route_j:
                    route_i[idx_i], route_j[idx_j] = poly_j, poly_i
                    tsp_route_i, new_time_i = self.optimizer.get_cached_tsp_route(route_i, i)
                    tsp_route_j, new_time_j = self.optimizer.get_cached_tsp_route(route_j, j)

                    if (
                        tsp_route_i is not None
                        and tsp_route_j is not None
                        and new_time_i <= self.max_time
                        and new_time_j <= self.max_time
                    ):
                        new_solution = solution.copy()
                        new_solution[i] = {"New route": tsp_route_i, "Total time": new_time_i}
                        new_solution[j] = {"New route": tsp_route_j, "Total time": new_time_j}
                        if not self.has_duplicate_polygons(new_solution):
                            return new_solution

        elif operation == "move":
            i, j = random.sample(courier_ids, 2)
            route_i = solution[i]["New route"][:]
            route_j = solution[j]["New route"][:]

            if len(route_i) > 2:
                idx_i = random.randint(1, len(route_i) - 1)
                poly_to_move = route_i[idx_i]

                if poly_to_move not in route_j:
                    idx_j = random.randint(1, len(route_j)) if len(route_j) > 1 else 1
                    del route_i[idx_i]
                    route_j.insert(idx_j, poly_to_move)

                    tsp_route_i, new_time_i = self.optimizer.get_cached_tsp_route(route_i, i)
                    tsp_route_j, new_time_j = self.optimizer.get_cached_tsp_route(route_j, j)

                    if (
                        tsp_route_i is not None
                        and tsp_route_j is not None
                        and new_time_i <= self.max_time
                        and new_time_j <= self.max_time
                    ):
                        new_solution = solution.copy()
                        new_solution[i] = {"New route": tsp_route_i, "Total time": new_time_i}
                        new_solution[j] = {"New route": tsp_route_j, "Total time": new_time_j}
                        if not self.has_duplicate_polygons(new_solution):
                            return new_solution

        return solution

    def simulated_annealing(self) -> Tuple[RoutingDict, float]:
        cfg = self.config
        current_solution = copy.deepcopy(self.initial_solution)
        current_energy = self.total_solution_time(current_solution)
        best_solution = copy.deepcopy(current_solution)
        best_energy = current_energy

        T = cfg.sa_initial_temperature
        iteration = 0
        self._sa_start = time.time()

        logger.info("SA initial objective: %s", current_energy)

        while T > cfg.sa_min_temperature:
            for _ in range(cfg.sa_iterations_per_temp):
                new_solution = self.generate_neighbor(current_solution)
                new_energy = self.total_solution_time(new_solution)
                delta_energy = new_energy - current_energy

                if delta_energy < 0 or random.random() < math.exp(-delta_energy / T):
                    current_solution = new_solution
                    current_energy = new_energy
                    if new_energy < best_energy:
                        best_solution = copy.deepcopy(new_solution)
                        best_energy = new_energy
                        logger.info("SA best: %s (T=%.4f)", best_energy, T)

            if self.time_history_callback:
                elapsed = self.elapsed_offset + (time.time() - self._sa_start)
                self.time_history_callback(elapsed, current_energy)

            T *= cfg.sa_cooling_rate
            iteration += 1
            if iteration % 10 == 0:
                logger.info("SA iter %s T=%.4f objective=%s", iteration, T, current_energy)

        return self._finalize_metrics(best_solution), self.total_solution_time(best_solution)

    def _finalize_metrics(self, best_solution: RoutingDict) -> RoutingDict:
        for courier_id, route_data in best_solution.items():
            route = route_data["New route"]
            travelling_time = sum(
                self.optimizer.get_distance(route[i], route[i + 1])
                for i in range(len(route) - 1)
            )

            polygonal_service = 0
            total_orders = 0
            for poly_id in route[1:]:
                if poly_id in self.polygon_results:
                    orders_in_poly = len(self.polygon_results[poly_id]["route"])
                    total_orders += orders_in_poly
                    if poly_id in self.new_couriers_dict.get(courier_id, {}):
                        polygonal_service += (
                            self.new_couriers_dict[courier_id][poly_id] * orders_in_poly
                        )

            polygonal_travelling = sum(
                self.polygon_results[poly_id]["total_distance"]
                for poly_id in route[1:]
                if poly_id in self.polygon_results
            )

            route_data.update(
                {
                    "Travelling time": travelling_time,
                    "Polygonal service": polygonal_service,
                    "Polygonal travelling": polygonal_travelling,
                    "Total orders": total_orders,
                    "Avg service time": round(
                        route_data["Total time"] / total_orders if total_orders > 0 else 0, 2
                    ),
                }
            )
        return best_solution


def run_sa_optimization(
    current_routing_dict: RoutingDict,
    polygon_results: PolygonResults,
    new_couriers_dict: Dict[int, Dict[int, int]],
    cross_mem,
    polygon_to_index: dict,
    config: Config,
    time_history: Optional[list] = None,
    elapsed_offset: float = 0.0,
) -> Tuple[RoutingDict, float]:
    random.seed(42)

    def on_tick(elapsed: float, objective: float) -> None:
        if time_history is not None:
            time_history.append((elapsed, objective))

    sa = CourierRoutingSA(
        initial_solution=copy.deepcopy(current_routing_dict),
        polygon_results=polygon_results,
        new_couriers_dict=new_couriers_dict,
        cross_mem=cross_mem,
        polygon_to_index=polygon_to_index,
        config=config,
        time_history_callback=on_tick,
        elapsed_offset=elapsed_offset,
    )
    return sa.simulated_annealing()
