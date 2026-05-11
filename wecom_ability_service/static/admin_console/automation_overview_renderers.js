(function () {
  "use strict";

  const AutomationOverview = window.AutomationOverview || {};
  window.AutomationOverview = AutomationOverview;

  const elements = AutomationOverview.elements;
  const escapeHtml = AutomationOverview.escapeHtml;
  const overviewExecutionBodyId = "overview-execution-body";
  const overviewQuestionnaireSubmittedId = "overview-questionnaire-submitted";

  function renderMemberGroups(dashboard) {
    const { memberGroups, profileTemplateNote } = elements();
    if (!memberGroups || !profileTemplateNote) return;
    const detail = dashboard.audience_member_details || {};
    const groups = detail.groups || [];
    const profileTemplate = detail.profile_segment_template || {};
    const skippedInvalidCount = Number(profileTemplate.skipped_invalid_enabled_template_count || 0);
    const reasonMessages = Array.isArray(profileTemplate.reason_messages) ? profileTemplate.reason_messages.filter(Boolean) : [];
    if (profileTemplate.template_name && profileTemplate.valid !== false) {
      profileTemplateNote.textContent = skippedInvalidCount > 0
        ? `自然画像模板：${profileTemplate.template_name}（已跳过 ${skippedInvalidCount} 个无效启用模板）`
        : `自然画像模板：${profileTemplate.template_name}`;
    } else if (profileTemplate.selection_status === "no_valid_enabled_template") {
      profileTemplateNote.textContent = `自然画像模板：当前没有有效的启用模板，已跳过 ${skippedInvalidCount} 个无效模板。${reasonMessages[0] || ""}`;
    } else {
      profileTemplateNote.textContent = "自然画像模板：当前未启用或无有效模板，相关列暂不展示命中结果";
    }
    memberGroups.innerHTML = groups.map((group) => {
      const rows = (group.items || []).length
        ? group.items.map((item) => {
            const phone = String(item.phone || "").trim();
            const phoneDisplay = phone || "-";
            const customerName = String(item.customer_name || "").trim() || "-";
            const externalContactId = String(item.external_contact_id || "").trim();
            const externalContactDisplay = externalContactId || "-";
            const dataId = escapeHtml(externalContactId);
            return `
            <tr data-external-contact-id="${dataId}">
              <td>${escapeHtml(customerName)}</td>
              <td>${escapeHtml(phoneDisplay)}</td>
              <td class="admin-mono">${escapeHtml(externalContactDisplay)}</td>
              <td>${escapeHtml(item.profile_segment_label || "-")}</td>
              <td>${escapeHtml(item.behavior_segment_label || "-")}</td>
              <td>${escapeHtml(item.conversation_count || 0)}</td>
            </tr>
          `;
          }).join("")
        : "<tr><td colspan=\"6\">当前池子还没有用户。</td></tr>";
      return `
          <article class="ac-overview-group-card">
            <div class="ac-overview-group-head">
              <div>
                <strong>${escapeHtml(group.audience_label || "-")}</strong>
                <div class="ac-overview-subtle">${escapeHtml(group.audience_description || "")}</div>
              </div>
              <span class="admin-chip admin-chip--neutral">用户 ${escapeHtml(group.count || 0)}</span>
            </div>
            <div class="ac-overview-table-wrap">
              <table class="ac-overview-table">
                <thead>
                  <tr>
                    <th>昵称</th>
                    <th>手机号</th>
                    <th>企微 ID</th>
                    <th>自然画像分层</th>
                    <th>行为画像分层</th>
                    <th>对话次数</th>
                  </tr>
                </thead>
                <tbody>${rows}</tbody>
              </table>
            </div>
          </article>
        `;
    }).join("");
  }

  function computeAdditionalStats(dashboard) {
    const { additionalStats, questionnaireSubmitted, segmentationStats } = elements();
    if (!additionalStats || !questionnaireSubmitted || !segmentationStats) return;
    const groups = ((dashboard.audience_member_details || {}).groups || []);
    let questionnaireSubmittedCount = 0;
    const profileSegments = new Map();
    const behaviorSegments = new Map();

    function incrementSegment(counter, label) {
      const normalizedLabel = String(label || "").trim();
      if (!normalizedLabel || normalizedLabel === "-") return;
      counter.set(normalizedLabel, Number(counter.get(normalizedLabel) || 0) + 1);
    }

    groups.forEach((group) => {
      (group.items || []).forEach((item) => {
        const questionnaireLabel = String(item.questionnaire_status_label || "").trim();

        if (questionnaireLabel.includes("已提交")) {
          questionnaireSubmittedCount += 1;
        }

        incrementSegment(profileSegments, item.profile_segment_label);
        incrementSegment(behaviorSegments, item.behavior_segment_label);
      });
    });

    if (questionnaireSubmitted.id === overviewQuestionnaireSubmittedId) {
      questionnaireSubmitted.textContent = String(questionnaireSubmittedCount);
    }

    function renderSegmentationPanel(title, segments) {
      const entries = Array.from(segments.entries()).sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0], "zh-CN"));
      const items = entries.length
        ? entries.map(([label, count]) => `<span class="ac-overview-segmentation-item">${escapeHtml(label)}：${escapeHtml(count)}</span>`).join("")
        : "<span class=\"ac-overview-segmentation-item\">暂无数据：0</span>";
      return `
          <div class="ac-overview-segmentation-panel">
            <strong>${escapeHtml(title)}</strong>
            <div class="ac-overview-segmentation-list">${items}</div>
          </div>
        `;
    }

    segmentationStats.innerHTML = [
      renderSegmentationPanel("自然画像分层", profileSegments),
      renderSegmentationPanel("行为画像分层", behaviorSegments),
    ].join("");
    additionalStats.hidden = false;
    segmentationStats.hidden = false;
  }

  function renderDashboard(dashboard) {
    const {
      activeWorkflowChip,
      activeWorkflowCount,
      converted,
      executionBody,
      lastUpdated,
      loading,
      operating,
      pendingQuestionnaire,
      summaryGrid,
    } = elements();
    const audience = dashboard.audience_overview || {};
    const taskExecutionSummary = (dashboard.task_execution_summary || {}).items || [];
    if (loading) loading.hidden = true;
    if (summaryGrid) summaryGrid.hidden = false;
    if (pendingQuestionnaire) pendingQuestionnaire.textContent = String(audience.pending_questionnaire_count || 0);
    if (operating) operating.textContent = String(audience.operating_count || 0);
    if (converted) converted.textContent = String(audience.converted_count || 0);
    if (activeWorkflowCount) activeWorkflowCount.textContent = String(dashboard.active_workflow_count || 0);
    if (activeWorkflowChip) activeWorkflowChip.textContent = "启用任务流 " + String(dashboard.active_workflow_count || 0);
    const fmt = (window.AdminFmt || {});
    if (lastUpdated) {
      const localized = fmt.localTime ? fmt.localTime(new Date()) : new Date().toLocaleString();
      lastUpdated.textContent = "最近刷新：" + localized;
    }
    if (executionBody && executionBody.id === overviewExecutionBodyId) {
      executionBody.innerHTML = taskExecutionSummary.length
        ? taskExecutionSummary.map((item) => {
            const at = item.latest_execution_at;
            const atDisplay = at ? (fmt.relativeTime ? fmt.relativeTime(at) : at) : "-";
            return `
          <tr>
            <td>${escapeHtml(item.workflow_name || "-")}</td>
            <td>${escapeHtml(item.execution_count || 0)}</td>
            <td>${escapeHtml(atDisplay)}</td>
          </tr>
        `;
          }).join("")
        : "<tr><td colspan=\"3\">当前还没有任务流执行摘要。</td></tr>";
    }
    renderMemberGroups(dashboard);
    computeAdditionalStats(dashboard);
  }

  AutomationOverview.renderMemberGroups = renderMemberGroups;
  AutomationOverview.computeAdditionalStats = computeAdditionalStats;
  AutomationOverview.renderDashboard = renderDashboard;
})();
