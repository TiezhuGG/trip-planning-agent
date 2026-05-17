import type {
  Activity,
  DayPlan,
  MealRecommendation,
  RouteStep,
} from "../types/planning";
import type {
  CompareCategoryFilter,
  CompareChangeDetailKind,
  CompareChangeFilter,
  CompareChangeSignals,
  CompareCollectionChangeCounts,
  CompareDayDiffItem,
} from "../components/workspaceVersionCompareTypes";

export function buildCompareDayDiffItem(
  dayNumber: number,
  currentDay: DayPlan | undefined,
  targetDay: DayPlan | undefined,
): CompareDayDiffItem | null {
  const fields = buildDayDiffFields(currentDay, targetDay);
  const highlights = buildDayDiffHighlights(currentDay, targetDay);
  const timelineEntries = buildDayTimelineEntries(currentDay, targetDay);
  const routeStepEntries = buildRouteStepEntries(currentDay, targetDay);
  if (!fields.length && !highlights.length && !timelineEntries.length && !routeStepEntries.length) {
    return null;
  }
  const changeKind = resolveCompareChangeKind(currentDay, targetDay);
  const changeSignals = buildCompareChangeSignals(currentDay, targetDay, routeStepEntries);
  const changeDetailKind = resolveCompareChangeDetailKind(changeKind, changeSignals);
  return {
    dayNumber,
    changeKind,
    changeDetailKind,
    changeLabel: resolveCompareChangeDetailLabel(changeDetailKind),
    changeSummary: buildCompareChangeSummary(changeDetailKind, dayNumber, changeSignals),
    changeSignals,
    impactScore: buildCompareImpactScore(
      changeKind,
      changeSignals,
      fields.length,
      routeStepEntries.length,
    ),
    fields,
    highlights,
    timelineEntries,
    routeStepEntries,
  };
}

export function buildDayExtendedHighlights(
  currentDay: DayPlan | undefined,
  targetDay: DayPlan | undefined,
) {
  const highlights: string[] = [];
  const currentActivities = currentDay?.activities ?? [];
  const targetActivities = targetDay?.activities ?? [];
  const currentMeals = currentDay?.meals ?? [];
  const targetMeals = targetDay?.meals ?? [];

  currentActivities.forEach((activity) => {
    const match = targetActivities.find((item) => item.title === activity.title);
    if (!match) return;
    if (activity.start_time !== match.start_time || activity.end_time !== match.end_time) {
      highlights.push(
        `活动时间调整：${activity.title} ${activity.start_time}-${activity.end_time} -> ${match.start_time}-${match.end_time}`,
      );
    } else if (activity.location_name !== match.location_name) {
      highlights.push(
        `活动地点调整：${activity.title} ${activity.location_name} -> ${match.location_name}`,
      );
    }
  });

  currentMeals.forEach((meal) => {
    const match = targetMeals.find((item) => item.meal_type === meal.meal_type);
    if (!match) return;
    if (meal.venue_name !== match.venue_name) {
      highlights.push(`餐饮替换：${meal.meal_type} ${meal.venue_name} -> ${match.venue_name}`);
    }
  });

  if ((currentDay?.stay?.hotel_name ?? "") !== (targetDay?.stay?.hotel_name ?? "")) {
    highlights.push(
      `住宿更换：${currentDay?.stay?.hotel_name ?? "无"} -> ${targetDay?.stay?.hotel_name ?? "无"}`,
    );
  }

  const currentRoute = currentDay?.route_summary;
  const targetRoute = targetDay?.route_summary;
  if ((currentRoute?.distance_text ?? "") !== (targetRoute?.distance_text ?? "")) {
    highlights.push(
      `路线距离变化：${currentRoute?.distance_text ?? "无"} -> ${targetRoute?.distance_text ?? "无"}`,
    );
  }
  if ((currentRoute?.duration_text ?? "") !== (targetRoute?.duration_text ?? "")) {
    highlights.push(
      `路线时长变化：${currentRoute?.duration_text ?? "无"} -> ${targetRoute?.duration_text ?? "无"}`,
    );
  }
  const currentWaypoints = (currentRoute?.waypoints ?? []).join("、");
  const targetWaypoints = (targetRoute?.waypoints ?? []).join("、");
  if (currentWaypoints !== targetWaypoints) {
    highlights.push(`路线途经点变化：${currentWaypoints || "无"} -> ${targetWaypoints || "无"}`);
  }

  return [...new Set(highlights)];
}

