from optimization.config.config import Config
from optimization.loaders.distance_loader import ensure_distances_ready


def ensure_distance_index(config: Config, rebuild: bool = False):
    return ensure_distances_ready(config, rebuild=rebuild)
