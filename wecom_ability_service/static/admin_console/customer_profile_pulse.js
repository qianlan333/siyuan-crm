(function () {
  "use strict";

  const CustomerProfile = window.CustomerProfile || {};
  window.CustomerProfile = CustomerProfile;

  const escapeHtml = CustomerProfile.escapeHtml;
  const requestCustomerPulseJson = CustomerProfile.requestCustomerPulseJson;
  const showSectionError = CustomerProfile.showSectionError;
  const showSectionEmpty = CustomerProfile.showSectionEmpty;
  const toDateTimeLocalValue = CustomerProfile.toDateTimeLocalValue;
  const state = CustomerProfile.state;

  function customerPulseElements() {
    return {
      state: document.querySelector("[data-customer-pulse-state]"),
      widget: document.querySelector("[data-customer-pulse-widget]"),
      chips: document.querySelector("[data-customer-pulse-chips]"),
      summary: document.querySelector("[data-customer-pulse-summary]"),
      detail: document.querySelector("[data-customer-pulse-detail]"),
      evidence: document.querySelector("[data-customer-pulse-evidence]"),
      actions: document.querySelector("[data-customer-pulse-actions]"),
      editor: document.querySelector("[data-customer-pulse-editor]"),
      feedback: document.querySelector("[data-customer-pulse-feedback]"),
    };
  }

  function customerPulseInlineStateHtml(title, body, tone) {
    const className =
      tone === "error"
        ? "admin-state admin-state--inline admin-state--error"
        : "admin-state admin-state--inline";
    return `<div class="${className}"><strong>${escapeHtml(title)}</strong><span>${escapeHtml(body)}</span></div>`;
  }

  function customerPulseActionButtons(card) {
    const buttons = [];
    if (card && card.draft_editor_available) {
      buttons.push({ action_type: "generate_reply_draft", action_label: "编辑草稿" });
    }
    (card && Array.isArray(card.supported_action_buttons) ? card.supported_action_buttons : []).forEach((item) => {
      if (!item || !item.action_type) return;
      if (buttons.some((button) => button.action_type === item.action_type)) return;
      buttons.push(item);
    });
    return buttons;
  }

  function customerPulseEvidenceRefsHtml(items) {
    const evidence = Array.isArray(items) ? items : [];
    if (!evidence.length) {
      return customerPulseInlineStateHtml("暂无证据线索", "当前没有可展示的 evidence refs。");
    }
    return evidence
      .map(
        (item) => `
          <article class="admin-profile-message">
            <div class="admin-profile-message-meta">
              <span>${escapeHtml(item.title || item.sourceType || "证据")}</span>
              <span>${escapeHtml(item.eventTime || "-")}</span>
            </div>
            <div class="admin-profile-message-content">${escapeHtml(
              [item.sourceType, item.sourceId].filter(Boolean).join(" · ") || "原始记录引用",
            )}</div>
          </article>
        `,
      )
      .join("");
  }

  function customerPulseEvidenceItemsHtml(items) {
    const evidence = Array.isArray(items) ? items : [];
    if (!evidence.length) {
      return customerPulseInlineStateHtml("暂无可展开证据", "当前没有命中可展示的原始证据内容。");
    }
    return evidence
      .map(
        (item) => `
          <article class="admin-profile-message">
            <div class="admin-profile-message-meta">
              <span>${escapeHtml(item.title || "证据")}</span>
              <span>${escapeHtml(item.event_time || item.source || "-")}</span>
            </div>
            <div class="admin-profile-message-content">${escapeHtml(item.detail || "暂无详情")}</div>
          </article>
        `,
      )
      .join("");
  }

  function customerPulseFormFields(preview) {
    const actionType = String((preview && preview.action_type) || "");
    const payload = (preview && preview.preview) || {};
    if (actionType === "generate_reply_draft") {
      return `
        <label>
          <span>草稿内容</span>
          <textarea rows="6" data-customer-pulse-field="draft_message">${escapeHtml(payload.draft_message || "")}</textarea>
          <small>${escapeHtml(payload.draft_notice || "所有外发消息默认只生成草稿，需人工确认后再发送。")}</small>
        </label>
      `;
    }
    if (actionType === "create_followup_task") {
      return `
        <label>
          <span>任务标题</span>
          <input type="text" data-customer-pulse-field="task_title" value="${escapeHtml(payload.task_title || "")}">
        </label>
        <label>
          <span>截止时间</span>
          <input type="datetime-local" data-customer-pulse-field="due_at" value="${escapeHtml(toDateTimeLocalValue(payload.due_at || ""))}">
        </label>
      `;
    }
    if (actionType === "update_followup_segment") {
      const currentSegment = String(payload.followup_segment || "focus");
      const options = [
        { value: "focus", label: "重点跟进" },
        { value: "normal", label: "普通跟进" },
        { value: "core", label: "Core" },
        { value: "top", label: "Top" },
      ];
      return `
        <label>
          <span>目标阶段</span>
          <select data-customer-pulse-field="followup_segment">
            ${options
              .map(
                (option) =>
                  `<option value="${escapeHtml(option.value)}"${option.value === currentSegment ? " selected" : ""}>${escapeHtml(option.label)}</option>`,
              )
              .join("")}
          </select>
        </label>
      `;
    }
    if (actionType === "update_tags") {
      return `
        <label>
          <span>新增标签 ID</span>
          <input type="text" data-customer-pulse-field="add_tag_ids" value="${escapeHtml((payload.add_tag_ids || []).join(","))}" placeholder="tag_a,tag_b">
        </label>
        <label>
          <span>移除标签 ID</span>
          <input type="text" data-customer-pulse-field="remove_tag_ids" value="${escapeHtml((payload.remove_tag_ids || []).join(","))}" placeholder="tag_c,tag_d">
        </label>
      `;
    }
    if (actionType === "set_followup_reminder") {
      return `
        <label>
          <span>提醒时间</span>
          <input type="datetime-local" data-customer-pulse-field="due_at" value="${escapeHtml(toDateTimeLocalValue(payload.due_at || ""))}">
        </label>
      `;
    }
    return "";
  }

  function renderCustomerPulse(payload) {
    const elements = customerPulseElements();
    if (!elements.state) return;
    const detailPayload = (payload && payload.customer_pulse) || {};
    const card = detailPayload.card || null;
    state.currentCustomerPulsePayload = detailPayload;
    if (!detailPayload.enabled) {
      if (elements.widget) elements.widget.hidden = true;
      showSectionEmpty(elements.state, "AI 下一步未启用", "当前 feature flag 关闭。");
      return;
    }
    if (!card) {
      if (elements.widget) elements.widget.hidden = true;
      showSectionEmpty(elements.state, "当前暂不展示 AI 下一步", "当前客户还没有可执行的行动卡，或证据不足。");
      return;
    }
    elements.state.hidden = true;
    if (elements.widget) {
      elements.widget.hidden = false;
    }
    if (elements.chips) {
      elements.chips.hidden = false;
      elements.chips.innerHTML = `
        <span class="admin-inline-chip admin-inline-chip--neutral">${escapeHtml(card.card_status_label || "待处理")}</span>
        <span class="admin-inline-chip admin-inline-chip--${card.priority === "high" ? "warn" : "ok"}">${escapeHtml(card.priority_label || "常规")}</span>
        <span class="admin-inline-chip admin-inline-chip--neutral">${escapeHtml(card.confidence === null || card.confidence === undefined ? "规则建议" : `置信度 ${Number(card.confidence).toFixed(2)}`)}</span>
      `;
    }
    if (elements.summary) {
      elements.summary.hidden = false;
      elements.summary.className = `admin-state admin-state--inline${card.draft_blocked_by_ai ? " admin-state--error" : ""}`;
      elements.summary.innerHTML = [
        `<strong>${escapeHtml(card.draft_blocked_by_ai ? "已降级为规则建议" : "当前判断")}</strong>`,
        `<span>${escapeHtml(card.current_judgement || card.summary || "暂无摘要")}</span>`,
      ].join("");
    }
    if (elements.detail) {
      elements.detail.hidden = false;
      elements.detail.innerHTML = `
        <div>
          <dt>建议动作</dt>
          <dd>${escapeHtml(card.suggested_action_label || "人工确认后决定下一步")}</dd>
        </div>
        <div>
          <dt>负责人</dt>
          <dd>${escapeHtml(card.owner_display_name || card.owner_userid || "未分配")}</dd>
        </div>
        <div>
          <dt>当前阶段</dt>
          <dd>${escapeHtml(card.stage_label || "未分类")}</dd>
        </div>
        <div>
          <dt>最近事件</dt>
          <dd>${escapeHtml((card.latest_event && card.latest_event.title) || "最近事件")} · ${escapeHtml((card.latest_event && card.latest_event.detail) || "暂无详情")}</dd>
        </div>
        <div>
          <dt>为什么现在</dt>
          <dd>${escapeHtml(card.why_now || "当前信号已达到行动阈值")}</dd>
        </div>
        <div>
          <dt>处理要求</dt>
          <dd>${escapeHtml(card.draft_notice || "所有外发消息默认只生成草稿，由人工确认。")}</dd>
        </div>
      `;
    }
    if (elements.evidence) {
      const refs = Array.isArray(card.evidence_refs) ? card.evidence_refs : [];
      const permissions = card.permissions || {};
      const canExpandEvidence = Boolean(permissions.evidence_view && card.evidence_expand_available);
      elements.evidence.hidden = false;
      elements.evidence.innerHTML = `
        ${customerPulseEvidenceRefsHtml(refs)}
        ${
          state.currentCustomerPulseEvidencePayload && Array.isArray(state.currentCustomerPulseEvidencePayload.evidence)
            ? customerPulseEvidenceItemsHtml(state.currentCustomerPulseEvidencePayload.evidence)
            : ""
        }
        ${
          Array.isArray(state.currentCustomerPulseEvidencePayload && state.currentCustomerPulseEvidencePayload.inaccessible_refs) &&
          state.currentCustomerPulseEvidencePayload.inaccessible_refs.length
            ? customerPulseInlineStateHtml(
                "部分证据未展示",
                `有 ${state.currentCustomerPulseEvidencePayload.inaccessible_refs.length} 条 evidence refs 未通过原始边界校验。`,
              )
            : ""
        }
        ${
          !canExpandEvidence && refs.length
            ? customerPulseInlineStateHtml("当前角色无权展开原始证据", "可以看到 evidence refs，但不能直接读取原始记录内容。")
            : ""
        }
        ${state.currentCustomerPulseEvidenceError ? customerPulseInlineStateHtml("当前无法展开原始证据", state.currentCustomerPulseEvidenceError, "error") : ""}
      `;
    }
    if (elements.actions) {
      const buttons = customerPulseActionButtons(card);
      const feedbackButtons = Array.isArray(card.feedback_actions) ? card.feedback_actions : [];
      const canExpandEvidence = Boolean((card.permissions || {}).evidence_view && card.evidence_expand_available);
      elements.actions.hidden = !buttons.length && !feedbackButtons.length && !canExpandEvidence;
      elements.actions.innerHTML = `
        ${buttons
          .map(
            (item) => `
              <button
                type="button"
                class="admin-button ${item.action_type === card.suggested_action_type ? "admin-button--primary" : "admin-button--ghost"}"
                data-customer-pulse-preview
                data-card-id="${card.id}"
                data-action-type="${escapeHtml(item.action_type)}"
              >
                ${escapeHtml(item.action_label || "动作")}
              </button>
            `,
          )
          .join("")}
        ${
          canExpandEvidence
            ? `
              <button
                type="button"
                class="admin-button admin-button--ghost"
                data-customer-pulse-evidence-load
                data-card-id="${card.id}"
              >
                查看原始证据
              </button>
            `
            : ""
        }
        ${feedbackButtons
          .map(
            (item) => `
              <button
                type="button"
                class="admin-button admin-button--ghost"
                data-customer-pulse-feedback-action
                data-card-id="${card.id}"
                data-feedback-type="${escapeHtml(item.type || "")}"
              >
                ${escapeHtml(item.label || item.type || "反馈")}
              </button>
            `,
          )
          .join("")}
      `;
    }
    if (elements.editor) {
      const buttons = customerPulseActionButtons(card);
      if (state.currentCustomerPulsePreview && state.currentCustomerPulsePreview.action_type) {
        elements.editor.hidden = false;
        elements.editor.innerHTML = `
          <form class="admin-form-grid admin-form-grid--stacked" data-customer-pulse-action-form data-card-id="${card.id}" data-action-type="${escapeHtml(state.currentCustomerPulsePreview.action_type || "")}">
            <div class="admin-state admin-state--inline">
              <strong>${escapeHtml(state.currentCustomerPulsePreview.action_label || "动作预览")}</strong>
              <span>${escapeHtml(state.currentCustomerPulsePreview.action_title || state.currentCustomerPulsePreview.why_now || "请确认后执行")}</span>
            </div>
            ${
              state.currentCustomerPulsePreview.undo_notice
                ? `
                  <div class="admin-state admin-state--inline">
                    <strong>撤销窗口</strong>
                    <span>${escapeHtml(state.currentCustomerPulsePreview.undo_notice)}</span>
                  </div>
                `
                : ""
            }
            ${customerPulseFormFields(state.currentCustomerPulsePreview)}
            <div class="admin-customer-pulse-detail__form-actions">
              <button type="submit" class="admin-button admin-button--primary">确认并保存</button>
            </div>
          </form>
        `;
      } else if (state.currentCustomerPulsePreviewError) {
        elements.editor.hidden = false;
        elements.editor.innerHTML = `<div class="admin-state admin-state--error"><strong>当前无法加载动作预览</strong><span>${escapeHtml(state.currentCustomerPulsePreviewError)}</span></div>`;
      } else if (buttons.length) {
        elements.editor.hidden = false;
        elements.editor.innerHTML = customerPulseInlineStateHtml("先预览再执行", "选择一个候选动作后，系统才会加载可编辑草稿或执行字段。");
      } else {
        elements.editor.hidden = false;
        elements.editor.innerHTML = customerPulseInlineStateHtml("当前角色只能查看", "该卡片已对当前角色隐藏所有可执行动作。");
      }
    }
  }

  function customerPulseFeedback(message, tone) {
    const node = customerPulseElements().feedback;
    if (!node) return;
    node.hidden = false;
    node.className = `admin-state admin-state--inline${tone === "error" ? " admin-state--error" : ""}`;
    node.innerHTML = `<strong>${tone === "error" ? "处理失败" : "处理结果"}</strong><span>${escapeHtml(message)}</span>`;
  }

  function currentCustomerPulseCard() {
    return state.currentCustomerPulsePayload && state.currentCustomerPulsePayload.card ? state.currentCustomerPulsePayload.card : null;
  }

  function customerPulseActionPayload(form) {
    const actionType = String(form.dataset.actionType || "");
    if (actionType === "generate_reply_draft") {
      return { draft_message: form.querySelector("[data-customer-pulse-field='draft_message']")?.value || "" };
    }
    if (actionType === "create_followup_task") {
      return {
        task_title: form.querySelector("[data-customer-pulse-field='task_title']")?.value || "",
        due_at: (form.querySelector("[data-customer-pulse-field='due_at']")?.value || "").replace("T", " "),
      };
    }
    if (actionType === "update_followup_segment") {
      return { followup_segment: form.querySelector("[data-customer-pulse-field='followup_segment']")?.value || "" };
    }
    if (actionType === "update_tags") {
      return {
        add_tag_ids: (form.querySelector("[data-customer-pulse-field='add_tag_ids']")?.value || "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        remove_tag_ids: (form.querySelector("[data-customer-pulse-field='remove_tag_ids']")?.value || "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
      };
    }
    if (actionType === "set_followup_reminder") {
      return { due_at: (form.querySelector("[data-customer-pulse-field='due_at']")?.value || "").replace("T", " ") };
    }
    return {};
  }

  function customerPulseCardApiUrl(root, cardId, suffix) {
    return `${root.dataset.customerPulseCardApiBase}/${cardId}${suffix}`;
  }

  function loadCustomerPulsePreview(root, cardId, actionType, options = {}) {
    const card = currentCustomerPulseCard();
    if (!card) return Promise.resolve(null);
    state.currentCustomerPulsePreview = null;
    state.currentCustomerPulsePreviewError = "";
    renderCustomerPulse({ customer_pulse: state.currentCustomerPulsePayload });
    return requestCustomerPulseJson(root, customerPulseCardApiUrl(root, cardId, "/actions/preview"), {
      method: "POST",
      body: {
        action_type: actionType || card.suggested_action_type,
        track_click: Boolean(options.trackClick),
        metric_source: options.metricSource || "customer_profile_widget",
      },
    })
      .then((payload) => {
        state.currentCustomerPulsePreview = payload.preview || {};
        state.currentCustomerPulsePreviewError = "";
        renderCustomerPulse({ customer_pulse: state.currentCustomerPulsePayload });
        return state.currentCustomerPulsePreview;
      })
      .catch((error) => {
        state.currentCustomerPulsePreview = null;
        state.currentCustomerPulsePreviewError = error.message || "请稍后重试。";
        renderCustomerPulse({ customer_pulse: state.currentCustomerPulsePayload });
        return null;
      });
  }

  function loadCustomerPulseEvidence(root, cardId) {
    const card = currentCustomerPulseCard();
    if (!card) return Promise.resolve(null);
    state.currentCustomerPulseEvidencePayload = null;
    state.currentCustomerPulseEvidenceError = "";
    renderCustomerPulse({ customer_pulse: state.currentCustomerPulsePayload });
    return requestCustomerPulseJson(root, customerPulseCardApiUrl(root, cardId, "/evidence"), {
      method: "GET",
    })
      .then((payload) => {
        state.currentCustomerPulseEvidencePayload = payload;
        state.currentCustomerPulseEvidenceError = "";
        renderCustomerPulse({ customer_pulse: state.currentCustomerPulsePayload });
        return payload;
      })
      .catch((error) => {
        state.currentCustomerPulseEvidencePayload = null;
        state.currentCustomerPulseEvidenceError = error.message || "请稍后重试。";
        renderCustomerPulse({ customer_pulse: state.currentCustomerPulsePayload });
        return null;
      });
  }

  function executeCustomerPulseAction(root, form) {
    const card = currentCustomerPulseCard();
    if (!card) return Promise.resolve(null);
    return requestCustomerPulseJson(root, customerPulseCardApiUrl(root, card.id, "/actions/execute"), {
      method: "POST",
      body: {
        admin_action_token: root.dataset.adminActionToken,
        action_type: form.dataset.actionType || "",
        ...customerPulseActionPayload(form),
      },
    })
      .then((payload) => {
        const execution = (payload && payload.execution) || {};
        const message =
          execution.undo_available && execution.undo_until
            ? `操作已保存，可在 ${execution.undo_until} 前撤销。正在刷新当前客户脉冲。`
            : "操作已保存，正在刷新当前客户脉冲。";
        customerPulseFeedback(message, "success");
        return loadCustomerPulse(root);
      })
      .catch((error) => {
        customerPulseFeedback(error.message || "当前无法执行动作。", "error");
        return null;
      });
  }

  function submitCustomerPulseFeedback(root, cardId, feedbackType) {
    return requestCustomerPulseJson(root, customerPulseCardApiUrl(root, cardId, "/feedback"), {
      method: "POST",
      body: {
        admin_action_token: root.dataset.adminActionToken,
        feedback_type: feedbackType,
        feedback_source: "customer_profile_widget",
      },
    })
      .then(() => {
        customerPulseFeedback("反馈已记录，正在刷新当前客户脉冲。", "success");
        return loadCustomerPulse(root);
      })
      .catch((error) => {
        customerPulseFeedback(error.message || "当前无法记录反馈。", "error");
        return null;
      });
  }

  function loadCustomerPulse(root) {
    const elements = customerPulseElements();
    if (!elements.state || !root.dataset.pulseUrl) return Promise.resolve(null);
    return requestCustomerPulseJson(root, root.dataset.pulseUrl)
      .then((payload) => {
        state.currentCustomerPulsePreview = null;
        state.currentCustomerPulsePreviewError = "";
        state.currentCustomerPulseEvidencePayload = null;
        state.currentCustomerPulseEvidenceError = "";
        renderCustomerPulse(payload);
        return payload;
      })
      .catch((error) => {
        showSectionError(elements.state, error.message || "当前无法加载 AI 下一步");
        return null;
      });
  }

  function wireCustomerPulseActions(root) {
    document.addEventListener("click", (event) => {
      const previewButton = event.target.closest("[data-customer-pulse-preview]");
      if (previewButton) {
        loadCustomerPulsePreview(root, previewButton.dataset.cardId, previewButton.dataset.actionType, {
          trackClick: true,
          metricSource: "customer_profile_widget_action",
        });
        return;
      }
      const evidenceButton = event.target.closest("[data-customer-pulse-evidence-load]");
      if (evidenceButton) {
        loadCustomerPulseEvidence(root, evidenceButton.dataset.cardId);
        return;
      }
      const feedbackButton = event.target.closest("[data-customer-pulse-feedback-action]");
      if (feedbackButton) {
        submitCustomerPulseFeedback(root, feedbackButton.dataset.cardId, feedbackButton.dataset.feedbackType);
      }
    });
    document.addEventListener("submit", (event) => {
      const form = event.target.closest("[data-customer-pulse-action-form]");
      if (!form) return;
      event.preventDefault();
      executeCustomerPulseAction(root, form);
    });
  }

  function bootCustomerPulse(root) {
    loadCustomerPulse(root);
    wireCustomerPulseActions(root);
  }

  CustomerProfile.loadCustomerPulse = loadCustomerPulse;
  CustomerProfile.bootCustomerPulse = bootCustomerPulse;
  CustomerProfile.loadCustomerPulsePreview = loadCustomerPulsePreview;
  CustomerProfile.loadCustomerPulseEvidence = loadCustomerPulseEvidence;
  CustomerProfile.executeCustomerPulseAction = executeCustomerPulseAction;
  CustomerProfile.submitCustomerPulseFeedback = submitCustomerPulseFeedback;
})();
