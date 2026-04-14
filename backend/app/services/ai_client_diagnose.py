from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.config import Settings
from app.services.ai_client_models import LLMDiagnosisResult, LLMProvider, copy_llm_diagnosis

RequestJsonPayload = Callable[..., Awaitable[dict[str, Any]]]
ShouldSwitchToBackupModel = Callable[[Exception], bool]
DefaultModelName = Callable[[], str]


def read_cached_diagnosis(
    *,
    check_connection: bool,
    cache_ttl_seconds: float,
    cached_result: LLMDiagnosisResult | None,
    cached_at: float,
    now: float,
) -> LLMDiagnosisResult | None:
    if check_connection and cache_ttl_seconds > 0:
        if cached_result is not None and (now - cached_at) <= cache_ttl_seconds:
            return copy_llm_diagnosis(cached_result)
    return None


async def build_diagnosis_result(
    *,
    settings: Settings,
    providers: list[LLMProvider],
    check_connection: bool,
    default_model_name_fn: DefaultModelName,
    request_json_payload_fn: RequestJsonPayload,
    should_switch_to_backup_model_fn: ShouldSwitchToBackupModel,
    primary_base_url: str,
    secondary_base_url: str,
) -> LLMDiagnosisResult:
    if not providers and not settings.has_any_openai:
        return LLMDiagnosisResult(
            enabled=False,
            reachable=False,
            model=default_model_name_fn(),
            base_url=primary_base_url or secondary_base_url,
            warnings=["未配置大模型 API Key 或模型名。"],
        )

    if not providers:
        return LLMDiagnosisResult(
            enabled=True,
            reachable=False,
            model=default_model_name_fn(),
            base_url=primary_base_url or secondary_base_url,
            warnings=["OpenAI Python SDK 不可用，请检查依赖安装。"],
        )

    if not check_connection:
        return LLMDiagnosisResult(
            enabled=True,
            reachable=False,
            model=default_model_name_fn(),
            base_url=(providers[0].base_url if providers else ""),
            warnings=[],
        )

    warnings: list[str] = []
    for index, provider in enumerate(providers):
        try:
            payload = await request_json_payload_fn(
                system_prompt="你是联调探针。请只返回 JSON。",
                user_payload={"task": "ping", "response_schema_hint": {"status": "ok"}},
                temperature=0,
                max_tokens=32,
                client=provider.client,
                model=provider.model,
            )
            if str(payload.get("status", "")).lower() != "ok":
                raise ValueError("模型未按约定返回诊断 JSON")
            if index > 0:
                warnings.append(f"主模型不可用，当前诊断已切换到备用模型 {provider.model}。")
            return LLMDiagnosisResult(
                enabled=True,
                reachable=True,
                model=provider.model,
                base_url=provider.base_url,
                warnings=warnings,
            )
        except Exception as exc:
            warnings.append(f"{provider.label}连通性检查失败: {exc}")
            if index < len(providers) - 1 and should_switch_to_backup_model_fn(exc):
                continue

    return LLMDiagnosisResult(
        enabled=True,
        reachable=False,
        model=default_model_name_fn(),
        base_url=(providers[0].base_url if providers else ""),
        warnings=warnings,
    )
