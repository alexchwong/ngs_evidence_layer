(() => {
  'use strict';

  const TOKEN = new URLSearchParams(window.location.search).get('t') || '';
  const $ = id => document.getElementById(id);
  const nativeFetch = window.fetch.bind(window);
  let boot = null;

  function setupUrl(input) {
    try {
      const raw = typeof input === 'string' ? input : input?.url;
      if (!raw) return false;
      return new URL(raw, window.location.href).pathname === '/api/setup';
    } catch (_) {
      return false;
    }
  }

  window.fetch = function withDefaultConfig(input, init = {}) {
    if (!setupUrl(input) || !init?.body || $('workflowSelect')?.value !== 'default') {
      return nativeFetch(input, init);
    }
    try {
      const payload = JSON.parse(init.body);
      const selected = String($('defaultConfigSelect')?.value || '').trim();
      if (selected) payload.default_config = selected;
      return nativeFetch(input, {...init, body: JSON.stringify(payload)});
    } catch (_) {
      return nativeFetch(input, init);
    }
  };

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
    installControl();
    try {
      const response = await nativeFetch('/api/bootstrap', {headers: {'X-NEL-Token': TOKEN}});
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
