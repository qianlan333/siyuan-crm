import { type GroupOpsStatusInput } from "./group_ops_status.js";
export interface GroupOpsOverviewPayload {
    cards: GroupOpsStatusInput[];
    evidenceSummary: {
        effectJobId: string;
        pushCenterStatus: string;
        realExternalCallEvidence: string;
        retryable: boolean;
        operatorActionRequired: boolean;
        finalStatus: string;
    };
}
export declare function renderGroupOpsOverview(root: HTMLElement, payload: GroupOpsOverviewPayload): void;
