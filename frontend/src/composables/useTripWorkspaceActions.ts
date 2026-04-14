import type { Ref } from "vue";

import type {
  TripPlanningRequest,
  TripWorkspace,
} from "../types/planning";
import {
  type NoticeTone,
} from "./tripWorkspaceActionHelpers";
import { createTripWorkspacePersistenceActions } from "./tripWorkspacePersistenceActions";
import { createTripWorkspaceReplanActions } from "./tripWorkspaceReplanActions";
import { createTripWorkspaceReservationActions } from "./tripWorkspaceReservationActions";

export function useTripWorkspaceActions(options: {
  currentTrip: Ref<TripWorkspace | null>;
  tripNotes: Ref<string>;
  tripSaving: Ref<boolean>;
  tripLoading: Ref<boolean>;
  tripReplanning: Ref<boolean>;
  draftSaving: Ref<boolean>;
  replanningDays: Ref<number[]>;
  shareLink: Ref<string>;
  form: TripPlanningRequest;
  mustVisitText: Ref<string>;
  diningText: Ref<string>;
  showDevPanels: boolean;
  applyWorkspace: (workspace: TripWorkspace, options?: { syncUrl?: boolean }) => void;
  openNotice: (tone: NoticeTone, title: string, messages: string[]) => void;
  syncTripQuery: (shareToken?: string | null) => void;
  isChineseCityName: (value: string) => boolean;
  splitText: (value: string) => string[];
}) {
  const {
    currentTrip,
    tripNotes,
    tripSaving,
    tripLoading,
    tripReplanning,
    draftSaving,
    replanningDays,
    shareLink,
    form,
    mustVisitText,
    diningText,
    showDevPanels,
    applyWorkspace,
    openNotice,
    syncTripQuery,
    isChineseCityName,
    splitText,
  } = options;

  const persistenceActions = createTripWorkspacePersistenceActions({
    currentTrip,
    tripNotes,
    tripSaving,
    tripLoading,
    draftSaving,
    shareLink,
    form,
    mustVisitText,
    diningText,
    showDevPanels,
    applyWorkspace,
    openNotice,
    syncTripQuery,
    isChineseCityName,
    splitText,
  });

  const reservationActions = createTripWorkspaceReservationActions({
    currentTrip,
    tripNotes,
    openNotice,
    saveWorkspacePatch: persistenceActions.saveWorkspacePatch,
  });

  const replanActions = createTripWorkspaceReplanActions({
    currentTrip,
    tripNotes,
    tripReplanning,
    replanningDays,
    showDevPanels,
    applyWorkspace,
    openNotice,
  });

  return {
    ...persistenceActions,
    ...reservationActions,
    ...replanActions,
  };
}
