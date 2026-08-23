#!/usr/bin/env python3
"""Terraced-v4 prototype: proformas -> semantic evidence -> sentence planning -> report."""
from __future__ import annotations
import argparse, contextlib, hashlib, io, json, shutil, sys, tempfile, time, zipfile
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
from workflows.terraced_v4 import card_identity, layout, model_client, pipeline_registry, rendering, runtime, schema_validation

WORKFLOW_ID='terraced-v4'; RUN_STATE_SCHEMA_VERSION=1; HERE=Path(__file__).resolve().parent; PROMPTS=HERE/'prompts'
SETTINGS_PATH=HERE/'settings.json'; SETTINGS_TEMPLATE_PATH=HERE/'settings.json.template'; CORPUS_FILTERS=HERE/'corpus_filters.yaml'; USAGE_FILE='model-usage.json'
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
    if d.get('schema_version')!=1: raise StepFailure('unsupported terraced-v4 settings schema')
    return d
def configured_pipeline(): return str(load_settings().get('pipeline') or 'self')
def _run_state_path(work): return _artifact(work,'run_state','terraced-v4-run.json',new=True)
def _load_run_state(work):
    d=json.loads(_read(_artifact(work,'run_state','terraced-v4-run.json')))
    if d.get('schema_version')!=RUN_STATE_SCHEMA_VERSION: raise StepFailure('incompatible terraced-v4 run state; start a fresh run')
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
    out=[f'# Terraced-v4 model operation — {call_id}','']
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
    attempts=int(max_attempts or (load_settings().get('fatal_attempts',10) if fatal else 3)); previous=None; last_error=feedback or ''
    # Syntax repair has its own global cap. It must never silently inherit
    # the larger clinical/fatal retry budget.
    syntax_attempts=int(load_settings().get('syntax_repair_attempts',5))
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
    settings=load_settings(); syntax_attempts=int(settings.get('syntax_repair_attempts',5)); max_rewrites=int(settings.get('proforma_rewrite_attempts',3) if max_rewrites is None else max_rewrites)
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
    prompt=_read(PROMPTS/'structure_case.md')+'\n\n# Authoritative case\n'+_read(layout.input(work,'case.md'))+'\n\n# Allowed bootstrap CMCs\n'+_read(layout.setup(work,'case-major-categories.json'))+'\n\n# Assay scope\n'+_read(layout.setup(work,'ngs-panel-scope.md'))
    _model_call(work,call_id='structure-case',role='structure',prompt=prompt,output=out,validator=runtime.validate_case_text,profile=profile,fmt='json')
    case=runtime.read_json(out); reg={f'v{i:02d}':{'variant_id':row['variant_id'],'gene':row['gene'],'description':row['description']} for i,row in enumerate(case.get('variants') or [],1)}
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

def _render_cards(cards):
    if not cards: return 'No candidate cards.'
    blocks=[]
    for c in cards:
        blocks.append('\n'.join([
            f'### {c.get("card_id")}',f'category: {c.get("category")}',f'genes: {", ".join(c.get("genes") or []) or "none"}',f'diseases: {", ".join(c.get("diseases") or []) or "none"}',f'evidence_tier: {c.get("evidence_tier") or "unspecified"}',f'interpretation: {c.get("interpretation") or ""}',f'source_hint: {c.get("paper_nickname") or c.get("citation_display") or ""}'
        ]))
    return '\n\n'.join(blocks)
def _draw_diagnosis_cards(eligible,genes,cmcs):
    hits=[]; wanted=set(genes)
    for c in eligible:
        if c.get('category')!='diagnosis': continue
        mg=core_retrieval.match_genes(c,wanted); mc=core_retrieval._matches_case_major_category(c,cmcs)
        if mg or mc: hits.append(c)
    return sorted(hits,key=lambda x:x.get('card_id') or '')
def _diagnosis_authority_publications(authority):
    doc=yaml.safe_load(_read(CORPUS_FILTERS)) or {}; keys=(((doc.get('diagnosis') or {}).get(authority) or {}).get('publication_keys') or [])
    if not keys: raise StepFailure(f'no diagnosis publication_keys configured for {authority!r}')
    return set(keys)
def _filter_diagnosis_authority(cards,authority):
    keys=_diagnosis_authority_publications(authority)
    return [c for c in cards if c.get('publication_key') in keys]
def _disease_match(card,diseases,category):
    for disease in diseases:
        allowed={disease,*runtime.vocab.retrieval_related_diseases(disease,category)}
        if set(card.get('diseases') or []) & allowed: return True
    return False
def _draw_domain_cards(eligible,domain,genes,diseases):
    hits=[]; wanted=set(genes)
    for c in eligible:
        if c.get('category')!=domain: continue
        mg=core_retrieval.match_genes(c,wanted)
        if domain=='germline':
            if mg: hits.append(c)
        elif _disease_match(c,diseases,domain) and (mg or not c.get('genes')): hits.append(c)
    return sorted(hits,key=lambda x:x.get('card_id') or '')
def _allowed_diseases(work): return set(runtime.read_json(layout.setup(work,'allowed-schema-diseases.json'))['allowed_schema_diseases'])

