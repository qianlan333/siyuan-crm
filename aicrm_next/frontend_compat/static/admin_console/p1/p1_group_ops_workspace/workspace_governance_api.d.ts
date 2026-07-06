import { type WorkspaceDraftApiConfig, type WorkspaceDraftRequestJson } from "./workspace_draft_api.js";
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
export declare const DEFAULT_WORKSPACE_GOVERNANCE_API_CONFIG: WorkspaceGovernanceApiConfig;
export declare function stablePushCenterBridgeIdempotencyKey(reviewId: string, snapshotHash: string, allowlistHash: string, grayWindowHash: string): string;
export declare function stableGovernanceIdempotencyKey(draftId: string, snapshotHash: string, allowlistHash: string, grayWindowHash: string): string;
export declare function stableGovernanceStepIdempotencyKey(action: WorkspaceGovernanceStepAction, reviewId: string, stepIdOrReview: string, currentStatus: string, payloadHash: string): string;
export declare function assertWorkspaceGovernancePayloadSafe(payload: WorkspaceGovernanceRequestPayload): true;
export declare function assertWorkspaceGovernanceStepPayloadSafe(payload: WorkspaceGovernanceStepCommandPayload): true;
export declare function assertWorkspacePushCenterBridgePayloadSafe(payload: WorkspacePushCenterBridgePayload): true;
export declare function buildWorkspaceGovernanceRequestPayload(draftId: string, snapshotHash: string, options?: BuildWorkspaceGovernancePayloadOptions): WorkspaceGovernanceRequestPayload;
export declare function buildPushCenterBridgePayload(review: WorkspaceGovernanceReviewContext & {
    snapshot_hash?: string;
}, options?: BuildWorkspacePushCenterBridgePayloadOptions): WorkspacePushCenterBridgePayload;
export declare function buildApproveGovernanceStepPayload(review: WorkspaceGovernanceReviewContext, step: WorkspaceGovernanceStepContext, options?: BuildWorkspaceGovernanceStepPayloadOptions): WorkspaceGovernanceStepCommandPayload;
export declare function buildRejectGovernanceStepPayload(review: WorkspaceGovernanceReviewContext, step: WorkspaceGovernanceStepContext, options?: BuildWorkspaceGovernanceStepPayloadOptions): WorkspaceGovernanceStepCommandPayload;
export declare function buildExpireGovernanceReviewPayload(review: WorkspaceGovernanceReviewContext, options?: BuildWorkspaceGovernanceStepPayloadOptions): WorkspaceGovernanceStepCommandPayload;
export declare function assertGovernanceResponseSafe(value: WorkspaceGovernanceResponse | WorkspaceGovernanceListResponse): true;
export declare function assertPushCenterBridgeResponseSafe(value: WorkspacePushCenterBridgeResponse): true;
export declare function isGovernanceConflictError(error: unknown): boolean;
export declare function requestGovernance(draftId: string, payload: WorkspaceGovernanceRequestPayload, config?: WorkspaceGovernanceApiConfig, requestJson?: WorkspaceDraftRequestJson): Promise<WorkspaceGovernanceResponse>;
export declare function getGovernanceReview(reviewId: string, config?: WorkspaceGovernanceApiConfig, requestJson?: WorkspaceDraftRequestJson): Promise<WorkspaceGovernanceResponse>;
export declare function getDraftGovernance(draftId: string, config?: WorkspaceGovernanceApiConfig, requestJson?: WorkspaceDraftRequestJson): Promise<WorkspaceGovernanceListResponse>;
export declare function approveGovernanceStep(reviewId: string, stepId: string, payload: WorkspaceGovernanceStepCommandPayload, config?: WorkspaceGovernanceApiConfig, requestJson?: WorkspaceDraftRequestJson): Promise<WorkspaceGovernanceResponse>;
export declare function rejectGovernanceStep(reviewId: string, stepId: string, payload: WorkspaceGovernanceStepCommandPayload, config?: WorkspaceGovernanceApiConfig, requestJson?: WorkspaceDraftRequestJson): Promise<WorkspaceGovernanceResponse>;
export declare function expireGovernanceReview(reviewId: string, payload: WorkspaceGovernanceStepCommandPayload, config?: WorkspaceGovernanceApiConfig, requestJson?: WorkspaceDraftRequestJson): Promise<WorkspaceGovernanceResponse>;
export declare function bridgeGovernanceToPushCenter(reviewId: string, payload: WorkspacePushCenterBridgePayload, config?: WorkspaceGovernanceApiConfig, requestJson?: WorkspaceDraftRequestJson): Promise<WorkspacePushCenterBridgeResponse>;
export declare function getGovernancePushCenterBridge(reviewId: string, config?: WorkspaceGovernanceApiConfig, requestJson?: WorkspaceDraftRequestJson): Promise<WorkspacePushCenterBridgeResponse>;
