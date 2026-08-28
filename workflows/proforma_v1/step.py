#!/usr/bin/env python3
"""Proforma-v1 minimal prototype: owner proformas -> evidence -> deterministic blocks -> report."""
from __future__ import annotations
import argparse, contextlib, hashlib, io, json, re, shutil, sys, tempfile, time, zipfile
from datetime import datetime, timezone
from pathlib import Path
import yaml

REPO_ROOT=Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path: sys.path.insert(0,str(REPO_ROOT))
from scripts.core import citations, corpus, retrieval as core_retrieval, syntax_repair, validated_model_task
from scripts.setup_workflow import setup_workflow
from scripts.workflow_registry import read_workflow_state, write_workflow_state
from validation.package_marking import package_marking_bundle
from validation import cases as validation_cases
from workflows.proforma_v1 import card_identity, domain_contract, evidence_resolution, layout, model_client, model_context, pipeline_registry, prognosis_report, prompt_loader, rendering, runtime, schema_validation, stage_checks, stage_spec
from workflows.proforma_v1.engine.context import WorkflowContext
from workflows.proforma_v1.engine import schema_validation as generic_schema_validation
from workflows.proforma_v1.engine import bindings as workflow_bindings, prompt_renderer as workflow_prompt_renderer, artifacts as workflow_artifacts
from workflows.proforma_v1.engine.workflow_compiler import compile_workflow, describe as describe_workflow, resolve_workflow_path
from workflows.proforma_v1.engine.workflow_runner import WorkflowRunner
from workflows.proforma_v1.executors.provider import ProviderExecutor
from workflows.proforma_v1.trace import TraceRecorder

WORKFLOW_ID='proforma-v1'; RUN_STATE_SCHEMA_VERSION=3; HERE=Path(__file__).resolve().parent; PROMPTS=HERE/'prompts'; WORKFLOW_PATH=HERE/'workflow.json'
SETTINGS_PATH=HERE/'settings.json'; SETTINGS_TEMPLATE_PATH=HERE/'settings.json.template'; USAGE_FILE='model-usage.json'

def configure_runtime(*,settings_path=None,pipelines_dir=None):
    """Bind workflow-local defaults or explicit public/frozen runtime inputs."""
    global SETTINGS_PATH, SETTINGS_TEMPLATE_PATH
    SETTINGS_PATH=Path(settings_path).expanduser().resolve() if settings_path is not None else HERE/'settings.json'
    SETTINGS_TEMPLATE_PATH=SETTINGS_PATH.with_name('settings.json.template') if settings_path is not None else HERE/'settings.json.template'
    pipeline_registry.configure(pipelines_dir)
    return SETTINGS_PATH,pipeline_registry.ROOT
EXIT_OK=0; EXIT_FAILURE=1; EXIT_HANDOFF=10
def supported_modes():
    doc=json.loads(WORKFLOW_PATH.read_text(encoding='utf-8'))
    modes=doc.get('supported_modes') or []
    if not isinstance(modes,list) or not modes or any(not isinstance(x,str) or not x for x in modes):
        raise ValueError(f'invalid supported_modes in {WORKFLOW_PATH}')
    return tuple(modes)
VALIDATION_MODES={m for m in supported_modes() if m.startswith('nel-validate')}
MARKING_PREFIX={'nel-validate':'nel-validation','nel-validate-function':'nel-validation-function','nel-validate-brief':'nel-validation-brief'}
_EXECUTION_STARTED_AT=None
_ACTIVE_COMPILED_WORKFLOW=None
_ACTIVE_WORKFLOW_CONTEXT=None

class StepFailure(RuntimeError): pass
class SyntaxCycleExhausted(StepFailure):
    """One full syntax-only budget was exhausted for a model artifact."""
    def __init__(self,message,*,feedback=None):
        self.feedback=feedback or message
        super().__init__(message)
class Handoff(RuntimeError):
    def __init__(self,call_id,prompt,output): self.call_id=call_id; self.prompt=prompt; self.output=output; super().__init__(call_id)

def _read(p): return Path(p).read_text(encoding='utf-8')
def _write(p,text):
    p=Path(p); p.parent.mkdir(parents=True,exist_ok=True); q=p.with_name(p.name+'.tmp'); q.write_text(text,encoding='utf-8'); q.replace(p); return p

def load_settings():
    p=SETTINGS_PATH if SETTINGS_PATH.is_file() else SETTINGS_TEMPLATE_PATH
    d=json.loads(_read(p))
    if d.get('schema_version')!=1: raise StepFailure('unsupported proforma-v1 settings schema; expected 1')
    required={'retries','diagnosis','ptbg','reportability','prompts'}
    missing=sorted(required-set(d))
    if missing: raise StepFailure(f'proforma-v1 settings missing required sections: {missing}')
    who5=((d.get('diagnosis') or {}).get('who5') or {})
    if 'reconsider_after_cmc_expansion' not in who5 and 'max_cmc_passes' in who5:
        who5['reconsider_after_cmc_expansion']=int(who5.get('max_cmc_passes') or 1)>1
    return d

def _setting(*keys):
    value=load_settings()
    for key in keys:
        if not isinstance(value,dict) or key not in value: raise StepFailure(f'missing proforma-v1 setting: {".".join(keys)}')
        value=value[key]
    return value

def _retry(name): return int(_setting('retries',name))

def _card_render_mode():
    mode=str(((load_settings().get('rendering') or {}).get('cards') or 'compact')).strip().lower()
    if mode not in {'compact','verbose'}: raise StepFailure("rendering.cards must be 'compact' or 'verbose'")
    return mode

_REPORTABILITY_DEFAULTS={
    'diagnosis':{'who5':True,'icc':True,'second_diagnosis':True},
    'prognosis':{'framework_favorable':True,'framework_adverse':True,'framework_neutral':True,'other_evidence_favorable':True,'other_evidence_adverse':True,'other_evidence_neutral':True,'no_prognostic_evidence':False,'prognostic_frameworks':True},
    'treatment':{'drug_target':True,'drug_sensitive':True,'drug_resistant':True,'no_drug_implication':False},
    'biomarker':{'mrd_marker':True,'not_mrd_marker':False},
    'germline':{'germline_suspicious':True,'germline_against':False,'germline_uncertain':False},
}

def _reportable(domain,key):
    default=_REPORTABILITY_DEFAULTS.get(domain,{}).get(key,True)
    reportability=load_settings().get('reportability') or {}
    domains=reportability.get('domains') or {}
    domain_cfg=domains.get(domain) or {}
    if domain=='germline' and key=='germline_suspicious' and key not in domain_cfg and 'germline_support' in domain_cfg:
        value=domain_cfg['germline_support']
    else:
        value=domain_cfg.get(key,default)
    if not isinstance(value,bool):
        raise StepFailure(f'reportability.domains.{domain}.{key} must be true or false')
    return value
def configured_pipeline(): return str(load_settings().get('pipeline') or 'self')
def _prompt(name):
    rel=str(_setting('prompts',name))
    return prompt_loader.render(Path(rel),root=PROMPTS)

def _compiled_prompt(step, workflow, context=None, *, output_template=""):
    if not step.prompt:
        raise StepFailure(f'workflow step {step.id!r} has no prompt')
    if context is None:
        # Static-only compatibility path used by inspection helpers. Runtime
        # placeholders are rendered by the shared binding resolver during runs.
        return prompt_loader.render(step.prompt, root=workflow.asset_root)
    inputs=workflow_bindings.resolve_inputs(step,context)
    return workflow_prompt_renderer.render(step.prompt,root=workflow.asset_root,inputs=inputs,output_template=output_template)
def _run_state_path(work): return _artifact(work,'run_state','proforma-v1-run.json',new=True)
def _load_run_state(work):
    d=json.loads(_read(_artifact(work,'run_state','proforma-v1-run.json')))
    if d.get('schema_version')!=RUN_STATE_SCHEMA_VERSION: raise StepFailure('incompatible proforma-v1 run state; start a fresh run')
    return d
def _save_run_state(work,d): _write(_run_state_path(work),json.dumps(d,indent=2,ensure_ascii=False)+'\n')
def _pipeline_id(work,selector=None):
    if selector: return selector
    try: return str(_load_run_state(work).get('pipeline') or configured_pipeline())
    except Exception: return configured_pipeline()
def _plan(work,selector=None): return pipeline_registry.load(_pipeline_id(work,selector))
def _profile(work,selector,role): return pipeline_registry.binding(_plan(work,selector),role)

def _elapsed():
    global _EXECUTION_STARTED_AT
    now=time.time(); _EXECUTION_STARTED_AT=now if _EXECUTION_STARTED_AT is None else _EXECUTION_STARTED_AT
    return max(0,int(now-_EXECUTION_STARTED_AT))
def _status(msg): print(f'[ {_elapsed():04d} ] - {msg}',file=sys.stderr)

class _LoggedStream:
    def __init__(self,terminal,handle): self.terminal=terminal; self.handle=handle
    def write(self,s): self.handle.write(s); self.handle.flush(); self.terminal.write(s); self.terminal.flush(); return len(s)
    def flush(self): self.handle.flush(); self.terminal.flush()
    def __getattr__(self,n): return getattr(self.terminal,n)
@contextlib.contextmanager
def _cli_logging(work):
    p=layout.logs(work)/'workflow.log'
    with p.open('a',encoding='utf-8') as h, contextlib.redirect_stdout(_LoggedStream(sys.stdout,h)), contextlib.redirect_stderr(_LoggedStream(sys.stderr,h)): yield

def _artifact(work,group,name,new=False):
    d=layout.intermediate_dir(work,group,existing=not new); return d/name
def artifact_path(work,group,name,*,create=False): return _artifact(work,group,name,new=create)
def has_artifact(work,group,name): return artifact_path(work,group,name).is_file()
def _existing_or_new(work,group,name):
    p=_artifact(work,group,name)
    return p if p.exists() else _artifact(work,group,name,new=True)
def _case_json(work): return _existing_or_new(work,'structured_case','case.json')
def _variants_path(work): return _existing_or_new(work,'variant_registry','variants.yaml')
def _usage_path(work): return layout.logs(work)/USAGE_FILE
def _record_usage(work,call_id,model,attempt,usage,*,role=None,duration_ms=None,logical_operation=None,call_kind='model',error=None):
    p=_usage_path(work); doc={'schema_version':1,'calls':[]}
    if p.is_file():
        try: doc=json.loads(_read(p))
        except (OSError,json.JSONDecodeError,TypeError): doc={'schema_version':1,'calls':[]}
    calls=doc.setdefault('calls',[])
    row={
        'call_index':len(calls)+1,'operation':call_id,'logical_operation':logical_operation or call_id,
        'call_kind':call_kind,'role':role,'model':model,'attempt':attempt,'duration_ms':duration_ms,'usage':usage,
    }
    if error: row['error']=str(error)
    calls.append(row)
    _write(p,json.dumps(doc,indent=2,ensure_ascii=False)+'\n')
def _usage_summary(work):
    p=_usage_path(work)
    if not p.is_file(): return None
    try: calls=json.loads(_read(p)).get('calls',[])
    except (OSError,json.JSONDecodeError,TypeError): return None
    reported=[r.get('usage') for r in calls if isinstance(r.get('usage'),dict)]
    token_totals={k:sum((u or {}).get(k,0) for u in reported) for k in ('prompt_tokens','completion_tokens','total_tokens')}
    duration_ms=sum(int(r.get('duration_ms') or 0) for r in calls)
    logical=[]
    for row in calls:
        op=row.get('logical_operation') or row.get('operation')
        if op and op not in logical: logical.append(op)
    by_operation={}
    for op in logical:
        rows=[r for r in calls if (r.get('logical_operation') or r.get('operation'))==op]
        usages=[r.get('usage') for r in rows if isinstance(r.get('usage'),dict)]
        by_operation[op]={
            'physical_calls':len(rows),
            'retry_calls':max(0,len([r for r in rows if r.get('call_kind','model')=='model'])-1),
            'syntax_repair_calls':len([r for r in rows if r.get('call_kind')=='syntax_repair']),
            'duration_ms':sum(int(r.get('duration_ms') or 0) for r in rows),
            'tokens':{k:sum((u or {}).get(k,0) for u in usages) for k in ('prompt_tokens','completion_tokens','total_tokens')},
        }
    return {
        'logical_operations':len(logical),'physical_calls':len(calls),
        'retry_calls':sum(max(0,len([r for r in calls if (r.get('logical_operation') or r.get('operation'))==op and r.get('call_kind','model')=='model'])-1) for op in logical),
        'syntax_repair_calls':sum(1 for r in calls if r.get('call_kind')=='syntax_repair'),
        'reported_calls':len(reported),'unreported_calls':len(calls)-len(reported),
        'duration_ms':duration_ms,'totals':token_totals,'by_operation':by_operation,
    }
def _print_usage(work):
    summary=_usage_summary(work)
    if summary is None:
        _status('Token usage: unavailable (self handoff or no provider usage ledger)'); return
    _status(
        f"Model execution: {summary['logical_operations']} logical operation(s), "
        f"{summary['physical_calls']} provider call(s), {summary['retry_calls']} retry call(s), "
        f"{summary['syntax_repair_calls']} syntax-repair call(s), {summary['duration_ms']/1000:.2f}s provider runtime"
    )
    if not summary['reported_calls']:
        _status('Token usage: unavailable (provider did not report usage)'); return
    t=summary['totals']; suffix=f"; partial, {summary['unreported_calls']} attempt(s) unreported" if summary['unreported_calls'] else ''
    _status(f"Token usage: prompt {t['prompt_tokens']:,}, completion {t['completion_tokens']:,}, total {t['total_tokens']:,}{suffix}")

def _risk_path(work): return layout.logs(work)/'risk_log.yaml'
def _risk_doc(work):
    if _risk_path(work).is_file(): return yaml.safe_load(_read(_risk_path(work))) or {'run_status':'completed','risks':[]}
    return {'run_status':'completed','risks':[]}
def _risk(work,*,stage,risk_type,message,severity='warning',schema_element=None,attempts=0,action='retained',human_review='recommended'):
    d=_risk_doc(work); rows=d.setdefault('risks',[])
    payload={'stage':stage,'schema_element':schema_element,'severity':severity,'type':risk_type,'message':message,'action_taken':action,'attempts':attempts,'human_review':human_review}
    # Self handoffs replay completed Python stages. Risk logging must therefore be
    # idempotent: the same resolved event may be encountered many times while a
    # later model call is pending, but it is still one risk.
    for row in rows:
        if all(row.get(k)==v for k,v in payload.items()): return row.get('id')
    rid=f'R{len(rows)+1:03d}'
    rows.append({'id':rid,**payload})
    if severity in {'warning','error'}: d['run_status']='completed_with_risks'
    _write(_risk_path(work),yaml.safe_dump(d,sort_keys=False,allow_unicode=True,width=110))
    return rid

def _semantic_dissent_path(work): return layout.logs(work)/'semantic_dissent.yaml'

def _semantic_dissent_doc(work):
    """Load the persistent semantic-dissent issue ledger.

    Schema v2 is issue-centric.  A small migration keeps older interrupted runs
    readable: each legacy flat item becomes one open issue whose first history
    event is the original dissent.
    """
    path=_semantic_dissent_path(work)
    if path.is_file():
        try:
            doc=yaml.safe_load(_read(path)) or {}
        except (OSError,yaml.YAMLError,TypeError):
            doc={}
        if isinstance(doc,dict) and isinstance(doc.get('issues'),list):
            doc.setdefault('schema_version',2)
            return doc
        if isinstance(doc,dict) and isinstance(doc.get('items'),list):
            issues=[]
            for idx,row in enumerate(doc.get('items') or [],1):
                reviewed=str(row.get('reviewed_text') or '').strip()
                reasons=[str(x).strip() for x in row.get('dissent_reason') or [] if str(x).strip()]
                actions=[str(x).strip() for x in row.get('action_recommended') or [] if str(x).strip()]
                if not reviewed or not reasons or not actions: continue
                did=str(row.get('id') or f'D{idx:03d}')
                issues.append({
                    'id':did,
                    'issue_key':f'legacy:{did}',
                    'reviewed_text':reviewed,
                    'status':'open',
                    'history':[{
                        'stage':'legacy semantic dissent',
                        'event':'raised',
                        'reason':reasons,
                        'resolution_recommendation':actions,
                    }],
                })
            migrated={'schema_version':2,'issues':issues}
            _write(path,yaml.safe_dump(migrated,sort_keys=False,allow_unicode=True,width=110))
            return migrated
    return {'schema_version':2,'issues':[]}

def _semantic_dissent_issue(work,issue_key):
    key=str(issue_key or '').strip()
    if not key: return None
    for issue in _semantic_dissent_doc(work).get('issues') or []:
        if issue.get('issue_key')==key: return issue
    return None

