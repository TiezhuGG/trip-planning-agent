from __future__ import annotations

from datetime import timedelta
from typing import Any, Callable

from app.schemas.planning import (
    Activity,
    BudgetBreakdown,
    DayCostBreakdown,
    DailyForecast,
    DayPlan,
    DayStayInfo,
    InitialPlanDay,
    InitialPlanDraft,
    MealRecommendation,
    PlanningContext,
    RouteStep,
    RouteSummary,
    StayRecommendation,
    TravelPlan,
    TripPlanningRequest,
)


def fallback_plan(
    request: TripPlanningRequest,
    initial_plan: InitialPlanDraft,
    context: PlanningContext,
    extract_cny_amount: Callable[[str], int],
) -> TravelPlan:
    attractions = context.attractions or []
    restaurants = context.restaurants or []
    hotels = context.hotels or []
    daily_forecasts = context.weather.daily_forecasts or []
    routes = context.routes or []

    budget_map = {
        "economy": ("¥280-450/晚", "¥60-120/天", "¥50-100/天", "¥100-180/天", "¥500-900/人"),
        "comfort": ("¥450-800/晚", "¥120-220/天", "¥120-220/天", "¥180-320/天", "¥1200-2200/人"),
        "luxury": ("¥900-1800/晚", "¥260-500/天", "¥280-480/天", "¥320-600/天", "¥2800-5200/人"),
    }
    stay_cost, transport_cost, food_cost, ticket_cost, total_cost = budget_map[request.budget_level]

    days: list[DayPlan] = []
    for day_index in range(request.days):
        trip_date = request.start_date + timedelta(days=day_index)
        seed_day = initial_plan.days[day_index] if day_index < len(initial_plan.days) else None
        hotel = hotels[day_index % len(hotels)] if hotels else None
        day_weather = (
            daily_forecasts[day_index]
            if day_index < len(daily_forecasts)
            else default_daily_forecast(str(trip_date))
        )
        day_route = routes[day_index] if day_index < len(routes) else None
        day_attractions = select_day_attractions(attractions, seed_day, day_index)
        day_restaurants = select_day_restaurants(restaurants, day_index)

        activities: list[Activity] = []
        for attraction_index, attraction in enumerate(day_attractions[:2]):
            start_time = "09:00" if attraction_index == 0 else "14:00"
            end_time = "11:30" if attraction_index == 0 else "17:00"
            transport_tip = "从酒店出发，优先使用地铁或网约车。"
            if attraction_index != 0:
                transport_tip = "结合路线规划在午餐后前往下一站。"
            if day_route and day_route.steps:
                step_index = min(attraction_index, len(day_route.steps) - 1)
                transport_tip = day_route.steps[step_index].instruction or transport_tip
            activities.append(
                Activity(
                    start_time=start_time,
                    end_time=end_time,
                    title=f"游览 {attraction.name}",
                    category="sightseeing" if attraction_index == 0 else "explore",
                    description=f"围绕 {attraction.name} 安排核心游览与拍照时间，并根据现场排队情况灵活微调。",
                    location_name=attraction.name,
                    transport_from_previous=transport_tip,
                    expected_cost="¥80/人",
                    ticket_cost_cny=80,
                    booking_tip="热门景点建议提前预约并错峰到达",
                )
            )
        if not activities:
            focus = seed_day.focus if seed_day else request.destination
            activities.append(
                Activity(
                    start_time="09:30",
                    end_time="12:00",
                    title=f"{focus} 城市漫游",
                    category="explore",
                    description=(
                        f"围绕 {focus} 安排一段弹性较高的城市漫游，"
                        "优先覆盖核心街区、地标外观和适合停留拍照的开放区域。"
                    ),
                    location_name=request.destination,
                    transport_from_previous="从住宿区域出发，优先使用地铁或步行衔接。",
                    expected_cost="¥0/人",
                    ticket_cost_cny=0,
                    booking_tip="根据当天体力和天气灵活调整停留时长。",
                )
            )

        if day_route is None:
            day_route = fallback_route_summary(
                day_number=day_index + 1,
                request=request,
                hotel=hotel,
                seed_day=seed_day,
                destination_name=activities[0].location_name,
            )

        meals = build_meals(day_restaurants, food_cost, extract_cny_amount)
        route_tip = (
            f"参考路线总时长约 {day_route.duration_text}。"
            if day_route and day_route.duration_text
            else "优先选择地铁与网约车组合，兼顾效率与舒适度。"
        )
        transport_tips = [
            f"天气：{day_weather.day_weather or context.weather.overview}，建议按当天实际温度调整出发时间。",
            route_tip,
            day_weather.advice or "午后注意补水，夜间备一件薄外套。",
        ]

        days.append(
            DayPlan(
                day_number=day_index + 1,
                date=str(trip_date),
                theme=seed_day.theme if seed_day else theme_for_day(day_index, request),
                overview=(
                    f"第 {day_index + 1} 天以 {seed_day.focus if seed_day else request.destination} 为重点，"
                    f"串联景点、餐饮和返程动线，整体节奏保持{pace_label(request.pace)}。"
                ),
                hotel_area=hotel.address if hotel and hotel.address else request.hotel_style,
                transport_tips=[tip for tip in transport_tips if tip],
                meals=meals,
                activities=activities,
                weather=day_weather,
                route_summary=day_route,
                route_summaries=[day_route] if day_route else [],
                stay=DayStayInfo(
                    area=hotel.address if hotel and hotel.address else request.hotel_style,
                    hotel_name=hotel.name if hotel else f"{request.destination} 市中心酒店",
                    reason="靠近主要游览区域，适合当日行程动线。",
                    room_nightly_cost_cny=extract_cny_amount(stay_cost),
                ),
                cost_breakdown=DayCostBreakdown(),
            )
        )

    stay_recommendations = [
        StayRecommendation(
            area=hotel.address or request.hotel_style,
            hotel_name=hotel.name,
            reason="靠近主要游览片区，适合多日行程中转。",
            nightly_budget=stay_cost,
        )
        for hotel in hotels[:2]
    ]
    if not stay_recommendations:
        stay_recommendations.append(
            StayRecommendation(
                area=request.hotel_style,
                hotel_name=f"{request.destination} 市中心酒店",
                reason="交通便利，适合作为默认住宿区域。",
                nightly_budget=stay_cost,
            )
        )

    return TravelPlan(
        title=f"{request.destination}{request.days}天智能旅行计划",
        summary=(
            f"围绕 {request.destination} 设计了一份 {request.days} 天行程，"
            "先由总控 Agent 输出初步草案，再结合景点、天气、餐饮和路线信息汇总成最终计划。"
        ),
        weather_summary=f"{context.weather.overview} 温度约 {context.weather.temperature_range}。",
        best_booking_tip="热门景点和核心商圈酒店建议至少提前 3-7 天预订，节假日需更早锁定。",
        estimated_budget=BudgetBreakdown(
            accommodation=stay_cost,
            transport=transport_cost,
            food=food_cost,
            tickets=ticket_cost,
            extras="¥100-300/人",
            total_estimate=total_cost,
        ),
        stay_recommendations=stay_recommendations,
        city_tips=[
            "第一天尽量安排轻量行程，避免长途到达后过度疲劳。",
            "核心景点建议早到，午后转入街区或美食场景。",
            "如有老人或儿童同行，适当压缩单日步行距离。",
        ],
        packing_list=[
            "身份证件与预订信息",
            "舒适步行鞋",
            "轻薄外套",
            "充电宝和数据线",
            "基础防晒用品",
        ],
        days=days,
    )


