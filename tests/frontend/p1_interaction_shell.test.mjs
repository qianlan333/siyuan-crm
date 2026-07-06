import assert from "node:assert/strict";

import {
  createDraftState
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/shared/draft_state.js";
import {
  explainBlockedDrop,
  getExecutionModeForStatus,
  validateDropIntent
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/shared/drop_validation.js";
import {
  applyReadonlyReorderPreview,
  renderInteractionShell,
  serializeDraftPreviewForDisplay
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/shared/interaction_shell.js";

const scenarios = [
  {
    key: "wecom_auth",
    title: "WeCom",
    status: "external-config-blocked",
    evidenceStatus: "BLOCKED_CONFIG_NOT_APPROVED",
    derivedStatus: "external_config_exception",
    summary: "external config blocked",
    guardrail: "requires external config"
  },
  {
    key: "group_ops",
    title: "Group Ops",
    status: "governance-missing",
    evidenceStatus: "EVIDENCE_COLLECTED",
    derivedStatus: "sent_with_governance_residual_risk",
    summary: "sent evidence exists but governance is incomplete",
    guardrail: "requires approval, allowlist, and gray window"
  },
  {
    key: "ops_plan_broadcast",
    title: "Ops Plan",
    status: "downstream-pending",
    evidenceStatus: "EVIDENCE_COLLECTED",
    derivedStatus: "push_center_pending",
    summary: "broadcast job is pending downstream work",
    guardrail: "preview only"
  },
  {
    key: "external_orders",
    title: "External Orders",
    status: "sent",
    evidenceStatus: "EVIDENCE_COLLECTED",
    derivedStatus: "order_linked",
    summary: "order evidence collected",
    guardrail: "sent does not bypass governance"
  }
];

const draft = createDraftState(scenarios, {
  id: "test-draft",
  createdAt: "2026-06-23T00:00:00.000Z"
});
const beforeStatuses = draft.cards.map((card) => card.status);
const statusById = new Map(draft.cards.map((card) => [card.id, card.status]));
const reordered = applyReadonlyReorderPreview(draft, 0, 2);

assert.deepEqual(draft.cards.map((card) => card.status), beforeStatuses);
assert.equal(reordered.cards.every((card) => statusById.get(card.id) === card.status), true);
assert.notEqual(reordered.cards[0].id, draft.cards[0].id);
assert.equal(reordered.cards.every((card) => card.mutatedEvidenceStatus === false), true);
assert.equal(draft.productionWriteExecuted, false);
assert.equal(reordered.productionWriteExecuted, false);
assert.equal(reordered.realExternalCallExecuted, false);

const blockedNoop = validateDropIntent(scenarios[1], "blocked_noop");
assert.equal(blockedNoop.allowed, false);
assert.equal(blockedNoop.statusAfterDrop, "governance-missing");
assert.equal(explainBlockedDrop(blockedNoop).includes("no-op"), true);

assert.equal(getExecutionModeForStatus("external-config-blocked"), "external_config_blocked");
assert.equal(validateDropIntent(scenarios[0], "draft_update").allowed, false);
assert.equal(validateDropIntent(scenarios[0], "draft_update").executionMode, "external_config_blocked");

const governanceDrop = validateDropIntent(scenarios[1], "reorder");
assert.equal(governanceDrop.allowed, false);
assert.equal(governanceDrop.guardrails.includes("requires_approval"), true);
assert.equal(governanceDrop.guardrails.includes("requires_allowlist"), true);
assert.equal(governanceDrop.guardrails.includes("requires_gray_window"), true);

const downstreamPreview = validateDropIntent(scenarios[2], "preview");
assert.equal(downstreamPreview.allowed, true);
assert.equal(downstreamPreview.executionMode, "preview_only");
assert.equal(downstreamPreview.statusAfterDrop, "downstream-pending");

const sentPreview = validateDropIntent(scenarios[3], "reorder");
assert.equal(sentPreview.executionMode, "readonly");
assert.equal(sentPreview.guardrails.includes("no_direct_send"), true);
assert.equal(sentPreview.guardrails.includes("no_external_call"), true);
assert.equal(sentPreview.statusAfterDrop, "sent");

const display = serializeDraftPreviewForDisplay(reordered);
assert.equal(display.canClaimPass90Plus, false);
assert.equal(display.productionWriteExecuted, false);
assert.equal(display.realExternalCallExecuted, false);
assert.equal(display.cards.every((card) => card.mutatedEvidenceStatus === false), true);

const html = renderInteractionShell({
  finalVerdict: "P1_READY_WITH_EXCEPTIONS",
  canClaimPass90Plus: false,
  scenarios
});
assert.equal(html.includes("data-persistence=\"memory_only\""), true);
assert.equal(html.includes("data-real-external-call-executed=\"false\""), true);
assert.equal(html.includes("data-production-write-executed=\"false\""), true);
assert.equal(html.includes("data-can-claim-pass90=\"false\""), true);
assert.equal(html.includes("external_config_blocked"), true);
assert.equal(html.includes("requires_gray_window"), true);
assert.equal(html.includes("preview_only"), true);
assert.equal(html.includes("Draft-only / preview-only interaction shell"), true);

for (const forbidden of [
  "raw_external_userid",
  "receiver_plaintext",
  "raw_callback_body",
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

console.log("p1 interaction shell OK");
