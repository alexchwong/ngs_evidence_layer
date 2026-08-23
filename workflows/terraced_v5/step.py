#!/usr/bin/env python3
"""Terraced-v5 prototype: proformas -> semantic evidence -> sentence planning -> report."""
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
from workflows.terraced_v5 import card_identity, layout, model_client, pipeline_registry, prompt_loader, rendering, runtime, schema_validation

WORKFLOW_ID='terraced-v5'; RUN_STATE_SCHEMA_VERSION=1; HERE=Path(__file__).resolve().parent; PROMPTS=HERE/'prompts'
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
    if d.get('schema_version')!=2: raise StepFailure('unsupported terraced-v5 settings schema; expected 2')
    required={'retries','diagnosis','ptbg','reportability','summary','prompts'}
    missing=sorted(required-set(d))
    if missing: raise StepFailure(f'terraced-v5 settings missing required sections: {missing}')
    return d

def _setting(*keys):
    value=load_settings()
    for key in keys:
        if not isinstance(value,dict) or key not in value: raise StepFailure(f'missing terraced-v5 setting: {".".join(keys)}')
        value=value[key]
    return value

def _retry(name): return int(_setting('retries',name))
def configured_pipeline(): return str(load_settings().get('pipeline') or 'self')
def _prompt(name):
    rel=str(_setting('prompts',name))
    return prompt_loader.render(Path(rel),root=PROMPTS)
def _run_state_path(work): return _artifact(work,'run_state','terraced-v5-run.json',new=True)
def _load_run_state(work):
    d=json.loads(_read(_artifact(work,'run_state','terraced-v5-run.json')))
    if d.get('schema_version')!=RUN_STATE_SCHEMA_VERSION: raise StepFailure('incompatible terraced-v5 run state; start a fresh run')
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
    out=[f'# Terraced-v5 model operation — {call_id}','']
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
    attempts=int(max_attempts if max_attempts is not None else (_retry('fatal_model_attempts') if fatal else _retry('statement_generation_attempts'))); previous=None; last_error=feedback or ''
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
    cfg=_setting('diagnosis',authority); keys=list(cfg.get('publication_keys') or [])
    if authority in {'who5','icc'} and not keys: raise StepFailure(f'no diagnosis publication_keys configured for {authority!r}')
    return set(keys)

def _filter_diagnosis_authority(cards,authority):
    keys=_diagnosis_authority_publications(authority)
    return [c for c in cards if c.get('publication_key') in keys] if keys else list(cards)

def _disease_match(card,diseases,category):
    for disease in diseases:
        allowed={disease,*runtime.vocab.retrieval_related_diseases(disease,category)}
        if set(card.get('diseases') or []) & allowed: return True
    return False

def _draw_domain_cards(eligible,domain,genes,diseases):
    cfg=_setting('ptbg','domains',domain); category=str(cfg['card_category'])
    hits=[]; wanted=set(genes)
    for c in eligible:
        if c.get('category')!=category: continue
        mg=core_retrieval.match_genes(c,wanted)
        if domain=='germline':
            if mg: hits.append(c)
        elif _disease_match(c,diseases,category) and (mg or not c.get('genes')): hits.append(c)
    return sorted(hits,key=lambda x:x.get('card_id') or '')

def _allowed_diseases(work): return set(runtime.read_json(layout.setup(work,'allowed-schema-diseases.json'))['allowed_schema_diseases'])

def _variant_context(reg): return yaml.safe_dump({'variants':reg},sort_keys=False,allow_unicode=True,width=110)

def _negative_guidance_text(rows):
    out=[]
    for row in rows:
        guidance=row.get('negative_guidance') or []
        issues=row.get('issues') or []
        if guidance or issues:
            out.append({'schema_id':row.get('schema_id'),'do_not_repeat':guidance,'audit_issues':issues})
    return yaml.safe_dump({'previous_audit_negative_guidance':out},sort_keys=False,allow_unicode=True,width=110)

def _variant_display_fields():
    # `reporting.variant_display_fields` is configurable in v5 settings.  The
    # fallback preserves compatibility with settings files created before this
    # display/provenance separation was introduced.
    fields=(load_settings().get('reporting') or {}).get('variant_display_fields') or ['description','gene']
    return [str(field) for field in fields if str(field).strip()]


def _variant_display(reg, variant_id):
    row=reg.get(variant_id) or {}
    for field in _variant_display_fields():
        value=row.get(field)
        if isinstance(value,str) and value.strip(): return value.strip()
    # This should only be reachable for malformed legacy registries.  Keep the
    # internal ID out of reportable text even in that case.
    return 'reported variant'


def _render_statement_text(text, reg):
    """Render internal variant IDs as human-readable identities for prose input."""
    rendered=str(text)
    # Longest IDs first avoids accidental partial replacement if an external
    # configuration ever uses variable-width identifiers.
    for variant_id in sorted(reg,key=len,reverse=True):
        display=_variant_display(reg,variant_id)
        rendered=re.sub(rf'(?<![A-Za-z0-9_]){re.escape(variant_id)}(?![A-Za-z0-9_])',lambda _m,d=display:d,rendered)
    return rendered


def _statement_public(elements, reg):
    rows=[]
    for e in elements:
        variants=e.get('variants',[])
        rows.append({
            'schema_id':e['schema_id'],
            'domain':e['domain'],
            'proposition':_render_statement_text(e['proposition'],reg),
            'reasons':[_render_statement_text(reason,reg) for reason in e['reasons']],
            'variant_display':[_variant_display(reg,variant_id) for variant_id in variants],
        })
    return rows

