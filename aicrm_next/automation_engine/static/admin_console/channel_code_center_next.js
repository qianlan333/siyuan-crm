(function () {
  const root = document.querySelector('[data-channel-admission-page="channel-center"]');
  if (!root) return;

  const list = root.querySelector("[data-channel-list]");
  const search = root.querySelector("[data-channel-search]");
  const drawer = root.querySelector("[data-channel-drawer]");
  const drawerBody = root.querySelector("[data-channel-drawer-body]");
  const apiUrl = root.dataset.apiChannels || "/api/admin/channels?limit=300";
  if (!list) return;

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[char]));
  }

  function isLink(channel) {
    return channel.carrier_type === "link" || channel.channel_type === "wecom_customer_acquisition";
  }

  function statusLabel(value) {
    return {
      active: "启用",
      inactive: "停用",
      disabled: "禁用",
      paused: "暂停",
      archived: "归档",
    }[value] || value || "-";
  }

  function metric(name, value) {
    const node = root.querySelector(`[data-channel-metric="${name}"]`);
    if (node) node.textContent = String(value || 0);
  }

  function updateMetrics(channels) {
    metric("total", channels.length);
    metric("standalone", channels.filter((channel) => !channel.bound_program_id).length);
    metric("link", channels.filter(isLink).length);
    metric("entered", channels.reduce((total, channel) => total + Number(channel.channel_contact_count || 0), 0));
  }

  function channelLinkText(channel) {
    return channel.copy_text || channel.share_url || channel.final_url || channel.link_url || "";
  }

  function ensureFeedback() {
    let node = root.querySelector("[data-channel-center-feedback]");
    if (node) return node;
    node = document.createElement("div");
    node.className = "channel-save-feedback";
    node.setAttribute("role", "status");
    node.setAttribute("aria-live", "polite");
    node.setAttribute("data-channel-center-feedback", "");
    const metrics = root.querySelector("[data-channel-metrics]");
    root.insertBefore(node, metrics ? metrics.nextSibling : root.firstChild);
    return node;
  }

  function toast(message, tone = "success") {
    root.dataset.lastToast = message;
    if (window.AdminConsole && typeof window.AdminConsole.showToast === "function") {
      window.AdminConsole.showToast(message);
    }
    const feedback = ensureFeedback();
    feedback.textContent = String(message || "");
    feedback.hidden = false;
    feedback.classList.toggle("is-error", tone === "error");
  }

  function fallbackCopy(text) {
    const input = document.createElement("textarea");
    input.value = String(text || "");
    input.setAttribute("readonly", "readonly");
    input.style.position = "fixed";
    input.style.opacity = "0";
    document.body.appendChild(input);
    input.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (error) {
      ok = false;
    }
    input.remove();
    toast(ok ? "链接已复制" : "请手动复制链接", ok ? "success" : "error");
    return ok;
  }

  function copyText(text) {
    const value = String(text || "").trim();
    if (!value) {
      toast("没有可复制链接", "error");
      return Promise.resolve(false);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(value).then(
        () => {
          toast("链接已复制");
          return true;
        },
        () => fallbackCopy(value)
      );
    }
    return Promise.resolve(fallbackCopy(value));
  }

  function shareText(text) {
    const value = String(text || "").trim();
    if (!value) return copyText(value);
    if (navigator.share) {
      return navigator.share({ title: "企微获客助手链接", url: value }).catch(() => copyText(value));
    }
    return copyText(value);
  }

  function urlFromBase(base, id) {
    return String(base || "").replace(/\/0($|[/?#])/, "/" + id + "$1");
  }

  function parseJsonResponse(response) {
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      return response.text().then((text) => ({
        response,
        data: {
          ok: false,
          detail: text || response.statusText || "non_json_response",
        },
      }));
    }
    return response.json().then((data) => ({ response, data }));
  }

  function apiJson(url) {
    return fetch(url, { credentials: "same-origin" }).then(parseJsonResponse);
  }

  function postJson(url, payload) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    }).then(parseJsonResponse);
  }

  function errorReason(data) {
    const detail = data && data.detail;
    if (typeof detail === "object" && detail) {
      return detail.reason || detail.detail || detail.error || "";
    }
    return (data && (data.reason || data.error || detail)) || "";
  }

  function qrcodeGenerateMessage(reason) {
    return {
      owner_staff_id_required: "请先编辑渠道并选择负责人，再生成二维码",
      link_channel_does_not_support_qrcode_generate: "企微获客助手链接不支持生成二维码",
      channel_not_found: "渠道不存在或已删除",
      qrcode_asset_scene_channel_conflict: "该二维码场景值已绑定其他渠道，请换一个场景值后重试",
      wecom_adapter_disabled: "企微真实生成未开启，请检查企微运行配置",
      wecom_credentials_missing: "企微配置缺失，请先补齐企微凭证",
      wecom_api_error: "企微返回失败，请稍后重试或查看生成日志",
    }[reason] || reason || "二维码生成失败";
  }

  function qrcodeReady(channel) {
    return Boolean(channel.qrcode_asset_id) && ["active", "generated"].includes(String(channel.qrcode_status || ""));
  }

  function bootstrapUrls() {
    const node = root.querySelector("[data-channel-bootstrap]");
    if (!node) return {};
    try {
      return (JSON.parse(node.textContent || "{}").api_urls) || {};
    } catch (error) {
      return {};
    }
  }

  function renderRow(channel) {
    const link = isLink(channel);
    const searchText = String(channel.channel_name || "").toLowerCase();
    const typeText = link ? "企微获客助手链接" : "普通二维码";
    const downloadUrl = channel.qr_download_url || `/api/admin/channels/${encodeURIComponent(channel.id)}/qrcode/download`;
    const copyText = channelLinkText(channel);
    const bound = channel.bound_program_name
      ? `<span class="channel-pill is-bound">${escapeHtml(channel.bound_program_name)}</span>`
      : '<span class="channel-pill is-standalone">独立使用</span>';
    let action = link
      ? `<button class="admin-button admin-button--secondary" type="button" data-copy-channel-link data-copy-text="${escapeHtml(copyText)}">复制链接</button>
         <button class="admin-button admin-button--secondary" type="button" data-share-channel-link data-copy-text="${escapeHtml(copyText)}">分享链接</button>`
      : qrcodeReady(channel)
        ? `<a class="admin-button admin-button--secondary" href="${escapeHtml(downloadUrl)}">下载二维码</a>`
        : `<button class="admin-button admin-button--secondary" type="button" data-generate-channel-qrcode>生成二维码</button>`;
    if (!link && !qrcodeReady(channel) && !String(channel.owner_staff_id || "").trim()) {
      action = `<button class="admin-button admin-button--secondary" type="button" data-generate-channel-qrcode data-disabled-reason="owner_staff_id_required">生成二维码</button>`;
    }
    return `
      <tr data-channel-row data-channel-id="${escapeHtml(channel.id)}" data-search-text="${escapeHtml(searchText)}">
        <td>
          <strong>${escapeHtml(channel.channel_name || "-")}</strong>
        </td>
        <td><span class="channel-pill ${link ? "is-link" : "is-qrcode"}">${typeText}</span></td>
        <td><span class="channel-pill is-status">${escapeHtml(statusLabel(channel.status))}</span></td>
        <td>
          <span class="channel-pill ${channel.welcome_message_configured ? "is-ok" : ""}">${channel.welcome_message_configured ? "欢迎语" : "无欢迎语"}</span>
          <span class="channel-pill">${escapeHtml(channel.welcome_attachment_count || 0)} 素材</span>
          <span class="channel-pill ${channel.entry_tag_configured ? "is-ok" : ""}">${channel.entry_tag_configured ? "标签" : "无标签"}</span>
        </td>
        <td>${escapeHtml(channel.channel_contact_count || 0)}</td>
        <td>${bound}</td>
        <td class="channel-action-cell">
          <div class="channel-row-actions">
            ${action}
            <button class="admin-button admin-button--ghost" type="button" data-open-channel-drawer>查看</button>
            <a class="admin-button admin-button--ghost" href="/admin/channels/${encodeURIComponent(channel.id)}/edit">编辑</a>
          </div>
        </td>
      </tr>`;
  }

  fetch(apiUrl, { credentials: "same-origin" })
    .then((response) => response.json().then((data) => ({ response, data })))
    .then(({ response, data }) => {
      if (!response.ok || data.ok === false) {
        throw new Error(data.error || data.reason || "channels_load_failed");
      }
      const channels = Array.isArray(data.channels) ? data.channels : [];
      updateMetrics(channels);
      list.innerHTML = channels.length ? channels.map(renderRow).join("") : '<tr><td colspan="7">暂无渠道。</td></tr>';
    })
    .catch(() => {
      list.innerHTML = '<tr><td colspan="7">渠道加载失败，请稍后重试。</td></tr>';
    });

  search?.addEventListener("input", () => {
    const query = search.value.trim().toLowerCase();
    Array.from(list.querySelectorAll("[data-channel-row]")).forEach((row) => {
      const text = row.dataset.searchText || "";
      row.hidden = Boolean(query) && !text.includes(query);
    });
  });

  list.addEventListener("click", (event) => {
    const copyButton = event.target.closest("[data-copy-channel-link]");
    if (copyButton) {
      copyText(copyButton.dataset.copyText);
      return;
    }
    const shareButton = event.target.closest("[data-share-channel-link]");
    if (shareButton) {
      shareText(shareButton.dataset.copyText);
      return;
    }
    const generateButton = event.target.closest("[data-generate-channel-qrcode]");
    if (generateButton) {
      const disabledReason = generateButton.dataset.disabledReason || "";
      if (disabledReason) {
        toast(qrcodeGenerateMessage(disabledReason), "error");
        return;
      }
      const row = generateButton.closest("[data-channel-row]");
      const channelId = row ? row.dataset.channelId : "";
      if (!channelId) return;
      generateButton.disabled = true;
      generateButton.textContent = "生成中";
      postJson(`/api/admin/channels/${encodeURIComponent(channelId)}/qrcode/generate`, {}).then(({ response, data }) => {
        if (!response.ok || data.ok === false) {
          throw new Error(qrcodeGenerateMessage(errorReason(data)));
        }
        toast("二维码已生成");
        window.location.reload();
      }).catch((error) => {
        generateButton.disabled = false;
        generateButton.textContent = "生成二维码";
        toast(error.message || "二维码生成失败", "error");
      });
      return;
    }
    const detailButton = event.target.closest("[data-open-channel-drawer]");
    if (!detailButton || !drawer || !drawerBody) return;
    const row = detailButton.closest("[data-channel-row]");
    const channelId = row ? row.dataset.channelId : "";
    drawer.hidden = false;
    drawerBody.innerHTML = row
      ? `<p><strong>${escapeHtml(row.querySelector("strong")?.textContent || "")}</strong></p><p class="channel-muted">正在加载渠道用户列表...</p>`
      : "<p>暂无详情。</p>";
    if (!channelId) return;
    const urls = bootstrapUrls();
    Promise.all([
      apiJson(urlFromBase(urls.contacts_base, channelId) + "?limit=20").catch(() => ({ data: { contacts: [] } })),
      apiJson(urlFromBase(urls.bindings_base, channelId)).catch(() => ({ data: { bindings: [] } })),
    ]).then(([contactsResult, bindingsResult]) => {
      const contacts = (contactsResult.data || {}).contacts || [];
      const bindings = (bindingsResult.data || {}).bindings || [];
      const contactRows = contacts.length
        ? contacts.map((item) => `<tr><td>${escapeHtml(item.display_name || item.name || item.external_contact_id || "-")}</td><td>${escapeHtml(item.enter_count || 0)}</td></tr>`).join("")
        : '<tr><td colspan="2">暂无渠道用户。</td></tr>';
      const bindingText = bindings.length
        ? bindings.map((item) => `${escapeHtml(item.program_name || item.program_id || "-")} / ${escapeHtml(statusLabel(item.binding_status))}`).join("<br>")
        : "独立使用";
      drawerBody.innerHTML = `
        <p><strong>${escapeHtml(row.querySelector("strong")?.textContent || "")}</strong></p>
        <p class="channel-muted">当前绑定自动化运营状态：${bindingText}</p>
        <h3>渠道用户列表</h3>
        <table class="admin-table channel-table"><thead><tr><th>客户</th><th>进入次数</th></tr></thead><tbody>${contactRows}</tbody></table>`;
    });
  });

  root.querySelector("[data-close-channel-drawer]")?.addEventListener("click", () => {
    if (drawer) drawer.hidden = true;
  });
})();
