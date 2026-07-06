import {
  DEFAULT_WORKSPACE_DRAFT_API_CONFIG,
  assertWorkspaceSensitiveSafe,
  defaultWorkspaceDraftRequestJson,
  workspaceSimpleHash,
  type WorkspaceDraftApiConfig,
  type WorkspaceDraftRequestJson,
  type WorkspaceDraftRequestOptions
} from "./workspace_draft_api.js";

export interface WorkspaceGovernanceApiConfig extends WorkspaceDraftApiConfig {
  governanceUrl: string;
}

export interface WorkspaceGovernanceAllowlistSummary {
  allowlist_hash: string;
  allowlist_count: number;
  source_reference: Record<string, unknown>;
}

export interface WorkspaceGovernanceGrayWindow {
  start_at: string;
  end_at: string;
  timezone: string;
}

export interface WorkspaceGovernanceRequestPayload {
  idempotency_key: string;
  client_snapshot_hash: string;
  allowlist_summary: WorkspaceGovernanceAllowlistSummary;
  gray_window: WorkspaceGovernanceGrayWindow;
  request_note?: string;
}

export interface WorkspaceGovernanceStep {
  step_id?: string;
  step_type: "operator_approval" | "receiver_allowlist" | "gray_window" | string;
  step_status: "pending" | "approved" | "rejected" | "expired" | string;
  actor_metadata?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
}

export interface WorkspaceGovernanceResponse {
  ok: boolean;
  operation?: string;
  review_id?: string;
  draft_id?: string;
  review_status?: string;
  snapshot_hash?: string;
  sanitized_payload_hash?: string;
  steps?: WorkspaceGovernanceStep[];
  allowlist_summary?: {
    hash?: string;
    count?: number;
    source_reference_summary?: Record<string, unknown>;
    expires_at?: string;
  };
  gray_window?: {
    start_at?: string;
    end_at?: string;
    timezone?: string;
    window_status?: string;
  };
  created_at?: string;
  updated_at?: string;
  expires_at?: string;
  preview_only?: boolean;
  production_write?: boolean;
  approved?: boolean;
  ready_for_review?: boolean;
  push_center_job_created?: boolean;
  external_effect_job_created?: boolean;
  broadcast_job_created?: boolean;
  internal_event_created?: boolean;
  real_external_call?: boolean;
  real_external_call_executed?: boolean;
  can_claim_pass_90_plus?: boolean;
  execution_status?: string;
  idempotent_replay?: boolean;
  step_id?: string;
  step_type?: string;
  step_status?: string;
  governance_approved?: boolean;
  error?: string;
  detail?: string;
}

export interface WorkspacePushCenterBridgePayload {
  idempotency_key: string;
  client_snapshot_hash: string;
  allowlist_hash: string;
  allowlist_count: number;
  gray_window_summary?: WorkspaceGovernanceGrayWindow & {
    window_status?: string;
  };
  bridge_note?: string;
}

export interface WorkspacePushCenterBridgeResponse {
  ok: boolean;
  operation?: string;
  review_id?: string;
  draft_id?: string;
  review_status?: string;
  push_center_job_created?: boolean;
  push_center_job_id?: string;
  push_center_projection_id?: string;
  push_center_status?: string;
  push_center_metadata?: {
    source?: string;
    draft_id?: string;
    review_id?: string;
    governance_status?: string;
    snapshot_hash?: string;
    allowlist_hash?: string;
    allowlist_count?: number;
    gray_window?: Record<string, unknown>;
    no_external_call?: boolean;
  };
  preview_only?: boolean;
  production_write?: boolean;
  production_write_scope?: string;
  approved?: boolean;
  governance_approved?: boolean;
  ready_for_review?: boolean;
  external_effect_job_created?: boolean;
  broadcast_job_created?: boolean;
  internal_event_created?: boolean;
  real_external_call?: boolean;
  real_external_call_executed?: boolean;
  execution_status?: string;
  can_claim_pass_90_plus?: boolean;
  idempotent_replay?: boolean;
  error?: string;
  detail?: string;
}

export interface WorkspaceGovernanceListResponse {
  ok: boolean;
  items: WorkspaceGovernanceResponse[];
  total?: number;
  preview_only?: boolean;
  production_write?: boolean;
  real_external_call?: boolean;
  real_external_call_executed?: boolean;
  push_center_job_created?: boolean;
  external_effect_job_created?: boolean;
  broadcast_job_created?: boolean;
  internal_event_created?: boolean;
  can_claim_pass_90_plus?: boolean;
  execution_status?: string;
}