export function hasRouteCompareDiff(day: CompareDayDiffItem) {
  return day.changeSignals.route > 0 || day.routeStepEntries.length > 0;
}

export function hasStayCompareDiff(day: CompareDayDiffItem) {
  return day.fields.some((field) => field.label === "住宿" || field.label === "住宿区域");
}

export function hasTimelineCompareDiff(day: CompareDayDiffItem) {
  return day.timelineEntries.length > 0 || day.changeSignals.time > 0;
}

export function buildPlanCollectionChangeCounts(
  currentDays: DayPlan[],
  targetDays: DayPlan[],
  key: "activities" | "meals",
): CompareCollectionChangeCounts {
  if (key === "activities") {
    return buildActivityChangeCounts(
      currentDays.flatMap((day) => day.activities ?? []),
      targetDays.flatMap((day) => day.activities ?? []),
    );
  }

  return buildMealChangeCounts(
    currentDays.flatMap((day) => day.meals ?? []),
    targetDays.flatMap((day) => day.meals ?? []),
  );
}

export function formatChangeCounts(counts: CompareCollectionChangeCounts) {
  return `+${counts.added} / -${counts.removed} / ~${counts.changed}`;
}

export function matchesCompareCategory(label: string, filter: CompareCategoryFilter) {
  if (filter === "activities") return label === "活动";
  if (filter === "meals") return label === "餐饮";
  if (filter === "stay") return ["住宿", "住宿区域"].includes(label);
  if (filter === "route") return label === "路线";
  return true;
}

export function matchesCompareHighlight(highlight: string, filter: CompareCategoryFilter) {
  if (filter === "activities") return highlight.includes("活动");
  if (filter === "meals") return highlight.includes("餐饮");
  if (filter === "stay") return highlight.includes("住宿");
  if (filter === "route") return highlight.includes("路线");
  return true;
}

function buildDayDiffFields(
  currentDay: DayPlan | undefined,
  targetDay: DayPlan | undefined,
): CompareDayDiffItem["fields"] {
  const fields: CompareDayDiffItem["fields"] = [];
  const appendDiff = (label: string, current: string, target: string) => {
    if (current !== target) {
      fields.push({ label, current, target });
    }
  };

  appendDiff("主题", currentDay?.theme ?? "无", targetDay?.theme ?? "无");
  appendDiff("概览", currentDay?.overview ?? "无", targetDay?.overview ?? "无");
  appendDiff("住宿区域", currentDay?.hotel_area ?? "无", targetDay?.hotel_area ?? "无");
  appendDiff("住宿", currentDay?.stay?.hotel_name ?? "无", targetDay?.stay?.hotel_name ?? "无");
  appendDiff(
    "活动",
    summarizeActivities(currentDay?.activities),
    summarizeActivities(targetDay?.activities),
  );
  appendDiff("餐饮", summarizeMeals(currentDay?.meals), summarizeMeals(targetDay?.meals));
  appendDiff("路线", currentDay?.route_summary?.title ?? "无", targetDay?.route_summary?.title ?? "无");

  return fields;
}

function buildDayDiffHighlights(
  currentDay: DayPlan | undefined,
  targetDay: DayPlan | undefined,
) {
  const highlights: string[] = [];

  const currentActivityTitles = new Set((currentDay?.activities ?? []).map((item) => item.title));
  const targetActivityTitles = new Set((targetDay?.activities ?? []).map((item) => item.title));
  const currentMealTitles = new Set((currentDay?.meals ?? []).map((item) => item.venue_name));
  const targetMealTitles = new Set((targetDay?.meals ?? []).map((item) => item.venue_name));

  const addedActivities = [...targetActivityTitles].filter((item) => !currentActivityTitles.has(item));
  const removedActivities = [...currentActivityTitles].filter((item) => !targetActivityTitles.has(item));
  const addedMeals = [...targetMealTitles].filter((item) => !currentMealTitles.has(item));
  const removedMeals = [...currentMealTitles].filter((item) => !targetMealTitles.has(item));

  if (addedActivities.length) {
    highlights.push(`对比版本新增活动：${addedActivities.slice(0, 3).join("、")}${addedActivities.length > 3 ? "..." : ""}`);
  }
  if (removedActivities.length) {
    highlights.push(`当前版本独有活动：${removedActivities.slice(0, 3).join("、")}${removedActivities.length > 3 ? "..." : ""}`);
  }
  if (addedMeals.length) {
    highlights.push(`对比版本新增餐饮：${addedMeals.slice(0, 3).join("、")}${addedMeals.length > 3 ? "..." : ""}`);
  }
  if (removedMeals.length) {
    highlights.push(`当前版本独有餐饮：${removedMeals.slice(0, 3).join("、")}${removedMeals.length > 3 ? "..." : ""}`);
  }

  return highlights;
}

