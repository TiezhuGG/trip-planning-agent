export type CompareCategoryFilter = "all" | "activities" | "meals" | "stay" | "route";
export type CompareChangeFilter = "all" | "added" | "removed" | "changed";
export type CompareChangeDetailKind = "added" | "removed" | "time" | "location" | "route" | "mixed";
export type CompareSortMode = "day" | "impact";
export type CompareImpactFilter = "all" | "high";
export type CompareSignalFocus = "all" | "time" | "location" | "route" | "structure";

export type CompareSummaryItem = {
  key: string;
  label: string;
  current: string;
  target: string;
};

export type CompareOverviewItem = {
  key: string;
  label: string;
  value: string;
  description: string;
  toneClass: string;
};

export type CompareFilterChipKey =
  | "category"
  | "change"
  | "sort"
  | "impact"
  | "signal"
  | "threshold";

export type CompareActiveFilterChip = {
  key: CompareFilterChipKey;
  label: string;
};

export type CompareCollectionChangeCounts = {
  added: number;
  removed: number;
  changed: number;
};

export type CompareChangeSignals = {
  time: number;
  location: number;
  route: number;
  collection: number;
  meta: number;
};

export type CompareDayDiffItem = {
  dayNumber: number;
  changeKind: Exclude<CompareChangeFilter, "all">;
  changeDetailKind: CompareChangeDetailKind;
  changeLabel: string;
  changeSummary: string;
  changeSignals: CompareChangeSignals;
  impactScore: number;
  fields: Array<{
    label: string;
    current: string;
    target: string;
  }>;
  highlights: string[];
  timelineEntries: Array<{
    key: string;
    kind: "activity" | "meal";
    label: string;
    current: string;
    target: string;
  }>;
  routeStepEntries: Array<{
    key: string;
    label: string;
    current: string;
    target: string;
  }>;
};
