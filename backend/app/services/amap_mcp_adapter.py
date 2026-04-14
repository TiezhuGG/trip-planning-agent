from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx

from app.config import Settings
from app.schemas.planning import (
    IntegrationStatus,
    POIRecommendation,
)
from app.services.amap_mcp_adapter_discovery_api import AmapMCPAdapterDiscoveryApiMixin
from app.services.amap_mcp_adapter_helpers import AmapMCPAdapterHelpersMixin
from app.services.amap_mcp_adapter_route_api import AmapMCPAdapterRouteApiMixin
from app.services.amap_mcp_adapter_route_helpers import AmapMCPAdapterRouteHelpersMixin
from app.services.amap_mcp_adapter_selection_helpers import (
    AmapMCPAdapterSelectionHelpersMixin,
)
from app.services.amap_mcp_adapter_runtime import AmapMCPAdapterRuntimeMixin
from app.services.amap_mcp_diagnose import (
    build_diagnose_status as build_diagnose_status_runtime,
    read_cached_diagnose_status as read_cached_diagnose_status_runtime,
)
from app.services.mcp_stdio_client import MCPProtocolError, MCPStdioClient


class AmapMCPAdapter(
    AmapMCPAdapterDiscoveryApiMixin,
    AmapMCPAdapterHelpersMixin,
    AmapMCPAdapterRouteApiMixin,
    AmapMCPAdapterSelectionHelpersMixin,
    AmapMCPAdapterRouteHelpersMixin,
    AmapMCPAdapterRuntimeMixin,
):
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
        self._tool_catalog_cached_at: float = 0.0
        self._tool_catalog_ttl_seconds = max(0.0, float(settings.amap_mcp_tool_catalog_cache_seconds))
        self._tool_catalog_lock = asyncio.Lock()
        self._resolved_tools: dict[str, str] = {}
        self._poi_detail_concurrency = 2
        self._poi_detail_limit = 4
        self._poi_detail_cache: dict[str, POIRecommendation] = {}
        self._location_candidate_cache: dict[str, POIRecommendation | None] = {}
        self._location_candidate_simple_cache: dict[str, POIRecommendation | None] = {}
        self._location_candidate_cache_limit = 512
        self._route_location_cache: dict[str, str] = {}
        self._route_location_cache_limit = 512
        self._route_retry_attempts = 3
        self._route_retry_base_delay_seconds = 0.6
        self._geocode_retry_attempts = 3
        self._poi_query_budget_floor = 8
        self._poi_query_budget_cap = 12
        self._poi_search_consecutive_empty_stop = 3
        self._tool_circuit_state: dict[str, dict[str, Any]] = {}
        self._tool_circuit_lock = asyncio.Lock()
        self._adaptive_retry_stats: dict[str, dict[str, Any]] = {}
        self._adaptive_retry_lock = asyncio.Lock()
        self._diagnose_cache_ttl_seconds = max(0.0, float(settings.amap_mcp_diagnose_cache_seconds))
        self._diagnose_cached_at: float = 0.0
        self._diagnose_cached_status: IntegrationStatus | None = None
        self._diagnose_lock = asyncio.Lock()

    @property
    def has_client(self) -> bool:
        return self.client is not None

    @asynccontextmanager
    async def request_scope(self):
        # Keep location candidate cache request-scoped to avoid stale cross-request reuse.
        self._location_candidate_cache.clear()
        self._location_candidate_simple_cache.clear()
        if self.client is None or not hasattr(self.client, "session_scope"):
            yield
            return
        async with self.client.session_scope():
            yield

    async def diagnose(self, force_refresh: bool = True) -> IntegrationStatus:
        now = time.monotonic()
        cached = read_cached_diagnose_status_runtime(
            force_refresh=force_refresh,
            cache_ttl_seconds=self._diagnose_cache_ttl_seconds,
            cached_status=self._diagnose_cached_status,
            cached_at=self._diagnose_cached_at,
            now=now,
        )
        if cached is not None:
            return cached

        async with self._diagnose_lock:
            now = time.monotonic()
            cached = read_cached_diagnose_status_runtime(
                force_refresh=force_refresh,
                cache_ttl_seconds=self._diagnose_cache_ttl_seconds,
                cached_status=self._diagnose_cached_status,
                cached_at=self._diagnose_cached_at,
                now=now,
            )
            if cached is not None:
                return cached

            status = await build_diagnose_status_runtime(
                settings=self.settings,
                has_client=self.client is not None,
                force_refresh=force_refresh,
                ensure_tool_catalog_fn=self._ensure_tool_catalog,
                resolve_tool_name_fn=self._resolve_tool_name,
                format_connection_error_fn=self._format_connection_error,
                tool_circuit_warning_messages_fn=self._tool_circuit_warning_messages,
            )
            if self._diagnose_cache_ttl_seconds > 0:
                self._diagnose_cached_status = status.model_copy(deep=True)
                self._diagnose_cached_at = now
            return status







