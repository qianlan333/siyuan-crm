(function () {
  const root = document.getElementById("sidebar-workbench-root");
  const content = document.getElementById("content");
  const tabsNode = document.getElementById("tabs");
  const toastNode = document.getElementById("toast");
  const debugWrap = document.getElementById("debug-wrap");
  const mobileModal = document.getElementById("mobile-modal");
  const mobileInput = document.getElementById("mobile-input");
  const mobileStatus = document.getElementById("mobile-status");
  const confirmMobileButton = document.getElementById("confirm-mobile-button");

  const tabs = [
    ["profile", "核心画像"],
    ["questionnaires", "问卷"],
    ["products", "商品"],
    ["orders", "订单"],
    ["materials", "素材"],
    ["other_staff_messages", "其他客服聊天"],
  ];
  const materialTabs = [
    ["image", "图片素材"],
    ["mini", "小程序素材"],
    ["pdf", "PDF 素材"],
  ];
  const WORKBENCH_STATES = {
    identifying_customer: "identifying_customer",
    sdk_unavailable: "sdk_unavailable",
    context_missing: "context_missing",
    loading_workbench: "loading_workbench",
    ready: "ready",
    degraded_ready: "degraded_ready",
    error: "error",
  };
  const DEFAULT_TIMEOUT_MS = 8000;
  const SDK_TIMEOUT_MS = 5000;
  const PRODUCT_CARD_IMAGE_PATH = "/static/sidebar_workbench/product-card-cover.png";

  const state = {
    status: WORKBENCH_STATES.identifying_customer,
    external_userid: "",
    owner_userid: "",
    bind_by_userid: "",
    activeTab: "profile",
    materialType: "image",
    workbench: null,
    loaded: {},
    data: {
      questionnaires: null,
      products: null,
      orders: null,
      materials: {},
      other_staff_messages: null,
    },
    profileSaveTimer: null,
    toastTimer: null,
    lastError: null,
  };

  const debugEnabled = root && root.dataset.debugEnabled === "true";
  debugWrap.classList.toggle("hidden", !debugEnabled);

  function endpoint(name) {
    return root.dataset[name] || "";
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function safeJsonParse(text) {
    try {
      return JSON.parse(text);
    } catch (_error) {
      return null;
    }
  }

  function writeDebug(label, payload) {
    if (!debugEnabled) return;
    const line = "[" + new Date().toISOString() + "] " + label + (payload === undefined ? "" : " " + JSON.stringify(payload));
    const item = document.createElement("pre");
    item.textContent = line;
    debugWrap.appendChild(item);
    console.log(line);
  }

  function getWeComSdk() {
    const sdk = window.jWeixin || window.wx || null;
    if (sdk && window.wx !== sdk) {
      window.wx = sdk;
    }
    return sdk;
  }

  function customerContextQuery() {
    return {
      external_userid: state.external_userid,
      owner_userid: state.owner_userid,
      bind_by_userid: state.bind_by_userid || state.owner_userid,
    };
  }

  function productContextDiagnostics(payload) {
    const products = (payload && payload.products) || [];
    return {
      context_source: payload && payload.diagnostics ? payload.diagnostics.context_source : "",
      context_status: payload && payload.diagnostics ? payload.diagnostics.context_status : "",
      product_url_has_context: products.some((item) => {
        try {
          return new URL(item.product_url || "", window.location.origin).searchParams.has("ctx");
        } catch (_error) {
          return String(item.product_url || "").indexOf("ctx=") !== -1;
        }
      }),
    };
  }

  function showToast(message, tone) {
    window.clearTimeout(state.toastTimer);
    toastNode.textContent = message || "";
    toastNode.className = "toast" + (tone === "error" ? " error" : "");
    toastNode.classList.remove("hidden");
    state.toastTimer = window.setTimeout(() => toastNode.classList.add("hidden"), 1900);
  }

  async function requestJson(url, options) {
    const timeoutMs = Number((options && options.timeoutMs) || DEFAULT_TIMEOUT_MS);
    const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    const timer = controller
      ? window.setTimeout(() => controller.abort(), timeoutMs)
      : null;
    const finalOptions = {
      headers: {
        Accept: "application/json",
        ...(options && options.body ? { "Content-Type": "application/json" } : {}),
        ...((options && options.headers) || {}),
      },
      ...(options || {}),
      ...(controller ? { signal: controller.signal } : {}),
    };
    delete finalOptions.timeoutMs;
    try {
      const response = await fetch(url, finalOptions);
      const text = await response.text();
      const payload = text ? safeJsonParse(text) : null;
      if (!response.ok || (payload && payload.ok === false)) {
        const error = new Error((payload && payload.error) || "请求失败");
        error.status = response.status;
        error.payload = payload || {};
        throw error;
      }
      return payload || { ok: true };
    } catch (error) {
      if (error && error.name === "AbortError") {
        const timeoutError = new Error("请求超时，请重试");
        timeoutError.stage = "request_timeout";
        throw timeoutError;
      }
      throw error;
    } finally {
      if (timer) window.clearTimeout(timer);
    }
  }

  function queryUrl(baseUrl, params) {
    const url = new URL(baseUrl, window.location.origin);
    Object.entries(params || {}).forEach(([key, value]) => {
      if (value !== undefined && value !== null && String(value).trim() !== "") {
        url.searchParams.set(key, String(value).trim());
      }
    });
    return url.toString();
  }

  function absoluteUrl(path) {
    const text = String(path || "").trim();
    if (!text) return "";
    try {
      return new URL(text, window.location.origin).toString();
    } catch (_error) {
      return text;
    }
  }

  function getQueryValue(key) {
    return new URLSearchParams(window.location.search).get(key) || "";
  }

  function setPanelLoading(title) {
    content.innerHTML = panel(title || "", '<div class="status">正在加载…</div>');
  }

  function stateLabel(status) {
    const labels = {
      identifying_customer: "识别中",
      sdk_unavailable: "未识别到客户",
      context_missing: "未识别到客户",
      loading_workbench: "加载中",
      ready: "",
      degraded_ready: "部分加载",
      error: "加载失败",
    };
    return labels[status] || "加载失败";
  }

  function setWorkbenchState(status, detail) {
    state.status = status;
    state.lastError = detail || null;
    writeDebug("state transition", { status, detail: detail || {} });
    if (status !== WORKBENCH_STATES.ready && status !== WORKBENCH_STATES.degraded_ready) {
      renderTopState(status, detail || {});
    }
  }

  function renderTopState(status, detail) {
    const isLoading = status === WORKBENCH_STATES.identifying_customer || status === WORKBENCH_STATES.loading_workbench;
    document.getElementById("customer-name").textContent = stateLabel(status);
    document.getElementById("customer-mobile").textContent = "";
    document.getElementById("customer-external-userid").textContent = state.external_userid ? "外部联系人 ID " + state.external_userid : "";
    document.getElementById("workflow-title").textContent = "";
    const bindingState = document.getElementById("binding-state");
    bindingState.textContent = isLoading ? (status === WORKBENCH_STATES.identifying_customer ? "识别中" : "加载中...") : stateLabel(status);
    bindingState.classList.toggle("loading", isLoading);
    bindingState.classList.toggle("unbound", !isLoading);
    if (detail && detail.message) writeDebug("top state detail", detail);
  }

  function renderRetryPanel(title, message) {
    content.innerHTML = panel(
      title || "",
      '<div class="status error">' + escapeHtml(message || "加载失败，请稍后重试。") + "</div>" +
        '<div class="row-actions"><button class="btn primary" type="button" data-retry-boot>重试</button></div>'
    );
  }

  function panel(title, body) {
    const head = title ? '<div class="head"><h2>' + escapeHtml(title) + "</h2></div>" : "";
    return '<section class="panel">' + head + body + "</section>";
  }

  function empty(message) {
    return '<div class="empty">' + escapeHtml(message) + "</div>";
  }

  function renderTabs() {
    tabsNode.innerHTML = tabs
      .map(([key, label]) => {
        const active = key === state.activeTab ? " active" : "";
        return '<button class="tab' + active + '" type="button" data-tab="' + key + '">' + escapeHtml(label) + "</button>";
      })
      .join("");
  }

  function renderTop() {
    const workbench = state.workbench || {};
    const customer = workbench.customer || {};
    const workflow = workbench.workflow || {};
    const name = String(customer.display_name || "当前客户").trim();
    const mobile = String(customer.mobile || "").trim();
    const externalUserid = String(customer.external_userid || state.external_userid || "").trim();
    const isBound = Boolean(customer.is_bound);
    document.getElementById("customer-name").textContent = name;
    document.getElementById("customer-mobile").textContent = mobile ? "手机号 " + mobile : "";
    document.getElementById("customer-external-userid").textContent = externalUserid ? "外部联系人 ID " + externalUserid : "";
    document.getElementById("workflow-title").textContent = String(workflow.title || "").trim();
    const bindingState = document.getElementById("binding-state");
    bindingState.textContent = isBound ? "手机号已绑定" : "手机号未绑定";
    bindingState.classList.remove("loading");
    bindingState.classList.toggle("unbound", !isBound);
  }

  function updateProfileField(key, value) {
    const profile = state.workbench.profile || {};
    profile[key] = value;
    state.workbench.profile = profile;
  }

  function saveProfileSoon() {
    window.clearTimeout(state.profileSaveTimer);
    state.profileSaveTimer = window.setTimeout(saveProfile, 520);
  }

  async function saveProfile() {
    if (!state.workbench || !state.external_userid) return;
    const profile = state.workbench.profile || {};
    try {
      await requestJson(endpoint("profileUrl"), {
        method: "PUT",
        body: JSON.stringify({
          external_userid: state.external_userid,
          source: profile.source || "",
          industry: profile.industry || "",
          industry_description: profile.industry_description || "",
          needs_blockers_followup: profile.needs_blockers_followup || "",
          updated_by: state.bind_by_userid || state.owner_userid || "",
        }),
      });
      showToast("已保存");
    } catch (error) {
      showToast(error.message || "保存失败", "error");
    }
  }

  function textAreaField(key, label, value) {
    return (
      '<div class="field">' +
      '<div class="field-title">' + escapeHtml(label) + "</div>" +
      '<textarea class="textarea" data-profile-field="' + key + '">' + escapeHtml(value || "") + "</textarea>" +
      "</div>"
    );
  }

  function renderProfile() {
    const profile = (state.workbench && state.workbench.profile) || {};
    content.innerHTML = panel(
      "核心画像",
      '<div class="editor">' +
        textAreaField("source", "用户来源", profile.source || "") +
        textAreaField("industry", "行业信息", profile.industry || "") +
        textAreaField("industry_description", "行业具体描述", profile.industry_description || "") +
        textAreaField("needs_blockers_followup", "需求、卡点、跟进状态", profile.needs_blockers_followup || "") +
      "</div>"
    );
  }

  function renderQuestionnaires() {
    const rows = state.data.questionnaires || [];
    if (!rows.length) {
      content.innerHTML = panel("问卷", empty("暂无问卷记录"));
      return;
    }
    content.innerHTML = panel(
      "问卷",
      rows
        .map((item, index) => {
          const answers = item.answers || [];
          const count = String(item.answer_count || answers.length || 0) + "/" + String(item.total_count || item.answer_count || answers.length || 0) + " 题";
          return (
            '<article class="card" data-questionnaire-card="' + index + '">' +
            '<div class="card-title"><div><h3>' + escapeHtml(item.title || "未命名问卷") + "</h3>" +
            '<div class="mini">' + escapeHtml([item.submitted_at || "", count].filter(Boolean).join(" · ")) + "</div></div></div>" +
            '<div class="row-actions"><button class="btn primary" type="button" data-toggle-questionnaire="' + index + '">查看答案</button></div>' +
            '<div class="questions">' +
            answers.map((answer) => '<div class="question"><b>' + escapeHtml(answer.question || "未命名问题") + "</b><em>" + escapeHtml(answer.answer || "未填写") + "</em></div>").join("") +
            "</div></article>"
          );
        })
        .join("")
    );
  }

  function renderProducts() {
    const rows = state.data.products || [];
    if (!rows.length) {
      content.innerHTML = panel("商品", empty("暂无商品记录"));
      return;
    }
    content.innerHTML = panel(
      "商品",
      rows
        .map((item, index) => {
          return (
            '<article class="card"><div class="card-title"><h3>' + escapeHtml(item.title || "未命名商品") + "</h3>" +
            '<div class="price">' + escapeHtml(item.price_label || "") + "</div></div>" +
            '<div class="row-actions"><button class="btn primary" type="button" data-product-send="' + escapeHtml(index) + '">发送商品</button></div></article>'
          );
        })
        .join("")
    );
  }

  function renderOrders() {
    const rows = state.data.orders || [];
    if (!rows.length) {
      content.innerHTML = panel("订单", empty("暂无订单记录"));
      return;
    }
    content.innerHTML = panel(
      "订单",
      rows
        .map((item) => (
          '<article class="card"><div class="card-title"><div><h3>' + escapeHtml(item.title || "未命名商品") + "</h3>" +
          '<div class="mini">' + escapeHtml(item.id || "") + '</div></div><div class="price">' + escapeHtml(item.amount_label || "") + "</div></div>" +
          '<div class="kv"><span>状态</span><strong>' + escapeHtml(item.status_label || "") + "</strong>" +
          '<span>时间</span><strong>' + escapeHtml(item.paid_at || "") + "</strong></div>" +
          '<div class="row-actions"><button class="btn primary" type="button" data-order-detail-url="' + escapeHtml(item.detail_url || "") + '">查看详情</button></div></article>'
        ))
        .join("")
    );
  }

  function renderMaterials() {
    const rows = state.data.materials[state.materialType] || [];
    const controls = '<div class="seg">' + materialTabs.map(([key, label]) => '<button type="button" class="' + (key === state.materialType ? "active" : "") + '" data-material-type="' + key + '">' + escapeHtml(label) + "</button>").join("") + "</div>";
    if (!rows.length) {
      content.innerHTML = panel("素材", controls + empty("暂无素材"));
      return;
    }
    content.innerHTML = panel(
      "素材",
      controls +
        rows
          .map((item) => {
            const type = item.type === "mini" ? "mini" : item.type === "pdf" ? "pdf" : "image";
            const thumbClass = type === "mini" ? "mini-program" : type === "pdf" ? "pdf" : "image-thumb";
            const materialClass = type === "mini" ? "material--mini" : type === "pdf" ? "material--pdf" : "material--image";
            const fallbackLabel = item.thumbnail_label || (type === "mini" ? "小" : type === "pdf" ? "PDF" : "图");
            const thumb = item.thumbnail_url
              ? '<div class="material-thumb thumb image-thumb"><img src="' + escapeHtml(item.thumbnail_url) + '" alt="" data-material-thumb-img data-fallback-label="' + escapeHtml(fallbackLabel) + '"></div>'
              : '<div class="material-thumb thumb ' + thumbClass + '">' + escapeHtml(fallbackLabel) + "</div>";
            return (
              '<article class="card material ' + materialClass + '">' + thumb +
              '<div class="material-main"><h3 class="material-title">' + escapeHtml(item.title || "未命名素材") + '</h3><div class="material-tags tags">' +
              (item.tags || []).map((tag) => '<span class="tag">' + escapeHtml(tag) + "</span>").join("") +
              '</div></div><button class="btn primary material-send" type="button" data-material-send="' + escapeHtml(item.id || "") + '">发送</button></article>'
            );
          })
          .join("")
    );
  }

  function messageTitle(item) {
    const customer = ((state.workbench || {}).customer || {}).display_name || "客户";
    if (item.scene === "group") {
      return (item.scene_label || "群聊") + " · 客户" + customer;
    }
    return "客户与 " + (item.staff_name || item.staff_userid || "客服") + " 私聊";
  }

  function renderOtherStaffMessages() {
    const rows = state.data.other_staff_messages || [];
    if (!rows.length) {
      content.innerHTML = panel("其他客服的聊天记录", empty("暂无其他客服聊天记录"));
      return;
    }
    content.innerHTML = panel(
      "其他客服的聊天记录",
      '<div class="timeline">' +
        rows
          .map((item) => (
            '<article class="msg"><div class="msg-meta"><span>' + escapeHtml(item.send_time || "") + "</span><span>" + escapeHtml(item.scene_label || "") + "</span></div>" +
            '<div class="msg-title">' + escapeHtml(messageTitle(item)) + "</div>" +
            (item.type === "image"
              ? '<div class="imgmsg"><div class="imgph">图</div><div class="txt">' + escapeHtml(item.content || "发送了图片") + "</div></div>"
              : '<div class="txt">' + escapeHtml(item.sender_label || item.staff_name || "") + "：" + escapeHtml(item.content || "") + "</div>") +
            "</article>"
          ))
          .join("") +
      "</div>"
    );
  }

  async function loadWorkbench() {
    setWorkbenchState(WORKBENCH_STATES.loading_workbench, { external_userid: state.external_userid });
    const payload = await requestJson(
      queryUrl(endpoint("workbenchUrl"), {
        external_userid: state.external_userid,
        owner_userid: state.owner_userid,
      })
    );
    writeDebug("workbench response", payload);
    state.workbench = payload;
    const customer = payload.customer || {};
    state.external_userid = customer.external_userid || state.external_userid;
    state.owner_userid = customer.owner_userid || state.owner_userid;
    if (!state.bind_by_userid) state.bind_by_userid = state.owner_userid;
    renderTop();
    renderTabs();
    renderActiveTab();
    setWorkbenchState(payload.diagnostics && payload.diagnostics.context_source_status === "error" ? WORKBENCH_STATES.degraded_ready : WORKBENCH_STATES.ready, payload.diagnostics || {});
  }

  async function loadTabData(tab) {
    if (tab === "profile" || state.loaded[tab]) return;
    if (tab === "questionnaires") {
      const payload = await requestJson(queryUrl(endpoint("questionnairesUrl"), { external_userid: state.external_userid }));
      state.data.questionnaires = payload.questionnaires || [];
    } else if (tab === "products") {
      const payload = await requestJson(queryUrl(endpoint("productsUrl"), customerContextQuery()));
      writeDebug("products response", productContextDiagnostics(payload));
      state.data.products = payload.products || [];
    } else if (tab === "orders") {
      const payload = await requestJson(queryUrl(endpoint("ordersUrl"), customerContextQuery()));
      if (payload.customer) {
        state.workbench.customer = Object.assign({}, state.workbench.customer || {}, payload.customer);
        renderTop();
      }
      writeDebug("orders response", payload.diagnostics || {});
      state.data.orders = payload.orders || [];
    } else if (tab === "materials") {
      await loadMaterials(state.materialType);
    } else if (tab === "other_staff_messages") {
      const payload = await requestJson(
        queryUrl(endpoint("otherStaffMessagesUrl"), {
          external_userid: state.external_userid,
          current_userid: state.bind_by_userid || state.owner_userid,
          limit: 20,
        })
      );
      state.data.other_staff_messages = (payload.messages || [])
        .filter((item) => item && (item.type === "text" || item.type === "image"))
        .slice(-20);
    }
    state.loaded[tab] = true;
  }

  async function loadMaterials(type) {
    if (state.data.materials[type]) return;
    const payload = await requestJson(queryUrl(endpoint("materialsUrl"), { type, limit: 50 }));
    state.data.materials[type] = payload.materials || [];
  }

  function renderActiveTab() {
    if (state.activeTab === "profile") renderProfile();
    if (state.activeTab === "questionnaires") renderQuestionnaires();
    if (state.activeTab === "products") renderProducts();
    if (state.activeTab === "orders") renderOrders();
    if (state.activeTab === "materials") renderMaterials();
    if (state.activeTab === "other_staff_messages") renderOtherStaffMessages();
  }

  async function switchTab(tab) {
    state.activeTab = tab;
    renderTabs();
    setPanelLoading(tabs.find((item) => item[0] === tab)?.[1] || "");
    try {
      await loadTabData(tab);
      renderActiveTab();
    } catch (error) {
      content.innerHTML = panel(tabs.find((item) => item[0] === tab)?.[1] || "", '<div class="status error">' + escapeHtml(error.message || "加载失败") + "</div>");
    }
  }

  async function sendMaterial(materialId) {
    try {
      const payload = await requestJson(endpoint("materialSendUrl"), {
        method: "POST",
        body: JSON.stringify({
          external_userid: state.external_userid,
          owner_userid: state.owner_userid,
          type: state.materialType,
          material_id: materialId,
          operator: state.bind_by_userid || state.owner_userid || "",
          delivery_mode: state.materialType === "image" ? "chat_toolbar" : "dispatch",
        }),
      });
      if (state.materialType === "image") {
        if (!payload.media_id) throw new Error("图片素材未取得 media_id");
        await sendImageToCurrentChat(payload.media_id);
        showToast("已发送到当前会话");
        return;
      }
      showToast("已发送");
    } catch (error) {
      showToast(error.message || "发送失败", "error");
    }
  }

  async function sendProduct(productIndex) {
    const item = (state.data.products || [])[Number(productIndex)] || {};
    const link = absoluteUrl(item.product_url || (item.id ? "/p/" + item.id : ""));
    if (!link) {
      showToast("暂无商品链接", "error");
      return;
    }
    try {
      await sendLinkToCurrentChat({
        title: item.title || "未命名商品",
        url: link,
        imageUrl: absoluteUrl(PRODUCT_CARD_IMAGE_PATH),
      });
      showToast("已发送商品");
    } catch (error) {
      showToast(error.message || "发送失败", "error");
    }
  }

  function assertWeComSendOk(res) {
    const errMsg = String((res || {}).err_msg || "");
    if (!errMsg || errMsg.indexOf(":ok") >= 0) return;
    throw new Error(String((res || {}).errmsg || errMsg || "发送失败"));
  }

  async function sendLinkToCurrentChat(payload) {
    const sdkReady = await initWeComSdk();
    if (!sdkReady.ok || !window.wx || typeof window.wx.invoke !== "function") {
      throw new Error("请在企微侧边栏内发送");
    }
    const res = await invokeWeCom("sendChatMessage", {
      msgtype: "news",
      news: {
        link: String(payload.url || ""),
        title: String(payload.title || "未命名商品"),
        desc: "",
        imgUrl: String(payload.imageUrl || ""),
      },
    }, SDK_TIMEOUT_MS);
    writeDebug("sendChatMessage news result", res || {});
    assertWeComSendOk(res);
    return res;
  }

  async function sendImageToCurrentChat(mediaId) {
    const sdkReady = await initWeComSdk();
    if (!sdkReady.ok || !window.wx || typeof window.wx.invoke !== "function") {
      throw new Error("请在企微侧边栏内发送");
    }
    const res = await invokeWeCom("sendChatMessage", {
      msgtype: "image",
      image: { mediaid: mediaId },
    }, SDK_TIMEOUT_MS);
    writeDebug("sendChatMessage result", res || {});
    assertWeComSendOk(res);
    return res;
  }

  function openMobileModal() {
    mobileInput.value = ((state.workbench || {}).customer || {}).mobile || "";
    mobileStatus.textContent = "";
    mobileStatus.className = "status";
    mobileModal.classList.remove("hidden");
    mobileInput.focus();
  }

  function closeMobileModal() {
    mobileModal.classList.add("hidden");
  }

  async function saveMobile() {
    confirmMobileButton.disabled = true;
    mobileStatus.textContent = "正在保存…";
    try {
      const customer = (state.workbench || {}).customer || {};
      const payload = await requestJson(endpoint("bindMobileUrl"), {
        method: "POST",
        body: JSON.stringify({
          external_userid: state.external_userid,
          owner_userid: state.owner_userid,
          bind_by_userid: state.bind_by_userid || state.owner_userid,
          mobile: mobileInput.value,
          force_rebind: Boolean(customer.is_bound),
        }),
      });
      const binding = payload.binding || payload;
      state.workbench.customer.mobile = binding.mobile || mobileInput.value;
      state.workbench.customer.is_bound = true;
      renderTop();
      closeMobileModal();
      showToast("手机号已保存");
    } catch (error) {
      mobileStatus.textContent = error.message || "保存失败";
      mobileStatus.className = "status error";
      showToast(error.message || "保存失败", "error");
    } finally {
      confirmMobileButton.disabled = false;
    }
  }

  async function resolveContextFromQuery() {
    state.external_userid = getQueryValue("external_userid").trim();
    state.owner_userid = getQueryValue("owner_userid").trim();
    state.bind_by_userid = getQueryValue("bind_by_userid").trim() || state.owner_userid;
    writeDebug("query context", {
      external_userid: state.external_userid,
      owner_userid: state.owner_userid,
      bind_by_userid: state.bind_by_userid,
      query: Object.fromEntries(new URLSearchParams(window.location.search).entries()),
    });
    return Boolean(state.external_userid);
  }

  async function initWeComSdk() {
    const wxSdk = getWeComSdk();
    if (!wxSdk) return { ok: false, status: WORKBENCH_STATES.sdk_unavailable, reason: "wx_missing" };
    let configPayload;
    try {
      const currentUrl = window.location.href.split("#")[0];
      configPayload = await requestJson(endpoint("jssdkConfigUrl") + "?url=" + encodeURIComponent(currentUrl), { timeoutMs: SDK_TIMEOUT_MS });
      writeDebug("jssdk config response", { has_config: Boolean(configPayload && configPayload.config), has_agent_config: Boolean(configPayload && configPayload.agent_config) });
    } catch (error) {
      writeDebug("jssdk config error", { message: error.message || String(error) });
      return { ok: false, status: WORKBENCH_STATES.sdk_unavailable, reason: "jssdk_config_failed", error: error.message || String(error) };
    }
    return await new Promise((resolve) => {
      let resolved = false;
      const timer = window.setTimeout(() => finish(false, "sdk_timeout"), SDK_TIMEOUT_MS);
      const finish = (ok, reason) => {
        if (!resolved) {
          resolved = true;
          window.clearTimeout(timer);
          resolve({ ok, status: ok ? WORKBENCH_STATES.identifying_customer : WORKBENCH_STATES.sdk_unavailable, reason: reason || "" });
        }
      };
      wxSdk.config({
        beta: true,
        debug: false,
        appId: configPayload.corp_id,
        timestamp: Number(configPayload.config.timestamp),
        nonceStr: configPayload.config.nonceStr,
        signature: configPayload.config.signature,
        jsApiList: ["getContext", "sendChatMessage"],
      });
      wxSdk.ready(function () {
        writeDebug("wx.config success", { url: configPayload.config.url });
        if (typeof wxSdk.agentConfig !== "function") {
          finish(false, "agentConfig_missing");
          return;
        }
        wxSdk.agentConfig({
          corpid: configPayload.corp_id,
          agentid: String(configPayload.agent_id),
          timestamp: Number(configPayload.agent_config.timestamp),
          nonceStr: configPayload.agent_config.nonceStr,
          signature: configPayload.agent_config.signature,
          jsApiList: ["getContext", "getCurExternalContact", "sendChatMessage"],
          success: function (res) {
            writeDebug("wx.agentConfig success", res || {});
            finish(true, "");
          },
          fail: function (err) {
            writeDebug("wx.agentConfig fail", err || {});
            finish(false, "agentConfig_failed");
          },
        });
      });
      wxSdk.error(function (err) {
        writeDebug("wx.config fail", err || {});
        finish(false, "wx_config_failed");
      });
    });
  }

  function invokeWeCom(method, payload, timeoutMs) {
    return new Promise((resolve, reject) => {
      if (!window.wx || typeof window.wx.invoke !== "function") {
        reject(new Error("wx.invoke unavailable"));
        return;
      }
      let resolved = false;
      const timer = window.setTimeout(() => {
        if (resolved) return;
        resolved = true;
        const error = new Error(method + " timeout");
        error.stage = method;
        reject(error);
      }, timeoutMs || SDK_TIMEOUT_MS);
      window.wx.invoke(method, payload || {}, function (res) {
        if (resolved) return;
        resolved = true;
        window.clearTimeout(timer);
        resolve(res || {});
      });
    });
  }

  async function resolveContextFromWeCom() {
    const sdkReady = await initWeComSdk();
    if (!sdkReady.ok || !window.wx || typeof window.wx.invoke !== "function") return sdkReady;
    invokeWeCom("getContext", {}, SDK_TIMEOUT_MS)
      .then((res) => writeDebug("getContext result", res || {}))
      .catch((error) => writeDebug("getContext error", { message: error.message || String(error) }));
    try {
      const res = await invokeWeCom("getCurExternalContact", {}, SDK_TIMEOUT_MS);
      writeDebug("getCurExternalContact result", res || {});
      const externalUserid = String((res || {}).userId || (res || {}).external_userid || "").trim();
      if (!externalUserid) {
        return { ok: false, status: WORKBENCH_STATES.context_missing, reason: "external_userid_missing" };
      }
      state.external_userid = externalUserid;
      state.owner_userid = String((res || {}).owner_userid || state.owner_userid || "").trim();
      state.bind_by_userid = String((res || {}).operator_userid || state.bind_by_userid || state.owner_userid || "").trim();
      writeDebug("getCurExternalContact success", {
        external_userid: state.external_userid,
        owner_userid: state.owner_userid,
        bind_by_userid: state.bind_by_userid,
      });
      return { ok: true, status: WORKBENCH_STATES.identifying_customer };
    } catch (error) {
      writeDebug("getCurExternalContact error", { message: error.message || String(error), stage: error.stage || "" });
      return { ok: false, status: WORKBENCH_STATES.context_missing, reason: error.stage || "getCurExternalContact_failed", error: error.message || String(error) };
    }
  }

  async function boot() {
    renderTabs();
    setWorkbenchState(WORKBENCH_STATES.identifying_customer);
    setPanelLoading("");
    try {
      const hasQuery = await resolveContextFromQuery();
      const contextResult = hasQuery ? { ok: true, status: WORKBENCH_STATES.identifying_customer, source: "query" } : await resolveContextFromWeCom();
      writeDebug("identity result", contextResult);
      if (!contextResult.ok) {
        setWorkbenchState(contextResult.status || WORKBENCH_STATES.context_missing, contextResult);
        renderRetryPanel("", contextResult.status === WORKBENCH_STATES.sdk_unavailable ? "企微 SDK 暂不可用，请确认从企微侧边栏打开，或带 external_userid 参数重试。" : "未识别到客户，请从企微客户侧边栏重新打开。");
        return;
      }
      await loadWorkbench();
    } catch (error) {
      writeDebug("boot error", { message: error.message || String(error), stage: error.stage || "" });
      setWorkbenchState(WORKBENCH_STATES.error, { message: error.message || String(error), stage: error.stage || "" });
      renderRetryPanel("", error.message || "加载失败，请稍后重试。");
    }
  }

  tabsNode.addEventListener("click", (event) => {
    const button = event.target.closest("[data-tab]");
    if (!button) return;
    switchTab(button.dataset.tab);
  });

  content.addEventListener("change", (event) => {
    const field = event.target.dataset.profileField;
    if (!field || event.target.tagName === "TEXTAREA") return;
    updateProfileField(field, event.target.value);
    saveProfile();
  });

  content.addEventListener("input", (event) => {
    const field = event.target.dataset.profileField;
    if (!field || event.target.tagName !== "TEXTAREA") return;
    updateProfileField(field, event.target.value);
    saveProfileSoon();
  });

  content.addEventListener("blur", (event) => {
    const field = event.target.dataset.profileField;
    if (!field || event.target.tagName !== "TEXTAREA") return;
    updateProfileField(field, event.target.value);
    saveProfile();
  }, true);

  content.addEventListener("click", async (event) => {
    const retryButton = event.target.closest("[data-retry-boot]");
    if (retryButton) {
      retryButton.disabled = true;
      boot();
      return;
    }
    const qButton = event.target.closest("[data-toggle-questionnaire]");
    if (qButton) {
      const card = content.querySelector('[data-questionnaire-card="' + qButton.dataset.toggleQuestionnaire + '"]');
      if (card) card.classList.toggle("open");
      return;
    }
    const materialTypeButton = event.target.closest("[data-material-type]");
    if (materialTypeButton) {
      state.materialType = materialTypeButton.dataset.materialType;
      setPanelLoading("素材");
      try {
        await loadMaterials(state.materialType);
        renderMaterials();
      } catch (error) {
        content.innerHTML = panel("素材", '<div class="status error">' + escapeHtml(error.message || "加载失败") + "</div>");
      }
      return;
    }
    const materialSendButton = event.target.closest("[data-material-send]");
    if (materialSendButton) {
      materialSendButton.disabled = true;
      try {
        await sendMaterial(materialSendButton.dataset.materialSend);
      } finally {
        materialSendButton.disabled = false;
      }
      return;
    }
    const productSendButton = event.target.closest("[data-product-send]");
    if (productSendButton) {
      productSendButton.disabled = true;
      try {
        await sendProduct(productSendButton.dataset.productSend);
      } finally {
        productSendButton.disabled = false;
      }
      return;
    }
    const orderDetailButton = event.target.closest("[data-order-detail-url]");
    if (orderDetailButton) {
      const link = absoluteUrl(orderDetailButton.dataset.orderDetailUrl);
      if (!link) {
        showToast("暂无订单详情链接", "error");
        return;
      }
      window.open(link, "_blank", "noopener");
      showToast("已打开订单详情");
      return;
    }
  });

  content.addEventListener("error", (event) => {
    const image = event.target.closest ? event.target.closest("[data-material-thumb-img]") : null;
    if (!image) return;
    const parent = image.parentElement;
    if (!parent) return;
    parent.textContent = image.dataset.fallbackLabel || "图";
    parent.classList.remove("image-thumb");
  }, true);

  document.getElementById("change-mobile-button").addEventListener("click", openMobileModal);
  document.getElementById("close-mobile-modal").addEventListener("click", closeMobileModal);
  document.getElementById("cancel-mobile-button").addEventListener("click", closeMobileModal);
  confirmMobileButton.addEventListener("click", saveMobile);

  boot();
})();