def _generate_and_audit_statements(work,block_key,elements,case,reg,profile):
    """Generate atomic statements, then audit proposition/reason coherence.

    Returns (elements_with_statement, proforma_regeneration_needed, negative_guidance).
    Statement-only semantic drift is regenerated de novo here.  A reasoning
    failure belongs to the preceding proforma and is returned to its caller.
    """
    if not elements: return [],False,[]
    max_regen=_retry('statement_regenerations'); negative=[]
    source=_statement_public(elements,reg)
    for regen in range(max_regen+1):
        sid=f'{block_key}-statement-generation-a{regen+1}'
        out=_artifact(work,'statement_generation',f'{sid}.yaml',new=True)
        prompt=_prompt('statement_generation')+'\n\n# Proforma elements\n```yaml\n'+yaml.safe_dump({'items':source},sort_keys=False,allow_unicode=True,width=110)+'```\n'
        if negative:
            prompt+='\n# Negative guidance from the previous semantic audit\nDo not edit or copy the rejected statements. Generate all statements de novo from the original proforma elements.\n```yaml\n'+_negative_guidance_text(negative)+'```\n'
        try:
            _model_call(work,call_id=sid,role='statement_generation',prompt=prompt,output=out,validator=lambda t,it=source:schema_validation.validate_statement_generation_batch(t,it),profile=profile,fatal=False,max_attempts=_retry('statement_generation_attempts'))
            rows=yaml.safe_load(_read(out))['statements']
        except StepFailure as exc:
            _risk(work,stage='statement_generation',risk_type='statement_generation_failure',message=str(exc),schema_element=block_key,attempts=regen+1,action='marked_semantically_unresolved',human_review='required')
            public_by_id={row['schema_id']:row for row in source}
            failed=[dict(e,statement=public_by_id[e['schema_id']]['proposition'],semantic_status='unsupported',statement_audit=None) for e in elements]
            return failed,False,[]
        amap={r['schema_id']:r['statement'] for r in rows}
        audit_items=[{**src,'statement':amap[src['schema_id']]} for src in source]
        aid=f'{block_key}-statement-audit-a{regen+1}'; apath=_artifact(work,'statement_audits',f'{aid}.yaml',new=True)
        aprompt=_prompt('statement_audit')+'\n\n# Structured case context\n```json\n'+json.dumps(case,indent=2,ensure_ascii=False)+'\n```\n\n# Proforma elements and generated statements\n```yaml\n'+yaml.safe_dump({'items':audit_items},sort_keys=False,allow_unicode=True,width=110)+'```\n'
        try:
            _model_call(work,call_id=aid,role='statement_audit',prompt=aprompt,output=apath,validator=lambda t,it=audit_items:schema_validation.validate_statement_audit_batch(t,it),profile=profile,fatal=False,max_attempts=_retry('statement_audit_attempts'))
            audits=yaml.safe_load(_read(apath))['audits']
        except StepFailure as exc:
            _risk(work,stage='statement_audit',risk_type='statement_audit_failure',message=str(exc),schema_element=block_key,attempts=regen+1,action='marked_semantically_unresolved',human_review='required')
            failed=[dict(e,statement=amap[e['schema_id']],semantic_status='unsupported',statement_audit=None) for e in elements]
            return failed,False,[]
        audit_map={a['schema_id']:a for a in audits}
        proforma_fail=[a for a in audits if a['reasoning_status']=='unsupported']
        if proforma_fail:
            return [dict(e,statement=amap[e['schema_id']],semantic_status=audit_map[e['schema_id']]['reasoning_status'],statement_audit=audit_map[e['schema_id']]) for e in elements],True,proforma_fail
        statement_fail=[a for a in audits if not a['statement_represents_proforma']]
        if not statement_fail:
            return [dict(e,statement=amap[e['schema_id']],semantic_status=audit_map[e['schema_id']]['reasoning_status'],statement_audit=audit_map[e['schema_id']]) for e in elements],False,[]
        negative=statement_fail
        if regen>=max_regen:
            bad={a['schema_id'] for a in statement_fail}
            for a in statement_fail:
                _risk(work,stage='statement_audit',risk_type='statement_representation_unresolved',message='; '.join(a.get('issues') or a.get('negative_guidance') or ['statement did not faithfully represent proforma']),schema_element=a['schema_id'],attempts=regen+1,action='suppressed_from_automatic_reporting',human_review='required')
            return [dict(e,statement=amap[e['schema_id']],semantic_status='unsupported' if e['schema_id'] in bad else audit_map[e['schema_id']]['reasoning_status'],statement_audit=audit_map[e['schema_id']]) for e in elements],False,[]
    raise AssertionError('unreachable statement regeneration loop')

def _who5_elements(who):
    return [{'schema_id':f'DX-WHO5-{i:02d}','domain':'diagnosis','proposition':f'WHO5 classification: {row["diagnosis"]}.','reasons':row['reasons'],'evidence_domain':'diagnosis_who5','positive_effect':False} for i,row in enumerate(who['diagnoses'],1)]

def _icc_elements(icc):
    els=[{'schema_id':f'DX-ICC-{i:02d}','domain':'diagnosis','proposition':f'ICC classification: {row["diagnosis"]}.','reasons':row['reasons'],'evidence_domain':'diagnosis_icc','positive_effect':False} for i,row in enumerate(icc['diagnoses'],1)]
    comp=icc['comparison_with_who5']
    els.append({'schema_id':'DX-CONCORDANCE','domain':'diagnosis','proposition':'WHO5 and ICC are significantly different.' if comp['significantly_different'] else 'WHO5 and ICC are not significantly different.','reasons':[comp['explanation']],'evidence_domain':'diagnosis_icc','positive_effect':False})
    return els

def _other_elements(other):
    row=other['concurrent_second_diagnosis']; answer=row['answer']
    if answer.strip().lower() in {'none','none supported','no concurrent second diagnosis supported'}: return []
    return [{'schema_id':'DX-CONCURRENT','domain':'diagnosis','proposition':answer,'reasons':row['reasons'],'evidence_domain':'diagnosis_other','positive_effect':False}]

def _domain_elements(domain,doc):
    cfg=_setting('ptbg','domains',domain); positive=set(cfg.get('positive_buckets') or []); els=[]
    if domain=='prognosis':
        for bucket in ('favorable','adverse','other','uncertain'):
            for i,row in enumerate(doc[bucket],1):
                els.append({'schema_id':f'PX-{bucket.upper()}-{i:02d}','domain':'prognosis','proposition':f'{bucket} prognostic contribution for {", ".join(row["variants"])}','reasons':[row['reason']],'variants':row['variants'],'evidence_domain':'prognosis','positive_effect':bucket in positive})
        els.append({'schema_id':'PX-OVERALL','domain':'prognosis','proposition':doc['overall']['classification'],'reasons':[doc['overall']['reason']],'evidence_domain':'prognosis','positive_effect':bool(cfg.get('overall_requires_evidence',False))})
    elif domain=='treatment':
        for bucket in ('drug_target','drug_resistance','other'):
            for i,row in enumerate(doc[bucket],1):
                prop=f'{bucket.replace("_"," ")} for {", ".join(row["variants"])}'+(f' — {row.get("therapy")}' if row.get('therapy') else '')
                els.append({'schema_id':f'TX-{bucket.upper()}-{i:02d}','domain':'treatment','proposition':prop,'reasons':[row['reason']],'variants':row['variants'],'evidence_domain':'treatment','positive_effect':bucket in positive})
    elif domain=='biomarker':
        for bucket in ('suitable_mrd','unsuitable_mrd','uncertain'):
            for i,row in enumerate(doc[bucket],1):
                els.append({'schema_id':f'MRD-{bucket.upper()}-{i:02d}','domain':'biomarker','proposition':f'{bucket.replace("_"," ")} for {", ".join(row["variants"])}','reasons':[row['reason']],'variants':row['variants'],'evidence_domain':'biomarker','positive_effect':bucket in positive})
    elif domain=='germline':
        for bucket in ('suspect','uncertain'):
            for i,row in enumerate(doc[bucket],1):
                els.append({'schema_id':f'GL-{bucket.upper()}-{i:02d}','domain':'germline','proposition':f'{bucket} germline origin for {", ".join(row["variants"])}','reasons':[row['reason']],'variants':row['variants'],'evidence_domain':'germline','positive_effect':bucket in positive})
        for row in doc['clinical_support']:
            target=set(row['variants'])
            for el in els:
                if target & set(el.get('variants') or []): el['reasons'].append(f'Clinical syndrome support ({row["support"]}): {row["reason"]}')
    else: raise StepFailure(f'unsupported PTBG domain {domain!r}')
    return els

