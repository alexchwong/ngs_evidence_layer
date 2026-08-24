"""Minimal deterministic runtime helpers retained for terraced-v5."""
from __future__ import annotations
import json, re, shutil, sys
from pathlib import Path
import yaml
from scripts import vocab
from scripts.core.validated_model_task import ValidationFailure, ValidationIssue, fail
from workflows.terraced_v5 import layout

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

def _type_name(v):
    if v is None: return 'null'
    if isinstance(v,bool): return 'boolean'
    if isinstance(v,dict): return 'mapping'
    if isinstance(v,list): return 'list'
    if isinstance(v,str): return 'string'
    if isinstance(v,int): return 'integer'
    if isinstance(v,float): return 'number'
    return type(v).__name__

def _preview(v,limit=180):
    text=repr(v); return text if len(text)<=limit else text[:limit-3]+'...'

def _single_mapping_list(v): return isinstance(v,list) and len(v)==1 and isinstance(v[0],dict)
def _single_scalar_mapping(v):
    if not isinstance(v,dict) or len(v)!=1:return False
    k,val=next(iter(v.items()))
    scalar=lambda x: x is None or isinstance(x,(str,int,float,bool))
    return scalar(k) and scalar(val)
def _scalar_string_repairable(v): return _single_scalar_mapping(v) or isinstance(v,(bool,int,float)) or (isinstance(v,list) and len(v)==1 and isinstance(v[0],str))
def _bool_repairable(v): return isinstance(v,str) and v.strip().lower() in {'true','false','yes','no'}

def parse_yaml_mapping(text:str,context='YAML')->dict:
    try:d=yaml.safe_load(text)
    except yaml.YAMLError as exc: raise ValueError(f'{context}: invalid YAML: {exc}') from exc
    if not isinstance(d,dict):
        safe=_single_mapping_list(d)
        fail(context,[ValidationIssue(context,f'expected mapping; received {_type_name(d)}','remove the extra one-item list wrapper without changing fields or values' if safe else 'return the required top-level mapping; this value cannot be safely repaired by syntax-only reserialization',repair_class='serialization' if safe else 'content',received=_preview(d),expected='mapping/object')])
    return d

def _exact(issues,row,expected,path=''):
    if not isinstance(row,dict): return
    missing=sorted(set(expected)-set(row)); extra=sorted(set(row)-set(expected))
    if missing or extra:
        issues.append(ValidationIssue(path or 'root',f'missing fields {missing}; unexpected fields {extra}',f'return exactly {sorted(expected)}',repair_class='content',received=str(sorted(row)),expected=str(sorted(expected))))
def _nonempty(v): return isinstance(v,str) and bool(v.strip())

def normalize_case_variant_descriptions(case:dict)->dict:
    """Preserve detailed variant text while enforcing a gene-prefixed description."""
    for row in case.get('variants') or []:
        if not isinstance(row,dict):
            continue
        gene=row.get('gene'); desc=row.get('description')
        if isinstance(gene,str) and gene.strip() and isinstance(desc,str) and desc.strip():
            gene=gene.strip(); desc=desc.strip()
            row['description']=desc if desc.startswith(gene) else f'{gene} {desc}'
    return case

