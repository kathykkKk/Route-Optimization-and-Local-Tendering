import pickle
from pathlib import Path
from typing import Any

from optimization.utils.logger import get_logger

logger = get_logger(__name__)


def save_pickle(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        pickle.dump(obj, f)
    logger.info("Saved %s", path)


def load_pickle(path: Path) -> Any:
    with path.open("rb") as f:
        return pickle.load(f)
