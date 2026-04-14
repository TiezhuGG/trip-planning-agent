from __future__ import annotations

from typing import Any

from app.schemas.planning import DayStayInfo, MealRecommendation, POIRecommendation
from app.utils.local_cuisine import get_city_signature_keywords


def ensure_daily_core_meals(
    meals: list[MealRecommendation],
    restaurants: list[Any],
    stay: DayStayInfo,
    hotel_area: str,
    day_theme: str,
    day_index: int,
    budget_level: str,
) -> list[MealRecommendation]:
    by_type: dict[str, MealRecommendation] = {}
    for meal in meals:
        by_type.setdefault(meal.meal_type, meal)

    def _fallback_meal(meal_type: str) -> MealRecommendation:
        base_cost = default_meal_cost(meal_type, budget_level)
        if meal_type == "breakfast":
            venue = f"{stay.hotel_name} 早餐厅" if stay.hotel_name else f"{hotel_area or '酒店附近'} 早餐店"
            cuisine = "本地早餐"
            suggestion = "建议 08:00 前后用餐，出发前补充能量。"
        else:
            offset = 0 if meal_type == "lunch" else 1
            candidate = restaurants[(day_index * 2 + offset) % len(restaurants)] if restaurants else None
            venue = getattr(candidate, "name", "") or f"{day_theme} 附近餐厅"
            cuisine = ",".join(getattr(candidate, "tags", [])[:2]) if candidate else "本地风味"
            suggestion = "优先选择当日景点片区附近的本地小吃或地方餐馆，减少往返耗时。"
        return MealRecommendation(
            meal_type=meal_type,  # type: ignore[arg-type]
            venue_name=venue,
            cuisine=cuisine,
            suggestion=suggestion,
            estimated_cost=f"¥{base_cost}/人",
            estimated_cost_cny=base_cost,
        )

    ordered = [
        by_type.get("breakfast") or _fallback_meal("breakfast"),
        by_type.get("lunch") or _fallback_meal("lunch"),
        by_type.get("dinner") or _fallback_meal("dinner"),
    ]
    extras = [meal for meal in meals if meal.meal_type not in {"breakfast", "lunch", "dinner"}]
    return ordered + extras


def default_room_nightly_cost(budget_level: str) -> int:
    return {
        "economy": 360,
        "comfort": 620,
        "luxury": 1350,
    }.get(budget_level, 620)


def default_meal_cost(
    meal_type: str,
    budget_level: str,
) -> int:
    budget_map = {
        "economy": {"breakfast": 20, "lunch": 45, "dinner": 65},
        "comfort": {"breakfast": 30, "lunch": 70, "dinner": 110},
        "luxury": {"breakfast": 45, "lunch": 120, "dinner": 180},
    }
    return budget_map.get(budget_level, budget_map["comfort"]).get(meal_type, 50)


def harmonize_cost_estimate(
    observed_cost: int,
    heuristic_cost: int,
    floor_ratio: float,
    ceiling_ratio: float,
) -> int:
    if heuristic_cost <= 0:
        return max(0, observed_cost)
    if observed_cost <= 0:
        return heuristic_cost
    if observed_cost < int(heuristic_cost * floor_ratio):
        return heuristic_cost
    if observed_cost > int(heuristic_cost * ceiling_ratio):
        return heuristic_cost
    return observed_cost


