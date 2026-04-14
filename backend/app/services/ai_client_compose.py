from __future__ import annotations

from typing import Any

from app.schemas.planning import PlanningContext, TripPlanningRequest


def normalize_compose_payload(
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
