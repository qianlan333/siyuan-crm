import { type EvidenceStatus } from "../shared/status_model.js";
import { type WorkspaceCanvasSortMode } from "./workspace_view_state.js";

export interface WorkspaceSortableCanvasCard {
  originalIndex: number;
  status: EvidenceStatus;
  entityType: string;
  updatedOrCreatedTime: string;
}

const BLOCKED_STATUS_PRIORITY: Partial<Record<EvidenceStatus, number>> = {
  blocked: 0,
  "external-config-blocked": 1,
  "governance-missing": 2,
  "evidence-incomplete": 3,
  "failed-terminal": 4,
  "operator-action-required": 5,
  retryable: 6,
  "downstream-pending": 7,
  pending: 8,
  ready: 9,
  sent: 10
};

const ACTION_REQUIRED_PRIORITY: Partial<Record<EvidenceStatus, number>> = {
  "operator-action-required": 0,
  "governance-missing": 1,
  retryable: 2,
  blocked: 3,
  "external-config-blocked": 4,
  "evidence-incomplete": 5,
  "downstream-pending": 6,
  "failed-terminal": 7,
  pending: 8,
  ready: 9,
  sent: 10
};

function statusRank(status: EvidenceStatus, ranking: Partial<Record<EvidenceStatus, number>>): number {
  return ranking[status] ?? 99;
}

function timeValue(value: string): number {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function sortCanvasCards<T extends WorkspaceSortableCanvasCard>(
  cards: T[],
  mode: WorkspaceCanvasSortMode
): T[] {
  const sorted = [...cards];
  sorted.sort((left, right) => {
    if (mode === "status") {
      return left.status.localeCompare(right.status) || left.originalIndex - right.originalIndex;
    }
    if (mode === "entity_type") {
      return left.entityType.localeCompare(right.entityType) || left.originalIndex - right.originalIndex;
    }
    if (mode === "updated_or_created_time") {
      return timeValue(right.updatedOrCreatedTime) - timeValue(left.updatedOrCreatedTime) || left.originalIndex - right.originalIndex;
    }
    if (mode === "blocked_first") {
      return statusRank(left.status, BLOCKED_STATUS_PRIORITY) - statusRank(right.status, BLOCKED_STATUS_PRIORITY) || left.originalIndex - right.originalIndex;
    }
    if (mode === "action_required_first") {
      return statusRank(left.status, ACTION_REQUIRED_PRIORITY) - statusRank(right.status, ACTION_REQUIRED_PRIORITY) || left.originalIndex - right.originalIndex;
    }
    return left.originalIndex - right.originalIndex;
  });
  return sorted;
}
