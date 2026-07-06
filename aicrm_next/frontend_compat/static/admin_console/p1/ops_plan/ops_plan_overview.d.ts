import { type OpsPlanStatusInput } from "./ops_plan_status.js";
export interface OpsPlanOverviewPayload {
    cards: OpsPlanStatusInput[];
    evidenceSummary: {
        planId: string;
        planType: string;
        internalEvent: string;
        consumerName: string;
        plannerResult: string;
        broadcastJobId: string;
        pushCenterStatus: string;
        downstreamStatus: string;
        externalEffectJob: string;
        realExternalCallExecuted: boolean;
        finalStatus: string;
    };
}
export declare function renderOpsPlanOverview(root: HTMLElement, payload: OpsPlanOverviewPayload): void;