def validate_case_text(text:str,*,require_gene_prefixed_description:bool=False)->str:
    try:d=json.loads(text)
    except json.JSONDecodeError as exc: raise ValueError(f'structured case: invalid JSON: {exc}') from exc
    issues=[]
    if not isinstance(d,dict):
        safe=_single_mapping_list(d)
        issues.append(ValidationIssue('structured case',f'expected object; received {_type_name(d)}','remove the extra one-item list wrapper without changing fields or values' if safe else 'return the required top-level object from the case-structure proforma',repair_class='serialization' if safe else 'content',received=_preview(d),expected='object'))
        d={}
    _exact(issues,d,{'provisional_disease','bootstrap_cmcs','variants','detected_variants_summary','case_facts'})
    provisional=d.get('provisional_disease')
    if not _nonempty(provisional):
        cls='serialization' if _scalar_string_repairable(provisional) else 'content'
        fix='quote/reserialize the existing value as one string without changing its words' if cls=='serialization' else 'return a source-faithful provisional disease description'
        issues.append(ValidationIssue('provisional_disease',f'expected non-empty string; received {_type_name(provisional)}',fix,repair_class=cls,received=_preview(provisional),expected='non-empty string'))
    cmcs=d.get('bootstrap_cmcs')
    if not isinstance(cmcs,list):
        safe=isinstance(cmcs,str)
        issues.append(ValidationIssue('bootstrap_cmcs',f'expected non-empty list; received {_type_name(cmcs)}','wrap the existing single CMC scalar in a JSON list without changing it' if safe else 'use one or more exact allowed CMC values as a list',repair_class='serialization' if safe else 'content',received=_preview(cmcs),expected='non-empty list of allowed CMC values'))
        cmcs=[]
    elif not cmcs:
        issues.append(ValidationIssue('bootstrap_cmcs','list is empty','use one or more exact allowed CMC values',repair_class='content'))
    for i,c in enumerate(cmcs):
        if c not in vocab.CASE_MAJOR_CATEGORY_SET: issues.append(ValidationIssue(f'bootstrap_cmcs[{i}]',f'unknown CMC {c!r}',f'use an exact allowed CMC from {list(vocab.CASE_MAJOR_CATEGORIES)}',repair_class='content',received=repr(c),expected=str(list(vocab.CASE_MAJOR_CATEGORIES))))
    scalar_cmcs=[c for c in cmcs if isinstance(c,str)]
    if len(scalar_cmcs)!=len(set(scalar_cmcs)): issues.append(ValidationIssue('bootstrap_cmcs','contains duplicate CMC values','list each CMC once',repair_class='content'))
    variants=d.get('variants')
    if not isinstance(variants,list):
        safe=isinstance(variants,dict)
        issues.append(ValidationIssue('variants',f'expected list; received {_type_name(variants)}','wrap the existing single variant object in a JSON list without changing it' if safe else 'return every detected variant as a list of variant objects in case order',repair_class='serialization' if safe else 'content',received=_preview(variants),expected='list of variant objects')); variants=[]
    for i,row in enumerate(variants,1):
        path=f'variants[{i-1}]'
        if not isinstance(row,dict):
            safe=_single_mapping_list(row)
            issues.append(ValidationIssue(path,f'expected object; received {_type_name(row)}','remove the extra one-item list wrapper without changing fields or values' if safe else 'return one variant object with variant_id, gene, and description',repair_class='serialization' if safe else 'content',received=_preview(row),expected='object')); continue
        _exact(issues,row,{'variant_id','gene','description'},path)
        if row.get('variant_id')!=f'V{i}': issues.append(ValidationIssue(f'{path}.variant_id',f'received {row.get("variant_id")!r}',f'use sequential stable ID V{i}',repair_class='content'))
        gene=row.get('gene')
        if not _nonempty(gene) or gene!=gene.upper(): issues.append(ValidationIssue(f'{path}.gene',f'invalid gene {gene!r}','use uppercase reported gene symbol',repair_class='content'))
        desc=row.get('description')
        if not _nonempty(desc):
            cls='serialization' if _scalar_string_repairable(desc) else 'content'
            issues.append(ValidationIssue(f'{path}.description',f'expected non-empty string; received {_type_name(desc)}','quote/reserialize the existing description as one string without changing its words' if cls=='serialization' else 'preserve complete variant description',repair_class=cls,received=_preview(desc),expected='non-empty string'))
        elif require_gene_prefixed_description and isinstance(gene,str) and gene.strip() and not desc.strip().startswith(gene.strip()):
            issues.append(ValidationIssue(f'{path}.description',f'description does not begin with gene {gene!r}',f'prefix the unchanged detailed variant description with exact gene {gene!r}',repair_class='content',received=_preview(desc),expected=f'{gene} + complete reported variant description'))
    summary=d.get('detected_variants_summary')
    if not _nonempty(summary):
        cls='serialization' if _scalar_string_repairable(summary) else 'content'
        issues.append(ValidationIssue('detected_variants_summary',f'expected non-empty string; received {_type_name(summary)}','quote/reserialize the existing summary as one string without changing its words' if cls=='serialization' else 'return one clean source-faithful sentence',repair_class=cls,received=_preview(summary),expected='non-empty one-line string'))
    elif '\n' in summary or summary!=summary.strip():
        issues.append(ValidationIssue('detected_variants_summary','must be one clean physical line','reserialize the same summary on one physical line without changing its words',repair_class='serialization',received=_preview(summary),expected='one physical-line string'))
    facts=d.get('case_facts')
    if not isinstance(facts,list):
        safe=isinstance(facts,dict)
        issues.append(ValidationIssue('case_facts',f'expected list; received {_type_name(facts)}','wrap the existing single case-fact object in a JSON list without changing it' if safe else 'return case facts as a list of objects',repair_class='serialization' if safe else 'content',received=_preview(facts),expected='list')); facts=[]
    for i,row in enumerate(facts,1):
        path=f'case_facts[{i-1}]'
        if not isinstance(row,dict):
            safe=_single_mapping_list(row); issues.append(ValidationIssue(path,f'expected object; received {_type_name(row)}','remove the extra one-item list wrapper without changing fields or values' if safe else 'return one case-fact object with fact_id, kind, and value',repair_class='serialization' if safe else 'content',received=_preview(row),expected='object')); continue
        _exact(issues,row,{'fact_id','kind','value'},path)
        if row.get('fact_id')!=f'C{i}': issues.append(ValidationIssue(f'{path}.fact_id',f'received {row.get("fact_id")!r}',f'use sequential C{i}',repair_class='content'))
        for f in ('kind','value'):
            value=row.get(f)
            if not _nonempty(value):
                cls='serialization' if _scalar_string_repairable(value) else 'content'
                issues.append(ValidationIssue(f'{path}.{f}',f'expected non-empty string; received {_type_name(value)}','quote/reserialize the existing value as one string without changing its words' if cls=='serialization' else 'return non-empty source-faithful text',repair_class=cls,received=_preview(value),expected='non-empty string'))
    fail('structured case',issues); return 'structured case validated'



