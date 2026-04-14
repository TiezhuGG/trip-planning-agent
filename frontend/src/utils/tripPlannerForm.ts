import type { Ref } from "vue";

import type { TripPlanningRequest, TravelerProfile } from "../types/planning";

export function formatDate(date: Date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function createDate(dateString: string) {
  const [year, month, day] = dateString.split("-").map(Number);
  return new Date(year, month - 1, day, 12, 0, 0);
}

export function addDays(dateString: string, days: number) {
  const base = createDate(dateString);
  base.setDate(base.getDate() + Math.max(0, days));
  return formatDate(base);
}

export function diffDays(start: string, end: string) {
  return Math.floor((createDate(end).getTime() - createDate(start).getTime()) / 86400000) + 1;
}

export function splitText(value: string) {
  return value
    .split(/[\n,，、;；]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function isChineseCityName(value: string) {
  return /^[\u4e00-\u9fff]{2,30}$/.test(value.trim());
}

export function formatTravelers(travelers: TravelerProfile) {
  const parts: string[] = [];
  if (travelers.adults) parts.push(`${travelers.adults} 位成人`);
  if (travelers.children) parts.push(`${travelers.children} 位儿童`);
  if (travelers.seniors) parts.push(`${travelers.seniors} 位长者`);
  return parts.join(" · ") || "1 位成人";
}

export function applyRequestToFormState(options: {
  form: TripPlanningRequest;
  request: TripPlanningRequest;
  startDate: Ref<string>;
  endDate: Ref<string>;
  mustVisitText: Ref<string>;
  diningText: Ref<string>;
}) {
  const { form, request, startDate, endDate, mustVisitText, diningText } = options;
  form.origin = request.origin ?? "";
  form.destination = request.destination;
  form.start_date = request.start_date;
  form.days = request.days;
  form.interests = [...request.interests];
  form.must_visit = [...request.must_visit];
  form.pace = request.pace;
  form.budget_level = request.budget_level;
  form.transport_preferences = [...request.transport_preferences];
  form.hotel_style = request.hotel_style;
  form.dining_preferences = [...request.dining_preferences];
  form.travelers = { ...request.travelers };
  form.notes = request.notes ?? "";
  startDate.value = request.start_date;
  endDate.value = addDays(request.start_date, request.days - 1);
  mustVisitText.value = request.must_visit.join("、");
  diningText.value = request.dining_preferences.join("、");
}
