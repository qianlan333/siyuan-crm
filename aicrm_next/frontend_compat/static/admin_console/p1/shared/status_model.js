export const STATUS_META = {
    ready: { label: "就绪", tone: "success", isSuccessComplete: true },
    pending: { label: "待处理", tone: "info", isSuccessComplete: false },
    sent: { label: "已发送", tone: "success", isSuccessComplete: true },
    blocked: { label: "阻塞", tone: "danger", isSuccessComplete: false },
    "external-config-blocked": { label: "外部配置阻塞", tone: "danger", isSuccessComplete: false },
    "governance-missing": { label: "治理证据缺失", tone: "warning", isSuccessComplete: false },
    "evidence-incomplete": { label: "证据不完整", tone: "warning", isSuccessComplete: false },
    "downstream-pending": { label: "下游待执行", tone: "info", isSuccessComplete: false },
    "operator-action-required": { label: "需要运营动作", tone: "warning", isSuccessComplete: false },
    retryable: { label: "可重试", tone: "warning", isSuccessComplete: false },
    "failed-terminal": { label: "终态失败", tone: "danger", isSuccessComplete: false }
};
const NORMALIZED_STATUS = {
    ready: "ready",
    pending: "pending",
    sent: "sent",
    blocked: "blocked",
    external_config_blocked: "external-config-blocked",
    "external-config-blocked": "external-config-blocked",
    governance_missing: "governance-missing",
    "governance-missing": "governance-missing",
    evidence_incomplete: "evidence-incomplete",
    "evidence-incomplete": "evidence-incomplete",
    downstream_pending: "downstream-pending",
    "downstream-pending": "downstream-pending",
    operator_action_required: "operator-action-required",
    "operator-action-required": "operator-action-required",
    retryable: "retryable",
    failed_terminal: "failed-terminal",
    "failed-terminal": "failed-terminal"
};
export function normalizeEvidenceStatus(rawStatus) {
    return NORMALIZED_STATUS[rawStatus] ?? "evidence-incomplete";
}
export function statusMeta(status) {
    return STATUS_META[status];
}
export function canRenderGlobalPass(payload) {
    return payload.finalVerdict === "PASS_90_PLUS"
        && payload.canClaimPass90Plus === true
        && payload.scenarios.every((scenario) => statusMeta(scenario.status).isSuccessComplete);
}
export function scenarioNeedsOperatorAction(scenario) {
    return scenario.status === "operator-action-required"
        || scenario.status === "governance-missing"
        || scenario.status === "external-config-blocked"
        || scenario.status === "retryable";
}
