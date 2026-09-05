"""Validation-marking extension for the workflow-aware NEL browser server.

The module layers optional validation marking on top of :mod:`ui.workflow_server`.
It keeps marking separate from clinical execution, exposes one explicit POST action,
and injects a small browser extension without duplicating the main UI page.
"""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any

from ui import workflow_server as workflow

batch = workflow.batch
base = workflow.base

MARKING_CONTROLS_ASSET = "marking-controls.js"
MARKING_CONTROLS_SCRIPT = f'<script src="/assets/{MARKING_CONTROLS_ASSET}"></script>'


def _json_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _functional_definitions() -> dict[str, str]:
    try:
        from validation.scripts.score_functional_dublin import load_spec

        return dict(load_spec().functions)
    except Exception:
        return {}


def marking(run_ref: str) -> dict[str, Any]:
    """Return marking state plus already-written renderable artifacts."""
    kind = batch._top_kind(run_ref)
    if kind in {"legacy", "invalid"}:
        return {
            "available": False,
            "applicable": False,
            "status": "unavailable",
            "kind": kind,
            "text": "",
        }

    if kind == "batch":
        doc = batch._nel_json("batch", "status", "--run-id", run_ref, "--json")
        if not isinstance(doc, dict):
            doc = {}
        state = dict(doc.get("marking") or {})
        location = batch._batch_location(run_ref).path
        markdown = batch._safe_read(location / "batch-marking.md")
        payload = _json_file(location / "batch-marking.json")
        functional = payload.get("functional") if isinstance(payload, dict) else None
        return {
            "available": bool(state.get("applicable")),
            "applicable": bool(state.get("applicable")),
            "status": state.get("status") or "not_applicable",
            "kind": "batch",
            "suite": doc.get("mode"),
            "marked": state.get("marked", 0),
            "total": state.get("total", 0),
            "text": markdown.get("text", "") if markdown.get("exists") else "",
            "payload": payload,
            "functional": functional,
            "functional_definitions": (
                (functional or {}).get("function_definitions")
                if isinstance(functional, dict)
                else None
            ) or (_functional_definitions() if doc.get("mode") == "nel-validate-dublin" else {}),
            "artifacts": state.get("artifacts") or {},
        }

    doc = batch._nel_json("status", "--run-id", run_ref, "--json")
    if not isinstance(doc, dict):
        doc = {}
    state = dict(doc.get("marking") or {})
    location = batch._run_location(run_ref).path
    markdown = batch._safe_read(location / "marking.md")
    payload = _json_file(location / "marking.json")
    functional = _json_file(location / "functional.json") if state.get("status") == "complete" else None
    return {
        "available": bool(state.get("applicable")),
        "applicable": bool(state.get("applicable")),
        "status": state.get("status") or "not_applicable",
        "kind": "batch-child" if kind == "batch-child" else "run",
        "suite": state.get("suite") or doc.get("mode"),
        "case": state.get("case"),
        "text": markdown.get("text", "") if markdown.get("exists") else "",
        "payload": payload,
        "functional": functional,
        "functional_definitions": _functional_definitions() if functional else {},
        "error": state.get("error"),
        "artifacts": state.get("artifacts") or {},
    }


def _mark_execution_target(run_ref: str) -> tuple[str, str]:
    """Return registry owner and pipeline for a single run, child, or batch."""
    kind = batch._top_kind(run_ref)
    if kind in {"legacy", "invalid"}:
        raise base.UIError("marking is unavailable for legacy or invalid run folders", 409)
    if kind == "batch":
        location = batch._batch_location(run_ref)
        return location.batch_id, str(location.manifest.get("pipeline") or "")
    location = batch._run_location(run_ref)
    owner = location.batch_id or location.run_id
    return str(owner), str(location.manifest.get("pipeline") or "")


