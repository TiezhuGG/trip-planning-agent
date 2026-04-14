from app.agents.route_agent_resolution import (
    resolve_activity_location as resolve_activity_location_runtime,
    resolve_activity_points as resolve_activity_points_runtime,
    resolve_named_location as resolve_named_location_runtime,
)
from app.schemas.planning import DayPlan, POIRecommendation, PlanningContext, ToolCallRecord, TripPlanningRequest


class RoutePlanningAgentResolutionMixin:
    async def _resolve_origin_for_day(
        self,
        request: TripPlanningRequest,
        day: DayPlan,
        context: PlanningContext,
        anchor_points: list[POIRecommendation],
        trace: list[ToolCallRecord],
    ) -> POIRecommendation | None:
        if day.stay.hotel_name:
            resolved = await self._resolve_named_location(
                city=request.destination,
                location_name=day.stay.hotel_name,
                known_points=context.hotels,
                trace=trace,
                anchor_points=context.hotels or anchor_points,
            )
            if resolved is not None:
                return resolved

        if context.hotels:
            return self._ensure_route_ready_poi(context.hotels[0], request.destination)

        if day.hotel_area:
            resolved = await self._resolve_named_location(
                city=request.destination,
                location_name=day.hotel_area,
                known_points=context.hotels,
                trace=trace,
                anchor_points=anchor_points,
            )
            if resolved is not None:
                return resolved
        return None

    async def _resolve_activity_points(
        self,
        request: TripPlanningRequest,
        day: DayPlan,
        context: PlanningContext,
        anchor_points: list[POIRecommendation],
        trace: list[ToolCallRecord],
    ) -> list[tuple[POIRecommendation, str]]:
        return await resolve_activity_points_runtime(
            request_destination=request.destination,
            day=day,
            context=context,
            anchor_points=anchor_points,
            trace=trace,
            activity_resolve_concurrency=self._activity_resolve_concurrency,
            resolve_activity_location_fn=self._resolve_activity_location,
            ensure_route_ready_poi_fn=self._ensure_route_ready_poi,
        )

    async def _resolve_activity_location(
        self,
        city: str,
        location_name: str,
        activity_title: str,
        context: PlanningContext,
        trace: list[ToolCallRecord],
        anchor_points: list[POIRecommendation],
    ) -> POIRecommendation | None:
        return await resolve_activity_location_runtime(
            city=city,
            location_name=location_name,
            activity_title=activity_title,
            context=context,
            trace=trace,
            anchor_points=anchor_points,
            build_activity_location_queries_fn=self._build_activity_location_queries,
            match_known_point_fn=self._match_known_point,
            ensure_route_ready_poi_fn=self._ensure_route_ready_poi,
            resolve_named_location_fn=self._resolve_named_location,
        )

    async def _resolve_named_location(
        self,
        city: str,
        location_name: str,
        known_points: list[POIRecommendation],
        trace: list[ToolCallRecord],
        anchor_points: list[POIRecommendation],
    ) -> POIRecommendation | None:
        return await resolve_named_location_runtime(
            city=city,
            location_name=location_name,
            known_points=known_points,
            trace=trace,
            anchor_points=anchor_points,
            named_location_cache=self._named_location_cache,
            named_location_cache_key_fn=self._named_location_cache_key,
            match_known_point_fn=self._match_known_point,
            ensure_route_ready_poi_fn=self._ensure_route_ready_poi,
            adapter=self.adapter,
        )
