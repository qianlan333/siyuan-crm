(function (window) {
  "use strict";

  function safeJsonParse(text) {
    if (!text) return null;
    try {
      return JSON.parse(text);
    } catch (_error) {
      return null;
    }
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function headersToObject(headers) {
    const result = {};
    if (!headers) return result;
    if (typeof Headers !== "undefined") {
      try {
        const normalizedHeaders = new Headers(headers);
        normalizedHeaders.forEach((value, key) => {
          result[key] = value;
        });
        return result;
      } catch (_error) {
        return { ...headers };
      }
    }
    return { ...headers };
  }

  function hasHeader(headers, name) {
    const normalizedName = String(name || "").toLowerCase();
    return Object.keys(headers).some((key) => key.toLowerCase() === normalizedName);
  }

  function hasBody(options) {
    return Object.prototype.hasOwnProperty.call(options, "body") && options.body !== undefined && options.body !== null;
  }

  function isFormData(value) {
    return typeof FormData !== "undefined" && value instanceof FormData;
  }

  function isUrlSearchParams(value) {
    return typeof URLSearchParams !== "undefined" && value instanceof URLSearchParams;
  }

  function isJsonBody(value) {
    return Array.isArray(value) || Object.prototype.toString.call(value) === "[object Object]";
  }

  function buildRequestOptions(options) {
    const finalOptions = { ...options };
    const headers = headersToObject(options.headers);
    const body = options.body;

    if (!hasHeader(headers, "Accept")) {
      headers.Accept = "application/json";
    }

    finalOptions.method = String(options.method || "GET").toUpperCase();
    finalOptions.credentials = options.credentials || "same-origin";

    if (!hasBody(options)) {
      delete finalOptions.body;
    } else if (isFormData(body) || isUrlSearchParams(body) || typeof body === "string") {
      finalOptions.body = body;
    } else if (isJsonBody(body)) {
      if (!hasHeader(headers, "Content-Type")) {
        headers["Content-Type"] = "application/json";
      }
      finalOptions.body = JSON.stringify(body);
    } else {
      finalOptions.body = body;
    }

    finalOptions.headers = headers;
    return finalOptions;
  }

  function responseErrorMessage(response, payload) {
    if (payload && payload.error) return String(payload.error);
    if (payload && payload.message) return String(payload.message);
    if (response && response.statusText) return response.statusText;
    if (response && response.status) return `request failed (${response.status})`;
    return "request failed";
  }

  function normalizeRequestError(error, context = {}) {
    if (!error.status && context.response) {
      error.status = context.response.status;
    } else if (!error.status && context.status) {
      error.status = context.status;
    }
    if (!Object.prototype.hasOwnProperty.call(error, "payload")) {
      error.payload = context.payload || null;
    }
    if (!error.response && context.response) {
      error.response = context.response;
    }
    if (!error.url && context.url) {
      error.url = context.url;
    }
    if (!error.method && context.method) {
      error.method = context.method;
    }
    return error;
  }

  function buildRequestError(response, payload, context) {
    return normalizeRequestError(new Error(responseErrorMessage(response, payload)), {
      ...context,
      response,
      payload,
      status: response.status,
    });
  }

  function requestJson(url, options = {}) {
    const finalOptions = buildRequestOptions(options);
    const method = finalOptions.method || "GET";
    return fetch(url, finalOptions)
      .then((response) =>
        response.text().then((text) => ({
          response,
          payload: safeJsonParse(text),
        })),
      )
      .then(({ response, payload }) => {
        if (!response.ok || (payload && payload.ok === false)) {
          throw buildRequestError(response, payload, { url, method });
        }
        return payload || { ok: true };
      });
  }

  function isPermissionError(error) {
    const message = String((error && error.message) || "");
    const loweredMessage = message.toLowerCase();
    return Boolean(error) && (
      error.status === 401 ||
      error.status === 403 ||
      message.includes("令牌无效") ||
      loweredMessage.includes("permission") ||
      message.includes("权限")
    );
  }

  window.AdminApi = {
    ...(window.AdminApi || {}),
    safeJsonParse,
    escapeHtml,
    requestJson,
    isPermissionError,
    normalizeRequestError,
  };
})(window);
