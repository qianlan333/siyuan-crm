const cards = [
    {
        key: "external_orders",
        title: "External Orders / order linked",
        status: "ready",
        evidenceStatus: "EVIDENCE_COLLECTED",
        derivedStatus: "order_linked",
        summary: "订单链路已有 evidence collected；这不会让全局结论变成 PASS_90_PLUS。",
        guardrail: "只读展示 order_linked；不保存草稿，不写生产。"
    },
    {
        key: "external_orders",
        title: "Push Center / pending",
        status: "pending",
        evidenceStatus: "FIXTURE_PREVIEW",
        derivedStatus: "push_center_pending",
        summary: "待执行任务只能进入 preview_only；不能渲染为 sent 或 completed。",
        guardrail: "requires_push_center / no_direct_send"
    },
    {
        key: "group_ops",
        title: "Push Center / sent",
        status: "sent",
        evidenceStatus: "FIXTURE_PREVIEW",
        derivedStatus: "push_center_sent",
        summary: "sent 只表示主发送链路 evidence 成立；不代表治理记录完整。",
        guardrail: "sent evidence cannot bypass approval or governance checks."
    },
    {
        key: "external_orders",
        title: "Push Center / retryable",
        status: "retryable",
        evidenceStatus: "FIXTURE_PREVIEW",
        derivedStatus: "retryable_failure",
        summary: "可重试状态需要明确下一步运营动作，不能显示为 complete。",
        guardrail: "requires_approval / preview_only"
    },
    {
        key: "group_ops",
        title: "Push Center / operator action",
        status: "operator-action-required",
        evidenceStatus: "FIXTURE_PREVIEW",
        derivedStatus: "operator_action_required",
        summary: "需要运营动作的任务不能通过拖拽进入执行态。",
        guardrail: "requires_approval / no_direct_send"
    },
    {
        key: "group_ops",
        title: "Group Ops / sent evidence",
        status: "sent",
        evidenceStatus: "EVIDENCE_COLLECTED",
        derivedStatus: "external_effect_job:97_sent",
        summary: "Group Ops 真实发送 evidence 已成立，但 governance 仍是独立维度。",
        guardrail: "Push Center sent does not equal governance complete."
    },
    {
        key: "group_ops",
        title: "Group Ops / governance missing",
        status: "governance-missing",
        evidenceStatus: "EVIDENCE_COLLECTED",
        derivedStatus: "approval_allowlist_window_missing",
        summary: "缺 independent approval、receiver allowlist、gray-window 佐证。",
        guardrail: "requires_approval / requires_allowlist / requires_gray_window"
    },
    {
        key: "group_ops",
        title: "Group Ops / evidence incomplete",
        status: "evidence-incomplete",
        evidenceStatus: "EVIDENCE_INCOMPLETE",
        derivedStatus: "governance_evidence_incomplete",
        summary: "证据不完整不能显示为 pass-complete 或 PASS_90_PLUS_CANDIDATE。",
        guardrail: "blocked_noop keeps evidence status unchanged."
    },
    {
        key: "ops_plan_broadcast",
        title: "Ops Plan / downstream pending",
        status: "downstream-pending",
        evidenceStatus: "EVIDENCE_COLLECTED",
        derivedStatus: "broadcast_job:3644_pending",
        summary: "已到 broadcast_job:3644 / Push Center pending；下游 external effect 尚未执行。",
        guardrail: "preview_only / no_external_call"
    },
    {
        key: "ops_plan_broadcast",
        title: "Ops Plan / external effect not created",
        status: "evidence-incomplete",
        evidenceStatus: "EVIDENCE_COLLECTED",
        derivedStatus: "external_effect_job_not_created",
        summary: "broadcast_job created 不等于 external-effect sent。",
        guardrail: "do not render downstream pending as completed."
    },
    {
        key: "wecom_auth",
        title: "WeCom / external config blocked",
        status: "external-config-blocked",
        evidenceStatus: "BLOCKED_CONFIG_NOT_APPROVED",
        derivedStatus: "external_config_blocked",
        summary: "WeCom 外部配置未批准，不能进入可执行队列。",
        guardrail: "requires_external_config / no_external_call"
    },
    {
        key: "wecom_auth",
        title: "WeCom / callback fail closed",
        status: "blocked",
        evidenceStatus: "FAIL_CLOSED",
        derivedStatus: "callback_fail_closed",
        summary: "callback fail-closed 只能说明安全失败，不能显示为 callback success。",
        guardrail: "blocked_noop / no_production_write"
    },
    {
        key: "wecom_auth",
        title: "WeCom / missing evidence",
        status: "evidence-incomplete",
        evidenceStatus: "EVIDENCE_INCOMPLETE",
        derivedStatus: "missing_auth_record_signature_permission_scope",
        summary: "缺 valid signature、auth record、internal event、permission scope evidence。",
        guardrail: "cannot render as authorized or complete."
    }
];
export const P1_PREVIEW_BOARD_FIXTURE = {
    summary: {
        globalVerdict: "P1_READY_WITH_EXCEPTIONS",
        canClaimPass90Plus: false,
        previewOnly: true,
        productionWriteExecuted: false,
        realExternalCallExecuted: false
    },
    payload: {
        finalVerdict: "P1_READY_WITH_EXCEPTIONS",
        canClaimPass90Plus: false,
        scenarios: cards
    }
};
