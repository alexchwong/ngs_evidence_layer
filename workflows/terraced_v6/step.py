#!/usr/bin/env python3
"""Terraced-v6 minimal prototype: owner proformas -> evidence -> deterministic blocks -> report."""
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
from validation.scripts.package_marking import package_marking_bundle
from validation.scripts.bundled_cases import is_validation_mode, write_demo_marking_criteria_after_report
from workflows.terraced_v6 import card_identity, domain_contract, evidence_resolution, layout, model_client, model_context, pipeline_registry, prognosis_report, prompt_loader, rendering, runtime, schema_validation, stage_checks, stage_spec

WORKFLOW_ID='terraced-v6'; RUN_STATE_SCHEMA_VERSION=3; HERE=Path(__file__).resolve().parent; PROMPTS=HERE/'prompts'; WORKFLOW_PATH=HERE/'workflow.json'
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
_EXECUTION_STARTED_AT=None

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
    if d.get('schema_version')!=1: raise StepFailure('unsupported terraced-v6 settings schema; expected 1')
    required={'retries','diagnosis','ptbg','reportability','prompts'}
    missing=sorted(required-set(d))
    if missing: raise StepFailure(f'terraced-v6 settings missing required sections: {missing}')
    return d

def _setting(*keys):
    value=load_settings()
    for key in keys:
        if not isinstance(value,dict) or key not in value: raise StepFailure(f'missing terraced-v6 setting: {".".join(keys)}')
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
    'germline':{'germline_support':True,'germline_against':False,'germline_uncertain':False},
}

def _reportable(domain,key):
    default=_REPORTABILITY_DEFAULTS.get(domain,{}).get(key,True)
    reportability=load_settings().get('reportability') or {}
    domains=reportability.get('domains') or {}
    domain_cfg=domains.get(domain) or {}
    value=domain_cfg.get(key,default)
    if not isinstance(value,bool):
        raise StepFailure(f'reportability.domains.{domain}.{key} must be true or false')
    return value
def configured_pipeline(): return str(load_settings().get('pipeline') or 'self')
def _prompt(name):
    rel=str(_setting('prompts',name))
    return prompt_loader.render(Path(rel),root=PROMPTS)
def _run_state_path(work): return _artifact(work,'run_state','terraced-v6-run.json',new=True)
def _load_run_state(work):
    d=json.loads(_read(_artifact(work,'run_state','terraced-v6-run.json')))
    if d.get('schema_version')!=RUN_STATE_SCHEMA_VERSION: raise StepFailure('incompatible terraced-v6 run state; start a fresh run')
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
def _record_usage(work,call_id,model,attempt,usage,*,role=None):
    p=_usage_path(work); doc={'schema_version':1,'calls':[]}
    if p.is_file():
        try: doc=json.loads(_read(p))
        except (OSError,json.JSONDecodeError,TypeError): doc={'schema_version':1,'calls':[]}
    doc.setdefault('calls',[]).append({'operation':call_id,'role':role,'model':model,'attempt':attempt,'usage':usage})
    _write(p,json.dumps(doc,indent=2,ensure_ascii=False)+'\n')
def _usage_summary(work):
    p=_usage_path(work)
    if not p.is_file(): return None
    try: calls=json.loads(_read(p)).get('calls',[])
    except (OSError,json.JSONDecodeError,TypeError): return None
    reported=[r.get('usage') for r in calls if isinstance(r.get('usage'),dict)]
    totals={k:sum((u or {}).get(k,0) for u in reported) for k in ('prompt_tokens','completion_tokens','total_tokens')}
    return {'calls':len(calls),'reported_calls':len(reported),'unreported_calls':len(calls)-len(reported),'totals':totals}
def _print_usage(work):
    summary=_usage_summary(work)
    if summary is None:
        _status('Token usage: unavailable (self handoff or no provider usage ledger)'); return
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
    out=[f'# Terraced-v6 model operation — {call_id}','']
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
        try: comp=model_client.complete_messages(binding,[{'role':'system','content':syntax_repair.SYNTAX_REPAIR_SYSTEM_PROMPT},{'role':'user','content':prompt}])
        except model_client.TruncatedCompletion as exc:
            _record_usage(work,sid,binding.model,attempt,exc.usage,role='syntax_repair'); text=exc.content
        except RuntimeError as exc: raise StepFailure(str(exc)) from exc
        else:
            if isinstance(comp,model_client.Completion): text=comp.content; usage=comp.usage
            else: text=comp; usage=None
            _record_usage(work,sid,binding.model,attempt,usage,role='syntax_repair')
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


