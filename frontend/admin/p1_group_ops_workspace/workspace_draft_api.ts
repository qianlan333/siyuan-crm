import { type FilteredWorkspaceView } from "./workspace_filters.js";
import {
  type WorkspaceDetailItem,
  type WorkspaceEntityType,
  type WorkspaceFixture
} from "./workspace_fixture.js";
import { buildWorkspacePreviewBundle } from "./workspace_preview_bundle.js";
import { type WorkspaceViewState } from "./workspace_view_state.js";

export interface WorkspaceDraftApiConfig {
  draftsUrl: string;
}

export interface WorkspaceDraftRequestOptions {
  method?: "GET" | "POST" | "PATCH";
  headers?: Record<string, string>;
  body?: string;
}

export type WorkspaceDraftRequestJson = (url: string, options?: WorkspaceDraftRequestOptions) => Promise<unknown>;

export interface WorkspaceDraftItemPayload {
  item_type: WorkspaceEntityType;
  item_ref_id: string;
  item_order: number;
  sanitized_item: Record<string, unknown>;
  guardrail_summary: Record<string, unknown>;
}

export interface WorkspaceDraftPayload {
  source_plan_id: string;
  sanitized_payload: Record<string, unknown>;
  guardrail_summary: Record<string, unknown>;
  approval_requirements: Record<string, unknown>;
  items: WorkspaceDraftItemPayload[];
  idempotency_key: string;
  version?: number;
}

export interface WorkspaceDraftReviewPayload {
  version: number;
  idempotency_key: string;
  review_note?: string;
  client_snapshot_hash?: string;
}

export interface WorkspaceDraftResponse {
  ok: boolean;
  operation?: string;
  draft_id?: string;
  draft_status?: string;
  version?: number;
  source_plan_id?: string;
  sanitized_payload?: Record<string, unknown>;
  guardrail_summary?: Record<string, unknown>;
  approval_requirements?: Record<string, unknown>;
  items?: WorkspaceDraftItemPayload[];
  snapshot_hash?: string;
  created_at?: string;
  updated_at?: string;
  archived_at?: string;
  preview_only?: boolean;
  production_write?: boolean;
  ready_for_review?: boolean;
  approved?: boolean;
  real_external_call?: boolean;
  real_external_call_executed?: boolean;
  push_center_job_created?: boolean;
  external_effect_job_created?: boolean;
  broadcast_job_created?: boolean;
  internal_event_created?: boolean;
  can_claim_pass_90_plus?: boolean;
  execution_status?: string;
  error?: string;
  detail?: string;
}

export interface BuildWorkspaceDraftPayloadOptions {
  idempotencyKeyOverride?: string;
  version?: number;
}

export const DEFAULT_WORKSPACE_DRAFT_API_CONFIG: WorkspaceDraftApiConfig = {
  draftsUrl: "/api/admin/p1/group-ops-workspace/drafts"
};

function text(value: unknown): string {
  return String(value ?? "").trim();
}

