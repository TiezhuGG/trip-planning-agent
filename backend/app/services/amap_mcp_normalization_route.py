from __future__ import annotations

from typing import Any, Callable

from app.schemas.planning import GeoPoint, POIRecommendation, RouteStep, RouteSummary


_STEP_CONTINUE_STRAIGHT = "\u7ee7\u7eed\u76f4\u884c"
_STEP_WALK_TO_NEXT_STOP = "\u6b65\u884c\u524d\u5f80\u4e0b\u4e00\u7ad9"
_TRANSIT_FALLBACK_NAME = "\u516c\u5171\u4ea4\u901a"
_TAKE_TRANSIT_TEMPLATE = "\u4e58\u5750 {name}"
_BOARD_TEMPLATE = "\uff0c\u4ece {name} \u4e0a\u8f66"
_ALIGHT_TEMPLATE = "\uff0c\u5230 {name} \u4e0b\u8f66"
_ROUTE_TITLE_TEMPLATE = "\u7b2c {day_number} \u5929\u8def\u7ebf"
_PENDING_TEXT = "\u5f85\u5de5\u5177\u8fd4\u56de"


def extract_polyline_points(
    raw_polyline: Any,
    *,
    to_float: Callable[[Any], float | None],
) -> list[GeoPoint]:
    points: list[GeoPoint] = []
    if isinstance(raw_polyline, str):
        for segment in raw_polyline.split(";"):
            if "," not in segment:
                continue
            longitude_text, latitude_text = segment.split(",", 1)
            longitude = to_float(longitude_text)
            latitude = to_float(latitude_text)
            if longitude is None or latitude is None:
                continue
            points.append(GeoPoint(longitude=longitude, latitude=latitude))
    elif isinstance(raw_polyline, list):
        for item in raw_polyline:
            if isinstance(item, dict):
                longitude = to_float(item.get("lng", item.get("longitude")))
                latitude = to_float(item.get("lat", item.get("latitude")))
                if longitude is not None and latitude is not None:
                    points.append(GeoPoint(longitude=longitude, latitude=latitude))
    return points


def normalize_route(
    raw: Any,
    *,
    day_number: int,
    origin: POIRecommendation,
    destination: POIRecommendation,
    waypoints: list[POIRecommendation],
    mode: str,
    extract_polyline_points_fn: Callable[[Any], list[GeoPoint]],
    fallback_polyline_fn: Callable[[POIRecommendation, POIRecommendation, list[POIRecommendation]], list[GeoPoint]],
    format_distance_text_fn: Callable[[str], str],
    format_duration_text_fn: Callable[[str], str],
    extract_transport_cost_cny_fn: Callable[[Any, Any, str], float | None],
) -> RouteSummary:
    route_root = raw.get("route") if isinstance(raw, dict) and isinstance(raw.get("route"), dict) else None
    route_data = route_root if route_root is not None else raw
    if isinstance(route_data, dict) and isinstance(route_data.get("paths"), list) and route_data["paths"]:
        route_data = route_data["paths"][0]
    elif isinstance(route_data, dict) and isinstance(route_data.get("transits"), list) and route_data["transits"]:
        route_data = route_data["transits"][0]

    distance_text = ""
    duration_text = ""
    steps: list[RouteStep] = []
    polyline: list[GeoPoint] = []

    if isinstance(route_data, dict):
        distance_text = str(route_data.get("distance_text", route_data.get("distance", "")))
        duration_text = str(route_data.get("duration_text", route_data.get("duration", "")))
        if route_root is not None:
            if not distance_text:
                distance_text = str(route_root.get("distance", route_root.get("walking_distance", "")))
            if not duration_text:
                duration_text = str(route_root.get("duration", ""))
        raw_steps = route_data.get("steps", [])
        if isinstance(raw_steps, list):
            for item in raw_steps[:8]:
                if not isinstance(item, dict):
                    continue
                steps.append(
                    RouteStep(
                        instruction=str(item.get("instruction", item.get("text", _STEP_CONTINUE_STRAIGHT))),
                        distance_text=str(item.get("distance_text", item.get("distance", ""))),
                        duration_text=str(item.get("duration_text", item.get("duration", ""))),
                    )
                )
                polyline.extend(extract_polyline_points_fn(item.get("polyline")))
                tmcs = item.get("tmcs")
                if isinstance(tmcs, list):
                    for tmc in tmcs:
                        if isinstance(tmc, dict):
                            polyline.extend(extract_polyline_points_fn(tmc.get("polyline")))

        if not polyline:
            polyline.extend(extract_polyline_points_fn(route_data.get("polyline")))

        raw_segments = route_data.get("segments", [])
        if isinstance(raw_segments, list) and raw_segments:
            for segment in raw_segments:
                if not isinstance(segment, dict):
                    continue
                walking = segment.get("walking")
                if isinstance(walking, dict):
                    walking_steps = walking.get("steps")
                    if isinstance(walking_steps, list):
                        for step in walking_steps:
                            if not isinstance(step, dict):
                                continue
                            steps.append(
                                RouteStep(
                                    instruction=str(step.get("instruction", _STEP_WALK_TO_NEXT_STOP)),
                                    distance_text=str(step.get("distance", "")),
                                    duration_text=str(step.get("duration", "")),
                                )
                            )
                bus = segment.get("bus")
                if isinstance(bus, dict):
                    buslines = bus.get("buslines", [])
                    if isinstance(buslines, list):
                        for busline in buslines[:2]:
                            if not isinstance(busline, dict):
                                continue
                            instruction = _TAKE_TRANSIT_TEMPLATE.format(
                                name=busline.get("name", _TRANSIT_FALLBACK_NAME)
                            )
                            dep = busline.get("departure_stop")
                            arr = busline.get("arrival_stop")
                            if isinstance(dep, dict) and dep.get("name"):
                                instruction += _BOARD_TEMPLATE.format(name=dep["name"])
                            if isinstance(arr, dict) and arr.get("name"):
                                instruction += _ALIGHT_TEMPLATE.format(name=arr["name"])
                            steps.append(
                                RouteStep(
                                    instruction=instruction,
                                    distance_text=str(busline.get("distance", "")),
                                    duration_text=str(busline.get("duration", "")),
                                )
                            )

    if not polyline:
        polyline = fallback_polyline_fn(origin, destination, waypoints)

    return RouteSummary(
        day_number=day_number,
        title=_ROUTE_TITLE_TEMPLATE.format(day_number=day_number),
        from_name=origin.name,
        to_name=destination.name,
        waypoints=[item.name for item in waypoints],
        distance_text=format_distance_text_fn(distance_text) or _PENDING_TEXT,
        duration_text=format_duration_text_fn(duration_text) or _PENDING_TEXT,
        mode=mode,
        estimated_transport_cost_cny=extract_transport_cost_cny_fn(route_root, route_data, mode),
        steps=steps,
        polyline=polyline,
    )
