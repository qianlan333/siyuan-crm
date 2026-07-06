import { normalizeEvidenceStatus, statusMeta } from "../shared/status_model.js";
import { dragPreviewForScenario, executionModeForStatus, guardrailsForScenario, validateDropIntent } from "../shared/interaction_contract.js";
const PUSH_CENTER_STATUS_ALIASES = {
    queued: "pending",
    running: "pending",
    scheduled: "pending",
    succeeded: "sent",
    success: "sent",
    sent: "sent",
    completed: "sent",
    failed: "failed-terminal",
    terminal_failed: "failed-terminal",
    failed_terminal: "failed-terminal",
    retry_due: "retryable",
    retryable: "retryable",
    needs_operator: "operator-action-required",
    operator_action_required: "operator-action-required",
    blocked: "blocked",
    downstream_pending: "downstream-pending",
    evidence_incomplete: "evidence-incomplete",
    governance_missing: "governance-missing",
    external_config_blocked: "external-config-blocked",
    order_linked: "ready"
};
function normalizedRawStatus(rawStatus) {
    return String(rawStatus || "").trim().toLowerCase().replace(/-/g, "_");
}
export function normalizePushCenterStatus(rawStatus, options = {}) {
    const normalized = normalizedRawStatus(rawStatus);
    if (options.operatorActionRequired)
        return "operator-action-required";
    if (options.retryable)
        return "retryable";
    return PUSH_CENTER_STATUS_ALIASES[normalized] ?? normalizeEvidenceStatus(rawStatus);
}
export function toPushCenterScenario(input) {
    return {
        key: input.key,
        title: input.title,
        status: normalizePushCenterStatus(input.rawStatus, {
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
export function buildPushCenterStatusViewModel(input) {
    const scenario = toPushCenterScenario(input);
    const preview = dragPreviewForScenario(scenario);
    const blockedNoop = validateDropIntent(scenario, "blocked_noop");
    return {
        scenario,
        executionMode: executionModeForStatus(scenario.status),
        guardrails: guardrailsForScenario(scenario),
        preview,
        blockedNoop,
        isSuccessComplete: statusMeta(scenario.status).isSuccessComplete,
        operatorPrompt: operatorPromptForStatus(scenario.status)
    };
}
export function operatorPromptForStatus(status) {
    if (status === "operator-action-required")
        return "需要运营处理后才能继续。";
    if (status === "retryable")
        return "任务可重试，但不能显示为完成。";
    if (status === "failed-terminal")
        return "终态失败，不能自动重试。";
    if (status === "downstream-pending")
        return "下游仍待处理，不能显示为已完成。";
    if (status === "governance-missing")
        return "真实发送已取证，但治理证据仍不完整。";
    if (status === "external-config-blocked")
        return "外部配置未生效，不能进入可执行队列。";
    if (status === "evidence-incomplete")
        return "证据仍不完整，需要继续补齐。";
    if (status === "blocked")
        return "当前阻塞，不能执行。";
    return "当前状态只读展示，不绑定真实执行。";
}
export function readonlyDropDoesNotMutate(input) {
    const viewModel = buildPushCenterStatusViewModel(input);
    return viewModel.blockedNoop.allowed === false
        && viewModel.blockedNoop.statusAfterDrop === viewModel.scenario.status;
}
export const PUSH_CENTER_P1_DEFAULT_INPUTS = [
    {
        key: "group_ops",
        title: "Group Ops / Push Center",
        rawStatus: "governance_missing",
        evidenceStatus: "EVIDENCE_COLLECTED",
        derivedStatus: "sent_with_governance_residual_risk",
        summary: "真实发送和 Push Center sent 已成立，但 approval / allowlist / gray-window 治理证据仍未 attach。",
        guardrail: "展示 sent 与 governance_missing 的差异；不得渲染为治理完成。",
        route: "/admin/push-center?section=group_ops"
    },
    {
        key: "ops_plan_broadcast",
        title: "Ops Plan -> Broadcast",
        rawStatus: "downstream_pending",
        evidenceStatus: "EVIDENCE_COLLECTED",
        derivedStatus: "push_center_pending",
        summary: "Next-native cloud_plan 已生成 broadcast_job，并在 Push Center 中保持 pending。",
        guardrail: "显示 downstream-pending；不得显示为 sent 或 completed。",
        route: "/admin/push-center?section=group_broadcast"
    },
    {
        key: "wecom_auth",
        title: "WeCom Auth / Callback",
        rawStatus: "external_config_blocked",
        evidenceStatus: "BLOCKED_CONFIG_NOT_APPROVED",
        derivedStatus: "external_config_exception",
        summary: "企微外部配置尚未批准生效；不可进入可执行任务队列。",
        guardrail: "必须展示 external-config-blocked，不能假装授权完成。",
        route: "/admin/channels"
    },
    {
        key: "external_orders",
        title: "External Orders",
        rawStatus: "order_linked",
        evidenceStatus: "EVIDENCE_COLLECTED",
        derivedStatus: "order_linked",
        summary: "订单链路已完成鉴权、幂等、customer/channel/source、admin visibility 与 Push Center evidence。",
        guardrail: "只读展示 order_linked evidence；不新增外部订单写入。",
        route: "/admin/push-center?section=order"
    }
];
export function defaultPushCenterViewModels() {
    return PUSH_CENTER_P1_DEFAULT_INPUTS.map(buildPushCenterStatusViewModel);
}