export function workspaceSimpleHash(value: string): string {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

function sensitiveFragments(): string[] {
  return [
    "raw_" + "external_userid",
    "receiver_" + "plaintext",
    "raw_" + "receiver",
    "raw_" + "chat",
    "raw_" + "member",
    "open" + "id",
    "union" + "id",
    "access_" + "token",
    "corp" + "secret",
    "suite_" + "secret",
    "bearer ",
    "authorization",
    "token",
    "secret",
    "raw_" + "message_body",
    "raw_" + "callback_body",
    "target_" + "list",
    "raw_" + "target",
    "phone",
    "mobile"
  ];
}

export function assertWorkspaceSensitiveSafe(value: unknown, path = "$"): void {
  if (Array.isArray(value)) {
    value.forEach((item, index) => assertWorkspaceSensitiveSafe(item, `${path}[${index}]`));
    return;
  }
  if (value && typeof value === "object") {
    for (const [rawKey, item] of Object.entries(value as Record<string, unknown>)) {
      const key = rawKey.toLowerCase();
      if (sensitiveFragments().some((fragment) => key.includes(fragment))) {
        throw new Error(`draft_payload_sensitive_field:${path}.${rawKey}`);
      }
      assertWorkspaceSensitiveSafe(item, `${path}.${rawKey}`);
    }
    return;
  }
  if (typeof value === "string") {
    const lower = value.toLowerCase();
    if (/\b1[3-9]\d{9}\b/.test(value)) {
      throw new Error(`draft_payload_sensitive_value:${path}`);
    }
    if (sensitiveFragments().some((fragment) => lower.includes(fragment))) {
      throw new Error(`draft_payload_sensitive_value:${path}`);
    }
  }
}

export function assertWorkspaceDraftPayloadSafe(payload: WorkspaceDraftPayload): true {
  assertWorkspaceSensitiveSafe(payload);
  return true;
}

export function assertWorkspaceDraftReviewPayloadSafe(payload: WorkspaceDraftReviewPayload): true {
  assertWorkspaceSensitiveSafe(payload);
  return true;
}

function sourcePlanId(fixture: WorkspaceFixture): string {
  const detailPlan = fixture.detailItems.find((item) => item.entityType === "plan");
  if (detailPlan) return text(detailPlan.id) || "p1_group_ops_workspace";
  const listPlan = fixture.leftRailItems.find((item) => item.entityType === "plan");
  return text(listPlan?.detailId || listPlan?.id || "p1_group_ops_workspace");
}

function detailForItem(fixture: WorkspaceFixture, entityType: WorkspaceEntityType, detailId: string): WorkspaceDetailItem | undefined {
  return fixture.detailItems.find((item) => item.entityType === entityType && item.id === detailId);
}

function itemPayload(
  detail: WorkspaceDetailItem,
  itemOrder: number,
  visibleInCurrentFilter: boolean
): WorkspaceDraftItemPayload {
  return {
    item_type: detail.entityType,
    item_ref_id: detail.id,
    item_order: itemOrder,
    sanitized_item: {
      title: detail.title,
      status: detail.status,
      evidence_status: detail.evidenceStatus,
      derived_status: detail.derivedStatus,
      visible_in_current_filter: visibleInCurrentFilter
    },
    guardrail_summary: {
      guardrail: detail.guardrail,
      preview_only: true,
      no_direct_send: true,
      no_external_call: true,
      no_production_write: true
    }
  };
}

function selectedDraftItems(fixture: WorkspaceFixture, filtered: FilteredWorkspaceView, viewState: WorkspaceViewState): WorkspaceDraftItemPayload[] {
  const bundle = buildWorkspacePreviewBundle(fixture, filtered, viewState);
  if (bundle.items.length > 0) {
    return bundle.items
      .map((item, index) => {
        const detail = detailForItem(fixture, item.entityType, item.detailId);
        return detail ? itemPayload(detail, index, item.isVisible) : null;
      })
      .filter((item): item is WorkspaceDraftItemPayload => item !== null);
  }
  const current = detailForItem(fixture, viewState.selectedEntityType, viewState.selectedEntityId)
    || fixture.detailItems[0];
  return current ? [itemPayload(current, 0, true)] : [];
}

function stableIdempotencyKey(sourcePlan: string, items: WorkspaceDraftItemPayload[]): string {
  const hash = workspaceSimpleHash(JSON.stringify({
    sourcePlan,
    items: items.map((item) => ({
      item_type: item.item_type,
      item_ref_id: item.item_ref_id,
      item_order: item.item_order,
      status: item.sanitized_item.status,
      derived_status: item.sanitized_item.derived_status
    }))
  }));
  return `p1-gow-draft:${sourcePlan}:${hash}`;
}

export function stableRequestReviewIdempotencyKey(draftId: string, version: number, snapshotHash: string): string {
  return `p1-gow-request-review:${text(draftId)}:${Number(version || 0)}:${text(snapshotHash || "no_snapshot")}`;
}

export function buildWorkspaceDraftPayload(
  fixture: WorkspaceFixture,
  filtered: FilteredWorkspaceView,
  viewState: WorkspaceViewState,
  options: BuildWorkspaceDraftPayloadOptions = {}
): WorkspaceDraftPayload {
  const sourcePlan = sourcePlanId(fixture);
  const items = selectedDraftItems(fixture, filtered, viewState);
  const payload: WorkspaceDraftPayload = {
    source_plan_id: sourcePlan,
    sanitized_payload: {
      workspace: "p1_group_ops_workspace",
      workspace_mode: fixture.workspaceMode,
      data_binding_status: fixture.dataBindingStatus,
      final_verdict: fixture.payload.finalVerdict,
      selected_entity_type: viewState.selectedEntityType,
      selected_count: items.length,
      preview_bundle_id: viewState.previewBundleId,
      preview_only: true,
      can_claim_pass_90_plus: false
    },
    guardrail_summary: {
      preview_only: true,
      production_write_scope: "draft_tables_only",
      real_external_call: false,
      push_center_job_created: false,
      external_effect_job_created: false,
      broadcast_job_created: false,
      internal_event_created: false,
      can_claim_pass_90_plus: false,
      sent_evidence_requires_governance_review: true,
      requires_approval: true,
      requires_allowlist: true,
      requires_gray_window: true
    },
    approval_requirements: {
      request_review_required: true,
      governance_review_required: true,
      push_center_bridge_requires_governance_approved: true,
      execution_not_allowed_from_draft: true
    },
    items,
    idempotency_key: options.idempotencyKeyOverride || viewState.currentDraftIdempotencyKey || stableIdempotencyKey(sourcePlan, items)
  };
  if (options.version !== undefined && options.version > 0) {
    payload.version = options.version;
  }
  assertWorkspaceDraftPayloadSafe(payload);
  return payload;
}

export function buildWorkspaceDraftReviewPayload(
  draftId: string,
  version: number,
  snapshotHash: string,
  reviewNote?: string
): WorkspaceDraftReviewPayload {
  const payload: WorkspaceDraftReviewPayload = {
    version,
    idempotency_key: stableRequestReviewIdempotencyKey(draftId, version, snapshotHash)
  };
  if (snapshotHash) {
    payload.client_snapshot_hash = snapshotHash;
  }
  if (reviewNote) {
    payload.review_note = reviewNote;
  }
  assertWorkspaceDraftReviewPayloadSafe(payload);
  return payload;
}

export function defaultWorkspaceDraftRequestJson(): WorkspaceDraftRequestJson {
  const adminApi = (globalThis as typeof globalThis & { AdminApi?: { requestJson?: WorkspaceDraftRequestJson } }).AdminApi;
  if (adminApi?.requestJson) return adminApi.requestJson.bind(adminApi);
  return async function requestJsonWithFetch(url: string, options: WorkspaceDraftRequestOptions = {}): Promise<unknown> {
    const response = await fetch(url, {
      method: options.method || "GET",
      headers: { Accept: "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) },
      body: options.body,
      credentials: "same-origin"
    });
    const payload = await response.json();
    if (!response.ok || payload?.ok === false) {
      throw new Error(text(payload?.detail || payload?.error || response.statusText || response.status));
    }
    return payload;
  };
}

function asDraftResponse(value: unknown): WorkspaceDraftResponse {
  const payload = value && typeof value === "object" ? value as WorkspaceDraftResponse : { ok: false };
  if (
    payload.can_claim_pass_90_plus === true
    || payload.real_external_call === true
    || payload.real_external_call_executed === true
    || payload.external_effect_job_created === true
    || payload.push_center_job_created === true
    || payload.broadcast_job_created === true
    || payload.internal_event_created === true
    || payload.approved === true
  ) {
    throw new Error("draft_api_response_violates_execution_guardrail");
  }
  if (
    payload.draft_status === "sent"
    || payload.draft_status === "completed"
    || payload.draft_status === "approved"
    || payload.execution_status === "sent"
    || payload.execution_status === "completed"
    || payload.execution_status === "approved"
  ) {
    throw new Error("draft_api_response_claims_execution_state");
  }
  return payload;
}

export function isDraftConflictError(error: unknown): boolean {
  return text(error instanceof Error ? error.message : error).toLowerCase().includes("conflict")
    || text(error instanceof Error ? error.message : error).includes("409");
}

export async function listDrafts(
  config: WorkspaceDraftApiConfig = DEFAULT_WORKSPACE_DRAFT_API_CONFIG,
  requestJson: WorkspaceDraftRequestJson = defaultWorkspaceDraftRequestJson()
): Promise<WorkspaceDraftResponse> {
  return asDraftResponse(await requestJson(config.draftsUrl));
}

export async function getDraft(
  draftId: string,
  config: WorkspaceDraftApiConfig = DEFAULT_WORKSPACE_DRAFT_API_CONFIG,
  requestJson: WorkspaceDraftRequestJson = defaultWorkspaceDraftRequestJson()
): Promise<WorkspaceDraftResponse> {
  return asDraftResponse(await requestJson(`${config.draftsUrl}/${encodeURIComponent(draftId)}`));
}

export async function createDraft(
  payload: WorkspaceDraftPayload,
  config: WorkspaceDraftApiConfig = DEFAULT_WORKSPACE_DRAFT_API_CONFIG,
  requestJson: WorkspaceDraftRequestJson = defaultWorkspaceDraftRequestJson()
): Promise<WorkspaceDraftResponse> {
  assertWorkspaceDraftPayloadSafe(payload);
  return asDraftResponse(await requestJson(config.draftsUrl, {
    method: "POST",
    body: JSON.stringify(payload)
  }));
}

export async function updateDraft(
  draftId: string,
  payload: WorkspaceDraftPayload,
  config: WorkspaceDraftApiConfig = DEFAULT_WORKSPACE_DRAFT_API_CONFIG,
  requestJson: WorkspaceDraftRequestJson = defaultWorkspaceDraftRequestJson()
): Promise<WorkspaceDraftResponse> {
  assertWorkspaceDraftPayloadSafe(payload);
  return asDraftResponse(await requestJson(`${config.draftsUrl}/${encodeURIComponent(draftId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  }));
}

export async function archiveDraft(
  draftId: string,
  version: number,
  config: WorkspaceDraftApiConfig = DEFAULT_WORKSPACE_DRAFT_API_CONFIG,
  requestJson: WorkspaceDraftRequestJson = defaultWorkspaceDraftRequestJson()
): Promise<WorkspaceDraftResponse> {
  return asDraftResponse(await requestJson(`${config.draftsUrl}/${encodeURIComponent(draftId)}/archive`, {
    method: "POST",
    body: JSON.stringify({ version, archive_reason: "p1_workspace_user_archive" })
  }));
}

export async function requestDraftReview(
  draftId: string,
  payload: WorkspaceDraftReviewPayload,
  config: WorkspaceDraftApiConfig = DEFAULT_WORKSPACE_DRAFT_API_CONFIG,
  requestJson: WorkspaceDraftRequestJson = defaultWorkspaceDraftRequestJson()
): Promise<WorkspaceDraftResponse> {
  assertWorkspaceDraftReviewPayloadSafe(payload);
  return asDraftResponse(await requestJson(`${config.draftsUrl}/${encodeURIComponent(draftId)}/request-review`, {
    method: "POST",
    body: JSON.stringify(payload)
  }));
}