def stage_diagnosis(work,case,eligible,profile):
    allowed=_allowed_diseases(work); genes=runtime.case_genes(case); bootstrap=list(case.get('bootstrap_cmcs') or [])

    # WHO5 is the CMC-driving authority.  Pass 1 always runs first and sees only
    # Khoury 2022 diagnosis cards, matching v3's authority-specific filter.
    who1_path=_existing_or_new(work,'diagnosis_who5_pass_1','who5.yaml')
    who1_cards=_filter_diagnosis_authority(_draw_diagnosis_cards(eligible,genes,bootstrap),'who5')
    who1_prompt=_read(PROMPTS/'diagnosis_who5.md')+'\n\n# Pass\nWHO5 pass 1: classify from scratch.\n\n# Structured case\n```json\n'+json.dumps(case,indent=2,ensure_ascii=False)+'\n```\n\n# Allowed WHO5 schema diseases\n'+yaml.safe_dump(sorted(allowed))+'\n# WHO5 authority cards — Khoury 2022 only\n'+_render_cards(who1_cards)
    _model_call(work,call_id='diagnosis-who5-pass-01',role='diagnosis',prompt=who1_prompt,output=who1_path,validator=lambda t:schema_validation.validate_who5_diagnosis(t,allowed_diseases=allowed),profile=profile,proforma=True)
    who1=yaml.safe_load(_read(who1_path)); cmc1=runtime.derive_cmcs(who1); changed=cmc1!=bootstrap

    pass2_cmc_history=[]
    for cmc in list(bootstrap)+list(cmc1):
        if cmc not in pass2_cmc_history: pass2_cmc_history.append(cmc)

    # A second WHO5 call exists only when pass 1 changed the deterministic CMC.
    # It starts from scratch and recalls cumulative old+new CMC evidence.
    if changed:
        who2_path=_existing_or_new(work,'diagnosis_who5_pass_2','who5.yaml')
        who2_cards=_filter_diagnosis_authority(_draw_diagnosis_cards(eligible,genes,pass2_cmc_history),'who5')
        who2_prompt=_read(PROMPTS/'diagnosis_who5.md')+'\n\n# Pass\nWHO5 pass 2: the CMC changed after pass 1. START FROM SCRATCH. Do not use or anchor on the pass-1 answer.\n\n# Cumulative CMC recall\n```yaml\n'+yaml.safe_dump(pass2_cmc_history,sort_keys=False)+'```\n\n# Structured case\n```json\n'+json.dumps(case,indent=2,ensure_ascii=False)+'\n```\n\n# Allowed WHO5 schema diseases\n'+yaml.safe_dump(sorted(allowed))+'\n# WHO5 authority cards — Khoury 2022 only, cumulative CMC draw\n'+_render_cards(who2_cards)
        _model_call(work,call_id='diagnosis-who5-pass-02',role='diagnosis',prompt=who2_prompt,output=who2_path,validator=lambda t:schema_validation.validate_who5_diagnosis(t,allowed_diseases=allowed),profile=profile,proforma=True)
        final_who=yaml.safe_load(_read(who2_path)); who_cards=who2_cards; authoritative_pass=2
    else:
        final_who=who1; who_cards=who1_cards; authoritative_pass=1

    final_cmcs=runtime.derive_cmcs(final_who); diagnostic_cmc_history=list(pass2_cmc_history)
    for cmc in final_cmcs:
        if cmc not in diagnostic_cmc_history: diagnostic_cmc_history.append(cmc)
    if changed and final_cmcs!=cmc1:
        _risk(work,stage='diagnosis',risk_type='cmc_changed_after_final_pass',message=f'WHO5 pass 2 changed CMCs from {cmc1} to {final_cmcs}; prototype intentionally stops after pass 2, so no third CMC redraw occurred.',action='continued_with_who5_pass_2_as_authoritative',human_review='recommended')

    # ICC runs once, after authoritative WHO5 is frozen.  It sees Arber 2022
    # cards only and the WHO5 output solely to assess significant difference.
    icc_cards=_filter_diagnosis_authority(_draw_diagnosis_cards(eligible,genes,diagnostic_cmc_history),'icc')
    icc_path=_existing_or_new(work,'diagnosis_icc','icc.yaml')
    icc_prompt=_read(PROMPTS/'diagnosis_icc.md')+'\n\n# Structured case\n```json\n'+json.dumps(case,indent=2,ensure_ascii=False)+'\n```\n\n# Authoritative WHO5 result — comparison only\n```yaml\n'+yaml.safe_dump(final_who,sort_keys=False,allow_unicode=True,width=110)+'```\n\n# ICC authority cards — Arber 2022 only\n'+_render_cards(icc_cards)
    _model_call(work,call_id='diagnosis-icc',role='diagnosis',prompt=icc_prompt,output=icc_path,validator=schema_validation.validate_icc_diagnosis,profile=profile,proforma=True)
    icc_full=yaml.safe_load(_read(icc_path)); comp=icc_full['comparison_with_who5']

    # Other diagnostic considerations see the case and authoritative WHO5 only;
    # ICC is intentionally excluded from this reasoning call.
    other_path=_existing_or_new(work,'diagnosis_other','other.yaml')
    other_prompt=_read(PROMPTS/'diagnosis_other.md')+'\n\n# Structured case\n```json\n'+json.dumps(case,indent=2,ensure_ascii=False)+'\n```\n\n# Authoritative WHO5 result\n```yaml\n'+yaml.safe_dump(final_who,sort_keys=False,allow_unicode=True,width=110)+'```\n'
    _model_call(work,call_id='diagnosis-other-considerations',role='diagnosis',prompt=other_prompt,output=other_path,validator=schema_validation.validate_other_diagnosis,profile=profile,proforma=True)
    other=yaml.safe_load(_read(other_path))

    diagnosis={
        'who5':final_who,
        'icc':{'diagnoses':icc_full['diagnoses']},
        'concordance':{
            'answer':'WHO5 and ICC are significantly different.' if comp['significantly_different'] else 'WHO5 and ICC are not significantly different.',
            'reasons':[comp['explanation']],
        },
        'concurrent_second_diagnosis':other['concurrent_second_diagnosis'],
    }
    _write(_existing_or_new(work,'diagnosis','diagnosis-final.yaml'),yaml.safe_dump(diagnosis,sort_keys=False,allow_unicode=True,width=110))
    routing={
        'bootstrap_cmcs':bootstrap,'pass_1_cmcs':cmc1,'cmc_changed_after_pass_1':changed,
        'pass_2_cmc_history':pass2_cmc_history,'who5_authoritative_pass':authoritative_pass,
        'final_cmcs':final_cmcs,'diagnostic_cmc_history':diagnostic_cmc_history,
    }
    _write(_existing_or_new(work,'diagnosis','routing.json'),json.dumps(routing,indent=2,ensure_ascii=False)+'\n')
    # Keep authority-specific pools distinct for subsequent semantic evidence matching.
    other_cards=_draw_diagnosis_cards(eligible,genes,diagnostic_cmc_history)
    return diagnosis,final_cmcs,{'diagnosis_who5':who_cards,'diagnosis_icc':icc_cards,'diagnosis_other':other_cards}

