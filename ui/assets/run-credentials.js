(() => {
  'use strict';

  const TOKEN = new URLSearchParams(window.location.search).get('t') || '';
  const $ = id => document.getElementById(id);
  let bypassRunGate = false;
  let pendingRunRef = '';
  let refreshTimer = null;
  let refreshSeq = 0;
  let explicitKeyDialogUntil = 0;

  async function api(path) {
    const response = await fetch(path, { headers: { 'X-NEL-Token': TOKEN } });
    let doc = {};
    try {
      doc = await response.json();
    } catch (_) {
      doc = { error: await response.text() };
    }
    if (!response.ok) throw new Error(doc.error || `${response.status} ${response.statusText}`);
    return doc;
  }

  function installStyles() {
    if ($('nelRunCredentialStyles')) return;
    const style = document.createElement('style');
    style.id = 'nelRunCredentialStyles';
    style.textContent = `
      #runCredentialStatus{font-size:11px;line-height:1.25;max-width:260px;white-space:normal}
      #runCredentialStatus.error{color:var(--danger)}
      .run-actions{flex-wrap:wrap;align-items:center}
    `;
    document.head.appendChild(style);
  }

  function installStatus() {
    if ($('runCredentialStatus')) return $('runCredentialStatus');
    const runButton = $('runBtn');
    const actions = runButton?.closest('.run-actions');
    if (!runButton || !actions) return null;
    const status = document.createElement('span');
    status.id = 'runCredentialStatus';
    status.hidden = true;
    actions.appendChild(status);
    return status;
  }

  function setStatus(text = '', error = false) {
    const status = installStatus();
    if (!status) return;
    status.textContent = text;
    status.hidden = !text;
    status.classList.toggle('error', !!error);
  }

  function selectedRunRef() {
    return String(document.querySelector('#runsList .run-row.selected')?.title || '').trim();
  }

  function credentialLabel(doc) {
    const env = String(doc?.env || doc?.credential_env || '').trim();
    return env ? `API key required (${env})` : 'API key required';
  }

  async function credentialForCurrentContext() {
    const runRef = selectedRunRef();
    if (runRef) {
      return api(`/api/run-credential?run=${encodeURIComponent(runRef)}`);
    }
    const profile = String($('profileSelect')?.value || '').trim();
    if (!profile) return { credential_required: false };
    const cul = String($('culSelect')?.value || '').trim();
    return api(`/api/config-check?pipeline=${encodeURIComponent(profile)}&cul=${encodeURIComponent(cul)}`);
  }

  async function refreshStatus() {
    const seq = ++refreshSeq;
    try {
      const doc = await credentialForCurrentContext();
      if (seq !== refreshSeq) return;
      if (doc?.credential_required) setStatus(credentialLabel(doc), true);
      else setStatus('');
    } catch (_) {
      if (seq === refreshSeq) setStatus('');
    }
  }

  function scheduleRefresh() {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(refreshStatus, 80);
  }

  function allowKeyDialogFor(ms = 1500) {
    explicitKeyDialogUntil = Math.max(explicitKeyDialogUntil, Date.now() + ms);
  }

  function installKeyDialogGuard() {
    const dialog = $('keyDialog');
    if (!dialog || dialog.dataset.nelCredentialGuard === '1') return;
    dialog.dataset.nelCredentialGuard = '1';
    const nativeShowModal = dialog.showModal.bind(dialog);
    dialog.showModal = function guardedShowModal() {
      if (Date.now() > explicitKeyDialogUntil) return;
      if (!dialog.open) nativeShowModal();
    };

    document.addEventListener('click', event => {
      if (event.target.closest?.('#keyChip, #loadModels')) allowKeyDialogFor();
    }, true);
  }

  function openKeyDialog(env) {
    const dialog = $('keyDialog');
    if (!dialog || !env) return;
    allowKeyDialogFor();
    if ($('keyEnv')) $('keyEnv').value = env;
    if ($('keyValue')) $('keyValue').value = '';
    const msg = $('keyMsg');
    if (msg) {
      msg.textContent = '';
      msg.hidden = true;
      msg.classList.remove('error');
    }
    dialog.showModal();
    setTimeout(() => $('keyValue')?.focus(), 0);
  }

  async function checkRunCredential(runRef) {
    return api(`/api/run-credential?run=${encodeURIComponent(runRef)}`);
  }

  function redispatchRun() {
    const button = $('runBtn');
    if (!button || button.disabled) return;
    bypassRunGate = true;
    button.click();
  }

  function installRunGate() {
    document.addEventListener('click', event => {
      const button = event.target.closest?.('#runBtn');
      if (!button || button.disabled || button.classList.contains('danger')) return;
      if (bypassRunGate) {
        bypassRunGate = false;
        return;
      }
      const runRef = selectedRunRef();
      if (!runRef) return;

      event.preventDefault();
      event.stopImmediatePropagation();
      void (async () => {
        try {
          const doc = await checkRunCredential(runRef);
          if (!doc?.credential_required) {
            setStatus('');
            redispatchRun();
            return;
          }
          pendingRunRef = runRef;
          setStatus(credentialLabel(doc), true);
          openKeyDialog(String(doc.env || ''));
        } catch (error) {
          setStatus(error.message || 'Could not check provider credentials.', true);
        }
      })();
    }, true);
  }

  function installKeySaveResume() {
    const msg = $('keyMsg');
    const dialog = $('keyDialog');
    if (!msg || !dialog) return;
    const observer = new MutationObserver(() => {
      const text = msg.textContent.trim();
      if (text === 'Session key updated.') {
        const runRef = pendingRunRef;
        pendingRunRef = '';
        void (async () => {
          await refreshStatus();
          if (runRef && selectedRunRef() === runRef) redispatchRun();
        })();
      } else if (text === 'Session key forgotten.') {
        scheduleRefresh();
      }
    });
    observer.observe(msg, { childList: true, characterData: true, subtree: true });
    dialog.addEventListener('close', () => {
      if (msg.textContent.trim() !== 'Session key updated.') pendingRunRef = '';
      scheduleRefresh();
    });
  }

  function installRefreshObservers() {
    $('profileSelect')?.addEventListener('change', scheduleRefresh);
    $('culSelect')?.addEventListener('change', scheduleRefresh);
    const runs = $('runsList');
    if (runs) new MutationObserver(scheduleRefresh).observe(runs, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
    const runButton = $('runBtn');
    if (runButton) new MutationObserver(scheduleRefresh).observe(runButton, { childList: true, attributes: true, attributeFilter: ['disabled', 'class'] });
  }

  installStyles();
  installStatus();
  installKeyDialogGuard();
  installRunGate();
  installKeySaveResume();
  installRefreshObservers();
  scheduleRefresh();
})();
