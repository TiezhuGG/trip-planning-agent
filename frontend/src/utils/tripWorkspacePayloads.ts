import type {
  ReservationItem,
  TripCreateRequest,
  TripPlanningRequest,
  TripWorkspacePatchRequest,
} from "../types/planning";

export function createReservationId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `reservation-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

export function buildTripPlanningRequestPayload(options: {
  form: TripPlanningRequest;
  mustVisit: string[];
  diningPreferences: string[];
}): TripPlanningRequest {
  const { form, mustVisit, diningPreferences } = options;
  return {
    ...form,
    origin: form.origin?.trim() || null,
    destination: form.destination.trim(),
    hotel_style: form.hotel_style || "舒适型酒店",
    interests: [...form.interests],
    must_visit: [...mustVisit],
    transport_preferences: [...form.transport_preferences],
    dining_preferences: [...diningPreferences],
    travelers: {
      adults: Number(form.travelers.adults) || 1,
      children: Number(form.travelers.children) || 0,
      seniors: Number(form.travelers.seniors) || 0,
    },
  };
}

export function buildWorkspaceStatePayload(options: {
  manualNotes: string;
  lockedDayNumbers: number[];
  reservations: ReservationItem[];
  includeDebug: boolean;
}): Pick<
  TripCreateRequest,
  "manual_notes" | "locked_day_numbers" | "reservations" | "include_debug"
> &
  Pick<TripWorkspacePatchRequest, "manual_notes" | "locked_day_numbers" | "reservations" | "include_debug"> {
  const { manualNotes, lockedDayNumbers, reservations, includeDebug } = options;
  return {
    manual_notes: manualNotes,
    locked_day_numbers: lockedDayNumbers,
    reservations,
    include_debug: includeDebug,
  };
}
