from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    """Paths and hyperparameters for the routing pipeline."""

    project_root: Path = Path(__file__).resolve().parents[2]

    # Data
    raw_data_dir: Path = project_root / "data" / "raw"
    processed_data_dir: Path = project_root / "data" / "processed"
    output_dir: Path = project_root / "output"

    orders_json: str = "ml_ozon_logistic_dataSetOrders.json"
    couriers_json: str = "ml_ozon_logistic_dataSetCouriers.json"
    distances_db: str = "distances.db"
    distances_dat: str = "distances.dat"
    cross_matrix_dat: str = "cross_matrix.dat"

    # Routing constants
    warehouse_point: int = 0
    max_courier_time_sec: int = 43_200
    cross_polygon_punishment: int = 8_000
    penalty_per_order_sec: int = 3_000
    missing_distance_default: int = 10**9
    inf_distance: int = 10**9

    top_courier_candidates: int = 10
    sa_bitmask_max_points: int = 13

    # Simulated annealing
    sa_initial_temperature: float = 50_000.0
    sa_cooling_rate: float = 0.995
    sa_iterations_per_temp: int = 300
    sa_min_temperature: float = 0.0005

    # Rebalance
    rebalance_max_iterations: int = 30
    rebalance_initial_avg_threshold: float = 120.0

    # Cross-matrix build
    cross_matrix_workers: int = 4

    # TSP optimizers (see optimization/solvers/tsp/)
    # inner: christofides | branch_and_cut | branch_and_cut_gurobi  (aliases: cbc_open, gurobi_ampl)
    inner_tsp_solver: str = "christofides"
    outer_tsp_solver: str = "christofides"
    polish_tsp_solver: str = "lkh"  # post-rebalance; lkh | christofides

    branch_and_cut_max_time_s: float = 30.0
    branch_and_cut_gurobi_max_time_s: float = 30_000.0
    cbc_threads: int = 4
    ampl_license_uuid: str | None = None
    lkh_binary: str = "LKH-3.0.13/LKH"
    lkh_runs: int = 5

    inner_tsp_fallback_to_christofides: bool = True
    polish_tsp_fallback_to_christofides: bool = True

    # Pipeline stages (set False to skip optional steps)
    run_simulated_annealing: bool = True
    run_rebalance: bool = True
    run_local_order_polish: bool = True

    @property
    def orders_path(self) -> Path:
        return self.raw_data_dir / self.orders_json

    @property
    def couriers_path(self) -> Path:
        return self.raw_data_dir / self.couriers_json

    @property
    def distances_db_path(self) -> Path:
        return self.raw_data_dir / self.distances_db

    @property
    def distances_dat_path(self) -> Path:
        return self.processed_data_dir / self.distances_dat

    @property
    def cross_matrix_path(self) -> Path:
        return self.processed_data_dir / self.cross_matrix_dat