def _semantic_guidance_block(rows):
    return '\n# Negative semantic guidance from prior audit\nThe prior proforma failed semantic review. Regenerate the complete proforma de novo from the original case/evidence. Do not copy or edit the rejected proforma. Do not repeat these reasoning mistakes, and do not treat the auditor as prescribing the replacement answer.\n```yaml\n'+_negative_guidance_text(rows)+'```\n'

def stage_diagnosis(work,case,eligible,profile):
    allowed=_allowed_diseases(work); genes=runtime.case_genes(case); bootstrap=list(case.get('bootstrap_cmcs') or [])
    max_cmc=int(_setting('diagnosis','who5','max_cmc_passes')); cmc_history=list(bootstrap); prior=list(bootstrap); final_who=None; who_cards=[]; authoritative_pass=1
    for pass_idx in range(1,max_cmc+1):
        who_cards=_filter_diagnosis_authority(_draw_diagnosis_cards(eligible,genes,cmc_history),'who5')
        path=_existing_or_new(work,f'diagnosis_who5_pass_{pass_idx}','who5.yaml')
        pass_note='WHO5 pass 1: classify from scratch.' if pass_idx==1 else f'WHO5 pass {pass_idx}: CMC changed. START FROM SCRATCH; do not anchor on earlier answers.'
        prompt=_prompt('diagnosis_who5')+f'\n\n# Pass\n{pass_note}\n\n# Cumulative CMC recall\n```yaml\n'+yaml.safe_dump(cmc_history,sort_keys=False)+'```\n\n# Structured case\n```json\n'+json.dumps(case,indent=2,ensure_ascii=False)+'\n```\n\n# Allowed WHO5 schema diseases\n'+yaml.safe_dump(sorted(allowed))+'\n# Configured WHO5 authority cards\n'+_render_cards(who_cards)
        _model_call(work,call_id=f'diagnosis-who5-pass-{pass_idx:02d}',role='diagnosis',prompt=prompt,output=path,validator=lambda t:schema_validation.validate_who5_diagnosis(t,allowed_diseases=allowed),profile=profile,proforma=True)
        final_who=yaml.safe_load(_read(path)); cmcs=runtime.derive_cmcs(final_who); authoritative_pass=pass_idx
        if cmcs==prior: break
        for cmc in cmcs:
            if cmc not in cmc_history: cmc_history.append(cmc)
        if pass_idx==max_cmc:
            _risk(work,stage='diagnosis',risk_type='cmc_changed_at_configured_pass_limit',message=f'WHO5 pass {pass_idx} changed CMCs from {prior} to {cmcs}; settings cap who5.max_cmc_passes={max_cmc}.',action='continued_with_last_who5_pass_as_authoritative',human_review='recommended')
            break
        prior=cmcs
    assert final_who is not None

    # Semantic proforma regeneration for authoritative WHO5 if its reasons do not justify its statements.
    sem_cap=_retry('semantic_proforma_regenerations'); sem_round=0
    while True:
        who_elements,need,guidance=_generate_and_audit_statements(work,f'diagnosis-who5-proforma-{sem_round:02d}',_who5_elements(final_who),case,{},profile)
        if not need: break
        if sem_round>=sem_cap:
            for row in guidance: _risk(work,stage='statement_audit',risk_type='who5_reasoning_unresolved',message='; '.join(row.get('issues') or row.get('negative_guidance') or ['WHO5 reason did not justify statement']),schema_element=row['schema_id'],attempts=sem_round+1,action='suppressed_from_automatic_reporting',human_review='required')
            break
        sem_round+=1
        for cmc in runtime.derive_cmcs(final_who):
            if cmc not in cmc_history: cmc_history.append(cmc)
        who_cards=_filter_diagnosis_authority(_draw_diagnosis_cards(eligible,genes,cmc_history),'who5')
        path=_artifact(work,'diagnosis_who5_semantic',f'who5-rewrite-{sem_round:02d}.yaml',new=True)
        prompt=_prompt('diagnosis_who5')+'\n\n# Semantic regeneration\nRegenerate authoritative WHO5 classification from scratch.\n\n# Cumulative CMC recall\n```yaml\n'+yaml.safe_dump(cmc_history,sort_keys=False)+'```\n\n# Structured case\n```json\n'+json.dumps(case,indent=2,ensure_ascii=False)+'\n```\n\n# Allowed WHO5 schema diseases\n'+yaml.safe_dump(sorted(allowed))+'\n# Configured WHO5 authority cards\n'+_render_cards(who_cards)+_semantic_guidance_block(guidance)
        _model_call(work,call_id=f'diagnosis-who5-semantic-rewrite-{sem_round:02d}',role='diagnosis',prompt=prompt,output=path,validator=lambda t:schema_validation.validate_who5_diagnosis(t,allowed_diseases=allowed),profile=profile,proforma=True)
        final_who=yaml.safe_load(_read(path))
    final_cmcs=runtime.derive_cmcs(final_who)
    for cmc in final_cmcs:
        if cmc not in cmc_history: cmc_history.append(cmc)

    icc_cards=_filter_diagnosis_authority(_draw_diagnosis_cards(eligible,genes,cmc_history),'icc'); icc_sem=0; icc_guidance=[]; icc_full=None; icc_elements=[]
    while True:
        path=_artifact(work,'diagnosis_icc',f'icc-semantic-{icc_sem:02d}.yaml',new=True)
        prompt=_prompt('diagnosis_icc')+'\n\n# Structured case\n```json\n'+json.dumps(case,indent=2,ensure_ascii=False)+'\n```\n\n# Authoritative WHO5 result — comparison only\n```yaml\n'+yaml.safe_dump(final_who,sort_keys=False,allow_unicode=True,width=110)+'```\n\n# Configured ICC authority cards\n'+_render_cards(icc_cards)
        if icc_guidance: prompt+=_semantic_guidance_block(icc_guidance)
        _model_call(work,call_id='diagnosis-icc' if icc_sem==0 else f'diagnosis-icc-semantic-rewrite-{icc_sem:02d}',role='diagnosis',prompt=prompt,output=path,validator=schema_validation.validate_icc_diagnosis,profile=profile,proforma=True)
        icc_full=yaml.safe_load(_read(path)); icc_elements,need,icc_guidance=_generate_and_audit_statements(work,f'diagnosis-icc-proforma-{icc_sem:02d}',_icc_elements(icc_full),case,{},profile)
        if not need: break
        if icc_sem>=sem_cap:
            for row in icc_guidance: _risk(work,stage='statement_audit',risk_type='icc_reasoning_unresolved',message='; '.join(row.get('issues') or row.get('negative_guidance') or ['ICC reason did not justify statement']),schema_element=row['schema_id'],attempts=icc_sem+1,action='suppressed_from_automatic_reporting',human_review='required')
            break
        icc_sem+=1

    other_cards=_filter_diagnosis_authority(_draw_diagnosis_cards(eligible,genes,cmc_history),'other'); other_sem=0; other_guidance=[]; other=None; other_elements=[]
    while True:
        path=_artifact(work,'diagnosis_other',f'other-semantic-{other_sem:02d}.yaml',new=True)
        prompt=_prompt('diagnosis_other')+'\n\n# Structured case\n```json\n'+json.dumps(case,indent=2,ensure_ascii=False)+'\n```\n\n# Authoritative WHO5 result\n```yaml\n'+yaml.safe_dump(final_who,sort_keys=False,allow_unicode=True,width=110)+'```\n'
        if bool(_setting('diagnosis','other','supply_cards_to_proforma')): prompt+='\n# Configured other-diagnosis cards\n'+_render_cards(other_cards)
        if other_guidance: prompt+=_semantic_guidance_block(other_guidance)
        _model_call(work,call_id='diagnosis-other-considerations' if other_sem==0 else f'diagnosis-other-semantic-rewrite-{other_sem:02d}',role='diagnosis',prompt=prompt,output=path,validator=schema_validation.validate_other_diagnosis,profile=profile,proforma=True)
        other=yaml.safe_load(_read(path)); other_elements,need,other_guidance=_generate_and_audit_statements(work,f'diagnosis-other-proforma-{other_sem:02d}',_other_elements(other),case,{},profile)
        if not need: break
        if other_sem>=sem_cap:
            for row in other_guidance: _risk(work,stage='statement_audit',risk_type='other_diagnosis_reasoning_unresolved',message='; '.join(row.get('issues') or row.get('negative_guidance') or ['Other-diagnosis reason did not justify statement']),schema_element=row['schema_id'],attempts=other_sem+1,action='suppressed_from_automatic_reporting',human_review='required')
            break
        other_sem+=1

    comp=icc_full['comparison_with_who5']
    diagnosis={'who5':final_who,'icc':{'diagnoses':icc_full['diagnoses']},'concordance':{'answer':'WHO5 and ICC are significantly different.' if comp['significantly_different'] else 'WHO5 and ICC are not significantly different.','reasons':[comp['explanation']]},'concurrent_second_diagnosis':other['concurrent_second_diagnosis']}
    _write(_existing_or_new(work,'diagnosis','diagnosis-final.yaml'),yaml.safe_dump(diagnosis,sort_keys=False,allow_unicode=True,width=110))
    routing={'bootstrap_cmcs':bootstrap,'who5_authoritative_pass':authoritative_pass,'final_cmcs':final_cmcs,'diagnostic_cmc_history':cmc_history,'who5_max_cmc_passes':max_cmc}
    _write(_existing_or_new(work,'diagnosis','routing.json'),json.dumps(routing,indent=2,ensure_ascii=False)+'\n')
    elements=who_elements+icc_elements+other_elements
    _write(_existing_or_new(work,'statement_generation','diagnosis-elements.yaml'),yaml.safe_dump({'elements':elements},sort_keys=False,allow_unicode=True,width=110))
    return diagnosis,final_cmcs,{'diagnosis_who5':who_cards,'diagnosis_icc':icc_cards,'diagnosis_other':other_cards},elements