function buildDayTimelineEntries(
  currentDay: DayPlan | undefined,
  targetDay: DayPlan | undefined,
) {
  const entries: Array<{
    key: string;
    kind: "activity" | "meal";
    label: string;
    current: string;
    target: string;
  }> = [];

  const currentActivities = currentDay?.activities ?? [];
  const targetActivities = targetDay?.activities ?? [];
  const currentActivityMap = new Map(currentActivities.map((item) => [item.title, item]));
  const targetActivityMap = new Map(targetActivities.map((item) => [item.title, item]));
  const activityKeys = [...new Set([...currentActivityMap.keys(), ...targetActivityMap.keys()])];

  activityKeys.forEach((key) => {
    const current = currentActivityMap.get(key);
    const target = targetActivityMap.get(key);
    if (describeActivity(current) === describeActivity(target)) return;
    entries.push({
      key: `activity-${key}`,
      kind: "activity",
      label: key,
      current: describeActivity(current),
      target: describeActivity(target),
    });
  });

  const currentMealMap = new Map((currentDay?.meals ?? []).map((item) => [item.meal_type, item]));
  const targetMealMap = new Map((targetDay?.meals ?? []).map((item) => [item.meal_type, item]));
  const mealKeys = [...new Set([...currentMealMap.keys(), ...targetMealMap.keys()])];

  mealKeys.forEach((key) => {
    const current = currentMealMap.get(key);
    const target = targetMealMap.get(key);
    if (describeMeal(current) === describeMeal(target)) return;
    entries.push({
      key: `meal-${key}`,
      kind: "meal",
      label: key,
      current: describeMeal(current),
      target: describeMeal(target),
    });
  });

  return entries;
}

function buildRouteStepEntries(
  currentDay: DayPlan | undefined,
  targetDay: DayPlan | undefined,
): CompareDayDiffItem["routeStepEntries"] {
  const currentSteps = currentDay?.route_summary?.steps ?? [];
  const targetSteps = targetDay?.route_summary?.steps ?? [];
  const maxLength = Math.max(currentSteps.length, targetSteps.length);
  const entries: CompareDayDiffItem["routeStepEntries"] = [];

  for (let index = 0; index < maxLength; index += 1) {
    const current = currentSteps[index];
    const target = targetSteps[index];
    const currentText = describeRouteStep(current);
    const targetText = describeRouteStep(target);
    if (currentText === targetText) continue;

    entries.push({
      key: `route-step-${index + 1}`,
      label: `Step ${index + 1}`,
      current: currentText,
      target: targetText,
    });
  }

  return entries;
}

function resolveCompareChangeKind(
  currentDay: DayPlan | undefined,
  targetDay: DayPlan | undefined,
): Exclude<CompareChangeFilter, "all"> {
  if (!currentDay && targetDay) return "added";
  if (currentDay && !targetDay) return "removed";
  return "changed";
}

