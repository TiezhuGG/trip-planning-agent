from app.schemas.planning import (
    AgentExecution,
    MealRecommendation,
    POIRecommendation,
    PlanningContext,
    ToolCallRecord,
    TravelPlan,
    TripPlanningRequest,
)
from app.services.amap_mcp_adapter import AmapMCPAdapter


class MealRecommendationAgent:
    def __init__(self, adapter: AmapMCPAdapter | None = None) -> None:
        self.adapter = adapter

    def gather(
        self,
        request: TripPlanningRequest,
        initial_plan,
        restaurants: list[POIRecommendation],
    ) -> dict[int, list[POIRecommendation]]:
        _ = (request, initial_plan)
        if not restaurants:
            return {}

        day_meals: dict[int, list[POIRecommendation]] = {}
        for day_index in range(len(initial_plan.days)):
            start_index = day_index % len(restaurants)
            selected: list[POIRecommendation] = []
            for offset in range(len(restaurants)):
                restaurant = restaurants[(start_index + offset) % len(restaurants)]
                if restaurant in selected:
                    continue
                selected.append(restaurant)
                if len(selected) >= 2:
                    break
            day_meals[day_index + 1] = selected
        return day_meals

    async def bind_daily_meals(
        self,
        request: TripPlanningRequest,
        plan: TravelPlan,
        context: PlanningContext,
        trace: list[ToolCallRecord],
    ) -> tuple[TravelPlan, list[POIRecommendation], AgentExecution]:
        if self.adapter is None:
            return (
                plan,
                context.restaurants,
                AgentExecution(agent_name="meal_binding_agent", success=True, summary="未配置按天餐饮绑定，保留原餐饮结果。"),
            )

        updated_days = []
        selected_restaurants: list[POIRecommendation] = []
        warnings: list[str] = []
        rebound_days = 0

        for day in sorted(plan.days, key=lambda item: item.day_number):
            location_names = [activity.location_name for activity in day.activities if activity.location_name][:3]
            stay_hint = day.stay.hotel_name or day.hotel_area
            area_hint = day.hotel_area or day.stay.area
            try:
                day_restaurants = await self.adapter.fetch_restaurants_for_locations(
                    request=request,
                    trace=trace,
                    location_names=location_names,
                    area_hint=area_hint,
                    stay_hint=stay_hint,
                )
            except Exception as exc:
                warnings.append(f"第 {day.day_number} 天餐饮绑定失败，已保留原餐饮。原因: {exc}")
                updated_days.append(day)
                continue

            updated_days.append(
                day.model_copy(
                    update={
                        "meals": self._build_day_meals(day, day_restaurants),
                    }
                )
            )
            selected_restaurants.extend(day_restaurants[:3])
            if day_restaurants:
                rebound_days += 1

        summary = "已按每日活动区域校正餐饮推荐。" if rebound_days else "未命中需要校正的每日餐饮推荐。"
        return (
            plan.model_copy(update={"days": updated_days}),
            self._merge_unique_restaurants([*selected_restaurants, *context.restaurants]),
            AgentExecution(
                agent_name="meal_binding_agent",
                success=True,
                summary=summary,
                used_llm=False,
                used_tools=[],
                warnings=warnings,
            ),
        )

    def _build_day_meals(
        self,
        day,
        restaurants: list[POIRecommendation],
    ) -> list[MealRecommendation]:
        breakfast_candidate = self._pick_restaurant(restaurants, preferred_kind="breakfast")
        lunch_candidate = self._pick_restaurant(restaurants, preferred_kind="lunch", exclude={breakfast_candidate.name} if breakfast_candidate else set())
        dinner_candidate = self._pick_restaurant(
            restaurants,
            preferred_kind="dinner",
            exclude={name for name in [getattr(breakfast_candidate, "name", ""), getattr(lunch_candidate, "name", "")] if name},
        )

        breakfast_venue = (
            breakfast_candidate.name
            if breakfast_candidate is not None
            else (f"{day.stay.hotel_name} 早餐厅" if day.stay.hotel_name else f"{day.hotel_area or '酒店附近'} 早餐店")
        )
        lunch_venue = lunch_candidate.name if lunch_candidate is not None else f"{day.activities[0].location_name if day.activities else day.theme} 附近餐厅"
        dinner_focus = day.activities[-1].location_name if day.activities else day.theme
        dinner_venue = dinner_candidate.name if dinner_candidate is not None else f"{dinner_focus} 附近餐厅"

        return [
            MealRecommendation(
                meal_type="breakfast",
                venue_name=breakfast_venue,
                cuisine=self._restaurant_cuisine(breakfast_candidate, "本地早餐"),
                suggestion="优先选择酒店附近或出发点周边早餐，减少晨间折返。",
                estimated_cost="¥30/人",
                estimated_cost_cny=30,
            ),
            MealRecommendation(
                meal_type="lunch",
                venue_name=lunch_venue,
                cuisine=self._restaurant_cuisine(lunch_candidate, "本地风味"),
                suggestion="午餐安排在上午活动点附近，方便接下午行程。",
                estimated_cost="¥80/人",
                estimated_cost_cny=80,
            ),
            MealRecommendation(
                meal_type="dinner",
                venue_name=dinner_venue,
                cuisine=self._restaurant_cuisine(dinner_candidate, "海鲜/地方菜"),
                suggestion="晚餐安排在收尾活动或返住片区附近，减少跨区往返。",
                estimated_cost="¥120/人",
                estimated_cost_cny=120,
            ),
        ]

    def _pick_restaurant(
        self,
        restaurants: list[POIRecommendation],
        preferred_kind: str,
        exclude: set[str] | None = None,
    ) -> POIRecommendation | None:
        exclude = exclude or set()
        scored: list[tuple[int, int, POIRecommendation]] = []
        for restaurant in restaurants:
            if restaurant.name in exclude:
                continue
            score = self._restaurant_kind_score(restaurant, preferred_kind)
            coordinate_bonus = 0 if restaurant.longitude is not None and restaurant.latitude is not None else 1
            scored.append((-score, coordinate_bonus, restaurant))
        if not scored:
            return None
        scored.sort(key=lambda item: item[:2])
        return scored[0][2]

    def _restaurant_kind_score(
        self,
        restaurant: POIRecommendation,
        preferred_kind: str,
    ) -> int:
        text = f"{restaurant.name} {' '.join(restaurant.tags)}"
        breakfast_words = ("早餐", "早茶", "面线糊", "包子", "粥", "豆浆", "小吃")
        dinner_words = ("海鲜", "酒楼", "饭店", "餐厅", "大排档", "私房")
        if preferred_kind == "breakfast":
            return 3 if any(word in text for word in breakfast_words) else 1
        if preferred_kind == "dinner":
            return 3 if any(word in text for word in dinner_words) else 1
        return 2 if any(word in text for word in ("餐厅", "饭店", "馆", "小吃")) else 1

    def _restaurant_cuisine(
        self,
        restaurant: POIRecommendation | None,
        fallback: str,
    ) -> str:
        if restaurant is None or not restaurant.tags:
            return fallback
        return ",".join(restaurant.tags[:2])

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
