from __future__ import annotations

import asyncio
from typing import Any


def catalog_is_fresh(
    tool_catalog: list[dict[str, Any]] | None,
    cached_at: float,
    ttl_seconds: float,
    now: float,
    force_refresh: bool,
) -> bool:
    return (
        tool_catalog is not None
        and not force_refresh
        and (now - cached_at) <= ttl_seconds
    )


async def fetch_tool_catalog(
    client: Any,
    timeout_seconds: float,
) -> list[dict[str, Any]]:
    result = await asyncio.wait_for(
        client.list_tools(),
        timeout=timeout_seconds + 2,
    )
    tools = result.get("tools", []) if isinstance(result, dict) else []
    if not isinstance(tools, list):
        tools = []
    return [item for item in tools if isinstance(item, dict)]


def purpose_keywords(purpose: str) -> list[str]:
    return {
        "poi_search": ["text_search", "poi", "keyword", "search", "place"],
        "route_plan": ["direction", "driving", "walking", "transit", "bicycling", "address"],
        "weather": ["weather", "forecast", "climate"],
    }[purpose]


def resolve_tool_name(
    *,
    purpose: str,
    configured_name: str,
    catalog: list[dict[str, Any]],
    resolved_tools: dict[str, str],
    strict: bool = True,
) -> str | None:
    if purpose in resolved_tools:
        return resolved_tools[purpose]

    available = [item.get("name", "") for item in catalog if item.get("name")]

    if configured_name and configured_name in available:
        resolved_tools[purpose] = configured_name
        return configured_name

    best_name = ""
    best_score = -1
    keywords = purpose_keywords(purpose)
    for item in catalog:
        name = str(item.get("name", ""))
        description = str(item.get("description", ""))
        text = f"{name} {description}".lower()
        score = 0
        for keyword in keywords:
            if keyword in text:
                score += 1
        if score > best_score:
            best_score = score
            best_name = name

    if best_name and best_score > 0:
        resolved_tools[purpose] = best_name
        return best_name

    if configured_name:
        return configured_name if not strict else None
    return None


def resolve_search_detail_tool_name(catalog: list[dict[str, Any]]) -> str | None:
    available = [str(item.get("name", "")) for item in catalog if item.get("name")]
    if "maps_search_detail" in available:
        return "maps_search_detail"

    best_name = ""
    best_score = -1
    for item in catalog:
        name = str(item.get("name", ""))
        description = str(item.get("description", ""))
        text = f"{name} {description}".lower()
        score = sum(1 for keyword in ["detail", "poi", "search"] if keyword in text)
        if score > best_score:
            best_score = score
            best_name = name

    return best_name if best_name and best_score > 0 else None


def resolve_route_tool_name(
    *,
    mode: str,
    coordinate: bool | None,
    catalog: list[dict[str, Any]],
    route_plan_fallback: str,
    route_plan_resolver: Any,
) -> str | None:
    available = [str(item.get("name", "")) for item in catalog if item.get("name")]
    preferred_map = {
        ("driving", True): "maps_direction_driving_by_coordinates",
        ("driving", False): "maps_direction_driving_by_address",
        ("transit", True): "maps_direction_transit_integrated_by_coordinates",
        ("transit", False): "maps_direction_transit_integrated_by_address",
        ("walking", True): "maps_direction_walking_by_coordinates",
        ("walking", False): "maps_direction_walking_by_address",
        ("bicycling", True): "maps_bicycling_by_coordinates",
        ("bicycling", False): "maps_bicycling_by_address",
    }
    preferred = (
        preferred_map.get((mode, coordinate))
        if coordinate is not None
        else preferred_map.get((mode, False), route_plan_fallback)
    )
    if preferred in available:
        return preferred

    fallback_keywords = {
        "driving": ["driving", "direction"],
        "transit": ["transit", "integrated", "direction"],
        "walking": ["walking", "direction"],
        "bicycling": ["bicycling", "cycling", "direction"],
    }.get(mode, ["direction"])
    location_keywords = ["coordinate", "coordinates"] if coordinate is True else ["address"] if coordinate is False else []

    best_name = ""
    best_score = -1
    for item in catalog:
        name = str(item.get("name", ""))
        description = str(item.get("description", ""))
        text = f"{name} {description}".lower()
        score = sum(1 for keyword in fallback_keywords if keyword in text)
        if location_keywords and not any(keyword in text for keyword in location_keywords):
            score -= 1
        if score > best_score:
            best_score = score
            best_name = name

    if best_name and best_score > 0:
        return best_name

    return route_plan_resolver("route_plan", strict=False)


def route_mode_candidates(preferred_mode: str) -> list[str]:
    candidates = {
        "transit": ["transit", "walking", "driving"],
        "walking": ["walking", "transit", "driving"],
        "bicycling": ["bicycling", "walking", "driving"],
        "driving": ["driving"],
    }.get(preferred_mode, ["driving", "walking", "transit"])
    return list(dict.fromkeys(candidates))
