import { type WorkspaceFixture } from "./workspace_fixture.js";
export interface WorkspaceApiConfig {
    plansUrl: string;
    planDetailBaseUrl: string;
    planGroupsSuffix: string;
    planNodesSuffix: string;
    planExecutionsBaseUrl: string;
    pushCenterJobsUrl: string;
}
export type RequestJson = (url: string, options?: {
    method?: string;
}) => Promise<unknown>;
export declare const DEFAULT_WORKSPACE_API_CONFIG: WorkspaceApiConfig;
export declare function parseWorkspaceApiConfig(documentRef?: Document): WorkspaceApiConfig;
export declare function defaultRequestJson(): RequestJson;
export declare function loadGroupOpsWorkspaceData(config?: WorkspaceApiConfig, requestJson?: RequestJson): Promise<WorkspaceFixture>;
