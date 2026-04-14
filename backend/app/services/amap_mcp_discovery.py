from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.schemas.planning import POIRecommendation, ToolCallRecord, TripPlanningRequest
from app.utils.local_cuisine import get_city_signature_keywords

SearchPoiCandidates = Callable[
    [str, list[str], list[ToolCallRecord], str, int],
    Awaitable[list[POIRecommendation]],
]
EnrichPoisWithDetails = Callable[
    [list[POIRecommendation], list[ToolCallRecord], str],
    Awaitable[list[POIRecommendation]],
]
FilterPoisByGeoScope = Callable[
    [str, list[POIRecommendation], float, list[POIRecommendation] | None],
    list[POIRecommendation],
]
ResolveLocationCandidate = Callable[
    [str, str, list[ToolCallRecord], list[POIRecommendation] | None],
    Awaitable[POIRecommendation | None],
]
SortPoisByCityCenter = Callable[[str, list[POIRecommendation]], list[POIRecommendation]]
SortRestaurantsForRoute = Callable[
    [list[POIRecommendation], str, list[POIRecommendation]],
    list[POIRecommendation],
]
DedupeQueries = Callable[[list[str]], list[str]]
BuildHotelQueries = Callable[[TripPlanningRequest, list[POIRecommendation]], list[str]]
SortHotelsForStay = Callable[
    [list[POIRecommendation], list[POIRecommendation], str],
    list[POIRecommendation],
]


async def fetch_attractions(
    *,
    request: TripPlanningRequest,
    trace: list[ToolCallRecord],
    search_poi_candidates_fn: SearchPoiCandidates,
    enrich_pois_with_details_fn: EnrichPoisWithDetails,
    filter_pois_by_geo_scope_fn: FilterPoisByGeoScope,
    sort_pois_by_city_center_fn: SortPoisByCityCenter,
) -> list[POIRecommendation]:
    queries: list[str] = []
    for keyword in request.must_visit[:4]:
        queries.extend([keyword, f"{keyword} 景点"])
    for interest in request.interests[:3]:
        queries.append(f"{interest} 景点")
    queries.extend(["旅游景点", "热门景点", "景区"])
    merged = await search_poi_candidates_fn(
        request.destination,
        queries,
        trace,
        "景点",
        10,
    )
    enriched = await enrich_pois_with_details_fn(merged, trace, "attraction")
    filtered = filter_pois_by_geo_scope_fn(
        request.destination,
        enriched,
        35,
        None,
    )
    return sort_pois_by_city_center_fn(request.destination, filtered)


async def fetch_restaurants(
    *,
    request: TripPlanningRequest,
    trace: list[ToolCallRecord],
    anchor_pois: list[POIRecommendation],
    search_poi_candidates_fn: SearchPoiCandidates,
    enrich_pois_with_details_fn: EnrichPoisWithDetails,
    filter_pois_by_geo_scope_fn: FilterPoisByGeoScope,
    sort_restaurants_for_route_fn: SortRestaurantsForRoute,
) -> list[POIRecommendation]:
    queries: list[str] = []
    for poi in anchor_pois[:4]:
        if poi.name:
            queries.append(f"{poi.name} 附近 餐厅")
        if poi.district:
            queries.append(f"{poi.district} 美食")
    for preference in request.dining_preferences[:3]:
        queries.extend([preference, f"{preference} 餐厅"])
    for keyword in get_city_signature_keywords(request.destination)[:3]:
        queries.extend([keyword, f"{request.destination} {keyword}", f"{keyword} 餐厅"])
    queries.extend(["本地美食", "特色餐厅", "热门餐厅"])
    merged = await search_poi_candidates_fn(
        request.destination,
        queries,
        trace,
        "餐厅",
        8,
    )
    enriched = await enrich_pois_with_details_fn(merged, trace, "")
    filtered = filter_pois_by_geo_scope_fn(
        request.destination,
        enriched,
        25,
        anchor_pois,
    )
    return sort_restaurants_for_route_fn(filtered, request.destination, anchor_pois)


