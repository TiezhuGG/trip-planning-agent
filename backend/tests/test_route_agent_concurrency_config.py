from app.agents.route_agent import RoutePlanningAgent
from app.config import Settings
from app.services.amap_mcp_adapter import AmapMCPAdapter


def test_route_agent_uses_configured_concurrency() -> None:
    settings = Settings(
        amap_mcp_command="uvx",
        planner_route_segment_concurrency=4,
        planner_route_day_concurrency=3,
        planner_truth_binding_day_concurrency=5,
        planner_route_activity_resolve_concurrency=6,
    )
    adapter = AmapMCPAdapter(settings)
    agent = RoutePlanningAgent(adapter, settings)

    assert agent._segment_concurrency == 4
    assert agent._day_concurrency == 3
    assert agent._truth_binding_day_concurrency == 5
    assert agent._activity_resolve_concurrency == 6


def test_route_agent_concurrency_has_floor_of_one() -> None:
    settings = Settings(
        amap_mcp_command="uvx",
        planner_route_segment_concurrency=0,
        planner_route_day_concurrency=-2,
        planner_truth_binding_day_concurrency=0,
        planner_route_activity_resolve_concurrency=0,
    )
    adapter = AmapMCPAdapter(settings)
    agent = RoutePlanningAgent(adapter, settings)

    assert agent._segment_concurrency == 1
    assert agent._day_concurrency == 1
    assert agent._truth_binding_day_concurrency == 1
    assert agent._activity_resolve_concurrency == 1
