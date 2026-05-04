(function () {
  "use strict";

  const AutomationAgentConfig = window.AutomationAgentConfig || {};
  window.AutomationAgentConfig = AutomationAgentConfig;

  const state = AutomationAgentConfig.state || {};

  function normalizeTagId(value) {
    return String(value || "").trim();
  }

  function buildUnknownTag(tagId, tagName, groupName) {
    const normalizedTagId = normalizeTagId(tagId);
    return {
      tag_id: normalizedTagId,
      tag_name: String(tagName || "").trim() || `未知标签（${normalizedTagId}）`,
      group_name: String(groupName || "").trim() || "未知标签",
    };
  }

  function ensureTagKnown(tagId, fallbackTag) {
    const normalizedTagId = normalizeTagId(tagId);
    if (!normalizedTagId) return null;
    return state.availableTagMap.get(normalizedTagId) || fallbackTag || buildUnknownTag(normalizedTagId);
  }

  function formatTagGroupName(tag) {
    return String(((tag || {}).group_name) || "").trim() || "未分组";
  }

  function formatTagLabel(tag) {
    if (!tag) return "";
    return `${formatTagGroupName(tag)} / ${String(tag.tag_name || tag.tag_id || "未命名标签").trim()}`;
  }

  function buildTagBadge(tag) {
    const escapeHtml = AutomationAgentConfig.escapeHtml;
    if (!tag || !normalizeTagId(tag.tag_id)) {
      return '<span class="ac-config-tag-picker-note">未配置扫码自动打标签</span>';
    }
    const normalizedTagId = normalizeTagId(tag.tag_id);
    const isUnknown = !state.availableTagMap.has(normalizedTagId);
    return `<span class="ac-config-tag-badge${isUnknown ? " is-unknown" : ""}">${escapeHtml(formatTagLabel(tag))}</span>`;
  }

  function renderSelectedTags() {
    const elements = AutomationAgentConfig.elements();
    const defaultChannelFields = AutomationAgentConfig.defaultChannelFields();
    if (!elements.defaultChannelEntryTagDisplay) return;
    elements.defaultChannelEntryTagDisplay.innerHTML = buildTagBadge(state.defaultChannelSelectedTag);
    if (defaultChannelFields.entryTagId) {
      defaultChannelFields.entryTagId.value = normalizeTagId((state.defaultChannelSelectedTag || {}).tag_id);
    }
  }

  function setDefaultChannelSelectedTag(tag) {
    const normalizedTagId = normalizeTagId((tag || {}).tag_id);
    state.defaultChannelSelectedTag = normalizedTagId ? ensureTagKnown(normalizedTagId, tag) : null;
    renderSelectedTags();
  }

  function currentTagModalSelection() {
    const elements = AutomationAgentConfig.elements();
    const manualTagId = normalizeTagId((elements.defaultChannelTagManualInput || {}).value || "");
    return manualTagId || normalizeTagId(state.tagModal.selected);
  }

  function filterTags(query) {
    const keyword = String(query || "").trim().toLowerCase();
    return state.availableTags.filter((tag) => {
      if (!keyword) return true;
      const haystack = `${tag.group_name || ""} ${tag.tag_name || ""} ${tag.tag_id || ""}`.toLowerCase();
      return haystack.includes(keyword);
    });
  }

  function groupedTagsForModal() {
    const grouped = new Map();
    filterTags(state.tagModal.search).forEach((tag) => {
      const groupName = formatTagGroupName(tag);
      if (!grouped.has(groupName)) grouped.set(groupName, []);
      grouped.get(groupName).push(tag);
    });
    return [...grouped.entries()];
  }

  function selectTag(tagId) {
    const nextTagId = normalizeTagId(tagId);
    state.tagModal.selected = nextTagId;
    const { defaultChannelTagManualInput } = AutomationAgentConfig.elements();
    if (defaultChannelTagManualInput) {
      defaultChannelTagManualInput.value = "";
    }
    renderTagGroups();
  }

  function unselectTag(tagId) {
    if (!tagId || normalizeTagId(state.tagModal.selected) === normalizeTagId(tagId)) {
      state.tagModal.selected = "";
      renderTagGroups();
    }
  }

  function renderTagGroups() {
    const elements = AutomationAgentConfig.elements();
    const escapeHtml = AutomationAgentConfig.escapeHtml;
    if (!elements.defaultChannelTagGroups || !elements.defaultChannelTagSelected) return;
    const selectedTagId = currentTagModalSelection();
    const selectedTag = ensureTagKnown(selectedTagId, selectedTagId ? buildUnknownTag(selectedTagId) : null);
    const groups = groupedTagsForModal();
    elements.defaultChannelTagGroups.innerHTML = groups.length
      ? groups.map(([groupName, tags]) => `
          <section class="ac-config-tag-group">
            <h4 class="ac-config-tag-group-title">${escapeHtml(groupName)}</h4>
            <div class="ac-config-tag-chip-grid">
              ${tags.map((tag) => `
                <button
                  class="ac-config-tag-chip${selectedTagId === normalizeTagId(tag.tag_id) ? " is-active" : ""}"
                  data-tag-id="${escapeHtml(tag.tag_id)}"
                  type="button"
                >
                  ${escapeHtml(tag.tag_name || tag.tag_id || "-")}
                </button>
              `).join("")}
            </div>
          </section>
        `).join("")
      : '<div class="ac-config-empty">没有匹配到标签</div>';
    elements.defaultChannelTagSelected.innerHTML = buildTagBadge(selectedTag);
    elements.defaultChannelTagGroups.querySelectorAll("[data-tag-id]").forEach((button) => {
      button.addEventListener("click", function () {
        const nextTagId = normalizeTagId(button.dataset.tagId);
        if (state.tagModal.selected === nextTagId) {
          unselectTag(nextTagId);
          return;
        }
        selectTag(nextTagId);
      });
    });
  }

  function openTagPicker() {
    const elements = AutomationAgentConfig.elements();
    const currentTagId = normalizeTagId((state.defaultChannelSelectedTag || {}).tag_id);
    state.tagModal.open = true;
    state.tagModal.search = "";
    state.tagModal.selected = state.availableTagMap.has(currentTagId) ? currentTagId : "";
    if (elements.defaultChannelTagSearch) {
      elements.defaultChannelTagSearch.value = "";
    }
    if (elements.defaultChannelTagManualInput) {
      elements.defaultChannelTagManualInput.value = currentTagId && !state.availableTagMap.has(currentTagId) ? currentTagId : "";
    }
    renderTagGroups();
    if (elements.defaultChannelTagModalOverlay) {
      elements.defaultChannelTagModalOverlay.hidden = false;
    }
    if (elements.defaultChannelTagSearch) {
      requestAnimationFrame(() => elements.defaultChannelTagSearch.focus());
    }
  }

  function closeTagPicker() {
    const { defaultChannelTagModalOverlay } = AutomationAgentConfig.elements();
    state.tagModal.open = false;
    state.tagModal.search = "";
    state.tagModal.selected = "";
    if (defaultChannelTagModalOverlay) {
      defaultChannelTagModalOverlay.hidden = true;
    }
  }

  function confirmTagSelection() {
    const elements = AutomationAgentConfig.elements();
    const defaultChannelFields = AutomationAgentConfig.defaultChannelFields();
    const selectedTagId = currentTagModalSelection();
    if (defaultChannelFields.entryTagIdManual) {
      defaultChannelFields.entryTagIdManual.value = normalizeTagId((elements.defaultChannelTagManualInput || {}).value || "");
    }
    if (!selectedTagId) {
      setDefaultChannelSelectedTag(null);
      closeTagPicker();
      return;
    }
    const fallbackTag = buildUnknownTag(selectedTagId, "手工填写标签", "手工填写");
    setDefaultChannelSelectedTag(ensureTagKnown(selectedTagId, fallbackTag));
    closeTagPicker();
  }

  async function loadWeComTags() {
    const apiUrls = AutomationAgentConfig.getApiUrls();
    const elements = AutomationAgentConfig.elements();
    if (!apiUrls.wecom_tags) return;
    try {
      const result = await AutomationAgentConfig.requestJson(apiUrls.wecom_tags, { credentials: "same-origin" });
      state.availableTags = Array.isArray(result.items) ? result.items : [];
      state.availableTagMap = new Map(state.availableTags.map((item) => [normalizeTagId(item.tag_id), item]));
      if (elements.defaultChannelEntryTagHelp) {
        elements.defaultChannelEntryTagHelp.textContent = state.availableTags.length
          ? "从已有企微标签和标签组中选择；保存时只写入 tag_id。"
          : "当前未获取到企微标签，可稍后重试或手工填写 tag_id。";
      }
    } catch (_error) {
      state.availableTags = [];
      state.availableTagMap = new Map();
      if (elements.defaultChannelEntryTagHelp) {
        elements.defaultChannelEntryTagHelp.textContent = "企微标签列表加载失败，可手工填写 tag_id；保存失败时会直接显示真实接口错误。";
      }
    }
    if (state.defaultChannelSelectedTag) {
      setDefaultChannelSelectedTag(state.defaultChannelSelectedTag);
    }
    if (state.tagModal.open) {
      renderTagGroups();
    }
  }

  function bindTagPickerInteractions() {
    const elements = AutomationAgentConfig.elements();
    const defaultChannelFields = AutomationAgentConfig.defaultChannelFields();
    if (elements.defaultChannelEntryTagPickButton) {
      elements.defaultChannelEntryTagPickButton.addEventListener("click", function () {
        openTagPicker();
      });
    }

    if (elements.defaultChannelEntryTagClearButton) {
      elements.defaultChannelEntryTagClearButton.addEventListener("click", function () {
        if (defaultChannelFields.entryTagIdManual) defaultChannelFields.entryTagIdManual.value = "";
        setDefaultChannelSelectedTag(null);
      });
    }

    if (elements.defaultChannelTagModalClose) {
      elements.defaultChannelTagModalClose.addEventListener("click", closeTagPicker);
    }

    if (elements.defaultChannelTagModalCancel) {
      elements.defaultChannelTagModalCancel.addEventListener("click", closeTagPicker);
    }

    if (elements.defaultChannelTagModalConfirm) {
      elements.defaultChannelTagModalConfirm.addEventListener("click", confirmTagSelection);
    }

    if (elements.defaultChannelTagSearch) {
      elements.defaultChannelTagSearch.addEventListener("input", function (event) {
        state.tagModal.search = String((event.target || {}).value || "");
        renderTagGroups();
      });
    }

    if (elements.defaultChannelTagManualInput) {
      elements.defaultChannelTagManualInput.addEventListener("input", function () {
        renderTagGroups();
      });
    }

    if (elements.defaultChannelTagModalOverlay) {
      elements.defaultChannelTagModalOverlay.addEventListener("click", function (event) {
        if (event.target === elements.defaultChannelTagModalOverlay) {
          closeTagPicker();
        }
      });
    }

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && state.tagModal.open) {
        closeTagPicker();
      }
    });
  }

  AutomationAgentConfig.normalizeTagId = normalizeTagId;
  AutomationAgentConfig.buildUnknownTag = buildUnknownTag;
  AutomationAgentConfig.ensureTagKnown = ensureTagKnown;
  AutomationAgentConfig.formatTagGroupName = formatTagGroupName;
  AutomationAgentConfig.formatTagLabel = formatTagLabel;
  AutomationAgentConfig.buildTagBadge = buildTagBadge;
  AutomationAgentConfig.renderSelectedTags = renderSelectedTags;
  AutomationAgentConfig.setDefaultChannelSelectedTag = setDefaultChannelSelectedTag;
  AutomationAgentConfig.currentTagModalSelection = currentTagModalSelection;
  AutomationAgentConfig.filterTags = filterTags;
  AutomationAgentConfig.renderTagGroups = renderTagGroups;
  AutomationAgentConfig.selectTag = selectTag;
  AutomationAgentConfig.unselectTag = unselectTag;
  AutomationAgentConfig.openTagPicker = openTagPicker;
  AutomationAgentConfig.closeTagPicker = closeTagPicker;
  AutomationAgentConfig.confirmTagSelection = confirmTagSelection;
  AutomationAgentConfig.loadWeComTags = loadWeComTags;
  AutomationAgentConfig.bindTagPickerInteractions = bindTagPickerInteractions;
})();
