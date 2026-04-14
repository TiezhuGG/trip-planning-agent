from __future__ import annotations

import re

from app.schemas.planning import BudgetBreakdown, TravelPlan


def extract_cny_amount(value: str | None) -> int:
    if not value:
        return 0
    numbers = [float(item.replace(",", "")) for item in re.findall(r"\d+(?:\.\d+)?", value)]
    if not numbers:
        return 0
    if len(numbers) == 1:
        return max(0, int(round(numbers[0])))
    return max(0, int(round(sum(numbers[:2]) / 2)))


def format_per_person_amount(value: int) -> str:
    return f"¥{max(0, value):,}/人"


def apply_deterministic_budget(plan: TravelPlan) -> TravelPlan:
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
                accommodation=format_per_person_amount(accommodation),
                transport=format_per_person_amount(transport),
                food=format_per_person_amount(food),
                tickets=format_per_person_amount(tickets),
                extras=format_per_person_amount(extras),
                total_estimate=format_per_person_amount(total),
            ),
            "days": sorted_days,
        }
    )
