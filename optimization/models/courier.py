from dataclasses import dataclass
from typing import Dict


@dataclass
class Courier:
    id: int
    service_times: Dict[int, int]
