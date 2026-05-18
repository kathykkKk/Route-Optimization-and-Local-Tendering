from dataclasses import dataclass, field
from typing import Any, Dict, List, TypedDict


class PolygonRouteResult(TypedDict):
    start_point: int
    end_point: int
    total_distance: int
    route: List[int]


CourierRouteState = TypedDict(
    "CourierRouteState",
    {
        "New route": List[int],
        "Travelling time": int,
        "Polygonal service": int,
        "Polygonal travelling": int,
        "Total time": int,
        "Total orders": int,
        "last EP": int,
        "Avg service time": float,
    },
    total=False,
)


RoutingDict = Dict[int, CourierRouteState]
PolygonResults = Dict[int, PolygonRouteResult]


@dataclass
class PipelineArtifacts:
    """Mutable state passed between pipeline stages."""

    mpids_dict: Dict[int, List[int]] = field(default_factory=dict)
    mpids_list: List[int] = field(default_factory=list)
    poly_mapping: Dict[int, int] = field(default_factory=dict)
    couriers_data: List[Any] = field(default_factory=list)
    all_courier_ids: List[int] = field(default_factory=list)
    new_couriers_dict: Dict[int, Dict[int, int]] = field(default_factory=dict)

    routing_dict: RoutingDict = field(default_factory=dict)
    each_polygon_opt_route: PolygonResults = field(default_factory=dict)
    optimized_routing: RoutingDict = field(default_factory=dict)
    best_solution: RoutingDict = field(default_factory=dict)
    optimized_solution_fast: RoutingDict = field(default_factory=dict)
    final_solution: RoutingDict = field(default_factory=dict)
    final_each_polygon_opt_route: PolygonResults = field(default_factory=dict)

    distance_array: Any = None
    idx_dict: Dict[int, tuple] = field(default_factory=dict)
    cross_mem: Any = None
    polygon_to_index: Dict[int, int] = field(default_factory=dict)

    total_orders: int = 0
    absolute_total_dist: int = 0
    punishment: int = 0
    absolute_total: int = 0
    time_history: List[tuple] = field(default_factory=list)
