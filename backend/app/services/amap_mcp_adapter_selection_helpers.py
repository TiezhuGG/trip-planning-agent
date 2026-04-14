from __future__ import annotations

from app.schemas.planning import GeoPoint, POIRecommendation, TripPlanningRequest
from app.services.amap_mcp_selection import (
    anchor_center as anchor_center_selection,
    build_hotel_queries as build_hotel_queries_selection,
    cache_limited_mapping as cache_limited_mapping_selection,
    distance_score as distance_score_selection,
    filter_pois_by_geo_scope as filter_pois_by_geo_scope_selection,
    geo_distance_km as geo_distance_km_selection,
    is_simple_cached_candidate_usable as is_simple_cached_candidate_usable_selection,
    location_candidate_cache_key as location_candidate_cache_key_selection,
    location_candidate_simple_cache_key as location_candidate_simple_cache_key_selection,
    location_hint_tokens as location_hint_tokens_selection,
    location_name_match_score as location_name_match_score_selection,
    normalize_location_token as normalize_location_token_selection,
    poi_matches_location_tokens as poi_matches_location_tokens_selection,
    poi_within_scope as poi_within_scope_selection,
    sort_hotels_for_stay as sort_hotels_for_stay_selection,
    sort_pois_by_city_center as sort_pois_by_city_center_selection,
    sort_restaurants_for_route as sort_restaurants_for_route_selection,
)


class AmapMCPAdapterSelectionHelpersMixin:
    def _is_simple_cached_candidate_usable(
        self,
        city: str,
        candidate: POIRecommendation,
        anchors: list[POIRecommendation],
    ) -> bool:
        return is_simple_cached_candidate_usable_selection(
            city=city,
            candidate=candidate,
            anchors=anchors,
            city_center=self._city_center,
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

    def _sort_pois_by_city_center(
        self,
        city: str,
        pois: list[POIRecommendation],
    ) -> list[POIRecommendation]:
        return sort_pois_by_city_center_selection(
            city,
            pois,
            city_center=self._city_center,
        )

    def _filter_pois_by_geo_scope(
        self,
        city: str,
        pois: list[POIRecommendation],
        radius_km: float,
        anchor_pois: list[POIRecommendation] | None = None,
    ) -> list[POIRecommendation]:
        return filter_pois_by_geo_scope_selection(
            city=city,
            pois=pois,
            radius_km=radius_km,
            anchor_pois=anchor_pois,
            merge_unique_pois=self._merge_unique_pois,
            sort_pois_by_city_center=self._sort_pois_by_city_center,
            city_center=self._city_center,
        )

    def _distance_score(self, poi: POIRecommendation, center: GeoPoint) -> float:
        return distance_score_selection(poi, center)

    def _poi_within_scope(
        self,
        poi: POIRecommendation,
        center: GeoPoint,
        radius_km: float,
    ) -> bool:
        return poi_within_scope_selection(poi, center, radius_km)

    def _location_hint_tokens(
        self,
        city: str,
        anchor_pois: list[POIRecommendation],
    ) -> set[str]:
        return location_hint_tokens_selection(city, anchor_pois)

    def _poi_matches_location_tokens(
        self,
        poi: POIRecommendation,
        tokens: set[str],
    ) -> bool:
        return poi_matches_location_tokens_selection(poi, tokens)

    def _normalize_location_token(self, value: str) -> str:
        return normalize_location_token_selection(value)

    def _geo_distance_km(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        return geo_distance_km_selection(lat1, lon1, lat2, lon2)

    def _location_name_match_score(
        self,
        query: str,
        poi: POIRecommendation,
    ) -> tuple[int, int, float]:
        return location_name_match_score_selection(
            query,
            poi,
            normalize_city_name=self._normalize_city_name,
            city_center=self._city_center,
        )

    def _location_candidate_cache_key(
        self,
        city: str,
        query: str,
        anchor_pois: list[POIRecommendation],
    ) -> str:
        return location_candidate_cache_key_selection(
            city,
            query,
            anchor_pois,
            normalize_city_name=self._normalize_city_name,
        )

    def _location_candidate_simple_cache_key(
        self,
        city: str,
        query: str,
    ) -> str:
        return location_candidate_simple_cache_key_selection(
            city,
            query,
            normalize_city_name=self._normalize_city_name,
        )

    def _cache_location_candidate(
        self,
        key: str,
        poi: POIRecommendation | None,
    ) -> None:
        cache_limited_mapping_selection(
            self._location_candidate_cache,
            key=key,
            value=poi,
            limit=self._location_candidate_cache_limit,
        )

    def _cache_location_candidate_simple(
        self,
        key: str,
        poi: POIRecommendation | None,
    ) -> None:
        cache_limited_mapping_selection(
            self._location_candidate_simple_cache,
            key=key,
            value=poi,
            limit=self._location_candidate_cache_limit,
        )

    def _build_hotel_queries(
        self,
        request: TripPlanningRequest,
        anchor_pois: list[POIRecommendation],
    ) -> list[str]:
        return build_hotel_queries_selection(
            request,
            anchor_pois,
            dedupe_queries=self._dedupe_queries,
        )

    def _sort_hotels_for_stay(
        self,
        hotels: list[POIRecommendation],
        anchor_pois: list[POIRecommendation],
        city: str,
    ) -> list[POIRecommendation]:
        return sort_hotels_for_stay_selection(
            hotels=hotels,
            anchor_pois=anchor_pois,
            city=city,
            city_center=self._city_center,
            has_coordinates=self._has_coordinates,
        )

    def _sort_restaurants_for_route(
        self,
        restaurants: list[POIRecommendation],
        city: str,
        anchor_pois: list[POIRecommendation],
    ) -> list[POIRecommendation]:
        return sort_restaurants_for_route_selection(
            restaurants=restaurants,
            city=city,
            anchor_pois=anchor_pois,
            city_center=self._city_center,
            has_coordinates=self._has_coordinates,
        )

    def _anchor_center(self, pois: list[POIRecommendation]) -> GeoPoint:
        return anchor_center_selection(pois, city_center=self._city_center)
