from __future__ import annotations

import math
from typing import Any, Callable

from app.schemas.planning import (
    Activity,
    DayCostBreakdown,
    MealRecommendation,
    POIRecommendation,
    PlanningContext,
    RouteSummary,
    TravelPlan,
    TripPlanningRequest,
)
from app.services.ai_client_truth import ensure_display_ready_poi, match_named_poi
from app.services.ai_client_stays import normalize_location_text


def resolve_known_poi(
    lookup_name: str,
    candidates: list[POIRecommendation],
    destination: str,
) -> POIRecommendation | None:
    normalized_lookup = normalize_location_text(lookup_name)
    if not normalized_lookup:
        return None
    matched = match_named_poi(normalized_lookup, candidates)
    if matched is None:
        return None
    return ensure_display_ready_poi(matched, destination)


def route_to_transport_tip(route: RouteSummary) -> str:
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


def sync_activity_transport_from_routes(
    activities: list[Activity],
    routes: list[RouteSummary],
) -> list[Activity]:
    if not activities:
        return activities

    normalized: list[Activity] = []
    for index, activity in enumerate(activities):
        transport_tip = activity.transport_from_previous
        if index < len(routes):
            transport_tip = route_to_transport_tip(routes[index])
        normalized.append(
            activity.model_copy(
                update={
                    "transport_from_previous": transport_tip,
                }
            )
        )
    return normalized


def merge_transport_tips(
    existing_tips: list[str],
    routes: list[RouteSummary],
) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    route_tips = [route_to_transport_tip(route) for route in routes]
    for tip in [*existing_tips, *route_tips]:
        normalized_tip = tip.strip()
        if not normalized_tip or normalized_tip in seen:
            continue
        seen.add(normalized_tip)
        merged.append(normalized_tip)
    return merged


def normalize_plan_days(
    request: TripPlanningRequest,
    plan: TravelPlan,
    context: PlanningContext,
    *,
    extract_cny_amount: Callable[[str | None], int],
    reconcile_day_stay: Callable[[Any, Any, list[Any]], tuple[Any, str]],
    estimate_room_nightly_cost: Callable[[str, POIRecommendation | None], int],
    harmonize_cost_estimate: Callable[[int, int, float, float], int],
    estimate_meal_cost: Callable[[str, str, POIRecommendation | None, str], int],
    ensure_daily_core_meals: Callable[[list[MealRecommendation], list[Any], Any, str, str, int, str], list[MealRecommendation]],
    normalize_stay_recommendations: Callable[[list[Any], list[Any], list[Any]], list[Any]],
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

    normalized_days = []
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
            ticket_cost_cny = activity.ticket_cost_cny or extract_cny_amount(activity.expected_cost)
            expected_cost = activity.expected_cost or (f"¥{ticket_cost_cny}/人" if ticket_cost_cny else None)
            normalized_activities.append(
                activity.model_copy(
                    update={
                        "ticket_cost_cny": max(0, ticket_cost_cny),
                        "expected_cost": expected_cost,
                    }
                )
            )

        stay, resolved_hotel_area = reconcile_day_stay(
            day=day.model_copy(update={"activities": normalized_activities}),
            stay=stay,
            hotels=context.hotels,
        )
        matched_hotel_poi = resolve_known_poi(
            lookup_name=stay.hotel_name or resolved_hotel_area,
            candidates=context.hotels,
            destination=context.destination,
        )
        room_cost_heuristic = estimate_room_nightly_cost(
            budget_level=request.budget_level,
            hotel=matched_hotel_poi,
        )
        room_nightly_cost_cny = stay.room_nightly_cost_cny
        if room_nightly_cost_cny <= 0 and stays:
            room_nightly_cost_cny = extract_cny_amount(stays[day_index % len(stays)].nightly_budget)
        room_nightly_cost_cny = harmonize_cost_estimate(
            observed_cost=room_nightly_cost_cny,
            heuristic_cost=room_cost_heuristic,
            floor_ratio=0.45,
            ceiling_ratio=2.4,
        )
        stay = stay.model_copy(
            update={
                "area": stay.area or resolved_hotel_area,
                "room_nightly_cost_cny": max(0, room_nightly_cost_cny),
            }
        )

        normalized_meals: list[MealRecommendation] = []
        for meal in day.meals:
            meal_poi = resolve_known_poi(
                lookup_name=meal.venue_name,
                candidates=context.restaurants,
                destination=context.destination,
            )
            if meal_poi is None and meal.meal_type == "breakfast":
                meal_poi = matched_hotel_poi
            estimated_cost_cny = meal.estimated_cost_cny or extract_cny_amount(meal.estimated_cost)
            meal_cost_heuristic = estimate_meal_cost(
                meal_type=meal.meal_type,
                budget_level=request.budget_level,
                restaurant=meal_poi,
                destination=request.destination,
            )
            estimated_cost_cny = harmonize_cost_estimate(
                observed_cost=estimated_cost_cny,
                heuristic_cost=meal_cost_heuristic,
                floor_ratio=0.5,
                ceiling_ratio=2.2,
            )
            estimated_cost = f"¥{estimated_cost_cny}/人" if estimated_cost_cny else ""
            normalized_meals.append(
                meal.model_copy(
                    update={
                        "estimated_cost_cny": max(0, estimated_cost_cny),
                        "estimated_cost": estimated_cost,
                    }
                )
            )
        normalized_meals = ensure_daily_core_meals(
            meals=normalized_meals,
            restaurants=context.restaurants,
            stay=stay,
            hotel_area=day.hotel_area,
            day_theme=day.theme,
            day_index=day_index,
            budget_level=request.budget_level,
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
        normalized_activities = sync_activity_transport_from_routes(
            normalized_activities,
            normalized_routes,
        )
        transport_tips = merge_transport_tips(day.transport_tips, normalized_routes)

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
                    "route_segments": normalized_routes,
                    "cost_breakdown": cost_breakdown,
                }
            )
        )

    normalized_stays = normalize_stay_recommendations(
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
