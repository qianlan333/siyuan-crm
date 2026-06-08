(function () {
  "use strict";

  const AdminApi = window.AdminApi || {};
  const AutomationOverview = window.AutomationOverview || {};
  window.AutomationOverview = AutomationOverview;

  const state = {};

  const safeJsonParse = AdminApi.safeJsonParse || function safeJsonParse(text) {
    if (!text) return null;
    try {
      return JSON.parse(text);
    } catch (_error) {
      return null;
    }
  };

  const adminEscapeHtml = AdminApi.escapeHtml;
  function escapeHtml(value) {
    const normalizedValue = String(value == null ? "" : value);
    if (typeof adminEscapeHtml === "function") {
      return adminEscapeHtml(normalizedValue);
    }
    return normalizedValue
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  const adminRequestJson = AdminApi.requestJson || function adminApiRequestJsonUnavailable() {
    return Promise.reject(new Error("AdminApi.requestJson unavailable"));
  };

  function requestJson(url, options = {}) {
    return adminRequestJson(url, options).catch((error) => {
      const message = String((error && error.message) || "");
      if (!message || message === "request failed" || message.startsWith("request failed (") || (error && error.status && !error.payload)) {
        throw new Error("请求失败");
      }
      throw error;
    });
  }

  function root() {
    return document.getElementById("automation-overview-root");
  }

  function getApiUrls(rootNode) {
    const source = rootNode || root();
    if (!source) return {};
    return safeJsonParse(source.dataset.apiUrls || "{}") || {};
  }

  function getAdminActionToken(rootNode) {
    const source = rootNode || root();
    return String((source && source.dataset && source.dataset.adminActionToken) || "");
  }

  function elements() {
    return {
      feedback: document.getElementById("overview-feedback"),
      loading: document.getElementById("overview-loading"),
      summaryGrid: document.getElementById("overview-summary-grid"),
      refreshButton: document.getElementById("overview-refresh-button"),
      refreshStatus: document.getElementById("overview-refresh-status"),
      memberGroups: document.getElementById("overview-member-groups"),
      profileTemplateNote: document.getElementById("overview-profile-template-note"),
      additionalStats: document.getElementById("overview-additional-stats"),
      segmentationStats: document.getElementById("overview-segmentation-stats"),
      pendingQuestionnaire: document.getElementById("overview-pending-questionnaire"),
      operating: document.getElementById("overview-operating"),
      converted: document.getElementById("overview-converted"),
      activeWorkflowCount: document.getElementById("overview-active-workflow-count"),
      activeWorkflowChip: document.getElementById("overview-active-workflow-chip"),
      questionnaireSubmitted: document.getElementById("overview-questionnaire-submitted"),
      lastUpdated: document.getElementById("overview-last-updated"),
      executionBody: document.getElementById("overview-execution-body"),
    };
  }

  function showFeedback(message, tone) {
    const { feedback } = elements();
    if (!feedback) return;
    if (!message) {
      feedback.hidden = true;
      feedback.textContent = "";
      feedback.className = "ac-overview-feedback";
      return;
    }
    feedback.hidden = false;
    feedback.textContent = message;
    feedback.className = "ac-overview-feedback" + (tone === "error" ? " is-error" : tone === "success" ? " is-success" : "");
  }

  function setLoadingVisible(visible) {
    const { loading } = elements();
    if (loading) {
      loading.hidden = !visible;
    }
  }

  AutomationOverview.root = root;
  AutomationOverview.escapeHtml = escapeHtml;
  AutomationOverview.requestJson = requestJson;
  AutomationOverview.getApiUrls = getApiUrls;
  AutomationOverview.getAdminActionToken = getAdminActionToken;
  AutomationOverview.elements = elements;
  AutomationOverview.showFeedback = showFeedback;
  AutomationOverview.setLoadingVisible = setLoadingVisible;
  AutomationOverview.state = state;
})();