def action_mark(payload: dict[str, Any]) -> dict[str, Any]:
    run_ref = str(payload.get("run_id") or "").strip()
    if not run_ref:
        raise base.UIError("marking requires a run identifier")
    owner, pipeline = _mark_execution_target(run_ref)
    current = marking(run_ref)
    if not current.get("applicable"):
        raise base.UIError("marking is available only for completed validation runs", 409)
    if current.get("status") == "complete":
        return {"run_id": owner, "phase": "marking", "active": False, "already_complete": True}
    argv = [sys.executable, "-u", str(base.ROOT / "nel.py"), "mark", "--run-id", run_ref]
    return base.REGISTRY.start(
        argv,
        run_id=owner,
        phase="marking",
        exclusive=base.is_local_pipeline_safe(pipeline) if pipeline else True,
    )


# workflow_server owns setup construction. Thread-local argv injection lets this top
# layer add the one frozen policy flag without copying that setup implementation.
_SETUP_CONTEXT = threading.local()
_REGISTRY_START = base.REGISTRY.start
_WORKFLOW_ACTION_SETUP = batch.action_setup


def _registry_start_with_marking(argv: list[str], *args: Any, **kwargs: Any) -> dict[str, Any]:
    values = list(argv)
    if getattr(_SETUP_CONTEXT, "mark_validation", False) and "--mark-validation" not in values:
        values.append("--mark-validation")
    return _REGISTRY_START(values, *args, **kwargs)


def _action_setup_with_marking(payload: dict[str, Any]) -> dict[str, Any]:
    enabled = bool(payload.get("mark_validation"))
    mode = str(payload.get("mode") or "").strip()
    if enabled and not (mode == "nel-validate" or mode.startswith("nel-validate-")):
        raise base.UIError("automatic marking can be enabled only for a validation suite")
    _SETUP_CONTEXT.mark_validation = enabled
    try:
        return _WORKFLOW_ACTION_SETUP(payload)
    finally:
        _SETUP_CONTEXT.mark_validation = False


base.REGISTRY.start = _registry_start_with_marking
batch.action_setup = _action_setup_with_marking

_WORKFLOW_HANDLE = batch.Handler._handle


def _handle_with_marking(self, path: str, method: str) -> Any:
    if method == "GET" and path == "/api/marking":
        return marking(self._param("run"))
    if method == "GET" and path == "/api/console":
        run_ref = str(self._param("run") or "").strip()
        # During setup the transient console exists before run.json/batch.json.
        # The batch-aware handler cannot classify that not-yet-materialised path,
        # so read the registry-owned console directly while the setup child lives.
        if run_ref and ":" not in run_ref and base.REGISTRY.is_active(run_ref):
            try:
                offset = int(self._param("offset", "0"))
            except ValueError:
                offset = 0
            return base.read_console(run_ref, offset)
    if method == "POST" and path == "/api/mark":
        return action_mark(self._body())
    return _WORKFLOW_HANDLE(self, path, method)


batch.Handler._handle = _handle_with_marking



