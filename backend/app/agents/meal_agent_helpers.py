from __future__ import annotations

from app.schemas.planning import MealRecommendation, POIRecommendation, TripPlanningRequest
from app.utils.local_cuisine import get_city_signature_keywords, get_generic_local_food_keywords


class MealRecommendationAgentHelpersMixin:
    def _build_day_meals(
        self,
        request: TripPlanningRequest,
        day,
        restaurants: list[POIRecommendation],
    ) -> list[MealRecommendation]:
        breakfast_candidate = self._pick_restaurant(
            restaurants,
            preferred_kind="breakfast",
            city=request.destination,
        )
        lunch_candidate = self._pick_restaurant(
            restaurants,
            preferred_kind="lunch",
            exclude={breakfast_candidate.name} if breakfast_candidate else set(),
            city=request.destination,
        )
        dinner_candidate = self._pick_restaurant(
            restaurants,
            preferred_kind="dinner",
            exclude={
                name
                for name in [
                    getattr(breakfast_candidate, "name", ""),
                    getattr(lunch_candidate, "name", ""),
                ]
                if name
            },
            city=request.destination,
        )
        breakfast_cost, lunch_cost, dinner_cost = self._daily_meal_budget(request)

        breakfast_venue = (
            breakfast_candidate.name
            if breakfast_candidate is not None
            else (
                f"{day.stay.hotel_name} 早餐厅"
                if day.stay.hotel_name
                else f"{day.hotel_area or '酒店附近'} 早餐店"
            )
        )
        lunch_venue = (
            lunch_candidate.name
            if lunch_candidate is not None
            else f"{day.activities[0].location_name if day.activities else day.theme} 附近餐馆"
        )
        dinner_focus = day.activities[-1].location_name if day.activities else day.theme
        dinner_venue = (
            dinner_candidate.name
            if dinner_candidate is not None
            else f"{dinner_focus} 附近餐馆"
        )

        return [
            MealRecommendation(
                meal_type="breakfast",
                venue_name=breakfast_venue,
                cuisine=self._restaurant_cuisine(breakfast_candidate, "本地早餐"),
                suggestion="优先选择出发点附近的本地早餐铺或小吃店，减少晨间折返。",
                estimated_cost=f"¥{breakfast_cost}/人",
                estimated_cost_cny=breakfast_cost,
            ),
            MealRecommendation(
                meal_type="lunch",
                venue_name=lunch_venue,
                cuisine=self._restaurant_cuisine(lunch_candidate, "地方风味"),
                suggestion="午餐优先安排在上午活动景点周边的本地小吃或地方餐馆。",
                estimated_cost=f"¥{lunch_cost}/人",
                estimated_cost_cny=lunch_cost,
            ),
            MealRecommendation(
                meal_type="dinner",
                venue_name=dinner_venue,
                cuisine=self._restaurant_cuisine(dinner_candidate, "地方菜"),
                suggestion="晚餐优先安排在收尾活动或返住片区附近的本地特色餐馆。",
                estimated_cost=f"¥{dinner_cost}/人",
                estimated_cost_cny=dinner_cost,
            ),
        ]

    def _pick_restaurant(
        self,
        restaurants: list[POIRecommendation],
        preferred_kind: str,
        exclude: set[str] | None = None,
        city: str = "",
    ) -> POIRecommendation | None:
        exclude = exclude or set()
        scored: list[tuple[int, int, int, int, int, int, POIRecommendation]] = []
        for restaurant in restaurants:
            if restaurant.name in exclude:
                continue
            type_score = self._restaurant_kind_score(restaurant, preferred_kind, city=city)
            timing_penalty = self._restaurant_timing_penalty(restaurant, preferred_kind)
            signature_penalty = 0 if self._matches_city_signature(restaurant, city) else 1
            local_penalty = 0 if self._is_local_restaurant(restaurant) else 1
            chain_penalty = 1 if self._is_chain_restaurant(restaurant) else 0
            coordinate_penalty = 0 if restaurant.longitude is not None and restaurant.latitude is not None else 1
            scored.append(
                (
                    -type_score,
                    timing_penalty,
                    signature_penalty,
                    local_penalty,
                    chain_penalty,
                    coordinate_penalty,
                    restaurant,
                )
            )
        if not scored:
            return None
        scored.sort(key=lambda item: item[:6])
        return scored[0][6]

    def _restaurant_kind_score(
        self,
        restaurant: POIRecommendation,
        preferred_kind: str,
        city: str = "",
    ) -> int:
        text = self._restaurant_text(restaurant)
        breakfast_words = ("早餐", "早茶", "面线糊", "包子", "粥", "豆浆", "小吃", "汤粉", "沙茶")
        lunch_words = ("餐厅", "饭店", "小馆", "简餐", "面馆", "粉店", "小吃", "套餐")
        local_words = ("小吃", "地方菜", "闽南", "本地", "老字号", "海鲜", "土菜", "风味", "私房")
        dinner_words = ("海鲜", "酒楼", "饭店", "餐厅", "大排档", "私房", "地方菜", "土菜")
        city_signature_bonus = 2 if self._matches_city_signature(restaurant, city) else 0
        if preferred_kind == "breakfast":
            return (4 if any(word in text for word in breakfast_words) else 1) + city_signature_bonus
        if preferred_kind == "lunch":
            if any(word in text for word in lunch_words):
                return 4 + city_signature_bonus
            if any(word in text for word in local_words):
                return 3 + city_signature_bonus
            return 2 + city_signature_bonus
        if preferred_kind == "dinner":
            return (4 if any(word in text for word in dinner_words) else 2) + min(1, city_signature_bonus)
        return (4 if any(word in text for word in local_words) else 2) + city_signature_bonus

    def _restaurant_timing_penalty(
        self,
        restaurant: POIRecommendation,
        preferred_kind: str,
    ) -> int:
        text = self._restaurant_text(restaurant)
        breakfast_words = ("早餐", "早茶", "豆浆", "包子", "粥")
        dinner_words = ("海鲜", "酒楼", "大排档", "私房", "烧烤")
        if preferred_kind == "breakfast":
            return 0 if any(word in text for word in breakfast_words) else 1
        if preferred_kind == "lunch":
            if any(word in text for word in breakfast_words):
                return 2
            if any(word in text for word in dinner_words):
                return 1
            return 0
        return 0 if any(word in text for word in dinner_words) else 1

    def _is_local_restaurant(self, restaurant: POIRecommendation) -> bool:
        text = self._restaurant_text(restaurant)
        local_words = (*get_generic_local_food_keywords(), "闽南", "渔港", "砂锅", "面线糊", "姜母鸭")
        return any(word in text for word in local_words)

    def _is_chain_restaurant(self, restaurant: POIRecommendation) -> bool:
        text = self._restaurant_text(restaurant)
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

    def _restaurant_text(self, restaurant: POIRecommendation) -> str:
        return f"{restaurant.name} {' '.join(str(tag) for tag in restaurant.tags)} {restaurant.address or ''}"

    def _matches_city_signature(
        self,
        restaurant: POIRecommendation,
        city: str,
    ) -> bool:
        if not city:
            return False
        text = self._restaurant_text(restaurant)
        return any(word in text for word in get_city_signature_keywords(city))

    def _restaurant_cuisine(
        self,
        restaurant: POIRecommendation | None,
        fallback: str,
    ) -> str:
        if restaurant is None or not restaurant.tags:
            return fallback
        readable_tags = [tag for tag in restaurant.tags if not str(tag).isdigit()]
        return ",".join(readable_tags[:2]) if readable_tags else fallback

    def _daily_meal_budget(
        self,
        request: TripPlanningRequest,
    ) -> tuple[int, int, int]:
        budget_map = {
            "economy": (20, 45, 65),
            "comfort": (30, 70, 110),
            "luxury": (45, 120, 180),
        }
        return budget_map[request.budget_level]

    def _merge_unique_restaurants(
        self,
        restaurants: list[POIRecommendation],
    ) -> list[POIRecommendation]:
        merged: list[POIRecommendation] = []
        seen: set[str] = set()
        for restaurant in restaurants:
            key = restaurant.poi_id or restaurant.name
            if key in seen:
                continue
            seen.add(key)
            merged.append(restaurant)
        return merged
