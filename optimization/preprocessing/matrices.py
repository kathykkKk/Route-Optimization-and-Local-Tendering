import os
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple

import numpy as np
from tqdm import tqdm

from optimization.config.config import Config
from optimization.loaders.distance_loader import get_distance
from optimization.models.route import PolygonResults


def create_distance_matrix(
    points: List[int],
    distance_array: np.ndarray,
    idx_dict: Dict[int, Tuple[int, int]],
    poly_mapping: Optional[Dict[int, int]] = None,
    punishment: Optional[int] = None,
) -> List[List[int]]:
    if punishment is None:
        punishment = Config().cross_polygon_punishment

    n = len(points)
    matrix = np.zeros((n, n), dtype=np.int64)

    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            distance = get_distance(distance_array, idx_dict, points[i], points[j])
            if poly_mapping is not None and poly_mapping[points[i]] != poly_mapping[points[j]]:
                matrix[i, j] = distance + punishment
            else:
                matrix[i, j] = distance

    return matrix.astype(int).tolist()


def create_distance_matrix_no_return(
    points: List[int],
    distance_array: np.ndarray,
    idx_dict: Dict[int, Tuple[int, int]],
    poly_mapping: Optional[Dict[int, int]] = None,
    punishment: Optional[int] = None,
) -> List[List[int]]:
    if punishment is None:
        punishment = Config().cross_polygon_punishment

    n = len(points)
    matrix = np.zeros((n, n), dtype=int)

    for i in range(n):
        for j in range(n):
            if i == j or j == 0:
                matrix[i, j] = 0
                continue
            distance = get_distance(distance_array, idx_dict, points[i], points[j])
            if poly_mapping is not None and poly_mapping[points[i]] != poly_mapping[points[j]]:
                matrix[i, j] = distance + punishment
            else:
                matrix[i, j] = distance

    return matrix.tolist()


def get_depot_point(
    points: List[int],
    prev_point: int,
    distance_array: np.ndarray,
    idx_dict: Dict[int, Tuple[int, int]],
) -> int:
    distances_vector = [
        int(get_distance(distance_array, idx_dict, prev_point, p)) for p in points
    ]
    return distances_vector.index(min(distances_vector))


def _fill_row_worker(
    path: str,
    rows_range: list,
    start_pts: list,
    end_pts: list,
    distance_array: np.ndarray,
    idx_dict: dict,
    inf: int,
) -> bool:
    cross = np.memmap(path, dtype=np.int32, mode="r+", shape=(len(start_pts), len(start_pts)))
    for i in rows_range:
        fp = int(end_pts[i])
        row = np.empty(len(start_pts), dtype=np.int32)
        for j in range(len(start_pts)):
            tp = int(start_pts[j])
            d = get_distance(distance_array, idx_dict, fp, tp, default=inf)
            row[j] = int(d)
        cross[i, :] = row
    cross.flush()
    return True


def make_cross_memmap_threads(
    path: str,
    polygons: List[int],
    each_polygon_opt_route: PolygonResults,
    warehouse_point: int,
    distance_array: np.ndarray,
    idx_dict: Dict[int, Tuple[int, int]],
    n_workers: int = 4,
    inf: Optional[int] = None,
) -> np.memmap:
    if inf is None:
        inf = Config().inf_distance

    start_pts = [
        warehouse_point if pid == warehouse_point else each_polygon_opt_route[pid]["start_point"]
        for pid in polygons
    ]
    end_pts = [
        warehouse_point if pid == warehouse_point else each_polygon_opt_route[pid]["end_point"]
        for pid in polygons
    ]

    if os.path.exists(path):
        os.remove(path)

    p = len(polygons)
    cross = np.memmap(path, dtype=np.int32, mode="w+", shape=(p, p))
    cross.flush()

    rows = list(range(p))
    chunk_size = (p + n_workers - 1) // n_workers
    chunks = [rows[i : i + chunk_size] for i in range(0, p, chunk_size)]

    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        list(
            tqdm(
                executor.map(
                    lambda ch: _fill_row_worker(
                        path, ch, start_pts, end_pts, distance_array, idx_dict, inf
                    ),
                    chunks,
                ),
                total=len(chunks),
                desc="Filling cross_matrix.dat",
            )
        )

    return np.memmap(path, dtype=np.int32, mode="r+", shape=(p, p))
