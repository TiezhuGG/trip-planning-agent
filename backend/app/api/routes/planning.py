from datetime import datetime

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.schemas.planning import IntegrationStatus, PlanningResponse, TripPlanningRequest
from app.services.planner import TravelPlannerService

router = APIRouter(tags=["planning"])


def get_planner_service() -> TravelPlannerService:
    return TravelPlannerService(get_settings())


@router.get("/plans/integrations/status", response_model=IntegrationStatus)
async def get_integration_status() -> IntegrationStatus:
    try:
        return await get_planner_service().diagnose_integrations()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"集成状态检查失败: {exc.__class__.__name__}: {exc}") from exc


@router.post("/plans/generate", response_model=PlanningResponse)
async def generate_plan(payload: TripPlanningRequest) -> PlanningResponse:
    try:
        return await get_planner_service().generate(payload, generated_at=datetime.utcnow())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"生成旅行计划失败: {exc.__class__.__name__}: {exc}") from exc
