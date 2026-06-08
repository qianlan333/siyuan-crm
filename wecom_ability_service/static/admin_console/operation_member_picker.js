(function (window, document) {
  "use strict";

  const apiUrl = "/api/admin/common/operation-members";
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));

  const state = {
    selected: null,
    confirmed: null,
    onSelect: null,
    loading: false,
    items: [],
    debounceTimer: null,
    errorMessage: "",
    escapeBound: false,
  };

  function memberLabel(member) {
    const userId = String((member || {}).user_id || "").trim();
    const displayName = String((member || {}).display_name || "").trim();
    if (!displayName || displayName === userId) return userId;
    return `${displayName} / ${userId}`;
  }

  function ensureStyles() {
    if (document.querySelector("[data-operation-member-picker-style]")) return;
    const style = document.createElement("style");
    style.setAttribute("data-operation-member-picker-style", "1");
    style.textContent = `
      .operation-member-picker {
        position: fixed;
        inset: 0;
        z-index: 10000;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 24px;
        background: rgba(15, 23, 42, 0.4);
      }
      .operation-member-picker[hidden] {
        display: none !important;
      }
      .operation-member-picker__panel {
        width: min(820px, 100%);
        max-height: min(720px, 92vh);
        display: grid;
        grid-template-rows: auto auto minmax(0, 1fr) auto;
        overflow: hidden;
        border-radius: 22px;
        background: var(--panel-strong, #fff);
        box-shadow: var(--shadow-lg, 0 18px 54px rgba(15, 23, 42, 0.18));
      }
      .operation-member-picker__head {
        padding: 22px 24px 14px;
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 16px;
        border-bottom: 1px solid var(--line, #e5e7eb);
      }
      .operation-member-picker__head h2 {
        margin: 0 0 4px;
        font-size: 20px;
      }
      .operation-member-picker__head p {
        margin: 0;
        color: var(--muted, #6b7280);
        font-size: 13px;
      }
      .operation-member-picker__close {
        white-space: nowrap;
      }
      .operation-member-picker__search {
        padding: 14px 24px;
        display: grid;
        grid-template-columns: 1fr 110px;
        gap: 10px;
        border-bottom: 1px solid var(--line, #e5e7eb);
        background: #fbfdff;
      }
      .operation-member-picker__search input {
        width: 100%;
        min-width: 0;
        min-height: 46px;
        border: 1px solid var(--line, #e5e7eb);
        border-radius: 12px;
        padding: 0 14px;
        font-size: 14px;
        background: var(--panel-strong, #fff);
      }
      .operation-member-picker__list {
        display: grid;
        align-content: start;
        gap: 10px;
        overflow: auto;
        padding: 14px 18px 18px;
        background: var(--panel-strong, #fff);
      }
      .operation-member-picker__row {
        min-height: 74px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
        padding: 13px 14px;
        border: 1px solid var(--line, #e5e7eb);
        border-radius: 14px;
        background: var(--panel-strong, #fff);
      }
      .operation-member-picker__row.is-selected {
        border-color: #93c5fd;
        background: #eff6ff;
      }
      .operation-member-picker__member-main {
        min-width: 0;
        display: flex;
        align-items: center;
        gap: 12px;
      }
      .operation-member-picker__avatar {
        width: 40px;
        height: 40px;
        flex: 0 0 auto;
        border-radius: 50%;
        object-fit: cover;
        border: 1px solid var(--line, #e5e7eb);
        background: #f9fafb;
      }
      .operation-member-picker__identity {
        display: grid;
        gap: 3px;
        min-width: 0;
      }
      .operation-member-picker__name {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        font-weight: 800;
        line-height: 1.35;
      }
      .operation-member-picker__user-id {
        margin-top: 3px;
        color: var(--muted, #6b7280);
        font-size: 13px;
        overflow-wrap: anywhere;
      }
      .operation-member-picker__select {
        white-space: nowrap;
      }
      .operation-member-picker__empty {
        padding: 44px 12px;
        border: 1px dashed var(--line, #e5e7eb);
        border-radius: 14px;
        color: var(--muted, #6b7280);
        text-align: center;
        font-size: 14px;
      }
      .operation-member-picker__actions {
        padding: 14px 24px;
        display: flex;
        justify-content: flex-end;
        gap: 10px;
        border-top: 1px solid var(--line, #e5e7eb);
        background: var(--panel-strong, #fff);
      }
      @media (max-width: 820px) {
        .operation-member-picker__search {
          grid-template-columns: 1fr;
        }
        .operation-member-picker__panel {
          max-height: 94vh;
        }
      }
    `;
    document.head.appendChild(style);
  }

  function ensureModal() {
    ensureStyles();
    let modal = document.querySelector("[data-operation-member-picker]");
    if (modal) return modal;
    modal = document.createElement("aside");
    modal.className = "operation-member-picker";
    modal.hidden = true;
    modal.setAttribute("data-operation-member-picker", "1");
    modal.setAttribute("aria-hidden", "true");
    modal.innerHTML = `
      <section class="operation-member-picker__panel" role="dialog" aria-modal="true" aria-labelledby="operation-member-picker-title">
        <div class="operation-member-picker__head">
          <div>
            <h2 id="operation-member-picker-title" data-operation-member-title>选择运营人员</h2>
            <p>搜索姓名或 userID，选择后回填到当前页面。</p>
          </div>
          <button class="operation-member-picker__close" type="button" data-operation-member-close>关闭</button>
        </div>
        <div class="operation-member-picker__search">
          <input type="search" data-operation-member-search placeholder="搜索：Anne / WangJiaYin / 嘉茵 / support1" autocomplete="off">
          <button class="admin-button admin-button--secondary" type="button" data-operation-member-clear>清空</button>
        </div>
        <div class="operation-member-picker__list" data-operation-member-list></div>
        <div class="operation-member-picker__actions">
          <button class="admin-button admin-button--secondary" type="button" data-operation-member-cancel>取消</button>
          <button class="admin-button admin-button--primary" type="button" data-operation-member-confirm>确认选择</button>
        </div>
      </section>
    `;
    document.body.appendChild(modal);
    modal.addEventListener("click", (event) => {
      if (event.target === modal || event.target.closest("[data-operation-member-cancel]") || event.target.closest("[data-operation-member-close]")) {
        close();
        return;
      }
      const pickButton = event.target.closest("[data-operation-member-row-select]");
      if (pickButton) {
        const row = pickButton.closest("[data-operation-member-row]");
        select(row ? row.dataset.userId || "" : "");
        return;
      }
      if (event.target.closest("[data-operation-member-clear]")) {
        const input = modal.querySelector("[data-operation-member-search]");
        if (input) input.value = "";
        clearTimeout(state.debounceTimer);
        load().then(() => {
          if (input) input.focus();
        });
      }
      if (event.target.closest("[data-operation-member-confirm]")) confirm();
    });
    const searchInput = modal.querySelector("[data-operation-member-search]");
    searchInput?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        clearTimeout(state.debounceTimer);
        load();
      }
    });
    searchInput?.addEventListener("input", () => {
      clearTimeout(state.debounceTimer);
      state.debounceTimer = setTimeout(() => load(), 260);
    });
    if (!state.escapeBound) {
      state.escapeBound = true;
      window.addEventListener("keydown", (event) => {
        const current = document.querySelector("[data-operation-member-picker]");
        if (event.key === "Escape" && current && !current.hidden) close();
      });
    }
    return modal;
  }

  function currentQuery() {
    const modal = ensureModal();
    return String(modal.querySelector("[data-operation-member-search]")?.value || "").trim();
  }

  function renderEmpty(text) {
    return `<div class="operation-member-picker__empty">${escapeHtml(text)}</div>`;
  }

  function render() {
    const modal = ensureModal();
    const list = modal.querySelector("[data-operation-member-list]");
    const confirmButton = modal.querySelector("[data-operation-member-confirm]");
    if (confirmButton) confirmButton.disabled = !state.selected;
    if (!list) return;
    if (state.loading) {
      list.innerHTML = renderEmpty("正在加载人员...");
      return;
    }
    if (state.errorMessage) {
      list.innerHTML = renderEmpty(state.errorMessage);
      return;
    }
    if (!state.items.length) {
      list.innerHTML = renderEmpty("没有找到匹配人员");
      return;
    }
    list.innerHTML = state.items.map((member) => {
      const userId = String(member.user_id || "");
      const displayName = String(member.display_name || userId || "");
      const avatarUrl = String(member.avatar_url || "").trim();
      const selected = state.selected && state.selected.user_id === userId;
      return `
        <div class="operation-member-picker__row${selected ? " is-selected" : ""}" data-operation-member-row data-user-id="${escapeHtml(userId)}">
          <div class="operation-member-picker__member-main">
            ${avatarUrl ? `<img class="operation-member-picker__avatar" src="${escapeHtml(avatarUrl)}" alt="">` : ""}
            <div class="operation-member-picker__identity">
              <div class="operation-member-picker__name">${escapeHtml(displayName)}</div>
              <div class="operation-member-picker__user-id">${escapeHtml(userId)}</div>
            </div>
          </div>
          <button class="admin-button ${selected ? "admin-button--primary" : "admin-button--secondary"} operation-member-picker__select" type="button" data-operation-member-row-select>${selected ? "已选" : "选择"}</button>
        </div>
      `;
    }).join("");
  }

  async function load() {
    state.loading = true;
    state.errorMessage = "";
    render();
    const url = new URL(apiUrl, window.location.origin);
    const q = currentQuery();
    if (q) url.searchParams.set("q", q);
    try {
      const response = await fetch(url.toString(), { headers: { Accept: "application/json" }, credentials: "same-origin" });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !Array.isArray(data.items)) throw new Error("load_failed");
      state.items = data.items;
      const selectedUserId = String((state.selected || {}).user_id || (state.confirmed || {}).user_id || "");
      const matchedSelected = state.items.find((item) => item.user_id === selectedUserId);
      if (matchedSelected) state.selected = matchedSelected;
    } catch (error) {
      state.items = [];
      state.errorMessage = "人员加载失败，请稍后重试";
    } finally {
      state.loading = false;
      render();
    }
  }

  function select(userId) {
    state.selected = state.items.find((item) => item.user_id === userId) || null;
    render();
  }

  function close() {
    clearTimeout(state.debounceTimer);
    const modal = ensureModal();
    modal.hidden = true;
    modal.setAttribute("aria-hidden", "true");
    state.selected = state.confirmed;
  }

  function confirm() {
    if (!state.selected) return;
    state.confirmed = state.selected;
    if (typeof state.onSelect === "function") state.onSelect(state.selected);
    const modal = ensureModal();
    modal.hidden = true;
    modal.setAttribute("aria-hidden", "true");
  }

  async function open(options = {}) {
    const modal = ensureModal();
    const value = String(options.value || options.selectedUserId || "").trim();
    state.confirmed = options.selectedMember || (value ? { user_id: value, display_name: options.selectedLabel || value, avatar_url: "" } : null);
    state.selected = state.confirmed;
    state.onSelect = options.onSelect || options.onConfirm || null;
    clearTimeout(state.debounceTimer);
    modal.querySelector("[data-operation-member-title]").textContent = options.title || "选择运营人员";
    const search = modal.querySelector("[data-operation-member-search]");
    if (search) search.value = "";
    modal.hidden = false;
    modal.setAttribute("aria-hidden", "false");
    await load();
    if (search) search.focus();
  }

  async function resolve(userId) {
    const normalized = String(userId || "").trim();
    if (!normalized) return null;
    const url = new URL(apiUrl, window.location.origin);
    url.searchParams.set("q", normalized);
    const response = await fetch(url.toString(), { headers: { Accept: "application/json" }, credentials: "same-origin" });
    const data = await response.json().catch(() => ({}));
    return (data.items || []).find((item) => item.user_id === normalized) || (data.items || [])[0] || null;
  }

  window.OperationMemberPicker = { open, resolve, memberLabel };
})(window, document);
