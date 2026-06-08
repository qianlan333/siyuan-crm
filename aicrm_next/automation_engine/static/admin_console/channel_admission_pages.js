(function () {
  function normalizeIdList(value) {
    const raw = Array.isArray(value) ? value : String(value || "").split(",");
    const ids = [];
    raw.forEach((item) => {
      const id = parseInt(String(item).trim(), 10);
      if (id > 0 && ids.indexOf(id) === -1) ids.push(id);
    });
    return ids;
  }

  function welcomeFieldsToContentPackage(fields) {
    const data = fields || {};
    return {
      content_text: String(data.welcome_message || "").trim(),
      image_library_ids: normalizeIdList(data.welcome_image_library_ids),
      miniprogram_library_ids: normalizeIdList(data.welcome_miniprogram_library_ids),
      attachment_library_ids: normalizeIdList(data.welcome_attachment_library_ids),
    };
  }

  function contentPackageToWelcomeFields(contentPackage) {
    const data = contentPackage || {};
    return {
      welcome_message: String(data.content_text || "").trim(),
      welcome_image_library_ids: normalizeIdList(data.image_library_ids),
      welcome_miniprogram_library_ids: normalizeIdList(data.miniprogram_library_ids),
      welcome_attachment_library_ids: normalizeIdList(data.attachment_library_ids),
    };
  }

  if (typeof window !== "undefined") {
    window.AICRMChannelWelcomeAdapter = {
      normalizeIdList,
      welcomeFieldsToContentPackage,
      contentPackageToWelcomeFields,
    };
  }

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

  function setSaveFeedback(message, tone) {
    const node = root.querySelector("[data-channel-save-feedback]");
    if (!node) return;
    const text = String(message || "").trim();
    node.textContent = text;
    node.hidden = !text;
    node.classList.toggle("is-error", tone === "error");
  }

  function safeInit(name, fn) {
    try {
      fn();
    } catch (error) {
      console.error(`[channel_admission_pages] ${name} init failed`, error);
      root.dataset[`init${name}Error`] = error.message || "init failed";
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
    return normalizeIdList(value);
  }

  function setIds(input, ids) {
    if (!input) return;
    input.value = normalizeIdList(ids).join(",");
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
    const imageIds = intList(root.querySelector("[data-image-ids]")?.value);
    const attachmentIds = intList(root.querySelector("[data-attachment-ids]")?.value);
    const entryTagId = root.querySelector("[data-entry-tag-id]")?.value || "";
    const entryTagName = root.querySelector("[data-entry-tag-name]")?.value || "";
    const entryTagGroupName = root.querySelector("[data-entry-tag-group-name]")?.value || "";
    if (miniprogramIds.length + imageIds.length + attachmentIds.length > 9) {
      throw new Error("欢迎语素材最多选择 9 个");
    }
    const payload = {
      admin_action_token: adminToken,
      channel_type: isLink ? "wecom_customer_acquisition" : "qrcode",
      carrier_type: isLink ? "link" : "qrcode",
      channel_name: data.channel_name || "",
      channel_code: data.channel_code || "",
      link_url: isLink ? data.link_url || "" : "",
      final_url: isLink ? data.final_url || finalUrl(data.link_url, data.customer_channel) : "",
      qr_url: isLink ? "" : data.qr_url || "",
      welcome_message: root.querySelector("[data-welcome-message]")?.value || "",
      welcome_image_library_ids: imageIds,
      welcome_miniprogram_library_ids: miniprogramIds,
      welcome_attachment_library_ids: attachmentIds,
      auto_accept_friend: !isLink && !!form.querySelector('[name="auto_accept_friend"]')?.checked,
      entry_tag_id: entryTagId,
      entry_tag_name: entryTagName,
      entry_tag_group_name: entryTagGroupName,
      owner_staff_id: data.owner_staff_id || "",
      status: data.status || "active",
    };
    if (isLink) {
      payload.scene_value = data.customer_channel || data.scene_value || "";
      payload.customer_channel = data.customer_channel || data.scene_value || "";
    }
    return payload;
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
      const saveButton = root.querySelector("[data-save-channel]");
      const isEdit = root.dataset.isEdit === "1";
      const url = isEdit ? root.dataset.apiDetail : root.dataset.apiCreate;
      const method = isEdit ? "PATCH" : "POST";
      let payload = {};
      try {
        payload = channelFormPayload();
      } catch (error) {
        toast(error.message || "保存失败");
        setSaveFeedback(error.message || "保存失败", "error");
        return;
      }
      if (saveButton) {
        saveButton.disabled = true;
        saveButton.textContent = "保存中...";
      }
      setSaveFeedback("正在保存渠道配置...");
      apiJson(url, { method, body: JSON.stringify(payload) }).then(({ response, data }) => {
        if (!response.ok || data.ok === false) {
          toast(data.error || data.reason || "保存失败");
          setSaveFeedback(data.error || data.reason || "保存失败", "error");
          return;
        }
        const savedAt = new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
        toast("渠道已保存");
        setSaveFeedback("保存成功，欢迎语和素材已更新。" + (savedAt ? " " + savedAt : ""));
        if (!isEdit && data.channel && data.channel.id) {
          window.location.href = "/admin/channels/" + data.channel.id + "/edit";
        }
      }).catch((error) => {
        toast(error.message || "保存失败");
        setSaveFeedback(error.message || "保存失败", "error");
      }).finally(() => {
        if (saveButton) {
          saveButton.disabled = false;
          saveButton.textContent = "保存渠道";
        }
      });
    });
  }

  function setupChannelOwnerPicker() {
    const ownerStaffInput = root.querySelector("[data-channel-owner-staff-id]");
    const ownerCurrent = root.querySelector("[data-channel-owner-current]");
    const renderOwner = (member, fallbackUserId) => {
      const userId = (member && member.user_id) || fallbackUserId || "";
      const label = window.OperationMemberPicker && member
        ? window.OperationMemberPicker.memberLabel(member)
        : userId;
      if (ownerCurrent) {
        ownerCurrent.innerHTML = "<strong>" + escapeHtml(label || "未选择负责人") + "</strong><small>" + escapeHtml(userId || "从企业微信通讯录或后台成员中选择") + "</small>";
      }
    };
    const currentOwner = ownerStaffInput ? ownerStaffInput.value : "";
    if (currentOwner && window.OperationMemberPicker && typeof window.OperationMemberPicker.resolve === "function") {
      window.OperationMemberPicker.resolve(currentOwner).then((member) => {
        if (member && (!ownerStaffInput || ownerStaffInput.value === currentOwner)) renderOwner(member, currentOwner);
      }).catch(() => undefined);
    }
    root.querySelector("[data-channel-owner-picker-open]")?.addEventListener("click", () => {
      if (!window.OperationMemberPicker) {
        toast("人员加载失败，请稍后重试");
        return;
      }
      window.OperationMemberPicker.open({
        value: ownerStaffInput ? ownerStaffInput.value : "",
        title: "选择运营人员",
        onSelect: (member) => {
          if (ownerStaffInput) ownerStaffInput.value = member.user_id || "";
          renderOwner(member, member.user_id || "");
          toast("已选择负责人：" + (window.OperationMemberPicker.memberLabel(member) || member.user_id || ""));
        },
      });
    });
  }

  function setupWelcomeComposer() {
    const messageInput = root.querySelector("[data-welcome-message]");
    const miniInput = root.querySelector("[data-miniprogram-ids]");
    const imageInput = root.querySelector("[data-image-ids]");
    const attachmentInput = root.querySelector("[data-attachment-ids]");
    const summary = root.querySelector("[data-welcome-content-summary]");
    if (!root.querySelector("[data-open-welcome-composer]")) return;

    const currentPackage = () => welcomeFieldsToContentPackage({
      welcome_message: messageInput?.value || "",
      welcome_image_library_ids: intList(imageInput?.value),
      welcome_miniprogram_library_ids: intList(miniInput?.value),
      welcome_attachment_library_ids: intList(attachmentInput?.value),
    });

    const renderSummary = () => {
      const contentPackage = currentPackage();
      const text = String(contentPackage.content_text || "").trim();
      const textSummary = text ? (text.length > 60 ? text.slice(0, 60) + "..." : text) : "未配置话术";
      if (summary) {
        summary.innerHTML =
          '<strong>话术：</strong><span>' + escapeHtml(textSummary) + '</span>' +
          '<strong>素材：</strong><span>图片 ' + contentPackage.image_library_ids.length +
          ' / 小程序 ' + contentPackage.miniprogram_library_ids.length +
          ' / 附件 ' + contentPackage.attachment_library_ids.length + '</span>';
      }
    };

    const openWelcomeComposer = () => {
      if (!window.AICRMSendContentComposer || typeof window.AICRMSendContentComposer.open !== "function") {
        const message = "标准内容编辑器未加载，请刷新页面后重试";
        toast(message);
        setSaveFeedback(message, "error");
        root.dataset.welcomeComposerError = "composer_not_loaded";
        return;
      }
      window.AICRMSendContentComposer.open({
        title: "配置欢迎语和素材",
        textEnabled: true,
        value: currentPackage(),
        limits: {
          image: 3,
          miniprogram: 1,
          attachment: 9,
        },
        onConfirm(contentPackage) {
          const fields = contentPackageToWelcomeFields(contentPackage);
          if (messageInput) messageInput.value = fields.welcome_message;
          setIds(imageInput, fields.welcome_image_library_ids);
          setIds(miniInput, fields.welcome_miniprogram_library_ids);
          setIds(attachmentInput, fields.welcome_attachment_library_ids);
          renderSummary();
          toast("欢迎语和素材已更新");
        },
      });
    };

    root.addEventListener("click", (event) => {
      const openButton = event.target.closest("[data-open-welcome-composer]");
      if (!openButton) return;
      event.preventDefault();
      openWelcomeComposer();
    });

    renderSummary();
    root.dataset.welcomeComposerReady = "1";
  }

  function setupEntryTagPicker() {
    const openButton = root.querySelector("[data-open-tag-picker]");
    if (!openButton) return;
    const tagSelected = root.querySelector("[data-tag-selected]");
    const tagIdInput = root.querySelector("[data-entry-tag-id]");
    const tagNameInput = root.querySelector("[data-entry-tag-name]");
    const tagGroupInput = root.querySelector("[data-entry-tag-group-name]");
    const pickerState = { catalog: null, failed: false };

    const fetchTagCatalog = () => {
      if (pickerState.catalog) return Promise.resolve(pickerState.catalog);
      const apiUrl = (bootstrap.api_urls || {}).wecom_tags || "/api/admin/wecom/tags";
      return apiJson(apiUrl, { method: "GET" }).then(({ data }) => {
        pickerState.catalog = {
          groups: Array.isArray(data.groups) ? data.groups : [],
          items: Array.isArray(data.items) ? data.items : [],
        };
        pickerState.failed = false;
        return pickerState.catalog;
      }).catch(() => {
        pickerState.catalog = { groups: [], items: [] };
        pickerState.failed = true;
        return pickerState.catalog;
      });
    };

    const renderSelectedMaterials = () => {
      if (tagSelected) {
        const tagId = String(tagIdInput?.value || "").trim();
        const tagName = String(tagNameInput?.value || "").trim();
        const groupName = String(tagGroupInput?.value || "").trim();
        tagSelected.innerHTML = tagId
          ? '<button type="button" class="channel-material-chip" data-remove-picked="tag">' + escapeHtml((groupName ? groupName + " / " : "") + (tagName || "已选择标签")) + ' ×</button>'
          : '<span class="channel-muted">暂未选择标签</span>';
      }
    };

    const openPicker = () => {
      if (!window.AICRMWeComTagPicker) {
        toast("标签选择器加载失败，请刷新后重试");
        return;
      }
      fetchTagCatalog().then((catalog) => {
        const currentValue = String(tagIdInput?.value || "").trim()
          ? {
              tag_id: tagIdInput.value,
              tag_name: tagNameInput?.value || "",
              group_name: tagGroupInput?.value || "",
            }
          : null;
        window.AICRMWeComTagPicker.open({
          title: "选择入渠标签",
          mode: "single",
          value: currentValue,
          catalog,
          allowManual: pickerState.failed,
          onConfirm: (tag) => {
            if (tagIdInput) tagIdInput.value = tag?.tag_id || "";
            if (tagNameInput) tagNameInput.value = tag?.tag_name || "";
            if (tagGroupInput) tagGroupInput.value = tag?.group_name || "";
            renderSelectedMaterials();
          },
          onClear: () => {
            if (tagIdInput) tagIdInput.value = "";
            if (tagNameInput) tagNameInput.value = "";
            if (tagGroupInput) tagGroupInput.value = "";
            renderSelectedMaterials();
          },
        });
      });
    };

    openButton.addEventListener("click", openPicker);
    root.addEventListener("click", (event) => {
      const button = event.target.closest("[data-remove-picked]");
      if (!button) return;
      const kind = button.dataset.removePicked;
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
          initial_audience_code: "pending_questionnaire",
          operator_id: "next_admin",
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

  safeInit("ChannelSearch", setupChannelSearch);
  safeInit("CopyShare", setupCopyShare);
  safeInit("ChannelDrawer", setupChannelDrawer);
  safeInit("ChannelForm", setupChannelForm);
  safeInit("ChannelOwnerPicker", setupChannelOwnerPicker);
  safeInit("WelcomeComposer", setupWelcomeComposer);
  safeInit("EntryTagPicker", setupEntryTagPicker);
  safeInit("BindModal", setupBindModal);
  safeInit("ImportPanel", setupImportPanel);
  safeInit("EntryActions", setupEntryActions);
})();
