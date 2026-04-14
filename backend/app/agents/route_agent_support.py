from __future__ import annotations

from app.schemas.planning import DayPOI, DayPlan, POIRecommendation, RouteSummary, TripPlanningRequest


def dedupe_route_nodes(
    nodes: list[tuple[POIRecommendation, str]],
) -> list[tuple[POIRecommendation, str]]:
    deduped: list[tuple[POIRecommendation, str]] = []
    seen: set[str] = set()
    for poi, label in nodes:
        key = poi.poi_id or label or poi.name
        if key in seen:
            continue
        seen.add(key)
        deduped.append((poi, label))
    return deduped


def build_unique_day_pois(
    pois: list[DayPOI],
) -> list[DayPOI]:
    deduped: list[DayPOI] = []
    seen: set[str] = set()
    for item in pois:
        key = item.poi.poi_id or f"{item.kind}:{item.poi.name}:{item.poi.address}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def ensure_route_ready_poi(
    poi: POIRecommendation,
    city: str,
) -> POIRecommendation:
    district = poi.district or city
    address = poi.address or f"{district}{poi.name}"
    return poi.model_copy(
        update={
            "district": district,
            "address": address,
        }
    )


def build_synthetic_origin(
    request: TripPlanningRequest,
    day: DayPlan,
) -> POIRecommendation:
    name = day.stay.hotel_name or day.hotel_area or request.hotel_style
    address = day.stay.area or day.hotel_area or request.destination
    return POIRecommendation(
        name=name,
        address=f"{request.destination}{address}",
        district=request.destination,
        source="stay_fallback",
    )


def fallback_day_route(
    day: DayPlan,
    request: TripPlanningRequest,
    origin: POIRecommendation | None,
    preferred_mode: str,
) -> RouteSummary:
    destination_name = day.activities[-1].location_name if day.activities else request.destination
    waypoints = [activity.location_name for activity in day.activities[:-1]]
    from_name = (
        (origin.name if origin is not None else "")
        or day.stay.hotel_name
        or day.hotel_area
        or request.hotel_style
    )
    return RouteSummary(
        day_number=day.day_number,
        title=f"第 {day.day_number} 天路线 1",
        from_name=from_name,
        to_name=destination_name,
        waypoints=waypoints,
        duration_text="约 30-45 分钟",
        mode=preferred_mode,
        estimated_transport_cost_cny=20,
        steps=[],
    )
