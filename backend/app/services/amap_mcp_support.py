from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.schemas.planning import (
    DailyForecast,
    GeoPoint,
    POIRecommendation,
    PlanningContext,
    RouteStep,
    RouteSummary,
    ToolCallRecord,
    TripPlanningRequest,
    WeatherSummary,
)


def city_center(city: str) -> GeoPoint:
    centers = {
        "北京": GeoPoint(longitude=116.4074, latitude=39.9042),
        "上海": GeoPoint(longitude=121.4737, latitude=31.2304),
        "杭州": GeoPoint(longitude=120.1551, latitude=30.2741),
        "成都": GeoPoint(longitude=104.0665, latitude=30.5728),
        "广州": GeoPoint(longitude=113.2644, latitude=23.1291),
        "深圳": GeoPoint(longitude=114.0579, latitude=22.5431),
    }
    return centers.get(city, GeoPoint(longitude=121.4737, latitude=31.2304))


def to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def fallback_polyline(
    origin: POIRecommendation,
    destination: POIRecommendation,
    waypoints: list[POIRecommendation],
) -> list[GeoPoint]:
    points: list[GeoPoint] = []
    for poi in [origin, *waypoints, destination]:
        if poi.longitude is None or poi.latitude is None:
            continue
        points.append(GeoPoint(longitude=poi.longitude, latitude=poi.latitude))
    return points


def route_address(poi: POIRecommendation) -> str:
    if poi.address:
        return poi.address
    if poi.district:
        return f"{poi.district}{poi.name}"
    return poi.name


def legacy_mock_context(request: TripPlanningRequest) -> tuple[PlanningContext, list[ToolCallRecord]]:
    city = request.destination
    center = city_center(city)
    attractions = [
        POIRecommendation(
            name=request.must_visit[0] if request.must_visit else f"{city} 博物馆",
            address=f"{city} 中心城区",
            tags=["文化", "地标"],
            rating=4.7,
            recommended_duration_minutes=120,
            opening_hours="09:00-17:30",
            longitude=center.longitude + 0.02,
            latitude=center.latitude + 0.01,
            source="mock",
        ),
        POIRecommendation(
            name=f"{city} 老城区步行街",
            address=f"{city} 历史街区",
            tags=["街区", "美食"],
            rating=4.6,
            recommended_duration_minutes=150,
            opening_hours="全天开放",
            longitude=center.longitude - 0.015,
            latitude=center.latitude + 0.018,
            source="mock",
        ),
        POIRecommendation(
            name=f"{city} 城市公园",
            address=f"{city} 滨水区域",
            tags=["自然", "休闲"],
            rating=4.5,
            recommended_duration_minutes=90,
            opening_hours="06:00-22:00",
            longitude=center.longitude + 0.01,
            latitude=center.latitude - 0.02,
            source="mock",
        ),
    ]
    restaurants = [
        POIRecommendation(
            name=f"{city} 本地风味馆",
            address=f"{city} 核心商圈",
            tags=["地方菜"],
            longitude=center.longitude + 0.008,
            latitude=center.latitude + 0.004,
            source="mock",
        ),
        POIRecommendation(
            name=f"{city} 夜市小吃街",
            address=f"{city} 老城区",
            tags=["小吃", "夜游"],
            longitude=center.longitude - 0.01,
            latitude=center.latitude + 0.013,
            source="mock",
        ),
    ]
    hotels = [
        POIRecommendation(
            name=f"{city} 中心商务酒店",
            address=f"{city} 地铁沿线",
            tags=["交通方便"],
            longitude=center.longitude,
            latitude=center.latitude,
            source="mock",
        ),
        POIRecommendation(
            name=f"{city} 景观轻奢酒店",
            address=f"{city} 江景片区",
            tags=["景观", "舒适"],
            longitude=center.longitude + 0.012,
            latitude=center.latitude - 0.012,
            source="mock",
        ),
    ]
    forecasts = [
        DailyForecast(
            date=str(request.start_date + timedelta(days=index)),
            day_weather="晴到多云" if index % 2 == 0 else "多云",
            night_weather="多云",
            high_temperature=str(28 - index),
            low_temperature=str(20 - min(index, 2)),
            advice="白天注意防晒，夜间可准备薄外套。",
        )
        for index in range(request.days)
    ]
    trace = [
        ToolCallRecord(
            tool_name="mock_poi_search",
            arguments={"city": city},
            success=True,
            summary="未配置高德 MCP，已使用开发态 Mock 景点和餐饮数据。",
        ),
        ToolCallRecord(
            tool_name="mock_weather",
            arguments={"city": city},
            success=True,
            summary="未配置高德 MCP，已使用开发态 Mock 天气数据。",
        ),
    ]
    context = PlanningContext(
        destination=city,
        attractions=attractions,
        restaurants=restaurants,
        hotels=hotels,
        routes=[],
        weather=WeatherSummary(
            overview=f"{city} 行程期间天气总体适合出游。",
            temperature_range=f"{forecasts[-1].low_temperature}-{forecasts[0].high_temperature}°C",
            suggestions=["白天建议防晒", "夜间可准备薄外套", "适合步行和城市观光"],
            daily_forecasts=forecasts,
        ),
    )
    return context, trace


def mock_route(
    day_number: int,
    origin: POIRecommendation,
    destination: POIRecommendation,
    waypoints: list[POIRecommendation],
    mode: str,
) -> RouteSummary:
    return RouteSummary(
        day_number=day_number,
        title=f"第 {day_number} 天路线",
        from_name=origin.name,
        to_name=destination.name,
        waypoints=[item.name for item in waypoints],
        distance_text="12km",
        duration_text="35分钟",
        mode=mode,
        estimated_transport_cost_cny=30 if mode in {"driving", "transit"} else 0,
        steps=[
            RouteStep(
                instruction=f"从 {origin.name} 出发前往 {waypoints[0].name if waypoints else destination.name}",
                distance_text="5km",
                duration_text="15分钟",
            ),
            RouteStep(
                instruction=f"继续前往 {destination.name}",
                distance_text="7km",
                duration_text="20分钟",
            ),
        ],
        polyline=fallback_polyline(origin, destination, waypoints),
    )
