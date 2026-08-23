#!/usr/bin/env python3
"""Terraced-v4 prototype: proformas -> semantic evidence -> sentence planning -> report."""
from __future__ import annotations
import argparse, contextlib, hashlib, json, shutil, sys, tempfile, time, zipfile
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
SETTINGS_PATH=HERE/'settings.json'; SETTINGS_TEMPLATE_PATH=HERE/'settings.json.template'
EXIT_OK=0; EXIT_FAILURE=1; EXIT_HANDOFF=10
VALIDATION_MODES={'nel-validate','nel-validate-function','nel-validate-brief'}
MARKING_PREFIX={'nel-validate':'nel-validation','nel-validate-function':'nel-validation-function','nel-validate-brief':'nel-validation-brief'}
_EXECUTION_STARTED_AT=None

class StepFailure(RuntimeError): pass
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
def _risk_path(work): return layout.logs(work)/'risk_log.yaml'
def _risk_doc(work):
    if _risk_path(work).is_file(): return yaml.safe_load(_read(_risk_path(work))) or {'run_status':'completed','risks':[]}
    return {'run_status':'completed','risks':[]}
def _risk(work,*,stage,risk_type,message,severity='warning',schema_element=None,attempts=0,action='retained',human_review='recommended'):
    d=_risk_doc(work); rows=d.setdefault('risks',[]); rid=f'R{len(rows)+1:03d}'
    rows.append({'id':rid,'stage':stage,'schema_element':schema_element,'severity':severity,'type':risk_type,'message':message,'action_taken':action,'attempts':attempts,'human_review':human_review})
    if severity in {'warning','error'}: d['run_status']='completed_with_risks'
    _write(_risk_path(work),yaml.safe_dump(d,sort_keys=False,allow_unicode=True,width=110))

def _render_bundle(call_id,messages,output,error=None):
    out=[f'# Terraced-v4 model operation — {call_id}','']
    for i,m in enumerate(messages,1): out += [f'## Message {i} — {m["role"]}','',m['content'].rstrip(),'']
    if error: out += ['## Deterministic structural feedback','',error,'','Repair only the reported structural defects. Preserve clinical meaning.','']
    out += ['## Output','',f'Write only the requested artifact to: `{output}`','Do not modify any other file.','']
    return '\n'.join(out)

def _syntax_callback(work,binding,call_id):
    def repair(prompt,attempt):
        sid=f'{call_id}-syntax-{attempt}'; root=layout.model_step_dir(work,sid,existing=False); out=root/'output.txt'; _write(root/'prompt.md',prompt)
        _status(f'  {call_id}: syntax-only repair {attempt}/{load_settings().get("syntax_repair_attempts",2)}')
        if binding.is_self:
            if out.is_file(): return _read(out)
            raise Handoff(sid,root/'prompt.md',out)
        try: comp=model_client.complete_messages(binding,[{'role':'system','content':syntax_repair.SYNTAX_REPAIR_SYSTEM_PROMPT},{'role':'user','content':prompt}])
        except model_client.TruncatedCompletion as exc: text=exc.content
        except RuntimeError as exc: raise StepFailure(str(exc)) from exc
        else: text=comp.content
        _write(out,text.rstrip()+'\n'); return text
    return repair

def _prepare_structured(work,raw,fmt,call_id,syntax_binding):
    if not fmt: return model_client.strip_code_fence(raw)
    attempts=int(load_settings().get('syntax_repair_attempts',2))
    result=syntax_repair.repair_structured_output(raw,format_name=fmt,model_repair=_syntax_callback(work,syntax_binding,call_id),model_attempts=attempts)
    return result.text