export interface BuildWorkspaceGovernancePayloadOptions {
  allowlistHash?: string;
  allowlistCount?: number;
  sourceReference?: Record<string, unknown>;
  grayWindow?: WorkspaceGovernanceGrayWindow;
  requestNote?: string;
}

export type WorkspaceGovernanceStepAction = "approve" | "reject" | "expire";

export interface WorkspaceGovernanceStepCommandPayload {
  idempotency_key: string;
  approval_note?: string;
  reject_reason?: string;
  expire_reason?: string;
  allowlist_hash?: string;
  allowlist_count?: number;
}

export interface WorkspaceGovernanceStepContext {
  step_id?: string;
  step_type?: string;
  step_status?: string;
}

export interface WorkspaceGovernanceReviewContext {
  review_id?: string;
  review_status?: string;
  allowlist_summary?: {
    hash?: string;
    count?: number;
  };
  gray_window?: {
    start_at?: string;
    end_at?: string;
    timezone?: string;
    window_status?: string;
  };
}

export interface BuildWorkspaceGovernanceStepPayloadOptions {
  approvalNote?: string;
  rejectReason?: string;
  expireReason?: string;
  allowlistHash?: string;
  allowlistCount?: number;
}

export interface BuildWorkspacePushCenterBridgePayloadOptions {
  bridgeNote?: string;
  allowlistHash?: string;
  allowlistCount?: number;
  grayWindow?: WorkspaceGovernanceGrayWindow & {
    window_status?: string;
  };
}

export const DEFAULT_WORKSPACE_GOVERNANCE_API_CONFIG: WorkspaceGovernanceApiConfig = {
  ...DEFAULT_WORKSPACE_DRAFT_API_CONFIG,
  governanceUrl: "/api/admin/p1/group-ops-workspace/governance"
};

function text(value: unknown): string {
  return String(value ?? "").trim();
}

function bodyOptions(payload: unknown): WorkspaceDraftRequestOptions {
  return {
    method: "POST",
    body: JSON.stringify(payload)
  };
}

function defaultGrayWindow(snapshotHash: string): WorkspaceGovernanceGrayWindow {
  const dayOffset = Number.parseInt(workspaceSimpleHash(snapshotHash || "no_snapshot").slice(0, 2), 16) % 20;
  const day = String(1 + dayOffset).padStart(2, "0");
  return {
    start_at: `2026-06-${day}T09:00:00+08:00`,
    end_at: `2026-06-${day}T10:00:00+08:00`,
    timezone: "Asia/Shanghai"
  };
}

function stableGrayWindowHash(grayWindow: WorkspaceGovernanceGrayWindow): string {
  return workspaceSimpleHash(JSON.stringify({
    start_at: grayWindow.start_at,
    end_at: grayWindow.end_at,
    timezone: grayWindow.timezone
  }));
}

export function stablePushCenterBridgeIdempotencyKey(
  reviewId: string,
  snapshotHash: string,
  allowlistHash: string,
  grayWindowHash: string
): string {
  return [
    "p1-gow-push-center-bridge",
    text(reviewId),
    text(snapshotHash || "no_snapshot"),
    text(allowlistHash || "allowlist_missing"),
    text(grayWindowHash || "window_missing")
  ].join(":");
}

export function stableGovernanceIdempotencyKey(
  draftId: string,
  snapshotHash: string,
  allowlistHash: string,
  grayWindowHash: string
): string {
  return [
    "p1-gow-governance",
    text(draftId),
    text(snapshotHash || "no_snapshot"),
    text(allowlistHash || "allowlist_missing"),
    text(grayWindowHash || "window_missing")
  ].join(":");
}

function stableStepPayloadHash(payload: Record<string, unknown>): string {
  return workspaceSimpleHash(JSON.stringify(payload, Object.keys(payload).sort()));
}

export function stableGovernanceStepIdempotencyKey(
  action: WorkspaceGovernanceStepAction,
  reviewId: string,
  stepIdOrReview: string,
  currentStatus: string,
  payloadHash: string
): string {
  if (action === "expire") {
    return [
      "p1-gow-review-expire",
      text(reviewId),
      text(currentStatus || "unknown_status"),
      text(payloadHash || "empty_payload")
    ].join(":");
  }
  return [
    `p1-gow-step-${action}`,
    text(reviewId),
    text(stepIdOrReview),
    text(currentStatus || "unknown_status"),
    text(payloadHash || "empty_payload")
  ].join(":");
}