def _semantic_dissent(work,*,issue_key,stage,reviewed_text,dissent_reason,action_recommended):
    """Raise or revisit one semantic dissent issue.

    `issue_key` is stable across retries/self-handoffs and is never rendered.
    Repeated raises append history only when the stage/reason/recommendation is
    materially different, so replay remains idempotent.
    """
    key=str(issue_key or '').strip(); stage=str(stage or '').strip(); reviewed=str(reviewed_text or '').strip()
    reasons=[str(x).strip() for x in (dissent_reason if isinstance(dissent_reason,list) else [dissent_reason]) if str(x or '').strip()]
    actions=[str(x).strip() for x in (action_recommended if isinstance(action_recommended,list) else [action_recommended]) if str(x or '').strip()]
    if not key or not stage or not reviewed or not reasons or not actions: return None
    doc=_semantic_dissent_doc(work); issues=doc.setdefault('issues',[])
    issue=next((row for row in issues if row.get('issue_key')==key),None)
    if issue is None:
        did=f'D{len(issues)+1:03d}'
        issue={'id':did,'issue_key':key,'reviewed_text':reviewed,'status':'open','history':[]}
        issues.append(issue)
    else:
        did=issue.get('id')
        if not issue.get('reviewed_text'): issue['reviewed_text']=reviewed
        # A recurring concern means the issue is open again unless it was
        # deliberately retained with dissent.
        if issue.get('status')=='resolved': issue['status']='open'
    event={'stage':stage,'event':'raised','reason':reasons,'resolution_recommendation':actions}
    if event not in issue.setdefault('history',[]): issue['history'].append(event)
    _write(_semantic_dissent_path(work),yaml.safe_dump(doc,sort_keys=False,allow_unicode=True,width=110))
    _write_dissent(work)
    return did

def _semantic_dissent_address(work,*,issue_key,stage,action,outcome=None,status=None):
    """Append an action/outcome to an existing semantic dissent issue."""
    key=str(issue_key or '').strip(); stage=str(stage or '').strip()
    actions=[str(x).strip() for x in (action if isinstance(action,list) else [action]) if str(x or '').strip()]
    outcomes=[str(x).strip() for x in (outcome if isinstance(outcome,list) else [outcome]) if str(x or '').strip()]
    if not key or not stage or not actions: return None
    doc=_semantic_dissent_doc(work); issues=doc.setdefault('issues',[])
    issue=next((row for row in issues if row.get('issue_key')==key),None)
    if issue is None: return None
    event={'stage':stage,'event':'addressed','action':actions}
    if outcomes: event['outcome']=outcomes
    if event not in issue.setdefault('history',[]): issue['history'].append(event)
    if status:
        if status not in {'open','resolved','retained_with_dissent'}: raise ValueError(f'unsupported dissent status: {status}')
        issue['status']=status
    _write(_semantic_dissent_path(work),yaml.safe_dump(doc,sort_keys=False,allow_unicode=True,width=110))
    _write_dissent(work)
    return issue.get('id')

def _semantic_dissent_keys(work,prefix,*,statuses=('open',)):
    wanted=set(statuses or [])
    return [
        str(issue.get('issue_key'))
        for issue in _semantic_dissent_doc(work).get('issues') or []
        if str(issue.get('issue_key') or '').startswith(prefix) and (not wanted or issue.get('status') in wanted)
    ]

def _progress_path(work): return layout.logs(work)/'progress.json'

def _model_retry_state_path(work): return layout.logs(work)/'model-retry-state.json'
def _model_retry_state(work):
    p=_model_retry_state_path(work)
    if not p.is_file(): return {}
    try:
        d=json.loads(_read(p)); return d if isinstance(d,dict) else {}
    except (OSError,json.JSONDecodeError,TypeError): return {}
def _save_model_retry_state(work,state): _write(_model_retry_state_path(work),json.dumps(state,indent=2,ensure_ascii=False)+'\n')
def _retry_entry(work,call_id): return dict(_model_retry_state(work).get(call_id) or {})
def _set_retry_entry(work,call_id,entry):
    state=_model_retry_state(work)
    if entry: state[call_id]=entry
    else: state.pop(call_id,None)
    _save_model_retry_state(work,state)

def _transform_log_path(work): return layout.logs(work)/'transforms.yaml'
def _log_transforms(work,records):
    """Record every deterministic change made to an accepted model artifact.

    Without this a developer cannot tell whether a stored artifact differs from
    the model's answer because the model said so or because Python normalised it.
    Idempotent: self handoffs replay completed deterministic stages.
    """
    records=[r for r in (records or []) if r]
    if not records: return
    path=_transform_log_path(work); doc={'schema_version':1,'transforms':[]}
    if path.is_file():
        try: doc=yaml.safe_load(_read(path)) or doc
        except (OSError,yaml.YAMLError,TypeError): pass
    rows=doc.setdefault('transforms',[])
    for record in records:
        if record not in rows: rows.append(record)
    _write(path,yaml.safe_dump(doc,sort_keys=False,allow_unicode=True,width=110))

def _log_once(work,key,msg,*,raw=False):
    """Log one diagnostic or stage message once across self-handoff resumes."""
    p=_progress_path(work); doc={'announced':[]}
    if p.is_file():
        try: doc=json.loads(_read(p))
        except (json.JSONDecodeError,TypeError): doc={'announced':[]}
    announced=doc.setdefault('announced',[])
    if key in announced: return
    if raw: print(msg,file=sys.stderr)
    else: _status(msg)
    announced.append(key); _write(p,json.dumps(doc,indent=2,ensure_ascii=False)+'\n')

def _stage_status(work,key,msg):
    """Log each coarse workflow stage once across self-handoff resumes."""
    _log_once(work,key,msg)

def _render_bundle(call_id,messages,output,error=None):
    out=[f'# Proforma-v1 model operation — {call_id}','']
    for i,m in enumerate(messages,1): out += [f'## Message {i} — {m["role"]}','',m['content'].rstrip(),'']
    if error: out += ['## Deterministic structural feedback','',error,'','Repair only the reported structural defects. Preserve clinical meaning.','']
    out += ['## Output','',f'Write only the requested artifact to: `{output}`','Do not modify any other file.','']
    return '\n'.join(out)

def _syntax_callback(work,binding,call_id,total_attempts):
    def repair(prompt,attempt):
        sid=f'{call_id}-syntax-{attempt}'; root=layout.model_step_dir(work,sid,existing=False); out=root/'output.txt'; _write(root/'prompt.md',prompt)
        _status(f'  {call_id}: syntax-only repair {attempt}/{total_attempts}')
        if binding.is_self:
            if out.is_file(): return _read(out)
            raise Handoff(sid,root/'prompt.md',out)
        logical_id=_logical_operation_id(call_id)
        started=time.perf_counter()
        try: comp=model_client.complete_messages(binding,[{'role':'system','content':syntax_repair.SYNTAX_REPAIR_SYSTEM_PROMPT},{'role':'user','content':prompt}])
        except model_client.TruncatedCompletion as exc:
            duration_ms=round((time.perf_counter()-started)*1000)
            _record_usage(work,sid,binding.model,attempt,exc.usage,role='syntax_repair',duration_ms=duration_ms,logical_operation=logical_id,call_kind='syntax_repair'); text=exc.content
        except RuntimeError as exc:
            duration_ms=round((time.perf_counter()-started)*1000)
            _record_usage(work,sid,binding.model,attempt,None,role='syntax_repair',duration_ms=duration_ms,logical_operation=logical_id,call_kind='syntax_repair',error=exc)
            raise StepFailure(str(exc)) from exc
        else:
            duration_ms=round((time.perf_counter()-started)*1000)
            if isinstance(comp,model_client.Completion): text=comp.content; usage=comp.usage
            else: text=comp; usage=None
            _record_usage(work,sid,binding.model,attempt,usage,role='syntax_repair',duration_ms=duration_ms,logical_operation=logical_id,call_kind='syntax_repair')
        _write(out,text.rstrip()+'\n'); return text
    return repair


def _archive_failed_syntax_attempts(work, call_id, attempts):
    """Copy rejected syntax/serialization repair responses into logs/errors.

    model_steps remains the chronological call trace.  This additional copy
    keeps failed repair artefacts together with the other error artefacts for
    post-mortem review.  Successful repair attempts are intentionally omitted.
    """
    for attempt in attempts or ():
        failure = attempt.parser_error or attempt.preservation_error or attempt.validation_error
        if not failure:
            continue
        out = layout.errors(work) / f'{call_id}-syntax-attempt-{attempt.index:02d}.txt'
        body = [
            attempt.response.rstrip(),
            '',
            'SYNTAX_REPAIR_FAILURE:',
            failure.strip(),
            '',
            'REPAIR_PROMPT:',
            attempt.prompt.rstrip(),
            '',
        ]
        _write(out, '\n'.join(body))


def _serialization_feedback(exc):
    """Return all representation-only validation defects, or None.

    The clinical task must never be asked to fix these.  They are sent to the
    generic syntax/serialization repair model first.  Other validation issues
    remain untouched and will be reported together after representation repair.
    """
    if not isinstance(exc,validated_model_task.ValidationFailure): return None
    serial=[issue for issue in exc.issues if issue.repair_class=='serialization']
    if not serial: return None
    return '\n'.join(issue.render(i) for i,issue in enumerate(serial,1))


def _prepare_structured(work,raw,fmt,call_id,syntax_binding,*,syntax_attempts):
    if not fmt: return model_client.strip_code_fence(raw)
    try:
        result=syntax_repair.repair_structured_output(
            raw,
            format_name=fmt,
            model_repair=_syntax_callback(work,syntax_binding,call_id,syntax_attempts),
            model_attempts=syntax_attempts,
        )
        _archive_failed_syntax_attempts(work,call_id,result.model_attempts)
    except Handoff: raise
    except syntax_repair.SyntaxRepairExhausted as exc:
        _archive_failed_syntax_attempts(work,call_id,exc.attempts)
        detail=(
            f'model operation {call_id} produced {fmt.upper()} that remained unparsable after '
            f'{syntax_attempts} syntax-only repair attempt(s): {exc.parser_error}'
        )
        raise SyntaxCycleExhausted(detail,feedback=exc.parser_error) from exc
    return result.text


_RUNTIME_CARD_TAG_RE=re.compile(r"\[card:[0-9a-f]{12}\]")


def _sanitize_proforma_text(work,call_id,text,*,preserve_card_assignments=False):
    """Normalize model-authored card tags according to the selected owner policy.

    Owner steps without ``evidence.owner_assignment`` still have leaked runtime
    card tags stripped before validation.  Phase 3 PTBG owner steps preserve their
    explicit evidence assignments so deterministic envelope validation can accept
    or feed them back to the same owner step for repair.
    """
    if not preserve_card_assignments:
        declared=_workflow_step_for_call(call_id)
        preserve_card_assignments=bool(declared and (declared.evidence or {}).get("owner_assignment"))
    try:
        doc=yaml.safe_load(text)
    except yaml.YAMLError:
        return text
    records=[]

    def walk(value,path=''):
        if isinstance(value,dict):
            out={}
            for key,item in value.items():
                child=f'{path}.{key}' if path else str(key)
                if key in {'card_tag','card_tags','evidence_card_tags','other_evidence_card_tags'} and not preserve_card_assignments:
                    records.append({'stage':call_id,'transform':'strip_proforma_card_assignment','path':child})
                    continue
                if key=='reason' and isinstance(item,str):
                    cleaned=' '.join(_RUNTIME_CARD_TAG_RE.sub(' ',item).split()).strip()
                    if cleaned!=item:
                        records.append({'stage':call_id,'transform':'strip_runtime_card_tag_from_reason','path':child})
                    out[key]=cleaned
                else:
                    out[key]=walk(item,child)
            return out
        if isinstance(value,list):
            return [walk(item,f'{path}[{i}]') for i,item in enumerate(value)]
        return value

    cleaned=walk(doc)
    if not records:
        return text
    _log_transforms(work,records)
    return yaml.safe_dump(cleaned,sort_keys=False,allow_unicode=True,width=110)


def _logical_operation_id(call_id):
    step=_workflow_step_for_call(call_id)
    return step.id if step is not None else call_id


def _task_io(work,*,call_id,role,binding,syntax_binding,output,root):
    """Bind the shared runner to this workflow's filesystem, logging and provider.

    The runner performs no I/O of its own; everything environment-specific is
    supplied here.  That is what lets the same runner drive the interactive
    `self` pipeline and a direct provider pipeline without knowing about either.
    """
    logical_id=_logical_operation_id(call_id)
    model_attempt=0
    def call_model(messages):
        nonlocal model_attempt
        model_attempt+=1
        _write(root/'messages.json',json.dumps(messages,indent=2,ensure_ascii=False)+'\n')
        _write(root/'prompt.md',_render_bundle(call_id,messages,output))
        started=time.perf_counter()
        try: comp=model_client.complete_messages(binding,messages)
        except model_client.TruncatedCompletion as exc:
            duration_ms=round((time.perf_counter()-started)*1000)
            _record_usage(work,call_id,binding.model,model_attempt,exc.usage,role=role,duration_ms=duration_ms,logical_operation=logical_id)
            return validated_model_task.Truncated(exc.content,max_tokens=exc.max_tokens)
        except RuntimeError as exc:
            duration_ms=round((time.perf_counter()-started)*1000)
            _record_usage(work,call_id,binding.model,model_attempt,None,role=role,duration_ms=duration_ms,logical_operation=logical_id,error=exc)
            raise StepFailure(str(exc)) from exc
        duration_ms=round((time.perf_counter()-started)*1000)
        if isinstance(comp,model_client.Completion):
            _record_usage(work,call_id,binding.model,model_attempt,comp.usage,role=role,duration_ms=duration_ms,logical_operation=logical_id)
            return comp.content
        _record_usage(work,call_id,binding.model,model_attempt,None,role=role,duration_ms=duration_ms,logical_operation=logical_id)
        return comp

    def call_syntax(prompt,attempt):
        sid=f'{call_id}-syntax-{attempt}'; sroot=layout.model_step_dir(work,sid,existing=False)
        _write(sroot/'prompt.md',prompt)
        if syntax_binding.is_self:
            existing=sroot/'output.txt'
            if existing.is_file(): return _read(existing)
            raise Handoff(sid,sroot/'prompt.md',existing)
        started=time.perf_counter()
        try: comp=model_client.complete_messages(syntax_binding,[{'role':'system','content':syntax_repair.SYNTAX_REPAIR_SYSTEM_PROMPT},{'role':'user','content':prompt}])
        except model_client.TruncatedCompletion as exc:
            duration_ms=round((time.perf_counter()-started)*1000)
            _record_usage(work,sid,syntax_binding.model,attempt,exc.usage,role='syntax_repair',duration_ms=duration_ms,logical_operation=logical_id,call_kind='syntax_repair')
            return exc.content
        except RuntimeError as exc:
            duration_ms=round((time.perf_counter()-started)*1000)
            _record_usage(work,sid,syntax_binding.model,attempt,None,role='syntax_repair',duration_ms=duration_ms,logical_operation=logical_id,call_kind='syntax_repair',error=exc)
            raise StepFailure(str(exc)) from exc
        duration_ms=round((time.perf_counter()-started)*1000)
        usage=comp.usage if isinstance(comp,model_client.Completion) else None
        _record_usage(work,sid,syntax_binding.model,attempt,usage,role='syntax_repair',duration_ms=duration_ms,logical_operation=logical_id,call_kind='syntax_repair')
        return comp.content if isinstance(comp,model_client.Completion) else comp

    def record(attempt):
        if attempt.error: _write(layout.errors(work)/f'{call_id}-attempt-{attempt.index:02d}.txt',attempt.response.rstrip()+'\n\nVALIDATION:\n'+attempt.error+'\n')

    return validated_model_task.TaskIO(
        call_model=call_model,
        call_syntax_model=call_syntax,
        load_state=lambda key:_retry_entry(work,key),
        save_state=lambda key,value:_set_retry_entry(work,key,value),
        read_output=lambda:_read(output) if output.is_file() else None,
        write_output=lambda text:(_write(output,text),_write(root/'accepted-output.txt',text)) and None,
        record_attempt=record,
        status=_status,
        is_self=binding.is_self,
    )


def _run_model_task(work,*,call_id,role,prompt,output,validator,profile=None,fmt='yaml',mode='standard',max_attempts=None,max_rewrites=None,feedback=None,system_prompt=None):
    """Run one validated model task through the shared runner."""
    binding=_profile(work,profile,role); syntax_binding=_profile(work,profile,'syntax_repair')
    root=layout.model_step_dir(work,call_id,existing=False)
    messages=[{'role':'system','content':system_prompt or model_client.SYSTEM_PROMPT},{'role':'user','content':prompt}]
    if feedback: messages.append({'role':'user','content':feedback})
    def prepare(raw):
        text=_prepare_structured(work,raw,fmt,call_id,syntax_binding,syntax_attempts=_retry('syntax_repair_attempts')) if fmt else model_client.strip_code_fence(raw)
        return _sanitize_proforma_text(work,call_id,text) if mode=='proforma' and fmt=='yaml' else text
    request=validated_model_task.TaskRequest(
        task_id=call_id,
        messages=messages,
        validate=validator,
        fmt=fmt,
        mode=mode,
        prepare=prepare,
        budgets=validated_model_task.Budgets(
            content=int(max_attempts if max_attempts is not None else _retry('fatal_model_attempts')),
            serialization=_retry('syntax_repair_attempts'),
            rewrite=int(max_rewrites if max_rewrites is not None else _retry('proforma_rewrite_attempts')),
        ),
    )
    io=_task_io(work,call_id=call_id,role=role,binding=binding,syntax_binding=syntax_binding,output=output,root=root)
    try:
        candidate=validated_model_task.run(request,io)
    except validated_model_task.Suspend as suspend:
        _write(root/'messages.json',json.dumps(suspend.messages,indent=2,ensure_ascii=False)+'\n')
        _write(root/'prompt.md',_render_bundle(call_id,suspend.messages,output,suspend.feedback or None))
        raise Handoff(call_id,root/'prompt.md',output) from suspend
    except validated_model_task.TaskFailed as exc:
        raise StepFailure(str(exc)) from exc
    _write(root/'validated.txt','accepted\n')
    return candidate