def _model_call(work,*,call_id,role,prompt,output,validator,profile=None,fmt='yaml',fatal=True,max_attempts=None,feedback=None):
    binding=_profile(work,profile,role); syntax_binding=_profile(work,profile,'syntax_repair'); root=layout.model_step_dir(work,call_id,existing=False)
    messages=[{'role':'system','content':model_client.SYSTEM_PROMPT},{'role':'user','content':prompt}]
    attempts=int(max_attempts or (load_settings().get('fatal_attempts',10) if fatal else 3)); previous=None; last_error=feedback or ''
    self_count_path=root/'self-attempt-count.json'
    self_count=0
    if self_count_path.is_file():
        try: self_count=int(json.loads(_read(self_count_path)).get('attempts',0))
        except Exception: self_count=0
    if output.is_file():
        try:
            candidate=_prepare_structured(work,_read(output),fmt,call_id,syntax_binding); msg=validator(candidate); _write(output,candidate); _write(root/'accepted-output.txt',candidate); _write(root/'validated.txt',msg+'\n'); return candidate
        except Handoff: raise
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
        except model_client.TruncatedCompletion as exc: raw=exc.content; previous=raw; last_error=f'Output truncated at max_tokens={exc.max_tokens}; return the complete requested artifact.'; continue
        except RuntimeError as exc: raise StepFailure(str(exc)) from exc
        raw=comp.content
        try:
            candidate=_prepare_structured(work,raw,fmt,call_id,syntax_binding); msg=validator(candidate)
        except Handoff: raise
        except Exception as exc:
            previous=raw; last_error=validated_model_task.retry_instruction(exc)
            _write(layout.errors(work)/f'{call_id}-attempt-{attempt:02d}.txt',raw.rstrip()+'\n\nVALIDATION:\n'+last_error+'\n')
            continue
        _write(output,candidate); _write(root/'accepted-output.txt',candidate); _write(root/'validated.txt',msg+'\n'); return candidate
    raise StepFailure(f'model operation {call_id} failed validation after {attempts} attempts: {last_error}')

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
    all_cards,eligible,digest,manifest=_load_corpus()
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
def _diagnosis_to_who5_runtime(doc):
    return {'diagnoses':[{'diagnosis_id':f'DX{i}','schema_disease':r['schema_disease'],'status':r['status'],'diagnosis':r['diagnosis']} for i,r in enumerate(doc['who5']['diagnoses'],1)]}

def stage_diagnosis(work,case,eligible,profile):
    allowed=_allowed_diseases(work); genes=runtime.case_genes(case); bootstrap=list(case.get('bootstrap_cmcs') or [])
    p1=_existing_or_new(work,'diagnosis','pass-01.yaml'); cards1=_draw_diagnosis_cards(eligible,genes,bootstrap)
    prompt1=_read(PROMPTS/'diagnosis.md')+'\n\n# Pass\nPass 1: build the complete diagnosis from scratch.\n\n# Structured case\n```json\n'+json.dumps(case,indent=2,ensure_ascii=False)+'\n```\n\n# Allowed WHO5 schema diseases\n'+yaml.safe_dump(sorted(allowed))+'\n# Diagnostic candidate cards\n'+_render_cards(cards1)
    _model_call(work,call_id='diagnosis-pass-01',role='diagnosis',prompt=prompt1,output=p1,validator=lambda t:schema_validation.validate_diagnosis(t,allowed_diseases=allowed),profile=profile)
    d1=yaml.safe_load(_read(p1)); cmc1=runtime.derive_cmcs(_diagnosis_to_who5_runtime(d1)); changed=cmc1!=bootstrap; cards2=_draw_diagnosis_cards(eligible,genes,cmc1)
    p2=_existing_or_new(work,'diagnosis','pass-02.yaml')
    if changed:
        instruction='Pass 2: the CMC state changed after pass 1. START FROM SCRATCH using the new CMC-driven evidence. Do not use or anchor on the pass-1 proforma.'; prior=''
    else:
        instruction='Pass 2: the CMC state did not change. Reconsider and EDIT the current proforma. Return the complete replacement proforma.'; prior='\n\n# Current pass-1 proforma\n```yaml\n'+yaml.safe_dump(d1,sort_keys=False,allow_unicode=True,width=110)+'```\n'
    prompt2=_read(PROMPTS/'diagnosis.md')+f'\n\n# Pass\n{instruction}'+prior+'\n\n# Structured case\n```json\n'+json.dumps(case,indent=2,ensure_ascii=False)+'\n```\n\n# Allowed WHO5 schema diseases\n'+yaml.safe_dump(sorted(allowed))+'\n# Diagnostic candidate cards\n'+_render_cards(cards2)
    _model_call(work,call_id='diagnosis-pass-02',role='diagnosis',prompt=prompt2,output=p2,validator=lambda t:schema_validation.validate_diagnosis(t,allowed_diseases=allowed),profile=profile)
    final=yaml.safe_load(_read(p2)); final_cmcs=runtime.derive_cmcs(_diagnosis_to_who5_runtime(final))
    routing={'bootstrap_cmcs':bootstrap,'pass_1_cmcs':cmc1,'cmc_changed_after_pass_1':changed,'final_cmcs':final_cmcs}
    _write(_existing_or_new(work,'diagnosis','routing.json'),json.dumps(routing,indent=2,ensure_ascii=False)+'\n')
    if final_cmcs!=cmc1: _risk(work,stage='diagnosis',risk_type='cmc_changed_after_final_pass',message=f'Pass 2 changed CMCs from {cmc1} to {final_cmcs}; prototype is intentionally limited to two diagnosis passes, so no third CMC redraw occurred.',action='continued_with_pass_2_as_authoritative',human_review='recommended')
    return final,final_cmcs,cards2

