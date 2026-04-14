from __future__ import annotations

from typing import Any

from app.schemas.planning import GeoPoint, POIRecommendation, RouteSummary
from app.services.amap_mcp_route_runtime import (
    estimate_fallback_transport_cost as estimate_fallback_transport_cost_runtime,
    extract_transport_cost_cny as extract_transport_cost_cny_runtime,
    fallback_route as fallback_route_runtime,
    format_distance_text as format_distance_text_runtime,
    format_duration_text as format_duration_text_runtime,
    haversine_km as haversine_km_runtime,
    parse_cny_amount as parse_cny_amount_runtime,
    polyline_distance_km as polyline_distance_km_runtime,
    route_address_candidates as route_address_candidates_runtime,
)
from app.services.amap_mcp_selection import (
    cache_limited_mapping as cache_limited_mapping_selection,
    route_location_cache_key as route_location_cache_key_selection,
)
from app.services.amap_mcp_support import (
    city_center as city_center_runtime,
    fallback_polyline as fallback_polyline_runtime,
    route_address as route_address_runtime,
    to_float as to_float_runtime,
    to_int as to_int_runtime,
)


class AmapMCPAdapterRouteHelpersMixin:
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

    def _normalize_route(
        self,
        raw: Any,
        day_number: int,
        origin: POIRecommendation,
        destination: POIRecommendation,
        waypoints: list[POIRecommendation],
        mode: str,
    ) -> RouteSummary:
        return self._normalize_route_runtime(
            raw,
            day_number=day_number,
            origin=origin,
            destination=destination,
            waypoints=waypoints,
            mode=mode,
        )

    def _route_address(self, poi: POIRecommendation) -> str:
        return route_address_runtime(poi)

    def _route_location_cache_key(self, poi: POIRecommendation) -> str:
        return route_location_cache_key_selection(poi)

    def _cache_route_location(self, key: str, location: str) -> None:
        cache_limited_mapping_selection(
            self._route_location_cache,
            key=key,
            value=location,
            limit=self._route_location_cache_limit,
        )

    def _route_address_candidates(self, poi: POIRecommendation) -> list[str]:
        return route_address_candidates_runtime(poi, dedupe_queries=self._dedupe_queries)

    def _fallback_route(
        self,
        day_number: int,
        origin: POIRecommendation,
        destination: POIRecommendation,
        waypoints: list[POIRecommendation],
        mode: str,
    ) -> RouteSummary:
        return fallback_route_runtime(
            day_number=day_number,
            origin=origin,
            destination=destination,
            waypoints=waypoints,
            mode=mode,
            fallback_polyline=self._fallback_polyline(origin, destination, waypoints),
        )

    def _extract_transport_cost_cny(
        self,
        route_root: dict[str, Any] | None,
        route_data: Any,
        mode: str,
    ) -> int:
        return extract_transport_cost_cny_runtime(
            route_root=route_root,
            route_data=route_data,
            mode=mode,
        )

    def _parse_cny_amount(self, value: Any) -> int | None:
        return parse_cny_amount_runtime(value)

    def _estimate_fallback_transport_cost(self, total_km: float, mode: str) -> int:
        return estimate_fallback_transport_cost_runtime(total_km, mode)

    def _polyline_distance_km(self, polyline: list[GeoPoint]) -> float:
        return polyline_distance_km_runtime(polyline)

    def _haversine_km(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        return haversine_km_runtime(lat1, lon1, lat2, lon2)

    def _city_center(self, city: str) -> GeoPoint:
        return city_center_runtime(city)

    def _to_float(self, value: Any) -> float | None:
        return to_float_runtime(value)

    def _to_int(self, value: Any) -> int | None:
        return to_int_runtime(value)

    def _extract_coordinates(self, item: dict[str, Any]) -> tuple[float | None, float | None]:
        return self._extract_coordinates_runtime(item)

    def _extract_polyline_points(self, raw_polyline: Any) -> list[GeoPoint]:
        return self._extract_polyline_points_runtime(raw_polyline)

    def _fallback_polyline(
        self,
        origin: POIRecommendation,
        destination: POIRecommendation,
        waypoints: list[POIRecommendation],
    ) -> list[GeoPoint]:
        return fallback_polyline_runtime(origin, destination, waypoints)

    def _format_distance_text(self, value: str) -> str:
        return format_distance_text_runtime(value, to_int=self._to_int)

    def _format_duration_text(self, value: str) -> str:
        return format_duration_text_runtime(value, to_int=self._to_int)
