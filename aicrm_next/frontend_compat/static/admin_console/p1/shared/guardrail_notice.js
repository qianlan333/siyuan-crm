import { escapeHtml } from "./dom.js";
import { scenarioNeedsOperatorAction } from "./status_model.js";
export function renderGuardrailNotice(scenario) {
    const actionText = scenarioNeedsOperatorAction(scenario) ? "需要继续跟踪" : "当前无需运营动作";
    return `
    <p class="p1-closure-guardrail" data-operator-action="${scenarioNeedsOperatorAction(scenario) ? "required" : "none"}">
      ${escapeHtml(scenario.guardrail)}
      <strong>${escapeHtml(actionText)}</strong>
    </p>
  `;
}
