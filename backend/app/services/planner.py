from datetime import datetime

from app.agents.planning_agent import PlanningCoordinatorAgent
from app.config import Settings
from app.schemas.planning import IntegrationStatus, PlanningResponse, TripPlanningRequest


class TravelPlannerService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.coordinator = PlanningCoordinatorAgent(settings)

    async def generate(
        self,
        request: TripPlanningRequest,
        generated_at: datetime,
        include_debug: bool = True,
    ) -> PlanningResponse:
        return await self.coordinator.generate(
            request,
            generated_at,
            include_debug=include_debug,
        )

    async def diagnose_integrations(self) -> IntegrationStatus:
        return await self.coordinator.diagnose()
