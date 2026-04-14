from __future__ import annotations

import asyncio
import inspect

from app.schemas.planning import (
    AgentExecution,
    DayPOI,
    DayPlan,
    InitialPlanDraft,
    POIRecommendation,
    PlanningContext,
    RouteSummary,
    ToolCallRecord,
    TravelPlan,
    TripPlanningRequest,
)


class RoutePlanningAgentOrchestrationMixin:
    async def gather(
        self,
        request: TripPlanningRequest,
        initial_plan: InitialPlanDraft,
        attractions: list[POIRecommendation],
        hotels: list[POIRecommendation],
        day_restaurants: dict[int, list[POIRecommendation]],
        trace: list[ToolCallRecord],
    ) -> tuple[list[RouteSummary], AgentExecution]:
        routes: list[RouteSummary] = []
        fallback_days = 0

        for day_index, day in enumerate(initial_plan.days):
            day_attractions = self._select_day_attractions(attractions, day_index, day.must_visit)
            meal_points = day_restaurants.get(day.day_number, [])
            attraction_pool = [*day_attractions, *attractions]
            route_points = [
                *self._take_coordinate_points(attraction_pool, 2),
                *self._take_coordinate_points(meal_points, 2),
            ]
            if not route_points:
                raise ValueError(f"第 {day.day_number} 天缺少可用于路线规划的景点或餐饮节点。")

            origin = self._select_origin(hotels, route_points)
            preferred_mode = self._preferred_mode(request)
            daily_had_fallback = False
            ordered_points = self._dedupe_points([origin, *route_points])
            if len(ordered_points) < 2:
                raise ValueError(f"第 {day.day_number} 天路线节点不足，无法拆分多段路线。")

            segment_jobs: list[tuple[int, POIRecommendation, POIRecommendation]] = []
            for segment_index in range(len(ordered_points) - 1):
                segment_origin = ordered_points[segment_index]
                segment_destination = ordered_points[segment_index + 1]
                if segment_origin == segment_destination:
                    continue
                segment_jobs.append((segment_index, segment_origin, segment_destination))

            async def _plan_segment(
                segment_index: int,
                segment_origin: POIRecommendation,
                segment_destination: POIRecommendation,
            ) -> tuple[int, RouteSummary]:
                async with semaphore:
                    route = await self.adapter.plan_route(
                        day_number=day.day_number,
                        origin=segment_origin,
                        destination=segment_destination,
                        waypoints=[],
                        mode=preferred_mode,
                        trace=trace,
                    )
                return segment_index, route.model_copy(
                    update={
                        "title": f"第 {day.day_number} 天路线 {segment_index + 1}",
                    }
                )

            semaphore = asyncio.Semaphore(max(1, self._segment_concurrency))
            segment_results = await asyncio.gather(
                *[
                    _plan_segment(segment_index, segment_origin, segment_destination)
                    for segment_index, segment_origin, segment_destination in segment_jobs
                ]
            )
            segment_results.sort(key=lambda item: item[0])
            for _, route in segment_results:
                routes.append(route)
                if route.mode != preferred_mode:
                    daily_had_fallback = True

            if daily_had_fallback:
                fallback_days += 1

        used_tools = {
            item.tool_name
            for item in trace
            if item.tool_name.startswith("maps_direction")
            or item.tool_name.startswith("maps_bicycling")
            or item.tool_name.startswith("amap_webservice_")
        }

        summary = f"已生成 {len(routes)} 条分段路线。" if routes else "暂无可用的每日路线结果。"
        if fallback_days:
            summary = f"{summary} 其中 {fallback_days} 天因路况数据限制切换为其他交通方式。"

        return (
            routes,
            AgentExecution(
                agent_name="route_agent",
                success=True,
                summary=summary,
                used_llm=False,
                used_tools=sorted(used_tools),
                warnings=[],
            ),
        )

    async def gather_for_plan(
        self,
        request: TripPlanningRequest,
        plan: TravelPlan,
        context: PlanningContext,
        trace: list[ToolCallRecord],
    ) -> tuple[list[RouteSummary], AgentExecution]:
        self._named_location_cache.clear()
        routes: list[RouteSummary] = []
        fallback_days = 0
        warnings: list[str] = []
        sorted_days = sorted(plan.days, key=lambda item: item.day_number)
        effective_day_concurrency = self._day_concurrency
        effective_segment_concurrency = self._segment_concurrency
        suggest_parallelism = getattr(self.adapter, "suggest_route_parallelism", None)
        if callable(suggest_parallelism):
            try:
                (
                    effective_day_concurrency,
                    effective_segment_concurrency,
                    parallelism_warning,
                ) = await suggest_parallelism(
                    day_concurrency=self._day_concurrency,
                    segment_concurrency=self._segment_concurrency,
                )
                if parallelism_warning:
                    warnings.append(parallelism_warning)
            except Exception:
                effective_day_concurrency = self._day_concurrency
                effective_segment_concurrency = self._segment_concurrency

        day_concurrency = min(effective_day_concurrency, max(1, len(sorted_days)))
        semaphore = asyncio.Semaphore(day_concurrency)

        async def _plan_day(index: int, day: DayPlan):
            async with semaphore:
                planner = self._plan_routes_for_day
                planner_kwargs = {
                    "request": request,
                    "day": day,
                    "context": context,
                    "trace": trace,
                }
                if "segment_concurrency" in inspect.signature(planner).parameters:
                    planner_kwargs["segment_concurrency"] = effective_segment_concurrency
                day_routes, day_used_fallback, day_warning = await planner(**planner_kwargs)
            return index, day_routes, day_used_fallback, day_warning

        day_results = await asyncio.gather(
            *[_plan_day(index, day) for index, day in enumerate(sorted_days)]
        )
        day_results.sort(key=lambda item: item[0])
        for _, day_routes, day_used_fallback, day_warning in day_results:
            routes.extend(day_routes)
            if day_used_fallback:
                fallback_days += 1
            if day_warning:
                warnings.append(day_warning)

        used_tools = {
            item.tool_name
            for item in trace
            if item.tool_name.startswith("maps_direction")
            or item.tool_name.startswith("maps_bicycling")
            or item.tool_name.startswith("amap_webservice_")
        }
        summary = (
            f"已基于最终行程生成 {len(routes)} 条分段路线。"
            if routes
            else "暂无可用的每日路线结果。"
        )
        if fallback_days:
            summary = f"{summary} 其中 {fallback_days} 天使用了规则路线摘要。"

        return (
            routes,
            AgentExecution(
                agent_name="route_agent",
                success=True,
                summary=summary,
                used_llm=False,
                used_tools=sorted(used_tools),
                warnings=warnings,
            ),
        )

    async def _legacy_bind_plan_truth(
        self,
        request: TripPlanningRequest,
        plan: TravelPlan,
        context: PlanningContext,
        trace: list[ToolCallRecord],
    ) -> tuple[TravelPlan, AgentExecution]:
        updated_days: list[DayPlan] = []
        warnings: list[str] = []

        for day in sorted(plan.days, key=lambda item: item.day_number):
            anchor_points = [*context.attractions, *context.hotels]
            day_fallbacks = list(day.fallbacks)
            map_pois: list[DayPOI] = []

            stay_poi = day.stay.poi
            if self._should_rebind_poi(stay_poi):
                try:
                    stay_poi = await self._resolve_origin_for_day(
                        request=request,
                        day=day,
                        context=context,
                        anchor_points=anchor_points,
                        trace=trace,
                    )
                except Exception as exc:
                    warnings.append(f"第 {day.day_number} 天住宿点位校正失败: {exc}")
                    day_fallbacks.append("stay_poi_binding_failed")
            updated_stay = day.stay.model_copy(update={"poi": stay_poi})
            if stay_poi is not None and updated_stay.hotel_name:
                map_pois.append(
                    DayPOI(kind="stay", label=updated_stay.hotel_name, poi=stay_poi)
                )
            elif updated_stay.hotel_name:
                day_fallbacks.append("stay_poi_unresolved")

            updated_activities = []
            for activity in day.activities:
                resolved = activity.poi
                if self._should_rebind_poi(resolved):
                    try:
                        resolved = await self._resolve_activity_location(
                            city=request.destination,
                            location_name=activity.location_name,
                            activity_title=activity.title,
                            context=context,
                            trace=trace,
                            anchor_points=anchor_points,
                        ) or resolved
                    except Exception as exc:
                        warnings.append(
                            f"第 {day.day_number} 天活动点位校正失败: {activity.location_name} | {exc}"
                        )
                        day_fallbacks.append(
                            f"activity_poi_binding_failed:{activity.location_name}"
                        )
                updated_activity = activity.model_copy(update={"poi": resolved})
                updated_activities.append(updated_activity)
                if resolved is not None:
                    map_pois.append(
                        DayPOI(
                            kind="activity",
                            label=activity.title or activity.location_name,
                            poi=resolved,
                        )
                    )
                elif activity.location_name:
                    day_fallbacks.append(f"activity_poi_unresolved:{activity.location_name}")

            updated_meals = []
            for meal in day.meals:
                resolved_meal = meal.poi
                if self._should_rebind_poi(resolved_meal) and meal.venue_name:
                    try:
                        resolved_meal = await self._resolve_named_location(
                            city=request.destination,
                            location_name=meal.venue_name,
                            known_points=context.restaurants,
                            trace=trace,
                            anchor_points=context.restaurants or anchor_points,
                        ) or resolved_meal
                    except Exception as exc:
                        warnings.append(
                            f"第 {day.day_number} 天餐饮点位校正失败: {meal.venue_name} | {exc}"
                        )
                        day_fallbacks.append(f"meal_poi_binding_failed:{meal.venue_name}")
                    if resolved_meal is None and meal.meal_type == "breakfast":
                        resolved_meal = updated_stay.poi
                updated_meal = meal.model_copy(update={"poi": resolved_meal})
                updated_meals.append(updated_meal)
                if resolved_meal is not None:
                    map_pois.append(
                        DayPOI(
                            kind="meal",
                            label=meal.meal_type,
                            poi=resolved_meal,
                        )
                    )

            route_segments = list(day.route_segments or day.route_summaries)
            if not route_segments and day.route_summary is not None:
                route_segments = [day.route_summary]
            if updated_activities and not any(
                item.poi.longitude is not None and item.poi.latitude is not None
                for item in map_pois
                if item.kind == "activity"
            ):
                warnings.append(f"第 {day.day_number} 天活动点位未解析出坐标，地图将只显示已确认位置。")

            updated_days.append(
                day.model_copy(
                    update={
                        "stay": updated_stay,
                        "activities": updated_activities,
                        "meals": updated_meals,
                        "map_pois": self._build_unique_day_pois(map_pois),
                        "route_segments": route_segments,
                        "fallbacks": sorted(set(day_fallbacks)),
                    }
                )
            )

        summary = "已完成最终日程点位校正。"
        if warnings:
            summary = "已完成最终日程点位校正，部分活动点位未能解析精确坐标。"
        return (
            plan.model_copy(update={"days": updated_days}),
            AgentExecution(
                agent_name="plan_truth_agent",
                success=True,
                summary=summary,
                used_llm=False,
                used_tools=[],
                warnings=warnings,
            ),
        )

    async def bind_plan_truth(
        self,
        request: TripPlanningRequest,
        plan: TravelPlan,
        context: PlanningContext,
        trace: list[ToolCallRecord],
    ) -> tuple[TravelPlan, AgentExecution]:
        self._named_location_cache.clear()
        warnings: list[str] = []
        sorted_days = sorted(plan.days, key=lambda item: item.day_number)
        day_concurrency = min(self._truth_binding_day_concurrency, max(1, len(sorted_days)))
        semaphore = asyncio.Semaphore(day_concurrency)

        async def _bind_day(index: int, day: DayPlan):
            async with semaphore:
                updated_day, day_warnings = await self._bind_truth_for_day(
                    request=request,
                    day=day,
                    context=context,
                    trace=trace,
                )
            return index, updated_day, day_warnings

        day_results = await asyncio.gather(
            *[_bind_day(index, day) for index, day in enumerate(sorted_days)]
        )
        day_results.sort(key=lambda item: item[0])
        updated_days: list[DayPlan] = []
        for _, updated_day, day_warnings in day_results:
            updated_days.append(updated_day)
            warnings.extend(day_warnings)

        summary = "已完成最终点位校正。"
        if warnings:
            summary = "已完成最终点位校正，部分点位未能精确定位。"
        return (
            plan.model_copy(update={"days": updated_days}),
            AgentExecution(
                agent_name="plan_truth_agent",
                success=True,
                summary=summary,
                used_llm=False,
                used_tools=[],
                warnings=warnings,
            ),
        )
