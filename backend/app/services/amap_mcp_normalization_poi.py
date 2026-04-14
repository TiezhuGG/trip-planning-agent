from __future__ import annotations

from typing import Any, Callable

from app.schemas.planning import POIRecommendation


FloatParser = Callable[[Any], float | None]
IntParser = Callable[[Any], int | None]


def normalize_tags(item: dict[str, Any]) -> list[str]:
    tags = item.get("tags", item.get("tag", item.get("type", item.get("typecode", []))))
    if isinstance(tags, str):
        return [segment.strip() for segment in tags.replace("|", ",").split(",") if segment.strip()]
    if isinstance(tags, list):
        return [str(tag) for tag in tags if str(tag).strip()]
    return []


def extract_coordinates(
    item: dict[str, Any],
    *,
    to_float: FloatParser,
) -> tuple[float | None, float | None]:
    if "longitude" in item or "latitude" in item:
        return to_float(item.get("longitude")), to_float(item.get("latitude"))

    location = item.get("location") or item.get("lnglat") or item.get("point")
    if isinstance(location, str) and "," in location:
        longitude_text, latitude_text = location.split(",", 1)
        return to_float(longitude_text), to_float(latitude_text)
    if isinstance(location, dict):
        return to_float(location.get("lng", location.get("longitude"))), to_float(
            location.get("lat", location.get("latitude"))
        )
    return None, None


def extract_poi_items(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]

    if not isinstance(raw, dict):
        return []

    for key in ("pois", "items", "results", "list"):
        value = raw.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    data = raw.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        nested_items = extract_poi_items(data)
        if nested_items:
            return nested_items

    if any(key in raw for key in ("name", "id", "address", "location")):
        return [raw]

    return []


def extract_poi_detail_record(raw: Any) -> dict[str, Any] | None:
    items = extract_poi_items(raw)
    if items:
        return items[0]
    return raw if isinstance(raw, dict) else None


def normalize_pois(
    raw: Any,
    *,
    fallback_kind: str,
    to_float: FloatParser,
    to_int: IntParser,
) -> list[POIRecommendation]:
    data = extract_poi_items(raw)
    if not isinstance(data, list):
        return []

    pois: list[POIRecommendation] = []
    for item in data[:20]:
        if not isinstance(item, dict):
            continue
        longitude, latitude = extract_coordinates(item, to_float=to_float)
        pois.append(
            POIRecommendation(
                name=str(item.get("name", item.get("title", fallback_kind))),
                poi_id=str(item.get("id", item.get("poi_id", ""))) or None,
                address=str(item.get("address", item.get("location_name", ""))),
                tags=normalize_tags(item),
                rating=to_float(item.get("rating", item.get("score"))),
                recommended_duration_minutes=to_int(
                    item.get("recommended_duration_minutes", item.get("duration"))
                ),
                opening_hours=str(item.get("opening_hours", item.get("business_hours", ""))) or None,
                district=str(item.get("district", item.get("adname", ""))) or None,
                longitude=longitude,
                latitude=latitude,
                source="amap_mcp",
            )
        )
    return pois


def normalize_poi_detail(
    raw: Any,
    *,
    fallback: POIRecommendation,
    to_float: FloatParser,
) -> POIRecommendation:
    detail = extract_poi_detail_record(raw)
    if not isinstance(detail, dict):
        return fallback

    longitude, latitude = extract_coordinates(detail, to_float=to_float)
    merged_tags = fallback.tags or normalize_tags(detail)
    return POIRecommendation(
        name=str(detail.get("name", fallback.name)),
        poi_id=str(detail.get("id", fallback.poi_id or "")) or None,
        address=str(detail.get("address", fallback.address)),
        tags=merged_tags,
        rating=to_float(detail.get("rating", fallback.rating)),
        recommended_duration_minutes=fallback.recommended_duration_minutes,
        opening_hours=str(
            detail.get("opening_hours", detail.get("business_hours", fallback.opening_hours or ""))
        )
        or fallback.opening_hours,
        district=str(
            detail.get("district", detail.get("adname", detail.get("city", fallback.district or "")))
        )
        or fallback.district,
        longitude=longitude if longitude is not None else fallback.longitude,
        latitude=latitude if latitude is not None else fallback.latitude,
        source=fallback.source,
    )
