export type EvidenceStatus = "ready" | "pending" | "sent" | "blocked" | "external-config-blocked" | "governance-missing" | "evidence-incomplete" | "downstream-pending" | "operator-action-required" | "retryable" | "failed-terminal";
export type ScenarioKey = "external_orders" | "ops_plan_broadcast" | "group_ops" | "wecom_auth";
export type FinalVerdict = "P1_READY_WITH_EXCEPTIONS" | "PASS_90_PLUS" | "BLOCKED";
export interface ScenarioEvidence {
    key: ScenarioKey;
    title: string;
    status: EvidenceStatus;
    evidenceStatus: string;
    derivedStatus: string;
    summary: string;
    guardrail: string;
    route?: string;
}
export interface BusinessClosurePayload {
    finalVerdict: FinalVerdict;
    canClaimPass90Plus: boolean;
    scenarios: ScenarioEvidence[];
}
export interface StatusMeta {
    label: string;
    tone: "success" | "info" | "warning" | "danger" | "neutral";
    isSuccessComplete: boolean;
}
export declare const STATUS_META: Record<EvidenceStatus, StatusMeta>;
export declare function normalizeEvidenceStatus(rawStatus: string): EvidenceStatus;
export declare function statusMeta(status: EvidenceStatus): StatusMeta;
export declare function canRenderGlobalPass(payload: BusinessClosurePayload): boolean;
export declare function scenarioNeedsOperatorAction(scenario: ScenarioEvidence): boolean;
