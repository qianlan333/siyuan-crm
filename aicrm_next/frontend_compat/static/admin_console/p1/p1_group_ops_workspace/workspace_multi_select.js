import { updateWorkspaceViewState } from "./workspace_view_state.js";
const ENTITY_TYPES = ["plan", "group", "node", "execution", "push_center", "evidence"];
function emptySelectedEntityIds() {
    return {
        plan: [],
        group: [],
        node: [],
        execution: [],
        push_center: [],
        evidence: []
    };
}
function selectedCount(selectedEntityIds) {
    return ENTITY_TYPES.reduce((count, entityType) => count + selectedEntityIds[entityType].length, 0);
}
function bundleId(selectedEntityIds) {
    const parts = ENTITY_TYPES
        .map((entityType) => `${entityType}:${selectedEntityIds[entityType].length}`)
        .join("|");
    return `preview-bundle-${selectedCount(selectedEntityIds)}-${parts}`;
}
function guardrailSummary(selectedEntityIds) {
    if (selectedCount(selectedEntityIds) === 0)
        return [];
    return [
        "sent evidence 不等于 governance complete",
        "governance-missing requires approval / allowlist / gray-window",
        "Push Center pending 不等于 completed",
        "evidence-incomplete 不等于 success",
        "external-config-blocked 不进入可执行队列",
        "any blocked item -> bundle cannot execute"
    ];
}
export function isEntityMultiSelected(viewState, entityType, detailId) {
    return viewState.selectedEntityIds[entityType]?.includes(detailId) || false;
}
export function countMultiSelected(viewState) {
    return selectedCount(viewState.selectedEntityIds);
}
export function toggleMultiSelectedEntity(viewState, entityType, detailId) {
    const current = viewState.selectedEntityIds[entityType] || [];
    const nextForType = current.includes(detailId)
        ? current.filter((id) => id !== detailId)
        : [...current, detailId];
    const selectedEntityIds = {
        ...viewState.selectedEntityIds,
        [entityType]: nextForType
    };
    const total = selectedCount(selectedEntityIds);
    return updateWorkspaceViewState(viewState, {
        selectedEntityIds,
        activeSelectionMode: total > 0 ? "multi" : "single",
        lastSelectedEntity: { entityType, id: detailId },
        previewBundleId: total > 0 ? bundleId(selectedEntityIds) : "preview-bundle-empty",
        bulkGuardrailSummary: guardrailSummary(selectedEntityIds)
    });
}
export function clearMultiSelection(viewState) {
    return updateWorkspaceViewState(viewState, {
        selectedEntityIds: emptySelectedEntityIds(),
        activeSelectionMode: "single",
        lastSelectedEntity: null,
        previewBundleId: "preview-bundle-empty",
        bulkGuardrailSummary: []
    });
}
export function selectVisibleItems(viewState, items) {
    const selectedEntityIds = emptySelectedEntityIds();
    for (const item of items) {
        if (!selectedEntityIds[item.entityType].includes(item.detailId)) {
            selectedEntityIds[item.entityType].push(item.detailId);
        }
    }
    const first = items[0];
    const lastSelectedEntity = first
        ? { entityType: first.entityType, id: first.detailId }
        : null;
    return updateWorkspaceViewState(viewState, {
        selectedEntityIds,
        activeSelectionMode: selectedCount(selectedEntityIds) > 0 ? "multi" : "single",
        lastSelectedEntity,
        previewBundleId: selectedCount(selectedEntityIds) > 0 ? bundleId(selectedEntityIds) : "preview-bundle-empty",
        bulkGuardrailSummary: guardrailSummary(selectedEntityIds)
    });
}
export function selectVisibleLaneItems(viewState, items, entityType) {
    return selectVisibleItems(viewState, items.filter((item) => item.entityType === entityType));
}
