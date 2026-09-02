(() => {
  'use strict';

  const OTHER_MODEL = '__nel_other_model__';
  const TOKEN = new URLSearchParams(window.location.search).get('t') || '';
  const $ = id => document.getElementById(id);
  const CLASS_LABELS = {
    lmstudio: 'LM Studio',
    openrouter: 'OpenRouter',
    other: 'Other OpenAI-compatible',
  };
  const PROVIDER_DEFAULTS = {
    lmstudio: {
      baseUrl: 'http://localhost:1234/v1',
      baseUrlEnv: 'NEL_LMSTUDIO_BASE_URL',
      apiKeyEnv: 'NEL_LMSTUDIO_API_KEY',
      timeoutS: '900',
      apiKeyRequired: false,
    },
    openrouter: {
      baseUrl: 'https://openrouter.ai/api/v1',
      baseUrlEnv: 'NEL_OPENROUTER_BASE_URL',
      apiKeyEnv: 'OPENROUTER_API_KEY',
      timeoutS: '900',
      apiKeyRequired: true,
    },
  };
  const PROVIDER_DESCRIPTIONS = {
    lmstudio: 'Local OpenAI-compatible models served by LM Studio.',
    openrouter: 'Hosted models accessed through OpenRouter with optional provider routing.',
    other: 'Custom OpenAI-compatible provider profile.',
  };

  let boot = { pipelines: [], shipped: [] };
  let openRouterSuggestions = [];
  let topValidation = { name: '', pending: true, ok: false, errors: ['Not validated yet.'] };
  let topValidationSeq = 0;
  let editorValidationSeq = 0;
  let activeCatalogue = { key: '', kind: '', models: [], providers: [] };
  const catalogueCache = new Map();
  const providerEndpointCache = new Map();
  let overwriteApprovedName = '';

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
    try {
      doc = await response.json();
    } catch (_) {
      doc = { error: await response.text() };
    }
    if (!response.ok) throw new Error(doc.error || `${response.status} ${response.statusText}`);
    return doc;
  }

  function profileRow(name) {
    return (boot.pipelines || []).find(row => row.name === name) || null;
  }

  function classForRow(row) {
    return String(row?.provider_class || 'other').toLowerCase();
  }

  function availableClasses() {
    const values = ['lmstudio', 'openrouter'];
    if ((boot.pipelines || []).some(row => classForRow(row) === 'other')) values.push('other');
    return values;
  }

  function fillClassSelect(select, preferred = '') {
    if (!select) return;
    const classes = availableClasses();
    const desired = classes.map(kind => `${kind}:${CLASS_LABELS[kind]}`).join('|');
    if (select.dataset.nelClasses !== desired) {
      select.replaceChildren(...classes.map(kind => {
        const option = document.createElement('option');
        option.value = kind;
        option.textContent = CLASS_LABELS[kind];
        return option;
      }));
      select.dataset.nelClasses = desired;
    }
    if (classes.includes(preferred)) select.value = preferred;
    else if (!classes.includes(select.value)) select.value = classes[0] || 'lmstudio';
  }

  function installProfileStyles() {
    if ($('nelProviderProfileStyles')) return;
    const style = document.createElement('style');
    style.id = 'nelProviderProfileStyles';
    style.textContent = `
      #profileDialog .nel-profile-toolbar{display:grid;grid-template-columns:minmax(150px,.8fr) minmax(220px,1.35fr) auto;gap:8px;align-items:end}
      #profileDialog .nel-profile-toolbar .field{margin:0}
      #profileDialog .nel-profile-toolbar button{height:38px;white-space:nowrap}
      #profileDialog .nel-profile-identity-actions{display:flex;justify-content:flex-end;margin-top:8px}
      #profileDialog .nel-profile-identity-actions #saveProfile{min-height:38px;white-space:nowrap}
      #profileDialog .nel-connection-summary{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
      #profileDialog .nel-connection-summary .help{flex:1;min-width:260px;margin:0}
      #profileDialog .nel-connection-advanced{margin-top:10px;padding-top:10px;border-top:1px solid var(--line)}
      #profileDialog .alias-head{grid-template-columns:minmax(125px,.8fr) minmax(320px,2fr) 112px 78px;gap:8px;align-items:end}
      #profileDialog .alias-head>.field{display:flex;flex-direction:column;gap:5px;min-width:0}
      #profileDialog .alias-head input,#profileDialog .alias-head select,#profileDialog .alias-head button{min-height:38px}
      #profileDialog [data-nel-model-select]{margin:0!important;width:100%}
      #profileDialog .routing-grid{grid-template-columns:minmax(260px,1.5fr) minmax(170px,.8fr);align-items:end}
      #profileDialog .nel-routing-provider-field{grid-column:auto}
      #profileDialog .nel-routing-status{margin-top:4px}
      #profileDialog .dialog-foot #saveProfile{display:none}
      #profileOverwriteDialog{width:min(470px,calc(100vw - 36px))}
      @media(max-width:760px){#profileDialog .nel-profile-toolbar{grid-template-columns:1fr 1fr}#profileDialog .alias-head{grid-template-columns:1fr}#profileDialog .routing-grid{grid-template-columns:1fr}#profileDialog .nel-routing-provider-field{grid-column:auto}}
    `;
    document.head.appendChild(style);
  }

  function insertProviderControls() {
    const profileSelect = $('profileSelect');
    if (!profileSelect || $('providerClass')) return;

    const profileControl = profileSelect.closest('.top-control');
    const providerControl = document.createElement('div');
    providerControl.className = 'top-control';
    providerControl.style.minWidth = '118px';
    providerControl.innerHTML = '<label for="providerClass">Provider Class</label><select id="providerClass"></select>';
    profileControl.parentNode.insertBefore(providerControl, profileControl);

    const topLabel = profileControl.querySelector('label[for="profileSelect"]');
    if (topLabel && !$('profileStatus')) {
      topLabel.style.display = 'flex';
      topLabel.style.gap = '6px';
      topLabel.style.alignItems = 'center';
      topLabel.innerHTML = 'Profile <span id="profileStatus" style="font-size:9px;text-transform:none;letter-spacing:0;overflow:hidden;text-overflow:ellipsis"></span>';
    }

    const profileDialog = $('profileDialog');
    const firstBlock = profileDialog?.querySelector('.dialog-body > .profile-block');
    const profileLoad = $('profileLoad');
    const loadButton = $('loadProfile');
    const saveButton = $('saveProfile');
    const profileMsg = $('profileMsg');
    if (firstBlock && profileLoad && loadButton && saveButton && !$('profileProviderClass')) {
      firstBlock.innerHTML = '';
      const toolbar = document.createElement('div');
      toolbar.className = 'nel-profile-toolbar';
      toolbar.innerHTML = `
        <div class="field"><label for="profileProviderClass">Provider Class</label><select id="profileProviderClass"></select></div>
        <div class="field"><label for="profileLoad">Saved profile <span id="profileLoadStatus" style="font-size:9px;text-transform:none;letter-spacing:0"></span></label></div>
      `;
      toolbar.children[1].appendChild(profileLoad);
      toolbar.appendChild(loadButton);
      firstBlock.appendChild(toolbar);
      if (profileMsg) firstBlock.appendChild(profileMsg);

      const identityBlock = firstBlock.nextElementSibling;
      if (identityBlock?.classList.contains('profile-block')) {
        let actions = identityBlock.querySelector('.nel-profile-identity-actions');
        if (!actions) {
          actions = document.createElement('div');
          actions.className = 'nel-profile-identity-actions';
          identityBlock.appendChild(actions);
        }
        actions.appendChild(saveButton);
      }
    }

    $('checkProfile')?.remove();
    const overwrite = $('overwriteProfile');
    if (overwrite) {
      overwrite.checked = false;
      const row = overwrite.closest('label');
      if (row) row.hidden = true;
    }

    fillClassSelect($('providerClass'));
    fillClassSelect($('profileProviderClass'));
    installConnectionSummary();
    installOverwriteConfirmation();
  }

  function suggestedDescription(kind) {
    return PROVIDER_DESCRIPTIONS[kind] || PROVIDER_DESCRIPTIONS.other;
  }

  function updateDescriptionSuggestion(kind) {
    const input = $('profileDescription');
    if (!input) return;
    const prior = input.dataset.nelSuggestedDescription || '';
    const next = suggestedDescription(kind);
    input.placeholder = next;
    if (!input.value.trim() || (prior && input.value.trim() === prior)) input.value = next;
    input.dataset.nelSuggestedDescription = next;
  }

  function fieldConnection() {
    return {
      baseUrl: String($('baseUrl')?.value || '').trim(),
      baseUrlEnv: String($('baseUrlEnv')?.value || '').trim(),
      apiKeyEnv: String($('apiKeyEnv')?.value || '').trim(),
      timeoutS: String($('timeoutS')?.value || '').trim(),
      apiKeyRequired: !!$('apiKeyRequired')?.checked,
    };
  }

  function connectionMatches(connection, defaults) {
    if (!defaults) return false;
    return connection.baseUrl === defaults.baseUrl &&
      connection.baseUrlEnv === defaults.baseUrlEnv &&
      connection.apiKeyEnv === defaults.apiKeyEnv &&
      connection.timeoutS === defaults.timeoutS &&
      connection.apiKeyRequired === defaults.apiKeyRequired;
  }

  function applyConnectionDefaults(kind) {
    const defaults = PROVIDER_DEFAULTS[kind];
    if (!defaults) return false;
    $('baseUrl').value = defaults.baseUrl;
    $('baseUrlEnv').value = defaults.baseUrlEnv;
    $('apiKeyEnv').value = defaults.apiKeyEnv;
    $('timeoutS').value = defaults.timeoutS;
    $('apiKeyRequired').checked = defaults.apiKeyRequired;
    return true;
  }

  function updateConnectionSummary() {
    const summary = $('connectionSummaryText');
    if (!summary) return;
    const kind = providerKindForEditor();
    const current = fieldConnection();
    const defaults = PROVIDER_DEFAULTS[kind];
    if (!defaults) {
      summary.textContent = current.baseUrl ? `Current: ${current.baseUrl}` : 'Custom OpenAI-compatible connection.';
      return;
    }
    const prefix = connectionMatches(current, defaults) ? 'Default' : 'Current · custom';
    const key = current.apiKeyRequired ? (current.apiKeyEnv || 'API key required') : 'no API key required';
    summary.textContent = `${prefix}: ${current.baseUrl || defaults.baseUrl} · ${key} · ${current.timeoutS || defaults.timeoutS}s timeout`;
  }

  function installConnectionSummary() {
    const baseUrl = $('baseUrl');
    const block = baseUrl?.closest('.profile-block');
    const grid = baseUrl?.closest('.grid2');
    if (!block || !grid || $('connectionSummary')) return;
    const keyRow = $('apiKeyRequired')?.closest('label');
    const advanced = document.createElement('div');
    advanced.id = 'connectionAdvanced';
    advanced.className = 'nel-connection-advanced';
    advanced.hidden = true;
    grid.parentNode.insertBefore(advanced, grid);
    advanced.appendChild(grid);
    if (keyRow) advanced.appendChild(keyRow);

    const row = document.createElement('div');
    row.id = 'connectionSummary';
    row.className = 'nel-connection-summary';
    row.innerHTML = '<span class="help" id="connectionSummaryText"></span><button type="button" id="changeConnection">Change…</button>';
    advanced.parentNode.insertBefore(row, advanced);
    $('changeConnection').addEventListener('click', () => {
      advanced.hidden = !advanced.hidden;
      $('changeConnection').textContent = advanced.hidden ? 'Change…' : 'Hide';
    });
    [baseUrl, $('baseUrlEnv'), $('apiKeyEnv'), $('timeoutS'), $('apiKeyRequired')].filter(Boolean).forEach(el => {
      el.addEventListener('input', updateConnectionSummary);
      el.addEventListener('change', updateConnectionSummary);
    });
    const loadModels = $('loadModels');
    if (loadModels) loadModels.textContent = 'Refresh models';
    updateConnectionSummary();
  }

  function ensureOverwriteDialog() {
    if ($('profileOverwriteDialog')) return $('profileOverwriteDialog');
    const dialog = document.createElement('dialog');
    dialog.id = 'profileOverwriteDialog';
    dialog.innerHTML = `
      <div class="dialog-head"><div class="dialog-title">Overwrite profile?</div><button type="button" class="ghost" data-overwrite-cancel>✕</button></div>
      <div class="dialog-body"><div id="profileOverwriteText"></div></div>
      <div class="dialog-foot"><button type="button" data-overwrite-cancel>Cancel</button><button type="button" class="danger" id="confirmProfileOverwrite">Overwrite</button></div>
    `;
    document.body.appendChild(dialog);
    dialog.querySelectorAll('[data-overwrite-cancel]').forEach(button => button.addEventListener('click', () => dialog.close()));
    dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
    $('confirmProfileOverwrite').addEventListener('click', () => {
      const name = String($('profileName')?.value || '').trim();
      if (!name) return;
      overwriteApprovedName = name;
      if ($('overwriteProfile')) $('overwriteProfile').checked = true;
      dialog.close();
      $('saveProfile')?.click();
    });
    return dialog;
  }

  function installOverwriteConfirmation() {
    const saveButton = $('saveProfile');
    if (!saveButton || saveButton.dataset.nelOverwriteGuard === '1') return;
    saveButton.dataset.nelOverwriteGuard = '1';
    ensureOverwriteDialog();
    saveButton.addEventListener('click', event => {
      const name = String($('profileName')?.value || '').trim();
      if (!name) return;
      if (overwriteApprovedName === name) {
        overwriteApprovedName = '';
        return;
      }
      if ($('overwriteProfile')) $('overwriteProfile').checked = false;
      const row = profileRow(name);
      if (!row) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      if (row.shipped) {
        setStatus($('profileLoadStatus'), 'Read-only shipped profile', false);
        const msg = $('profileMsg');
        if (msg) {
          msg.textContent = `Profile ${name} is shipped with NEL and cannot be overwritten. Choose a different profile file name.`;
          msg.classList.add('error');
        }
        return;
      }
      $('profileOverwriteText').innerHTML = `This will replace the existing custom profile <code>${name.replace(/[&<>"']/g, '')}</code>.<br><br>Continue?`;
      $('profileOverwriteDialog').showModal();
    }, true);
  }

  function desiredProfileRows(kind, includeUnreadable = false) {
    return (boot.pipelines || [])
      .filter(row => classForRow(row) === kind && (includeUnreadable || row.readable))
      .sort((a, b) => String(a.name).localeCompare(String(b.name)));
  }

  function optionSignature(rows, includeUnreadable) {
    return rows.map(row => `${row.name}:${row.shipped ? 1 : 0}:${row.readable ? 1 : 0}:${includeUnreadable ? 1 : 0}`).join('|');
  }

  function rebuildProfileSelect(select, rows, preferred = '', includeUnreadable = false) {
    if (!select) return '';
    const signature = optionSignature(rows, includeUnreadable);
    const currentValues = [...select.options].map(option => option.value).join('|');
    const desiredValues = rows.map(row => row.name).join('|');
    if (select.dataset.nelProfileSignature !== signature || currentValues !== desiredValues) {
      select.replaceChildren();
      for (const row of rows) {
        const option = document.createElement('option');
        option.value = row.name;
        const tags = [];
        if (row.shipped) tags.push('shipped');
        if (!row.readable) tags.push('unparseable');
        option.textContent = tags.length ? `${row.name} (${tags.join(', ')})` : row.name;
        select.appendChild(option);
      }
      if (!rows.length) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = `No ${CLASS_LABELS[$('providerClass')?.value] || ''} profiles`;
        select.appendChild(option);
      }
      select.dataset.nelProfileSignature = signature;
    }
    const names = rows.map(row => row.name);
    if (names.includes(preferred)) select.value = preferred;
    else if (!names.includes(select.value)) {
      const shippedDefault = rows.find(row => row.shipped && row.name === classForRow(row));
      const classDefault = rows.find(row => row.name === classForRow(row));
      select.value = (shippedDefault || classDefault || rows[0])?.name || '';
    }
    return select.value;
  }

  function filterTopProfiles(preferred = '') {
    const kind = $('providerClass')?.value || 'lmstudio';
    const rows = desiredProfileRows(kind, false);
    return rebuildProfileSelect($('profileSelect'), rows, preferred, false);
  }

  function filterEditorProfiles(preferred = '') {
    const kind = $('profileProviderClass')?.value || $('providerClass')?.value || 'lmstudio';
    const rows = desiredProfileRows(kind, true);
    return rebuildProfileSelect($('profileLoad'), rows, preferred, true);
  }

  function setStatus(element, text, ok = null, title = '') {
    if (!element) return;
    element.textContent = text;
    element.title = title || text;
    element.style.color = ok === false ? 'var(--danger)' : ok === true ? 'var(--accent)' : 'var(--muted)';
  }

  function validationText(doc) {
    if (doc?.pending) return { short: 'Checking…', title: 'Checking profile configuration.', ok: null };
    const warnings = Array.isArray(doc?.warnings) ? doc.warnings.filter(Boolean) : [];
    const errors = Array.isArray(doc?.errors) ? doc.errors.filter(Boolean) : [];
    if (doc?.ok) {
      return {
        short: warnings.length ? 'Valid ⚠' : 'Valid',
        title: ['Configuration valid.', ...warnings.map(item => `Warning: ${item}`)].join('\n'),
        ok: true,
      };
    }
    const first = errors[0] || 'configuration check failed';
    return {
      short: `Invalid: ${first}`,
      title: errors.length ? errors.map(item => `Error: ${item}`).join('\n') : first,
      ok: false,
    };
  }

  function renderTopValidation() {
    const display = validationText(topValidation);
    setStatus($('profileStatus'), display.short, display.ok, display.title);
    const select = $('profileSelect');
    if (select) select.setAttribute('aria-invalid', String(display.ok === false));
  }

  async function validateProfile(name, target = 'top') {
    const row = profileRow(name);
    const statusEl = target === 'top' ? $('profileStatus') : $('profileLoadStatus');
    if (!name) {
      const doc = { name, pending: false, ok: false, errors: ['No profile selected.'], warnings: [] };
      if (target === 'top') { topValidation = doc; renderTopValidation(); }
      else setStatus(statusEl, 'Invalid: no profile selected', false);
      return doc;
    }
    if (row && row.readable === false) {
      const message = String(row.description || 'profile YAML cannot be parsed').replace(/^unreadable:\s*/i, '');
      const doc = { name, pending: false, ok: false, errors: [message], warnings: [] };
      if (target === 'top') { topValidation = doc; renderTopValidation(); }
      else setStatus(statusEl, `Invalid: ${message}`, false, message);
      return doc;
    }

    const seq = target === 'top' ? ++topValidationSeq : ++editorValidationSeq;
    const pending = { name, pending: true, ok: false, errors: [], warnings: [] };
    if (target === 'top') { topValidation = pending; renderTopValidation(); }
    else setStatus(statusEl, 'Checking…', null);

    let doc;
    try {
      doc = await api(`/api/config-check?pipeline=${encodeURIComponent(name)}&cul=${encodeURIComponent($('culSelect')?.value || '')}`);
    } catch (error) {
      doc = { ok: false, errors: [error.message], warnings: [] };
    }
    doc = {
      name,
      pending: false,
      ok: !!doc.ok,
      errors: Array.isArray(doc.errors) ? doc.errors : [],
      warnings: Array.isArray(doc.warnings) ? doc.warnings : [],
    };
    if (target === 'top') {
      if (seq !== topValidationSeq || $('profileSelect')?.value !== name) return doc;
      topValidation = doc;
      renderTopValidation();
    } else {
      if (seq !== editorValidationSeq || $('profileLoad')?.value !== name) return doc;
      const display = validationText(doc);
      setStatus(statusEl, display.short, display.ok, display.title);
    }
    return doc;
  }

  function showPrepareError(message) {
    const box = $('prepareMsg');
    if (!box) return;
    box.textContent = message;
    box.hidden = false;
    box.classList.add('error');
  }

  function installPrepareGuard() {
    document.addEventListener('click', event => {
      if (!event.target.closest?.('#prepareBtn')) return;
      const selected = $('profileSelect')?.value || '';
      if (topValidation.name !== selected || topValidation.pending || !topValidation.ok) {
        event.preventDefault();
        event.stopImmediatePropagation();
        const display = validationText(topValidation);
        showPrepareError(`Cannot prepare a new run: ${display.title || display.short}`);
      }
    }, true);
  }

  function keyControl() {
    return $('keyChip')?.closest('.top-control') || null;
  }

  function renderKeyVisibility() {
    const control = keyControl();
    if (control) control.hidden = ($('providerClass')?.value !== 'openrouter');
  }

  async function keyIsSet(env) {
    if (!env) return false;
    try {
      const doc = await api('/api/key-status');
      return !!doc.keys?.[env]?.set;
    } catch (_) {
      return false;
    }
  }

  function openKeyDialog(env) {
    const dialog = $('keyDialog');
    if (!dialog || !env) return;
    $('keyEnv').value = env;
    $('keyValue').value = '';
    const msg = $('keyMsg');
    if (msg) {
      msg.textContent = '';
      msg.hidden = true;
      msg.classList.remove('error');
    }
    if (!dialog.open) dialog.showModal();
    setTimeout(() => $('keyValue')?.focus(), 0);
  }

  async function maybePromptOpenRouterKey() {
    if ($('providerClass')?.value !== 'openrouter') return false;
    const row = profileRow($('profileSelect')?.value || '');
    const env = String(row?.api_key_env || '').trim();
    if (!env || await keyIsSet(env)) return false;
    openKeyDialog(env);
    return true;
  }

  function connectionFromRow(row) {
    return {
      baseUrl: String(row?.base_url || '').trim(),
      apiKeyEnv: String(row?.api_key_env || '').trim(),
    };
  }

  function editorConnection() {
    return {
      baseUrl: String($('baseUrl')?.value || '').trim(),
      apiKeyEnv: String($('apiKeyEnv')?.value || '').trim(),
    };
  }

  function catalogueKey(kind, connection) {
    return `${kind}\n${connection.baseUrl}\n${connection.apiKeyEnv}`;
  }

  function applyCatalogue(kind, connection, doc) {
    const key = catalogueKey(kind, connection);
    const models = [...new Set((doc.models || []).map(String).filter(Boolean))]
      .sort((a, b) => a.localeCompare(b));
    const providers = [...new Set((doc.providers || []).map(String).filter(Boolean))]
      .sort((a, b) => a.localeCompare(b));
    const value = { key, kind, models, providers };
    catalogueCache.set(key, value);
    activeCatalogue = value;
    updateDatalists(models, providers);
    syncCards();
    return value;
  }

  function useCachedCatalogue(kind, connection) {
    const key = catalogueKey(kind, connection);
    const cached = catalogueCache.get(key);
    if (!cached) {
      activeCatalogue = { key, kind, models: [], providers: [] };
      updateDatalists([], []);
      syncCards();
      return false;
    }
    activeCatalogue = cached;
    updateDatalists(cached.models, cached.providers);
    syncCards();
    return true;
  }

  async function discoverModels(kind, connection, force = false, messageEl = null) {
    if (!connection.baseUrl) {
      if (messageEl) messageEl.textContent = 'Enter a base URL first.';
      return null;
    }
    if (!force && useCachedCatalogue(kind, connection)) return activeCatalogue;
    if (messageEl) messageEl.textContent = kind === 'lmstudio' ? 'Detecting LM Studio models…' : 'Loading OpenRouter models…';
    try {
      const doc = await api('/api/provider-models', {
        method: 'POST',
        body: {
          base_url: connection.baseUrl,
          api_key_env: connection.apiKeyEnv,
          api_key: '',
        },
      });
      const value = applyCatalogue(kind, connection, doc);
      if (messageEl) {
        const notes = (doc.notes || []).join(' ');
        if (notes) messageEl.textContent = notes;
        else if (kind === 'openrouter') messageEl.textContent = `${value.models.length} live model(s) loaded; ${openRouterSuggestions.length} suggestions pinned.`;
        else messageEl.textContent = `${value.models.length} LM Studio model(s) detected.`;
      }
      return value;
    } catch (error) {
      activeCatalogue = { key: catalogueKey(kind, connection), kind, models: [], providers: [] };
      syncCards();
      if (messageEl) messageEl.textContent = error.message;
      return null;
    }
  }

  async function autoDiscoverTop(force = false) {
    const kind = $('providerClass')?.value || '';
    if (!['lmstudio', 'openrouter'].includes(kind)) return;
    const row = profileRow($('profileSelect')?.value || '');
    if (!row) return;
    if (kind === 'openrouter') {
      const prompted = await maybePromptOpenRouterKey();
      if (prompted) return;
    }
    await discoverModels(kind, connectionFromRow(row), force, null);
  }

  function watchKeySave() {
    const msg = $('keyMsg');
    const dialog = $('keyDialog');
    if (!msg || !dialog) return;
    const observer = new MutationObserver(() => {
      if (!dialog.open || msg.textContent.trim() !== 'Session key updated.') return;
      dialog.close();
      validateProfile($('profileSelect')?.value || '', 'top');
      autoDiscoverTop(true);
    });
    observer.observe(msg, { childList: true, characterData: true, subtree: true });
  }

  function addOtherOption(select) {
    const option = document.createElement('option');
    option.value = OTHER_MODEL;
    option.textContent = 'Other…';
    select.appendChild(option);
  }

  function suggestionGroups() {
    const groups = new Map();
    for (const row of openRouterSuggestions) {
      const category = String(row.category || 'Suggestions');
      if (!groups.has(category)) groups.set(category, []);
      groups.get(category).push(row);
    }
    return groups;
  }

  function populateOpenRouter(select) {
    const suggestedIds = new Set(openRouterSuggestions.map(row => String(row.id)));
    for (const [category, rows] of suggestionGroups()) {
      const group = document.createElement('optgroup');
      group.label = category;
      for (const row of rows) {
        const option = document.createElement('option');
        option.value = String(row.id || '');
        option.textContent = `${row.name || row.id} — ${row.id}`;
        group.appendChild(option);
      }
      select.appendChild(group);
    }
    const others = activeCatalogue.kind === 'openrouter'
      ? activeCatalogue.models.filter(id => !suggestedIds.has(id)).sort((a, b) => a.localeCompare(b))
      : [];
    if (others.length) {
      const group = document.createElement('optgroup');
      group.label = 'Other OpenRouter models — alphabetical';
      for (const id of others) {
        const option = document.createElement('option');
        option.value = id;
        option.textContent = id;
        group.appendChild(option);
      }
      select.appendChild(group);
    }
    addOtherOption(select);
  }

  function populateLocal(select) {
    const models = activeCatalogue.kind === 'lmstudio' ? activeCatalogue.models : [];
    if (models.length) {
      const group = document.createElement('optgroup');
      group.label = 'Available in LM Studio';
      for (const id of models) {
        const option = document.createElement('option');
        option.value = id;
        option.textContent = id;
        group.appendChild(option);
      }
      select.appendChild(group);
    }
    addOtherOption(select);
  }

  function modelInput(card) {
    return card.querySelector('[data-model]');
  }

  function providerKindForEditor() {
    return $('profileProviderClass')?.value || $('providerClass')?.value || 'other';
  }

  function modelCatalogueSignature(kind) {
    if (kind === 'openrouter') {
      return `openrouter:${openRouterSuggestions.map(row => `${row.category}:${row.id}`).join('|')}::${activeCatalogue.kind === 'openrouter' ? activeCatalogue.models.join('|') : ''}`;
    }
    if (kind === 'lmstudio') {
      return `lmstudio:${activeCatalogue.kind === 'lmstudio' ? activeCatalogue.models.join('|') : ''}`;
    }
    return kind;
  }

  function knownModelValues(select) {
    return new Set([...select.querySelectorAll('option')]
      .map(option => option.value)
      .filter(value => value && value !== OTHER_MODEL));
  }

  function dispatchInput(input) {
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function routingSelect(card) {
    return card.querySelector('select[data-nel-route-order-select]');
  }

  function routingStatus(card) {
    let status = card.querySelector('[data-nel-routing-status]');
    if (status) return status;
    const select = routingSelect(card);
    if (!select) return null;
    status = document.createElement('div');
    status.className = 'help nel-routing-status';
    status.dataset.nelRoutingStatus = '1';
    select.parentNode.appendChild(status);
    return status;
  }

  function routeCacheKey(model) {
    const connection = editorConnection();
    return `${connection.baseUrl}\n${connection.apiKeyEnv}\n${model}`;
  }

  function providerRowsFromGlobalCatalogue() {
    return (activeCatalogue.kind === 'openrouter' ? activeCatalogue.providers : [])
      .map(id => ({ id, label: id }));
  }

  function fillRoutingSelect(select, rows, current = '') {
    if (!select) return;
    const options = [{ id: '', label: 'Default / Auto' }, ...rows];
    const ids = new Set(options.map(row => row.id));
    if (current && !ids.has(current)) options.push({ id: current, label: `Existing: ${current}` });
    const signature = options.map(row => `${row.id}:${row.label}`).join('|');
    if (select.dataset.nelProviderSignature !== signature) {
      select.replaceChildren(...options.map(row => {
        const option = document.createElement('option');
        option.value = row.id;
        option.textContent = row.label;
        return option;
      }));
      select.dataset.nelProviderSignature = signature;
    }
    select.value = ids.has(current) || current ? current : '';
  }

  async function loadRoutingProviders(card, force = false) {
    if (providerKindForEditor() !== 'openrouter') return;
    const model = String(modelInput(card)?.value || '').trim();
    const select = routingSelect(card);
    const status = routingStatus(card);
    if (!select) return;
    const current = select.value || select.dataset.nelOriginalRoute || '';
    if (!model || !model.includes('/')) {
      fillRoutingSelect(select, providerRowsFromGlobalCatalogue(), current);
      if (status) status.textContent = 'Choose an OpenRouter model to list its available providers.';
      return;
    }
    const key = routeCacheKey(model);
    if (!force && providerEndpointCache.has(key)) {
      const rows = providerEndpointCache.get(key);
      fillRoutingSelect(select, rows, current);
      if (status) status.textContent = `${rows.length} provider endpoint${rows.length === 1 ? '' : 's'} available for this model.`;
      return;
    }
    if (status) status.textContent = 'Loading providers for this model…';
    const connection = editorConnection();
    try {
      const doc = await api(`/api/openrouter-providers?base_url=${encodeURIComponent(connection.baseUrl)}&api_key_env=${encodeURIComponent(connection.apiKeyEnv)}&model=${encodeURIComponent(model)}`);
      const rows = Array.isArray(doc.providers) ? doc.providers.filter(row => row?.id) : [];
      providerEndpointCache.set(key, rows);
      fillRoutingSelect(select, rows, current);
      if (status) status.textContent = rows.length
        ? `${rows.length} provider endpoint${rows.length === 1 ? '' : 's'} available for this model.`
        : 'OpenRouter reports no routable provider endpoints for this model.';
    } catch (error) {
      const fallback = providerRowsFromGlobalCatalogue();
      fillRoutingSelect(select, fallback, current);
      if (status) status.textContent = fallback.length
        ? `Model-specific providers unavailable (${error.message}); showing the general provider list.`
        : `Could not load providers: ${error.message}`;
    }
  }

  function enhanceRouting(card) {
    const details = card.querySelector('details.advanced');
    if (!details) return;
    details.hidden = providerKindForEditor() !== 'openrouter';
    if (details.dataset.nelRoutingEnhanced === '1') return;
    const orderInput = details.querySelector('input[data-route="order"]');
    if (orderInput && !details.querySelector('[data-nel-route-order-select]')) {
      const field = orderInput.closest('.field');
      const value = String(orderInput.value || '').trim();
      const select = document.createElement('select');
      select.dataset.nelRouteOrderSelect = '1';
      select.dataset.nelOriginalRoute = value;
      orderInput.hidden = true;
      orderInput.removeAttribute('list');
      orderInput.insertAdjacentElement('beforebegin', select);
      select.addEventListener('change', () => {
        orderInput.value = select.value;
        dispatchInput(orderInput);
      });
      const label = field?.querySelector('label');
      if (label) label.textContent = 'Preferred provider';
      if (field) field.classList.add('nel-routing-provider-field');
      fillRoutingSelect(select, providerRowsFromGlobalCatalogue(), value);
    }
    for (const route of ['only', 'ignore', 'require_parameters']) {
      const control = details.querySelector(`[data-route="${route}"]`);
      const field = control?.closest('.field');
      if (field) field.hidden = true;
    }
    const fallbackSelect = details.querySelector('select[data-route="allow_fallbacks"]');
    const fallbackLabel = fallbackSelect?.closest('.field')?.querySelector('label');
    if (fallbackLabel) fallbackLabel.textContent = 'Allow fallback providers';
    details.addEventListener('toggle', () => {
      if (details.open) loadRoutingProviders(card, false);
    });
    details.dataset.nelRoutingEnhanced = '1';
  }

  function syncCard(card) {
    const input = modelInput(card);
    const select = card.querySelector('[data-nel-model-select]');
    if (!input || !select) return;
    const kind = providerKindForEditor();
    const signature = modelCatalogueSignature(kind);
    enhanceRouting(card);
    const details = card.querySelector('details.advanced');
    if (details) details.hidden = kind !== 'openrouter';
    if (!['openrouter', 'lmstudio'].includes(kind)) {
      select.hidden = true;
      input.hidden = false;
      select.dataset.nelCatalogueSignature = signature;
      return;
    }
    if (select.dataset.nelCatalogueSignature !== signature) {
      select.replaceChildren();
      if (kind === 'openrouter') populateOpenRouter(select);
      else populateLocal(select);
      select.dataset.nelCatalogueSignature = signature;
    }
    select.hidden = false;
    const current = input.value.trim();
    const known = knownModelValues(select);
    if (current && known.has(current)) {
      select.value = current;
      input.hidden = true;
    } else {
      select.value = OTHER_MODEL;
      input.hidden = false;
    }
    if (kind === 'openrouter' && details?.open) loadRoutingProviders(card, false);
  }

  function enhanceCard(card) {
    if (card.dataset.nelModelEnhanced === '1') return;
    const input = modelInput(card);
    if (!input) return;
    const select = document.createElement('select');
    select.dataset.nelModelSelect = '1';
    select.setAttribute('aria-label', 'Provider model selection');
    select.style.marginBottom = '6px';
    input.parentNode.insertBefore(select, input);
    select.addEventListener('change', () => {
      if (select.value === OTHER_MODEL) {
        input.value = '';
        input.hidden = false;
        dispatchInput(input);
        input.focus();
        if (providerKindForEditor() === 'openrouter') loadRoutingProviders(card, true);
        return;
      }
      input.value = select.value;
      input.hidden = true;
      dispatchInput(input);
      if (providerKindForEditor() === 'openrouter') loadRoutingProviders(card, true);
    });
    input.addEventListener('change', () => {
      if (providerKindForEditor() === 'openrouter') loadRoutingProviders(card, true);
    });
    card.dataset.nelModelEnhanced = '1';
    syncCard(card);
  }

  function syncCards() {
    const aliases = $('aliases');
    if (!aliases) return;
    aliases.querySelectorAll('.alias-card').forEach(enhanceCard);
    aliases.querySelectorAll('.alias-card').forEach(syncCard);
  }

  function watchAliasCards() {
    const aliases = $('aliases');
    if (!aliases) return;
    const observer = new MutationObserver(mutations => {
      const changedCards = mutations.some(mutation =>
        [...mutation.addedNodes, ...mutation.removedNodes].some(node =>
          node.nodeType === 1 && node.classList?.contains('alias-card')),
      );
      if (changedCards) syncCards();
    });
    // Deliberately observe only direct card additions/removals. Watching the
    // subtree caused a self-triggering dropdown rebuild loop in the prior UI.
    observer.observe(aliases, { childList: true });
  }

  function updateDatalists(models, providers) {
    const modelList = $('modelList');
    const providerList = $('providerList');
    if (modelList) {
      modelList.replaceChildren(...models.map(id => {
        const option = document.createElement('option');
        option.value = id;
        return option;
      }));
    }
    if (providerList) {
      providerList.replaceChildren(...providers.map(id => {
        const option = document.createElement('option');
        option.value = id;
        return option;
      }));
    }
  }

  function installLoadModelsOverride() {
    const button = $('loadModels');
    if (!button) return;
    button.addEventListener('click', async event => {
      event.preventDefault();
      event.stopImmediatePropagation();
      const kind = providerKindForEditor();
      const msg = $('catalogueMsg');
      if (!['lmstudio', 'openrouter'].includes(kind)) {
        if (msg) msg.textContent = 'Live model discovery is available for LM Studio and OpenRouter.';
        return;
      }
      await discoverModels(kind, editorConnection(), true, msg);
    }, true);
  }

  async function loadSuggestions() {
    try {
      const doc = await api('/api/openrouter-models');
      openRouterSuggestions = Array.isArray(doc.models) ? doc.models.filter(row => row?.id) : [];
    } catch (_) {
      openRouterSuggestions = [];
    }
    syncCards();
  }

  function installPipelineSaveMetadata() {
    const nativeFetch = window.fetch.bind(window);
    window.fetch = (resource, options = {}) => {
      const url = typeof resource === 'string' ? resource : String(resource?.url || '');
      const method = String(options.method || 'GET').toUpperCase();
      if (method === 'POST' && /\/api\/pipeline(?:$|\?)/.test(url) && typeof options.body === 'string') {
        try {
          const body = JSON.parse(options.body);
          body.provider_class = $('profileProviderClass')?.value || $('providerClass')?.value || 'other';
          options = { ...options, body: JSON.stringify(body) };
        } catch (_) {
          // Leave malformed/unexpected requests untouched; the server will report them.
        }
      }
      return nativeFetch(resource, options);
    };
  }

  async function refreshPipelines() {
    try {
      const doc = await api('/api/pipelines');
      boot.pipelines = Array.isArray(doc.pipelines) ? doc.pipelines : boot.pipelines;
      fillClassSelect($('providerClass'), $('providerClass')?.value || '');
      fillClassSelect($('profileProviderClass'), $('profileProviderClass')?.value || '');
    } catch (_) {
      // Keep the last usable list if refresh fails.
    }
  }

  async function handleTopProfileChange() {
    await validateProfile($('profileSelect')?.value || '', 'top');
    renderKeyVisibility();
    await autoDiscoverTop(false);
  }

  async function handleTopProviderChange(preferredProfile = '') {
    const selected = filterTopProfiles(preferredProfile);
    renderKeyVisibility();
    if (selected) {
      $('profileSelect').dispatchEvent(new Event('change', { bubbles: true }));
    } else {
      await validateProfile('', 'top');
    }
  }

  function installProfileObservers() {
    const profileSelect = $('profileSelect');
    if (profileSelect) {
      profileSelect.addEventListener('change', handleTopProfileChange);
      const observer = new MutationObserver(() => {
        const kind = $('providerClass')?.value || 'lmstudio';
        const allowed = new Set(desiredProfileRows(kind, false).map(row => row.name));
        const values = [...profileSelect.options].map(option => option.value).filter(Boolean);
        if (values.some(value => !allowed.has(value))) filterTopProfiles(profileSelect.value);
      });
      observer.observe(profileSelect, { childList: true });
    }

    const profileLoad = $('profileLoad');
    if (profileLoad) {
      profileLoad.addEventListener('change', () => validateProfile(profileLoad.value, 'editor'));
      const observer = new MutationObserver(() => {
        const kind = $('profileProviderClass')?.value || 'lmstudio';
        const allowed = new Set(desiredProfileRows(kind, true).map(row => row.name));
        const values = [...profileLoad.options].map(option => option.value).filter(Boolean);
        if (values.some(value => !allowed.has(value))) filterEditorProfiles(profileLoad.value);
      });
      observer.observe(profileLoad, { childList: true });
    }

    $('providerClass')?.addEventListener('change', () => handleTopProviderChange());
    $('profileProviderClass')?.addEventListener('change', () => {
      const kind = providerKindForEditor();
      applyConnectionDefaults(kind);
      updateDescriptionSuggestion(kind);
      updateConnectionSummary();
      const selected = filterEditorProfiles('');
      validateProfile(selected, 'editor');
      useCachedCatalogue(kind, editorConnection());
      syncCards();
      if (kind === 'openrouter') {
        const env = fieldConnection().apiKeyEnv;
        keyIsSet(env).then(isSet => { if (!isSet) openKeyDialog(env); });
      }
      const advanced = $('connectionAdvanced');
      const toggle = $('changeConnection');
      if (advanced && kind === 'other') {
        advanced.hidden = false;
        if (toggle) toggle.textContent = 'Hide';
      }
    });
    $('culSelect')?.addEventListener('change', () => validateProfile($('profileSelect')?.value || '', 'top'));

    $('profileEdit')?.addEventListener('click', () => {
      const kind = $('providerClass')?.value || 'lmstudio';
      fillClassSelect($('profileProviderClass'), kind);
      updateDescriptionSuggestion(kind);
      updateConnectionSummary();
      setTimeout(() => {
        const selected = filterEditorProfiles($('profileSelect')?.value || '');
        validateProfile(selected, 'editor');
      }, 0);
    }, true);

    const msg = $('profileMsg');
    if (msg) {
      const observer = new MutationObserver(async () => {
        const text = msg.textContent.trim();
        if (!text) return;
        if (text.startsWith('Saved ')) {
          const savedName = $('profileSelect')?.value || $('profileName')?.value || '';
          const editorKind = $('profileProviderClass')?.value || 'lmstudio';
          overwriteApprovedName = '';
          if ($('overwriteProfile')) $('overwriteProfile').checked = false;
          updateDescriptionSuggestion(editorKind);
          updateConnectionSummary();
          await refreshPipelines();
          fillClassSelect($('providerClass'), editorKind);
          filterTopProfiles(savedName);
          filterEditorProfiles(savedName);
          await validateProfile(savedName, 'top');
          await validateProfile(savedName, 'editor');
          renderKeyVisibility();
          await autoDiscoverTop(false);
          return;
        }
        if (text.includes('Profile loaded.') || text.includes('Shipped profiles are read-only.')) {
          const name = $('profileLoad')?.value || '';
          const row = profileRow(name);
          const kind = classForRow(row);
          fillClassSelect($('profileProviderClass'), kind);
              updateDescriptionSuggestion(kind);
          updateConnectionSummary();
          filterEditorProfiles(name);
          await validateProfile(name, 'editor');
          const conn = editorConnection();
          if (!useCachedCatalogue(kind, conn) && kind === 'lmstudio') {
            await discoverModels(kind, conn, false, $('catalogueMsg'));
          }
          syncCards();
          const advanced = $('connectionAdvanced');
          const toggle = $('changeConnection');
          if (advanced && kind === 'other') {
            advanced.hidden = false;
            if (toggle) toggle.textContent = 'Hide';
          }
        }
      });
      observer.observe(msg, { childList: true, characterData: true, subtree: true });
    }
  }

  async function init() {
    installPipelineSaveMetadata();
    installProfileStyles();
    insertProviderControls();
    installPrepareGuard();
    installLoadModelsOverride();
    watchAliasCards();
    watchKeySave();

    try {
      boot = await api('/api/bootstrap');
    } catch (_) {
      boot = { pipelines: [], shipped: [] };
    }
    await loadSuggestions();

    const defaultRow = profileRow(boot.default_pipeline) ||
      (boot.pipelines || []).find(row => row.readable) || null;
    const initialKind = classForRow(defaultRow);
    fillClassSelect($('providerClass'), initialKind);
    fillClassSelect($('profileProviderClass'), initialKind);
    updateDescriptionSuggestion(initialKind);
    updateConnectionSummary();
    filterTopProfiles(defaultRow?.name || '');
    filterEditorProfiles(defaultRow?.name || '');
    renderKeyVisibility();
    installProfileObservers();
    syncCards();
    await handleTopProfileChange();
  }

  init();
})();
