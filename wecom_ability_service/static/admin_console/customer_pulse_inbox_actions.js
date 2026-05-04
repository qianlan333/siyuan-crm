(function () {
  "use strict";

  const CustomerPulseInbox = window.CustomerPulseInbox || {};
  window.CustomerPulseInbox = CustomerPulseInbox;

  const cardApiUrl = CustomerPulseInbox.cardApiUrl;
  const cardById = CustomerPulseInbox.cardById;
  const escapeHtml = CustomerPulseInbox.escapeHtml;
  const highlightSelectedCard = CustomerPulseInbox.highlightSelectedCard;
  const isPermissionError = CustomerPulseInbox.isPermissionError;
  const renderSelectedCard = CustomerPulseInbox.renderSelectedCard;
  const requestJson = CustomerPulseInbox.requestJson;
  const setDetailState = CustomerPulseInbox.setDetailState;
  const store = CustomerPulseInbox.store;
  const upsertStoredCard = CustomerPulseInbox.upsertStoredCard;

  function ensureCardDetail(root, cardId) {
    const cached = store.detailPayloads[String(cardId)];
    if (cached) {
      return Promise.resolve(cached);
    }
    return requestJson(root, cardApiUrl(root, cardId, ""), { method: "GET" }).then((payload) => {
      store.detailPayloads[String(cardId)] = payload;
      if (payload && payload.card) {
        upsertStoredCard(payload.card);
      }
      return payload;
    });
  }

  function loadCardDetail(root, cardId) {
    store.selectedCardId = String(cardId);
    highlightSelectedCard(cardId);
    setDetailState("loading", "正在加载行动卡详情", "系统正在读取当前判断、证据引用和可执行动作。");
    ensureCardDetail(root, cardId)
      .then(() => {
        renderSelectedCard(root, cardId);
      })
      .catch((error) => {
        if (isPermissionError(error)) {
          setDetailState("permission", "没有权限查看当前卡片", error.message || "请刷新页面后重试。");
          return;
        }
        setDetailState("error", "当前无法加载行动卡详情", error.message || "请稍后重试。");
      });
  }

  function loadPreview(root, cardId, actionType, options = {}) {
    store.selectedCardId = String(cardId);
    highlightSelectedCard(cardId);
    store.previewErrors[String(cardId)] = "";
    store.previewPayloads[String(cardId)] = null;
    ensureCardDetail(root, cardId)
      .then((detailPayload) => {
        const card = (detailPayload && detailPayload.card) || cardById(cardId);
        if (!card) {
          setDetailState("empty", "当前没有可用卡片", "请先刷新行动卡。");
          return null;
        }
        renderSelectedCard(root, cardId);
        return requestJson(
          root,
          cardApiUrl(root, cardId, "/actions/preview"),
          {
            method: "POST",
            body: {
              action_type: actionType || card.suggested_action_type,
              track_click: Boolean(options.trackClick),
              metric_source: options.metricSource || "customer_pulse_inbox",
            },
          },
        );
      })
      .then((payload) => {
        if (!payload) return;
        store.previewPayloads[String(cardId)] = payload.preview || {};
        renderSelectedCard(root, cardId);
      })
      .catch((error) => {
        store.previewErrors[String(cardId)] = error.message || "当前无法加载动作预览。";
        renderSelectedCard(root, cardId);
      });
  }

  function loadEvidence(root, cardId) {
    store.selectedCardId = String(cardId);
    highlightSelectedCard(cardId);
    store.evidenceErrors[String(cardId)] = "";
    store.evidencePayloads[String(cardId)] = null;
    ensureCardDetail(root, cardId)
      .then(() =>
        requestJson(root, cardApiUrl(root, cardId, "/evidence"), { method: "GET" }).then((payload) => {
          store.evidencePayloads[String(cardId)] = payload;
          renderSelectedCard(root, cardId);
        }),
      )
      .catch((error) => {
        store.evidenceErrors[String(cardId)] = error.message || "当前无法加载原始证据。";
        renderSelectedCard(root, cardId);
      });
  }

  function feedbackNode() {
    return document.querySelector("[data-detail-feedback]");
  }

  function setFeedback(message, tone) {
    const node = feedbackNode();
    if (!node) return;
    node.hidden = false;
    node.className = `admin-state admin-state--inline${tone === "error" ? " admin-state--error" : ""}`;
    node.innerHTML = `<strong>${tone === "error" ? "处理失败" : "操作结果"}</strong><span>${escapeHtml(message)}</span>`;
  }

  function currentFormPayload(form) {
    const actionType = String(form.dataset.actionType || "");
    if (actionType === "generate_reply_draft") {
      return { draft_message: form.querySelector("[data-preview-field='draft_message']")?.value || "" };
    }
    if (actionType === "create_followup_task") {
      return {
        task_title: form.querySelector("[data-preview-field='task_title']")?.value || "",
        due_at: (form.querySelector("[data-preview-field='due_at']")?.value || "").replace("T", " "),
      };
    }
    if (actionType === "update_followup_segment") {
      return { followup_segment: form.querySelector("[data-preview-field='followup_segment']")?.value || "" };
    }
    if (actionType === "update_tags") {
      const addTagIds = (form.querySelector("[data-preview-field='add_tag_ids']")?.value || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      const removeTagIds = (form.querySelector("[data-preview-field='remove_tag_ids']")?.value || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      return { add_tag_ids: addTagIds, remove_tag_ids: removeTagIds };
    }
    if (actionType === "set_followup_reminder") {
      return { due_at: (form.querySelector("[data-preview-field='due_at']")?.value || "").replace("T", " ") };
    }
    return {};
  }

  function submitAction(root, form) {
    const cardId = form.dataset.cardId;
    const actionType = form.dataset.actionType;
    const payload = {
      admin_action_token: root.dataset.adminActionToken,
      action_type: actionType,
      ...currentFormPayload(form),
    };
    requestJson(
      root,
      cardApiUrl(root, cardId, "/actions/execute"),
      {
        method: "POST",
        body: payload,
      },
    )
      .then((responsePayload) => {
        const execution = (responsePayload && responsePayload.execution) || {};
        const message =
          execution.undo_available && execution.undo_until
            ? `操作已保存，可在 ${execution.undo_until} 前撤销。正在刷新收件箱。`
            : "操作已保存，正在刷新收件箱。";
        setFeedback(message, "success");
        window.setTimeout(() => window.location.reload(), 320);
      })
      .catch((error) => {
        if (isPermissionError(error)) {
          setFeedback(error.message || "后台动作令牌无效，请刷新页面后重试。", "error");
          return;
        }
        setFeedback(error.message || "当前无法执行行动卡。", "error");
      });
  }

  function submitFeedback(root, cardId, feedbackType, feedbackSource) {
    requestJson(
      root,
      cardApiUrl(root, cardId, "/feedback"),
      {
        method: "POST",
        body: {
          admin_action_token: root.dataset.adminActionToken,
          feedback_type: feedbackType,
          feedback_source: feedbackSource || "customer_pulse_inbox",
        },
      },
    )
      .then(() => {
        setFeedback("反馈已记录，正在刷新收件箱。", "success");
        window.setTimeout(() => window.location.reload(), 320);
      })
      .catch((error) => {
        if (isPermissionError(error)) {
          setFeedback(error.message || "后台动作令牌无效，请刷新页面后重试。", "error");
          return;
        }
        setFeedback(error.message || "当前无法记录反馈。", "error");
      });
  }

  CustomerPulseInbox.ensureCardDetail = ensureCardDetail;
  CustomerPulseInbox.loadCardDetail = loadCardDetail;
  CustomerPulseInbox.loadPreview = loadPreview;
  CustomerPulseInbox.loadEvidence = loadEvidence;
  CustomerPulseInbox.feedbackNode = feedbackNode;
  CustomerPulseInbox.setFeedback = setFeedback;
  CustomerPulseInbox.currentFormPayload = currentFormPayload;
  CustomerPulseInbox.submitAction = submitAction;
  CustomerPulseInbox.submitFeedback = submitFeedback;
})();