def _workflow_step_for_call(call_id):
    workflow=_ACTIVE_COMPILED_WORKFLOW
    if workflow is None: return None
    mapping={
        'structure-case':'structure','diagnosis-who5-pass-01':'diagnosis.who1','diagnosis-who5-pass-02':'diagnosis.who2',
        'diagnosis-icc':'diagnosis.icc','diagnosis-other':'diagnosis.other',
        'prognosis':'prognosis','treatment':'treatment','biomarker':'biomarker','germline':'germline',
        'report-write':'report.write','report-preservation':'report.preservation',
    }
    if call_id.startswith('who1-evidence-match-'): sid='diagnosis.who1.evidence.assignment'
    elif call_id=='who1-evidence-audit': sid='diagnosis.who1.evidence.audit'
    elif call_id=='who1-evidence-adjudication': sid='diagnosis.who1.evidence.adjudication'
    elif call_id.startswith('evidence-match-batch-') or call_id.startswith('evidence-assignment-rescue-') or call_id=='evidence-assignment': sid='evidence.assignment'
    elif call_id.startswith('evidence-audit-batch-') or call_id=='evidence-audit': sid='evidence.audit'
    elif call_id=='evidence-adjudication': sid='evidence.adjudication'
    else: sid=mapping.get(call_id)
    if not sid: return None
    try: return workflow.step(sid)
    except KeyError: return None


def _with_declared_validation(call_id, validator):
    step=_workflow_step_for_call(call_id); workflow=_ACTIVE_COMPILED_WORKFLOW
    if step is None or workflow is None: return validator
    schema_rel=(step.output or {}).get('schema')
    if not schema_rel and not step.checks: return validator
    schema_path=(workflow.asset_root/schema_rel).resolve() if schema_rel else None
    schema=generic_schema_validation.load_schema(schema_path) if schema_path else None
    def combined(text):
        message=validator(text)
        runtime_context=_ACTIVE_WORKFLOW_CONTEXT.data if _ACTIVE_WORKFLOW_CONTEXT is not None else {}
        generic_schema_validation.validate(text,fmt=(step.output or {}).get('format','yaml'),schema=schema,check_specs=step.checks,context=runtime_context)
        return message
    return combined

def _model_call(work,*,call_id,role,prompt,output,validator,profile=None,fmt='yaml',max_attempts=None,feedback=None,system_prompt=None,proforma=False,max_rewrites=None):
    """Run one validated model task.

    Retry, repair, budget and suspension behaviour now live in the shared runner
    (`scripts.core.validated_model_task`).  This function only binds this
    workflow's prompts, paths and provider bindings to it.
    """
    return _run_model_task(
        work,call_id=call_id,role=role,prompt=prompt,output=output,validator=_with_declared_validation(call_id,validator),
        profile=profile,fmt=fmt,mode='proforma' if proforma else 'standard',
        max_attempts=max_attempts,max_rewrites=max_rewrites,feedback=feedback,system_prompt=system_prompt,
    )


def run_check_stage(args):
    """Validate one artifact against one stage, with no model and no run directory."""
    context=stage_checks.fixture_context(args.stage)
    if args.context: context=yaml.safe_load(_read(args.context)) or {}
    try:
        message=stage_checks.check(args.stage,_read(args.file),context)
    except (validated_model_task.ValidationFailure,ValueError) as exc:
        print(f'STAGE={args.stage}'); print('RESULT=invalid'); print(); print(str(exc)); return EXIT_FAILURE
    print(f'STAGE={args.stage}'); print(f'RESULT=valid ({message})'); return EXIT_OK


def run_show_prompt(args):
    """Print a stage's prompt asset and its model-facing output contract."""
    context=stage_checks.fixture_context(args.stage)
    if args.context: context=yaml.safe_load(_read(args.context)) or {}
    name=args.stage if args.stage in (load_settings().get('prompts') or {}) else None
    if name: print(_prompt(name))
    else: print(f'(no prompt asset registered for stage {args.stage!r})')
    skeleton=stage_checks.skeleton(args.stage,context)
    if skeleton: print(); print(skeleton)
    return EXIT_OK


def run_stage_check_assets(args):
    """Load and describe every declarative stage asset."""
    lines=stage_spec.check_all()
    print(f'STAGES={len(lines)}')
    for line in lines: print(line)
    return EXIT_OK


def _safe_slug(text):
    s=''.join(c.lower() if c.isalnum() else '-' for c in text).strip('-')
    while '--' in s:s=s.replace('--','-')
    return s or 'case'
def _timestamped_work_dir(root,label):
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'); base=root/f'{_safe_slug(label)}-{stamp}'; p=base; n=2
    while p.exists(): p=Path(f'{base}-{n}'); n+=1
    return p

def _workflow_state(compiled):
    return {
        'id': compiled.workflow_id,
        'path': str(compiled.source),
        'sha256': compiled.source_sha256,
        'asset_root': str(compiled.asset_root),
        'assets': dict(compiled.asset_sha256),
    }

def _compile_selected_workflow(selection=None):
    return compile_workflow(resolve_workflow_path(selection))

def _workflow_for_run(work, selection=None):
    state=_load_run_state(Path(work))
    saved=state.get('workflow_definition') or {}
    if selection is not None:
        compiled=_compile_selected_workflow(selection)
        if saved and (compiled.source_sha256!=saved.get('sha256') or compiled.workflow_id!=saved.get('id') or compiled.asset_sha256!=(saved.get('assets') or {})):
            raise StepFailure('selected --workflow does not match the workflow definition bound to this run')
        return compiled
    if saved:
        path=Path(saved.get('path') or '')
        if not path.is_file():
            raise StepFailure(f'workflow definition bound to this run is missing: {path}')
        compiled=compile_workflow(path)
        if compiled.source_sha256!=saved.get('sha256'):
            raise StepFailure('workflow definition changed since run setup; resume refused for reproducibility')
        if compiled.asset_sha256!=(saved.get('assets') or {}):
            raise StepFailure('workflow prompt/schema/proforma assets changed since run setup; resume refused for reproducibility')
        return compiled
    return compile_workflow()

def run_setup(args):
    compiled=_compile_selected_workflow(args.workflow)
    plan=pipeline_registry.load(args.pipeline or configured_pipeline()); label=args.mode
    if args.mode=='ngs-report' and args.case_file: label+='-'+args.case_file.stem
    elif args.mode=='nel-demo': label+=f'-{args.example}'
    elif args.case_id: label+='-'+args.case_id
    work_arg=args.work_dir or _timestamped_work_dir(HERE/'runs',label); work_arg.parent.mkdir(parents=True,exist_ok=True)
    work,demo_case,demo_expected=setup_workflow(workflow=WORKFLOW_ID,mode=args.mode,work_dir=work_arg,project=False,example=args.example,case_id=args.case_id)
    write_workflow_state(work,WORKFLOW_ID,args.mode,model_profile=plan.pipeline_id)
    case_path=layout.input(work,'case.md',existing=False)
    if args.case_file: shutil.copyfile(args.case_file.expanduser().resolve(),case_path)
    elif args.mode=='nel-demo' and demo_case: shutil.copyfile(demo_case,case_path)
    if not case_path.is_file() or not _read(case_path).strip(): raise StepFailure(f'case.md missing or empty: {case_path}')
    if demo_expected: shutil.copyfile(demo_expected,_artifact(work,'setup','demo-expected.md',new=True))
    _save_run_state(work,{'schema_version':RUN_STATE_SCHEMA_VERSION,'workflow_id':WORKFLOW_ID,'mode':args.mode,'validation_case':args.case_id,'pipeline':plan.pipeline_id,'workflow_definition':_workflow_state(compiled),'created_at':datetime.now(timezone.utc).isoformat()})
    with _cli_logging(work): print(work); print(f'PIPELINE={plan.pipeline_id}')
    return EXIT_OK

def _require_work(work):
    state=read_workflow_state(work)
    if state.get('workflow_id')!=WORKFLOW_ID: raise StepFailure(f'work directory is bound to {state.get("workflow_id")!r}, not {WORKFLOW_ID!r}')
    _load_run_state(work)

def run_metadata(work):
    state=_load_run_state(Path(work))
    return {'pipeline':state.get('pipeline'),'mode':state.get('mode')}

def inspect_run(work):
    """Return canonical staged-provider progress without exposing artifact names to callers."""
    work=Path(work)
    try: meta=run_metadata(work)
    except Exception: meta={'pipeline':None,'mode':None}
    if (work/'report-final.md').is_file():
        label,stage,nxt,complete='Complete','complete',None,True
    elif has_artifact(work,'report_write','report-write.yaml') or has_artifact(work,'report_blocks','report-blocks.yaml') or has_artifact(work,'evidence_enriched','reportable-elements.yaml'):
        label,stage,nxt,complete='At report synthesis','report_synthesis','complete report',False
    elif has_artifact(work,'germline_state','proforma.yaml'):
        label,stage,nxt,complete='At evidence review','evidence_review','resolve evidence',False
    elif has_artifact(work,'biomarker_state','proforma.yaml'):
        label,stage,nxt,complete='At germline','germline','complete germline',False
    elif has_artifact(work,'treatment_state','proforma.yaml'):
        label,stage,nxt,complete='At biomarker','biomarker','complete biomarker',False
    elif has_artifact(work,'prognosis_state','proforma.yaml'):
        label,stage,nxt,complete='At treatment','treatment','complete treatment',False
    elif has_artifact(work,'diagnosis','diagnosis-final.yaml'):
        label,stage,nxt,complete='At prognosis','prognosis','complete prognosis',False
    elif has_artifact(work,'structured_case','case.json'):
        label,stage,nxt,complete='At diagnosis','diagnosis','complete diagnosis',False
    elif (work/'workflow.json').is_file() and (work/'case.md').is_file():
        label,stage,nxt,complete='Setup only','setup','structure case',False
    else:
        label,stage,nxt,complete='Unrecognized','unknown','inspect run',False
    return {'label':label,'stage':stage,'next':nxt,'complete':complete,**meta}

def _load_corpus():
    corpus_doc,_index,digest=corpus.load_corpus(corpus.DEFAULT_CORPUS,corpus.DEFAULT_INDEX); all_cards=corpus.flatten(corpus_doc)
    try: eligible=corpus.blacklist_cards(all_cards,corpus.DEFAULT_BLACKLIST)
    except ValueError as exc:
        if 'blacklist names unknown publication_key' not in str(exc): raise
        raw=json.loads(Path(corpus.DEFAULT_BLACKLIST).read_text(encoding='utf-8')); present={c.get('publication_key') for c in all_cards}; filtered=dict(raw); filtered['papers']={k:v for k,v in (raw.get('papers') or {}).items() if k in present}
        with tempfile.NamedTemporaryFile('w',suffix='.json',encoding='utf-8',delete=False) as h: json.dump(filtered,h); tmp=Path(h.name)
        try: eligible=corpus.blacklist_cards(all_cards,tmp)
        finally: tmp.unlink(missing_ok=True)
    manifest=card_identity.build_manifest(all_cards,corpus_sha256=digest); return all_cards,eligible,digest,manifest

def _manifest_path(work): return _existing_or_new(work,'card_identity','card-identity-manifest.json')
def stage_structure(work,profile,*,prompt_text=None):
    out=_case_json(work)
    prompt=(prompt_text if prompt_text is not None else _prompt('structure_case'))+'\n\n# Authoritative case\n'+_read(layout.input(work,'case.md'))+'\n\n# Allowed bootstrap CMCs\n'+_read(layout.setup(work,'case-major-categories.json'))
    _model_call(work,call_id='structure-case',role='structure',prompt=prompt,output=out,validator=runtime.validate_case_text,profile=profile,fmt='json')
    case=runtime.normalize_case_variant_descriptions(runtime.read_json(out))
    case=runtime.materialize_ngs_no_variants_detected(case,_read(layout.setup(work,'ngs-panel-scope.md')))
    _write(out,json.dumps(case,indent=2,ensure_ascii=False)+'\n')
    runtime.validate_case_text(_read(out),require_gene_prefixed_description=True)
    reg={f'v{i:02d}':{'variant_id':row['variant_id'],'gene':row['gene'],'description':row['description']} for i,row in enumerate(case.get('variants') or [],1)}
    _write(_variants_path(work),yaml.safe_dump({'variants':reg},sort_keys=False,allow_unicode=True,width=110)); return case,reg

