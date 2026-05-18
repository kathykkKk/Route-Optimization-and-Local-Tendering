import time
from dataclasses import dataclass, field
from typing import List, Tuple

from optimization.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Timer:
    label: str = "stage"
    _start: float = field(default=0.0, init=False, repr=False)

    def __enter__(self) -> "Timer":
        self._start = time.time()
        logger.info("Start: %s", self.label)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        elapsed = time.time() - self._start
        logger.info("Done: %s in %.2f s", self.label, elapsed)


def append_time_history(
    history: List[Tuple[float, float]],
    elapsed_offset: float,
    objective: float,
) -> None:
    history.append((elapsed_offset, objective))
