(function () {
  "use strict";

  const CustomerProfile = window.CustomerProfile || {};
  window.CustomerProfile = CustomerProfile;

  const escapeHtml = CustomerProfile.escapeHtml;
  const requestJson = CustomerProfile.requestJson;
  const showSectionError = CustomerProfile.showSectionError;
  const showSectionEmpty = CustomerProfile.showSectionEmpty;

  function renderLiveTags(payload) {
    const stateNode = document.querySelector("[data-profile-tags-state]");
    const listNode = document.querySelector("[data-profile-tags]");
    if (!stateNode || !listNode) return;
    const tags = payload && Array.isArray(payload.tags) ? payload.tags : [];
    if (!tags.length) {
      listNode.hidden = true;
      showSectionEmpty(stateNode, "当前没有实时标签", "暂未读取到企微标签。");
      return;
    }
    stateNode.hidden = true;
    listNode.hidden = false;
    listNode.innerHTML = tags
      .map((tag) => `<span class="admin-profile-tag">${tag.tag_name || tag.tag_id}</span>`)
      .join("");
  }

  function renderQuestionnaireAnswers(payload) {
    const stateNode = document.querySelector("[data-profile-questionnaire-state]");
    const wrapNode = document.querySelector("[data-profile-questionnaire-wrap]");
    const bodyNode = document.querySelector("[data-profile-questionnaire-body]");
    if (!stateNode || !wrapNode || !bodyNode) return;
    const answers = payload && Array.isArray(payload.answers) ? payload.answers : [];
    if (!answers.length) {
      wrapNode.hidden = true;
      showSectionEmpty(stateNode, "当前没有问卷记录", "暂未找到可展示的问卷问答。");
      return;
    }
    bodyNode.innerHTML = answers
      .map(
        (item) => `
          <tr>
            <td>${item.question || "未命名问题"}</td>
            <td>${item.answer || "未填写"}</td>
          </tr>
        `,
      )
      .join("");
    stateNode.hidden = true;
    wrapNode.hidden = false;
  }

  function renderMessages(payload) {
    const stateNode = document.querySelector("[data-profile-messages-state]");
    const listNode = document.querySelector("[data-profile-messages]");
    if (!stateNode || !listNode) return;
    const messages = payload && Array.isArray(payload.messages) ? payload.messages : [];
    if (!messages.length) {
      listNode.hidden = true;
      showSectionEmpty(stateNode, "当前没有聊天记录", "暂未找到聊天内容。");
      return;
    }
    listNode.innerHTML = messages
      .map(
        (item) => `
          <article class="admin-profile-message">
            <div class="admin-profile-message-meta">
              <span>${escapeHtml(item.send_time || "未知时间")}</span>
              <span>${escapeHtml(item.speaker || "未知发送方")}</span>
            </div>
            <div class="admin-profile-message-content">${escapeHtml(item.content || "无内容")}</div>
          </article>
        `,
      )
      .join("");
    stateNode.hidden = true;
    listNode.hidden = false;
  }

  function loadLiveTags(root) {
    return requestJson(root.dataset.tagsUrl)
      .then((payload) => {
        renderLiveTags(payload);
        return payload;
      })
      .catch((error) => {
        showSectionError(document.querySelector("[data-profile-tags-state]"), error.message || "当前无法加载实时标签");
        return null;
      });
  }

  function loadQuestionnaireAnswers(root) {
    return requestJson(root.dataset.questionnaireUrl)
      .then((payload) => {
        renderQuestionnaireAnswers(payload);
        return payload;
      })
      .catch((error) => {
        showSectionError(document.querySelector("[data-profile-questionnaire-state]"), error.message || "当前无法加载问卷记录");
        return null;
      });
  }

  function loadMessages(root, fetchAll) {
    const url = new URL(root.dataset.messagesUrl, window.location.origin);
    if (fetchAll) {
      url.searchParams.set("fetch_all", "1");
    }
    return requestJson(url.toString())
      .then((payload) => {
        renderMessages(payload);
        return payload;
      })
      .catch((error) => {
        showSectionError(document.querySelector("[data-profile-messages-state]"), error.message || "当前无法加载聊天记录");
        return null;
      });
  }

  function wireFetchAllButton(root) {
    const button = document.querySelector("[data-profile-fetch-all-messages]");
    if (!button) return;
    button.addEventListener("click", () => {
      button.disabled = true;
      button.textContent = "正在加载全部聊天记录";
      loadMessages(root, true).finally(() => {
        button.disabled = false;
        button.textContent = "获取全部聊天记录";
      });
    });
  }

  function bootBasicSections(root) {
    loadLiveTags(root);
    loadQuestionnaireAnswers(root);
    loadMessages(root, false);
    wireFetchAllButton(root);
  }

  CustomerProfile.renderLiveTags = renderLiveTags;
  CustomerProfile.renderQuestionnaireAnswers = renderQuestionnaireAnswers;
  CustomerProfile.renderMessages = renderMessages;
  CustomerProfile.loadLiveTags = loadLiveTags;
  CustomerProfile.loadQuestionnaireAnswers = loadQuestionnaireAnswers;
  CustomerProfile.loadMessages = loadMessages;
  CustomerProfile.bootBasicSections = bootBasicSections;
})();
