import assert from "node:assert/strict";

import {
  broadcastJobCreatedIsExternalEffectSent,
  buildOpsPlanStatusViewModel,
  normalizeOpsPlanStatus,
  pushCenterPendingIsSent,
  readonlyOpsPlanDropDoesNotMutate
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/ops_plan/ops_plan_status.js";
import { renderOpsPlanOverview } from "../../aicrm_next/frontend_compat/static/admin_console/p1/ops_plan/ops_plan_overview.js";
import { validateDropIntent } from "../../aicrm_next/frontend_compat/static/admin_console/p1/shared/interaction_contract.js";
import { statusMeta } from "../../aicrm_next/frontend_compat/static/admin_console/p1/shared/status_model.js";

const downstreamPending = normalizeOpsPlanStatus("downstream_pending");
assert.equal(downstreamPending, "downstream-pending");
assert.equal(statusMeta(downstreamPending).isSuccessComplete, false);
assert.notEqual(downstreamPending, "sent");

const pushCenterPendingInput = {
  title: "Push Center projection",
  rawStatus: "push_center_pending",
  evidenceStatus: "EVIDENCE_COLLECTED",
  derivedStatus: "push_center_pending",
  summary: "pending",
  guardrail: "not sent"
};
const pushCenterViewModel = buildOpsPlanStatusViewModel(pushCenterPendingInput);
assert.equal(pushCenterViewModel.scenario.status, "downstream-pending");
assert.equal(pushCenterPendingIsSent(pushCenterPendingInput), false);
assert.equal(pushCenterViewModel.isSuccessComplete, false);

const broadcastJobInput = {
  title: "Planner consumer",
  rawStatus: "planner_created_broadcast_job",
  evidenceStatus: "EVIDENCE_COLLECTED",
  derivedStatus: "planner_created_broadcast_job",
  summary: "broadcast_job:3644",
  guardrail: "not external effect sent"
};
const broadcastJobViewModel = buildOpsPlanStatusViewModel(broadcastJobInput);
assert.equal(broadcastJobViewModel.scenario.status, "downstream-pending");
assert.equal(broadcastJobCreatedIsExternalEffectSent(broadcastJobInput), false);
assert.equal(broadcastJobViewModel.guardrails.includes("requires_push_center"), true);
assert.equal(broadcastJobViewModel.guardrails.includes("no_direct_send"), true);
assert.equal(broadcastJobViewModel.guardrails.includes("no_external_call"), true);
assert.equal(broadcastJobViewModel.guardrails.includes("no_production_write"), true);

const incomplete = normalizeOpsPlanStatus("external_effect_not_created");
assert.equal(incomplete, "evidence-incomplete");
assert.equal(statusMeta(incomplete).isSuccessComplete, false);

const operatorAction = normalizeOpsPlanStatus("pending", { operatorActionRequired: true });
assert.equal(operatorAction, "operator-action-required");

const retryable = normalizeOpsPlanStatus("failed", { retryable: true });
assert.equal(retryable, "retryable");

const failedTerminal = normalizeOpsPlanStatus("failed");
assert.equal(failedTerminal, "failed-terminal");

assert.equal(readonlyOpsPlanDropDoesNotMutate(pushCenterPendingInput), true);
const blockedNoop = validateDropIntent(pushCenterViewModel.scenario, "blocked_noop");
assert.equal(blockedNoop.allowed, false);
assert.equal(blockedNoop.statusAfterDrop, "downstream-pending");

const root = { innerHTML: "" };
renderOpsPlanOverview(root, {
  cards: [
    {
      title: "Approval event",
      rawStatus: "pending",
      evidenceStatus: "EVIDENCE_COLLECTED",
      derivedStatus: "ops_plan_approved_event_created",
      evidenceId: "ops_plan.approved",
      summary: "event exists",
      guardrail: "not completed"
    },
    broadcastJobInput,
    {
      ...pushCenterPendingInput,
      evidenceId: "broadcast_job:3644"
    },
    {
      title: "Downstream external effect",
      rawStatus: "external_effect_not_created",
      evidenceStatus: "EVIDENCE_COLLECTED",
      derivedStatus: "not_pass_90_plus_candidate",
      evidenceId: "external_effect_job:not_created",
      summary: "not created",
      guardrail: "not pass complete"
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

assert.equal(root.innerHTML.includes("p0-1283-plan-20260615152503"), true);
assert.equal(root.innerHTML.includes("broadcast_job:3644"), true);
assert.equal(root.innerHTML.includes("downstream-pending"), true);
assert.equal(root.innerHTML.includes("data-drop-intent=\"blocked_noop\""), true);
assert.equal(root.innerHTML.includes("data-status-after-drop=\"downstream-pending\""), true);
assert.equal(root.innerHTML.includes("no_direct_send"), true);
assert.equal(root.innerHTML.includes("not_pass_90_plus_candidate"), true);
assert.equal(root.innerHTML.includes("<dt>Completion</dt><dd>complete</dd>"), false);
assert.equal(root.innerHTML.includes("external_effect_sent"), false);
for (const forbidden of [
  "raw_external_userid",
  "raw_target_list",
  "raw_member_id",
  "customer_identifier",
  "Authorization",
  "access_token",
  "corpsecret",
  "13800138000",
  "secret",
  "token"
]) {
  assert.equal(root.innerHTML.includes(forbidden), false);
}

console.log("p1 ops plan status model OK");