def panel_genes_from_scope(text:str)->list[str]:
    """Return the explicit gene-level NGS panel scope in source order."""
    out=[]
    for gene in re.findall(r"^- `([A-Z0-9]+)`\s*$", str(text), flags=re.MULTILINE):
        if gene not in out:
            out.append(gene)
    return out

def diagnostic_result_context(case:dict, reg:dict, panel_scope_text:str)->dict:
    """Build compact deterministic testing-state context for diagnosis prompts.

    Do not materialize the full set of unreported panel genes.  The workflow
    invariant is supplied as a rule and core verifies any authority-relevant
    bare-gene negative on demand.  This keeps model prompts proportional to the
    detected findings rather than panel size.
    """
    # Parse the panel here so malformed/empty scope still fails through the same
    # setup path, but intentionally do not serialize the gene list into prompts.
    panel=panel_genes_from_scope(panel_scope_text)
    detected=[]
    for vid,row in reg.items():
        detected.append({'subject':vid,'gene':row.get('gene')})
    facts=[]
    for row in case.get('case_facts') or []:
        if isinstance(row,dict):
            facts.append({'subject':row.get('fact_id'),'kind':row.get('kind'),'value':row.get('value')})
    return {
        'ngs':{
            'detected_variants':detected,
            'panel_gene_count':len(panel),
            'negative_rule':'An unreported gene on the supplied NGS panel is verified negative within assay scope; mention one only when an authority card makes that negative result relevant.',
        },
        'non_ngs':{
            'reported_case_facts':facts,
            'absence_rule':'A relevant non-NGS test not supplied, or explicitly pending/not done, is presumed negative/normal for provisional diagnostic reasoning.',
        },
    }

def case_genes(case:dict)->list[str]:
    out=[]
    for row in case.get('variants') or []:
        g=row.get('gene')
        if isinstance(g,str) and g not in out: out.append(g)
    return out

