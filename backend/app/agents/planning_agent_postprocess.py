from __future__ import annotations

from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Any

from app.schemas.planning import (
    AgentExecution,
    PlanningContext,
    POIRecommendation,
    RouteSummary,
    ToolCallRecord,
    TravelPlan,
    TripPlanningRequest,
)

AwaitWithOptionalTimeout = Callable[[Awaitable[Any], float], Awaitable[Any]]
FormatTimeoutSeconds = Callable[[float], str]
ElapsedMs = Callable[[float], int]
FinalizePlanWithRoutes = Callable[[TripPlanningRequest, TravelPlan, PlanningContext], TravelPlan]


async def run_post_compose_pipeline(
    *,
    request: TripPlanningRequest,
    plan: TravelPlan,
    context: PlanningContext,
    tool_trace: list[ToolCallRecord],
    resolved_poi_search_tool: str,
    resolved_route_plan_tool: str,
    hotel_binding_timeout: float,
    meal_binding_timeout: float,
    route_generation_timeout: float,
    truth_binding_timeout: float,
    bind_daily_stays_fn: Callable[..., Awaitable[tuple[TravelPlan, list[POIRecommendation], AgentExecution]]],
    bind_daily_meals_fn: Callable[..., Awaitable[tuple[TravelPlan, list[POIRecommendation], AgentExecution]]],
    gather_routes_fn: Callable[..., Awaitable[tuple[list[RouteSummary], AgentExecution]]],
    finalize_plan_with_routes_fn: FinalizePlanWithRoutes,
    bind_plan_truth_fn: Callable[..., Awaitable[tuple[TravelPlan, AgentExecution]]],
    await_with_optional_timeout_fn: AwaitWithOptionalTimeout,
    format_timeout_seconds_fn: FormatTimeoutSeconds,
    elapsed_ms_fn: ElapsedMs,
) -> tuple[
    TravelPlan,
    PlanningContext,
    AgentExecution,
    AgentExecution,
    AgentExecution,
    AgentExecution,
    list[str],
    dict[str, int],
]:
    warnings: list[str] = []
    stage_timings_ms: dict[str, int] = {}

    hotel_binding_started = perf_counter()
    try:
        (
            plan,
            rebound_hotels,
            hotel_binding_trace,
        ) = await await_with_optional_timeout_fn(
            bind_daily_stays_fn(
                request=request,
                plan=plan,
                context=context,
                trace=tool_trace,
            ),
            timeout_seconds=hotel_binding_timeout,
        )
    except TimeoutError:
        timeout_text = format_timeout_seconds_fn(hotel_binding_timeout)
        timeout_warning = f"hotel_binding_agent 调用超时（>{timeout_text}s），已保留现有住宿安排。"
        warnings.append(timeout_warning)
        rebound_hotels = []
        hotel_binding_trace = AgentExecution(
            agent_name="hotel_binding_agent",
            success=False,
            summary="每日酒店绑定超时，已保留现有住宿安排。",
            used_llm=False,
            used_tools=[resolved_poi_search_tool],
            warnings=[timeout_warning],
        )
    except Exception as exc:
        warning = f"hotel_binding_agent 调用失败: {exc}"
        warnings.append(warning)
        rebound_hotels = []
        hotel_binding_trace = AgentExecution(
            agent_name="hotel_binding_agent",
            success=False,
            summary="每日酒店绑定失败，已保留现有住宿安排。",
            used_llm=False,
            used_tools=[resolved_poi_search_tool],
            warnings=[str(exc)],
        )
    stage_timings_ms["hotel_binding"] = elapsed_ms_fn(hotel_binding_started)
    if rebound_hotels:
        context.hotels = rebound_hotels[:8]
    warnings.extend(hotel_binding_trace.warnings)

    meal_binding_started = perf_counter()
    try:
        (
            plan,
            rebound_restaurants,
            meal_binding_trace,
        ) = await await_with_optional_timeout_fn(
            bind_daily_meals_fn(
                request=request,
                plan=plan,
                context=context,
                trace=tool_trace,
            ),
            timeout_seconds=meal_binding_timeout,
        )
    except TimeoutError:
        timeout_text = format_timeout_seconds_fn(meal_binding_timeout)
        timeout_warning = f"meal_binding_agent 调用超时（>{timeout_text}s），已保留现有餐饮安排。"
        warnings.append(timeout_warning)
        rebound_restaurants = []
        meal_binding_trace = AgentExecution(
            agent_name="meal_binding_agent",
            success=False,
            summary="每日餐饮绑定超时，已保留现有餐饮安排。",
            used_llm=False,
            used_tools=[resolved_poi_search_tool],
            warnings=[timeout_warning],
        )
    except Exception as exc:
        warning = f"meal_binding_agent 调用失败: {exc}"
        warnings.append(warning)
        rebound_restaurants = []
        meal_binding_trace = AgentExecution(
            agent_name="meal_binding_agent",
            success=False,
            summary="每日餐饮绑定失败，已保留现有餐饮安排。",
            used_llm=False,
            used_tools=[resolved_poi_search_tool],
            warnings=[str(exc)],
        )
    stage_timings_ms["meal_binding"] = elapsed_ms_fn(meal_binding_started)
    if rebound_restaurants:
        context.restaurants = rebound_restaurants[:12]
    warnings.extend(meal_binding_trace.warnings)

    route_generation_started = perf_counter()
    routes: list[RouteSummary] = []
    try:
        routes, route_trace = await await_with_optional_timeout_fn(
            gather_routes_fn(
                request=request,
                plan=plan,
                context=context,
                trace=tool_trace,
            ),
            timeout_seconds=route_generation_timeout,
        )
    except TimeoutError:
        timeout_text = format_timeout_seconds_fn(route_generation_timeout)
        timeout_warning = f"route_agent 调用超时（>{timeout_text}s），已保留原始行程动线信息。"
        warnings.append(timeout_warning)
        route_trace = AgentExecution(
            agent_name="route_agent",
            success=False,
            summary="路线生成超时，已保留原始行程动线信息。",
            used_llm=False,
            used_tools=[resolved_route_plan_tool],
            warnings=[timeout_warning],
        )
    except Exception as exc:
        warning = f"route_agent 调用失败: {exc}"
        warnings.append(warning)
        route_trace = AgentExecution(
            agent_name="route_agent",
            success=False,
            summary="路线生成失败，已保留原始行程动线信息。",
            used_llm=False,
            used_tools=[resolved_route_plan_tool],
            warnings=[str(exc)],
        )
    stage_timings_ms["route_generation"] = elapsed_ms_fn(route_generation_started)
    context.routes = routes

    route_finalize_started = perf_counter()
    if context.routes:
        try:
            plan = finalize_plan_with_routes_fn(request, plan, context)
        except Exception as exc:
            warning = f"route_finalize 处理失败: {exc}"
            warnings.append(warning)
            route_trace = route_trace.model_copy(
                update={
                    "success": False,
                    "summary": "路线结果整合失败，已保留基础行程结果。",
                    "warnings": list(dict.fromkeys([*route_trace.warnings, str(exc)])),
                }
            )
    stage_timings_ms["route_finalize"] = elapsed_ms_fn(route_finalize_started)
    warnings.extend(route_trace.warnings)

    truth_binding_started = perf_counter()
    try:
        plan, truth_trace = await await_with_optional_timeout_fn(
            bind_plan_truth_fn(
                request=request,
                plan=plan,
                context=context,
                trace=tool_trace,
            ),
            timeout_seconds=truth_binding_timeout,
        )
    except TimeoutError:
        timeout_text = format_timeout_seconds_fn(truth_binding_timeout)
        timeout_warning = f"plan_truth_agent 调用超时（>{timeout_text}s），已保留基础行程结果。"
        warnings.append(timeout_warning)
        truth_trace = AgentExecution(
            agent_name="plan_truth_agent",
            success=False,
            summary="最终点位校正超时，已保留基础行程结果继续返回。",
            used_llm=False,
            used_tools=[],
            warnings=[timeout_warning],
        )
    except Exception as exc:
        warning = f"plan_truth_agent 调用失败: {exc}"
        warnings.append(warning)
        truth_trace = AgentExecution(
            agent_name="plan_truth_agent",
            success=False,
            summary="最终点位校正失败，已保留基础行程结果继续返回。",
            used_llm=False,
            used_tools=[],
            warnings=[str(exc)],
        )
    stage_timings_ms["truth_binding"] = elapsed_ms_fn(truth_binding_started)
    warnings.extend(truth_trace.warnings)

    return (
        plan,
        context,
        hotel_binding_trace,
        meal_binding_trace,
        route_trace,
        truth_trace,
        warnings,
        stage_timings_ms,
    )
