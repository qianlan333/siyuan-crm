import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

const source = await readFile(
  new URL("../../aicrm_next/frontend_compat/static/sidebar_workbench/sidebar_workbench.js", import.meta.url),
  "utf8",
);

const bootMarker = "  boot();\n})();";
assert.equal(source.includes(bootMarker), true, "workbench boot marker changed; update the test harness");

function createNode() {
  return {
    className: "",
    dataset: {},
    disabled: false,
    innerHTML: "",
    parentElement: null,
    textContent: "",
    value: "",
    addEventListener() {},
    appendChild() {},
    closest() {
      return null;
    },
    querySelector() {
      return null;
    },
    classList: {
      add() {},
      remove() {},
      toggle() {},
    },
  };
}

function jsonResponse(payload, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    async text() {
      return JSON.stringify(payload);
    },
  };
}

function loadHarness(fetchImpl) {
  const nodes = new Map();
  const node = (id) => {
    if (!nodes.has(id)) nodes.set(id, createNode());
    return nodes.get(id);
  };
  node("sidebar-workbench-root").dataset = {
    debugEnabled: "false",
    jssdkConfigUrl: "/api/sidebar/jssdk-config",
    materialsUrl: "/api/sidebar/v2/materials",
    questionnairesUrl: "/api/sidebar/v2/questionnaires",
    ordersUrl: "/api/sidebar/v2/orders",
    workbenchUrl: "/api/sidebar/v2/workbench",
  };

  const document = {
    createElement() {
      return createNode();
    },
    getElementById(id) {
      return node(id);
    },
  };
  const nativeSetTimeout = globalThis.setTimeout;
  let nowMs = 1_000_000;
  class HarnessDate extends Date {
    static now() {
      return nowMs;
    }
  }
  const window = {
    clearTimeout: globalThis.clearTimeout,
    location: {
      href: "https://crm.example.test/sidebar/bind-mobile",
      origin: "https://crm.example.test",
      pathname: "/sidebar/bind-mobile",
      search: "",
    },
    open() {},
    setTimeout(callback, delay, ...args) {
      return nativeSetTimeout(callback, delay === 420 ? 0 : delay, ...args);
    },
  };
  const instrumented = source.replace(
    bootMarker,
    "  globalThis.__sidebarTestApi = { jssdkConfigUrl, loadWorkbench, requestJssdkConfig, requestPanelJson, switchTab, switchMaterialType: typeof switchMaterialType === 'function' ? switchMaterialType : null, state };\n})();",
  );
  const context = {
    AbortController,
    Date: HarnessDate,
    URL,
    URLSearchParams,
    console,
    document,
    encodeURIComponent,
    fetch: fetchImpl,
    window,
  };
  vm.runInNewContext(instrumented, context);
  return {
    api: context.__sidebarTestApi,
    nodes,
    advanceTime(ms) {
      nowMs += ms;
    },
  };
}

test("same-URL JSSDK config calls share one request until the token-safe cache expiry", async () => {
  let fetchCalls = 0;
  const { api, advanceTime } = loadHarness(async () => {
    fetchCalls += 1;
    return jsonResponse({
      ok: true,
      corp_id: "corp",
      config: { signature: `sig-${fetchCalls}` },
      sidebar_owner_context: { expires_in: 60 },
    });
  });

  const [first, second] = await Promise.all([
    api.requestJssdkConfig(),
    api.requestJssdkConfig(),
  ]);
  const resolved = await api.requestJssdkConfig();

  assert.equal(fetchCalls, 1);
  assert.equal(JSON.stringify(first), JSON.stringify(second));
  assert.equal(JSON.stringify(first), JSON.stringify(resolved));
  assert.equal(api.state.jssdkConfigRequests.size, 0);
  assert.equal(api.state.jssdkConfigCache.size, 1);

  advanceTime(30_001);
  const refreshed = await api.requestJssdkConfig();
  assert.equal(fetchCalls, 2);
  assert.equal(refreshed.config.signature, "sig-2");
});

test("JSSDK config without a valid owner expiry is single-flight only", async () => {
  let fetchCalls = 0;
  const { api } = loadHarness(async () => {
    fetchCalls += 1;
    return jsonResponse({ ok: true, corp_id: "corp", config: { signature: `sig-${fetchCalls}` } });
  });

  await Promise.all([api.requestJssdkConfig(), api.requestJssdkConfig()]);
  assert.equal(fetchCalls, 1);
  assert.equal(api.state.jssdkConfigCache.size, 0);

  await api.requestJssdkConfig();
  assert.equal(fetchCalls, 2);
});

