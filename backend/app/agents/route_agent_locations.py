from __future__ import annotations

from app.schemas.planning import POIRecommendation


def normalize_location_name(value: str) -> str:
    return "".join(
        ch for ch in value.strip().lower() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff"
    )


def named_location_cache_key(
    city: str,
    location_name: str,
    anchor_points: list[POIRecommendation],
) -> str:
    normalized_city = normalize_location_name(city)
    normalized_location = normalize_location_name(location_name)
    anchor_tokens = [
        normalize_location_name(poi.poi_id or poi.name or "")
        for poi in anchor_points[:3]
    ]
    anchor_key = "|".join(token for token in anchor_tokens if token)
    return f"{normalized_city}::{normalized_location}::{anchor_key}"


def match_known_point(
    location_name: str,
    candidates: list[POIRecommendation],
    allow_contains: bool = True,
) -> POIRecommendation | None:
    normalized_target = normalize_location_name(location_name)
    if not normalized_target:
        return None

    scored: list[tuple[int, int, int, POIRecommendation]] = []
    for poi in candidates:
        normalized_name = normalize_location_name(poi.name)
        if not normalized_name:
            continue
        exact_penalty = 0 if normalized_name == normalized_target else 1
        contains_penalty = (
            0
            if normalized_target in normalized_name or normalized_name in normalized_target
            else 1
        )
        coordinate_penalty = 0 if poi.longitude is not None and poi.latitude is not None else 1
        if exact_penalty and (contains_penalty or not allow_contains):
            continue
        scored.append((exact_penalty, contains_penalty, coordinate_penalty, poi))

    if not scored:
        return None
    scored.sort(key=lambda item: item[:3])
    return scored[0][3]


def should_rebind_poi(poi: POIRecommendation | None) -> bool:
    if poi is None:
        return True
    if poi.longitude is None or poi.latitude is None:
        return True
    return (poi.source or "").lower() in {
        "manual_placeholder",
        "activity_fallback",
        "stay_fallback",
    }


def trusted_candidates(
    candidates: list[POIRecommendation | None],
) -> list[POIRecommendation]:
    trusted: list[POIRecommendation] = []
    for item in candidates:
        if item is None or should_rebind_poi(item):
            continue
        trusted.append(item)
    return trusted


def poi_matches_expected_name(
    poi: POIRecommendation,
    references: list[str],
) -> bool:
    normalized_name = normalize_location_name(poi.name)
    normalized_address = normalize_location_name(poi.address or "")
    normalized_district = normalize_location_name(poi.district or "")
    if not any((normalized_name, normalized_address, normalized_district)):
        return False

    for reference in references:
        normalized_reference = normalize_location_name(reference)
        if not normalized_reference:
            continue
        if normalized_name:
            if normalized_reference == normalized_name:
                return True
            if len(normalized_reference) >= 2 and normalized_reference in normalized_name:
                return True
            if len(normalized_name) >= 4 and normalized_name in normalized_reference:
                return True
        if len(normalized_reference) >= 4:
            if normalized_address and normalized_reference in normalized_address:
                return True
            if normalized_district and normalized_reference == normalized_district:
                return True
    return False


def add_location_variant(
    variants: list[str],
    value: str,
) -> None:
    candidate = value.strip()
    if not candidate or candidate in variants:
        return
    variants.append(candidate)


def activity_alias_variants(value: str) -> list[str]:
    alias_map = {
        "奥森": "奥林匹克森林公园",
        "奥森公园": "奥林匹克森林公园",
        "鸟巢": "国家体育场",
        "水立方": "国家游泳中心",
        "圆明园遗址": "圆明园",
        "国家植物园温室": "国家植物园",
    }
    expanded: list[str] = []
    for alias, canonical in alias_map.items():
        if alias in value and canonical != value:
            expanded.append(canonical)
    return expanded


def expand_location_variants(value: str) -> list[str]:
    text = value.strip()
    if not text:
        return []

    variants: list[str] = []
    add_location_variant(variants, text)
    trimmed = text
    suffixes = (
        "景区",
        "景点",
        "旅游区",
        "旅游景区",
        "风景区",
        "公园",
        "乐园",
        "园区",
        "园",
        "古镇",
        "博物馆",
        "美术馆",
        "纪念馆",
        "遗址公园",
        "遗址",
    )
    for suffix in suffixes:
        if trimmed.endswith(suffix) and len(trimmed) > len(suffix):
            trimmed = trimmed[: -len(suffix)].strip()
            add_location_variant(variants, trimmed)
    if "步行街" in trimmed:
        simplified = trimmed.replace("步行街", "").strip()
        add_location_variant(variants, simplified)
    return variants


def append_activity_variants(
    variants: list[str],
    value: str,
) -> None:
    for item in expand_location_variants(value):
        if item and item not in variants:
            variants.append(item)
        for alias in activity_alias_variants(item):
            if alias and alias not in variants:
                variants.append(alias)


def build_activity_location_queries(
    location_name: str,
    activity_title: str,
) -> list[str]:
    variants: list[str] = []
    for candidate in (location_name, activity_title):
        append_activity_variants(variants, candidate)
    place_suffixes = (
        "南门",
        "北门",
        "东门",
        "西门",
        "正门",
        "南园",
        "北园",
        "东园",
        "西园",
        "外围",
        "外圈",
        "入口",
        "出口",
        "游客中心",
        "温室",
        "长廊",
        "遗址",
    )
    for base in list(variants):
        for suffix in place_suffixes:
            if base.endswith(suffix) and len(base) > len(suffix):
                add_location_variant(variants, base[: -len(suffix)].strip())
    return variants


def should_rebind_named_poi(
    expected_name: str,
    poi: POIRecommendation | None,
    activity_title: str = "",
) -> bool:
    if should_rebind_poi(poi):
        return True
    if poi is None:
        return True

    references = (
        build_activity_location_queries(expected_name, activity_title)
        if activity_title
        else [expected_name]
    )
    return not poi_matches_expected_name(poi, references)


def match_trusted_candidate(
    expected_name: str,
    candidates: list[POIRecommendation],
    activity_title: str = "",
) -> POIRecommendation | None:
    references = (
        build_activity_location_queries(expected_name, activity_title)
        if activity_title
        else [expected_name]
    )
    for candidate in candidates:
        if poi_matches_expected_name(candidate, references):
            return candidate
    return None
