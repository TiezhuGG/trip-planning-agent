from __future__ import annotations

from typing import Callable, TypeVar

from app.schemas.planning import POIRecommendation
from app.services.amap_mcp_selection_geo import normalize_location_token

NormalizeCityName = Callable[[str | None], str]
T = TypeVar("T")


def route_location_cache_key(poi: POIRecommendation) -> str:
    if poi.poi_id:
        return f"poi:{poi.poi_id}"
    district = (poi.district or "").strip()
    address = (poi.address or "").strip()
    name = poi.name.strip()
    return f"addr:{district}|{address}|{name}"


def location_candidate_cache_key(
    city: str,
    query: str,
    anchor_pois: list[POIRecommendation],
    *,
    normalize_city_name: NormalizeCityName,
) -> str:
    normalized_city = normalize_city_name(city)
    normalized_query = normalize_location_token(query)
    anchor_tokens: list[str] = []
    for poi in anchor_pois[:3]:
        token = normalize_location_token(poi.name or poi.address or "")
        if token:
            anchor_tokens.append(token)
    anchor_part = "|".join(anchor_tokens)
    return f"{normalized_city}:{normalized_query}:{anchor_part}"


def location_candidate_simple_cache_key(
    city: str,
    query: str,
    *,
    normalize_city_name: NormalizeCityName,
) -> str:
    normalized_city = normalize_city_name(city)
    normalized_query = normalize_location_token(query)
    return f"{normalized_city}:{normalized_query}"


def cache_limited_mapping(
    cache: dict[str, T],
    *,
    key: str,
    value: T,
    limit: int,
) -> None:
    if key in cache:
        cache[key] = value
        return
    if len(cache) >= limit:
        oldest_key = next(iter(cache))
        cache.pop(oldest_key, None)
    cache[key] = value
