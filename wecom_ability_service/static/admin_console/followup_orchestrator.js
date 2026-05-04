function orchestratorRoot() {
  return document.querySelector("[data-followup-orchestrator-root]");
}

function safeJsonParse(text) {
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

function orchestratorAccessHeaders(root) {
  const headers = {};
  if (!root || !root.dataset) return headers;
  if (root.dataset.customerPulseTenantKey) {
    headers["X-Tenant-Key"] = root.dataset.customerPulseTenantKey;
  }
  if (root.dataset.customerPulseActorUserid) {
    headers["X-Admin-Userid"] = root.dataset.customerPulseActorUserid;
  }
  if (root.dataset.customerPulseActorRole) {
    headers["X-Admin-Role"] = root.dataset.customerPulseActorRole;
  }
  return headers;
}

function requestJson(url, options = {}, root = null) {
  const finalOptions = {
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...orchestratorAccessHeaders(root),
      ...(options.headers || {}),
    },
    ...options,
  };
  return fetch(url, finalOptions)
    .then((response) =>
      response.text().then((text) => ({
        response,
        payload: text ? safeJsonParse(text) : null,
      })),
    )
    .then(({ response, payload }) => {
      if (!response.ok || (payload && payload.ok === false)) {
        const error = new Error((payload && payload.error) || "request failed");
        error.status = response.status;
        throw error;
      }
      return payload || { ok: true };
    });
}

function isPermissionError(error) {
  const message = String((error && error.message) || "");
  return Boolean(error) && (error.status === 401 || error.status === 403 || message.includes("令牌无效"));
}

function toDateTimeLocalValue(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  return text.replace(" ", "T").slice(0, 16);
}

function fromDateTimeLocalValue(value) {
  return String(value || "").trim().replace("T", " ");
}

function inlineStateHtml(title, body, tone = "inline") {
  const className =
    tone === "error"
      ? "admin-state admin-state--inline admin-state--error"
      : "admin-state admin-state--inline";
  return `<div class="${className}"><strong>${escapeHtml(title)}</strong><span>${escapeHtml(body)}</span></div>`;
}

function missionApiUrl(root, missionKey, suffix = "") {
  return `${root.dataset.missionApiBase}/${encodeURIComponent(missionKey)}${suffix}`;
}

function missionItemActionUrl(root, missionKey, missionItemKey, actionName) {
  return missionApiUrl(
    root,
    missionKey,
    `/items/${encodeURIComponent(missionItemKey)}/actions/${encodeURIComponent(actionName)}`,
  );
}

function customerDetailUrl(root, externalUserid) {
  return `${root.dataset.customerDetailBase}/${encodeURIComponent(externalUserid)}`;
}

function pulseInboxUrl(root, externalUserid) {
  const url = new URL(root.dataset.customerPulseInboxUrl, window.location.origin);
  if (externalUserid) {
    url.searchParams.set("external_userid", externalUserid);
  }
  return `${url.pathname}${url.search}`;
}

