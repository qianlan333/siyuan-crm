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

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[char]));
  }

  function intList(value) {
    return String(value || "")
      .split(",")
      .map((item) => parseInt(item.trim(), 10))
      .filter((item, index, list) => item > 0 && list.indexOf(item) === index)
      .slice(0, 9);
  }

  function setIds(input, ids) {
    if (!input) return;
    input.value = (ids || [])
      .map((item) => parseInt(item, 10))
      .filter((item, index, list) => item > 0 && list.indexOf(item) === index)
      .slice(0, 9)
      .join(",");
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

  function statusLabel(value) {
    return {
      active: "启用",
      paused: "暂停",
      archived: "归档",
      accepted: "已入池",
      waiting: "等待审核",
      converted: "已成交",
      rejected: "已拒绝",
      duplicate_active: "重复扫码",
      manual_review: "人工审核",
      standalone_channel: "独立渠道",
    }[value] || value || "-";
  }

  function stageLabel(value) {
    return {
      scan_enter: "扫码进入",
      order_review: "订单审核",
      questionnaire_review: "问卷审核",
      operating: "运营中",
      conversion_review: "成交判定",
      converted: "已成交",
      finished: "结束",
    }[value] || statusLabel(value);
  }

  function renderImportResult(data) {
    if (!data || typeof data !== "object") return "导入任务已处理";
    const lines = [];
    if (data.dry_run === true) lines.push("导入模式：只做预估");
    if (data.dry_run === false) lines.push("导入模式：确认导入");
    if (typeof data.planned_count !== "undefined") lines.push("预计导入人数：" + data.planned_count);
    if (typeof data.imported_count !== "undefined") lines.push("已导入人数：" + data.imported_count);
    if (typeof data.created_count !== "undefined") lines.push("新建人数：" + data.created_count);
    if (typeof data.skipped_count !== "undefined") lines.push("跳过人数：" + data.skipped_count);
    if (data.reason) lines.push("处理说明：" + data.reason);
    if (Array.isArray(data.errors) && data.errors.length) lines.push("错误：" + data.errors.join("；"));
    return lines.length ? lines.join("\n") : "导入任务已处理";
  }

  function renderMemberStageSummary(data) {
    const summary = (data || {}).summary || {};
    const members = (data || {}).members || [];
    const summaryRows = [
      ["总人数", summary.total],
      ["订单审核", summary.order_review],
      ["问卷审核", summary.questionnaire_review],
      ["运营中", summary.operating],
      ["已成交", summary.converted],
      ["已结束", summary.finished],
      ["已退出", summary.exited],
    ].map((item) => "<tr><td>" + item[0] + "</td><td>" + (item[1] || 0) + "</td></tr>").join("");
    const memberRows = members.length
      ? members.map((item) => "<tr><td>" + (item.display_name || item.name || item.external_contact_id || "-") + "</td><td>" + stageLabel(item.current_stage_code) + "</td><td>" + (item.pool_entered_at || "-") + "</td><td>" + (item.stage_entered_at || "-") + "</td></tr>").join("")
      : "<tr><td colspan=\"4\">暂无池内用户。</td></tr>";
    return "<h3>阶段分布</h3><table class=\"admin-table channel-table\"><tbody>" + summaryRows + "</tbody></table>" +
      "<h3>池内用户</h3><table class=\"admin-table channel-table\"><thead><tr><th>客户</th><th>当前阶段</th><th>入池时间</th><th>阶段进入时间</th></tr></thead><tbody>" + memberRows + "</tbody></table>";
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
            ? contacts.map((item) => "<tr><td>" + (item.display_name || item.name || item.external_contact_id || "-") + "</td><td>" + (item.enter_count || 0) + "</td><td>" + (item.last_channel_entered_at || "-") + "</td></tr>").join("")
            : "<tr><td colspan=\"3\">暂无渠道用户。</td></tr>";
          const bindingText = bindings.length
            ? bindings.map((item) => (item.program_name || item.program_id || "-") + " / " + statusLabel(item.binding_status)).join("<br>")
            : "独立使用";
          body.innerHTML =
            "<p><strong>" + row.querySelector("strong").textContent + "</strong></p>" +
            "<p class=\"channel-muted\">当前绑定自动化运营状态：" + bindingText + "</p>" +
            "<h3>渠道用户列表</h3>" +
            "<table class=\"admin-table channel-table\"><thead><tr><th>客户</th><th>进入次数</th><th>最近进入</th></tr></thead><tbody>" +
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
      if (preview) preview.textContent = computed || "填写原始链接和渠道参数后预览最终分享链接";
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
    const entryTagId = root.querySelector("[data-entry-tag-id]")?.value || "";
    const entryTagName = root.querySelector("[data-entry-tag-name]")?.value || "";
    const entryTagGroupName = root.querySelector("[data-entry-tag-group-name]")?.value || "";
    if (miniprogramIds.length + attachmentIds.length > 9) {
      throw new Error("欢迎语素材最多选择 9 个");
    }
    return {
      admin_action_token: adminToken,
      channel_type: isLink ? "wecom_customer_acquisition" : "qrcode",
      carrier_type: isLink ? "link" : "qrcode",
      channel_name: data.channel_name || "",
      channel_code: data.channel_code || "",
      scene_value: isLink ? data.customer_channel || data.scene_value || "" : data.scene_value || data.channel_code || "",
      customer_channel: isLink ? data.customer_channel || data.scene_value || "" : "",
      link_url: isLink ? data.link_url || "" : "",
      final_url: isLink ? data.final_url || finalUrl(data.link_url, data.customer_channel) : "",
      qr_url: isLink ? "" : data.qr_url || "",
      welcome_message: root.querySelector("[data-welcome-message]")?.value || "",
      welcome_miniprogram_library_ids: miniprogramIds,
      welcome_attachment_library_ids: attachmentIds,
      entry_tag_id: entryTagId,
      entry_tag_name: entryTagName,
      entry_tag_group_name: entryTagGroupName,
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

  function setupChannelOwnerPicker() {
    const modal = root.querySelector("[data-channel-owner-modal]");
    if (!modal) return;
    const ownerStaffInput = root.querySelector("[data-channel-owner-staff-id]");
    const ownerCurrent = root.querySelector("[data-channel-owner-current]");
    root.querySelector("[data-channel-owner-picker-open]")?.addEventListener("click", () => {
      modal.hidden = false;
    });
    root.querySelector("[data-channel-owner-picker-close]")?.addEventListener("click", () => {
      modal.hidden = true;
    });
    modal.addEventListener("click", (event) => {
      if (event.target === modal) {
        modal.hidden = true;
        return;
      }
      const pick = event.target.closest("[data-channel-owner-pick]");
      if (!pick) return;
      const ownerStaffId = pick.dataset.ownerStaffId || "";
      const ownerDisplayName = pick.dataset.ownerDisplayName || ownerStaffId;
      if (ownerStaffInput) ownerStaffInput.value = ownerStaffId;
      if (ownerCurrent) {
        ownerCurrent.innerHTML = "<strong>" + escapeHtml(ownerDisplayName || "未选择负责人") + "</strong><small>" + escapeHtml(ownerStaffId || "从企业微信通讯录或后台成员中选择") + "</small>";
      }
      modal.hidden = true;
      toast("已选择负责人：" + (ownerDisplayName || ownerStaffId));
    });
  }

  function setupWelcomeMaterialPicker() {
    const modal = root.querySelector("[data-resource-picker-modal]");
    if (!modal) return;
    const list = root.querySelector("[data-resource-picker-results]");
    const title = root.querySelector("[data-resource-picker-title]");
    const subtitle = root.querySelector("[data-resource-picker-subtitle]");
    const search = root.querySelector("[data-resource-picker-search]");
    const miniInput = root.querySelector("[data-miniprogram-ids]");
    const attachmentInput = root.querySelector("[data-attachment-ids]");
    const miniSelected = root.querySelector("[data-miniprogram-selected]");
    const attachmentSelected = root.querySelector("[data-attachment-selected]");
    const tagSelected = root.querySelector("[data-tag-selected]");
    const tagIdInput = root.querySelector("[data-entry-tag-id]");
    const tagNameInput = root.querySelector("[data-entry-tag-name]");
    const tagGroupInput = root.querySelector("[data-entry-tag-group-name]");
    const pickerState = { kind: "", selected: new Set(), selectedTagId: "", items: [] };

    const materialTypeLabel = (type) => ({
      miniprogram: "小程序",
      image: "图片",
      pdf: "PDF",
      attachment: "附件",
      tag: "标签",
    }[type] || type || "素材");

    const fetchWelcomeMaterials = (type, keyword) => {
      const url = new URL((bootstrap.api_urls || {}).welcome_materials || "/api/admin/channel-welcome-materials", window.location.origin);
      url.searchParams.set("type", type);
      url.searchParams.set("keyword", keyword || "");
      return apiJson(url.toString(), { method: "GET" }).then(({ data }) => data.materials || []);
    };

    const fetchTags = (keyword) => {
      const apiUrl = (bootstrap.api_urls || {}).wecom_tags || "/api/admin/wecom/tags";
      return apiJson(apiUrl, { method: "GET" }).then(({ data }) => {
        const query = String(keyword || "").trim().toLowerCase();
        return (Array.isArray(data.items) ? data.items : [])
          .filter((item) => {
            if (!query) return true;
            return [item.group_name, item.tag_name, item.tag_id].join(" ").toLowerCase().includes(query);
          })
          .map((item) => ({
            id: item.tag_id,
            type: "tag",
            name: item.tag_name || item.tag_id,
            description: item.group_name || "未分组",
            tag_id: item.tag_id,
            tag_name: item.tag_name || item.tag_id,
            group_name: item.group_name || "",
          }));
      }).catch(() => []);
    };

    const renderSelectedMaterials = () => {
      const miniIds = intList(miniInput?.value);
      const attachmentIds = intList(attachmentInput?.value);
      Promise.all([
        fetchWelcomeMaterials("miniprogram", ""),
        fetchWelcomeMaterials("all", ""),
      ]).then(([miniItems, attachmentItems]) => {
        const miniMap = new Map(miniItems.map((item) => [Number(item.id), item]));
        const attachmentMap = new Map(attachmentItems.map((item) => [Number(item.id), item]));
        if (miniSelected) {
          miniSelected.innerHTML = miniIds.length
            ? miniIds.map((id) => {
              const item = miniMap.get(id) || { id, name: "小程序 " + id };
              return '<button type="button" class="channel-material-chip" data-remove-picked="miniprogram" data-id="' + id + '">' + escapeHtml(item.name || item.title || ("小程序 " + id)) + ' ×</button>';
            }).join("")
            : '<span class="channel-muted">暂未选择小程序</span>';
        }
        if (attachmentSelected) {
          attachmentSelected.innerHTML = attachmentIds.length
            ? attachmentIds.map((id) => {
              const item = attachmentMap.get(id) || { id, type: "attachment", name: "素材 " + id };
              return '<button type="button" class="channel-material-chip" data-remove-picked="attachment" data-id="' + id + '">' + escapeHtml(materialTypeLabel(item.type)) + " · " + escapeHtml(item.name || item.title || ("素材 " + id)) + ' ×</button>';
            }).join("")
            : '<span class="channel-muted">暂未选择图片/PDF</span>';
        }
      });
      if (tagSelected) {
        const tagId = String(tagIdInput?.value || "").trim();
        const tagName = String(tagNameInput?.value || "").trim();
        const groupName = String(tagGroupInput?.value || "").trim();
        tagSelected.innerHTML = tagId
          ? '<button type="button" class="channel-material-chip" data-remove-picked="tag" data-id="' + escapeHtml(tagId) + '">' + escapeHtml((groupName ? groupName + " / " : "") + (tagName || tagId)) + ' ×</button>'
          : '<span class="channel-muted">暂未选择标签</span>';
      }
    };

    const renderPickerRows = () => {
      const isTag = pickerState.kind === "tag";
      const rows = pickerState.items.map((item) => {
        const value = String(isTag ? item.tag_id : item.id);
        const checked = isTag ? (pickerState.selectedTagId === value ? "checked" : "") : (pickerState.selected.has(value) ? "checked" : "");
        const inputType = isTag ? "radio" : "checkbox";
        const meta = isTag ? (item.description || "未分组") : (materialTypeLabel(item.type) + (item.description ? " · " + item.description : ""));
        return '<label class="channel-material-row channel-material-row--preview">' +
          '<input type="' + inputType + '" name="channel-resource-picker" data-resource-checkbox value="' + escapeHtml(value) + '" ' + checked + '>' +
          '<strong>' + escapeHtml(item.name || item.title || value || "-") + '</strong>' +
          '<span>' + escapeHtml(meta) + '</span>' +
          '</label>';
      });
      list.innerHTML = rows.length ? rows.join("") : '<p class="channel-muted">没有匹配结果。</p>';
    };

    const loadPickerItems = () => {
      const keyword = search?.value || "";
      list.innerHTML = '<p class="channel-muted">正在加载...</p>';
      const loader = pickerState.kind === "miniprogram"
        ? fetchWelcomeMaterials("miniprogram", keyword)
        : pickerState.kind === "attachment"
          ? fetchWelcomeMaterials("all", keyword).then((items) => items.filter((item) => item.type === "image" || item.type === "pdf"))
          : fetchTags(keyword);
      loader.then((items) => {
        pickerState.items = items;
        renderPickerRows();
      });
    };

    const openPicker = (kind) => {
      pickerState.kind = kind;
      pickerState.items = [];
      pickerState.selected = new Set(kind === "miniprogram" ? intList(miniInput?.value).map(String) : intList(attachmentInput?.value).map(String));
      pickerState.selectedTagId = String(tagIdInput?.value || "");
      if (search) search.value = "";
      if (kind === "miniprogram") {
        title.textContent = "预览并选择小程序素材";
        subtitle.textContent = "从小程序素材库中预览标题、appid 和页面路径后选择。";
      } else if (kind === "attachment") {
        title.textContent = "预览并选择图片/PDF素材";
        subtitle.textContent = "从附件素材库中选择图片或 PDF；欢迎语素材总数最多 9 个。";
      } else {
        title.textContent = "预览并选择标签";
        subtitle.textContent = "从已同步的企微标签组中选择，保存时只写入标签编号。";
      }
      modal.hidden = false;
      loadPickerItems();
    };

    root.querySelector("[data-open-miniprogram-picker]")?.addEventListener("click", () => openPicker("miniprogram"));
    root.querySelector("[data-open-attachment-picker]")?.addEventListener("click", () => openPicker("attachment"));
    root.querySelector("[data-open-tag-picker]")?.addEventListener("click", () => openPicker("tag"));
    root.querySelector("[data-close-resource-picker]")?.addEventListener("click", () => {
      modal.hidden = true;
    });
    search?.addEventListener("input", loadPickerItems);
    root.querySelector("[data-confirm-resource-picker]")?.addEventListener("click", () => {
      if (pickerState.kind === "tag") {
        const checked = modal.querySelector("[data-resource-checkbox]:checked");
        const item = pickerState.items.find((candidate) => String(candidate.tag_id) === String(checked?.value || ""));
        if (tagIdInput) tagIdInput.value = item?.tag_id || "";
        if (tagNameInput) tagNameInput.value = item?.tag_name || "";
        if (tagGroupInput) tagGroupInput.value = item?.group_name || "";
      } else {
        const checkedIds = Array.from(pickerState.selected);
        const currentMini = pickerState.kind === "miniprogram" ? checkedIds : intList(miniInput?.value).map(String);
        const currentAttachments = pickerState.kind === "attachment" ? checkedIds : intList(attachmentInput?.value).map(String);
        if (currentMini.length + currentAttachments.length > 9) {
          toast("欢迎语素材最多选择 9 个");
          return;
        }
        if (pickerState.kind === "miniprogram") setIds(miniInput, checkedIds);
        if (pickerState.kind === "attachment") setIds(attachmentInput, checkedIds);
      }
      modal.hidden = true;
      renderSelectedMaterials();
    });
    modal.addEventListener("change", (event) => {
      const checkbox = event.target.closest("[data-resource-checkbox]");
      if (!checkbox) return;
      if (pickerState.kind === "tag") {
        pickerState.selectedTagId = checkbox.value;
        return;
      }
      if (checkbox.checked) pickerState.selected.add(checkbox.value);
      else pickerState.selected.delete(checkbox.value);
    });
    root.addEventListener("click", (event) => {
      const button = event.target.closest("[data-remove-picked]");
      if (!button) return;
      const kind = button.dataset.removePicked;
      if (kind === "miniprogram") setIds(miniInput, intList(miniInput?.value).filter((id) => String(id) !== String(button.dataset.id)));
      if (kind === "attachment") setIds(attachmentInput, intList(attachmentInput?.value).filter((id) => String(id) !== String(button.dataset.id)));
      if (kind === "tag") {
        if (tagIdInput) tagIdInput.value = "";
        if (tagNameInput) tagNameInput.value = "";
        if (tagGroupInput) tagGroupInput.value = "";
      }
      renderSelectedMaterials();
    });
    renderSelectedMaterials();
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
      preview.textContent = "导入模式：" + (dryRun === false ? "确认导入" : "只做预估") + "\n入池时间：使用导入时间";
    };
    update(true);
    root.querySelector("[data-import-channel-id]")?.addEventListener("change", () => update(true));
    root.querySelector("[data-run-import-dry-run]")?.addEventListener("click", () => {
      const payload = importPayload(true);
      update(true);
      apiJson(root.dataset.apiImport, { method: "POST", body: JSON.stringify(payload) }).then(({ data }) => {
        preview.textContent = renderImportResult(data);
      });
    });
    root.querySelector("[data-run-import-confirm]")?.addEventListener("click", () => {
      const payload = importPayload(false);
      update(false);
      apiJson(root.dataset.apiImport, { method: "POST", body: JSON.stringify(payload) }).then(({ data }) => {
        preview.textContent = renderImportResult(data);
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
          if (preview) preview.innerHTML = renderMemberStageSummary(data);
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
  setupChannelOwnerPicker();
  setupWelcomeMaterialPicker();
  setupBindModal();
  setupImportPanel();
  setupEntryActions();
})();
