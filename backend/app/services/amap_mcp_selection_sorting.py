from __future__ import annotations

from typing import Callable

from app.schemas.planning import POIRecommendation
from app.utils.local_cuisine import get_city_signature_keywords, get_generic_local_food_keywords

from app.services.amap_mcp_selection_geo import anchor_center, distance_score

CityCenterResolver = Callable[[str], object]
HasCoordinates = Callable[[POIRecommendation], bool]


def sort_hotels_for_stay(
    *,
    hotels: list[POIRecommendation],
    anchor_pois: list[POIRecommendation],
    city: str,
    city_center: CityCenterResolver,
    has_coordinates: HasCoordinates,
) -> list[POIRecommendation]:
    center = anchor_center(anchor_pois, city_center=city_center) if anchor_pois else city_center(city)

    def is_stay_hotel(poi: POIRecommendation) -> bool:
        name = poi.name
        tags = [str(tag) for tag in poi.tags]
        name_hit = any(word in name for word in ("酒店", "宾馆", "旅馆", "民宿", "客栈"))
        tag_hit = any(tag.startswith(("10", "100")) for tag in tags)
        return name_hit or tag_hit

    def is_non_stay_facility(poi: POIRecommendation) -> bool:
        name = poi.name
        return any(
            word in name
            for word in ("博物馆", "服务中心", "政务", "体育馆", "售票处", "康复中心", "汽车", "4S")
        )

    return sorted(
        hotels,
        key=lambda poi: (
            0 if is_stay_hotel(poi) else 1,
            0 if has_coordinates(poi) else 1,
            1 if is_non_stay_facility(poi) else 0,
            distance_score(poi, center),
        ),
    )


def sort_restaurants_for_route(
    *,
    restaurants: list[POIRecommendation],
    city: str,
    anchor_pois: list[POIRecommendation],
    city_center: CityCenterResolver,
    has_coordinates: HasCoordinates,
) -> list[POIRecommendation]:
    center = anchor_center(anchor_pois, city_center=city_center) if anchor_pois else city_center(city)
    city_signature_words = get_city_signature_keywords(city)
    generic_local_words = get_generic_local_food_keywords()

    def is_restaurant(poi: POIRecommendation) -> bool:
        text = f"{poi.name} {' '.join(str(tag) for tag in poi.tags)}"
        tags = [str(tag) for tag in poi.tags]
        name_hit = any(word in text for word in ("餐厅", "饭店", "酒楼", "馆", "小吃", "奶茶", "咖啡"))
        tag_hit = any(tag.startswith("05") for tag in tags)
        signature_hit = any(word in text for word in city_signature_words)
        return name_hit or tag_hit or signature_hit

    def is_chain_restaurant(poi: POIRecommendation) -> bool:
        text = f"{poi.name} {' '.join(str(tag) for tag in poi.tags)}"
        chain_words = (
            "肯德基",
            "麦当劳",
            "德克士",
            "必胜客",
            "汉堡王",
            "星巴克",
            "瑞幸",
            "喜茶",
            "奈雪",
            "沪上阿姨",
            "costa",
            "kfc",
            "mcdonald",
        )
        return any(word.lower() in text.lower() for word in chain_words)

    def is_local_flavor(poi: POIRecommendation) -> bool:
        text = f"{poi.name} {' '.join(str(tag) for tag in poi.tags)}"
        local_words = (*generic_local_words, "闽南")
        return any(word in text for word in local_words)

    def is_city_signature(poi: POIRecommendation) -> bool:
        if not city_signature_words:
            return False
        text = f"{poi.name} {' '.join(str(tag) for tag in poi.tags)}"
        return any(word in text for word in city_signature_words)

    return sorted(
        restaurants,
        key=lambda poi: (
            0 if has_coordinates(poi) else 1,
            0 if bool((poi.district or "").strip()) else 1,
            0 if is_restaurant(poi) else 1,
            0 if is_city_signature(poi) else 1,
            0 if is_local_flavor(poi) else 1,
            1 if is_chain_restaurant(poi) else 0,
            distance_score(poi, center),
        ),
    )
