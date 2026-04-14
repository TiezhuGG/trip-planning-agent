from __future__ import annotations

import re
from typing import Any

from app.schemas.planning import DayPlan, DayStayInfo, StayRecommendation


def reconcile_day_stay(
    day: DayPlan,
    stay: DayStayInfo,
    hotels: list[Any],
) -> tuple[DayStayInfo, str]:
    resolved_hotel_area = day.hotel_area or stay.area
    if not hotels:
        return stay, resolved_hotel_area

    best_hotel = max(
        hotels,
        key=lambda hotel: score_hotel_for_day(hotel, day, stay),
    )
    best_score = score_hotel_for_day(best_hotel, day, stay)

    current_hotel = match_hotel_candidate(stay.hotel_name, hotels)
    current_score = score_hotel_for_day(
        current_hotel or stay_stub_poi(stay, day.hotel_area),
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
        resolved_hotel_area = preferred_area_for_day(
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
                    "reason": hotel_reason_for_day(best_hotel, day),
                }
            ),
            resolved_hotel_area,
        )

    if current_hotel is not None:
        resolved_hotel_area = preferred_area_for_day(
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


def preferred_area_for_day(
    day: DayPlan,
    stay: DayStayInfo,
    fallback_area: str,
) -> str:
    for candidate in [day.hotel_area, stay.area]:
        if area_matches_day(candidate, day):
            return candidate
    return fallback_area or day.hotel_area or stay.area


def area_matches_day(
    area: str,
    day: DayPlan,
) -> bool:
    normalized_area = normalize_location_text(area)
    if not normalized_area:
        return False
    for activity in day.activities:
        normalized_location = normalize_location_text(activity.location_name)
        if not normalized_location:
            continue
        if normalized_area in normalized_location or normalized_location in normalized_area:
            return True
        if any(fragment in normalized_location for fragment in location_fragments(normalized_area)):
            return True
    return False


def match_hotel_candidate(
    hotel_name: str,
    hotels: list[Any],
) -> Any | None:
    normalized_target = normalize_location_text(hotel_name)
    if not normalized_target:
        return None

    scored: list[tuple[int, int, Any]] = []
    for hotel in hotels:
        candidate_name = normalize_location_text(getattr(hotel, "name", ""))
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


def score_hotel_for_day(
    hotel: Any,
    day: DayPlan,
    stay: DayStayInfo,
) -> int:
    hotel_text = normalize_location_text(
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
        score += text_overlap_score(hotel_text, phrase, hit_score=8, partial_score=3)

    for activity in day.activities:
        score += text_overlap_score(hotel_text, activity.location_name, hit_score=6, partial_score=2)

    return score


def text_overlap_score(
    hotel_text: str,
    phrase: str,
    hit_score: int,
    partial_score: int,
) -> int:
    normalized_phrase = normalize_location_text(phrase)
    if not normalized_phrase:
        return 0
    if normalized_phrase in hotel_text:
        return hit_score

    partial_hits = 0
    for fragment in location_fragments(normalized_phrase):
        if fragment and fragment in hotel_text:
            partial_hits += 1
    if partial_hits:
        return partial_score * partial_hits
    return 0


def location_fragments(value: str) -> list[str]:
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


def normalize_location_text(value: str | None) -> str:
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


def stay_stub_poi(
    stay: DayStayInfo,
    hotel_area: str,
) -> Any:
    class _StayStub:
        def __init__(self, name: str, address: str) -> None:
            self.name = name
            self.address = address
            self.district = ""

    return _StayStub(stay.hotel_name, stay.area or hotel_area)


def hotel_reason_for_day(
    hotel: Any,
    day: DayPlan,
) -> str:
    _ = hotel
    focus = day.activities[0].location_name if day.activities else day.theme
    return f"更贴近{focus}等当日活动区域，往返更省时。"


def format_nightly_budget(room_nightly_cost_cny: int) -> str:
    if room_nightly_cost_cny <= 0:
        return ""
    return f"¥{room_nightly_cost_cny:,}/晚"


def normalize_stay_recommendations(
    existing_recommendations: list[StayRecommendation],
    normalized_days: list[DayPlan],
    hotels: list[Any],
) -> list[StayRecommendation]:
    existing_by_name: dict[str, StayRecommendation] = {}
    for recommendation in existing_recommendations:
        key = normalize_location_text(recommendation.hotel_name)
        if key and key not in existing_by_name:
            existing_by_name[key] = recommendation

    recommendations: list[StayRecommendation] = []
    seen: set[str] = set()
    for day in normalized_days:
        hotel_name = day.stay.hotel_name.strip()
        area = (day.stay.area or day.hotel_area).strip()
        if not hotel_name and not area:
            continue

        key = normalize_location_text(hotel_name or area)
        if key in seen:
            continue
        seen.add(key)

        existing = existing_by_name.get(normalize_location_text(hotel_name))
        candidate_hotel = match_hotel_candidate(hotel_name, hotels)
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
        nightly_budget = format_nightly_budget(day.stay.room_nightly_cost_cny)
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
