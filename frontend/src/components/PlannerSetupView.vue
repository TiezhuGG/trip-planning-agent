<script setup lang="ts">
import LandingHero from "./LandingHero.vue";
import IntegrationPrecheckPanel from "./IntegrationPrecheckPanel.vue";
import PlanningTelemetryPanel from "./PlanningTelemetryPanel.vue";
import PlannerLaunchPanel from "./PlannerLaunchPanel.vue";
import PlannerRequestForm from "./PlannerRequestForm.vue";
import TravelTonePanel from "./TravelTonePanel.vue";

import type {
  IntegrationStatus,
  PlanningTelemetry,
  TripPlanningRequest,
} from "../types/planning";

type PlannerOption<T> = {
  label: string;
  value: T;
};

const props = defineProps<{
  summaryTags: string[];
  isEditingWorkspace: boolean;
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
  destinationValid: boolean;
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
  (event: "save-draft"): void;
  (event: "refresh-integration"): void;
  (event: "refresh-telemetry"): void;
}>();
</script>

<template>
  <section class="flex min-h-[calc(100vh-3rem)] flex-col justify-center gap-8">
    <LandingHero :summary-tags="summaryTags" />

    <article
      v-if="isEditingWorkspace && editingTripVersion !== null"
      class="rounded-[30px] border border-[#d8e3ee] bg-white/92 px-6 py-5 shadow-card"
    >
      <div class="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div class="text-xs uppercase tracking-[0.24em] text-[#6f7f92]">
            Editing Workspace
          </div>
          <div class="mt-2 text-lg font-semibold text-ink">正在编辑当前行程工作区</div>
          <div class="mt-2 text-sm text-slate-600">
            继续提交会更新当前 trip，而不是创建新的工作区。当前版本：v{{ editingTripVersion }}
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
          :can-submit="destinationValid"
          compact
          @submit="emit('submit')"
          @save-draft="emit('save-draft')"
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
