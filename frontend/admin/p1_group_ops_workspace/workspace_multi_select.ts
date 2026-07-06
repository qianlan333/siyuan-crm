import {
  updateWorkspaceViewState,
  type WorkspaceSelectedEntityIds,
  type WorkspaceSelectedEntityRef,
  type WorkspaceViewState
} from "./workspace_view_state.js";
import { type WorkspaceEntityType, type WorkspaceListItem } from "./workspace_fixture.js";

const ENTITY_TYPES: WorkspaceEntityType[] = ["plan", "group", "node", "execution", "push_center", "evidence"];

function emptySelectedEntityIds(): WorkspaceSelectedEntityIds {
  return {
    plan: [],
    group: [],
    node: [],
    execution: [],
    push_center: [],
    evidence: []
  };
}

function selectedCount(selectedEntityIds: WorkspaceSelectedEntityIds): number {
  return ENTITY_TYPES.reduce((count, entityType) => count + selectedEntityIds[entityType].length, 0);
}

function bundleId(selectedEntityIds: WorkspaceSelectedEntityIds): string {
  const parts = ENTITY_TYPES
    .map((entityType) => `${entityType}:${selectedEntityIds[entityType].length}`)
    .join("|");
  return `preview-bundle-${selectedCount(selectedEntityIds)}-${parts}`;
}

function guardrailSummary(selectedEntityIds: WorkspaceSelectedEntityIds): string[] {
  if (selectedCount(selectedEntityIds) === 0) return [];
  return [
    "sent evidence 不等于 governance complete",
    "governance-missing requires approval / allowlist / gray-window",
    "Push Center pending 不等于 completed",
    "evidence-incomplete 不等于 success",
    "external-config-blocked 不进入可执行队列",
    "any blocked item -> bundle cannot execute"
  ];
}

export function isEntityMultiSelected(
  viewState: WorkspaceViewState,
  entityType: WorkspaceEntityType,
  detailId: string
): boolean {
  return viewState.selectedEntityIds[entityType]?.includes(detailId) || false;
}

export function countMultiSelected(viewState: WorkspaceViewState): number {
  return selectedCount(viewState.selectedEntityIds);
}

export function toggleMultiSelectedEntity(
  viewState: WorkspaceViewState,
  entityType: WorkspaceEntityType,
  detailId: string
): WorkspaceViewState {
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

export function clearMultiSelection(viewState: WorkspaceViewState): WorkspaceViewState {
  return updateWorkspaceViewState(viewState, {
    selectedEntityIds: emptySelectedEntityIds(),
    activeSelectionMode: "single",
    lastSelectedEntity: null,
    previewBundleId: "preview-bundle-empty",
    bulkGuardrailSummary: []
  });
}

export function selectVisibleItems(viewState: WorkspaceViewState, items: WorkspaceListItem[]): WorkspaceViewState {
  const selectedEntityIds = emptySelectedEntityIds();
  for (const item of items) {
    if (!selectedEntityIds[item.entityType].includes(item.detailId)) {
      selectedEntityIds[item.entityType].push(item.detailId);
    }
  }
  const first = items[0];
  const lastSelectedEntity: WorkspaceSelectedEntityRef | null = first
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

export function selectVisibleLaneItems(
  viewState: WorkspaceViewState,
  items: WorkspaceListItem[],
  entityType: WorkspaceEntityType
): WorkspaceViewState {
  return selectVisibleItems(viewState, items.filter((item) => item.entityType === entityType));
}
