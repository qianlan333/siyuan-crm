import { renderInteractionShell } from "../shared/interaction_shell.js";
import { renderStatusCard } from "../shared/status_card.js";
import { PUSH_CENTER_P1_DEFAULT_INPUTS, buildPushCenterStatusViewModel } from "./push_center_status.js";
function parsePayload() {
    const payloadNode = document.getElementById("pushCenterP1StatusPayload");
    if (!payloadNode?.textContent)
        return { cards: PUSH_CENTER_P1_DEFAULT_INPUTS };
    const parsed = JSON.parse(payloadNode.textContent);
    return {
        cards: parsed.cards?.length ? parsed.cards : PUSH_CENTER_P1_DEFAULT_INPUTS
    };
}
function renderPushCenterInteractionShell(inputs) {
    return renderInteractionShell({
        finalVerdict: "P1_READY_WITH_EXCEPTIONS",
        canClaimPass90Plus: false,
        scenarios: inputs.map((input) => buildPushCenterStatusViewModel(input).scenario)
    }, {
        id: "push-center-draft-preview",
        title: "Push Center draft-only preview shell",
        description: "任务卡只做前端内存 reorder preview；pending / retryable / operator-action-required 不会变成 sent 或 complete。"
    });
}
export function renderPushCenterOverview(root, payload) {
    const cards = payload.cards.length ? payload.cards : PUSH_CENTER_P1_DEFAULT_INPUTS;
    const cardHtml = cards.map((input) => {
        const viewModel = buildPushCenterStatusViewModel(input);
        return renderStatusCard(viewModel.scenario, {
            dragHandle: true,
            dragDisabledReason: `${viewModel.operatorPrompt} Readonly preview only; no direct send.`
        });
    }).join("");
    root.innerHTML = `
    <section class="p1-push-banner" data-push-center-slice="readonly" data-real-external-call-executed="false" data-production-write-executed="false">
      <div>
        <h2>P1 Push Center status slice</h2>
        <p>只读呈现 P1 exception 状态；不新增写操作、不绕过 Push Center、不触发真实外呼。</p>
      </div>
      <span class="p1-closure-pill p1-closure-pill--warning">P1_READY_WITH_EXCEPTIONS</span>
    </section>
    <section class="p1-closure-grid" aria-label="Push Center P1 status cards">
      ${cardHtml}
    </section>
    ${renderPushCenterInteractionShell(cards)}
  `;
}
function boot() {
    const root = document.getElementById("pushCenterP1StatusApp");
    if (!root)
        return;
    renderPushCenterOverview(root, parsePayload());
}
if (typeof document !== "undefined") {
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot, { once: true });
    }
    else {
        boot();
    }
}
