import assert from "node:assert/strict";

import {
  buildWeComStatusViewModel,
  callbackFailClosedIsSuccess,
  externalConfigBlockedIsAuthorized,
  missingSignatureIsVerified,
  missingWeComEvidenceIsComplete,
  normalizeWeComStatus,
  readonlyWeComDropDoesNotMutate
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/wecom/wecom_status.js";
import { renderWeComOverview } from "../../aicrm_next/frontend_compat/static/admin_console/p1/wecom/wecom_overview.js";
import { validateDropIntent } from "../../aicrm_next/frontend_compat/static/admin_console/p1/shared/interaction_contract.js";
import { statusMeta } from "../../aicrm_next/frontend_compat/static/admin_console/p1/shared/status_model.js";

const configBlockedInput = {
  title: "Auth start",
  rawStatus: "external_config_blocked",
  evidenceStatus: "BLOCKED_CONFIG_NOT_APPROVED",
  derivedStatus: "external_call_blocked_503",
  summary: "blocked",
  guardrail: "not authorized"
};
const configBlocked = normalizeWeComStatus(configBlockedInput.rawStatus);
assert.equal(configBlocked, "external-config-blocked");
assert.equal(statusMeta(configBlocked).isSuccessComplete, false);
assert.equal(externalConfigBlockedIsAuthorized(configBlockedInput), false);

const failClosedInput = {
  title: "External contact callback",
  rawStatus: "callback_fail_closed",
  evidenceStatus: "EVIDENCE_COLLECTED_NOT_READY",
  derivedStatus: "missing_signature_fail_closed_400",
  summary: "fail closed",
  guardrail: "不是回调成功"
};
const failClosedViewModel = buildWeComStatusViewModel(failClosedInput);
assert.equal(failClosedViewModel.scenario.status, "blocked");
assert.equal(callbackFailClosedIsSuccess(failClosedInput), false);

const missingSignatureInput = {
  title: "Signature",
  rawStatus: "missing_valid_signature",
  evidenceStatus: "EVIDENCE_COLLECTED_NOT_READY",
  derivedStatus: "missing_signature",
  summary: "missing",
  guardrail: "not verified"
};
assert.equal(normalizeWeComStatus(missingSignatureInput.rawStatus), "evidence-incomplete");
assert.equal(missingSignatureIsVerified(missingSignatureInput), false);
assert.equal(missingWeComEvidenceIsComplete(missingSignatureInput), false);

const missingRecordInput = {
  title: "Admin event visibility",
  rawStatus: "missing_internal_event",
  evidenceStatus: "EVIDENCE_COLLECTED_NOT_READY",
  derivedStatus: "no_callback_linked_event_found",
  summary: "missing",
  guardrail: "not complete"
};
const missingRecordViewModel = buildWeComStatusViewModel(missingRecordInput);
assert.equal(missingRecordViewModel.scenario.status, "evidence-incomplete");
assert.equal(missingRecordViewModel.isSuccessComplete, false);
assert.equal(missingRecordViewModel.guardrails.includes("requires_external_config"), true);
assert.equal(missingRecordViewModel.guardrails.includes("no_external_call"), true);
assert.equal(missingRecordViewModel.guardrails.includes("no_production_write"), true);
assert.equal(missingRecordViewModel.guardrails.includes("no_direct_send"), true);

assert.equal(readonlyWeComDropDoesNotMutate(configBlockedInput), true);
const blockedNoop = validateDropIntent(failClosedViewModel.scenario, "blocked_noop");
assert.equal(blockedNoop.allowed, false);
assert.equal(blockedNoop.statusAfterDrop, "blocked");

const root = { innerHTML: "" };
renderWeComOverview(root, {
  cards: [
    configBlockedInput,
    {
      title: "Auth callback",
      rawStatus: "external_config_blocked",
      evidenceStatus: "BLOCKED_CONFIG_NOT_APPROVED",
      derivedStatus: "callback_external_call_blocked_503",
      evidenceId: "/auth/wecom/callback",
      summary: "blocked",
      guardrail: "not complete"
    },
    failClosedInput,
    missingRecordInput
  ],
  evidenceSummary: {
    authStartRoute: "/auth/wecom/start",
    authStartStatus: "controlled_external_call_blocked_503",
    authCallbackRoute: "/auth/wecom/callback",
    authCallbackStatus: "controlled_external_call_blocked_503",
    contactCallbackRoute: "/wecom/external-contact/callback",
    contactCallbackStatus: "fail_closed_400_missing_signature",
    eventsRoute: "/api/wecom/events",
    eventsStatus: "fail_closed_400_missing_signature",
    adminVisibility: "admin_internal_events_reachable",
    callbackLinkedEvent: "not_found",
    validCallbackSignature: "missing",
    authRecord: "not_found",
    idempotencyEvidence: "not_found",
    permissionScope: "not_found",
    realExternalCallExecuted: false,
    finalStatus: "BLOCKED_CONFIG_NOT_APPROVED"
  }
});

assert.equal(root.innerHTML.includes("external-config-blocked"), true);
assert.equal(root.innerHTML.includes("callback success"), false);
assert.equal(root.innerHTML.includes("signature_verified"), false);
assert.equal(root.innerHTML.includes("<dt>Completion</dt><dd>complete</dd>"), false);
assert.equal(root.innerHTML.includes("data-execution-mode=\"external_config_blocked\""), true);
assert.equal(root.innerHTML.includes("data-drop-intent=\"blocked_noop\""), true);
assert.equal(root.innerHTML.includes("requires_external_config"), true);
assert.equal(root.innerHTML.includes("no_external_call"), true);
assert.equal(root.innerHTML.includes("no_direct_send"), true);
assert.equal(root.innerHTML.includes("BLOCKED_CONFIG_NOT_APPROVED"), true);
for (const forbidden of [
  "raw_external_userid",
  "raw_callback_body",
  "openid",
  "unionid",
  "Authorization",
  "access_token",
  "corpsecret",
  "suite_secret",
  "13800138000",
  "secret",
  "token"
]) {
  assert.equal(root.innerHTML.includes(forbidden), false);
}

console.log("p1 wecom status model OK");
