import { type WeComStatusInput } from "./wecom_status.js";
export interface WeComOverviewPayload {
    cards: WeComStatusInput[];
    evidenceSummary: {
        authStartRoute: string;
        authStartStatus: string;
        authCallbackRoute: string;
        authCallbackStatus: string;
        contactCallbackRoute: string;
        contactCallbackStatus: string;
        eventsRoute: string;
        eventsStatus: string;
        adminVisibility: string;
        callbackLinkedEvent: string;
        validCallbackSignature: string;
        authRecord: string;
        idempotencyEvidence: string;
        permissionScope: string;
        realExternalCallExecuted: boolean;
        finalStatus: string;
    };
}
export declare function renderWeComOverview(root: HTMLElement, payload: WeComOverviewPayload): void;
