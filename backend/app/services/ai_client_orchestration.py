from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.schemas.planning import InitialPlanDraft, PlanningContext, ToolCallRecord, TravelPlan, TripPlanningRequest
from app.services.ai_client_models import FinalPlanBuildResult, InitialPlanBuildResult, LLMProvider

BuildInitialPlanWithProvider = Callable[
    [TripPlanningRequest, LLMProvider],
    Awaitable[tuple[InitialPlanDraft, list[str]]],
]
ComposeWithProvider = Callable[
    [TripPlanningRequest, InitialPlanDraft, PlanningContext, list[ToolCallRecord], LLMProvider],
    Awaitable[tuple[TravelPlan, list[str]]],
]
ShouldSwitchToBackupModel = Callable[[Exception], bool]
ShouldFallbackToTemplate = Callable[[Exception], bool]
FormatException = Callable[[Exception], str]
FallbackInitialPlan = Callable[[TripPlanningRequest], InitialPlanDraft]
BuildFallbackFinalPlan = Callable[[TripPlanningRequest, InitialPlanDraft, PlanningContext], TravelPlan]


async def build_initial_plan(
    *,
    request: TripPlanningRequest,
    providers: list[LLMProvider],
    build_initial_plan_with_provider_fn: BuildInitialPlanWithProvider,
    should_switch_to_backup_model_fn: ShouldSwitchToBackupModel,
    should_fallback_to_template_fn: ShouldFallbackToTemplate,
    format_exception_fn: FormatException,
    fallback_initial_plan_fn: FallbackInitialPlan,
) -> InitialPlanBuildResult:
    if not providers:
        raise RuntimeError("未配置可用的大模型客户端，无法生成初步规划。")

    warnings: list[str] = []
    last_error: Exception | None = None
    for index, provider in enumerate(providers):
        try:
            draft, provider_warnings = await build_initial_plan_with_provider_fn(
                request,
                provider,
            )
            warnings.extend(provider_warnings)
            return InitialPlanBuildResult(
                draft=draft,
                used_llm=True,
                fallback_used=False,
                warnings=warnings,
            )
        except Exception as exc:
            last_error = exc
            if index < len(providers) - 1 and should_switch_to_backup_model_fn(exc):
                warnings.append(
                    f"{provider.label} {provider.model} 暂不可用，已切换到备用模型。原因: {format_exception_fn(exc)}"
                )
                continue
            if should_fallback_to_template_fn(exc):
                warnings.append(
                    f"初步规划调用大模型受限，已切换到规则模板。原因: {format_exception_fn(exc)}"
                )
                return InitialPlanBuildResult(
                    draft=fallback_initial_plan_fn(request),
                    used_llm=False,
                    fallback_used=True,
                    warnings=warnings,
                )

    assert last_error is not None
    if should_fallback_to_template_fn(last_error):
        warnings.append(
            f"初步规划调用大模型受限，已切换到规则模板。原因: {format_exception_fn(last_error)}"
        )
        return InitialPlanBuildResult(
            draft=fallback_initial_plan_fn(request),
            used_llm=False,
            fallback_used=True,
            warnings=warnings,
        )
    raise RuntimeError(f"初步规划调用大模型失败: {format_exception_fn(last_error)}") from last_error


async def compose_plan(
    *,
    request: TripPlanningRequest,
    initial_plan: InitialPlanDraft,
    context: PlanningContext,
    tool_trace: list[ToolCallRecord],
    providers: list[LLMProvider],
    compose_with_provider_fn: ComposeWithProvider,
    should_switch_to_backup_model_fn: ShouldSwitchToBackupModel,
    should_fallback_to_template_fn: ShouldFallbackToTemplate,
    format_exception_fn: FormatException,
    build_fallback_final_plan_fn: BuildFallbackFinalPlan,
) -> FinalPlanBuildResult:
    if not providers:
        raise RuntimeError("未配置可用的大模型客户端，无法生成最终行程。")

    warnings: list[str] = []
    last_error: Exception | None = None
    for index, provider in enumerate(providers):
        try:
            plan, provider_warnings = await compose_with_provider_fn(
                request,
                initial_plan,
                context,
                tool_trace,
                provider,
            )
            warnings.extend(provider_warnings)
            return FinalPlanBuildResult(
                plan=plan,
                used_llm=True,
                fallback_used=False,
                warnings=warnings,
            )
        except Exception as exc:
            last_error = exc
            if index < len(providers) - 1 and should_switch_to_backup_model_fn(exc):
                warnings.append(
                    f"{provider.label} {provider.model} 暂不可用，已切换到备用模型。原因: {format_exception_fn(exc)}"
                )
                continue
            if should_fallback_to_template_fn(exc):
                return FinalPlanBuildResult(
                    plan=build_fallback_final_plan_fn(request, initial_plan, context),
                    used_llm=False,
                    fallback_used=True,
                    warnings=warnings
                    + [f"最终行程汇总调用大模型受限，已切换到规则模板。原因: {format_exception_fn(exc)}"],
                )
            raise RuntimeError(f"最终行程汇总调用大模型失败: {format_exception_fn(exc)}") from exc

    assert last_error is not None
    raise RuntimeError(f"最终行程汇总调用大模型失败: {format_exception_fn(last_error)}") from last_error
