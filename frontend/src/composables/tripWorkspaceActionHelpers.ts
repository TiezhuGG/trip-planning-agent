import type { Ref } from "vue";

import type {
  ReservationItem,
  TripCreateRequest,
  TripPlanningRequest,
  TripWorkspace,
  TripWorkspacePatchRequest,
} from "../types/planning";
import {
  buildTripPlanningRequestPayload,
  buildWorkspaceStatePayload,
} from "../utils/tripWorkspacePayloads";

export type NoticeTone = "success" | "warning" | "error";

export type OpenNotice = (
  tone: NoticeTone,
  title: string,
  messages: string[],
) => void;

export function toActionErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export function ensureCurrentWorkspace(
  currentTrip: Ref<TripWorkspace | null>,
  openNotice: OpenNotice,
  message: string,
): TripWorkspace | null {
  if (currentTrip.value) {
    return currentTrip.value;
  }
  openNotice("warning", "工作区尚未就绪", [message]);
  return null;
}

export function buildWorkspacePatchPayload(options: {
  currentTrip: TripWorkspace;
  tripNotes: string;
  showDevPanels: boolean;
  patch: {
    manual_notes?: string | null;
    locked_day_numbers?: number[] | null;
    reservations?: ReservationItem[] | null;
    request_brief?: TripPlanningRequest | null;
    generate_response?: boolean;
  };
}): TripWorkspacePatchRequest {
  const { currentTrip, tripNotes, showDevPanels, patch } = options;
  return {
    ...patch,
    ...buildWorkspaceStatePayload({
      manualNotes: patch.manual_notes ?? tripNotes,
      lockedDayNumbers: patch.locked_day_numbers ?? currentTrip.locked_day_numbers,
      reservations: patch.reservations ?? currentTrip.reservations,
      includeDebug: showDevPanels,
    }),
    request_brief: patch.request_brief,
    generate_response: patch.generate_response,
  };
}

export function buildPersistedWorkspacePayload(options: {
  requestBrief: TripPlanningRequest;
  tripNotes: string;
  currentTrip: TripWorkspace | null;
  showDevPanels: boolean;
  responseSnapshot?: TripCreateRequest["response_snapshot"];
  generateResponse: boolean;
}): TripCreateRequest {
  const {
    requestBrief,
    tripNotes,
    currentTrip,
    showDevPanels,
    responseSnapshot,
    generateResponse,
  } = options;
  return {
    request_brief: requestBrief,
    response_snapshot: responseSnapshot,
    ...buildWorkspaceStatePayload({
      manualNotes: tripNotes,
      lockedDayNumbers: currentTrip?.locked_day_numbers ?? [],
      reservations: currentTrip?.reservations ?? [],
      includeDebug: showDevPanels,
    }),
    generate_response: generateResponse,
  };
}

export function normalizeDraftRequest(options: {
  form: TripPlanningRequest;
  mustVisitText: string;
  diningText: string;
  isChineseCityName: (value: string) => boolean;
  splitText: (value: string) => string[];
}): { ok: true; request: TripPlanningRequest } | { ok: false; message: string } {
  const { form, mustVisitText, diningText, isChineseCityName, splitText } = options;
  const normalizedDestination = form.destination.trim();
  if (!isChineseCityName(normalizedDestination)) {
    return {
      ok: false,
      message: "目的地仅支持中文城市名，例如：上海、北京市。",
    };
  }
  const mustVisit = splitText(mustVisitText);
  const diningPreferences = splitText(diningText);
  form.must_visit = mustVisit;
  form.dining_preferences = diningPreferences;
  form.destination = normalizedDestination;
  return {
    ok: true,
    request: buildTripPlanningRequestPayload({
      form,
      mustVisit,
      diningPreferences,
    }),
  };
}