def _variant_context(reg): return yaml.safe_dump({'variants':reg},sort_keys=False,allow_unicode=True,width=110)
def stage_domain(work,domain,case,reg,diagnosis,eligible,profile):
    valid=set(reg); diseases=[r['schema_disease'] for r in diagnosis['who5']['diagnoses']]; cards=_draw_domain_cards(eligible,domain,runtime.case_genes(case),diseases)
    out=_existing_or_new(work,f'{domain}_state','proforma.yaml'); validator={'prognosis':schema_validation.validate_prognosis,'treatment':schema_validation.validate_treatment,'biomarker':schema_validation.validate_biomarker,'germline':schema_validation.validate_germline}[domain]
    prompt=_read(PROMPTS/f'{domain}.md')+'\n\n# Variant registry\n```yaml\n'+_variant_context(reg)+'```\n\n# Structured case\n```json\n'+json.dumps(case,indent=2,ensure_ascii=False)+'\n```\n\n# Authoritative diagnosis\n```yaml\n'+yaml.safe_dump(diagnosis,sort_keys=False,allow_unicode=True,width=110)+'```\n\n# Candidate evidence cards\n'+_render_cards(cards)
    system_prompt=None
    if domain=='germline':
        system_prompt=(
            'You are executing the germline-classification step of a clinical NGS reporting workflow. '
            'Use the supplied case and your clinical knowledge to decide whether each gene is a recognised germline-predisposition gene and whether the observed VAF is compatible with germline origin. '
            'Candidate evidence cards are not exhaustive, so absence of a germline card is not a reason to classify a variant as uncertain. '
            'Do not search the web or consult outside literature during this call. Evidence substantiation is handled later. Return exactly the requested artifact.'
        )
    _model_call(work,call_id=domain,role='ptbg',prompt=prompt,output=out,validator=lambda t:validator(t,valid),profile=profile,system_prompt=system_prompt,proforma=True)
    return yaml.safe_load(_read(out)),cards

def _schema_elements(diagnosis,domains):
    els=[]
    for i,row in enumerate(diagnosis['who5']['diagnoses'],1): els.append({'schema_id':f'DX-WHO5-{i:02d}','domain':'diagnosis','proposition':f'WHO5 classification: {row["diagnosis"]}.','reasons':row['reasons'],'evidence_domain':'diagnosis_who5'})
    for i,row in enumerate(diagnosis['icc']['diagnoses'],1): els.append({'schema_id':f'DX-ICC-{i:02d}','domain':'diagnosis','proposition':f'ICC classification: {row["diagnosis"]}.','reasons':row['reasons'],'evidence_domain':'diagnosis_icc'})
    els.append({'schema_id':'DX-CONCORDANCE','domain':'diagnosis','proposition':diagnosis['concordance']['answer'],'reasons':diagnosis['concordance']['reasons'],'evidence_domain':'diagnosis_icc'})
    if diagnosis['concurrent_second_diagnosis']['answer'].strip().lower() not in {'none','none supported','no concurrent second diagnosis supported'}:
        els.append({'schema_id':'DX-CONCURRENT','domain':'diagnosis','proposition':diagnosis['concurrent_second_diagnosis']['answer'],'reasons':diagnosis['concurrent_second_diagnosis']['reasons'],'evidence_domain':'diagnosis_other'})
    p=domains['prognosis']
    for b in ('favorable','adverse','other','uncertain'):
        for i,row in enumerate(p[b],1): els.append({'schema_id':f'PX-{b.upper()}-{i:02d}','domain':'prognosis','proposition':f'{b} prognostic contribution for {", ".join(row["variants"])}','reasons':[row['reason']],'variants':row['variants'],'evidence_domain':'prognosis'})
    els.append({'schema_id':'PX-OVERALL','domain':'prognosis','proposition':p['overall']['classification'],'reasons':[p['overall']['reason']],'evidence_domain':'prognosis'})
    t=domains['treatment']
    for b in ('drug_target','drug_resistance','other'):
        for i,row in enumerate(t[b],1):
            prop=(f'{b.replace("_"," ")} for {", ".join(row["variants"])}'+(f' — {row.get("therapy")}' if row.get('therapy') else ''))
            els.append({'schema_id':f'TX-{b.upper()}-{i:02d}','domain':'treatment','proposition':prop,'reasons':[row['reason']],'variants':row['variants'],'evidence_domain':'treatment'})
    b=domains['biomarker']
    for bucket in ('suitable_mrd','unsuitable_mrd','uncertain'):
        for i,row in enumerate(b[bucket],1): els.append({'schema_id':f'MRD-{bucket.upper()}-{i:02d}','domain':'biomarker','proposition':f'{bucket.replace("_"," ")} for {", ".join(row["variants"])}','reasons':[row['reason']],'variants':row['variants'],'evidence_domain':'biomarker'})
    g=domains['germline']
    for bucket in ('suspect','uncertain'):
        for i,row in enumerate(g[bucket],1): els.append({'schema_id':f'GL-{bucket.upper()}-{i:02d}','domain':'germline','proposition':f'{bucket} germline origin for {", ".join(row["variants"])}','reasons':[row['reason']],'variants':row['variants'],'evidence_domain':'germline'})
    # Clinical-support entries are case-evidence annotations, not literature claims; keep them as reasons on matching germline elements where possible.
    for row in g['clinical_support']:
        target=set(row['variants'])
        for el in els:
            if el['domain']=='germline' and target & set(el.get('variants') or []): el['reasons'].append(f'Clinical syndrome support ({row["support"]}): {row["reason"]}')
    return els

def _candidate_cards_for_element(el,cards_by_domain,reg):
    cards=list(cards_by_domain.get(el['evidence_domain']) or [])
    variants=el.get('variants') or []
    genes={reg[v]['gene'] for v in variants if v in reg}
    if genes:
        gene_cards=[c for c in cards if not c.get('genes') or genes & set(c.get('genes') or [])]
        if gene_cards: cards=gene_cards
    return cards

