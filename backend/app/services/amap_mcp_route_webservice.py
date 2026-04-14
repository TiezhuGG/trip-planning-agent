from __future__ import annotations

import asyncio
from typing import Any, Callable

from app.schemas.planning import POIRecommendation, ToolCallRecord
from app.services.mcp_stdio_client import MCPProtocolError


def route_address_candidates(
    poi: POIRecommendation,
    *,
    dedupe_queries: Callable[[list[str]], list[str]],
) -> list[str]:
    candidates = [
        " ".join(part for part in [poi.district or "", poi.address or "", poi.name] if part).strip(),
        " ".join(part for part in [poi.district or "", poi.name] if part).strip(),
        " ".join(part for part in [poi.district or "", poi.address or ""] if part).strip(),
        poi.address.strip(),
        poi.name.strip(),
    ]
    return [candidate for candidate in dedupe_queries(candidates) if candidate]


async def resolve_route_location(
    *,
    poi: POIRecommendation,
    cache_key: str,
    cached_location: str | None,
    api_key: str,
    geocode_retry_attempts: int,
    async_client_factory: Callable[..., Any],
    normalize_city_name: Callable[[str | None], str],
    route_address_candidates_fn: Callable[[POIRecommendation], list[str]],
    cache_route_location: Callable[[str, str], None],
    is_rate_limit_text: Callable[[str], bool],
    retry_delay_seconds: Callable[[int], float],
    route_address: Callable[[POIRecommendation], str],
) -> str:
    if poi.longitude is not None and poi.latitude is not None:
        return f"{poi.longitude},{poi.latitude}"

    if cached_location:
        return cached_location

    if not api_key:
        raise MCPProtocolError("缺少高德 Web Service Key，无法为路线规划补做 geocode。")

    city = normalize_city_name(poi.district)
    async with async_client_factory(timeout=15, trust_env=False) as client:
        for candidate in route_address_candidates_fn(poi):
            for attempt in range(geocode_retry_attempts):
                response = await client.get(
                    "https://restapi.amap.com/v3/geocode/geo",
                    params={
                        "key": api_key,
                        "address": candidate,
                        "city": city,
                    },
                )
                response.raise_for_status()
                payload = response.json()
                if str(payload.get("status", "")) == "1":
                    geocodes = payload.get("geocodes")
                    if isinstance(geocodes, list) and geocodes and geocodes[0].get("location"):
                        location = str(geocodes[0]["location"])
                        cache_route_location(cache_key, location)
                        return location

                info_text = str(payload.get("info", payload.get("infocode", "")))
                if attempt < geocode_retry_attempts - 1 and is_rate_limit_text(info_text):
                    await asyncio.sleep(retry_delay_seconds(attempt))
                    continue
                break

    raise MCPProtocolError(f"未能为地址解析坐标: {route_address(poi)}")


async def plan_transit_via_web_service(
    *,
    origin: POIRecommendation,
    destination: POIRecommendation,
    trace: list[ToolCallRecord],
    api_key: str,
    async_client_factory: Callable[..., Any],
    resolve_route_location: Callable[[POIRecommendation], Any],
    normalize_city_name: Callable[[str | None], str],
    summarize_tool_payload: Callable[[Any], str],
) -> dict[str, Any]:
    if not api_key:
        raise MCPProtocolError("未配置高德 Web Service Key，无法走公交路线直连兜底。")

    origin_location = await resolve_route_location(origin)
    destination_location = await resolve_route_location(destination)
    arguments = {
        "origin": origin_location,
        "destination": destination_location,
        "city": normalize_city_name(origin.district),
        "cityd": normalize_city_name(destination.district),
    }

    async with async_client_factory(timeout=20, trust_env=False) as client:
        response = await client.get(
            "https://restapi.amap.com/v3/direction/transit/integrated",
            params={
                "key": api_key,
                **arguments,
            },
        )
        response.raise_for_status()
        payload = response.json()

    if str(payload.get("status", "")) != "1":
        raise MCPProtocolError(
            f"高德公交 Web Service 返回错误: {payload.get('info') or payload.get('infocode') or payload}"
        )
    route = payload.get("route")
    if not isinstance(route, dict) or not isinstance(route.get("transits"), list) or not route.get("transits"):
        raise MCPProtocolError("高德公交 Web Service 未返回可用 transit 方案。")

    normalized_payload = {
        "route": {
            "origin": route.get("origin", origin_location),
            "destination": route.get("destination", destination_location),
            "distance": route.get("distance", route.get("taxi_cost", "")),
            "transits": route.get("transits", []),
        }
    }
    trace.append(
        ToolCallRecord(
            tool_name="amap_webservice_transit_integrated",
            arguments=arguments,
            success=True,
            summary=f"工具调用成功 (route_plan) {summarize_tool_payload(normalized_payload)}",
        )
    )
    return normalized_payload


async def plan_route_via_web_service(
    *,
    mode: str,
    origin: POIRecommendation,
    destination: POIRecommendation,
    waypoints: list[POIRecommendation],
    trace: list[ToolCallRecord],
    api_key: str,
    async_client_factory: Callable[..., Any],
    resolve_route_location: Callable[[POIRecommendation], Any],
    normalize_city_name: Callable[[str | None], str],
    summarize_tool_payload: Callable[[Any], str],
    plan_transit_via_web_service_fn: Callable[[POIRecommendation, POIRecommendation, list[ToolCallRecord]], Any],
) -> dict[str, Any]:
    if mode == "transit":
        return await plan_transit_via_web_service_fn(origin, destination, trace)

    if not api_key:
        raise MCPProtocolError("未配置高德 Web Service Key，无法走路线直连兜底。")

    origin_location = await resolve_route_location(origin)
    destination_location = await resolve_route_location(destination)
    endpoint = {
        "driving": "https://restapi.amap.com/v3/direction/driving",
        "walking": "https://restapi.amap.com/v3/direction/walking",
    }.get(mode)
    if not endpoint:
        raise MCPProtocolError(f"不支持的 Web Service 路线模式: {mode}")

    arguments: dict[str, Any] = {
        "origin": origin_location,
        "destination": destination_location,
    }
    if mode == "driving":
        waypoint_locations = [
            location
            for location in [await resolve_route_location(poi) for poi in waypoints[:3]]
            if location and location not in {origin_location, destination_location}
        ]
        if waypoint_locations:
            arguments["waypoints"] = "|".join(waypoint_locations)

    async with async_client_factory(timeout=20, trust_env=False) as client:
        response = await client.get(
            endpoint,
            params={
                "key": api_key,
                **arguments,
            },
        )
        response.raise_for_status()
        payload = response.json()

    if str(payload.get("status", "")) != "1":
        raise MCPProtocolError(
            f"高德 {mode} Web Service 返回错误: {payload.get('info') or payload.get('infocode') or payload}"
        )

    trace.append(
        ToolCallRecord(
            tool_name=f"amap_webservice_{mode}",
            arguments=arguments,
            success=True,
            summary=f"工具调用成功 (route_plan) {summarize_tool_payload(payload)}",
        )
    )
    return payload
