(function () {
  "use strict";

  const CustomerProfile = window.CustomerProfile || {};
  window.CustomerProfile = CustomerProfile;

  const requestJson = CustomerProfile.requestJson;
  const showSectionError = CustomerProfile.showSectionError;

  function automationElements() {
    return {
      state: document.querySelector("[data-automation-state]"),
      detail: document.querySelector("[data-automation-detail]"),
      feedback: document.querySelector("[data-automation-feedback]"),
      actionsWrap: document.querySelector("[data-automation-actions]"),
      buttons: Array.from(document.querySelectorAll("[data-automation-action]")),
      inPool: document.querySelector("[data-automation-in-pool]"),
      currentPool: document.querySelector("[data-automation-current-pool]"),
      currentStage: document.querySelector("[data-automation-current-stage]"),
      currentTarget: document.querySelector("[data-automation-current-target]"),
      questionnaireStatus: document.querySelector("[data-automation-questionnaire-status]"),
      latestManualAction: document.querySelector("[data-automation-latest-manual-action]"),
      lastAiPushAt: document.querySelector("[data-automation-last-ai-push-at]"),
      cooldown: document.querySelector("[data-automation-ai-cooldown]"),
    };
  }

  function setAutomationFeedback(message, tone) {
    const feedback = automationElements().feedback;
    if (!feedback) return;
    feedback.hidden = false;
    feedback.className = `admin-state admin-state--inline${tone === "error" ? " admin-state--error" : ""}`;
    feedback.innerHTML = [`<strong>${tone === "error" ? "执行失败" : "操作结果"}</strong>`, `<span>${message}</span>`].join("");
  }

  function clearAutomationFeedback() {
    const feedback = automationElements().feedback;
    if (!feedback) return;
    feedback.hidden = true;
    feedback.innerHTML = "";
  }

  function memberLookupPayload(root) {
    // admin_action_token remains reserved for Customer Pulse action payloads; automation keeps its existing payload.
    return {
      external_contact_id: root.dataset.externalUserid || "",
    };
  }

  function actionUrlFor(root, action) {
    const mapping = {
      put_in_pool: root.dataset.automationPutInPoolUrl,
      remove_from_pool: root.dataset.automationRemoveFromPoolUrl,
      set_focus: root.dataset.automationSetFocusUrl,
      set_normal: root.dataset.automationSetNormalUrl,
      mark_won: root.dataset.automationMarkWonUrl,
      unmark_won: root.dataset.automationUnmarkWonUrl,
      push_openclaw: root.dataset.automationPushOpenclawUrl,
    };
    return mapping[action];
  }

  let automationCooldownTimer = null;

  function renderAutomationCooldown(seconds) {
    const elements = automationElements();
    if (!elements.cooldown) return;
    if (!seconds || seconds <= 0) {
      elements.cooldown.textContent = "未冷却";
      return;
    }
    elements.cooldown.textContent = `冷却中，还剩 ${seconds} 秒`;
  }

  function startAutomationCooldown(seconds, root) {
    window.clearInterval(automationCooldownTimer);
    let remaining = Number(seconds || 0);
    renderAutomationCooldown(remaining);
    if (remaining <= 0) return;
    automationCooldownTimer = window.setInterval(() => {
      remaining -= 1;
      renderAutomationCooldown(remaining);
      if (remaining <= 0) {
        window.clearInterval(automationCooldownTimer);
        loadAutomationMember(root);
      }
    }, 1000);
  }

  function renderAutomationDetail(detail, root) {
    const elements = automationElements();
    const member = (detail && detail.member) || {};
    const latestManualAction = (detail && detail.latest_manual_action) || {};
    if (!elements.state || !elements.detail || !elements.actionsWrap) return;
    elements.state.hidden = true;
    elements.detail.hidden = false;
    elements.actionsWrap.hidden = false;
    elements.inPool.textContent = member.in_pool ? "是" : "否";
    elements.currentPool.textContent = member.current_pool_label || member.current_pool || "已移出";
    elements.currentStage.textContent = member.current_stage_label || member.current_stage || "已移出";
    elements.currentTarget.textContent = member.current_target_label || member.current_target || "无";
    elements.questionnaireStatus.textContent = detail.questionnaire && detail.questionnaire.status_label
      ? `${detail.questionnaire.status_label}${detail.questionnaire.result_label ? " / " + detail.questionnaire.result_label : ""}`
      : "待提交";
    elements.latestManualAction.textContent = latestManualAction.action
      ? `${latestManualAction.action} · ${latestManualAction.created_at || ""}`
      : "暂无";
    elements.lastAiPushAt.textContent = detail.last_ai_push_at || "暂无";
    const remainingSeconds = Number(detail.ai_cooldown_remaining_seconds || 0);
    startAutomationCooldown(remainingSeconds, root);
    elements.buttons.forEach((button) => {
      const action = button.dataset.automationAction;
      const enabled = Boolean(detail.actions && detail.actions[action] && detail.actions[action].enabled);
      if (action === "push_openclaw" && remainingSeconds > 0) {
        button.disabled = true;
      } else {
        button.disabled = !enabled;
      }
    });
  }

  function loadAutomationMember(root) {
    const stateNode = document.querySelector("[data-automation-state]");
    const url = root.dataset.automationMemberUrl;
    clearAutomationFeedback();
    if (stateNode) {
      stateNode.hidden = false;
      stateNode.classList.add("admin-state--loading");
    }
    return requestJson(url)
      .then((payload) => {
        renderAutomationDetail(payload.detail || {}, root);
        return payload.detail || {};
      })
      .catch((error) => {
        showSectionError(stateNode, error.message || "当前无法加载自动化状态");
        return null;
      });
  }

  function executeAutomationAction(root, action) {
    const url = actionUrlFor(root, action);
    if (!url) return Promise.resolve(null);
    clearAutomationFeedback();
    const payload = memberLookupPayload(root);
    return requestJson(url, {
      method: "POST",
      body: payload,
    })
      .then((response) => {
        if (action === "push_openclaw" && response.accepted) {
          setAutomationFeedback("已推送给 OpenClaw", "success");
        } else if (response.status === "cooldown_blocked") {
          setAutomationFeedback(`OpenClaw 冷却中，还剩 ${response.remaining_seconds || 0} 秒`, "error");
        } else {
          setAutomationFeedback("操作已执行", "success");
        }
        return loadAutomationMember(root);
      })
      .catch((error) => {
        setAutomationFeedback(error.message || "操作执行失败", "error");
        return null;
      });
  }

  function wireAutomationActions(root) {
    automationElements().buttons.forEach((button) => {
      button.addEventListener("click", () => {
        if (button.disabled) return;
        const originalText = button.textContent;
        button.disabled = true;
        button.textContent = "处理中";
        executeAutomationAction(root, button.dataset.automationAction).finally(() => {
          button.textContent = originalText;
        });
      });
    });
  }

  function bootAutomation(root) {
    loadAutomationMember(root);
    wireAutomationActions(root);
  }

  CustomerProfile.loadAutomationMember = loadAutomationMember;
  CustomerProfile.executeAutomationAction = executeAutomationAction;
  CustomerProfile.bootAutomation = bootAutomation;
})();
