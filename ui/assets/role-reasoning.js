(() => {
  'use strict';
  const LEVELS = ['default', 'none', 'minimal', 'low', 'medium', 'high', 'xhigh'];
  const PROVIDER_LEVELS = {
    openrouter: LEVELS,
    lmstudio: ['default', 'low', 'medium', 'high'],
    other: ['default'],
  };
  const LMSTUDIO_MIN_VERSION = '0.3.29';
  const roleBody = document.getElementById('roleRows');
  if (!roleBody) return;

  let loadedReasoning = {};
  let boot = null;
  const nativeFetch = window.fetch.bind(window);

  function selectedProviderClass() {
    return String(
      document.getElementById('profileProviderClass')?.value ||
      document.getElementById('providerClass')?.value ||
      'other'
    ).toLowerCase();
  }

  function allowedLevels() {
    return PROVIDER_LEVELS[selectedProviderClass()] || PROVIDER_LEVELS.other;
  }

  function installStyles() {
    if (document.getElementById('nelRoleReasoningStyles')) return;
    const style = document.createElement('style');
    style.id = 'nelRoleReasoningStyles';
    style.textContent = `
      #profileDialog table.roles [data-role-reasoning]{min-width:96px}
      #profileDialog .nel-reasoning-note{margin-top:6px}
      #profileDialog .nel-role-description{margin-top:3px;max-width:280px;font-size:10px;line-height:1.25;color:var(--muted)}
    `;
    document.head.appendChild(style);
  }

  function installHeader() {
    const row = document.querySelector('#profileDialog table.roles thead tr');
    if (!row || row.querySelector('[data-reasoning-head]')) return;
    const th = document.createElement('th');
    th.dataset.reasoningHead = '1';
    th.textContent = 'Reasoning';
    row.appendChild(th);
    const block = roleBody.closest('.profile-block');
    const help = block?.querySelector('.help');
    if (help && !block.querySelector('.nel-reasoning-note')) {
      const note = document.createElement('div');
      note.className = 'help nel-reasoning-note';
      note.id = 'nelReasoningNote';
      help.insertAdjacentElement('afterend', note);
    }
  }

  function updateNote() {
    const note = document.getElementById('nelReasoningNote');
    if (!note) return;
    const provider = selectedProviderClass();
    let text = '';
    if (provider === 'lmstudio') {
      text = `LM Studio ${LMSTUDIO_MIN_VERSION}+ uses /v1/responses. Per-role reasoning supports Default, Low, Medium, and High; Default sends no reasoning-effort parameter.`;
    } else if (provider === 'openrouter') {
      text = 'OpenRouter reasoning is per role. Default sends no reasoning-effort parameter; available effort levels depend on the selected model/provider.';
    } else {
      text = 'Per-role reasoning effort is unavailable for this provider class; use Default.';
    }
    if (note.textContent !== text) note.textContent = text;
  }

  function selectedWorkflowMetadata() {
    const name = String(
      document.getElementById('workflowSelect')?.value ||
      boot?.default_workflow ||
      'default'
    );
    const workflow = (boot?.workflows || []).find(row => String(row?.id || '') === name) || {};
    const descriptions = workflow.model_roles && typeof workflow.model_roles === 'object'
      ? workflow.model_roles
      : {};
    return { name, descriptions };
  }

  function updateRolePresentation() {
    const { descriptions } = selectedWorkflowMetadata();
    for (const tr of roleBody.querySelectorAll('tr[data-role]')) {
      const role = tr.dataset.role;
      if (!role) continue;
      const description = String(descriptions[role] || '').trim();
      tr.hidden = !description;
      if (!description) continue;
      const cell = tr.cells?.[0];
      if (!cell) continue;
      let note = cell.querySelector('[data-role-description]');
      if (!note) {
        note = document.createElement('div');
        note.dataset.roleDescription = '1';
        note.className = 'nel-role-description';
        cell.appendChild(note);
      }
      if (note.textContent !== description) note.textContent = description;
    }
  }

  function reasoningForRole(role) {
    const value = String(loadedReasoning?.[role] || 'default').toLowerCase();
    return LEVELS.includes(value) ? value : 'default';
  }

  function applyProviderCapabilities() {
    const allowed = new Set(allowedLevels());
    for (const select of roleBody.querySelectorAll('[data-role-reasoning]')) {
      for (const option of select.options) option.disabled = !allowed.has(option.value);
      if (!allowed.has(select.value)) {
        select.value = 'default';
        select.dataset.userSet = '1';
      }
    }
    updateNote();
  }

  function installSelects() {
    installHeader();
    for (const tr of roleBody.querySelectorAll('tr[data-role]')) {
      let cell = tr.querySelector('[data-reasoning-cell]');
      if (!cell) {
        cell = document.createElement('td');
        cell.dataset.reasoningCell = '1';
        const select = document.createElement('select');
        select.dataset.roleReasoning = '1';
        for (const level of LEVELS) {
          const option = document.createElement('option');
          option.value = level;
          option.textContent = level === 'default' ? 'Default' : level[0].toUpperCase() + level.slice(1);
          select.appendChild(option);
        }
        cell.appendChild(select);
        tr.appendChild(cell);
      }
      const select = cell.querySelector('[data-role-reasoning]');
      if (select && !select.dataset.userSet) select.value = reasoningForRole(tr.dataset.role);
      if (select && !select.dataset.nelBound) {
        select.dataset.nelBound = '1';
        select.addEventListener('change', () => { select.dataset.userSet = '1'; });
      }
    }
    updateRolePresentation();
    applyProviderCapabilities();
  }

  function captureProfile(doc) {
    const rows = doc?.model_roles || doc?.models || {};
    loadedReasoning = {};
    if (rows && typeof rows === 'object') {
      for (const [role, row] of Object.entries(rows)) {
        if (row && typeof row === 'object') loadedReasoning[role] = row.reasoning || 'default';
        else loadedReasoning[role] = 'default';
      }
    }
    queueMicrotask(() => {
      roleBody.querySelectorAll('[data-role-reasoning]').forEach(select => delete select.dataset.userSet);
      installSelects();
    });
  }

  function addReasoningToPayload(payload) {
    if (!payload?.roles || typeof payload.roles !== 'object') return payload;
    for (const tr of roleBody.querySelectorAll('tr[data-role]')) {
      const role = tr.dataset.role;
      const select = tr.querySelector('[data-role-reasoning]');
      if (role && payload.roles[role] && select) payload.roles[role].reasoning = select.value || 'default';
    }
    const providerClass = selectedProviderClass();
    if (providerClass) payload.provider_class = providerClass;
    return payload;
  }

  window.fetch = async function(input, init = {}) {
    const url = typeof input === 'string' ? input : String(input?.url || '');
    let nextInit = init;
    const method = String(init?.method || 'GET').toUpperCase();
    if (method === 'POST' && url.split('?')[0] === '/api/pipeline' && typeof init.body === 'string') {
      try {
        const payload = addReasoningToPayload(JSON.parse(init.body));
        nextInit = { ...init, body: JSON.stringify(payload) };
      } catch (_) {}
    }
    const response = await nativeFetch(input, nextInit);
    if (method === 'GET' && url === '/api/bootstrap' && response.ok) {
      try { boot = await response.clone().json(); } catch (_) {}
      queueMicrotask(updateRolePresentation);
    }
    if (method === 'GET' && url.startsWith('/api/pipeline?') && response.ok) {
      try {
        const doc = await response.clone().json();
        captureProfile(doc?.doc || {});
      } catch (_) {}
    }
    return response;
  };

  document.addEventListener('change', event => {
    if (event.target?.id === 'profileProviderClass' || event.target?.id === 'providerClass') {
      queueMicrotask(applyProviderCapabilities);
    }
    if (event.target?.id === 'workflowSelect') {
      queueMicrotask(updateRolePresentation);
    }
  });
  const observer = new MutationObserver(installSelects);
  observer.observe(roleBody, { childList: true });
  document.getElementById('profileDialog')?.addEventListener('toggle', installSelects);
  document.getElementById('profileDialog')?.addEventListener('click', () => queueMicrotask(installSelects));
  installStyles();
  installSelects();
})();
