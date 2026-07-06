import assert from "node:assert/strict";

import {
  P1_PREVIEW_BOARD_FIXTURE
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_preview_board/preview_board_fixture.js";
import {
  buildPreviewBoardModel,
  renderP1PreviewBoard
} from "../../aicrm_next/frontend_compat/static/admin_console/p1/p1_preview_board/preview_board.js";

const rendered = renderP1PreviewBoard();
const model = buildPreviewBoardModel();
const cards = P1_PREVIEW_BOARD_FIXTURE.payload.scenarios;

for (const label of [
  "External Orders / order linked",
  "Push Center / pending",
  "Push Center / sent",
  "Push Center / retryable",
  "Push Center / operator action",
  "Group Ops / sent evidence",
  "Group Ops / governance missing",
  "Group Ops / evidence incomplete",
  "Ops Plan / downstream pending",
  "Ops Plan / external effect not created",
  "WeCom / external config blocked",
  "WeCom / callback fail closed",
  "WeCom / missing evidence"
]) {
  assert.equal(rendered.includes(label), true);
}

assert.equal(P1_PREVIEW_BOARD_FIXTURE.summary.globalVerdict, "P1_READY_WITH_EXCEPTIONS");
assert.equal(P1_PREVIEW_BOARD_FIXTURE.summary.canClaimPass90Plus, false);
assert.equal(P1_PREVIEW_BOARD_FIXTURE.summary.previewOnly, true);
assert.equal(P1_PREVIEW_BOARD_FIXTURE.summary.productionWriteExecuted, false);
assert.equal(P1_PREVIEW_BOARD_FIXTURE.summary.realExternalCallExecuted, false);
assert.equal(P1_PREVIEW_BOARD_FIXTURE.payload.canClaimPass90Plus, false);
assert.equal(rendered.includes("PASS_90_PLUS</dt><dd>false"), true);
assert.equal(rendered.includes("data-can-claim-pass90=\"false\""), true);
assert.equal(rendered.includes("data-real-external-call-executed=\"false\""), true);
assert.equal(rendered.includes("data-production-write-executed=\"false\""), true);

assert.deepEqual(model.originalStatuses, cards.map((card) => card.status));
assert.notDeepEqual(model.previewStatuses.map((status, index) => `${index}:${status}`), model.originalStatuses.map((status, index) => `${index}:${status}`));
for (const row of model.validationRows) {
  assert.equal(row.statusAfterDrop, row.status);
}
assert.equal(rendered.includes("blocked_noop"), true);
assert.equal(rendered.includes("evidence status and production state are unchanged"), true);

const wecom = cards.find((card) => card.title === "WeCom / external config blocked");
assert.equal(wecom?.status, "external-config-blocked");
assert.equal(rendered.includes("data-status-after-drop=\"external-config-blocked\""), true);
assert.equal(rendered.includes("external_config_blocked"), true);

const groupOpsSent = cards.find((card) => card.title === "Group Ops / sent evidence");
const groupOpsGovernance = cards.find((card) => card.title === "Group Ops / governance missing");
assert.equal(groupOpsSent?.status, "sent");
assert.equal(groupOpsGovernance?.status, "governance-missing");
assert.equal(rendered.includes("Push Center sent does not equal governance complete."), true);
assert.equal(rendered.includes("requires_gray_window"), true);
assert.equal(rendered.includes("requires_allowlist"), true);
assert.equal(rendered.includes("governance complete</dd>"), false);

const opsPlan = cards.find((card) => card.title === "Ops Plan / downstream pending");
assert.equal(opsPlan?.status, "downstream-pending");
assert.equal(rendered.includes("broadcast_job:3644_pending"), true);
assert.equal(rendered.includes("preview_only"), true);
assert.equal(rendered.includes("downstream completed"), false);
assert.equal(rendered.includes("broadcast_job sent"), false);

const externalOrders = cards.find((card) => card.title === "External Orders / order linked");
assert.equal(externalOrders?.evidenceStatus, "EVIDENCE_COLLECTED");
assert.equal(externalOrders?.derivedStatus, "order_linked");
assert.equal(model.canRenderGlobalPass90Plus, false);

for (const forbidden of [
  "Authorization",
  "access_token",
  "corpsecret",
  "suite secret",
  "raw_external_userid",
  "external_userid=",
  "openid",
  "unionid",
  "13800138000",
  "receiver_plaintext"
]) {
  assert.equal(rendered.includes(forbidden), false);
}

console.log("p1 cross-page preview board OK");