def stage_corpus(work):
    p=_manifest_path(work)
    # Core corpus loading emits useful retrieval diagnostics to stderr.  A self
    # handoff re-enters this deterministic stage many times, so capture those
    # diagnostics and publish each distinct line only once per run.
    captured=io.StringIO()
    with contextlib.redirect_stderr(captured):
        all_cards,eligible,digest,manifest=_load_corpus()
    for line in captured.getvalue().splitlines():
        line=line.strip()
        if line:
            key='corpus-diagnostic-'+hashlib.sha256(line.encode('utf-8')).hexdigest()[:16]
            _log_once(work,key,line,raw=True)
    if not p.is_file(): _write(p,json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    return all_cards,eligible,digest,manifest


def _closed_gene_set(card):
    if card.get('category')!='diagnosis' or not card.get('genes'): return None
    text=str(card.get('interpretation') or '').lower()
    markers=('defined by mutation in ','defining somatic mutation in ','defining mutation in ','qualifying mutation in ')
    if any(m in text for m in markers) or ('mutations in ' in text and ' define ' in text): return set(card.get('genes') or [])
    return None

def _render_cards(cards,tag_by_id):
    return rendering.render_prompt_cards(cards,tag_by_id,mode=_card_render_mode())

def _render_diagnostic_cards(cards,tag_by_id,authority):
    return rendering.render_diagnostic_prompt_cards(cards,tag_by_id,authority=authority,mode=_card_render_mode())

def _finite_membership_context(reg,cards,tag_by_id):
    out={}
    for card in cards:
        closed=_closed_gene_set(card); cid=card.get('card_id')
        if closed and cid:
            tag=tag_by_id.get(cid)
            if not tag: raise StepFailure(f'card {cid!r} has no runtime tag')
            out[f'[card:{tag}]']={'qualifying':[vid for vid,row in reg.items() if row.get('gene') in closed],'not_qualifying':[vid for vid,row in reg.items() if row.get('gene') not in closed]}
    return {'finite_gene_set_membership':out} if out else {}

def _draw_diagnosis_cards(eligible,genes,cmcs):
    hits=[]; wanted=set(genes)
    for c in eligible:
        if c.get('category')!='diagnosis': continue
        if core_retrieval.match_genes(c,wanted) or core_retrieval._matches_case_major_category(c,cmcs): hits.append(c)
    return sorted(hits,key=lambda x:x.get('card_id') or '')

def _diagnosis_publication_keys(authority,setting,*,required):
    cfg=_setting('diagnosis',authority); values=cfg.get(setting)
    if not isinstance(values,list) or any(not isinstance(value,str) or not value.strip() for value in values):
        raise StepFailure(f'diagnosis.{authority}.{setting} must be a string list')
    keys={value.strip() for value in values}
    if required and not keys:
        raise StepFailure(f'diagnosis.{authority}.{setting} must not be empty')
    return keys

def _diagnosis_authority_publications(authority):
    return _diagnosis_publication_keys(authority,'included_publication_keys',required=False)

def _diagnosis_authority_excluded_publications(authority):
    return _diagnosis_publication_keys(authority,'excluded_publication_keys',required=False)

def _filter_diagnosis_authority(cards,authority):
    included=_diagnosis_authority_publications(authority)
    excluded=_diagnosis_authority_excluded_publications(authority)
    return [c for c in cards if (not included or c.get('publication_key') in included) and c.get('publication_key') not in excluded]

def _diagnostic_cards(eligible,genes,cmcs,authority):
    """Build one authority pool; exclusions take precedence over inclusions."""
    return _filter_diagnosis_authority(_draw_diagnosis_cards(eligible,genes,cmcs),authority)

def _ptbg_card_applicable(card,domain,genes,disease):
    """Return whether one PTBG card is in scope for the authoritative WHO5 disease.

    Downstream PTBG must not inherit evidence from ``retrieval_related`` diseases.
    Multi-disease applicability is expressed explicitly by the card's own ``diseases``
    list. Germline is the exception: disease-neutral cards are allowed because the
    constitutional proposition can legitimately be independent of the current neoplasm.
    """
    category=str(_setting('ptbg','domains',domain,'card_category'))
    if card.get('category')!=category: return False
    card_diseases=set(card.get('diseases') or [])
    exact_disease=disease in card_diseases
    gene_match=bool(core_retrieval.match_genes(card,set(genes)))
    if domain=='prognosis':
        # The owner must see the disease's prognostic framework even when none of
        # the framework genes are mutated. Variant-specific candidate cropping
        # happens later at evidence resolution.
        return exact_disease
    if domain in {'treatment','biomarker'}:
        return exact_disease and gene_match
    if domain=='germline':
        return gene_match and (not card_diseases or exact_disease)
    raise StepFailure(f'unsupported PTBG domain {domain!r}')

def _draw_domain_cards(eligible,domain,genes,diseases):
    """Draw PTBG cards using exact authoritative-disease scope, never related-disease expansion."""
    hits=[]
    for c in eligible:
        if any(_ptbg_card_applicable(c,domain,genes,disease) for disease in diseases): hits.append(c)
    return sorted(hits,key=lambda x:x.get('card_id') or '')

def _log_ptbg_retrieval(work,eligible,domain,genes,disease,cards):
    """Emit one concise, deterministic PTBG retrieval summary per run/domain."""
    category=str(_setting('ptbg','domains',domain,'card_category'))
    category_cards=[c for c in eligible if c.get('category')==category]
    wanted=set(genes)
    selected_ids={c.get('card_id') for c in cards}
    disease_mismatched=0; gene_mismatched=0
    for card in category_cards:
        if card.get('card_id') in selected_ids: continue
        card_diseases=set(card.get('diseases') or [])
        exact=disease in card_diseases
        gene_match=bool(core_retrieval.match_genes(card,wanted))
        disease_ok=(not card_diseases or exact) if domain=='germline' else exact
        if gene_match and not disease_ok: disease_mismatched+=1
        elif disease_ok and not gene_match and not (domain=='prognosis' and not card.get('genes')): gene_mismatched+=1
    variant_cards=sum(1 for c in cards if c.get('genes'))
    disease_level=sum(1 for c in cards if not c.get('genes'))
    neutral_germline=sum(1 for c in cards if domain=='germline' and not c.get('diseases'))
    detail=f'selected: {variant_cards} variant card(s)'
    if domain=='prognosis': detail+=f', {disease_level} disease-level card(s)'
    if domain=='germline': detail+=f', {neutral_germline} disease-neutral card(s)'
    _log_once(
        work,f'ptbg-retrieval-{domain}',
        f'{domain} retrieval: exact disease={disease}; genes={",".join(genes) if genes else "none"}; '
        f'{detail}; suppressed: {disease_mismatched} disease-mismatched, {gene_mismatched} gene-mismatched card(s)',
    )

def _assert_ptbg_audit_card_applicable(card,el,reg,authoritative_disease):
    """Fail closed before semantic audit if a selected PTBG card is out of deterministic scope."""
    if el.get('domain')=='diagnosis': return
    domain=el.get('domain')
    genes={reg[v]['gene'] for v in el.get('variants') or [] if v in reg}
    if domain=='prognosis':
        card_diseases=set(card.get('diseases') or [])
        disease_ok=authoritative_disease in card_diseases
        if el.get('bucket')=='prognostic_framework':
            applicable=disease_ok
        else:
            applicable=disease_ok and bool(core_retrieval.match_genes(card,genes))
    else:
        applicable=_ptbg_card_applicable(card,domain,genes,authoritative_disease)
    if not applicable:
        raise StepFailure(
            f'evidence audit refused out-of-scope card {card.get("card_id")!r} for {el.get("schema_id")}: '
            f'domain={domain}, authoritative disease={authoritative_disease!r}, element genes={sorted(genes)}'
        )

def _allowed_diseases(work):
    return set(runtime.read_json(layout.setup(work,'allowed-schema-diseases.json'))['allowed_schema_diseases'])

def _variant_identity_terms(reg,variants):
    terms=[]
    for vid in variants or []:
        row=reg.get(vid) or {}
        for value in (vid,row.get('gene'),row.get('description')):
            if isinstance(value,str) and value.strip() and value.strip() not in terms: terms.append(value.strip())
    return sorted(terms,key=len,reverse=True)

def _reason_template(reason,variants,reg):
    text=' '.join(str(reason or '').split()).strip()
    for term in _variant_identity_terms(reg,variants): text=re.sub(re.escape(term),'<VARIANT>',text,flags=re.I)
    text=re.sub(r'(?:<VARIANT>\s*)+(?:mutation|mutations|variant|variants)\b','<SUBJECT>',text,flags=re.I)
    text=re.sub(r'(?:<VARIANT>\s*)+','<SUBJECT> ',text,flags=re.I)
    text=re.sub(r'(?:<SUBJECT>\s*(?:and|,)?\s*){2,}','<SUBJECT> ',text,flags=re.I)
    template=' '.join(text.split()).strip()
    return template.casefold(),template

def _render_shared_reason(template,variants,reg):
    genes=[]
    for vid in variants:
        gene=(reg.get(vid) or {}).get('gene')
        if gene and gene not in genes: genes.append(gene)
    if not genes: subject='The variants'
    elif len(genes)==1: subject=f'{genes[0]} mutations' if len(variants)>1 else f'{genes[0]} mutation'
    else: subject=', '.join(genes[:-1])+(' and ' if len(genes)==2 else ', and ')+genes[-1]+' mutations'
    text=template.replace('<SUBJECT>',subject)
    if len(variants)>1:
        for singular,plural in (('is','are'),('has','have'),('confers','confer'),('contributes','contribute'),('predicts','predict'),('indicates','indicate'),('supports','support'),('defines','define')):
            text=re.sub(rf'\b{re.escape(subject)}\s+{singular}\b',f'{subject} {plural}',text,flags=re.I)
    return text

def _consolidate_rows(domain,doc,reg,contract_override=None):
    """Merge rows sharing one normalised proposition. Returns (doc, merge records).

    The model now emits one row per variant (see domain_contract), so this is the
    only place grouping happens.  Every merge is reported so a developer can tell
    model output from deterministic normalisation.
    """
    buckets=(contract_override or domain_contract.contract(domain)).buckets; merges=[]
    for bucket in buckets:
        rows=doc.get(bucket) or []; groups=[]; index={}; templates={}
        for row in rows:
            canonical,template=_reason_template(row.get('reason'),row.get('variants') or [],reg)
            extras=tuple(sorted((k,json.dumps(v,sort_keys=True,ensure_ascii=False)) for k,v in row.items() if k not in {'variants','reason','evidence_card_tags'}))
            key=(canonical,extras)
            if canonical and key in index:
                target=groups[index[key]]
                merged=[]
                for vid in row['variants']:
                    if vid not in target['variants']: target['variants'].append(vid); merged.append(vid)
                target['reason']=_render_shared_reason(templates[key],target['variants'],reg)
                for tag in row.get('evidence_card_tags') or []:
                    target.setdefault('evidence_card_tags',[])
                    if tag not in target['evidence_card_tags']: target['evidence_card_tags'].append(tag)
                if merged: merges.append({'domain':domain,'bucket':bucket,'transform':'consolidate_parallel_variant_rows','merged_variants':merged,'into_variants':list(target['variants']),'resulting_reason':target['reason']})
            else:
                clone=dict(row); clone['variants']=list(row.get('variants') or [])
                if canonical: index[key]=len(groups); templates[key]=template
                groups.append(clone)
        doc[bucket]=groups
    return doc,merges

def stage_diagnosis(work,case,reg,eligible,manifest,profile):
    allowed=_allowed_diseases(work); genes=runtime.case_genes(case); bootstrap=list(case.get('bootstrap_cmcs') or []); tag_by_id=card_identity.tag_by_id(manifest)
    max_passes=2 if bool(_setting('diagnosis','who5','reconsider_after_cmc_expansion')) else 1; prior=list(bootstrap); history=list(bootstrap); who=None; who_cards=[]; authoritative=1
    for idx in range(1,max_passes+1):
        who_cards=_diagnostic_cards(eligible,genes,history,'who5')
        out=_artifact(work,f'diagnosis_who5_pass_{idx}','who5.yaml',new=True)
        prompt=_prompt('diagnosis_who5')+f'\n\n# Starting morphologic diagnosis\n{case.get("provisional_disease")}\n\n# Variant registry\n```yaml\n'+model_context.registry_context(reg)+'```\n\n# Structured case\n```json\n'+model_context.case_context(case,fields=model_context.DIAGNOSIS_CASE_FIELDS)+'\n```\n\n# Deterministic finite-set context\n```yaml\n'+yaml.safe_dump(_finite_membership_context(reg,who_cards,tag_by_id),sort_keys=False,allow_unicode=True,width=110)+'```\n\n# Allowed schema diseases\n'+yaml.safe_dump(sorted(allowed))+'\n# WHO5 authority cards\n'+_render_diagnostic_cards(who_cards,tag_by_id,'who5')
        model_context.assert_canonical(prompt,source_ids=model_context.source_ids(reg))
        _model_call(work,call_id=f'diagnosis-who5-pass-{idx:02d}',role='diagnosis',prompt=prompt,output=out,validator=lambda t:schema_validation.validate_who5_diagnosis(t,allowed_diseases=allowed,valid_variants=set(reg)),profile=profile,proforma=True)
        who=yaml.safe_load(_read(out)); cmcs=runtime.derive_cmcs(who); authoritative=idx
        if cmcs==prior: break
        for cmc in cmcs:
            if cmc not in history: history.append(cmc)
        prior=cmcs
    final_cmcs=runtime.derive_cmcs(who)
    for cmc in final_cmcs:
        if cmc not in history: history.append(cmc)

    icc_cards=_diagnostic_cards(eligible,genes,history,'icc'); icc_out=_existing_or_new(work,'diagnosis_icc','icc.yaml')
    iprompt=_prompt('diagnosis_icc')+'\n\n# Starting morphologic diagnosis\n'+str(case.get('provisional_disease'))+'\n\n# Variant registry\n```yaml\n'+model_context.registry_context(reg)+'```\n\n# Structured case\n```json\n'+model_context.case_context(case,fields=model_context.DIAGNOSIS_CASE_FIELDS)+'\n```\n\n# WHO5 result — context only\n```yaml\n'+yaml.safe_dump(who,sort_keys=False,allow_unicode=True,width=110)+'```\n\n# Deterministic finite-set context\n```yaml\n'+yaml.safe_dump(_finite_membership_context(reg,icc_cards,tag_by_id),sort_keys=False,allow_unicode=True,width=110)+'```\n\n# ICC authority cards\n'+_render_diagnostic_cards(icc_cards,tag_by_id,'icc')
    model_context.assert_canonical(iprompt,source_ids=model_context.source_ids(reg))
    _model_call(work,call_id='diagnosis-icc',role='diagnosis',prompt=iprompt,output=icc_out,validator=lambda t:schema_validation.validate_icc_diagnosis(t,valid_variants=set(reg)),profile=profile,proforma=True)
    icc=yaml.safe_load(_read(icc_out))

    other_cards=_draw_diagnosis_cards(eligible,genes,history); other_out=_existing_or_new(work,'diagnosis_other','other.yaml')
    oprompt=_prompt('diagnosis_other')+'\n\n# Variant registry\n```yaml\n'+model_context.registry_context(reg)+'```\n\n# Structured case\n```json\n'+model_context.case_context(case,fields=model_context.DIAGNOSIS_CASE_FIELDS)+'\n```\n\n# Primary framework diagnoses\n```yaml\n'+yaml.safe_dump({'who5':who,'icc':icc},sort_keys=False,allow_unicode=True,width=110)+'```\n\n# Candidate diagnosis cards\n'+_render_cards(other_cards,tag_by_id)
    model_context.assert_canonical(oprompt,source_ids=model_context.source_ids(reg))
    _model_call(work,call_id='diagnosis-other',role='diagnosis',prompt=oprompt,output=other_out,validator=lambda t:schema_validation.validate_second_diagnosis(t,valid_variants=set(reg)),profile=profile,proforma=True)
    other=yaml.safe_load(_read(other_out))
    relationship='same' if runtime.normalize_dx(who['diagnosis'])==runtime.normalize_dx(icc['diagnosis']) else 'different'
    diagnosis={'who5':who,'icc':icc,'second_diagnosis':other,'relationship':relationship}
    _write(_existing_or_new(work,'diagnosis','diagnosis-final.yaml'),yaml.safe_dump(diagnosis,sort_keys=False,allow_unicode=True,width=110))
    _write(_existing_or_new(work,'diagnosis','routing.json'),json.dumps({'bootstrap_cmcs':bootstrap,'who5_authoritative_pass':authoritative,'final_cmcs':final_cmcs,'diagnostic_cmc_history':history},indent=2)+'\n')
    return diagnosis,final_cmcs,{'diagnosis_who5':who_cards,'diagnosis_icc':icc_cards,'diagnosis_other':other_cards}


def stage_diagnosis_who_pass(work,case,reg,eligible,manifest,profile,*,pass_number,history,prompt_text):
    allowed=_allowed_diseases(work); genes=runtime.case_genes(case); tag_by_id=card_identity.tag_by_id(manifest)
    who_cards=_diagnostic_cards(eligible,genes,history,'who5')
    out=_artifact(work,f'diagnosis_who5_pass_{pass_number}','who5.yaml',new=True)
    prompt=prompt_text+f'\n\n# Starting morphologic diagnosis\n{case.get("provisional_disease")}\n\n# Variant registry\n```yaml\n'+model_context.registry_context(reg)+'```\n\n# Structured case\n```json\n'+model_context.case_context(case,fields=model_context.DIAGNOSIS_CASE_FIELDS)+'\n```\n\n# Deterministic finite-set context\n```yaml\n'+yaml.safe_dump(_finite_membership_context(reg,who_cards,tag_by_id),sort_keys=False,allow_unicode=True,width=110)+'```\n\n# Allowed schema diseases\n'+yaml.safe_dump(sorted(allowed))+'\n# WHO5 authority cards\n'+_render_diagnostic_cards(who_cards,tag_by_id,'who5')
    model_context.assert_canonical(prompt,source_ids=model_context.source_ids(reg))
    _model_call(work,call_id=f'diagnosis-who5-pass-{pass_number:02d}',role='diagnosis',prompt=prompt,output=out,validator=lambda t:schema_validation.validate_who5_diagnosis(t,allowed_diseases=allowed,valid_variants=set(reg)),profile=profile,proforma=True)
    who=yaml.safe_load(_read(out)); return who,who_cards


def stage_diagnosis_icc_pass(work,case,reg,eligible,manifest,profile,*,history,who,prompt_text):
    genes=runtime.case_genes(case); tag_by_id=card_identity.tag_by_id(manifest)
    cards=_diagnostic_cards(eligible,genes,history,'icc'); out=_existing_or_new(work,'diagnosis_icc','icc.yaml')
    prompt=prompt_text+'\n\n# Starting morphologic diagnosis\n'+str(case.get('provisional_disease'))+'\n\n# Variant registry\n```yaml\n'+model_context.registry_context(reg)+'```\n\n# Structured case\n```json\n'+model_context.case_context(case,fields=model_context.DIAGNOSIS_CASE_FIELDS)+'\n```\n\n# WHO5 result — context only\n```yaml\n'+yaml.safe_dump(who,sort_keys=False,allow_unicode=True,width=110)+'```\n\n# Deterministic finite-set context\n```yaml\n'+yaml.safe_dump(_finite_membership_context(reg,cards,tag_by_id),sort_keys=False,allow_unicode=True,width=110)+'```\n\n# ICC authority cards\n'+_render_diagnostic_cards(cards,tag_by_id,'icc')
    model_context.assert_canonical(prompt,source_ids=model_context.source_ids(reg))
    _model_call(work,call_id='diagnosis-icc',role='diagnosis',prompt=prompt,output=out,validator=lambda t:schema_validation.validate_icc_diagnosis(t,valid_variants=set(reg)),profile=profile,proforma=True)
    return yaml.safe_load(_read(out)),cards


def stage_diagnosis_other_pass(work,case,reg,eligible,manifest,profile,*,history,who,icc,prompt_text):
    genes=runtime.case_genes(case); tag_by_id=card_identity.tag_by_id(manifest)
    cards=_draw_diagnosis_cards(eligible,genes,history); out=_existing_or_new(work,'diagnosis_other','other.yaml')
    prompt=prompt_text+'\n\n# Variant registry\n```yaml\n'+model_context.registry_context(reg)+'```\n\n# Structured case\n```json\n'+model_context.case_context(case,fields=model_context.DIAGNOSIS_CASE_FIELDS)+'\n```\n\n# Primary framework diagnoses\n```yaml\n'+yaml.safe_dump({'who5':who,'icc':icc},sort_keys=False,allow_unicode=True,width=110)+'```\n\n# Candidate diagnosis cards\n'+_render_cards(cards,tag_by_id)
    model_context.assert_canonical(prompt,source_ids=model_context.source_ids(reg))
    _model_call(work,call_id='diagnosis-other',role='diagnosis',prompt=prompt,output=out,validator=lambda t:schema_validation.validate_second_diagnosis(t,valid_variants=set(reg)),profile=profile,proforma=True)
    return yaml.safe_load(_read(out)),cards


def stage_diagnosis_finalize_pass(work,case,who1,who2,icc,other,history):
    who=who2 or who1; authoritative=2 if who2 is not None else 1
    final_cmcs=runtime.derive_cmcs(who)
    for cmc in final_cmcs:
        if cmc not in history: history.append(cmc)
    relationship='same' if runtime.normalize_dx(who['diagnosis'])==runtime.normalize_dx(icc['diagnosis']) else 'different'
    diagnosis={'who5':who,'icc':icc,'second_diagnosis':other,'relationship':relationship}
    _write(_existing_or_new(work,'diagnosis','diagnosis-final.yaml'),yaml.safe_dump(diagnosis,sort_keys=False,allow_unicode=True,width=110))
    _write(_existing_or_new(work,'diagnosis','routing.json'),json.dumps({'bootstrap_cmcs':list(case.get('bootstrap_cmcs') or []),'who5_authoritative_pass':authoritative,'final_cmcs':final_cmcs,'diagnostic_cmc_history':history},indent=2)+'\n')
    return diagnosis,final_cmcs


def stage_domain(work,domain,case,reg,diagnosis,eligible,manifest,profile,*,prompt_text=None,contract_override=None,stage_spec_override=None):
    valid=set(reg); disease=diagnosis['who5']['schema_disease']; genes=runtime.case_genes(case); cards=_draw_domain_cards(eligible,domain,genes,[disease]); _log_ptbg_retrieval(work,eligible,domain,genes,disease,cards); tag_by_id=card_identity.tag_by_id(manifest)
    contract=contract_override or domain_contract.contract(domain)
    owner_card_tags=[f"[card:{tag_by_id[c['card_id']]}]" for c in cards]
    out=_existing_or_new(work,f'{domain}_state','proforma.yaml')
    # The output contract is the final block of the prompt: recency matters
    # disproportionately for a low-active-parameter model.
    prompt=((prompt_text if prompt_text is not None else _prompt(domain))
        +'\n\n# Variant registry\n```yaml\n'+model_context.registry_context(reg)+'```'
        +'\n\n# Structured case\n```json\n'+model_context.case_context(case,fields=model_context.DOMAIN_CASE_FIELDS)+'\n```'
        +'\n\n# Authoritative framework diagnoses\n```yaml\n'+model_context.diagnosis_context(diagnosis)+'```'
        +'\n\n# Candidate evidence cards\n'+_render_cards(cards,tag_by_id)
        +'\n\n'+domain_contract.skeleton(contract,sorted(reg),registry=reg,applicable_disease=disease))
    model_context.assert_canonical(prompt,source_ids=model_context.source_ids(reg))
    def validate_owner(text):
        normalized,_records=domain_contract.normalize_model_output(text,contract,reg,disease)
        return domain_contract.validate(
            normalized,contract,{"variants":sorted(valid),"registry":reg,"authoritative_disease":disease,"owner_card_tags":owner_card_tags},spec=stage_spec_override
        )
    _model_call(work,call_id=domain,role='ptbg',prompt=prompt,output=out,validator=validate_owner,profile=profile,proforma=True)
    normalized,identity_records=domain_contract.normalize_model_output(_read(out),contract,reg,disease)
    if identity_records:
        _log_transforms(work,[dict(record,stage=domain) for record in identity_records])
    _write(out,normalized)
    # The model returns the variant-centric owner form; Python projects it into
    # the stable bucketed internal artifact consumed downstream.
    flat=yaml.safe_load(normalized); doc=domain_contract.pivot(flat,contract)
    doc,merges=_consolidate_rows(domain,doc,reg,contract); _log_transforms(work,merges)
    _write(out,yaml.safe_dump(doc,sort_keys=False,allow_unicode=True,width=110))
    _write(_artifact(work,f'{domain}_state','model-classification.yaml',new=False),yaml.safe_dump(flat,sort_keys=False,allow_unicode=True,width=110))
    return doc,cards

def _elements(diagnosis,domains,case,contracts=None):
    contracts=contracts or {}
    els=[]
    origin=case.get('morphologic_diagnosis_origin')
    starting=case.get('provisional_disease')
    if _reportable('diagnosis','who5'):
        w=diagnosis['who5']; effect=w.get('diagnostic_effect')
        statement=(
            f'WHO5 molecular/cytogenetic update: the supplied morphologic diagnosis {starting} remains unchanged.'
            if origin=='supplied' and effect=='unchanged'
            else f'WHO5 classification: {w["diagnosis"]}.'
        )
        els.append({'schema_id':'DX-WHO5','domain':'diagnosis','bucket':'who5','framework_label':'WHO5','statement':statement,'reason':w['reason'],'variants':w['variants'],'evidence_domain':'diagnosis_who5','required':True,'source':w,'morphologic_diagnosis_origin':origin,'starting_morphologic_diagnosis':starting})
    if _reportable('diagnosis','icc'):
        r=diagnosis['icc']; effect=r.get('diagnostic_effect')
        statement=(
            f'ICC molecular/cytogenetic update: the supplied morphologic diagnosis {starting} remains unchanged.'
            if origin=='supplied' and effect=='unchanged'
            else f'ICC classification: {r["diagnosis"]}.'
        )
        els.append({'schema_id':'DX-ICC','domain':'diagnosis','bucket':'icc','framework_label':'ICC','statement':statement,'reason':r['reason'],'variants':r['variants'],'evidence_domain':'diagnosis_icc','required':True,'source':r,'morphologic_diagnosis_origin':origin,'starting_morphologic_diagnosis':starting})
    sec=diagnosis['second_diagnosis']
    if _reportable('diagnosis','second_diagnosis') and sec.get('diagnosis'):
        els.append({'schema_id':'DX-SECOND','domain':'diagnosis','bucket':'second_diagnosis','statement':sec['diagnosis'],'reason':sec['reason'],'variants':sec['variants'],'evidence_domain':'diagnosis_other','required':False,'source':sec})
    prognosis=domains['prognosis']
    if _reportable('prognosis','prognostic_frameworks'):
        for i,framework in enumerate(prognosis.get('prognostic_frameworks') or [],1):
            tier=framework.get('tier')
            statement=(
                f'{framework["name"]} prognostic framework; tier: {tier}.'
                if tier is not None else
                f'{framework["name"]} is an applicable prognostic framework for {prognosis.get("applicable_disease") or "the authoritative disease"}.'
            )
            els.append({
                'schema_id':f'PX-FRAMEWORK-{i:02d}','domain':'prognosis','bucket':'prognostic_framework',
                'statement':statement,'reason':framework['reason'],'variants':[],'evidence_domain':'prognosis',
                'required':False,'source':framework,'owner_card_tags':list(framework.get('evidence_card_tags') or []),
            })
    for bucket in contracts.get('prognosis',domain_contract.contract('prognosis')).buckets:
        if not _reportable('prognosis',bucket): continue
        for i,row in enumerate(prognosis.get(bucket) or [],1):
            els.append({'schema_id':f'PX-{bucket.upper()}-{i:02d}','domain':'prognosis','bucket':bucket,'statement':row['reason'],'reason':row['reason'],'variants':row['variants'],'evidence_domain':'prognosis','required':False,'source':row,'owner_card_tags':list(row.get('evidence_card_tags') or [])})
    for domain,prefix in (('treatment','TX'),('biomarker','MRD'),('germline','GL')):
        doc=domains[domain]
        for bucket in contracts.get(domain,domain_contract.contract(domain)).buckets:
            if not _reportable(domain,bucket): continue
            for i,row in enumerate(doc[bucket],1):
                els.append({'schema_id':f'{prefix}-{bucket.upper()}-{i:02d}','domain':domain,'bucket':bucket,'statement':row['reason'],'reason':row['reason'],'variants':row['variants'],'evidence_domain':domain,'required':False,'source':row,'owner_card_tags':list(row.get('evidence_card_tags') or [])})
    return els

def _candidate_cards(el,cards_by_domain,reg):
    cards=list(cards_by_domain.get(el['evidence_domain']) or [])
    # Diagnosis pools already implement category AND (CMC OR gene), followed by
    # the WHO5/ICC authority filter. Do not destroy that OR retrieval semantics
    # by applying a second proposition-gene filter here.
    if el.get('domain')=='diagnosis': return cards
    if el.get('domain')=='prognosis' and el.get('bucket')=='prognostic_framework':
        return cards
    genes={reg[v]['gene'] for v in el.get('variants') or [] if v in reg}
    if genes:
        subset=[c for c in cards if genes & set(c.get('genes') or [])]
        if subset: return subset
        return []
    return cards

def _render_evidence_match_candidates(public_items,candidate_items,catalog,tag_by_id):
    """Render each evidence item's deterministic candidate set beside that item.

    The batch stays one model call, but separately filtered pools are never
    collapsed into one unlabeled global catalog.
    """
    by_eid={item['evidence_id']:item for item in candidate_items}
    sections=[]
    for public in public_items:
        item=by_eid[public['evidence_id']]
        allowed=set(public.get('candidate_card_tags') or [])
        cards=[]
        for cid in evidence_resolution.remaining_candidate_ids(item):
            tag=f'[card:{tag_by_id[cid]}]'
            if tag in allowed and cid in catalog:
                cards.append(catalog[cid])
        sections += [
            f"## Evidence item {public['evidence_id']}",
            "```yaml",
            yaml.safe_dump(public,sort_keys=False,allow_unicode=True,width=110).rstrip(),
            "```",
            f"### Candidate cards for {public['evidence_id']}",
            _render_cards(cards,tag_by_id).rstrip(),
            "",
        ]
    return '\n'.join(sections).rstrip()+'\n'


def _evidence_reviewed_text(el):
    return 'Statement: '+el['statement']+'\nReason: '+el['reason']

def _resolve_no_citation_support(work,el,*,attempt,reason):
    """Apply the domain-specific policy after semantic evidence resolution stops."""
    issue=f'evidence:{el["schema_id"]}'
    if _semantic_dissent_issue(work,issue) is None:
        _semantic_dissent(
            work,issue_key=issue,stage=f'evidence matching attempt {attempt}',
            reviewed_text=_evidence_reviewed_text(el),dissent_reason=reason,
            action_recommended='Use supplied morphology for a primary diagnosis when available; otherwise omit the unsupported proposition.',
        )
    policy=evidence_resolution.exhaustion_policy(el)
    if policy=='fallback_supplied':
        fallback=evidence_resolution.retain_supplied_morphology(el)
        _semantic_dissent_address(
            work,issue_key=issue,stage='evidence resolution',
            action='Discard the unsupported molecular/cytogenetic diagnosis update and retain the supplied morphologic diagnosis without a literature citation.',
            outcome=f'Retained supplied morphology: {fallback["source"]["diagnosis"]}.',status='resolved',
        )
        return fallback
    if policy=='unresolved':
        _semantic_dissent_address(
            work,issue_key=issue,stage='evidence resolution',
            action='Do not report this inferred primary diagnosis because direct citation support was not resolved.',
            outcome='Primary framework diagnosis remains unresolved and is omitted from report construction.',
        )
        return None
    _semantic_dissent_address(
        work,issue_key=issue,stage='evidence resolution',
        action='Suppress this unsupported optional proposition from report construction.',
        outcome='The optional proposition was excluded from the report.',status='resolved',
    )
    return None

def _card_evidence_source(card):
    for key in ('source_hint','paper_nickname','citation_display','publication_key'):
        value=str(card.get(key) or '').strip()
        if value: return value
    return 'unspecified source'


def _accepted_evidence(card,card_tag,audit,semantic_attempt):
    """Deterministic evidence record for one independently audited card."""
    return {
        'status':'matched',
        'card_id':card['card_id'],
        'card_tag':card_tag,
        'source':_card_evidence_source(card),
        'quote':str(card.get('interpretation') or '').strip(),
        'audit':audit,
        'semantic_attempt':semantic_attempt,
    }


def stage_evidence(work,elements,cards_by_domain,reg,manifest,profile,*,authoritative_disease=None,match_prompt=None,audit_prompt=None):
    """Resolve each reason to zero or more independently audited evidence cards.

    The matcher only selects cards whose proposition is an element of the reason.
    The auditor independently applies that same membership test per selected card.
    A semantic retry is needed only when none of the selected cards survives audit;
    mixed batches retain passing cards and drop failed cards individually.
    """
    tag_by_id=card_identity.tag_by_id(manifest); catalog={}; pending=[]; keep=[]
    enriched=[dict(el,evidence=[]) for el in elements]
    for idx,el in enumerate(enriched,1):
        candidates=_candidate_cards(el,cards_by_domain,reg)
        if not candidates:
            issue=f'evidence:{el["schema_id"]}'
            _semantic_dissent(
                work,issue_key=issue,stage='evidence selection',reviewed_text=_evidence_reviewed_text(el),
                dissent_reason='No candidate evidence card was available for this reportable proposition.',
                action_recommended='Use supplied morphology for a primary diagnosis when available; otherwise omit the unsupported proposition.',
            )
            resolved=_resolve_no_citation_support(work,el,attempt=0,reason='No candidate evidence card was available for this reportable proposition.')
            if resolved is not None: keep.append(resolved)
            continue
        eid=f'E{len(pending)+1:04d}'
        for c in candidates: catalog[c['card_id']]=c
        pending.append({'evidence_id':eid,'element_index':idx-1,'schema_id':el['schema_id'],'statement':el['statement'],'reason':el['reason'],'candidate_card_ids':[c['card_id'] for c in candidates],'failures':[]})
    max_attempts=max(1,_retry('evidence_resolution_attempts'))
    id_by_tag={f'[card:{tag}]':cid for cid,tag in tag_by_id.items()}
    for semantic_attempt in range(1,max_attempts+1):
        if not pending: break
        active=[]; exhausted=[]
        for item in pending:
            (active if evidence_resolution.remaining_candidate_ids(item) else exhausted).append(item)
        for item in exhausted:
            el=enriched[item['element_index']]
            resolved=_resolve_no_citation_support(work,el,attempt=semantic_attempt,reason='All candidate evidence cards were rejected by prior semantic audits.')
            if resolved is not None: keep.append(resolved)
        pending=active
        if not pending: break
        _status(f'  evidence resolution semantic attempt {semantic_attempt}/{max_attempts}: {len(pending)} item(s)')
        public=[evidence_resolution.public_match_item(item,tag_by_id) for item in pending]
        mpath=_existing_or_new(work,'evidence_matches',f'attempt-{semantic_attempt:02d}.yaml')
        mprompt=(
            (match_prompt if match_prompt is not None else _prompt('evidence_match'))+'\n\n# Evidence items with their deterministic candidate cards\n'
            +_render_evidence_match_candidates(public,pending,catalog,tag_by_id)
        )
        validation_items=[{'evidence_id':x['evidence_id'],'candidate_card_tags':x['candidate_card_tags']} for x in public]
        _model_call(
            work,call_id=f'evidence-match-batch-{semantic_attempt:02d}',role='evidence_match',prompt=mprompt,output=mpath,
            validator=lambda t,vi=validation_items:schema_validation.validate_evidence_match_batch(t,vi),profile=profile,
            max_attempts=_retry('evidence_match_model_attempts'),
        )
        matches=yaml.safe_load(_read(mpath))['matches']; mmap={m['evidence_id']:m for m in matches}
        audit_items=[]
        for item in pending:
            tags=list(mmap[item['evidence_id']].get('card_tags') or [])
            if tags: audit_items.append({'evidence_id':item['evidence_id'],'selected_card_tags':tags})
        audited={}
        if audit_items:
            audit_rows=[]
            selected_ids=[]
            for item in pending:
                tags=list(mmap[item['evidence_id']].get('card_tags') or [])
                if not tags: continue
                el=enriched[item['element_index']]
                audit_rows.append({'evidence_id':item['evidence_id'],'schema_id':item['schema_id'],'reason':item['reason'],'selected_card_tags':tags})
                for tag in tags:
                    cid=id_by_tag[tag]
                    if el.get('domain')!='diagnosis':
                        if not authoritative_disease:
                            raise StepFailure('authoritative WHO5 disease is required for PTBG evidence audit')
                        _assert_ptbg_audit_card_applicable(catalog[cid],el,reg,authoritative_disease)
                    if cid not in selected_ids: selected_ids.append(cid)
            apath=_existing_or_new(work,'evidence_audits',f'attempt-{semantic_attempt:02d}.yaml')
            selected_cards=[catalog[cid] for cid in selected_ids]
            aprompt=((audit_prompt if audit_prompt is not None else _prompt('evidence_audit'))+'\n\n# Selected reason/card sets\n```yaml\n'
                +yaml.safe_dump({'items':audit_rows},sort_keys=False,allow_unicode=True,width=110)+'```\n'
                +'\n# Selected card catalog\n'+_render_cards(selected_cards,tag_by_id)+'\n')
            _model_call(
                work,call_id=f'evidence-audit-batch-{semantic_attempt:02d}',role='evidence_audit',prompt=aprompt,output=apath,
                validator=lambda t,ai=audit_items:schema_validation.validate_evidence_audit_batch(t,ai),profile=profile,
                max_attempts=_retry('evidence_audit_model_attempts'),
            )
            audits=yaml.safe_load(_read(apath))['audits']
            audited={a['evidence_id']:{x['card_tag']:x for x in a.get('card_audits') or []} for a in audits}
        next_pending=[]
        for item in pending:
            el=enriched[item['element_index']]; tags=list(mmap[item['evidence_id']].get('card_tags') or [])
            if not tags:
                issue=f'evidence:{el["schema_id"]}'
                _semantic_dissent(
                    work,issue_key=issue,stage=f'evidence matching attempt {semantic_attempt}',reviewed_text=_evidence_reviewed_text(el),
                    dissent_reason='Evidence matcher declared that no remaining candidate card is an element of the reason.',
                    action_recommended='Do not force a merely related citation; apply the proposition-specific no-support policy.',
                )
                resolved=_resolve_no_citation_support(work,el,attempt=semantic_attempt,reason='Evidence matcher declared no card to be an element of the reason.')
                if resolved is not None: keep.append(resolved)
                continue
            passed=[]
            for tag in tags:
                cid=id_by_tag[tag]; audit=audited[item['evidence_id']][tag]
                if audit['card_is_element_of_reason']:
                    passed.append(_accepted_evidence(catalog[cid],tag,audit,semantic_attempt))
                    if audit.get('risk')=='warning':
                        warning=f'evidence-warning:{el["schema_id"]}:{tag}'
                        _semantic_dissent(work,issue_key=warning,stage=f'evidence audit attempt {semantic_attempt}',reviewed_text=el['reason'],dissent_reason=audit.get('comments') or ['Evidence fidelity/context warning.'],action_recommended='Retain this card/reason match with dissent visible for review.')
                        _semantic_dissent_address(work,issue_key=warning,stage='evidence resolution',action='Retain supported card/reason match.',outcome='Membership passed; warning remains visible.',status='retained_with_dissent')
                    continue
                comments=audit.get('comments') or ['Selected card is not an element of the reason.']
                item['failures'].append({'attempt':semantic_attempt,'card_id':cid,'comments':list(comments)})
                issue=f'evidence:{el["schema_id"]}'
                _semantic_dissent(
                    work,issue_key=issue,stage=f'evidence audit attempt {semantic_attempt}',reviewed_text=_evidence_reviewed_text(el),
                    dissent_reason=[f'Card {cid} rejected: {comment}' for comment in comments],
                    action_recommended='Exclude this card from later attempts; retain any independently passing cards; retry only if no selected card passed.',
                )
            if passed:
                el['evidence']=passed
                issue=f'evidence:{el["schema_id"]}'
                if item['failures']:
                    _semantic_dissent_address(
                        work,issue_key=issue,stage='evidence resolution',
                        action=f'Retain independently audited card/reason matches from semantic attempt {semantic_attempt}.',
                        outcome=f'{len(passed)} card(s) passed; rejected card attempts remain recorded.',status='resolved',
                    )
                keep.append(el)
                continue
            if semantic_attempt<max_attempts and evidence_resolution.remaining_candidate_ids(item):
                next_pending.append(item)
            else:
                resolved=_resolve_no_citation_support(work,el,attempt=semantic_attempt,reason='Semantic evidence-resolution attempts were exhausted without a card that is an element of the reason.')
                if resolved is not None: keep.append(resolved)
        pending=next_pending
    order={el['schema_id']:i for i,el in enumerate(enriched)}
    keep.sort(key=lambda el:order.get(el['schema_id'],len(order)))
    _write(_existing_or_new(work,'evidence_enriched','reportable-elements.yaml'),yaml.safe_dump({'elements':keep},sort_keys=False,allow_unicode=True,width=110))
    return keep

def _genes(reg,variants):
    out=[]
    for vid in variants or []:
        gene=(reg.get(vid) or {}).get('gene')
        if gene and gene not in out: out.append(gene)
    return out

def _fallback_block_text(block):
    if block['domain']=='diagnosis':
        comps=block['components']; who=next((x for x in comps if x['role']=='who5'),None); icc=next((x for x in comps if x['role']=='icc'),None)
        if who and icc and block.get('relationship')=='same': text=f'The diagnosis is {who["diagnosis"]} under both WHO5 and ICC classifications.'
        elif who and icc: text=f'Under WHO5, the diagnosis is {who["diagnosis"]}. In contrast, under ICC, the diagnosis is {icc["diagnosis"]}.'
        elif who: text=f'Under WHO5, the diagnosis is {who["diagnosis"]}.'
        elif icc: text=f'Under ICC, the diagnosis is {icc["diagnosis"]}.'
        else: text=''
        second=next((x for x in comps if x['role']=='second_diagnosis'),None)
        if second: text+=((' ' if text else '')+'An independent concurrent diagnosis of '+second['diagnosis']+' is also supported.')
        return text
    return runtime.ensure_sentence(block['components'][0]['reason'])

def stage_blocks(work,diagnosis,elements,reg):
    by_id={el['schema_id']:el for el in elements}; blocks=[]
    dx=[]
    for sid,role in (('DX-WHO5','who5'),('DX-ICC','icc'),('DX-SECOND','second_diagnosis')):
        el=by_id.get(sid)
        if not el: continue
        src=el['source']; dx.append({'role':role,'diagnosis':src.get('diagnosis'),'reason':src.get('reason'),'variants':src.get('variants') or [],'genes':_genes(reg,src.get('variants') or []),'card_tags':[ev['card_tag'] for ev in (el.get('evidence') or [])]})
    if dx:
        who=next((x for x in dx if x['role']=='who5'),None); icc=next((x for x in dx if x['role']=='icc'),None)
        relationship=('same' if who and icc and runtime.normalize_dx(who['diagnosis'])==runtime.normalize_dx(icc['diagnosis']) else 'different' if who and icc else 'partial')
        blocks.append({'block_id':'DX','domain':'diagnosis','relationship':relationship,'components':dx})

    # Prognosis remains variant-centric through semantic evidence resolution.
    # Only now, after card matching/audit, collapse supported findings into
    # report-sized clinical propositions. The declared report.blocks workflow
    # operation uses this same deterministic function for provider and self.
    prognosis_blocks,prognosis_trace=prognosis_report.aggregate(elements,diagnosis,reg)
    _write(
        _existing_or_new(work,'prognosis_report_aggregation','aggregation.yaml'),
        yaml.safe_dump(prognosis_trace,sort_keys=False,allow_unicode=True,width=110),
    )
    _status(
        '  prognosis report aggregation: '
        f"{len(prognosis_trace.get('framework_groups') or [])} framework block(s), "
        f"{len(prognosis_trace.get('retained_other') or [])} independent block(s), "
        f"{len(prognosis_trace.get('suppressed') or [])} redundant proposition(s) suppressed"
    )
    blocks.extend(prognosis_blocks)

    order={'treatment':2,'biomarker':3,'germline':4}
    for el in sorted((e for e in elements if e['domain'] in order),key=lambda e:(order[e['domain']],e['schema_id'])):
        src=dict(el['source']); blocks.append({'block_id':el['schema_id'],'domain':el['domain'],'components':[{'role':el['bucket'],'reason':el['reason'],'variants':el.get('variants') or [],'genes':_genes(reg,el.get('variants') or []),'source':src,'card_tags':[ev['card_tag'] for ev in (el.get('evidence') or [])]}]})
    _write(_existing_or_new(work,'report_blocks','report-blocks.yaml'),yaml.safe_dump({'blocks':blocks},sort_keys=False,allow_unicode=True,width=110))
    return blocks

def stage_report_write(work,blocks,case,reg,profile,*,prompt_text=None):
    schema_validation.validate_report_source_blocks(blocks)
    path=_existing_or_new(work,'report_write','report-write.yaml')
    prompt=(prompt_text if prompt_text is not None else _prompt('report_write'))+'\n\n# Deterministic report blocks\n```yaml\n'+yaml.safe_dump({'blocks':blocks},sort_keys=False,allow_unicode=True,width=110)+'```\n\n# Variant registry — naming context only\n```yaml\n'+model_context.registry_context(reg)+'```\n'
    model_context.assert_canonical(prompt,source_ids=model_context.source_ids(reg))
    _model_call(work,call_id='report-write',role='report_write',prompt=prompt,output=path,validator=lambda t:schema_validation.validate_report_write(t,blocks),profile=profile,max_attempts=_retry('report_write_attempts'))
    return yaml.safe_load(_read(path))['blocks']


def stage_report_preservation(work,blocks,rendered,profile,*,prompt_text=None):
    apath=_existing_or_new(work,'report_write','report-preservation.yaml')
    aprompt=(prompt_text if prompt_text is not None else _prompt('report_preservation'))+'\n\n# Deterministic source blocks\n```yaml\n'+yaml.safe_dump({'blocks':blocks},sort_keys=False,allow_unicode=True,width=110)+'```\n\n# Rendered blocks\n```yaml\n'+yaml.safe_dump({'blocks':rendered},sort_keys=False,allow_unicode=True,width=110)+'```\n'
    try:
        _model_call(work,call_id='report-preservation',role='preservation_check',prompt=aprompt,output=apath,validator=lambda t:schema_validation.validate_preservation(t,blocks),profile=profile,max_attempts=_retry('preservation_attempts'))
        audits=yaml.safe_load(_read(apath))['audits']; return {a['block_id']:a for a in audits}
    except StepFailure as exc:
        return {b['block_id']:{'preserved':False,'issue':'Preservation audit unavailable: '+str(exc)} for b in blocks}


def stage_report_finalize_blocks(work,blocks,rendered,*,audit_map=None):
    amap={r['block_id']:r['text'] for r in rendered}; final=[]
    for block in blocks:
        text=amap.get(block['block_id']) or _fallback_block_text(block)
        audit=(audit_map or {}).get(block['block_id'],{'preserved':True,'issue':None})
        if not audit['preserved']:
            issue_key=f'report-preservation:{block["block_id"]}'
            _semantic_dissent(work,issue_key=issue_key,stage='final preservation audit',reviewed_text=text,dissent_reason=audit.get('issue') or 'Rendered block did not preserve the deterministic source block.',action_recommended='Use the deterministic source-preserving fallback for this block.')
            fallback=_fallback_block_text(block)
            _semantic_dissent_address(work,issue_key=issue_key,stage='deterministic report fallback',action='Replace the failed rendered block with its deterministic fallback.',outcome=fallback,status='resolved')
            text=fallback
        tags=[]
        for comp in block['components']:
            for tag in comp.get('card_tags') or []:
                if tag not in tags: tags.append(tag)
        final.append({'block_id':block['block_id'],'domain':block['domain'],'text':runtime.ensure_sentence(text),'card_tags':tags})
    _write(_existing_or_new(work,'report_write','report-final-blocks.yaml'),yaml.safe_dump({'blocks':final},sort_keys=False,allow_unicode=True,width=110))
    return final


def _render_dissent_markdown(issues):
    sections=[]; labels={'open':'Open','resolved':'Resolved','retained_with_dissent':'Retained with dissent'}
    for issue in issues:
        if not issue.get('reviewed_text') or not issue.get('history'): continue
        lines=[f"## Issue {issue.get('id')}",'','**Reviewed text:**','',str(issue['reviewed_text'])]
        raised=False
        for event in issue['history']:
            stage=str(event.get('stage') or 'unknown stage')
            if event.get('event')=='raised':
                lines += ['',('### Stage first raised' if not raised else '### Stage dissent re-raised')+f' — {stage}','','**Reason**','']+[f'- {x}' for x in event.get('reason') or []]+['','**Resolution recommendation**','']+[f'- {x}' for x in event.get('resolution_recommendation') or []]; raised=True
            elif event.get('event')=='addressed':
                lines += ['',f'### Stage next addressed — {stage}','','**Action**','']+[f'- {x}' for x in event.get('action') or []]
                if event.get('outcome'): lines += ['','**Outcome**','']+[f'- {x}' for x in event.get('outcome') or []]
        lines += ['',f"**Status:** {labels.get(issue.get('status'),issue.get('status','Open'))}"]
        sections.append('\n'.join(lines))
    return '# Semantic dissent\n\n'+'\n\n---\n\n'.join(sections)+'\n' if sections else ''

def _write_dissent(work):
    path=Path(work)/'dissent.md'; text=_render_dissent_markdown(_semantic_dissent_doc(work).get('issues') or [])
    if text: _write(path,text)
    elif path.exists(): path.unlink()
    return path if text else None

def stage_final(work,case,final_blocks,elements,all_cards,digest,manifest):
    ids=[]
    for el in elements:
        for ev in el.get('evidence') or []:
            cid=ev.get('card_id')
            if cid and cid not in ids: ids.append(cid)
    by_id={c['card_id']:c for c in all_cards}; selected=[by_id[cid] for cid in ids if cid in by_id]
    bundle={'workflow_profile':WORKFLOW_ID,'terraced_domain':'all','genes':runtime.case_genes(case),'retrieved':selected,'runtime_card_tags':card_identity.runtime_tag_map(manifest),'provenance':{'corpus_sha256':digest,'retrieved_at':datetime.now(timezone.utc).isoformat()}}
    bpath=_existing_or_new(work,'final_evidence','bundle.json'); epath=_existing_or_new(work,'final_evidence','evidence.md'); tpath=_existing_or_new(work,'final_evidence','card-tags.json'); _write(bpath,json.dumps(bundle,indent=2,ensure_ascii=False)+'\n'); rendering.render_to_files(bpath,output=epath,card_tag_output=tpath,retrieved_only=True)
    headings={'diagnosis':'**Diagnosis**','prognosis':'**Prognosis**','treatment':'**Treatment Implications**','biomarker':'**MRD**','germline':'**Germline**'}; parts=[]
    for domain in ('diagnosis','prognosis','treatment','biomarker','germline'):
        rows=[b for b in final_blocks if b['domain']==domain]
        if not rows: continue
        parts.append(headings[domain]); parts.append('')
        for row in rows:
            suffix=' '+''.join(row.get('card_tags') or []) if row.get('card_tags') else ''
            parts.append(row['text'].rstrip()+suffix); parts.append('')
    cited='\n'.join(parts).rstrip()+'\n'; _write(_existing_or_new(work,'report_write','report-cited.md'),cited)
    rendered=citations.render(cited,_read(epath),_read(tpath),require_citation_after_full_stop=False); rendered=case['detected_variants_summary']+'\n\n'+rendered.lstrip(); _write(Path(work)/'report-final.md',rendered); _write_dissent(work)
    payload={'workflow':WORKFLOW_ID,'blocks':final_blocks,'risk_log':_risk_doc(work),'model_usage':_usage_summary(work),'report_markdown':rendered}; _write(Path(work)/'report-final.json',json.dumps(payload,indent=2,ensure_ascii=False)+'\n')
    mode=_load_run_state(work).get('mode')
    if mode in VALIDATION_MODES:
        case_id=_load_run_state(work).get('validation_case'); package_marking_bundle(case_id,Path(work)/'report-final.md',Path(work)/f'{MARKING_PREFIX[mode]}-{case_id}.zip',case_file=validation_cases.VALIDATION_CASE_FILES[mode])

def _who2_required(ctx):
    cfg=((load_settings().get('diagnosis') or {}).get('who5') or {})
    if not bool(cfg.get('reconsider_after_cmc_expansion', False)):
        return False
    case=ctx.get('case') or {}
    who1=ctx.get('committed_who1') or ctx.get('who1')
    if not who1:
        commit=_existing_or_new(ctx.work,'diagnosis_who1_commit','accepted-routing.yaml')
        if commit.is_file():
            who1=(yaml.safe_load(_read(commit)) or {}).get('accepted_who1')
    if not who1:
        return False
    return runtime.derive_cmcs(who1) != list(case.get('bootstrap_cmcs') or [])


def _workflow_domain_contracts(workflow):
    out={}
    for domain in ('prognosis','treatment','biomarker','germline'):
        try: step=workflow.step(domain)
        except KeyError: continue
        if step.stage_spec_obj and step.stage_spec_obj.type=='domain_proforma':
            out[domain]=domain_contract.from_spec(step.stage_spec_obj)
        else:
            out[domain]=domain_contract.contract(domain)
    return out


def _provider_handlers(workflow):
    def structure_handler(step, ctx):
        _stage_status(ctx.work, step.id, 'Workflow — structure case')
        case, reg = stage_structure(ctx.work, ctx.profile, prompt_text=_compiled_prompt(step,workflow,ctx))
        ctx.put('case', case); ctx.put('registry', reg)
        return {'artifact':case}

    def corpus_handler(step, ctx):
        _stage_status(ctx.work, step.id, 'Workflow — initialise corpus')
        all_cards, eligible, digest, manifest = stage_corpus(ctx.work)
        ctx.put('all_cards', all_cards); ctx.put('eligible', eligible)
        ctx.put('corpus_digest', digest); ctx.put('manifest', manifest)
        return {}

    def who1_handler(step, ctx):
        _stage_status(ctx.work, 'diagnosis', 'Workflow — WHO5 / ICC / independent concurrent diagnosis')
        history=list((ctx.get('case') or {}).get('bootstrap_cmcs') or [])
        who,cards=stage_diagnosis_who_pass(ctx.work,ctx.get('case'),ctx.get('registry'),ctx.get('eligible'),ctx.get('manifest'),ctx.profile,pass_number=1,history=history,prompt_text=_compiled_prompt(step,workflow,ctx))
        ctx.put('who1',who); ctx.put('diagnostic_history',history)
        cards_by=dict(ctx.get('cards_by_domain',{}) or {}); cards_by['diagnosis_who5']=cards; ctx.put('cards_by_domain',cards_by)
        return {'artifact':who}

    def who1_routing_change_handler(step, ctx):
        from workflows.proforma_v1 import self_runtime as sr
        change=sr.assess_who1_routing_change(ctx.work); ctx.put('who1_routing_change',change)
        return {'artifact':change}

    def who1_evidence_assignment_handler(step, ctx):
        from workflows.proforma_v1 import self_runtime as sr
        max_passes=int((step.evidence or {}).get('match_passes',2))
        while True:
            manifest=sr.prepare_who1_evidence_resolution(ctx.work,max_match_passes=max_passes,prompt=step.prompt)
            if manifest.get('complete'):
                if not manifest.get('required'):
                    doc={'matches':[]}
                else:
                    doc=sr.accept_who1_evidence_resolution(ctx.work)
                ctx.put('who1_evidence_assignments',doc); return {'artifact':doc,'status':'complete'}
            state=sr.read_yaml(sr._who1_gate_state_path(ctx.work)); item=state['item']
            prompt=_evidence_prompt(step,ctx,manifest)
            _model_call(ctx.work,call_id=f"who1-evidence-match-{manifest['match_pass']:02d}",role=step.role,prompt=prompt,output=manifest['output'],validator=lambda t,it=item:schema_validation.validate_evidence_match_batch(t,[{'evidence_id':it['evidence_id'],'candidate_card_tags':it['candidate_card_tags']}]),profile=ctx.profile)

    def who1_evidence_audit_handler(step, ctx):
        from workflows.proforma_v1 import self_runtime as sr
        manifest=sr.prepare_who1_evidence_audit(ctx.work,prompt=step.prompt)
        if not manifest.get('required'):
            doc={'audits':[]}; ctx.put('who1_evidence_audits',doc); return {'status':'skipped','reason':'no_matched_cards','artifact':doc}
        assignment=sr.accept_who1_evidence_resolution(ctx.work); tags=list((assignment.get('matches') or [{}])[0].get('card_tags') or [])
        prompt=_evidence_prompt(step,ctx,manifest)
        _model_call(ctx.work,call_id='who1-evidence-audit',role=step.role,prompt=prompt,output=manifest['output'],validator=lambda t,tags=tags:schema_validation.validate_evidence_audit_batch(t,[{'evidence_id':'EWHO1','selected_card_tags':tags}]),profile=ctx.profile)
        doc=sr.accept_who1_evidence_audit(ctx.work); ctx.put('who1_evidence_audits',doc); return {'artifact':doc}

    def who1_evidence_adjudication_handler(step, ctx):
        from workflows.proforma_v1 import self_runtime as sr
        manifest=sr.prepare_who1_evidence_adjudication(ctx.work,prompt=step.prompt)
        if not manifest.get('required'):
            return {'status':'skipped','reason':'no_disagreement','artifact':{'adjudications':[]}}
        _agreed,disputes=sr.who1_evidence_disputes(ctx.work)
        prompt=_evidence_prompt(step,ctx,manifest)
        _model_call(ctx.work,call_id='who1-evidence-adjudication',role=step.role,prompt=prompt,output=manifest['output'],validator=lambda t,d=disputes:sr.evidence_engine.validate_adjudication(yaml.safe_load(t),d),profile=ctx.profile)
        doc=sr.read_yaml(manifest['output']); ctx.put('who1_evidence_adjudication',doc); return {'artifact':doc}

    def who1_commit_handler(step, ctx):
        from workflows.proforma_v1 import self_runtime as sr
        commit=sr.commit_who1_routing(ctx.work); ctx.put('who1_commit',commit); ctx.put('committed_who1',commit['accepted_who1'])
        history=list((ctx.get('case') or {}).get('bootstrap_cmcs') or [])
        for cmc in commit.get('routing_cmcs') or []:
            if cmc not in history: history.append(cmc)
        ctx.put('diagnostic_history',history)
        return {'artifact':commit}

    def who2_handler(step, ctx):
        history=list(ctx.get('diagnostic_history') or [])
        who,cards=stage_diagnosis_who_pass(ctx.work,ctx.get('case'),ctx.get('registry'),ctx.get('eligible'),ctx.get('manifest'),ctx.profile,pass_number=2,history=history,prompt_text=_compiled_prompt(step,workflow,ctx))
        for cmc in runtime.derive_cmcs(who):
            if cmc not in history: history.append(cmc)
        ctx.put('who2',who); ctx.put('diagnostic_history',history)
        cards_by=dict(ctx.get('cards_by_domain',{}) or {}); cards_by['diagnosis_who5']=cards; ctx.put('cards_by_domain',cards_by)
        return {'artifact':who}

    def icc_handler(step, ctx):
        history=list(ctx.get('diagnostic_history') or [])
        who=ctx.get('who2') or ctx.get('committed_who1') or ctx.get('who1')
        icc,cards=stage_diagnosis_icc_pass(ctx.work,ctx.get('case'),ctx.get('registry'),ctx.get('eligible'),ctx.get('manifest'),ctx.profile,history=history,who=who,prompt_text=_compiled_prompt(step,workflow,ctx))
        ctx.put('icc',icc)
        cards_by=dict(ctx.get('cards_by_domain',{}) or {}); cards_by['diagnosis_icc']=cards; ctx.put('cards_by_domain',cards_by)
        return {'artifact':icc}

    def other_handler(step, ctx):
        history=list(ctx.get('diagnostic_history') or [])
        who=ctx.get('who2') or ctx.get('committed_who1') or ctx.get('who1')
        other,cards=stage_diagnosis_other_pass(ctx.work,ctx.get('case'),ctx.get('registry'),ctx.get('eligible'),ctx.get('manifest'),ctx.profile,history=history,who=who,icc=ctx.get('icc'),prompt_text=_compiled_prompt(step,workflow,ctx))
        ctx.put('diagnosis_other',other)
        cards_by=dict(ctx.get('cards_by_domain',{}) or {}); cards_by['diagnosis_other']=cards; ctx.put('cards_by_domain',cards_by)
        return {'artifact':other}

    def diagnosis_finalize_handler(step, ctx):
        diagnosis,cmcs=stage_diagnosis_finalize_pass(ctx.work,ctx.get('case'),ctx.get('committed_who1') or ctx.get('who1'),ctx.get('who2'),ctx.get('icc'),ctx.get('diagnosis_other'),list(ctx.get('diagnostic_history') or []))
        ctx.put('diagnosis',diagnosis); ctx.put('diagnostic_cmcs',cmcs)
        return {'artifact':diagnosis}

    def domain_handler(step, ctx):
        domain = step.id
        _stage_status(ctx.work, domain, f'Workflow — {domain} owner proforma')
        selected_contract=domain_contract.from_spec(step.stage_spec_obj) if step.stage_spec_obj and step.stage_spec_obj.type=='domain_proforma' else domain_contract.contract(domain)
        proforma, cards = stage_domain(
            ctx.work, domain, ctx.get('case'), ctx.get('registry'), ctx.get('diagnosis'),
            ctx.get('eligible'), ctx.get('manifest'), ctx.profile, prompt_text=_compiled_prompt(step,workflow,ctx),
            contract_override=selected_contract,stage_spec_override=step.stage_spec_obj
        )
        domains = dict(ctx.get('domains', {}) or {}); domains[domain] = proforma; ctx.put('domains', domains)
        cards_by_domain = dict(ctx.get('cards_by_domain', {}) or {}); cards_by_domain[domain] = cards; ctx.put('cards_by_domain', cards_by_domain)
        return {'artifact':proforma}

    def _evidence_prompt(step,ctx,manifest):
        parts=[_compiled_prompt(step,workflow,ctx).rstrip()]
        seen=set()
        for label,key in (("Fact blocks","facts"),("Evidence items","items"),("Disputes","disputes")):
            path=manifest.get(key)
            if isinstance(path,Path) and path.is_file() and path.resolve() not in seen:
                seen.add(path.resolve())
                parts += [f"\n# {label}\n",path.read_text(encoding='utf-8').rstrip()]
        cards=manifest.get('cards')
        if isinstance(cards,Path) and cards.is_file():
            parts += ["\n# Eligible card text\n",cards.read_text(encoding='utf-8').rstrip()]
        return "\n".join(parts)+"\n"

    def evidence_assignment_handler(step,ctx):
        from workflows.proforma_v1 import self_runtime as sr
        _stage_status(ctx.work,'evidence.assignment','Workflow — evidence assignment')
        contracts=_workflow_domain_contracts(workflow)
        specs={d:workflow.step(d).stage_spec_obj for d in contracts}
        rescue_passes=int((step.evidence or {}).get('rescue_match_passes',(step.evidence or {}).get('match_passes',1)))
        owner_domains={d for d in ('prognosis','treatment','biomarker','germline') if bool((workflow.step(d).evidence or {}).get('owner_assignment',False))}
        while True:
            manifest=sr.prepare_evidence_resolution(
                ctx.work,contracts=contracts,specs=specs,rescue_match_passes=rescue_passes,owner_assignment_domains=owner_domains
            )
            if manifest.get('complete'):
                break
            pass_no=int(manifest['match_pass'])
            rescue_round=int(manifest.get('rescue_round',1))
            _status(f"  evidence rescue round {rescue_round} pass {pass_no}/{rescue_passes}: {manifest['fact_count']} fact(s)")
            validation_items=list(manifest['validation_items'])
            call_id=f'evidence-assignment-rescue-{rescue_round:02d}-pass-{pass_no:02d}'
            _model_call(
                ctx.work,call_id=call_id,role=step.role,prompt=_evidence_prompt(step,ctx,manifest),output=manifest['output'],
                validator=lambda t,vi=validation_items:schema_validation.validate_evidence_match_batch(t,vi),profile=ctx.profile,
                max_attempts=_retry('evidence_match_model_attempts'),
            )
        doc=sr.accept_evidence_resolution(ctx.work); ctx.put('evidence_assignments',doc)
        return {'artifact':doc}

    def evidence_audit_handler(step,ctx):
        from workflows.proforma_v1 import self_runtime as sr
        _stage_status(ctx.work,'evidence.audit','Workflow — evidence audit')
        manifest=sr.prepare_evidence_audit(ctx.work)
        targets=list(manifest.get('targets') or [])
        if not manifest.get('required'):
            doc={'audits':[]}; sr.apply_evidence_audit(ctx.work); ctx.put('evidence_audits',doc)
            return {'status':'skipped','reason':'no_matched_cards','artifact':doc}
        validation_items=[{'evidence_id':x['evidence_id'],'selected_card_tags':x['selected_card_tags']} for x in targets]
        _model_call(
            ctx.work,call_id='evidence-audit',role=step.role,prompt=_evidence_prompt(step,ctx,manifest),output=manifest['output'],
            validator=lambda t,vi=validation_items:schema_validation.validate_evidence_audit_batch(t,vi),profile=ctx.profile,
            max_attempts=_retry('evidence_audit_model_attempts'),
        )
        doc=yaml.safe_load(_read(manifest['output'])) or {}; sr.apply_evidence_audit(ctx.work); ctx.put('evidence_audits',doc)
        return {'artifact':doc}

    def evidence_adjudication_handler(step,ctx):
        from workflows.proforma_v1 import self_runtime as sr
        manifest=sr.prepare_evidence_adjudication(ctx.work)
        if not manifest.get('required'):
            ctx.put('evidence_adjudication',{'adjudications':[]})
            return {'status':'skipped','reason':'no_disagreement','artifact':{'adjudications':[]}}
        disputes=(yaml.safe_load(_read(manifest['disputes'])) or {}).get('disputes') or []
        def validate(text):
            doc=yaml.safe_load(text)
            if not isinstance(doc,dict): raise ValueError('evidence adjudication output must be a YAML mapping')
            sr.validate_adjudication(doc,disputes)
            return 'valid evidence adjudication'
        _model_call(
            ctx.work,call_id='evidence-adjudication',role=step.role,prompt=_evidence_prompt(step,ctx,manifest),output=manifest['output'],
            validator=validate,profile=ctx.profile,max_attempts=_retry('evidence_audit_model_attempts'),
        )
        doc=yaml.safe_load(_read(manifest['output'])) or {}; ctx.put('evidence_adjudication',doc)
        return {'artifact':doc}

    def evidence_finalize_handler(step,ctx):
        from workflows.proforma_v1 import self_runtime as sr
        supported=sr.finalize_evidence(ctx.work); ctx.put('supported',supported)
        return {'artifact':supported}

    def report_blocks_handler(step, ctx):
        blocks = stage_blocks(ctx.work, ctx.get('diagnosis'), ctx.get('supported'), ctx.get('registry'))
        ctx.put('blocks', blocks)
        return {'artifact':blocks}

    def report_write_handler(step, ctx):
        _stage_status(ctx.work, 'report', 'Workflow — report writing')
        blocks=ctx.get('blocks')
        schema_validation.validate_report_source_blocks(blocks)
        rendered=stage_report_write(ctx.work,blocks,ctx.get('case'),ctx.get('registry'),ctx.profile,prompt_text=_compiled_prompt(step,workflow,ctx))
        ctx.put('rendered_blocks',rendered)
        return {'artifact':{'blocks':rendered}}

    def report_preservation_handler(step, ctx):
        audits=stage_report_preservation(ctx.work,ctx.get('blocks'),ctx.get('rendered_blocks'),ctx.profile,prompt_text=_compiled_prompt(step,workflow,ctx))
        ctx.put('report_audits',audits)
        return {'artifact':{'audits':list(audits.values())}}

    def report_finalize_handler(step, ctx):
        final_blocks=stage_report_finalize_blocks(ctx.work,ctx.get('blocks'),ctx.get('rendered_blocks'),audit_map=ctx.get('report_audits'))
        stage_final(ctx.work,ctx.get('case'),final_blocks,ctx.get('supported'),ctx.get('all_cards'),ctx.get('corpus_digest'),ctx.get('manifest'))
        ctx.put('final_blocks',final_blocks)
        return {'artifact':final_blocks}

    def generic_model_handler(step,ctx):
        if not step.role:
            raise StepFailure(f'generic model step {step.id!r} requires a role')
        output=workflow_artifacts.generic_output_path(ctx.work,step,create=True)
        schema_rel=(step.output or {}).get('schema')
        schema=generic_schema_validation.load_schema((workflow.asset_root/schema_rel).resolve()) if schema_rel else None
        fmt=(step.output or {}).get('format','yaml')
        def validate(text):
            generic_schema_validation.validate(text,fmt=fmt,schema=schema,check_specs=step.checks,context=ctx.data)
            return f'{step.id} valid'
        call_id='workflow-'+re.sub(r'[^a-zA-Z0-9_-]+','-',step.id).strip('-')
        _model_call(ctx.work,call_id=call_id,role=step.role,prompt=_compiled_prompt(step,workflow,ctx),output=output,validator=validate,profile=ctx.profile,fmt=fmt)
        raw=_read(output); doc=json.loads(raw) if fmt=='json' else yaml.safe_load(raw)
        artifact_name=(step.output or {}).get('artifact')
        if artifact_name: ctx.put(artifact_name,doc)
        return {'artifact':doc}

    return {
        'structure': structure_handler,
        'corpus': corpus_handler,
        'diagnosis_who1': who1_handler,
        'who1_routing_change': who1_routing_change_handler,
        'who1_evidence_assignment': who1_evidence_assignment_handler,
        'who1_evidence_audit': who1_evidence_audit_handler,
        'who1_evidence_adjudication': who1_evidence_adjudication_handler,
        'who1_commit': who1_commit_handler,
        'diagnosis_who2': who2_handler,
        'diagnosis_icc': icc_handler,
        'diagnosis_other': other_handler,
        'diagnosis_finalize': diagnosis_finalize_handler,
        'domain': domain_handler,
        'evidence_assignment': evidence_assignment_handler,
        'evidence_audit': evidence_audit_handler,
        'evidence_adjudication': evidence_adjudication_handler,
        'evidence_finalize': evidence_finalize_handler,
        'report_blocks': report_blocks_handler,
        'report_write': report_write_handler,
        'report_preservation': report_preservation_handler,
        'report_finalize': report_finalize_handler,
        'generic_model': generic_model_handler,
    }

def _model_step_validated(work, call_id):
    root=layout.model_step_dir(Path(work),call_id,existing=True)
    return (root/'validated.txt').is_file()


def _provider_step_complete(step_id, ctx):
    # Completion checks must be lazy.  In particular, checking an early step
    # such as ``structure`` must not evaluate downstream predicates that read
    # artifacts which cannot exist yet.
    from workflows.proforma_v1 import self_runtime as sr

    work = ctx.work
    checks = {
        'structure': lambda: (
            _model_step_validated(work,'structure-case')
            and has_artifact(work,'structured_case','case.json')
            and (
                not _profile(work,ctx.profile,'structure').is_self
                or has_artifact(work,'variant_registry','variants.yaml')
            )
        ),
        'corpus': lambda: has_artifact(work,'card_identity','card-identity-manifest.json'),
        'diagnosis.who1': lambda: _model_step_validated(work,'diagnosis-who5-pass-01'),
        'diagnosis.who1.routing_change': lambda: sr._who1_routing_change_path(work).is_file(),
        'diagnosis.who1.evidence.assignment': lambda: sr._who1_gate_match_final_path(work).is_file(),
        'diagnosis.who1.evidence.audit': lambda: sr._who1_gate_audit_path(work).is_file(),
        'diagnosis.who1.evidence.adjudication': lambda: (
            sr._who1_gate_adjudication_path(work).is_file()
            or not sr.assess_who1_routing_change(work).get('changed')
        ),
        'diagnosis.who1.commit': lambda: sr._who1_commit_path(work).is_file(),
        'diagnosis.who2': lambda: _model_step_validated(work,'diagnosis-who5-pass-02'),
        'diagnosis.icc': lambda: _model_step_validated(work,'diagnosis-icc'),
        'diagnosis.other': lambda: _model_step_validated(work,'diagnosis-other'),
        'diagnosis.finalize': lambda: has_artifact(work,'diagnosis','diagnosis-final.yaml'),
        'prognosis': lambda: _model_step_validated(work,'prognosis') and has_artifact(work,'prognosis_state','model-classification.yaml'),
        'treatment': lambda: _model_step_validated(work,'treatment') and has_artifact(work,'treatment_state','model-classification.yaml'),
        'biomarker': lambda: _model_step_validated(work,'biomarker') and has_artifact(work,'biomarker_state','model-classification.yaml'),
        'germline': lambda: _model_step_validated(work,'germline') and has_artifact(work,'germline_state','model-classification.yaml'),
        'evidence.assignment': lambda: has_artifact(work,'evidence_matches','self-resolution.yaml'),
        'evidence.audit': lambda: (
            (lambda path: path.is_file() and sr._evidence_state_path(work).is_file() and (
                sr._load_evidence_state(work).get('processed_audit_sha256') == sr._audit_sha256(path)
            ))(_existing_or_new(work,'evidence_audits','self-audit.yaml'))
        ),
        'evidence.adjudication': lambda: _model_step_validated(work,'evidence-adjudication') and has_artifact(work,'evidence_adjudication','adjudication.yaml'),
        'evidence.finalize': lambda: has_artifact(work,'evidence_enriched','reportable-elements.yaml'),
        'report.blocks': lambda: has_artifact(work,'report_blocks','report-blocks.yaml'),
        'report.write': lambda: _model_step_validated(work,'report-write') and has_artifact(work,'report_write','report-write.yaml'),
        'report.preservation': lambda: _model_step_validated(work,'report-preservation') and has_artifact(work,'report_write','report-preservation.yaml'),
        'report.finalize': lambda: (Path(work)/'report-final.md').is_file(),
    }
    check = checks.get(step_id)
    return bool(check()) if check is not None else False


def _hydrate_provider_context(work, context):
    work=Path(work)
    if has_artifact(work,'structured_case','case.json'):
        case=runtime.read_json(_case_json(work)); context.put('case',case)
        if has_artifact(work,'variant_registry','variants.yaml'):
            regdoc=yaml.safe_load(_read(_variants_path(work))) or {}; context.put('registry',regdoc.get('variants') or {})
        elif not _profile(work,context.profile,'structure').is_self:
            # Preserve the existing non-self provider contract: a missing deterministic
            # structure tail remains an error rather than being silently recovered.
            regdoc=yaml.safe_load(_read(_variants_path(work))) or {}; context.put('registry',regdoc.get('variants') or {})
    if has_artifact(work,'card_identity','card-identity-manifest.json'):
        all_cards,eligible,digest,manifest=stage_corpus(work)
        context.put('all_cards',all_cards); context.put('eligible',eligible); context.put('corpus_digest',digest); context.put('manifest',manifest)
    case=context.get('case') or {}
    history=list(case.get('bootstrap_cmcs') or [])
    if _model_step_validated(work,'diagnosis-who5-pass-01'):
        who1=yaml.safe_load(_read(_artifact(work,'diagnosis_who5_pass_1','who5.yaml'))) or {}; context.put('who1',who1)
    from workflows.proforma_v1 import self_runtime as _sr
    if _sr._who1_routing_change_path(work).is_file():
        context.put('who1_routing_change',yaml.safe_load(_read(_sr._who1_routing_change_path(work))) or {})
    if _sr._who1_commit_path(work).is_file():
        commit=yaml.safe_load(_read(_sr._who1_commit_path(work))) or {}; context.put('who1_commit',commit); context.put('committed_who1',commit.get('accepted_who1'))
        for cmc in runtime.derive_cmcs(commit.get('accepted_who1') or {}):
            if cmc not in history: history.append(cmc)
    if _model_step_validated(work,'diagnosis-who5-pass-02'):
        who2=yaml.safe_load(_read(_artifact(work,'diagnosis_who5_pass_2','who5.yaml'))) or {}; context.put('who2',who2)
        for cmc in runtime.derive_cmcs(who2):
            if cmc not in history: history.append(cmc)
    context.put('diagnostic_history',history)
    if _model_step_validated(work,'diagnosis-icc'): context.put('icc',yaml.safe_load(_read(_existing_or_new(work,'diagnosis_icc','icc.yaml'))) or {})
    if _model_step_validated(work,'diagnosis-other'): context.put('diagnosis_other',yaml.safe_load(_read(_existing_or_new(work,'diagnosis_other','other.yaml'))) or {})
    if has_artifact(work,'diagnosis','diagnosis-final.yaml'): context.put('diagnosis',yaml.safe_load(_read(_existing_or_new(work,'diagnosis','diagnosis-final.yaml'))) or {})
    domains={}
    for domain in ('prognosis','treatment','biomarker','germline'):
        if has_artifact(work,f'{domain}_state','proforma.yaml'):
            domains[domain]=yaml.safe_load(_read(_existing_or_new(work,f'{domain}_state','proforma.yaml'))) or {}
    context.put('domains',domains)
    if context.get('eligible') is not None and context.get('registry') is not None and context.get('diagnosis'):
        genes=runtime.case_genes(case); disease=context.get('diagnosis')['who5']['schema_disease']; cards_by={}
        cards_by['diagnosis_who5']=_diagnostic_cards(context.get('eligible'),genes,history,'who5')
        cards_by['diagnosis_icc']=_diagnostic_cards(context.get('eligible'),genes,history,'icc')
        cards_by['diagnosis_other']=_draw_diagnosis_cards(context.get('eligible'),genes,history)
        for domain in domains: cards_by[domain]=_draw_domain_cards(context.get('eligible'),domain,genes,[disease])
        context.put('cards_by_domain',cards_by)
    if has_artifact(work,'evidence_matches','self-resolution.yaml'):
        context.put('evidence_assignments',yaml.safe_load(_read(_existing_or_new(work,'evidence_matches','self-resolution.yaml'))) or {})
    if has_artifact(work,'evidence_audits','self-audit.yaml'):
        context.put('evidence_audits',yaml.safe_load(_read(_existing_or_new(work,'evidence_audits','self-audit.yaml'))) or {})
    if has_artifact(work,'evidence_adjudication','adjudication.yaml'):
        context.put('evidence_adjudication',yaml.safe_load(_read(_existing_or_new(work,'evidence_adjudication','adjudication.yaml'))) or {})
    if has_artifact(work,'evidence_enriched','reportable-elements.yaml'):
        context.put('supported',(yaml.safe_load(_read(_existing_or_new(work,'evidence_enriched','reportable-elements.yaml'))) or {}).get('elements') or [])
    if has_artifact(work,'report_blocks','report-blocks.yaml'):
        context.put('blocks',(yaml.safe_load(_read(_existing_or_new(work,'report_blocks','report-blocks.yaml'))) or {}).get('blocks') or [])
    if has_artifact(work,'report_write','report-write.yaml'):
        context.put('rendered_blocks',(yaml.safe_load(_read(_existing_or_new(work,'report_write','report-write.yaml'))) or {}).get('blocks') or [])
    if has_artifact(work,'report_write','report-preservation.yaml'):
        audits=(yaml.safe_load(_read(_existing_or_new(work,'report_write','report-preservation.yaml'))) or {}).get('audits') or []
        context.put('report_audits',{a['block_id']:a for a in audits})
    return context

def _provider_invalidate(step_ids, context):
    workflow=context.get('workflow')
    call_ids={
        'structure':'structure-case','diagnosis.who1':'diagnosis-who5-pass-01','diagnosis.who2':'diagnosis-who5-pass-02',
        'diagnosis.icc':'diagnosis-icc','diagnosis.other':'diagnosis-other','prognosis':'prognosis','treatment':'treatment',
        'biomarker':'biomarker','germline':'germline','evidence.assignment':'evidence-assignment','evidence.audit':'evidence-audit',
        'evidence.adjudication':'evidence-adjudication','report.write':'report-write','report.preservation':'report-preservation',
    }
    outputs={
        'structure':artifact_path(context.work,'structured_case','case.json',create=False),
        'diagnosis.who1':artifact_path(context.work,'diagnosis_who5_pass_1','who5.yaml',create=False),
        'diagnosis.who2':artifact_path(context.work,'diagnosis_who5_pass_2','who5.yaml',create=False),
        'diagnosis.icc':artifact_path(context.work,'diagnosis_icc','icc.yaml',create=False),
        'diagnosis.other':artifact_path(context.work,'diagnosis_other','other.yaml',create=False),
        'diagnosis.finalize':artifact_path(context.work,'diagnosis','diagnosis-final.yaml',create=False),
        'prognosis':artifact_path(context.work,'prognosis_state','model-classification.yaml',create=False),
        'treatment':artifact_path(context.work,'treatment_state','model-classification.yaml',create=False),
        'biomarker':artifact_path(context.work,'biomarker_state','model-classification.yaml',create=False),
        'germline':artifact_path(context.work,'germline_state','model-classification.yaml',create=False),
        'evidence.assignment':artifact_path(context.work,'evidence_matches','self-resolution.yaml',create=False),
        'evidence.audit':artifact_path(context.work,'evidence_audits','self-audit.yaml',create=False),
        'evidence.adjudication':artifact_path(context.work,'evidence_adjudication','adjudication.yaml',create=False),
        'evidence.finalize':artifact_path(context.work,'evidence_enriched','reportable-elements.yaml',create=False),
        'report.write':artifact_path(context.work,'report_write','report-write.yaml',create=False),
        'report.preservation':artifact_path(context.work,'report_write','report-preservation.yaml',create=False),
    }
    for step_id in step_ids:
        path=outputs.get(step_id)
        if path: Path(path).unlink(missing_ok=True)
        if workflow is not None and step_id not in outputs:
            try: workflow_artifacts.generic_output_path(context.work,workflow.step(step_id),create=False).unlink(missing_ok=True)
            except KeyError: pass
        call_id=call_ids.get(step_id)
        if call_id:
            root=layout.model_step_dir(context.work,call_id,existing=True)
            if root.is_dir(): shutil.rmtree(root)
        if step_id in {'prognosis','treatment','biomarker','germline'}:
            artifact_path(context.work,f'{step_id}_state','proforma.yaml',create=False).unlink(missing_ok=True)
        if step_id=='report.finalize':
            for name in ('report-final.md','report-final.json'): (Path(context.work)/name).unlink(missing_ok=True)


def run_pipeline(work,profile=None,*,workflow_path=None):
    global _ACTIVE_COMPILED_WORKFLOW, _ACTIVE_WORKFLOW_CONTEXT
    _require_work(work); layout.ensure_dirs(work)
    compiled=_workflow_for_run(work,workflow_path); _ACTIVE_COMPILED_WORKFLOW=compiled
    context=WorkflowContext(Path(work),executor='provider',profile=profile,data={'settings':load_settings(),'workflow':compiled})
    _ACTIVE_WORKFLOW_CONTEXT=context
    from workflows.proforma_v1 import self_runtime as sr
    context.put('predicates',{'who2_required':_who2_required,'who1_routing_changed':lambda c: bool(sr.assess_who1_routing_change(c.work).get('changed'))})
    context.put('review_predicates',{'evidence_audit_resolved':lambda step,c,result: sr.evidence_audit_resolved(c.work)})
    _hydrate_provider_context(work,context)
    trace=TraceRecorder(compiled.workflow_id)
    runner=WorkflowRunner(compiled,ProviderExecutor(_provider_handlers(compiled),completion=_provider_step_complete,invalidator=_provider_invalidate),trace=trace)
    runner.run_all(context)
    trace.write(layout.logs(work)/'workflow-trace.json')
    _print_usage(work); _stage_status(work,'complete','proforma-v1 complete'); return EXIT_OK

def run_pipeline_setting(pid):
    if pid is not None:
        plan=pipeline_registry.load(pid); s=load_settings(); s['pipeline']=plan.pipeline_id; _write(SETTINGS_PATH,json.dumps(s,indent=2)+'\n')
    plan=pipeline_registry.load(configured_pipeline()); print(f'PIPELINE={plan.pipeline_id}'); [print(x) for x in pipeline_registry.describe(plan)]; return EXIT_OK

def _resolve_run_work_dir(work_dir):
    if work_dir is not None:
        return Path(work_dir).expanduser().resolve()
    root=HERE/'runs'
    candidates=sorted(
        [x for x in root.iterdir() if x.is_dir()],
        key=lambda x:x.stat().st_mtime,
        reverse=True,
    ) if root.is_dir() else []
    if not candidates:
        raise StepFailure('no --work-dir given and no proforma-v1 runs exist')
    work=candidates[0]
    _status(f'using most recent run directory: {work}')
    return work

def build_parser():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='command',required=True)
    s=sub.add_parser('setup'); s.add_argument('--mode',required=True,choices=supported_modes()); s.add_argument('--case-file',type=Path); s.add_argument('--example',type=int); s.add_argument('--case-id'); s.add_argument('--work-dir',type=Path); s.add_argument('--pipeline',choices=pipeline_registry.names()); s.add_argument('--workflow',type=Path)
    cs=sub.add_parser('check-stage'); cs.add_argument('--stage',required=True,choices=stage_checks.names()); cs.add_argument('--file',type=Path,required=True); cs.add_argument('--context',type=Path)
    sp=sub.add_parser('show-prompt'); sp.add_argument('--stage',required=True,choices=stage_checks.names()); sp.add_argument('--context',type=Path)
    sub.add_parser('stages')
    sub.add_parser('pipelines')
    wc=sub.add_parser('workflow-check'); wc.add_argument('--workflow',type=Path)
    pc=sub.add_parser('pipeline-check'); pc.add_argument('--pipeline',required=True,choices=pipeline_registry.names()); pc.add_argument('--workflow',type=Path)
    pp=sub.add_parser('pipeline-plan'); pp.add_argument('--pipeline',required=True,choices=pipeline_registry.names()); pp.add_argument('--workflow',type=Path)
    ps=sub.add_parser('pipeline'); ps.add_argument('pipeline_id',nargs='?',choices=pipeline_registry.names())
    r=sub.add_parser('run'); r.add_argument('--work-dir',type=Path); r.add_argument('--workflow',type=Path)
    return p

