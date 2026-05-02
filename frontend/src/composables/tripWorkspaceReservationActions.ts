import type { Ref } from "vue";

import type { ReservationItem, TripWorkspace } from "../types/planning";
import { createReservationId } from "../utils/tripWorkspacePayloads";
import {
  ensureCurrentWorkspace,
  type NoticeTone,
} from "./tripWorkspaceActionHelpers";

const WAIT_FOR_WORKSPACE_MESSAGE = "请先等待当前工作区保存完成后再继续操作。";
const SAVE_OR_GENERATE_MESSAGE = "请先保存草稿或生成行程，然后再维护预订信息。";

export function createTripWorkspaceReservationActions(options: {
  currentTrip: Ref<TripWorkspace | null>;
  tripNotes: Ref<string>;
  openNotice: (tone: NoticeTone, title: string, messages: string[]) => void;
  saveWorkspacePatch: (patch: {
    manual_notes?: string | null;
    locked_day_numbers?: number[] | null;
    reservations?: ReservationItem[] | null;
  }) => Promise<TripWorkspace | null>;
}) {
  const { currentTrip, tripNotes, openNotice, saveWorkspacePatch } = options;

  async function toggleTripDayLock(dayNumber: number) {
    const workspace = ensureCurrentWorkspace(
      currentTrip,
      openNotice,
      WAIT_FOR_WORKSPACE_MESSAGE,
    );
    if (!workspace) {
      return;
    }

    const lockedDayNumbers = new Set(workspace.locked_day_numbers);
    if (lockedDayNumbers.has(dayNumber)) {
      lockedDayNumbers.delete(dayNumber);
    } else {
      lockedDayNumbers.add(dayNumber);
    }

    await saveWorkspacePatch({
      manual_notes: tripNotes.value,
      locked_day_numbers: [...lockedDayNumbers],
      reservations: workspace.reservations,
    });
  }

  async function addReservation(reservation: Omit<ReservationItem, "id">) {
    const workspace = ensureCurrentWorkspace(
      currentTrip,
      openNotice,
      SAVE_OR_GENERATE_MESSAGE,
    );
    if (!workspace) {
      return;
    }

    const nextReservations: ReservationItem[] = [
      ...workspace.reservations,
      {
        ...reservation,
        id: createReservationId(),
      },
    ];

    await saveWorkspacePatch({
      manual_notes: tripNotes.value,
      locked_day_numbers: workspace.locked_day_numbers,
      reservations: nextReservations,
    });
  }

  async function removeReservation(reservationId: string) {
    const workspace = ensureCurrentWorkspace(
      currentTrip,
      openNotice,
      SAVE_OR_GENERATE_MESSAGE,
    );
    if (!workspace) {
      return;
    }

    await saveWorkspacePatch({
      manual_notes: tripNotes.value,
      locked_day_numbers: workspace.locked_day_numbers,
      reservations: workspace.reservations.filter((item) => item.id !== reservationId),
    });
  }

  return {
    addReservation,
    removeReservation,
    toggleTripDayLock,
  };
}
