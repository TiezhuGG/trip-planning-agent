import type { Ref } from "vue";

import type { ReservationItem, TripWorkspace } from "../types/planning";
import { createReservationId } from "../utils/tripWorkspacePayloads";
import {
  ensureCurrentWorkspace,
  type NoticeTone,
} from "./tripWorkspaceActionHelpers";

export function createTripWorkspaceReservationActions(options: {
  currentTrip: Ref<TripWorkspace | null>;
  tripNotes: Ref<string>;
  openNotice: (tone: NoticeTone, title: string, messages: string[]) => void;
  saveWorkspacePatch: (patch: {
    manual_notes?: string | null;
    locked_day_numbers?: number[] | null;
    reservations?: ReservationItem[] | null;
  }) => Promise<void>;
}) {
  const { currentTrip, tripNotes, openNotice, saveWorkspacePatch } = options;

  async function toggleTripDayLock(dayNumber: number) {
    const workspace = ensureCurrentWorkspace(
      currentTrip,
      openNotice,
      "请先等待行程结果保存完成。",
    );
    if (!workspace) {
      return;
    }

    const locked = new Set(workspace.locked_day_numbers);
    if (locked.has(dayNumber)) locked.delete(dayNumber);
    else locked.add(dayNumber);

    await saveWorkspacePatch({
      manual_notes: tripNotes.value,
      locked_day_numbers: [...locked],
      reservations: workspace.reservations,
    });
  }

  async function addReservation(reservation: Omit<ReservationItem, "id">) {
    const workspace = ensureCurrentWorkspace(
      currentTrip,
      openNotice,
      "请先保存草稿或生成行程。",
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
      "请先保存草稿或生成行程。",
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
