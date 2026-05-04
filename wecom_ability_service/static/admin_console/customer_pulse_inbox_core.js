(function () {
  "use strict";

  const AdminApi = window.AdminApi || {};
  const CustomerPulseInbox = window.CustomerPulseInbox || {};
  window.CustomerPulseInbox = CustomerPulseInbox;

  const store = {
    payload: null,
    selectedCardId: null,
    detailPayloads: {},
    evidencePayloads: {},
    previewPayloads: {},
    evidenceErrors: {},
    previewErrors: {},
  };

  const safeJsonParse = AdminApi.safeJsonParse || function safeJsonParse(text) {
    if (!text) return null;
    try {
      return JSON.parse(text);
    } catch (_error) {
      return null;
    }
  };

  const escapeHtml = AdminApi.escapeHtml || function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  };

  const baseRequestJson = AdminApi.requestJson || function adminApiRequestJsonUnavailable() {
    return Promise.reject(new Error("AdminApi.requestJson unavailable"));
  };

  const isPermissionError = AdminApi.isPermissionError || function isPermissionError(error) {
    const message = String((error && error.message) || "");
    return error && (error.status === 401 || error.status === 403 || message.includes("令牌无效"));
  };

  function root() {
    return document.querySelector("[data-customer-pulse-inbox-root]");
  }

  function customerPulseAccessHeaders(rootNode) {
    const headers = {};
    if (!rootNode || !rootNode.dataset) return headers;
    if (rootNode.dataset.customerPulseTenantKey) {
      headers["X-Tenant-Key"] = rootNode.dataset.customerPulseTenantKey;
    }
    if (rootNode.dataset.customerPulseActorUserid) {
      headers["X-Admin-Userid"] = rootNode.dataset.customerPulseActorUserid;
    }
    if (rootNode.dataset.customerPulseActorRole) {
      headers["X-Admin-Role"] = rootNode.dataset.customerPulseActorRole;
    }
    return headers;
  }

  function requestJson(rootNode, url, options = {}) {
    return baseRequestJson(url, {
      ...options,
      headers: {
        ...customerPulseAccessHeaders(rootNode),
        ...(options.headers || {}),
      },
    });
  }

  function toDateTimeLocalValue(value) {
    const text = String(value || "").trim();
    if (!text) return "";
    return text.replace(" ", "T").slice(0, 16);
  }

  function inlineStateHtml(title, body, tone = "inline") {
    const className =
      tone === "error"
        ? "admin-state admin-state--inline admin-state--error"
        : "admin-state admin-state--inline";
    return `<div class="${className}"><strong>${escapeHtml(title)}</strong><span>${escapeHtml(body)}</span></div>`;
  }

  function inboxState() {
    return {
      stateNode: document.querySelector("[data-customer-pulse-detail-state]"),
      bodyNode: document.querySelector("[data-customer-pulse-detail-body]"),
    };
  }

  function setDetailState(kind, title, body) {
    const { stateNode, bodyNode } = inboxState();
    if (!stateNode || !bodyNode) return;
    bodyNode.hidden = true;
    stateNode.hidden = false;
    stateNode.className = "admin-state";
    if (kind === "loading") {
      stateNode.classList.add("admin-state--loading");
    } else if (kind === "error" || kind === "permission") {
      stateNode.classList.add("admin-state--error");
    } else if (kind === "inline") {
      stateNode.classList.add("admin-state--inline");
    } else {
      stateNode.classList.add("admin-state--empty");
    }
    stateNode.innerHTML = `<strong>${escapeHtml(title)}</strong><span>${escapeHtml(body)}</span>`;
  }

  function cardApiUrl(rootNode, cardId, suffix) {
    return `${rootNode.dataset.cardApiBase}/${cardId}${suffix}`;
  }

  CustomerPulseInbox.root = root;
  CustomerPulseInbox.safeJsonParse = safeJsonParse;
  CustomerPulseInbox.escapeHtml = escapeHtml;
  CustomerPulseInbox.requestJson = requestJson;
  CustomerPulseInbox.requestCustomerPulseJson = requestJson;
  CustomerPulseInbox.isPermissionError = isPermissionError;
  CustomerPulseInbox.customerPulseAccessHeaders = customerPulseAccessHeaders;
  CustomerPulseInbox.cardApiUrl = cardApiUrl;
  CustomerPulseInbox.toDateTimeLocalValue = toDateTimeLocalValue;
  CustomerPulseInbox.inlineStateHtml = inlineStateHtml;
  CustomerPulseInbox.inboxState = inboxState;
  CustomerPulseInbox.setDetailState = setDetailState;
  CustomerPulseInbox.store = store;
})();
