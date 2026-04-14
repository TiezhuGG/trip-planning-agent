from __future__ import annotations

import asyncio
from typing import Any

from app.config import Settings
from app.services.ai_client_domain_adapter import TravelAIClientDomainMixin
from app.services.ai_client_generation import TravelAIClientGenerationMixin
from app.services.ai_client_models import LLMDiagnosisResult
from app.services.ai_client_plan_adapter import TravelAIClientPlanAdapterMixin
from app.services.ai_client_runtime import normalize_base_url
from app.services.ai_client_runtime_adapter import TravelAIClientRuntimeMixin

try:
    from openai import AsyncOpenAI
except Exception:
    AsyncOpenAI = None  # type: ignore


class TravelAIClient(
    TravelAIClientDomainMixin,
    TravelAIClientGenerationMixin,
    TravelAIClientPlanAdapterMixin,
    TravelAIClientRuntimeMixin,
):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = None
        self.primary_model = settings.openai_model
        self.base_url = normalize_base_url(settings.openai_base_url)
        self.secondary_client = None
        self.secondary_model = settings.openai_backup_model
        self.secondary_base_url = normalize_base_url(settings.openai_backup_base_url)
        self._preferred_json_mode_by_model: dict[str, str] = {}
        self._unsupported_json_modes_by_model: dict[str, set[str]] = {}
        self._diagnose_cache_ttl_seconds = max(0.0, float(settings.openai_diagnose_cache_seconds))
        self._diagnose_cached_at: float = 0.0
        self._diagnose_cached_result: LLMDiagnosisResult | None = None
        self._diagnose_lock = asyncio.Lock()
        self._adaptive_retry_stats: dict[str, dict[str, Any]] = {}
        self._adaptive_retry_lock = asyncio.Lock()
        if settings.has_openai and AsyncOpenAI is not None:
            self.client = self._create_client(
                api_key=settings.openai_api_key,
                base_url=self.base_url,
            )
        if settings.has_backup_openai and AsyncOpenAI is not None:
            self.secondary_client = self._create_client(
                api_key=settings.openai_backup_api_key,
                base_url=self.secondary_base_url,
            )