def _sanitize_proforma_text(work,call_id,text):
    """Silently remove evidence-card assignment leaked into an owner pro-forma.

    Card identity belongs to evidence resolution, never to diagnosis/PTBG owner
    reasoning.  This runs after syntax repair but before deterministic validation,
    so a harmless leaked tag does not consume a model repair turn.
    """
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
                if key in {'card_tag','card_tags'}:
                    records.append({'stage':call_id,'transform':'strip_proforma_card_assignment','path':child})
                    continue
                if key in {'reason','other_evidence_reason'} and isinstance(item,str):
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


def _task_io(work,*,call_id,role,binding,syntax_binding,output,root):
    """Bind the shared runner to this workflow's filesystem, logging and provider.

    The runner performs no I/O of its own; everything environment-specific is
    supplied here.  That is what lets the same runner drive the interactive
    `self` pipeline and a direct provider pipeline without knowing about either.
    """
    def call_model(messages):
        _write(root/'messages.json',json.dumps(messages,indent=2,ensure_ascii=False)+'\n')
        _write(root/'prompt.md',_render_bundle(call_id,messages,output))
        try: comp=model_client.complete_messages(binding,messages)
        except model_client.TruncatedCompletion as exc:
            _record_usage(work,call_id,binding.model,0,exc.usage,role=role)
            return validated_model_task.Truncated(exc.content,max_tokens=exc.max_tokens)
        except RuntimeError as exc: raise StepFailure(str(exc)) from exc
        if isinstance(comp,model_client.Completion): _record_usage(work,call_id,binding.model,0,comp.usage,role=role); return comp.content
        _record_usage(work,call_id,binding.model,0,None,role=role); return comp

    def call_syntax(prompt,attempt):
        sid=f'{call_id}-syntax-{attempt}'; sroot=layout.model_step_dir(work,sid,existing=False)
        _write(sroot/'prompt.md',prompt)
        if syntax_binding.is_self:
            existing=sroot/'output.txt'
            if existing.is_file(): return _read(existing)
            raise Handoff(sid,sroot/'prompt.md',existing)
        try: comp=model_client.complete_messages(syntax_binding,[{'role':'system','content':syntax_repair.SYNTAX_REPAIR_SYSTEM_PROMPT},{'role':'user','content':prompt}])
        except model_client.TruncatedCompletion as exc: return exc.content
        except RuntimeError as exc: raise StepFailure(str(exc)) from exc
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