test("failed JSSDK config calls clear pending state and can be retried", async () => {
  let fetchCalls = 0;
  const { api } = loadHarness(async () => {
    fetchCalls += 1;
    if (fetchCalls <= 2) return jsonResponse({ ok: false, error: "temporary config failure" }, 503);
    return jsonResponse({
      ok: true,
      corp_id: "corp",
      config: { signature: "retry-sig" },
      sidebar_owner_context: { expires_in: 60 },
    });
  });

  await assert.rejects(api.requestJssdkConfig(), /temporary config failure/);
  assert.equal(fetchCalls, 2, "the existing one-retry JSSDK network policy remains intact");
  assert.equal(api.state.jssdkConfigRequests.size, 0);
  assert.equal(api.state.jssdkConfigCache.size, 0);

  const retried = await api.requestJssdkConfig();
  assert.equal(fetchCalls, 3);
  assert.equal(retried.config.signature, "retry-sig");
});

test("JSSDK config cache separates URLs with and without external_userid", async () => {
  const fetchedUrls = [];
  const { api } = loadHarness(async (url) => {
    fetchedUrls.push(String(url));
    return jsonResponse({ ok: true, request_url: String(url), sidebar_owner_context: { expires_in: 60 } });
  });

  const withoutCustomer = api.jssdkConfigUrl();
  await api.requestJssdkConfig();
  api.state.external_userid = "wm_jssdk_context";
  const withCustomer = api.jssdkConfigUrl();
  await api.requestJssdkConfig();

  assert.notEqual(withoutCustomer, withCustomer);
  assert.equal(new URL(withoutCustomer).searchParams.has("external_userid"), false);
  assert.equal(new URL(withCustomer).searchParams.get("external_userid"), "wm_jssdk_context");
  assert.equal(fetchedUrls.length, 2);
  assert.equal(api.state.jssdkConfigCache.size, 2);
});

test("non-profile tabs cannot request panels before the workbench is ready", async () => {
  let releaseWorkbench;
  let orderCalls = 0;
  const pendingWorkbench = new Promise((resolve) => {
    releaseWorkbench = resolve;
  });
  const { api } = loadHarness(async (url) => {
    if (String(url).includes("/workbench")) return pendingWorkbench;
    if (String(url).includes("/orders")) {
      orderCalls += 1;
      return jsonResponse({ ok: true, orders: [] });
    }
    throw new Error(`unexpected URL: ${url}`);
  });
  api.state.external_userid = "wm_ready_gate";
  api.state.owner_userid = "sales_01";

  const loading = api.loadWorkbench();
  await api.switchTab("orders");
  assert.equal(orderCalls, 0);
  assert.equal(api.state.activeTab, "profile");

  releaseWorkbench(jsonResponse({
    ok: true,
    customer: { external_userid: "wm_ready_gate", owner_userid: "sales_01" },
    profile: {},
    workflow: {},
    diagnostics: {},
  }));
  await loading;
  await api.switchTab("orders");

  assert.equal(api.state.status, "ready");
  assert.equal(orderCalls, 1);
  assert.equal(api.state.activeTab, "orders");
});

test("a failed material subtype has a manual retry path", async () => {
  let materialCalls = 0;
  const { api, nodes } = loadHarness(async (url) => {
    if (!String(url).includes("/materials")) throw new Error(`unexpected URL: ${url}`);
    materialCalls += 1;
    if (materialCalls === 1) return jsonResponse({ ok: false, error: "mini failed" }, 503);
    return jsonResponse({ ok: true, materials: [{ id: "mini-1", type: "mini", title: "Mini Ready" }] });
  });
  api.state.status = "ready";
  api.state.workbench = { customer: {}, profile: {}, workflow: {} };
  api.state.activeTab = "materials";

  await api.switchMaterialType("mini");
  assert.equal(materialCalls, 1);
  assert.equal(nodes.get("content").innerHTML.includes('data-retry-material-type="mini"'), true);

  await api.switchMaterialType("mini");
  assert.equal(materialCalls, 2);
  assert.equal(nodes.get("content").innerHTML.includes("Mini Ready"), true);
});

test("an old material subtype error cannot replace a newer subtype", async () => {
  let releaseImage;
  const pendingImage = new Promise((resolve) => {
    releaseImage = resolve;
  });
  const { api, nodes } = loadHarness(async (url) => {
    const type = new URL(String(url)).searchParams.get("type");
    if (type === "image") return pendingImage;
    if (type === "mini") return jsonResponse({ ok: true, materials: [{ id: "mini-2", type: "mini", title: "New Mini" }] });
    throw new Error(`unexpected material type: ${type}`);
  });
  api.state.status = "ready";
  api.state.workbench = { customer: {}, profile: {}, workflow: {} };
  api.state.activeTab = "materials";

  const oldType = api.switchMaterialType("image");
  await api.switchMaterialType("mini");
  const currentPanel = nodes.get("content").innerHTML;
  releaseImage(jsonResponse({ ok: false, error: "old image failed" }, 503));
  await oldType;

  assert.equal(api.state.materialType, "mini");
  assert.equal(nodes.get("content").innerHTML, currentPanel);
});

