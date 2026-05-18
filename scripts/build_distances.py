#!/usr/bin/env python3
"""Build data/processed/distances.dat from data/raw/distances.db."""

from optimization.config.config import Config
from optimization.loaders.distance_loader import build_distance_memmap_from_db


def main() -> None:
    config = Config()
    config.processed_data_dir.mkdir(parents=True, exist_ok=True)
    build_distance_memmap_from_db(config.distances_db_path, config.distances_dat_path)
    print(f"Created {config.distances_dat_path}")


if __name__ == "__main__":
    main()