def stage_domain(work,domain,case,reg,diagnosis,eligible,profile):
    valid=set(reg); diseases=[r['schema_disease'] for r in diagnosis['who5']['diagnoses']]; cards=_draw_domain_cards(eligible,domain,runtime.case_genes(case),diseases)
    validator={'prognosis':schema_validation.validate_prognosis,'treatment':schema_validation.validate_treatment,'biomarker':schema_validation.validate_biomarker,'germline':schema_validation.validate_germline}[domain]
    base=_prompt(domain)+'\n# Variant registry\n```yaml\n'+_variant_context(reg)+'```\n\n# Structured case\n```json\n'+json.dumps(case,indent=2,ensure_ascii=False)+'\n```\n\n# Authoritative diagnosis\n```yaml\n'+yaml.safe_dump(diagnosis,sort_keys=False,allow_unicode=True,width=110)+'```\n\n# Candidate evidence cards\n'+_render_cards(cards)
    sem_cap=_retry('semantic_proforma_regenerations'); guidance=[]; accepted=None; elements=[]
    for sem in range(sem_cap+1):
        out=_artifact(work,f'{domain}_state',f'proforma-semantic-{sem:02d}.yaml',new=True)
        prompt=base+(_semantic_guidance_block(guidance) if guidance else '')
        call_id=domain if sem==0 else f'{domain}-semantic-rewrite-{sem:02d}'
        _model_call(work,call_id=call_id,role='ptbg',prompt=prompt,output=out,validator=lambda t:validator(t,valid),profile=profile,proforma=True)
        accepted=yaml.safe_load(_read(out)); raw_elements=_domain_elements(domain,accepted)
        elements,need,guidance=_generate_and_audit_statements(work,f'{domain}-proforma-{sem:02d}',raw_elements,case,reg,profile)
        if not need: break
        if sem==sem_cap:
            for row in guidance:
                _risk(work,stage='statement_audit',risk_type='proforma_reasoning_unresolved',message='; '.join(row.get('issues') or row.get('negative_guidance') or ['reason did not justify statement']),schema_element=row['schema_id'],attempts=sem+1,action='suppressed_from_automatic_reporting',human_review='required')
    canonical=_existing_or_new(work,f'{domain}_state','proforma.yaml'); _write(canonical,yaml.safe_dump(accepted,sort_keys=False,allow_unicode=True,width=110))
    _write(_existing_or_new(work,'statement_generation',f'{domain}-elements.yaml'),yaml.safe_dump({'elements':elements},sort_keys=False,allow_unicode=True,width=110))
    return accepted,cards,elements

