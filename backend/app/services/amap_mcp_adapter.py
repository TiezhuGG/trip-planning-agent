from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

import httpx

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
                inherit_proxy_env=settings.amap_mcp_inherit_proxy_env,
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
        queries: list[str] = []
        for keyword in request.must_visit[:4]:
            queries.extend([keyword, f"{keyword} 景点"])
        for interest in request.interests[:3]:
            queries.append(f"{interest} 景点")
        queries.extend(["旅游景点", "热门景点", "景区"])
        merged = await self._search_poi_candidates(
            city=request.destination,
            queries=queries,
            trace=trace,
            fallback_kind="景点",
            target_count=10,
        )
        return await self._enrich_pois_with_details(merged, trace)

    async def fetch_restaurants(
        self, request: TripPlanningRequest, trace: list[ToolCallRecord]
    ) -> list[POIRecommendation]:
        queries: list[str] = []
        for preference in request.dining_preferences[:3]:
            queries.extend([preference, f"{preference} 餐厅"])
        queries.extend(["本地美食", "特色餐厅", "热门餐厅"])
        merged = await self._search_poi_candidates(
            city=request.destination,
            queries=queries,
            trace=trace,
            fallback_kind="餐厅",
            target_count=8,
        )
        return await self._enrich_pois_with_details(merged, trace)

    async def fetch_hotels(
        self,
        request: TripPlanningRequest,
        trace: list[ToolCallRecord],
        anchor_pois: list[POIRecommendation] | None = None,
    ) -> list[POIRecommendation]:
        queries = self._build_hotel_queries(request, anchor_pois or [])
        merged = await self._search_poi_candidates(
            city=request.destination,
            queries=queries,
            trace=trace,
            fallback_kind="酒店",
            target_count=10,
        )
        enriched = await self._enrich_pois_with_details(merged, trace)
        return self._sort_hotels_for_stay(enriched, anchor_pois or [], request.destination)

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

        attempted_modes: list[str] = []
        errors: list[str] = []
        for candidate_mode in self._route_mode_candidates(mode):
            attempted_modes.append(candidate_mode)

            if candidate_mode in {"transit", "driving", "walking"}:
                try:
                    raw = await self._plan_route_via_web_service(candidate_mode, origin, destination, waypoints, trace)
                    return self._normalize_route(raw, day_number, origin, destination, waypoints, candidate_mode)
                except Exception as exc:
                    errors.append(f"{candidate_mode}_webservice: {exc}")

            for tool_name, arguments in self._build_route_tool_attempts(candidate_mode, origin, destination):
                try:
                    raw = await self._call_tool_for_purpose(
                        "route_plan",
                        arguments,
                        trace,
                        tool_name_override=tool_name,
                    )
                    return self._normalize_route(raw, day_number, origin, destination, waypoints, candidate_mode)
                except Exception as exc:
                    errors.append(f"{candidate_mode}/{tool_name}: {exc}")

        fallback_route = self._fallback_route(day_number, origin, destination, waypoints, mode)
        trace.append(
            ToolCallRecord(
                tool_name="route_fallback_summary",
                arguments={
                    "origin": origin.name,
                    "destination": destination.name,
                    "mode": mode,
                },
                success=True,
                summary=f"路线工具失败，已回退为概览路线：{'；'.join(errors[:3])}",
            )
        )
        return fallback_route

    async def _plan_transit_via_web_service(
        self,
        origin: POIRecommendation,
        destination: POIRecommendation,
        trace: list[ToolCallRecord],
    ) -> dict[str, Any]:
        api_key = self._amap_web_service_key()
        if not api_key:
            raise MCPProtocolError("未配置高德 Web Service Key，无法走公交路线直连兜底。")

        origin_location = await self._resolve_route_location(origin)
        destination_location = await self._resolve_route_location(destination)
        origin_city = self._normalize_city_name(origin.district)
        destination_city = self._normalize_city_name(destination.district)
        arguments = {
            "origin": origin_location,
            "destination": destination_location,
            "city": origin_city,
            "cityd": destination_city,
        }

        async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
            response = await client.get(
                "https://restapi.amap.com/v3/direction/transit/integrated",
                params={
                    "key": api_key,
                    **arguments,
                },
            )
            response.raise_for_status()
            payload = response.json()

        if str(payload.get("status", "")) != "1":
            raise MCPProtocolError(
                f"高德公交 Web Service 返回错误: {payload.get('info') or payload.get('infocode') or payload}"
            )
        route = payload.get("route")
        if not isinstance(route, dict) or not isinstance(route.get("transits"), list) or not route.get("transits"):
            raise MCPProtocolError("高德公交 Web Service 未返回可用 transit 方案。")

        normalized_payload = {
            "route": {
                "origin": route.get("origin", origin_location),
                "destination": route.get("destination", destination_location),
                "distance": route.get("distance", route.get("taxi_cost", "")),
                "transits": route.get("transits", []),
            }
        }
        trace.append(
            ToolCallRecord(
                tool_name="amap_webservice_transit_integrated",
                arguments=arguments,
                success=True,
                summary=f"工具调用成功 (route_plan) {self._summarize_tool_payload(normalized_payload)}",
            )
        )
        return normalized_payload

    async def _plan_route_via_web_service(
        self,
        mode: str,
        origin: POIRecommendation,
        destination: POIRecommendation,
        waypoints: list[POIRecommendation],
        trace: list[ToolCallRecord],
    ) -> dict[str, Any]:
        if mode == "transit":
            return await self._plan_transit_via_web_service(origin, destination, trace)

        api_key = self._amap_web_service_key()
        if not api_key:
            raise MCPProtocolError("未配置高德 Web Service Key，无法走路线直连兜底。")

        origin_location = await self._resolve_route_location(origin)
        destination_location = await self._resolve_route_location(destination)
        endpoint = {
            "driving": "https://restapi.amap.com/v3/direction/driving",
            "walking": "https://restapi.amap.com/v3/direction/walking",
        }.get(mode)
        if not endpoint:
            raise MCPProtocolError(f"不支持的 Web Service 路线模式: {mode}")

        arguments: dict[str, Any] = {
            "origin": origin_location,
            "destination": destination_location,
        }
        if mode == "driving":
            waypoint_locations = [
                location
                for location in [await self._resolve_route_location(poi) for poi in waypoints[:3]]
                if location and location not in {origin_location, destination_location}
            ]
            if waypoint_locations:
                arguments["waypoints"] = "|".join(waypoint_locations)

        async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
            response = await client.get(
                endpoint,
                params={
                    "key": api_key,
                    **arguments,
                },
            )
            response.raise_for_status()
            payload = response.json()

        if str(payload.get("status", "")) != "1":
            raise MCPProtocolError(
                f"高德 {mode} Web Service 返回错误: {payload.get('info') or payload.get('infocode') or payload}"
            )

        trace.append(
            ToolCallRecord(
                tool_name=f"amap_webservice_{mode}",
                arguments=arguments,
                success=True,
                summary=f"工具调用成功 (route_plan) {self._summarize_tool_payload(payload)}",
            )
        )
        return payload

    def _build_route_tool_attempts(
        self,
        mode: str,
        origin: POIRecommendation,
        destination: POIRecommendation,
    ) -> list[tuple[str, dict[str, Any]]]:
        attempts: list[tuple[str, dict[str, Any]]] = []
        coordinate_tool = self._resolve_route_tool_name(mode, coordinate=True)
        if coordinate_tool and self._has_coordinates(origin) and self._has_coordinates(destination):
            attempts.append((coordinate_tool, self._build_route_coordinate_arguments(origin, destination)))

        address_tool = self._resolve_route_tool_name(mode, coordinate=False)
        if address_tool:
            attempts.append((address_tool, self._build_route_arguments(origin, destination)))

        deduped: list[tuple[str, dict[str, Any]]] = []
        seen: set[tuple[str, str]] = set()
        for tool_name, arguments in attempts:
            key = (tool_name, str(arguments))
            if key in seen:
                continue
            seen.add(key)
            deduped.append((tool_name, arguments))
        return deduped
    async def _resolve_route_location(self, poi: POIRecommendation) -> str:
        if poi.longitude is not None and poi.latitude is not None:
            return f"{poi.longitude},{poi.latitude}"

        api_key = self._amap_web_service_key()
        if not api_key:
            raise MCPProtocolError("缺少高德 Web Service Key，无法为路线规划补做 geocode。")

        city = self._normalize_city_name(poi.district)
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
            for candidate in self._route_address_candidates(poi):
                response = await client.get(
                    "https://restapi.amap.com/v3/geocode/geo",
                    params={
                        "key": api_key,
                        "address": candidate,
                        "city": city,
                    },
                )
                response.raise_for_status()
                payload = response.json()
                if str(payload.get("status", "")) != "1":
                    continue
                geocodes = payload.get("geocodes")
                if isinstance(geocodes, list) and geocodes and geocodes[0].get("location"):
                    return str(geocodes[0]["location"])

        raise MCPProtocolError(f"未能为地址解析坐标: {self._route_address(poi)}")

    def _amap_web_service_key(self) -> str:
        return str(self.settings.amap_mcp_env.get("AMAP_MAPS_API_KEY", "")).strip()

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
            self._raise_on_tool_error(normalized, tool_name)
            trace.append(
                ToolCallRecord(
                    tool_name=tool_name,
                    arguments=arguments,
                    success=True,
                    summary=f"工具调用成功 ({purpose}) {self._summarize_tool_payload(normalized)}",
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

    def _resolve_search_detail_tool_name(self) -> str | None:
        catalog = self._tool_catalog or []
        available = [str(item.get("name", "")) for item in catalog if item.get("name")]
        if "maps_search_detail" in available:
            return "maps_search_detail"

        best_name = ""
        best_score = -1
        for item in catalog:
            name = str(item.get("name", ""))
            description = str(item.get("description", ""))
            text = f"{name} {description}".lower()
            score = sum(1 for keyword in ["detail", "poi", "search"] if keyword in text)
            if score > best_score:
                best_score = score
                best_name = name

        return best_name if best_name and best_score > 0 else None

    async def _enrich_pois_with_details(
        self,
        pois: list[POIRecommendation],
        trace: list[ToolCallRecord],
    ) -> list[POIRecommendation]:
        if self.client is None or not pois:
            return pois

        detail_tool_name = self._resolve_search_detail_tool_name()
        if not detail_tool_name:
            return pois

        enriched: list[POIRecommendation] = []
        for poi in pois[:12]:
            if not poi.poi_id:
                enriched.append(poi)
                continue

            try:
                raw = await self._call_tool_for_purpose(
                    "poi_search",
                    {"id": poi.poi_id},
                    trace,
                    tool_name_override=detail_tool_name,
                )
                detail_poi = self._normalize_poi_detail(raw, poi)
                enriched.append(detail_poi)
            except Exception:
                enriched.append(poi)

        return enriched

    def _resolve_route_tool_name(self, mode: str, coordinate: bool | None = None) -> str | None:
        catalog = self._tool_catalog or []
        available = [str(item.get("name", "")) for item in catalog if item.get("name")]
        preferred_map = {
            ("driving", True): "maps_direction_driving_by_coordinates",
            ("driving", False): "maps_direction_driving_by_address",
            ("transit", True): "maps_direction_transit_integrated_by_coordinates",
            ("transit", False): "maps_direction_transit_integrated_by_address",
            ("walking", True): "maps_direction_walking_by_coordinates",
            ("walking", False): "maps_direction_walking_by_address",
            ("bicycling", True): "maps_bicycling_by_coordinates",
            ("bicycling", False): "maps_bicycling_by_address",
        }
        preferred = preferred_map.get((mode, coordinate)) if coordinate is not None else preferred_map.get((mode, False), self.settings.amap_mcp_tool_route_plan)
        if preferred in available:
            return preferred

        fallback_keywords = {
            "driving": ["driving", "direction"],
            "transit": ["transit", "integrated", "direction"],
            "walking": ["walking", "direction"],
            "bicycling": ["bicycling", "cycling", "direction"],
        }.get(mode, ["direction"])
        location_keywords = ["coordinate", "coordinates"] if coordinate is True else ["address"] if coordinate is False else []

        best_name = ""
        best_score = -1
        for item in catalog:
            name = str(item.get("name", ""))
            description = str(item.get("description", ""))
            text = f"{name} {description}".lower()
            score = sum(1 for keyword in fallback_keywords if keyword in text)
            if location_keywords and not any(keyword in text for keyword in location_keywords):
                score -= 1
            if score > best_score:
                best_score = score
                best_name = name

        if best_name and best_score > 0:
            return best_name

        return self._resolve_tool_name("route_plan", strict=False)

    def _route_mode_candidates(self, preferred_mode: str) -> list[str]:
        candidates = {
            "transit": ["transit", "walking", "driving"],
            "walking": ["walking", "transit", "driving"],
            "bicycling": ["bicycling", "walking", "driving"],
            "driving": ["driving", "walking"],
        }.get(preferred_mode, [preferred_mode, "walking", "driving"])
        seen: set[str] = set()
        ordered: list[str] = []
        for mode in candidates:
            if mode in seen:
                continue
            seen.add(mode)
            ordered.append(mode)
        return ordered

    async def _search_poi_candidates(
        self,
        city: str,
        queries: list[str],
        trace: list[ToolCallRecord],
        fallback_kind: str,
        target_count: int,
    ) -> list[POIRecommendation]:
        pois: list[POIRecommendation] = []
        deduped_queries = self._dedupe_queries(queries)
        for citylimit in ("true", "false"):
            for query in deduped_queries:
                raw = await self._call_tool_for_purpose(
                    "poi_search",
                    self._build_poi_search_arguments(city, query, citylimit=citylimit),
                    trace,
                )
                pois.extend(self._normalize_pois(raw, fallback_kind=fallback_kind))
                merged = self._merge_unique_pois(pois)
                if len(merged) >= target_count:
                    return merged
            if pois:
                return self._merge_unique_pois(pois)
        return self._merge_unique_pois(pois)

    def _build_poi_search_arguments(self, city: str, keywords: str, citylimit: str = "true") -> dict[str, Any]:
        return {
            "keywords": keywords,
            "city": city,
            "citylimit": citylimit,
        }

    def _dedupe_queries(self, queries: list[str]) -> list[str]:
        seen: set[str] = set()
        cleaned: list[str] = []
        for query in queries:
            normalized = query.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            cleaned.append(normalized)
        return cleaned

    def _build_route_arguments(
        self,
        origin: POIRecommendation,
        destination: POIRecommendation,
    ) -> dict[str, Any]:
        return {
            "origin_address": self._route_address(origin),
            "destination_address": self._route_address(destination),
            "origin_city": self._normalize_city_name(origin.district),
            "destination_city": self._normalize_city_name(destination.district),
        }

    def _build_route_coordinate_arguments(
        self,
        origin: POIRecommendation,
        destination: POIRecommendation,
    ) -> dict[str, Any]:
        return {
            "origin": f"{origin.longitude},{origin.latitude}",
            "destination": f"{destination.longitude},{destination.latitude}",
        }

    def _has_coordinates(self, poi: POIRecommendation) -> bool:
        return poi.longitude is not None and poi.latitude is not None

    def _normalize_city_name(self, value: str | None) -> str:
        if not value:
            return ""
        normalized = value.strip()
        for suffix in ("市", "区", "县"):
            if normalized.endswith(suffix) and len(normalized) > 1:
                normalized = normalized[:-1]
                break
        return normalized

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

    def _raise_on_tool_error(self, payload: Any, tool_name: str) -> None:
        if not isinstance(payload, dict):
            return
        error = payload.get("error")
        if error:
            raise MCPProtocolError(f"{tool_name} 返回错误: {error}")
        if payload.get("isError"):
            raise MCPProtocolError(f"{tool_name} 调用被标记为 isError")

    def _summarize_tool_payload(self, payload: Any) -> str:
        if isinstance(payload, dict):
            for key in ("pois", "results", "forecasts", "casts", "return"):
                value = payload.get(key)
                if isinstance(value, list):
                    return f"(返回 {len(value)} 项)"
            keys = ", ".join(list(payload.keys())[:4])
            return f"(keys: {keys})" if keys else ""
        if isinstance(payload, list):
            return f"(返回 {len(payload)} 项)"
        return ""

    def _normalize_pois(self, raw: Any, fallback_kind: str) -> list[POIRecommendation]:
        data = self._extract_poi_items(raw)
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

    def _normalize_poi_detail(self, raw: Any, fallback: POIRecommendation) -> POIRecommendation:
        detail = self._extract_poi_detail_record(raw)
        if not isinstance(detail, dict):
            return fallback

        longitude, latitude = self._extract_coordinates(detail)
        merged_tags = fallback.tags or self._normalize_tags(detail)
        return POIRecommendation(
            name=str(detail.get("name", fallback.name)),
            poi_id=str(detail.get("id", fallback.poi_id or "")) or None,
            address=str(detail.get("address", fallback.address)),
            tags=merged_tags,
            rating=self._to_float(detail.get("rating", fallback.rating)),
            recommended_duration_minutes=fallback.recommended_duration_minutes,
            opening_hours=str(detail.get("opening_hours", detail.get("business_hours", fallback.opening_hours or ""))) or fallback.opening_hours,
            district=str(detail.get("district", detail.get("adname", detail.get("city", fallback.district or "")))) or fallback.district,
            longitude=longitude if longitude is not None else fallback.longitude,
            latitude=latitude if latitude is not None else fallback.latitude,
            source=fallback.source,
        )

    def _extract_poi_items(self, raw: Any) -> list[dict[str, Any]]:
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
            nested_items = self._extract_poi_items(data)
            if nested_items:
                return nested_items

        if any(key in raw for key in ("name", "id", "address", "location")):
            return [raw]

        return []

    def _extract_poi_detail_record(self, raw: Any) -> dict[str, Any] | None:
        items = self._extract_poi_items(raw)
        if items:
            return items[0]
        return raw if isinstance(raw, dict) else None

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
        route_root = raw.get("route") if isinstance(raw, dict) and isinstance(raw.get("route"), dict) else None
        route_data = raw
        if route_root is not None:
            route_data = route_root
        if isinstance(route_data, dict) and isinstance(route_data.get("paths"), list) and route_data["paths"]:
            route_data = route_data["paths"][0]
        elif isinstance(route_data, dict) and isinstance(route_data.get("transits"), list) and route_data["transits"]:
            route_data = route_data["transits"][0]

        distance_text = ""
        duration_text = ""
        steps: list[RouteStep] = []
        polyline: list[GeoPoint] = []

        if isinstance(route_data, dict):
            distance_text = str(route_data.get("distance_text", route_data.get("distance", "")))
            duration_text = str(route_data.get("duration_text", route_data.get("duration", "")))
            if route_root is not None:
                if not distance_text:
                    distance_text = str(route_root.get("distance", route_root.get("walking_distance", "")))
                if not duration_text:
                    duration_text = str(route_root.get("duration", ""))
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
                    tmcs = item.get("tmcs")
                    if isinstance(tmcs, list):
                        for tmc in tmcs:
                            if isinstance(tmc, dict):
                                polyline.extend(self._extract_polyline_points(tmc.get("polyline")))

            if not polyline:
                polyline.extend(self._extract_polyline_points(route_data.get("polyline")))

            raw_segments = route_data.get("segments", [])
            if isinstance(raw_segments, list) and raw_segments:
                for segment in raw_segments:
                    if not isinstance(segment, dict):
                        continue
                    walking = segment.get("walking")
                    if isinstance(walking, dict):
                        for step in walking.get("steps", []) if isinstance(walking.get("steps"), list) else []:
                            if not isinstance(step, dict):
                                continue
                            steps.append(
                                RouteStep(
                                    instruction=str(step.get("instruction", "步行前往下一站")),
                                    distance_text=str(step.get("distance", "")),
                                    duration_text=str(step.get("duration", "")),
                                )
                            )
                    bus = segment.get("bus")
                    if isinstance(bus, dict):
                        buslines = bus.get("buslines", [])
                        if isinstance(buslines, list):
                            for busline in buslines[:2]:
                                if not isinstance(busline, dict):
                                    continue
                                instruction = f"乘坐 {busline.get('name', '公共交通')}"
                                dep = busline.get("departure_stop")
                                arr = busline.get("arrival_stop")
                                if isinstance(dep, dict) and dep.get("name"):
                                    instruction += f"，从 {dep['name']} 上车"
                                if isinstance(arr, dict) and arr.get("name"):
                                    instruction += f"，到 {arr['name']} 下车"
                                steps.append(
                                    RouteStep(
                                        instruction=instruction,
                                        distance_text=str(busline.get("distance", "")),
                                        duration_text=str(busline.get("duration", "")),
                                    )
                                )

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
            distance_text=self._format_distance_text(distance_text) or "待工具返回",
            duration_text=self._format_duration_text(duration_text) or "待工具返回",
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

    def _sort_pois_by_city_center(self, city: str, pois: list[POIRecommendation]) -> list[POIRecommendation]:
        center = self._city_center(city)
        return sorted(
            pois,
            key=lambda poi: self._distance_score(poi, center),
        )

    def _distance_score(self, poi: POIRecommendation, center: GeoPoint) -> float:
        if poi.longitude is None or poi.latitude is None:
            return float("inf")
        return (poi.longitude - center.longitude) ** 2 + (poi.latitude - center.latitude) ** 2

    def _normalize_tags(self, item: dict[str, Any]) -> list[str]:
        tags = item.get("tags", item.get("tag", item.get("type", item.get("typecode", []))))
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

    def _build_hotel_queries(
        self,
        request: TripPlanningRequest,
        anchor_pois: list[POIRecommendation],
    ) -> list[str]:
        queries: list[str] = []
        for poi in anchor_pois[:4]:
            if poi.name:
                queries.append(f"{poi.name} 附近 {request.hotel_style}")
                queries.append(f"{poi.name} 附近 酒店")
            if poi.district:
                queries.append(f"{poi.district} {request.hotel_style}")
        queries.extend([request.hotel_style, f"{request.destination} {request.hotel_style}", "酒店", "舒适型酒店"])
        return self._dedupe_queries(queries)

    def _sort_hotels_for_stay(
        self,
        hotels: list[POIRecommendation],
        anchor_pois: list[POIRecommendation],
        city: str,
    ) -> list[POIRecommendation]:
        if anchor_pois:
            center = self._anchor_center(anchor_pois)
            return sorted(hotels, key=lambda poi: self._distance_score(poi, center))
        return self._sort_pois_by_city_center(city, hotels)

    def _anchor_center(self, pois: list[POIRecommendation]) -> GeoPoint:
        coordinates = [(poi.longitude, poi.latitude) for poi in pois if poi.longitude is not None and poi.latitude is not None]
        if not coordinates:
            return self._city_center("")
        longitude = sum(item[0] for item in coordinates) / len(coordinates)
        latitude = sum(item[1] for item in coordinates) / len(coordinates)
        return GeoPoint(longitude=longitude, latitude=latitude)

    def _route_address_candidates(self, poi: POIRecommendation) -> list[str]:
        candidates = [
            " ".join(part for part in [poi.district or "", poi.address or "", poi.name] if part).strip(),
            " ".join(part for part in [poi.district or "", poi.name] if part).strip(),
            " ".join(part for part in [poi.district or "", poi.address or ""] if part).strip(),
            poi.address.strip(),
            poi.name.strip(),
        ]
        return [candidate for candidate in self._dedupe_queries(candidates) if candidate]

    def _fallback_route(
        self,
        day_number: int,
        origin: POIRecommendation,
        destination: POIRecommendation,
        waypoints: list[POIRecommendation],
        mode: str,
    ) -> RouteSummary:
        polyline = self._fallback_polyline(origin, destination, waypoints)
        total_km = self._polyline_distance_km(polyline) if len(polyline) > 1 else 8.0
        speed_kmh = {
            "walking": 4.5,
            "bicycling": 12.0,
            "transit": 20.0,
            "driving": 28.0,
        }.get(mode, 20.0)
        duration_minutes = max(10, round(total_km / max(speed_kmh, 1.0) * 60))
        step_target = waypoints[0].name if waypoints else destination.name
        return RouteSummary(
            day_number=day_number,
            title=f"第 {day_number} 天路线",
            from_name=origin.name,
            to_name=destination.name,
            waypoints=[item.name for item in waypoints],
            distance_text=f"{total_km:.1f}公里",
            duration_text=f"约 {duration_minutes} 分钟",
            mode=mode,
            steps=[
                RouteStep(instruction=f"从 {origin.name} 出发，前往 {step_target}", distance_text="", duration_text=""),
                RouteStep(instruction=f"随后继续前往 {destination.name}", distance_text="", duration_text=""),
            ],
            polyline=polyline,
        )

    def _polyline_distance_km(self, polyline: list[GeoPoint]) -> float:
        if len(polyline) < 2:
            return 0.0
        distance = 0.0
        for index in range(1, len(polyline)):
            prev = polyline[index - 1]
            curr = polyline[index]
            distance += self._haversine_km(prev.latitude, prev.longitude, curr.latitude, curr.longitude)
        return max(distance, 0.5)

    def _haversine_km(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        from math import asin, cos, radians, sin, sqrt

        d_lat = radians(lat2 - lat1)
        d_lon = radians(lon2 - lon1)
        a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
        return 6371.0 * 2 * asin(sqrt(a))
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

    def _format_distance_text(self, value: str) -> str:
        raw = value.strip()
        if not raw:
            return ""
        meters = self._to_int(raw)
        if meters is None:
            return raw
        if meters >= 1000:
            return f"{meters / 1000:.1f}公里"
        return f"{meters}米"

    def _format_duration_text(self, value: str) -> str:
        raw = value.strip()
        if not raw:
            return ""
        seconds = self._to_int(raw)
        if seconds is None:
            return raw
        if seconds >= 3600:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}小时{minutes}分钟" if minutes else f"{hours}小时"
        minutes = max(1, round(seconds / 60))
        return f"{minutes}分钟"







