(() => {
  'use strict';

  const TOKEN = new URLSearchParams(window.location.search).get('t') || '';
  const $ = id => document.getElementById(id);
  let setupBusy = false;
  let lastSelected = '';
  let lastStatus = null;
  let pipelineRows = [];
  let refreshing = false;

  async function api(path, options = {}) {
    const opts = {
      ...options,
      headers: {
        'X-NEL-Token': TOKEN,
        ...(options.headers || {}),
      },
    };
    if (opts.body && typeof opts.body !== 'string') {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(opts.body);
    }
    const response = await fetch(path, opts);
    let doc = {};
    try { doc = await response.json(); } catch (_) { doc = {}; }
    if (!response.ok) throw new Error(doc.error || `${response.status} ${response.statusText}`);
    return doc;
  }

  function validationSelection() {
    const bundledVisible = !$('bundledFields')?.hidden;
    const mode = String($('suiteSelect')?.value || '');
    return bundledVisible && (mode === 'nel-validate' || mode.startsWith('nel-validate-'));
  }

  function installMarkingChoice() {
    if ($('markValidation')) return;
    const runId = $('runId')?.closest('.field');
    if (!runId) return;
    const row = document.createElement('label');
    row.id = 'markValidationRow';
    row.className = 'row';
    row.style.cssText = 'justify-content:flex-start;margin:8px 0 2px;gap:7px';
    row.innerHTML = '<input id="markValidation" type="checkbox" style="width:auto"> Automatically mark validation result <span class="hint">(off by default)</span>';
    runId.insertAdjacentElement('afterend', row);
    $('markValidation').checked = false;
    updateMarkingChoice();
  }

  function updateMarkingChoice() {
    const row = $('markValidationRow');
    const box = $('markValidation');
    if (!row || !box) return;
    const applicable = validationSelection();
    row.hidden = !applicable;
    if (!applicable) box.checked = false;
  }

  function installMarkButton() {
    if ($('markBtn')) return;
    const run = $('runBtn');
    if (!run) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.id = 'markBtn';
    button.hidden = true;
    button.textContent = 'Mark';
    run.insertAdjacentElement('afterend', button);
    button.addEventListener('click', markSelected);
  }

  function installActionError() {
    if ($('providerActionError')) return;
    const actions = document.querySelector('.run-actions');
    if (!actions) return;
    const box = document.createElement('div');
    box.id = 'providerActionError';
    box.className = 'notice error';
    box.hidden = true;
    actions.insertAdjacentElement('beforebegin', box);
  }

  function selectedRef() {
    return document.querySelector('#runsList .run-row.selected')?.title || '';
  }

  function ownerRef(ref) {
    return String(ref || '').split(':', 1)[0];
  }

  function message(text, error = false) {
    const box = $('prepareMsg');
    if (!box) return;
    box.textContent = text;
    box.hidden = !text;
    box.classList.toggle('error', !!error);
  }

  function clinicalComplete(status) {
    if (!status || typeof status !== 'object') return false;
    if (status.kind === 'batch') {
      return ['complete', 'marking_incomplete'].includes(String(status.stored_status || status.status || ''));
    }
    return status.complete === true;
  }

  function markingActionable(status) {
    const marking = status?.marking || {};
    return clinicalComplete(status) && marking.applicable === true && ['pending', 'partial', 'failed', 'stale'].includes(String(marking.status || 'pending'));
  }

  async function runnerMarkingActive(ref) {
    if (!ref) return false;
    try {
      const doc = await api('/api/runner');
      const owner = ownerRef(ref);
      return (doc.children || []).some(row => row.run_id === owner && row.active && row.phase === 'marking');
    } catch (_) {
      return false;
    }
  }

  function applyRunButton(status) {
    const button = $('runBtn');
    if (!button || !clinicalComplete(status)) return;
    button.classList.remove('danger');
    button.disabled = true;
    button.textContent = status.kind === 'batch' ? 'Batch complete' : 'Run complete';
  }

  function applyProgressPolicy(status, markingActive = false) {
    if (!status || status.validation_marking !== false) return;
    const markingStatus = String(status?.marking?.status || 'pending');
    if (markingActive || markingStatus !== 'pending') return;
    const box = $('progressRows');
    if (!box) return;
    box.querySelectorAll('.progress-seg[title="Marking"]').forEach(node => node.remove());
    box.querySelectorAll('.progress-phase').forEach(node => {
      if (/^Marking(?:\b| )/i.test(node.textContent || '')) node.textContent = 'Complete';
    });
  }

  function applyMarkButton(status, markingActive, ownerClinicalComplete = true) {
    const button = $('markBtn');
    if (!button) return;
    const actionable = ownerClinicalComplete && markingActionable(status);
    const validation = profileValidationState();
    button.hidden = !actionable && !markingActive;
    button.disabled = !!markingActive || validation.checking || !validation.valid;
    if (markingActive) button.textContent = 'Marking…';
    else button.textContent = ['partial', 'failed', 'stale'].includes(String(status?.marking?.status || '')) ? 'Retry marking' : 'Mark';
    button.title = (!markingActive && (validation.checking || !validation.valid)) ? validation.detail : '';
  }

  async function markSelected() {
    const ref = selectedRef();
    if (!ref) return;
    const button = $('markBtn');
    if (button) { button.disabled = true; button.textContent = 'Marking…'; }
    try {
      await api('/api/mark', { method: 'POST', body: { run_id: ref } });
      message(`Marking started for ${ref}.`);
    } catch (error) {
      message(error.message, true);
    }
    await refreshSelected(true);
  }

  function profileClassFor(name) {
    return String(pipelineRows.find(row => row.name === name)?.provider_class || '');
  }

  async function restoreFrozenProfile(name) {
    if (!name) return;
    if (!pipelineRows.length) {
      try {
        const doc = await api('/api/pipelines');
        pipelineRows = Array.isArray(doc.pipelines) ? doc.pipelines : [];
      } catch (_) { return; }
    }
    if (!pipelineRows.some(row => row.name === name)) {
      try {
        const doc = await api('/api/pipelines');
        pipelineRows = Array.isArray(doc.pipelines) ? doc.pipelines : pipelineRows;
      } catch (_) { /* keep last usable rows */ }
    }
    const kind = profileClassFor(name);
    const provider = $('providerClass');
    const select = $('profileSelect');
    if (!select) return;
    if (kind && provider && provider.value !== kind) {
      provider.value = kind;
      provider.dispatchEvent(new Event('change', { bubbles: true }));
    }
    for (let attempt = 0; attempt < 12; attempt += 1) {
      if ([...select.options].some(option => option.value === name)) {
        if (select.value !== name) {
          select.value = name;
          select.dispatchEvent(new Event('change', { bubbles: true }));
        }
        return;
      }
      await new Promise(resolve => setTimeout(resolve, 25));
    }
  }

  async function refreshSelected(force = false) {
    if (refreshing) return;
    refreshing = true;
    try {
      const ref = selectedRef();
      if (!ref) {
        lastSelected = '';
        lastStatus = null;
        if ($('markBtn')) $('markBtn').hidden = true;
        return;
      }
      const doc = await api(`/api/status?run=${encodeURIComponent(ref)}`);
      const status = doc.available ? doc.status : null;
      if (!status) return;
      const changed = ref !== lastSelected;
      lastSelected = ref;
      lastStatus = status;
      if (changed || force) await restoreFrozenProfile(String(status.pipeline || ''));
      const active = await runnerMarkingActive(ref);
      let executionStatus = status;
      const owner = ownerRef(ref);
      if (owner && owner !== ref) {
        try {
          const parent = await api(`/api/status?run=${encodeURIComponent(owner)}`);
          if (parent.available && parent.status) executionStatus = parent.status;
        } catch (_) {
          // Keep the child status; the base UI will refresh the parent control.
        }
      }
      applyRunButton(executionStatus);
      applyMarkButton(status, active, clinicalComplete(executionStatus));
      applyProgressPolicy(status, active);
      if (executionStatus !== status) applyProgressPolicy(executionStatus, active);
    } catch (_) {
      // The base interface owns status errors; do not duplicate them here.
    } finally {
      refreshing = false;
    }
  }

  function installKeyDialogPolicy() {
    const dialog = $('keyDialog');
    const chip = $('keyChip');
    if (!dialog || !chip || dialog.dataset.nelManualOnly === '1') return;
    const nativeShow = dialog.showModal.bind(dialog);
    let userRequested = false;
    chip.addEventListener('click', () => {
      userRequested = true;
      setTimeout(() => { userRequested = false; }, 0);
    }, true);
    dialog.showModal = function showModalManualOnly() {
      if (!userRequested) return undefined;
      return nativeShow();
    };
    dialog.dataset.nelManualOnly = '1';
  }

  function profileValidationState() {
    const status = $('profileStatus');
    const text = String(status?.textContent || '').trim();
    const valid = text === 'Valid' || text.startsWith('Valid ');
    const checking = !text || text.startsWith('Checking');
    return {
      valid,
      checking,
      text,
      detail: String(status?.title || text || 'Waiting for profile validation.').trim(),
    };
  }

  function gateProviderActions() {
    const validation = profileValidationState();
    const error = $('providerActionError');
    const invalid = !validation.checking && !validation.valid;
    if (error) {
      error.hidden = !invalid;
      error.textContent = invalid ? `Provider unavailable: ${validation.detail}` : '';
    }

    const prepare = $('prepareBtn');
    if (prepare) {
      prepare.disabled = setupBusy || validation.checking || !validation.valid;
      prepare.title = (!setupBusy && (validation.checking || !validation.valid)) ? validation.detail : '';
    }

    const run = $('runBtn');
    if (run && !run.classList.contains('danger')) {
      if (validation.checking || !validation.valid) {
        if (/^(Start|Resume)/.test(run.textContent || '')) run.disabled = true;
        run.title = validation.detail;
      } else {
        if (/^(Start|Resume)/.test(run.textContent || '')) run.disabled = false;
        run.title = '';
      }
    }

    const mark = $('markBtn');
    if (mark && !mark.hidden && mark.textContent !== 'Marking…') {
      mark.disabled = validation.checking || !validation.valid;
      mark.title = (validation.checking || !validation.valid) ? validation.detail : '';
    }
  }

  function fixMarkingMessage() {
    const box = $('markingView');
    if (!box) return;
    const text = box.textContent || '';
    if (text.includes('Run or resume the validation item to retry marking.')) {
      box.querySelectorAll('.pending').forEach(node => {
        if (node.textContent.includes('Run or resume the validation item to retry marking.')) {
          node.textContent = 'Marking failed. Use Retry marking.';
        }
      });
    }
    if (text.includes('Run or resume to regenerate it.')) {
      box.querySelectorAll('.pending').forEach(node => {
        if (node.textContent.includes('Run or resume to regenerate it.')) {
          node.textContent = 'Marking is stale because the final report changed. Use Retry marking.';
        }
      });
    }
  }

  function installFetchPolicy() {
    const nativeFetch = window.fetch.bind(window);
    window.fetch = async (resource, options = {}) => {
      const url = typeof resource === 'string' ? resource : String(resource?.url || '');
      const method = String(options.method || 'GET').toUpperCase();
      let nextOptions = options;
      const isSetup = method === 'POST' && /\/api\/setup(?:$|\?)/.test(url);
      if (isSetup && typeof options.body === 'string') {
        try {
          const body = JSON.parse(options.body);
          body.mark_validation = validationSelection() && !!$('markValidation')?.checked;
          nextOptions = { ...options, body: JSON.stringify(body) };
        } catch (_) {
          // Leave malformed requests for the server to reject.
        }
      }
      if (isSetup) setupBusy = true;
      try {
        return await nativeFetch(resource, nextOptions);
      } finally {
        if (isSetup) setupBusy = false;
      }
    };
  }

  function wireChoiceUpdates() {
    ['suiteSelect', 'sourcePaste', 'sourceBundled', 'batchToggle'].forEach(id => {
      $(id)?.addEventListener('change', updateMarkingChoice);
      $(id)?.addEventListener('click', () => setTimeout(updateMarkingChoice, 0));
    });
  }

  installFetchPolicy();
  installKeyDialogPolicy();
  installMarkingChoice();
  installMarkButton();
  installActionError();
  wireChoiceUpdates();

  setInterval(() => {
    updateMarkingChoice();
    gateProviderActions();
    fixMarkingMessage();
    refreshSelected(false);
    if (lastStatus) {
      applyProgressPolicy(lastStatus);
      const ref = selectedRef();
      if (!ref.includes(':')) applyRunButton(lastStatus);
    }
  }, 700);
})();