def _variant_context(reg): return yaml.safe_dump({'variants':reg},sort_keys=False,allow_unicode=True,width=110)
def stage_domain(work,domain,case,reg,diagnosis,eligible,profile):
    valid=set(reg); diseases=[r['schema_disease'] for r in diagnosis['who5']['diagnoses']]; cards=_draw_domain_cards(eligible,domain,runtime.case_genes(case),diseases)
    out=_existing_or_new(work,f'{domain}_state','proforma.yaml'); validator={'prognosis':schema_validation.validate_prognosis,'treatment':schema_validation.validate_treatment,'biomarker':schema_validation.validate_biomarker,'germline':schema_validation.validate_germline}[domain]
    prompt=_read(PROMPTS/f'{domain}.md')+'\n\n# Variant registry\n```yaml\n'+_variant_context(reg)+'```\n\n# Structured case\n```json\n'+json.dumps(case,indent=2,ensure_ascii=False)+'\n```\n\n# Authoritative diagnosis\n```yaml\n'+yaml.safe_dump(diagnosis,sort_keys=False,allow_unicode=True,width=110)+'```\n\n# Candidate evidence cards\n'+_render_cards(cards)
    _model_call(work,call_id=domain,role='ptbg',prompt=prompt,output=out,validator=lambda t:validator(t,valid),profile=profile)
    return yaml.safe_load(_read(out)),cards

def _schema_elements(diagnosis,domains):
    els=[]
    for i,row in enumerate(diagnosis['who5']['diagnoses'],1): els.append({'schema_id':f'DX-WHO5-{i:02d}','domain':'diagnosis','proposition':f'WHO5 classification: {row["diagnosis"]}.','reasons':row['reasons'],'evidence_domain':'diagnosis'})
    for i,row in enumerate(diagnosis['icc']['diagnoses'],1): els.append({'schema_id':f'DX-ICC-{i:02d}','domain':'diagnosis','proposition':f'ICC classification: {row["diagnosis"]}.','reasons':row['reasons'],'evidence_domain':'diagnosis'})
    els.append({'schema_id':'DX-CONCORDANCE','domain':'diagnosis','proposition':diagnosis['concordance']['answer'],'reasons':diagnosis['concordance']['reasons'],'evidence_domain':'diagnosis'})
    if diagnosis['concurrent_second_diagnosis']['answer'].strip().lower() not in {'none','none supported','no concurrent second diagnosis supported'}:
        els.append({'schema_id':'DX-CONCURRENT','domain':'diagnosis','proposition':diagnosis['concurrent_second_diagnosis']['answer'],'reasons':diagnosis['concurrent_second_diagnosis']['reasons'],'evidence_domain':'diagnosis'})
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

