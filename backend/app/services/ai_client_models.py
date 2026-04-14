from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class InitialPlanBuildResult:
    draft: Any
    used_llm: bool
    fallback_used: bool
    warnings: list[str]


@dataclass
class FinalPlanBuildResult:
    plan: Any
    used_llm: bool
    fallback_used: bool
    warnings: list[str]


@dataclass
class LLMDiagnosisResult:
    enabled: bool
    reachable: bool
    model: str
    base_url: str
    warnings: list[str]


@dataclass(frozen=True)
class LLMProvider:
    label: str
    client: Any
    model: str
    base_url: str


def copy_llm_diagnosis(result: LLMDiagnosisResult) -> LLMDiagnosisResult:
    return LLMDiagnosisResult(
        enabled=bool(result.enabled),
        reachable=bool(result.reachable),
        model=str(result.model),
        base_url=str(result.base_url),
        warnings=list(result.warnings),
    )
