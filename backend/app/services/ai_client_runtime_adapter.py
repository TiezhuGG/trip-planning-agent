from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from app.services.ai_client_diagnose import (
    build_diagnosis_result as build_diagnosis_result_runtime,
    read_cached_diagnosis as read_cached_diagnosis_runtime,
)
from app.services.ai_client_models import LLMDiagnosisResult, LLMProvider, copy_llm_diagnosis
from app.services.ai_client_request import request_json_payload as request_json_payload_runtime
from app.services.ai_client_runtime import (
    extract_message_content,
    format_exception,
    is_terminal_request_error,
    is_unsupported_json_mode_error,
    mark_json_mode_unsupported,
    record_adaptive_retry_result,
    request_mode_order,
    retry_backoff_seconds,
    seed_retry_specs,
    trim_adaptive_retry_specs,
)

try:
    from openai import AsyncOpenAI
except Exception:
    AsyncOpenAI = None  # type: ignore


class TravelAIClientRuntimeMixin:
    def _create_client(self, api_key: str, base_url: str) -> Any:
        timeout = httpx.Timeout(
            self.settings.openai_timeout_seconds,
            connect=min(15, self.settings.openai_timeout_seconds),
        )
        kwargs: dict[str, Any] = {
            "api_key": api_key,
            "max_retries": self.settings.openai_max_retries,
            "http_client": httpx.AsyncClient(
                timeout=timeout,
                trust_env=self.settings.openai_trust_env,
            ),
        }
        if base_url:
            kwargs["base_url"] = base_url
        return AsyncOpenAI(**kwargs)

    def _configured_providers(self) -> list[LLMProvider]:
        providers: list[LLMProvider] = []
        if self.client is not None:
            providers.append(
                LLMProvider(
                    label="主模型",
                    client=self.client,
                    model=self.primary_model or self.settings.openai_model or "primary-model",
                    base_url=self.base_url,
                )
            )
        if self.secondary_client is not None:
            providers.append(
                LLMProvider(
                    label="备用模型",
                    client=self.secondary_client,
                    model=self.secondary_model or self.settings.openai_backup_model or "backup-model",
                    base_url=self.secondary_base_url,
                )
            )
        return providers

    def _default_model_name(self) -> str:
        for provider in self._configured_providers():
            if provider.model:
                return provider.model
        return (
            self.primary_model
            or self.secondary_model
            or self.settings.openai_model
            or self.settings.openai_backup_model
        )

    async def diagnose(self, check_connection: bool = True) -> LLMDiagnosisResult:
        if check_connection and self._diagnose_cache_ttl_seconds > 0:
            now = time.monotonic()
            cached = read_cached_diagnosis_runtime(
                check_connection=check_connection,
                cache_ttl_seconds=self._diagnose_cache_ttl_seconds,
                cached_result=self._diagnose_cached_result,
                cached_at=self._diagnose_cached_at,
                now=now,
            )
            if cached is not None:
                return cached
            async with self._diagnose_lock:
                now = time.monotonic()
                cached = read_cached_diagnosis_runtime(
                    check_connection=check_connection,
                    cache_ttl_seconds=self._diagnose_cache_ttl_seconds,
                    cached_result=self._diagnose_cached_result,
                    cached_at=self._diagnose_cached_at,
                    now=now,
                )
                if cached is not None:
                    return cached
                result = await self._diagnose_impl(check_connection=check_connection)
                self._diagnose_cached_result = copy_llm_diagnosis(result)
                self._diagnose_cached_at = now
                return result
        return await self._diagnose_impl(check_connection=check_connection)

    async def _diagnose_impl(self, check_connection: bool = True) -> LLMDiagnosisResult:
        return await build_diagnosis_result_runtime(
            settings=self.settings,
            providers=self._configured_providers(),
            check_connection=check_connection,
            default_model_name_fn=self._default_model_name,
            request_json_payload_fn=self._request_json_payload,
            should_switch_to_backup_model_fn=self._should_switch_to_backup_model,
            primary_base_url=self.base_url,
            secondary_base_url=self.secondary_base_url,
        )

    def _is_retryable_compose_error(self, exc: Exception) -> bool:
        if self._should_fallback_to_template(exc):
            return False
        message = str(exc).lower()
        retryable_keywords = (
            "天数不匹配",
            "day_number",
            "validation error",
            "field required",
            "missing",
            "venue_name",
            "不可解析",
            "timed out",
            "timeout",
            "readtimeout",
            "apitimeouterror",
            "json_object",
            "plain_text_json",
            "minimal",
        )
        return isinstance(exc, (ValueError, RuntimeError, httpx.TimeoutException)) and any(
            keyword in message for keyword in retryable_keywords
        )

    def _is_retryable_seed_error(self, exc: Exception) -> bool:
        if self._should_fallback_to_template(exc):
            return False
        message = str(exc).lower()
        retryable_keywords = (
            "timed out",
            "timeout",
            "readtimeout",
            "apitimeouterror",
            "json_object",
            "plain_text_json",
            "不可解析",
            "error code: 400",
            "output data may contain inappropriate content",
            "service unavailable",
            "rate limit",
            "temporarily",
        )
        return isinstance(exc, (ValueError, RuntimeError, httpx.TimeoutException)) and any(
            keyword in message for keyword in retryable_keywords
        )

    def _should_switch_to_backup_model(self, exc: Exception) -> bool:
        if self._should_fallback_to_template(exc):
            return True
        message = str(exc).lower()
        switch_keywords = (
            "apiconnectionerror",
            "connection error",
            "connecterror",
            "service unavailable",
            "temporarily unavailable",
            "server error",
            "internal server error",
            "bad gateway",
            "gateway timeout",
            "overloaded",
            "dns",
            "name or service not known",
            "connection refused",
            "ssl",
        )
        return isinstance(exc, (ValueError, RuntimeError, httpx.NetworkError)) and any(
            keyword in message for keyword in switch_keywords
        )

    def _should_fallback_to_template(self, exc: Exception) -> bool:
        message = str(exc).lower()
        fallback_keywords = (
            "error code: 429",
            "429 too many requests",
            "too many requests",
            "ratelimiterror",
            "rate limit",
            "setlimitexceeded",
            "service has been paused",
            "insufficient_quota",
        )
        return any(keyword in message for keyword in fallback_keywords)

    async def _request_json_payload(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        temperature: float,
        max_tokens: int | None = None,
        client: Any | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        if client is None:
            client = self.client
        if model is None:
            model = self.primary_model or self.settings.openai_model
        assert client is not None

        errors: list[str] = []
        mode_order = request_mode_order(
            model,
            self._preferred_json_mode_by_model,
            self._unsupported_json_modes_by_model,
        )
        return await request_json_payload_runtime(
            system_prompt=system_prompt,
            user_payload=user_payload,
            temperature=temperature,
            max_tokens=max_tokens,
            client=client,
            model=model,
            errors=errors,
            mode_order=mode_order,
            extract_message_content_fn=extract_message_content,
            format_exception_fn=format_exception,
            is_unsupported_json_mode_error_fn=is_unsupported_json_mode_error,
            mark_json_mode_unsupported_fn=lambda current_model, mode: mark_json_mode_unsupported(
                current_model,
                mode,
                self._preferred_json_mode_by_model,
                self._unsupported_json_modes_by_model,
            ),
            is_terminal_request_error_fn=lambda exc: is_terminal_request_error(
                exc,
                self._should_fallback_to_template,
            ),
            set_preferred_json_mode_fn=lambda current_model, mode: self._preferred_json_mode_by_model.__setitem__(
                str(current_model),
                mode,
            ),
        )

    def _retry_backoff_seconds(self, attempt: int) -> float:
        return retry_backoff_seconds(self.settings.openai_fast_mode, attempt)

    async def _adaptive_retry_specs(
        self,
        channel: str,
        retry_specs: list[tuple[float, int]],
    ) -> list[tuple[float, int]]:
        specs = list(retry_specs)
        if not self.settings.openai_adaptive_retry_enabled:
            return specs

        window = max(1, int(self.settings.openai_adaptive_retry_window))
        min_samples = max(1, int(self.settings.openai_adaptive_retry_min_samples))
        low_success_rate = float(self.settings.openai_adaptive_retry_low_success_rate)
        async with self._adaptive_retry_lock:
            return trim_adaptive_retry_specs(
                retry_specs=specs,
                adaptive_retry_stats=self._adaptive_retry_stats,
                channel=channel,
                window=window,
                min_samples=min_samples,
                low_success_rate=low_success_rate,
            )

    async def _record_adaptive_retry_result(self, channel: str, success: bool) -> None:
        if not self.settings.openai_adaptive_retry_enabled:
            return
        window = max(1, int(self.settings.openai_adaptive_retry_window))
        async with self._adaptive_retry_lock:
            record_adaptive_retry_result(
                adaptive_retry_stats=self._adaptive_retry_stats,
                channel=channel,
                success=success,
                window=window,
            )

    async def _build_initial_plan_with_provider(
        self,
        request,
        provider: LLMProvider,
    ):
        warnings: list[str] = []
        channel = f"seed::{provider.model}"
        retry_specs = await self._adaptive_retry_specs(
            channel=channel,
            retry_specs=seed_retry_specs(self.settings.openai_fast_mode),
        )
        last_error: Exception | None = None
        for attempt, (temperature, max_tokens) in enumerate(retry_specs, start=1):
            try:
                draft = await self._generate_initial_plan_with_openai(
                    request,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    client=provider.client,
                    model=provider.model,
                )
                await self._record_adaptive_retry_result(channel, success=True)
                if provider.label != "主模型" and self.client is not None:
                    warnings.append(f"已切换到备用模型 {provider.model} 继续生成初步规划。")
                return draft, warnings
            except Exception as exc:
                last_error = exc
                if self._should_switch_to_backup_model(exc):
                    await self._record_adaptive_retry_result(channel, success=False)
                    raise
                if not self._is_retryable_seed_error(exc) or attempt >= len(retry_specs):
                    await self._record_adaptive_retry_result(channel, success=False)
                    break
                warnings.append(f"seed 第 {attempt} 次失败，已重试。原因: {format_exception(exc)}")
                await asyncio.sleep(self._retry_backoff_seconds(attempt))

        assert last_error is not None
        raise last_error

    async def _compose_with_provider(
        self,
        request,
        initial_plan,
        context,
        tool_trace,
        provider: LLMProvider,
    ):
        plan, warnings = await self._compose_with_openai(
            request=request,
            initial_plan=initial_plan,
            context=context,
            tool_trace=tool_trace,
            client=provider.client,
            model=provider.model,
        )
        if provider.label != "主模型" and self.client is not None:
            warnings = [f"已切换到备用模型 {provider.model} 继续生成最终行程。"] + warnings
        return plan, warnings
