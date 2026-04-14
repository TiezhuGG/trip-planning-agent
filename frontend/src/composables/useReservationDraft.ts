import { computed, reactive } from "vue";

import type { ReservationItem, ReservationType } from "../types/planning";

type ReservationDraft = {
  type: ReservationType;
  title: string;
  start_at: string;
  end_at: string;
  location: string;
  notes: string;
  source: string;
  confirmation_code: string;
};

function createEmptyDraft(): ReservationDraft {
  return {
    type: "other",
    title: "",
    start_at: "",
    end_at: "",
    location: "",
    notes: "",
    source: "",
    confirmation_code: "",
  };
}

export function useReservationDraft() {
  const reservationDraft = reactive<ReservationDraft>(createEmptyDraft());

  const trimmedTitle = computed(() => reservationDraft.title.trim());

  const validationMessage = computed(() => {
    if (!trimmedTitle.value) {
      return "请先填写预订标题。";
    }
    if (reservationDraft.end_at && !reservationDraft.start_at) {
      return "如填写结束时间，请先填写开始时间。";
    }
    if (!reservationDraft.start_at || !reservationDraft.end_at) {
      return "";
    }
    const start = new Date(reservationDraft.start_at);
    const end = new Date(reservationDraft.end_at);
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
      return "预订时间格式无效，请重新选择。";
    }
    if (end < start) {
      return "结束时间不能早于开始时间。";
    }
    return "";
  });

  const canSubmit = computed(() => Boolean(trimmedTitle.value) && !validationMessage.value);

  function resetDraft() {
    Object.assign(reservationDraft, createEmptyDraft());
  }

  function toReservationPayload(): Omit<ReservationItem, "id"> {
    return {
      type: reservationDraft.type,
      title: trimmedTitle.value,
      start_at: reservationDraft.start_at || null,
      end_at: reservationDraft.end_at || null,
      location: reservationDraft.location.trim(),
      notes: reservationDraft.notes.trim(),
      source: reservationDraft.source.trim(),
      confirmation_code: reservationDraft.confirmation_code.trim(),
    };
  }

  return {
    reservationDraft,
    validationMessage,
    canSubmit,
    resetDraft,
    toReservationPayload,
  };
}
