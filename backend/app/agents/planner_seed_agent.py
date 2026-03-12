from app.schemas.planning import AgentExecution, InitialPlanDraft, TripPlanningRequest
from app.services.ai_client import TravelAIClient


class PlannerSeedAgent:
    def __init__(self, ai_client: TravelAIClient) -> None:
        self.ai_client = ai_client

    async def gather(self, request: TripPlanningRequest) -> tuple[InitialPlanDraft, AgentExecution]:
        result = await self.ai_client.build_initial_plan(request)
        summary = "已生成初步行程骨架。"
        if result.fallback_used:
            summary = "初步行程骨架已生成，但当前使用规则模板兜底。"
        return (
            result.draft,
            AgentExecution(
                agent_name="planner_seed_agent",
                success=True,
                summary=summary,
                used_llm=result.used_llm,
                used_tools=[],
                warnings=result.warnings,
            ),
        )
