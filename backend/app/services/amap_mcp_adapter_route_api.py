from __future__ import annotations

from typing import Any

import httpx

from app.schemas.planning import POIRecommendation, RouteSummary, ToolCallRecord
from app.services.amap_mcp_route_runtime import (
    build_route_tool_attempts as build_route_tool_attempts_runtime,
    plan_route as plan_route_runtime,
    plan_route_via_web_service as plan_route_via_web_service_runtime,
    plan_transit_via_web_service as plan_transit_via_web_service_runtime,
    resolve_route_location as resolve_route_location_runtime,
)
from app.services.amap_mcp_tools import (
    resolve_route_tool_name,
    route_mode_candidates,
)


class AmapMCPAdapterRouteApiMixin:
    async def plan_route(
        self,
        day_number: int,
        origin: POIRecommendation,
        destination: POIRecommendation,
        waypoints: list[POIRecommendation],
        mode: str,
        trace: list[ToolCallRecord],
    ) -> RouteSummary:
        return await plan_route_runtime(
            day_number=day_number,
            origin=origin,
            destination=destination,
            waypoints=waypoints,
            mode=mode,
            has_client=self.client is not None,
            trace=trace,
            route_mode_candidates_fn=self._route_mode_candidates,
            build_route_tool_attempts_fn=self._build_route_tool_attempts,
            call_route_tool_with_retry_fn=self._call_route_tool_with_retry,
            call_route_webservice_with_retry_fn=self._call_route_webservice_with_retry,
            normalize_route_fn=self._normalize_route,
        )

    async def _plan_transit_via_web_service(
        self,
        origin: POIRecommendation,
        destination: POIRecommendation,
        trace: list[ToolCallRecord],
    ) -> dict[str, Any]:
        return await plan_transit_via_web_service_runtime(
            origin=origin,
            destination=destination,
            trace=trace,
            api_key=self._amap_web_service_key(),
            async_client_factory=httpx.AsyncClient,
            resolve_route_location=self._resolve_route_location,
            normalize_city_name=self._normalize_city_name,
            summarize_tool_payload=self._summarize_tool_payload,
        )

    async def _plan_route_via_web_service(
        self,
        mode: str,
        origin: POIRecommendation,
        destination: POIRecommendation,
        waypoints: list[POIRecommendation],
        trace: list[ToolCallRecord],
    ) -> dict[str, Any]:
        return await plan_route_via_web_service_runtime(
            mode=mode,
            origin=origin,
            destination=destination,
            waypoints=waypoints,
            trace=trace,
            api_key=self._amap_web_service_key(),
            async_client_factory=httpx.AsyncClient,
            resolve_route_location=self._resolve_route_location,
            normalize_city_name=self._normalize_city_name,
            summarize_tool_payload=self._summarize_tool_payload,
            plan_transit_via_web_service_fn=self._plan_transit_via_web_service,
        )

    def _build_route_tool_attempts(
        self,
        mode: str,
        origin: POIRecommendation,
        destination: POIRecommendation,
    ) -> list[tuple[str, dict[str, Any]]]:
        return build_route_tool_attempts_runtime(
            mode=mode,
            origin=origin,
            destination=destination,
            has_coordinates=self._has_coordinates,
            resolve_route_tool_name=self._resolve_route_tool_name,
            build_route_coordinate_arguments=self._build_route_coordinate_arguments,
            build_route_arguments=self._build_route_arguments,
        )

    async def _resolve_route_location(self, poi: POIRecommendation) -> str:
        cache_key = self._route_location_cache_key(poi)
        return await resolve_route_location_runtime(
            poi=poi,
            cache_key=cache_key,
            cached_location=self._route_location_cache.get(cache_key),
            api_key=self._amap_web_service_key(),
            geocode_retry_attempts=self._geocode_retry_attempts,
            async_client_factory=httpx.AsyncClient,
            normalize_city_name=self._normalize_city_name,
            route_address_candidates_fn=self._route_address_candidates,
            cache_route_location=self._cache_route_location,
            is_rate_limit_text=self._is_rate_limit_text,
            retry_delay_seconds=self._retry_delay_seconds,
            route_address=self._route_address,
        )

    def _resolve_route_tool_name(self, mode: str, coordinate: bool | None = None) -> str | None:
        return resolve_route_tool_name(
            mode=mode,
            coordinate=coordinate,
            catalog=self._tool_catalog or [],
            route_plan_fallback=self.settings.amap_mcp_tool_route_plan,
            route_plan_resolver=self._resolve_tool_name,
        )

    def _route_mode_candidates(self, preferred_mode: str) -> list[str]:
        return route_mode_candidates(preferred_mode)