def _replace_required(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise base.UIError(f"UI compatibility patch failed: {label}", 500)
    return text.replace(old, new, 1)


def _patch_page_text(text: str) -> str:
    """Make the base UI renderer authoritative for selection/progress state."""
    replacements = [
        (
            "modelLoading:false,deleteRun:null,polling:false};",
            "modelLoading:false,deleteRun:null,polling:false,selectionGeneration:0};",
            "selection generation state",
        ),
        (
            "function contentRunRef(){const r=currentRow();if(!r)return state.selected;if(r.kind==='batch')return state.selectedBatchChild||r.run_id;if(r.kind==='batch-child')return r.run_id;return state.selected}",
            "function contentRunRef(){const r=currentRow();if(!r)return state.selected;if(r.kind==='batch')return state.selectedBatchChild||r.run_id;if(r.kind==='batch-child')return r.run_id;return state.selected}\nfunction selectedSnapshot(){return{generation:state.selectionGeneration,ref:contentRunRef()}}\nfunction selectedSnapshotCurrent(snapshot){return snapshot.generation===state.selectionGeneration&&snapshot.ref===contentRunRef()}\nfunction markingActiveFor(ref){const owner=String(ref||'').split(':')[0];return(state.runner?.children||[]).some(c=>c.run_id===owner&&c.active&&c.phase==='marking')}",
            "selection helpers",
        ),
        (
            "function selectRun(id){if(state.selected===id)return;setConsoleTarget(id);state.selected=id;",
            "function selectRun(id){if(state.selected===id){setConsoleTarget(id);return}state.selectionGeneration+=1;setConsoleTarget(id);state.selected=id;",
            "authoritative run selection",
        ),
        (
            "async function prepareRun(){setMessage($('prepareMsg'));const payload=",
            "async function prepareRun(){setMessage($('prepareMsg'));const payload=",
            "prepare function",
        ),
        (
            "const d=await api('/api/setup',{method:'POST',body:payload});state.selected=d.run_id;state.case=",
            "const d=await api('/api/setup',{method:'POST',body:payload});state.selectionGeneration+=1;state.selected=d.run_id;setConsoleTarget(d.run_id);state.runner={...(state.runner||{}),children:[...(state.runner?.children||[]).filter(c=>c.run_id!==d.run_id),d]};state.runs=mergePendingRuns(state.runs||[]);renderRuns();renderRunButton();loadConsole();state.case=",
            "immediate preparing row and console",
        ),
        (
            "if(target.kind==='batch'){if(target.status==='complete'){btn.disabled=true;btn.textContent='Batch complete'}else if(target.status==='marking_incomplete'){btn.disabled=false;btn.textContent='Retry marking'}else{btn.disabled=false;btn.textContent=['complete_with_errors','stopped','blocked'].includes(target.status)?'Resume batch':'Start batch'}return}const marking=target.marking||{};if(target.complete||target.archived){if(!target.archived&&marking.applicable&&['pending','failed','stale'].includes(String(marking.status||'pending'))){btn.disabled=false;btn.textContent='Retry marking'}else{btn.disabled=true;btn.textContent=target.archived?'Archived':'Run complete'}}else{btn.disabled=false;btn.textContent='Start run'}",
            "if(target.kind==='batch'){if(['complete','marking_incomplete'].includes(target.status)){btn.disabled=true;btn.textContent='Batch complete'}else{btn.disabled=false;btn.textContent=['complete_with_errors','stopped','blocked'].includes(target.status)?'Resume batch':'Start batch'}return}if(target.complete||target.archived){btn.disabled=true;btn.textContent=target.archived?'Archived':'Run complete'}else{btn.disabled=false;btn.textContent='Start run'}",
            "separate clinical and marking buttons",
        ),
        (
            "function markingPhase(marking,clinicalComplete){if(!marking?.applicable)return null;const rawStatus=String(marking.status||'pending');let status='pending';if(rawStatus==='complete')status='completed';else if(rawStatus==='failed')status='failed';else if(rawStatus==='stale')status='blocked';else if(clinicalComplete)status='running';return{id:'validation.marking',label:'Marking',status,rawStatus}}",
            "function markingPhase(marking,clinicalComplete,markingActive=false){if(!marking?.applicable)return null;const rawStatus=String(marking.status||'pending');let status='pending';if(rawStatus==='complete')status='completed';else if(rawStatus==='failed')status='failed';else if(rawStatus==='stale')status='blocked';else if(markingActive)status='running';return{id:'validation.marking',label:'Marking',status,rawStatus}}",
            "stable marking phase",
        ),
        (
            "function progressSegments(current,{complete=false,failed=false,blocked=false,marking=null}={},doc=null){const clinicalComplete=doc?.complete??complete,mark=markingPhase(marking,clinicalComplete);",
            "function progressSegments(current,{complete=false,failed=false,blocked=false,marking=null,markingActive=false}={},doc=null){const clinicalComplete=doc?.complete??complete,mark=markingPhase(marking,clinicalComplete,markingActive);",
            "marking segment activity",
        ),
        (
            "function progressPhaseText(current,{complete=false,failed=false,blocked=false,marking=null}={},doc=null){const clinicalComplete=doc?.complete??complete,mark=markingPhase(marking,clinicalComplete);if(mark&&clinicalComplete){if(mark.rawStatus==='complete')return'Complete';if(mark.rawStatus==='failed')return'Marking failed';if(mark.rawStatus==='stale')return'Marking stale · retry required';return'Marking'}",
            "function progressPhaseText(current,{complete=false,failed=false,blocked=false,marking=null,markingActive=false}={},doc=null){const clinicalComplete=doc?.complete??complete,mark=markingPhase(marking,clinicalComplete,markingActive);if(mark&&clinicalComplete){if(mark.rawStatus==='complete')return'Marking complete';if(mark.rawStatus==='failed')return'Marking failed';if(mark.rawStatus==='stale')return'Marking stale · retry required';return mark.status==='running'?'Marking':'Marking pending'}",
            "marking pending label",
        ),
        (
            "shown=active.length?active:(batch.status==='marking_incomplete'?unresolved:[]);",
            "shown=active.length?active:((batch.status==='marking_incomplete'||batch.status==='complete')?unresolved:[]);",
            "completed batch marking rows",
        ),
        (
            "phase=progressPhaseText(current,{complete:clinicalComplete,failed,blocked,marking:c.marking},doc)",
            "phase=progressPhaseText(current,{complete:clinicalComplete,failed,blocked,marking:c.marking,markingActive:markingActiveFor(c.run_id)},doc)",
            "batch marking phase label",
        ),
        (
            "progressSegments(current,{complete:clinicalComplete,failed,blocked,marking:c.marking},doc)",
            "progressSegments(current,{complete:clinicalComplete,failed,blocked,marking:c.marking,markingActive:markingActiveFor(c.run_id)},doc)",
            "batch marking segment",
        ),
        (
            "phase=progressPhaseText(current,{complete:clinicalComplete,failed,blocked,marking:st?.marking},doc);",
            "phase=progressPhaseText(current,{complete:clinicalComplete,failed,blocked,marking:st?.marking,markingActive:markingActiveFor(r.run_id)},doc);",
            "single marking phase label",
        ),
        (
            "progressSegments(current,{complete:clinicalComplete,failed,blocked,marking:st?.marking},doc)",
            "progressSegments(current,{complete:clinicalComplete,failed,blocked,marking:st?.marking,markingActive:markingActiveFor(r.run_id)},doc)",
            "single marking segment",
        ),
        (
            "async function loadConsole(){if(!state.selected)return;setConsoleTarget(state.selected);try{const pre=$('consoleView'),near=pre.scrollHeight-pre.scrollTop-pre.clientHeight<45,d=await api(`/api/console?run=${encodeURIComponent(state.selected)}&offset=${state.consoleOffset}`);if(d.offset<state.consoleOffset){pre.textContent='';state.consoleOffset=0}if(d.text)pre.textContent+=d.text;state.consoleOffset=d.offset;state.consoleCache[state.selected]={text:pre.textContent||'',offset:state.consoleOffset,scrollTop:near?pre.scrollHeight:pre.scrollTop};if(near)pre.scrollTop=pre.scrollHeight}catch(_){}}",
            "async function loadConsole(){if(!state.selected)return;const selected=state.selected,generation=state.selectionGeneration;setConsoleTarget(selected);try{const pre=$('consoleView'),near=pre.scrollHeight-pre.scrollTop-pre.clientHeight<45,d=await api(`/api/console?run=${encodeURIComponent(selected)}&offset=${state.consoleOffset}`);if(generation!==state.selectionGeneration||selected!==state.selected)return;if(d.offset<state.consoleOffset){pre.textContent='';state.consoleOffset=0}if(d.text)pre.textContent+=d.text;state.consoleOffset=d.offset;state.consoleCache[selected]={text:pre.textContent||'',offset:state.consoleOffset,scrollTop:near?pre.scrollHeight:pre.scrollTop};if(near)pre.scrollTop=pre.scrollHeight}catch(_){}}",
            "console stale guard",
        ),
        (
            "async function loadStatus(){if(!state.selected)return;try{const d=await api(`/api/status?run=${encodeURIComponent(state.selected)}`);state.status=d.available?d.status:null;const workflow=state.status?.workflow_definition;if(workflow&&[...$('workflowSelect').options].some(o=>o.value===workflow))$('workflowSelect').value=workflow;renderStages()}catch(_){state.status=null;renderStages()}}",
            "async function loadStatus(){if(!state.selected)return;const selected=state.selected,generation=state.selectionGeneration;try{const d=await api(`/api/status?run=${encodeURIComponent(selected)}`);if(generation!==state.selectionGeneration||selected!==state.selected)return;state.status=d.available?d.status:null;const workflow=state.status?.workflow_definition;if(workflow&&[...$('workflowSelect').options].some(o=>o.value===workflow))$('workflowSelect').value=workflow;renderStages()}catch(_){if(generation!==state.selectionGeneration||selected!==state.selected)return;state.status=null;renderStages()}}",
            "status stale guard",
        ),
        (
            "async function loadBatchContext(){const owner=batchOwnerId();if(!owner){state.batchStatus=null;state.batchProgress={};syncBatchSelectors();renderProgress();return}try{const d=await api(`/api/status?run=${encodeURIComponent(owner)}`);state.batchStatus=d.available?d.status:null;const workflow=state.batchStatus?.workflow_definition;if(workflow&&[...$('workflowSelect').options].some(o=>o.value===workflow))$('workflowSelect').value=workflow}catch(_){state.batchStatus=null}syncBatchSelectors();await loadBatchProgress();renderProgress()}",
            "async function loadBatchContext(){const generation=state.selectionGeneration,owner=batchOwnerId();if(!owner){state.batchStatus=null;state.batchProgress={};syncBatchSelectors();renderProgress();return}try{const d=await api(`/api/status?run=${encodeURIComponent(owner)}`);if(generation!==state.selectionGeneration||owner!==batchOwnerId())return;state.batchStatus=d.available?d.status:null;const workflow=state.batchStatus?.workflow_definition;if(workflow&&[...$('workflowSelect').options].some(o=>o.value===workflow))$('workflowSelect').value=workflow}catch(_){if(generation!==state.selectionGeneration||owner!==batchOwnerId())return;state.batchStatus=null}syncBatchSelectors();await loadBatchProgress();if(generation!==state.selectionGeneration||owner!==batchOwnerId())return;renderProgress()}",
            "batch context stale guard",
        ),
        (
            "async function loadWorkflowProgress(){const ref=contentRunRef(),r=currentRow();if(!ref||r?.kind==='batch'&&!state.selectedBatchChild){state.workflowProgress=null;renderProgress();return}state.workflowProgress=await readJsonRunFile(ref,'logs/workflow-progress.json');renderProgress()}",
            "async function loadWorkflowProgress(){const snapshot=selectedSnapshot(),ref=snapshot.ref,r=currentRow();if(!ref||r?.kind==='batch'&&!state.selectedBatchChild){state.workflowProgress=null;renderProgress();return}const next=await readJsonRunFile(ref,'logs/workflow-progress.json');if(!selectedSnapshotCurrent(snapshot))return;state.workflowProgress=next;renderProgress()}",
            "workflow progress stale guard",
        ),
        (
            "async function loadUsage(){const ref=contentRunRef();if(!ref)return;try{const d=await api(`/api/usage?run=${encodeURIComponent(ref)}`);state.usage=d.available?d.summary:null;state.usageLedger=await readJsonRunFile(ref,'logs/model-usage.json');if(!state.usage){$('usageText').textContent=isLegacy(currentRow())?'Legacy layout · cleanup only':'Usage pending.';renderUsageView();return}",
            "async function loadUsage(){const snapshot=selectedSnapshot(),ref=snapshot.ref;if(!ref)return;try{const d=await api(`/api/usage?run=${encodeURIComponent(ref)}`);if(!selectedSnapshotCurrent(snapshot))return;const ledger=await readJsonRunFile(ref,'logs/model-usage.json');if(!selectedSnapshotCurrent(snapshot))return;state.usage=d.available?d.summary:null;state.usageLedger=ledger;if(!state.usage){$('usageText').textContent=isLegacy(currentRow())?'Legacy layout · cleanup only':'Usage pending.';renderUsageView();return}",
            "usage stale guard",
        ),
        (
            "}catch(_){state.usage=null;state.usageLedger=null;$('usageText').textContent='Usage pending.';renderUsageView()}}\nfunction renderStages(){renderProgress()}",
            "}catch(_){if(!selectedSnapshotCurrent(snapshot))return;state.usage=null;state.usageLedger=null;$('usageText').textContent='Usage pending.';renderUsageView()}}\nfunction renderStages(){renderProgress()}",
            "usage stale catch",
        ),
        (
            "async function loadCase(){const ref=contentRunRef();if(!ref)return;try{state.case=await api(`/api/case?run=${encodeURIComponent(ref)}`);renderCase()}catch(_){}}",
            "async function loadCase(){const snapshot=selectedSnapshot(),ref=snapshot.ref;if(!ref)return;try{const next=await api(`/api/case?run=${encodeURIComponent(ref)}`);if(!selectedSnapshotCurrent(snapshot))return;state.case=next;renderCase()}catch(_){}}",
            "case stale guard",
        ),
        (
            "async function loadReport(){const ref=contentRunRef();if(!ref)return;try{state.report=await api(`/api/report?run=${encodeURIComponent(ref)}`);renderReport()}catch(_){}}",
            "async function loadReport(){const snapshot=selectedSnapshot(),ref=snapshot.ref;if(!ref)return;try{const next=await api(`/api/report?run=${encodeURIComponent(ref)}`);if(!selectedSnapshotCurrent(snapshot))return;state.report=next;renderReport()}catch(_){}}",
            "report stale guard",
        ),
        (
            "async function loadSelectedModelTexts(){const ref=contentRunRef(),{operation,call,attempt}=selectedModel();",
            "async function loadSelectedModelTexts(){const snapshot=selectedSnapshot(),ref=snapshot.ref,{operation,call,attempt}=selectedModel();",
            "model text stale snapshot",
        ),
        (
            "const next={ref,operation,call,attempt,output:entries[0],reasoning:entries[1],prompt:entries[2],messages:entries[3],validation:entries[4],metadata,repairs},signature=JSON.stringify(next);if(signature===state.modelTextSignature)return;state.modelTexts=next;",
            "if(!selectedSnapshotCurrent(snapshot))return;const next={ref,operation,call,attempt,output:entries[0],reasoning:entries[1],prompt:entries[2],messages:entries[3],validation:entries[4],metadata,repairs},signature=JSON.stringify(next);if(signature===state.modelTextSignature)return;state.modelTexts=next;",
            "model text stale guard",
        ),
        (
            "async function loadModels(){if(state.modelLoading)return;const ref=contentRunRef();",
            "async function loadModels(){if(state.modelLoading)return;const snapshot=selectedSnapshot(),ref=snapshot.ref;",
            "model index stale snapshot",
        ),
        (
            "if(!index){const d=await api(`/api/files?run=${encodeURIComponent(ref)}`);index=legacyModelIndex(d.files||[])}const signature=JSON.stringify({ref,legacy,index}),",
            "if(!index){const d=await api(`/api/files?run=${encodeURIComponent(ref)}`);index=legacyModelIndex(d.files||[])}if(!selectedSnapshotCurrent(snapshot))return;const signature=JSON.stringify({ref,legacy,index}),",
            "model index stale guard",
        ),
        (
            "}catch(_){const signature=`error:${ref}`;state.modelIndex={operations:[]};",
            "}catch(_){if(!selectedSnapshotCurrent(snapshot))return;const signature=`error:${ref}`;state.modelIndex={operations:[]};",
            "model index stale catch",
        ),
        (
            "async function loadDissent(){const ref=contentRunRef();if(!ref)return;try{state.dissent=await api(`/api/dissent?run=${encodeURIComponent(ref)}`);renderDissent()}catch(_){} }",
            "async function loadDissent(){const snapshot=selectedSnapshot(),ref=snapshot.ref;if(!ref)return;try{const next=await api(`/api/dissent?run=${encodeURIComponent(ref)}`);if(!selectedSnapshotCurrent(snapshot))return;state.dissent=next;renderDissent()}catch(_){} }",
            "dissent stale guard",
        ),
        (
            "async function loadMarking(){if(!state.selected)return;const ref=contentRunRef();if(!ref)return;try{state.marking=await api(`/api/marking?run=${encodeURIComponent(ref)}`);renderMarking()}catch(e){state.marking={available:false,applicable:false,status:'unavailable',text:'',error:e.message};renderMarking()}}",
            "async function loadMarking(){if(!state.selected)return;const snapshot=selectedSnapshot(),ref=snapshot.ref;if(!ref)return;try{const next=await api(`/api/marking?run=${encodeURIComponent(ref)}`);if(!selectedSnapshotCurrent(snapshot))return;state.marking=next;renderMarking()}catch(e){if(!selectedSnapshotCurrent(snapshot))return;state.marking={available:false,applicable:false,status:'unavailable',text:'',error:e.message};renderMarking()}}",
            "marking stale guard",
        ),
        (
            "async function loadFiles(){const ref=contentRunRef();if(!ref)return;try{const d=await api(`/api/files?run=${encodeURIComponent(ref)}`);state.files=d.files||[];",
            "async function loadFiles(){const snapshot=selectedSnapshot(),ref=snapshot.ref;if(!ref)return;try{const d=await api(`/api/files?run=${encodeURIComponent(ref)}`);if(!selectedSnapshotCurrent(snapshot))return;state.files=d.files||[];",
            "files stale guard",
        ),
        (
            "}catch(e){$('reportPane').innerHTML=`<div class=\"pending\">${esc(e.message)}</div>`}}\nfunction buildFileTree",
            "}catch(e){if(!selectedSnapshotCurrent(snapshot))return;$('reportPane').innerHTML=`<div class=\"pending\">${esc(e.message)}</div>`}}\nfunction buildFileTree",
            "files stale catch",
        ),
        (
            "async function loadFile(path){try{const ref=contentRunRef(),d=await api(`/api/file?run=${encodeURIComponent(ref)}&path=${encodeURIComponent(path)}`);state.filePath=path;",
            "async function loadFile(path){const snapshot=selectedSnapshot();try{const ref=snapshot.ref,d=await api(`/api/file?run=${encodeURIComponent(ref)}&path=${encodeURIComponent(path)}`);if(!selectedSnapshotCurrent(snapshot))return;state.filePath=path;",
            "file stale guard",
        ),
        (
            "}catch(e){state.filePath=path;state.fileText=e.message;state.fileMeta=null;renderFiles()}}\nfunction formatBytes",
            "}catch(e){if(!selectedSnapshotCurrent(snapshot))return;state.filePath=path;state.fileText=e.message;state.fileMeta=null;renderFiles()}}\nfunction formatBytes",
            "file stale catch",
        ),
        (
            "async function pollSelected(){if(!state.selected)return;const tasks=[loadConsole(),loadStatus(),loadBatchContext(),loadWorkflowProgress(),loadUsage(),loadCase(),loadReport(),loadDissent()];if(state.midMode==='models')tasks.push(loadModels());if(state.midMode==='marking')tasks.push(loadMarking());",
            "async function pollSelected(){if(!state.selected)return;const tasks=[loadConsole(),loadStatus(),loadBatchContext(),loadWorkflowProgress(),loadUsage(),loadCase(),loadReport()];if(state.midMode==='models')tasks.push(loadModels());if(state.midMode==='dissent')tasks.push(loadDissent());if(state.midMode==='marking')tasks.push(loadMarking());",
            "dissent active-tab polling",
        ),
    ]
    for old, new, label in replacements:
        text = _replace_required(text, old, new, label)
    return text


def _patched_page() -> tuple[Path, Path]:
    source = batch.PAGE
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise base.UIError(f"could not read UI page: {exc}", 500) from exc
    text = _patch_page_text(text)
    if MARKING_CONTROLS_SCRIPT not in text:
        text = text.replace("</body>", f"{MARKING_CONTROLS_SCRIPT}\n</body>", 1)
    target = base.STATE_DIR / "marking-index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return source, target


def serve(port: int = 8765, open_browser: bool = True) -> int:
    source, patched = _patched_page()
    batch.PAGE = patched
    try:
        return int(workflow.serve(port=port, open_browser=open_browser))
    finally:
        batch.PAGE = source
        try:
            patched.unlink()
        except OSError:
            pass
