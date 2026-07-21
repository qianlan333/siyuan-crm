const pageStateNode = document.getElementById('questionnaire-page-state');
const pageState = JSON.parse(pageStateNode ? pageStateNode.textContent || '{}' : '{}');
const slug = pageState.slug;
const apiUrl = pageState.api_url;
const submitUrl = pageState.submit_url;
const diagnosticsUrl = pageState.diagnostics_url;
const formEl = document.getElementById('questionnaire-form');
const stateEl = document.getElementById('state');
let questionnaire = null;
let submitInFlight = false;
let answersState = {};
let currentQuestionIndex = 0;
let autoNextTimer = null;

if (pageState.mode !== 'questionnaire') {
  window.pageState = pageState;
} else {
  window.pageState = pageState;
  const submittedUrl = pageState.submitted_url;
  const reportedDiagnostics = new Set();
  const weappLaunchPanel = document.getElementById('weapp-launch-panel');
  const weappLaunchHost = document.getElementById('weapp-launch-host');
  const weappLaunchDesc = document.getElementById('weapp-launch-desc');
  const weappFallbackLink = document.getElementById('weapp-fallback-link');

  function setState(message, isError = false) {
    stateEl.textContent = message || '';
    stateEl.className = isError ? 'state error' : 'state';
  }

  function isSafeRedirectUrl(url) {
    return /^https:\/\//.test(url) || /^\/(?!\/)[^\s\\]*$/.test(url);
  }

  function fallbackUrlFromTarget(target) {
    if (!target || !target.enabled) return '';
    const link = target.url_link || {};
    return String(target.fallback_url || target.h5_url || link.url || '');
  }

  function safeFallbackUrl(fallbackUrl, target) {
    const candidate = String(fallbackUrl || fallbackUrlFromTarget(target) || submittedUrl || '').trim();
    return candidate && isSafeRedirectUrl(candidate) ? candidate : submittedUrl;
  }

  function dynamicUrlLinkResolverUrl(target, fallbackUrl) {
    const link = target && target.url_link ? target.url_link : {};
    const sourceUrl = String(link.source_url || '').trim();
    if (!/^https:\/\/[^\s\\]+$/i.test(sourceUrl)) return '';
    const params = new URLSearchParams();
    params.set('source_url', sourceUrl);
    params.set('response_url_key', String(link.response_url_key || 'url_link'));
    const safeFallback = safeFallbackUrl(fallbackUrl, target);
    if (safeFallback) params.set('fallback_url', safeFallback);
    return `/api/h5/navigation-target/url-link/resolve?${params.toString()}`;
  }

  function escapeAttr(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function renderWeappLauncher(target, fallbackUrl) {
    const mini = target && target.mini_program ? target.mini_program : {};
    const safeFallback = safeFallbackUrl(fallbackUrl, target);
    const path = String(mini.path || '/') + (mini.query ? `?${mini.query}` : '');
    weappLaunchPanel.hidden = false;
    weappLaunchHost.innerHTML = '';
    weappFallbackLink.href = safeFallback;
    weappLaunchDesc.textContent = '请点击下方按钮继续。';
    if (!mini.username || !mini.path) {
      weappLaunchDesc.textContent = '无法直接打开，点击备用链接。';
      return;
    }
    weappLaunchHost.innerHTML = `
      <wx-open-launch-weapp
        id="launch-weapp"
        username="${escapeAttr(mini.username)}"
        path="${escapeAttr(path)}">
        <template>
          <style>
            .weapp-launch-button {
              width: 100%;
              height: 48px;
              border: 0;
              border-radius: 8px;
              background: #3370ff;
              color: #fff;
              font-size: 16px;
              font-weight: 800;
            }
          </style>
          <button class="weapp-launch-button">打开小程序</button>
        </template>
      </wx-open-launch-weapp>
    `;
    const launcher = weappLaunchHost.querySelector('#launch-weapp');
    if (launcher) {
      launcher.addEventListener('error', () => {
        weappLaunchDesc.textContent = '无法直接打开，点击备用链接。';
      });
    }
  }

  function handleCompletionTarget(target, fallbackUrl) {
    const normalizedTarget = target || {};
    const safeFallback = safeFallbackUrl(fallbackUrl, normalizedTarget);
    if (!normalizedTarget.enabled) {
      window.location.href = safeFallback;
      return;
    }
    if (normalizedTarget.target_type === 'h5') {
      const h5Url = String(normalizedTarget.h5_url || safeFallback).trim();
      window.location.href = h5Url && isSafeRedirectUrl(h5Url) ? h5Url : safeFallback;
      return;
    }
    if (normalizedTarget.target_type === 'url_link') {
      const link = normalizedTarget.url_link || {};
      const resolverUrl = dynamicUrlLinkResolverUrl(normalizedTarget, safeFallback);
      if (resolverUrl) {
        window.location.href = resolverUrl;
        return;
      }
      if (link.url && isSafeRedirectUrl(link.url)) {
        window.location.href = link.url;
        return;
      }
      window.location.href = safeFallback;
      return;
    }
    if (normalizedTarget.target_type === 'mini_program') {
      const h5Url = normalizedTarget.h5_url && isSafeRedirectUrl(normalizedTarget.h5_url) ? normalizedTarget.h5_url : '';
      if (!pageState.is_wechat_browser) {
        window.location.href = safeFallback || h5Url || submittedUrl;
        return;
      }
      setState('提交成功，正在打开小程序...');
      renderWeappLauncher(normalizedTarget, safeFallback || h5Url || submittedUrl);
      return;
    }
    window.location.href = safeFallback;
  }

  const handleCompletionResponse = window.AICRMQuestionnaireCompletionAction.create({ formEl, weappLaunchPanel, submittedUrl, setState, handleCompletionTarget });
  function normalizedErrorMessage(error, fallback) {
    if (!error) return fallback;
    if (typeof error === 'string') return error;
    if (error instanceof Error && error.message) return error.message;
    return fallback;
  }
  function isOAuthRequired(result) {
    return Boolean(result && (
      result.error === 'oauth_required'
      || result.error === 'unionid_oauth_required'
      || result.source_status === 'oauth_required'
      || result.source_status === 'unionid_oauth_required'
    ));
  }

  function questionnaireDraftKey() {
    const source = questionnaire || pageState.initial_questionnaire || {};
    const revision = source.updated_at || source.version || source.id || 'current';
    return `aicrm:questionnaire-draft:${pageState.slug}:${revision}`;
  }

  function saveQuestionnaireDraft(answers) {
    if (!answers || typeof answers !== 'object') return;
    try {
      window.sessionStorage.setItem(questionnaireDraftKey(), JSON.stringify({ answers }));
    } catch (error) {
      reportClientIssue('draft_save_failed', error, {});
    }
  }

  function clearQuestionnaireDraft() {
    try {
      window.sessionStorage.removeItem(questionnaireDraftKey());
    } catch (error) {
      reportClientIssue('draft_clear_failed', error, {});
    }
  }

  function restoreQuestionnaireDraft() {
    let draft = null;
    try {
      draft = JSON.parse(window.sessionStorage.getItem(questionnaireDraftKey()) || 'null');
    } catch (error) {
      reportClientIssue('draft_restore_failed', error, {});
      return;
    }
    const answers = draft && draft.answers;
    if (!answers || typeof answers !== 'object') return;
    answersState = { ...answersState, ...answers };
    if (questionnaire) renderQuestionnaire(questionnaire);
    setState('已恢复授权前填写的内容，请确认后提交。');
  }

  function oauthRedirectUrl(result) {
    if (result && result.redirect_url) return result.redirect_url;
    if (pageState.oauth_start_url) return pageState.oauth_start_url;
    return '';
  }

  function startOAuthRedirect(result, draftAnswers) {
    const redirectUrl = oauthRedirectUrl(result);
    const message = (result && result.message) || '请先完成企微认证，认证成功后会回到问卷继续提交。';
    saveQuestionnaireDraft(draftAnswers);
    reportClientIssue('oauth_required_redirect', message, {
      hasRedirectUrl: Boolean(redirectUrl),
      submitUrl,
    });
    setState(message, true);
    if (redirectUrl) {
      window.setTimeout(() => {
        window.location.href = redirectUrl;
      }, 450);
      return true;
    }
    setState('请先完成企微认证后再提交问卷；当前认证入口不可用，请联系管理员。', true);
    return false;
  }

  function reportClientIssue(stage, message, extra = {}) {
    if (!diagnosticsUrl || !stage) return;
    const normalizedMessage = normalizedErrorMessage(message, '');
    const dedupeKey = `${stage}:${normalizedMessage}`;
    if (reportedDiagnostics.has(dedupeKey)) return;
    reportedDiagnostics.add(dedupeKey);

    const payload = JSON.stringify({
      stage,
      message: normalizedMessage,
      extra,
    });
    try {
      if (navigator.sendBeacon) {
        navigator.sendBeacon(diagnosticsUrl, new Blob([payload], { type: 'application/json' }));
        return;
      }
    } catch (error) {
      window.__questionnaireDiagnosticsBeaconError = error.message || 'beacon failed';
    }

    fetch(diagnosticsUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: payload,
      keepalive: true,
    }).catch(() => {});
  }

  function collectMetaFromQuery() {
    const params = new URLSearchParams(window.location.search);
    const fields = ['respondent_key', 'openid', 'unionid', 'external_userid', 'source_channel', 'campaign_id', 'staff_id', 'sidebar_context_token', 'sidebar_context'];
    const meta = { ...(pageState.request_hints || {}) };
    fields.forEach((field) => {
      const value = params.get(field);
      if (value) meta[field] = value;
    });
    fields.forEach((field) => {
      const hidden = formEl.querySelector(`input[type="hidden"][name="${field}"]`);
      if (hidden && hidden.value && !meta[field]) meta[field] = hidden.value;
    });
    return meta;
  }

  function validateQuestionnaire(data) {
    if (!data || typeof data !== 'object') {
      throw new Error('问卷数据格式异常');
    }
    if (!Array.isArray(data.questions) || !data.questions.length) {
      throw new Error('问卷题目为空，请稍后重试');
    }
  }

  function normalizeAnswerDisplayMode(value) {
    return ['all_in_one', 'one_by_one'].includes(value) ? value : 'all_in_one';
  }

  function getAnswerDisplayMode(data = questionnaire) {
    return normalizeAnswerDisplayMode((data && data.answer_display_mode) || pageState.answer_display_mode);
  }

  function getInitialAnswersFromPrefill() {
    const prefillFields = pageState.prefill_fields || {};
    const answers = {};
    if (!questionnaire || !Array.isArray(questionnaire.questions)) return answers;
    questionnaire.questions.forEach((question) => {
      const fieldName = `q_${question.id}`;
      const value = prefillFields[fieldName];
      if (value === undefined || value === null || value === '' || (Array.isArray(value) && !value.length)) return;
      if (question.type === 'multi_choice') {
        answers[question.id] = Array.isArray(value) ? value.map(String) : [String(value)];
        return;
      }
      if (question.type === 'single_choice') {
        answers[question.id] = String(value);
        return;
      }
      answers[question.id] = String(value);
    });
    return answers;
  }

  function isOtherOption(option) {
    return option && option.is_other === true;
  }

  function choiceValueToIds(value, question) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      return (value.selected_option_ids || []).map(String);
    }
    if (question.type === 'multi_choice') {
      return Array.isArray(value) ? value.map(String) : [];
    }
    if (value === undefined || value === null || value === '') return [];
    return [String(value)];
  }

  function getSelectedOptionIds(question) {
    return choiceValueToIds(answersState[question.id], question);
  }

  function getOtherText(question) {
    const value = answersState[question.id];
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      return String(value.other_text || '');
    }
    return '';
  }

  function hasSelectedOther(question, selectedIds) {
    const normalized = new Set((selectedIds || []).map(String));
    return (question.options || []).some((option) => isOtherOption(option) && normalized.has(String(option.id)));
  }

  function setChoiceAnswer(question, selectedIds, otherText = '') {
    const normalizedIds = (selectedIds || []).map(String);
    if (hasSelectedOther(question, normalizedIds)) {
      answersState[question.id] = {
        selected_option_ids: normalizedIds,
        other_text: String(otherText || ''),
      };
      return;
    }
    if (question.type === 'single_choice') {
      answersState[question.id] = normalizedIds.length ? normalizedIds[0] : '';
      return;
    }
    answersState[question.id] = normalizedIds;
  }

  function syncOtherInputVisibility(wrapper, question) {
    const selectedIds = getSelectedOptionIds(question);
    const selectedOther = hasSelectedOther(question, selectedIds);
    const input = wrapper.querySelector(`input[name="q_${question.id}_other_text"]`);
    if (!input) return;
    input.hidden = !selectedOther;
    input.disabled = !selectedOther;
    if (!selectedOther) {
      input.value = '';
      setChoiceAnswer(question, selectedIds, '');
    }
  }

  function updateSelectedClasses(wrapper, question) {
    const selectedIds = new Set(getSelectedOptionIds(question).map(String));
    wrapper.querySelectorAll(`input[name="q_${question.id}"]`).forEach((input) => {
      const label = input.closest('label.option');
      if (!label) return;
      label.classList.toggle('is-selected', selectedIds.has(String(input.value)));
    });
  }

  function isAnswerCompleted(question, value) {
    if (question.type === 'single_choice' || question.type === 'multi_choice') {
      const selectedIds = choiceValueToIds(value, question);
      if (!selectedIds.length) return false;
      if (hasSelectedOther(question, selectedIds)) {
        return getOtherText(question).trim() !== '';
      }
      return true;
    }
    return String(value || '').trim() !== '';
  }

  function validateQuestion(question) {
    const value = answersState[question.id];
    if (question.type === 'single_choice' || question.type === 'multi_choice') {
      const selectedIds = getSelectedOptionIds(question);
      if (question.required && !selectedIds.length) {
        setState(`请完成必填题：“${question.title}”。`, true);
        return false;
      }
      const otherOption = (question.options || []).find((option) => isOtherOption(option) && selectedIds.includes(String(option.id)));
      if (otherOption) {
        const otherText = getOtherText(question).trim();
        if (!otherText) {
          setState(`请填写“${question.title}”中的其它内容。`, true);
          return false;
        }
        const maxLength = Number(otherOption.other_max_length || 80);
        if (otherText.length > maxLength) {
          setState(`“${question.title}”中的其它内容不能超过 ${maxLength} 个字。`, true);
          return false;
        }
      }
      setState('');
      return true;
    }
    if (question.required && !isAnswerCompleted(question, value)) {
      setState(`请完成必填题：“${question.title}”。`, true);
      return false;
    }
    if (question.type === 'mobile' && String(value || '').trim() && !/^1[3-9]\d{9}$/.test(String(value).replace(/\D+/g, ''))) {
      setState('请输入11位有效手机号。', true);
      return false;
    }
    setState('');
    return true;
  }

  function validateCurrentQuestion() {
    const question = questionnaire.questions[currentQuestionIndex];
    if (!question) return true;
    return validateQuestion(question);
  }

  function firstIncompleteRequiredIndex() {
    return questionnaire.questions.findIndex((question) => question.required && !isAnswerCompleted(question, answersState[question.id]));
  }

  function clearAutoNextTimer() {
    if (autoNextTimer) {
      clearTimeout(autoNextTimer);
      autoNextTimer = null;
    }
  }

  function renderQuestionnaire(data) {
    validateQuestionnaire(data);
    questionnaire = data;
    if (!Object.keys(answersState).length) {
      answersState = getInitialAnswersFromPrefill();
    }
    if (getAnswerDisplayMode(data) === 'one_by_one') {
      renderOneByOneQuestion();
      return;
    }
    renderAllInOneQuestionnaire(data);
  }

  function renderAllInOneQuestionnaire(data) {
    clearAutoNextTimer();
    formEl.closest('.questionnaire-card')?.classList.remove('one-by-one-card');
    formEl.innerHTML = '';

    data.questions.forEach((question) => {
      const wrapper = createQuestionShell(question);
      renderQuestionFields(wrapper, question);
      formEl.appendChild(wrapper);
    });

    const submitButton = document.createElement('button');
    submitButton.type = 'submit';
    submitButton.className = 'submit-btn';
    submitButton.textContent = '提交';
    formEl.appendChild(submitButton);
  }

  function createQuestionShell(question, index = null) {
    const wrapper = document.createElement('section');
    wrapper.className = 'question';
    if (index !== null) {
      const number = document.createElement('p');
      number.className = 'question-number';
      number.textContent = `第 ${index + 1} 题`;
      wrapper.appendChild(number);
    }
    const title = document.createElement('h2');
    title.className = 'question-title';
    title.textContent = question.title;
    if (question.required) {
      const required = document.createElement('span');
      required.className = 'required';
      required.textContent = '*';
      title.appendChild(required);
    }
    wrapper.appendChild(title);
    return wrapper;
  }

  function renderChoiceField(wrapper, question, options = {}) {
    const type = question.type === 'single_choice' ? 'radio' : 'checkbox';
    const selectedIds = new Set(getSelectedOptionIds(question).map(String));
    (question.options || []).forEach((option) => {
      const optionId = String(option.id);
      const label = document.createElement('label');
      label.className = 'option';
      const input = document.createElement('input');
      input.type = type;
      input.name = `q_${question.id}`;
      input.value = optionId;
      input.dataset.otherOption = isOtherOption(option) ? '1' : '0';
      if (selectedIds.has(optionId)) {
        input.checked = true;
        label.classList.add('is-selected');
      }
      const text = document.createElement('span');
      text.textContent = option.option_text || option.label || option.value || '';
      label.appendChild(input);
      label.appendChild(text);
      wrapper.appendChild(label);

      if (isOtherOption(option)) {
        const otherInput = document.createElement('input');
        otherInput.type = 'text';
        otherInput.className = 'other-text-input';
        otherInput.name = `q_${question.id}_other_text`;
        otherInput.placeholder = option.other_placeholder || '请填写其它内容';
        otherInput.maxLength = Number(option.other_max_length || 80);
        otherInput.value = getOtherText(question);
        otherInput.hidden = !input.checked;
        otherInput.disabled = !input.checked;
        otherInput.dataset.otherTextInput = '1';
        otherInput.addEventListener('input', (event) => {
          setChoiceAnswer(question, getSelectedOptionIds(question), event.target.value);
          setState('');
        });
        wrapper.appendChild(otherInput);
      }

      input.addEventListener('change', () => {
        setState('');
        clearAutoNextTimer();
        let nextSelectedIds = [];
        if (question.type === 'single_choice') {
          nextSelectedIds = [optionId];
        } else {
          nextSelectedIds = Array.from(wrapper.querySelectorAll(`input[name="q_${question.id}"]:checked`)).map((item) => String(item.value));
        }
        const otherInput = wrapper.querySelector(`input[name="q_${question.id}_other_text"]`);
        const existingOtherText = otherInput ? otherInput.value : '';
        setChoiceAnswer(question, nextSelectedIds, existingOtherText);
        syncOtherInputVisibility(wrapper, question);
        updateSelectedClasses(wrapper, question);
        const selectedOther = hasSelectedOther(question, nextSelectedIds);
        if (selectedOther && otherInput) {
          otherInput.focus();
        }
        if (question.type === 'single_choice' && options.autoAdvance && !selectedOther && currentQuestionIndex < questionnaire.questions.length - 1) {
          autoNextTimer = setTimeout(() => {
            currentQuestionIndex += 1;
            renderOneByOneQuestion();
          }, 450);
        }
      });
    });
    syncOtherInputVisibility(wrapper, question);
    updateSelectedClasses(wrapper, question);
  }

  function renderQuestionFields(wrapper, question, options = {}) {
    if (question.type === 'textarea') {
      const textarea = document.createElement('textarea');
      textarea.name = `q_${question.id}`;
      textarea.placeholder = question.placeholder_text || '';
      textarea.value = String(answersState[question.id] || '');
      textarea.addEventListener('input', (event) => {
        answersState[question.id] = event.target.value;
        setState('');
      });
      wrapper.appendChild(textarea);
      return;
    }
    if (question.type === 'mobile') {
      const input = document.createElement('input');
      input.type = 'tel';
      input.name = `q_${question.id}`;
      input.inputMode = 'numeric';
      input.autocomplete = 'tel';
      input.placeholder = question.placeholder_text || '请输入手机号';
      input.maxLength = 11;
      input.value = String(answersState[question.id] || '');
      input.addEventListener('input', (event) => {
        const mobile = String(event.target.value || '').replace(/\D+/g, '').slice(0, 11);
        event.target.value = mobile;
        answersState[question.id] = mobile;
        setState('');
      });
      wrapper.appendChild(input);
      return;
    }
    renderChoiceField(wrapper, question, options);
  }

  function renderOneByOneQuestion() {
    clearAutoNextTimer();
    formEl.closest('.questionnaire-card')?.classList.add('one-by-one-card');
    const total = questionnaire.questions.length;
    currentQuestionIndex = Math.max(0, Math.min(currentQuestionIndex, total - 1));
    const question = questionnaire.questions[currentQuestionIndex];
    formEl.innerHTML = '';

    const progress = document.createElement('div');
    progress.className = 'progress-head';
    const title = document.createElement('span');
    title.textContent = questionnaire.title || pageState.title || '';
    const count = document.createElement('span');
    count.className = 'progress-count';
    count.textContent = `第 ${currentQuestionIndex + 1} / ${total} 题`;
    progress.appendChild(title);
    progress.appendChild(count);
    formEl.appendChild(progress);

    const track = document.createElement('div');
    track.className = 'progress-track';
    const fill = document.createElement('div');
    fill.className = 'progress-fill';
    fill.style.width = `${Math.round(((currentQuestionIndex + 1) / total) * 100)}%`;
    track.appendChild(fill);
    formEl.appendChild(track);

    const wrapper = createQuestionShell(question, currentQuestionIndex);
    renderQuestionFields(wrapper, question, { autoAdvance: true });
    formEl.appendChild(wrapper);

    const tip = document.createElement('p');
    tip.className = 'one-by-one-tip';
    tip.textContent = question.type === 'single_choice'
      ? '普通选项会自动进入下一题；选择“其它”后请先填写内容。'
      : '完成当前题后点击下一题。';
    formEl.appendChild(tip);

    const actions = document.createElement('div');
    actions.className = 'one-by-one-actions';
    const prevButton = document.createElement('button');
    prevButton.type = 'button';
    prevButton.className = 'nav-btn';
    prevButton.textContent = '上一题';
    prevButton.disabled = currentQuestionIndex === 0;
    prevButton.addEventListener('click', () => {
      clearAutoNextTimer();
      currentQuestionIndex = Math.max(0, currentQuestionIndex - 1);
      setState('');
      renderOneByOneQuestion();
    });

    const nextButton = document.createElement('button');
    nextButton.type = currentQuestionIndex === total - 1 ? 'submit' : 'button';
    nextButton.className = 'nav-btn primary';
    nextButton.textContent = currentQuestionIndex === total - 1 ? '提交测评' : '下一题';
    if (currentQuestionIndex < total - 1) {
      nextButton.addEventListener('click', () => {
        clearAutoNextTimer();
        if (!validateCurrentQuestion()) return;
        currentQuestionIndex += 1;
        renderOneByOneQuestion();
      });
    }
    actions.appendChild(prevButton);
    actions.appendChild(nextButton);
    formEl.appendChild(actions);
  }

  function hydrateInitialQuestionnaire() {
    if (!pageState.initial_questionnaire) return false;
    validateQuestionnaire(pageState.initial_questionnaire);
    questionnaire = pageState.initial_questionnaire;
    renderQuestionnaire(questionnaire);
    restoreQuestionnaireDraft();
    return true;
  }

  function loadQuestionnaire() {
    try {
      if (hydrateInitialQuestionnaire()) {
        if (pageState.form_error) {
          setState(pageState.form_error, true);
        }
        return Promise.resolve();
      }
    } catch (error) {
      reportClientIssue('initial_hydrate_failed', error, {
        questionCount: (pageState.initial_questionnaire && pageState.initial_questionnaire.questions || []).length,
      });
      setState('问卷已返回，但页面渲染失败，请刷新后重试。', true);
    }

    setState('正在加载问卷...');
    return fetch(apiUrl)
      .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
      .then(({ ok, data }) => {
        if (data && data.error === 'already_submitted') {
          handleCompletionResponse(data);
          return;
        }
        if (isOAuthRequired(data)) {
          startOAuthRedirect(data);
          return;
        }
        if (!ok || !data.ok) throw new Error(data.error || '问卷不存在');
        setState('');
        renderQuestionnaire({ ...(data.questionnaire || {}), questions: data.questions || (data.questionnaire || {}).questions || [] });
        restoreQuestionnaireDraft();
      })
      .catch((error) => {
        reportClientIssue('load_failed', error, { apiUrl });
        setState(`${normalizedErrorMessage(error, '加载失败')}。如果持续异常，请关闭页面后重试。`, true);
      });
  }

  function collectChoiceAnswer(question) {
    const name = `q_${question.id}`;
    const checked = Array.from(formEl.querySelectorAll(`input[name="${name}"]:checked`));
    const selectedIds = checked.map((item) => String(item.value));
    if (!selectedIds.length) return undefined;
    if (checked.some((item) => item.dataset.otherOption === '1')) {
      const otherInput = formEl.querySelector(`input[name="${name}_other_text"]`);
      const otherText = otherInput ? otherInput.value.trim() : '';
      return {
        selected_option_ids: selectedIds,
        other_text: otherText,
      };
    }
    return question.type === 'single_choice' ? selectedIds[0] : selectedIds;
  }

  function collectAnswers() {
    if (!questionnaire || !Array.isArray(questionnaire.questions)) {
      throw new Error('问卷尚未完成初始化');
    }
    const answers = {};
    questionnaire.questions.forEach((question) => {
      const name = `q_${question.id}`;
      if (question.type === 'single_choice' || question.type === 'multi_choice') {
        const answer = collectChoiceAnswer(question);
        if (answer !== undefined) answers[question.id] = answer;
        return;
      }
      if (question.type === 'textarea') {
        const textarea = formEl.querySelector(`textarea[name="${name}"]`);
        if (textarea && textarea.value.trim()) answers[question.id] = textarea.value.trim();
        return;
      }
      const input = formEl.querySelector(`input[name="${name}"]`);
      if (input && input.value.trim()) answers[question.id] = input.value.trim();
    });
    return answers;
  }

  function normalizeOneByOneAnswersForSubmit() {
    const answers = {};
    questionnaire.questions.forEach((question) => {
      const value = answersState[question.id];
      if (question.type === 'single_choice' || question.type === 'multi_choice') {
        const selectedIds = getSelectedOptionIds(question);
        if (!selectedIds.length) return;
        if (hasSelectedOther(question, selectedIds)) {
          answers[question.id] = {
            selected_option_ids: selectedIds,
            other_text: getOtherText(question).trim(),
          };
          return;
        }
        answers[question.id] = question.type === 'single_choice' ? selectedIds[0] : selectedIds;
        return;
      }
      const text = String(value || '').trim();
      if (text) answers[question.id] = text;
    });
    return answers;
  }

  function validateAllQuestions() {
    for (let index = 0; index < questionnaire.questions.length; index += 1) {
      const question = questionnaire.questions[index];
      if (!validateQuestion(question)) {
        if (getAnswerDisplayMode() === 'one_by_one') {
          currentQuestionIndex = index;
          renderOneByOneQuestion();
        }
        return false;
      }
    }
    setState('');
    return true;
  }

  formEl.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!questionnaire || submitInFlight) return;
    const submitButton = formEl.querySelector('button[type="submit"]');
    if (!validateAllQuestions()) return;
    submitInFlight = true;
    if (submitButton) submitButton.disabled = true;
    setState('提交中...');
    try {
      const answers = getAnswerDisplayMode() === 'one_by_one' ? normalizeOneByOneAnswersForSubmit() : collectAnswers();
      const response = await fetch(submitUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...collectMetaFromQuery(), answers }),
      });
      const result = await response.json();
      if (result && result.error === 'already_submitted') {
        handleCompletionResponse(result);
        return;
      }
      if (isOAuthRequired(result)) {
        startOAuthRedirect(result, answers);
        return;
      }
      if (!response.ok || !result.success) {
        throw new Error(result.error || '提交失败');
      }
      clearQuestionnaireDraft();
      handleCompletionResponse(result);
    } catch (error) {
      reportClientIssue('submit_failed', error, { submitUrl });
      setState(normalizedErrorMessage(error, '提交失败，请稍后重试'), true);
    } finally {
      submitInFlight = false;
      if (submitButton) submitButton.disabled = false;
    }
  });

  window.addEventListener('error', (event) => {
    reportClientIssue('window_error', event.error || event.message || 'unknown_error', {
      filename: event.filename || '',
      lineno: event.lineno || 0,
      colno: event.colno || 0,
    });
  });

  window.addEventListener('unhandledrejection', (event) => {
    reportClientIssue('unhandled_rejection', event.reason || 'unknown_rejection');
  });

  loadQuestionnaire();
}