def fallback_route_summary(
    day_number: int,
    request: TripPlanningRequest,
    hotel: Any | None,
    seed_day: InitialPlanDay | None,
    destination_name: str,
) -> RouteSummary:
    hotel_name = getattr(hotel, "name", "") if hotel is not None else ""
    hotel_area = getattr(hotel, "address", "") if hotel is not None else ""
    focus = seed_day.focus if seed_day else request.destination
    return RouteSummary(
        day_number=day_number,
        title=f"第 {day_number} 天 {focus} 动线",
        from_name=hotel_name or hotel_area or request.hotel_style,
        to_name=destination_name or request.destination,
        waypoints=[focus] if focus and focus != request.destination else [],
        duration_text="约 30-45 分钟",
        mode="transit",
        estimated_transport_cost_cny=20,
        steps=[
            RouteStep(
                instruction="从住宿区域出发，优先乘坐地铁或打车前往当日核心片区。",
                distance_text="约 8 公里",
                duration_text="约 30-45 分钟",
            )
        ],
    )


def default_daily_forecast(date: str) -> DailyForecast:
    return DailyForecast(
        date=date,
        day_weather="晴到多云",
        night_weather="多云",
        high_temperature="28",
        low_temperature="20",
        advice="中午注意防晒，夜间可准备一件薄外套。",
    )


def select_day_attractions(
    attractions: list[Any],
    seed_day: InitialPlanDay | None,
    day_index: int,
) -> list[Any]:
    if not attractions:
        return []
    selected: list[Any] = []
    if seed_day and seed_day.must_visit:
        for keyword in seed_day.must_visit:
            matched = next((poi for poi in attractions if keyword in poi.name), None)
            if matched and matched not in selected:
                selected.append(matched)
    start = day_index % len(attractions)
    for offset in range(len(attractions)):
        poi = attractions[(start + offset) % len(attractions)]
        if poi not in selected:
            selected.append(poi)
        if len(selected) >= 2:
            break
    return selected


def select_day_restaurants(restaurants: list[Any], day_index: int) -> list[Any]:
    if not restaurants:
        return []
    lunch = restaurants[day_index % len(restaurants)]
    dinner = restaurants[(day_index + 1) % len(restaurants)] if len(restaurants) > 1 else lunch
    return [lunch, dinner]


def build_meals(
    restaurants: list[Any],
    food_cost: str,
    extract_cny_amount: Callable[[str], int],
) -> list[MealRecommendation]:
    meal_types = ["lunch", "dinner"]
    suggestions = [
        "中午建议安排在核心景点附近，减少往返折返。",
        "晚餐可放在夜游片区附近，方便继续散步或返程。",
    ]
    meals: list[MealRecommendation] = []
    for index, restaurant in enumerate(restaurants[:2]):
        meals.append(
            MealRecommendation(
                meal_type=meal_types[index],
                venue_name=restaurant.name,
                cuisine="本地特色 / 人气餐厅",
                suggestion=suggestions[index],
                estimated_cost=food_cost,
                estimated_cost_cny=extract_cny_amount(food_cost),
            )
        )
    return meals


def theme_for_day(day_index: int, request: TripPlanningRequest) -> str:
    themes = [
        "城市初见与核心地标",
        "文化探索与街区漫游",
        "自然休闲与夜游体验",
        "深度打卡与美食搜罗",
    ]
    if request.must_visit and day_index == 0:
        return f"优先打卡 {request.must_visit[0]}"
    return themes[day_index % len(themes)]


def pace_label(pace: str) -> str:
    return {
        "relaxed": "轻松",
        "balanced": "均衡",
        "intense": "紧凑",
    }.get(pace, "均衡")
