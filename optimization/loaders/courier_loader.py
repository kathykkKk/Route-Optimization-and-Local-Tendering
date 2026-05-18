import json
from pathlib import Path
from typing import Dict, List

from optimization.models.courier import Courier


def load_couriers_data(couriers_path: Path) -> List[Courier]:
    with couriers_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    couriers: List[Courier] = []
    for courier_group in data["Couriers"]:
        service_times: Dict[int, int] = {
            st["MpID"]: st["ServiceTime"] for st in courier_group["ServiceTimeInMps"]
        }
        couriers.append(Courier(id=courier_group["ID"], service_times=service_times))

    return couriers


def couriers_service_dict(couriers: List[Courier]) -> Dict[int, Dict[int, int]]:
    return {c.id: c.service_times for c in couriers}
