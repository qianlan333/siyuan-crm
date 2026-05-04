(function () {
  "use strict";

  const AutomationAgentConfig = window.AutomationAgentConfig || {};
  window.AutomationAgentConfig = AutomationAgentConfig;

  const state = AutomationAgentConfig.state || {};

  function showTemplateFormFeedback(message, tone) {
    const { templateFormFeedback } = AutomationAgentConfig.elements();
    if (!templateFormFeedback) return;
    if (!message) {
      templateFormFeedback.hidden = true;
      templateFormFeedback.textContent = "";
      templateFormFeedback.className = "ac-config-feedback";
      return;
    }
    templateFormFeedback.hidden = false;
    templateFormFeedback.textContent = message;
    templateFormFeedback.className = "ac-config-feedback" + (tone === "error" ? " is-error" : tone === "success" ? " is-success" : "");
  }

  function selectedCatalogQuestionnaire() {
    const templateFields = AutomationAgentConfig.templateFields();
    const questionnaireId = Number((templateFields.questionnaireId || {}).value || 0);
    return state.templateCatalog.find((item) => Number(item.id || 0) === questionnaireId) || null;
  }

  function selectedCatalogQuestion() {
    const templateFields = AutomationAgentConfig.templateFields();
    const questionnaire = selectedCatalogQuestionnaire();
    const questionId = Number((templateFields.segmentationQuestionId || {}).value || 0);
    return ((questionnaire || {}).questions || []).find((item) => Number(item.id || 0) === questionId) || null;
  }

  function currentQuestionOptions() {
    return (selectedCatalogQuestion() || {}).options || [];
  }

  function renderTemplateCatalog() {
    const templateFields = AutomationAgentConfig.templateFields();
    const select = templateFields.questionnaireId;
    if (!select) return;
    const escapeHtml = AutomationAgentConfig.escapeHtml;
    select.innerHTML = '<option value="">请选择问卷</option>' + state.templateCatalog.map((item) => (
      `<option value="${escapeHtml(item.id)}">${escapeHtml(item.name || item.slug || item.id)}</option>`
    )).join("");
  }

  function renderSegmentationQuestionOptions() {
    const templateFields = AutomationAgentConfig.templateFields();
    const questionnaire = selectedCatalogQuestionnaire();
    const select = templateFields.segmentationQuestionId;
    if (!select) return;
    const escapeHtml = AutomationAgentConfig.escapeHtml;
    const questions = ((questionnaire || {}).questions || []).filter((item) => ["single_choice", "multi_choice"].includes(String(item.type || "")));
    select.innerHTML = '<option value="">请选择分层题目</option>' + questions.map((item) => (
      `<option value="${escapeHtml(item.id)}">${escapeHtml(item.title || item.id)} · ${escapeHtml(item.type || "")}</option>`
    )).join("");
  }

  function renderTemplateCategories() {
    const { categoryList } = AutomationAgentConfig.elements();
    if (!categoryList) return;
    const escapeHtml = AutomationAgentConfig.escapeHtml;
    const options = currentQuestionOptions();
    categoryList.innerHTML = state.categoryDrafts.map((category, index) => `
      <section class="ac-config-category-card" data-category-index="${escapeHtml(index)}">
        <div class="ac-config-head">
          <div>
            <strong>分类 ${escapeHtml(index + 1)}</strong>
            <p class="ac-config-muted">一个分类可绑定多个问卷选项。</p>
          </div>
          <button class="admin-button admin-button--ghost" type="button" data-category-remove="${escapeHtml(index)}">删除</button>
        </div>
        <div class="ac-config-form-grid">
          <label class="admin-field">
            <span>分类名称</span>
            <input type="text" data-field="category_name" data-index="${escapeHtml(index)}" value="${escapeHtml(category.category_name || "")}" placeholder="例如：高意向用户">
          </label>
          <label class="admin-field">
            <span>category_key</span>
            <input type="text" data-field="category_key" data-index="${escapeHtml(index)}" value="${escapeHtml(category.category_key || "")}" placeholder="可选，不填则后端自动生成">
          </label>
        </div>
        <label class="admin-field">
          <span>说明</span>
          <textarea rows="3" data-field="description" data-index="${escapeHtml(index)}" placeholder="补充分类说明">${escapeHtml(category.description || "")}</textarea>
        </label>
        <label class="admin-checkbox">
          <input type="checkbox" data-field="enabled" data-index="${escapeHtml(index)}" ${category.enabled === false ? "" : "checked"}>
          <span>启用该分类</span>
        </label>
        <div class="ac-config-option-grid">
          ${options.map((option) => `
            <label class="ac-config-option-item">
              <input
                type="checkbox"
                data-field="option_ids"
                data-index="${escapeHtml(index)}"
                value="${escapeHtml(option.id)}"
                ${(category.option_ids || []).includes(Number(option.id || 0)) ? "checked" : ""}
              >
              <span>${escapeHtml(option.option_text || option.id)}</span>
            </label>
          `).join("") || '<div class="ac-config-empty">请先选择可分层的单选题或多选题。</div>'}
        </div>
      </section>
    `).join("") || '<div class="ac-config-empty">当前还没有分类，请先新增分类。</div>';
  }

  function renderTemplateRow(item) {
    const escapeHtml = AutomationAgentConfig.escapeHtml;
    const template = item.template || {};
    const questionnaire = item.questionnaire || {};
    const question = item.segmentation_question || {};
    const validity = item.validity || {};
    const isActive = Number(template.id || 0) === Number(state.selectedTemplateId || 0);
    const status = template.enabled
      ? (validity.is_valid === false ? "启用（无效）" : "启用")
      : (validity.is_valid === false ? "停用（待修复）" : "停用");
    return `
      <tr class="is-clickable${isActive ? " is-active" : ""}" data-template-id="${escapeHtml(template.id)}">
        <td>
          <strong>${escapeHtml(template.template_name || template.template_code || "-")}</strong>
          <div class="ac-config-code">${escapeHtml(template.template_code || "")}</div>
        </td>
        <td>${escapeHtml(questionnaire.name || "-")} / ${escapeHtml(question.title || "-")}</td>
        <td>${escapeHtml((item.categories || []).length)}</td>
        <td>${escapeHtml(status)}</td>
        <td>${escapeHtml(template.updated_at || "-")}</td>
      </tr>
    `;
  }

  function renderTemplateTable() {
    const { templateTableBody, templateEmpty } = AutomationAgentConfig.elements();
    if (templateTableBody) {
      templateTableBody.innerHTML = state.templates.map(renderTemplateRow).join("");
    }
    if (templateEmpty) {
      templateEmpty.hidden = state.templates.length > 0;
    }
  }

  function renderTemplateDetail() {
    const elements = AutomationAgentConfig.elements();
    const escapeHtml = AutomationAgentConfig.escapeHtml;
    const detail = state.selectedTemplateDetail;
    if (!detail) {
      if (elements.templateDetailPanel) elements.templateDetailPanel.hidden = true;
      return;
    }
    const template = detail.template || {};
    const questionnaire = detail.questionnaire || {};
    const question = detail.segmentation_question || {};
    const validity = detail.validity || {};
    const validityMessages = Array.isArray(validity.reason_messages) ? validity.reason_messages.filter(Boolean) : [];
    elements.templateDetailPanel.hidden = false;
    elements.templateDetailTitle.textContent = template.template_name || template.template_code || "模板详情";
    elements.templateDetailCode.textContent = "template_code=" + (template.template_code || "-");
    elements.templateDetailSummary.innerHTML = `
      <div><dt>问卷</dt><dd>${escapeHtml(questionnaire.name || "-")}</dd></div>
      <div><dt>分层题目</dt><dd>${escapeHtml(question.title || "-")}</dd></div>
      <div><dt>分类数</dt><dd>${escapeHtml((detail.categories || []).length)}</dd></div>
      <div><dt>状态</dt><dd>${escapeHtml(template.enabled ? (validity.is_valid === false ? "启用（无效）" : "启用") : (validity.is_valid === false ? "停用（待修复）" : "停用"))}</dd></div>
      <div><dt>有效性</dt><dd>${escapeHtml(validity.is_valid === false ? "无效" : "有效")}</dd></div>
      <div><dt>版本</dt><dd>${escapeHtml(template.version || 1)}</dd></div>
      <div><dt>说明</dt><dd>${escapeHtml(template.description || "暂无描述")}</dd></div>
      <div><dt>校验结果</dt><dd>${escapeHtml(validity.is_valid === false ? (validityMessages.join("；") || "模板结构不完整，请修复后再启用。") : "模板结构完整，可用于自然画像分层。")}</dd></div>
    `;
    elements.templateDetailCategories.innerHTML = (detail.categories || []).map((category) => `
      <section class="ac-config-category-card">
        <div>
          <strong>${escapeHtml(category.category_name || category.category_key || "-")}</strong>
          <p class="ac-config-code">${escapeHtml(category.category_key || "")}</p>
          <p class="ac-config-muted">${escapeHtml(category.description || "暂无说明")}</p>
        </div>
        <div class="ac-config-option-grid">
          ${(category.option_mappings || []).map((mapping) => `
            <div class="ac-config-option-item">
              <span>${escapeHtml((((mapping || {}).option) || {}).option_text || String(mapping.option_id || "-"))}</span>
            </div>
          `).join("") || '<div class="ac-config-empty">当前分类未绑定选项。</div>'}
        </div>
      </section>
    `).join("") || '<div class="ac-config-empty">当前模板还没有分类。</div>';
  }

  function normalizeTemplateBundle(payload) {
    if (payload && payload.template_bundle) {
      return payload.template_bundle;
    }
    if (payload && payload.template) {
      return payload;
    }
    return null;
  }

  function resetTemplateForm() {
    const elements = AutomationAgentConfig.elements();
    const templateFields = AutomationAgentConfig.templateFields();
    if (elements.templateForm) elements.templateForm.reset();
    if (templateFields.templateId) templateFields.templateId.value = "";
    renderTemplateCatalog();
    renderSegmentationQuestionOptions();
    state.categoryDrafts = [];
    renderTemplateCategories();
    showTemplateFormFeedback("", "");
  }

  function populateTemplateForm(detail) {
    const templateFields = AutomationAgentConfig.templateFields();
    const template = (detail || {}).template || {};
    if (templateFields.templateId) templateFields.templateId.value = String(template.id || "");
    if (templateFields.templateName) templateFields.templateName.value = template.template_name || "";
    if (templateFields.templateCode) templateFields.templateCode.value = template.template_code || "";
    if (templateFields.description) templateFields.description.value = template.description || "";
    if (templateFields.questionnaireId) templateFields.questionnaireId.value = template.questionnaire_id || "";
    renderSegmentationQuestionOptions();
    if (templateFields.segmentationQuestionId) templateFields.segmentationQuestionId.value = template.segmentation_question_id || "";
    if (templateFields.enabled) templateFields.enabled.checked = !!template.enabled;
    state.categoryDrafts = ((detail || {}).categories || []).map((item) => ({
      category_key: item.category_key || "",
      category_name: item.category_name || "",
      description: item.description || "",
      enabled: item.enabled !== false,
      option_ids: Array.isArray(item.option_ids) ? item.option_ids.map((value) => Number(value || 0)).filter(Boolean) : [],
    }));
    renderTemplateCategories();
  }

  function openTemplateForm(mode, detail) {
    const elements = AutomationAgentConfig.elements();
    const templateFields = AutomationAgentConfig.templateFields();
    if (!elements.templateFormPanel) return;
    elements.templateFormPanel.hidden = false;
    elements.templateFormTitle.textContent = mode === "edit" ? "编辑分层模板" : "新建分层模板";
    resetTemplateForm();
    if (mode === "edit" && detail) {
      populateTemplateForm(detail);
    } else if (templateFields.enabled) {
      templateFields.enabled.checked = true;
    }
    renderTemplateCategories();
    elements.templateFormPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    if (templateFields.templateName) {
      requestAnimationFrame(() => templateFields.templateName.focus());
    }
  }

  function closeTemplateForm() {
    const { templateFormPanel } = AutomationAgentConfig.elements();
    if (templateFormPanel) templateFormPanel.hidden = true;
    showTemplateFormFeedback("", "");
  }

  function collectTemplatePayload() {
    const templateFields = AutomationAgentConfig.templateFields();
    const templateId = Number((templateFields.templateId || {}).value || 0);
    const questionnaireId = Number((templateFields.questionnaireId || {}).value || 0);
    const questionId = Number((templateFields.segmentationQuestionId || {}).value || 0);
    const categories = state.categoryDrafts.map((item) => ({
      category_key: String(item.category_key || "").trim(),
      category_name: String(item.category_name || "").trim(),
      description: String(item.description || "").trim(),
      enabled: item.enabled !== false,
      option_ids: Array.isArray(item.option_ids) ? item.option_ids.map((value) => Number(value || 0)).filter(Boolean) : [],
    }));
    const payload = {
      template_name: String((templateFields.templateName || {}).value || "").trim(),
      template_code: String((templateFields.templateCode || {}).value || "").trim(),
      description: String((templateFields.description || {}).value || "").trim(),
      questionnaire_id: questionnaireId || null,
      segmentation_question_id: questionId || null,
      enabled: !!((templateFields.enabled || {}).checked),
      categories,
    };
    if (!payload.template_name) throw new Error("模板名称不能为空");
    const requiresCompleteTemplate = !templateId || payload.enabled;
    if (requiresCompleteTemplate) {
      if (!payload.questionnaire_id) throw new Error("请选择问卷");
      if (!payload.segmentation_question_id) throw new Error("请选择分层题目");
      if (!categories.length) throw new Error("请至少配置一个分类");
      categories.forEach((item, index) => {
        if (!item.category_name) throw new Error(`分类 ${index + 1} 的名称不能为空`);
        if (item.enabled !== false && !item.option_ids.length) throw new Error(`启用分类 ${index + 1} 至少要绑定一个问卷选项`);
      });
    }
    return payload;
  }

  async function loadTemplateDetail(templateId) {
    const apiUrls = AutomationAgentConfig.getApiUrls();
    const normalizedId = Number(templateId || 0);
    if (!normalizedId) {
      state.selectedTemplateId = null;
      state.selectedTemplateDetail = null;
      renderTemplateTable();
      renderTemplateDetail();
      return null;
    }
    const payload = await AutomationAgentConfig.requestJson(
      AutomationAgentConfig.withId(apiUrls.profile_segment_template_detail_base, normalizedId),
      { credentials: "same-origin" },
    );
    const bundle = normalizeTemplateBundle(payload);
    if (!bundle) {
      throw new Error("模板详情返回数据不完整");
    }
    state.selectedTemplateId = normalizedId;
    state.selectedTemplateDetail = bundle;
    renderTemplateTable();
    renderTemplateDetail();
    return bundle;
  }

  async function refreshTemplates() {
    const apiUrls = AutomationAgentConfig.getApiUrls();
    const [templateResult, catalogResult] = await Promise.all([
      AutomationAgentConfig.requestJson(apiUrls.profile_segment_templates, { credentials: "same-origin" }),
      AutomationAgentConfig.requestJson(apiUrls.profile_segment_template_catalog, { credentials: "same-origin" }),
    ]);
    state.templates = templateResult.items || [];
    state.templateCatalog = catalogResult.items || [];
    AutomationAgentConfig.updateSummaryCounters();
    renderTemplateTable();
    renderTemplateCatalog();
    renderSegmentationQuestionOptions();
    if (state.templates.length) {
      const targetId = state.templates.some((item) => Number((((item || {}).template) || {}).id || 0) === Number(state.selectedTemplateId || 0))
        ? state.selectedTemplateId
        : Number((((state.templates[0] || {}).template) || {}).id || 0);
      if (targetId) {
        await loadTemplateDetail(targetId);
      }
    } else {
      state.selectedTemplateId = null;
      state.selectedTemplateDetail = null;
      renderTemplateDetail();
    }
  }

  async function saveTemplate() {
    const elements = AutomationAgentConfig.elements();
    const templateFields = AutomationAgentConfig.templateFields();
    const apiUrls = AutomationAgentConfig.getApiUrls();
    const templateId = Number((templateFields.templateId || {}).value || 0);
    const payload = collectTemplatePayload();
    const url = templateId
      ? AutomationAgentConfig.withId(apiUrls.profile_segment_template_detail_base, templateId)
      : apiUrls.profile_segment_templates;
    // The template API keeps the legacy JSON payload unchanged; admin_action_token remains handled by endpoints that require it.
    const result = await AutomationAgentConfig.requestJson(url, {
      method: templateId ? "PUT" : "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const savedId = Number((((result || {}).template_bundle || {}).template || {}).id || templateId || 0);
    showTemplateFormFeedback(templateId ? "模板已更新" : "模板已创建", "success");
    await refreshTemplates();
    if (savedId) {
      await loadTemplateDetail(savedId);
    }
    closeTemplateForm();
    AutomationAgentConfig.showFeedback(templateId ? "模板已更新" : "模板已创建", "success");
    if (elements.templateFormPanel) elements.templateFormPanel.hidden = true;
  }

  function initializeTemplates() {
    AutomationAgentConfig.updateSummaryCounters();
    renderTemplateTable();
    renderTemplateCatalog();
    renderSegmentationQuestionOptions();
    if (state.templates.length) {
      const matched = state.templates.find((item) => Number((((item || {}).template) || {}).id || 0) === Number(state.selectedTemplateId || 0));
      state.selectedTemplateDetail = matched || state.templates[0] || null;
      state.selectedTemplateId = Number((((state.selectedTemplateDetail || {}).template) || {}).id || 0) || null;
      renderTemplateTable();
      renderTemplateDetail();
    } else {
      state.selectedTemplateDetail = null;
      state.selectedTemplateId = null;
      renderTemplateDetail();
    }
  }

  function addTemplateCategory() {
    state.categoryDrafts.push({
      category_key: "",
      category_name: "",
      description: "",
      enabled: true,
      option_ids: [],
    });
    renderTemplateCategories();
  }

  function removeTemplateCategory(index) {
    const normalizedIndex = Number(index || -1);
    if (normalizedIndex < 0) return;
    state.categoryDrafts.splice(normalizedIndex, 1);
    renderTemplateCategories();
  }

  function updateTemplateCategory(target) {
    const index = Number(target.dataset.index || -1);
    const field = String(target.dataset.field || "");
    if (index < 0 || !field || !state.categoryDrafts[index]) return;
    if (field === "enabled") {
      state.categoryDrafts[index].enabled = !!target.checked;
      return;
    }
    if (field === "option_ids") {
      const nextSet = new Set(state.categoryDrafts[index].option_ids || []);
      const optionId = Number(target.value || 0);
      if (target.checked) nextSet.add(optionId);
      else nextSet.delete(optionId);
      state.categoryDrafts[index].option_ids = Array.from(nextSet);
      return;
    }
    state.categoryDrafts[index][field] = target.value;
  }

  function bindTemplateInteractions() {
    const elements = AutomationAgentConfig.elements();
    const templateFields = AutomationAgentConfig.templateFields();
    if (elements.templateCreateButton) {
      elements.templateCreateButton.addEventListener("click", function () {
        openTemplateForm("create");
      });
    }

    if (elements.templateEditButton) {
      elements.templateEditButton.addEventListener("click", function () {
        if (!state.selectedTemplateDetail) return;
        openTemplateForm("edit", state.selectedTemplateDetail);
      });
    }

    if (elements.templateFormCancel) {
      elements.templateFormCancel.addEventListener("click", function () {
        closeTemplateForm();
      });
    }

    if (elements.categoryAddButton) {
      elements.categoryAddButton.addEventListener("click", addTemplateCategory);
    }

    if (elements.templateTableBody) {
      elements.templateTableBody.addEventListener("click", function (event) {
        const row = event.target.closest("tr[data-template-id]");
        if (!row) return;
        loadTemplateDetail(Number(row.dataset.templateId || 0)).catch((error) => {
          AutomationAgentConfig.showFeedback(error.message || "加载模板详情失败", "error");
        });
      });
    }

    if (templateFields.questionnaireId) {
      templateFields.questionnaireId.addEventListener("change", function () {
        renderSegmentationQuestionOptions();
        state.categoryDrafts = state.categoryDrafts.map((item) => ({ ...item, option_ids: [] }));
        renderTemplateCategories();
      });
    }

    if (templateFields.segmentationQuestionId) {
      templateFields.segmentationQuestionId.addEventListener("change", function () {
        state.categoryDrafts = state.categoryDrafts.map((item) => ({ ...item, option_ids: [] }));
        renderTemplateCategories();
      });
    }

    if (elements.categoryList) {
      elements.categoryList.addEventListener("click", function (event) {
        const button = event.target.closest("button[data-category-remove]");
        if (!button) return;
        removeTemplateCategory(button.dataset.categoryRemove || -1);
      });

      elements.categoryList.addEventListener("input", function (event) {
        updateTemplateCategory(event.target);
      });

      elements.categoryList.addEventListener("change", function (event) {
        updateTemplateCategory(event.target);
      });
    }

    if (elements.templateForm) {
      elements.templateForm.addEventListener("submit", function (event) {
        event.preventDefault();
        saveTemplate().catch((error) => {
          showTemplateFormFeedback(error.message || "保存模板失败", "error");
        });
      });
    }
  }

  AutomationAgentConfig.showTemplateFormFeedback = showTemplateFormFeedback;
  AutomationAgentConfig.selectedCatalogQuestionnaire = selectedCatalogQuestionnaire;
  AutomationAgentConfig.selectedCatalogQuestion = selectedCatalogQuestion;
  AutomationAgentConfig.currentQuestionOptions = currentQuestionOptions;
  AutomationAgentConfig.renderTemplateCatalog = renderTemplateCatalog;
  AutomationAgentConfig.renderSegmentationQuestionOptions = renderSegmentationQuestionOptions;
  AutomationAgentConfig.renderTemplateCategories = renderTemplateCategories;
  AutomationAgentConfig.renderTemplateRow = renderTemplateRow;
  AutomationAgentConfig.renderTemplateTable = renderTemplateTable;
  AutomationAgentConfig.renderTemplateDetail = renderTemplateDetail;
  AutomationAgentConfig.normalizeTemplateBundle = normalizeTemplateBundle;
  AutomationAgentConfig.populateTemplateForm = populateTemplateForm;
  AutomationAgentConfig.openTemplateForm = openTemplateForm;
  AutomationAgentConfig.closeTemplateForm = closeTemplateForm;
  AutomationAgentConfig.collectTemplatePayload = collectTemplatePayload;
  AutomationAgentConfig.loadTemplateDetail = loadTemplateDetail;
  AutomationAgentConfig.refreshTemplates = refreshTemplates;
  AutomationAgentConfig.saveTemplate = saveTemplate;
  AutomationAgentConfig.initializeTemplates = initializeTemplates;
  AutomationAgentConfig.addTemplateCategory = addTemplateCategory;
  AutomationAgentConfig.removeTemplateCategory = removeTemplateCategory;
  AutomationAgentConfig.updateTemplateCategory = updateTemplateCategory;
  AutomationAgentConfig.bindTemplateInteractions = bindTemplateInteractions;
})();
