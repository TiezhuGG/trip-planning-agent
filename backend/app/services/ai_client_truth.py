from __future__ import annotations

from app.schemas.planning import DayPOI, POIRecommendation, PlanningContext, TravelPlan
from app.services.ai_client_stays import location_fragments, normalize_location_text


def legacy_attach_plan_truth(
    plan: TravelPlan,
    context: PlanningContext,
    destination: str,
) -> TravelPlan:
    updated_days = []
    for day in sorted(plan.days, key=lambda item: item.day_number):
        day_fallbacks: list[str] = []
        map_pois: list[DayPOI] = []

        stay_lookup = day.stay.hotel_name or day.hotel_area
        stay_poi = resolve_final_poi(
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

        updated_activities = []
        for activity in day.activities:
            activity_poi = resolve_final_poi(
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

        updated_meals = []
        for meal in day.meals:
            meal_poi = None
            if meal.venue_name:
                meal_poi = resolve_final_poi(
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
                    "map_pois": dedupe_day_pois(map_pois),
                    "fallbacks": sorted(set(day.fallbacks + day_fallbacks)),
                }
            )
        )

    return plan.model_copy(update={"days": updated_days})


def resolve_final_poi(
    lookup_name: str,
    candidates: list[POIRecommendation],
    destination: str,
    fallback_name: str = "",
) -> POIRecommendation | None:
    normalized_lookup = normalize_location_text(lookup_name)
    if not normalized_lookup:
        return None

    matched = match_named_poi(normalized_lookup, candidates)
    if matched is not None:
        return ensure_display_ready_poi(matched, destination)

    display_name = fallback_name.strip() or lookup_name.strip()
    if not display_name:
        return None
    return POIRecommendation(
        name=display_name,
        address=f"{destination}{display_name}",
        district=destination,
        source="manual_placeholder",
    )


def match_named_poi(
    normalized_lookup: str,
    candidates: list[POIRecommendation],
) -> POIRecommendation | None:
    scored: list[tuple[int, int, int, int, POIRecommendation]] = []
    for candidate in candidates:
        normalized_name = normalize_location_text(candidate.name)
        if not normalized_name:
            continue
        exact_penalty = 0 if normalized_name == normalized_lookup else 1
        contains_penalty = 0 if normalized_lookup in normalized_name or normalized_name in normalized_lookup else 1
        coordinate_penalty = 0 if candidate.longitude is not None and candidate.latitude is not None else 1
        fragment_hits = sum(
            1
            for fragment in location_fragments(normalized_lookup)
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


def ensure_display_ready_poi(
    poi: POIRecommendation,
    destination: str,
) -> POIRecommendation:
    district = poi.district or destination
    address = poi.address or f"{district}{poi.name}"
    return poi.model_copy(update={"district": district, "address": address})


def dedupe_day_pois(items: list[DayPOI]) -> list[DayPOI]:
    deduped: list[DayPOI] = []
    seen: set[str] = set()
    for item in items:
        key = item.poi.poi_id or f"{item.kind}:{item.poi.name}:{item.poi.address}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped
