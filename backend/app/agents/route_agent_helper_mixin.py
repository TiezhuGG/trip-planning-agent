from app.agents.route_agent_day_planning import (
    plan_routes_for_day as plan_routes_for_day_runtime,
)
from app.agents.route_agent_locations import (
    activity_alias_variants as activity_alias_variants_runtime,
    add_location_variant as add_location_variant_runtime,
    append_activity_variants as append_activity_variants_runtime,
    build_activity_location_queries as build_activity_location_queries_runtime,
    expand_location_variants as expand_location_variants_runtime,
    match_known_point as match_known_point_runtime,
    match_trusted_candidate as match_trusted_candidate_runtime,
    named_location_cache_key as named_location_cache_key_runtime,
    normalize_location_name as normalize_location_name_runtime,
    poi_matches_expected_name as poi_matches_expected_name_runtime,
    should_rebind_named_poi as should_rebind_named_poi_runtime,
    should_rebind_poi as should_rebind_poi_runtime,
    trusted_candidates as trusted_candidates_runtime,
)
from app.agents.route_agent_planning import (
    average_distance_km as average_distance_km_runtime,
    dedupe_points as dedupe_points_runtime,
    distance_km as distance_km_runtime,
    preferred_mode as preferred_mode_runtime,
    select_day_attractions as select_day_attractions_runtime,
    select_origin as select_origin_runtime,
    take_coordinate_points as take_coordinate_points_runtime,
)
from app.agents.route_agent_support import (
    build_synthetic_origin as build_synthetic_origin_runtime,
    build_unique_day_pois as build_unique_day_pois_runtime,
    dedupe_route_nodes as dedupe_route_nodes_runtime,
    ensure_route_ready_poi as ensure_route_ready_poi_runtime,
    fallback_day_route as fallback_day_route_runtime,
)
from app.schemas.planning import DayPOI, DayPlan, POIRecommendation, PlanningContext, RouteSummary, ToolCallRecord, TripPlanningRequest


class RoutePlanningAgentHelperMixin:
    def _take_coordinate_points(
        self,
        points: list[POIRecommendation],
        limit: int,
    ) -> list[POIRecommendation]:
        return take_coordinate_points_runtime(points, limit)

    def _dedupe_points(self, points: list[POIRecommendation]) -> list[POIRecommendation]:
        return dedupe_points_runtime(points)

    def _select_day_attractions(
        self,
        attractions: list[POIRecommendation],
        day_index: int,
        must_visit: list[str],
    ) -> list[POIRecommendation]:
        return select_day_attractions_runtime(attractions, day_index, must_visit)

    def _preferred_mode(self, request: TripPlanningRequest) -> str:
        return preferred_mode_runtime(request)

    def _select_origin(
        self,
        hotels: list[POIRecommendation],
        route_points: list[POIRecommendation],
    ) -> POIRecommendation:
        return select_origin_runtime(hotels, route_points)

    def _average_distance_km(
        self,
        origin: POIRecommendation,
        targets: list[POIRecommendation],
    ) -> float:
        return average_distance_km_runtime(origin, targets)

    def _distance_km(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        return distance_km_runtime(lat1, lon1, lat2, lon2)

    async def _plan_routes_for_day(
        self,
        request: TripPlanningRequest,
        day: DayPlan,
        context: PlanningContext,
        trace: list[ToolCallRecord],
        segment_concurrency: int | None = None,
    ) -> tuple[list[RouteSummary], bool, str | None]:
        return await plan_routes_for_day_runtime(
            request=request,
            day=day,
            context=context,
            trace=trace,
            segment_concurrency=segment_concurrency,
            default_segment_concurrency=self._segment_concurrency,
            adapter=self.adapter,
            preferred_mode_fn=self._preferred_mode,
            resolve_origin_for_day_fn=self._resolve_origin_for_day,
            resolve_activity_points_fn=self._resolve_activity_points,
            dedupe_route_nodes_fn=self._dedupe_route_nodes,
            build_synthetic_origin_fn=self._build_synthetic_origin,
            fallback_day_route_fn=self._fallback_day_route,
        )

    def _named_location_cache_key(
        self,
        city: str,
        location_name: str,
        anchor_points: list[POIRecommendation],
    ) -> str:
        return named_location_cache_key_runtime(city, location_name, anchor_points)

    def _match_known_point(
        self,
        location_name: str,
        candidates: list[POIRecommendation],
        allow_contains: bool = True,
    ) -> POIRecommendation | None:
        return match_known_point_runtime(location_name, candidates, allow_contains)

    def _dedupe_route_nodes(
        self,
        nodes: list[tuple[POIRecommendation, str]],
    ) -> list[tuple[POIRecommendation, str]]:
        return dedupe_route_nodes_runtime(nodes)

    def _build_unique_day_pois(
        self,
        pois: list[DayPOI],
    ) -> list[DayPOI]:
        return build_unique_day_pois_runtime(pois)

    def _should_rebind_poi(self, poi: POIRecommendation | None) -> bool:
        return should_rebind_poi_runtime(poi)

    def _should_rebind_named_poi(
        self,
        expected_name: str,
        poi: POIRecommendation | None,
        activity_title: str = "",
    ) -> bool:
        return should_rebind_named_poi_runtime(expected_name, poi, activity_title)

    def _trusted_candidates(
        self,
        candidates: list[POIRecommendation | None],
    ) -> list[POIRecommendation]:
        return trusted_candidates_runtime(candidates)

    def _match_trusted_candidate(
        self,
        expected_name: str,
        candidates: list[POIRecommendation],
        activity_title: str = "",
    ) -> POIRecommendation | None:
        return match_trusted_candidate_runtime(expected_name, candidates, activity_title)

    def _poi_matches_expected_name(
        self,
        poi: POIRecommendation,
        references: list[str],
    ) -> bool:
        return poi_matches_expected_name_runtime(poi, references)

    def _build_activity_location_queries(
        self,
        location_name: str,
        activity_title: str,
    ) -> list[str]:
        return build_activity_location_queries_runtime(location_name, activity_title)

    def _append_activity_variants(
        self,
        variants: list[str],
        value: str,
    ) -> None:
        append_activity_variants_runtime(variants, value)

    def _expand_location_variants(self, value: str) -> list[str]:
        return expand_location_variants_runtime(value)

    def _activity_alias_variants(self, value: str) -> list[str]:
        return activity_alias_variants_runtime(value)

    def _add_location_variant(
        self,
        variants: list[str],
        value: str,
    ) -> None:
        add_location_variant_runtime(variants, value)

    def _ensure_route_ready_poi(
        self,
        poi: POIRecommendation,
        city: str,
    ) -> POIRecommendation:
        return ensure_route_ready_poi_runtime(poi, city)

    def _build_synthetic_origin(
        self,
        request: TripPlanningRequest,
        day: DayPlan,
    ) -> POIRecommendation:
        return build_synthetic_origin_runtime(request, day)

    def _fallback_day_route(
        self,
        day: DayPlan,
        request: TripPlanningRequest,
        origin: POIRecommendation | None,
    ) -> RouteSummary:
        return fallback_day_route_runtime(
            day,
            request,
            origin,
            self._preferred_mode(request),
        )

    def _normalize_location_name(self, value: str) -> str:
        return normalize_location_name_runtime(value)
