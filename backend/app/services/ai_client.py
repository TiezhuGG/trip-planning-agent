from __future__ import annotations

import asyncio
import json
import math
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import httpx

from app.config import Settings
from app.schemas.planning import (
    Activity,
    BudgetBreakdown,
    DayCostBreakdown,
    DailyForecast,
    DayPOI,
    DayPlan,
    DayStayInfo,
    InitialPlanDay,
    InitialPlanDraft,
    MealRecommendation,
    POIRecommendation,
    PlanningContext,
    RouteSummary,
    RouteStep,
    StayRecommendation,
    ToolCallRecord,
    TravelPlan,
    TripPlanningRequest,
)
from app.utils.json_extract import extract_json_payload

try:
    from openai import AsyncOpenAI
except Exception:
    AsyncOpenAI = None  # type: ignore


@dataclass
class InitialPlanBuildResult:
    draft: InitialPlanDraft
    used_llm: bool
    fallback_used: bool
    warnings: list[str]


@dataclass
class FinalPlanBuildResult:
    plan: TravelPlan
    used_llm: bool
    fallback_used: bool
    warnings: list[str]


@dataclass
class LLMDiagnosisResult:
    enabled: bool
    reachable: bool
    model: str
    base_url: str
    warnings: list[str]


@dataclass(frozen=True)
class LLMProvider:
    label: str
    client: Any
    model: str
    base_url: str


class TravelAIClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = None
        self.primary_model = settings.openai_model
        self.base_url = self._normalize_base_url(settings.openai_base_url)
        self.secondary_client = None
        self.secondary_model = settings.openai_backup_model
        self.secondary_base_url = self._normalize_base_url(settings.openai_backup_base_url)
        if settings.has_openai and AsyncOpenAI is not None:
            self.client = self._create_client(
                api_key=settings.openai_api_key,
                base_url=self.base_url,
            )
        if settings.has_backup_openai and AsyncOpenAI is not None:
            self.secondary_client = self._create_client(
                api_key=settings.openai_backup_api_key,
                base_url=self.secondary_base_url,
            )

    def _create_client(self, api_key: str, base_url: str) -> Any:
        timeout = httpx.Timeout(self.settings.openai_timeout_seconds, connect=min(15, self.settings.openai_timeout_seconds))
        kwargs: dict[str, Any] = {
            "api_key": api_key,
            "max_retries": self.settings.openai_max_retries,
            "http_client": httpx.AsyncClient(
                timeout=timeout,
                trust_env=self.settings.openai_trust_env,
            ),
        }
        if base_url:
            kwargs["base_url"] = base_url
        return AsyncOpenAI(**kwargs)

    def _configured_providers(self) -> list[LLMProvider]:
        providers: list[LLMProvider] = []
        if self.client is not None:
            providers.append(
                LLMProvider(
                    label="主模型",
                    client=self.client,
                    model=self.primary_model or self.settings.openai_model or "primary-model",
                    base_url=self.base_url,
                )
            )
        if self.secondary_client is not None:
            providers.append(
                LLMProvider(
                    label="备用模型",
                    client=self.secondary_client,
                    model=self.secondary_model or self.settings.openai_backup_model or "backup-model",
                    base_url=self.secondary_base_url,
                )
            )
        return providers

    def _default_model_name(self) -> str:
        for provider in self._configured_providers():
            if provider.model:
                return provider.model
        return self.primary_model or self.secondary_model or self.settings.openai_model or self.settings.openai_backup_model

    async def diagnose(self, check_connection: bool = True) -> LLMDiagnosisResult:
        providers = self._configured_providers()
        if not providers and not self.settings.has_any_openai:
            return LLMDiagnosisResult(
                enabled=False,
                reachable=False,
                model=self._default_model_name(),
                base_url=self.base_url or self.secondary_base_url,
                warnings=["未配置大模型 API Key 或模型名。"],
            )

        if not providers:
            return LLMDiagnosisResult(
                enabled=True,
                reachable=False,
                model=self._default_model_name(),
                base_url=self.base_url or self.secondary_base_url,
                warnings=["OpenAI Python SDK 不可用，请检查依赖安装。"],
            )

        if not check_connection:
            return LLMDiagnosisResult(
                enabled=True,
                reachable=False,
                model=self._default_model_name(),
                base_url=(providers[0].base_url if providers else ""),
                warnings=[],
            )

        warnings: list[str] = []
        for index, provider in enumerate(providers):
            try:
                payload = await self._request_json_payload(
                    system_prompt="你是联调探针。请只返回 JSON。",
                    user_payload={"task": "ping", "response_schema_hint": {"status": "ok"}},
                    temperature=0,
                    max_tokens=32,
                    client=provider.client,
                    model=provider.model,
                )
                if str(payload.get("status", "")).lower() != "ok":
                    raise ValueError("模型未按约定返回诊断 JSON")
                if index > 0:
                    warnings.append(f"主模型不可用，当前诊断已切换到备用模型 {provider.model}。")
                return LLMDiagnosisResult(
                    enabled=True,
                    reachable=True,
                    model=provider.model,
                    base_url=provider.base_url,
                    warnings=warnings,
                )
            except Exception as exc:
                warnings.append(f"{provider.label}连通性检查失败: {exc}")
                if index < len(providers) - 1 and self._should_switch_to_backup_model(exc):
                    continue
        return LLMDiagnosisResult(
            enabled=True,
            reachable=False,
            model=self._default_model_name(),
            base_url=(providers[0].base_url if providers else ""),
            warnings=warnings,
        )

    async def build_initial_plan(self, request: TripPlanningRequest) -> InitialPlanBuildResult:
        providers = self._configured_providers()
        if not providers:
            raise RuntimeError("未配置可用的大模型客户端，无法生成初步规划。")
        warnings: list[str] = []
        last_error: Exception | None = None
        for index, provider in enumerate(providers):
            try:
                draft, provider_warnings = await self._build_initial_plan_with_provider(
                    request,
                    provider,
                )
                warnings.extend(provider_warnings)
                return InitialPlanBuildResult(
                    draft=draft,
                    used_llm=True,
                    fallback_used=False,
                    warnings=warnings,
                )
            except Exception as exc:
                last_error = exc
                if index < len(providers) - 1 and self._should_switch_to_backup_model(exc):
                    warnings.append(
                        f"{provider.label} {provider.model} 暂不可用，已切换到备用模型。原因: {self._format_exception(exc)}"
                    )
                    continue
                if self._should_fallback_to_template(exc):
                    warnings.append(
                        f"初步规划调用大模型受限，已切换到规则模板。原因: {self._format_exception(exc)}"
                    )
                    return InitialPlanBuildResult(
                        draft=self._fallback_initial_plan(request),
                        used_llm=False,
                        fallback_used=True,
                        warnings=warnings,
                    )
        assert last_error is not None
        if self._should_fallback_to_template(last_error):
            warnings.append(
                f"初步规划调用大模型受限，已切换到规则模板。原因: {self._format_exception(last_error)}"
            )
            return InitialPlanBuildResult(
                draft=self._fallback_initial_plan(request),
                used_llm=False,
                fallback_used=True,
                warnings=warnings,
            )
        raise RuntimeError(f"初步规划调用大模型失败: {self._format_exception(last_error)}") from last_error

    async def compose_plan(
        self,
        request: TripPlanningRequest,
        initial_plan: InitialPlanDraft,
        context: PlanningContext,
        tool_trace: list[ToolCallRecord],
    ) -> FinalPlanBuildResult:
        providers = self._configured_providers()
        if not providers:
            raise RuntimeError("未配置可用的大模型客户端，无法生成最终行程。")
        warnings: list[str] = []
        last_error: Exception | None = None
        for index, provider in enumerate(providers):
            try:
                plan, provider_warnings = await self._compose_with_provider(
                    request=request,
                    initial_plan=initial_plan,
                    context=context,
                    tool_trace=tool_trace,
                    provider=provider,
                )
                warnings.extend(provider_warnings)
                return FinalPlanBuildResult(
                    plan=plan,
                    used_llm=True,
                    fallback_used=False,
                    warnings=warnings,
                )
            except Exception as exc:
                last_error = exc
                if index < len(providers) - 1 and self._should_switch_to_backup_model(exc):
                    warnings.append(
                        f"{provider.label} {provider.model} 暂不可用，已切换到备用模型。原因: {self._format_exception(exc)}"
                    )
                    continue
                if self._should_fallback_to_template(exc):
                    return FinalPlanBuildResult(
                        plan=self._build_fallback_final_plan(request, initial_plan, context),
                        used_llm=False,
                        fallback_used=True,
                        warnings=warnings
                        + [f"最终行程汇总调用大模型受限，已切换到规则模板。原因: {self._format_exception(exc)}"],
                    )
                raise RuntimeError(f"最终行程汇总调用大模型失败: {self._format_exception(exc)}") from exc

        assert last_error is not None
        raise RuntimeError(f"最终行程汇总调用大模型失败: {self._format_exception(last_error)}") from last_error

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
        retry_specs = [
            (0.35, 8192),
            (0.15, 9216),
            (0.0, 10240),
        ]

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
                return plan, warnings
            except Exception as exc:
                if payload is not None and self._is_retryable_compose_error(exc):
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
                            warnings.append(f"compose 第 {attempt} 次触发补全修复并成功。")
                            return plan, warnings
                        except Exception as repair_exc:
                            exc = repair_exc

                last_error = exc
                if not self._is_retryable_compose_error(exc) or attempt >= len(retry_specs):
                    break
                warnings.append(
                    f"compose 第 {attempt} 次失败，已重试。原因: {self._format_exception(exc)}"
                )

        assert last_error is not None
        raise last_error

    def _finalize_composed_plan(
        self,
        request: TripPlanningRequest,
        context: PlanningContext,
        payload: dict[str, Any],
    ) -> TravelPlan:
        normalized_payload = self._normalize_compose_payload(payload, request, context)
        plan = TravelPlan.model_validate(normalized_payload)
        plan = self._normalize_plan_days(request, plan, context)
        self._ensure_final_plan_integrity(request, plan, require_routes=bool(context.routes))
        return self._apply_deterministic_budget(request, plan)

    def finalize_plan_with_routes(
        self,
        request: TripPlanningRequest,
        plan: TravelPlan,
        context: PlanningContext,
    ) -> TravelPlan:
        plan = self._normalize_plan_days(request, plan, context)
        plan = self._attach_plan_truth(plan, context, request.destination)
        self._ensure_final_plan_integrity(request, plan, require_routes=True)
        return self._apply_deterministic_budget(request, plan)

    def _normalize_compose_payload(
        self,
        payload: dict[str, Any],
        request: TripPlanningRequest,
        context: PlanningContext,
    ) -> dict[str, Any]:
        days = payload.get("days")
        if not isinstance(days, list):
            return payload

        meal_type_alias = {
            "早餐": "breakfast",
            "早饭": "breakfast",
            "午餐": "lunch",
            "中餐": "lunch",
            "晚餐": "dinner",
            "晚饭": "dinner",
            "夜宵": "snack",
            "加餐": "snack",
        }
        default_venue = f"{request.destination}本地餐厅"
        for day_index, day in enumerate(days):
            if not isinstance(day, dict):
                continue
            meals = day.get("meals")
            if not isinstance(meals, list):
                continue

            day_restaurant = default_venue
            if context.restaurants:
                day_restaurant = context.restaurants[day_index % len(context.restaurants)].name or default_venue

            for meal in meals:
                if not isinstance(meal, dict):
                    continue
                raw_meal_type = str(meal.get("meal_type", "")).strip()
                if raw_meal_type in meal_type_alias:
                    meal["meal_type"] = meal_type_alias[raw_meal_type]

                venue_name = str(meal.get("venue_name", "")).strip()
                if not venue_name:
                    for alias in ("venue", "restaurant", "restaurant_name", "name", "location_name"):
                        alias_value = meal.get(alias)
                        if alias_value is None:
                            continue
                        alias_text = str(alias_value).strip()
                        if alias_text:
                            venue_name = alias_text
                            break
                if not venue_name:
                    venue_name = day_restaurant
                meal["venue_name"] = venue_name

        return payload

    async def _repair_compose_payload(
        self,
        request: TripPlanningRequest,
        raw_payload: dict[str, Any],
        schema_hint: dict[str, Any],
        client: Any | None = None,
        model: str | None = None,
    ) -> dict[str, Any] | None:
        try:
            return await self._request_json_payload(
                system_prompt=(
                    "You are a JSON repair assistant for travel plans. "
                    "Return JSON only. Keep natural Chinese text. "
                    "Fix the plan so days contains exactly request.days records "
                    "with unique day_number from 1..request.days."
                ),
                user_payload={
                    "request": request.model_dump(mode="json"),
                    "broken_plan": raw_payload,
                    "response_schema_hint": schema_hint,
                },
                temperature=0,
                max_tokens=8192,
                client=client,
                model=model,
            )
        except Exception:
            return None

    def _is_retryable_compose_error(self, exc: Exception) -> bool:
        if self._should_fallback_to_template(exc):
            return False
        message = str(exc).lower()
        retryable_keywords = (
            "天数不匹配",
            "day_number",
            "validation error",
            "field required",
            "missing",
            "venue_name",
            "不可解析",
            "timed out",
            "timeout",
            "readtimeout",
            "apitimeouterror",
            "json_object",
            "plain_text_json",
            "minimal",
        )
        return isinstance(exc, (ValueError, RuntimeError, httpx.TimeoutException)) and any(
            keyword in message for keyword in retryable_keywords
        )

    def _is_retryable_seed_error(self, exc: Exception) -> bool:
        if self._should_fallback_to_template(exc):
            return False
        message = str(exc).lower()
        retryable_keywords = (
            "timed out",
            "timeout",
            "readtimeout",
            "apitimeouterror",
            "json_object",
            "plain_text_json",
            "不可解析",
            "error code: 400",
            "output data may contain inappropriate content",
            "service unavailable",
            "rate limit",
            "temporarily",
        )
        return isinstance(exc, (ValueError, RuntimeError, httpx.TimeoutException)) and any(
            keyword in message for keyword in retryable_keywords
        )

    def _should_switch_to_backup_model(self, exc: Exception) -> bool:
        if self._should_fallback_to_template(exc):
            return True
        message = str(exc).lower()
        switch_keywords = (
            "apiconnectionerror",
            "connection error",
            "connecterror",
            "service unavailable",
            "temporarily unavailable",
            "server error",
            "internal server error",
            "bad gateway",
            "gateway timeout",
            "overloaded",
            "dns",
            "name or service not known",
            "connection refused",
            "ssl",
        )
        return isinstance(exc, (ValueError, RuntimeError, httpx.NetworkError)) and any(
            keyword in message for keyword in switch_keywords
        )

    def _should_fallback_to_template(self, exc: Exception) -> bool:
        message = str(exc).lower()
        fallback_keywords = (
            "error code: 429",
            "429 too many requests",
            "too many requests",
            "ratelimiterror",
            "rate limit",
            "setlimitexceeded",
            "service has been paused",
            "insufficient_quota",
        )
        return any(keyword in message for keyword in fallback_keywords)

    def _build_compose_user_payload(
        self,
        request: TripPlanningRequest,
        initial_plan: InitialPlanDraft,
        context: PlanningContext,
        tool_trace: list[ToolCallRecord],
    ) -> dict[str, Any]:
        for detail_level in ("full", "compact", "minimal"):
            payload = {
                "request": request.model_dump(mode="json"),
                "initial_plan": initial_plan.model_dump(mode="json"),
                "planning_context": self._serialize_context_for_llm(context, detail_level),
                "tool_trace": self._serialize_tool_trace_for_llm(tool_trace, detail_level),
            }
            if len(json.dumps(payload, ensure_ascii=True)) <= 180000:
                return payload

        return {
            "request": request.model_dump(mode="json"),
            "initial_plan": initial_plan.model_dump(mode="json"),
            "planning_context": self._serialize_context_for_llm(context, "minimal"),
            "tool_trace": self._serialize_tool_trace_for_llm(tool_trace, "minimal"),
        }

    def _serialize_context_for_llm(self, context: PlanningContext, detail_level: str) -> dict[str, Any]:
        poi_limit = {"full": 8, "compact": 5, "minimal": 3}[detail_level]
        route_limit = {"full": 6, "compact": 4, "minimal": 2}[detail_level]
        step_limit = {"full": 4, "compact": 2, "minimal": 1}[detail_level]
        return {
            "destination": context.destination,
            "attractions": [self._serialize_poi_for_llm(item) for item in context.attractions[:poi_limit]],
            "restaurants": [self._serialize_poi_for_llm(item) for item in context.restaurants[:poi_limit]],
            "hotels": [self._serialize_poi_for_llm(item) for item in context.hotels[:poi_limit]],
            "routes": [
                self._serialize_route_for_llm(item, step_limit=step_limit)
                for item in context.routes[:route_limit]
            ],
            "weather": {
                "overview": context.weather.overview,
                "temperature_range": context.weather.temperature_range,
                "suggestions": context.weather.suggestions[:3],
                "daily_forecasts": [
                    item.model_dump(mode="json")
                    for item in context.weather.daily_forecasts[: max(2, route_limit)]
                ],
            },
        }

    def _serialize_tool_trace_for_llm(
        self,
        tool_trace: list[ToolCallRecord],
        detail_level: str,
    ) -> list[dict[str, Any]]:
        limit = {"full": 12, "compact": 8, "minimal": 4}[detail_level]
        serialized: list[dict[str, Any]] = []
        for item in tool_trace[:limit]:
            serialized.append(
                {
                    "tool_name": item.tool_name,
                    "success": item.success,
                    "summary": item.summary[:180],
                    "arguments": self._compact_tool_arguments(item.arguments),
                }
            )
        return serialized

    def _serialize_poi_for_llm(self, poi: Any) -> dict[str, Any]:
        return {
            "name": getattr(poi, "name", ""),
            "address": getattr(poi, "address", ""),
            "district": getattr(poi, "district", None),
            "tags": list(getattr(poi, "tags", [])[:3]),
            "opening_hours": getattr(poi, "opening_hours", None),
            "rating": getattr(poi, "rating", None),
        }

    def _serialize_route_for_llm(self, route: RouteSummary, step_limit: int) -> dict[str, Any]:
        return {
            "day_number": route.day_number,
            "title": route.title,
            "from_name": route.from_name,
            "to_name": route.to_name,
            "waypoints": route.waypoints[:4],
            "distance_text": route.distance_text,
            "duration_text": route.duration_text,
            "mode": route.mode,
            "estimated_transport_cost_cny": route.estimated_transport_cost_cny,
            "steps": [step.model_dump(mode="json") for step in route.steps[:step_limit]],
        }

    def _compact_tool_arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        compact: dict[str, Any] = {}
        for key in ("keywords", "city", "origin", "destination", "origin_address", "destination_address", "mode"):
            value = arguments.get(key)
            if value not in (None, "", []):
                compact[key] = value
        return compact

    async def _request_json_payload(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        temperature: float,
        max_tokens: int | None = None,
        client: Any | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        if client is None:
            client = self.client
        if model is None:
            model = self.primary_model or self.settings.openai_model
        assert client is not None

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=True)},
        ]
        errors: list[str] = []

        for mode in ("json_object", "plain_text_json", "minimal"):
            try:
                request_kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                }
                if mode != "minimal":
                    request_kwargs["temperature"] = temperature
                if max_tokens is not None:
                    request_kwargs["max_tokens"] = max_tokens
                if mode == "json_object":
                    request_kwargs["response_format"] = {"type": "json_object"}

                completion = await client.chat.completions.create(**request_kwargs)
                content = self._extract_message_content(completion)
                payload = extract_json_payload(content)
                if isinstance(payload, dict):
                    return payload
                errors.append(f"{mode}: 返回了不可解析的内容")
            except Exception as exc:
                errors.append(f"{mode}: {self._format_exception(exc)}")

        raise ValueError("；".join(errors))

    async def _build_initial_plan_with_provider(
        self,
        request: TripPlanningRequest,
        provider: LLMProvider,
    ) -> tuple[InitialPlanDraft, list[str]]:
        warnings: list[str] = []
        retry_specs = [
            (0.4, 2048),
            (0.2, 3072),
            (0.1, 3072),
            (0.0, 4096),
            (0.0, 4096),
        ]
        last_error: Exception | None = None
        for attempt, (temperature, max_tokens) in enumerate(retry_specs, start=1):
            try:
                draft = await self._generate_initial_plan_with_openai(
                    request,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    client=provider.client,
                    model=provider.model,
                )
                if provider.label != "主模型" and self.client is not None:
                    warnings.append(f"已切换到备用模型 {provider.model} 继续生成初步规划。")
                return draft, warnings
            except Exception as exc:
                last_error = exc
                if self._should_switch_to_backup_model(exc):
                    raise
                if not self._is_retryable_seed_error(exc) or attempt >= len(retry_specs):
                    break
                warnings.append(f"seed 第 {attempt} 次失败，已重试。原因: {self._format_exception(exc)}")
                await asyncio.sleep(min(2.0, 0.4 * attempt))

        assert last_error is not None
        raise last_error

    async def _compose_with_provider(
        self,
        request: TripPlanningRequest,
        initial_plan: InitialPlanDraft,
        context: PlanningContext,
        tool_trace: list[ToolCallRecord],
        provider: LLMProvider,
    ) -> tuple[TravelPlan, list[str]]:
        plan, warnings = await self._compose_with_openai(
            request=request,
            initial_plan=initial_plan,
            context=context,
            tool_trace=tool_trace,
            client=provider.client,
            model=provider.model,
        )
        if provider.label != "主模型" and self.client is not None:
            warnings = [f"已切换到备用模型 {provider.model} 继续生成最终行程。"] + warnings
        return plan, warnings

    def _extract_message_content(self, completion: Any) -> str:
        choices = getattr(completion, "choices", None) or []
        if not choices:
            return "{}"
        message = getattr(choices[0], "message", None)
        if message is None:
            return "{}"
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            fragments: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    fragments.append(str(item.get("text", "")))
            return "\n".join(fragment for fragment in fragments if fragment)
        return str(content or "{}")

    def _normalize_base_url(self, value: str) -> str:
        normalized = value.strip().rstrip("/")
        for suffix in ("/chat/completions", "/completions", "/responses"):
            if normalized.lower().endswith(suffix):
                normalized = normalized[: -len(suffix)]
                break
        return normalized

    def _format_exception(self, exc: Exception) -> str:
        parts = [f"{exc.__class__.__name__}: {exc}"] if str(exc) else [exc.__class__.__name__]
        cause = exc.__cause__ or exc.__context__
        if cause is not None and cause is not exc:
            if str(cause):
                parts.append(f"cause={cause.__class__.__name__}: {cause}")
            else:
                parts.append(f"cause={cause.__class__.__name__}")
        return " | ".join(parts)

    def _ensure_initial_plan_integrity(
        self,
        request: TripPlanningRequest,
        draft: InitialPlanDraft,
    ) -> None:
        if len(draft.days) != request.days:
            raise ValueError(f"初步规划天数不匹配: 期望 {request.days} 天，实际 {len(draft.days)} 天。")

        day_numbers = [day.day_number for day in draft.days]
        if len(day_numbers) != len(set(day_numbers)):
            raise ValueError("初步规划包含重复 day_number。")

        expected = set(range(1, request.days + 1))
        if set(day_numbers) != expected:
            raise ValueError("初步规划的 day_number 必须覆盖 1..request.days。")

    def _ensure_final_plan_integrity(
        self,
        request: TripPlanningRequest,
        plan: TravelPlan,
        require_routes: bool = True,
    ) -> None:
        if len(plan.days) != request.days:
            raise ValueError(f"最终行程天数不匹配: 期望 {request.days} 天，实际 {len(plan.days)} 天。")

        day_numbers = [day.day_number for day in plan.days]
        if len(day_numbers) != len(set(day_numbers)):
            raise ValueError("最终行程包含重复 day_number。")

        expected = set(range(1, request.days + 1))
        if set(day_numbers) != expected:
            raise ValueError("最终行程的 day_number 必须覆盖 1..request.days。")

        for day in plan.days:
            if not day.activities:
                raise ValueError(f"第 {day.day_number} 天缺少 activities。")
            if not day.meals:
                raise ValueError(f"第 {day.day_number} 天缺少 meals。")
            if require_routes and not day.route_summaries:
                raise ValueError(f"第 {day.day_number} 天缺少 route_summaries。")
            for route in day.route_summaries:
                if route.day_number not in (None, day.day_number):
                    raise ValueError(f"第 {day.day_number} 天 route_summaries.day_number 不一致。")
            expected_total = (
                day.cost_breakdown.accommodation_per_person_cny
                + day.cost_breakdown.transport_per_person_cny
                + day.cost_breakdown.food_per_person_cny
                + day.cost_breakdown.tickets_per_person_cny
                + day.cost_breakdown.extras_per_person_cny
            )
            if day.cost_breakdown.total_per_person_cny != expected_total:
                raise ValueError(f"第 {day.day_number} 天 cost_breakdown.total_per_person_cny 不一致。")

    def _normalize_plan_days(
        self,
        request: TripPlanningRequest,
        plan: TravelPlan,
        context: PlanningContext,
    ) -> TravelPlan:
        routes_by_day: dict[int, list[RouteSummary]] = {}
        for route in context.routes:
            if route.day_number is None:
                continue
            routes_by_day.setdefault(route.day_number, []).append(route)

        head_count = max(
            1,
            request.travelers.adults + request.travelers.children + request.travelers.seniors,
        )
        room_count = max(1, math.ceil(head_count / 2))
        stays = plan.stay_recommendations

        normalized_days: list[DayPlan] = []
        for day_index, day in enumerate(sorted(plan.days, key=lambda item: item.day_number)):
            route_summaries = list(day.route_summaries)
            if day.route_summary is not None and not route_summaries:
                route_summaries = [day.route_summary]
            if routes_by_day.get(day.day_number):
                route_summaries = routes_by_day[day.day_number]
            route_summaries = [
                route.model_copy(update={"day_number": day.day_number})
                if route.day_number is None
                else route
                for route in route_summaries
            ]

            stay = day.stay
            if not stay.hotel_name and stays:
                fallback_stay = stays[day_index % len(stays)]
                stay = stay.model_copy(
                    update={
                        "area": stay.area or fallback_stay.area or day.hotel_area,
                        "hotel_name": fallback_stay.hotel_name,
                        "reason": stay.reason or fallback_stay.reason,
                    }
                )
            elif not stay.hotel_name and context.hotels:
                hotel = context.hotels[day_index % len(context.hotels)]
                stay = stay.model_copy(
                    update={
                        "area": stay.area or hotel.address or day.hotel_area,
                        "hotel_name": hotel.name,
                        "reason": stay.reason or "靠近当日主要活动区域，换乘更省时。",
                    }
                )

            normalized_activities: list[Activity] = []
            for activity in day.activities:
                ticket_cost_cny = activity.ticket_cost_cny or self._extract_cny_amount(activity.expected_cost)
                expected_cost = activity.expected_cost or (f"¥{ticket_cost_cny}/人" if ticket_cost_cny else None)
                normalized_activities.append(
                    activity.model_copy(
                        update={
                            "ticket_cost_cny": max(0, ticket_cost_cny),
                            "expected_cost": expected_cost,
                        }
                    )
                )
            room_nightly_cost_cny = stay.room_nightly_cost_cny
            if room_nightly_cost_cny <= 0 and stays:
                room_nightly_cost_cny = self._extract_cny_amount(stays[day_index % len(stays)].nightly_budget)
            stay, resolved_hotel_area = self._reconcile_day_stay(
                day=day.model_copy(update={"activities": normalized_activities}),
                stay=stay,
                hotels=context.hotels,
            )
            stay = stay.model_copy(
                update={
                    "area": stay.area or resolved_hotel_area,
                    "room_nightly_cost_cny": max(0, room_nightly_cost_cny),
                }
            )

            normalized_meals: list[MealRecommendation] = []
            for meal in day.meals:
                estimated_cost_cny = meal.estimated_cost_cny or self._extract_cny_amount(meal.estimated_cost)
                estimated_cost = meal.estimated_cost or (f"¥{estimated_cost_cny}/人" if estimated_cost_cny else "")
                normalized_meals.append(
                    meal.model_copy(
                        update={
                            "estimated_cost_cny": max(0, estimated_cost_cny),
                            "estimated_cost": estimated_cost,
                        }
                    )
                )
            normalized_meals = self._ensure_daily_core_meals(
                meals=normalized_meals,
                restaurants=context.restaurants,
                stay=stay,
                hotel_area=day.hotel_area,
                day_theme=day.theme,
                day_index=day_index,
            )

            normalized_routes: list[RouteSummary] = []
            for route in route_summaries:
                transport_cost = route.estimated_transport_cost_cny
                normalized_routes.append(
                    route.model_copy(
                        update={
                            "estimated_transport_cost_cny": max(0, transport_cost),
                        }
                    )
                )
            normalized_activities = self._sync_activity_transport_from_routes(
                normalized_activities,
                normalized_routes,
            )
            transport_tips = self._merge_transport_tips(day.transport_tips, normalized_routes)

            tickets_per_person = sum(item.ticket_cost_cny for item in normalized_activities)
            food_per_person = sum(item.estimated_cost_cny for item in normalized_meals)
            transport_per_person = sum(item.estimated_transport_cost_cny for item in normalized_routes)
            accommodation_per_person = day.cost_breakdown.accommodation_per_person_cny
            if accommodation_per_person <= 0 and stay.room_nightly_cost_cny > 0:
                accommodation_per_person = int(round(stay.room_nightly_cost_cny * room_count / head_count))
            extras_per_person = day.cost_breakdown.extras_per_person_cny
            total_per_person = (
                accommodation_per_person
                + transport_per_person
                + food_per_person
                + tickets_per_person
                + extras_per_person
            )
            cost_breakdown = DayCostBreakdown(
                accommodation_per_person_cny=max(0, accommodation_per_person),
                transport_per_person_cny=max(0, transport_per_person),
                food_per_person_cny=max(0, food_per_person),
                tickets_per_person_cny=max(0, tickets_per_person),
                extras_per_person_cny=max(0, extras_per_person),
                total_per_person_cny=max(0, total_per_person),
            )

            normalized_days.append(
                day.model_copy(
                    update={
                        "hotel_area": resolved_hotel_area,
                        "stay": stay,
                        "activities": normalized_activities,
                        "meals": normalized_meals,
                        "transport_tips": transport_tips,
                        "route_summaries": normalized_routes,
                        "route_summary": normalized_routes[0] if normalized_routes else None,
                        "cost_breakdown": cost_breakdown,
                    }
                )
            )

        normalized_stays = self._normalize_stay_recommendations(
            existing_recommendations=plan.stay_recommendations,
            normalized_days=normalized_days,
            hotels=context.hotels,
        )
        return plan.model_copy(
            update={
                "days": normalized_days,
                "stay_recommendations": normalized_stays,
            }
        )

    def _ensure_daily_core_meals(
        self,
        meals: list[MealRecommendation],
        restaurants: list[Any],
        stay: DayStayInfo,
        hotel_area: str,
        day_theme: str,
        day_index: int,
    ) -> list[MealRecommendation]:
        by_type: dict[str, MealRecommendation] = {}
        for meal in meals:
            by_type.setdefault(meal.meal_type, meal)

        def _fallback_meal(meal_type: str) -> MealRecommendation:
            base_cost = {"breakfast": 30, "lunch": 80, "dinner": 120}[meal_type]
            if meal_type == "breakfast":
                venue = f"{stay.hotel_name} 早餐厅" if stay.hotel_name else f"{hotel_area or '酒店附近'} 早餐店"
                cuisine = "本地早餐"
                suggestion = "建议 08:00 前后用餐，出发前补充能量。"
            else:
                offset = 0 if meal_type == "lunch" else 1
                candidate = restaurants[(day_index * 2 + offset) % len(restaurants)] if restaurants else None
                venue = getattr(candidate, "name", "") or f"{day_theme} 附近餐厅"
                cuisine = ",".join(getattr(candidate, "tags", [])[:2]) if candidate else "本地风味"
                suggestion = "优先选择当日行程片区内餐厅，减少往返耗时。"
            return MealRecommendation(
                meal_type=meal_type,  # type: ignore[arg-type]
                venue_name=venue,
                cuisine=cuisine,
                suggestion=suggestion,
                estimated_cost=f"¥{base_cost}/人",
                estimated_cost_cny=base_cost,
            )

        ordered = [
            by_type.get("breakfast") or _fallback_meal("breakfast"),
            by_type.get("lunch") or _fallback_meal("lunch"),
            by_type.get("dinner") or _fallback_meal("dinner"),
        ]
        extras = [meal for meal in meals if meal.meal_type not in {"breakfast", "lunch", "dinner"}]
        return ordered + extras

    def _ensure_day_activity_coverage(
        self,
        day: DayPlan,
        activities: list[Activity],
        context: PlanningContext,
    ) -> list[Activity]:
        _ = (day, context)
        return activities

    def _pick_supplemental_activity(
        self,
        day: DayPlan,
        context: PlanningContext,
        used_locations: set[str],
    ) -> Activity | None:
        for poi in context.attractions:
            normalized_name = self._normalize_location_text(getattr(poi, "name", ""))
            if not normalized_name or normalized_name in used_locations:
                continue
            if day.hotel_area and self._text_overlap_score(normalized_name, day.hotel_area, hit_score=1, partial_score=1) <= 0:
                continue
            start_time = self._next_activity_start_time(day.activities)
            return Activity(
                start_time=start_time,
                end_time="17:30",
                title=f"{poi.name} 周边延展游览",
                category="explore",
                description=f"补充下午时段，在 {poi.name} 周边继续安排街区漫游或轻量参观。",
                location_name=poi.name,
                transport_from_previous="从上一站短途前往周边片区继续游览。",
                expected_cost="¥0-60/人",
                ticket_cost_cny=0,
                booking_tip="按现场人流与体力情况灵活调整停留时长。",
            )

        area_name = day.hotel_area or day.stay.area or (day.activities[-1].location_name if day.activities else day.theme)
        if not area_name:
            return None
        start_time = self._next_activity_start_time(day.activities)
        return Activity(
            start_time=start_time,
            end_time="17:30",
            title=f"{area_name} 周边漫游",
            category="explore",
            description="补充下午时段，在当日主要活动片区安排街区散步、茶歇或自由探索。",
            location_name=area_name,
            transport_from_previous="从上一站短途前往周边片区继续游览。",
            expected_cost="¥0-50/人",
            ticket_cost_cny=0,
            booking_tip="优先选择与主行程顺路的街区或开放区域。",
        )

    def _next_activity_start_time(self, activities: list[Activity]) -> str:
        if not activities:
            return "14:00"
        latest_end = max((activity.end_time for activity in activities if activity.end_time), default="12:00")
        if latest_end < "13:30":
            return "14:00"
        if latest_end < "15:00":
            return "15:00"
        return latest_end

    def _reconcile_day_stay(
        self,
        day: DayPlan,
        stay: DayStayInfo,
        hotels: list[Any],
    ) -> tuple[DayStayInfo, str]:
        resolved_hotel_area = day.hotel_area or stay.area
        if not hotels:
            return stay, resolved_hotel_area

        best_hotel = max(
            hotels,
            key=lambda hotel: self._score_hotel_for_day(hotel, day, stay),
        )
        best_score = self._score_hotel_for_day(best_hotel, day, stay)

        current_hotel = self._match_hotel_candidate(stay.hotel_name, hotels)
        current_score = self._score_hotel_for_day(
            current_hotel or self._stay_stub_poi(stay, day.hotel_area),
            day,
            stay,
        )

        should_replace = False
        if not stay.hotel_name:
            should_replace = best_score > 0
        elif current_hotel is None:
            should_replace = best_score >= current_score + 2
        elif best_hotel.name != current_hotel.name:
            should_replace = best_score >= current_score + 4

        if should_replace:
            resolved_hotel_area = self._preferred_area_for_day(
                day=day,
                stay=stay,
                fallback_area=(
                getattr(best_hotel, "district", "")
                or getattr(best_hotel, "address", "")
                or day.hotel_area
                or stay.area
                ),
            )
            return (
                stay.model_copy(
                    update={
                        "area": resolved_hotel_area,
                        "hotel_name": getattr(best_hotel, "name", stay.hotel_name),
                        "reason": self._hotel_reason_for_day(best_hotel, day),
                    }
                ),
                resolved_hotel_area,
            )

        if current_hotel is not None:
            resolved_hotel_area = self._preferred_area_for_day(
                day=day,
                stay=stay,
                fallback_area=(
                stay.area
                or getattr(current_hotel, "district", "")
                or getattr(current_hotel, "address", "")
                or day.hotel_area
                ),
            )
            return (
                stay.model_copy(
                    update={
                        "area": resolved_hotel_area,
                        "hotel_name": getattr(current_hotel, "name", stay.hotel_name),
                    }
                ),
                resolved_hotel_area,
            )

        return stay, resolved_hotel_area

    def _preferred_area_for_day(
        self,
        day: DayPlan,
        stay: DayStayInfo,
        fallback_area: str,
    ) -> str:
        for candidate in [day.hotel_area, stay.area]:
            if self._area_matches_day(candidate, day):
                return candidate
        return fallback_area or day.hotel_area or stay.area

    def _area_matches_day(
        self,
        area: str,
        day: DayPlan,
    ) -> bool:
        normalized_area = self._normalize_location_text(area)
        if not normalized_area:
            return False
        for activity in day.activities:
            normalized_location = self._normalize_location_text(activity.location_name)
            if not normalized_location:
                continue
            if normalized_area in normalized_location or normalized_location in normalized_area:
                return True
            if any(fragment in normalized_location for fragment in self._location_fragments(normalized_area)):
                return True
        return False

    def _match_hotel_candidate(
        self,
        hotel_name: str,
        hotels: list[Any],
    ) -> Any | None:
        normalized_target = self._normalize_location_text(hotel_name)
        if not normalized_target:
            return None

        scored: list[tuple[int, int, Any]] = []
        for hotel in hotels:
            candidate_name = self._normalize_location_text(getattr(hotel, "name", ""))
            if not candidate_name:
                continue
            exact_penalty = 0 if candidate_name == normalized_target else 1
            contains_penalty = 0 if normalized_target in candidate_name or candidate_name in normalized_target else 1
            if exact_penalty and contains_penalty:
                continue
            scored.append((exact_penalty, contains_penalty, hotel))

        if not scored:
            return None
        scored.sort(key=lambda item: item[:2])
        return scored[0][2]

    def _score_hotel_for_day(
        self,
        hotel: Any,
        day: DayPlan,
        stay: DayStayInfo,
    ) -> int:
        hotel_text = self._normalize_location_text(
            " ".join(
                [
                    str(getattr(hotel, "name", "")),
                    str(getattr(hotel, "address", "")),
                    str(getattr(hotel, "district", "")),
                ]
            )
        )
        if not hotel_text:
            return 0

        score = 0
        if any(word in hotel_text for word in ("酒店", "宾馆", "旅馆", "民宿", "客栈")):
            score += 1

        area_references = [day.hotel_area, stay.area]
        for phrase in area_references:
            score += self._text_overlap_score(hotel_text, phrase, hit_score=8, partial_score=3)

        for activity in day.activities:
            score += self._text_overlap_score(hotel_text, activity.location_name, hit_score=6, partial_score=2)

        return score

    def _text_overlap_score(
        self,
        hotel_text: str,
        phrase: str,
        hit_score: int,
        partial_score: int,
    ) -> int:
        normalized_phrase = self._normalize_location_text(phrase)
        if not normalized_phrase:
            return 0
        if normalized_phrase in hotel_text:
            return hit_score

        partial_hits = 0
        for fragment in self._location_fragments(normalized_phrase):
            if fragment and fragment in hotel_text:
                partial_hits += 1
        if partial_hits:
            return partial_score * partial_hits
        return 0

    def _location_fragments(self, value: str) -> list[str]:
        fragments: list[str] = []
        for size in range(min(4, len(value)), 1, -1):
            for index in range(0, len(value) - size + 1):
                fragments.append(value[index : index + size])
        unique: list[str] = []
        seen: set[str] = set()
        for fragment in fragments:
            if fragment in seen:
                continue
            seen.add(fragment)
            unique.append(fragment)
        return unique[:8]

    def _normalize_location_text(self, value: str | None) -> str:
        if not value:
            return ""
        normalized = re.sub(r"\s+", "", str(value).strip())
        normalized = normalized.lower()
        for suffix in (
            "历史文化街区",
            "风景名胜区",
            "旅游度假区",
            "度假区",
            "风景区",
            "景区",
            "片区",
            "区域",
            "商圈",
            "古城",
            "街道",
            "酒店",
            "宾馆",
            "旅馆",
            "民宿",
            "客栈",
            "店",
            "寺",
        ):
            if normalized.endswith(suffix) and len(normalized) > len(suffix):
                normalized = normalized[: -len(suffix)]
                break
        return normalized

    def _stay_stub_poi(
        self,
        stay: DayStayInfo,
        hotel_area: str,
    ) -> Any:
        class _StayStub:
            def __init__(self, name: str, address: str) -> None:
                self.name = name
                self.address = address
                self.district = ""

        return _StayStub(stay.hotel_name, stay.area or hotel_area)

    def _hotel_reason_for_day(
        self,
        hotel: Any,
        day: DayPlan,
    ) -> str:
        focus = day.activities[0].location_name if day.activities else day.theme
        return f"更贴近{focus}等当日活动区域，往返更省时。"

    def _sync_activity_transport_from_routes(
        self,
        activities: list[Activity],
        routes: list[RouteSummary],
    ) -> list[Activity]:
        if not activities:
            return activities

        normalized: list[Activity] = []
        for index, activity in enumerate(activities):
            transport_tip = activity.transport_from_previous
            if index < len(routes):
                transport_tip = self._route_to_transport_tip(routes[index])
            normalized.append(
                activity.model_copy(
                    update={
                        "transport_from_previous": transport_tip,
                    }
                )
            )
        return normalized

    def _merge_transport_tips(
        self,
        existing_tips: list[str],
        routes: list[RouteSummary],
    ) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        route_tips = [self._route_to_transport_tip(route) for route in routes]
        for tip in [*existing_tips, *route_tips]:
            normalized_tip = tip.strip()
            if not normalized_tip or normalized_tip in seen:
                continue
            seen.add(normalized_tip)
            merged.append(normalized_tip)
        return merged

    def _route_to_transport_tip(self, route: RouteSummary) -> str:
        mode_label = {
            "walking": "步行",
            "transit": "公共交通",
            "bicycling": "骑行",
            "driving": "驾车",
        }.get(route.mode, route.mode)
        parts = [f"从 {route.from_name} 前往 {route.to_name}"]
        if mode_label:
            parts.append(f"建议{mode_label}")
        if route.duration_text:
            parts.append(route.duration_text)
        if route.distance_text:
            parts.append(route.distance_text)
        return "，".join(parts)

    def _normalize_stay_recommendations(
        self,
        existing_recommendations: list[StayRecommendation],
        normalized_days: list[DayPlan],
        hotels: list[Any],
    ) -> list[StayRecommendation]:
        existing_by_name: dict[str, StayRecommendation] = {}
        for recommendation in existing_recommendations:
            key = self._normalize_location_text(recommendation.hotel_name)
            if key and key not in existing_by_name:
                existing_by_name[key] = recommendation

        recommendations: list[StayRecommendation] = []
        seen: set[str] = set()
        for day in normalized_days:
            hotel_name = day.stay.hotel_name.strip()
            area = (day.stay.area or day.hotel_area).strip()
            if not hotel_name and not area:
                continue

            key = self._normalize_location_text(hotel_name or area)
            if key in seen:
                continue
            seen.add(key)

            existing = existing_by_name.get(self._normalize_location_text(hotel_name))
            candidate_hotel = self._match_hotel_candidate(hotel_name, hotels)
            recommendation_area = (
                area
                or getattr(candidate_hotel, "district", "")
                or getattr(candidate_hotel, "address", "")
                or (existing.area if existing is not None else "")
            )
            recommendation_reason = (
                day.stay.reason
                or (existing.reason if existing is not None else "")
                or f"更贴近第 {day.day_number} 天活动区域，通勤更省时。"
            )
            nightly_budget = self._format_nightly_budget(day.stay.room_nightly_cost_cny)
            if not nightly_budget and existing is not None:
                nightly_budget = existing.nightly_budget

            recommendations.append(
                StayRecommendation(
                    area=recommendation_area,
                    hotel_name=hotel_name or (existing.hotel_name if existing is not None else ""),
                    reason=recommendation_reason,
                    nightly_budget=nightly_budget,
                )
            )

        if recommendations:
            return recommendations

        if existing_recommendations:
            return existing_recommendations

        fallback: list[StayRecommendation] = []
        for hotel in hotels[:2]:
            area = getattr(hotel, "district", "") or getattr(hotel, "address", "")
            fallback.append(
                StayRecommendation(
                    area=area,
                    hotel_name=getattr(hotel, "name", ""),
                    reason="靠近主要活动区域，适合作为住宿备选。",
                    nightly_budget="",
                )
            )
        return fallback

    def _attach_plan_truth(
        self,
        plan: TravelPlan,
        context: PlanningContext,
        destination: str,
    ) -> TravelPlan:
        updated_days: list[DayPlan] = []
        for day in sorted(plan.days, key=lambda item: item.day_number):
            day_fallbacks: list[str] = []
            map_pois: list[DayPOI] = []

            stay_lookup = day.stay.hotel_name or day.hotel_area
            stay_poi = self._resolve_final_poi(
                lookup_name=stay_lookup,
                candidates=context.hotels,
                destination=destination,
                fallback_name=stay_lookup,
            )
            if stay_lookup and stay_poi is not None and stay_poi.source == "manual_placeholder":
                day_fallbacks.append("stay_poi_unresolved")
            updated_stay = day.stay.model_copy(update={"poi": stay_poi})
            if stay_poi is not None and updated_stay.hotel_name:
                map_pois.append(DayPOI(kind="stay", label=updated_stay.hotel_name, poi=stay_poi))

            updated_activities: list[Activity] = []
            for activity in day.activities:
                activity_poi = self._resolve_final_poi(
                    lookup_name=activity.location_name,
                    candidates=context.attractions,
                    destination=destination,
                    fallback_name=activity.location_name,
                )
                if activity.location_name and activity_poi is not None and activity_poi.source == "manual_placeholder":
                    day_fallbacks.append(f"activity_poi_unresolved:{activity.location_name}")
                updated_activity = activity.model_copy(update={"poi": activity_poi})
                updated_activities.append(updated_activity)
                if activity_poi is not None:
                    map_pois.append(
                        DayPOI(
                            kind="activity",
                            label=activity.title or activity.location_name,
                            poi=activity_poi,
                        )
                    )

            updated_meals: list[MealRecommendation] = []
            for meal in day.meals:
                meal_poi = None
                if meal.venue_name:
                    meal_poi = self._resolve_final_poi(
                        lookup_name=meal.venue_name,
                        candidates=context.restaurants,
                        destination=destination,
                        fallback_name=meal.venue_name,
                    )
                    if meal_poi is not None and meal_poi.source == "manual_placeholder" and meal.meal_type == "breakfast":
                        meal_poi = updated_stay.poi
                updated_meal = meal.model_copy(update={"poi": meal_poi})
                updated_meals.append(updated_meal)
                if meal_poi is not None:
                    map_pois.append(
                        DayPOI(
                            kind="meal",
                            label=meal.meal_type,
                            poi=meal_poi,
                        )
                    )

            route_segments = list(day.route_summaries)
            if not route_segments and day.route_summary is not None:
                route_segments = [day.route_summary]
            if updated_activities and not route_segments:
                day_fallbacks.append("route_summary_missing")

            updated_days.append(
                day.model_copy(
                    update={
                        "stay": updated_stay,
                        "activities": updated_activities,
                        "meals": updated_meals,
                        "route_segments": route_segments,
                        "map_pois": self._dedupe_day_pois(map_pois),
                        "fallbacks": sorted(set(day.fallbacks + day_fallbacks)),
                    }
                )
            )

        return plan.model_copy(update={"days": updated_days})

    def _resolve_final_poi(
        self,
        lookup_name: str,
        candidates: list[POIRecommendation],
        destination: str,
        fallback_name: str = "",
    ) -> POIRecommendation | None:
        normalized_lookup = self._normalize_location_text(lookup_name)
        if not normalized_lookup:
            return None

        matched = self._match_named_poi(normalized_lookup, candidates)
        if matched is not None:
            return self._ensure_display_ready_poi(matched, destination)

        display_name = fallback_name.strip() or lookup_name.strip()
        if not display_name:
            return None
        return POIRecommendation(
            name=display_name,
            address=f"{destination}{display_name}",
            district=destination,
            source="manual_placeholder",
        )

    def _match_named_poi(
        self,
        normalized_lookup: str,
        candidates: list[POIRecommendation],
    ) -> POIRecommendation | None:
        scored: list[tuple[int, int, int, int, POIRecommendation]] = []
        for candidate in candidates:
            normalized_name = self._normalize_location_text(candidate.name)
            if not normalized_name:
                continue
            exact_penalty = 0 if normalized_name == normalized_lookup else 1
            contains_penalty = 0 if normalized_lookup in normalized_name or normalized_name in normalized_lookup else 1
            coordinate_penalty = 0 if candidate.longitude is not None and candidate.latitude is not None else 1
            fragment_hits = sum(
                1
                for fragment in self._location_fragments(normalized_lookup)
                if fragment and fragment in normalized_name
            )
            fragment_penalty = 0 if fragment_hits > 0 else 1
            if exact_penalty and contains_penalty and fragment_penalty:
                continue
            scored.append(
                (
                    exact_penalty,
                    contains_penalty,
                    fragment_penalty,
                    coordinate_penalty,
                    candidate,
                )
            )

        if not scored:
            return None
        scored.sort(key=lambda item: item[:4])
        return scored[0][4]

    def _ensure_display_ready_poi(
        self,
        poi: POIRecommendation,
        destination: str,
    ) -> POIRecommendation:
        district = poi.district or destination
        address = poi.address or f"{district}{poi.name}"
        return poi.model_copy(update={"district": district, "address": address})

    def _dedupe_day_pois(
        self,
        items: list[DayPOI],
    ) -> list[DayPOI]:
        deduped: list[DayPOI] = []
        seen: set[str] = set()
        for item in items:
            key = item.poi.poi_id or f"{item.kind}:{item.poi.name}:{item.poi.address}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _format_nightly_budget(self, room_nightly_cost_cny: int) -> str:
        if room_nightly_cost_cny <= 0:
            return ""
        return f"¥{room_nightly_cost_cny:,}/晚"

    def _apply_deterministic_budget(
        self,
        request: TripPlanningRequest,
        plan: TravelPlan,
    ) -> TravelPlan:
        _ = request
        sorted_days = sorted(plan.days, key=lambda item: item.day_number)
        accommodation = sum(day.cost_breakdown.accommodation_per_person_cny for day in sorted_days)
        transport = sum(day.cost_breakdown.transport_per_person_cny for day in sorted_days)
        food = sum(day.cost_breakdown.food_per_person_cny for day in sorted_days)
        tickets = sum(day.cost_breakdown.tickets_per_person_cny for day in sorted_days)
        extras = sum(day.cost_breakdown.extras_per_person_cny for day in sorted_days)
        total = sum(day.cost_breakdown.total_per_person_cny for day in sorted_days)

        return plan.model_copy(
            update={
                "estimated_budget": BudgetBreakdown(
                    currency="CNY",
                    accommodation=self._format_per_person_amount(accommodation),
                    transport=self._format_per_person_amount(transport),
                    food=self._format_per_person_amount(food),
                    tickets=self._format_per_person_amount(tickets),
                    extras=self._format_per_person_amount(extras),
                    total_estimate=self._format_per_person_amount(total),
                ),
                "days": sorted_days,
            }
        )

    def _extract_cny_amount(self, value: str | None) -> int:
        if not value:
            return 0
        numbers = [float(item.replace(",", "")) for item in re.findall(r"\d+(?:\.\d+)?", value)]
        if not numbers:
            return 0
        if len(numbers) == 1:
            return max(0, int(round(numbers[0])))
        return max(0, int(round(sum(numbers[:2]) / 2)))

    def _format_per_person_amount(self, value: int) -> str:
        return f"¥{max(0, value):,}/人"

    def _fallback_initial_plan(self, request: TripPlanningRequest) -> InitialPlanDraft:
        interest_pool = request.interests or ["城市地标", "本地文化", "特色美食", "休闲漫游"]
        days: list[InitialPlanDay] = []
        for day_index in range(request.days):
            trip_date = request.start_date + timedelta(days=day_index)
            must_visit = []
            if request.must_visit:
                must_visit = [request.must_visit[day_index % len(request.must_visit)]]
            focus = must_visit[0] if must_visit else interest_pool[day_index % len(interest_pool)]
            days.append(
                InitialPlanDay(
                    day_number=day_index + 1,
                    date=str(trip_date),
                    theme=self._theme_for_day(day_index, request),
                    focus=focus,
                    must_visit=must_visit,
                    poi_query=f"{request.destination} {focus} 景点",
                    dining_query=f"{request.destination} {focus} 附近美食",
                )
            )
        return InitialPlanDraft(
            summary=f"先按 {request.days} 天拆分 {request.destination} 行程主题，再让各个 Agent 补齐景点、天气、路线和餐饮信息。",
            days=days,
        )

    def _fallback_plan(
        self,
        request: TripPlanningRequest,
        initial_plan: InitialPlanDraft,
        context: PlanningContext,
    ) -> TravelPlan:
        attractions = context.attractions or []
        restaurants = context.restaurants or []
        hotels = context.hotels or []
        daily_forecasts = context.weather.daily_forecasts or []
        routes = context.routes or []

        budget_map = {
            "economy": ("¥280-450/晚", "¥60-120/天", "¥50-100/天", "¥100-180/天", "¥500-900/人"),
            "comfort": ("¥450-800/晚", "¥120-220/天", "¥120-220/天", "¥180-320/天", "¥1200-2200/人"),
            "luxury": ("¥900-1800/晚", "¥260-500/天", "¥280-480/天", "¥320-600/天", "¥2800-5200/人"),
        }
        stay_cost, transport_cost, food_cost, ticket_cost, total_cost = budget_map[request.budget_level]

        days: list[DayPlan] = []
        for day_index in range(request.days):
            trip_date = request.start_date + timedelta(days=day_index)
            seed_day = initial_plan.days[day_index] if day_index < len(initial_plan.days) else None
            hotel = hotels[day_index % len(hotels)] if hotels else None
            day_weather = daily_forecasts[day_index] if day_index < len(daily_forecasts) else self._default_daily_forecast(str(trip_date))
            day_route = routes[day_index] if day_index < len(routes) else None
            day_attractions = self._select_day_attractions(attractions, seed_day, day_index)
            day_restaurants = self._select_day_restaurants(restaurants, day_index)

            activities: list[Activity] = []
            for attraction_index, attraction in enumerate(day_attractions[:2]):
                start_time = "09:00" if attraction_index == 0 else "14:00"
                end_time = "11:30" if attraction_index == 0 else "17:00"
                transport_tip = "从酒店出发，优先使用地铁或网约车。" if attraction_index == 0 else "结合路线规划在午餐后前往下一站。"
                if day_route and day_route.steps:
                    step_index = min(attraction_index, len(day_route.steps) - 1)
                    transport_tip = day_route.steps[step_index].instruction or transport_tip
                activities.append(
                    Activity(
                        start_time=start_time,
                        end_time=end_time,
                        title=f"游览 {attraction.name}",
                        category="sightseeing" if attraction_index == 0 else "explore",
                        description=f"围绕 {attraction.name} 安排核心游览与拍照时间，并根据现场排队情况灵活微调。",
                        location_name=attraction.name,
                        transport_from_previous=transport_tip,
                        expected_cost="¥80/人",
                        ticket_cost_cny=80,
                        booking_tip="热门景点建议提前预约并错峰到达",
                    )
                )
            if not activities:
                focus = seed_day.focus if seed_day else request.destination
                activities.append(
                    Activity(
                        start_time="09:30",
                        end_time="12:00",
                        title=f"{focus} 城市漫游",
                        category="explore",
                        description=(
                            f"围绕 {focus} 安排一段弹性较高的城市漫游，"
                            "优先覆盖核心街区、地标外观和适合停留拍照的开放区域。"
                        ),
                        location_name=request.destination,
                        transport_from_previous="从住宿区域出发，优先使用地铁或步行衔接。",
                        expected_cost="¥0/人",
                        ticket_cost_cny=0,
                        booking_tip="根据当天体力和天气灵活调整停留时长。",
                    )
                )

            if day_route is None:
                day_route = self._fallback_route_summary(
                    day_number=day_index + 1,
                    request=request,
                    hotel=hotel,
                    seed_day=seed_day,
                    destination_name=activities[0].location_name,
                )

            meals = self._build_meals(day_restaurants, food_cost)
            route_tip = (
                f"参考路线总时长约 {day_route.duration_text}。"
                if day_route and day_route.duration_text
                else "优先选择地铁与网约车组合，兼顾效率与舒适度。"
            )
            transport_tips = [
                f"天气：{day_weather.day_weather or context.weather.overview}，建议按当天实际温度调整出发时间。",
                route_tip,
                day_weather.advice or "午后注意补水，夜间备一件薄外套。",
            ]

            days.append(
                DayPlan(
                    day_number=day_index + 1,
                    date=str(trip_date),
                    theme=seed_day.theme if seed_day else self._theme_for_day(day_index, request),
                    overview=(
                        f"第 {day_index + 1} 天以 {seed_day.focus if seed_day else request.destination} 为重点，"
                        f"串联景点、餐饮和返程动线，整体节奏保持{self._pace_label(request.pace)}。"
                    ),
                    hotel_area=hotel.address if hotel and hotel.address else request.hotel_style,
                    transport_tips=[tip for tip in transport_tips if tip],
                    meals=meals,
                    activities=activities,
                    weather=day_weather,
                    route_summary=day_route,
                    route_summaries=[day_route] if day_route else [],
                    stay=DayStayInfo(
                        area=hotel.address if hotel and hotel.address else request.hotel_style,
                        hotel_name=hotel.name if hotel else f"{request.destination} 市中心酒店",
                        reason="靠近主要游览区域，适合当日行程动线。",
                        room_nightly_cost_cny=self._extract_cny_amount(stay_cost),
                    ),
                    cost_breakdown=DayCostBreakdown(),
                )
            )

        stay_recommendations = [
            StayRecommendation(
                area=hotel.address or request.hotel_style,
                hotel_name=hotel.name,
                reason="靠近主要游览片区，适合多日行程中转。",
                nightly_budget=stay_cost,
            )
            for hotel in hotels[:2]
        ]
        if not stay_recommendations:
            stay_recommendations.append(
                StayRecommendation(
                    area=request.hotel_style,
                    hotel_name=f"{request.destination} 市中心酒店",
                    reason="交通便利，适合作为默认住宿区域。",
                    nightly_budget=stay_cost,
                )
            )

        return TravelPlan(
            title=f"{request.destination}{request.days}天智能旅行计划",
            summary=(
                f"围绕 {request.destination} 设计了一份 {request.days} 天行程，"
                f"先由总控 Agent 输出初步草案，再结合景点、天气、餐饮和路线信息汇总成最终计划。"
            ),
            weather_summary=f"{context.weather.overview} 温度约 {context.weather.temperature_range}。",
            best_booking_tip="热门景点和核心商圈酒店建议至少提前 3-7 天预订，节假日需更早锁定。",
            estimated_budget=BudgetBreakdown(
                accommodation=stay_cost,
                transport=transport_cost,
                food=food_cost,
                tickets=ticket_cost,
                extras="¥100-300/人",
                total_estimate=total_cost,
            ),
            stay_recommendations=stay_recommendations,
            city_tips=[
                "第一天尽量安排轻量行程，避免长途到达后过度疲劳。",
                "核心景点建议早到，午后转入街区或美食场景。",
                "如有老人或儿童同行，适当压缩单日步行距离。",
            ],
            packing_list=[
                "身份证件与预订信息",
                "舒适步行鞋",
                "轻薄外套",
                "充电宝和数据线",
                "基础防晒用品",
            ],
            days=days,
        )

    def _build_fallback_final_plan(
        self,
        request: TripPlanningRequest,
        initial_plan: InitialPlanDraft,
        context: PlanningContext,
    ) -> TravelPlan:
        plan = self._fallback_plan(request, initial_plan, context)
        plan = self._normalize_plan_days(request, plan, context)
        self._ensure_final_plan_integrity(request, plan, require_routes=bool(context.routes))
        return self._apply_deterministic_budget(request, plan)

    def _fallback_route_summary(
        self,
        day_number: int,
        request: TripPlanningRequest,
        hotel: Any | None,
        seed_day: InitialPlanDay | None,
        destination_name: str,
    ) -> RouteSummary:
        hotel_name = getattr(hotel, "name", "") if hotel is not None else ""
        hotel_area = getattr(hotel, "address", "") if hotel is not None else ""
        focus = seed_day.focus if seed_day else request.destination
        return RouteSummary(
            day_number=day_number,
            title=f"第 {day_number} 天 {focus} 动线",
            from_name=hotel_name or hotel_area or request.hotel_style,
            to_name=destination_name or request.destination,
            waypoints=[focus] if focus and focus != request.destination else [],
            duration_text="约 30-45 分钟",
            mode="transit",
            estimated_transport_cost_cny=20,
            steps=[
                RouteStep(
                    instruction="从住宿区域出发，优先乘坐地铁或打车前往当日核心片区。",
                    distance_text="约 8 公里",
                    duration_text="约 30-45 分钟",
                )
            ],
        )

    def _default_daily_forecast(self, date: str) -> DailyForecast:
        return DailyForecast(
            date=date,
            day_weather="晴到多云",
            night_weather="多云",
            high_temperature="28",
            low_temperature="20",
            advice="中午注意防晒，夜间可准备一件薄外套。",
        )

    def _select_day_attractions(
        self,
        attractions: list,
        seed_day: InitialPlanDay | None,
        day_index: int,
    ) -> list:
        if not attractions:
            return []
        selected: list = []
        if seed_day and seed_day.must_visit:
            for keyword in seed_day.must_visit:
                matched = next((poi for poi in attractions if keyword in poi.name), None)
                if matched and matched not in selected:
                    selected.append(matched)
        start = day_index % len(attractions)
        for offset in range(len(attractions)):
            poi = attractions[(start + offset) % len(attractions)]
            if poi not in selected:
                selected.append(poi)
            if len(selected) >= 2:
                break
        return selected

    def _select_day_restaurants(self, restaurants: list, day_index: int) -> list:
        if not restaurants:
            return []
        lunch = restaurants[day_index % len(restaurants)]
        dinner = restaurants[(day_index + 1) % len(restaurants)] if len(restaurants) > 1 else lunch
        return [lunch, dinner]

    def _build_meals(self, restaurants: list, food_cost: str) -> list[MealRecommendation]:
        meal_types = ["lunch", "dinner"]
        suggestions = [
            "中午建议安排在核心景点附近，减少往返折返。",
            "晚餐可放在夜游片区附近，方便继续散步或返程。",
        ]
        meals: list[MealRecommendation] = []
        for index, restaurant in enumerate(restaurants[:2]):
            meals.append(
                MealRecommendation(
                    meal_type=meal_types[index],
                    venue_name=restaurant.name,
                    cuisine="本地特色 / 人气餐厅",
                    suggestion=suggestions[index],
                    estimated_cost=food_cost,
                    estimated_cost_cny=self._extract_cny_amount(food_cost),
                )
            )
        return meals

    def _theme_for_day(self, day_index: int, request: TripPlanningRequest) -> str:
        themes = [
            "城市初见与核心地标",
            "文化探索与街区漫游",
            "自然休闲与夜游体验",
            "深度打卡与美食搜罗",
        ]
        if request.must_visit and day_index == 0:
            return f"优先打卡 {request.must_visit[0]}"
        return themes[day_index % len(themes)]

    def _pace_label(self, pace: str) -> str:
        return {
            "relaxed": "轻松",
            "balanced": "均衡",
            "intense": "紧凑",
        }.get(pace, "均衡")
