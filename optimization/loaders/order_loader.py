import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

import polars as pl


def load_orders_by_polygon(orders_path: Path) -> Dict[int, List[int]]:
    """Load orders JSON and group order IDs by polygon (MpId)."""
    mpid_df = pl.read_json(orders_path)
    mpids_dict: Dict[int, List[int]] = defaultdict(list)

    for item in mpid_df["Orders"].to_list():
        for order in item:
            mpids_dict[order["MpId"]].append(order["ID"])

    return dict(mpids_dict)


def load_order_to_polygon_map(orders_path: Path) -> Dict[int, int]:
    mpid_df = pl.read_json(orders_path)
    df_exploded = mpid_df.explode("Orders").unnest("Orders")
    return dict(zip(df_exploded["ID"], df_exploded["MpId"]))
