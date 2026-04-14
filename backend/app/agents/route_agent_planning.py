from __future__ import annotations

import math

from app.schemas.planning import POIRecommendation, TripPlanningRequest


def take_coordinate_points(
    points: list[POIRecommendation],
    limit: int,
) -> list[POIRecommendation]:
    selected: list[POIRecommendation] = []
    for poi in points:
        if poi.longitude is None or poi.latitude is None:
            continue
        selected.append(poi)
        if len(selected) >= limit:
            break
    return selected


def dedupe_points(points: list[POIRecommendation]) -> list[POIRecommendation]:
    deduped: list[POIRecommendation] = []
    seen: set[str] = set()
    for poi in points:
        key = poi.poi_id or poi.name
        if key in seen:
            continue
        seen.add(key)
        deduped.append(poi)
    return deduped


def select_day_attractions(
    attractions: list[POIRecommendation],
    day_index: int,
    must_visit: list[str],
) -> list[POIRecommendation]:
    if not attractions:
        return []

    selected: list[POIRecommendation] = []
    for keyword in must_visit:
        matched = next((poi for poi in attractions if keyword in poi.name), None)
        if matched and matched not in selected:
            selected.append(matched)

    start_index = day_index % len(attractions)
    for offset in range(len(attractions)):
        poi = attractions[(start_index + offset) % len(attractions)]
        if poi in selected:
            continue
        selected.append(poi)
        if len(selected) >= 2:
            break
    return selected


def preferred_mode(request: TripPlanningRequest) -> str:
    preferences = request.transport_preferences
    if "\u6b65\u884c" in preferences:
        return "walking"
    if "\u516c\u5171\u4ea4\u901a" in preferences:
        return "transit"
    if "\u9a91\u884c" in preferences:
        return "bicycling"
    if "\u81ea\u9a7e" in preferences:
        return "driving"
    return "driving"


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat_scale = 111.0
    lon_scale = 111.0 * max(0.1, math.cos(math.radians((lat1 + lat2) / 2)))
    lat_distance = (lat1 - lat2) * lat_scale
    lon_distance = (lon1 - lon2) * lon_scale
    return math.sqrt(lat_distance * lat_distance + lon_distance * lon_distance)


def average_distance_km(
    origin: POIRecommendation,
    targets: list[POIRecommendation],
) -> float:
    if origin.longitude is None or origin.latitude is None:
        return float("inf")

    distances: list[float] = []
    for target in targets[:3]:
        if target.longitude is None or target.latitude is None:
            continue
        distances.append(
            distance_km(
                origin.latitude,
                origin.longitude,
                target.latitude,
                target.longitude,
            )
        )

    if not distances:
        return float("inf")
    return sum(distances) / len(distances)


def select_origin(
    hotels: list[POIRecommendation],
    route_points: list[POIRecommendation],
) -> POIRecommendation:
    if not hotels:
        return route_points[0]

    scored: list[tuple[float, POIRecommendation]] = []
    for hotel in hotels:
        distance = average_distance_km(hotel, route_points)
        scored.append((distance, hotel))

    scored.sort(key=lambda item: item[0])
    best_distance, best_hotel = scored[0]
    if best_distance == float("inf") or best_distance > 25:
        return route_points[0]
    return best_hotel
