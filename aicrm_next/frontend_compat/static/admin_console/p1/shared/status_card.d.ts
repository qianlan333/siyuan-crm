import { type ScenarioEvidence } from "./status_model.js";
export interface StatusCardOptions {
    dragHandle?: boolean;
    dragDisabledReason?: string;
}
export declare function renderStatusCard(scenario: ScenarioEvidence, options?: StatusCardOptions): string;