def _card_match_view(card):
    return {
        'card_id':card.get('card_id'),'category':card.get('category'),'genes':card.get('genes') or [],
        'diseases':card.get('diseases') or [],'evidence_tier':card.get('evidence_tier'),
        'interpretation':card.get('interpretation') or '',
        'source_hint':card.get('paper_nickname') or card.get('citation_display') or '',
    }

def _batch_match_prompt(items,card_catalog,state):
    public=[]
    for item in items:
        row={'evidence_id':item['evidence_id'],'schema_id':item['schema_id'],'proposition':item['proposition'],'reason':item['reason'],'candidate_card_ids':item['candidate_card_ids']}
        st=state.get(item['evidence_id']) or {}
        if st.get('previous_objection'):
            row['previous_auditor_concern']={'previous_card_id':st.get('previous_card_id'),'non_authoritative':True,'concern':st['previous_objection']}
        public.append(row)
    ids=[]
    for row in public:
        for cid in row['candidate_card_ids']:
            if cid not in ids: ids.append(cid)
    cards=[_card_match_view(card_catalog[cid]) for cid in ids]
    return _read(PROMPTS/'evidence_match.md')+'\n\n# Evidence items\n```yaml\n'+yaml.safe_dump({'items':public},sort_keys=False,allow_unicode=True,width=110)+'```\n\n# Candidate card catalog\n```yaml\n'+yaml.safe_dump({'cards':cards},sort_keys=False,allow_unicode=True,width=110)+'```\n'

def _batch_audit_prompt(items,matches,card_catalog):
    mmap={m['evidence_id']:m for m in matches}; rows=[]
    for item in items:
        match=mmap[item['evidence_id']]; rows.append({'evidence_id':item['evidence_id'],'schema_id':item['schema_id'],'reason':item['reason'],'source':match['source'],'quote':match['quote'],'selected_card':_card_match_view(card_catalog[match['card_id']])})
    return _read(PROMPTS/'evidence_audit.md')+'\n\n# Selected evidence pairs\n```yaml\n'+yaml.safe_dump({'items':rows},sort_keys=False,allow_unicode=True,width=110)+'```\n'

def stage_evidence(work,elements,cards_by_domain,reg,manifest,profile):
    tag_by_id=card_identity.tag_by_id(manifest); enriched=[dict(el,evidence=[]) for el in elements]
    records=[]; card_catalog={}; evidence_counter=0
    for ei,el in enumerate(elements):
        candidates=_candidate_cards_for_element(el,cards_by_domain,reg)
        for ri,reason in enumerate(el['reasons'],1):
            if reason.startswith('Clinical syndrome support ('):
                enriched[ei]['evidence'].append({'_reason_index':ri,'reason':reason,'status':'case_only','card_id':None,'card_tag':None,'source':None,'quote':None,'audit':None}); continue
            if not candidates:
                _risk(work,stage='evidence',risk_type='no_candidate_cards',message='No candidate evidence cards were available for this reason.',schema_element=el['schema_id'],action='continued_without_resolved_evidence',human_review='required')
                enriched[ei]['evidence'].append({'_reason_index':ri,'reason':reason,'status':'unresolved','card_id':None,'card_tag':None,'source':None,'quote':None,'audit':None}); continue
            evidence_counter+=1; evid=f'E{evidence_counter:04d}'
            for card in candidates: card_catalog[card['card_id']]=card
            records.append({'evidence_id':evid,'element_index':ei,'reason_index':ri,'schema_id':el['schema_id'],'proposition':el['proposition'],'reason':reason,'candidate_card_ids':[c['card_id'] for c in candidates]})

    results={}; pending=list(records); state={}; max_sem=int(load_settings().get('evidence_match_attempts',3))
    for attempt in range(1,max_sem+1):
        if not pending: break
        match_path=_artifact(work,'evidence_matches',f'batch-match-attempt-{attempt:02d}.yaml',new=True)
        prompt=_batch_match_prompt(pending,card_catalog,state)
        try:
            _model_call(work,call_id=f'evidence-match-batch-a{attempt}',role='evidence_match',prompt=prompt,output=match_path,validator=lambda t,it=list(pending):schema_validation.validate_evidence_match_batch(t,it),profile=profile,fatal=False,max_attempts=3)
            matches=yaml.safe_load(_read(match_path))['matches']
        except StepFailure as exc:
            for item in pending:
                _risk(work,stage='evidence',risk_type='evidence_match_structural_failure',message=str(exc),schema_element=item['schema_id'],attempts=attempt,action='continued_unresolved',human_review='required')
                results[item['evidence_id']]={'reason':item['reason'],'status':'unresolved','card_id':None,'card_tag':None,'source':None,'quote':None,'audit':None}
            pending=[]; break

        audit_path=_artifact(work,'evidence_audits',f'batch-audit-attempt-{attempt:02d}.yaml',new=True)
        aprompt=_batch_audit_prompt(pending,matches,card_catalog)
        try:
            _model_call(work,call_id=f'evidence-audit-batch-a{attempt}',role='evidence_audit',prompt=aprompt,output=audit_path,validator=lambda t,it=list(pending):schema_validation.validate_evidence_audit_batch(t,it),profile=profile,fatal=False,max_attempts=3)
            audits=yaml.safe_load(_read(audit_path))['audits']
        except StepFailure as exc:
            audits=[{'evidence_id':item['evidence_id'],'obvious_mismatch':False,'risk':'warning','comments':['Citation audit unavailable after bounded retries: '+str(exc)]} for item in pending]
            _risk(work,stage='evidence',risk_type='citation_audit_unavailable',message=str(exc),attempts=attempt,action='retained_batch_matches_without_successful_audit',human_review='recommended')

        mmap={m['evidence_id']:m for m in matches}; amap={a['evidence_id']:a for a in audits}; next_pending=[]
        for item in pending:
            evid=item['evidence_id']; chosen=mmap[evid]; audit=amap[evid]; st=state.setdefault(evid,{})
            if audit['risk']=='warning':
                _risk(work,stage='evidence',risk_type='citation_fidelity',message='; '.join(audit['comments']) or 'Citation auditor flagged a fidelity concern.',schema_element=item['schema_id'],attempts=attempt,action='retained_pending_human_review',human_review='recommended')
            if not audit['obvious_mismatch']:
                results[evid]={'reason':item['reason'],'status':'matched','card_id':chosen['card_id'],'card_tag':f'[card:{tag_by_id[chosen["card_id"]]}]','source':chosen['source'],'quote':chosen['quote'],'audit':audit,'resolution':'accepted'}
                continue
            objection='; '.join(audit['comments']) or f'Citation auditor flagged {chosen["card_id"]} as an obvious mismatch without detailed feedback.'
            if st.get('previous_objection') is not None and chosen['card_id']==st.get('previous_card_id'):
                _risk(work,stage='evidence',risk_type='citation_auditor_disagreement',message=f'Matcher re-selected {chosen["card_id"]} after being shown the auditor concern: {objection}',schema_element=item['schema_id'],attempts=attempt,action='retained_after_matcher_reaffirmation',human_review='required')
                results[evid]={'reason':item['reason'],'status':'matched','card_id':chosen['card_id'],'card_tag':f'[card:{tag_by_id[chosen["card_id"]]}]','source':chosen['source'],'quote':chosen['quote'],'audit':audit,'resolution':'auditor_disagreement_retained'}
                continue
            _risk(work,stage='evidence',risk_type='obvious_citation_mismatch',message=objection,schema_element=item['schema_id'],attempts=attempt,action='rematched_with_auditor_feedback' if attempt<max_sem else 'continued_unresolved',human_review='recommended' if attempt<max_sem else 'required')
            if attempt<max_sem:
                st['previous_objection']=objection; st['previous_card_id']=chosen['card_id']; next_pending.append(item)
            else:
                results[evid]={'reason':item['reason'],'status':'unresolved','card_id':chosen['card_id'],'card_tag':None,'source':chosen['source'],'quote':chosen['quote'],'audit':audit}
        pending=next_pending

    for item in records:
        ev=results.get(item['evidence_id'])
        if ev is None:
            ev={'reason':item['reason'],'status':'unresolved','card_id':None,'card_tag':None,'source':None,'quote':None,'audit':None}
        # Evidence append order remains identical to reason order within each schema element.
        ev=dict(ev); ev['_reason_index']=item['reason_index']; enriched[item['element_index']]['evidence'].append(ev)
    for row in enriched:
        row['evidence'].sort(key=lambda ev:ev.get('_reason_index',9999))
        for ev in row['evidence']: ev.pop('_reason_index',None)
    _write(_existing_or_new(work,'evidence_enriched','schema-elements.yaml'),yaml.safe_dump({'elements':enriched},sort_keys=False,allow_unicode=True,width=110)); return enriched

