(() => {
'use strict';

const nativeFetch = window.fetch.bind(window);
const batchMeta = new Map();
let boot = null;
let decorating = false;
let selectedValidation = [];
let collapsed = new Set();

function urlPath(input) {
  try {
    const raw = typeof input === 'string' ? input : input.url;
    return new URL(raw, window.location.href).pathname;
  } catch (_) { return ''; }
}
function jsonBody(init) {
  if (!init || typeof init.body !== 'string') return null;
  try { return JSON.parse(init.body); } catch (_) { return null; }
}
function selectedCaseIds() {
  return [...document.querySelectorAll('#batchCaseChecks input[type="checkbox"]:checked')].map(x => x.value);
}
function rememberRuns(rows) {
  batchMeta.clear();
  for (const row of rows || []) {
    if (row && row.run_id) batchMeta.set(String(row.run_id), row);
  }
}

window.fetch = async (input, init = {}) => {
  const path = urlPath(input);
  let nextInit = init;
  if (path === '/api/setup' && String(init.method || 'GET').toUpperCase() === 'POST') {
    const body = jsonBody(init);
    if (body && /^nel-validate/.test(String(body.mode || ''))) {
      body.case_ids = selectedCaseIds();
      delete body.case_id;
      nextInit = {...init, body: JSON.stringify(body)};
    }
  }
  const response = await nativeFetch(input, nextInit);
  if (response.ok && path === '/api/bootstrap') {
    try { boot = await response.clone().json(); } catch (_) {}
  }
  if (response.ok && path === '/api/runs') {
    try { const doc = await response.clone().json(); rememberRuns(doc.runs || []); } catch (_) {}
  }
  return response;
};

function addStyles() {
  const style = document.createElement('style');
  style.textContent = `
    .batch-format-hint{font-size:10.5px;color:var(--muted);margin-top:5px;line-height:1.35}
    .batch-format-hint.error{color:var(--danger)}
    .batch-case-picker{border:1px solid var(--line);border-radius:8px;max-height:210px;overflow:auto;padding:6px;background:var(--panel-2)}
    .batch-case-option{display:flex;gap:8px;align-items:center;padding:5px 6px;border-radius:6px;font-family:var(--mono);font-size:11px}
    .batch-case-option:hover{background:var(--panel)}
    .batch-case-option input{width:auto;margin:0}
    .batch-picker-head{display:flex;align-items:center;justify-content:space-between;gap:6px;margin:0 0 6px}
    .batch-picker-actions{display:flex;gap:5px}.batch-picker-actions button{font-size:10px;padding:.3rem .45rem}
    .run-row.batch-child{margin-left:20px;width:calc(100% - 20px);opacity:.96}
    .run-row.batch-child .run-id{font-weight:650}
    .run-row.batch-parent .run-id{display:flex;align-items:center;gap:5px}
    .batch-toggle{border:0;background:transparent;padding:0;color:var(--muted);font-size:11px;line-height:1}
    .run-dot.failed{background:var(--danger)!important}
    .batch-parallel{font-size:10px;color:var(--muted);white-space:nowrap;margin-left:5px}
  `;
  document.head.appendChild(style);
}

function ensurePasteHint() {
  const textarea = document.getElementById('caseInput');
  if (!textarea || document.getElementById('batchFormatHint')) return;
  textarea.placeholder = '# Case 1\nClinical case text…\n\n# Case 2\nClinical case text…';
  const hint = document.createElement('div');
  hint.id = 'batchFormatHint'; hint.className = 'batch-format-hint';
  textarea.insertAdjacentElement('afterend', hint);
  const update = () => {
    const text = textarea.value || '';
    const matches = [...text.matchAll(/^# Case\s+(.+?)\s*$/gmi)];
    let message = 'Batch format: every case must begin with # Case <title>.';
    let bad = false;
    if (text.trim()) {
      if (!matches.length) { message = 'No valid cases detected — add # Case <title> before every case.'; bad = true; }
      else if (text.slice(0, matches[0].index).trim()) { message = 'Invalid batch format — content appears before the first # Case <title>.'; bad = true; }
      else message = `${matches.length} case${matches.length === 1 ? '' : 's'} detected.`;
    }
    hint.textContent = message; hint.classList.toggle('error', bad);
  };
  textarea.addEventListener('input', update); update();
}

function suiteIsValidation() {
  const suite = document.getElementById('suiteSelect');
  return !!suite && /^nel-validate/.test(suite.value || '');
}
function suiteIsDemo() {
  const suite = document.getElementById('suiteSelect');
  return !!suite && suite.value === 'nel-demo';
}
function renderCaseChecks() {
  const select = document.getElementById('caseSelect');
  if (!select) return;
  let picker = document.getElementById('batchCaseChecksWrap');
  if (!picker) {
    picker = document.createElement('div'); picker.id = 'batchCaseChecksWrap';
    select.insertAdjacentElement('afterend', picker);
  }
  if (!suiteIsValidation()) {
    select.hidden = false; picker.hidden = true; selectedValidation = []; updatePrepareLabels(); return;
  }
  select.hidden = true; picker.hidden = false; selectedValidation = [];
  const cases = [...select.options].map(o => ({value:o.value, label:o.textContent || o.value}));
  picker.innerHTML = `<div class="batch-picker-head"><span class="hint" id="batchSelectedCount">0 of ${cases.length} selected</span><span class="batch-picker-actions"><button type="button" id="batchSelectAll">Select all</button><button type="button" id="batchClearAll">Clear</button></span></div><div class="batch-case-picker" id="batchCaseChecks">${cases.map(c => `<label class="batch-case-option"><input type="checkbox" value="${escapeHtml(c.value)}">${escapeHtml(c.label)}</label>`).join('')}</div>`;
  const refresh = () => {
    selectedValidation = selectedCaseIds();
    const counter = document.getElementById('batchSelectedCount');
    if (counter) counter.textContent = `${selectedValidation.length} of ${cases.length} selected`;
    const preview = document.getElementById('casePreview');
    if (preview) preview.value = selectedValidation.length ? `${selectedValidation.length} validation cases selected.\n\n${selectedValidation.join(', ')}` : 'Select one or more cases from this series.';
    updatePrepareLabels();
  };
  picker.querySelectorAll('input').forEach(cb => cb.addEventListener('change', refresh));
  document.getElementById('batchSelectAll')?.addEventListener('click', () => { picker.querySelectorAll('input').forEach(x => x.checked = true); refresh(); });
  document.getElementById('batchClearAll')?.addEventListener('click', () => { picker.querySelectorAll('input').forEach(x => x.checked = false); refresh(); });
  refresh();
}

function ensureParallelHint() {
  const profile = document.getElementById('profileSelect');
  if (!profile || document.getElementById('batchParallel')) return;
  const hint = document.createElement('span'); hint.id = 'batchParallel'; hint.className = 'batch-parallel';
  profile.insertAdjacentElement('afterend', hint);
  const update = () => {
    const row = (boot?.pipelines || []).find(p => p.name === profile.value);
    hint.textContent = row?.max_parallel_cases ? `batch ×${row.max_parallel_cases}` : '';
    hint.title = row?.max_parallel_cases ? `Maximum concurrent cases for this profile: ${row.max_parallel_cases}` : '';
  };
  profile.addEventListener('change', update); update();
}

function updatePrepareLabels() {
  const prepare = document.getElementById('prepareBtn');
  if (!prepare) return;
  const bundledVisible = !document.getElementById('bundledFields')?.hidden;
  const batch = !bundledVisible || suiteIsValidation();
  prepare.textContent = batch ? 'Prepare batch' : 'Prepare run';
}

function selectedRow() { return document.querySelector('#runsList .run-row.selected'); }
function updateRunButton() {
  const btn = document.getElementById('runBtn'); const row = selectedRow();
  if (!btn || !row) return;
  const id = row.title || row.dataset.runId || '';
  const meta = batchMeta.get(id);
  if (meta?.kind === 'batch-child' || id.includes(':')) {
    btn.disabled = true; btn.textContent = 'Use batch parent'; btn.classList.remove('danger');
    return;
  }
  if (meta?.kind === 'batch') {
    const active = row.querySelector('.run-dot.active');
    if (active) { btn.textContent = 'Stop batch'; return; }
    if (meta.status === 'complete_with_errors' || meta.status === 'stopped') btn.textContent = 'Resume batch';
    else if (meta.status === 'complete') btn.textContent = 'Batch complete';
    else btn.textContent = 'Start batch';
  }
}

function decorateRuns() {
  if (decorating) return; decorating = true;
  try {
    const box = document.getElementById('runsList'); if (!box) return;
    const rows = [...box.querySelectorAll('.run-row')];
    const byId = new Map(rows.map(row => [row.title || '', row]));
    for (const row of rows) {
      const id = row.title || ''; const meta = batchMeta.get(id);
      row.dataset.runId = id;
      const isChild = meta?.kind === 'batch-child' || id.includes(':');
      const isParent = meta?.kind === 'batch';
      row.classList.toggle('batch-child', !!isChild); row.classList.toggle('batch-parent', !!isParent);
      if (isChild) {
        const name = row.querySelector('.run-id');
        if (name) { name.textContent = meta?.case_title || meta?.case_id || id.split(':').slice(1).join(':'); name.title = id; }
        const status = String(meta?.batch_status || '');
        const dot = row.querySelector('.run-dot'); if (dot) { dot.classList.toggle('active', status === 'running'); dot.classList.toggle('failed', status === 'failed'); }
        row.querySelector('[data-archive]')?.remove();
      }
      if (isParent) {
        row.querySelector('[data-archive]')?.remove();
        const name = row.querySelector('.run-id');
        if (name && !name.querySelector('.batch-toggle')) {
          const toggle = document.createElement('button'); toggle.type = 'button'; toggle.className = 'batch-toggle'; toggle.textContent = collapsed.has(id) ? '▸' : '▾'; toggle.title = 'Collapse/expand batch cases';
          toggle.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); collapsed.has(id) ? collapsed.delete(id) : collapsed.add(id); decorateRunsSoon(); });
          name.prepend(toggle);
        }
        const action = row.querySelector('[data-delete]'); if (action && meta?.status === 'prepared') action.textContent = 'Discard';
      }
    }
    // Keep each child directly below its parent, regardless of the app's sort.
    for (const [id, parent] of byId) {
      const meta = batchMeta.get(id); if (meta?.kind !== 'batch') continue;
      const children = rows.filter(r => (batchMeta.get(r.title || '')?.parent_batch) === id);
      let anchor = parent;
      for (const child of children) { anchor.insertAdjacentElement('afterend', child); anchor = child; child.hidden = collapsed.has(id); }
      const toggle = parent.querySelector('.batch-toggle'); if (toggle) toggle.textContent = collapsed.has(id) ? '▸' : '▾';
      const parentActive = !!parent.querySelector('.run-dot.active');
      if (parentActive) children.forEach(c => c.querySelectorAll('.run-buttons button').forEach(b => b.disabled = true));
    }
    updateRunButton();
  } finally { decorating = false; }
}
function decorateRunsSoon() { setTimeout(decorateRuns, 0); }

function initPatch() {
  addStyles(); ensurePasteHint(); ensureParallelHint(); renderCaseChecks(); updatePrepareLabels();
  const suite = document.getElementById('suiteSelect');
  suite?.addEventListener('change', () => setTimeout(renderCaseChecks, 0));
  document.getElementById('sourcePaste')?.addEventListener('click', () => setTimeout(updatePrepareLabels, 0));
  document.getElementById('sourceBundled')?.addEventListener('click', () => setTimeout(() => { renderCaseChecks(); updatePrepareLabels(); }, 0));
  const caseSelect = document.getElementById('caseSelect');
  if (caseSelect) new MutationObserver(() => renderCaseChecks()).observe(caseSelect, {childList:true});
  const runs = document.getElementById('runsList');
  if (runs) new MutationObserver(decorateRunsSoon).observe(runs, {childList:true, subtree:true, attributes:true, attributeFilter:['class']});
  for (const paneId of ['casePane','reportPane']) {
    document.getElementById(paneId)?.addEventListener('click', event => {
      const link = event.target.closest('a[href^=\"nel-run:\"]');
      if (!link) return;
      event.preventDefault();
      const ref = (link.getAttribute('href') || '').slice('nel-run:'.length);
      const row = [...document.querySelectorAll('#runsList .run-row')].find(item => (item.title || item.dataset.runId || '') === ref);
      row?.click();
    });
  }
  setInterval(() => { ensureParallelHint(); decorateRuns(); updateRunButton(); }, 750);
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// This patch is injected immediately before the existing application script.
// Defer DOM decoration until that script has populated its initial selectors.
setTimeout(initPatch, 0);
})();
