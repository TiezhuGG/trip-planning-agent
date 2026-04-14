from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.schemas.planning import (
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
    StayRecommendation,
    TravelPlan,
    TripPlanningRequest,
)
from app.services.ai_client_budget import (
    apply_deterministic_budget,
    extract_cny_amount,
    format_per_person_amount,
)
from app.services.ai_client_costs import (
    ensure_daily_core_meals,
    estimate_meal_cost,
    estimate_room_nightly_cost,
    harmonize_cost_estimate,
)
from app.services.ai_client_fallback import (
    build_meals,
    default_daily_forecast,
    fallback_plan,
    fallback_route_summary,
    pace_label,
    select_day_attractions,
    select_day_restaurants,
    theme_for_day,
)
from app.services.ai_client_normalization import normalize_plan_days
from app.services.ai_client_stays import (
    area_matches_day,
    hotel_reason_for_day,
    location_fragments,
    match_hotel_candidate,
    normalize_location_text,
    normalize_stay_recommendations,
    preferred_area_for_day,
    reconcile_day_stay,
    score_hotel_for_day,
    stay_stub_poi,
    text_overlap_score,
)
from app.services.ai_client_truth import (
    dedupe_day_pois,
    ensure_display_ready_poi,
    legacy_attach_plan_truth,
    match_named_poi,
    resolve_final_poi,
)


class TravelAIClientDomainMixin:
    def _normalize_plan_days(
        self,
        request: TripPlanningRequest,
        plan: TravelPlan,
        context: PlanningContext,
    ) -> TravelPlan:
        return normalize_plan_days(
            request=request,
            plan=plan,
            context=context,
            extract_cny_amount=extract_cny_amount,
            reconcile_day_stay=reconcile_day_stay,
            estimate_room_nightly_cost=estimate_room_nightly_cost,
            harmonize_cost_estimate=harmonize_cost_estimate,
            estimate_meal_cost=estimate_meal_cost,
            ensure_daily_core_meals=ensure_daily_core_meals,
            normalize_stay_recommendations=normalize_stay_recommendations,
        )

    def _reconcile_day_stay(
        self,
        day: DayPlan,
        stay: DayStayInfo,
        hotels: list[Any],
    ) -> tuple[DayStayInfo, str]:
        return reconcile_day_stay(day, stay, hotels)

    def _preferred_area_for_day(
        self,
        day: DayPlan,
        stay: DayStayInfo,
        fallback_area: str,
    ) -> str:
        return preferred_area_for_day(day, stay, fallback_area)

    def _area_matches_day(
        self,
        area: str,
        day: DayPlan,
    ) -> bool:
        return area_matches_day(area, day)

    def _match_hotel_candidate(
        self,
        hotel_name: str,
        hotels: list[Any],
    ) -> Any | None:
        return match_hotel_candidate(hotel_name, hotels)

    def _score_hotel_for_day(
        self,
        hotel: Any,
        day: DayPlan,
        stay: DayStayInfo,
    ) -> int:
        return score_hotel_for_day(hotel, day, stay)

    def _text_overlap_score(
        self,
        hotel_text: str,
        phrase: str,
        hit_score: int,
        partial_score: int,
    ) -> int:
        return text_overlap_score(hotel_text, phrase, hit_score, partial_score)

    def _location_fragments(self, value: str) -> list[str]:
        return location_fragments(value)

    def _normalize_location_text(self, value: str | None) -> str:
        return normalize_location_text(value)

    def _stay_stub_poi(
        self,
        stay: DayStayInfo,
        hotel_area: str,
    ) -> Any:
        return stay_stub_poi(stay, hotel_area)

    def _hotel_reason_for_day(
        self,
        hotel: Any,
        day: DayPlan,
    ) -> str:
        return hotel_reason_for_day(hotel, day)

    def _normalize_stay_recommendations(
        self,
        existing_recommendations: list[StayRecommendation],
        normalized_days: list[DayPlan],
        hotels: list[Any],
    ) -> list[StayRecommendation]:
        return normalize_stay_recommendations(existing_recommendations, normalized_days, hotels)

    def _legacy_attach_plan_truth(
        self,
        plan: TravelPlan,
        context: PlanningContext,
        destination: str,
    ) -> TravelPlan:
        return legacy_attach_plan_truth(plan, context, destination)

    def _resolve_final_poi(
        self,
        lookup_name: str,
        candidates: list[POIRecommendation],
        destination: str,
        fallback_name: str = "",
    ) -> POIRecommendation | None:
        return resolve_final_poi(lookup_name, candidates, destination, fallback_name)

    def _match_named_poi(
        self,
        normalized_lookup: str,
        candidates: list[POIRecommendation],
    ) -> POIRecommendation | None:
        return match_named_poi(normalized_lookup, candidates)

    def _ensure_display_ready_poi(
        self,
        poi: POIRecommendation,
        destination: str,
    ) -> POIRecommendation:
        return ensure_display_ready_poi(poi, destination)

    def _dedupe_day_pois(
        self,
        items: list[DayPOI],
    ) -> list[DayPOI]:
        return dedupe_day_pois(items)

    def _apply_deterministic_budget(
        self,
        request: TripPlanningRequest,
        plan: TravelPlan,
    ) -> TravelPlan:
        _ = request
        return apply_deterministic_budget(plan)

    def _extract_cny_amount(self, value: str | None) -> int:
        return extract_cny_amount(value)

    def _format_per_person_amount(self, value: int) -> str:
        return format_per_person_amount(value)

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
        return fallback_plan(
            request=request,
            initial_plan=initial_plan,
            context=context,
            extract_cny_amount=self._extract_cny_amount,
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
        return fallback_route_summary(day_number, request, hotel, seed_day, destination_name)

    def _default_daily_forecast(self, date: str) -> DailyForecast:
        return default_daily_forecast(date)

    def _select_day_attractions(
        self,
        attractions: list,
        seed_day: InitialPlanDay | None,
        day_index: int,
    ) -> list:
        return select_day_attractions(attractions, seed_day, day_index)

    def _select_day_restaurants(self, restaurants: list, day_index: int) -> list:
        return select_day_restaurants(restaurants, day_index)

    def _build_meals(self, restaurants: list, food_cost: str) -> list[MealRecommendation]:
        return build_meals(restaurants, food_cost, self._extract_cny_amount)

    def _theme_for_day(self, day_index: int, request: TripPlanningRequest) -> str:
        return theme_for_day(day_index, request)

    def _pace_label(self, pace: str) -> str:
        return pace_label(pace)
