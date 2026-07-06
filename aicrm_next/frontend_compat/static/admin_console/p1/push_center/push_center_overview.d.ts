import { type PushCenterStatusInput } from "./push_center_status.js";
export interface PushCenterOverviewPayload {
    cards: PushCenterStatusInput[];
}
export declare function renderPushCenterOverview(root: HTMLElement, payload: PushCenterOverviewPayload): void;
