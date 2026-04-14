from __future__ import annotations

from typing import Any

from app.schemas.planning import POIRecommendation, ToolCallRecord, TripPlanningRequest, WeatherSummary
from app.services.amap_mcp_detail import (
    enrich_pois_with_details as enrich_pois_with_details_runtime,
)
from app.services.amap_mcp_discovery import (
    fetch_attractions as fetch_attractions_runtime,
    fetch_hotels as fetch_hotels_runtime,
    fetch_hotels_for_locations as fetch_hotels_for_locations_runtime,
    fetch_restaurants as fetch_restaurants_runtime,
    fetch_restaurants_for_locations as fetch_restaurants_for_locations_runtime,
)
from app.services.amap_mcp_poi import (
    adaptive_poi_search_plan as adaptive_poi_search_plan_poi,
    search_poi_candidates as search_poi_candidates_runtime,
)
from app.services.amap_mcp_selection import (
    resolve_location_candidate as resolve_location_candidate_selection,
)


class AmapMCPAdapterDiscoveryApiMixin:
    async def fetch_attractions(
        self, request: TripPlanningRequest, trace: list[ToolCallRecord]
    ) -> list[POIRecommendation]:
        return await fetch_attractions_runtime(
            request=request,
            trace=trace,
            search_poi_candidates_fn=self._search_poi_candidates,
            enrich_pois_with_details_fn=self._enrich_pois_with_details,
            filter_pois_by_geo_scope_fn=self._filter_pois_by_geo_scope,
            sort_pois_by_city_center_fn=self._sort_pois_by_city_center,
        )

    async def fetch_restaurants(
        self,
        request: TripPlanningRequest,
        trace: list[ToolCallRecord],
        anchor_pois: list[POIRecommendation] | None = None,
    ) -> list[POIRecommendation]:
        return await fetch_restaurants_runtime(
            request=request,
            trace=trace,
            anchor_pois=anchor_pois or [],
            search_poi_candidates_fn=self._search_poi_candidates,
            enrich_pois_with_details_fn=self._enrich_pois_with_details,
            filter_pois_by_geo_scope_fn=self._filter_pois_by_geo_scope,
            sort_restaurants_for_route_fn=self._sort_restaurants_for_route,
        )

    async def fetch_restaurants_for_locations(
        self,
        request: TripPlanningRequest,
        trace: list[ToolCallRecord],
        location_names: list[str],
        area_hint: str = "",
        stay_hint: str = "",
    ) -> list[POIRecommendation]:
        return await fetch_restaurants_for_locations_runtime(
            request=request,
            trace=trace,
            location_names=location_names,
            area_hint=area_hint,
            stay_hint=stay_hint,
            dedupe_queries_fn=self._dedupe_queries,
            resolve_location_candidate_fn=self.resolve_location_candidate,
            search_poi_candidates_fn=self._search_poi_candidates,
            enrich_pois_with_details_fn=self._enrich_pois_with_details,
            filter_pois_by_geo_scope_fn=self._filter_pois_by_geo_scope,
            sort_restaurants_for_route_fn=self._sort_restaurants_for_route,
        )

    async def fetch_hotels(
        self,
        request: TripPlanningRequest,
        trace: list[ToolCallRecord],
        anchor_pois: list[POIRecommendation] | None = None,
    ) -> list[POIRecommendation]:
        return await fetch_hotels_runtime(
            request=request,
            trace=trace,
            anchor_pois=anchor_pois or [],
            build_hotel_queries_fn=self._build_hotel_queries,
            search_poi_candidates_fn=self._search_poi_candidates,
            enrich_pois_with_details_fn=self._enrich_pois_with_details,
            filter_pois_by_geo_scope_fn=self._filter_pois_by_geo_scope,
            sort_hotels_for_stay_fn=self._sort_hotels_for_stay,
        )

    async def fetch_hotels_for_locations(
        self,
        request: TripPlanningRequest,
        trace: list[ToolCallRecord],
        location_names: list[str],
        area_hint: str = "",
    ) -> list[POIRecommendation]:
        return await fetch_hotels_for_locations_runtime(
            request=request,
            trace=trace,
            location_names=location_names,
            area_hint=area_hint,
            dedupe_queries_fn=self._dedupe_queries,
            resolve_location_candidate_fn=self.resolve_location_candidate,
            search_poi_candidates_fn=self._search_poi_candidates,
            enrich_pois_with_details_fn=self._enrich_pois_with_details,
            filter_pois_by_geo_scope_fn=self._filter_pois_by_geo_scope,
            sort_hotels_for_stay_fn=self._sort_hotels_for_stay,
        )

    async def resolve_location_candidate(
        self,
        city: str,
        location_name: str,
        trace: list[ToolCallRecord],
        anchor_pois: list[POIRecommendation] | None = None,
    ) -> POIRecommendation | None:
        return await resolve_location_candidate_selection(
            city=city,
            location_name=location_name,
            trace=trace,
            anchor_pois=anchor_pois,
            location_candidate_cache=self._location_candidate_cache,
            location_candidate_simple_cache=self._location_candidate_simple_cache,
            location_candidate_cache_key_fn=self._location_candidate_cache_key,
            location_candidate_simple_cache_key_fn=self._location_candidate_simple_cache_key,
            cache_location_candidate=self._cache_location_candidate,
            cache_location_candidate_simple=self._cache_location_candidate_simple,
            is_simple_cached_candidate_usable_fn=self._is_simple_cached_candidate_usable,
            search_poi_candidates=self._search_poi_candidates,
            filter_pois_by_geo_scope=self._filter_pois_by_geo_scope,
            location_name_match_score_fn=self._location_name_match_score,
            poi_detail_is_complete=self._poi_detail_is_complete,
            enrich_pois_with_details=self._enrich_pois_with_details,
            merge_unique_pois=self._merge_unique_pois,
        )

    async def fetch_weather(
        self, request: TripPlanningRequest, trace: list[ToolCallRecord]
    ) -> WeatherSummary:
        raw = await self._call_tool_for_purpose(
            "weather",
            {"city": request.destination},
            trace,
        )
        return self._normalize_weather(raw, request)

    async def _enrich_pois_with_details(
        self,
        pois: list[POIRecommendation],
        trace: list[ToolCallRecord],
        category: str | None = None,
    ) -> list[POIRecommendation]:
        return await enrich_pois_with_details_runtime(
            pois=pois,
            trace=trace,
            category=category,
            has_client=self.client is not None,
            poi_detail_limit=self._poi_detail_limit,
            poi_detail_concurrency=self._poi_detail_concurrency,
            poi_detail_cache=self._poi_detail_cache,
            resolve_search_detail_tool_name_fn=self._resolve_search_detail_tool_name,
            call_tool_for_purpose_fn=self._call_tool_for_purpose,
            normalize_poi_detail_fn=self._normalize_poi_detail,
            poi_detail_is_complete_fn=self._poi_detail_is_complete,
            is_rate_limit_error_fn=self._is_rate_limit_error,
        )

    async def _search_poi_candidates(
        self,
        city: str,
        queries: list[str],
        trace: list[ToolCallRecord],
        fallback_kind: str,
        target_count: int,
    ) -> list[POIRecommendation]:
        return await search_poi_candidates_runtime(
            city=city,
            queries=queries,
            trace=trace,
            fallback_kind=fallback_kind,
            target_count=target_count,
            build_poi_search_arguments=self._build_poi_search_arguments,
            call_tool_for_purpose=lambda purpose, arguments, inner_trace: self._call_tool_for_purpose(
                purpose,
                arguments,
                inner_trace,
            ),
            normalize_pois=lambda raw, fallback: self._normalize_pois(raw, fallback_kind=fallback),
            merge_unique_pois=self._merge_unique_pois,
            record_adaptive_retry_result=self._record_adaptive_retry_result,
            is_rate_limit_error=self._is_rate_limit_error,
            poi_query_budget_fn=self._poi_query_budget,
            adaptive_poi_search_plan_fn=self._adaptive_poi_search_plan,
            consecutive_empty_stop=self._poi_search_consecutive_empty_stop,
        )

    async def _adaptive_poi_search_plan(self, base_query_budget: int) -> tuple[int, tuple[str, ...]]:
        window = max(1, int(self.settings.amap_mcp_adaptive_retry_window))
        min_samples = max(1, int(self.settings.amap_mcp_adaptive_retry_min_samples))
        low_success_rate = float(self.settings.amap_mcp_adaptive_retry_low_success_rate)
        async with self._adaptive_retry_lock:
            state = self._adaptive_retry_state_item("poi_search", window)
            recent = list(state["recent"])
            consecutive_failures = int(state.get("consecutive_failures", 0))
        return adaptive_poi_search_plan_poi(
            adaptive_retry_enabled=self._adaptive_retry_enabled(),
            base_query_budget=base_query_budget,
            recent_results=recent,
            min_samples=min_samples,
            low_success_rate=low_success_rate,
            consecutive_failures=consecutive_failures,
        )
