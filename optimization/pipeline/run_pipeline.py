"""End-to-end route optimization pipeline (notebook refactor)."""

from __future__ import annotations

import argparse
import time
from collections import defaultdict
from dataclasses import replace

from optimization.config.config import Config
from optimization.loaders.courier_loader import couriers_service_dict, load_couriers_data
from optimization.loaders.order_loader import load_order_to_polygon_map, load_orders_by_polygon
from optimization.models.route import PipelineArtifacts
from optimization.preprocessing.distance_index import ensure_distance_index
from optimization.preprocessing.mappings import build_polygon_index, build_polygon_mapping
from optimization.preprocessing.matrices import make_cross_memmap_threads
from optimization.solvers.courier_assignment import assign_polygons_to_couriers, init_routing_state
from optimization.solvers.local_polish import polish_courier_routes
from optimization.solvers.rebalance import rebalance_couriers_with_tsp_optimized
from optimization.solvers.recombine import recombine_all_routes
from optimization.solvers.simulated_annealing import run_sa_optimization
from optimization.utils.logger import get_logger
from optimization.utils.metrics import compute_solution_metrics, count_total_orders
from optimization.utils.persistence import save_pickle
from optimization.utils.timing import Timer

logger = get_logger(__name__)


def run_pipeline(config: Config | None = None, rebuild_distances: bool = False) -> PipelineArtifacts:
    config = config or Config()
    config.output_dir.mkdir(parents=True, exist_ok=True)
    config.processed_data_dir.mkdir(parents=True, exist_ok=True)

    artifacts = PipelineArtifacts()

    with Timer("Load orders and couriers"):
        artifacts.mpids_dict = load_orders_by_polygon(config.orders_path)
        artifacts.mpids_list = list(artifacts.mpids_dict.keys())
        artifacts.total_orders = count_total_orders(artifacts.mpids_dict)
        logger.info("Total orders: %s", artifacts.total_orders)

        artifacts.couriers_data = load_couriers_data(config.couriers_path)
        artifacts.all_courier_ids = [c.id for c in artifacts.couriers_data]
        artifacts.new_couriers_dict = couriers_service_dict(artifacts.couriers_data)

    with Timer("Load distance index"):
        artifacts.distance_array, artifacts.idx_dict = ensure_distance_index(
            config, rebuild=rebuild_distances
        )

    artifacts.poly_mapping = build_polygon_mapping(
        artifacts.mpids_dict, config.warehouse_point
    )

    with Timer("Initial polygon-to-courier assignment"):
        artifacts.routing_dict = init_routing_state(artifacts.all_courier_ids)
        artifacts.each_polygon_opt_route = defaultdict(dict)
        assign_polygons_to_couriers(
            mpids_dict=artifacts.mpids_dict,
            mpids_list=artifacts.mpids_list,
            routing_dict=artifacts.routing_dict,
            each_polygon_opt_route=artifacts.each_polygon_opt_route,
            new_couriers_dict=artifacts.new_couriers_dict,
            all_courier_ids=artifacts.all_courier_ids,
            distance_array=artifacts.distance_array,
            idx_dict=artifacts.idx_dict,
            config=config,
        )

    with Timer("Build cross-polygon distance matrix"):
        artifacts.cross_mem = make_cross_memmap_threads(
            str(config.cross_matrix_path),
            polygons=artifacts.mpids_list,
            each_polygon_opt_route=artifacts.each_polygon_opt_route,
            warehouse_point=config.warehouse_point,
            distance_array=artifacts.distance_array,
            idx_dict=artifacts.idx_dict,
            n_workers=config.cross_matrix_workers,
        )
        artifacts.polygon_to_index = build_polygon_index(artifacts.mpids_list)

    with Timer("Recombine routes (outer TSP)"):
        artifacts.optimized_routing = recombine_all_routes(
            artifacts.routing_dict,
            artifacts.all_courier_ids,
            artifacts.cross_mem,
            artifacts.polygon_to_index,
            config.warehouse_point,
            config=config,
        )

    (
        artifacts.absolute_total_dist,
        artifacts.punishment,
        artifacts.absolute_total,
    ) = compute_solution_metrics(
        artifacts.optimized_routing,
        artifacts.each_polygon_opt_route,
        artifacts.total_orders,
        config.penalty_per_order_sec,
    )
    artifacts.time_history = [(0.0, float(artifacts.absolute_total))]
    logger.info(
        "Baseline objective: %s (unserved penalty %s)",
        artifacts.absolute_total,
        artifacts.punishment,
    )

    save_pickle(config.output_dir / "optimized_routing.pkl", artifacts.optimized_routing)
    save_pickle(config.output_dir / "each_polygon_opt_route.pkl", dict(artifacts.each_polygon_opt_route))

    pipeline_start = time.time()
    elapsed_offset = 0.0

    if config.run_simulated_annealing:
        with Timer("Simulated annealing"):
            artifacts.best_solution, sa_objective = run_sa_optimization(
                current_routing_dict=artifacts.optimized_routing,
                polygon_results=dict(artifacts.each_polygon_opt_route),
                new_couriers_dict=artifacts.new_couriers_dict,
                cross_mem=artifacts.cross_mem,
                polygon_to_index=artifacts.polygon_to_index,
                config=config,
                time_history=artifacts.time_history,
                elapsed_offset=elapsed_offset,
            )
            logger.info("SA objective: %s", sa_objective)
        elapsed_offset = time.time() - pipeline_start
    else:
        artifacts.best_solution = artifacts.optimized_routing

    rebalance_threshold = config.rebalance_initial_avg_threshold
    if config.run_rebalance:
        avg_times = [
            artifacts.best_solution[c]["Avg service time"]
            for c in artifacts.best_solution
            if artifacts.best_solution[c].get("Total orders", 0) > 0
        ]
        if avg_times:
            import numpy as np

            rebalance_threshold = float(np.mean(avg_times) + np.std(avg_times))

        def on_rebalance_tick(elapsed: float, objective: float) -> None:
            artifacts.time_history.append((elapsed, objective))

        with Timer("Rebalance overloaded couriers"):
            artifacts.optimized_solution_fast = rebalance_couriers_with_tsp_optimized(
                best_solution=artifacts.best_solution,
                polygon_results=dict(artifacts.each_polygon_opt_route),
                new_couriers_dict=artifacts.new_couriers_dict,
                cross_mem=artifacts.cross_mem,
                polygon_to_index=artifacts.polygon_to_index,
                config=config,
                initial_avg_threshold=rebalance_threshold,
                time_history_callback=on_rebalance_tick,
                elapsed_offset=elapsed_offset,
            )
    else:
        artifacts.optimized_solution_fast = artifacts.best_solution

    if config.run_local_order_polish:
        order_to_mpid = load_order_to_polygon_map(config.orders_path)
        with Timer("Local order-level polish"):
            artifacts.final_solution, artifacts.final_each_polygon_opt_route = polish_courier_routes(
                artifacts.optimized_solution_fast,
                dict(artifacts.each_polygon_opt_route),
                artifacts.distance_array,
                artifacts.idx_dict,
                artifacts.poly_mapping,
                order_to_mpid,
                config=config,
            )
    else:
        artifacts.final_solution = artifacts.optimized_solution_fast
        artifacts.final_each_polygon_opt_route = dict(artifacts.each_polygon_opt_route)

    save_pickle(config.output_dir / "final_solution.pkl", artifacts.final_solution)
    save_pickle(
        config.output_dir / "final_each_polygon_opt_route.pkl",
        artifacts.final_each_polygon_opt_route,
    )
    save_pickle(config.output_dir / "time_history.pkl", artifacts.time_history)

    logger.info("Pipeline complete. Outputs in %s", config.output_dir)
    return artifacts


def main() -> None:
    parser = argparse.ArgumentParser(description="Route optimization pipeline")
    parser.add_argument("--rebuild-distances", action="store_true")
    parser.add_argument("--skip-sa", action="store_true")
    parser.add_argument("--skip-rebalance", action="store_true")
    parser.add_argument("--skip-polish", action="store_true")
    parser.add_argument(
        "--inner-tsp-solver",
        choices=[
            "christofides",
            "branch_and_cut",
            "branch_and_cut_gurobi",
            "cbc_open",
            "gurobi_ampl",
        ],
        default="christofides",
        help="Inner (order-level) TSP for assignment",
    )
    parser.add_argument(
        "--polish-tsp-solver",
        choices=["lkh", "christofides"],
        default="lkh",
        help="Order-level TSP after rebalance (local polish)",
    )
    args = parser.parse_args()

    config = replace(
        Config(),
        run_simulated_annealing=not args.skip_sa,
        run_rebalance=not args.skip_rebalance,
        run_local_order_polish=not args.skip_polish,
        inner_tsp_solver=args.inner_tsp_solver,
        polish_tsp_solver=args.polish_tsp_solver,
    )
    run_pipeline(config=config, rebuild_distances=args.rebuild_distances)


if __name__ == "__main__":
    main()
