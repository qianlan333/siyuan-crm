import { type WorkspaceCanvasLane } from "./workspace_grouping.js";
import { type WorkspaceViewState } from "./workspace_view_state.js";
export type WorkspaceKeyboardKey = "ArrowUp" | "ArrowDown" | "ArrowLeft" | "ArrowRight" | "Enter" | " " | "Escape";
export declare function moveWorkspaceCanvasSelection(lanes: WorkspaceCanvasLane[], viewState: WorkspaceViewState, key: WorkspaceKeyboardKey): WorkspaceViewState;
export declare function keyboardHintText(): string;