def _candidate_cards_for_element(el,cards_by_domain,reg):
    cards=list(cards_by_domain.get(el['evidence_domain']) or []); variants=el.get('variants') or []; genes={reg[v]['gene'] for v in variants if v in reg}
    if genes:
        gene_cards=[c for c in cards if not c.get('genes') or genes & set(c.get('genes') or [])]
        if gene_cards: cards=gene_cards
    return cards

def _card_match_view(card):
    return {'card_id':card.get('card_id'),'category':card.get('category'),'genes':card.get('genes') or [],'diseases':card.get('diseases') or [],'evidence_tier':card.get('evidence_tier'),'interpretation':card.get('interpretation') or '','source_hint':card.get('paper_nickname') or card.get('citation_display') or ''}

def _batch_match_prompt(items,card_catalog,state):
    public=[]
    for item in items:
        row={'evidence_id':item['evidence_id'],'schema_id':item['schema_id'],'statement':item['statement'],'reason':item['reason'],'candidate_card_ids':item['candidate_card_ids']}
        st=state.get(item['evidence_id']) or {}
        if st.get('previous_objection'): row['previous_auditor_concern']={'previous_card_id':st.get('previous_card_id'),'non_authoritative':True,'concern':st['previous_objection']}
        public.append(row)
    ids=[]
    for row in public:
        for cid in row['candidate_card_ids']:
            if cid not in ids: ids.append(cid)
    cards=[_card_match_view(card_catalog[cid]) for cid in ids]
    return _prompt('evidence_match')+'\n\n# Evidence items\n```yaml\n'+yaml.safe_dump({'items':public},sort_keys=False,allow_unicode=True,width=110)+'```\n\n# Candidate card catalog\n```yaml\n'+yaml.safe_dump({'cards':cards},sort_keys=False,allow_unicode=True,width=110)+'```\n'

def _batch_audit_prompt(items,matches,card_catalog):
    mmap={m['evidence_id']:m for m in matches}; rows=[]
    for item in items:
        match=mmap[item['evidence_id']]; rows.append({'evidence_id':item['evidence_id'],'schema_id':item['schema_id'],'statement':item['statement'],'reason':item['reason'],'source':match['source'],'quote':match['quote'],'selected_card':_card_match_view(card_catalog[match['card_id']])})
    return _prompt('evidence_audit')+'\n\n# Selected evidence pairs\n```yaml\n'+yaml.safe_dump({'items':rows},sort_keys=False,allow_unicode=True,width=110)+'```\n'

def stage_evidence(work,elements,cards_by_domain,reg,manifest,profile):
    tag_by_id=card_identity.tag_by_id(manifest); enriched=[dict(el,evidence=[]) for el in elements]; records=[]; card_catalog={}; counter=0
    for ei,el in enumerate(elements):
        if el.get('semantic_status')=='unsupported': continue
        candidates=_candidate_cards_for_element(el,cards_by_domain,reg)
        for ri,reason in enumerate(el['reasons'],1):
            if reason.startswith('Clinical syndrome support ('):
                enriched[ei]['evidence'].append({'_reason_index':ri,'reason':reason,'status':'case_only','card_id':None,'card_tag':None,'source':None,'quote':None,'audit':None}); continue
            if not candidates:
                _risk(work,stage='evidence',risk_type='no_candidate_cards',message='No candidate evidence cards were available for this reason.',schema_element=el['schema_id'],action='continued_without_resolved_evidence',human_review='required')
                enriched[ei]['evidence'].append({'_reason_index':ri,'reason':reason,'status':'unresolved','card_id':None,'card_tag':None,'source':None,'quote':None,'audit':None}); continue
            counter+=1; evid=f'E{counter:04d}'
            for card in candidates: card_catalog[card['card_id']]=card
            records.append({'evidence_id':evid,'element_index':ei,'reason_index':ri,'schema_id':el['schema_id'],'statement':el['statement'],'reason':reason,'candidate_card_ids':[c['card_id'] for c in candidates]})
    results={}; pending=list(records); state={}; max_rounds=_retry('evidence_match_rounds')
    for attempt in range(1,max_rounds+1):
        if not pending: break
        match_path=_artifact(work,'evidence_matches',f'batch-match-attempt-{attempt:02d}.yaml',new=True); prompt=_batch_match_prompt(pending,card_catalog,state)
        try:
            _model_call(work,call_id=f'evidence-match-batch-a{attempt}',role='evidence_match',prompt=prompt,output=match_path,validator=lambda t,it=list(pending):schema_validation.validate_evidence_match_batch(t,it),profile=profile,fatal=False,max_attempts=_retry('evidence_match_model_attempts'))
            matches=yaml.safe_load(_read(match_path))['matches']
        except StepFailure as exc:
            for item in pending:
                _risk(work,stage='evidence',risk_type='evidence_match_structural_failure',message=str(exc),schema_element=item['schema_id'],attempts=attempt,action='continued_unresolved',human_review='required')
                results[item['evidence_id']]={'reason':item['reason'],'status':'unresolved','card_id':None,'card_tag':None,'source':None,'quote':None,'audit':None}
            pending=[]; break
        audit_path=_artifact(work,'evidence_audits',f'batch-audit-attempt-{attempt:02d}.yaml',new=True); aprompt=_batch_audit_prompt(pending,matches,card_catalog)
        try:
            _model_call(work,call_id=f'evidence-audit-batch-a{attempt}',role='evidence_audit',prompt=aprompt,output=audit_path,validator=lambda t,it=list(pending):schema_validation.validate_evidence_audit_batch(t,it),profile=profile,fatal=False,max_attempts=_retry('evidence_audit_model_attempts'))
            audits=yaml.safe_load(_read(audit_path))['audits']
        except StepFailure as exc:
            audits=[{'evidence_id':item['evidence_id'],'quote_supports_statement':False,'quote_supports_reason':False,'risk':'warning','comments':['Evidence audit unavailable after bounded retries: '+str(exc)]} for item in pending]
            _risk(work,stage='evidence',risk_type='evidence_audit_unavailable',message=str(exc),attempts=attempt,action='continued_unresolved',human_review='required')
        mmap={m['evidence_id']:m for m in matches}; amap={a['evidence_id']:a for a in audits}; next_pending=[]
        for item in pending:
            evid=item['evidence_id']; chosen=mmap[evid]; audit=amap[evid]; supports=bool(audit['quote_supports_statement'] and audit['quote_supports_reason'])
            if audit['risk']=='warning': _risk(work,stage='evidence',risk_type='citation_fidelity',message='; '.join(audit['comments']) or 'Evidence auditor flagged a fidelity concern.',schema_element=item['schema_id'],attempts=attempt,action='retained_if_support_checks_pass',human_review='recommended')
            if supports:
                results[evid]={'reason':item['reason'],'status':'matched','card_id':chosen['card_id'],'card_tag':f'[card:{tag_by_id[chosen["card_id"]]}]','source':chosen['source'],'quote':chosen['quote'],'audit':audit,'resolution':'accepted'}; continue
            objection='; '.join(audit['comments']) or 'Selected quote did not support both the statement and its reason.'; st=state.setdefault(evid,{})
            if attempt<max_rounds:
                st['previous_objection']=objection; st['previous_card_id']=chosen['card_id']; next_pending.append(item)
                _risk(work,stage='evidence',risk_type='evidence_support_failure',message=objection,schema_element=item['schema_id'],attempts=attempt,action='rematched_with_negative_guidance',human_review='recommended')
            else:
                if st.get('previous_card_id')==chosen['card_id']:
                    _risk(work,stage='evidence',risk_type='evidence_auditor_matcher_disagreement',message=f'Matcher repeatedly selected {chosen["card_id"]} despite audit failure: {objection}',schema_element=item['schema_id'],attempts=attempt,action='continued_unresolved',human_review='required')
                results[evid]={'reason':item['reason'],'status':'unresolved','card_id':chosen['card_id'],'card_tag':None,'source':chosen['source'],'quote':chosen['quote'],'audit':audit}
        pending=next_pending
    for item in records:
        ev=dict(results.get(item['evidence_id']) or {'reason':item['reason'],'status':'unresolved','card_id':None,'card_tag':None,'source':None,'quote':None,'audit':None}); ev['_reason_index']=item['reason_index']; enriched[item['element_index']]['evidence'].append(ev)
    for row in enriched:
        row['evidence'].sort(key=lambda ev:ev.get('_reason_index',9999))
        for ev in row['evidence']: ev.pop('_reason_index',None)
    _write(_existing_or_new(work,'evidence_enriched','schema-elements.yaml'),yaml.safe_dump({'elements':enriched},sort_keys=False,allow_unicode=True,width=110)); return enriched

