"""Minimal deterministic runtime helpers retained for terraced-v4."""
from __future__ import annotations
import json, re, shutil, sys
from pathlib import Path
import yaml
from scripts import vocab
from scripts.core.validated_model_task import ValidationFailure, ValidationIssue, fail
from workflows.terraced_v4 import layout

HERE=Path(__file__).resolve().parent; REPO_ROOT=HERE.parents[1]
WHO5_EXCLUDED_SCHEMA_DISEASES={'MDS/AML'}
VALIDATION_MODES={'nel-validate','nel-validate-function','nel-validate-brief'}
HEADINGS={'**Diagnosis**':'diagnosis','**Prognosis**':'prognosis','**Treatment Implications**':'treatment','**MRD**':'biomarker','**Germline**':'germline'}
DOMAIN_HEADINGS={v:k for k,v in HEADINGS.items()}

def setup_assets(work_dir:Path,*,mode:str,case_id:str|None=None)->None:
    work=Path(work_dir); layout.ensure_dirs(work)
    panel_root=work/'ngs-panel-scope.md'; panel_out=layout.setup(work,'ngs-panel-scope.md',existing=False)
    if panel_root.is_file() and panel_root!=panel_out: shutil.move(str(panel_root),str(panel_out))
    cmc_root=work/'case-major-categories.json'; cmc_out=layout.setup(work,'case-major-categories.json',existing=False)
    cmc_out.write_text(json.dumps({'case_major_categories':list(vocab.CASE_MAJOR_CATEGORIES),'instruction':'bootstrap_cmcs are retrieval scaffolds only. Authoritative CMCs are derived deterministically from validated WHO5 schema diseases.'},indent=2,ensure_ascii=False)+'\n',encoding='utf-8'); cmc_root.unlink(missing_ok=True)
    allowed=[d for d in vocab.CASE_DISEASES if d not in WHO5_EXCLUDED_SCHEMA_DISEASES]
    layout.setup(work,'allowed-schema-diseases.json',existing=False).write_text(json.dumps({'schema_version':1,'allowed_schema_diseases':allowed,'instruction':'WHO5 schema disease controls deterministic CMC routing; ICC never routes evidence.'},indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    if mode in VALIDATION_MODES:
        if not case_id: raise ValueError(f'{mode} requires a validation case ID')
        repo=str(REPO_ROOT); inserted=False
        if repo not in sys.path: sys.path.insert(0,repo); inserted=True
        try:
            from validation.cases import case_file_for_mode,retrieve_case
            text=retrieve_case(case_id,case_file_for_mode(mode))
        finally:
            if inserted and sys.path and sys.path[0]==repo: sys.path.pop(0)
        p=layout.input(work,'case.md',existing=False); payload=text.rstrip()+'\n'
        if p.exists() and p.read_text(encoding='utf-8')!=payload: raise ValueError(f'{p} exists with different validation case content')
        p.write_text(payload,encoding='utf-8')

def read_json(path:Path)->dict:
    d=json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(d,dict): raise ValueError(f'expected JSON object: {path}')
    return d

def parse_yaml_mapping(text:str,context='YAML')->dict:
    try:d=yaml.safe_load(text)
    except yaml.YAMLError as exc: raise ValueError(f'{context}: invalid YAML: {exc}') from exc
    if not isinstance(d,dict): raise ValueError(f'{context}: expected mapping')
    return d

def _exact(issues,row,expected,path=''):
    if not isinstance(row,dict): return
    if set(row)!=set(expected): issues.append(ValidationIssue(path or 'root',f'received fields {sorted(row)}',f'return exactly {sorted(expected)}'))
def _nonempty(v): return isinstance(v,str) and bool(v.strip())

def validate_case_text(text:str)->str:
    try:d=json.loads(text)
    except json.JSONDecodeError as exc: raise ValueError(f'structured case: invalid JSON: {exc}') from exc
    if not isinstance(d,dict): raise ValueError('structured case: expected object')
    issues=[]; _exact(issues,d,{'provisional_disease','bootstrap_cmcs','variants','detected_variants_summary','case_facts'})
    if not _nonempty(d.get('provisional_disease')): issues.append(ValidationIssue('provisional_disease','blank or not a string','return a source-faithful provisional disease description'))
    cmcs=d.get('bootstrap_cmcs')
    if not isinstance(cmcs,list) or not cmcs: issues.append(ValidationIssue('bootstrap_cmcs','must be a non-empty list','use one or more exact allowed CMC values'))
    else:
        for i,c in enumerate(cmcs):
            if c not in vocab.CASE_MAJOR_CATEGORY_SET: issues.append(ValidationIssue(f'bootstrap_cmcs[{i}]',f'unknown CMC {c!r}','use an exact allowed CMC'))
        if len(cmcs)!=len(set(cmcs)): issues.append(ValidationIssue('bootstrap_cmcs','contains duplicates','list each CMC once'))
    variants=d.get('variants')
    if not isinstance(variants,list): issues.append(ValidationIssue('variants','expected list','return every detected variant in case order')); variants=[]
    for i,row in enumerate(variants,1):
        path=f'variants[{i-1}]'
        if not isinstance(row,dict): issues.append(ValidationIssue(path,'expected object','return variant_id, gene, description')); continue
        _exact(issues,row,{'variant_id','gene','description'},path)
        if row.get('variant_id')!=f'V{i}': issues.append(ValidationIssue(f'{path}.variant_id',f'received {row.get("variant_id")!r}',f'use sequential stable ID V{i}'))
        if not _nonempty(row.get('gene')) or row['gene']!=row['gene'].upper(): issues.append(ValidationIssue(f'{path}.gene',f'invalid gene {row.get("gene")!r}','use uppercase reported gene symbol'))
        if not _nonempty(row.get('description')): issues.append(ValidationIssue(f'{path}.description','blank','preserve complete variant description'))
    summary=d.get('detected_variants_summary')
    if not _nonempty(summary) or '\n' in str(summary) or str(summary)!=str(summary).strip(): issues.append(ValidationIssue('detected_variants_summary','must be one non-empty physical line','return one clean source-faithful sentence'))
    facts=d.get('case_facts')
    if not isinstance(facts,list): issues.append(ValidationIssue('case_facts','expected list','return case facts as a list')); facts=[]
    for i,row in enumerate(facts,1):
        path=f'case_facts[{i-1}]'
        if not isinstance(row,dict): issues.append(ValidationIssue(path,'expected object','return fact_id, kind, value')); continue
        _exact(issues,row,{'fact_id','kind','value'},path)
        if row.get('fact_id')!=f'C{i}': issues.append(ValidationIssue(f'{path}.fact_id',f'received {row.get("fact_id")!r}',f'use sequential C{i}'))
        for f in ('kind','value'):
            if not _nonempty(row.get(f)): issues.append(ValidationIssue(f'{path}.{f}','blank','return non-empty source-faithful text'))
    fail('structured case',issues); return 'structured case validated'

def case_genes(case:dict)->list[str]:
    out=[]
    for row in case.get('variants') or []:
        g=row.get('gene')
        if isinstance(g,str) and g not in out: out.append(g)
    return out

def active_who5_diagnoses(doc:dict)->list[dict]: return [r for r in doc.get('diagnoses') or [] if r.get('status') in {'established','indeterminate'}]
def derive_cmcs(doc:dict)->list[str]:
    cmcs=[]
    for row in active_who5_diagnoses(doc):
        disease=row.get('schema_disease'); cmc=vocab.preferred_case_major_category(disease)
        if disease==vocab.NO_HAEMATOLOGICAL_MALIGNANCY: cmc=vocab.NO_HAEMATOLOGICAL_MALIGNANCY
        if not cmc: raise ValueError(f'WHO5 schema disease {disease!r} has no deterministic preferred CMC mapping')
        if cmc not in cmcs: cmcs.append(cmc)
    if not cmcs: raise ValueError('WHO5 state produced no active diagnosis from which to derive CMC')
    return cmcs

def validate_summary_plan_doc(doc:dict,statements:list[dict])->str:
    issues=[]; _exact(issues,doc,{'dispositions','sentences'}); smap={s['statement_id']:s for s in statements}
    disp=doc.get('dispositions');
    if not isinstance(disp,list): issues.append(ValidationIssue('dispositions','expected list','return one disposition per statement')); disp=[]
    if len(disp)!=len(statements): issues.append(ValidationIssue('dispositions',f'expected {len(statements)} rows, received {len(disp)}','return every statement exactly once in order'))
    included=set(); omitted=set()
    for i,s in enumerate(statements):
        if i>=len(disp) or not isinstance(disp[i],dict): continue
        r=disp[i]; path=f'dispositions[{i}]'; _exact(issues,r,{'statement_id','decision','reason'},path)
        if r.get('statement_id')!=s['statement_id']: issues.append(ValidationIssue(f'{path}.statement_id',f'received {r.get("statement_id")!r}',f'copy {s["statement_id"]!r}'))
        dec=r.get('decision')
        if dec=='include': included.add(s['statement_id']);
        elif dec=='omit': omitted.add(s['statement_id'])
        else: issues.append(ValidationIssue(f'{path}.decision',f'invalid {dec!r}','use include or omit'))
        if s.get('domain')=='diagnosis' and dec=='omit': issues.append(ValidationIssue(f'{path}.decision','diagnosis sentence cannot be omitted','include diagnosis statements'))
        if dec=='include' and r.get('reason') is not None: issues.append(ValidationIssue(f'{path}.reason','include requires null','set reason: null'))
        if dec=='omit' and not _nonempty(r.get('reason')): issues.append(ValidationIssue(f'{path}.reason','omit requires reason','state why omission is safe'))
    rows=doc.get('sentences')
    if not isinstance(rows,list) or not rows: issues.append(ValidationIssue('sentences','expected non-empty list','return ordered sentence plans')); rows=[]
    represented=set(); counts={d:0 for d in DOMAIN_HEADINGS}; order={d:i for i,d in enumerate(DOMAIN_HEADINGS)}; last=-1; seen=set()
    for i,r in enumerate(rows):
        path=f'sentences[{i}]'
        if not isinstance(r,dict): issues.append(ValidationIssue(path,'expected mapping','return sentence plan')); continue
        _exact(issues,r,{'sentence_id','domain','source_statement_ids','draft_sentence'},path); domain=r.get('domain')
        if domain not in DOMAIN_HEADINGS: issues.append(ValidationIssue(f'{path}.domain',f'invalid {domain!r}',f'use one of {list(DOMAIN_HEADINGS)}'))
        else:
            if order[domain]<last: issues.append(ValidationIssue(f'{path}.domain','out of canonical section order','preserve diagnosis→prognosis→treatment→biomarker→germline'))
            last=max(last,order[domain]); counts[domain]+=1; expected=f'{domain}-{counts[domain]}'
            if r.get('sentence_id')!=expected: issues.append(ValidationIssue(f'{path}.sentence_id',f'received {r.get("sentence_id")!r}',f'use {expected!r}'))
        if r.get('sentence_id') in seen: issues.append(ValidationIssue(f'{path}.sentence_id','duplicate','use each sentence ID once'))
        seen.add(r.get('sentence_id')); draft=r.get('draft_sentence')
        if not _nonempty(draft) or draft!=draft.strip() or '\n' in draft or not draft.endswith('.'): issues.append(ValidationIssue(f'{path}.draft_sentence','must be one complete physical-line sentence','return a self-contained sentence ending with a full stop'))
        ids=r.get('source_statement_ids')
        if not isinstance(ids,list) or not ids or len(ids)!=len(set(ids)): issues.append(ValidationIssue(f'{path}.source_statement_ids','invalid','list one or more unique included statement IDs')); continue
        for sid in ids:
            s=smap.get(sid)
            if s is None: issues.append(ValidationIssue(f'{path}.source_statement_ids',f'unknown {sid!r}','use only supplied IDs')); continue
            if sid in omitted: issues.append(ValidationIssue(f'{path}.source_statement_ids',f'{sid} is omitted','remove it or include it'))
            if s['domain']!=domain: issues.append(ValidationIssue(f'{path}.source_statement_ids',f'{sid} belongs to {s["domain"]}','combine only same-domain sentences'))
            represented.add(sid)
    missing=sorted(included-represented)
    if missing: issues.append(ValidationIssue('included statement coverage',f'missing {missing}','represent every included statement'))
    fail('summarization plan',issues); return 'summarization plan validated'
def validate_summary_plan_text(text:str,statements:list[dict])->str: return validate_summary_plan_doc(parse_yaml_mapping(text,'summary plan'),statements)
def paraphrase_items(plan:dict,statements:list[dict])->list[dict]:
    validate_summary_plan_doc(plan,statements); smap={s['statement_id']:s for s in statements}; counts={}
    for r in plan['sentences']:
        for sid in r['source_statement_ids']: counts[sid]=counts.get(sid,0)+1
    return [{'sentence_id':r['sentence_id'],'domain':r['domain'],'draft_sentence':r['draft_sentence'],'source_statement_ids':list(r['source_statement_ids']),'source_statements':[{'statement_id':sid,'statement':smap[sid]['statement']} for sid in r['source_statement_ids']],'split_source_statement_ids':[sid for sid in r['source_statement_ids'] if counts.get(sid,0)>1]} for r in plan['sentences']]
def validate_paraphrase_text(text:str,item:dict)->str:
    d=parse_yaml_mapping(text,'paraphrase'); issues=[]; _exact(issues,d,{'sentence_id','sentence'})
    if d.get('sentence_id')!=item['sentence_id']: issues.append(ValidationIssue('sentence_id',f'received {d.get("sentence_id")!r}',f'copy {item["sentence_id"]!r}'))
    s=d.get('sentence')
    if not _nonempty(s) or s!=s.strip() or '\n' in s or not s.endswith('.'): issues.append(ValidationIssue('sentence','must be one self-contained sentence ending with a full stop','return one physical-line sentence'))
    fail('paraphrase',issues); return 'paraphrase validated'
def deterministic_sentence_card_tags(ids:list[str],statements:list[dict])->list[str]:
    smap={s['statement_id']:s for s in statements}; out=[]
    for sid in ids:
        for tag in smap[sid].get('card_tags') or []:
            if tag not in out: out.append(tag)
    return out
def validate_canonical_summary_doc(doc:dict,statements:list[dict])->str:
    # It is core-published from an already validated plan; verify only source/card ancestry and sentence shape.
    smap={s['statement_id']:s for s in statements}
    if set(doc)!={'dispositions','sentences'}: raise ValueError('canonical summary must contain dispositions and sentences')
    for r in doc['sentences']:
        ids=r.get('source_statement_ids') or []
        if any(sid not in smap for sid in ids): raise ValueError(f'canonical summary references unknown source statement in {ids}')
        expected=deterministic_sentence_card_tags(ids,statements)
        if r.get('card_tags')!=expected: raise ValueError(f'{r.get("sentence_id")}: card_tags are not deterministic from source statements')
    return 'canonical summary validated'
def render_canonical_summary(doc:dict)->str:
    out=[]; current=None
    for r in doc.get('sentences') or []:
        if r['domain']!=current:
            if out: out.append('')
            out.append(DOMAIN_HEADINGS[r['domain']]); current=r['domain']
        tags=''.join(r.get('card_tags') or []); out.append(r['sentence']+((' '+tags) if tags else ''))
    return '\n'.join(out).rstrip()+'\n'
