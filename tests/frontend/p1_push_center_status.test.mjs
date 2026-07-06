import assert from "node:assert/strict";

import {
  buildPushCenterStatusViewModel,
  normalizePushCenterStatus,
  readonlyDropDoesNotMutate
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/push_center/push_center_status.js";
import { renderPushCenterOverview } from "../../aicrm_next/frontend_compat/static/admin_console/p1/push_center/push_center_overview.js";
import { executionModeForStatus, validateDropIntent } from "../../aicrm_next/frontend_compat/static/admin_console/p1/shared/interaction_contract.js";
import { statusMeta } from "../../aicrm_next/frontend_compat/static/admin_console/p1/shared/status_model.js";

const pending = normalizePushCenterStatus("pending");
assert.equal(pending, "pending");
assert.equal(statusMeta(pending).isSuccessComplete, false);
assert.notEqual(pending, "sent");

const retryable = normalizePushCenterStatus("failed", { retryable: true });
assert.equal(retryable, "retryable");
assert.equal(statusMeta(retryable).isSuccessComplete, false);

const operatorAction = normalizePushCenterStatus("pending", { operatorActionRequired: true });
assert.equal(operatorAction, "operator-action-required");
assert.equal(executionModeForStatus(operatorAction), "requires_approval");

const failedTerminal = normalizePushCenterStatus("failed");
assert.equal(failedTerminal, "failed-terminal");
assert.equal(statusMeta(failedTerminal).isSuccessComplete, false);

const downstreamPending = normalizePushCenterStatus("downstream_pending");
assert.equal(downstreamPending, "downstream-pending");
assert.equal(statusMeta(downstreamPending).isSuccessComplete, false);

const groupOpsInput = {
  key: "group_ops",
  title: "Group Ops",
  rawStatus: "governance_missing",
  evidenceStatus: "EVIDENCE_COLLECTED",
  derivedStatus: "sent_with_governance_residual_risk",
  summary: "sent but governance incomplete",
  guardrail: "governance required"
};
const groupOpsViewModel = buildPushCenterStatusViewModel(groupOpsInput);
assert.equal(groupOpsViewModel.scenario.status, "governance-missing");
assert.equal(groupOpsViewModel.executionMode, "requires_approval");
assert.equal(groupOpsViewModel.guardrails.includes("requires_approval"), true);
assert.equal(groupOpsViewModel.guardrails.includes("requires_allowlist"), true);
assert.equal(groupOpsViewModel.guardrails.includes("requires_gray_window"), true);
assert.equal(readonlyDropDoesNotMutate(groupOpsInput), true);

const blockedNoop = validateDropIntent(groupOpsViewModel.scenario, "blocked_noop");
assert.equal(blockedNoop.allowed, false);
assert.equal(blockedNoop.statusAfterDrop, "governance-missing");

const wecomInput = {
  key: "wecom_auth",
  title: "WeCom",
  rawStatus: "external_config_blocked",
  evidenceStatus: "BLOCKED_CONFIG_NOT_APPROVED",
  derivedStatus: "external_config_exception",
  summary: "config blocked",
  guardrail: "no execution"
};
const wecomViewModel = buildPushCenterStatusViewModel(wecomInput);
assert.equal(wecomViewModel.scenario.status, "external-config-blocked");
assert.equal(wecomViewModel.executionMode, "external_config_blocked");
assert.equal(wecomViewModel.guardrails.includes("requires_external_config"), true);

const root = { innerHTML: "" };
renderPushCenterOverview(root, {
  cards: [
    groupOpsInput,
    wecomInput,
    {
      key: "ops_plan_broadcast",
      title: "Ops Plan",
      rawStatus: "downstream_pending",
      evidenceStatus: "EVIDENCE_COLLECTED",
      derivedStatus: "push_center_pending",
      summary: "pending downstream",
      guardrail: "do not mark complete"
    },
    {
      key: "external_orders",
      title: "External Orders",
      rawStatus: "order_linked",
      evidenceStatus: "EVIDENCE_COLLECTED",
      derivedStatus: "order_linked",
      summary: "order linked",
      guardrail: "readonly"
    }
  ]
});

assert.equal(root.innerHTML.includes("data-drop-intent=\"blocked_noop\""), true);
assert.equal(root.innerHTML.includes("data-status-after-drop=\"governance-missing\""), true);
assert.equal(root.innerHTML.includes("external-config-blocked"), true);
assert.equal(root.innerHTML.includes("downstream-pending"), true);
assert.equal(root.innerHTML.includes("P1_READY_WITH_EXCEPTIONS"), true);
assert.equal(root.innerHTML.includes("PASS_90_PLUS"), false);
for (const forbidden of [
  "raw_external_userid",
  "receiver_plaintext",
  "Authorization",
  "access_token",
  "corpsecret",
  "13800138000",
  "secret",
  "token"
]) {
  assert.equal(root.innerHTML.includes(forbidden), false);
}

console.log("p1 push center status model OK");
