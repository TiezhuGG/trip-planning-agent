from __future__ import annotations

import math
import re
from typing import Callable

from app.schemas.planning import GeoPoint, POIRecommendation

CityCenterResolver = Callable[[str], GeoPoint]
NormalizeCityName = Callable[[str | None], str]


def distance_score(poi: POIRecommendation, center: GeoPoint) -> float:
    if poi.longitude is None or poi.latitude is None:
        return float("inf")
    return (poi.longitude - center.longitude) ** 2 + (poi.latitude - center.latitude) ** 2


def geo_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat_scale = 111.0
    lon_scale = 111.0 * max(0.1, math.cos(math.radians((lat1 + lat2) / 2)))
    lat_distance = (lat1 - lat2) * lat_scale
    lon_distance = (lon1 - lon2) * lon_scale
    return math.sqrt(lat_distance * lat_distance + lon_distance * lon_distance)


def poi_within_scope(
    poi: POIRecommendation,
    center: GeoPoint,
    radius_km: float,
) -> bool:
    if poi.longitude is None or poi.latitude is None:
        return False
    return geo_distance_km(
        poi.latitude,
        poi.longitude,
        center.latitude,
        center.longitude,
    ) <= radius_km


def normalize_location_token(value: str) -> str:
    normalized = re.sub(r"\s+", "", value.strip())
    for suffix in ("风景名胜区", "旅游度假区", "景区", "街道", "镇", "乡", "村", "市", "区", "县"):
        if normalized.endswith(suffix) and len(normalized) > len(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized


def location_hint_tokens(
    city: str,
    anchor_pois: list[POIRecommendation],
) -> set[str]:
    tokens = {normalize_location_token(city)}
    for poi in anchor_pois:
        for candidate in (poi.district or "", poi.address or "", poi.name):
            token = normalize_location_token(candidate)
            if token:
                tokens.add(token)
    return {token for token in tokens if token}


def poi_matches_location_tokens(
    poi: POIRecommendation,
    tokens: set[str],
) -> bool:
    haystacks = [
        normalize_location_token(poi.district or ""),
        normalize_location_token(poi.address or ""),
        normalize_location_token(poi.name),
    ]
    for haystack in haystacks:
        if not haystack:
            continue
        if any(token and token in haystack for token in tokens):
            return True
    return False


def anchor_center(
    pois: list[POIRecommendation],
    *,
    city_center: CityCenterResolver,
) -> GeoPoint:
    coordinates = [
        (poi.longitude, poi.latitude)
        for poi in pois
        if poi.longitude is not None and poi.latitude is not None
    ]
    if not coordinates:
        return city_center("")
    longitude = sum(item[0] for item in coordinates) / len(coordinates)
    latitude = sum(item[1] for item in coordinates) / len(coordinates)
    return GeoPoint(longitude=longitude, latitude=latitude)


def filter_pois_by_geo_scope(
    *,
    city: str,
    pois: list[POIRecommendation],
    radius_km: float,
    anchor_pois: list[POIRecommendation] | None,
    merge_unique_pois: Callable[[list[POIRecommendation]], list[POIRecommendation]],
    sort_pois_by_city_center: Callable[[str, list[POIRecommendation]], list[POIRecommendation]],
    city_center: CityCenterResolver,
) -> list[POIRecommendation]:
    if not pois:
        return []

    center = anchor_center(anchor_pois or [], city_center=city_center) if anchor_pois else city_center(city)
    tokens = location_hint_tokens(city, anchor_pois or [])

    filtered: list[POIRecommendation] = []
    for poi in pois:
        if poi_within_scope(poi, center, radius_km):
            filtered.append(poi)
            continue
        if (poi.longitude is None or poi.latitude is None) and poi_matches_location_tokens(poi, tokens):
            filtered.append(poi)

    if filtered:
        return merge_unique_pois(filtered)

    return merge_unique_pois(sort_pois_by_city_center(city, pois))


def sort_pois_by_city_center(
    city: str,
    pois: list[POIRecommendation],
    *,
    city_center: CityCenterResolver,
) -> list[POIRecommendation]:
    center = city_center(city)
    return sorted(
        pois,
        key=lambda poi: distance_score(poi, center),
    )


def location_name_match_score(
    query: str,
    poi: POIRecommendation,
    *,
    normalize_city_name: NormalizeCityName,
    city_center: CityCenterResolver,
) -> tuple[int, int, float]:
    normalized_query = normalize_location_token(query)
    normalized_name = normalize_location_token(poi.name)
    exact_penalty = 0 if normalized_query == normalized_name else 1
    contains_penalty = 0 if normalized_query in normalized_name or normalized_name in normalized_query else 1
    return (
        exact_penalty,
        contains_penalty,
        distance_score(poi, city_center(normalize_city_name(poi.district) or "")),
    )
