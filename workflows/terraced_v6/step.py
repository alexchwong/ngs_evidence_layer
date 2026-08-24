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
from validation.package_marking import package_marking_bundle
from validation import cases as validation_cases
from workflows.terraced_v6 import card_identity, layout, model_client, pipeline_registry, prompt_loader, rendering, runtime, schema_validation

WORKFLOW_ID='terraced-v6'; RUN_STATE_SCHEMA_VERSION=1; HERE=Path(__file__).resolve().parent; PROMPTS=HERE/'prompts'
SETTINGS_PATH=HERE/'settings.json'; SETTINGS_TEMPLATE_PATH=HERE/'settings.json.template'; USAGE_FILE='model-usage.json'
EXIT_OK=0; EXIT_FAILURE=1; EXIT_HANDOFF=10
VALIDATION_MODES={'nel-validate','nel-validate-function','nel-validate-brief'}
MARKING_PREFIX={'nel-validate':'nel-validation','nel-validate-function':'nel-validation-function','nel-validate-brief':'nel-validation-brief'}
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

_REPORTABILITY_DEFAULTS={
    'diagnosis':{'who5':True,'icc':True,'second_diagnosis':True},
    'prognosis':{'favorable':True,'adverse':True,'neutral':True,'uncertain':False,'prognostic_score':True},
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


def _validate_candidate(work,*,candidate,fmt,call_id,syntax_binding,validator,syntax_attempts):
    """Validate once, repairing only representation errors before content retry.

    All validators are expected to accumulate their issues.  If any issues are
    tagged ``serialization``, the shared v3 syntax-repair machinery receives only
    those representation defects and must preserve all lexical informational
    content.  Once representation defects are gone, a fresh full validation is
    run; any remaining issues are returned to the originating task together.
    """
    try:
        msg=validator(candidate)
        return candidate,msg
    except validated_model_task.ValidationFailure as exc:
        if not fmt or not _serialization_feedback(exc): raise
    try:
        result=syntax_repair.repair_schema_serialization(
            candidate,
            format_name=fmt,
            validator=validator,
            serialization_feedback=_serialization_feedback,
            model_repair=_syntax_callback(work,syntax_binding,call_id,syntax_attempts),
            model_attempts=syntax_attempts,
        )
        _archive_failed_syntax_attempts(work,call_id,result.model_attempts)
    except Handoff: raise
    except syntax_repair.SchemaSerializationRepairExhausted as exc:
        _archive_failed_syntax_attempts(work,call_id,exc.attempts)
        detail=(
            f'model operation {call_id} remained mis-serialized after {syntax_attempts} syntax-only '
            f'repair attempt(s): {exc.validation_error}'
        )
        raise SyntaxCycleExhausted(detail,feedback=exc.validation_error) from exc
    repaired=result.text
    # Re-run the complete validator.  If content/coverage defects remain they are
    # now reported all at once to the originating clinical/model task.
    msg=validator(repaired)
    return repaired,msg

def _standard_model_call(work,*,call_id,role,prompt,output,validator,profile=None,fmt='yaml',fatal=True,max_attempts=None,feedback=None,system_prompt=None):
    binding=_profile(work,profile,role); syntax_binding=_profile(work,profile,'syntax_repair'); root=layout.model_step_dir(work,call_id,existing=False)
    messages=[{'role':'system','content':system_prompt or model_client.SYSTEM_PROMPT},{'role':'user','content':prompt}]
    attempts=int(max_attempts if max_attempts is not None else _retry('fatal_model_attempts')); previous=None; last_error=feedback or ''
    # Syntax repair has its own global cap. It must never silently inherit
    # the larger clinical/fatal retry budget.
    syntax_attempts=_retry('syntax_repair_attempts')
    self_count_path=root/'self-attempt-count.json'
    self_count=0
    if self_count_path.is_file():
        try: self_count=int(json.loads(_read(self_count_path)).get('attempts',0))
        except Exception: self_count=0
    if output.is_file():
        try:
            candidate=_prepare_structured(work,_read(output),fmt,call_id,syntax_binding,syntax_attempts=syntax_attempts); candidate,msg=_validate_candidate(work,candidate=candidate,fmt=fmt,call_id=call_id,syntax_binding=syntax_binding,validator=validator,syntax_attempts=syntax_attempts); _write(output,candidate); _write(root/'accepted-output.txt',candidate); _write(root/'validated.txt',msg+'\n'); return candidate
        except Handoff: raise
        except StepFailure: raise
        except Exception as exc:
            previous=_read(output); last_error=validated_model_task.retry_instruction(exc)
            if binding.is_self:
                self_count += 1
                _write(self_count_path,json.dumps({'attempts':self_count},indent=2)+'\n')
                _write(layout.errors(work)/f'{call_id}-self-attempt-{self_count:02d}.txt',previous+'\n\nVALIDATION:\n'+last_error+'\n')
                if self_count >= attempts:
                    raise StepFailure(f'model operation {call_id} failed validation after {attempts} self-model attempts: {last_error}')
            else:
                err=layout.errors(work)/f'{call_id}-resume-invalid.txt'; _write(err,previous+'\n\nVALIDATION:\n'+last_error+'\n')
    if binding.is_self:
        call_messages=list(messages)
        if previous is not None: call_messages += [{'role':'assistant','content':previous},{'role':'user','content':last_error}]
        _write(root/'messages.json',json.dumps(call_messages,indent=2,ensure_ascii=False)+'\n'); _write(root/'prompt.md',_render_bundle(call_id,call_messages,output,last_error or None))
        raise Handoff(call_id,root/'prompt.md',output)
    for attempt in range(1,attempts+1):
        _status(f'  {call_id}: answering' if attempt==1 else f'  {call_id}: retry {attempt}/{attempts}')
        call_messages=list(messages)
        if previous is not None: call_messages += [{'role':'assistant','content':previous},{'role':'user','content':last_error}]
        _write(root/'messages.json',json.dumps(call_messages,indent=2,ensure_ascii=False)+'\n'); _write(root/'prompt.md',_render_bundle(call_id,call_messages,output,last_error or None))
        try: comp=model_client.complete_messages(binding,call_messages)
        except model_client.TruncatedCompletion as exc:
            _record_usage(work,call_id,binding.model,attempt,exc.usage,role=role)
            raw=exc.content; previous=raw; last_error=f'Output truncated at max_tokens={exc.max_tokens}; return the complete requested artifact.'; continue
        except RuntimeError as exc: raise StepFailure(str(exc)) from exc
        if isinstance(comp,model_client.Completion): raw=comp.content; usage=comp.usage
        else: raw=comp; usage=None
        _record_usage(work,call_id,binding.model,attempt,usage,role=role)
        try:
            candidate=_prepare_structured(work,raw,fmt,call_id,syntax_binding,syntax_attempts=syntax_attempts); candidate,msg=_validate_candidate(work,candidate=candidate,fmt=fmt,call_id=call_id,syntax_binding=syntax_binding,validator=validator,syntax_attempts=syntax_attempts)
        except Handoff: raise
        except StepFailure: raise
        except Exception as exc:
            previous=raw; last_error=validated_model_task.retry_instruction(exc)
            _write(layout.errors(work)/f'{call_id}-attempt-{attempt:02d}.txt',raw.rstrip()+'\n\nVALIDATION:\n'+last_error+'\n')
            continue
        _write(output,candidate); _write(root/'accepted-output.txt',candidate); _write(root/'validated.txt',msg+'\n'); return candidate
    raise StepFailure(f'model operation {call_id} failed validation after {attempts} attempts: {last_error}')


def _proforma_restart_feedback(call_id,syntax_attempts,detail):
    return (
        f'The previous complete {call_id} proforma could not be made structurally valid after '
        f'{syntax_attempts} syntax-only repair attempts. Regenerate the complete proforma from scratch '
        'from the original task and supplied context. Do not copy, patch, or troubleshoot the previous '
        'artifact. Follow the proforma shape exactly. The structural problem that defeated syntax repair was:\n\n'
        + str(detail).strip()
    )


def _proforma_active_id(call_id,rewrite_index):
    return call_id if rewrite_index==0 else f'{call_id}-rewrite-{rewrite_index:02d}'


def _proforma_status(call_id,rewrite_index,max_rewrites,mode):
    if rewrite_index==0:
        _status(f'  {call_id}: proforma attempt 1/{max_rewrites+1}')
        return
    suffix=' from scratch after syntax exhaustion' if mode=='fresh' else ' using deterministic validation feedback'
    _status(f'  {call_id}: proforma rewrite {rewrite_index}/{max_rewrites}{suffix}')


def _proforma_model_call(work,*,call_id,role,prompt,output,validator,profile=None,fmt='yaml',feedback=None,system_prompt=None,max_rewrites=None):
    """Run a clinical proforma with nested syntax and full-proforma retry budgets.

    One proforma generation may use at most ``syntax_repair_attempts`` syntax-only
    repairs.  If that budget is exhausted, the damaged artifact is abandoned and
    the original proforma task is run again from scratch.  Full proforma rewrites
    have a separate cap and never inherit the old generic 10-attempt fatal budget.
    """
    syntax_attempts=_retry('syntax_repair_attempts'); max_rewrites=int(_retry('proforma_rewrite_attempts') if max_rewrites is None else max_rewrites)
    binding=_profile(work,profile,role); syntax_binding=_profile(work,profile,'syntax_repair')
    base_messages=[{'role':'system','content':system_prompt or model_client.SYSTEM_PROMPT},{'role':'user','content':prompt}]

    # Self handoffs persist the outer rewrite state because each model response
    # arrives on a later CLI invocation.
    if binding.is_self:
        state=_retry_entry(work,call_id); rewrite_index=int(state.get('rewrites',0)); mode=state.get('mode') or 'initial'; restart_feedback=state.get('feedback') or feedback or ''; previous=state.get('previous')
        active_id=_proforma_active_id(call_id,rewrite_index); root=layout.model_step_dir(work,active_id,existing=False)
        if output.is_file():
            raw=_read(output)
            try:
                candidate=_prepare_structured(work,raw,fmt,active_id,syntax_binding,syntax_attempts=syntax_attempts)
                candidate,msg=_validate_candidate(work,candidate=candidate,fmt=fmt,call_id=active_id,syntax_binding=syntax_binding,validator=validator,syntax_attempts=syntax_attempts)
            except Handoff: raise
            except SyntaxCycleExhausted as exc:
                _write(layout.errors(work)/f'{active_id}-proforma-invalid.txt',raw.rstrip()+'\n\nSYNTAX_REPAIR_EXHAUSTED:\n'+str(exc)+'\n')
                if rewrite_index>=max_rewrites:
                    raise StepFailure(f'model operation {call_id} exhausted {syntax_attempts} syntax repairs on the initial proforma plus {max_rewrites} full proforma rewrite(s): {exc}') from exc
                rewrite_index+=1; mode='fresh'; restart_feedback=_proforma_restart_feedback(call_id,syntax_attempts,exc.feedback); previous=None; output.unlink(missing_ok=True)
                _set_retry_entry(work,call_id,{'rewrites':rewrite_index,'mode':mode,'feedback':restart_feedback,'previous':None})
                active_id=_proforma_active_id(call_id,rewrite_index); root=layout.model_step_dir(work,active_id,existing=False)
            except Exception as exc:
                last_error=validated_model_task.retry_instruction(exc)
                _write(layout.errors(work)/f'{active_id}-proforma-invalid.txt',raw.rstrip()+'\n\nVALIDATION:\n'+last_error+'\n')
                if rewrite_index>=max_rewrites:
                    raise StepFailure(f'model operation {call_id} failed after the initial proforma plus {max_rewrites} full proforma rewrite(s): {last_error}') from exc
                rewrite_index+=1; mode='repair'; restart_feedback=last_error; previous=raw; output.unlink(missing_ok=True)
                _set_retry_entry(work,call_id,{'rewrites':rewrite_index,'mode':mode,'feedback':restart_feedback,'previous':previous})
                active_id=_proforma_active_id(call_id,rewrite_index); root=layout.model_step_dir(work,active_id,existing=False)
            else:
                _write(output,candidate); _write(root/'accepted-output.txt',candidate); _write(root/'validated.txt',msg+'\n'); _set_retry_entry(work,call_id,{})
                return candidate

        call_messages=list(base_messages)
        if rewrite_index>0 and mode=='fresh':
            call_messages += [{'role':'user','content':restart_feedback}]
        elif rewrite_index>0 and mode=='repair':
            call_messages += [{'role':'assistant','content':previous or ''},{'role':'user','content':restart_feedback}]
        elif feedback:
            call_messages += [{'role':'user','content':feedback}]
        _proforma_status(call_id,rewrite_index,max_rewrites,mode)
        _write(root/'messages.json',json.dumps(call_messages,indent=2,ensure_ascii=False)+'\n'); _write(root/'prompt.md',_render_bundle(active_id,call_messages,output,restart_feedback if rewrite_index else feedback))
        raise Handoff(active_id,root/'prompt.md',output)

    previous=None; mode='initial'; restart_feedback=feedback or ''; start_index=0
    if output.is_file():
        raw=_read(output)
        try:
            candidate=_prepare_structured(work,raw,fmt,call_id,syntax_binding,syntax_attempts=syntax_attempts)
            candidate,msg=_validate_candidate(work,candidate=candidate,fmt=fmt,call_id=call_id,syntax_binding=syntax_binding,validator=validator,syntax_attempts=syntax_attempts)
        except SyntaxCycleExhausted as exc:
            _write(layout.errors(work)/f'{call_id}-resume-proforma-invalid.txt',raw.rstrip()+'\n\nSYNTAX_REPAIR_EXHAUSTED:\n'+str(exc)+'\n')
            mode='fresh'; restart_feedback=_proforma_restart_feedback(call_id,syntax_attempts,exc.feedback); start_index=1
        except Exception as exc:
            previous=raw; mode='repair'; restart_feedback=validated_model_task.retry_instruction(exc); start_index=1
            _write(layout.errors(work)/f'{call_id}-resume-proforma-invalid.txt',raw.rstrip()+'\n\nVALIDATION:\n'+restart_feedback+'\n')
        else:
            root=layout.model_step_dir(work,call_id,existing=False); _write(output,candidate); _write(root/'accepted-output.txt',candidate); _write(root/'validated.txt',msg+'\n'); return candidate
    for rewrite_index in range(start_index,max_rewrites+1):
        active_id=_proforma_active_id(call_id,rewrite_index); root=layout.model_step_dir(work,active_id,existing=False)
        _proforma_status(call_id,rewrite_index,max_rewrites,mode)
        call_messages=list(base_messages)
        if rewrite_index>0 and mode=='fresh': call_messages += [{'role':'user','content':restart_feedback}]
        elif rewrite_index>0 and mode=='repair': call_messages += [{'role':'assistant','content':previous or ''},{'role':'user','content':restart_feedback}]
        elif feedback: call_messages += [{'role':'user','content':feedback}]
        _write(root/'messages.json',json.dumps(call_messages,indent=2,ensure_ascii=False)+'\n'); _write(root/'prompt.md',_render_bundle(active_id,call_messages,output,restart_feedback if rewrite_index else feedback))
        try: comp=model_client.complete_messages(binding,call_messages)
        except model_client.TruncatedCompletion as exc:
            _record_usage(work,active_id,binding.model,rewrite_index+1,exc.usage,role=role); previous=None; mode='fresh'; restart_feedback=f'Previous full proforma was truncated at max_tokens={exc.max_tokens}. Regenerate the complete proforma from scratch.'
            _write(layout.errors(work)/f'{active_id}-truncated.txt',exc.content.rstrip()+'\n\nVALIDATION:\n'+restart_feedback+'\n'); continue
        except RuntimeError as exc: raise StepFailure(str(exc)) from exc
        if isinstance(comp,model_client.Completion): raw=comp.content; usage=comp.usage
        else: raw=comp; usage=None
        _record_usage(work,active_id,binding.model,rewrite_index+1,usage,role=role)
        try:
            candidate=_prepare_structured(work,raw,fmt,active_id,syntax_binding,syntax_attempts=syntax_attempts)
            candidate,msg=_validate_candidate(work,candidate=candidate,fmt=fmt,call_id=active_id,syntax_binding=syntax_binding,validator=validator,syntax_attempts=syntax_attempts)
        except Handoff: raise
        except SyntaxCycleExhausted as exc:
            _write(layout.errors(work)/f'{active_id}-proforma-invalid.txt',raw.rstrip()+'\n\nSYNTAX_REPAIR_EXHAUSTED:\n'+str(exc)+'\n')
            previous=None; mode='fresh'; restart_feedback=_proforma_restart_feedback(call_id,syntax_attempts,exc.feedback); continue
        except Exception as exc:
            previous=raw; mode='repair'; restart_feedback=validated_model_task.retry_instruction(exc)
            _write(layout.errors(work)/f'{active_id}-proforma-invalid.txt',raw.rstrip()+'\n\nVALIDATION:\n'+restart_feedback+'\n'); continue
        _write(output,candidate); _write(root/'accepted-output.txt',candidate); _write(root/'validated.txt',msg+'\n'); return candidate
    raise StepFailure(f'model operation {call_id} failed after the initial proforma plus {max_rewrites} full proforma rewrite(s): {restart_feedback}')


def _model_call(work,*,call_id,role,prompt,output,validator,profile=None,fmt='yaml',fatal=True,max_attempts=None,feedback=None,system_prompt=None,proforma=False,max_rewrites=None):
    if proforma:
        return _proforma_model_call(work,call_id=call_id,role=role,prompt=prompt,output=output,validator=validator,profile=profile,fmt=fmt,feedback=feedback,system_prompt=system_prompt,max_rewrites=max_rewrites)
    return _standard_model_call(work,call_id=call_id,role=role,prompt=prompt,output=output,validator=validator,profile=profile,fmt=fmt,fatal=fatal,max_attempts=max_attempts,feedback=feedback,system_prompt=system_prompt)

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
    work,demo_case,demo_expected=setup_workflow(workflow=WORKFLOW_ID,mode=args.mode,work_dir=work_arg,project=False,example=args.example,case_id=args.case_id)
    write_workflow_state(work,WORKFLOW_ID,args.mode,model_profile=plan.pipeline_id)
    case_path=layout.input(work,'case.md',existing=False)
    if args.case_file: shutil.copyfile(args.case_file.expanduser().resolve(),case_path)
    elif args.mode=='nel-demo' and demo_case: shutil.copyfile(demo_case,case_path)
    if not case_path.is_file() or not _read(case_path).strip(): raise StepFailure(f'case.md missing or empty: {case_path}')
    if demo_expected: shutil.copyfile(demo_expected,_artifact(work,'setup','demo-expected.md',new=True))
    _save_run_state(work,{'schema_version':1,'workflow_id':WORKFLOW_ID,'mode':args.mode,'validation_case':args.case_id,'pipeline':plan.pipeline_id,'created_at':datetime.now(timezone.utc).isoformat()})
    with _cli_logging(work): print(work); print(f'PIPELINE={plan.pipeline_id}')
    return EXIT_OK

def _require_work(work):
    state=read_workflow_state(work)
    if state.get('workflow_id')!=WORKFLOW_ID: raise StepFailure(f'work directory is bound to {state.get("workflow_id")!r}, not {WORKFLOW_ID!r}')
    _load_run_state(work)

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
    prompt=_prompt('structure_case')+'\n\n# Authoritative case\n'+_read(layout.input(work,'case.md'))+'\n\n# Allowed bootstrap CMCs\n'+_read(layout.setup(work,'case-major-categories.json'))+'\n\n# Assay scope\n'+_read(layout.setup(work,'ngs-panel-scope.md'))
    _model_call(work,call_id='structure-case',role='structure',prompt=prompt,output=out,validator=runtime.validate_case_text,profile=profile,fmt='json')
    case=runtime.normalize_case_variant_descriptions(runtime.read_json(out))
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

def _render_cards(cards):
    if not cards: return 'No candidate cards.'
    blocks=[]
    for c in cards:
        lines=[f'### {c.get("card_id")}',f'category: {c.get("category")}',f'genes: {", ".join(c.get("genes") or []) or "none"}',f'diseases: {", ".join(c.get("diseases") or []) or "none"}',f'evidence_tier: {c.get("evidence_tier") or "unspecified"}',f'interpretation: {c.get("interpretation") or ""}',f'source_hint: {c.get("paper_nickname") or c.get("citation_display") or ""}']
        if _closed_gene_set(c): lines.insert(4,'closed_gene_set: true')
        blocks.append('\n'.join(lines))
    return '\n\n'.join(blocks)

def _finite_membership_context(reg,cards):
    out={}
    for card in cards:
        closed=_closed_gene_set(card); cid=card.get('card_id')
        if closed and cid:
            out[cid]={'qualifying':[vid for vid,row in reg.items() if row.get('gene') in closed],'not_qualifying':[vid for vid,row in reg.items() if row.get('gene') not in closed]}
    return {'finite_gene_set_membership':out} if out else {}

def _draw_diagnosis_cards(eligible,genes,cmcs):
    hits=[]; wanted=set(genes)
    for c in eligible:
        if c.get('category')!='diagnosis': continue
        if core_retrieval.match_genes(c,wanted) or core_retrieval._matches_case_major_category(c,cmcs): hits.append(c)
    return sorted(hits,key=lambda x:x.get('card_id') or '')

def _diagnosis_authority_publications(authority):
    return set((_setting('diagnosis',authority).get('publication_keys') or []))

def _filter_diagnosis_authority(cards,authority):
    keys=_diagnosis_authority_publications(authority)
    return [c for c in cards if c.get('publication_key') in keys] if keys else list(cards)

def _disease_match(card,diseases,category):
    for disease in diseases:
        allowed={disease,*runtime.vocab.retrieval_related_diseases(disease,category)}
        if set(card.get('diseases') or []) & allowed: return True
    return False

def _draw_domain_cards(eligible,domain,genes,diseases):
    category=str(_setting('ptbg','domains',domain,'card_category')); wanted=set(genes); hits=[]
    for c in eligible:
        if c.get('category')!=category: continue
        mg=core_retrieval.match_genes(c,wanted)
        if domain=='germline':
            if mg: hits.append(c)
        elif _disease_match(c,diseases,category) and (mg or not c.get('genes')): hits.append(c)
    return sorted(hits,key=lambda x:x.get('card_id') or '')

def _allowed_diseases(work):
    return set(runtime.read_json(layout.setup(work,'allowed-schema-diseases.json'))['allowed_schema_diseases'])

def _variant_context(reg): return yaml.safe_dump({'variants':reg},sort_keys=False,allow_unicode=True,width=110)

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
    buckets={
      'prognosis':('favorable','adverse','neutral','uncertain'),
      'treatment':('drug_target','drug_sensitive','drug_resistant','no_drug_implication'),
      'biomarker':('mrd_marker','not_mrd_marker'),
      'germline':('germline_support','germline_against','germline_uncertain'),
    }[domain]
    for bucket in buckets:
        rows=doc.get(bucket) or []; groups=[]; index={}; templates={}
        for row in rows:
            canonical,template=_reason_template(row.get('reason'),row.get('variants') or [],reg)
            extras=tuple(sorted((k,json.dumps(v,sort_keys=True,ensure_ascii=False)) for k,v in row.items() if k not in {'variants','reason'}))
            key=(canonical,extras)
            if canonical and key in index:
                target=groups[index[key]]
                for vid in row['variants']:
                    if vid not in target['variants']: target['variants'].append(vid)
                target['reason']=_render_shared_reason(templates[key],target['variants'],reg)
            else:
                clone=dict(row); clone['variants']=list(row.get('variants') or [])
                if canonical: index[key]=len(groups); templates[key]=template
                groups.append(clone)
        doc[bucket]=groups
    return doc

def stage_diagnosis(work,case,reg,eligible,profile):
    allowed=_allowed_diseases(work); genes=runtime.case_genes(case); bootstrap=list(case.get('bootstrap_cmcs') or [])
    max_passes=int(_setting('diagnosis','who5','max_cmc_passes')); prior=list(bootstrap); history=list(bootstrap); who=None; who_cards=[]; authoritative=1
    for idx in range(1,max_passes+1):
        who_cards=_filter_diagnosis_authority(_draw_diagnosis_cards(eligible,genes,history),'who5')
        out=_artifact(work,f'diagnosis_who5_pass_{idx}','who5.yaml',new=True)
        prompt=_prompt('diagnosis_who5')+f'\n\n# Starting morphologic diagnosis\n{case.get("provisional_disease")}\n\n# Structured case\n```json\n'+json.dumps(case,indent=2,ensure_ascii=False)+'\n```\n\n# Deterministic finite-set context\n```yaml\n'+yaml.safe_dump(_finite_membership_context(reg,who_cards),sort_keys=False,allow_unicode=True,width=110)+'```\n\n# Allowed schema diseases\n'+yaml.safe_dump(sorted(allowed))+'\n# WHO5 authority cards\n'+_render_cards(who_cards)
        _model_call(work,call_id=f'diagnosis-who5-pass-{idx:02d}',role='diagnosis',prompt=prompt,output=out,validator=lambda t:schema_validation.validate_who5_diagnosis(t,allowed_diseases=allowed,valid_variants=set(reg)),profile=profile,proforma=True)
        who=yaml.safe_load(_read(out)); runtime.validate_no_false_missing_case_claims(who,case,domain='WHO5 diagnosis'); cmcs=runtime.derive_cmcs(who); authoritative=idx
        if cmcs==prior: break
        for cmc in cmcs:
            if cmc not in history: history.append(cmc)
        prior=cmcs
    final_cmcs=runtime.derive_cmcs(who)
    for cmc in final_cmcs:
        if cmc not in history: history.append(cmc)

    icc_cards=_filter_diagnosis_authority(_draw_diagnosis_cards(eligible,genes,history),'icc'); icc_out=_existing_or_new(work,'diagnosis_icc','icc.yaml')
    iprompt=_prompt('diagnosis_icc')+'\n\n# Starting morphologic diagnosis\n'+str(case.get('provisional_disease'))+'\n\n# Structured case\n```json\n'+json.dumps(case,indent=2,ensure_ascii=False)+'\n```\n\n# WHO5 result — context only\n```yaml\n'+yaml.safe_dump(who,sort_keys=False,allow_unicode=True,width=110)+'```\n\n# Deterministic finite-set context\n```yaml\n'+yaml.safe_dump(_finite_membership_context(reg,icc_cards),sort_keys=False,allow_unicode=True,width=110)+'```\n\n# ICC authority cards\n'+_render_cards(icc_cards)
    _model_call(work,call_id='diagnosis-icc',role='diagnosis',prompt=iprompt,output=icc_out,validator=lambda t:schema_validation.validate_icc_diagnosis(t,valid_variants=set(reg)),profile=profile,proforma=True)
    icc=yaml.safe_load(_read(icc_out)); runtime.validate_no_false_missing_case_claims(icc,case,domain='ICC diagnosis')

    other_cards=_draw_diagnosis_cards(eligible,genes,history); other_out=_existing_or_new(work,'diagnosis_other','other.yaml')
    oprompt=_prompt('diagnosis_other')+'\n\n# Structured case\n```json\n'+json.dumps(case,indent=2,ensure_ascii=False)+'\n```\n\n# Primary framework diagnoses\n```yaml\n'+yaml.safe_dump({'who5':who,'icc':icc},sort_keys=False,allow_unicode=True,width=110)+'```\n\n# Candidate diagnosis cards\n'+_render_cards(other_cards)
    _model_call(work,call_id='diagnosis-other',role='diagnosis',prompt=oprompt,output=other_out,validator=lambda t:schema_validation.validate_second_diagnosis(t,valid_variants=set(reg)),profile=profile,proforma=True)
    other=yaml.safe_load(_read(other_out)); runtime.validate_no_false_missing_case_claims(other,case,domain='second diagnosis')
    relationship='same' if runtime.normalize_dx(who['diagnosis'])==runtime.normalize_dx(icc['diagnosis']) else 'different'
    diagnosis={'who5':who,'icc':icc,'second_diagnosis':other,'relationship':relationship}
    _write(_existing_or_new(work,'diagnosis','diagnosis-final.yaml'),yaml.safe_dump(diagnosis,sort_keys=False,allow_unicode=True,width=110))
    _write(_existing_or_new(work,'diagnosis','routing.json'),json.dumps({'bootstrap_cmcs':bootstrap,'who5_authoritative_pass':authoritative,'final_cmcs':final_cmcs,'diagnostic_cmc_history':history},indent=2)+'\n')
    return diagnosis,final_cmcs,{'diagnosis_who5':who_cards,'diagnosis_icc':icc_cards,'diagnosis_other':other_cards}

def stage_domain(work,domain,case,reg,diagnosis,eligible,profile):
    valid=set(reg); disease=diagnosis['who5']['schema_disease']; cards=_draw_domain_cards(eligible,domain,runtime.case_genes(case),[disease])
    validator={'prognosis':schema_validation.validate_prognosis,'treatment':schema_validation.validate_treatment,'biomarker':schema_validation.validate_biomarker,'germline':schema_validation.validate_germline}[domain]
    out=_existing_or_new(work,f'{domain}_state','proforma.yaml')
    prompt=_prompt(domain)+'\n\n# Variant registry\n```yaml\n'+_variant_context(reg)+'```\n\n# Structured case\n```json\n'+json.dumps(case,indent=2,ensure_ascii=False)+'\n```\n\n# Authoritative framework diagnoses\n```yaml\n'+yaml.safe_dump(diagnosis,sort_keys=False,allow_unicode=True,width=110)+'```\n\n# Candidate evidence cards\n'+_render_cards(cards)
    _model_call(work,call_id=domain,role='ptbg',prompt=prompt,output=out,validator=lambda t:validator(t,valid),profile=profile,proforma=True)
    doc=yaml.safe_load(_read(out)); runtime.validate_no_false_missing_case_claims(doc,case,domain=domain); doc=_consolidate_rows(domain,doc,reg); _write(out,yaml.safe_dump(doc,sort_keys=False,allow_unicode=True,width=110))
    return doc,cards

def _elements(diagnosis,domains):
    els=[]
    if _reportable('diagnosis','who5'):
        w=diagnosis['who5']; els.append({'schema_id':'DX-WHO5','domain':'diagnosis','bucket':'who5','statement':f'WHO5 classification: {w["diagnosis"]}.','reason':w['reason'],'variants':w['variants'],'evidence_domain':'diagnosis_who5','required':True,'source':w})
    if _reportable('diagnosis','icc'):
        r=diagnosis['icc']; els.append({'schema_id':'DX-ICC','domain':'diagnosis','bucket':'icc','statement':f'ICC classification: {r["diagnosis"]}.','reason':r['reason'],'variants':r['variants'],'evidence_domain':'diagnosis_icc','required':True,'source':r})
    sec=diagnosis['second_diagnosis']
    if _reportable('diagnosis','second_diagnosis') and sec.get('diagnosis'):
        els.append({'schema_id':'DX-SECOND','domain':'diagnosis','bucket':'second_diagnosis','statement':sec['diagnosis'],'reason':sec['reason'],'variants':sec['variants'],'evidence_domain':'diagnosis_other','required':False,'source':sec})
    p=domains['prognosis']
    for bucket in ('favorable','adverse','neutral','uncertain'):
        if not _reportable('prognosis',bucket): continue
        for i,row in enumerate(p[bucket],1): els.append({'schema_id':f'PX-{bucket.upper()}-{i:02d}','domain':'prognosis','bucket':bucket,'statement':row['reason'],'reason':row['reason'],'variants':row['variants'],'evidence_domain':'prognosis','required':False,'source':row})
    score=p.get('prognostic_score')
    if score and _reportable('prognosis','prognostic_score'):
        els.append({'schema_id':'PX-SCORE','domain':'prognosis','bucket':'prognostic_score','statement':f'{score["name"]}: {score["result"]}.','reason':score['reason'],'variants':[],'evidence_domain':'prognosis','required':False,'source':score})
    t=domains['treatment']
    for bucket in ('drug_target','drug_sensitive','drug_resistant','no_drug_implication'):
        if not _reportable('treatment',bucket): continue
        for i,row in enumerate(t[bucket],1): els.append({'schema_id':f'TX-{bucket.upper()}-{i:02d}','domain':'treatment','bucket':bucket,'statement':row['reason'],'reason':row['reason'],'variants':row['variants'],'evidence_domain':'treatment','required':False,'source':row})
    b=domains['biomarker']
    for bucket in ('mrd_marker','not_mrd_marker'):
        if not _reportable('biomarker',bucket): continue
        for i,row in enumerate(b[bucket],1): els.append({'schema_id':f'MRD-{bucket.upper()}-{i:02d}','domain':'biomarker','bucket':bucket,'statement':row['reason'],'reason':row['reason'],'variants':row['variants'],'evidence_domain':'biomarker','required':False,'source':row})
    g=domains['germline']
    for bucket in ('germline_support','germline_against','germline_uncertain'):
        if not _reportable('germline',bucket): continue
        for i,row in enumerate(g[bucket],1): els.append({'schema_id':f'GL-{bucket.upper()}-{i:02d}','domain':'germline','bucket':bucket,'statement':row['reason'],'reason':row['reason'],'variants':row['variants'],'evidence_domain':'germline','required':False,'source':row})
    return els

def _candidate_cards(el,cards_by_domain,reg):
    cards=list(cards_by_domain.get(el['evidence_domain']) or []); genes={reg[v]['gene'] for v in el.get('variants') or [] if v in reg}
    if genes:
        subset=[c for c in cards if not c.get('genes') or genes & set(c.get('genes') or [])]
        if subset: cards=subset
    return cards

def _card_view(card): return {'card_id':card.get('card_id'),'category':card.get('category'),'genes':card.get('genes') or [],'diseases':card.get('diseases') or [],'evidence_tier':card.get('evidence_tier'),'interpretation':card.get('interpretation') or '','source_hint':card.get('paper_nickname') or card.get('citation_display') or ''}

def stage_evidence(work,elements,cards_by_domain,reg,manifest,profile):
    tag_by_id=card_identity.tag_by_id(manifest); catalog={}; items=[]; enriched=[dict(el,evidence=None) for el in elements]
    for idx,el in enumerate(elements,1):
        candidates=_candidate_cards(el,cards_by_domain,reg)
        if not candidates:
            issue=f'evidence:{el["schema_id"]}'
            _semantic_dissent(work,issue_key=issue,stage='evidence selection',reviewed_text=el['statement'],dissent_reason='No candidate evidence card was available for this reportable proposition.',action_recommended='Suppress optional proposition; fail closed for a primary framework diagnosis.')
            if el['required']:
                _semantic_dissent_address(work,issue_key=issue,stage='evidence resolution',action='Fail closed because a primary diagnosis lacks candidate evidence.',outcome='Final report generation stopped.',status='retained_with_dissent')
                raise StepFailure(f'{el["schema_id"]}: primary diagnosis has no candidate evidence cards')
            continue
        eid=f'E{len(items)+1:04d}'
        for c in candidates: catalog[c['card_id']]=c
        items.append({'evidence_id':eid,'element_index':idx-1,'schema_id':el['schema_id'],'statement':el['statement'],'reason':el['reason'],'candidate_card_ids':[c['card_id'] for c in candidates]})
    if not items:
        return [x for x in enriched if x['required']]
    public=[{k:item[k] for k in ('evidence_id','schema_id','statement','reason','candidate_card_ids')} for item in items]
    cards=[_card_view(catalog[cid]) for cid in dict.fromkeys(cid for item in items for cid in item['candidate_card_ids'])]
    mpath=_existing_or_new(work,'evidence_matches','batch-match.yaml'); mprompt=_prompt('evidence_match')+'\n\n# Evidence items\n```yaml\n'+yaml.safe_dump({'items':public},sort_keys=False,allow_unicode=True,width=110)+'```\n\n# Candidate card catalog\n```yaml\n'+yaml.safe_dump({'cards':cards},sort_keys=False,allow_unicode=True,width=110)+'```\n'
    _model_call(work,call_id='evidence-match-batch',role='evidence_match',prompt=mprompt,output=mpath,validator=lambda t:schema_validation.validate_evidence_match_batch(t,items),profile=profile,fatal=False,max_attempts=_retry('evidence_match_model_attempts'))
    matches=yaml.safe_load(_read(mpath))['matches']; mmap={m['evidence_id']:m for m in matches}
    audit_rows=[]
    for item in items:
        m=mmap[item['evidence_id']]; audit_rows.append({'evidence_id':item['evidence_id'],'schema_id':item['schema_id'],'statement':item['statement'],'reason':item['reason'],'source':m['source'],'quote':m['quote'],'selected_card':_card_view(catalog[m['card_id']])})
    apath=_existing_or_new(work,'evidence_audits','batch-audit.yaml'); aprompt=_prompt('evidence_audit')+'\n\n# Selected evidence pairs\n```yaml\n'+yaml.safe_dump({'items':audit_rows},sort_keys=False,allow_unicode=True,width=110)+'```\n'
    _model_call(work,call_id='evidence-audit-batch',role='evidence_audit',prompt=aprompt,output=apath,validator=lambda t:schema_validation.validate_evidence_audit_batch(t,items),profile=profile,fatal=False,max_attempts=_retry('evidence_audit_model_attempts'))
    audits=yaml.safe_load(_read(apath))['audits']; amap={a['evidence_id']:a for a in audits}; keep=[]
    for item in items:
        el=enriched[item['element_index']]; m=mmap[item['evidence_id']]; a=amap[item['evidence_id']]; ok=bool(a['quote_supports_statement'] and a['quote_supports_reason'])
        if not ok:
            issue=f'evidence:{el["schema_id"]}'; comments=a.get('comments') or ['Selected evidence did not support the proposition and reason.']
            _semantic_dissent(work,issue_key=issue,stage='evidence audit',reviewed_text='Statement: '+el['statement']+'\nReason: '+el['reason'],dissent_reason=comments,action_recommended='Suppress optional proposition; fail closed for a primary framework diagnosis.')
            if el['required']:
                _semantic_dissent_address(work,issue_key=issue,stage='evidence resolution',action='Fail closed because primary diagnosis evidence did not pass.',outcome='Final report generation stopped.',status='retained_with_dissent')
                raise StepFailure(f'{el["schema_id"]}: primary diagnosis evidence unsupported: {"; ".join(comments)}')
            _semantic_dissent_address(work,issue_key=issue,stage='evidence resolution',action='Suppress this optional proposition from report construction.',outcome='The optional proposition was excluded from the report.',status='resolved')
            continue
        if a.get('risk')=='warning':
            issue=f'evidence-warning:{el["schema_id"]}'; _semantic_dissent(work,issue_key=issue,stage='evidence audit',reviewed_text=el['statement'],dissent_reason=a.get('comments') or ['Evidence fidelity/context warning.'],action_recommended='Retain the supported proposition with dissent visible for review.'); _semantic_dissent_address(work,issue_key=issue,stage='evidence resolution',action='Retain supported proposition.',outcome='Support passed; warning remains visible.',status='retained_with_dissent')
        el['evidence']={'status':'matched','card_id':m['card_id'],'card_tag':f'[card:{tag_by_id[m["card_id"]]}]','source':m['source'],'quote':m['quote'],'audit':a}; keep.append(el)
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
        comps=block['components']; who=next(x for x in comps if x['role']=='who5'); icc=next(x for x in comps if x['role']=='icc')
        if block.get('relationship')=='same': text=f'The diagnosis is {who["diagnosis"]} under both WHO5 and ICC classifications.'
        else: text=f'Under WHO5, the diagnosis is {who["diagnosis"]}. In contrast, under ICC, the diagnosis is {icc["diagnosis"]}.'
        second=next((x for x in comps if x['role']=='second_diagnosis'),None)
        if second: text+=' An independent concurrent diagnosis of '+second['diagnosis']+' is also supported.'
        return text
    return runtime.ensure_sentence(block['components'][0]['reason'])

def stage_blocks(work,diagnosis,elements,reg):
    by_id={el['schema_id']:el for el in elements}; blocks=[]
    dx=[]
    for sid,role in (('DX-WHO5','who5'),('DX-ICC','icc'),('DX-SECOND','second_diagnosis')):
        el=by_id.get(sid)
        if not el: continue
        src=el['source']; dx.append({'role':role,'diagnosis':src.get('diagnosis'),'reason':src.get('reason'),'variants':src.get('variants') or [],'genes':_genes(reg,src.get('variants') or []),'card_tags':[el['evidence']['card_tag']] if el.get('evidence') else []})
    if dx: blocks.append({'block_id':'DX','domain':'diagnosis','relationship':diagnosis['relationship'],'components':dx})
    order={'prognosis':1,'treatment':2,'biomarker':3,'germline':4}
    for el in sorted((e for e in elements if e['domain']!='diagnosis'),key=lambda e:(order[e['domain']],e['schema_id'])):
        src=dict(el['source']); blocks.append({'block_id':el['schema_id'],'domain':el['domain'],'components':[{'role':el['bucket'],'reason':el['reason'],'variants':el.get('variants') or [],'genes':_genes(reg,el.get('variants') or []),'source':src,'card_tags':[el['evidence']['card_tag']] if el.get('evidence') else []}]})
    _write(_existing_or_new(work,'report_blocks','report-blocks.yaml'),yaml.safe_dump({'blocks':blocks},sort_keys=False,allow_unicode=True,width=110))
    return blocks

def stage_report_write(work,blocks,case,reg,profile):
    path=_existing_or_new(work,'report_write','report-write.yaml'); prompt=_prompt('report_write')+'\n\n# Deterministic report blocks\n```yaml\n'+yaml.safe_dump({'blocks':blocks},sort_keys=False,allow_unicode=True,width=110)+'```\n\n# Variant registry — naming context only\n```yaml\n'+_variant_context(reg)+'```\n'
    _model_call(work,call_id='report-write',role='report_write',prompt=prompt,output=path,validator=lambda t:schema_validation.validate_report_write(t,blocks),profile=profile,fatal=False,max_attempts=_retry('report_write_attempts'))
    rendered=yaml.safe_load(_read(path))['blocks']; amap={r['block_id']:r['text'] for r in rendered}
    apath=_existing_or_new(work,'report_write','report-preservation.yaml'); aprompt=_prompt('report_preservation')+'\n\n# Deterministic source blocks\n```yaml\n'+yaml.safe_dump({'blocks':blocks},sort_keys=False,allow_unicode=True,width=110)+'```\n\n# Rendered blocks\n```yaml\n'+yaml.safe_dump({'blocks':rendered},sort_keys=False,allow_unicode=True,width=110)+'```\n'
    try:
        _model_call(work,call_id='report-preservation',role='preservation_check',prompt=aprompt,output=apath,validator=lambda t:schema_validation.validate_preservation(t,blocks),profile=profile,fatal=False,max_attempts=_retry('preservation_attempts'))
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
        ev=el.get('evidence') or {}; cid=ev.get('card_id')
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

def run_pipeline(work,profile=None):
    _require_work(work); layout.ensure_dirs(work)
    _stage_status(work,'stage-1','Stage 1 of 9 — structure case'); case,reg=stage_structure(work,profile)
    _stage_status(work,'stage-2','Stage 2 of 9 — initialise corpus'); all_cards,eligible,digest,manifest=stage_corpus(work)
    _stage_status(work,'stage-3','Stage 3 of 9 — WHO5 / ICC / independent concurrent diagnosis'); diagnosis,cmcs,diagnosis_cards=stage_diagnosis(work,case,reg,eligible,profile)
    domains={}; cards_by_domain=dict(diagnosis_cards)
    for idx,domain in enumerate(('prognosis','treatment','biomarker','germline'),4):
        _stage_status(work,f'stage-{idx}',f'Stage {idx} of 9 — {domain} owner proforma'); domains[domain],cards_by_domain[domain]=stage_domain(work,domain,case,reg,diagnosis,eligible,profile)
    _stage_status(work,'stage-8','Stage 8 of 9 — evidence, reportability, deterministic blocks'); elements=_elements(diagnosis,domains); supported=stage_evidence(work,elements,cards_by_domain,reg,manifest,profile); blocks=stage_blocks(work,diagnosis,supported,reg)
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
    s=sub.add_parser('setup'); s.add_argument('--mode',required=True,choices=['ngs-report','nel-demo','nel-validate','nel-validate-function','nel-validate-brief']); s.add_argument('--case-file',type=Path); s.add_argument('--example',type=int); s.add_argument('--case-id'); s.add_argument('--work-dir',type=Path); s.add_argument('--pipeline',choices=pipeline_registry.names())
    sub.add_parser('pipelines'); pc=sub.add_parser('pipeline-check'); pc.add_argument('--pipeline',required=True,choices=pipeline_registry.names()); pp=sub.add_parser('pipeline-plan'); pp.add_argument('--pipeline',required=True,choices=pipeline_registry.names()); ps=sub.add_parser('pipeline'); ps.add_argument('pipeline_id',nargs='?',choices=pipeline_registry.names()); r=sub.add_parser('run'); r.add_argument('--work-dir',type=Path)
    return p

def main(argv=None):
    args=build_parser().parse_args(argv)
    try:
        if args.command=='setup': return run_setup(args)
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
