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

export interface GroupOpsStatusInput {
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

export interface GroupOpsStatusViewModel {
  scenario: ScenarioEvidence;
  evidenceId: string;
  executionMode: ExecutionMode;
  guardrails: InteractionGuardrail[];
  preview: DragPreviewState;
  blockedNoop: DropValidationResult;
  isSuccessComplete: boolean;
  operatorPrompt: string;
}

const GROUP_OPS_STATUS_ALIASES: Record<string, EvidenceStatus> = {
  sent: "sent",
  succeeded: "sent",
  succeeded_send_path: "sent",
  governance_missing: "governance-missing",
  evidence_incomplete: "evidence-incomplete",
  operator_action_required: "operator-action-required",
  blocked: "blocked",
  retryable: "retryable",
  failed_terminal: "failed-terminal",
  failed: "failed-terminal"
};

function normalizeRawStatus(rawStatus: string): string {
  return String(rawStatus || "").trim().toLowerCase().replace(/-/g, "_");
}

export function normalizeGroupOpsStatus(
  rawStatus: string,
  options: { retryable?: boolean; operatorActionRequired?: boolean } = {}
): EvidenceStatus {
  if (options.operatorActionRequired) return "operator-action-required";
  if (options.retryable) return "retryable";
  return GROUP_OPS_STATUS_ALIASES[normalizeRawStatus(rawStatus)] ?? normalizeEvidenceStatus(rawStatus);
}

export function toGroupOpsScenario(input: GroupOpsStatusInput): ScenarioEvidence {
  return {
    key: "group_ops",
    title: input.title,
    status: normalizeGroupOpsStatus(input.rawStatus, {
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

export function buildGroupOpsStatusViewModel(input: GroupOpsStatusInput): GroupOpsStatusViewModel {
  const scenario = toGroupOpsScenario(input);
  const preview = dragPreviewForScenario(scenario);
  const blockedNoop = validateDropIntent(scenario, "blocked_noop");
  return {
    scenario,
    evidenceId: input.evidenceId || scenario.derivedStatus,
    executionMode: executionModeForStatus(scenario.status),
    guardrails: groupOpsGuardrailsForScenario(scenario),
    preview,
    blockedNoop,
    isSuccessComplete: statusMeta(scenario.status).isSuccessComplete,
    operatorPrompt: groupOpsPromptForStatus(scenario.status)
  };
}

export function groupOpsGuardrailsForScenario(scenario: ScenarioEvidence): InteractionGuardrail[] {
  const guardrails = new Set<InteractionGuardrail>(guardrailsForScenario(scenario));
  guardrails.add("requires_push_center");
  guardrails.add("no_direct_send");
  guardrails.add("no_external_call");
  guardrails.add("no_production_write");
  if (scenario.status === "governance-missing" || scenario.status === "evidence-incomplete") {
    guardrails.add("requires_approval");
    guardrails.add("requires_allowlist");
    guardrails.add("requires_gray_window");
  }
  return Array.from(guardrails);
}

export function groupOpsPromptForStatus(status: EvidenceStatus): string {
  if (status === "sent") return "发送链路 evidence 成立；这不代表 governance 完整。";
  if (status === "governance-missing") return "缺 independent approval / receiver allowlist / gray-window 记录。";
  if (status === "evidence-incomplete") return "证据仍不完整，不能进入 90%+ 候选。";
  if (status === "operator-action-required") return "需要运营补充动作后才能继续。";
  if (status === "retryable") return "可重试，但不能显示为完成。";
  if (status === "failed-terminal") return "终态失败，不能自动重试。";
  if (status === "blocked") return "当前阻塞，不能执行。";
  return "只读展示，不绑定真实发送、审批或名单配置。";
}

export function groupOpsSentIsGovernanceComplete(input: GroupOpsStatusInput): boolean {
  const viewModel = buildGroupOpsStatusViewModel(input);
  return viewModel.scenario.status === "sent" && viewModel.scenario.derivedStatus === "governance_complete";
}

export function readonlyGroupOpsDropDoesNotMutate(input: GroupOpsStatusInput): boolean {
  const viewModel = buildGroupOpsStatusViewModel(input);
  return viewModel.blockedNoop.allowed === false
    && viewModel.blockedNoop.statusAfterDrop === viewModel.scenario.status;
}

export const GROUP_OPS_P1_DEFAULT_INPUTS: GroupOpsStatusInput[] = [
  {
    title: "发送链路证据",
    rawStatus: "sent",
    evidenceStatus: "EVIDENCE_COLLECTED",
    derivedStatus: "push_center_sent",
    evidenceId: "external_effect_job:97",
    summary: "external_effect_job:97 已在 Push Center 显示 sent；retryable=false，operator_action_required=false。",
    guardrail: "sent 只表示发送链路 evidence 成立，不代表 governance 完整。",
    route: "/api/admin/push-center/jobs/external_effect_job:97/reconciliation"
  },
  {
    title: "治理证据",
    rawStatus: "governance_missing",
    evidenceStatus: "EVIDENCE_COLLECTED",
    derivedStatus: "governance_residual_risk",
    evidenceId: "approval_allowlist_window",
    summary: "独立 operator approval、receiver allowlist、gray-window approval 记录仍未 attach。",
    guardrail: "必须显示 requires_approval / requires_allowlist / requires_gray_window。",
    route: "docs/reports/evidence/group_ops_gray_send_approval_allowlist_window_supplement_20260623.md"
  },
  {
    title: "最终判定",
    rawStatus: "evidence_incomplete",
    evidenceStatus: "EVIDENCE_COLLECTED",
    derivedStatus: "not_pass_90_plus_candidate",
    evidenceId: "business_closure_exception",
    summary: "Group Ops 保持 EVIDENCE_COLLECTED，不是 PASS_90_PLUS_CANDIDATE。",
    guardrail: "证据不完整不能渲染为 pass-complete。",
    route: "docs/reports/business_closure_final_p1_readiness_20260623.md"
  }
];

export function defaultGroupOpsViewModels(): GroupOpsStatusViewModel[] {
  return GROUP_OPS_P1_DEFAULT_INPUTS.map(buildGroupOpsStatusViewModel);
}