function buildCompareChangeSignals(
  currentDay: DayPlan | undefined,
  targetDay: DayPlan | undefined,
  routeStepEntries: CompareDayDiffItem["routeStepEntries"],
): CompareChangeSignals {
  const signals: CompareChangeSignals = {
    time: 0,
    location: 0,
    route: 0,
    collection: 0,
    meta: 0,
  };

  const currentActivities = currentDay?.activities ?? [];
  const targetActivities = targetDay?.activities ?? [];
  const currentMeals = currentDay?.meals ?? [];
  const targetMeals = targetDay?.meals ?? [];

  const currentActivityMap = new Map(currentActivities.map((item) => [item.title, item]));
  const targetActivityMap = new Map(targetActivities.map((item) => [item.title, item]));
  const activityKeys = [...new Set([...currentActivityMap.keys(), ...targetActivityMap.keys()])];
  activityKeys.forEach((key) => {
    const current = currentActivityMap.get(key);
    const target = targetActivityMap.get(key);
    if (!current || !target) {
      signals.collection += 1;
      return;
    }
    if (current.start_time !== target.start_time || current.end_time !== target.end_time) {
      signals.time += 1;
    }
    if (current.location_name !== target.location_name) {
      signals.location += 1;
    }
  });

  const currentMealMap = new Map(currentMeals.map((item) => [item.meal_type, item]));
  const targetMealMap = new Map(targetMeals.map((item) => [item.meal_type, item]));
  const mealKeys = [...new Set([...currentMealMap.keys(), ...targetMealMap.keys()])];
  mealKeys.forEach((key) => {
    const current = currentMealMap.get(key);
    const target = targetMealMap.get(key);
    if (!current || !target) {
      signals.collection += 1;
      return;
    }
    if (current.venue_name !== target.venue_name) {
      signals.location += 1;
    }
  });

  if ((currentDay?.stay?.hotel_name ?? "") !== (targetDay?.stay?.hotel_name ?? "")) {
    signals.location += 1;
  }

  if ((currentDay?.hotel_area ?? "") !== (targetDay?.hotel_area ?? "")) {
    signals.location += 1;
  }

  if ((currentDay?.theme ?? "") !== (targetDay?.theme ?? "")) {
    signals.meta += 1;
  }

  if ((currentDay?.overview ?? "") !== (targetDay?.overview ?? "")) {
    signals.meta += 1;
  }

  const currentRoute = currentDay?.route_summary;
  const targetRoute = targetDay?.route_summary;
  if ((currentRoute?.title ?? "") !== (targetRoute?.title ?? "")) {
    signals.route += 1;
  }
  if ((currentRoute?.distance_text ?? "") !== (targetRoute?.distance_text ?? "")) {
    signals.route += 1;
  }
  if ((currentRoute?.duration_text ?? "") !== (targetRoute?.duration_text ?? "")) {
    signals.route += 1;
  }
  if ((currentRoute?.waypoints ?? []).join("|") !== (targetRoute?.waypoints ?? []).join("|")) {
    signals.route += 1;
  }
  if (routeStepEntries.length) {
    signals.route += routeStepEntries.length;
  }

  return signals;
}

function resolveCompareChangeDetailKind(
  changeKind: Exclude<CompareChangeFilter, "all">,
  signals: CompareChangeSignals,
): CompareChangeDetailKind {
  if (changeKind === "added") return "added";
  if (changeKind === "removed") return "removed";

  const activeSignals = [
    signals.time > 0,
    signals.location > 0,
    signals.route > 0,
    signals.collection > 0 || signals.meta > 0,
  ].filter(Boolean).length;

  if (activeSignals > 1) return "mixed";
  if (signals.route > 0) return "route";
  if (signals.time > 0) return "time";
  if (signals.location > 0) return "location";
  return "mixed";
}

function resolveCompareChangeDetailLabel(kind: CompareChangeDetailKind) {
  if (kind === "added") return "整天新增";
  if (kind === "removed") return "整天移除";
  if (kind === "time") return "时间调整";
  if (kind === "location") return "地点/住宿调整";
  if (kind === "route") return "路线调整";
  return "多项变更";
}

function buildCompareChangeSummary(
  kind: CompareChangeDetailKind,
  dayNumber: number,
  signals: CompareChangeSignals,
) {
  if (kind === "added") return `第 ${dayNumber} 天仅存在于对比版本中，可视为整天新增。`;
  if (kind === "removed") return `第 ${dayNumber} 天仅存在于当前版本中，可视为整天移除。`;
  if (kind === "time") return `第 ${dayNumber} 天以时间安排调整为主，识别到 ${signals.time} 处时间相关变更。`;
  if (kind === "location") return `第 ${dayNumber} 天以地点或住宿调整为主，识别到 ${signals.location} 处位置相关变更。`;
  if (kind === "route") return `第 ${dayNumber} 天以路线安排调整为主，识别到 ${signals.route} 处路线相关变更。`;
  return `第 ${dayNumber} 天存在多项内容变更，时间 ${signals.time} / 地点 ${signals.location} / 路线 ${signals.route} / 结构 ${signals.collection + signals.meta}。`;
}

