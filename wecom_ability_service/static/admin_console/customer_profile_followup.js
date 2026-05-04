(function () {
  "use strict";

  const CustomerProfile = window.CustomerProfile || {};
  window.CustomerProfile = CustomerProfile;

  const escapeHtml = CustomerProfile.escapeHtml;
  const requestCustomerPulseJson = CustomerProfile.requestCustomerPulseJson;
  const isPermissionError = CustomerProfile.isPermissionError;
  const showSectionError = CustomerProfile.showSectionError;
  const showSectionEmpty = CustomerProfile.showSectionEmpty;

  function followupOrchestratorElements() {
    return {
      state: document.querySelector("[data-followup-orchestrator-widget-state]"),
      widget: document.querySelector("[data-followup-orchestrator-widget]"),
      chips: document.querySelector("[data-followup-orchestrator-widget-chips]"),
      detail: document.querySelector("[data-followup-orchestrator-widget-detail]"),
      items: document.querySelector("[data-followup-orchestrator-widget-items]"),
    };
  }

  function followupMissionTypeLabel(value) {
    const mapping = {
      claim_queue: "待认领客户队列",
      handoff_wave: "团队接力转派波次",
      risk_escalation_wave: "风险升级波次",
      batch_draft_wave: "批量草稿波次",
      priority_wave: "今日优先推进任务包",
    };
    return mapping[String(value || "")] || "团队任务包";
  }

  function renderFollowupOrchestratorWidget(payload, root) {
    const elements = followupOrchestratorElements();
    if (!elements.state) return;
    if (!payload || !payload.enabled) {
      if (elements.widget) elements.widget.hidden = true;
      showSectionEmpty(elements.state, "团队编排未启用", "当前租户或角色尚未进入团队编排灰度范围。");
      return;
    }
    const missionItems = Array.isArray(payload.mission_items) ? payload.mission_items : [];
    const assignmentSuggestions = Array.isArray(payload.assignment_suggestions) ? payload.assignment_suggestions : [];
    const escalationSuggestions = Array.isArray(payload.escalation_suggestions) ? payload.escalation_suggestions : [];
    const batchSuggestions = Array.isArray(payload.batch_draft_suggestions) ? payload.batch_draft_suggestions : [];
    if (!missionItems.length && !assignmentSuggestions.length && !escalationSuggestions.length && !batchSuggestions.length) {
      if (elements.widget) elements.widget.hidden = true;
      showSectionEmpty(elements.state, "当前未进入团队编排", "这位客户暂时不在任何 mission 中，也没有待审批或待接力建议。");
      return;
    }
    elements.state.hidden = true;
    if (elements.widget) elements.widget.hidden = false;
    if (elements.chips) {
      const chips = [];
      if (missionItems.length) chips.push(`<span class="admin-inline-chip admin-inline-chip--ok">Mission ${escapeHtml(missionItems.length)}</span>`);
      if (assignmentSuggestions.length) chips.push('<span class="admin-inline-chip admin-inline-chip--warn">待接力</span>');
      if (escalationSuggestions.length) chips.push('<span class="admin-inline-chip admin-inline-chip--danger">待升级</span>');
      if (batchSuggestions.length) chips.push('<span class="admin-inline-chip admin-inline-chip--neutral">批量草稿候选</span>');
      elements.chips.hidden = !chips.length;
      elements.chips.innerHTML = chips.join("");
    }
    if (elements.detail) {
      const firstMissionItem = missionItems[0] || {};
      const firstAssignment = assignmentSuggestions[0] || {};
      const firstEscalation = escalationSuggestions[0] || {};
      elements.detail.hidden = false;
      elements.detail.innerHTML = `
        <div>
          <dt>当前任务包</dt>
          <dd>${escapeHtml(followupMissionTypeLabel((firstMissionItem.payload || {}).mission_type))}</dd>
        </div>
        <div>
          <dt>当前建议归属</dt>
          <dd>${escapeHtml(firstMissionItem.suggested_assignee_userid || firstMissionItem.owner_userid || "保持当前 owner")}</dd>
        </div>
        <div>
          <dt>待审批 / 待接力</dt>
          <dd>${escapeHtml(firstAssignment.reason || "当前没有待审批的转派建议")}</dd>
        </div>
        <div>
          <dt>升级状态</dt>
          <dd>${escapeHtml(firstEscalation.reason || "当前没有升级建议")}</dd>
        </div>
        <div>
          <dt>草稿波次</dt>
          <dd>${batchSuggestions.length ? `命中 ${batchSuggestions.length} 个批量草稿 mission` : "当前未命中批量草稿波次"}</dd>
        </div>
        <div>
          <dt>入口</dt>
          <dd><a class="admin-inline-link admin-inline-link--compact" href="${escapeHtml(root.dataset.followupOrchestratorUrl || "#")}">打开团队编排</a></dd>
        </div>
      `;
    }
    if (elements.items) {
      elements.items.hidden = false;
      elements.items.innerHTML = missionItems
        .slice(0, 3)
        .map(
          (item) => `
            <article class="admin-profile-message">
              <div class="admin-profile-message-meta">
                <span>${escapeHtml(item.customer_name || item.external_userid || "客户")}</span>
                <span>${escapeHtml((item.payload || {}).stage_label || (item.payload || {}).stage_key || "未标记阶段")}</span>
                <span>${escapeHtml(item.item_status || "suggested")}</span>
              </div>
              <div class="admin-profile-message-content">${escapeHtml(
                (item.payload || {}).why_now ||
                  (item.payload || {}).current_judgement ||
                  "当前已进入团队编排，可前往任务包查看详情。",
              )}</div>
            </article>
          `,
        )
        .join("");
    }
  }

  function loadFollowupOrchestrator(root) {
    const elements = followupOrchestratorElements();
    if (!elements.state || root.dataset.followupOrchestratorEnabled !== "1" || !root.dataset.followupOrchestratorApiUrl) {
      return Promise.resolve(null);
    }
    return requestCustomerPulseJson(root, root.dataset.followupOrchestratorApiUrl)
      .then((payload) => {
        renderFollowupOrchestratorWidget(payload.customer_orchestrator || {}, root);
        return payload.customer_orchestrator || {};
      })
      .catch((error) => {
        if (isPermissionError(error)) {
          showSectionError(elements.state, error.message || "当前角色没有查看团队编排 widget 的权限");
        } else {
          showSectionError(elements.state, error.message || "当前无法加载团队编排状态");
        }
        return null;
      });
  }

  function bootFollowupOrchestrator(root) {
    return loadFollowupOrchestrator(root);
  }

  CustomerProfile.renderFollowupOrchestratorWidget = renderFollowupOrchestratorWidget;
  CustomerProfile.loadFollowupOrchestrator = loadFollowupOrchestrator;
  CustomerProfile.bootFollowupOrchestrator = bootFollowupOrchestrator;
})();