def stage_reportable_sentences(work,elements):
    statements=[]; suppressed=[]
    for el in elements:
        reason_status=el.get('semantic_status')
        if reason_status=='unsupported':
            suppressed.append({'schema_id':el['schema_id'],'reason':'semantic statement/reason audit unresolved'}); _risk(work,stage='reportability',risk_type='semantic_unresolved_suppressed',message='Statement/reason semantic audit remained unsupported after bounded de-novo regeneration.',schema_element=el['schema_id'],action='suppressed_from_final_report',human_review='required'); continue
        if el.get('positive_effect'):
            literature=[ev for ev in el.get('evidence') or [] if ev.get('status')!='case_only']
            resolved=bool(literature) and all(ev.get('status')=='matched' for ev in literature)
            if not resolved:
                suppressed.append({'schema_id':el['schema_id'],'reason':'positive PTBG statement not evidence-resolved'}); _risk(work,stage='reportability',risk_type='positive_ptbg_unresolved_suppressed',message='Positive PTBG statement was not affirmatively evidence-resolved.',schema_element=el['schema_id'],action='suppressed_from_final_report',human_review='required'); continue
        tags=[]
        for ev in el.get('evidence') or []:
            tag=ev.get('card_tag')
            if tag and tag not in tags: tags.append(tag)
        statements.append({'schema_id':el['schema_id'],'domain':el['domain'],'statement':el['statement'].strip().rstrip('.')+'.','reason':' | '.join(el['reasons']),'card_tags':tags,'semantic_status':reason_status})
    for i,row in enumerate(statements,1): row['statement_id']=f'S{i:04d}'
    _write(_existing_or_new(work,'reportable_sentences','statements.yaml'),yaml.safe_dump({'statements':statements,'suppressed':suppressed},sort_keys=False,allow_unicode=True,width=110)); return statements


def _validate_summary_plan_audit(text):
    try: d=yaml.safe_load(text)
    except yaml.YAMLError as exc: raise ValueError(f'summary-plan audit: invalid YAML: {exc}') from exc
    out=[]
    if not isinstance(d,dict):
        safe=runtime._single_mapping_list(d); out.append(validated_model_task.ValidationIssue('summary-plan audit',f'expected mapping; received {type(d).__name__}','remove the extra one-item list wrapper without changing fields or values' if safe else 'return the required mapping',repair_class='serialization' if safe else 'content',received=repr(d),expected='mapping')); d={}
    expected={'preserved','unnecessarily_fragmented','issues'}; missing=sorted(expected-set(d)); extra=sorted(set(d)-expected)
    if missing or extra: out.append(validated_model_task.ValidationIssue('summary-plan audit',f'missing fields {missing}; unexpected fields {extra}',f'return exactly {sorted(expected)}',repair_class='content'))
    preserved=d.get('preserved'); fragmented=d.get('unnecessarily_fragmented')
    for field,value in (('preserved',preserved),('unnecessarily_fragmented',fragmented)):
        if not isinstance(value,bool):
            safe=runtime._bool_repairable(value); out.append(validated_model_task.ValidationIssue(field,f'expected boolean; received {type(value).__name__}','serialize the existing true/false decision as a YAML boolean' if safe else 'return the required true/false decision',repair_class='serialization' if safe else 'content',received=repr(value),expected='true or false'))
    rows=d.get('issues')
    if not isinstance(rows,list):
        safe=isinstance(rows,dict); out.append(validated_model_task.ValidationIssue('issues',f'expected list; received {type(rows).__name__}','wrap the existing single issue mapping in a list without changing it' if safe else 'return issues as a list of target/issue mappings',repair_class='serialization' if safe else 'content',received=repr(rows),expected='list')); rows=[]
    for i,row in enumerate(rows):
        path=f'issues[{i}]'
        if not isinstance(row,dict): out.append(validated_model_task.ValidationIssue(path,f'expected mapping; received {type(row).__name__}','return one mapping with target and issue',repair_class='content')); continue
        miss=sorted({'target','issue'}-set(row)); extra=sorted(set(row)-{'target','issue'})
        if miss or extra: out.append(validated_model_task.ValidationIssue(path,f'missing fields {miss}; unexpected fields {extra}',"return exactly ['issue', 'target']",repair_class='content'))
        for field in ('target','issue'):
            value=row.get(field)
            if not isinstance(value,str) or not value.strip(): out.append(validated_model_task.ValidationIssue(f'{path}.{field}',f'expected non-empty string; received {type(value).__name__}',f'return a non-empty {field} string',repair_class='content'))
    if (preserved is False or fragmented is True) and not rows: out.append(validated_model_task.ValidationIssue('issues','failed preservation/fragmentation audit requires at least one actionable issue','identify the affected statement/block and the semantic or fragmentation problem; do not write replacement prose',repair_class='content'))
    if preserved is True and fragmented is False and rows: out.append(validated_model_task.ValidationIssue('issues','clean audit requires issues: []','return issues: []',repair_class='content'))
    validated_model_task.fail('summary-plan audit',out); return 'summary-plan audit structurally valid'

