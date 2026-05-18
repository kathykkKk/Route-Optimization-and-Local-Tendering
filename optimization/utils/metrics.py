from typing import Dict

from optimization.models.route import PolygonResults, RoutingDict


def count_total_orders(mpids_dict: Dict[int, list], skip_polygon: int = 0) -> int:
    total = 0
    for polygon_id, orders in mpids_dict.items():
        if polygon_id != skip_polygon:
            total += len(orders)
    return total


def compute_solution_metrics(
    routing: RoutingDict,
    polygon_results: PolygonResults,
    total_orders: int,
    penalty_per_order: int,
) -> tuple[int, int, int]:
    absolute_total_dist = sum(
        data["Total time"] for data in routing.values() if data.get("Total orders", 0) > 0
    )

    total_served = 0
    for data in routing.values():
        for poly_id in data["New route"]:
            if poly_id != 0 and poly_id in polygon_results:
                total_served += len(polygon_results[poly_id]["route"])

    punishment = (total_orders - total_served) * penalty_per_order
    absolute_total = absolute_total_dist + punishment
    return absolute_total_dist, punishment, absolute_total