test("an old material subtype result cannot replace a later tab", async () => {
  let releasePdf;
  const pendingPdf = new Promise((resolve) => {
    releasePdf = resolve;
  });
  const { api, nodes } = loadHarness(async (url) => {
    if (String(url).includes("/materials")) return pendingPdf;
    if (String(url).includes("/orders")) return jsonResponse({ ok: true, orders: [] });
    throw new Error(`unexpected URL: ${url}`);
  });
  api.state.status = "ready";
  api.state.workbench = { customer: {}, profile: {}, workflow: {} };
  api.state.activeTab = "materials";

  const oldType = api.switchMaterialType("pdf");
  await api.switchTab("orders");
  const currentPanel = nodes.get("content").innerHTML;
  releasePdf(jsonResponse({ ok: true, materials: [{ id: "pdf-1", type: "pdf", title: "Old PDF" }] }));
  await oldType;

  assert.equal(api.state.activeTab, "orders");
  assert.equal(nodes.get("content").innerHTML, currentPanel);
});

test("concurrent requests for one customer panel share the production request", async () => {
  let fetchCalls = 0;
  const { api } = loadHarness(async () => {
    fetchCalls += 1;
    return jsonResponse({ ok: true, questionnaires: [{ id: "q-1" }] });
  });
  api.state.external_userid = "wm_single_flight";

  const url = "https://crm.example.test/api/sidebar/v2/questionnaires?external_userid=wm_single_flight";
  const [first, second] = await Promise.all([
    api.requestPanelJson("questionnaires", url),
    api.requestPanelJson("questionnaires", url),
  ]);

  assert.equal(fetchCalls, 1);
  assert.equal(JSON.stringify(first), JSON.stringify(second));
  assert.equal(api.state.panelRequests.size, 0);
});

test("a failed panel request is not replayed automatically and can be requested again", async () => {
  let fetchCalls = 0;
  const { api } = loadHarness(async () => {
    fetchCalls += 1;
    if (fetchCalls === 1) return jsonResponse({ ok: false, error: "temporary panel failure" }, 503);
    return jsonResponse({ ok: true, questionnaires: [{ id: "q-retry" }] });
  });
  api.state.external_userid = "wm_manual_retry";

  const url = "https://crm.example.test/api/sidebar/v2/questionnaires?external_userid=wm_manual_retry";
  await assert.rejects(api.requestPanelJson("questionnaires", url), /temporary panel failure/);
  assert.equal(fetchCalls, 1);
  assert.equal(api.state.panelRequests.size, 0);

  const retried = await api.requestPanelJson("questionnaires", url);
  assert.equal(fetchCalls, 2);
  assert.equal(retried.questionnaires[0].id, "q-retry");
});

test("an old tab failure cannot replace the currently active tab", async () => {
  let releaseQuestionnaires;
  let questionnaireCalls = 0;
  const pendingQuestionnaires = new Promise((resolve) => {
    releaseQuestionnaires = resolve;
  });
  const { api, nodes } = loadHarness(async (url) => {
    if (String(url).includes("/questionnaires")) {
      questionnaireCalls += 1;
      if (questionnaireCalls === 1) return pendingQuestionnaires;
      return jsonResponse({ ok: false, error: "old questionnaire failure" }, 503);
    }
    if (String(url).includes("/orders")) return jsonResponse({ ok: true, orders: [] });
    throw new Error(`unexpected URL: ${url}`);
  });
  api.state.external_userid = "wm_tab_race";
  api.state.owner_userid = "sales_01";
  api.state.status = "ready";
  api.state.workbench = { customer: {}, profile: {}, workflow: {} };

  const oldTab = api.switchTab("questionnaires");
  assert.equal(questionnaireCalls, 1);
  await api.switchTab("orders");
  const currentPanel = nodes.get("content").innerHTML;
  assert.equal(currentPanel.includes("订单"), true);

  releaseQuestionnaires(jsonResponse({ ok: false, error: "old questionnaire failure" }, 503));
  await oldTab;

  assert.equal(api.state.activeTab, "orders");
  assert.equal(nodes.get("content").innerHTML, currentPanel);
});