def stage_reportable_sentences(work,elements,profile):
    out=_existing_or_new(work,'reportable_sentences','reportable-sentences.yaml')
    public=[{'schema_id':e['schema_id'],'domain':e['domain'],'proposition':e['proposition'],'reasons':e['reasons'],'variants':e.get('variants',[])} for e in elements]
    prompt=_read(PROMPTS/'reportable_sentences.md')+'\n\n# Schema elements\n```yaml\n'+yaml.safe_dump(public,sort_keys=False,allow_unicode=True,width=110)+'```\n'
    _model_call(work,call_id='reportable-sentences',role='reportable_sentences',prompt=prompt,output=out,validator=lambda t:schema_validation.validate_reportable_sentences(t,public),profile=profile)
    rows=yaml.safe_load(_read(out))['sentences']; statements=[]
    for i,(sentence,el) in enumerate(zip(rows,elements),1):
        tags=[]
        for ev in el.get('evidence') or []:
            tag=ev.get('card_tag')
            if tag and tag not in tags: tags.append(tag)
        statements.append({'statement_id':f'S{i:04d}','schema_id':el['schema_id'],'domain':el['domain'],'statement':sentence['sentence'].strip().rstrip('.')+'.','reason':' | '.join(el['reasons']),'card_tags':tags})
    path=_existing_or_new(work,'reportable_sentences','statements.yaml'); _write(path,yaml.safe_dump({'statements':statements},sort_keys=False,allow_unicode=True,width=110)); return statements

def _validate_para_audit(text):
    try: d=yaml.safe_load(text)
    except yaml.YAMLError as exc: raise ValueError(f'paraphrase audit: invalid YAML: {exc}') from exc
    issues=[]
    if not isinstance(d,dict):
        safe=runtime._single_mapping_list(d)
        issues.append(validated_model_task.ValidationIssue('paraphrase audit',f'expected mapping; received {type(d).__name__}','remove the extra one-item list wrapper without changing fields or values' if safe else 'return the required mapping with preserved and issue',repair_class='serialization' if safe else 'content',received=repr(d),expected='mapping'))
        d={}
    expected={'preserved','issue'}; missing=sorted(expected-set(d)); extra=sorted(set(d)-expected)
    if missing or extra:
        issues.append(validated_model_task.ValidationIssue('paraphrase audit',f'missing fields {missing}; unexpected fields {extra}',f'return exactly {sorted(expected)}',repair_class='content'))
    preserved=d.get('preserved')
    if not isinstance(preserved,bool):
        safe=runtime._bool_repairable(preserved)
        issues.append(validated_model_task.ValidationIssue('preserved',f'expected boolean; received {type(preserved).__name__}','serialize the existing true/false decision as a YAML boolean' if safe else 'return the required true/false decision',repair_class='serialization' if safe else 'content',received=repr(preserved),expected='true or false'))
    issue=d.get('issue')
    if preserved is True and issue is not None:
        issues.append(validated_model_task.ValidationIssue('issue',f'preserved=true but issue is {issue!r}','set issue: null when preserved is true',repair_class='content'))
    if preserved is False and (not isinstance(issue,str) or not issue.strip()):
        issues.append(validated_model_task.ValidationIssue('issue','preserved=false requires a non-empty explanation','state the specific semantic-preservation problem',repair_class='content',received=repr(issue),expected='non-empty string'))
    validated_model_task.fail('paraphrase audit',issues)
    return 'paraphrase audit structurally valid'