def _model_call(work,*,call_id,role,prompt,output,validator,profile=None,fmt='yaml',max_attempts=None,feedback=None,system_prompt=None,proforma=False,max_rewrites=None):
    """Run one validated model task.

    Retry, repair, budget and suspension behaviour now live in the shared runner
    (`scripts.core.validated_model_task`).  This function only binds this
    workflow's prompts, paths and provider bindings to it.
    """
    return _run_model_task(
        work,call_id=call_id,role=role,prompt=prompt,output=output,validator=validator,
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

def run_setup(args):
    plan=pipeline_registry.load(args.pipeline or configured_pipeline()); label=args.mode
    if args.mode=='ngs-report' and args.case_file: label+='-'+args.case_file.stem
    elif args.mode=='nel-demo': label+=f'-{args.example}'
    elif args.case_id: label+='-'+args.case_id
    work_arg=args.work_dir or _timestamped_work_dir(HERE/'runs',label); work_arg.parent.mkdir(parents=True,exist_ok=True)
    work=setup_workflow(workflow=WORKFLOW_ID,mode=args.mode,work_dir=work_arg,project=False,example=args.example,case_id=args.case_id)
    write_workflow_state(work,WORKFLOW_ID,args.mode,model_profile=plan.pipeline_id)
    case_path=layout.input(work,'case.md',existing=False)
    if args.case_file: shutil.copyfile(args.case_file.expanduser().resolve(),case_path)
    if not case_path.is_file() or not _read(case_path).strip(): raise StepFailure(f'case.md missing or empty: {case_path}')
    _save_run_state(work,{'schema_version':RUN_STATE_SCHEMA_VERSION,'workflow_id':WORKFLOW_ID,'mode':args.mode,'validation_case':args.case_id,'example':args.example,'pipeline':plan.pipeline_id,'created_at':datetime.now(timezone.utc).isoformat()})
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
def stage_structure(work,profile):
    out=_case_json(work)
    prompt=_prompt('structure_case')+'\n\n# Authoritative case\n'+_read(layout.input(work,'case.md'))+'\n\n# Allowed bootstrap CMCs\n'+_read(layout.setup(work,'case-major-categories.json'))
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

def _consolidate_rows(domain,doc,reg):
    """Merge rows sharing one normalised proposition. Returns (doc, merge records).

    The model now emits one row per variant (see domain_contract), so this is the
    only place grouping happens.  Every merge is reported so a developer can tell
    model output from deterministic normalisation.
    """
    buckets=domain_contract.contract(domain).buckets; merges=[]
    for bucket in buckets:
        rows=doc.get(bucket) or []; groups=[]; index={}; templates={}
        for row in rows:
            canonical,template=_reason_template(row.get('reason'),row.get('variants') or [],reg)
            extras=tuple(sorted((k,json.dumps(v,sort_keys=True,ensure_ascii=False)) for k,v in row.items() if k not in {'variants','reason'}))
            key=(canonical,extras)
            if canonical and key in index:
                target=groups[index[key]]
                merged=[]
                for vid in row['variants']:
                    if vid not in target['variants']: target['variants'].append(vid); merged.append(vid)
                target['reason']=_render_shared_reason(templates[key],target['variants'],reg)
                if merged: merges.append({'domain':domain,'bucket':bucket,'transform':'consolidate_parallel_variant_rows','merged_variants':merged,'into_variants':list(target['variants']),'resulting_reason':target['reason']})
            else:
                clone=dict(row); clone['variants']=list(row.get('variants') or [])
                if canonical: index[key]=len(groups); templates[key]=template
                groups.append(clone)
        doc[bucket]=groups
    return doc,merges

def stage_diagnosis(work,case,reg,eligible,manifest,profile):
    allowed=_allowed_diseases(work); genes=runtime.case_genes(case); bootstrap=list(case.get('bootstrap_cmcs') or []); tag_by_id=card_identity.tag_by_id(manifest)
    max_passes=int(_setting('diagnosis','who5','max_cmc_passes')); prior=list(bootstrap); history=list(bootstrap); who=None; who_cards=[]; authoritative=1
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

def stage_domain(work,domain,case,reg,diagnosis,eligible,manifest,profile):
    valid=set(reg); disease=diagnosis['who5']['schema_disease']; genes=runtime.case_genes(case); cards=_draw_domain_cards(eligible,domain,genes,[disease]); _log_ptbg_retrieval(work,eligible,domain,genes,disease,cards); tag_by_id=card_identity.tag_by_id(manifest)
    contract=domain_contract.contract(domain)
    out=_existing_or_new(work,f'{domain}_state','proforma.yaml')
    # The output contract is the final block of the prompt: recency matters
    # disproportionately for a low-active-parameter model.
    prompt=(_prompt(domain)
        +'\n\n# Variant registry\n```yaml\n'+model_context.registry_context(reg)+'```'
        +'\n\n# Structured case\n```json\n'+model_context.case_context(case,fields=model_context.DOMAIN_CASE_FIELDS)+'\n```'
        +'\n\n# Authoritative framework diagnoses\n```yaml\n'+model_context.diagnosis_context(diagnosis)+'```'
        +'\n\n# Candidate evidence cards\n'+_render_cards(cards,tag_by_id)
        +'\n\n'+domain_contract.skeleton(contract,sorted(reg),registry=reg,applicable_disease=disease))
    model_context.assert_canonical(prompt,source_ids=model_context.source_ids(reg))
    def validate_owner(text):
        normalized,_records=domain_contract.normalize_model_output(text,contract,reg,disease)
        return schema_validation.validate_domain(
            normalized,domain,valid,registry=reg,authoritative_disease=disease
        )
    _model_call(work,call_id=domain,role='ptbg',prompt=prompt,output=out,validator=validate_owner,profile=profile,proforma=True)
    normalized,identity_records=domain_contract.normalize_model_output(_read(out),contract,reg,disease)
    if identity_records:
        _log_transforms(work,[dict(record,stage=domain) for record in identity_records])
    _write(out,normalized)
    # The model returns the variant-centric owner form; Python projects it into
    # the stable bucketed internal artifact consumed downstream.
    flat=yaml.safe_load(normalized); doc=domain_contract.pivot(flat,contract)
    doc,merges=_consolidate_rows(domain,doc,reg); _log_transforms(work,merges)
    _write(out,yaml.safe_dump(doc,sort_keys=False,allow_unicode=True,width=110))
    _write(_artifact(work,f'{domain}_state','model-classification.yaml',new=False),yaml.safe_dump(flat,sort_keys=False,allow_unicode=True,width=110))
    return doc,cards

def _elements(diagnosis,domains,case):
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
                'required':False,'source':framework,
            })
    for bucket in domain_contract.contract('prognosis').buckets:
        if not _reportable('prognosis',bucket): continue
        for i,row in enumerate(prognosis.get(bucket) or [],1):
            els.append({'schema_id':f'PX-{bucket.upper()}-{i:02d}','domain':'prognosis','bucket':bucket,'statement':row['reason'],'reason':row['reason'],'variants':row['variants'],'evidence_domain':'prognosis','required':False,'source':row})
    for domain,prefix in (('treatment','TX'),('biomarker','MRD'),('germline','GL')):
        doc=domains[domain]
        for bucket in domain_contract.contract(domain).buckets:
            if not _reportable(domain,bucket): continue
            for i,row in enumerate(doc[bucket],1):
                els.append({'schema_id':f'{prefix}-{bucket.upper()}-{i:02d}','domain':domain,'bucket':bucket,'statement':row['reason'],'reason':row['reason'],'variants':row['variants'],'evidence_domain':domain,'required':False,'source':row})
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