def active_who5_diagnoses(doc:dict)->list[dict]: return [r for r in doc.get('diagnoses') or [] if r.get('status') in {'established','conditional','indeterminate'}]
def derive_cmcs(doc:dict)->list[str]:
    cmcs=[]
    for row in active_who5_diagnoses(doc):
        disease=row.get('schema_disease'); cmc=vocab.preferred_case_major_category(disease)
        if disease==vocab.NO_HAEMATOLOGICAL_MALIGNANCY: cmc=vocab.NO_HAEMATOLOGICAL_MALIGNANCY
        if not cmc: raise ValueError(f'WHO5 schema disease {disease!r} has no deterministic preferred CMC mapping')
        if cmc not in cmcs: cmcs.append(cmc)
    if not cmcs: raise ValueError('WHO5 state produced no active diagnosis from which to derive CMC')
    return cmcs

def validate_summary_plan_doc(doc:dict,statements:list[dict],*,allow_cross_domain_merge:bool=False)->str:
    issues=[]
    if not isinstance(doc,dict):
        safe=_single_mapping_list(doc)
        issues.append(ValidationIssue('summary plan',f'expected mapping; received {_type_name(doc)}','remove the extra one-item list wrapper without changing fields or values' if safe else 'return the required mapping with dispositions and parts',repair_class='serialization' if safe else 'content',received=_preview(doc),expected='mapping')); doc={}
    _exact(issues,doc,{'dispositions','parts'}); smap={s['statement_id']:s for s in statements}
    disp=doc.get('dispositions')
    if not isinstance(disp,list):
        safe=isinstance(disp,dict)
        issues.append(ValidationIssue('dispositions',f'expected list; received {_type_name(disp)}','wrap the existing single disposition mapping in a list without changing it' if safe else 'return one disposition mapping per statement',repair_class='serialization' if safe else 'content',received=_preview(disp),expected=f'list with {len(statements)} rows')); disp=[]
    if len(disp)!=len(statements): issues.append(ValidationIssue('dispositions',f'expected {len(statements)} rows, received {len(disp)}','return every statement exactly once in order',repair_class='content'))
    decisions={}
    for i,srow in enumerate(statements):
        if i>=len(disp): continue
        raw=disp[i]; path=f'dispositions[{i}]'
        if not isinstance(raw,dict):
            safe=_single_mapping_list(raw); issues.append(ValidationIssue(path,f'expected mapping; received {_type_name(raw)}','remove the extra one-item list wrapper without changing fields or values' if safe else 'return one disposition mapping with statement_id, decision, and reason',repair_class='serialization' if safe else 'content',received=_preview(raw),expected='mapping')); continue
        _exact(issues,raw,{'statement_id','decision','reason'},path)
        if raw.get('statement_id')!=srow['statement_id']: issues.append(ValidationIssue(f'{path}.statement_id',f'received {raw.get("statement_id")!r}',f'copy {srow["statement_id"]!r}',repair_class='content'))
        dec=raw.get('decision'); decisions[srow['statement_id']]=dec
        if dec not in {'include','omit','split'}: issues.append(ValidationIssue(f'{path}.decision',f'invalid {dec!r}',"use exactly 'include', 'omit', or 'split'",repair_class='content'))
        if srow.get('domain')=='diagnosis' and dec=='omit': issues.append(ValidationIssue(f'{path}.decision','diagnosis sentence cannot be omitted','use include or split for diagnosis statements',repair_class='content'))
        if dec in {'include','split'} and raw.get('reason') is not None: issues.append(ValidationIssue(f'{path}.reason',f'{dec} requires null','set reason: null',repair_class='content'))
        if dec=='omit' and not _nonempty(raw.get('reason')): issues.append(ValidationIssue(f'{path}.reason','omit requires reason','state why omission is safe',repair_class='content'))
    parts=doc.get('parts')
    if not isinstance(parts,list):
        safe=isinstance(parts,dict)
        issues.append(ValidationIssue('parts',f'expected list; received {_type_name(parts)}','wrap the existing single part mapping in a list without changing it' if safe else 'return the included/split statement parts as a list of mappings',repair_class='serialization' if safe else 'content',received=_preview(parts),expected='list')); parts=[]
    occurrences={sid:[] for sid in smap}; group_domains={}; group_roles={}
    for i,raw in enumerate(parts):
        path=f'parts[{i}]'
        if not isinstance(raw,dict):
            safe=_single_mapping_list(raw); issues.append(ValidationIssue(path,f'expected mapping; received {_type_name(raw)}','remove the extra one-item list wrapper without changing fields or values' if safe else 'return one part mapping with statement_id, group, and split_text',repair_class='serialization' if safe else 'content',received=_preview(raw),expected='mapping')); continue
        _exact(issues,raw,{'statement_id','group','split_text'},path); sid=raw.get('statement_id'); group=raw.get('group')
        if sid not in smap: issues.append(ValidationIssue(f'{path}.statement_id',f'unknown {sid!r}','use one exact supplied statement ID',repair_class='content',expected=str(sorted(smap)))); continue
        if not _nonempty(group):
            cls='serialization' if group is not None and not isinstance(group,str) else 'content'; issues.append(ValidationIssue(f'{path}.group',f'expected non-empty string; received {_type_name(group)}','quote/reserialize the existing group label as one string' if cls=='serialization' else 'return a non-empty temporary group label',repair_class=cls,received=_preview(group),expected='non-empty string'))
        else:
            statement=smap[sid]; domain=statement['domain']; role=statement.get('summary_role'); prior=group_domains.get(group)
            if prior is not None and prior!=domain and not allow_cross_domain_merge: issues.append(ValidationIssue(f'{path}.group',f'group {group!r} mixes domains {prior!r} and {domain!r}','use a different group label; current settings do not permit cross-domain merging',repair_class='content'))
            elif prior is None: group_domains[group]=domain
            if group in group_roles:
                prior_role=group_roles[group]
                if prior_role!=role and (prior_role is not None or role is not None):
                    issues.append(ValidationIssue(f'{path}.group',f'group {group!r} mixes summary roles {prior_role!r} and {role!r}','use separate groups for statements with different summary_role values',repair_class='content'))
            else: group_roles[group]=role
        occurrences[sid].append(raw)
    for sid,statement in smap.items():
        dec=decisions.get(sid); rows=occurrences.get(sid) or []
        if dec=='omit' and rows: issues.append(ValidationIssue(f'parts for {sid}',f'omitted statement appears {len(rows)} time(s)','remove all parts for omitted statements',repair_class='content'))
        if dec=='include':
            if len(rows)!=1: issues.append(ValidationIssue(f'parts for {sid}',f'include requires exactly one part, received {len(rows)}','return exactly one part for the included statement',repair_class='content'))
            elif rows[0].get('split_text') is not None: issues.append(ValidationIssue(f'parts for {sid}.split_text','include requires split_text: null','set split_text: null so Python uses the original sentence verbatim',repair_class='content'))
        if dec=='split':
            if len(rows)<2: issues.append(ValidationIssue(f'parts for {sid}',f'split requires at least two parts, received {len(rows)}','return two or more parts for the split statement',repair_class='content'))
            for j,row in enumerate(rows):
                value=row.get('split_text')
                if not _nonempty(value):
                    cls='serialization' if _scalar_string_repairable(value) else 'content'; issues.append(ValidationIssue(f'parts for {sid}[{j}].split_text',f'expected non-empty split text; received {_type_name(value)}','quote/reserialize the existing split text as one string without changing its words' if cls=='serialization' else 'state the semantic fragment assigned to this split part',repair_class=cls,received=_preview(value),expected='non-empty string'))
    fail('summarization plan',issues); return 'summarization plan validated'