export function assertWorkspaceGovernancePayloadSafe(payload: WorkspaceGovernanceRequestPayload): true {
  assertWorkspaceSensitiveSafe(payload);
  const start = Date.parse(payload.gray_window.start_at);
  const end = Date.parse(payload.gray_window.end_at);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) {
    throw new Error("governance_payload_invalid_gray_window");
  }
  if (!payload.idempotency_key || !payload.client_snapshot_hash || !payload.allowlist_summary.allowlist_hash) {
    throw new Error("governance_payload_missing_required_field");
  }
  return true;
}

export function assertWorkspaceGovernanceStepPayloadSafe(payload: WorkspaceGovernanceStepCommandPayload): true {
  assertWorkspaceSensitiveSafe(payload);
  if (!payload.idempotency_key) {
    throw new Error("governance_step_payload_missing_idempotency_key");
  }
  if (payload.allowlist_count !== undefined && (!Number.isFinite(payload.allowlist_count) || payload.allowlist_count < 0)) {
    throw new Error("governance_step_payload_invalid_allowlist_count");
  }
  return true;
}

export function assertWorkspacePushCenterBridgePayloadSafe(payload: WorkspacePushCenterBridgePayload): true {
  assertWorkspaceSensitiveSafe(payload);
  if (!payload.idempotency_key || !payload.client_snapshot_hash || !payload.allowlist_hash) {
    throw new Error("push_center_bridge_payload_missing_required_field");
  }
  if (!Number.isFinite(payload.allowlist_count) || payload.allowlist_count < 0) {
    throw new Error("push_center_bridge_payload_invalid_allowlist_count");
  }
  if (payload.gray_window_summary) {
    const start = Date.parse(payload.gray_window_summary.start_at);
    const end = Date.parse(payload.gray_window_summary.end_at);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) {
      throw new Error("push_center_bridge_payload_invalid_gray_window");
    }
  }
  return true;
}

export function buildWorkspaceGovernanceRequestPayload(
  draftId: string,
  snapshotHash: string,
  options: BuildWorkspaceGovernancePayloadOptions = {}
): WorkspaceGovernanceRequestPayload {
  const grayWindow = options.grayWindow || defaultGrayWindow(snapshotHash);
  const allowlistHash = options.allowlistHash || `allowlist-${workspaceSimpleHash(`${draftId}:${snapshotHash}:summary`)}`;
  const grayWindowHash = stableGrayWindowHash(grayWindow);
  const payload: WorkspaceGovernanceRequestPayload = {
    idempotency_key: stableGovernanceIdempotencyKey(draftId, snapshotHash, allowlistHash, grayWindowHash),
    client_snapshot_hash: snapshotHash,
    allowlist_summary: {
      allowlist_hash: allowlistHash,
      allowlist_count: options.allowlistCount ?? 0,
      source_reference: options.sourceReference || {
        reference_type: "p1_workspace_governance",
        reference_id: `draft-${text(draftId) || "not_saved"}`,
        summary_only: true
      }
    },
    gray_window: grayWindow
  };
  if (options.requestNote) {
    payload.request_note = options.requestNote;
  }
  assertWorkspaceGovernancePayloadSafe(payload);
  return payload;
}

export function buildPushCenterBridgePayload(
  review: WorkspaceGovernanceReviewContext & {
    snapshot_hash?: string;
  },
  options: BuildWorkspacePushCenterBridgePayloadOptions = {}
): WorkspacePushCenterBridgePayload {
  const reviewId = requireReviewId(review);
  const snapshotHash = text(review.snapshot_hash);
  if (!snapshotHash) throw new Error("push_center_bridge_missing_snapshot_hash");
  const allowlistHash = options.allowlistHash || text(review.allowlist_summary?.hash);
  const allowlistCount = options.allowlistCount ?? Number(review.allowlist_summary?.count ?? 0);
  const grayWindow = options.grayWindow || review.gray_window;
  if (!grayWindow?.start_at || !grayWindow?.end_at || !grayWindow?.timezone) {
    throw new Error("push_center_bridge_missing_gray_window");
  }
  const safeGrayWindow: WorkspaceGovernanceGrayWindow & { window_status?: string } = {
    start_at: grayWindow.start_at,
    end_at: grayWindow.end_at,
    timezone: grayWindow.timezone,
    window_status: text(grayWindow.window_status || "approved")
  };
  const grayWindowHash = stableGrayWindowHash(safeGrayWindow);
  const payload: WorkspacePushCenterBridgePayload = {
    idempotency_key: stablePushCenterBridgeIdempotencyKey(reviewId, snapshotHash, allowlistHash, grayWindowHash),
    client_snapshot_hash: snapshotHash,
    allowlist_hash: allowlistHash,
    allowlist_count: allowlistCount,
    gray_window_summary: safeGrayWindow
  };
  if (options.bridgeNote) {
    payload.bridge_note = options.bridgeNote;
  }
  assertWorkspacePushCenterBridgePayloadSafe(payload);
  return payload;
}

