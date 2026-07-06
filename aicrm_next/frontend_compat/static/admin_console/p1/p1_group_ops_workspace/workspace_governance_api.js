import { DEFAULT_WORKSPACE_DRAFT_API_CONFIG, assertWorkspaceSensitiveSafe, defaultWorkspaceDraftRequestJson, workspaceSimpleHash } from "./workspace_draft_api.js";
export const DEFAULT_WORKSPACE_GOVERNANCE_API_CONFIG = {
    ...DEFAULT_WORKSPACE_DRAFT_API_CONFIG,
    governanceUrl: "/api/admin/p1/group-ops-workspace/governance"
};
function text(value) {
    return String(value ?? "").trim();
}
function bodyOptions(payload) {
    return {
        method: "POST",
        body: JSON.stringify(payload)
    };
}
function defaultGrayWindow(snapshotHash) {
    const dayOffset = Number.parseInt(workspaceSimpleHash(snapshotHash || "no_snapshot").slice(0, 2), 16) % 20;
    const day = String(1 + dayOffset).padStart(2, "0");
    return {
        start_at: `2026-06-${day}T09:00:00+08:00`,
        end_at: `2026-06-${day}T10:00:00+08:00`,
        timezone: "Asia/Shanghai"
    };
}
function stableGrayWindowHash(grayWindow) {
    return workspaceSimpleHash(JSON.stringify({
        start_at: grayWindow.start_at,
        end_at: grayWindow.end_at,
        timezone: grayWindow.timezone
    }));
}
export function stablePushCenterBridgeIdempotencyKey(reviewId, snapshotHash, allowlistHash, grayWindowHash) {
    return [
        "p1-gow-push-center-bridge",
        text(reviewId),
        text(snapshotHash || "no_snapshot"),
        text(allowlistHash || "allowlist_missing"),
        text(grayWindowHash || "window_missing")
    ].join(":");
}
export function stableGovernanceIdempotencyKey(draftId, snapshotHash, allowlistHash, grayWindowHash) {
    return [
        "p1-gow-governance",
        text(draftId),
        text(snapshotHash || "no_snapshot"),
        text(allowlistHash || "allowlist_missing"),
        text(grayWindowHash || "window_missing")
    ].join(":");
}
function stableStepPayloadHash(payload) {
    return workspaceSimpleHash(JSON.stringify(payload, Object.keys(payload).sort()));
}
export function stableGovernanceStepIdempotencyKey(action, reviewId, stepIdOrReview, currentStatus, payloadHash) {
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
export function assertWorkspaceGovernancePayloadSafe(payload) {
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
export function assertWorkspaceGovernanceStepPayloadSafe(payload) {
    assertWorkspaceSensitiveSafe(payload);
    if (!payload.idempotency_key) {
        throw new Error("governance_step_payload_missing_idempotency_key");
    }
    if (payload.allowlist_count !== undefined && (!Number.isFinite(payload.allowlist_count) || payload.allowlist_count < 0)) {
        throw new Error("governance_step_payload_invalid_allowlist_count");
    }
    return true;
}
export function assertWorkspacePushCenterBridgePayloadSafe(payload) {
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
export function buildWorkspaceGovernanceRequestPayload(draftId, snapshotHash, options = {}) {
    const grayWindow = options.grayWindow || defaultGrayWindow(snapshotHash);
    const allowlistHash = options.allowlistHash || `allowlist-${workspaceSimpleHash(`${draftId}:${snapshotHash}:summary`)}`;
    const grayWindowHash = stableGrayWindowHash(grayWindow);
    const payload = {
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
export function buildPushCenterBridgePayload(review, options = {}) {
    const reviewId = requireReviewId(review);
    const snapshotHash = text(review.snapshot_hash);
    if (!snapshotHash)
        throw new Error("push_center_bridge_missing_snapshot_hash");
    const allowlistHash = options.allowlistHash || text(review.allowlist_summary?.hash);
    const allowlistCount = options.allowlistCount ?? Number(review.allowlist_summary?.count ?? 0);
    const grayWindow = options.grayWindow || review.gray_window;
    if (!grayWindow?.start_at || !grayWindow?.end_at || !grayWindow?.timezone) {
        throw new Error("push_center_bridge_missing_gray_window");
    }
    const safeGrayWindow = {
        start_at: grayWindow.start_at,
        end_at: grayWindow.end_at,
        timezone: grayWindow.timezone,
        window_status: text(grayWindow.window_status || "approved")
    };
    const grayWindowHash = stableGrayWindowHash(safeGrayWindow);
    const payload = {
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
function requireReviewId(review) {
    const reviewId = text(review.review_id);
    if (!reviewId)
        throw new Error("governance_step_missing_review_id");
    return reviewId;
}
function requireStepId(step) {
    const stepId = text(step.step_id);
    if (!stepId)
        throw new Error("governance_step_missing_step_id");
    return stepId;
}
function assertGrayWindowCanApprove(review) {
    const endAt = Date.parse(String(review.gray_window?.end_at || ""));
    if (!Number.isFinite(endAt)) {
        throw new Error("governance_step_invalid_gray_window");
    }
    if (endAt <= Date.now()) {
        throw new Error("governance_step_gray_window_expired");
    }
}
export function buildApproveGovernanceStepPayload(review, step, options = {}) {
    const reviewId = requireReviewId(review);
    const stepId = requireStepId(step);
    const stepType = text(step.step_type);
    const body = {};
    if (options.approvalNote)
        body.approval_note = options.approvalNote;
    if (stepType === "receiver_allowlist") {
        body.allowlist_hash = options.allowlistHash || text(review.allowlist_summary?.hash);
        body.allowlist_count = options.allowlistCount ?? Number(review.allowlist_summary?.count ?? 0);
        if (!body.allowlist_hash)
            throw new Error("governance_step_allowlist_hash_missing");
    }
    if (stepType === "gray_window") {
        assertGrayWindowCanApprove(review);
    }
    const payload = {
        ...body,
        idempotency_key: stableGovernanceStepIdempotencyKey("approve", reviewId, stepId, text(step.step_status || "pending"), stableStepPayloadHash(body))
    };
    assertWorkspaceGovernanceStepPayloadSafe(payload);
    return payload;
}
export function buildRejectGovernanceStepPayload(review, step, options = {}) {
    const reviewId = requireReviewId(review);
    const stepId = requireStepId(step);
    const body = {};
    if (options.rejectReason)
        body.reject_reason = options.rejectReason;
    const payload = {
        ...body,
        idempotency_key: stableGovernanceStepIdempotencyKey("reject", reviewId, stepId, text(step.step_status || "pending"), stableStepPayloadHash(body))
    };
    assertWorkspaceGovernanceStepPayloadSafe(payload);
    return payload;
}
export function buildExpireGovernanceReviewPayload(review, options = {}) {
    const reviewId = requireReviewId(review);
    const body = {};
    if (options.expireReason)
        body.expire_reason = options.expireReason;
    const payload = {
        ...body,
        idempotency_key: stableGovernanceStepIdempotencyKey("expire", reviewId, reviewId, text(review.review_status || "unknown_status"), stableStepPayloadHash(body))
    };
    assertWorkspaceGovernanceStepPayloadSafe(payload);
    return payload;
}
export function assertGovernanceResponseSafe(value) {
    assertWorkspaceSensitiveSafe(value);
    const payload = value;
    const serialized = JSON.stringify(value).toLowerCase();
    if (payload.approved === true
        || payload.push_center_job_created === true
        || payload.external_effect_job_created === true
        || payload.broadcast_job_created === true
        || payload.internal_event_created === true
        || payload.real_external_call === true
        || payload.real_external_call_executed === true
        || payload.can_claim_pass_90_plus === true) {
        throw new Error("governance_api_response_violates_execution_guardrail");
    }
    if (payload.execution_status && payload.execution_status !== "not_execution"
        || payload.review_status === "sent"
        || payload.review_status === "completed"
        || payload.review_status === "approved"
        || payload.step_status === "sent"
        || payload.step_status === "completed") {
        throw new Error("governance_api_response_claims_execution_state");
    }
    if (serialized.includes("\"push_center_job_id\"")
        || serialized.includes("\"external_effect_job_id\"")
        || serialized.includes("execution started")) {
        throw new Error("governance_api_response_claims_execution_state");
    }
    if (Array.isArray(payload.steps) && payload.steps.some((step) => step.step_status === "sent" || step.step_status === "completed")) {
        throw new Error("governance_api_response_claims_execution_state");
    }
    const list = value;
    if (Array.isArray(list.items)) {
        list.items.forEach((item) => assertGovernanceResponseSafe(item));
    }
    return true;
}
export function assertPushCenterBridgeResponseSafe(value) {
    assertWorkspaceSensitiveSafe(value);
    const serialized = JSON.stringify(value).toLowerCase();
    if (value.approved === true
        || value.external_effect_job_created === true
        || value.broadcast_job_created === true
        || value.internal_event_created === true
        || value.real_external_call === true
        || value.real_external_call_executed === true
        || value.can_claim_pass_90_plus === true) {
        throw new Error("push_center_bridge_response_violates_execution_guardrail");
    }
    if (value.push_center_job_created === true
        && (value.push_center_status !== "pending"
            || value.execution_status !== "push_center_pending_not_sent")) {
        throw new Error("push_center_bridge_response_not_pending_projection");
    }
    if (value.push_center_job_created !== true
        && (value.push_center_status !== "not_bridged"
            || value.execution_status !== "not_execution"
            || Boolean(value.push_center_job_id)
            || Boolean(value.push_center_projection_id))) {
        throw new Error("push_center_bridge_response_not_safe_read_state");
    }
    if (serialized.includes("\"external_effect_job_id\"")
        || serialized.includes("\"broadcast_job_id\"")
        || serialized.includes("\"internal_event_id\"")
        || serialized.includes("execution started")
        || serialized.includes("\"sent\"")
        || serialized.includes("\"completed\"")) {
        throw new Error("push_center_bridge_response_claims_execution_state");
    }
    return true;
}
function asGovernanceResponse(value) {
    const payload = value && typeof value === "object" ? value : { ok: false };
    assertGovernanceResponseSafe(payload);
    return payload;
}
function asGovernanceListResponse(value) {
    const payload = value && typeof value === "object" ? value : { ok: false, items: [] };
    if (!Array.isArray(payload.items)) {
        payload.items = [];
    }
    assertGovernanceResponseSafe(payload);
    return payload;
}
function asPushCenterBridgeResponse(value) {
    const payload = value && typeof value === "object" ? value : { ok: false };
    assertPushCenterBridgeResponseSafe(payload);
    return payload;
}
export function isGovernanceConflictError(error) {
    const message = text(error instanceof Error ? error.message : error).toLowerCase();
    return message.includes("conflict") || message.includes("409") || message.includes("active governance review exists");
}
export async function requestGovernance(draftId, payload, config = DEFAULT_WORKSPACE_GOVERNANCE_API_CONFIG, requestJson = defaultWorkspaceDraftRequestJson()) {
    assertWorkspaceGovernancePayloadSafe(payload);
    return asGovernanceResponse(await requestJson(`${config.draftsUrl}/${encodeURIComponent(draftId)}/governance/request`, bodyOptions(payload)));
}
export async function getGovernanceReview(reviewId, config = DEFAULT_WORKSPACE_GOVERNANCE_API_CONFIG, requestJson = defaultWorkspaceDraftRequestJson()) {
    return asGovernanceResponse(await requestJson(`${config.governanceUrl}/${encodeURIComponent(reviewId)}`));
}
export async function getDraftGovernance(draftId, config = DEFAULT_WORKSPACE_GOVERNANCE_API_CONFIG, requestJson = defaultWorkspaceDraftRequestJson()) {
    return asGovernanceListResponse(await requestJson(`${config.draftsUrl}/${encodeURIComponent(draftId)}/governance`));
}
export async function approveGovernanceStep(reviewId, stepId, payload, config = DEFAULT_WORKSPACE_GOVERNANCE_API_CONFIG, requestJson = defaultWorkspaceDraftRequestJson()) {
    assertWorkspaceGovernanceStepPayloadSafe(payload);
    return asGovernanceResponse(await requestJson(`${config.governanceUrl}/${encodeURIComponent(reviewId)}/steps/${encodeURIComponent(stepId)}/approve`, bodyOptions(payload)));
}
export async function rejectGovernanceStep(reviewId, stepId, payload, config = DEFAULT_WORKSPACE_GOVERNANCE_API_CONFIG, requestJson = defaultWorkspaceDraftRequestJson()) {
    assertWorkspaceGovernanceStepPayloadSafe(payload);
    return asGovernanceResponse(await requestJson(`${config.governanceUrl}/${encodeURIComponent(reviewId)}/steps/${encodeURIComponent(stepId)}/reject`, bodyOptions(payload)));
}
export async function expireGovernanceReview(reviewId, payload, config = DEFAULT_WORKSPACE_GOVERNANCE_API_CONFIG, requestJson = defaultWorkspaceDraftRequestJson()) {
    assertWorkspaceGovernanceStepPayloadSafe(payload);
    return asGovernanceResponse(await requestJson(`${config.governanceUrl}/${encodeURIComponent(reviewId)}/expire`, bodyOptions(payload)));
}
export async function bridgeGovernanceToPushCenter(reviewId, payload, config = DEFAULT_WORKSPACE_GOVERNANCE_API_CONFIG, requestJson = defaultWorkspaceDraftRequestJson()) {
    assertWorkspacePushCenterBridgePayloadSafe(payload);
    return asPushCenterBridgeResponse(await requestJson(`${config.governanceUrl}/${encodeURIComponent(reviewId)}/bridge-push-center`, bodyOptions(payload)));
}
export async function getGovernancePushCenterBridge(reviewId, config = DEFAULT_WORKSPACE_GOVERNANCE_API_CONFIG, requestJson = defaultWorkspaceDraftRequestJson()) {
    return asPushCenterBridgeResponse(await requestJson(`${config.governanceUrl}/${encodeURIComponent(reviewId)}/push-center-bridge`));
}
