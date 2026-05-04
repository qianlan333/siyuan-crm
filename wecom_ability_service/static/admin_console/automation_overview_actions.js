(function () {
  "use strict";

  const AutomationOverview = window.AutomationOverview || {};
  window.AutomationOverview = AutomationOverview;

  const elements = AutomationOverview.elements;
  const getAdminActionToken = AutomationOverview.getAdminActionToken;
  const getApiUrls = AutomationOverview.getApiUrls;
  const requestJson = AutomationOverview.requestJson;
  const renderDashboard = AutomationOverview.renderDashboard;
  const showFeedback = AutomationOverview.showFeedback;

  async function loadDashboard(rootNode) {
    const apiUrls = getApiUrls(rootNode);
    showFeedback("", "");
    const payload = await requestJson(apiUrls.dashboard, { credentials: "same-origin" });
    renderDashboard(payload.dashboard || {});
  }

  async function postAdminAction(rootNode, url) {
    const formData = new FormData();
    formData.append("admin_action_token", getAdminActionToken(rootNode));
    const response = await fetch(url, {
      method: "POST",
      body: formData,
      credentials: "same-origin",
      headers: {
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
    });
    const payload = await response.json().catch(() => ({}));
    const accepted = Boolean(payload.ok) || ["disabled", "idle", "throttled", "quiet_hours"].includes(String(payload.status || ""));
    if (!response.ok || !accepted) {
      throw new Error(payload.error || payload.message || "执行失败");
    }
    return payload;
  }

  function bindRefreshAction(rootNode) {
    const apiUrls = getApiUrls(rootNode);
    const { refreshButton, refreshStatus } = elements();
    if (!refreshButton || !refreshStatus) return;
    refreshButton.addEventListener("click", async () => {
      refreshButton.disabled = true;
      refreshStatus.textContent = "正在刷新自动化转化模块状态...";
      try {
        await postAdminAction(rootNode, apiUrls.message_activity_sync_run);
        await postAdminAction(rootNode, apiUrls.reply_monitor_capture);
        await postAdminAction(rootNode, apiUrls.reply_monitor_run_due);
        await loadDashboard(rootNode);
        refreshStatus.textContent = "状态刷新完成";
        showFeedback("自动化转化模块状态已刷新", "success");
      } catch (error) {
        refreshStatus.textContent = error.message || "状态刷新失败";
        showFeedback(error.message || "状态刷新失败", "error");
      } finally {
        refreshButton.disabled = false;
      }
    });
  }

  AutomationOverview.loadDashboard = loadDashboard;
  AutomationOverview.postAdminAction = postAdminAction;
  AutomationOverview.bindRefreshAction = bindRefreshAction;
})();
