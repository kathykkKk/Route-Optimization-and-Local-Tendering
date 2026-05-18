import sqlite3
import time
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
from tqdm import tqdm

from optimization.config.config import Config
from optimization.utils.logger import get_logger

logger = get_logger(__name__)


def build_distance_memmap_from_db(db_path: Path, dat_path: Path, batch_size: int = 100_000) -> np.ndarray:
    """Export sorted distances from SQLite into a memory-mapped .dat file."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM distances")
    total_rows = cursor.fetchone()[0]

    dat_path.parent.mkdir(parents=True, exist_ok=True)
    mmap_array = np.memmap(dat_path, dtype=np.int32, mode="w+", shape=(total_rows, 3))

    cursor.execute(
        "SELECT from_location, to_location, distance FROM distances "
        "ORDER BY from_location, to_location"
    )

    index = 0
    with tqdm(total=total_rows, desc="Building distances.dat", unit="row") as progress:
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            batch_array = np.array(rows, dtype=np.int32)
            mmap_array[index : index + len(batch_array)] = batch_array
            index += len(batch_array)
            progress.update(len(rows))

    conn.close()
    mmap_array.flush()
    logger.info("Wrote %s rows to %s", total_rows, dat_path)
    return mmap_array


def load_distance_array(dat_path: Path) -> np.ndarray:
    with dat_path.open("rb") as f:
        data_bytes = f.read()
    return np.frombuffer(data_bytes, dtype=np.int32).reshape(-1, 3)


def create_search_index(distance_array: np.ndarray) -> Dict[int, Tuple[int, int]]:
    unique_from, start_indices = np.unique(distance_array[:, 0], return_index=True)
    index_dict: Dict[int, Tuple[int, int]] = {}
    for i in range(len(unique_from)):
        start = int(start_indices[i])
        end = int(start_indices[i + 1]) if i + 1 < len(start_indices) else len(distance_array)
        index_dict[int(unique_from[i])] = (start, end)
    return index_dict


def get_distance(
    distance_array: np.ndarray,
    idx_dict: Dict[int, Tuple[int, int]],
    from_point: int,
    to_point: int,
    default: int | None = None,
) -> int:
    if default is None:
        default = Config().missing_distance_default

    if from_point not in idx_dict:
        return default

    start, end = idx_dict[from_point]
    subset = distance_array[start:end]
    to_points = subset[:, 1]
    pos = np.searchsorted(to_points, to_point)

    if pos < len(to_points) and to_points[pos] == to_point:
        return int(subset[pos, 2])
    return default


def ensure_distances_ready(config: Config, rebuild: bool = False) -> tuple[np.ndarray, Dict[int, Tuple[int, int]]]:
    dat_path = config.distances_dat_path
    if rebuild or not dat_path.exists():
        if not config.distances_db_path.exists():
            raise FileNotFoundError(
                f"Missing {config.distances_db_path}. Place raw distances.db under data/raw/."
            )
        logger.info("Building %s from SQLite...", dat_path)
        build_distance_memmap_from_db(config.distances_db_path, dat_path)

    start = time.time()
    distance_array = load_distance_array(dat_path)
    idx_dict = create_search_index(distance_array)
    logger.info(
        "Distance cache ready in %.2f s (%s records)",
        time.time() - start,
        len(distance_array),
    )
    return distance_array, idx_dict