def _audit_validator(text):
    d=yaml.safe_load(text); schema_validation.validate_evidence_audit(text); return 'evidence audit structurally valid'
def stage_evidence(work,elements,cards_by_domain,reg,manifest,profile):
    tag_by_id=card_identity.tag_by_id(manifest); enriched=[]
    for el in elements:
        row=dict(el); row['evidence']=[]
        candidates=_candidate_cards_for_element(el,cards_by_domain,reg)
        for ri,reason in enumerate(el['reasons'],1):
            if reason.startswith('Clinical syndrome support ('):
                row['evidence'].append({'reason':reason,'status':'case_only','card_id':None,'card_tag':None,'source':None,'quote':None,'audit':None}); continue
            if not candidates:
                _risk(work,stage='evidence',risk_type='no_candidate_cards',message='No candidate evidence cards were available for this reason.',schema_element=el['schema_id'],action='continued_without_resolved_evidence',human_review='required')
                row['evidence'].append({'reason':reason,'status':'unresolved','card_id':None,'card_tag':None,'source':None,'quote':None,'audit':None}); continue
            excluded=set(); chosen=None; audit=None; max_sem=int(load_settings().get('evidence_match_attempts',3))
            for attempt in range(1,max_sem+1):
                available=[c for c in candidates if c.get('card_id') not in excluded] or candidates
                out=_artifact(work,'evidence_matches',f'{el["schema_id"]}-reason-{ri:02d}-match-{attempt:02d}.yaml',new=True)
                prompt=_read(PROMPTS/'evidence_match.md')+'\n\n# Clinical schema element\n```yaml\n'+yaml.safe_dump({'schema_id':el['schema_id'],'proposition':el['proposition'],'reason':reason},sort_keys=False,allow_unicode=True,width=110)+'```\n\n# Candidate cards\n'+_render_cards(available)
                try:
                    _model_call(work,call_id=f'evidence-match-{el["schema_id"]}-r{ri:02d}-a{attempt}',role='evidence_match',prompt=prompt,output=out,validator=lambda t,ids={c['card_id'] for c in available}:schema_validation.validate_evidence_match(t,ids),profile=profile,fatal=False,max_attempts=3)
                except StepFailure as exc:
                    _risk(work,stage='evidence',risk_type='evidence_match_structural_failure',message=str(exc),schema_element=el['schema_id'],attempts=attempt,action='continued_unresolved',human_review='required')
                    chosen=None; audit=None; break
                chosen=yaml.safe_load(_read(out)); card=next(c for c in available if c['card_id']==chosen['card_id'])
                aout=_artifact(work,'evidence_audits',f'{el["schema_id"]}-reason-{ri:02d}-audit-{attempt:02d}.yaml',new=True)
                aprompt=_read(PROMPTS/'evidence_audit.md')+'\n\n# Reason and selected evidence\n```yaml\n'+yaml.safe_dump({'reason':reason,'source':chosen['source'],'quote':chosen['quote'],'selected_card':card},sort_keys=False,allow_unicode=True,width=110)+'```\n'
                try:
                    _model_call(work,call_id=f'evidence-audit-{el["schema_id"]}-r{ri:02d}-a{attempt}',role='evidence_audit',prompt=aprompt,output=aout,validator=_audit_validator,profile=profile,fatal=False,max_attempts=3)
                    audit=yaml.safe_load(_read(aout))
                except StepFailure as exc:
                    audit={'obvious_mismatch':False,'risk':'warning','comments':['Citation audit unavailable after bounded retries: '+str(exc)]}
                    _risk(work,stage='evidence',risk_type='citation_audit_unavailable',message=str(exc),schema_element=el['schema_id'],attempts=attempt,action='retained_match_without_successful_audit',human_review='recommended')
                if audit['risk']=='warning': _risk(work,stage='evidence',risk_type='citation_fidelity',message='; '.join(audit['comments']) or 'Citation auditor flagged a fidelity concern.',schema_element=el['schema_id'],attempts=attempt,action='retained_pending_human_review',human_review='recommended')
                if not audit['obvious_mismatch']: break
                excluded.add(chosen['card_id']); _risk(work,stage='evidence',risk_type='obvious_citation_mismatch',message='; '.join(audit['comments']) or f'Citation auditor rejected {chosen["card_id"]} as an obvious mismatch.',schema_element=el['schema_id'],attempts=attempt,action='rematched' if attempt<max_sem else 'continued_unresolved',human_review='recommended' if attempt<max_sem else 'required')
            if chosen is None or (audit and audit['obvious_mismatch']):
                row['evidence'].append({'reason':reason,'status':'unresolved','card_id':chosen.get('card_id') if chosen else None,'card_tag':None,'source':chosen.get('source') if chosen else None,'quote':chosen.get('quote') if chosen else None,'audit':audit}); continue
            row['evidence'].append({'reason':reason,'status':'matched','card_id':chosen['card_id'],'card_tag':f'[card:{tag_by_id[chosen["card_id"]]}]','source':chosen['source'],'quote':chosen['quote'],'audit':audit})
        enriched.append(row)
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
    d=yaml.safe_load(text)
    if not isinstance(d,dict) or set(d)!={'preserved','issue'} or not isinstance(d['preserved'],bool): raise ValueError('paraphrase audit requires preserved:boolean and issue')
    if d['preserved'] and d['issue'] is not None: raise ValueError('preserved=true requires issue: null')
    if not d['preserved'] and (not isinstance(d['issue'],str) or not d['issue'].strip()): raise ValueError('preserved=false requires non-empty issue')
    return 'paraphrase audit structurally valid'
def stage_summary(work,statements,profile):
    plan_path=_existing_or_new(work,'summary','summary-plan.yaml')
    prompt=_read(PROMPTS/'summary_plan.md')+'\n\n# Reportable sentences\n```yaml\n'+yaml.safe_dump(statements,sort_keys=False,allow_unicode=True,width=110)+'```\n'
    try:
        _model_call(work,call_id='summary-plan',role='summarization',prompt=prompt,output=plan_path,validator=lambda t:runtime.validate_summary_plan_text(t,statements),profile=profile,fatal=False,max_attempts=2)
        plan=yaml.safe_load(_read(plan_path))
    except StepFailure as exc:
        counts={}; sentences=[]; dispositions=[]
        for statement in statements:
            dispositions.append({'statement_id':statement['statement_id'],'decision':'include','reason':None})
            domain=statement['domain']; counts[domain]=counts.get(domain,0)+1
            sentences.append({'sentence_id':f'{domain}-{counts[domain]}','domain':domain,'source_statement_ids':[statement['statement_id']],'draft_sentence':statement['statement']})
        plan={'dispositions':dispositions,'sentences':sentences}
        runtime.validate_summary_plan_doc(plan,statements)
        _write(plan_path,yaml.safe_dump(plan,sort_keys=False,allow_unicode=True,width=110))
        _risk(work,stage='summarization',risk_type='summary_plan_failure',message=str(exc),attempts=2,action='fell_back_to_one_sentence_per_reportable_statement',human_review='optional')
    items=runtime.paraphrase_items(plan,statements); paras=[]; max_sem=int(load_settings().get('paraphrase_repair_attempts',2))
    for item in items:
        accepted=None; last_issue=None
        for attempt in range(1,max_sem+1):
            out=_artifact(work,'summary',f'paraphrase-{item["sentence_id"]}-attempt-{attempt:02d}.yaml',new=True)
            feedback=('\n\n# Previous semantic-audit issue\n'+last_issue if last_issue else '')
            pprompt=_read(PROMPTS/'paraphrase.md')+'\n\n# Planned sentence\n```yaml\n'+yaml.safe_dump(item,sort_keys=False,allow_unicode=True,width=110)+'```\n'+feedback
            try:
                _model_call(work,call_id=f'paraphrase-{item["sentence_id"]}-a{attempt}',role='paraphrasing',prompt=pprompt,output=out,validator=lambda t,it=item:runtime.validate_paraphrase_text(t,it),profile=profile,fatal=False,max_attempts=2)
                para=yaml.safe_load(_read(out))
            except StepFailure as exc:
                last_issue=str(exc)
                continue
            audit_out=_artifact(work,'summary',f'paraphrase-audit-{item["sentence_id"]}-attempt-{attempt:02d}.yaml',new=True)
            aprompt=_read(PROMPTS/'paraphrase_audit.md')+'\n\n# Comparison\n```yaml\n'+yaml.safe_dump({'planned':item,'paraphrased_sentence':para['sentence']},sort_keys=False,allow_unicode=True,width=110)+'```\n'
            try:
                _model_call(work,call_id=f'paraphrase-audit-{item["sentence_id"]}-a{attempt}',role='semantic_preservation_check',prompt=aprompt,output=audit_out,validator=_validate_para_audit,profile=profile,fatal=False,max_attempts=2)
                audit=yaml.safe_load(_read(audit_out))
            except StepFailure as exc:
                last_issue=str(exc)
                continue
            if audit['preserved']: accepted=para; break
            last_issue=audit['issue']
        if accepted is None:
            accepted={'sentence_id':item['sentence_id'],'sentence':item['draft_sentence'].strip().rstrip('.')+'.'}
            _risk(work,stage='summarization',risk_type='paraphrase_semantic_preservation',message=f'Paraphrase for {item["sentence_id"]} failed semantic preservation after {max_sem} attempts; used the planned draft sentence unchanged.',schema_element=item['sentence_id'],attempts=max_sem,action='fell_back_to_unparaphrased_planned_sentence',human_review='optional')
        paras.append(accepted)
    pmap={p['sentence_id']:p for p in paras}; final={'dispositions':plan['dispositions'],'sentences':[]}
    for row in plan['sentences']:
        final['sentences'].append({'sentence_id':row['sentence_id'],'domain':row['domain'],'sentence':pmap[row['sentence_id']]['sentence'],'source_statement_ids':row['source_statement_ids'],'card_tags':runtime.deterministic_sentence_card_tags(row['source_statement_ids'],statements)})
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
    risks=_risk_doc(work); payload={'workflow':WORKFLOW_ID,'summary':summary,'risk_log':risks,'report_markdown':rendered}; _write(work/'report-final.json',json.dumps(payload,indent=2,ensure_ascii=False)+'\n')
    mode=_load_run_state(work).get('mode')
    if mode in VALIDATION_MODES:
        case_id=_load_run_state(work).get('validation_case'); package_marking_bundle(case_id,report,work/f'{MARKING_PREFIX[mode]}-{case_id}.zip',case_file=validation_cases.VALIDATION_CASE_FILES[mode])