async def fetch_restaurants_for_locations(
    *,
    request: TripPlanningRequest,
    trace: list[ToolCallRecord],
    location_names: list[str],
    area_hint: str,
    stay_hint: str,
    dedupe_queries_fn: DedupeQueries,
    resolve_location_candidate_fn: ResolveLocationCandidate,
    search_poi_candidates_fn: SearchPoiCandidates,
    enrich_pois_with_details_fn: EnrichPoisWithDetails,
    filter_pois_by_geo_scope_fn: FilterPoisByGeoScope,
    sort_restaurants_for_route_fn: SortRestaurantsForRoute,
) -> list[POIRecommendation]:
    anchor_pois: list[POIRecommendation] = []
    for location_name in dedupe_queries_fn([stay_hint, *location_names[:3], area_hint]):
        resolved = await resolve_location_candidate_fn(
            request.destination,
            location_name,
            trace,
            anchor_pois,
        )
        if resolved is not None:
            anchor_pois.append(resolved)

    queries: list[str] = []
    for location_name in dedupe_queries_fn(location_names[:3]):
        queries.extend(
            [
                f"{location_name} 附近 早餐",
                f"{location_name} 附近 餐厅",
                f"{location_name} 附近 晚餐",
            ]
        )
    if stay_hint:
        queries.extend([f"{stay_hint} 附近 早餐", f"{stay_hint} 附近 餐厅"])
    if area_hint:
        queries.extend([f"{area_hint} 美食", f"{area_hint} 餐厅"])
    for keyword in get_city_signature_keywords(request.destination)[:3]:
        queries.extend(
            [
                f"{request.destination} {keyword}",
                f"{area_hint or request.destination} {keyword}",
            ]
        )
    queries.extend(["本地美食", "特色餐厅", "热门餐厅"])

    merged = await search_poi_candidates_fn(
        request.destination,
        queries,
        trace,
        "餐厅",
        10,
    )
    enriched = await enrich_pois_with_details_fn(merged, trace, "")
    filtered = filter_pois_by_geo_scope_fn(
        request.destination,
        enriched,
        10 if anchor_pois else 20,
        anchor_pois,
    )
    return sort_restaurants_for_route_fn(filtered, request.destination, anchor_pois)


async def fetch_hotels(
    *,
    request: TripPlanningRequest,
    trace: list[ToolCallRecord],
    anchor_pois: list[POIRecommendation],
    build_hotel_queries_fn: BuildHotelQueries,
    search_poi_candidates_fn: SearchPoiCandidates,
    enrich_pois_with_details_fn: EnrichPoisWithDetails,
    filter_pois_by_geo_scope_fn: FilterPoisByGeoScope,
    sort_hotels_for_stay_fn: SortHotelsForStay,
) -> list[POIRecommendation]:
    queries = build_hotel_queries_fn(request, anchor_pois)
    merged = await search_poi_candidates_fn(
        request.destination,
        queries,
        trace,
        "酒店",
        10,
    )
    enriched = await enrich_pois_with_details_fn(merged, trace, "")
    filtered = filter_pois_by_geo_scope_fn(
        request.destination,
        enriched,
        25,
        anchor_pois,
    )
    return sort_hotels_for_stay_fn(filtered, anchor_pois, request.destination)


async def fetch_hotels_for_locations(
    *,
    request: TripPlanningRequest,
    trace: list[ToolCallRecord],
    location_names: list[str],
    area_hint: str,
    dedupe_queries_fn: DedupeQueries,
    resolve_location_candidate_fn: ResolveLocationCandidate,
    search_poi_candidates_fn: SearchPoiCandidates,
    enrich_pois_with_details_fn: EnrichPoisWithDetails,
    filter_pois_by_geo_scope_fn: FilterPoisByGeoScope,
    sort_hotels_for_stay_fn: SortHotelsForStay,
) -> list[POIRecommendation]:
    anchor_pois: list[POIRecommendation] = []
    for location_name in dedupe_queries_fn([*location_names[:3], area_hint]):
        resolved = await resolve_location_candidate_fn(
            request.destination,
            location_name,
            trace,
            anchor_pois,
        )
        if resolved is not None:
            anchor_pois.append(resolved)

    queries: list[str] = []
    for location_name in dedupe_queries_fn(location_names[:3]):
        queries.append(f"{location_name} 附近 {request.hotel_style}")
        queries.append(f"{location_name} 附近 酒店")
    if area_hint:
        queries.extend([f"{area_hint} {request.hotel_style}", f"{area_hint} 酒店"])
    queries.extend([request.hotel_style, f"{request.destination} {request.hotel_style}", "酒店"])

    merged = await search_poi_candidates_fn(
        request.destination,
        queries,
        trace,
        "酒店",
        8,
    )
    enriched = await enrich_pois_with_details_fn(merged, trace, "")
    filtered = filter_pois_by_geo_scope_fn(
        request.destination,
        enriched,
        12 if anchor_pois else 25,
        anchor_pois,
    )
    return sort_hotels_for_stay_fn(filtered, anchor_pois, request.destination)
