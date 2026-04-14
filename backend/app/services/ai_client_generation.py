from __future__ import annotations

from typing import Any

import httpx

from app.schemas.planning import (
    InitialPlanDraft,
    PlanningContext,
    ToolCallRecord,
    TravelPlan,
    TripPlanningRequest,
)
from app.services.ai_client_runtime import compose_retry_specs, format_exception


class TravelAIClientGenerationMixin:
    async def _generate_initial_plan_with_openai(
        self,
        request: TripPlanningRequest,
        temperature: float = 0.4,
        max_tokens: int | None = None,
        client: Any | None = None,
        model: str | None = None,
    ) -> InitialPlanDraft:
        if client is None:
            client = self.client
        assert client is not None
        schema_hint = {
            "summary": "string",
            "days": [
                {
                    "day_number": 1,
                    "date": "YYYY-MM-DD",
                    "theme": "string",
                    "focus": "string",
                    "must_visit": ["string"],
                    "poi_query": "string",
                    "dining_query": "string",
                }
            ],
        }
        payload = await self._request_json_payload(
            system_prompt=(
                "You are a travel-planning orchestrator. "
                "Return JSON only. Keep all user-facing text natural Chinese. "
                "The draft must contain exactly request.days items in days, "
                "with unique day_number values from 1 to request.days."
            ),
            user_payload={
                "request": request.model_dump(mode="json"),
                "response_schema_hint": schema_hint,
            },
            temperature=temperature,
            max_tokens=max_tokens,
            client=client,
            model=model,
        )
        draft = InitialPlanDraft.model_validate(payload)
        self._ensure_initial_plan_integrity(request, draft)
        return draft

    async def _compose_with_openai(
        self,
        request: TripPlanningRequest,
        initial_plan: InitialPlanDraft,
        context: PlanningContext,
        tool_trace: list[ToolCallRecord],
        client: Any | None = None,
        model: str | None = None,
    ) -> tuple[TravelPlan, list[str]]:
        if client is None:
            client = self.client
        assert client is not None
        schema_hint = {
            "title": "string",
            "summary": "string",
            "weather_summary": "string",
            "best_booking_tip": "string",
            "estimated_budget": {
                "currency": "CNY",
                "accommodation": "string",
                "transport": "string",
                "food": "string",
                "tickets": "string",
                "extras": "string",
                "total_estimate": "string",
            },
            "stay_recommendations": [
                {"area": "string", "hotel_name": "string", "reason": "string", "nightly_budget": "string"}
            ],
            "city_tips": ["string"],
            "packing_list": ["string"],
            "days": [
                {
                    "day_number": 1,
                    "date": "YYYY-MM-DD",
                    "theme": "string",
                    "overview": "string",
                    "hotel_area": "string",
                    "transport_tips": ["string"],
                    "weather": {
                        "date": "YYYY-MM-DD",
                        "day_weather": "string",
                        "night_weather": "string",
                        "high_temperature": "string",
                        "low_temperature": "string",
                        "advice": "string",
                    },
                    "meals": [
                        {
                            "meal_type": "breakfast|lunch|dinner|snack",
                            "venue_name": "string",
                            "cuisine": "string",
                            "suggestion": "string",
                            "estimated_cost": "string",
                        }
                    ],
                    "activities": [
                        {
                            "start_time": "09:00",
                            "end_time": "11:00",
                            "title": "string",
                            "category": "string",
                            "description": "string",
                            "location_name": "string",
                            "transport_from_previous": "string",
                            "expected_cost": "string",
                            "booking_tip": "string",
                        }
                    ],
                }
            ],
        }
        user_payload = self._build_compose_user_payload(
            request=request,
            initial_plan=initial_plan,
            context=context,
            tool_trace=tool_trace,
        )
        warnings: list[str] = []
        last_error: Exception | None = None
        channel = f"compose::{model or self.primary_model or self.settings.openai_model}"
        retry_specs = await self._adaptive_retry_specs(
            channel=channel,
            retry_specs=compose_retry_specs(self.settings.openai_fast_mode),
        )

        for attempt, (temperature, max_tokens) in enumerate(retry_specs, start=1):
            payload: dict[str, Any] | None = None
            try:
                payload = await self._request_json_payload(
                    system_prompt=(
                        "You are a senior trip planner. "
                        "Use the provided draft, map data, weather, and routes to produce the final plan. "
                        "Return JSON only and keep user-facing text natural Chinese. "
                        "days must contain exactly request.days records with unique day_number from 1..request.days. "
                        "Each day must include at least one activity and meals that cover breakfast, lunch, and dinner. "
                        "Each day's stay and hotel_area must stay close to that day's main activity cluster. "
                        "Do not place lodging in a far-away district within the same city. "
                        "Keep descriptions concise and avoid verbose wording."
                    ),
                    user_payload={**user_payload, "response_schema_hint": schema_hint},
                    temperature=temperature,
                    max_tokens=max_tokens,
                    client=client,
                    model=model,
                )
                plan = self._finalize_composed_plan(request=request, context=context, payload=payload)
                await self._record_adaptive_retry_result(channel, success=True)
                return plan, warnings
            except Exception as exc:
                allow_repair = (not self.settings.openai_fast_mode) or attempt == len(retry_specs)
                if payload is not None and allow_repair and self._is_retryable_compose_error(exc):
                    repaired_payload = await self._repair_compose_payload(
                        request=request,
                        raw_payload=payload,
                        schema_hint=schema_hint,
                        client=client,
                        model=model,
                    )
                    if repaired_payload is not None:
                        try:
                            plan = self._finalize_composed_plan(
                                request=request,
                                context=context,
                                payload=repaired_payload,
                            )
                            await self._record_adaptive_retry_result(channel, success=True)
                            warnings.append(f"compose 第 {attempt} 次触发补全修复并成功。")
                            return plan, warnings
                        except Exception as repair_exc:
                            exc = repair_exc

                last_error = exc
                if not self._is_retryable_compose_error(exc) or attempt >= len(retry_specs):
                    await self._record_adaptive_retry_result(channel, success=False)
                    break
                warnings.append(f"compose 第 {attempt} 次失败，已重试。原因: {format_exception(exc)}")

        assert last_error is not None
        raise last_error
