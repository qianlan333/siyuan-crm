(function () {
  "use strict";

  const CustomerPulseInbox = window.CustomerPulseInbox || {};
  window.CustomerPulseInbox = CustomerPulseInbox;

  const escapeHtml = CustomerPulseInbox.escapeHtml;
  const inlineStateHtml = CustomerPulseInbox.inlineStateHtml;
  const inboxState = CustomerPulseInbox.inboxState;
  const setDetailState = CustomerPulseInbox.setDetailState;
  const store = CustomerPulseInbox.store;
  const toDateTimeLocalValue = CustomerPulseInbox.toDateTimeLocalValue;

  function availableActionButtons(card) {
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

  function evidenceRefsHtml(items) {
    const rows = Array.isArray(items) ? items : [];
    if (!rows.length) {
      return inlineStateHtml("暂无证据线索", "当前没有可展示的 evidence refs。");
    }
    return rows
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

  function evidenceItemsHtml(items) {
    const rows = Array.isArray(items) ? items : [];
    if (!rows.length) {
      return inlineStateHtml("暂无可展开证据", "当前没有命中可展示的原始证据内容。");
    }
    return rows
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

  function pulseFormFields(preview) {
    const actionType = String((preview && preview.action_type) || "");
    const payload = (preview && preview.preview) || {};
    if (actionType === "generate_reply_draft") {
      return `
        <label>
          <span>草稿内容</span>
          <textarea rows="7" data-preview-field="draft_message" placeholder="在这里继续编辑草稿">${escapeHtml(payload.draft_message || "")}</textarea>
          <small>${escapeHtml(payload.draft_notice || "所有外发消息默认只生成草稿，需人工确认后再发送。")}</small>
        </label>
      `;
    }
    if (actionType === "create_followup_task") {
      return `
        <label>
          <span>任务标题</span>
          <input type="text" data-preview-field="task_title" value="${escapeHtml(payload.task_title || "")}">
        </label>
        <label>
          <span>截止时间</span>
          <input type="datetime-local" data-preview-field="due_at" value="${escapeHtml(toDateTimeLocalValue(payload.due_at || ""))}">
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
          <select data-preview-field="followup_segment">
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
          <input type="text" data-preview-field="add_tag_ids" value="${escapeHtml((payload.add_tag_ids || []).join(","))}" placeholder="tag_a,tag_b">
        </label>
        <label>
          <span>移除标签 ID</span>
          <input type="text" data-preview-field="remove_tag_ids" value="${escapeHtml((payload.remove_tag_ids || []).join(","))}" placeholder="tag_c,tag_d">
        </label>
      `;
    }
    if (actionType === "set_followup_reminder") {
      return `
        <label>
          <span>提醒时间</span>
          <input type="datetime-local" data-preview-field="due_at" value="${escapeHtml(toDateTimeLocalValue(payload.due_at || ""))}">
        </label>
      `;
    }
    return "";
  }

  function highlightSelectedCard(cardId) {
    document.querySelectorAll("[data-card-id]").forEach((node) => {
      node.classList.toggle("is-selected", String(node.dataset.cardId || "") === String(cardId || ""));
    });
  }

  function cardById(cardId) {
    const cards = (store.payload && store.payload.cards) || [];
    return cards.find((item) => String(item.id) === String(cardId)) || null;
  }

  function upsertStoredCard(card) {
    if (!card || !store.payload || !Array.isArray(store.payload.cards)) return;
    const cards = store.payload.cards;
    const index = cards.findIndex((item) => String(item.id) === String(card.id));
    if (index >= 0) {
      cards[index] = { ...cards[index], ...card };
    }
  }

  function actionSlotHtml(root, card, preview, previewError) {
    const actionButtons = availableActionButtons(card);
    const feedbackButtons = Array.isArray(card.feedback_actions) ? card.feedback_actions : [];
    const actionButtonsHtml = actionButtons.length
      ? `
        <div class="admin-customer-pulse-card__actions">
          ${actionButtons
            .map(
              (item) => `
                <button
                  type="button"
                  class="admin-button ${item.action_type === (preview && preview.action_type) ? "admin-button--primary" : "admin-button--ghost"}"
                  data-detail-action-preview
                  data-card-id="${card.id}"
                  data-action-type="${escapeHtml(item.action_type)}"
                >
                  ${escapeHtml(item.action_label || "动作")}
                </button>
              `,
            )
            .join("")}
        </div>
      `
      : inlineStateHtml("当前角色只能查看", "该卡片已对当前角色隐藏所有可执行动作。");
    const feedbackButtonsHtml = feedbackButtons.length
      ? `
        <div class="admin-customer-pulse-card__actions">
          ${feedbackButtons
            .map(
              (item) => `
                <button
                  type="button"
                  class="admin-button admin-button--ghost"
                  data-detail-feedback
                  data-card-id="${card.id}"
                  data-feedback-type="${escapeHtml(item.type || "")}"
                >
                  ${escapeHtml(item.label || item.type || "反馈")}
                </button>
              `,
            )
            .join("")}
        </div>
      `
      : "";
    let editorHtml = "";
    if (preview && preview.action_type) {
      editorHtml = `
        <form class="admin-form-grid admin-form-grid--stacked" data-detail-action-form data-card-id="${card.id}" data-action-type="${escapeHtml(preview.action_type || "")}">
          <div class="admin-state admin-state--inline">
            <strong>${escapeHtml(preview.action_label || "动作预览")}</strong>
            <span>${escapeHtml(preview.action_title || preview.action_label || "请确认后执行")}</span>
          </div>
          ${
            preview.undo_notice
              ? `
                <div class="admin-state admin-state--inline">
                  <strong>撤销窗口</strong>
                  <span>${escapeHtml(preview.undo_notice)}</span>
                </div>
              `
              : ""
          }
          ${pulseFormFields(preview)}
          <div class="admin-customer-pulse-detail__form-actions">
            <button type="submit" class="admin-button admin-button--primary">确认并保存</button>
            <a class="admin-button admin-button--ghost" href="${escapeHtml(`${root.dataset.customerDetailBase}/${card.external_userid}`)}">打开客户详情</a>
          </div>
        </form>
      `;
    } else if (previewError) {
      editorHtml = inlineStateHtml("当前无法预览动作", previewError, "error");
    } else if (actionButtons.length) {
      editorHtml = inlineStateHtml("先预览再执行", "选择一个候选动作后，系统才会加载可编辑草稿或执行字段。");
    }
    return `
      <div>
        <div class="admin-customer-pulse-detail__section-title">候选动作</div>
        ${actionButtonsHtml}
      </div>
      ${editorHtml}
      ${
        feedbackButtonsHtml
          ? `
            <div>
              <div class="admin-customer-pulse-detail__section-title">反馈</div>
              ${feedbackButtonsHtml}
            </div>
          `
          : ""
      }
    `;
  }

  function evidenceSlotHtml(card, evidencePayload, evidenceError) {
    const permissions = (card && card.permissions) || {};
    const refs = Array.isArray(card.evidence_refs) ? card.evidence_refs : [];
    const canExpand = Boolean(permissions.evidence_view && card.evidence_expand_available);
    let extraHtml = "";
    if (canExpand) {
      if (evidencePayload && Array.isArray(evidencePayload.evidence) && evidencePayload.evidence.length) {
        extraHtml = `
          <div class="admin-customer-pulse-detail__section-title">原始证据</div>
          <div class="admin-profile-message-list">${evidenceItemsHtml(evidencePayload.evidence)}</div>
          ${
            Array.isArray(evidencePayload.inaccessible_refs) && evidencePayload.inaccessible_refs.length
              ? inlineStateHtml(
                  "部分证据未展示",
                  `有 ${evidencePayload.inaccessible_refs.length} 条 evidence refs 未通过原始边界校验。`,
                )
              : ""
          }
        `;
      } else if (evidenceError) {
        extraHtml = inlineStateHtml("当前无法展开原始证据", evidenceError, "error");
      } else if (refs.length) {
        extraHtml = `
          <div class="admin-toolbar">
            <button type="button" class="admin-button admin-button--ghost" data-detail-evidence-load data-card-id="${card.id}">
              查看原始证据
            </button>
          </div>
        `;
      }
    } else if (refs.length) {
      extraHtml = inlineStateHtml("当前角色无权展开原始证据", "可以看到 evidence refs，但不能直接读取原始记录内容。");
    }
    return `
      <div>
        <div class="admin-customer-pulse-detail__section-title">证据线索</div>
        <div class="admin-profile-message-list">${evidenceRefsHtml(refs)}</div>
      </div>
      ${extraHtml}
    `;
  }

  function renderDetail(root, card, detailPayload, preview, previewError, evidencePayload, evidenceError) {
    const { stateNode, bodyNode } = inboxState();
    if (!stateNode || !bodyNode || !card) return;
    bodyNode.innerHTML = `
      <div class="admin-customer-pulse-detail__body">
        <div class="admin-customer-pulse-detail__head">
          <div>
            <h2>${escapeHtml(card.customer_name || "未命名客户")}</h2>
            <p>${escapeHtml(card.title || "客户推进行动卡")}</p>
          </div>
          <div class="admin-toolbar">
            <span class="admin-inline-chip admin-inline-chip--neutral">${escapeHtml(card.card_status_label || "待处理")}</span>
            <span class="admin-inline-chip admin-inline-chip--${card.priority === "high" ? "warn" : "ok"}">${escapeHtml(card.priority_label || "常规")}</span>
          </div>
        </div>

        <div class="admin-state admin-state--inline">
          <strong>当前判断</strong>
          <span>${escapeHtml(card.current_judgement || card.summary || "暂无判断")}</span>
        </div>

        <dl class="admin-definition-list">
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
            <dd>${escapeHtml((card.latest_event && card.latest_event.title) || "最近事件")} · ${escapeHtml(
              (card.latest_event && card.latest_event.detail) || "暂无详情",
            )}</dd>
          </div>
          <div>
            <dt>为什么现在</dt>
            <dd>${escapeHtml((preview && preview.why_now) || card.why_now || "当前信号已达到行动阈值")}</dd>
          </div>
          <div>
            <dt>处理要求</dt>
            <dd>${escapeHtml(card.draft_notice || "所有外发消息默认只生成草稿，由人工确认。")}</dd>
          </div>
        </dl>

        <div class="admin-customer-pulse-flags">
          ${(card.risk_flags || [])
            .map((item) => `<span class="admin-inline-chip admin-inline-chip--warn">${escapeHtml(item.label || item.key || "风险")}</span>`)
            .join("")}
          ${(card.opportunity_flags || [])
            .map((item) => `<span class="admin-inline-chip admin-inline-chip--ok">${escapeHtml(item.label || item.key || "机会")}</span>`)
            .join("")}
        </div>

        ${evidenceSlotHtml(card, evidencePayload, evidenceError)}
        ${actionSlotHtml(root, card, preview, previewError)}

        <div class="admin-state admin-state--inline" data-detail-feedback hidden></div>
      </div>
    `;
    stateNode.hidden = true;
    bodyNode.hidden = false;
  }

  function renderSelectedCard(root, cardId) {
    const detailPayload = store.detailPayloads[String(cardId)] || null;
    const previewPayload = store.previewPayloads[String(cardId)] || null;
    const evidencePayload = store.evidencePayloads[String(cardId)] || null;
    const card = (detailPayload && detailPayload.card) || cardById(cardId);
    if (!card) {
      setDetailState("empty", "当前没有可用卡片", "请先刷新行动卡。");
      return;
    }
    renderDetail(
      root,
      card,
      detailPayload,
      previewPayload,
      store.previewErrors[String(cardId)] || "",
      evidencePayload,
      store.evidenceErrors[String(cardId)] || "",
    );
  }

  CustomerPulseInbox.availableActionButtons = availableActionButtons;
  CustomerPulseInbox.evidenceRefsHtml = evidenceRefsHtml;
  CustomerPulseInbox.evidenceItemsHtml = evidenceItemsHtml;
  CustomerPulseInbox.pulseFormFields = pulseFormFields;
  CustomerPulseInbox.actionSlotHtml = actionSlotHtml;
  CustomerPulseInbox.evidenceSlotHtml = evidenceSlotHtml;
  CustomerPulseInbox.renderDetail = renderDetail;
  CustomerPulseInbox.renderSelectedCard = renderSelectedCard;
  CustomerPulseInbox.highlightSelectedCard = highlightSelectedCard;
  CustomerPulseInbox.cardById = cardById;
  CustomerPulseInbox.upsertStoredCard = upsertStoredCard;
})();