function requireReviewId(review: WorkspaceGovernanceReviewContext): string {
  const reviewId = text(review.review_id);
  if (!reviewId) throw new Error("governance_step_missing_review_id");
  return reviewId;
}

function requireStepId(step: WorkspaceGovernanceStepContext): string {
  const stepId = text(step.step_id);
  if (!stepId) throw new Error("governance_step_missing_step_id");
  return stepId;
}

function assertGrayWindowCanApprove(review: WorkspaceGovernanceReviewContext): void {
  const endAt = Date.parse(String(review.gray_window?.end_at || ""));
  if (!Number.isFinite(endAt)) {
    throw new Error("governance_step_invalid_gray_window");
  }
  if (endAt <= Date.now()) {
    throw new Error("governance_step_gray_window_expired");
  }
}

export function buildApproveGovernanceStepPayload(
  review: WorkspaceGovernanceReviewContext,
  step: WorkspaceGovernanceStepContext,
  options: BuildWorkspaceGovernanceStepPayloadOptions = {}
): WorkspaceGovernanceStepCommandPayload {
  const reviewId = requireReviewId(review);
  const stepId = requireStepId(step);
  const stepType = text(step.step_type);
  const body: Record<string, unknown> = {};
  if (options.approvalNote) body.approval_note = options.approvalNote;
  if (stepType === "receiver_allowlist") {
    body.allowlist_hash = options.allowlistHash || text(review.allowlist_summary?.hash);
    body.allowlist_count = options.allowlistCount ?? Number(review.allowlist_summary?.count ?? 0);
    if (!body.allowlist_hash) throw new Error("governance_step_allowlist_hash_missing");
  }
  if (stepType === "gray_window") {
    assertGrayWindowCanApprove(review);
  }
  const payload: WorkspaceGovernanceStepCommandPayload = {
    ...body,
    idempotency_key: stableGovernanceStepIdempotencyKey(
      "approve",
      reviewId,
      stepId,
      text(step.step_status || "pending"),
      stableStepPayloadHash(body)
    )
  };
  assertWorkspaceGovernanceStepPayloadSafe(payload);
  return payload;
}

export function buildRejectGovernanceStepPayload(
  review: WorkspaceGovernanceReviewContext,
  step: WorkspaceGovernanceStepContext,
  options: BuildWorkspaceGovernanceStepPayloadOptions = {}
): WorkspaceGovernanceStepCommandPayload {
  const reviewId = requireReviewId(review);
  const stepId = requireStepId(step);
  const body: Record<string, unknown> = {};
  if (options.rejectReason) body.reject_reason = options.rejectReason;
  const payload: WorkspaceGovernanceStepCommandPayload = {
    ...body,
    idempotency_key: stableGovernanceStepIdempotencyKey(
      "reject",
      reviewId,
      stepId,
      text(step.step_status || "pending"),
      stableStepPayloadHash(body)
    )
  };
  assertWorkspaceGovernanceStepPayloadSafe(payload);
  return payload;
}

export function buildExpireGovernanceReviewPayload(
  review: WorkspaceGovernanceReviewContext,
  options: BuildWorkspaceGovernanceStepPayloadOptions = {}
): WorkspaceGovernanceStepCommandPayload {
  const reviewId = requireReviewId(review);
  const body: Record<string, unknown> = {};
  if (options.expireReason) body.expire_reason = options.expireReason;
  const payload: WorkspaceGovernanceStepCommandPayload = {
    ...body,
    idempotency_key: stableGovernanceStepIdempotencyKey(
      "expire",
      reviewId,
      reviewId,
      text(review.review_status || "unknown_status"),
      stableStepPayloadHash(body)
    )
  };
  assertWorkspaceGovernanceStepPayloadSafe(payload);
  return payload;
}

