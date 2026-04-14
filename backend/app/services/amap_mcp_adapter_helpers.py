from __future__ import annotations

from typing import Any

from app.schemas.planning import (
    GeoPoint,
    POIRecommendation,
    PlanningContext,
    RouteSummary,
    ToolCallRecord,
    TripPlanningRequest,
    WeatherSummary,
)
from app.services.amap_mcp_normalization import (
    extract_coordinates as extract_coordinates_normalized,
    extract_polyline_points as extract_polyline_points_normalized,
    extract_poi_detail_record as extract_poi_detail_record_normalized,
    extract_poi_items as extract_poi_items_normalized,
    normalize_poi_detail as normalize_poi_detail_runtime,
    normalize_pois as normalize_pois_runtime,
    normalize_route as normalize_route_runtime,
    normalize_tags as normalize_tags_runtime,
    normalize_weather as normalize_weather_runtime,
)
from app.services.amap_mcp_payloads import (
    format_connection_error as format_connection_error_runtime,
    raise_on_tool_error as raise_on_tool_error_runtime,
    summarize_tool_payload as summarize_tool_payload_runtime,
    unwrap_tool_result as unwrap_tool_result_runtime,
)
from app.services.amap_mcp_poi import (
    dedupe_queries as dedupe_queries_poi,
    poi_query_budget as poi_query_budget_poi,
    prioritize_poi_queries as prioritize_poi_queries_poi,
)
from app.services.amap_mcp_support import (
    legacy_mock_context as legacy_mock_context_runtime,
    mock_route as mock_route_runtime,
)


class AmapMCPAdapterHelpersMixin:
    def _poi_detail_is_complete(
        self,
        poi: POIRecommendation,
        category: str | None = None,
    ) -> bool:
        _ = category
        return (
            bool((poi.district or "").strip())
            and bool(poi.tags)
            and poi.longitude is not None
            and poi.latitude is not None
        )

    def _build_poi_search_arguments(
        self,
        city: str,
        keywords: str,
        citylimit: str = "true",
    ) -> dict[str, Any]:
        return {
            "keywords": keywords,
            "city": city,
            "citylimit": citylimit,
        }

    def _dedupe_queries(self, queries: list[str]) -> list[str]:
        return dedupe_queries_poi(queries)

    def _prioritize_poi_queries(self, queries: list[str]) -> list[str]:
        return prioritize_poi_queries_poi(queries)

    def _poi_query_budget(self, target_count: int, total_queries: int) -> int:
        return poi_query_budget_poi(
            target_count=target_count,
            total_queries=total_queries,
            budget_floor=self._poi_query_budget_floor,
            budget_cap=self._poi_query_budget_cap,
        )

    def _normalize_city_name(self, value: str | None) -> str:
        if not value:
            return ""
        normalized = value.strip()
        for suffix in ("\u5e02", "\u533a", "\u53bf"):
            if normalized.endswith(suffix) and len(normalized) > 1:
                normalized = normalized[:-1]
                break
        return normalized

    def _format_connection_error(self, exc: Exception) -> str:
        return format_connection_error_runtime(
            exc=exc,
            client=self.client,
            command=self.settings.amap_mcp_command,
        )

    def _unwrap_tool_result(self, result: Any) -> Any:
        return unwrap_tool_result_runtime(result)

    def _raise_on_tool_error(self, payload: Any, tool_name: str) -> None:
        raise_on_tool_error_runtime(payload, tool_name)

    def _summarize_tool_payload(self, payload: Any) -> str:
        return summarize_tool_payload_runtime(payload)

    def _normalize_pois(self, raw: Any, fallback_kind: str) -> list[POIRecommendation]:
        return normalize_pois_runtime(
            raw,
            fallback_kind=fallback_kind,
            to_float=self._to_float,
            to_int=self._to_int,
        )

    def _normalize_poi_detail(self, raw: Any, fallback: POIRecommendation) -> POIRecommendation:
        return normalize_poi_detail_runtime(
            raw,
            fallback=fallback,
            to_float=self._to_float,
        )

    def _extract_poi_items(self, raw: Any) -> list[dict[str, Any]]:
        return extract_poi_items_normalized(raw)

    def _extract_poi_detail_record(self, raw: Any) -> dict[str, Any] | None:
        return extract_poi_detail_record_normalized(raw)

    def _normalize_weather(self, raw: Any, request: TripPlanningRequest) -> WeatherSummary:
        return normalize_weather_runtime(
            raw,
            request=request,
            to_int=self._to_int,
        )

    def _normalize_route_runtime(
        self,
        raw: Any,
        *,
        day_number: int,
        origin: POIRecommendation,
        destination: POIRecommendation,
        waypoints: list[POIRecommendation],
        mode: str,
    ) -> RouteSummary:
        return normalize_route_runtime(
            raw,
            day_number=day_number,
            origin=origin,
            destination=destination,
            waypoints=waypoints,
            mode=mode,
            extract_polyline_points_fn=self._extract_polyline_points,
            fallback_polyline_fn=self._fallback_polyline,
            format_distance_text_fn=self._format_distance_text,
            format_duration_text_fn=self._format_duration_text,
            extract_transport_cost_cny_fn=self._extract_transport_cost_cny,
        )

    def _legacy_mock_context(
        self,
        request: TripPlanningRequest,
    ) -> tuple[PlanningContext, list[ToolCallRecord]]:
        return legacy_mock_context_runtime(request)

    def _mock_route(
        self,
        day_number: int,
        origin: POIRecommendation,
        destination: POIRecommendation,
        waypoints: list[POIRecommendation],
        mode: str,
    ) -> RouteSummary:
        return mock_route_runtime(day_number, origin, destination, waypoints, mode)

    def _normalize_tags(self, item: dict[str, Any]) -> list[str]:
        return normalize_tags_runtime(item)

    def _extract_coordinates_runtime(self, item: dict[str, Any]) -> tuple[float | None, float | None]:
        return extract_coordinates_normalized(item, to_float=self._to_float)

    def _extract_polyline_points_runtime(self, raw_polyline: Any) -> list[GeoPoint]:
        return extract_polyline_points_normalized(raw_polyline, to_float=self._to_float)
