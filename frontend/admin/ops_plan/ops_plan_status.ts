import {
  type EvidenceStatus,
  type ScenarioEvidence,
  normalizeEvidenceStatus,
  statusMeta
} from "../shared/status_model.js";
import {
  type DropValidationResult,
  type DragPreviewState,
  type ExecutionMode,
  type InteractionGuardrail,
  dragPreviewForScenario,
  executionModeForStatus,
  guardrailsForScenario,
  validateDropIntent
} from "../shared/interaction_contract.js";

export interface OpsPlanStatusInput {
  title: string;
  rawStatus: string;
  evidenceStatus: string;
  derivedStatus: string;
  summary: string;
  guardrail: string;
  evidenceId?: string;
  route?: string;
  retryable?: boolean;
  operatorActionRequired?: boolean;
}

export interface OpsPlanStatusViewModel {
  scenario: ScenarioEvidence;
  evidenceId: string;
  executionMode: ExecutionMode;
  guardrails: InteractionGuardrail[];
  preview: DragPreviewState;
  blockedNoop: DropValidationResult;
  isSuccessComplete: boolean;
  operatorPrompt: string;
}

const OPS_PLAN_STATUS_ALIASES: Record<string, EvidenceStatus> = {
  approval_event_created: "pending",
  planner_created_broadcast_job: "downstream-pending",
  broadcast_job_created: "downstream-pending",
  push_center_pending: "downstream-pending",
  downstream_pending: "downstream-pending",
  external_effect_not_created: "evidence-incomplete",
  evidence_incomplete: "evidence-incomplete",
  pending: "pending",
  sent: "sent",
  succeeded: "sent",
  blocked: "blocked",
  retryable: "retryable",
  operator_action_required: "operator-action-required",
  failed_terminal: "failed-terminal",
  failed: "failed-terminal"
};

function normalizeRawStatus(rawStatus: string): string {
  return String(rawStatus || "").trim().toLowerCase().replace(/-/g, "_");
}

export function normalizeOpsPlanStatus(
  rawStatus: string,
  options: { retryable?: boolean; operatorActionRequired?: boolean } = {}
): EvidenceStatus {
  if (options.operatorActionRequired) return "operator-action-required";
  if (options.retryable) return "retryable";
  return OPS_PLAN_STATUS_ALIASES[normalizeRawStatus(rawStatus)] ?? normalizeEvidenceStatus(rawStatus);
}

export function toOpsPlanScenario(input: OpsPlanStatusInput): ScenarioEvidence {
  return {
    key: "ops_plan_broadcast",
    title: input.title,
    status: normalizeOpsPlanStatus(input.rawStatus, {
      retryable: input.retryable,
      operatorActionRequired: input.operatorActionRequired
    }),
    evidenceStatus: input.evidenceStatus,
    derivedStatus: input.derivedStatus,
    summary: input.summary,
    guardrail: input.guardrail,
    route: input.route
  };
}

export function opsPlanGuardrailsForScenario(scenario: ScenarioEvidence): InteractionGuardrail[] {
  const guardrails = new Set<InteractionGuardrail>(guardrailsForScenario(scenario));
  guardrails.add("requires_push_center");
  guardrails.add("no_direct_send");
  guardrails.add("no_external_call");
  guardrails.add("no_production_write");
  return Array.from(guardrails);
}

export function buildOpsPlanStatusViewModel(input: OpsPlanStatusInput): OpsPlanStatusViewModel {
  const scenario = toOpsPlanScenario(input);
  const preview = dragPreviewForScenario(scenario);
  const blockedNoop = validateDropIntent(scenario, "blocked_noop");
  return {
    scenario,
    evidenceId: input.evidenceId || scenario.derivedStatus,
    executionMode: executionModeForStatus(scenario.status),
    guardrails: opsPlanGuardrailsForScenario(scenario),
    preview,
    blockedNoop,
    isSuccessComplete: statusMeta(scenario.status).isSuccessComplete,
    operatorPrompt: opsPlanPromptForStatus(scenario.status)
  };
}