export function assertGovernanceResponseSafe(value: WorkspaceGovernanceResponse | WorkspaceGovernanceListResponse): true {
  assertWorkspaceSensitiveSafe(value);
  const payload = value as WorkspaceGovernanceResponse;
  const serialized = JSON.stringify(value).toLowerCase();
  if (
    payload.approved === true
    || payload.push_center_job_created === true
    || payload.external_effect_job_created === true
    || payload.broadcast_job_created === true
    || payload.internal_event_created === true
    || payload.real_external_call === true
    || payload.real_external_call_executed === true
    || payload.can_claim_pass_90_plus === true
  ) {
    throw new Error("governance_api_response_violates_execution_guardrail");
  }
  if (
    payload.execution_status && payload.execution_status !== "not_execution"
    || payload.review_status === "sent"
    || payload.review_status === "completed"
    || payload.review_status === "approved"
    || payload.step_status === "sent"
    || payload.step_status === "completed"
  ) {
    throw new Error("governance_api_response_claims_execution_state");
  }
  if (
    serialized.includes("\"push_center_job_id\"")
    || serialized.includes("\"external_effect_job_id\"")
    || serialized.includes("execution started")
  ) {
    throw new Error("governance_api_response_claims_execution_state");
  }
  if (Array.isArray(payload.steps) && payload.steps.some((step) => step.step_status === "sent" || step.step_status === "completed")) {
    throw new Error("governance_api_response_claims_execution_state");
  }
  const list = value as WorkspaceGovernanceListResponse;
  if (Array.isArray(list.items)) {
    list.items.forEach((item) => assertGovernanceResponseSafe(item));
  }
  return true;
}

export function assertPushCenterBridgeResponseSafe(value: WorkspacePushCenterBridgeResponse): true {
  assertWorkspaceSensitiveSafe(value);
  const serialized = JSON.stringify(value).toLowerCase();
  if (
    value.approved === true
    || value.external_effect_job_created === true
    || value.broadcast_job_created === true
    || value.internal_event_created === true
    || value.real_external_call === true
    || value.real_external_call_executed === true
    || value.can_claim_pass_90_plus === true
  ) {
    throw new Error("push_center_bridge_response_violates_execution_guardrail");
  }
  if (
    value.push_center_job_created === true
    && (
      value.push_center_status !== "pending"
      || value.execution_status !== "push_center_pending_not_sent"
    )
  ) {
    throw new Error("push_center_bridge_response_not_pending_projection");
  }
  if (
    value.push_center_job_created !== true
    && (
      value.push_center_status !== "not_bridged"
      || value.execution_status !== "not_execution"
      || Boolean(value.push_center_job_id)
      || Boolean(value.push_center_projection_id)
    )
  ) {
    throw new Error("push_center_bridge_response_not_safe_read_state");
  }
  if (
    serialized.includes("\"external_effect_job_id\"")
    || serialized.includes("\"broadcast_job_id\"")
    || serialized.includes("\"internal_event_id\"")
    || serialized.includes("execution started")
    || serialized.includes("\"sent\"")
    || serialized.includes("\"completed\"")
  ) {
    throw new Error("push_center_bridge_response_claims_execution_state");
  }
  return true;
}

function asGovernanceResponse(value: unknown): WorkspaceGovernanceResponse {
  const payload = value && typeof value === "object" ? value as WorkspaceGovernanceResponse : { ok: false };
  assertGovernanceResponseSafe(payload);
  return payload;
}

function asGovernanceListResponse(value: unknown): WorkspaceGovernanceListResponse {
  const payload = value && typeof value === "object" ? value as WorkspaceGovernanceListResponse : { ok: false, items: [] };
  if (!Array.isArray(payload.items)) {
    payload.items = [];
  }
  assertGovernanceResponseSafe(payload);
  return payload;
}

function asPushCenterBridgeResponse(value: unknown): WorkspacePushCenterBridgeResponse {
  const payload = value && typeof value === "object" ? value as WorkspacePushCenterBridgeResponse : { ok: false };
  assertPushCenterBridgeResponseSafe(payload);
  return payload;
}

export function isGovernanceConflictError(error: unknown): boolean {
  const message = text(error instanceof Error ? error.message : error).toLowerCase();
  return message.includes("conflict") || message.includes("409") || message.includes("active governance review exists");
}

export async function requestGovernance(
  draftId: string,
  payload: WorkspaceGovernanceRequestPayload,
  config: WorkspaceGovernanceApiConfig = DEFAULT_WORKSPACE_GOVERNANCE_API_CONFIG,
  requestJson: WorkspaceDraftRequestJson = defaultWorkspaceDraftRequestJson()
): Promise<WorkspaceGovernanceResponse> {
  assertWorkspaceGovernancePayloadSafe(payload);
  return asGovernanceResponse(await requestJson(
    `${config.draftsUrl}/${encodeURIComponent(draftId)}/governance/request`,
    bodyOptions(payload)
  ));
}

