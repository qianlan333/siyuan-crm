import assert from "node:assert/strict";

import { renderPushCenterOverview } from "../../aicrm_next/frontend_compat/static/admin_console/p1/push_center/push_center_overview.js";
import { renderGroupOpsOverview } from "../../aicrm_next/frontend_compat/static/admin_console/p1/group_ops/group_ops_overview.js";
import { renderOpsPlanOverview } from "../../aicrm_next/frontend_compat/static/admin_console/p1/ops_plan/ops_plan_overview.js";

function assertNoSensitiveFixtureStrings(html) {
  for (const forbidden of [
    "raw_external_userid",
    "receiver_plaintext",
    "raw_callback_body",
    "raw_target_list",
    "raw_member_id",
    "openid",
    "unionid",
    "Authorization",
    "access_token",
    "corpsecret",
    "13800138000",
    "secret",
    "token"
  ]) {
    assert.equal(html.includes(forbidden), false);
  }
}

const pushRoot = { innerHTML: "" };
renderPushCenterOverview(pushRoot, {
  cards: [
    {
      key: "ops_plan_broadcast",
      title: "Push Center pending",
      rawStatus: "pending",
      evidenceStatus: "EVIDENCE_COLLECTED",
      derivedStatus: "push_center_pending",
      summary: "pending",
      guardrail: "requires push center"
    },
    {
      key: "external_orders",
      title: "Retryable job",
      rawStatus: "failed",
      evidenceStatus: "EVIDENCE_COLLECTED",
      derivedStatus: "retryable_failure",
      summary: "retryable",
      guardrail: "not complete",
      retryable: true
    },
    {
      key: "group_ops",
      title: "Operator action",
      rawStatus: "pending",
      evidenceStatus: "EVIDENCE_COLLECTED",
      derivedStatus: "operator_action_required",
      summary: "action",
      guardrail: "approval required",
      operatorActionRequired: true
    },
    {
      key: "wecom_auth",
      title: "WeCom blocked",
      rawStatus: "external_config_blocked",
      evidenceStatus: "BLOCKED_CONFIG_NOT_APPROVED",
      derivedStatus: "external_config_exception",
      summary: "blocked",
      guardrail: "not executable"
    }
  ]
});
assert.equal(pushRoot.innerHTML.includes("p1-draft-shell"), true);
assert.equal(pushRoot.innerHTML.includes("data-persistence=\"memory_only\""), true);
assert.equal(pushRoot.innerHTML.includes("data-can-claim-pass90=\"false\""), true);
assert.equal(pushRoot.innerHTML.includes("data-drop-intent=\"blocked_noop\""), true);
assert.equal(pushRoot.innerHTML.includes("data-evidence-status=\"pending\""), true);
assert.equal(pushRoot.innerHTML.includes("data-execution-mode=\"preview_only\""), true);
assert.equal(pushRoot.innerHTML.includes("data-evidence-status=\"retryable\""), true);
assert.equal(pushRoot.innerHTML.includes("data-execution-mode=\"requires_approval\""), true);
assert.equal(pushRoot.innerHTML.includes("external_config_blocked"), true);
assert.equal(pushRoot.innerHTML.includes("PASS_90_PLUS"), false);
assertNoSensitiveFixtureStrings(pushRoot.innerHTML);

const groupOpsRoot = { innerHTML: "" };
renderGroupOpsOverview(groupOpsRoot, {
  cards: [
    {
      title: "发送链路证据",
      rawStatus: "sent",
      evidenceStatus: "EVIDENCE_COLLECTED",
      derivedStatus: "push_center_sent",
      evidenceId: "external_effect_job:97",
      summary: "sent but not governance complete",
      guardrail: "sent does not bypass governance"
    },
    {
      title: "治理证据",
      rawStatus: "governance_missing",
      evidenceStatus: "EVIDENCE_COLLECTED",
      derivedStatus: "governance_residual_risk",
      summary: "governance missing",
      guardrail: "requires approval allowlist gray window"
    },
    {
      title: "最终判定",
      rawStatus: "evidence_incomplete",
      evidenceStatus: "EVIDENCE_COLLECTED",
      derivedStatus: "not_pass_90_plus_candidate",
      summary: "incomplete",
      guardrail: "not pass complete"
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
assert.equal(groupOpsRoot.innerHTML.includes("p1-draft-shell"), true);
assert.equal(groupOpsRoot.innerHTML.includes("data-persistence=\"memory_only\""), true);
assert.equal(groupOpsRoot.innerHTML.includes("data-can-claim-pass90=\"false\""), true);
assert.equal(groupOpsRoot.innerHTML.includes("data-evidence-status=\"sent\""), true);
assert.equal(groupOpsRoot.innerHTML.includes("data-status-after-drop=\"sent\""), true);
assert.equal(groupOpsRoot.innerHTML.includes("requires_approval"), true);
assert.equal(groupOpsRoot.innerHTML.includes("requires_allowlist"), true);
assert.equal(groupOpsRoot.innerHTML.includes("requires_gray_window"), true);
assert.equal(groupOpsRoot.innerHTML.includes("no_direct_send"), true);
assert.equal(groupOpsRoot.innerHTML.includes("PASS_90_PLUS"), false);
assertNoSensitiveFixtureStrings(groupOpsRoot.innerHTML);

const opsPlanRoot = { innerHTML: "" };
renderOpsPlanOverview(opsPlanRoot, {
  cards: [
    {
      title: "Planner consumer",
      rawStatus: "planner_created_broadcast_job",
      evidenceStatus: "EVIDENCE_COLLECTED",
      derivedStatus: "planner_created_broadcast_job",
      evidenceId: "broadcast_task_planner_consumer",
      summary: "broadcast_job created",
      guardrail: "not external effect sent"
    },
    {
      title: "Push Center projection",
      rawStatus: "push_center_pending",
      evidenceStatus: "EVIDENCE_COLLECTED",
      derivedStatus: "push_center_pending",
      evidenceId: "broadcast_job:3644",
      summary: "pending",
      guardrail: "not sent"
    }
  ],
  evidenceSummary: {
    planId: "p0-1283-plan-20260615152503",
    planType: "cloud_plan",
    internalEvent: "ops_plan.approved",
    consumerName: "broadcast_task_planner_consumer",
    plannerResult: "planner_created_broadcast_job",
    broadcastJobId: "broadcast_job:3644",
    pushCenterStatus: "pending",
    downstreamStatus: "downstream_pending",
    externalEffectJob: "not_created",
    realExternalCallExecuted: false,
    finalStatus: "EVIDENCE_COLLECTED"
  }
});
assert.equal(opsPlanRoot.innerHTML.includes("p1-draft-shell"), true);
assert.equal(opsPlanRoot.innerHTML.includes("data-persistence=\"memory_only\""), true);
assert.equal(opsPlanRoot.innerHTML.includes("data-evidence-status=\"downstream-pending\""), true);
assert.equal(opsPlanRoot.innerHTML.includes("data-execution-mode=\"preview_only\""), true);
assert.equal(opsPlanRoot.innerHTML.includes("data-status-after-drop=\"downstream-pending\""), true);
assert.equal(opsPlanRoot.innerHTML.includes("<dt>Completion</dt><dd>complete</dd>"), false);
assert.equal(opsPlanRoot.innerHTML.includes("external_effect_sent"), false);
assert.equal(opsPlanRoot.innerHTML.includes("PASS_90_PLUS"), false);
assertNoSensitiveFixtureStrings(opsPlanRoot.innerHTML);

console.log("p1 business pages interaction shell OK");
