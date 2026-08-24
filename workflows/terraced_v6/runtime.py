"""Minimal deterministic runtime helpers retained for terraced-v6."""
from __future__ import annotations
import json, re, shutil, sys
from pathlib import Path
import yaml
from scripts import vocab
from scripts.core.validated_model_task import ValidationFailure, ValidationIssue, fail
from workflows.terraced_v6 import layout

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

def validate_no_false_missing_case_claims(doc:dict,case:dict,*,domain:str='clinical')->str:
    """Reject claims that an explicitly observed case fact is missing/pending/unavailable."""
    issues=[]
    text=yaml.safe_dump(doc,sort_keys=False,allow_unicode=True,width=110)
    negative=r'(?:missing|pending|unavailable|unknown|not\s+(?:done|performed|available|reported)|no\s+(?:available\s+)?)'
    for row in case.get('case_facts') or []:
        if not isinstance(row,dict): continue
        kind=str(row.get('kind') or '').strip()
        value=str(row.get('value') or '').strip()
        observed=' '.join((kind,value)).casefold()
        if not kind or any(token in observed for token in ('pending','not done','not performed','unavailable','awaiting')):
            continue
        aliases={kind.casefold()}
        words=[re.sub(r'[^a-z0-9]+','',w.casefold()) for w in kind.split()]
        for word in words:
            if len(word)>=5:
                aliases.add(word[:-1] if word.endswith('s') else word)
        if 'blast' in kind.casefold(): aliases.update({'blast','blast percentage','blast count'})
        if 'cytogen' in kind.casefold(): aliases.update({'cytogenetic','cytogenetics','karyotype'})
        for alias in sorted(aliases,key=len,reverse=True):
            a=re.escape(alias)
            patterns=(
                rf'\b{negative}\b[^.;\n]{{0,45}}\b{a}\b',
                rf'\b{a}\b[^.;\n]{{0,18}}\b(?:is\s+|are\s+|was\s+|were\s+)?{negative}\b',
            )
            if any(re.search(pattern,text,flags=re.IGNORECASE) for pattern in patterns):
                issues.append(ValidationIssue(
                    f'{domain} proforma',
                    f'claims observed case fact {kind!r} is missing/pending/unavailable',
                    f'use the supplied observed value {value!r}; do not describe this case fact as missing or indeterminate',
                    repair_class='content',
                    received=f'{kind}: {value}',
                    expected='observed case fact used as supplied',
                ))
                break
    fail(f'{domain} case-fact consistency',issues)
    return f'{domain} case facts consistent'

def case_genes(case:dict)->list[str]:
    out=[]
    for row in case.get('variants') or []:
        g=row.get('gene')
        if isinstance(g,str) and g not in out: out.append(g)
    return out

def derive_cmcs(doc:dict)->list[str]:
    disease=doc.get("schema_disease")
    cmc=vocab.preferred_case_major_category(disease)
    if disease==vocab.NO_HAEMATOLOGICAL_MALIGNANCY:
        cmc=vocab.NO_HAEMATOLOGICAL_MALIGNANCY
    if not cmc:
        raise ValueError(f"WHO5 schema disease {disease!r} has no deterministic preferred CMC mapping")
    return [cmc]

def ensure_sentence(text:str)->str:
    text=" ".join(str(text or "").split()).strip()
    if not text:
        return ""
    return text if text[-1] in ".!?" else text+"."

def normalize_dx(text:str)->str:
    text=re.sub(r"\s+"," ",str(text or "").strip()).casefold()
    text=re.sub(r"[^a-z0-9]+"," ",text)
    return " ".join(text.split())
