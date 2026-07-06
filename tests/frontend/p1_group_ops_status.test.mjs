import assert from "node:assert/strict";

import {
  buildGroupOpsStatusViewModel,
  groupOpsSentIsGovernanceComplete,
  normalizeGroupOpsStatus,
  readonlyGroupOpsDropDoesNotMutate
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/group_ops/group_ops_status.js";
import { renderGroupOpsOverview } from "../../aicrm_next/frontend_compat/static/admin_console/p1/group_ops/group_ops_overview.js";
import { statusMeta } from "../../aicrm_next/frontend_compat/static/admin_console/p1/shared/status_model.js";

const sent = normalizeGroupOpsStatus("sent");
assert.equal(sent, "sent");
assert.equal(statusMeta(sent).isSuccessComplete, true);
assert.equal(
  groupOpsSentIsGovernanceComplete({
    title: "发送链路证据",
    rawStatus: "sent",
    evidenceStatus: "EVIDENCE_COLLECTED",
    derivedStatus: "push_center_sent",
    summary: "sent",
    guardrail: "not governance complete"
  }),
  false
);

const governanceMissingInput = {
  title: "治理证据",
  rawStatus: "governance_missing",
  evidenceStatus: "EVIDENCE_COLLECTED",
  derivedStatus: "governance_residual_risk",
  summary: "governance missing",
  guardrail: "requires governance evidence"
};
const governanceViewModel = buildGroupOpsStatusViewModel(governanceMissingInput);
assert.equal(governanceViewModel.scenario.status, "governance-missing");
assert.equal(governanceViewModel.isSuccessComplete, false);
assert.equal(governanceViewModel.guardrails.includes("requires_approval"), true);
assert.equal(governanceViewModel.guardrails.includes("requires_allowlist"), true);
assert.equal(governanceViewModel.guardrails.includes("requires_gray_window"), true);
assert.equal(governanceViewModel.guardrails.includes("no_direct_send"), true);
assert.equal(readonlyGroupOpsDropDoesNotMutate(governanceMissingInput), true);

const incomplete = normalizeGroupOpsStatus("evidence_incomplete");
assert.equal(incomplete, "evidence-incomplete");
assert.equal(statusMeta(incomplete).isSuccessComplete, false);

const operatorAction = normalizeGroupOpsStatus("pending", { operatorActionRequired: true });
assert.equal(operatorAction, "operator-action-required");

const retryable = normalizeGroupOpsStatus("failed", { retryable: true });
assert.equal(retryable, "retryable");
assert.equal(statusMeta(retryable).isSuccessComplete, false);

const failedTerminal = normalizeGroupOpsStatus("failed");
assert.equal(failedTerminal, "failed-terminal");
assert.equal(statusMeta(failedTerminal).isSuccessComplete, false);

const root = { innerHTML: "" };
renderGroupOpsOverview(root, {
  cards: [
    {
      title: "发送链路证据",
      rawStatus: "sent",
      evidenceStatus: "EVIDENCE_COLLECTED",
      derivedStatus: "push_center_sent",
      evidenceId: "external_effect_job:97",
      summary: "sent but not governance complete",
      guardrail: "do not claim governance complete"
    },
    governanceMissingInput,
    {
      title: "最终判定",
      rawStatus: "evidence_incomplete",
      evidenceStatus: "EVIDENCE_COLLECTED",
      derivedStatus: "not_pass_90_plus_candidate",
      summary: "not candidate",
      guardrail: "evidence incomplete"
    }
  ],
  evidenceSummary: {
    effectJobId: "external_effect_job:97",
    pushCenterStatus: "sent",
    realExternalCallEvidence: "collected_in_prior_report",
    retryable: false,
    operatorActionRequired: false,
    finalStatus: "EVIDENCE_COLLECTED"
  }
});

assert.equal(root.innerHTML.includes("external_effect_job:97"), true);
assert.equal(root.innerHTML.includes("data-drop-intent=\"blocked_noop\""), true);
assert.equal(root.innerHTML.includes("data-status-after-drop=\"governance-missing\""), true);
assert.equal(root.innerHTML.includes("requires_allowlist"), true);
assert.equal(root.innerHTML.includes("requires_gray_window"), true);
assert.equal(root.innerHTML.includes("no_direct_send"), true);
assert.equal(root.innerHTML.includes("not_pass_90_plus_candidate"), true);
for (const forbidden of [
  "raw_external_userid",
  "receiver_plaintext",
  "raw_chat_id",
  "raw_member_id",
  "Authorization",
  "access_token",
  "corpsecret",
  "13800138000",
  "secret",
  "token"
]) {
  assert.equal(root.innerHTML.includes(forbidden), false);
}

console.log("p1 group ops status model OK");
