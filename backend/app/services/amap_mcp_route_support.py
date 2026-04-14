from __future__ import annotations

import re
from math import asin, cos, radians, sin, sqrt
from typing import Any, Callable

from app.schemas.planning import GeoPoint, POIRecommendation, RouteStep, RouteSummary

ToInt = Callable[[Any], int | None]


def estimate_fallback_transport_cost(total_km: float, mode: str) -> int:
    if mode in {"walking", "bicycling"}:
        return 0
    if mode == "transit":
        return max(2, int(round(total_km * 1.8)))
    return max(10, int(round(total_km * 4.5)))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(a))


def polyline_distance_km(polyline: list[GeoPoint]) -> float:
    if len(polyline) < 2:
        return 0.0
    distance = 0.0
    for index in range(1, len(polyline)):
        prev = polyline[index - 1]
        curr = polyline[index]
        distance += haversine_km(prev.latitude, prev.longitude, curr.latitude, curr.longitude)
    return max(distance, 0.5)


def fallback_route(
    *,
    day_number: int,
    origin: POIRecommendation,
    destination: POIRecommendation,
    waypoints: list[POIRecommendation],
    mode: str,
    fallback_polyline: list[GeoPoint],
) -> RouteSummary:
    total_km = polyline_distance_km(fallback_polyline) if len(fallback_polyline) > 1 else 8.0
    speed_kmh = {
        "walking": 4.5,
        "bicycling": 12.0,
        "transit": 20.0,
        "driving": 28.0,
    }.get(mode, 20.0)
    duration_minutes = max(10, round(total_km / max(speed_kmh, 1.0) * 60))
    step_target = waypoints[0].name if waypoints else destination.name
    return RouteSummary(
        day_number=day_number,
        title=f"第 {day_number} 天路线",
        from_name=origin.name,
        to_name=destination.name,
        waypoints=[item.name for item in waypoints],
        distance_text=f"{total_km:.1f}公里",
        duration_text=f"约 {duration_minutes} 分钟",
        mode=mode,
        estimated_transport_cost_cny=estimate_fallback_transport_cost(total_km, mode),
        steps=[
            RouteStep(instruction=f"从 {origin.name} 出发，前往 {step_target}", distance_text="", duration_text=""),
            RouteStep(instruction=f"随后继续前往 {destination.name}", distance_text="", duration_text=""),
        ],
        polyline=fallback_polyline,
    )


def parse_cny_amount(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return max(0, int(round(float(value))))
    text = str(value).strip()
    if not text:
        return None
    numbers = [float(item.replace(",", "")) for item in re.findall(r"\d+(?:\.\d+)?", text)]
    if not numbers:
        return None
    if len(numbers) == 1:
        return max(0, int(round(numbers[0])))
    return max(0, int(round(sum(numbers[:2]) / 2)))


def extract_transport_cost_cny(
    *,
    route_root: dict[str, Any] | None,
    route_data: Any,
    mode: str,
) -> int:
    if mode in {"walking", "bicycling"}:
        return 0

    root = route_root if isinstance(route_root, dict) else {}
    data = route_data if isinstance(route_data, dict) else {}

    transit_cost = parse_cny_amount(data.get("cost"))
    taxi_cost = parse_cny_amount(root.get("taxi_cost"))
    tolls = parse_cny_amount(data.get("tolls"))

    if mode == "transit":
        if transit_cost is not None:
            return transit_cost
        if taxi_cost is not None:
            return taxi_cost
        return 0

    if taxi_cost is not None:
        return taxi_cost
    if tolls is not None:
        return tolls
    return 0


def format_distance_text(value: str, *, to_int: ToInt) -> str:
    raw = value.strip()
    if not raw:
        return ""
    meters = to_int(raw)
    if meters is None:
        return raw
    if meters >= 1000:
        return f"{meters / 1000:.1f}公里"
    return f"{meters}米"


def format_duration_text(value: str, *, to_int: ToInt) -> str:
    raw = value.strip()
    if not raw:
        return ""
    seconds = to_int(raw)
    if seconds is None:
        return raw
    if seconds >= 3600:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}小时{minutes}分钟" if minutes else f"{hours}小时"
    minutes = max(1, round(seconds / 60))
    return f"{minutes}分钟"
