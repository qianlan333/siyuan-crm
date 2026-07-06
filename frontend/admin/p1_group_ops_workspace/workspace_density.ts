import { type WorkspaceDensity } from "./workspace_view_state.js";

export const WORKSPACE_DENSITY_OPTIONS: WorkspaceDensity[] = ["compact", "comfortable"];

export function densityClassName(density: WorkspaceDensity): string {
  return density === "compact" ? "p1-workspace-density--compact" : "p1-workspace-density--comfortable";
}

export function densityLabel(density: WorkspaceDensity): string {
  return density === "compact" ? "Compact" : "Comfortable";
}

export function densityDescription(density: WorkspaceDensity): string {
  return density === "compact"
    ? "Compact density keeps cards shorter for first-screen scanning; it does not hide status or guardrails."
    : "Comfortable density keeps full summaries visible for review; it remains memory-only.";
}
