import { selectEntityInViewState } from "./workspace_view_state.js";
const STATUS_VALUES = [
    "ready",
    "pending",
    "sent",
    "blocked",
    "external-config-blocked",
    "governance-missing",
    "evidence-incomplete",
    "downstream-pending",
    "operator-action-required",
    "retryable",
    "failed-terminal"
];
export const STATUS_FILTER_OPTIONS = ["all", ...STATUS_VALUES];
export const ENTITY_FILTER_OPTIONS = [
    "all",
    "plan",
    "group",
    "node",
    "execution",
    "push_center",
    "evidence"
];
function normalized(value) {
    return value.trim().toLowerCase();
}
function detailForItem(fixture, item) {
    return fixture.detailItems.find((detail) => detail.id === item.detailId && detail.entityType === item.entityType);
}
function searchableText(item, detail) {
    const fields = detail?.fields.map((field) => `${field.label} ${field.value}`).join(" ") || "";
    return normalized([
        item.id,
        item.label,
        item.kind,
        item.entityType,
        item.status,
        item.summary,
        detail?.id,
        detail?.title,
        detail?.status,
        detail?.evidenceStatus,
        detail?.derivedStatus,
        detail?.summary,
        fields
    ].filter(Boolean).join(" "));
}
function matchesKeyword(item, detail, keyword) {
    const query = normalized(keyword);
    if (!query)
        return true;
    return searchableText(item, detail).includes(query);
}
function matchesEntityFilter(item, filter) {
    return filter === "all" || item.entityType === filter;
}
function matchesStatusFilter(item, filter, entityType) {
    if (filter === "all")
        return true;
    return item.entityType === entityType && item.status === filter;
}
function itemMatches(fixture, item, viewState) {
    const detail = detailForItem(fixture, item);
    if (!matchesKeyword(item, detail, viewState.keyword))
        return false;
    if (!matchesEntityFilter(item, viewState.entityTypeFilter))
        return false;
    if (!matchesStatusFilter(item, viewState.planStatusFilter, "plan"))
        return false;
    if (!matchesStatusFilter(item, viewState.executionStatusFilter, "execution"))
        return false;
    if (!matchesStatusFilter(item, viewState.pushCenterStatusFilter, "push_center"))
        return false;
    return true;
}
function selectedItemStillVisible(items, viewState) {
    return items.some((item) => item.entityType === viewState.selectedEntityType && item.detailId === viewState.selectedEntityId);
}
function fallbackViewState(items, viewState) {
    if (selectedItemStillVisible(items, viewState))
        return viewState;
    const first = items[0];
    if (!first)
        return { ...viewState, panelMode: "summary" };
    return selectEntityInViewState(viewState, first.entityType, first.detailId);
}
function dataState(fixture, visibleItems) {
    if (fixture.dataBindingStatus === "real_data_unavailable")
        return "real_data_unavailable";
    if (visibleItems.length === 0)
        return "partial_data";
    if (fixture.detailItems.some((item) => item.status === "evidence-incomplete"))
        return "partial_data";
    return "ready";
}
function emptyReason(fixture, viewState) {
    if (fixture.dataBindingStatus === "real_data_unavailable") {
        return "Read-only API data is unavailable; the workspace keeps preview-only fallback and does not render sent/completed.";
    }
    if (viewState.keyword)
        return "No loaded redacted workspace item matches the keyword and filters.";
    return "No loaded redacted workspace item matches the active filters.";
}
export function filterWorkspaceView(fixture, viewState) {
    const visibleLeftRailItems = fixture.leftRailItems.filter((item) => itemMatches(fixture, item, viewState));
    const visibleDetailIds = new Set(visibleLeftRailItems.map((item) => `${item.entityType}:${item.detailId}`));
    const visibleDetailItems = fixture.detailItems.filter((item) => visibleDetailIds.has(`${item.entityType}:${item.id}`));
    const reconciledViewState = fallbackViewState(visibleLeftRailItems, viewState);
    const isEmpty = visibleLeftRailItems.length === 0;
    return {
        visibleLeftRailItems,
        visibleDetailItems,
        viewState: reconciledViewState,
        emptyReason: isEmpty ? emptyReason(fixture, viewState) : "",
        isEmpty,
        dataState: dataState(fixture, visibleLeftRailItems),
        resultSummary: `${visibleLeftRailItems.length} visible / ${fixture.leftRailItems.length} loaded`
    };
}
