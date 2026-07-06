import { createUnavailableWorkspaceFixture } from "./workspace_fixture.js";
function text(value) {
    return String(value ?? "").trim();
}
function intValue(value) {
    const parsed = Number.parseInt(text(value), 10);
    return Number.isFinite(parsed) ? Math.max(0, parsed) : 0;
}
function asRecord(value) {
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}
function asArray(value) {
    return Array.isArray(value) ? value : [];
}
function normalizePlanStatus(rawStatus) {
    const status = text(rawStatus).toLowerCase();
    if (status === "active" || status === "enabled")
        return "ready";
    if (status === "disabled" || status === "paused")
        return "blocked";
    if (status === "archived" || status === "deleted")
        return "failed-terminal";
    return "pending";
}
function normalizePushCenterStatus(rawStatus, retryable = false, operatorActionRequired = false) {
    const status = text(rawStatus).toLowerCase().replace(/_/g, "-");
    if (operatorActionRequired)
        return "operator-action-required";
    if (retryable)
        return "retryable";
    if (status === "sent" || status === "succeeded" || status === "success")
        return "sent";
    if (status === "failed-terminal" || status === "terminal-failed")
        return "failed-terminal";
    if (status === "blocked")
        return "blocked";
    if (status === "pending" || status === "queued" || status === "running")
        return "pending";
    return "evidence-incomplete";
}
function firstPlan(payload) {
    const item = asArray(payload.items)[0];
    return item ? asRecord(item) : null;
}
function sourceStatus(...payloads) {
    for (const payload of payloads) {
        const value = text(payload.source_status);
        if (value)
            return value;
    }
    return "read_only_api";
}
function planId(plan) {
    return intValue(plan?.id);
}
function planName(plan) {
    return text(plan?.plan_name || plan?.name) || "Group Ops plan";
}
function groupSummary(detail, groupsPayload, listPlan) {
    const detailSummary = asRecord(detail.groups_summary);
    const groupsSummary = asRecord(groupsPayload.summary);
    return {
        bound_group_count: intValue(detailSummary.bound_group_count ?? groupsSummary.bound_group_count ?? listPlan?.bound_group_count),
        estimated_reach: intValue(detailSummary.estimated_reach ?? groupsSummary.estimated_reach ?? listPlan?.today_estimated_reach),
        internal_member_count: intValue(detailSummary.internal_member_count ?? groupsSummary.internal_member_count),
        external_member_count: intValue(detailSummary.external_member_count ?? groupsSummary.external_member_count)
    };
}
function firstPushCenterItem(payload) {
    const item = asArray(payload.items)[0];
    return item ? asRecord(item) : null;
}
function firstNode(detail, nodes) {
    const item = asArray(nodes.items)[0] || asArray(detail.nodes)[0];
    return item ? asRecord(item) : null;
}
function firstExecution(executions) {
    const item = asArray(executions.items)[0];
    return item ? asRecord(item) : null;
}
function detailId(entityType, id) {
    return `${entityType}-${text(id) || "unknown"}`;
}
function field(label, value) {
    return { label, value: text(value) || "not_found" };
}
function detailItem(entityType, id, title, status, evidenceStatus, derivedStatus, summary, guardrail, fields) {
    return {
        id: detailId(entityType, id),
        entityType,
        title,
        status,
        evidenceStatus,
        derivedStatus,
        summary,
        guardrail,
        fields
    };
}
function pushCenterProjectionId(pushItem) {
    return text(pushItem?.projection_id || pushItem?.id || pushItem?.display_id) || "not_found";
}
function defaultSelectionForPlan(plan, pushItem) {
    const id = String(planId(plan));
    return {
        selectedPlanId: detailId("plan", id),
        selectedGroupId: detailId("group", `plan-${id}`),
        selectedNodeId: detailId("node", `plan-${id}`),
        selectedExecutionId: detailId("execution", `plan-${id}`),
        selectedPushCenterJobId: detailId("push_center", pushCenterProjectionId(pushItem)),
        selectedEntityType: "plan"
    };
}
function leftRailFromRealData(plan, detail, groups, nodes, executions, pushCenter) {
    const summary = groupSummary(detail, groups, plan);
    const nodeCount = asArray(nodes.items ?? detail.nodes).length;
    const executionTotal = intValue(executions.total);
    const pushItem = firstPushCenterItem(pushCenter);
    const pushStatus = pushItem
        ? normalizePushCenterStatus(pushItem.effective_status || pushItem.status || pushItem.raw_status, Boolean(pushItem.retryable), Boolean(pushItem.operator_action_required))
        : "evidence-incomplete";
    return [
        {
            id: `plan-${planId(plan)}`,
            label: planName(plan),
            kind: "plan",
            entityType: "plan",
            detailId: detailId("plan", planId(plan)),
            status: normalizePlanStatus(plan.status),
            summary: `${text(plan.plan_type) || "standard"} / ${text(plan.status) || "unknown"} / 只读绑定`
        },
        {
            id: `audience-plan-${planId(plan)}`,
            label: "Audience / receiver summary",
            kind: "group",
            entityType: "group",
            detailId: detailId("group", `plan-${planId(plan)}`),
            status: intValue(summary.bound_group_count) > 0 ? "ready" : "evidence-incomplete",
            summary: `${intValue(summary.bound_group_count)} 个绑定群，预计触达 ${intValue(summary.estimated_reach)}；不展示 raw receiver 或群成员标识。`
        },
        {
            id: `task-plan-${planId(plan)}`,
            label: "Task / content summary",
            kind: "node",
            entityType: "node",
            detailId: detailId("node", `plan-${planId(plan)}`),
            status: nodeCount > 0 ? "pending" : "evidence-incomplete",
            summary: `${nodeCount} 个动作节点，${executionTotal} 条执行记录；preview-only，不执行任务。`
        },
        {
            id: `execution-plan-${planId(plan)}`,
            label: "Execution summary",
            kind: "execution",
            entityType: "execution",
            detailId: detailId("execution", `plan-${planId(plan)}`),
            status: executionTotal > 0 ? "pending" : "evidence-incomplete",
            summary: `${executionTotal} 条执行记录；只显示状态摘要，不展示 receiver 或成员标识。`
        },
        {
            id: `push-center-plan-${planId(plan)}`,
            label: "Push Center linked status",
            kind: "push_center",
            entityType: "push_center",
            detailId: detailId("push_center", pushCenterProjectionId(pushItem)),
            status: pushStatus,
            summary: pushItem ? "找到只读 Push Center projection；详情仍需通过 Push Center gate 解释。" : "未找到 linked Push Center projection，不能伪造成 sent。"
        },
        {
            id: `evidence-plan-${planId(plan)}-governance`,
            label: "Evidence / guardrails",
            kind: "evidence",
            entityType: "evidence",
            detailId: detailId("evidence", `plan-${planId(plan)}-governance`),
            status: "governance-missing",
            summary: "发送或 projection evidence 不代表 governance complete；approval / allowlist / gray-window 仍需 attach。"
        }
    ];
}
function detailsFromRealData(plan, detail, groups, nodes, executions, pushCenter) {
    const id = planId(plan);
    const summary = groupSummary(detail, groups, plan);
    const node = firstNode(detail, nodes);
    const execution = firstExecution(executions);
    const pushItem = firstPushCenterItem(pushCenter);
    const nodeCount = asArray(nodes.items ?? detail.nodes).length;
    const executionTotal = intValue(executions.total);
    const pushStatus = pushItem
        ? normalizePushCenterStatus(pushItem.effective_status || pushItem.status || pushItem.raw_status, Boolean(pushItem.retryable), Boolean(pushItem.operator_action_required))
        : "evidence-incomplete";
    const executionStatus = execution
        ? normalizePushCenterStatus(execution.status || execution.execution_status || execution.raw_status)
        : "evidence-incomplete";
    return [
        detailItem("plan", id, planName(plan), normalizePlanStatus(plan.status), "REAL_DATA_BOUND", `plan_${id}_readonly`, "计划详情为只读绑定；不审批、不保存、不发送。", "draft-only / preview-only；必须继续走 approval / allowlist / Push Center gates。", [
            field("plan_id", id),
            field("plan_name", planName(plan)),
            field("plan_type", plan.plan_type || "standard"),
            field("status", plan.status || "unknown"),
            field("node_count", nodeCount),
            field("execution_count", executionTotal)
        ]),
        detailItem("group", `plan-${id}`, "Audience / receiver summary", intValue(summary.bound_group_count) > 0 ? "ready" : "evidence-incomplete", "REAL_DATA_BOUND", "receiver_summary_redacted", "只展示人群聚合统计，不展示 receiver、群、成员或客户明文。", "requires_allowlist / no_direct_send。", [
            field("bound_group_count", summary.bound_group_count),
            field("estimated_reach", summary.estimated_reach),
            field("internal_member_count", summary.internal_member_count),
            field("external_member_count", summary.external_member_count),
            field("sensitive_data", "redacted")
        ]),
        detailItem("node", `plan-${id}`, "Node / task summary", nodeCount > 0 ? "pending" : "evidence-incomplete", nodeCount > 0 ? "REAL_DATA_BOUND" : "EVIDENCE_INCOMPLETE", `nodes_${nodeCount}`, "节点详情只展示类型、状态与数量；不展示消息正文或接收人明文。", "preview_only / no_external_call / no_production_write。", [
            field("node_id", node?.id || "not_found"),
            field("node_type", node?.node_type || node?.action_type || "not_found"),
            field("action_title", node?.action_title || "redacted_or_not_found"),
            field("node_count", nodeCount),
            field("execution", "not_triggered_by_workspace")
        ]),
        detailItem("execution", `plan-${id}`, "Execution summary", executionStatus, execution ? "REAL_DATA_BOUND" : "EVIDENCE_INCOMPLETE", execution ? `execution_${text(execution.id) || "found"}` : "execution_not_found", execution ? "执行记录只读可见；状态不代表 workspace 执行过发送。" : "未找到执行记录；保持 evidence-incomplete。", "preview_only / no_direct_send。", [
            field("execution_id", execution?.id || "not_found"),
            field("execution_status", execution?.status || execution?.execution_status || "not_found"),
            field("attempt_count", execution?.attempt_count || "not_found"),
            field("real_external_call", "false")
        ]),
        detailItem("push_center", pushCenterProjectionId(pushItem), "Push Center projection summary", pushStatus, pushItem ? "REAL_DATA_BOUND" : "EVIDENCE_INCOMPLETE", pushCenterProjectionId(pushItem), pushItem ? "Push Center projection 只读可见；sent 不等于 governance complete。" : "未找到 Push Center projection，不能伪造成 sent。", "requires_push_center / no_direct_send。", [
            field("projection_id", pushCenterProjectionId(pushItem)),
            field("push_center_status", pushItem?.effective_status || pushItem?.status || "not_found"),
            field("retryable", pushItem?.retryable ?? "not_found"),
            field("operator_action_required", pushItem?.operator_action_required ?? "not_found"),
            field("can_claim_pass_90_plus", "false")
        ]),
        detailItem("evidence", `plan-${id}-governance`, "Evidence / guardrail summary", "governance-missing", "EVIDENCE_COLLECTED", "approval_allowlist_window_missing", "发送或 projection evidence 不代表治理证据完整。", "requires_approval / requires_allowlist / requires_gray_window。", [
            field("approval_evidence", "missing"),
            field("allowlist_evidence", "missing"),
            field("gray_window_evidence", "missing"),
            field("sent_bypasses_governance", "false")
        ])
    ];
}
function scenariosFromRealData(plan, detail, groups, nodes, executions, pushCenter) {
    const summary = groupSummary(detail, groups, plan);
    const nodeCount = asArray(nodes.items ?? detail.nodes).length;
    const executionTotal = intValue(executions.total);
    const pushItem = firstPushCenterItem(pushCenter);
    const pushStatus = pushItem
        ? normalizePushCenterStatus(pushItem.effective_status || pushItem.status || pushItem.raw_status, Boolean(pushItem.retryable), Boolean(pushItem.operator_action_required))
        : "evidence-incomplete";
    const pushDerived = pushItem ? text(pushItem.projection_id || pushItem.id || pushItem.display_id) || "push_center_projection_found" : "push_center_not_linked";
    return [
        {
            key: "group_ops",
            title: `计划：${planName(plan)}`,
            status: normalizePlanStatus(plan.status),
            evidenceStatus: "REAL_DATA_BOUND",
            derivedStatus: `plan_${planId(plan)}_readonly`,
            summary: `${intValue(summary.bound_group_count)} 个绑定群，预计触达 ${intValue(summary.estimated_reach)}；真实数据只读展示。`,
            guardrail: "只读绑定计划状态；不保存、不审批、不发送。",
            route: `/admin/automation-conversion/group-ops/plans/${planId(plan)}`
        },
        {
            key: "group_ops",
            title: "Push Center / evidence node",
            status: pushStatus,
            evidenceStatus: pushItem ? "REAL_DATA_BOUND" : "EVIDENCE_INCOMPLETE",
            derivedStatus: pushDerived,
            summary: pushItem ? "Push Center 只读 projection 可见；sent 仍不代表 governance complete。" : "未找到 Push Center projection，保持 evidence-incomplete。",
            guardrail: "必须通过 Push Center gate 解释，不允许 direct send。",
            route: "/admin/push-center"
        },
        {
            key: "group_ops",
            title: "治理状态",
            status: "governance-missing",
            evidenceStatus: "EVIDENCE_COLLECTED",
            derivedStatus: "approval_allowlist_window_missing",
            summary: "独立 operator approval、receiver allowlist、gray-window 记录仍需 attach。",
            guardrail: "requires_approval / requires_allowlist / requires_gray_window 仍然生效。",
            route: "/admin/p1/group-ops-workspace"
        },
        {
            key: "ops_plan_broadcast",
            title: "Preview canvas summary",
            status: nodeCount > 0 ? "downstream-pending" : "evidence-incomplete",
            evidenceStatus: "REAL_DATA_BOUND",
            derivedStatus: `nodes_${nodeCount}_executions_${executionTotal}`,
            summary: `${nodeCount} 个计划节点，${executionTotal} 条执行记录；仅前端内存 preview，不执行 downstream external effect。`,
            guardrail: "no_direct_send / no_external_call / no_production_write。",
            route: `/admin/automation-conversion/group-ops/plans/${planId(plan)}`
        }
    ];
}
export const DEFAULT_WORKSPACE_API_CONFIG = {
    plansUrl: "/api/admin/automation-conversion/group-ops/plans?limit=8",
    planDetailBaseUrl: "/api/admin/automation-conversion/group-ops/plans/",
    planGroupsSuffix: "/groups",
    planNodesSuffix: "/nodes",
    planExecutionsBaseUrl: "/api/automation/group-ops/plans/",
    pushCenterJobsUrl: "/api/admin/push-center/jobs?section=group_ops&limit=8"
};
export function parseWorkspaceApiConfig(documentRef = document) {
    const node = documentRef.getElementById("p1GroupOpsWorkspaceApiConfig");
    if (!node?.textContent)
        return DEFAULT_WORKSPACE_API_CONFIG;
    try {
        return { ...DEFAULT_WORKSPACE_API_CONFIG, ...JSON.parse(node.textContent) };
    }
    catch (_error) {
        return DEFAULT_WORKSPACE_API_CONFIG;
    }
}
export function defaultRequestJson() {
    const adminApi = globalThis.AdminApi;
    if (adminApi?.requestJson)
        return adminApi.requestJson.bind(adminApi);
    return async function requestJsonWithFetch(url) {
        const response = await fetch(url, { headers: { Accept: "application/json" }, credentials: "same-origin" });
        const payload = await response.json();
        if (!response.ok || payload?.ok === false)
            throw new Error(text(payload?.error || payload?.message || response.statusText));
        return payload;
    };
}
export async function loadGroupOpsWorkspaceData(config = DEFAULT_WORKSPACE_API_CONFIG, requestJson = defaultRequestJson()) {
    const plans = asRecord(await requestJson(config.plansUrl));
    const plan = firstPlan(plans);
    const selectedPlanId = planId(plan);
    if (!plan || selectedPlanId <= 0) {
        const unavailable = createUnavailableWorkspaceFixture(sourceStatus(plans));
        return {
            ...unavailable,
            dataSourceLabel: sourceStatus(plans),
            payload: {
                ...unavailable.payload,
                scenarios: [
                    {
                        key: "group_ops",
                        title: "Group Ops real-data binding",
                        status: "evidence-incomplete",
                        evidenceStatus: "REAL_DATA_UNAVAILABLE",
                        derivedStatus: "plan_not_found",
                        summary: "没有找到 Group Ops plan，保留 preview-only fallback。",
                        guardrail: "不能伪造成真实数据已绑定。",
                        route: "/admin/automation-conversion/group-ops/ui"
                    }
                ]
            }
        };
    }
    const detailUrl = `${config.planDetailBaseUrl}${encodeURIComponent(String(selectedPlanId))}`;
    const [detail, groups, nodes, executions, pushCenter] = await Promise.all([
        requestJson(detailUrl),
        requestJson(`${detailUrl}${config.planGroupsSuffix}`),
        requestJson(`${detailUrl}${config.planNodesSuffix}`),
        requestJson(`${config.planExecutionsBaseUrl}${encodeURIComponent(String(selectedPlanId))}/executions?limit=8`),
        requestJson(config.pushCenterJobsUrl)
    ]);
    const detailPayload = asRecord(detail);
    const groupsPayload = asRecord(groups);
    const nodesPayload = asRecord(nodes);
    const executionsPayload = asRecord(executions);
    const pushPayload = asRecord(pushCenter);
    return {
        payload: {
            finalVerdict: "P1_READY_WITH_EXCEPTIONS",
            canClaimPass90Plus: false,
            scenarios: scenariosFromRealData(plan, detailPayload, groupsPayload, nodesPayload, executionsPayload, pushPayload)
        },
        leftRailItems: leftRailFromRealData(plan, detailPayload, groupsPayload, nodesPayload, executionsPayload, pushPayload),
        detailItems: detailsFromRealData(plan, detailPayload, groupsPayload, nodesPayload, executionsPayload, pushPayload),
        defaultSelection: defaultSelectionForPlan(plan, firstPushCenterItem(pushPayload)),
        workspaceMode: "draft_only_preview_only",
        dataSourceLabel: sourceStatus(plans, detailPayload, groupsPayload, nodesPayload, executionsPayload),
        dataBindingStatus: "real_data_bound",
        realExternalCallExecuted: false,
        productionWriteExecuted: false
    };
}
