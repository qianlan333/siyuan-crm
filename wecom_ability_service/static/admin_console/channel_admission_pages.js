(function () {
  const root = document.querySelector("[data-channel-admission-page]");
  if (!root) return;

  const bootstrapNode = root.querySelector("[data-channel-bootstrap]");
  const bootstrap = bootstrapNode ? JSON.parse(bootstrapNode.textContent || "{}") : {};
  const adminToken = root.dataset.adminToken || "";

  function bySelector(selector, scope) {
    return Array.from((scope || root).querySelectorAll(selector));
  }

  function toast(message) {
    root.dataset.lastToast = message;
    if (window.AdminConsole && typeof window.AdminConsole.showToast === "function") {
      window.AdminConsole.showToast(message);
    }
  }

  function intList(value) {
    return String(value || "")
      .split(",")
      .map((item) => parseInt(item.trim(), 10))
      .filter((item, index, list) => item > 0 && list.indexOf(item) === index)
      .slice(0, 9);
  }

  function materialKey(type, id) {
    const normalizedType = String(type || "") === "miniprogram" ? "miniprogram" : "attachment";
    return normalizedType + ":" + String(id || "");
  }

  function selectedWelcomeMaterials() {
    const miniIds = intList(root.querySelector("[data-miniprogram-ids]")?.value);
    const attachmentIds = intList(root.querySelector("[data-attachment-ids]")?.value);
    return [
      ...miniIds.map((id) => ({ id, type: "miniprogram", name: "小程序 " + id })),
      ...attachmentIds.map((id) => ({ id, type: "attachment", name: "附件 " + id })),
    ];
  }

  function apiJson(url, options) {
    return fetch(url, {
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      ...options,
    }).then((response) => response.json().then((data) => ({ response, data })));
  }

  function urlFromBase(base, id) {
    return String(base || "").replace(/\/0($|[/?#])/, "/" + id + "$1");
  }

  function linkValueFrom(text) {
    return String(text || "").trim();
  }

  function copyText(text) {
    const value = linkValueFrom(text);
    if (!value) {
      toast("没有可复制链接");
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

  function fallbackCopy(text) {
    const input = document.createElement("textarea");
    input.value = text;
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
    toast(ok ? "链接已复制" : "请手动复制链接");
    return ok;
  }

  function shareText(text) {
    const value = linkValueFrom(text);
    if (!value) return copyText(value);
    if (navigator.share) {
      return navigator.share({ title: "企微获客助手链接", url: value }).catch(() => copyText(value));
    }
    return copyText(value);
  }

  function finalUrl(linkUrl, customerChannel) {
    const link = linkValueFrom(linkUrl);
    const channel = linkValueFrom(customerChannel);
    if (!link || !channel) return link;
    try {
      const url = new URL(link, window.location.origin);
      url.searchParams.set("customer_channel", channel);
      return url.toString();
    } catch (error) {
      return link + (link.indexOf("?") >= 0 ? "&" : "?") + "customer_channel=" + encodeURIComponent(channel);
    }
  }

  function setupChannelSearch() {
    const input = root.querySelector("[data-channel-search]");
    if (!input) return;
    input.addEventListener("input", () => {
      const query = input.value.trim().toLowerCase();
      bySelector("[data-channel-row]").forEach((row) => {
        const text = row.dataset.searchText || "";
        row.hidden = query && text.indexOf(query) === -1;
      });
    });
  }

  function setupCopyShare() {
    bySelector("[data-copy-channel-link]").forEach((button) => {
      button.addEventListener("click", () => copyText(button.dataset.copyText));
    });
    bySelector("[data-share-channel-link]").forEach((button) => {
      button.addEventListener("click", () => shareText(button.dataset.copyText));
    });
  }

  function setupChannelDrawer() {
    const drawer = root.querySelector("[data-channel-drawer]");
    if (!drawer) return;
    const body = root.querySelector("[data-channel-drawer-body]");
    bySelector("[data-open-channel-drawer]").forEach((button) => {
      button.addEventListener("click", () => {
        const row = button.closest("[data-channel-row]");
        const channelId = row ? row.dataset.channelId : "";
        body.innerHTML = row
          ? "<p><strong>" + row.querySelector("strong").textContent + "</strong></p><p class=\"channel-muted\">正在加载渠道用户列表...</p>"
          : "<p>暂无详情。</p>";
        drawer.hidden = false;
        if (!channelId) return;
        const urls = (bootstrap.api_urls || {});
        Promise.all([
          apiJson(urlFromBase(urls.contacts_base, channelId) + "?limit=20", { method: "GET" }).catch(() => ({ data: { contacts: [] } })),
          apiJson(urlFromBase(urls.bindings_base, channelId), { method: "GET" }).catch(() => ({ data: { bindings: [] } })),
        ]).then(([contactsResult, bindingsResult]) => {
          const contacts = (contactsResult.data || {}).contacts || [];
          const bindings = (bindingsResult.data || {}).bindings || [];
          const contactRows = contacts.length
            ? contacts.map((item) => "<tr><td>" + (item.external_contact_id || "-") + "</td><td>" + (item.enter_count || 0) + "</td><td>" + (item.last_channel_entered_at || "-") + "</td></tr>").join("")
            : "<tr><td colspan=\"3\">暂无渠道用户。</td></tr>";
          const bindingText = bindings.length
            ? bindings.map((item) => (item.program_name || item.program_id || "-") + " / " + item.binding_status).join("<br>")
            : "standalone 独立使用";
          body.innerHTML =
            "<p><strong>" + row.querySelector("strong").textContent + "</strong></p>" +
            "<p class=\"channel-muted\">当前绑定自动化运营状态：" + bindingText + "</p>" +
            "<h3>渠道用户列表</h3>" +
            "<table class=\"admin-table channel-table\"><thead><tr><th>external_contact_id</th><th>进入次数</th><th>最近进入</th></tr></thead><tbody>" +
            contactRows +
            "</tbody></table>";
        });
      });
    });
    root.querySelector("[data-close-channel-drawer]")?.addEventListener("click", () => {
      drawer.hidden = true;
    });
  }

  function updateTypeVisibility() {
    const select = root.querySelector("[data-channel-type-select]");
    if (!select) return;
    const isLink = select.value === "wecom_customer_acquisition";
    bySelector("[data-link-field], [data-link-section]").forEach((node) => {
      node.hidden = !isLink;
    });
    bySelector("[data-qrcode-field], [data-qrcode-section]").forEach((node) => {
      node.hidden = isLink;
    });
    const form = root.querySelector("[data-channel-form]");
    if (form) {
      const linkUrl = form.querySelector('[name="link_url"]')?.value || "";
      const customerChannel = form.querySelector('[name="customer_channel"]')?.value || "";
      const preview = root.querySelector("[data-link-preview]");
      const finalInput = form.querySelector('[name="final_url"]');
      const computed = finalUrl(linkUrl, customerChannel);
      if (preview) preview.textContent = computed || "填写 link_url 和 customer_channel 后预览 final_url";
      if (finalInput && computed && isLink) finalInput.value = computed;
    }
  }

  function channelFormPayload() {
    const form = root.querySelector("[data-channel-form]");
    if (!form) return {};
    const data = Object.fromEntries(new FormData(form).entries());
    const isLink = data.channel_type === "wecom_customer_acquisition";
    const miniprogramIds = intList(root.querySelector("[data-miniprogram-ids]")?.value);
    const attachmentIds = intList(root.querySelector("[data-attachment-ids]")?.value);
    if (miniprogramIds.length + attachmentIds.length > 9) {
      throw new Error("欢迎语素材最多选择 9 个");
    }
    return {
      admin_action_token: adminToken,
      channel_type: isLink ? "wecom_customer_acquisition" : "qrcode",
      carrier_type: isLink ? "link" : "qrcode",
      channel_name: data.channel_name || "",
      channel_code: data.channel_code || "",
      scene_value: isLink ? data.customer_channel || data.scene_value || "" : data.scene_value || "",
      customer_channel: isLink ? data.customer_channel || data.scene_value || "" : "",
      link_url: isLink ? data.link_url || "" : "",
      final_url: isLink ? data.final_url || finalUrl(data.link_url, data.customer_channel) : "",
      qr_url: isLink ? "" : data.qr_url || "",
      welcome_message: root.querySelector("[data-welcome-message]")?.value || "",
      welcome_miniprogram_library_ids: miniprogramIds,
      welcome_attachment_library_ids: attachmentIds,
      entry_tag_id: data.entry_tag_id || "",
      entry_tag_name: data.entry_tag_name || "",
      owner_staff_id: data.owner_staff_id || "",
      status: data.status || "active",
    };
  }

  function setupChannelForm() {
    const select = root.querySelector("[data-channel-type-select]");
    if (!select) return;
    select.addEventListener("change", updateTypeVisibility);
    bySelector('[name="link_url"], [name="customer_channel"]').forEach((input) => {
      input.addEventListener("input", updateTypeVisibility);
    });
    updateTypeVisibility();
    root.querySelector("[data-copy-form-link]")?.addEventListener("click", () => {
      copyText(root.querySelector("[data-link-preview]")?.textContent);
    });
    root.querySelector("[data-share-form-link]")?.addEventListener("click", () => {
      shareText(root.querySelector("[data-link-preview]")?.textContent);
    });
    root.querySelector("[data-save-channel]")?.addEventListener("click", () => {
      const isEdit = root.dataset.isEdit === "1";
      const url = isEdit ? root.dataset.apiDetail : root.dataset.apiCreate;
      const method = isEdit ? "PATCH" : "POST";
      let payload = {};
      try {
        payload = channelFormPayload();
      } catch (error) {
        toast(error.message || "保存失败");
        return;
      }
      apiJson(url, { method, body: JSON.stringify(payload) }).then(({ response, data }) => {
        if (!response.ok || data.ok === false) {
          toast(data.error || data.reason || "保存失败");
          return;
        }
        toast("渠道已保存");
        if (!isEdit && data.channel && data.channel.id) {
          window.location.href = "/admin/channels/" + data.channel.id + "/edit";
        }
      });
    });
  }

  function setupWelcomeMaterialPicker() {
    const picker = root.querySelector("[data-welcome-material-picker]");
    if (!picker) return;
    const modal = root.querySelector("[data-material-modal]");
    const list = root.querySelector("[data-material-results]");
    const selectedBox = root.querySelector("[data-selected-materials]");
    const miniInput = root.querySelector("[data-miniprogram-ids]");
    const attachmentInput = root.querySelector("[data-attachment-ids]");
    const renderSelected = () => {
      const selected = selectedWelcomeMaterials();
      selectedBox.innerHTML = selected.length
        ? selected.map((item) => '<button type="button" class="channel-material-chip" data-remove-material data-material-type="' + item.type + '" data-material-id="' + item.id + '">' + item.name + ' ×</button>').join("")
        : '<span class="channel-muted">暂未选择素材</span>';
    };
    const setSelected = (items) => {
      const miniIds = [];
      const attachmentIds = [];
      items.forEach((item) => {
        if (item.type === "miniprogram") miniIds.push(item.id);
        else attachmentIds.push(item.id);
      });
      miniInput.value = miniIds.slice(0, 9).join(",");
      attachmentInput.value = attachmentIds.slice(0, Math.max(0, 9 - miniIds.length)).join(",");
      renderSelected();
    };
    const loadMaterials = () => {
      const url = new URL((bootstrap.api_urls || {}).welcome_materials || "/api/admin/channel-welcome-materials", window.location.origin);
      url.searchParams.set("type", root.querySelector("[data-material-type-filter]")?.value || "all");
      url.searchParams.set("keyword", root.querySelector("[data-material-search]")?.value || "");
      apiJson(url.toString(), { method: "GET" }).then(({ data }) => {
        const selectedKeys = new Set(selectedWelcomeMaterials().map((item) => materialKey(item.type, item.id)));
        const rows = (data.materials || []).map((item) => {
          const payloadType = item.type === "miniprogram" ? "miniprogram" : "attachment";
          const checked = selectedKeys.has(materialKey(payloadType, item.id)) ? "checked" : "";
          return '<label class="channel-material-row"><input type="checkbox" data-material-checkbox value="' + item.id + '" data-material-type="' + payloadType + '" ' + checked + '><strong>' + (item.name || item.title || "-") + '</strong><span>' + item.type + ' · ' + (item.description || "") + '</span></label>';
        });
        list.innerHTML = rows.length ? rows.join("") : '<p class="channel-muted">没有匹配素材。</p>';
      });
    };
    picker.addEventListener("click", () => {
      modal.hidden = false;
      loadMaterials();
    });
    root.querySelector("[data-close-material-modal]")?.addEventListener("click", () => {
      modal.hidden = true;
    });
    root.querySelector("[data-material-search]")?.addEventListener("input", loadMaterials);
    root.querySelector("[data-material-type-filter]")?.addEventListener("change", loadMaterials);
    root.querySelector("[data-confirm-materials]")?.addEventListener("click", () => {
      const current = selectedWelcomeMaterials();
      const byKey = new Map(current.map((item) => [materialKey(item.type, item.id), item]));
      bySelector("[data-material-checkbox]", modal).forEach((checkbox) => {
        const id = parseInt(checkbox.value, 10);
        const type = checkbox.dataset.materialType || "";
        const key = materialKey(type, id);
        if (checkbox.checked) byKey.set(key, { id, type, name: type + " " + id });
        else byKey.delete(key);
      });
      const items = Array.from(byKey.values()).slice(0, 9);
      if (byKey.size > 9) toast("欢迎语素材最多选择 9 个，已保留前 9 个");
      setSelected(items);
      modal.hidden = true;
    });
    selectedBox?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-remove-material]");
      if (!button) return;
      const removeKey = materialKey(button.dataset.materialType, button.dataset.materialId);
      setSelected(selectedWelcomeMaterials().filter((item) => materialKey(item.type, item.id) !== removeKey));
    });
    renderSelected();
  }

  function setupBindModal() {
    const modal = root.querySelector("[data-bind-modal]");
    if (!modal) return;
    root.querySelector("[data-open-bind-modal]")?.addEventListener("click", () => {
      modal.hidden = false;
    });
    root.querySelector("[data-close-bind-modal]")?.addEventListener("click", () => {
      modal.hidden = true;
    });
    root.querySelector("[data-confirm-bind]")?.addEventListener("click", () => {
      const ids = bySelector("[data-bind-channel-checkbox]:checked", modal).map((item) => parseInt(item.value, 10)).filter(Boolean);
      if (!ids.length) {
        toast("请选择渠道");
        return;
      }
      apiJson(root.dataset.apiBindings, {
        method: "POST",
        body: JSON.stringify({
          admin_action_token: adminToken,
          channel_ids: ids,
        }),
      }).then(({ response, data }) => {
        if (!response.ok || data.ok === false) {
          toast(data.error || data.reason || "绑定失败");
          return;
        }
        window.location.reload();
      });
    });
  }

  function importPayload(dryRun) {
    const channelId = parseInt(root.querySelector("[data-import-channel-id]")?.value || "0", 10);
    return {
      admin_action_token: adminToken,
      channel_id: channelId,
      dry_run: dryRun !== false,
      use_historical_channel_entered_at: false,
    };
  }

  function setupImportPanel() {
    const preview = root.querySelector("[data-import-payload-preview]");
    if (!preview) return;
    const update = (dryRun) => {
      preview.textContent = JSON.stringify(importPayload(dryRun), null, 2);
    };
    update(true);
    root.querySelector("[data-import-channel-id]")?.addEventListener("change", () => update(true));
    root.querySelector("[data-run-import-dry-run]")?.addEventListener("click", () => {
      const payload = importPayload(true);
      update(true);
      apiJson(root.dataset.apiImport, { method: "POST", body: JSON.stringify(payload) }).then(({ data }) => {
        preview.textContent = JSON.stringify(data, null, 2);
      });
    });
    root.querySelector("[data-run-import-confirm]")?.addEventListener("click", () => {
      const payload = importPayload(false);
      update(false);
      apiJson(root.dataset.apiImport, { method: "POST", body: JSON.stringify(payload) }).then(({ data }) => {
        preview.textContent = JSON.stringify(data, null, 2);
      });
    });
  }

  function setupEntryActions() {
    bySelector("[data-unbind-channel]").forEach((button) => {
      button.addEventListener("click", () => {
        const bindingId = button.dataset.bindingId;
        const base = (bootstrap.api_urls || {}).binding_base || "";
        const url = base.replace(/\/0($|[/?#])/, "/" + bindingId + "$1");
        apiJson(url, { method: "DELETE", body: JSON.stringify({ admin_action_token: adminToken }) }).then(({ response, data }) => {
          if (!response.ok || data.ok === false) {
            toast(data.error || data.reason || "解绑失败");
            return;
          }
          window.location.reload();
        });
      });
    });
    bySelector("[data-open-import-panel]").forEach((button) => {
      button.addEventListener("click", () => {
        const bindingId = button.dataset.bindingId || button.closest("[data-bound-channel-id]")?.dataset.bindingId || "";
        const base = (bootstrap.api_urls || {}).member_stage_summary_base || "";
        const url = base.replace(/\/0($|[/?#])/, "/" + bindingId + "$1");
        if (!bindingId || !url) return;
        apiJson(url, { method: "GET" }).then(({ data }) => {
          const preview = root.querySelector("[data-import-payload-preview]");
          if (preview) preview.textContent = JSON.stringify(data, null, 2);
        });
      });
    });
    const drawer = root.querySelector("[data-attempt-drawer]");
    if (drawer) {
      bySelector("[data-open-attempt-drawer]").forEach((button) => {
        button.addEventListener("click", () => {
          const row = button.closest("[data-admission-attempt-id]");
          root.querySelector("[data-attempt-drawer-body]").innerHTML = row ? row.innerHTML : "暂无详情";
          drawer.hidden = false;
        });
      });
      root.querySelector("[data-close-attempt-drawer]")?.addEventListener("click", () => {
        drawer.hidden = true;
      });
    }
  }

  setupChannelSearch();
  setupCopyShare();
  setupChannelDrawer();
  setupChannelForm();
  setupWelcomeMaterialPicker();
  setupBindModal();
  setupImportPanel();
  setupEntryActions();
})();