def validate_summary_plan_text(text:str,statements:list[dict],*,allow_cross_domain_merge:bool=False)->str: return validate_summary_plan_doc(parse_yaml_mapping(text,'summary plan'),statements,allow_cross_domain_merge=allow_cross_domain_merge)

def build_summary_blocks(plan:dict,statements:list[dict],*,domain_order:list[str]|None=None,allow_cross_domain_merge:bool=False)->list[dict]:
    validate_summary_plan_doc(plan,statements,allow_cross_domain_merge=allow_cross_domain_merge); smap={s['statement_id']:s for s in statements}; order={s['statement_id']:i for i,s in enumerate(statements)}; configured=domain_order or list(DOMAIN_HEADINGS); domain_order={d:i for i,d in enumerate(configured)}
    groups={}
    for part_index,part in enumerate(plan['parts']):
        sid=part['statement_id']; statement=smap[sid]; key=(statement['domain'],part['group'])
        text=statement['statement'] if part.get('split_text') is None else part['split_text']
        groups.setdefault(key,[]).append({'statement_id':sid,'text':text,'split':part.get('split_text') is not None,'_part_index':part_index})
    for parts in groups.values(): parts.sort(key=lambda p:(order[p['statement_id']],p['_part_index']))
    sorted_groups=sorted(groups.items(),key=lambda kv:(domain_order.get(kv[0][0],len(domain_order)),min(order[p['statement_id']] for p in kv[1]),min(p['_part_index'] for p in kv[1])))
    counts={d:0 for d in DOMAIN_HEADINGS}; blocks=[]
    for (domain,_group),parts in sorted_groups:
        counts[domain]+=1; ids=[]
        for p in parts:
            if p['statement_id'] not in ids: ids.append(p['statement_id'])
        clean_parts=[]
        for p in parts:
            q=dict(p); q.pop('_part_index',None); clean_parts.append(q)
        roles=[]
        for sid in ids:
            role=smap[sid].get('summary_role')
            if role is not None and role not in roles: roles.append(role)
        block={'block_id':f'{domain}-{counts[domain]}','domain':domain,'source_statement_ids':ids,'source_parts':clean_parts}
        if roles: block['summary_role']=roles[0] if len(roles)==1 else roles
        blocks.append(block)
    return blocks

