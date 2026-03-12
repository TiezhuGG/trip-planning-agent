from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from app.config import Settings
from app.schemas.planning import (
    Activity,
    BudgetBreakdown,
    DailyForecast,
    DayPlan,
    InitialPlanDay,
    InitialPlanDraft,
    MealRecommendation,
    PlanningContext,
    RouteSummary,
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


class TravelAIClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = None
        if settings.has_openai and AsyncOpenAI is not None:
            kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
            if settings.openai_base_url:
                kwargs["base_url"] = settings.openai_base_url
            self.client = AsyncOpenAI(**kwargs)

    async def build_initial_plan(self, request: TripPlanningRequest) -> InitialPlanBuildResult:
        if self.client is not None:
            try:
                return InitialPlanBuildResult(
                    draft=await self._generate_initial_plan_with_openai(request),
                    used_llm=True,
                    fallback_used=False,
                    warnings=[],
                )
            except Exception as exc:
                return InitialPlanBuildResult(
                    draft=self._fallback_initial_plan(request),
                    used_llm=False,
                    fallback_used=True,
                    warnings=[f"初步规划调用大模型失败，已回退到规则模板: {exc}"],
                )

        return InitialPlanBuildResult(
            draft=self._fallback_initial_plan(request),
            used_llm=False,
            fallback_used=True,
            warnings=["未配置大模型，初步规划使用规则模板生成。"],
        )

    async def compose_plan(
        self,
        request: TripPlanningRequest,
        initial_plan: InitialPlanDraft,
        context: PlanningContext,
        tool_trace: list[ToolCallRecord],
    ) -> FinalPlanBuildResult:
        if self.client is not None:
            try:
                return FinalPlanBuildResult(
                    plan=await self._compose_with_openai(request, initial_plan, context, tool_trace),
                    used_llm=True,
                    fallback_used=False,
                    warnings=[],
                )
            except Exception as exc:
                return FinalPlanBuildResult(
                    plan=self._fallback_plan(request, initial_plan, context),
                    used_llm=False,
                    fallback_used=True,
                    warnings=[f"最终行程汇总调用大模型失败，已回退到规则模板: {exc}"],
                )

        return FinalPlanBuildResult(
            plan=self._fallback_plan(request, initial_plan, context),
            used_llm=False,
            fallback_used=True,
            warnings=["未配置大模型，最终行程使用规则模板生成。"],
        )

    async def _generate_initial_plan_with_openai(self, request: TripPlanningRequest) -> InitialPlanDraft:
        assert self.client is not None
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
        completion = await self.client.chat.completions.create(
            model=self.settings.openai_model,
            response_format={"type": "json_object"},
            temperature=0.4,
            messages=[
                {
                    "role": "system",
                    "content": "你是旅行规划的总控 Agent。请根据用户需求输出初步行程草案 JSON，只返回 JSON。",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "request": request.model_dump(mode="json"),
                            "response_schema_hint": schema_hint,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        )
        content = completion.choices[0].message.content or "{}"
        payload = extract_json_payload(content)
        if not isinstance(payload, dict):
            raise ValueError("Initial plan JSON invalid")
        return InitialPlanDraft.model_validate(payload)

    async def _compose_with_openai(
        self,
        request: TripPlanningRequest,
        initial_plan: InitialPlanDraft,
        context: PlanningContext,
        tool_trace: list[ToolCallRecord],
    ) -> TravelPlan:
        assert self.client is not None
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
                    "route_summary": {
                        "day_number": 1,
                        "title": "string",
                        "from_name": "string",
                        "to_name": "string",
                        "waypoints": ["string"],
                        "distance_text": "string",
                        "duration_text": "string",
                        "mode": "string",
                        "steps": [{"instruction": "string", "distance_text": "string", "duration_text": "string"}],
                        "polyline": [{"longitude": 0, "latitude": 0}],
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
        completion = await self.client.chat.completions.create(
            model=self.settings.openai_model,
            response_format={"type": "json_object"},
            temperature=0.7,
            messages=[
                {
                    "role": "system",
                    "content": "你是资深旅游规划师。请严格基于初步计划、地图信息、天气和路线信息输出最终 JSON，只返回 JSON。",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "request": request.model_dump(mode="json"),
                            "initial_plan": initial_plan.model_dump(mode="json"),
                            "planning_context": context.model_dump(mode="json"),
                            "tool_trace": [item.model_dump(mode="json") for item in tool_trace],
                            "response_schema_hint": schema_hint,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        )
        content = completion.choices[0].message.content or "{}"
        payload = extract_json_payload(content)
        if not isinstance(payload, dict):
            raise ValueError("Final plan JSON invalid")
        return TravelPlan.model_validate(payload)

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
                        expected_cost="门票和体验消费以现场或官方平台为准",
                        booking_tip="热门景点建议提前预约并错峰到达",
                    )
                )

            meals = self._build_meals(day_restaurants, food_cost)
            transport_tips = [
                f"天气：{day_weather.day_weather or context.weather.overview}，建议按当天实际温度调整出发时间。",
                day_route.duration_text and f"参考路线总时长约 {day_route.duration_text}。" or "优先选择地铁与网约车组合，兼顾效率与舒适度。",
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
