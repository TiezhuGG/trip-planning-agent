from datetime import datetime

from fastapi import APIRouter

from app.config import get_settings
from app.schemas.planning import IntegrationStatus, PlanningResponse, TripPlanningRequest
from app.services.planner import TravelPlannerService

router = APIRouter(tags=["planning"])


def get_planner_service() -> TravelPlannerService:
    return TravelPlannerService(get_settings())


@router.get("/plans/integrations/status", response_model=IntegrationStatus)
async def get_integration_status() -> IntegrationStatus:
    return await get_planner_service().diagnose_integrations()


@router.post("/plans/generate", response_model=PlanningResponse)
async def generate_plan(payload: TripPlanningRequest) -> PlanningResponse:
    return await get_planner_service().generate(payload, generated_at=datetime.utcnow())
