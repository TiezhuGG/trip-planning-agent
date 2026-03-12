from app.schemas.planning import AgentExecution, InitialPlanDraft, PlanningContext, TravelPlan, TripPlanningRequest
from app.services.ai_client import TravelAIClient


class ItineraryComposerAgent:
    def __init__(self, ai_client: TravelAIClient) -> None:
        self.ai_client = ai_client

    async def gather(
        self,
        request: TripPlanningRequest,
        initial_plan: InitialPlanDraft,
        context: PlanningContext,
        tool_trace: list,
    ) -> tuple[TravelPlan, AgentExecution, bool, bool, list[str]]:
        result = await self.ai_client.compose_plan(request, initial_plan, context, tool_trace)
        summary = "已完成最终行程整合。"
        if result.fallback_used:
            summary = "最终行程已生成，但当前使用规则模板兜底。"
        return (
            result.plan,
            AgentExecution(
                agent_name="itinerary_composer_agent",
                success=True,
                summary=summary,
                used_llm=result.used_llm,
                used_tools=[],
                warnings=result.warnings,
            ),
            result.used_llm,
            result.fallback_used,
            result.warnings,
        )
