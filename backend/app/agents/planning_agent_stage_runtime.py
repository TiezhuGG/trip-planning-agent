from __future__ import annotations

from app.agents.planning_agent_diagnostics import collect_stage_tool_warnings
from app.schemas.planning import AgentExecution, WeatherSummary


async def gather_poi_stage(
    *,
    request,
    sight_agent,
    tool_trace: list,
    resolved_poi_search_tool: str,
    is_rate_limit_text,
) -> tuple[list, list, AgentExecution, list[str]]:
    poi_tool_trace_start = len(tool_trace)
    try:
        attractions, restaurants = await sight_agent.gather(request, tool_trace)
        selected_attractions = attractions[:12]
        selected_restaurants = restaurants[:12]
        poi_stage_warnings = collect_stage_tool_warnings(
            stage_trace=tool_trace[poi_tool_trace_start:],
            fallback_message="景点或餐饮数据部分受限，已使用当前可用候选继续生成。",
            is_rate_limit_text=is_rate_limit_text,
        )
        trace = AgentExecution(
            agent_name="poi_agent",
            success=True,
            summary=f"已获取 {len(selected_attractions)} 个景点和 {len(selected_restaurants)} 个餐饮候选。",
            used_llm=False,
            used_tools=[resolved_poi_search_tool],
            warnings=poi_stage_warnings,
        )
        return selected_attractions, selected_restaurants, trace, poi_stage_warnings
    except Exception as exc:
        warning = f"poi_agent 调用失败: {exc}"
        trace = AgentExecution(
            agent_name="poi_agent",
            success=False,
            summary="景点与餐饮候选不可用，已在缺少 POI 上下文条件下继续生成行程。",
            used_llm=False,
            used_tools=[resolved_poi_search_tool],
            warnings=[str(exc)],
        )
        return [], [], trace, [warning]


async def gather_hotel_stage(
    *,
    request,
    attractions: list,
    hotel_agent,
    tool_trace: list,
    resolved_poi_search_tool: str,
    is_rate_limit_text,
) -> tuple[list, AgentExecution, list[str]]:
    hotel_tool_trace_start = len(tool_trace)
    try:
        hotels = await hotel_agent.gather(request, attractions, tool_trace)
        selected_hotels = hotels[:8]
        hotel_stage_warnings = collect_stage_tool_warnings(
            stage_trace=tool_trace[hotel_tool_trace_start:],
            fallback_message="酒店候选部分受限，已使用当前可用候选继续生成。",
            is_rate_limit_text=is_rate_limit_text,
        )
        trace = AgentExecution(
            agent_name="hotel_agent",
            success=True,
            summary=f"已获取 {len(selected_hotels)} 个酒店候选。",
            used_llm=False,
            used_tools=[resolved_poi_search_tool],
            warnings=hotel_stage_warnings,
        )
        return selected_hotels, trace, hotel_stage_warnings
    except Exception as exc:
        warning = f"hotel_agent 调用失败: {exc}"
        trace = AgentExecution(
            agent_name="hotel_agent",
            success=False,
            summary="酒店候选不可用，已在缺少酒店推荐条件下继续生成行程。",
            used_llm=False,
            used_tools=[resolved_poi_search_tool],
            warnings=[str(exc)],
        )
        return [], trace, [warning]


async def gather_weather_stage(
    *,
    request,
    weather_agent,
    tool_trace: list,
    resolved_weather_tool: str,
) -> tuple[WeatherSummary, AgentExecution, list[str]]:
    try:
        weather = await weather_agent.gather(request, tool_trace)
        trace = AgentExecution(
            agent_name="weather_agent",
            success=True,
            summary=f"已获取 {len(weather.daily_forecasts)} 天天气信息。",
            used_llm=False,
            used_tools=[resolved_weather_tool],
        )
        return weather, trace, []
    except Exception as exc:
        warning = f"weather_agent 调用失败: {exc}"
        trace = AgentExecution(
            agent_name="weather_agent",
            success=False,
            summary="天气数据不可用，已在无天气详情条件下继续生成行程。",
            used_llm=False,
            used_tools=[resolved_weather_tool],
            warnings=[str(exc)],
        )
        return WeatherSummary(), trace, [warning]


def build_meal_candidate_trace(day_restaurants: list) -> AgentExecution:
    return AgentExecution(
        agent_name="meal_agent",
        success=True,
        summary=f"已为 {len(day_restaurants)} 天行程匹配餐饮候选。",
        used_llm=False,
        used_tools=[],
    )
