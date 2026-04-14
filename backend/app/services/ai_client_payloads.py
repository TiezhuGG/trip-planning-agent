from __future__ import annotations

import json
from typing import Any

from app.schemas.planning import PlanningContext, RouteSummary, ToolCallRecord


def compact_tool_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key in (
        "keywords",
        "city",
        "origin",
        "destination",
        "origin_address",
        "destination_address",
        "mode",
    ):
        value = arguments.get(key)
        if value not in (None, "", []):
            compact[key] = value
    return compact


def serialize_poi_for_llm(poi: Any) -> dict[str, Any]:
    return {
        "name": getattr(poi, "name", ""),
        "address": getattr(poi, "address", ""),
        "district": getattr(poi, "district", None),
        "tags": list(getattr(poi, "tags", [])[:3]),
        "opening_hours": getattr(poi, "opening_hours", None),
        "rating": getattr(poi, "rating", None),
    }


def serialize_route_for_llm(route: RouteSummary, step_limit: int) -> dict[str, Any]:
    return {
        "day_number": route.day_number,
        "title": route.title,
        "from_name": route.from_name,
        "to_name": route.to_name,
        "waypoints": route.waypoints[:4],
        "distance_text": route.distance_text,
        "duration_text": route.duration_text,
        "mode": route.mode,
        "estimated_transport_cost_cny": route.estimated_transport_cost_cny,
        "steps": [step.model_dump(mode="json") for step in route.steps[:step_limit]],
    }


def serialize_tool_trace_for_llm(
    tool_trace: list[ToolCallRecord],
    detail_level: str,
) -> list[dict[str, Any]]:
    limit = {"full": 10, "compact": 6, "minimal": 3}[detail_level]
    serialized: list[dict[str, Any]] = []
    for item in tool_trace[:limit]:
        serialized.append(
            {
                "tool_name": item.tool_name,
                "success": item.success,
                "summary": item.summary[:180],
                "arguments": compact_tool_arguments(item.arguments),
            }
        )
    return serialized


def serialize_context_for_llm(context: PlanningContext, detail_level: str) -> dict[str, Any]:
    poi_limit = {"full": 6, "compact": 4, "minimal": 2}[detail_level]
    route_limit = {"full": 5, "compact": 3, "minimal": 2}[detail_level]
    step_limit = {"full": 3, "compact": 2, "minimal": 1}[detail_level]
    return {
        "destination": context.destination,
        "attractions": [serialize_poi_for_llm(item) for item in context.attractions[:poi_limit]],
        "restaurants": [serialize_poi_for_llm(item) for item in context.restaurants[:poi_limit]],
        "hotels": [serialize_poi_for_llm(item) for item in context.hotels[:poi_limit]],
        "routes": [
            serialize_route_for_llm(item, step_limit=step_limit)
            for item in context.routes[:route_limit]
        ],
        "weather": {
            "overview": context.weather.overview,
            "temperature_range": context.weather.temperature_range,
            "suggestions": context.weather.suggestions[:3],
            "daily_forecasts": [
                item.model_dump(mode="json")
                for item in context.weather.daily_forecasts[: max(2, route_limit)]
            ],
        },
    }


def build_compose_user_payload(
    *,
    request_payload: dict[str, Any],
    initial_plan_payload: dict[str, Any],
    context: PlanningContext,
    tool_trace: list[ToolCallRecord],
) -> dict[str, Any]:
    for detail_level in ("full", "compact", "minimal"):
        payload = {
            "request": request_payload,
            "initial_plan": initial_plan_payload,
            "planning_context": serialize_context_for_llm(context, detail_level),
            "tool_trace": serialize_tool_trace_for_llm(tool_trace, detail_level),
        }
        if len(json.dumps(payload, ensure_ascii=True)) <= 180000:
            return payload

    return {
        "request": request_payload,
        "initial_plan": initial_plan_payload,
        "planning_context": serialize_context_for_llm(context, "minimal"),
        "tool_trace": serialize_tool_trace_for_llm(tool_trace, "minimal"),
    }
