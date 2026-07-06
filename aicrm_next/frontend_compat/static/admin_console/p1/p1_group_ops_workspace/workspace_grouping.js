import { WORKSPACE_CANVAS_LANE_IDS } from "./workspace_view_state.js";
import { sortCanvasCards } from "./workspace_sorting.js";
export const WORKSPACE_CANVAS_LANE_DEFINITIONS = [
    { id: "plans", title: "Plans", description: "计划对象，只读展示 plan status 与 internal id。" },
    { id: "groups", title: "Audiences / Groups", description: "人群和 receiver 聚合摘要，不展示成员明文。" },
    { id: "nodes", title: "Tasks / Nodes", description: "任务和消息节点 preview，不执行任务。" },
    { id: "executions", title: "Executions", description: "执行记录摘要，不能代表 workspace 触发发送。" },
    { id: "push_center", title: "Push Center", description: "Push Center projection 状态，pending 不等于 completed。" },
    { id: "evidence", title: "Evidence / Guardrails", description: "治理证据和 guardrail 摘要，sent 不等于 governance complete。" }
];
function laneForEntity(entityType) {
    if (entityType === "plan")
        return "plans";
    if (entityType === "group")
        return "groups";
    if (entityType === "node")
        return "nodes";
    if (entityType === "execution")
        return "executions";
    if (entityType === "push_center")
        return "push_center";
    return "evidence";
}
function detailForItem(fixture, item) {
    return fixture.detailItems.find((detail) => detail.id === item.detailId && detail.entityType === item.entityType);
}
function fieldValue(detail, names) {
    if (!detail)
        return "";
    const normalizedNames = new Set(names.map((name) => name.toLowerCase()));
    const field = detail.fields.find((candidate) => normalizedNames.has(candidate.label.toLowerCase()));
    return field?.value || "";
}
function isBlockedStatus(status) {
    return status === "blocked"
        || status === "external-config-blocked"
        || status === "governance-missing"
        || status === "evidence-incomplete"
        || status === "failed-terminal";
}
function requiresOperatorAction(status) {
    return status === "operator-action-required"
        || status === "governance-missing"
        || status === "retryable"
        || status === "blocked";
}
export function buildWorkspaceCanvasCards(fixture, filtered) {
    return filtered.visibleLeftRailItems.map((item, index) => {
        const detail = detailForItem(fixture, item);
        return {
            id: item.id,
            laneId: laneForEntity(item.entityType),
            originalIndex: index,
            entityType: item.entityType,
            detailId: item.detailId,
            title: item.label,
            status: item.status,
            evidenceStatus: detail?.evidenceStatus || "not_found",
            derivedStatus: detail?.derivedStatus || item.status,
            summary: item.summary,
            guardrail: detail?.guardrail || "preview_only / no_direct_send / no_external_call / no_production_write",
            updatedOrCreatedTime: fieldValue(detail, ["updated_at", "created_at", "executed_at"])
        };
    });
}
export function buildWorkspaceCanvasLanes(fixture, filtered, viewState) {
    const visibleLaneIds = new Set(viewState.visibleLaneIds);
    const cards = buildWorkspaceCanvasCards(fixture, filtered);
    return WORKSPACE_CANVAS_LANE_DEFINITIONS
        .filter((lane) => WORKSPACE_CANVAS_LANE_IDS.includes(lane.id))
        .map((lane) => {
        const laneCards = cards.filter((card) => card.laneId === lane.id);
        return {
            ...lane,
            cards: sortCanvasCards(laneCards, viewState.canvasSortMode),
            visibleCount: laneCards.length,
            blockedCount: laneCards.filter((card) => isBlockedStatus(card.status)).length,
            actionRequiredCount: laneCards.filter((card) => requiresOperatorAction(card.status)).length,
            isCollapsed: Boolean(viewState.laneCollapsedState[lane.id]),
            isVisible: visibleLaneIds.has(lane.id),
            emptyReason: filtered.isEmpty
                ? filtered.emptyReason
                : `No visible ${lane.title} item matches the current local filters.`
        };
    })
        .filter((lane) => lane.isVisible);
}
