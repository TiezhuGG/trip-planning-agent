from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from time import monotonic

from app.schemas.planning import PlanningResponse, TripPlanningRequest


@dataclass
class _GenerateCacheEntry:
    response: PlanningResponse
    expires_at: float


class TravelPlannerGenerateCacheMixin:
    def _init_generate_cache_state(self) -> None:
        self._generate_cache: OrderedDict[str, _GenerateCacheEntry] = OrderedDict()
        self._inflight_generations: dict[str, asyncio.Task[PlanningResponse]] = {}
        self._cache_lock = asyncio.Lock()

    def _generate_cache_enabled(self) -> bool:
        if not self.settings.planner_generate_cache_enabled:
            return False
        if self.settings.planner_generate_cache_ttl_seconds <= 0:
            return False
        if self.settings.planner_generate_cache_max_entries <= 0:
            return False
        return True

    def _request_cache_key(self, request: TripPlanningRequest, include_debug: bool) -> str:
        request_payload = request.model_dump_json(by_alias=True, exclude_none=False)
        return f"{int(include_debug)}::{request_payload}"

    async def _get_cached_response(self, cache_key: str) -> PlanningResponse | None:
        async with self._cache_lock:
            return self._get_cached_response_unlocked(cache_key)

    def _get_cached_response_unlocked(self, cache_key: str) -> PlanningResponse | None:
        self._evict_expired_unlocked()
        entry = self._generate_cache.get(cache_key)
        if entry is None:
            return None
        self._generate_cache.move_to_end(cache_key)
        return entry.response.model_copy(deep=True)

    async def _put_cached_response(self, cache_key: str, response: PlanningResponse) -> None:
        async with self._cache_lock:
            self._evict_expired_unlocked()
            self._generate_cache[cache_key] = _GenerateCacheEntry(
                response=response.model_copy(deep=True),
                expires_at=monotonic() + float(self.settings.planner_generate_cache_ttl_seconds),
            )
            self._generate_cache.move_to_end(cache_key)
            while len(self._generate_cache) > self.settings.planner_generate_cache_max_entries:
                self._generate_cache.popitem(last=False)

    def _evict_expired_unlocked(self) -> None:
        if not self._generate_cache:
            return
        now = monotonic()
        expired_keys = [
            key
            for key, entry in self._generate_cache.items()
            if entry.expires_at <= now
        ]
        for key in expired_keys:
            self._generate_cache.pop(key, None)

    def _should_cache_response(self, response: PlanningResponse) -> bool:
        # Do not cache degraded partial_success to avoid amplifying transient stage failures.
        return response.status in {"success", "fallback_success"}
