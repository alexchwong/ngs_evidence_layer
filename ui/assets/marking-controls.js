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

  function applyMarkButton(status, markingActive, ownerClinicalComplete = true) {
    const button = $('markBtn');
    if (!button) return;
    const actionable = ownerClinicalComplete && markingActionable(status);
    button.hidden = !actionable && !markingActive;
    button.disabled = !!markingActive;
    if (markingActive) button.textContent = 'Marking…';
    else button.textContent = ['partial', 'failed', 'stale'].includes(String(status?.marking?.status || '')) ? 'Retry marking' : 'Mark validation';
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
      if (ref !== selectedRef()) return;
      const status = doc.available ? doc.status : null;
      if (!status) return;
      const changed = ref !== lastSelected;
      lastSelected = ref;
      lastStatus = status;
      if (changed || force) await restoreFrozenProfile(String(status.pipeline || ''));
      if (ref !== selectedRef()) return;
      const active = await runnerMarkingActive(ref);
      if (ref !== selectedRef()) return;
      let executionStatus = status;
      const owner = ownerRef(ref);
      if (owner && owner !== ref) {
        try {
          const parent = await api(`/api/status?run=${encodeURIComponent(owner)}`);
          if (ref !== selectedRef()) return;
          if (parent.available && parent.status) executionStatus = parent.status;
        } catch (_) {
          // Keep the child status; the base UI will refresh the parent control.
        }
      }
      if (ref !== selectedRef()) return;
      applyMarkButton(status, active, clinicalComplete(executionStatus));
    } catch (_) {
      // The base interface owns status errors; do not duplicate them here.
    } finally {
      refreshing = false;
    }
  }

  function installStabilityStyles() {
    if ($('nelUiStabilityStyles')) return;
    const style = document.createElement('style');
    style.id = 'nelUiStabilityStyles';
    style.textContent = `
      .model-activity-head{display:grid!important;grid-template-columns:minmax(0,1fr) auto;grid-template-rows:auto auto;align-items:center!important;gap:4px 10px!important}
      .model-activity-title{grid-column:1;grid-row:1;min-width:0}
      .model-activity-tabs{grid-column:2;grid-row:1;justify-self:end;min-width:max-content}
      .model-activity-meta{grid-column:1/-1;grid-row:2;min-width:0!important;white-space:normal!important;overflow:visible!important;text-overflow:clip!important;overflow-wrap:anywhere;word-break:break-word}
    `;
    document.head.appendChild(style);
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

  function gatePrepare() {
    const button = $('prepareBtn');
    if (!button) return;
    const status = $('profileStatus');
    const text = String(status?.textContent || '').trim();
    const valid = text === 'Valid' || text.startsWith('Valid ');
    const checking = !text || text.startsWith('Checking');
    if (setupBusy || checking || !valid) {
      button.disabled = true;
      button.dataset.nelProfileGate = '1';
      if (!setupBusy) button.title = text || 'Waiting for profile validation.';
      return;
    }
    if (button.dataset.nelProfileGate === '1') {
      button.disabled = false;
      button.title = '';
      delete button.dataset.nelProfileGate;
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
  installStabilityStyles();
  installKeyDialogPolicy();
  installMarkingChoice();
  installMarkButton();
  wireChoiceUpdates();

  setInterval(() => {
    updateMarkingChoice();
    gatePrepare();
    fixMarkingMessage();
    refreshSelected(false);
  }, 700);
})();