def _fallback_summary_plan(statements):
    dispositions=[]; parts=[]
    for i,statement in enumerate(statements,1):
        dispositions.append({'statement_id':statement['statement_id'],'decision':'include','reason':None}); parts.append({'statement_id':statement['statement_id'],'group':f'F{i:04d}','split_text':None})
    plan={'dispositions':dispositions,'parts':parts}; runtime.validate_summary_plan_doc(plan,statements,allow_cross_domain_merge=bool(_setting('summary','allow_cross_domain_merge'))); return plan

def _summary_blocks(plan,statements):
    return runtime.build_summary_blocks(plan,statements,domain_order=list(_setting('summary','domain_order')),allow_cross_domain_merge=bool(_setting('summary','allow_cross_domain_merge')))

def stage_summary(work,statements,case,profile):
    if not statements:
        final={'dispositions':[],'sentences':[]}; _write(_existing_or_new(work,'summary','summary-final.yaml'),yaml.safe_dump(final,sort_keys=False)); return final
    allow_cross=bool(_setting('summary','allow_cross_domain_merge')); plan=None; blocks=None; negative=[]; semantic_cap=_retry('summary_plan_regenerations'); frag_cap=_retry('summary_plan_fragmentation_regenerations'); frag_used=0
    for sem in range(semantic_cap+1):
        call_id='summary-plan' if sem==0 else f'summary-plan-regenerate-{sem:02d}'; path=_artifact(work,'summary',f'summary-plan-attempt-{sem+1:02d}.yaml',new=True)
        policy={'allow_cross_domain_merge':allow_cross,'domain_order':list(_setting('summary','domain_order')),'prefer_fewest_readable_sentences':bool(_setting('summary','prefer_fewest_readable_sentences'))}
        prompt=_prompt('summary_plan')+'\n\n# Workflow summary policy\n```yaml\n'+yaml.safe_dump(policy,sort_keys=False)+'```\n\n# Reportable statements\n```yaml\n'+yaml.safe_dump(statements,sort_keys=False,allow_unicode=True,width=110)+'```\n'
        if negative: prompt+='\n# Negative guidance from prior plan audit\nGenerate a new plan de novo from the original statements. Do not edit the rejected plan.\n```yaml\n'+yaml.safe_dump({'do_not_repeat':negative},sort_keys=False,allow_unicode=True,width=110)+'```\n'
        try:
            _model_call(work,call_id=call_id,role='summarization',prompt=prompt,output=path,validator=lambda t:runtime.validate_summary_plan_text(t,statements,allow_cross_domain_merge=allow_cross),profile=profile,fatal=False,max_attempts=_retry('summary_plan_attempts'))
            candidate=yaml.safe_load(_read(path)); candidate_blocks=_summary_blocks(candidate,statements)
            aid=f'{call_id}-audit'; apath=_artifact(work,'summary',f'summary-plan-audit-{sem+1:02d}.yaml',new=True)
            aprompt=_prompt('summary_plan_audit')+'\n\n# Original reportable statements\n```yaml\n'+yaml.safe_dump(statements,sort_keys=False,allow_unicode=True,width=110)+'```\n\n# Proposed plan\n```yaml\n'+yaml.safe_dump(candidate,sort_keys=False,allow_unicode=True,width=110)+'```\n\n# Deterministically assembled blocks\n```yaml\n'+yaml.safe_dump({'blocks':candidate_blocks},sort_keys=False,allow_unicode=True,width=110)+'```\n'
            _model_call(work,call_id=aid,role='semantic_preservation_check',prompt=aprompt,output=apath,validator=_validate_summary_plan_audit,profile=profile,fatal=False,max_attempts=_retry('summary_plan_audit_attempts'))
            audit=yaml.safe_load(_read(apath)); issues=[f"{x['target']}: {x['issue']}" for x in audit['issues']]
            if audit['preserved'] and not audit['unnecessarily_fragmented']:
                plan=candidate; blocks=candidate_blocks; break
            if audit['preserved'] and audit['unnecessarily_fragmented']:
                if frag_used>=frag_cap:
                    _risk(work,stage='summarization',risk_type='summary_fragmentation_retained',message='; '.join(issues),attempts=sem+1,action='retained_after_configured_fragmentation_replans',human_review='optional'); plan=candidate; blocks=candidate_blocks; break
                frag_used+=1
            negative=issues
            if sem==semantic_cap:
                if audit['preserved']:
                    plan=candidate; blocks=candidate_blocks; break
                _risk(work,stage='summarization',risk_type='summary_plan_semantic_preservation',message='; '.join(issues) or 'Summary plan failed semantic-preservation audit.',attempts=sem+1,action='fell_back_to_one_block_per_reportable_statement',human_review='optional'); plan=_fallback_summary_plan(statements); blocks=_summary_blocks(plan,statements); break
        except StepFailure as exc:
            if sem==semantic_cap:
                _risk(work,stage='summarization',risk_type='summary_plan_failure',message=str(exc),attempts=sem+1,action='fell_back_to_one_block_per_reportable_statement',human_review='optional'); plan=_fallback_summary_plan(statements); blocks=_summary_blocks(plan,statements); break
            negative=[str(exc)]
    assert plan is not None and blocks is not None
    _write(_existing_or_new(work,'summary','summary-plan.yaml'),yaml.safe_dump(plan,sort_keys=False,allow_unicode=True,width=110)); _write(_existing_or_new(work,'summary','summary-blocks.yaml'),yaml.safe_dump({'blocks':blocks},sort_keys=False,allow_unicode=True,width=110))

    # One whole-report paraphrase per semantic attempt, always from original blocks.
    paras=None; audits=None; para_negative=[]; para_cap=_retry('paraphrase_regenerations')
    case_text=_read(layout.input(work,'case.md'))
    for sem in range(para_cap+1):
        cid='paraphrase-batch' if sem==0 else f'paraphrase-batch-regenerate-{sem:02d}'; path=_artifact(work,'summary',f'paraphrase-batch-{sem+1:02d}.yaml',new=True)
        pprompt=_prompt('paraphrase')+'\n\n# Deterministically assembled blocks\n```yaml\n'+yaml.safe_dump({'blocks':blocks},sort_keys=False,allow_unicode=True,width=110)+'```\n\n# case.md — context only\n```text\n'+case_text.rstrip()+'\n```\n'
        if para_negative: pprompt+='\n# Negative guidance from prior paraphrase audit\nRegenerate the entire set de novo from the original blocks. Do not edit rejected prose.\n```yaml\n'+yaml.safe_dump({'do_not_repeat':para_negative},sort_keys=False,allow_unicode=True,width=110)+'```\n'
        try:
            _model_call(work,call_id=cid,role='paraphrasing',prompt=pprompt,output=path,validator=lambda t:runtime.validate_paraphrase_batch_text(t,blocks),profile=profile,fatal=False,max_attempts=_retry('paraphrase_attempts'))
            candidate=yaml.safe_load(_read(path))['sentences']; aid=f'{cid}-audit'; apath=_artifact(work,'summary',f'paraphrase-audit-{sem+1:02d}.yaml',new=True)
            aprompt=_prompt('paraphrase_audit')+'\n\n# Blocks and paraphrased sentences\n```yaml\n'+yaml.safe_dump({'blocks':blocks,'sentences':candidate},sort_keys=False,allow_unicode=True,width=110)+'```\n\n# case.md — context only\n```text\n'+case_text.rstrip()+'\n```\n'
            _model_call(work,call_id=aid,role='semantic_preservation_check',prompt=aprompt,output=apath,validator=lambda t:runtime.validate_paraphrase_audit_batch_text(t,blocks),profile=profile,fatal=False,max_attempts=_retry('paraphrase_audit_attempts'))
            candidate_audits=yaml.safe_load(_read(apath))['audits']; failed=[a for a in candidate_audits if not a['preserved']]
            paras=candidate; audits=candidate_audits
            if not failed: break
            para_negative=[{'block_id':a['block_id'],'issue':a['issue'],'negative_guidance':a.get('negative_guidance') or []} for a in failed]
            if sem==para_cap: break
        except StepFailure as exc:
            para_negative=[{'issue':str(exc)}]
            if sem==para_cap:
                paras=[{'block_id':b['block_id'],'sentence':runtime.fallback_block_sentence(b)} for b in blocks]; audits=[{'block_id':b['block_id'],'preserved':False,'issue':'Audit unavailable after bounded retries.','negative_guidance':['Use source-preserving fallback.']} for b in blocks]; break
    assert paras is not None and audits is not None
    pmap={p['block_id']:p['sentence'] for p in paras}; amap={a['block_id']:a for a in audits}; final={'dispositions':plan['dispositions'],'sentences':[]}
    for block in blocks:
        audit=amap.get(block['block_id'],{'preserved':False,'issue':'Missing audit row.','negative_guidance':[]}); sentence=pmap.get(block['block_id']) or runtime.fallback_block_sentence(block)
        if not audit['preserved']:
            _risk(work,stage='summarization',risk_type='paraphrase_semantic_preservation',message=audit.get('issue') or 'Paraphrase lost material block semantics.',schema_element=block['block_id'],attempts=para_cap+1,action='fell_back_to_source_preserving_block_sentence',human_review='optional'); sentence=runtime.fallback_block_sentence(block)
        final['sentences'].append({'sentence_id':block['block_id'],'domain':block['domain'],'sentence':sentence,'source_statement_ids':block['source_statement_ids'],'card_tags':runtime.deterministic_sentence_card_tags(block['source_statement_ids'],statements)})
    runtime.validate_canonical_summary_doc(final,statements); _write(_existing_or_new(work,'summary','summary-final.yaml'),yaml.safe_dump(final,sort_keys=False,allow_unicode=True,width=110)); return final


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
    _stage_status(work,'stage-3','Stage 3 of 9 — diagnosis proformas + statement audits'); diagnosis,cmcs,diagnosis_cards,diagnosis_elements=stage_diagnosis(work,case,eligible,profile)
    domains={}; cards_by_domain=dict(diagnosis_cards); elements=list(diagnosis_elements)
    for idx,domain in enumerate(('prognosis','treatment','biomarker','germline'),4):
        _stage_status(work,f'stage-{idx}',f'Stage {idx} of 9 — {domain} proforma + statement audit'); domains[domain],cards_by_domain[domain],domain_elements=stage_domain(work,domain,case,reg,diagnosis,eligible,profile); elements.extend(domain_elements)
    _stage_status(work,'stage-8','Stage 8 of 9 — statement-grounded evidence matching and report synthesis')
    enriched=stage_evidence(work,elements,cards_by_domain,reg,manifest,profile); statements=stage_reportable_sentences(work,enriched); summary=stage_summary(work,statements,case,profile)
    _stage_status(work,'stage-9','Stage 9 of 9 — finalise report'); stage_final(work,case,summary,enriched,all_cards,digest,manifest); _print_usage(work); _stage_status(work,'complete','terraced-v5 complete'); return EXIT_OK

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
            if not c: raise StepFailure('no --work-dir given and no terraced-v5 runs exist')
            work=c[0]; _status(f'using most recent run directory: {work}')
        with _cli_logging(work): return run_pipeline(work)
    except Handoff as h: print(f'HANDOFF={h.call_id}'); print(f'PROMPT={h.prompt}'); print(f'OUTPUT={h.output}'); return EXIT_HANDOFF
    except (StepFailure,ValueError,OSError,KeyError,json.JSONDecodeError,yaml.YAMLError,syntax_repair.SyntaxRepairExhausted) as exc: print(f'terraced-v5 failed: {exc}',file=sys.stderr); return EXIT_FAILURE
if __name__=='__main__': raise SystemExit(main())