def run_pipeline(work,profile=None):
    _require_work(work); layout.ensure_dirs(work)
    _status('Stage 1 of 9 — structure case'); case,reg=stage_structure(work,profile)
    _status('Stage 2 of 9 — initialise corpus'); all_cards,eligible,digest,manifest=stage_corpus(work)
    _status('Stage 3 of 9 — diagnosis: two serial passes'); diagnosis,cmcs,diagnosis_cards=stage_diagnosis(work,case,eligible,profile)
    domains={}; cards_by_domain={'diagnosis':diagnosis_cards}
    for idx,domain in enumerate(('prognosis','treatment','biomarker','germline'),4):
        _status(f'Stage {idx} of 9 — {domain} proforma'); domains[domain],cards_by_domain[domain]=stage_domain(work,domain,case,reg,diagnosis,eligible,profile)
    _status('Stage 8 of 9 — semantic evidence matching and report synthesis')
    elements=_schema_elements(diagnosis,domains); enriched=stage_evidence(work,elements,cards_by_domain,reg,manifest,profile); statements=stage_reportable_sentences(work,enriched,profile); summary=stage_summary(work,statements,profile)
    _status('Stage 9 of 9 — finalise report'); stage_final(work,case,summary,enriched,all_cards,digest,manifest); _status('terraced-v4 complete'); return EXIT_OK

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