def validate_paraphrase_batch_text(text:str,blocks:list[dict])->str:
    d=parse_yaml_mapping(text,'paraphrase batch'); issues=[]; _exact(issues,d,{'sentences'}); rows=d.get('sentences')
    if not isinstance(rows,list):
        safe=isinstance(rows,dict)
        issues.append(ValidationIssue('sentences',f'expected list; received {_type_name(rows)}','wrap the existing single sentence mapping in a list without changing it' if safe else 'return one sentence mapping per block',repair_class='serialization' if safe else 'content',received=_preview(rows),expected=f'list with {len(blocks)} rows')); rows=[]
    if len(rows)!=len(blocks): issues.append(ValidationIssue('sentences',f'expected {len(blocks)} rows, received {len(rows)}','return exactly one sentence row for every supplied block, in the same order',repair_class='content'))
    for i,raw in enumerate(rows):
        path=f'sentences[{i}]'
        if not isinstance(raw,dict):
            safe=_single_mapping_list(raw); issues.append(ValidationIssue(path,f'expected mapping; received {_type_name(raw)}','remove the extra one-item list wrapper without changing fields or values' if safe else 'return one mapping with block_id and sentence',repair_class='serialization' if safe else 'content',received=_preview(raw),expected='mapping')); continue
        _exact(issues,raw,{'block_id','sentence'},path)
        if i<len(blocks) and raw.get('block_id')!=blocks[i]['block_id']: issues.append(ValidationIssue(f'{path}.block_id',f'received {raw.get("block_id")!r}',f'copy {blocks[i]["block_id"]!r}',repair_class='content'))
        sentence=raw.get('sentence')
        if not _nonempty(sentence):
            cls='serialization' if _scalar_string_repairable(sentence) else 'content'; issues.append(ValidationIssue(f'{path}.sentence',f'expected non-empty string; received {_type_name(sentence)}','quote/reserialize the existing sentence as one string without changing its words' if cls=='serialization' else 'return one self-contained sentence ending with a full stop',repair_class=cls,received=_preview(sentence),expected='one-line sentence'))
        elif sentence!=sentence.strip() or '\n' in sentence: issues.append(ValidationIssue(f'{path}.sentence','must be one clean physical-line sentence','reserialize the same sentence on one physical line without changing its words',repair_class='serialization',received=_preview(sentence),expected='one physical-line sentence'))
        elif not sentence.endswith('.'): issues.append(ValidationIssue(f'{path}.sentence','sentence does not end with a full stop','return one self-contained sentence ending with a full stop',repair_class='content'))
    fail('paraphrase batch',issues); return 'paraphrase batch validated'

