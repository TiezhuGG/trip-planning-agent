<script setup lang="ts">
import LandingHero from "./LandingHero.vue";
import IntegrationPrecheckPanel from "./IntegrationPrecheckPanel.vue";
import PlanningTelemetryPanel from "./PlanningTelemetryPanel.vue";
import PlannerLaunchPanel from "./PlannerLaunchPanel.vue";
import PlannerRequestForm from "./PlannerRequestForm.vue";
import RecentTripListPanel from "./RecentTripListPanel.vue";
import TravelTonePanel from "./TravelTonePanel.vue";

import type {
  IntegrationStatus,
  PlanningTelemetry,
  TripSummary,
  TripPlanningRequest,
} from "../types/planning";
import type { PlannerInputCheck } from "../composables/usePlannerDerivedState";
import { formatDateTimeZhCn } from "../utils/workspaceFormatting";

type PlannerOption<T> = {
  label: string;
  value: T;
};

const props = defineProps<{
  summaryTags: string[];
  isEditingWorkspace: boolean;
  localDraftRestored: boolean;
  localDraftSavedAt: string;
  editingTripVersion: number | null;
  form: TripPlanningRequest;
  interestOptions: string[];
  transportOptions: string[];
  hotelOptions: string[];
  paceOptions: PlannerOption<TripPlanningRequest["pace"]>[];
  budgetOptions: PlannerOption<TripPlanningRequest["budget_level"]>[];
  showDevPanels: boolean;
  inputSummary: Array<{ label: string; value: string }>;
  progress: number;
  progressLabel: string;
  loading: boolean;
  draftSaving: boolean;
  recentTrips: TripSummary[];
  recentTripsLoading: boolean;
  recentTripsError: string;
  planningChecks: PlannerInputCheck[];
  canSaveDraft: boolean;
  canSubmit: boolean;
  saveDraftHint: string;
  submitHint: string;
  currentIntegrationStatus: IntegrationStatus;
  integrationLoading: boolean;
  telemetry: PlanningTelemetry;
  telemetryLoading: boolean;
  telemetryError: string;
  paceLabel: (value: TripPlanningRequest["pace"]) => string;
  toggleSelection: (list: string[], value: string) => void;
}>();

const startDate = defineModel<string>("startDate", { required: true });
const endDate = defineModel<string>("endDate", { required: true });
const mustVisitText = defineModel<string>("mustVisitText", { required: true });
const diningText = defineModel<string>("diningText", { required: true });

const emit = defineEmits<{
  (event: "reset"): void;
  (event: "submit"): void;
  (event: "dismiss-local-draft"): void;
  (event: "open-recent-trip", tripId: string): void;
  (event: "save-draft"): void;
  (event: "refresh-recent-trips"): void;
  (event: "refresh-integration"): void;
  (event: "refresh-telemetry"): void;
}>();

function formatDateTime(value: string) {
  return formatDateTimeZhCn(value);
}
</script>

<template>
  <section class="flex min-h-[calc(100vh-3rem)] flex-col justify-center gap-8">
    <LandingHero :summary-tags="summaryTags" />

    <article
      v-if="localDraftRestored && !isEditingWorkspace"
      class="rounded-[30px] border border-sky-100 bg-[linear-gradient(135deg,_rgba(231,244,255,0.94),_rgba(247,251,255,0.96))] px-6 py-5 shadow-card"
    >
      <div class="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div class="text-xs uppercase tracking-[0.24em] text-sky-600">
            浏览器草稿
          </div>
          <div class="mt-2 text-lg font-semibold text-ink">已恢复上次未提交的输入</div>
          <div class="mt-2 text-sm text-slate-600">
            {{
              localDraftSavedAt
                ? `最近自动保存于 ${formatDateTime(localDraftSavedAt)}，你可以直接继续编辑。`
                : "检测到浏览器里有未提交输入，已帮你恢复到当前表单。"
            }}
          </div>
        </div>
        <div class="flex flex-wrap gap-2">
          <button
            type="button"
            class="rounded-full border border-slate-200 bg-white px-5 py-3 text-sm shadow-sm"
            @click="emit('dismiss-local-draft')"
          >
            继续编辑
          </button>
          <button
            type="button"
            class="rounded-full border border-slate-200 bg-white px-5 py-3 text-sm shadow-sm"
            @click="emit('reset')"
          >
            清空重填
          </button>
        </div>
      </div>
    </article>

    <article
      v-if="isEditingWorkspace && editingTripVersion !== null"
      class="rounded-[30px] border border-[#d8e3ee] bg-white/92 px-6 py-5 shadow-card"
    >
      <div class="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div class="text-xs uppercase tracking-[0.24em] text-[#6f7f92]">
            正在编辑工作区
          </div>
          <div class="mt-2 text-lg font-semibold text-ink">正在编辑当前行程工作区</div>
          <div class="mt-2 text-sm text-slate-600">
            继续提交会更新当前工作区，而不是创建新的工作区。当前版本：v{{ editingTripVersion }}
          </div>
        </div>
        <button
          type="button"
          class="rounded-full border border-slate-200 bg-white px-5 py-3 text-sm shadow-sm"
          @click="emit('reset')"
        >
          退出并新建规划
        </button>
      </div>
    </article>

    <section class="grid gap-6 xl:grid-cols-[1.18fr_0.82fr]">
      <PlannerRequestForm
        v-model:start-date="startDate"
        v-model:end-date="endDate"
        v-model:must-visit-text="mustVisitText"
        v-model:dining-text="diningText"
        :form="form"
        :interest-options="interestOptions"
        :transport-options="transportOptions"
        :hotel-options="hotelOptions"
        :pace-options="paceOptions"
        :budget-options="budgetOptions"
        :planning-checks="planningChecks"
        :can-submit="canSubmit"
        :submit-hint="submitHint"
        :pace-label="paceLabel"
        :toggle-selection="toggleSelection"
      />
      <div class="flex flex-col gap-6">
        <TravelTonePanel
          :destination="form.destination"
          :interests="form.interests"
          :hotel-style="form.hotel_style"
          :transport-preferences="form.transport_preferences"
        />
        <PlannerLaunchPanel
          :input-summary="inputSummary"
          :progress="progress"
          :progress-label="progressLabel"
          :loading="loading"
          :saving-draft="draftSaving"
          :can-save-draft="canSaveDraft"
          :can-submit="canSubmit"
          :save-draft-hint="saveDraftHint"
          :submit-hint="submitHint"
          :local-draft-saved-at="localDraftSavedAt"
          :local-draft-restored="localDraftRestored"
          compact
          @submit="emit('submit')"
          @save-draft="emit('save-draft')"
        />
        <RecentTripListPanel
          :trips="recentTrips"
          :loading="recentTripsLoading"
          :error="recentTripsError"
          @open="(tripId) => emit('open-recent-trip', tripId)"
          @refresh="emit('refresh-recent-trips')"
        />
        <IntegrationPrecheckPanel
          v-if="showDevPanels"
          :integration-status="currentIntegrationStatus"
          :integration-loading="integrationLoading"
          @refresh="emit('refresh-integration')"
        />
        <PlanningTelemetryPanel
          v-if="showDevPanels"
          :telemetry="telemetry"
          :loading="telemetryLoading"
          :error="telemetryError"
          @refresh="emit('refresh-telemetry')"
        />
      </div>
    </section>
  </section>
</template>