function buildCompareImpactScore(
  changeKind: Exclude<CompareChangeFilter, "all">,
  signals: CompareChangeSignals,
  fieldCount: number,
  routeStepCount: number,
) {
  const base =
    signals.time * 2 +
    signals.location * 2 +
    signals.route * 3 +
    signals.collection * 2 +
    signals.meta;
  const fieldWeight = fieldCount;
  const routeWeight = routeStepCount;
  const changeKindBonus = changeKind === "changed" ? 2 : 1;
  return base + fieldWeight + routeWeight + changeKindBonus;
}

function summarizeActivities(activities: DayPlan["activities"] | undefined) {
  if (!activities?.length) return "无";
  return `${activities.length} 项：${activities.slice(0, 3).map((item) => item.title).join("、")}${activities.length > 3 ? "..." : ""}`;
}

function summarizeMeals(meals: DayPlan["meals"] | undefined) {
  if (!meals?.length) return "无";
  return `${meals.length} 项：${meals.slice(0, 3).map((item) => item.venue_name).join("、")}${meals.length > 3 ? "..." : ""}`;
}

function describeActivity(activity: Activity | undefined) {
  if (!activity) return "无";
  return [
    `${activity.start_time}-${activity.end_time}`,
    activity.location_name || "未标注地点",
    activity.category || "未分类",
  ].join(" · ");
}

function describeMeal(meal: MealRecommendation | undefined) {
  if (!meal) return "无";
  return [
    meal.venue_name || "未安排",
    meal.cuisine || "未标注菜系",
    meal.suggestion || "无备注",
  ].join(" · ");
}

function describeRouteStep(step: RouteStep | undefined) {
  if (!step) return "无";
  return [step.instruction || "无指引", step.distance_text || "-", step.duration_text || "-"].join(
    " | ",
  );
}

export function countDayCollectionItems(days: DayPlan[], key: "activities" | "meals") {
  return days.reduce((sum, day) => sum + (day[key]?.length ?? 0), 0);
}

export function formatDeltaValue(delta: number) {
  if (delta === 0) return "0";
  return delta > 0 ? `+${delta}` : `${delta}`;
}

function buildActivityChangeCounts(
  currentItems: DayPlan["activities"],
  targetItems: DayPlan["activities"],
): CompareCollectionChangeCounts {
  const currentMap = new Map(currentItems.map((item) => [item.title, item]));
  const targetMap = new Map(targetItems.map((item) => [item.title, item]));
  let added = 0;
  let removed = 0;
  let changed = 0;

  targetMap.forEach((item, key) => {
    const current = currentMap.get(key);
    if (!current) {
      added += 1;
      return;
    }
    if (
      current.start_time !== item.start_time ||
      current.end_time !== item.end_time ||
      current.location_name !== item.location_name
    ) {
      changed += 1;
    }
  });

  currentMap.forEach((_, key) => {
    if (!targetMap.has(key)) removed += 1;
  });

  return { added, removed, changed };
}

function buildMealChangeCounts(
  currentItems: DayPlan["meals"],
  targetItems: DayPlan["meals"],
): CompareCollectionChangeCounts {
  const currentMap = new Map(currentItems.map((item) => [item.meal_type, item]));
  const targetMap = new Map(targetItems.map((item) => [item.meal_type, item]));
  let added = 0;
  let removed = 0;
  let changed = 0;

  targetMap.forEach((item, key) => {
    const current = currentMap.get(key);
    if (!current) {
      added += 1;
      return;
    }
    if (
      current.venue_name !== item.venue_name ||
      current.cuisine !== item.cuisine ||
      current.suggestion !== item.suggestion
    ) {
      changed += 1;
    }
  });

  currentMap.forEach((_, key) => {
    if (!targetMap.has(key)) removed += 1;
  });

  return { added, removed, changed };
}