def validate_paraphrase_audit_batch_text(text:str,blocks:list[dict])->str:
    d=parse_yaml_mapping(text,'paraphrase audit batch'); issues=[]; _exact(issues,d,{'audits'}); rows=d.get('audits')
    if not isinstance(rows,list):
        safe=isinstance(rows,dict)
        issues.append(ValidationIssue('audits',f'expected list; received {_type_name(rows)}','wrap the existing single audit mapping in a list without changing it' if safe else 'return one audit mapping per block',repair_class='serialization' if safe else 'content',received=_preview(rows),expected=f'list with {len(blocks)} rows')); rows=[]
    if len(rows)!=len(blocks): issues.append(ValidationIssue('audits',f'expected {len(blocks)} rows, received {len(rows)}','return exactly one audit row for every supplied block, in the same order',repair_class='content'))
    for i,raw in enumerate(rows):
        path=f'audits[{i}]'
        if not isinstance(raw,dict):
            safe=_single_mapping_list(raw); issues.append(ValidationIssue(path,f'expected mapping; received {_type_name(raw)}','remove the extra one-item list wrapper without changing fields or values' if safe else 'return one audit mapping with block_id, preserved, issue, and negative_guidance',repair_class='serialization' if safe else 'content',received=_preview(raw),expected='mapping')); continue
        _exact(issues,raw,{'block_id','preserved','issue','negative_guidance'},path)
        if i<len(blocks) and raw.get('block_id')!=blocks[i]['block_id']: issues.append(ValidationIssue(f'{path}.block_id',f'received {raw.get("block_id")!r}',f'copy {blocks[i]["block_id"]!r}',repair_class='content'))
        preserved=raw.get('preserved')
        if not isinstance(preserved,bool): issues.append(ValidationIssue(f'{path}.preserved',f'expected boolean; received {_type_name(preserved)}','serialize the existing true/false decision as a YAML boolean' if _bool_repairable(preserved) else 'return the required true/false decision',repair_class='serialization' if _bool_repairable(preserved) else 'content',received=_preview(preserved),expected='true or false'))
        issue=raw.get('issue')
        if preserved is True and issue is not None: issues.append(ValidationIssue(f'{path}.issue','preserved=true requires issue: null','set issue: null',repair_class='content'))
        if preserved is False and not _nonempty(issue): issues.append(ValidationIssue(f'{path}.issue','preserved=false requires a non-empty explanation','state the specific semantic-preservation problem',repair_class='content'))
        guidance=raw.get('negative_guidance')
        if not isinstance(guidance,list):
            safe=isinstance(guidance,str); issues.append(ValidationIssue(f'{path}.negative_guidance',f'expected list; received {_type_name(guidance)}','wrap the existing guidance string in a list without changing it' if safe else 'return a list of negative-guidance strings',repair_class='serialization' if safe else 'content',received=_preview(guidance),expected='list'))
            guidance=[]
        for j,g in enumerate(guidance): _nonempty(g) or issues.append(ValidationIssue(f'{path}.negative_guidance[{j}]','expected non-empty string','state what semantic mistake must not be repeated, without prescribing replacement prose',repair_class='content'))
        if preserved is False and not guidance: issues.append(ValidationIssue(f'{path}.negative_guidance','preserved=false requires negative guidance','state what semantic mistake must not be repeated on de-novo regeneration',repair_class='content'))
    fail('paraphrase audit batch',issues); return 'paraphrase audit batch validated'

def fallback_block_sentence(block:dict)->str:
    texts=[]
    for part in block.get('source_parts') or []:
        text=str(part.get('text') or '').strip()
        if text: texts.append(text.rstrip('.'))
    return ('; '.join(texts).strip()+'.') if texts else 'Unresolved report block.'

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
