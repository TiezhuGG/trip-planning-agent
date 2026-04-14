from app.agents.route_agent_helper_mixin import RoutePlanningAgentHelperMixin
from app.agents.route_agent_orchestration import (
    RoutePlanningAgentOrchestrationMixin,
)
from app.agents.route_agent_resolution_mixin import RoutePlanningAgentResolutionMixin
from app.agents.route_agent_truth import (
    bind_truth_for_day as bind_truth_for_day_runtime,
)
from app.config import Settings
from app.schemas.planning import (
    DayPlan,
    POIRecommendation,
    PlanningContext,
    ToolCallRecord,
    TripPlanningRequest,
)
from app.services.amap_mcp_adapter import AmapMCPAdapter


class RoutePlanningAgent(
    RoutePlanningAgentHelperMixin,
    RoutePlanningAgentResolutionMixin,
    RoutePlanningAgentOrchestrationMixin,
):
    def __init__(self, adapter: AmapMCPAdapter, settings: Settings | None = None) -> None:
        self.adapter = adapter
        # Keep low default concurrency to balance latency and upstream rate-limit pressure.
        self._segment_concurrency = max(
            1,
            int((settings.planner_route_segment_concurrency if settings else 2)),
        )
        self._day_concurrency = max(
            1,
            int((settings.planner_route_day_concurrency if settings else 2)),
        )
        self._truth_binding_day_concurrency = max(
            1,
            int((settings.planner_truth_binding_day_concurrency if settings else 2)),
        )
        self._activity_resolve_concurrency = max(
            1,
            int((settings.planner_route_activity_resolve_concurrency if settings else 3)),
        )
        self._named_location_cache: dict[str, POIRecommendation | None] = {}

    async def _bind_truth_for_day(
        self,
        request: TripPlanningRequest,
        day: DayPlan,
        context: PlanningContext,
        trace: list[ToolCallRecord],
    ) -> tuple[DayPlan, list[str]]:
        return await bind_truth_for_day_runtime(
            request=request,
            day=day,
            context=context,
            trace=trace,
            should_rebind_named_poi_fn=self._should_rebind_named_poi,
            resolve_origin_for_day_fn=self._resolve_origin_for_day,
            resolve_activity_location_fn=self._resolve_activity_location,
            resolve_named_location_fn=self._resolve_named_location,
            ensure_route_ready_poi_fn=self._ensure_route_ready_poi,
            build_unique_day_pois_fn=self._build_unique_day_pois,
        )