export function opsPlanPromptForStatus(status: EvidenceStatus): string {
  if (status === "downstream-pending") return "Planner 已到 broadcast_job / Push Center pending；下游 external effect 尚未执行，不能显示为 completed。";
  if (status === "pending") return "事件或 projection 仍待处理，不能显示为 sent。";
  if (status === "sent") return "仅当 external effect sent evidence 成立时才可显示为 sent。";
  if (status === "operator-action-required") return "需要运营动作后才能继续。";
  if (status === "retryable") return "可重试，但不能显示为完成。";
  if (status === "failed-terminal") return "终态失败，不能自动重试。";
  if (status === "blocked") return "当前阻塞，不能执行。";
  if (status === "evidence-incomplete") return "缺少下游 evidence，不能渲染为 pass-complete。";
  return "只读展示，不绑定审批、任务执行或外呼。";
}

export function pushCenterPendingIsSent(input: OpsPlanStatusInput): boolean {
  const viewModel = buildOpsPlanStatusViewModel(input);
  return viewModel.scenario.derivedStatus === "push_center_sent"
    && viewModel.scenario.status === "sent";
}

export function broadcastJobCreatedIsExternalEffectSent(input: OpsPlanStatusInput): boolean {
  const viewModel = buildOpsPlanStatusViewModel(input);
  return viewModel.scenario.derivedStatus === "external_effect_sent"
    && viewModel.scenario.status === "sent";
}

export function readonlyOpsPlanDropDoesNotMutate(input: OpsPlanStatusInput): boolean {
  const viewModel = buildOpsPlanStatusViewModel(input);
  return viewModel.blockedNoop.allowed === false
    && viewModel.blockedNoop.statusAfterDrop === viewModel.scenario.status;
}

export const OPS_PLAN_P1_DEFAULT_INPUTS: OpsPlanStatusInput[] = [
  {
    title: "Approval event",
    rawStatus: "pending",
    evidenceStatus: "EVIDENCE_COLLECTED",
    derivedStatus: "ops_plan_approved_event_created",
    evidenceId: "ops_plan.approved",
    summary: "Next-native cloud_plan approval 已生成 ops_plan.approved internal_event。",
    guardrail: "approval evidence 只表示事件存在，不代表下游发送完成。",
    route: "docs/reports/evidence/ops_plan_to_broadcast_next_native_cloud_plan_e2e_20260623.md"
  },
  {
    title: "Planner consumer",
    rawStatus: "planner_created_broadcast_job",
    evidenceStatus: "EVIDENCE_COLLECTED",
    derivedStatus: "planner_created_broadcast_job",
    evidenceId: "broadcast_task_planner_consumer",
    summary: "broadcast_task_planner_consumer succeeded，并幂等创建 broadcast_job:3644。",
    guardrail: "broadcast_job created 不等于 external-effect sent。",
    route: "docs/reports/evidence/ops_plan_to_broadcast_next_native_cloud_plan_e2e_20260623.md"
  },
  {
    title: "Push Center projection",
    rawStatus: "push_center_pending",
    evidenceStatus: "EVIDENCE_COLLECTED",
    derivedStatus: "push_center_pending",
    evidenceId: "broadcast_job:3644",
    summary: "broadcast_job:3644 已在 Push Center 中显示 pending / 待执行。",
    guardrail: "Push Center pending 不能显示为 sent 或 completed。",
    route: "/admin/push-center?section=group_broadcast"
  },
  {
    title: "Downstream external effect",
    rawStatus: "external_effect_not_created",
    evidenceStatus: "EVIDENCE_COLLECTED",
    derivedStatus: "not_pass_90_plus_candidate",
    evidenceId: "external_effect_job:not_created",
    summary: "external_effect_job 尚未创建，real external call=false；最终状态不是 90%+ 候选。",
    guardrail: "缺下游 external effect evidence 不能渲染为 pass-complete。",
    route: "docs/reports/business_closure_final_p1_readiness_20260623.md"
  }
];

export function defaultOpsPlanViewModels(): OpsPlanStatusViewModel[] {
  return OPS_PLAN_P1_DEFAULT_INPUTS.map(buildOpsPlanStatusViewModel);
}
