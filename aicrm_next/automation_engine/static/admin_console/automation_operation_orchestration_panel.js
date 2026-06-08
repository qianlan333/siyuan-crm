(() => {
  function initOperationPanel(root) {
    if (!root || root.dataset.operationPanelReady === "1") return;

    const apiUrls = JSON.parse(root.dataset.apiUrls || "{}");
    const programId = Number(root.dataset.programId || 0);
    const endpoints = {
      tasks: apiUrls.operation_tasks || apiUrls.tasks || `/api/admin/automation-conversion/programs/${programId}/setup/operation-tasks`,
      taskBase:
        apiUrls.operation_task_base ||
        apiUrls.task_detail_base ||
        apiUrls.task_base ||
        `/api/admin/automation-conversion/programs/${programId}/setup/operation-tasks/0`,
      taskGroups:
        apiUrls.task_groups ||
        apiUrls.groups ||
        `/api/admin/automation-conversion/programs/${programId}/setup/operation-task-groups`,
      taskGroupBase:
        apiUrls.task_group_detail_base ||
        `/api/admin/automation-conversion/programs/${programId}/setup/operation-task-groups/0`,
      taskCopyBase: apiUrls.task_copy_base || "",
      taskActivateBase: apiUrls.task_activate_base || "",
      taskPauseBase: apiUrls.task_pause_base || "",
      taskDeleteBase: apiUrls.task_delete_base || "",
      taskPreviewAudienceBase: apiUrls.task_preview_audience_base || "",
      profileOptions:
        apiUrls.profile_segment_templates_options ||
        "/api/admin/automation-conversion/profile-segment-templates/options",
      profileDetailBase:
        apiUrls.profile_segment_template_detail_base ||
        "/api/admin/automation-conversion/profile-segment-templates/0",
      agents: apiUrls.agents_options || apiUrls.agents || "/api/admin/automation-conversion/agents",
      behaviorRules: apiUrls.behavior_segment_rules || "/api/admin/automation-conversion/behavior-segment-rules",
    };
    const state = {
      groups: [],
      tasks: [],
      currentTask: null,
      profileTemplates: [],
      profileSegments: [],
      setupProfileSegments: [],
      behaviorRules: [],
      agents: [],
      agentLoadStatus: "idle",
      agentLoadMessage: "",
      preview: {},
    };
    const labels = {
      status: { draft: "草稿", active: "启用", paused: "停用", archived: "归档" },
      trigger: { scheduled_daily: "每天固定时间", audience_entered: "进入人群后" },
      audience: { pending_questionnaire: "待填问卷", operating: "运营中", converted: "已转化" },
    };
    const VALID_MODES = new Set(["unified", "profile_layered", "behavior_layered", "agent"]);
    const REASON_LABELS = {
      source_channel_missing: "缺少来源渠道",
      program_channel_not_matched: "来源渠道不属于当前方案",
      audience_code_not_matched: "目标人群不匹配",
      entry_reason_not_matched: "入池原因不匹配",
      day_offset_not_due: "触达日期未到",
      behavior_filter_not_matched: "行为分层不匹配",
      profile_segment_not_matched: "画像分层不匹配",
      content_missing: "发送内容缺失",
      external_contact_id_missing: "企微客户 ID 缺失",
    };
    const CONTRACT_LABELS = {
      content_missing: "统一内容缺失",
      profile_segment_template_missing: "画像模板缺失",
      segment_content_missing: "分层话术缺失",
      segment_content_incomplete: "分层话术不完整",
      behavior_segment_content_missing: "行为分层未覆盖所选分层，实时触发不会入队",
      agent_code_missing: "Agent 未配置",
      questionnaire_context_missing: "缺少问卷答案上下文",
      agent_runtime_content_missing: "缺少 Agent 发布提示词或任务生成要求",
      trigger_type_invalid: "触发方式不正确",
      behavior_filter_invalid: "行为过滤不正确",
      content_mode_invalid: "发送策略不正确",
    };
    const normalizeContentMode = (mode) => (VALID_MODES.has(String(mode || "")) ? String(mode) : "unified");
    const dom = {
      groupFilter: root.querySelector("[data-group-filter]"),
      taskSearch: root.querySelector("[data-task-search]"),
      groupSelect: root.querySelector("[data-field='group_id']"),
      list: root.querySelector("[data-task-list]"),
      form: root.querySelector("[data-task-form]"),
      empty: root.querySelector("[data-task-empty]"),
      feedback: root.querySelector("[data-task-feedback]"),
      listFeedback: root.querySelector("[data-task-list-feedback]"),
      previewTotal: root.querySelector("[data-preview-total]"),
      previewReasons: root.querySelector("[data-preview-reasons]"),
      strategyPanel: root.querySelector("[data-strategy-panel]"),
    };
    const escapeHtml = (value) =>
      String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
    const withId = (url, id) => String(url || "").replace(/\/0(?=\/|$)/, `/${encodeURIComponent(String(id || 0))}`);
    const currentId = () => Number((state.currentTask || {}).id || 0);
    const getField = (name) => root.querySelector(`[data-field="${name}"]`);
    const getValue = (name) => getField(name)?.value ?? "";
    const setValue = (name, value) => {
      const field = getField(name);
      if (field) field.value = value ?? "";
    };
    const showFeedback = (target, message, ok = false) => {
      if (!target) return;
      target.textContent = message;
      target.classList.toggle("is-success", ok);
      target.style.display = "block";
    };
    const clearFeedback = () =>
      [dom.feedback, dom.listFeedback].forEach((item) => {
        if (item) item.style.display = "none";
      });
    const requestJson = async (url, options = {}) => {
      const response = await fetch(url, {
        headers: { Accept: "application/json", "Content-Type": "application/json", ...(options.headers || {}) },
        ...options,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.ok === false) throw new Error(data.error || data.detail || "操作失败，请稍后重试");
      return data;
    };

    function operationContent(task = state.currentTask || {}) {
      const config = task.config && typeof task.config === "object" ? task.config : {};
      const content = task.operation_content || config.operation_content || {};
      return {
        content_mode: normalizeContentMode(content.content_mode || task.content_mode || "unified"),
        profile_segment_template_id: Number(content.profile_segment_template_id || task.profile_segment_template_id || 0),
        unified_content_json: content.unified_content_json || task.unified_content_json || {},
        segment_contents_json: Array.isArray(content.segment_contents_json || task.segment_contents_json)
          ? content.segment_contents_json || task.segment_contents_json
          : [],
        agent_config_json: content.agent_config_json || task.agent_config_json || {},
      };
    }

    function selectedTargetAudienceCode() {
      const selected = getField("target_stage_code")?.selectedOptions?.[0];
      return selected?.dataset.audienceCode || getValue("target_stage_code") || "operating";
    }

    function collectOperationTaskPayload(statusOverride = "") {
      const content = operationContent();
      return {
        task_name: String(getValue("task_name") || "新运营任务").trim(),
        group_id: Number(getValue("group_id") || 0) || null,
        status: statusOverride || getValue("status") || "draft",
        description: String(getValue("description") || "").trim(),
        trigger_type: getValue("trigger_type") || "scheduled_daily",
        send_time: getValue("send_time") || "10:00",
        timezone: "Asia/Shanghai",
        target_stage_code: getValue("target_stage_code") || selectedTargetAudienceCode(),
        target_audience_code: selectedTargetAudienceCode(),
        audience_day_offset: Math.max(Number(getValue("audience_day_offset") || 1), 1),
        behavior_filter: getValue("behavior_filter") || "none",
        content_mode: content.content_mode,
        profile_segment_template_id: content.profile_segment_template_id || null,
        unified_content_json: content.unified_content_json || {},
        segment_contents_json: content.segment_contents_json || [],
        agent_config_json: content.agent_config_json || {},
      };
    }

    function contentSummary(content, agent = false) {
      const text = String(content.content_text || "").trim();
      const total =
        (content.image_library_ids || []).length +
        (content.miniprogram_library_ids || []).length +
        (content.attachment_library_ids || []).length;
      if (agent) return total ? `已配置素材 ${total} 个` : "未配置素材";
      if (!text && !total) return "未配置";
      return `已配置 · ${text ? "有话术" : "无话术"} · ${total} 素材`;
    }

    function groupName(id) {
      const group = state.groups.find((item) => Number(item.id) === Number(id));
      return group ? group.group_name : "未分组";
    }

    function syncGroupControls() {
      const selectedFilter = dom.groupFilter?.value ?? "";
      const selectedGroup = dom.groupSelect?.value ?? "";
      const filterOptions = [`<option value="">全部分组</option>`, `<option value="0">未分组</option>`]
        .concat(state.groups.map((group) => `<option value="${group.id}">${escapeHtml(group.group_name)}</option>`))
        .join("");
      const taskOptions = [`<option value="">未分组</option>`]
        .concat(state.groups.map((group) => `<option value="${group.id}">${escapeHtml(group.group_name)}</option>`))
        .join("");
      if (dom.groupFilter) {
        dom.groupFilter.innerHTML = filterOptions;
        dom.groupFilter.value = selectedFilter;
      }
      if (dom.groupSelect) {
        dom.groupSelect.innerHTML = taskOptions;
        dom.groupSelect.value = selectedGroup;
      }
    }

    function filteredTasks() {
      const groupValue = dom.groupFilter?.value ?? "";
      const keyword = String(dom.taskSearch?.value || "").trim().toLowerCase();
      return state.tasks.filter((task) => {
        if (groupValue === "0" && task.group_id) return false;
        if (groupValue && groupValue !== "0" && Number(task.group_id || 0) !== Number(groupValue)) return false;
        if (keyword && !String(task.task_name || "").toLowerCase().includes(keyword)) return false;
        return String(task.status || "") !== "archived";
      });
    }

    function taskActionButtons(task) {
      const status = String(task.status || "draft");
      const toggle =
        status === "active"
          ? `<button class="op-task-button" type="button" data-task-action="pause">停用</button>`
          : `<button class="op-task-button is-soft" type="button" data-task-action="activate">启用</button>`;
      return `
        <div class="op-task-actions">
          <button class="op-task-button is-soft" type="button" data-task-action="edit">编辑</button>
          <button class="op-task-button" type="button" data-task-action="copy">复制</button>
          ${toggle}
          <button class="op-task-button" type="button" data-task-action="delete">删除</button>
        </div>`;
    }

    function runtimeContractSummary(task) {
      const contract = task.runtime_contract || {};
      const diagnostics = contract.diagnostics || {};
      const errors = Array.isArray(diagnostics.errors) ? diagnostics.errors : [];
      if (String(task.status || "") !== "active") {
        return { ok: true, text: "草稿/停用可保存不完整配置" };
      }
      if (!errors.length && (diagnostics.ok || contract.status === "executable")) {
        return { ok: true, text: "可执行" };
      }
      const text = errors.map((key) => CONTRACT_LABELS[key] || key).join("；") || "不可执行";
      return { ok: false, text };
    }

    function renderList() {
      if (!dom.list) return;
      const tasks = filteredTasks();
      if (!tasks.length) {
        dom.list.innerHTML = `<div class="op-task-empty">暂无任务</div>`;
        return;
      }
      const grouped = new Map();
      tasks.forEach((task) => {
        const key = task.group_id ? String(task.group_id) : "0";
        if (!grouped.has(key)) grouped.set(key, []);
        grouped.get(key).push(task);
      });
      dom.list.innerHTML = [...grouped.entries()]
        .map(
          ([key, items]) => `
        <section class="op-task-group">
          <div class="op-task-group__title">${escapeHtml(key === "0" ? "未分组" : groupName(key))}</div>
          ${items
            .map((task) => {
              const active = Number(task.id) === currentId();
              const status = String(task.status || "draft");
              const contract = runtimeContractSummary(task);
              return `<article class="op-task-item${active ? " is-active" : ""}" data-task-id="${task.id}">
                <div class="op-task-item__top"><strong>${escapeHtml(task.task_name || "未命名任务")}</strong><span class="op-task-badge is-${escapeHtml(status)}">${escapeHtml(labels.status[status] || status)}</span></div>
                <div class="op-task-muted">${escapeHtml(labels.trigger[task.trigger_type] || task.trigger_type || "每天固定时间")} · ${escapeHtml(labels.audience[task.target_audience_code] || task.target_audience_code || "运营中")}</div>
                <div class="op-task-muted">${escapeHtml(contract.ok ? "运行合同：可执行" : `运行合同：不可执行 · ${contract.text}`)}</div>
                ${taskActionButtons(task)}
              </article>`;
            })
            .join("")}
        </section>`
        )
        .join("");
    }

    function syncTriggerFields() {
      const triggerType = getValue("trigger_type") || "scheduled_daily";
      root.querySelectorAll("[data-scheduled-trigger-field]").forEach((field) => {
        field.disabled = triggerType === "audience_entered";
      });
    }

    function setCurrentTask(task) {
      state.currentTask = task ? { ...task } : null;
      dom.empty.hidden = Boolean(task);
      dom.form.hidden = !task;
      if (!task) {
        renderList();
        return;
      }
      const content = operationContent(task);
      setValue("task_name", task.task_name || "");
      setValue("group_id", task.group_id || "");
      setValue("status", task.status || "draft");
      setValue("description", task.description || "");
      setValue("trigger_type", task.trigger_type || "scheduled_daily");
      setValue("send_time", task.send_time || "10:00");
      setValue("target_stage_code", task.target_stage_code || task.target_audience_code || "operating");
      setValue("audience_day_offset", task.audience_day_offset || 1);
      setValue("behavior_filter", task.behavior_filter || "none");
      syncTriggerFields();
      setMode(content.content_mode, false);
      renderList();
    }

    async function refreshTask() {
      const data = await requestJson(withId(endpoints.taskBase, currentId()));
      const task = data.task;
      const index = state.tasks.findIndex((item) => Number(item.id) === Number(task.id));
      if (index >= 0) state.tasks[index] = task;
      setCurrentTask(task);
      return task;
    }

    async function loadProfileTemplates() {
      const data = await requestJson(endpoints.profileOptions);
      state.profileTemplates = mergeByValue(
        state.profileTemplates,
        normalizeProfileTemplates(data.items || data.options || data.templates || []),
        (item) => item.id ?? item.template_id ?? item.value
      );
    }

    function normalizeSegments(raw) {
      const rows = Array.isArray(raw) ? raw : [];
      return rows
        .map((item) => ({
          segment_key: item.segment_key || item.category_key || item.profile_segment_key || item.key || String(item.id || ""),
          segment_name:
            item.segment_name ||
            item.category_name ||
            item.profile_segment_name ||
            item.name ||
            item.label ||
            item.segment_key ||
            String(item.id || ""),
          hit_count: item.hit_count ?? item.count ?? item.preview_count,
        }))
        .filter((item) => item.segment_key);
    }

    function mergeByValue(primary, fallback, valueGetter) {
      const seen = new Set();
      return []
        .concat(primary || [], fallback || [])
        .filter((item) => {
          const rawValue = valueGetter(item);
          const value = String(rawValue ?? "").trim();
          if (!value || seen.has(value)) return false;
          seen.add(value);
          return true;
        });
    }

    function normalizeProfileTemplates(raw) {
      const rows = Array.isArray(raw) ? raw : [];
      return rows
        .map((item) => {
          const id = item.id ?? item.template_id ?? item.value ?? 0;
          const name = item.label || item.name || item.template_name || item.code || item.template_code || id;
          return { ...item, id, template_id: id, label: name, template_name: name };
        })
        .filter((item) => item.label || item.template_name);
    }

    async function loadProfileSegments(templateId) {
      if (!Number(templateId) && state.setupProfileSegments.length) {
        state.profileSegments = state.setupProfileSegments;
        return state.profileSegments;
      }
      if (!templateId) {
        state.profileSegments = [];
        return [];
      }
      const data = await requestJson(withId(endpoints.profileDetailBase, templateId));
      const bundle = data.template_bundle || data.bundle || data;
      const template = bundle.template || data.template || {};
      state.profileSegments = normalizeSegments(
        bundle.categories || bundle.segments || bundle.profile_segments || template.categories || template.segments || []
      );
      return state.profileSegments;
    }

    async function loadBehaviorRules() {
      const data = await requestJson(endpoints.behaviorRules);
      state.behaviorRules = data.rules || [];
    }

    async function loadAgents() {
      state.agentLoadStatus = "loading";
      state.agentLoadMessage = "";
      try {
        const data = await requestJson(endpoints.agents);
        state.agents = mergeByValue(data.items || data.agents || data.options || [], [], (agent) => agent.agent_code || agent.code || agent.value);
        state.agentLoadStatus = state.agents.length ? "ready" : "empty";
        state.agentLoadMessage = state.agents.length ? "" : "智能体列表为空，请检查 Agent 接口/生产数据源";
      } catch (error) {
        state.agents = [];
        state.agentLoadStatus = "error";
        state.agentLoadMessage = "智能体列表加载失败，请检查 Agent 接口/生产数据源";
        throw error;
      }
    }

    async function safeLoadAuxiliary() {
      const results = await Promise.allSettled([loadProfileTemplates(), loadBehaviorRules(), loadAgents()]);
      results.forEach((result) => {
        if (result.status === "rejected") {
          console.warn("[automation_operation_orchestration_panel] auxiliary load failed", result.reason);
        }
      });
    }

    async function loadTasks() {
      const data = await requestJson(endpoints.tasks);
      state.groups = data.groups || [];
      state.tasks = data.tasks || data.items || [];
      const setupTemplates = normalizeProfileTemplates(data.profile_templates || data.profile_segment_templates || []);
      const setupSegments = normalizeSegments(data.profile_segments || data.segmentation_profile_segments || []);
      state.profileTemplates = mergeByValue(setupTemplates, state.profileTemplates, (item) => item.id ?? item.template_id ?? item.value);
      state.setupProfileSegments = setupSegments;
      if (setupSegments.length) state.profileSegments = setupSegments;
      syncGroupControls();
      const selected = state.currentTask ? state.tasks.find((item) => Number(item.id) === currentId()) : state.tasks[0];
      setCurrentTask(selected || null);
    }

    async function saveBaseTask(statusOverride = "", silent = false) {
      if (!state.currentTask) throw new Error("请先选择一个运营任务");
      const data = await requestJson(withId(endpoints.taskBase, currentId()), {
        method: "PUT",
        body: JSON.stringify(collectOperationTaskPayload(statusOverride)),
      });
      const task = data.task;
      const index = state.tasks.findIndex((item) => Number(item.id) === Number(task.id));
      if (index >= 0) state.tasks[index] = task;
      setCurrentTask(task);
      if (!silent) showFeedback(dom.feedback, "任务已保存", true);
      return task;
    }

    async function createTask() {
      const selectedGroupId = dom.groupFilter?.value && dom.groupFilter.value !== "0" ? Number(dom.groupFilter.value) : null;
      const data = await requestJson(endpoints.tasks, {
        method: "POST",
        body: JSON.stringify({
          task_name: "新运营任务",
          group_id: selectedGroupId,
          status: "draft",
          trigger_type: "scheduled_daily",
          send_time: "10:00",
          target_stage_code: "operating",
          target_audience_code: "operating",
          audience_day_offset: 1,
          behavior_filter: "none",
          content_mode: "unified",
          unified_content_json: {},
          segment_contents_json: [],
          agent_config_json: {},
        }),
      });
      state.tasks.unshift(data.task);
      syncGroupControls();
      setCurrentTask(data.task);
      showFeedback(dom.listFeedback, "已新增运营任务", true);
    }

    async function createGroup() {
      const name = String(window.prompt("请输入分组名称", "") || "").trim();
      if (!name) return;
      const data = await requestJson(endpoints.taskGroups, { method: "POST", body: JSON.stringify({ group_name: name }) });
      const group = data.group || (data.groups || [])[0];
      if (group) state.groups.push(group);
      syncGroupControls();
      if (group && dom.groupFilter) dom.groupFilter.value = String(group.id);
      renderList();
      showFeedback(dom.listFeedback, "已新增分组", true);
    }

    async function deleteSelectedGroup() {
      const groupId = Number(dom.groupFilter?.value || getValue("group_id") || 0);
      if (!groupId) {
        showFeedback(dom.listFeedback, "请先在左侧选择一个分组");
        return;
      }
      const group = state.groups.find((item) => Number(item.id) === groupId);
      if (!window.confirm(`确认删除分组「${group?.group_name || groupId}」？分组内任务会回到未分组。`)) return;
      await requestJson(withId(endpoints.taskGroupBase, groupId), { method: "DELETE" });
      state.groups = state.groups.filter((item) => Number(item.id) !== groupId);
      state.tasks = state.tasks.map((task) => (Number(task.group_id || 0) === groupId ? { ...task, group_id: null, group_name: "未分组" } : task));
      if (dom.groupFilter) dom.groupFilter.value = "";
      syncGroupControls();
      setCurrentTask(state.currentTask ? state.tasks.find((item) => Number(item.id) === currentId()) || null : state.tasks[0] || null);
      showFeedback(dom.listFeedback, "分组已删除", true);
    }

    async function previewAudience() {
      if (!state.currentTask) return;
      state.preview = {};
      dom.previewTotal.textContent = "-";
      if (dom.previewReasons) dom.previewReasons.textContent = "";
      const previewUrl = endpoints.taskPreviewAudienceBase || `${withId(endpoints.taskBase, currentId())}/preview-audience`;
      const data = await requestJson(withId(previewUrl, currentId()), {
        method: "POST",
        body: JSON.stringify(collectOperationTaskPayload()),
      });
      state.preview = data.preview || {};
      dom.previewTotal.textContent = state.preview.target_count ?? state.preview.total ?? 0;
      const filtered = state.preview.filtered_out_counts || {};
      const reasonText = Object.keys(filtered)
        .filter((key) => Number(filtered[key] || 0) > 0)
        .map((key) => `${REASON_LABELS[key] || key} ${Number(filtered[key] || 0)}`)
        .join("；");
      const diagnostics = state.preview.content_diagnostics || {};
      const diagnosticText = (diagnostics.errors || []).map((key) => CONTRACT_LABELS[key] || key).join("；");
      const agent = state.preview.agent_runtime_diagnostics || {};
      const agentText =
        Object.keys(agent).length && !agent.expected_send_body_present
          ? agent.questionnaire_context_required && !agent.questionnaire_context_available
            ? "Agent 需要问卷答案上下文"
            : "缺少 Agent 发布提示词或任务生成要求"
          : "";
      if (dom.previewReasons) {
        dom.previewReasons.textContent = [reasonText ? `未命中：${reasonText}` : "", diagnosticText ? `内容诊断：${diagnosticText}` : "", agentText]
          .filter(Boolean)
          .join("；");
      }
      showFeedback(dom.feedback, "命中人群已刷新", true);
    }

    async function updateStrategy(payload) {
      await saveBaseTask("", true);
      const data = await requestJson(`${withId(endpoints.taskBase, currentId())}/send-strategy`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      const task = data.task;
      const index = state.tasks.findIndex((item) => Number(item.id) === Number(task.id));
      if (index >= 0) state.tasks[index] = task;
      setCurrentTask(task);
      return task;
    }

    async function saveContent(url, body) {
      await saveBaseTask("", true);
      await requestJson(url, { method: "PUT", body: JSON.stringify(body) });
      await refreshTask();
      showFeedback(dom.feedback, "发送内容已保存", true);
    }

    function findSegmentContent(segmentKey) {
      const content = operationContent();
      const row = (content.segment_contents_json || []).find((item) => String(item.segment_key) === String(segmentKey));
      return row?.content_package || row || {};
    }

    function renderUnified(content) {
      const unified = content.unified_content_json || {};
      return `
        <div class="op-task-strategy-head">
          <div><h4>统一内容</h4><div class="op-task-muted">${escapeHtml(contentSummary(unified))}</div></div>
          <button class="op-task-button is-soft" type="button" data-config-unified>配置话术和素材</button>
        </div>`;
    }

    function renderProfile(content) {
      const selectedTemplateId = Number(content.profile_segment_template_id || 0);
      const templates = normalizeProfileTemplates(state.profileTemplates);
      const options = [`<option value="">请选择分层规则</option>`]
        .concat(
          templates.map((item) => {
            const id = item.id ?? item.template_id ?? item.value ?? "";
            const name = item.label || item.name || item.template_name || item.code || id;
            return `<option value="${escapeHtml(id)}" ${Number(id) === selectedTemplateId ? "selected" : ""}>${escapeHtml(name)}</option>`;
          })
        )
        .join("");
      const rows = state.profileSegments.length
        ? state.profileSegments
            .map((segment) => {
              const current = findSegmentContent(segment.segment_key);
              const count = segment.hit_count === undefined ? "" : `<span class="op-task-chip">${Number(segment.hit_count)} 人</span>`;
              return `<article class="op-task-segment" data-profile-segment="${escapeHtml(segment.segment_key)}" data-segment-name="${escapeHtml(segment.segment_name)}">
                <div class="op-task-segment-row">
                  <div><strong>${escapeHtml(segment.segment_name)}</strong><div class="op-task-muted">${escapeHtml(segment.segment_key)} ${count}</div><div class="op-task-muted">${escapeHtml(contentSummary(current))}</div></div>
                  <button class="op-task-button is-soft" type="button" data-config-profile-segment="${escapeHtml(segment.segment_key)}">配置话术和素材</button>
                </div>
              </article>`;
            })
            .join("")
        : `<div class="op-task-empty">当前方案分层规则还没有可填写的分层，请先在第 3 步配置分层分类。</div>`;
      return `
        <label class="op-task-field"><span>分层规则</span><select data-profile-template-select>${options}</select></label>
        <div class="op-task-segments">${rows}</div>`;
    }

    function renderBehavior() {
      const rule = state.behaviorRules[0] || {
        rule_key: "default_message_count",
        rule_name: "默认：消息数三层",
        segments: [
          { segment_key: "lt_2", segment_name: "消息少于 2" },
          { segment_key: "between_2_9", segment_name: "消息 2-9" },
          { segment_key: "gte_10", segment_name: "消息大于等于 10" },
        ],
      };
      const rows = (rule.segments || [])
        .map((segment) => {
          const current = findSegmentContent(segment.segment_key);
          return `<article class="op-task-segment" data-behavior-segment="${escapeHtml(segment.segment_key)}" data-segment-name="${escapeHtml(segment.segment_name)}">
            <div class="op-task-segment-row">
              <div><strong>${escapeHtml(segment.segment_name)}</strong><div class="op-task-muted">${escapeHtml(segment.segment_key)}</div><div class="op-task-muted">${escapeHtml(contentSummary(current))}</div></div>
              <button class="op-task-button is-soft" type="button" data-config-behavior-segment="${escapeHtml(segment.segment_key)}">配置话术和素材</button>
            </div>
          </article>`;
        })
        .join("");
      return `
        <label class="op-task-field"><span>消息分层规则</span><select data-behavior-rule-select><option value="${escapeHtml(rule.rule_key)}">${escapeHtml(rule.rule_name || "默认：消息数三层")}</option></select></label>
        <div class="op-task-segments">${rows}</div>`;
    }

    function renderAgent(content) {
      const agentConfig = content.agent_config_json || {};
      const contractAgent = ((state.currentTask || {}).runtime_contract || {}).agent_runtime_diagnostics || {};
      const previewAgent = state.preview.agent_runtime_diagnostics || {};
      const runtimeAgent = Object.keys(previewAgent).length ? previewAgent : contractAgent;
      const options = [`<option value="">请选择智能体</option>`]
        .concat(
          state.agents.map((agent) => {
            const code = agent.agent_code || agent.code || agent.value || "";
            const name = agent.agent_name || agent.name || agent.label || code;
            return `<option value="${escapeHtml(code)}" ${String(agentConfig.agent_code || "") === String(code) ? "selected" : ""}>${escapeHtml(name)}</option>`;
          })
        )
        .join("");
      const statusMessage =
        state.agentLoadStatus === "error" || state.agentLoadStatus === "empty"
          ? `<div class="op-task-feedback" style="display:block">${escapeHtml(state.agentLoadMessage)}</div>`
          : "";
      const hasMaterial = []
        .concat(agentConfig.image_library_ids || [], agentConfig.miniprogram_library_ids || [], agentConfig.attachment_library_ids || [])
        .filter(Boolean).length > 0;
      const hasInstruction = Boolean(
        String(agentConfig.fallback_content || agentConfig.requirement || agentConfig.prompt || agentConfig.material_prompt || "").trim() ||
          String((state.currentTask || {}).description || "").trim()
      );
      const hasPublishedPrompt = Boolean(runtimeAgent.agent_published_prompt_present);
      const agentWarnings = [];
      if (!String(agentConfig.agent_code || "").trim()) agentWarnings.push("请选择智能体");
      if (!hasInstruction && !hasMaterial && !hasPublishedPrompt) agentWarnings.push("缺少 Agent 发布提示词或任务生成要求");
      const statusRows = [
        `已选择 Agent：${String(agentConfig.agent_code || "").trim() ? "是" : "否"}`,
        `已配置生成要求/兜底：${hasInstruction || hasMaterial ? "是" : "否"}`,
        `可使用 Agent 已发布提示词 + 问卷答案生成：${hasPublishedPrompt ? "是" : "待刷新命中人数确认"}`,
      ];
      return `
        <label class="op-task-field"><span>智能体</span><select data-agent-select>${options}</select></label>
        ${statusMessage}
        ${agentWarnings.length ? `<div class="op-task-feedback" style="display:block">${escapeHtml(agentWarnings.join("；"))}</div>` : ""}
        <div class="op-task-muted">${escapeHtml(statusRows.join("；"))}</div>
        <label class="op-task-field"><span>生成要求</span><textarea data-agent-requirement rows="3">${escapeHtml(agentConfig.requirement || agentConfig.prompt || "")}</textarea></label>
        <label class="op-task-field"><span>兜底话术</span><textarea data-agent-fallback rows="3">${escapeHtml(agentConfig.fallback_content || "")}</textarea></label>
        <div class="op-task-strategy-head">
          <div><h4>Agent 个性化配置</h4><div class="op-task-muted">${escapeHtml(contentSummary(agentConfig, true))}</div></div>
          <div class="op-task-actions">
            <button class="op-task-button is-soft" type="button" data-save-agent-text>保存生成要求</button>
            <button class="op-task-button is-soft" type="button" data-config-agent-materials>配置素材</button>
          </div>
        </div>`;
    }

    function renderStrategyPanel() {
      if (!state.currentTask) return;
      const content = operationContent();
      const mode = normalizeContentMode(content.content_mode || "unified");
      root.querySelectorAll("[data-mode]").forEach((button) => button.classList.toggle("is-active", button.dataset.mode === mode));
      if (mode === "profile_layered") dom.strategyPanel.innerHTML = renderProfile(content);
      else if (mode === "behavior_layered") dom.strategyPanel.innerHTML = renderBehavior(content);
      else if (mode === "agent") dom.strategyPanel.innerHTML = renderAgent(content);
      else dom.strategyPanel.innerHTML = renderUnified(content);
    }

    async function setMode(mode, updateTask = true) {
      if (!state.currentTask) return;
      mode = normalizeContentMode(mode);
      const content = operationContent();
      if (!updateTask) {
        renderStrategyPanel();
        return;
      }
      if (mode === "profile_layered") {
        await loadProfileTemplates().catch(() => {});
        await updateStrategy({ content_mode: "profile_layered", profile_segment_template_id: content.profile_segment_template_id || null });
        return;
      }
      if (mode === "behavior_layered") {
        await loadBehaviorRules().catch(() => {});
        await updateStrategy({ content_mode: "behavior_layered" });
        return;
      }
      if (mode === "agent") {
        await loadAgents().catch(() => {});
        await updateStrategy({ content_mode: "agent", agent_code: content.agent_config_json.agent_code || "" });
        return;
      }
      await updateStrategy({ content_mode: "unified" });
    }

    function openSendContentComposer(options) {
      if (!window.AICRMSendContentComposer || typeof window.AICRMSendContentComposer.open !== "function") {
        showFeedback(dom.feedback, "标准内容编辑器未加载，请刷新页面后重试");
        return;
      }
      window.AICRMSendContentComposer.open(options || {});
    }

    function openUnifiedComposer() {
      const content = operationContent();
      openSendContentComposer({
        title: "统一内容",
        textEnabled: true,
        value: content.unified_content_json || {},
        onConfirm: (contentPackage) =>
          saveContent(`${withId(endpoints.taskBase, currentId())}/send-content/unified`, { content_package: contentPackage }),
      });
    }

    function openProfileComposer(segmentKey, segmentName) {
      const content = operationContent();
      const templateId = Number(dom.strategyPanel.querySelector("[data-profile-template-select]")?.value || content.profile_segment_template_id || 0);
      if (!templateId && !state.setupProfileSegments.length) {
        showFeedback(dom.feedback, "请先选择分层规则");
        return;
      }
      openSendContentComposer({
        title: segmentName,
        textEnabled: true,
        value: findSegmentContent(segmentKey),
        onConfirm: (contentPackage) =>
          saveContent(`${withId(endpoints.taskBase, currentId())}/send-content/profile-segments/${encodeURIComponent(segmentKey)}`, {
            profile_segment_template_id: templateId,
            segment_name: segmentName,
            content_package: contentPackage,
          }),
      });
    }

    function openBehaviorComposer(segmentKey, segmentName) {
      openSendContentComposer({
        title: segmentName,
        textEnabled: true,
        value: findSegmentContent(segmentKey),
        onConfirm: (contentPackage) =>
          saveContent(`${withId(endpoints.taskBase, currentId())}/send-content/behavior-segments/${encodeURIComponent(segmentKey)}`, {
            segment_name: segmentName,
            content_package: contentPackage,
          }),
      });
    }

    function openAgentComposer() {
      const agentCode = String(dom.strategyPanel.querySelector("[data-agent-select]")?.value || "").trim();
      if (!agentCode) {
        showFeedback(dom.feedback, "请先选择智能体");
        return;
      }
      const config = operationContent().agent_config_json || {};
      openSendContentComposer({
        title: "Agent 个性化素材",
        textEnabled: true,
        value: {
          content_text: config.requirement || config.prompt || "",
          image_library_ids: config.image_library_ids || [],
          miniprogram_library_ids: config.miniprogram_library_ids || [],
          attachment_library_ids: config.attachment_library_ids || [],
        },
        onConfirm: (contentPackage) =>
          saveContent(`${withId(endpoints.taskBase, currentId())}/send-content/agent-materials`, {
            agent_code: agentCode,
            requirement: contentPackage.content_text || config.requirement || "",
            fallback_content: config.fallback_content || "",
            prompt: config.prompt || "",
            material_prompt: config.material_prompt || "",
            content_package: contentPackage,
          }),
      });
    }

    function saveAgentTextConfig() {
      const agentCode = String(dom.strategyPanel.querySelector("[data-agent-select]")?.value || "").trim();
      if (!agentCode) {
        showFeedback(dom.feedback, "请先选择智能体");
        return Promise.resolve();
      }
      const config = operationContent().agent_config_json || {};
      return saveContent(`${withId(endpoints.taskBase, currentId())}/send-content/agent-materials`, {
        agent_code: agentCode,
        requirement: String(dom.strategyPanel.querySelector("[data-agent-requirement]")?.value || "").trim(),
        fallback_content: String(dom.strategyPanel.querySelector("[data-agent-fallback]")?.value || "").trim(),
        prompt: config.prompt || "",
        material_prompt: config.material_prompt || "",
        content_package: {
          image_library_ids: config.image_library_ids || [],
          miniprogram_library_ids: config.miniprogram_library_ids || [],
          attachment_library_ids: config.attachment_library_ids || [],
        },
      });
    }

    async function runTaskAction(action, taskId) {
      if (action === "edit") {
        setCurrentTask(state.tasks.find((item) => Number(item.id) === taskId));
        return;
      }
      if (action === "delete" && !window.confirm("确认删除这个运营任务？")) return;
      const urlMap = {
        copy: endpoints.taskCopyBase || `${withId(endpoints.taskBase, taskId)}/copy`,
        activate: endpoints.taskActivateBase || `${withId(endpoints.taskBase, taskId)}/activate`,
        pause: endpoints.taskPauseBase || `${withId(endpoints.taskBase, taskId)}/pause`,
        delete: endpoints.taskDeleteBase || withId(endpoints.taskBase, taskId),
      };
      const data = await requestJson(withId(urlMap[action], taskId), { method: action === "delete" ? "DELETE" : "POST" });
      if (action === "copy" && data.task) {
        state.tasks.unshift(data.task);
        setCurrentTask(data.task);
      } else if (action === "delete") {
        state.tasks = state.tasks.filter((item) => Number(item.id) !== taskId);
        setCurrentTask(state.tasks[0] || null);
      } else if (data.task) {
        const index = state.tasks.findIndex((item) => Number(item.id) === Number(data.task.id));
        if (index >= 0) state.tasks[index] = data.task;
        setCurrentTask(data.task);
      }
      showFeedback(dom.listFeedback, "操作已保存", true);
    }

    root.addEventListener("click", async (event) => {
      try {
        clearFeedback();
        const modeButton = event.target.closest("[data-mode]");
        if (modeButton) await setMode(modeButton.dataset.mode || "unified").catch((error) => showFeedback(dom.feedback, error.message || "切换策略失败"));
        if (event.target.closest("[data-create-task]")) await createTask().catch((error) => showFeedback(dom.listFeedback, error.message || "新增失败"));
        if (event.target.closest("[data-create-group]")) await createGroup().catch((error) => showFeedback(dom.listFeedback, error.message || "新增失败"));
        if (event.target.closest("[data-delete-group]")) await deleteSelectedGroup().catch((error) => showFeedback(dom.listFeedback, error.message || "删除分组失败"));
        if (event.target.closest("[data-preview-audience]")) await previewAudience().catch((error) => showFeedback(dom.feedback, error.message || "预览失败"));
        if (event.target.closest("[data-save-task]")) await saveBaseTask("", false).catch((error) => showFeedback(dom.feedback, error.message || "保存任务失败"));
        if (event.target.closest("[data-config-unified]")) openUnifiedComposer();
        const profileButton = event.target.closest("[data-config-profile-segment]");
        if (profileButton) openProfileComposer(profileButton.dataset.configProfileSegment || "", profileButton.closest("[data-segment-name]")?.dataset.segmentName || "");
        const behaviorButton = event.target.closest("[data-config-behavior-segment]");
        if (behaviorButton) openBehaviorComposer(behaviorButton.dataset.configBehaviorSegment || "", behaviorButton.closest("[data-segment-name]")?.dataset.segmentName || "");
        if (event.target.closest("[data-config-agent-materials]")) openAgentComposer();
        if (event.target.closest("[data-save-agent-text]")) await saveAgentTextConfig().catch((error) => showFeedback(dom.feedback, error.message || "保存失败"));
        const actionButton = event.target.closest("[data-task-action]");
        if (actionButton) {
          const taskId = Number(actionButton.closest("[data-task-id]")?.dataset.taskId || 0);
          await runTaskAction(actionButton.dataset.taskAction, taskId).catch((error) => showFeedback(dom.listFeedback, error.message || "任务操作失败"));
        }
      } catch (error) {
        showFeedback(dom.feedback, error.message || "操作失败，请刷新后重试");
      }
    });

    root.addEventListener("change", async (event) => {
      if (event.target.matches("[data-profile-template-select]")) {
        const rawTemplateId = String(event.target.value || "");
        const templateId = Number(rawTemplateId || 0);
        if (rawTemplateId || state.setupProfileSegments.length) {
          await updateStrategy({ content_mode: "profile_layered", profile_segment_template_id: templateId || null }).catch((error) =>
            showFeedback(dom.feedback, error.message || "分层规则保存失败")
          );
          await loadProfileSegments(templateId).catch((error) => showFeedback(dom.feedback, error.message || "分层规则详情加载失败"));
        } else {
          state.profileSegments = [];
        }
        renderStrategyPanel();
      }
      if (event.target.matches("[data-agent-select]")) {
        const agentCode = String(event.target.value || "").trim();
        if (agentCode) await updateStrategy({ content_mode: "agent", agent_code: agentCode }).catch((error) => showFeedback(dom.feedback, error.message || "智能体保存失败"));
      }
      if (event.target.matches("[data-field='trigger_type']")) syncTriggerFields();
    });

    root.addEventListener("input", (event) => {
      if (event.target === dom.taskSearch) renderList();
      if (!state.currentTask || !event.target.matches("[data-field]")) return;
      state.currentTask[event.target.dataset.field] = event.target.value;
    });
    dom.groupFilter?.addEventListener("change", renderList);

    window.__automationOperationSaveCurrent = async () => {
      if (!state.currentTask) return true;
      await saveBaseTask("", true);
      return true;
    };
    window.__automationOperationSaveDraft = async () => saveBaseTask("draft", true);
    window.__automationOperationPublish = async () => saveBaseTask("active", true);

    (async () => {
      try {
        await safeLoadAuxiliary();
        await loadTasks();
        const content = operationContent();
        if (content.content_mode === "profile_layered" && content.profile_segment_template_id) {
          await loadProfileSegments(content.profile_segment_template_id).catch((error) => showFeedback(dom.feedback, error.message || "画像模板详情加载失败"));
        }
        renderStrategyPanel();
        root.dataset.operationPanelReady = "1";
      } catch (error) {
        root.dataset.operationPanelError = error.message || "运营任务加载失败";
        showFeedback(dom.feedback, error.message || "运营任务加载失败");
      }
    })();
  }

  function boot() {
    const root = document.querySelector("[data-operation-task-root]");
    if (!root) return;
    try {
      initOperationPanel(root);
    } catch (error) {
      root.dataset.operationPanelError = error.message || "初始化失败";
      const feedback = root.querySelector("[data-task-feedback]");
      if (feedback) {
        feedback.textContent = root.dataset.operationPanelError;
        feedback.style.display = "block";
      }
    }
  }

  window.AICRMAutomationOperationPanel = { init: initOperationPanel };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
