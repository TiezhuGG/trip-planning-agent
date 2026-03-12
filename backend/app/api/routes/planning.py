from datetime import datetime

from fastapi import APIRouter

from app.config import get_settings
from app.schemas.planning import PlanningResponse, TripPlanningRequest
from app.services.planner import TravelPlannerService

router = APIRouter(tags=["planning"])

settings = get_settings()
planner_service = TravelPlannerService(settings)


@router.post("/plans/generate", response_model=PlanningResponse)
async def generate_plan(payload: TripPlanningRequest) -> PlanningResponse:
    return await planner_service.generate(payload, generated_at=datetime.utcnow())