def estimate_room_nightly_cost(
    budget_level: str,
    hotel: POIRecommendation | None,
) -> int:
    base_cost = default_room_nightly_cost(budget_level)
    if hotel is None:
        return base_cost

    text = poi_text(hotel)
    multiplier = 1.0
    economy_keywords = ("青年旅舍", "客栈", "驿站", "快捷", "轻居", "宾馆", "公寓", "hostel", "inn")
    comfort_keywords = ("酒店", "智选", "欢朋", "美居", "桔子", "全季", "亚朵", "精选", "假日")
    premium_keywords = (
        "豪华",
        "国际",
        "温泉",
        "度假",
        "庄园",
        "万豪",
        "希尔顿",
        "凯悦",
        "洲际",
        "君悦",
        "香格里拉",
        "悦榕庄",
    )

    if any(word.lower() in text.lower() for word in premium_keywords):
        multiplier += 0.35
    elif any(word.lower() in text.lower() for word in comfort_keywords):
        multiplier += 0.08
    elif any(word.lower() in text.lower() for word in economy_keywords):
        multiplier -= 0.18

    rating = hotel.rating or 0.0
    if rating >= 4.8:
        multiplier += 0.18
    elif rating >= 4.6:
        multiplier += 0.10
    elif rating >= 4.3:
        multiplier += 0.04
    elif 0 < rating < 4.0:
        multiplier -= 0.08

    if any(tag.startswith("1001") for tag in hotel.tags):
        multiplier += 0.08
    if any(tag.startswith("1003") for tag in hotel.tags):
        multiplier -= 0.08

    estimated = round_price(base_cost * multiplier)
    bounds = {
        "economy": (220, 880),
        "comfort": (360, 1580),
        "luxury": (680, 3200),
    }
    lower_bound, upper_bound = bounds.get(budget_level, bounds["comfort"])
    return max(lower_bound, min(upper_bound, estimated))


def estimate_meal_cost(
    meal_type: str,
    budget_level: str,
    restaurant: POIRecommendation | None,
    destination: str = "",
) -> int:
    base_cost = default_meal_cost(meal_type, budget_level)
    if restaurant is None:
        return base_cost

    text = poi_text(restaurant)
    multiplier = 1.0

    local_words = ("小吃", "风味", "地方菜", "本地", "老字号", "私房", "海鲜", "土菜", "闽南", "渔港")
    breakfast_words = ("早餐", "早茶", "包子", "粥", "豆浆", "粉", "面线糊", "面馆")
    light_meal_words = ("面馆", "粉店", "快餐", "简餐", "套餐", "小馆", "小吃")
    dinner_words = ("海鲜", "酒楼", "大排档", "私房", "火锅", "烤肉", "烧烤", "宴", "景观")
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

    if any(word.lower() in text.lower() for word in chain_words):
        multiplier -= 0.18
    if any(word in text for word in local_words):
        multiplier += 0.10
    if any(word in text for word in get_city_signature_keywords(destination)):
        multiplier += 0.08

    if meal_type == "breakfast":
        if any(word in text for word in breakfast_words):
            multiplier -= 0.05
        if any(word in text for word in dinner_words):
            multiplier += 0.12
    elif meal_type == "lunch":
        if any(word in text for word in light_meal_words):
            multiplier -= 0.02
        if any(word in text for word in dinner_words):
            multiplier += 0.10
    elif meal_type == "dinner":
        if any(word in text for word in dinner_words):
            multiplier += 0.22
        if any(word in text for word in light_meal_words):
            multiplier -= 0.05

    rating = restaurant.rating or 0.0
    if rating >= 4.8:
        multiplier += 0.12
    elif rating >= 4.6:
        multiplier += 0.07
    elif 0 < rating < 4.0:
        multiplier -= 0.06

    estimated = round_price(base_cost * multiplier)
    bounds = {
        "breakfast": (15, max(50, int(base_cost * 1.7))),
        "lunch": (25, max(120, int(base_cost * 1.9))),
        "dinner": (35, max(180, int(base_cost * 2.4))),
        "snack": (15, max(80, int(base_cost * 1.6))),
    }
    lower_bound, upper_bound = bounds.get(meal_type, (20, max(120, int(base_cost * 2.0))))
    return max(lower_bound, min(upper_bound, estimated))


def poi_text(poi: POIRecommendation) -> str:
    return " ".join(
        [
            poi.name,
            poi.address,
            poi.district or "",
            *[str(tag) for tag in poi.tags],
        ]
    )


def round_price(value: float) -> int:
    rounded = int(round(max(0.0, value) / 5.0) * 5)
    return max(0, rounded)
