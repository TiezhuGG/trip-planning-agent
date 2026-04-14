from __future__ import annotations

from app.schemas.planning import PlanningResponse, TripPlanningRequest


def validate_snapshot_matches_request(
    request: TripPlanningRequest,
    response: PlanningResponse,
) -> None:
    request_payload = request.model_dump(mode="json")
    response_payload = response.request_echo.model_dump(mode="json")
    if request_payload != response_payload:
        raise ValueError("response_snapshot.request_echo 与 request_brief 不一致。")
