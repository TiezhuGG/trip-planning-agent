from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from app.config import Settings
from app.schemas.planning import (
    DailyForecast,
    GeoPoint,
    IntegrationStatus,
    POIRecommendation,
    PlanningContext,
    RouteStep,
    RouteSummary,
    ToolCallRecord,
    TripPlanningRequest,
    WeatherSummary,
)
from app.services.mcp_stdio_client import MCPProtocolError, MCPStdioClient
from app.utils.json_extract import extract_json_payload


class AmapMCPAdapter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = (
            MCPStdioClient(
                command=settings.amap_mcp_command,
                args=settings.amap_mcp_args,
                env=settings.amap_mcp_env,
                timeout_seconds=settings.amap_mcp_timeout_seconds,
            )
            if settings.has_mcp
            else None
        )
        self._tool_catalog: list[dict[str, Any]] | None = None
        self._resolved_tools: dict[str, str] = {}

    @property
    def has_client(self) -> bool:
        return self.client is not None

    def mock_context(
        self, request: TripPlanningRequest
    ) -> tuple[PlanningContext, list[ToolCallRecord]]:
        return self._mock_context(request)

    async def diagnose(self) -> IntegrationStatus:
        warnings: list[str] = []
        available_tools: list[str] = []
        resolved_tools: dict[str, str] = {}
        missing_tools: list[str] = []
        mcp_connected = False

        if self.client is not None:
            try:
                catalog = await asyncio.wait_for(
                    self._ensure_tool_catalog(force_refresh=True),
                    timeout=self.settings.amap_mcp_timeout_seconds + 2,
                )
                available_tools = [item.get("name", "") for item in catalog if item.get("name")]
                mcp_connected = True
                resolved_tools = {
                    purpose: self._resolve_tool_name(purpose, strict=False) or ""
                    for purpose in ("poi_search", "route_plan", "weather")
                }
                resolved_tools = {key: value for key, value in resolved_tools.items() if value}
                missing_tools = [
                    purpose
                    for purpose in ("poi_search", "route_plan", "weather")
                    if purpose not in resolved_tools
                ]
                if missing_tools:
                    warnings.append(
                        f"MCP 已连接，但仍缺少工具映射: {', '.join(missing_tools)}。"
                    )
            except Exception as exc:
                warnings.append(self._format_connection_error(exc))
        elif not self.settings.enable_mock_mcp:
            warnings.append("未配置 MCP 启动命令，且已关闭 Mock。规划请求会直接失败。")

        if self.settings.amap_api_key and not self.settings.amap_security_js_code:
            warnings.append("已配置高德 JS Key，但未配置安全密钥；如果控制台开启了安全校验，前端地图会加载失败。")

        return IntegrationStatus(
            mcp_enabled=self.settings.has_mcp,
            mcp_connected=mcp_connected,
            mcp_command=self.settings.amap_mcp_command,
            available_tools=available_tools,
            resolved_tools=resolved_tools,
            missing_tools=missing_tools,
            map_rendering_enabled=self.settings.has_map_rendering,
            map_js_key_configured=bool(self.settings.amap_api_key),
            security_js_code_configured=bool(self.settings.amap_security_js_code),
            mock_enabled=self.settings.enable_mock_mcp,
            warnings=warnings,
        )

    async def collect_context(
        self, request: TripPlanningRequest
    ) -> tuple[PlanningContext, list[ToolCallRecord]]:
        if self.client is None:
            return self._mock_context(request)

        trace: list[ToolCallRecord] = []
        try:
            attractions = await self.fetch_attractions(request, trace)
            restaurants = await self.fetch_restaurants(request, trace)
            hotels = await self.fetch_hotels(request, trace)
            weather = await self.fetch_weather(request, trace)
            return (
                PlanningContext(
                    destination=request.destination,
                    attractions=attractions[:12],
                    restaurants=restaurants[:12],
                    hotels=hotels[:8],
                    routes=[],
                    weather=weather,
                ),
                trace,
            )
        except Exception:
            if self.settings.enable_mock_mcp:
                return self._mock_context(request)
            raise

    async def fetch_attractions(
        self, request: TripPlanningRequest, trace: list[ToolCallRecord]
    ) -> list[POIRecommendation]:
        queries = [f"{request.destination} 热门景点"]
        queries.extend(f"{request.destination} {keyword}" for keyword in request.must_visit[:4])
        pois: list[POIRecommendation] = []
        for query in queries:
            raw = await self._call_tool_for_purpose(
                "poi_search",
                self._build_poi_search_arguments(request.destination, query),
                trace,
            )
            pois.extend(self._normalize_pois(raw, fallback_kind="景点"))
        return self._merge_unique_pois(pois)

    async def fetch_restaurants(
        self, request: TripPlanningRequest, trace: list[ToolCallRecord]
    ) -> list[POIRecommendation]:
        preference = request.dining_preferences[0] if request.dining_preferences else "特色餐厅"
        raw = await self._call_tool_for_purpose(
            "poi_search",
            self._build_poi_search_arguments(request.destination, f"{request.destination} {preference}"),
            trace,
        )
        return self._normalize_pois(raw, fallback_kind="餐厅")

    async def fetch_hotels(
        self, request: TripPlanningRequest, trace: list[ToolCallRecord]
    ) -> list[POIRecommendation]:
        raw = await self._call_tool_for_purpose(
            "poi_search",
            self._build_poi_search_arguments(request.destination, f"{request.destination} {request.hotel_style}"),
            trace,
        )
        return self._normalize_pois(raw, fallback_kind="酒店")

    async def fetch_weather(
        self, request: TripPlanningRequest, trace: list[ToolCallRecord]
    ) -> WeatherSummary:
        raw = await self._call_tool_for_purpose(
            "weather",
            {"city": request.destination},
            trace,
        )
        return self._normalize_weather(raw, request)

    async def plan_route(
        self,
        day_number: int,
        origin: POIRecommendation,
        destination: POIRecommendation,
        waypoints: list[POIRecommendation],
        mode: str,
        trace: list[ToolCallRecord],
    ) -> RouteSummary:
        if self.client is None:
            return self._mock_route(day_number, origin, destination, waypoints, mode)

        tool_name = self._resolve_route_tool_name(mode)
        raw = await self._call_tool_for_purpose(
            "route_plan",
            self._build_route_arguments(origin, destination),
            trace,
            tool_name_override=tool_name,
        )
        return self._normalize_route(raw, day_number, origin, destination, waypoints, mode)

    async def _call_tool_for_purpose(
        self,
        purpose: str,
        arguments: dict[str, Any],
        trace: list[ToolCallRecord],
        tool_name_override: str | None = None,
    ) -> Any:
        assert self.client is not None
        await asyncio.wait_for(
            self._ensure_tool_catalog(),
            timeout=self.settings.amap_mcp_timeout_seconds + 2,
        )
        tool_name = tool_name_override or self._resolve_tool_name(purpose)
        if not tool_name:
            available = [item.get("name", "") for item in (self._tool_catalog or []) if item.get("name")]
            raise MCPProtocolError(
                f"未找到可用于 {purpose} 的 MCP 工具；当前可用工具: {', '.join(available) if available else '无'}"
            )
        try:
            result = await asyncio.wait_for(
                self.client.call_tool(tool_name, arguments),
                timeout=self.settings.amap_mcp_timeout_seconds + 2,
            )
            normalized = self._unwrap_tool_result(result)
            trace.append(
                ToolCallRecord(
                    tool_name=tool_name,
                    arguments=arguments,
                    success=True,
                    summary=f"工具调用成功 ({purpose})",
                )
            )
            return normalized
        except MCPProtocolError as exc:
            trace.append(
                ToolCallRecord(
                    tool_name=tool_name,
                    arguments=arguments,
                    success=False,
                    summary=f"工具调用失败 ({purpose}): {exc}",
                )
            )
            raise
        except Exception as exc:
            trace.append(
                ToolCallRecord(
                    tool_name=tool_name,
                    arguments=arguments,
                    success=False,
                    summary=f"工具调用异常 ({purpose}): {exc}",
                )
            )
            raise

    async def _ensure_tool_catalog(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        if self.client is None:
            return []
        if self._tool_catalog is not None and not force_refresh:
            return self._tool_catalog

        result = await asyncio.wait_for(
            self.client.list_tools(),
            timeout=self.settings.amap_mcp_timeout_seconds + 2,
        )
        tools = result.get("tools", []) if isinstance(result, dict) else []
        if not isinstance(tools, list):
            tools = []
        self._tool_catalog = [item for item in tools if isinstance(item, dict)]
        return self._tool_catalog

    def _resolve_tool_name(self, purpose: str, strict: bool = True) -> str | None:
        if purpose in self._resolved_tools:
            return self._resolved_tools[purpose]

        configured_name = {
            "poi_search": self.settings.amap_mcp_tool_poi_search,
            "route_plan": self.settings.amap_mcp_tool_route_plan,
            "weather": self.settings.amap_mcp_tool_weather,
        }[purpose]
        catalog = self._tool_catalog or []
        available = [item.get("name", "") for item in catalog if item.get("name")]

        if configured_name and configured_name in available:
            self._resolved_tools[purpose] = configured_name
            return configured_name

        best_name = ""
        best_score = -1
        keywords = self._purpose_keywords(purpose)
        for item in catalog:
            name = str(item.get("name", ""))
            description = str(item.get("description", ""))
            text = f"{name} {description}".lower()
            score = 0
            for keyword in keywords:
                if keyword in text:
                    score += 1
            if score > best_score:
                best_score = score
                best_name = name

        if best_name and best_score > 0:
            self._resolved_tools[purpose] = best_name
            return best_name

        if configured_name:
            return configured_name if not strict else None
        return None

    def _purpose_keywords(self, purpose: str) -> list[str]:
        return {
            "poi_search": ["text_search", "poi", "keyword", "search", "place"],
            "route_plan": ["direction", "driving", "walking", "transit", "bicycling", "address"],
            "weather": ["weather", "forecast", "climate"],
        }[purpose]

    def _resolve_route_tool_name(self, mode: str) -> str | None:
        catalog = self._tool_catalog or []
        available = [str(item.get("name", "")) for item in catalog if item.get("name")]
        preferred = {
            "driving": "maps_direction_driving_by_address",
            "transit": "maps_direction_transit_integrated_by_address",
            "walking": "maps_direction_walking_by_address",
            "bicycling": "maps_direction_bicycling_by_address",
        }.get(mode, self.settings.amap_mcp_tool_route_plan)

        if preferred in available:
            return preferred

        fallback_keywords = {
            "driving": ["driving", "direction"],
            "transit": ["transit", "integrated", "direction"],
            "walking": ["walking", "direction"],
            "bicycling": ["bicycling", "cycling", "direction"],
        }.get(mode, ["direction"])

        best_name = ""
        best_score = -1
        for item in catalog:
            name = str(item.get("name", ""))
            description = str(item.get("description", ""))
            text = f"{name} {description}".lower()
            score = sum(1 for keyword in fallback_keywords if keyword in text)
            if score > best_score:
                best_score = score
                best_name = name

        if best_name and best_score > 0:
            return best_name

        return self._resolve_tool_name("route_plan", strict=False)

    def _build_poi_search_arguments(self, city: str, keywords: str) -> dict[str, Any]:
        return {
            "keywords": keywords,
            "city": city,
            "city_limit": True,
        }

    def _build_route_arguments(
        self,
        origin: POIRecommendation,
        destination: POIRecommendation,
    ) -> dict[str, Any]:
        return {
            "origin": self._route_address(origin),
            "destination": self._route_address(destination),
            "city": origin.district or origin.address or origin.name,
            "cityd": destination.district or destination.address or destination.name,
        }

    def _format_connection_error(self, exc: Exception) -> str:
        detail = f"{exc.__class__.__name__}: {exc}" if str(exc) else exc.__class__.__name__
        if self.client is None:
            return f"MCP 连接失败: {detail}"

        snapshot = self.client.get_debug_snapshot()
        resolved_command = snapshot.get("resolved_command") or snapshot.get("command") or self.settings.amap_mcp_command
        stderr_tail = snapshot.get("stderr_tail") or []
        stderr_text = f"；stderr: {' | '.join(stderr_tail)}" if stderr_tail else ""
        return f"MCP 连接失败: {detail}；命令: {resolved_command}{stderr_text}"

    def _unwrap_tool_result(self, result: Any) -> Any:
        if isinstance(result, dict) and "content" in result:
            content = result["content"]
            if isinstance(content, list):
                texts: list[str] = []
                structured: list[Any] = []
                for item in content:
                    if isinstance(item, dict):
                        if "json" in item:
                            structured.append(item["json"])
                        if item.get("type") == "text" and "text" in item:
                            texts.append(item["text"])
                if structured:
                    return structured[0] if len(structured) == 1 else structured
                if texts:
                    extracted = extract_json_payload("\n".join(texts))
                    return extracted if extracted is not None else {"text": "\n".join(texts)}
            return content
        return result

    def _normalize_pois(self, raw: Any, fallback_kind: str) -> list[POIRecommendation]:
        data = raw
        if isinstance(raw, dict):
            for key in ("pois", "items", "data", "results", "list"):
                if key in raw and isinstance(raw[key], list):
                    data = raw[key]
                    break
        if not isinstance(data, list):
            return []

        pois: list[POIRecommendation] = []
        for item in data[:20]:
            if not isinstance(item, dict):
                continue
            longitude, latitude = self._extract_coordinates(item)
            pois.append(
                POIRecommendation(
                    name=str(item.get("name", item.get("title", fallback_kind))),
                    poi_id=str(item.get("id", item.get("poi_id", ""))) or None,
                    address=str(item.get("address", item.get("location_name", ""))),
                    tags=self._normalize_tags(item),
                    rating=self._to_float(item.get("rating", item.get("score"))),
                    recommended_duration_minutes=self._to_int(
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

    def _normalize_weather(self, raw: Any, request: TripPlanningRequest) -> WeatherSummary:
        forecasts: list[DailyForecast] = []
        overview = f"{request.destination} 行程期间天气整体适合出游。"
        suggestions: list[str] = ["建议准备轻薄外套", "中午时段注意防晒"]
        temp_range = "18-28°C"

        if isinstance(raw, dict):
            overview = str(raw.get("overview", raw.get("summary", overview)))
            suggestions_raw = raw.get("suggestions", raw.get("tips", suggestions))
            if isinstance(suggestions_raw, str):
                suggestions = [suggestions_raw]
            elif isinstance(suggestions_raw, list):
                suggestions = [str(item) for item in suggestions_raw][:4]

            temp_range = str(
                raw.get(
                    "temperature_range",
                    raw.get("temperature", raw.get("temp_range", temp_range)),
                )
            )

            forecast_items = None
            for key in ("daily_forecasts", "forecasts", "casts", "data"):
                value = raw.get(key)
                if isinstance(value, list):
                    forecast_items = value
                    break
                if isinstance(value, dict):
                    for nested_key in ("casts", "forecasts", "daily"):
                        nested_value = value.get(nested_key)
                        if isinstance(nested_value, list):
                            forecast_items = nested_value
                            break
                if forecast_items is not None:
                    break

            if isinstance(forecast_items, list):
                for index, item in enumerate(forecast_items[: request.days]):
                    if not isinstance(item, dict):
                        continue
                    forecasts.append(
                        DailyForecast(
                            date=str(item.get("date", request.start_date + timedelta(days=index))),
                            day_weather=str(item.get("day_weather", item.get("dayweather", item.get("weather", "")))),
                            night_weather=str(item.get("night_weather", item.get("nightweather", ""))),
                            high_temperature=str(item.get("high_temperature", item.get("daytemp", item.get("high", "")))),
                            low_temperature=str(item.get("low_temperature", item.get("nighttemp", item.get("low", "")))),
                            advice=str(item.get("advice", item.get("tip", ""))),
                        )
                    )

        if not forecasts:
            for index in range(request.days):
                date = request.start_date + timedelta(days=index)
                forecasts.append(
                    DailyForecast(
                        date=str(date),
                        day_weather="晴到多云",
                        night_weather="多云",
                        high_temperature="28",
                        low_temperature="20",
                        advice="白天注意防晒，夜间可准备一件薄外套。",
                    )
                )

        if forecasts:
            highs = [self._to_int(item.high_temperature) for item in forecasts if self._to_int(item.high_temperature) is not None]
            lows = [self._to_int(item.low_temperature) for item in forecasts if self._to_int(item.low_temperature) is not None]
            if highs and lows:
                temp_range = f"{min(lows)}-{max(highs)}°C"

        return WeatherSummary(
            overview=overview,
            temperature_range=temp_range,
            suggestions=suggestions,
            daily_forecasts=forecasts,
        )

    def _normalize_route(
        self,
        raw: Any,
        day_number: int,
        origin: POIRecommendation,
        destination: POIRecommendation,
        waypoints: list[POIRecommendation],
        mode: str,
    ) -> RouteSummary:
        route_data = raw
        if isinstance(raw, dict) and isinstance(raw.get("route"), dict):
            route_data = raw["route"]
        if isinstance(route_data, dict) and isinstance(route_data.get("paths"), list) and route_data["paths"]:
            route_data = route_data["paths"][0]

        distance_text = ""
        duration_text = ""
        steps: list[RouteStep] = []
        polyline: list[GeoPoint] = []

        if isinstance(route_data, dict):
            distance_text = str(route_data.get("distance_text", route_data.get("distance", "")))
            duration_text = str(route_data.get("duration_text", route_data.get("duration", "")))
            raw_steps = route_data.get("steps", [])
            if isinstance(raw_steps, list):
                for item in raw_steps[:8]:
                    if not isinstance(item, dict):
                        continue
                    steps.append(
                        RouteStep(
                            instruction=str(item.get("instruction", item.get("text", "继续直行"))),
                            distance_text=str(item.get("distance_text", item.get("distance", ""))),
                            duration_text=str(item.get("duration_text", item.get("duration", ""))),
                        )
                    )
                    polyline.extend(self._extract_polyline_points(item.get("polyline")))

            if not polyline:
                polyline.extend(self._extract_polyline_points(route_data.get("polyline")))

        if not polyline:
            polyline = self._fallback_polyline(origin, destination, waypoints)

        route_title = f"第 {day_number} 天路线"
        waypoint_names = [item.name for item in waypoints]
        return RouteSummary(
            day_number=day_number,
            title=route_title,
            from_name=origin.name,
            to_name=destination.name,
            waypoints=waypoint_names,
            distance_text=distance_text or "待工具返回",
            duration_text=duration_text or "待工具返回",
            mode=mode,
            steps=steps,
            polyline=polyline,
        )

    def _mock_context(
        self, request: TripPlanningRequest
    ) -> tuple[PlanningContext, list[ToolCallRecord]]:
        city = request.destination
        center = self._city_center(city)
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

    def _mock_route(
        self,
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
            steps=[
                RouteStep(instruction=f"从 {origin.name} 出发前往 {waypoints[0].name if waypoints else destination.name}", distance_text="5km", duration_text="15分钟"),
                RouteStep(instruction=f"继续前往 {destination.name}", distance_text="7km", duration_text="20分钟"),
            ],
            polyline=self._fallback_polyline(origin, destination, waypoints),
        )

    def _merge_unique_pois(self, pois: list[POIRecommendation]) -> list[POIRecommendation]:
        seen: set[str] = set()
        merged: list[POIRecommendation] = []
        for poi in pois:
            key = poi.poi_id or poi.name
            if key in seen:
                continue
            seen.add(key)
            merged.append(poi)
        return merged

    def _normalize_tags(self, item: dict[str, Any]) -> list[str]:
        tags = item.get("tags", item.get("tag", item.get("type", [])))
        if isinstance(tags, str):
            return [segment.strip() for segment in tags.replace("|", ",").split(",") if segment.strip()]
        if isinstance(tags, list):
            return [str(tag) for tag in tags if str(tag).strip()]
        return []

    def _extract_coordinates(self, item: dict[str, Any]) -> tuple[float | None, float | None]:
        if "longitude" in item or "latitude" in item:
            return self._to_float(item.get("longitude")), self._to_float(item.get("latitude"))

        location = item.get("location") or item.get("lnglat") or item.get("point")
        if isinstance(location, str) and "," in location:
            longitude_text, latitude_text = location.split(",", 1)
            return self._to_float(longitude_text), self._to_float(latitude_text)
        if isinstance(location, dict):
            return self._to_float(location.get("lng", location.get("longitude"))), self._to_float(
                location.get("lat", location.get("latitude"))
            )
        return None, None

    def _extract_polyline_points(self, raw_polyline: Any) -> list[GeoPoint]:
        points: list[GeoPoint] = []
        if isinstance(raw_polyline, str):
            for segment in raw_polyline.split(";"):
                if "," not in segment:
                    continue
                longitude_text, latitude_text = segment.split(",", 1)
                longitude = self._to_float(longitude_text)
                latitude = self._to_float(latitude_text)
                if longitude is None or latitude is None:
                    continue
                points.append(GeoPoint(longitude=longitude, latitude=latitude))
        elif isinstance(raw_polyline, list):
            for item in raw_polyline:
                if isinstance(item, dict):
                    longitude = self._to_float(item.get("lng", item.get("longitude")))
                    latitude = self._to_float(item.get("lat", item.get("latitude")))
                    if longitude is not None and latitude is not None:
                        points.append(GeoPoint(longitude=longitude, latitude=latitude))
        return points

    def _fallback_polyline(
        self,
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

    def _route_address(self, poi: POIRecommendation) -> str:
        if poi.address:
            return poi.address
        if poi.district:
            return f"{poi.district}{poi.name}"
        return poi.name

    def _city_center(self, city: str) -> GeoPoint:
        centers = {
            "北京": GeoPoint(longitude=116.4074, latitude=39.9042),
            "上海": GeoPoint(longitude=121.4737, latitude=31.2304),
            "杭州": GeoPoint(longitude=120.1551, latitude=30.2741),
            "成都": GeoPoint(longitude=104.0665, latitude=30.5728),
            "广州": GeoPoint(longitude=113.2644, latitude=23.1291),
            "深圳": GeoPoint(longitude=114.0579, latitude=22.5431),
        }
        return centers.get(city, GeoPoint(longitude=121.4737, latitude=31.2304))

    def _to_float(self, value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _to_int(self, value: Any) -> int | None:
        try:
            if value is None or value == "":
                return None
            return int(float(value))
        except (TypeError, ValueError):
            return None
