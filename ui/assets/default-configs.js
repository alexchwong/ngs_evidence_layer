(() => {
  'use strict';

  const TOKEN = new URLSearchParams(window.location.search).get('t') || '';
  const $ = id => document.getElementById(id);
  const nativeFetch = window.fetch.bind(window);
  let boot = null;

  function requestUrl(input) {
    try {
      const raw = typeof input === 'string' ? input : input?.url;
      return raw ? new URL(raw, window.location.href) : null;
    } catch (_) {
      return null;
    }
  }

  function setupUrl(input) {
    return requestUrl(input)?.pathname === '/api/setup';
  }

  function dissentUrl(input) {
    return requestUrl(input)?.pathname === '/api/dissent';
  }

  function apiHeaders(extra = {}) {
    return {'X-NEL-Token': TOKEN, ...extra};
  }

  function auditResponse(doc) {
    const payload = {
      exists: !!doc?.exists,
      text: String(doc?.text || ''),
      size: Number(doc?.size || 0),
      truncated: !!doc?.truncated,
      label: 'Audit log',
    };
    return new Response(JSON.stringify(payload), {
      status: 200,
      headers: {'Content-Type': 'application/json; charset=utf-8'},
    });
  }

  async function loadAuditLog(run) {
    try {
      const response = await nativeFetch(
        `/api/file?run=${encodeURIComponent(run)}&path=${encodeURIComponent('audit-log.md')}`,
        {headers: apiHeaders()},
      );
      if (!response.ok) return auditResponse({exists: false});
      const doc = await response.json();
      return auditResponse({...doc, exists: true});
    } catch (_) {
      return auditResponse({exists: false});
    }
  }

  function setAuditLabel() {
    const tab = $('dissentTab');
    if (tab) tab.textContent = 'Audit log';
    const view = $('dissentView');
    if (!view) return;
    const pending = view.querySelector('.pending');
    if (pending) {
      const current = pending.textContent;
      const replacement = current
        .replace(/Select a run to view dissent\.?/i, 'Select a run to view the audit log.')
        .replace(/Select a batch case to view dissent\.?/i, 'Select a batch case to view the audit log.')
        .replace(/Dissent pending/i, 'Audit log pending')
        .replace(/No dissent recorded\.?/i, 'No audit log recorded.');
      if (replacement !== current) pending.textContent = replacement;
    }
  }

  window.fetch = async function withDefaultWorkflowExtensions(input, init = {}) {
    if (setupUrl(input) && init?.body && $('workflowSelect')?.value === 'default') {
      try {
        const payload = JSON.parse(init.body);
        const selected = String($('defaultConfigSelect')?.value || '').trim();
        if (selected) payload.default_config = selected;
        return nativeFetch(input, {...init, body: JSON.stringify(payload)});
      } catch (_) {
        return nativeFetch(input, init);
      }
    }

    if (dissentUrl(input)) {
      const url = requestUrl(input);
      const run = String(url?.searchParams.get('run') || '').trim();
      setAuditLabel();
      return loadAuditLog(run);
    }

    return nativeFetch(input, init);
  };

  const observer = new MutationObserver(() => setAuditLabel());
  setAuditLabel();

  function installControl() {
    const workflow = $('workflowSelect');
    if (!workflow || $('defaultConfigControl')) return;
    const parent = workflow.closest('.top-control');
    if (!parent) return;
    const control = document.createElement('div');
    control.className = 'top-control';
    control.id = 'defaultConfigControl';
    control.innerHTML = '<label for="defaultConfigSelect">Default config</label><select id="defaultConfigSelect"></select>';
    parent.insertAdjacentElement('afterend', control);
    workflow.addEventListener('change', syncVisibility);
  }

  function fillConfigs() {
    const select = $('defaultConfigSelect');
    if (!select || !boot) return;
    const rows = Array.isArray(boot.default_configs) ? boot.default_configs : [];
    select.replaceChildren(...rows.map(row => {
      const option = document.createElement('option');
      option.value = String(row.id || '');
      option.textContent = String(row.label || row.id || '');
      return option;
    }));
    const preferred = String(boot.default_default_config || 'default');
    if ([...select.options].some(option => option.value === preferred)) select.value = preferred;
  }

  function syncVisibility() {
    const control = $('defaultConfigControl');
    if (!control) return;
    control.hidden = $('workflowSelect')?.value !== 'default';
  }

  async function load() {
    setAuditLabel();
    installControl();
    const view = $('dissentView');
    if (view) observer.observe(view, {subtree: true, childList: true, characterData: true});
    try {
      const response = await nativeFetch('/api/bootstrap', {headers: apiHeaders()});
      if (response.ok) boot = await response.json();
    } catch (_) {
      boot = null;
    }
    fillConfigs();
    syncVisibility();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', load, {once: true});
  else load();
})();