export async function getGovernanceReview(
  reviewId: string,
  config: WorkspaceGovernanceApiConfig = DEFAULT_WORKSPACE_GOVERNANCE_API_CONFIG,
  requestJson: WorkspaceDraftRequestJson = defaultWorkspaceDraftRequestJson()
): Promise<WorkspaceGovernanceResponse> {
  return asGovernanceResponse(await requestJson(`${config.governanceUrl}/${encodeURIComponent(reviewId)}`));
}

export async function getDraftGovernance(
  draftId: string,
  config: WorkspaceGovernanceApiConfig = DEFAULT_WORKSPACE_GOVERNANCE_API_CONFIG,
  requestJson: WorkspaceDraftRequestJson = defaultWorkspaceDraftRequestJson()
): Promise<WorkspaceGovernanceListResponse> {
  return asGovernanceListResponse(await requestJson(`${config.draftsUrl}/${encodeURIComponent(draftId)}/governance`));
}

export async function approveGovernanceStep(
  reviewId: string,
  stepId: string,
  payload: WorkspaceGovernanceStepCommandPayload,
  config: WorkspaceGovernanceApiConfig = DEFAULT_WORKSPACE_GOVERNANCE_API_CONFIG,
  requestJson: WorkspaceDraftRequestJson = defaultWorkspaceDraftRequestJson()
): Promise<WorkspaceGovernanceResponse> {
  assertWorkspaceGovernanceStepPayloadSafe(payload);
  return asGovernanceResponse(await requestJson(
    `${config.governanceUrl}/${encodeURIComponent(reviewId)}/steps/${encodeURIComponent(stepId)}/approve`,
    bodyOptions(payload)
  ));
}

export async function rejectGovernanceStep(
  reviewId: string,
  stepId: string,
  payload: WorkspaceGovernanceStepCommandPayload,
  config: WorkspaceGovernanceApiConfig = DEFAULT_WORKSPACE_GOVERNANCE_API_CONFIG,
  requestJson: WorkspaceDraftRequestJson = defaultWorkspaceDraftRequestJson()
): Promise<WorkspaceGovernanceResponse> {
  assertWorkspaceGovernanceStepPayloadSafe(payload);
  return asGovernanceResponse(await requestJson(
    `${config.governanceUrl}/${encodeURIComponent(reviewId)}/steps/${encodeURIComponent(stepId)}/reject`,
    bodyOptions(payload)
  ));
}

export async function expireGovernanceReview(
  reviewId: string,
  payload: WorkspaceGovernanceStepCommandPayload,
  config: WorkspaceGovernanceApiConfig = DEFAULT_WORKSPACE_GOVERNANCE_API_CONFIG,
  requestJson: WorkspaceDraftRequestJson = defaultWorkspaceDraftRequestJson()
): Promise<WorkspaceGovernanceResponse> {
  assertWorkspaceGovernanceStepPayloadSafe(payload);
  return asGovernanceResponse(await requestJson(
    `${config.governanceUrl}/${encodeURIComponent(reviewId)}/expire`,
    bodyOptions(payload)
  ));
}

export async function bridgeGovernanceToPushCenter(
  reviewId: string,
  payload: WorkspacePushCenterBridgePayload,
  config: WorkspaceGovernanceApiConfig = DEFAULT_WORKSPACE_GOVERNANCE_API_CONFIG,
  requestJson: WorkspaceDraftRequestJson = defaultWorkspaceDraftRequestJson()
): Promise<WorkspacePushCenterBridgeResponse> {
  assertWorkspacePushCenterBridgePayloadSafe(payload);
  return asPushCenterBridgeResponse(await requestJson(
    `${config.governanceUrl}/${encodeURIComponent(reviewId)}/bridge-push-center`,
    bodyOptions(payload)
  ));
}

export async function getGovernancePushCenterBridge(
  reviewId: string,
  config: WorkspaceGovernanceApiConfig = DEFAULT_WORKSPACE_GOVERNANCE_API_CONFIG,
  requestJson: WorkspaceDraftRequestJson = defaultWorkspaceDraftRequestJson()
): Promise<WorkspacePushCenterBridgeResponse> {
  return asPushCenterBridgeResponse(await requestJson(
    `${config.governanceUrl}/${encodeURIComponent(reviewId)}/push-center-bridge`
  ));
}