def _validate_summary_plan_audit(text):
    try: d=yaml.safe_load(text)
    except yaml.YAMLError as exc: raise ValueError(f'summary-plan audit: invalid YAML: {exc}') from exc
    out=[]
    if not isinstance(d,dict):
        safe=runtime._single_mapping_list(d)
        out.append(validated_model_task.ValidationIssue('summary-plan audit',f'expected mapping; received {type(d).__name__}','remove the extra one-item list wrapper without changing fields or values' if safe else 'return the required mapping with preserved and issues',repair_class='serialization' if safe else 'content',received=repr(d),expected='mapping'))
        d={}
    expected={'preserved','issues'}; missing=sorted(expected-set(d)); extra=sorted(set(d)-expected)
    if missing or extra:
        out.append(validated_model_task.ValidationIssue('summary-plan audit',f'missing fields {missing}; unexpected fields {extra}',f'return exactly {sorted(expected)}',repair_class='content'))
    preserved=d.get('preserved')
    if not isinstance(preserved,bool):
        safe=runtime._bool_repairable(preserved)
        out.append(validated_model_task.ValidationIssue('preserved',f'expected boolean; received {type(preserved).__name__}','serialize the existing true/false decision as a YAML boolean' if safe else 'return the required true/false decision',repair_class='serialization' if safe else 'content',received=repr(preserved),expected='true or false'))
    rows=d.get('issues')
    if not isinstance(rows,list):
        safe=isinstance(rows,dict)
        out.append(validated_model_task.ValidationIssue('issues',f'expected list; received {type(rows).__name__}','wrap the existing single issue mapping in a list without changing it' if safe else 'return issues as a list of target/issue mappings',repair_class='serialization' if safe else 'content',received=repr(rows),expected='list'))
        rows=[]
    for i,row in enumerate(rows):
        path=f'issues[{i}]'
        if not isinstance(row,dict):
            safe=runtime._single_mapping_list(row)
            out.append(validated_model_task.ValidationIssue(path,f'expected mapping; received {type(row).__name__}','remove the extra one-item list wrapper without changing fields or values' if safe else 'return one mapping with target and issue',repair_class='serialization' if safe else 'content',received=repr(row),expected='mapping'))
            continue
        miss=sorted({'target','issue'}-set(row)); extra=sorted(set(row)-{'target','issue'})
        if miss or extra: out.append(validated_model_task.ValidationIssue(path,f'missing fields {miss}; unexpected fields {extra}',"return exactly ['issue', 'target']",repair_class='content'))
        for field in ('target','issue'):
            value=row.get(field)
            if not isinstance(value,str) or not value.strip():
                cls='serialization' if runtime._scalar_string_repairable(value) else 'content'
                fix='quote/reserialize the existing value as one non-empty string without changing its words' if cls=='serialization' else f'return a non-empty {field} string'
                out.append(validated_model_task.ValidationIssue(f'{path}.{field}',f'expected non-empty string; received {type(value).__name__}',fix,repair_class=cls,received=repr(value),expected='non-empty string'))
    if preserved is True and rows:
        out.append(validated_model_task.ValidationIssue('issues','preserved=true requires an empty issue list','return issues: []',repair_class='content'))
    if preserved is False and not rows:
        out.append(validated_model_task.ValidationIssue('issues','preserved=false requires at least one issue','return at least one target/issue mapping',repair_class='content'))
    validated_model_task.fail('summary-plan audit',out)
    return 'summary-plan audit structurally valid'

def _fallback_summary_plan(statements):
    dispositions=[]; parts=[]
    for i,statement in enumerate(statements,1):
        dispositions.append({'statement_id':statement['statement_id'],'decision':'include','reason':None})
        parts.append({'statement_id':statement['statement_id'],'group':f'F{i:04d}','split_text':None})
    plan={'dispositions':dispositions,'parts':parts}; runtime.validate_summary_plan_doc(plan,statements); return plan

