from __future__ import annotations

from typing import Awaitable, Callable

from app.schemas.planning import POIRecommendation, TripPlanningRequest

DeduplicateQueries = Callable[[list[str]], list[str]]
SearchPoiCandidates = Callable[[str, list[str], list, str, int], Awaitable[list[POIRecommendation]]]
FilterPoisByGeoScope = Callable[[str, list[POIRecommendation], float, list[POIRecommendation] | None], list[POIRecommendation]]
LocationNameMatchScore = Callable[[str, POIRecommendation], tuple[int, int, float]]
PoiDetailComplete = Callable[[POIRecommendation], bool]
EnrichPoisWithDetails = Callable[[list[POIRecommendation], list, str | None], Awaitable[list[POIRecommendation]]]
MergeUniquePois = Callable[[list[POIRecommendation]], list[POIRecommendation]]
CacheLocationCandidate = Callable[[str, POIRecommendation | None], None]
CacheLocationCandidateSimple = Callable[[str, POIRecommendation | None], None]
SimpleCachedCandidateUsable = Callable[[str, POIRecommendation, list[POIRecommendation]], bool]
CityCenterResolver = Callable[[str], object]

from app.services.amap_mcp_selection_geo import (
    anchor_center,
    location_hint_tokens,
    poi_matches_location_tokens,
    poi_within_scope,
)


def build_hotel_queries(
    request: TripPlanningRequest,
    anchor_pois: list[POIRecommendation],
    *,
    dedupe_queries: DeduplicateQueries,
) -> list[str]:
    queries: list[str] = []
    for poi in anchor_pois[:4]:
        if poi.name:
            queries.append(f"{poi.name} 附近 {request.hotel_style}")
            queries.append(f"{poi.name} 附近 酒店")
        if poi.district:
            queries.append(f"{poi.district} {request.hotel_style}")
    queries.extend([request.hotel_style, f"{request.destination} {request.hotel_style}", "酒店", "舒适型酒店"])
    return dedupe_queries(queries)


def is_simple_cached_candidate_usable(
    *,
    city: str,
    candidate: POIRecommendation,
    anchors: list[POIRecommendation],
    city_center: CityCenterResolver,
) -> bool:
    if not anchors:
        return True
    if candidate.longitude is not None and candidate.latitude is not None:
        center = anchor_center(anchors, city_center=city_center)
        return poi_within_scope(candidate, center, 35)
    tokens = location_hint_tokens(city, anchors)
    return poi_matches_location_tokens(candidate, tokens)


async def resolve_location_candidate(
    *,
    city: str,
    location_name: str,
    trace: list,
    anchor_pois: list[POIRecommendation] | None,
    location_candidate_cache: dict[str, POIRecommendation | None],
    location_candidate_simple_cache: dict[str, POIRecommendation | None],
    location_candidate_cache_key_fn: Callable[[str, str, list[POIRecommendation]], str],
    location_candidate_simple_cache_key_fn: Callable[[str, str], str],
    cache_location_candidate: CacheLocationCandidate,
    cache_location_candidate_simple: CacheLocationCandidateSimple,
    is_simple_cached_candidate_usable_fn: SimpleCachedCandidateUsable,
    search_poi_candidates: SearchPoiCandidates,
    filter_pois_by_geo_scope: FilterPoisByGeoScope,
    location_name_match_score_fn: LocationNameMatchScore,
    poi_detail_is_complete: PoiDetailComplete,
    enrich_pois_with_details: EnrichPoisWithDetails,
    merge_unique_pois: MergeUniquePois,
) -> POIRecommendation | None:
    query = location_name.strip()
    if not query:
        return None
    anchors = anchor_pois or []
    cache_key = location_candidate_cache_key_fn(city, query, anchors)
    if cache_key in location_candidate_cache:
        return location_candidate_cache[cache_key]

    simple_cache_key = location_candidate_simple_cache_key_fn(city, query)
    if simple_cache_key in location_candidate_simple_cache:
        cached_simple = location_candidate_simple_cache[simple_cache_key]
        if cached_simple is None:
            cache_location_candidate(cache_key, None)
            return None
        if is_simple_cached_candidate_usable_fn(city, cached_simple, anchors):
            cache_location_candidate(cache_key, cached_simple)
            return cached_simple

    merged = await search_poi_candidates(city, [query], trace, "地点", 5)
    filtered = filter_pois_by_geo_scope(city, merged, 35, anchors)
    if not filtered:
        cache_location_candidate(cache_key, None)
        cache_location_candidate_simple(simple_cache_key, None)
        return None

    ranked_base = sorted(
        filtered,
        key=lambda poi: location_name_match_score_fn(query, poi),
    )
    top_candidates = ranked_base[:2]
    should_enrich = any(not poi_detail_is_complete(item) for item in top_candidates)
    ranked = ranked_base
    if should_enrich:
        enriched_top = await enrich_pois_with_details(top_candidates, trace, "location")
        if enriched_top:
            merged_candidates = merge_unique_pois([*enriched_top, *ranked_base])
            ranked = sorted(
                merged_candidates,
                key=lambda poi: location_name_match_score_fn(query, poi),
            )
    selected = ranked[0] if ranked else None
    cache_location_candidate(cache_key, selected)
    cache_location_candidate_simple(simple_cache_key, selected)
    return selected