def main(argv=None):
    args=build_parser().parse_args(argv)
    try:
        if args.command=='setup': return run_setup(args)
        if args.command=='check-stage': return run_check_stage(args)
        if args.command=='show-prompt': return run_show_prompt(args)
        if args.command=='stages': return run_stage_check_assets(args)
        if args.command=='pipelines':
            for name in pipeline_registry.names(): print(f'{name}: {pipeline_registry.descriptions()[name]}')
            return EXIT_OK
        if args.command=='workflow-check':
            [print(x) for x in describe_workflow(_compile_selected_workflow(args.workflow))]; return EXIT_OK
        if args.command in {'pipeline-check','pipeline-plan'}:
            compiled=_compile_selected_workflow(args.workflow); plan=pipeline_registry.load(args.pipeline); print(f'PIPELINE={plan.pipeline_id}'); [print(x) for x in pipeline_registry.describe(plan)]; [print(x) for x in describe_workflow(compiled)]; return EXIT_OK
        if args.command=='pipeline': return run_pipeline_setting(args.pipeline_id)
        if args.command=='run':
            work=_resolve_run_work_dir(args.work_dir)
            with _cli_logging(work): return run_pipeline(work,workflow_path=args.workflow)
        raise StepFailure(f'unknown command {args.command}')
    except Handoff as h:
        print(f'HANDOFF={h.call_id}'); print(f'PROMPT={h.prompt}'); print(f'OUTPUT={h.output}'); return EXIT_HANDOFF
    except Exception as exc:
        print(f'proforma-v1 failed: {exc}',file=sys.stderr); return EXIT_FAILURE

if __name__=='__main__': raise SystemExit(main())