def stage_summary(work,statements,profile):
    plan_path=_existing_or_new(work,'summary','summary-plan.yaml'); plan_status=_existing_or_new(work,'summary','summary-plan-status.json')
    if plan_path.is_file() and plan_status.is_file():
        plan=yaml.safe_load(_read(plan_path)); runtime.validate_summary_plan_doc(plan,statements); blocks=runtime.build_summary_blocks(plan,statements)
    else:
        attempt_path=_artifact(work,'summary','summary-plan-attempt-01.yaml',new=True)
        prompt=_read(PROMPTS/'summary_plan.md')+'\n\n# Reportable sentences\n```yaml\n'+yaml.safe_dump(statements,sort_keys=False,allow_unicode=True,width=110)+'```\n'
        try:
            _model_call(work,call_id='summary-plan',role='summarization',prompt=prompt,output=attempt_path,validator=lambda t:runtime.validate_summary_plan_text(t,statements),profile=profile,fatal=False,max_attempts=2)
            candidate=yaml.safe_load(_read(attempt_path)); blocks=runtime.build_summary_blocks(candidate,statements)
            audit_path=_artifact(work,'summary','summary-plan-audit.yaml',new=True)
            audit_prompt=_read(PROMPTS/'summary_plan_audit.md')+'\n\n# Source reportable sentences\n```yaml\n'+yaml.safe_dump(statements,sort_keys=False,allow_unicode=True,width=110)+'```\n\n# Proposed plan\n```yaml\n'+yaml.safe_dump(candidate,sort_keys=False,allow_unicode=True,width=110)+'```\n\n# Deterministically assembled blocks\n```yaml\n'+yaml.safe_dump({'blocks':blocks},sort_keys=False,allow_unicode=True,width=110)+'```\n'
            _model_call(work,call_id='summary-plan-audit',role='semantic_preservation_check',prompt=audit_prompt,output=audit_path,validator=_validate_summary_plan_audit,profile=profile,fatal=False,max_attempts=2)
            audit=yaml.safe_load(_read(audit_path))
            if audit['preserved']:
                plan=candidate
            else:
                msg='; '.join(f"{x['target']}: {x['issue']}" for x in audit['issues'])
                _risk(work,stage='summarization',risk_type='summary_plan_semantic_preservation',message=msg or 'Summary plan failed semantic-preservation audit.',attempts=1,action='fell_back_to_one_block_per_reportable_statement',human_review='optional')
                plan=_fallback_summary_plan(statements); blocks=runtime.build_summary_blocks(plan,statements)
        except StepFailure as exc:
            _risk(work,stage='summarization',risk_type='summary_plan_failure',message=str(exc),attempts=1,action='fell_back_to_one_block_per_reportable_statement',human_review='optional')
            plan=_fallback_summary_plan(statements); blocks=runtime.build_summary_blocks(plan,statements)
        _write(plan_path,yaml.safe_dump(plan,sort_keys=False,allow_unicode=True,width=110)); _write(plan_status,json.dumps({'status':'audited_or_safe_fallback'},indent=2)+'\n')
    blocks_path=_existing_or_new(work,'summary','summary-blocks.yaml'); _write(blocks_path,yaml.safe_dump({'blocks':blocks},sort_keys=False,allow_unicode=True,width=110))

    # One whole-report paraphrasing call.  Semantic failures degrade per block
    # to a deterministic source-preserving sentence; no per-sentence call loop.
    para_path=_existing_or_new(work,'summary','paraphrase-batch.yaml')
    pprompt=_read(PROMPTS/'paraphrase.md')+'\n\n# Deterministically assembled blocks\n```yaml\n'+yaml.safe_dump({'blocks':blocks},sort_keys=False,allow_unicode=True,width=110)+'```\n'
    try:
        _model_call(work,call_id='paraphrase-batch',role='paraphrasing',prompt=pprompt,output=para_path,validator=lambda t:runtime.validate_paraphrase_batch_text(t,blocks),profile=profile,fatal=False,max_attempts=2)
        paras=yaml.safe_load(_read(para_path))['sentences']
    except StepFailure as exc:
        _risk(work,stage='summarization',risk_type='paraphrase_batch_failure',message=str(exc),attempts=1,action='fell_back_to_source_preserving_block_sentences',human_review='optional')
        paras=[{'block_id':b['block_id'],'sentence':runtime.fallback_block_sentence(b)} for b in blocks]

    audit_path=_existing_or_new(work,'summary','paraphrase-audit-batch.yaml')
    audit_prompt=_read(PROMPTS/'paraphrase_audit.md')+'\n\n# Blocks and paraphrased sentences\n```yaml\n'+yaml.safe_dump({'blocks':blocks,'sentences':paras},sort_keys=False,allow_unicode=True,width=110)+'```\n'
    try:
        _model_call(work,call_id='paraphrase-audit-batch',role='semantic_preservation_check',prompt=audit_prompt,output=audit_path,validator=lambda t:runtime.validate_paraphrase_audit_batch_text(t,blocks),profile=profile,fatal=False,max_attempts=2)
        audits=yaml.safe_load(_read(audit_path))['audits']
    except StepFailure as exc:
        audits=[{'block_id':b['block_id'],'preserved':False,'issue':'Semantic audit unavailable after bounded retries: '+str(exc)} for b in blocks]
        _risk(work,stage='summarization',risk_type='paraphrase_audit_unavailable',message=str(exc),attempts=1,action='fell_back_to_source_preserving_block_sentences',human_review='optional')

    pmap={p['block_id']:p['sentence'] for p in paras}; amap={a['block_id']:a for a in audits}; final={'dispositions':plan['dispositions'],'sentences':[]}
    for block in blocks:
        audit=amap.get(block['block_id'],{'preserved':False,'issue':'Missing audit row.'}); sentence=pmap.get(block['block_id']) or runtime.fallback_block_sentence(block)
        if not audit['preserved']:
            _risk(work,stage='summarization',risk_type='paraphrase_semantic_preservation',message=audit.get('issue') or 'Paraphrase lost material block semantics.',schema_element=block['block_id'],attempts=1,action='fell_back_to_source_preserving_block_sentence',human_review='optional')
            sentence=runtime.fallback_block_sentence(block)
        final['sentences'].append({'sentence_id':block['block_id'],'domain':block['domain'],'sentence':sentence,'source_statement_ids':block['source_statement_ids'],'card_tags':runtime.deterministic_sentence_card_tags(block['source_statement_ids'],statements)})
    runtime.validate_canonical_summary_doc(final,statements); path=_existing_or_new(work,'summary','summary-final.yaml'); _write(path,yaml.safe_dump(final,sort_keys=False,allow_unicode=True,width=110)); return final

def stage_final(work,case,summary,elements,all_cards,digest,manifest):
    selected=[]; ids=[]
    for el in elements:
        for ev in el.get('evidence') or []:
            cid=ev.get('card_id') if ev.get('status')=='matched' else None
            if cid and cid not in ids: ids.append(cid)
    by_id={c['card_id']:c for c in all_cards}; selected=[by_id[cid] for cid in ids if cid in by_id]
    bundle={'workflow_profile':WORKFLOW_ID,'terraced_domain':'all','genes':runtime.case_genes(case),'provisional_cmcs':[],'accepted_schema_diseases':[],'diagnostic_context':[],'retrieved':selected,'runtime_card_tags':card_identity.runtime_tag_map(manifest),'provenance':{'corpus_version':None,'corpus_sha256':digest,'retrieved_at':datetime.now(timezone.utc).isoformat()}}
    bpath=_existing_or_new(work,'final_evidence','bundle.json'); epath=_existing_or_new(work,'final_evidence','evidence.md'); tpath=_existing_or_new(work,'final_evidence','card-tags.json'); _write(bpath,json.dumps(bundle,indent=2,ensure_ascii=False)+'\n'); rendering.render_to_files(bpath,output=epath,card_tag_output=tpath,retrieved_only=True)
    cited=runtime.render_canonical_summary(summary); cpath=_existing_or_new(work,'summary','report-cited.md'); _write(cpath,cited)
    rendered=citations.render(cited,_read(epath),_read(tpath),require_citation_after_full_stop=False); rendered=case['detected_variants_summary']+'\n\n'+rendered.lstrip(); report=work/'report-final.md'; _write(report,rendered)
    risks=_risk_doc(work); payload={'workflow':WORKFLOW_ID,'summary':summary,'risk_log':risks,'model_usage':_usage_summary(work),'report_markdown':rendered}; _write(work/'report-final.json',json.dumps(payload,indent=2,ensure_ascii=False)+'\n')
    mode=_load_run_state(work).get('mode')
    if mode in VALIDATION_MODES:
        case_id=_load_run_state(work).get('validation_case'); package_marking_bundle(case_id,report,work/f'{MARKING_PREFIX[mode]}-{case_id}.zip',case_file=validation_cases.VALIDATION_CASE_FILES[mode])