def stage_evidence(work,elements,cards_by_domain,reg,manifest,profile,*,authoritative_disease=None):
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
            _prompt('evidence_match')+'\n\n# Evidence items with their deterministic candidate cards\n'
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
            aprompt=(_prompt('evidence_audit')+'\n\n# Selected reason/card sets\n```yaml\n'
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
    # report-sized clinical propositions.  The same function is used by the
    # native-self path via self_runtime.finalize_evidence().
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

def stage_report_write(work,blocks,case,reg,profile):
    path=_existing_or_new(work,'report_write','report-write.yaml'); prompt=_prompt('report_write')+'\n\n# Deterministic report blocks\n```yaml\n'+yaml.safe_dump({'blocks':blocks},sort_keys=False,allow_unicode=True,width=110)+'```\n\n# Variant registry — naming context only\n```yaml\n'+model_context.registry_context(reg)+'```\n'
    model_context.assert_canonical(prompt,source_ids=model_context.source_ids(reg))
    _model_call(work,call_id='report-write',role='report_write',prompt=prompt,output=path,validator=lambda t:schema_validation.validate_report_write(t,blocks),profile=profile,max_attempts=_retry('report_write_attempts'))
    rendered=yaml.safe_load(_read(path))['blocks']; amap={r['block_id']:r['text'] for r in rendered}
    apath=_existing_or_new(work,'report_write','report-preservation.yaml'); aprompt=_prompt('report_preservation')+'\n\n# Deterministic source blocks\n```yaml\n'+yaml.safe_dump({'blocks':blocks},sort_keys=False,allow_unicode=True,width=110)+'```\n\n# Rendered blocks\n```yaml\n'+yaml.safe_dump({'blocks':rendered},sort_keys=False,allow_unicode=True,width=110)+'```\n'
    try:
        _model_call(work,call_id='report-preservation',role='preservation_check',prompt=aprompt,output=apath,validator=lambda t:schema_validation.validate_preservation(t,blocks),profile=profile,max_attempts=_retry('preservation_attempts'))
        audits=yaml.safe_load(_read(apath))['audits']; audit_map={a['block_id']:a for a in audits}
    except StepFailure as exc:
        audit_map={b['block_id']:{'preserved':False,'issue':'Preservation audit unavailable: '+str(exc)} for b in blocks}
    final=[]
    for block in blocks:
        audit=audit_map[block['block_id']]; text=amap.get(block['block_id']) or _fallback_block_text(block)
        if not audit['preserved']:
            issue_key=f'report-preservation:{block["block_id"]}'; _semantic_dissent(work,issue_key=issue_key,stage='final preservation audit',reviewed_text=text,dissent_reason=audit.get('issue') or 'Rendered block did not preserve the deterministic source block.',action_recommended='Use the deterministic source-preserving fallback for this block.'); fallback=_fallback_block_text(block); _semantic_dissent_address(work,issue_key=issue_key,stage='deterministic report fallback',action='Replace the failed rendered block with its deterministic fallback.',outcome=fallback,status='resolved'); text=fallback
        tags=[]
        for comp in block['components']:
            for tag in comp.get('card_tags') or []:
                if tag not in tags: tags.append(tag)
        final.append({'block_id':block['block_id'],'domain':block['domain'],'text':runtime.ensure_sentence(text),'card_tags':tags})
    _write(_existing_or_new(work,'report_write','report-final-blocks.yaml'),yaml.safe_dump({'blocks':final},sort_keys=False,allow_unicode=True,width=110)); return final

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
    state=_load_run_state(work); mode=state.get('mode')
    if is_validation_mode(mode):
        case_id=state.get('validation_case'); package_marking_bundle(mode,case_id,Path(work)/'report-final.md')
    elif mode=='nel-demo':
        write_demo_marking_criteria_after_report(state.get('example'),report_path=Path(work)/'report-final.md',output_path=_artifact(work,'setup','demo-expected.md',new=True))

def run_pipeline(work,profile=None):
    _require_work(work); layout.ensure_dirs(work)
    _stage_status(work,'stage-1','Stage 1 of 9 — structure case'); case,reg=stage_structure(work,profile)
    _stage_status(work,'stage-2','Stage 2 of 9 — initialise corpus'); all_cards,eligible,digest,manifest=stage_corpus(work)
    _stage_status(work,'stage-3','Stage 3 of 9 — WHO5 / ICC / independent concurrent diagnosis'); diagnosis,cmcs,diagnosis_cards=stage_diagnosis(work,case,reg,eligible,manifest,profile)
    domains={}; cards_by_domain=dict(diagnosis_cards)
    for idx,domain in enumerate(('prognosis','treatment','biomarker','germline'),4):
        _stage_status(work,f'stage-{idx}',f'Stage {idx} of 9 — {domain} owner proforma'); domains[domain],cards_by_domain[domain]=stage_domain(work,domain,case,reg,diagnosis,eligible,manifest,profile)
    _stage_status(work,'stage-8','Stage 8 of 9 — evidence, reportability, deterministic blocks'); elements=_elements(diagnosis,domains,case); supported=stage_evidence(work,elements,cards_by_domain,reg,manifest,profile,authoritative_disease=diagnosis['who5']['schema_disease']); blocks=stage_blocks(work,diagnosis,supported,reg)
    _stage_status(work,'stage-9','Stage 9 of 9 — one report-writing call + preservation check'); final_blocks=stage_report_write(work,blocks,case,reg,profile); stage_final(work,case,final_blocks,supported,all_cards,digest,manifest); _print_usage(work); _stage_status(work,'complete','terraced-v6 complete'); return EXIT_OK

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
        raise StepFailure('no --work-dir given and no terraced-v6 runs exist')
    work=candidates[0]
    _status(f'using most recent run directory: {work}')
    return work

def build_parser():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='command',required=True)
    s=sub.add_parser('setup'); s.add_argument('--mode',required=True,choices=supported_modes()); s.add_argument('--case-file',type=Path); s.add_argument('--example',type=int); s.add_argument('--case-id'); s.add_argument('--work-dir',type=Path); s.add_argument('--pipeline',choices=pipeline_registry.names())
    cs=sub.add_parser('check-stage'); cs.add_argument('--stage',required=True,choices=stage_checks.names()); cs.add_argument('--file',type=Path,required=True); cs.add_argument('--context',type=Path)
    sp=sub.add_parser('show-prompt'); sp.add_argument('--stage',required=True,choices=stage_checks.names()); sp.add_argument('--context',type=Path)
    sub.add_parser('stages')
    sub.add_parser('pipelines'); pc=sub.add_parser('pipeline-check'); pc.add_argument('--pipeline',required=True,choices=pipeline_registry.names()); pp=sub.add_parser('pipeline-plan'); pp.add_argument('--pipeline',required=True,choices=pipeline_registry.names()); ps=sub.add_parser('pipeline'); ps.add_argument('pipeline_id',nargs='?',choices=pipeline_registry.names()); r=sub.add_parser('run'); r.add_argument('--work-dir',type=Path)
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
        if args.command in {'pipeline-check','pipeline-plan'}:
            plan=pipeline_registry.load(args.pipeline); print(f'PIPELINE={plan.pipeline_id}'); [print(x) for x in pipeline_registry.describe(plan)]; return EXIT_OK
        if args.command=='pipeline': return run_pipeline_setting(args.pipeline_id)
        if args.command=='run':
            work=_resolve_run_work_dir(args.work_dir)
            with _cli_logging(work): return run_pipeline(work)
        raise StepFailure(f'unknown command {args.command}')
    except Handoff as h:
        print(f'HANDOFF={h.call_id}'); print(f'PROMPT={h.prompt}'); print(f'OUTPUT={h.output}'); return EXIT_HANDOFF
    except Exception as exc:
        print(f'terraced-v6 failed: {exc}',file=sys.stderr); return EXIT_FAILURE

if __name__=='__main__': raise SystemExit(main())
