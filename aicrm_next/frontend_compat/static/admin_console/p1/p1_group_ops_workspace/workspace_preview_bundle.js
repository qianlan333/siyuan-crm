const ENTITY_TYPES = ["plan", "group", "node", "execution", "push_center", "evidence"];
function emptyCounts() {
    return {
        plan: 0,
        group: 0,
        node: 0,
        execution: 0,
        push_center: 0,
        evidence: 0
    };
}
function isBlocked(status) {
    return status === "blocked"
        || status === "external-config-blocked"
        || status === "governance-missing"
        || status === "evidence-incomplete"
        || status === "failed-terminal";
}
function needsAction(status) {
    return status === "operator-action-required"
        || status === "governance-missing"
        || status === "retryable"
        || status === "blocked";
}
function detailLookup(fixture, entityType, detailId) {
    return fixture.detailItems.find((item) => item.entityType === entityType && item.id === detailId);
}
export function buildWorkspacePreviewBundle(fixture, filtered, viewState) {
    const visibleKeys = new Set(filtered.visibleLeftRailItems.map((item) => `${item.entityType}:${item.detailId}`));
    const countsByEntityType = emptyCounts();
    const items = [];
    for (const entityType of ENTITY_TYPES) {
        for (const detailId of viewState.selectedEntityIds[entityType]) {
            const detail = detailLookup(fixture, entityType, detailId);
            if (!detail)
                continue;
            countsByEntityType[entityType] += 1;
            items.push({
                entityType,
                detailId,
                title: detail.title,
                status: detail.status,
                derivedStatus: detail.derivedStatus,
                isVisible: visibleKeys.has(`${entityType}:${detailId}`)
            });
        }
    }
    const selectedCount = items.length;
    const blockedCount = items.filter((item) => isBlocked(item.status)).length;
    const actionRequiredCount = items.filter((item) => needsAction(item.status)).length;
    const governanceMissingCount = items.filter((item) => item.status === "governance-missing").length;
    const pushCenterPendingCount = items.filter((item) => item.entityType === "push_center" && item.status === "pending").length;
    const evidenceIncompleteCount = items.filter((item) => item.status === "evidence-incomplete").length;
    const hiddenSelectedCount = items.filter((item) => !item.isVisible).length;
    return {
        bundleId: viewState.previewBundleId,
        title: selectedCount > 0 ? `Read-only preview bundle (${selectedCount})` : "Read-only preview bundle",
        selectedCount,
        countsByEntityType,
        blockedCount,
        actionRequiredCount,
        governanceMissingCount,
        pushCenterPendingCount,
        evidenceIncompleteCount,
        hiddenSelectedCount,
        canExecute: false,
        previewOnly: true,
        productionWrite: false,
        realExternalCall: false,
        canClaimPass90Plus: false,
        guardrails: [
            "sent evidence 不等于 governance complete",
            "governance-missing requires approval / allowlist / gray-window",
            "Push Center pending 不等于 completed",
            "evidence-incomplete 不等于 success",
            "external-config-blocked 不进入可执行队列",
            "any blocked item -> bundle cannot execute"
        ],
        items
    };
}
