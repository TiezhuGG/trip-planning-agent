from __future__ import annotations

import math
from collections.abc import Awaitable, Callable

from app.schemas.planning import POIRecommendation, ToolCallRecord

BuildPoiSearchArguments = Callable[[str, str, str], dict[str, object]]
CallToolForPurpose = Callable[[str, dict[str, object], list[ToolCallRecord]], Awaitable[object]]
NormalizePois = Callable[[object, str], list[POIRecommendation]]
MergeUniquePois = Callable[[list[POIRecommendation]], list[POIRecommendation]]
RecordAdaptiveRetryResult = Callable[[str, bool], Awaitable[None]]
IsRateLimitError = Callable[[Exception], bool]
QueryBudgetCalculator = Callable[[int, int], int]
AdaptivePoiSearchPlan = Callable[[int], Awaitable[tuple[int, tuple[str, ...]]]]


def dedupe_queries(queries: list[str]) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for query in queries:
        normalized = query.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)
    return cleaned


def prioritize_poi_queries(queries: list[str]) -> list[str]:
    generic_markers = (
        "热门景点",
        "旅游景点",
        "景区",
        "本地美食",
        "特色餐厅",
        "热门餐厅",
        "酒店",
        "舒适型酒店",
        "景点",
        "餐厅",
        "美食",
    )
    specific: list[str] = []
    generic: list[str] = []
    for query in queries:
        if any(marker in query for marker in generic_markers):
            generic.append(query)
        else:
            specific.append(query)
    return [*specific, *generic]


def poi_query_budget(
    *,
    target_count: int,
    total_queries: int,
    budget_floor: int,
    budget_cap: int,
) -> int:
    if total_queries <= 0:
        return 0
    dynamic_budget = max(budget_floor, target_count + 2)
    budget = min(budget_cap, dynamic_budget)
    return max(1, min(total_queries, budget))


def adaptive_poi_search_plan(
    *,
    adaptive_retry_enabled: bool,
    base_query_budget: int,
    recent_results: list[int],
    min_samples: int,
    low_success_rate: float,
    consecutive_failures: int,
) -> tuple[int, tuple[str, ...]]:
    if not adaptive_retry_enabled:
        return max(1, base_query_budget), ("true", "false")

    samples = len(recent_results)
    if samples < min_samples:
        return max(1, base_query_budget), ("true", "false")

    success_rate = (sum(recent_results) / samples) if samples else 1.0
    if consecutive_failures >= 3:
        return max(1, min(base_query_budget, 3)), ("true",)
    if success_rate <= max(0.01, low_success_rate / 2):
        return max(1, min(base_query_budget, int(math.ceil(base_query_budget * 0.4)))), ("true",)
    if success_rate <= max(0.01, low_success_rate):
        return max(1, min(base_query_budget, int(math.ceil(base_query_budget * 0.6)))), ("true",)
    return max(1, base_query_budget), ("true", "false")


async def search_poi_candidates(
    *,
    city: str,
    queries: list[str],
    trace: list[ToolCallRecord],
    fallback_kind: str,
    target_count: int,
    build_poi_search_arguments: BuildPoiSearchArguments,
    call_tool_for_purpose: CallToolForPurpose,
    normalize_pois: NormalizePois,
    merge_unique_pois: MergeUniquePois,
    record_adaptive_retry_result: RecordAdaptiveRetryResult,
    is_rate_limit_error: IsRateLimitError,
    poi_query_budget_fn: QueryBudgetCalculator,
    adaptive_poi_search_plan_fn: AdaptivePoiSearchPlan,
    consecutive_empty_stop: int,
) -> list[POIRecommendation]:
    pois: list[POIRecommendation] = []
    deduped_queries = prioritize_poi_queries(dedupe_queries(queries))
    query_budget = poi_query_budget_fn(target_count, len(deduped_queries))
    query_budget, citylimit_modes = await adaptive_poi_search_plan_fn(query_budget)
    selected_queries = deduped_queries[:query_budget]
    for citylimit in citylimit_modes:
        consecutive_empty = 0
        for index, query in enumerate(selected_queries):
            try:
                raw = await call_tool_for_purpose(
                    "poi_search",
                    build_poi_search_arguments(city, query, citylimit),
                    trace,
                )
            except Exception as exc:
                await record_adaptive_retry_result("poi_search", False)
                if is_rate_limit_error(exc):
                    return merge_unique_pois(pois)
                raise
            normalized = normalize_pois(raw, fallback_kind)
            await record_adaptive_retry_result("poi_search", bool(normalized))
            if normalized:
                consecutive_empty = 0
            else:
                consecutive_empty += 1
            pois.extend(normalized)
            merged = merge_unique_pois(pois)
            if len(merged) >= target_count:
                return merged
            if consecutive_empty >= consecutive_empty_stop:
                if pois:
                    break
                if index + 1 >= max(1, len(selected_queries) // 2):
                    break
        if pois:
            return merge_unique_pois(pois)
    return merge_unique_pois(pois)