def run_pipeline(work,profile=None):
    _require_work(work); layout.ensure_dirs(work)
    _stage_status(work,'stage-1','Stage 1 of 9 — structure case'); case,reg=stage_structure(work,profile)
    _stage_status(work,'stage-2','Stage 2 of 9 — initialise corpus'); all_cards,eligible,digest,manifest=stage_corpus(work)
    _stage_status(work,'stage-3','Stage 3 of 9 — diagnosis: WHO5 → conditional WHO5 pass 2 → ICC → other considerations'); diagnosis,cmcs,diagnosis_cards=stage_diagnosis(work,case,eligible,profile)
    domains={}; cards_by_domain=dict(diagnosis_cards)
    for idx,domain in enumerate(('prognosis','treatment','biomarker','germline'),4):
        _stage_status(work,f'stage-{idx}',f'Stage {idx} of 9 — {domain} proforma'); domains[domain],cards_by_domain[domain]=stage_domain(work,domain,case,reg,diagnosis,eligible,profile)
    _stage_status(work,'stage-8','Stage 8 of 9 — semantic evidence matching and report synthesis')
    elements=_schema_elements(diagnosis,domains); enriched=stage_evidence(work,elements,cards_by_domain,reg,manifest,profile); statements=stage_reportable_sentences(work,enriched,profile); summary=stage_summary(work,statements,profile)
    _stage_status(work,'stage-9','Stage 9 of 9 — finalise report'); stage_final(work,case,summary,enriched,all_cards,digest,manifest); _print_usage(work); _stage_status(work,'complete','terraced-v4 complete'); return EXIT_OK

def run_pipeline_setting(pid):
    if pid is not None:
        plan=pipeline_registry.load(pid); s=load_settings(); s['pipeline']=plan.pipeline_id; _write(SETTINGS_PATH,json.dumps(s,indent=2)+'\n')
    plan=pipeline_registry.load(configured_pipeline()); print(f'PIPELINE={plan.pipeline_id}'); [print(x) for x in pipeline_registry.describe(plan)]; return EXIT_OK

def build_parser():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='command',required=True)
    s=sub.add_parser('setup'); s.add_argument('--mode',required=True,choices=['ngs-report','nel-demo','nel-validate','nel-validate-function','nel-validate-brief']); s.add_argument('--case-file',type=Path); s.add_argument('--example',type=int); s.add_argument('--case-id'); s.add_argument('--work-dir',type=Path); s.add_argument('--pipeline',choices=pipeline_registry.names())
    sub.add_parser('pipelines'); pc=sub.add_parser('pipeline-check'); pc.add_argument('--pipeline',required=True,choices=pipeline_registry.names()); pp=sub.add_parser('pipeline-plan'); pp.add_argument('--pipeline',required=True,choices=pipeline_registry.names()); ps=sub.add_parser('pipeline'); ps.add_argument('pipeline_id',nargs='?',choices=pipeline_registry.names()); r=sub.add_parser('run'); r.add_argument('--work-dir',type=Path)
    return p

def main(argv=None):
    global _EXECUTION_STARTED_AT; _EXECUTION_STARTED_AT=time.time(); args=build_parser().parse_args(argv)
    try:
        if args.command=='setup':
            if args.mode=='ngs-report' and args.case_file is None: raise StepFailure('ngs-report requires --case-file case.md')
            if args.mode=='nel-demo' and args.example is None: raise StepFailure('nel-demo requires --example N')
            if args.mode in VALIDATION_MODES and not args.case_id: raise StepFailure(f'{args.mode} requires --case-id ID')
            return run_setup(args)
        if args.command=='pipelines':
            for n,d in pipeline_registry.descriptions().items(): print(f'{n}: {d}')
            return EXIT_OK
        if args.command=='pipeline-check': pipeline_registry.load(args.pipeline); print(f'OK {args.pipeline}'); return EXIT_OK
        if args.command=='pipeline-plan':
            plan=pipeline_registry.load(args.pipeline); print(f'PIPELINE={plan.pipeline_id}'); [print(x) for x in pipeline_registry.describe(plan)]; return EXIT_OK
        if args.command=='pipeline': return run_pipeline_setting(args.pipeline_id)
        work=args.work_dir.expanduser().resolve() if args.work_dir else None
        if work is None:
            root=HERE/'runs'; c=sorted([x for x in root.iterdir() if x.is_dir()],key=lambda x:x.stat().st_mtime,reverse=True) if root.is_dir() else []
            if not c: raise StepFailure('no --work-dir given and no terraced-v4 runs exist')
            work=c[0]; _status(f'using most recent run directory: {work}')
        with _cli_logging(work): return run_pipeline(work)
    except Handoff as h: print(f'HANDOFF={h.call_id}'); print(f'PROMPT={h.prompt}'); print(f'OUTPUT={h.output}'); return EXIT_HANDOFF
    except (StepFailure,ValueError,OSError,KeyError,json.JSONDecodeError,yaml.YAMLError,syntax_repair.SyntaxRepairExhausted) as exc: print(f'terraced-v4 failed: {exc}',file=sys.stderr); return EXIT_FAILURE
if __name__=='__main__': raise SystemExit(main())
