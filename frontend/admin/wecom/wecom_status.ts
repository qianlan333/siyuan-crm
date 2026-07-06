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

export interface WeComStatusInput {
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

export interface WeComStatusViewModel {
  scenario: ScenarioEvidence;
  evidenceId: string;
  executionMode: ExecutionMode;
  guardrails: InteractionGuardrail[];
  preview: DragPreviewState;
  blockedNoop: DropValidationResult;
  isSuccessComplete: boolean;
  operatorPrompt: string;
}

const WECOM_STATUS_ALIASES: Record<string, EvidenceStatus> = {
  external_config_blocked: "external-config-blocked",
  config_not_approved: "external-config-blocked",
  auth_start_blocked: "external-config-blocked",
  callback_blocked: "external-config-blocked",
  callback_fail_closed: "blocked",
  fail_closed: "blocked",
  missing_signature: "evidence-incomplete",
  missing_valid_signature: "evidence-incomplete",
  missing_auth_record: "evidence-incomplete",
  missing_internal_event: "evidence-incomplete",
  missing_permission_scope: "evidence-incomplete",
  evidence_incomplete: "evidence-incomplete",
  operator_action_required: "operator-action-required",
  blocked: "blocked",
  failed_terminal: "failed-terminal",
  failed: "failed-terminal",
  pending: "pending",
  authorized: "ready",
  ready: "ready"
};

function normalizeRawStatus(rawStatus: string): string {
  return String(rawStatus || "").trim().toLowerCase().replace(/-/g, "_");
}

export function normalizeWeComStatus(
  rawStatus: string,
  options: { retryable?: boolean; operatorActionRequired?: boolean } = {}
): EvidenceStatus {
  if (options.operatorActionRequired) return "operator-action-required";
  if (options.retryable) return "retryable";
  return WECOM_STATUS_ALIASES[normalizeRawStatus(rawStatus)] ?? normalizeEvidenceStatus(rawStatus);
}

export function toWeComScenario(input: WeComStatusInput): ScenarioEvidence {
  return {
    key: "wecom_auth",
    title: input.title,
    status: normalizeWeComStatus(input.rawStatus, {
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

export function weComGuardrailsForScenario(scenario: ScenarioEvidence): InteractionGuardrail[] {
  const guardrails = new Set<InteractionGuardrail>(guardrailsForScenario(scenario));
  guardrails.add("requires_external_config");
  guardrails.add("no_direct_send");
  guardrails.add("no_external_call");
  guardrails.add("no_production_write");
  return Array.from(guardrails);
}

export function buildWeComStatusViewModel(input: WeComStatusInput): WeComStatusViewModel {
  const scenario = toWeComScenario(input);
  const preview = dragPreviewForScenario(scenario);
  const blockedNoop = validateDropIntent(scenario, "blocked_noop");
  return {
    scenario,
    evidenceId: input.evidenceId || scenario.derivedStatus,
    executionMode: executionModeForStatus(scenario.status),
    guardrails: weComGuardrailsForScenario(scenario),
    preview,
    blockedNoop,
    isSuccessComplete: statusMeta(scenario.status).isSuccessComplete,
    operatorPrompt: weComPromptForStatus(scenario.status)
  };
}

export function weComPromptForStatus(status: EvidenceStatus): string {
  if (status === "external-config-blocked") return "外部配置未批准生效；不能显示为授权完成，也不能进入可执行队列。";
  if (status === "blocked") return "Callback fail-closed 是安全阻塞，不是回调成功。";
  if (status === "evidence-incomplete") return "缺 valid callback signature / auth record / internal_event / permission scope evidence，不能显示为 complete。";
  if (status === "operator-action-required") return "需要 operator 完成 git 外配置和 evidence window。";
  if (status === "failed-terminal") return "终态失败，不能自动重试。";
  if (status === "pending") return "仍待配置或 evidence，不代表授权完成。";
  return "只读展示，不绑定真实授权、callback、配置写入或外呼。";
}

export function externalConfigBlockedIsAuthorized(input: WeComStatusInput): boolean {
  const viewModel = buildWeComStatusViewModel(input);
  return viewModel.scenario.status === "ready"
    && viewModel.scenario.derivedStatus === "authorized";
}

export function callbackFailClosedIsSuccess(input: WeComStatusInput): boolean {
  const viewModel = buildWeComStatusViewModel(input);
  return viewModel.scenario.status === "ready"
    && viewModel.scenario.derivedStatus === "callback_success";
}

export function missingSignatureIsVerified(input: WeComStatusInput): boolean {
  const viewModel = buildWeComStatusViewModel(input);
  return viewModel.scenario.status === "ready"
    && viewModel.scenario.derivedStatus === "signature_verified";
}

export function missingWeComEvidenceIsComplete(input: WeComStatusInput): boolean {
  const viewModel = buildWeComStatusViewModel(input);
  return viewModel.isSuccessComplete
    && viewModel.scenario.derivedStatus === "wecom_complete";
}

export function readonlyWeComDropDoesNotMutate(input: WeComStatusInput): boolean {
  const viewModel = buildWeComStatusViewModel(input);
  return viewModel.blockedNoop.allowed === false
    && viewModel.blockedNoop.statusAfterDrop === viewModel.scenario.status;
}

export const WECOM_P1_DEFAULT_INPUTS: WeComStatusInput[] = [
  {
    title: "Auth start",
    rawStatus: "external_config_blocked",
    evidenceStatus: "BLOCKED_CONFIG_NOT_APPROVED",
    derivedStatus: "external_call_blocked_503",
    evidenceId: "/auth/wecom/start",
    summary: "/auth/wecom/start 可达，但 controlled external_call_blocked 503；未进入真实 redirect/auth flow。",
    guardrail: "external-config-blocked 不能显示为授权完成。",
    route: "docs/reports/evidence/wecom_auth_callback_operator_evidence_20260623.md"
  },
  {
    title: "Auth callback",
    rawStatus: "external_config_blocked",
    evidenceStatus: "BLOCKED_CONFIG_NOT_APPROVED",
    derivedStatus: "callback_external_call_blocked_503",
    evidenceId: "/auth/wecom/callback",
    summary: "/auth/wecom/callback 可达，但 controlled external_call_blocked 503；没有 auth/callback record。",
    guardrail: "controlled blocked 不是授权完成。",
    route: "docs/reports/evidence/wecom_auth_callback_operator_evidence_20260623.md"
  },
  {
    title: "External contact callback",
    rawStatus: "callback_fail_closed",
    evidenceStatus: "EVIDENCE_COLLECTED_NOT_READY",
    derivedStatus: "missing_signature_fail_closed_400",
    evidenceId: "/wecom/external-contact/callback",
    summary: "缺签名时 fail-closed 400；没有 valid callback signature evidence。",
    guardrail: "fail-closed 不能显示为 callback success。",
    route: "docs/reports/evidence/wecom_auth_callback_evidence_20260623.md"
  },
  {
    title: "Admin event visibility",
    rawStatus: "evidence_incomplete",
    evidenceStatus: "EVIDENCE_COLLECTED_NOT_READY",
    derivedStatus: "no_callback_linked_event_found",
    evidenceId: "/api/admin/internal-events",
    summary: "admin internal events 查询可达，但 no callback-linked event / idempotency / permission scope evidence。",
    guardrail: "缺 auth record、internal_event、permission scope 不能显示为 complete。",
    route: "/api/admin/internal-events"
  }
];

export function defaultWeComViewModels(): WeComStatusViewModel[] {
  return WECOM_P1_DEFAULT_INPUTS.map(buildWeComStatusViewModel);
}
