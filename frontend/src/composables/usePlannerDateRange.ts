import { ref, watch } from "vue";

import type { TripPlanningRequest } from "../types/planning";
import { addDays, diffDays } from "../utils/tripPlannerForm";

export function usePlannerDateRange(form: TripPlanningRequest) {
  const startDate = ref(form.start_date);
  const endDate = ref(addDays(form.start_date, form.days - 1));

  watch([startDate, endDate], ([start, end]) => {
    if (!start) return;
    if (!end || end < start) {
      endDate.value = start;
      form.days = 1;
      form.start_date = start;
      return;
    }
    form.start_date = start;
    form.days = Math.min(14, Math.max(1, diffDays(start, end)));
  });

  watch(
    () => form.days,
    (days) => {
      const safe = Math.min(14, Math.max(1, Number(days) || 1));
      if (safe !== days) {
        form.days = safe;
        return;
      }
      endDate.value = addDays(startDate.value, safe - 1);
    },
  );

  return {
    startDate,
    endDate,
  };
}
