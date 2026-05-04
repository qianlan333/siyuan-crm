(function () {
  "use strict";

  const CustomerPulseInbox = window.CustomerPulseInbox || {};
  window.CustomerPulseInbox = CustomerPulseInbox;

  const loadCardDetail = CustomerPulseInbox.loadCardDetail;
  const loadEvidence = CustomerPulseInbox.loadEvidence;
  const loadPreview = CustomerPulseInbox.loadPreview;
  const root = CustomerPulseInbox.root;
  const safeJsonParse = CustomerPulseInbox.safeJsonParse;
  const setDetailState = CustomerPulseInbox.setDetailState;
  const store = CustomerPulseInbox.store;
  const submitAction = CustomerPulseInbox.submitAction;
  const submitFeedback = CustomerPulseInbox.submitFeedback;

  function wireInboxInteractions(rootNode) {
    document.addEventListener("click", (event) => {
      const selectButton = event.target.closest("[data-card-select]");
      if (selectButton) {
        loadCardDetail(rootNode, selectButton.dataset.cardId);
        return;
      }
      const actionButton = event.target.closest("[data-card-action-preview],[data-detail-action-preview]");
      if (actionButton) {
        loadPreview(rootNode, actionButton.dataset.cardId, actionButton.dataset.actionType, {
          trackClick: true,
          metricSource: actionButton.hasAttribute("data-detail-action-preview")
            ? "customer_pulse_inbox_detail_action"
            : "customer_pulse_inbox_card_action",
        });
        return;
      }
      const evidenceButton = event.target.closest("[data-detail-evidence-load]");
      if (evidenceButton) {
        loadEvidence(rootNode, evidenceButton.dataset.cardId);
        return;
      }
      const feedbackButton = event.target.closest("[data-card-feedback],[data-detail-feedback]");
      if (feedbackButton) {
        submitFeedback(
          rootNode,
          feedbackButton.dataset.cardId,
          feedbackButton.dataset.feedbackType,
          feedbackButton.hasAttribute("data-detail-feedback") ? "customer_pulse_inbox_detail_feedback" : "customer_pulse_inbox_card_feedback",
        );
      }
    });
    document.addEventListener("submit", (event) => {
      const form = event.target.closest("[data-detail-action-form]");
      if (!form) return;
      event.preventDefault();
      submitAction(rootNode, form);
    });
  }

  function boot() {
    const rootNode = root();
    if (!rootNode) return;
    const rawPayload = rootNode.querySelector("[data-customer-pulse-inbox-json]");
    store.payload = safeJsonParse(rawPayload ? rawPayload.textContent : "") || { cards: [] };
    wireInboxInteractions(rootNode);
    const firstCard = ((store.payload && store.payload.cards) || [])[0];
    if (!firstCard) {
      setDetailState("empty", "当前没有待处理行动卡", "可以先刷新行动卡，或调整筛选条件。");
      return;
    }
    loadCardDetail(rootNode, firstCard.id);
  }

  CustomerPulseInbox.wireInteractions = wireInboxInteractions;
  CustomerPulseInbox.wireInboxInteractions = wireInboxInteractions;
  CustomerPulseInbox.boot = boot;
})();