function todayDateKey() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function parseDateTime(value) {
  const text = String(value || "").trim();
  if (!text) return null;
  const normalized = text.includes("T") ? text : text.replace(" ", "T");
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

function sortedUniqueStrings(items) {
  return Array.from(
    new Set(
      (Array.isArray(items) ? items : [])
        .map((item) => String(item || "").trim())
        .filter(Boolean),
    ),
  ).sort((left, right) => left.localeCompare(right, "zh-CN"));
}

function pulseFormFields(preview) {
  const actionType = String((preview && preview.action_type) || "");
  const payload = (preview && preview.preview) || {};
  if (actionType === "generate_reply_draft") {
    return `
      <label>
        <span>草稿内容</span>
        <textarea rows="7" data-preview-field="draft_message" placeholder="在这里继续编辑草稿">${escapeHtml(payload.draft_message || "")}</textarea>
        <small>${escapeHtml(payload.draft_notice || "所有外发消息默认只生成草稿，需人工确认后再发送。")}</small>
      </label>
    `;
  }
  if (actionType === "create_followup_task") {
    return `
      <label>
        <span>任务标题</span>
        <input type="text" data-preview-field="task_title" value="${escapeHtml(payload.task_title || "")}">
      </label>
      <label>
        <span>截止时间</span>
        <input type="datetime-local" data-preview-field="due_at" value="${escapeHtml(toDateTimeLocalValue(payload.due_at || ""))}">
      </label>
    `;
  }
  if (actionType === "update_followup_segment") {
    const currentSegment = String(payload.followup_segment || "focus");
    const options = [
      { value: "focus", label: "重点跟进" },
      { value: "normal", label: "普通跟进" },
      { value: "core", label: "Core" },
      { value: "top", label: "Top" },
    ];
    return `
      <label>
        <span>目标阶段</span>
        <select data-preview-field="followup_segment">
          ${options
            .map(
              (option) =>
                `<option value="${escapeHtml(option.value)}"${option.value === currentSegment ? " selected" : ""}>${escapeHtml(option.label)}</option>`,
            )
            .join("")}
        </select>
      </label>
    `;
  }
  if (actionType === "update_tags") {
    return `
      <label>
        <span>新增标签 ID</span>
        <input type="text" data-preview-field="add_tag_ids" value="${escapeHtml((payload.add_tag_ids || []).join(","))}" placeholder="tag_a,tag_b">
      </label>
      <label>
        <span>移除标签 ID</span>
        <input type="text" data-preview-field="remove_tag_ids" value="${escapeHtml((payload.remove_tag_ids || []).join(","))}" placeholder="tag_c,tag_d">
      </label>
    `;
  }
  if (actionType === "set_followup_reminder") {
    return `
      <label>
        <span>提醒时间</span>
        <input type="datetime-local" data-preview-field="due_at" value="${escapeHtml(toDateTimeLocalValue(payload.due_at || ""))}">
      </label>
    `;
  }
  return "";
}

function currentPulseFormPayload(form) {
  const actionType = form.dataset.actionType || "";
  if (actionType === "generate_reply_draft") {
    return { draft_message: form.querySelector("[data-preview-field='draft_message']")?.value || "" };
  }
  if (actionType === "create_followup_task") {
    return {
      task_title: form.querySelector("[data-preview-field='task_title']")?.value || "",
      due_at: fromDateTimeLocalValue(form.querySelector("[data-preview-field='due_at']")?.value || ""),
    };
  }
  if (actionType === "update_followup_segment") {
    return { followup_segment: form.querySelector("[data-preview-field='followup_segment']")?.value || "" };
  }
  if (actionType === "update_tags") {
    const parseCsv = (value) =>
      String(value || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
    return {
      add_tag_ids: parseCsv(form.querySelector("[data-preview-field='add_tag_ids']")?.value || ""),
      remove_tag_ids: parseCsv(form.querySelector("[data-preview-field='remove_tag_ids']")?.value || ""),
    };
  }
  if (actionType === "set_followup_reminder") {
    return { due_at: fromDateTimeLocalValue(form.querySelector("[data-preview-field='due_at']")?.value || "") };
  }
  return {};
}

const orchestratorStore = {
  payloads: {
    mine: null,
    team: null,
  },
  activeView: "mine",
  selectedMissionKey: "",
  detailCache: {},
  filters: {
    search: "",
    team: "",
    owner: "",
    stage: "",
    risk: "",
    dueTodayOnly: false,
    approvalOnly: false,
    overloadedOnly: false,
    unownedOnly: false,
  },
  pulsePreviewMap: {},
  pulsePreviewErrors: {},
  detailFeedback: null,
};

function currentPayload() {
  return orchestratorStore.payloads[orchestratorStore.activeView] || null;
}

function missionItems(mission) {
  return Array.isArray(mission && mission.items) ? mission.items : [];
}

function allMissionItems(payload) {
  const missions = Array.isArray(payload && payload.missions) ? payload.missions : [];
  return missions.flatMap((mission) => missionItems(mission));
}

function missionWhyText(mission) {
  if (!mission) return "";
  const ai = mission.ai_enhancement && mission.ai_enhancement.recommendation ? mission.ai_enhancement.recommendation : {};
  return (
    ai.missionSummary ||
    mission.assignment_why ||
    mission.escalation_why ||
    mission.handoff_summary ||
    mission.summary ||
    ""
  );
}

function missionDeadline(mission) {
  const dueValues = missionItems(mission)
    .map((item) => (item.signals && item.signals.due ? item.signals.due.due_at : ""))
    .filter(Boolean)
    .sort();
  return dueValues[0] || "";
}

function missionPrimaryActionLabel(mission) {
  const missionType = String((mission && mission.mission_type) || "");
  if (missionType === "claim_queue") return "认领客户";
  if (missionType === "handoff_wave") return "审批转派";
  if (missionType === "risk_escalation_wave") return "升级处理";
  if (missionType === "batch_draft_wave") return "批量生成草稿";
  return "接受任务包";
}

function missionRiskSummary(mission) {
  const items = missionItems(mission);
  const highRiskCount = items.filter((item) => Boolean(item.signals && item.signals.high_risk)).length;
  const overdueCount = items.filter((item) => Boolean(item.signals && item.signals.due && item.signals.due.is_overdue)).length;
  const unownedCount = items.filter((item) => !String(item.owner_userid || "").trim()).length;
  const chunks = [];
  if (highRiskCount) chunks.push(`${highRiskCount} 个高风险`);
  if (overdueCount) chunks.push(`${overdueCount} 个超 SLA`);
  if (unownedCount) chunks.push(`${unownedCount} 个无 owner`);
  return chunks.join(" / ");
}

function evidenceRefsHtml(items) {
  const rows = Array.isArray(items) ? items : [];
  if (!rows.length) {
    return inlineStateHtml("暂无证据线索", "当前没有可展示的 evidence refs。");
  }
  return rows
    .map(
      (item) => `
        <article class="admin-profile-message">
          <div class="admin-profile-message-meta">
            <span>${escapeHtml(item.title || item.sourceType || "证据")}</span>
            <span>${escapeHtml(item.eventTime || "-")}</span>
          </div>
          <div class="admin-profile-message-content">${escapeHtml(
            [item.sourceType, item.sourceId].filter(Boolean).join(" · ") || "原始记录引用",
          )}</div>
        </article>
      `,
    )
    .join("");
}

function toneForPriority(score) {
  if (Number(score || 0) >= 90) return "warn";
  if (Number(score || 0) >= 70) return "ok";
  return "neutral";
}

function isMissionSelected(missionKey) {
  return String(orchestratorStore.selectedMissionKey || "") === String(missionKey || "");
}

function actionPermissions(payload) {
  const access = payload && payload.access ? payload.access : {};
  const permissions = access.permissions || {};
  return {
    canViewAll: Boolean(access.can_view_all),
    canExecuteAny: Boolean(permissions.can_execute_any),
    canViewEvidence: Boolean(permissions.evidence_view),
    actionMap: permissions.action_permissions || {},
  };
}

function buildFilterOptions(payload) {
  const missions = Array.isArray(payload && payload.missions) ? payload.missions : [];
  const items = allMissionItems(payload);
  return {
    teams: sortedUniqueStrings(missions.map((mission) => mission.team_scope_key)),
    owners: sortedUniqueStrings(
      items.flatMap((item) => [item.owner_userid, item.owner_display_name]),
    ),
    stages: sortedUniqueStrings(
      items.flatMap((item) => [item.stage_key, item.stage_label]),
    ),
    risks: sortedUniqueStrings(
      items.flatMap((item) =>
        (Array.isArray(item.risk_flags) ? item.risk_flags : []).flatMap((risk) => [risk.key, risk.label]),
      ),
    ),
  };
}

function filterValueMap(root) {
  const result = {};
  root.querySelectorAll("[data-orchestrator-filter]").forEach((node) => {
    const key = node.dataset.orchestratorFilter;
    if (!key) return;
    result[key] = node.type === "checkbox" ? Boolean(node.checked) : String(node.value || "").trim();
  });
  return result;
}

function syncFilterControls(root, payload) {
  const options = buildFilterOptions(payload);
  const selectMap = {
    team: options.teams,
    owner: options.owners,
    stage: options.stages,
    risk: options.risks,
  };
  Object.entries(selectMap).forEach(([name, values]) => {
    const select = root.querySelector(`[data-orchestrator-filter="${name}"]`);
    if (!select) return;
    const currentValue = orchestratorStore.filters[name] || "";
    const firstOption = select.querySelector("option");
    select.innerHTML = firstOption ? firstOption.outerHTML : "";
    values.forEach((value) => {
      select.insertAdjacentHTML(
        "beforeend",
        `<option value="${escapeHtml(value)}"${value === currentValue ? " selected" : ""}>${escapeHtml(value)}</option>`,
      );
    });
    select.value = currentValue;
  });
  root.querySelectorAll("[data-orchestrator-filter]").forEach((node) => {
    const key = node.dataset.orchestratorFilter;
    if (!key) return;
    if (node.type === "checkbox") {
      node.checked = Boolean(orchestratorStore.filters[key]);
    } else if (node.value !== orchestratorStore.filters[key]) {
      node.value = orchestratorStore.filters[key] || "";
    }
  });
}

function missionMatchesFilters(mission, filters) {
  const items = missionItems(mission);
  const search = String(filters.search || "").toLowerCase();
  if (search) {
    const haystack = [
      mission.title,
      mission.summary,
      missionWhyText(mission),
      mission.assignment_why,
      mission.escalation_why,
      ...items.flatMap((item) => [
        item.customer_name,
        item.external_userid,
        item.owner_userid,
        item.owner_display_name,
        item.stage_label,
        item.stage_key,
        item.current_judgement,
        item.why_now,
      ]),
    ]
      .join(" ")
      .toLowerCase();
    if (!haystack.includes(search)) return false;
  }
  if (filters.team && String(mission.team_scope_key || "") !== String(filters.team)) {
    return false;
  }
  if (filters.owner) {
    const ownerMatched = items.some(
      (item) =>
        String(item.owner_userid || "") === String(filters.owner) ||
        String(item.owner_display_name || "") === String(filters.owner),
    );
    if (!ownerMatched) return false;
  }
  if (filters.stage) {
    const stageMatched = items.some(
      (item) =>
        String(item.stage_key || "") === String(filters.stage) ||
        String(item.stage_label || "") === String(filters.stage),
    );
    if (!stageMatched) return false;
  }
  if (filters.risk) {
    const riskMatched = items.some((item) =>
      (Array.isArray(item.risk_flags) ? item.risk_flags : []).some(
        (risk) => String(risk.key || "") === String(filters.risk) || String(risk.label || "") === String(filters.risk),
      ),
    );
    if (!riskMatched) return false;
  }
  if (filters.dueTodayOnly) {
    const dueMatched = items.some((item) => {
      const due = item.signals && item.signals.due ? item.signals.due : {};
      const dueText = String(due.due_at || "");
      return Boolean(due.is_overdue) || dueText.slice(0, 10) === todayDateKey();
    });
    if (!dueMatched) return false;
  }
  if (filters.approvalOnly) {
    const approvalMatched =
      Boolean(mission.requires_manager_approval) ||
      items.some((item) => Boolean(item.decision && item.decision.payload && item.decision.payload.needs_manager_approval));
    if (!approvalMatched) return false;
  }
  if (filters.overloadedOnly) {
    if (!items.some((item) => Boolean(item.signals && item.signals.owner_workload && item.signals.owner_workload.is_overloaded))) {
      return false;
    }
  }
  if (filters.unownedOnly) {
    if (!items.some((item) => !String(item.owner_userid || "").trim())) {
      return false;
    }
  }
  return true;
}

function filteredMissions(payload) {
  const missions = Array.isArray(payload && payload.missions) ? payload.missions : [];
  return missions.filter((mission) => missionMatchesFilters(mission, orchestratorStore.filters));
}

function boardMetricCards(payload) {
  const items = allMissionItems(payload);
  const ownerWorkload = Array.isArray(payload && payload.owner_workload) ? payload.owner_workload : [];
  return [
    {
      label: "高风险堆积",
      value: items.filter((item) => Boolean(item.signals && item.signals.high_risk)).length,
      description: "命中高风险信号，且仍在 mission 中待处理。",
    },
    {
      label: "超 SLA",
      value: items.filter((item) => Boolean(item.signals && item.signals.due && item.signals.due.is_overdue)).length,
      description: "已超时或应立即处理的客户项。",
    },
    {
      label: "无 owner",
      value: items.filter((item) => !String(item.owner_userid || "").trim()).length,
      description: "当前还没有负责人，需认领。",
    },
    {
      label: "Owner 过载",
      value: ownerWorkload.filter((item) => Boolean(item.is_overloaded)).length,
      description: "当前待办负载已越过阈值的 owner 数。",
    },
    {
      label: "待审批转派",
      value: items.filter((item) => Boolean(item.decision && item.decision.payload && item.decision.payload.needs_manager_approval)).length,
      description: "需要经理确认的转派建议。",
    },
    {
      label: "待升级客户",
      value: items.filter((item) => String(item.escalation_reason || "").trim()).length,
      description: "建议升级或已有升级状态的客户项。",
    },
  ];
}

function renderSummaryCards(root, payload) {
  const node = root.querySelector("[data-orchestrator-summary-cards]");
  if (!node) return;
  const cards = Array.isArray(payload && payload.summary_cards) ? payload.summary_cards : [];
  node.innerHTML = cards
    .map(
      (card) => `
        <article class="admin-card admin-stat-card admin-stat-card--nested">
          <div class="admin-card-label">${escapeHtml(card.label || "")}</div>
          <div class="admin-card-value">${escapeHtml(card.value || 0)}</div>
          <p class="admin-card-copy">${escapeHtml(card.description || "")}</p>
        </article>
      `,
    )
    .join("");
}

function renderBoardMetrics(root, payload) {
  const node = root.querySelector("[data-orchestrator-board-metrics]");
  if (!node) return;
  const isTeam = orchestratorStore.activeView === "team";
  node.hidden = !isTeam;
  if (!isTeam) {
    node.innerHTML = "";
    return;
  }
  node.innerHTML = boardMetricCards(payload)
    .map(
      (card) => `
        <article class="admin-card admin-stat-card admin-stat-card--nested">
          <div class="admin-card-label">${escapeHtml(card.label || "")}</div>
          <div class="admin-card-value admin-card-value--compact">${escapeHtml(card.value || 0)}</div>
          <p class="admin-card-copy">${escapeHtml(card.description || "")}</p>
        </article>
      `,
    )
    .join("");
}

function setListState(root, kind, title, body) {
  const stateNode = root.querySelector("[data-orchestrator-list-state]");
  const listNode = root.querySelector("[data-orchestrator-list]");
  if (!stateNode || !listNode) return;
  listNode.hidden = true;
  stateNode.hidden = false;
  stateNode.className = "admin-state";
  if (kind === "loading") {
    stateNode.classList.add("admin-state--loading");
  } else if (kind === "error" || kind === "permission") {
    stateNode.classList.add("admin-state--error");
  } else {
    stateNode.classList.add("admin-state--empty");
  }
  stateNode.innerHTML = `<strong>${escapeHtml(title)}</strong><span>${escapeHtml(body)}</span>`;
}

function setDetailState(root, kind, title, body) {
  const stateNode = root.querySelector("[data-orchestrator-detail-state]");
  const bodyNode = root.querySelector("[data-orchestrator-detail-body]");
  if (!stateNode || !bodyNode) return;
  bodyNode.hidden = true;
  stateNode.hidden = false;
  stateNode.className = "admin-state";
  if (kind === "loading") {
    stateNode.classList.add("admin-state--loading");
  } else if (kind === "error" || kind === "permission") {
    stateNode.classList.add("admin-state--error");
  } else {
    stateNode.classList.add("admin-state--empty");
  }
  stateNode.innerHTML = `<strong>${escapeHtml(title)}</strong><span>${escapeHtml(body)}</span>`;
}

function renderMissionList(root, payload) {
  const listNode = root.querySelector("[data-orchestrator-list]");
  const titleNode = root.querySelector("[data-orchestrator-list-title]");
  const summaryNode = root.querySelector("[data-orchestrator-list-summary]");
  const sectionTitle = root.querySelector("[data-orchestrator-section-title]");
  const sectionSummary = root.querySelector("[data-orchestrator-section-summary]");
  if (!listNode) return;
  const missions = filteredMissions(payload);
  const isMine = orchestratorStore.activeView === "mine";
  if (titleNode) {
    titleNode.textContent = isMine ? "我的任务包" : "团队任务板";
  }
  if (summaryNode) {
    summaryNode.textContent = isMine
      ? "默认展示今日 mission，可在详情里直接接受任务、认领客户或逐个预览草稿。"
      : "聚焦高风险堆积、超 SLA、转派审批和团队负载。";
  }
  if (sectionTitle) {
    sectionTitle.textContent = isMine ? "我的任务包" : "团队指挥台";
  }
  if (sectionSummary) {
    sectionSummary.textContent = isMine
      ? "默认展示今天优先处理的 mission，按优先级和行动时机排序。"
      : "按团队风险、超 SLA、无 owner、转派审批和升级状态组织指挥台。";
  }
  if (!missions.length) {
    setListState(root, "empty", "当前没有匹配的任务包", "可以切换视图、重置筛选，或刷新编排结果。");
    return;
  }
  const selectedKey = orchestratorStore.selectedMissionKey && missions.some((mission) => mission.mission_key === orchestratorStore.selectedMissionKey)
    ? orchestratorStore.selectedMissionKey
    : String(missions[0].mission_key || "");
  orchestratorStore.selectedMissionKey = selectedKey;
  listNode.innerHTML = missions
    .map((mission) => {
      const deadline = missionDeadline(mission);
      const riskSummary = missionRiskSummary(mission);
      const why = missionWhyText(mission);
      return `
        <article
          class="admin-card admin-orchestrator-mission-card${isMissionSelected(mission.mission_key) ? " is-selected" : ""}"
          data-mission-select
          data-mission-key="${escapeHtml(mission.mission_key || "")}"
        >
          <div class="admin-customer-pulse-card__head">
            <div>
              <div class="admin-customer-pulse-card__title-row">
                <h2>${escapeHtml((mission.ai_enhancement && mission.ai_enhancement.recommendation && mission.ai_enhancement.recommendation.missionTitle) || mission.title || "团队任务包")}</h2>
                ${mission.requires_manager_approval ? '<span class="admin-inline-chip admin-inline-chip--warn">待审批</span>' : ""}
              </div>
              <p>${escapeHtml(why || mission.summary || "暂无说明")}</p>
            </div>
            <div class="admin-toolbar">
              <span class="admin-inline-chip admin-inline-chip--neutral">${escapeHtml(mission.mission_status_label || mission.mission_status || "待处理")}</span>
              <span class="admin-inline-chip admin-inline-chip--${toneForPriority(mission.priority_score)}">优先级 ${escapeHtml(mission.priority_score || 0)}</span>
            </div>
          </div>

          <div class="admin-customer-pulse-card__meta">
            <span>截止时间：${escapeHtml(deadline || "未设置")}</span>
            <span>客户数：${escapeHtml(mission.item_count || 0)}</span>
            <span>建议动作：${escapeHtml(missionPrimaryActionLabel(mission))}</span>
            <span>团队：${escapeHtml(mission.team_scope_key || "当前 scope")}</span>
          </div>

          <dl class="admin-definition-list admin-customer-pulse-card__facts">
            <div>
              <dt>为什么现在</dt>
              <dd>${escapeHtml(why || "当前信号已达到编排阈值")}</dd>
            </div>
            <div>
              <dt>风险</dt>
              <dd>${escapeHtml(riskSummary || "无显著风险")}</dd>
            </div>
            <div>
              <dt>审批</dt>
              <dd>${mission.requires_manager_approval ? "需要经理确认" : "无需额外审批"}</dd>
            </div>
            <div>
              <dt>首批客户</dt>
              <dd>${escapeHtml(
                missionItems(mission)
                  .slice(0, 3)
                  .map((item) => item.customer_name || item.external_userid)
                  .join(" / ") || "暂无",
              )}</dd>
            </div>
          </dl>
        </article>
      `;
    })
    .join("");
  root.querySelector("[data-orchestrator-list-state]").hidden = true;
  listNode.hidden = false;
}

function missionActionButtonsHtml(mission, payload) {
  const permissions = actionPermissions(payload);
  const buttons = [];
  if (permissions.canExecuteAny) {
    if (mission.mission_type === "batch_draft_wave" && permissions.actionMap.generate_reply_draft) {
      buttons.push({ actionType: "prebuild_batch_draft", label: "批量生成草稿" });
    }
    if (mission.mission_type === "claim_queue") {
      buttons.push({ actionType: "accept", label: "接受任务包" });
    }
    if (mission.mission_type === "priority_wave") {
      buttons.push({ actionType: "accept", label: "接受任务包" });
    }
    if (mission.mission_type === "risk_escalation_wave") {
      buttons.push({ actionType: "escalate", label: "升级处理" });
    }
    if (permissions.canViewAll && mission.mission_type === "handoff_wave") {
      buttons.push({ actionType: "suggest_assignment", label: "建议转派" });
      buttons.push({ actionType: "request_manager_approval", label: "审批转派" });
    }
    buttons.push({ actionType: "mark_blocked", label: "标记阻塞", variant: "ghost" });
    buttons.push({ actionType: "complete", label: "完成任务包", variant: "ghost" });
    buttons.push({ actionType: "skip", label: "跳过", variant: "ghost" });
  }
  if (!buttons.length) {
    return inlineStateHtml("当前没有可执行动作", "请检查权限、owner scope 或当前任务状态。");
  }
  return `
    <label class="admin-orchestrator-note">
      <span>执行备注 / 跳过原因</span>
      <textarea rows="3" data-mission-note-field placeholder="用于审批说明、阻塞原因、完成备注或跳过理由"></textarea>
    </label>
    <div class="admin-toolbar admin-orchestrator-action-bar">
      ${buttons
        .map(
          (button) => `
            <button
              type="button"
              class="admin-button${button.variant === "ghost" ? " admin-button--ghost" : " admin-button--primary"}"
              data-orchestrator-mission-action
              data-mission-key="${escapeHtml(mission.mission_key || "")}"
              data-action-type="${escapeHtml(button.actionType || "")}"
            >
              ${escapeHtml(button.label || "")}
            </button>
          `,
        )
        .join("")}
    </div>
  `;
}

function itemActionButtonsHtml(mission, item, payload) {
  const permissions = actionPermissions(payload);
  const buttons = [];
  const latestExecutionId =
    (item.latest_pulse_execution && item.latest_pulse_execution.id) ||
    item.latest_pulse_execution_id ||
    "";
  const noteArea = `
    <label class="admin-orchestrator-note admin-orchestrator-note--item">
      <span>客户项备注</span>
      <textarea rows="2" data-mission-item-note-field="${escapeHtml(item.mission_item_key || "")}" placeholder="阻塞 / 完成 / 跳过原因"></textarea>
    </label>
  `;
  if (permissions.canExecuteAny) {
    if (mission.mission_type === "claim_queue" || !String(item.owner_userid || "").trim()) {
      buttons.push({ actionType: "claim", label: "认领客户" });
    } else {
      buttons.push({ actionType: "accept", label: "接受" });
    }
    if (permissions.canViewAll && mission.mission_type === "handoff_wave") {
      buttons.push({ actionType: "request_manager_approval", label: "审批转派" });
    }
    if (permissions.canViewAll && item.decision && item.decision.decision_type === "reassign") {
      buttons.push({ actionType: "suggest_assignment", label: "建议转派" });
    }
    buttons.push({ actionType: "mark_blocked", label: "标记阻塞", variant: "ghost" });
    buttons.push({ actionType: "complete", label: "完成", variant: "ghost" });
    buttons.push({ actionType: "skip", label: "跳过", variant: "ghost" });
  }
  const actionMap = permissions.actionMap || {};
  if (item.pulse_card_id && item.suggested_action_type && actionMap[item.suggested_action_type]) {
    buttons.push({
      pulsePreview: true,
      actionType: item.suggested_action_type,
      label: item.suggested_action_type === "generate_reply_draft" ? "草稿入口" : "预览动作",
      variant: "ghost",
    });
  }
  buttons.push({ href: customerDetailUrl(orchestratorRoot(), item.external_userid), label: "客户详情", link: true, variant: "ghost" });
  buttons.push({ href: pulseInboxUrl(orchestratorRoot(), item.external_userid), label: "查看 AI推进", link: true, variant: "ghost" });
  return `
    ${noteArea}
    <div class="admin-toolbar admin-orchestrator-action-bar">
      ${buttons
        .map((button) => {
          if (button.link) {
            return `<a class="admin-button${button.variant === "ghost" ? " admin-button--ghost" : ""}" href="${escapeHtml(button.href || "#")}">${escapeHtml(button.label || "")}</a>`;
          }
          if (button.pulsePreview) {
            return `
              <button
                type="button"
                class="admin-button${button.variant === "ghost" ? " admin-button--ghost" : ""}"
                data-orchestrator-pulse-preview
                data-mission-key="${escapeHtml(mission.mission_key || "")}"
                data-action-type="${escapeHtml(button.actionType || "")}"
                data-mission-item-key="${escapeHtml(item.mission_item_key || "")}"
              >
                ${escapeHtml(button.label || "")}
              </button>
            `;
          }
          return `
            <button
              type="button"
              class="admin-button${button.variant === "ghost" ? " admin-button--ghost" : " admin-button--secondary"}"
              data-orchestrator-item-action
              data-mission-key="${escapeHtml(mission.mission_key || "")}"
              data-mission-item-key="${escapeHtml(item.mission_item_key || "")}"
              data-action-type="${escapeHtml(button.actionType || "")}"
            >
              ${escapeHtml(button.label || "")}
            </button>
          `;
        })
        .join("")}
      ${
        latestExecutionId
          ? `
            <button
              type="button"
              class="admin-button admin-button--ghost"
              data-orchestrator-pulse-undo
              data-mission-key="${escapeHtml(mission.mission_key || "")}"
              data-mission-item-key="${escapeHtml(item.mission_item_key || "")}"
              data-execution-id="${escapeHtml(latestExecutionId)}"
            >
              撤销上次执行
            </button>
          `
          : ""
      }
    </div>
  `;
}

function previewStoreKey(itemKey, actionType) {
  return `${String(itemKey || "")}:${String(actionType || "")}`;
}

function itemPreviewHtml(item) {
  const previews = orchestratorStore.pulsePreviewMap || {};
  const errors = orchestratorStore.pulsePreviewErrors || {};
  const actionType = String(item.suggested_action_type || "");
  const key = previewStoreKey(item.mission_item_key, actionType);
  const preview = previews[key];
  const error = errors[key];
  const aiDraft = item.ai_draft_suggestion || {};
  const draftText = aiDraft.draftText || aiDraft.draft_text || "";
  const aiReason = aiDraft.whyNow || aiDraft.why_now || "";
  if (error) {
    return inlineStateHtml("当前无法加载草稿预览", error, "error");
  }
  const aiSuggestionHtml = draftText
    ? `
      <div class="admin-state admin-state--inline">
        <strong>批量草稿建议</strong>
        <span>${escapeHtml(aiReason || "以下草稿仅为建议，仍需逐个确认。")}</span>
      </div>
      <label class="admin-orchestrator-note admin-orchestrator-note--draft">
        <span>建议草稿</span>
        <textarea rows="5">${escapeHtml(draftText)}</textarea>
      </label>
    `
    : "";
  if (!preview) {
    return aiSuggestionHtml || "";
  }
  return `
    ${aiSuggestionHtml}
    <form
      class="admin-drawer admin-orchestrator-preview-form"
      data-orchestrator-pulse-action-form
      data-mission-key="${escapeHtml(orchestratorStore.selectedMissionKey || "")}"
      data-action-type="${escapeHtml(preview.action_type || actionType)}"
      data-mission-item-key="${escapeHtml(item.mission_item_key || "")}"
    >
      <div class="admin-card-head admin-card-head--tight">
        <div>
          <h2>动作预览</h2>
          <p>${escapeHtml(preview.preview && preview.preview.notice ? preview.preview.notice : "当前只会提交到现有安全执行链路，不会静默对外发送。")}</p>
        </div>
      </div>
      <div class="admin-form-grid admin-form-grid--stacked">
        ${pulseFormFields(preview)}
      </div>
      <div class="admin-toolbar admin-customer-pulse-detail__form-actions">
        <button type="submit" class="admin-button admin-button--primary">确认执行</button>
      </div>
    </form>
  `;
}

function renderExecutionLogs(logs) {
  const rows = Array.isArray(logs) ? logs : [];
  if (!rows.length) {
    return inlineStateHtml("暂无执行记录", "当前任务包还没有执行日志。");
  }
  return `
    <div class="admin-profile-message-list">
      ${rows
        .slice(0, 8)
        .map(
          (log) => `
            <article class="admin-profile-message">
              <div class="admin-profile-message-meta">
                <span>${escapeHtml(log.action_type || "动作")}</span>
                <span>${escapeHtml(log.execution_status || "-")}</span>
                <span>${escapeHtml(log.actor_userid || log.operator || "-")}</span>
                <span>${escapeHtml(log.created_at || "-")}</span>
              </div>
              <div class="admin-profile-message-content">${escapeHtml(
                JSON.stringify(log.result_payload || {}, null, 2),
              )}</div>
            </article>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderMissionDetail(root, mission) {
  const stateNode = root.querySelector("[data-orchestrator-detail-state]");
  const bodyNode = root.querySelector("[data-orchestrator-detail-body]");
  const payload = currentPayload();
  if (!bodyNode || !stateNode) return;
  const permissions = actionPermissions(payload);
  const detailFeedback = orchestratorStore.detailFeedback;
  const feedbackHtml = detailFeedback
    ? inlineStateHtml(detailFeedback.title || "操作结果", detailFeedback.message || "", detailFeedback.tone || "inline")
    : "";
  const evidenceHtml = permissions.canViewEvidence
    ? evidenceRefsHtml(mission.evidence_refs || [])
    : inlineStateHtml("证据已受限", "当前角色可见任务包，但没有展开 evidence 的权限。");
  bodyNode.innerHTML = `
    <section class="admin-orchestrator-mission-detail">
      <div class="admin-customer-pulse-card__head">
        <div>
          <div class="admin-customer-pulse-card__title-row">
            <h2>${escapeHtml((mission.ai_enhancement && mission.ai_enhancement.recommendation && mission.ai_enhancement.recommendation.missionTitle) || mission.title || "团队任务包")}</h2>
            <span class="admin-inline-chip admin-inline-chip--neutral">${escapeHtml(mission.mission_status_label || mission.mission_status || "待处理")}</span>
            ${mission.requires_manager_approval ? '<span class="admin-inline-chip admin-inline-chip--warn">需要审批</span>' : ""}
          </div>
          <p>${escapeHtml(missionWhyText(mission) || mission.summary || "暂无说明")}</p>
        </div>
        <div class="admin-toolbar">
          <span class="admin-inline-chip admin-inline-chip--${toneForPriority(mission.priority_score)}">优先级 ${escapeHtml(mission.priority_score || 0)}</span>
          <span class="admin-inline-chip admin-inline-chip--ok">客户 ${escapeHtml(mission.item_count || 0)}</span>
        </div>
      </div>

      <dl class="admin-definition-list admin-orchestrator-definition-list">
        <div>
          <dt>截止时间</dt>
          <dd>${escapeHtml(missionDeadline(mission) || "未设置")}</dd>
        </div>
        <div>
          <dt>建议动作</dt>
          <dd>${escapeHtml(missionPrimaryActionLabel(mission))}</dd>
        </div>
        <div>
          <dt>为什么现在</dt>
          <dd>${escapeHtml(missionWhyText(mission) || "当前信号已达到团队编排阈值")}</dd>
        </div>
        <div>
          <dt>风险</dt>
          <dd>${escapeHtml(missionRiskSummary(mission) || "无显著风险")}</dd>
        </div>
      </dl>

      ${feedbackHtml}

      <section class="admin-orchestrator-block">
        <div class="admin-card-head admin-card-head--tight">
          <div>
            <h2>任务包动作</h2>
            <p>接受、审批、升级、阻塞、完成和跳过都走 tenant-scoped、RBAC-controlled 的 mission action 链路。</p>
          </div>
        </div>
        ${missionActionButtonsHtml(mission, payload)}
      </section>

      <section class="admin-orchestrator-block">
        <div class="admin-card-head admin-card-head--tight">
          <div>
            <h2>证据</h2>
            <p>每个 mission 都能追溯到原始 evidence refs；无证据权限时只显示受限状态。</p>
          </div>
        </div>
        <div class="admin-profile-message-list">${evidenceHtml}</div>
      </section>

      <section class="admin-orchestrator-block">
        <div class="admin-card-head admin-card-head--tight">
          <div>
            <h2>客户项</h2>
            <p>这里展示每位客户的阶段、owner、evidence、推荐动作和草稿入口。批量草稿仍然逐客户预览和编辑。</p>
          </div>
        </div>
        <div class="admin-orchestrator-item-list">
          ${missionItems(mission)
            .map(
              (item) => `
                <article class="admin-orchestrator-item-card">
                  <div class="admin-customer-pulse-card__head">
                    <div>
                      <div class="admin-customer-pulse-card__title-row">
                        <h2>${escapeHtml(item.customer_name || item.external_userid || "未命名客户")}</h2>
                        <a class="admin-button admin-button--ghost" href="${escapeHtml(customerDetailUrl(root, item.external_userid))}">客户详情</a>
                      </div>
                      <p>${escapeHtml(item.current_judgement || item.title || "暂无判断")}</p>
                    </div>
                    <div class="admin-toolbar">
                      <span class="admin-inline-chip admin-inline-chip--neutral">${escapeHtml(item.item_status_label || item.item_status || "待处理")}</span>
                      <span class="admin-inline-chip admin-inline-chip--ok">${escapeHtml(item.assignment_status_label || item.assignment_status || "待确认")}</span>
                      <span class="admin-inline-chip admin-inline-chip--${toneForPriority(item.execution_state === "draft_ready" ? 85 : item.execution_state === "executed" ? 78 : 58)}">${escapeHtml(item.execution_state_label || "未开始")}</span>
                    </div>
                  </div>

                  <div class="admin-customer-pulse-card__meta">
                    <span>阶段：${escapeHtml(item.stage_label || item.stage_key || "未标记")}</span>
                    <span>Owner：${escapeHtml(item.owner_display_name || item.owner_userid || "未分配")}</span>
                    <span>建议归属：${escapeHtml(item.suggested_assignee_userid || item.owner_userid || "保持当前 owner")}</span>
                    <span>推荐动作：${escapeHtml(item.suggested_action_label || item.suggested_action_type || "人工确认")}</span>
                  </div>

                  <dl class="admin-definition-list admin-orchestrator-item-facts">
                    <div>
                      <dt>为什么现在</dt>
                      <dd>${escapeHtml(item.why_now || "当前信号已达到行动阈值")}</dd>
                    </div>
                    <div>
                      <dt>接力 / 审批</dt>
                      <dd>${escapeHtml(
                        (item.decision && item.decision.payload && item.decision.payload.reason) ||
                          item.escalation_reason ||
                          "当前没有额外审批说明",
                      )}</dd>
                    </div>
                    <div>
                      <dt>执行闭环</dt>
                      <dd>${escapeHtml(item.execution_state_label || "未开始")}</dd>
                    </div>
                    <div>
                      <dt>证据</dt>
                      <dd>${permissions.canViewEvidence ? escapeHtml((item.evidence_refs || []).length || 0) + " 条" : "无权限查看"}</dd>
                    </div>
                    <div>
                      <dt>风险 / 机会</dt>
                      <dd>${escapeHtml(
                        []
                          .concat((item.risk_flags || []).map((risk) => risk.label || risk.key))
                          .concat((item.opportunity_flags || []).map((opportunity) => opportunity.label || opportunity.key))
                          .filter(Boolean)
                          .join(" / ") || "暂无显著信号",
                      )}</dd>
                    </div>
                  </dl>

                  ${
                    permissions.canViewEvidence
                      ? `<div class="admin-profile-message-list admin-orchestrator-item-evidence">${evidenceRefsHtml((item.evidence_refs || []).slice(0, 3))}</div>`
                      : ""
                  }

                  ${
                    item.handoff_packet && Object.keys(item.handoff_packet).length
                      ? `
                        <div class="admin-state admin-state--inline">
                          <strong>接力摘要</strong>
                          <span>${escapeHtml(item.handoff_packet.handoff_summary || item.handoff_packet.recent_event_summary || "已生成 handoff packet")}</span>
                        </div>
                        <dl class="admin-definition-list admin-orchestrator-item-facts">
                          <div>
                            <dt>下一步建议</dt>
                            <dd>${escapeHtml(item.handoff_packet.next_action_suggestion || item.handoff_packet.next_action_type || "人工确认")}</dd>
                          </div>
                          <div>
                            <dt>已有产物</dt>
                            <dd>${escapeHtml(
                              [
                                item.handoff_packet.artifact_status && item.handoff_packet.artifact_status.draft_ready ? "已有草稿" : "",
                                item.handoff_packet.artifact_status && item.handoff_packet.artifact_status.followup_task_open ? "已有任务" : "",
                                item.handoff_packet.artifact_status && item.handoff_packet.artifact_status.reminder_scheduled ? "已有提醒" : "",
                              ]
                                .filter(Boolean)
                                .join(" / ") || "暂无",
                            )}</dd>
                          </div>
                        </dl>
                      `
                      : ""
                  }

                  ${itemActionButtonsHtml(mission, item, payload)}
                  ${itemPreviewHtml(item)}
                </article>
              `,
            )
            .join("")}
        </div>
      </section>

      <section class="admin-orchestrator-block">
        <div class="admin-card-head admin-card-head--tight">
          <div>
            <h2>执行日志</h2>
            <p>记录任务包和客户项动作的 actor、结果和时间，便于追责和回归。</p>
          </div>
        </div>
        ${renderExecutionLogs(mission.execution_logs)}
      </section>
    </section>
  `;
  stateNode.hidden = true;
  bodyNode.hidden = false;
}

function missionFromCurrentPayload(missionKey) {
  const payload = currentPayload();
  const missions = Array.isArray(payload && payload.missions) ? payload.missions : [];
  return missions.find((mission) => String(mission.mission_key || "") === String(missionKey || "")) || null;
}

function renderCurrentView(root) {
  const payload = currentPayload();
  if (!payload || !payload.enabled) {
    setListState(root, "error", "团队编排暂不可用", "请确认 ai_followup_orchestrator 已启用且当前租户具备访问权限。");
    setDetailState(root, "empty", "当前没有可展示详情", "等待任务包加载完成后再查看。");
    return;
  }
  syncFilterControls(root, payload);
  renderSummaryCards(root, payload);
  renderBoardMetrics(root, payload);
  renderMissionList(root, payload);
  const selectedMissionKey = orchestratorStore.selectedMissionKey;
  if (!selectedMissionKey) {
    setDetailState(root, "empty", "请选择一个任务包", "左侧任务包列表已经准备好。");
    return;
  }
  const cached = orchestratorStore.detailCache[selectedMissionKey];
  if (cached) {
    renderMissionDetail(root, cached);
    return;
  }
  const mission = missionFromCurrentPayload(selectedMissionKey);
  if (mission) {
    renderMissionDetail(root, mission);
  } else {
    setDetailState(root, "empty", "当前任务包不存在", "可能已被处理完成或不再命中筛选条件。");
  }
}

function setActiveView(root, view) {
  orchestratorStore.activeView = view === "team" ? "team" : "mine";
  root.querySelectorAll("[data-orchestrator-view-tab]").forEach((node) => {
    const active = node.dataset.view === orchestratorStore.activeView;
    node.classList.toggle("is-active", active);
    node.setAttribute("aria-selected", active ? "true" : "false");
  });
}

function loadOverview(root, view, options = {}) {
  const preserveSelection = Boolean(options.preserveSelection);
  const url = new URL(root.dataset.apiUrl, window.location.origin);
  url.searchParams.set("scope", view);
  setListState(root, "loading", "正在加载任务包", "系统正在汇总最新 mission。");
  if (!preserveSelection) {
    orchestratorStore.selectedMissionKey = "";
    orchestratorStore.detailFeedback = null;
  }
  return requestJson(`${url.pathname}${url.search}`, {}, root)
    .then((payload) => {
      orchestratorStore.payloads[view] = payload.orchestrator || null;
      if (orchestratorStore.activeView === view) {
        renderCurrentView(root);
        const currentSelection = orchestratorStore.selectedMissionKey;
        if (currentSelection) {
          return loadMissionDetail(root, currentSelection, { silent: true });
        }
      }
      return payload.orchestrator || null;
    })
    .catch((error) => {
      setListState(
        root,
        isPermissionError(error) ? "permission" : "error",
        isPermissionError(error) ? "当前无权查看" : "当前无法加载任务包",
        error.message || "请稍后再试。",
      );
      setDetailState(root, "empty", "详情暂不可用", "请先解决列表加载错误。");
      return null;
    });
}

function loadMissionDetail(root, missionKey, options = {}) {
  const silent = Boolean(options.silent);
  if (!missionKey) {
    setDetailState(root, "empty", "请选择一个任务包", "左侧列表已就绪。");
    return Promise.resolve(null);
  }
  orchestratorStore.selectedMissionKey = missionKey;
  if (!silent) {
    setDetailState(root, "loading", "正在加载任务包详情", "系统正在准备证据、客户项和可执行动作。");
  }
  const fallbackMission = missionFromCurrentPayload(missionKey);
  if (fallbackMission && !silent) {
    renderMissionDetail(root, fallbackMission);
  }
  return requestJson(missionApiUrl(root, missionKey), {}, root)
    .then((payload) => {
      orchestratorStore.detailCache[missionKey] = payload.mission || null;
      if (isMissionSelected(missionKey)) {
        renderMissionDetail(root, payload.mission || fallbackMission || {});
      }
      return payload.mission || null;
    })
    .catch((error) => {
      if (fallbackMission) {
        renderMissionDetail(root, fallbackMission);
        orchestratorStore.detailFeedback = {
          title: "详情已回退到列表快照",
          message: error.message || "当前无法读取最新详情。",
          tone: "error",
        };
        renderMissionDetail(root, fallbackMission);
        return fallbackMission;
      }
      setDetailState(
        root,
        isPermissionError(error) ? "permission" : "error",
        isPermissionError(error) ? "当前无权查看详情" : "当前无法加载详情",
        error.message || "请稍后再试。",
      );
      return null;
    });
}

function missionNoteForAction(button) {
  const itemCard = button.closest(".admin-orchestrator-item-card");
  if (itemCard) {
    const noteField = itemCard.querySelector(`[data-mission-item-note-field="${button.dataset.missionItemKey || ""}"]`);
    return noteField ? noteField.value || "" : "";
  }
  const detail = button.closest(".admin-orchestrator-mission-detail");
  const noteField = detail ? detail.querySelector("[data-mission-note-field]") : null;
  return noteField ? noteField.value || "" : "";
}

function executeMissionAction(root, button) {
  const missionKey = button.dataset.missionKey;
  const actionType = button.dataset.actionType;
  const missionItemKey = button.dataset.missionItemKey || "";
  if (!missionKey || !actionType) return Promise.resolve(null);
  button.disabled = true;
  const payload = {
    admin_action_token: root.dataset.adminActionToken,
    mission_item_key: missionItemKey,
    note: missionNoteForAction(button),
  };
  return requestJson(
    missionApiUrl(root, missionKey, `/actions/${encodeURIComponent(actionType)}`),
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    root,
  )
    .then((responsePayload) => {
      const result = responsePayload.result || {};
      if (result.mission) {
        orchestratorStore.detailCache[missionKey] = result.mission;
      }
      orchestratorStore.detailFeedback = {
        title: "操作已执行",
        message: missionItemKey ? "客户项状态已更新，正在刷新任务包。" : "任务包状态已更新，正在刷新列表。",
        tone: "inline",
      };
      return loadOverview(root, orchestratorStore.activeView, { preserveSelection: true }).then(() =>
        loadMissionDetail(root, missionKey, { silent: true }),
      );
    })
    .catch((error) => {
      orchestratorStore.detailFeedback = {
        title: isPermissionError(error) ? "操作被拒绝" : "执行失败",
        message: error.message || "当前无法执行该动作。",
        tone: "error",
      };
      const mission = orchestratorStore.detailCache[missionKey] || missionFromCurrentPayload(missionKey);
      if (mission) {
        renderMissionDetail(root, mission);
      }
      return null;
    })
    .finally(() => {
      button.disabled = false;
    });
}

function loadPulsePreview(root, button) {
  const missionKey = button.dataset.missionKey || orchestratorStore.selectedMissionKey;
  const actionType = button.dataset.actionType;
  const itemKey = button.dataset.missionItemKey;
  if (!missionKey || !actionType || !itemKey) return Promise.resolve(null);
  const storeKey = previewStoreKey(itemKey, actionType);
  button.disabled = true;
  delete orchestratorStore.pulsePreviewErrors[storeKey];
  return requestJson(
    missionItemActionUrl(root, missionKey, itemKey, "preview"),
    {
      method: "POST",
      body: JSON.stringify({
        action_type: actionType,
      }),
    },
    root,
  )
    .then((payload) => {
      orchestratorStore.pulsePreviewMap[storeKey] = payload.preview || null;
      const mission = orchestratorStore.detailCache[orchestratorStore.selectedMissionKey] || missionFromCurrentPayload(orchestratorStore.selectedMissionKey);
      if (mission) {
        renderMissionDetail(root, mission);
      }
      return payload.preview || null;
    })
    .catch((error) => {
      orchestratorStore.pulsePreviewErrors[storeKey] = error.message || "当前无法加载预览。";
      const mission = orchestratorStore.detailCache[orchestratorStore.selectedMissionKey] || missionFromCurrentPayload(orchestratorStore.selectedMissionKey);
      if (mission) {
        renderMissionDetail(root, mission);
      }
      return null;
    })
    .finally(() => {
      button.disabled = false;
    });
}

function submitPulseAction(root, form) {
  const missionKey = form.dataset.missionKey || orchestratorStore.selectedMissionKey;
  const itemKey = form.dataset.missionItemKey;
  const actionType = form.dataset.actionType;
  if (!itemKey || !actionType || !missionKey) return Promise.resolve(null);
  const submitButton = form.querySelector("button[type='submit']");
  if (submitButton) submitButton.disabled = true;
  return requestJson(
    missionItemActionUrl(root, missionKey, itemKey, "execute"),
    {
      method: "POST",
      body: JSON.stringify({
        admin_action_token: root.dataset.adminActionToken,
        action_type: actionType,
        extra_payload: currentPulseFormPayload(form),
      }),
    },
    root,
  )
    .then(() => {
      orchestratorStore.detailFeedback = {
        title: "执行成功",
        message: "已提交到 Customer Pulse 安全执行链路，正在刷新任务包和详情。",
        tone: "inline",
      };
      orchestratorStore.pulsePreviewMap = {};
      orchestratorStore.pulsePreviewErrors = {};
      return loadOverview(root, orchestratorStore.activeView, { preserveSelection: true }).then(() =>
        loadMissionDetail(root, missionKey, { silent: true }),
      );
    })
    .catch((error) => {
      orchestratorStore.detailFeedback = {
        title: isPermissionError(error) ? "操作被拒绝" : "执行失败",
        message: error.message || "当前无法提交动作。",
        tone: "error",
      };
      const mission = orchestratorStore.detailCache[missionKey] || missionFromCurrentPayload(missionKey);
      if (mission) {
        renderMissionDetail(root, mission);
      }
      return null;
    })
    .finally(() => {
      if (submitButton) submitButton.disabled = false;
    });
}

function undoPulseAction(root, button) {
  const missionKey = button.dataset.missionKey || orchestratorStore.selectedMissionKey;
  const itemKey = button.dataset.missionItemKey;
  const executionId = button.dataset.executionId;
  if (!missionKey || !itemKey || !executionId) return Promise.resolve(null);
  button.disabled = true;
  return requestJson(
    missionItemActionUrl(root, missionKey, itemKey, "undo"),
    {
      method: "POST",
      body: JSON.stringify({
        admin_action_token: root.dataset.adminActionToken,
        execution_id: Number(executionId),
      }),
    },
    root,
  )
    .then(() => {
      orchestratorStore.detailFeedback = {
        title: "撤销成功",
        message: "已撤销最近一次执行，并同步回写任务包状态。",
        tone: "inline",
      };
      orchestratorStore.pulsePreviewMap = {};
      orchestratorStore.pulsePreviewErrors = {};
      return loadOverview(root, orchestratorStore.activeView, { preserveSelection: true }).then(() =>
        loadMissionDetail(root, missionKey, { silent: true }),
      );
    })
    .catch((error) => {
      orchestratorStore.detailFeedback = {
        title: isPermissionError(error) ? "撤销被拒绝" : "撤销失败",
        message: error.message || "当前无法撤销该动作。",
        tone: "error",
      };
      const mission = orchestratorStore.detailCache[missionKey] || missionFromCurrentPayload(missionKey);
      if (mission) {
        renderMissionDetail(root, mission);
      }
      return null;
    })
    .finally(() => {
      button.disabled = false;
    });
}

function applyFilterControls(root) {
  orchestratorStore.filters = {
    ...orchestratorStore.filters,
    ...filterValueMap(root),
  };
  orchestratorStore.selectedMissionKey = "";
  renderCurrentView(root);
}

function resetFilterControls(root) {
  orchestratorStore.filters = {
    search: "",
    team: "",
    owner: "",
    stage: "",
    risk: "",
    dueTodayOnly: false,
    approvalOnly: false,
    overloadedOnly: false,
    unownedOnly: false,
  };
  syncFilterControls(root, currentPayload() || {});
  orchestratorStore.selectedMissionKey = "";
  renderCurrentView(root);
}

function wireOrchestratorInteractions(root) {
  document.addEventListener("click", (event) => {
    const viewTab = event.target.closest("[data-orchestrator-view-tab]");
    if (viewTab && root.contains(viewTab)) {
      const view = viewTab.dataset.view === "team" ? "team" : "mine";
      setActiveView(root, view);
      orchestratorStore.selectedMissionKey = "";
      orchestratorStore.detailFeedback = null;
      if (orchestratorStore.payloads[view]) {
        renderCurrentView(root);
      } else {
        loadOverview(root, view);
      }
      return;
    }
    const refreshButton = event.target.closest("[data-orchestrator-refresh]");
    if (refreshButton && root.contains(refreshButton)) {
      loadOverview(root, orchestratorStore.activeView, { preserveSelection: true });
      return;
    }
    const applyFiltersButton = event.target.closest("[data-orchestrator-apply-filters]");
    if (applyFiltersButton && root.contains(applyFiltersButton)) {
      applyFilterControls(root);
      return;
    }
    const resetFiltersButton = event.target.closest("[data-orchestrator-reset-filters]");
    if (resetFiltersButton && root.contains(resetFiltersButton)) {
      resetFilterControls(root);
      return;
    }
    const missionSelect = event.target.closest("[data-mission-select]");
    if (missionSelect && root.contains(missionSelect)) {
      const missionKey = missionSelect.dataset.missionKey || "";
      loadMissionDetail(root, missionKey);
      renderMissionList(root, currentPayload() || {});
      return;
    }
    const missionAction = event.target.closest("[data-orchestrator-mission-action],[data-orchestrator-item-action]");
    if (missionAction && root.contains(missionAction)) {
      executeMissionAction(root, missionAction);
      return;
    }
    const pulsePreviewButton = event.target.closest("[data-orchestrator-pulse-preview]");
    if (pulsePreviewButton && root.contains(pulsePreviewButton)) {
      loadPulsePreview(root, pulsePreviewButton);
      return;
    }
    const pulseUndoButton = event.target.closest("[data-orchestrator-pulse-undo]");
    if (pulseUndoButton && root.contains(pulseUndoButton)) {
      undoPulseAction(root, pulseUndoButton);
    }
  });
  document.addEventListener("submit", (event) => {
    const form = event.target.closest("[data-orchestrator-pulse-action-form]");
    if (!form || !root.contains(form)) return;
    event.preventDefault();
    submitPulseAction(root, form);
  });
}

function initializeOrchestratorPage(root) {
  const rawPayload = root.querySelector("[data-followup-orchestrator-json]");
  const initialPayload = safeJsonParse(rawPayload ? rawPayload.textContent : "") || { missions: [], enabled: true };
  const initialScope = initialPayload && initialPayload.filters && initialPayload.filters.scope === "mine" ? "mine" : "team";
  orchestratorStore.payloads[initialScope] = initialPayload;

  const params = new URLSearchParams(window.location.search);
  const requestedView = params.get("scope");
  const defaultView = requestedView === "team" ? "team" : "mine";
  setActiveView(root, defaultView);
  wireOrchestratorInteractions(root);
  if (orchestratorStore.payloads[defaultView]) {
    renderCurrentView(root);
    const missions = filteredMissions(currentPayload() || {});
    if (missions[0]) {
      loadMissionDetail(root, missions[0].mission_key, { silent: true });
    }
  } else {
    loadOverview(root, defaultView);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const root = orchestratorRoot();
  if (!root) return;
  initializeOrchestratorPage(root);
});
