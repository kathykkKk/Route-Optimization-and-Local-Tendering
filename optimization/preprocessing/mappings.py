from typing import Dict, List


def build_polygon_mapping(mpids_dict: Dict[int, List[int]], warehouse_point: int = 0) -> Dict[int, int]:
    poly_mapping: Dict[int, int] = {}
    for polygon_id, points_list in mpids_dict.items():
        for point in points_list:
            poly_mapping[point] = polygon_id
    poly_mapping[warehouse_point] = warehouse_point
    return poly_mapping


def build_polygon_index(mpids_list: List[int]) -> Dict[int, int]:
    return {pid: idx for idx, pid in enumerate(mpids_list)}
