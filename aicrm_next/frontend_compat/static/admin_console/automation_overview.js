(function () {
  "use strict";

  const AutomationOverview = window.AutomationOverview || {};
  window.AutomationOverview = AutomationOverview;

  function boot() {
    const root = AutomationOverview.root();
    if (!root) return;
    AutomationOverview.bindRefreshAction(root);
    AutomationOverview.loadDashboard(root).catch((error) => {
      AutomationOverview.setLoadingVisible(false);
      AutomationOverview.showFeedback(error.message || "加载自动化转化概览失败", "error");
    });
  }

  AutomationOverview.boot = boot;

  document.addEventListener("DOMContentLoaded", () => {
    if (typeof AutomationOverview.boot === "function") {
      AutomationOverview.boot();
    }
  });
})();
