"""Minimal deterministic runtime helpers retained for proforma-v1."""
from __future__ import annotations
import json, re, shutil, sys
from pathlib import Path
import yaml
from scripts import vocab
from validation.scripts.bundled_cases import is_bundled_mode, retrieve_case_input
from scripts.core.validated_model_task import ValidationIssue, fail
from workflows.proforma_v1 import layout
HERE=Path(__file__).resolve().parent; REPO_ROOT=HERE.parents[1]
WHO5_EXCLUDED_SCHEMA_DISEASES={'MDS/AML'}
HEADINGS={'**Diagnosis**':'diagnosis','**Prognosis**':'prognosis','**Treatment Implications**':'treatment','**MRD**':'biomarker','**Germline**':'germline'}
DOMAIN_HEADINGS={v:k for k,v in HEADINGS.items()}
WHO5_LEGACY_FIELDS=('schema_disease','diagnosis','diagnostic_effect','variants','reason')
EVENT_TYPES={'sequence_variant','fusion','copy_number','structural_variant','other','unknown'}
def legacy_who_view(who:dict|None)->dict:
    """Project a WHO model artifact to the pre-variant-assessment workflow contract."""
    row=who or {}
    return {field:row.get(field) for field in WHO5_LEGACY_FIELDS}
def concurrent_pathology_from_who(who:dict|None)->list[dict]:
    """Project WHO variant assessments into non-routing concurrent-pathology signals."""
    out=[]
    for row in (who or {}).get('variant_assessments') or []:
        if not isinstance(row,dict) or row.get('classification')!='diagnostic_for_other_pathology':
            continue
        out.append({
            'variant_id':row.get('variant_id'),
            'other_pathology':row.get('other_pathology'),
            'reason':row.get('reason'),
        })
    return out
def authoritative_who_assessment_source(who1:dict|None,who2:dict|None,who1_commit:dict|None)->dict|None:
    """Return the raw authoritative WHO artifact for non-routing variant assessment use.
    A rejected WHO1 routing change falls back to supplied morphology. Its raw WHO1
    interpretation must not create concurrent-pathology report propositions.
    """
    if who2:
        return who2
    if (who1_commit or {}).get('fallback'):
        return None
    return who1
def setup_assets(work_dir:Path,*,mode:str,case_id:str|None=None,example:int|None=None)->None:
    work=Path(work_dir); layout.ensure_dirs(work)
    panel_root=work/'ngs-panel-scope.md'; panel_out=layout.setup(work,'ngs-panel-scope.md',existing=False)
    if panel_root.is_file() and panel_root!=panel_out: shutil.move(str(panel_root),str(panel_out))
    cmc_root=work/'case-major-categories.json'; cmc_out=layout.setup(work,'case-major-categories.json',existing=False)
    cmc_out.write_text(json.dumps({'case_major_categories':list(vocab.CASE_MAJOR_CATEGORIES),'instruction':'bootstrap_cmcs are retrieval scaffolds only. Authoritative CMCs are derived deterministically from validated WHO5 schema diseases.'},indent=2,ensure_ascii=False)+'\n',encoding='utf-8'); cmc_root.unlink(missing_ok=True)
    allowed=[d for d in vocab.CASE_DISEASES if d not in WHO5_EXCLUDED_SCHEMA_DISEASES]
    layout.setup(work,'allowed-schema-diseases.json',existing=False).write_text(json.dumps({'schema_version':1,'allowed_schema_diseases':allowed,'instruction':'WHO5 schema disease controls deterministic CMC routing; ICC never routes evidence.'},indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    if is_bundled_mode(mode):
        selector=example if mode=='nel-demo' else case_id
        if selector is None: raise ValueError(f'{mode} requires a bundled case selector')
        text=retrieve_case_input(mode,selector)
        p=layout.input(work,'case.md',existing=False); payload=text.rstrip()+'\n'
        if p.exists() and p.read_text(encoding='utf-8')!=payload: raise ValueError(f'{p} exists with different bundled case content')
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
    case_fields={'provisional_disease','morphologic_diagnosis_origin','patient_age','bootstrap_cmcs','variants','detected_variants_summary','ngs_result_completeness','ngs_no_variants_detected','case_facts'}
    # diagnosis_status was added after existing run artifacts were already in use.
    # Accept its absence for legacy saved cases, but reject every other unexpected field.
    expected=case_fields|({'diagnosis_status'} if 'diagnosis_status' in d else set())
    _exact(issues,d,expected)
    diagnosis_status=d.get('diagnosis_status','new')
    if diagnosis_status not in {'new','progress'}:
        issues.append(ValidationIssue('diagnosis_status',f'expected new or progress; received {_preview(diagnosis_status)}','use new for a diagnostic work-up and progress for a follow-up/response/progression specimen with an established prior disease',repair_class='content',received=_preview(diagnosis_status),expected="'new' or 'progress'"))
    provisional=d.get('provisional_disease')
    if not _nonempty(provisional):
        cls='serialization' if _scalar_string_repairable(provisional) else 'content'
        fix='quote/reserialize the existing value as one string without changing its words' if cls=='serialization' else 'return a source-faithful provisional disease description'
        issues.append(ValidationIssue('provisional_disease',f'expected non-empty string; received {_type_name(provisional)}',fix,repair_class=cls,received=_preview(provisional),expected='non-empty string'))
    origin=d.get('morphologic_diagnosis_origin')
    if origin not in {'supplied','inferred'}:
        issues.append(ValidationIssue('morphologic_diagnosis_origin',f'expected supplied or inferred; received {_preview(origin)}','use supplied only when the case explicitly states the morphologic/pathologic diagnosis; otherwise use inferred',repair_class='content',received=_preview(origin),expected="'supplied' or 'inferred'"))
    age=d.get('patient_age')
    if age is not None and not _nonempty(age):
        cls='serialization' if _scalar_string_repairable(age) else 'content'
        issues.append(ValidationIssue('patient_age',f'expected source-faithful non-empty string or null; received {_type_name(age)}','quote/reserialize the supplied age as one string without changing it' if cls=='serialization' else 'return the explicitly supplied age source-faithfully, or null when age was not supplied',repair_class=cls,received=_preview(age),expected='non-empty string or null'))
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
        issues.append(ValidationIssue('variants',f'expected list; received {_type_name(variants)}','wrap the existing single variant object in a JSON list without changing it' if safe else 'return every detected molecular finding as a list of variant objects in case order',repair_class='serialization' if safe else 'content',received=_preview(variants),expected='list of variant objects')); variants=[]
    for i,row in enumerate(variants,1):
        path=f'variants[{i-1}]'
        if not isinstance(row,dict):
            safe=_single_mapping_list(row)
            issues.append(ValidationIssue(path,f'expected object; received {_type_name(row)}','remove the extra one-item list wrapper without changing fields or values' if safe else 'return one variant object with variant_id, gene, description, event_type, and vaf',repair_class='serialization' if safe else 'content',received=_preview(row),expected='object')); continue
        _exact(issues,row,{'variant_id','gene','description','event_type','vaf'},path)
        if row.get('variant_id')!=f'V{i}': issues.append(ValidationIssue(f'{path}.variant_id',f'received {row.get("variant_id")!r}',f'use sequential stable ID V{i}',repair_class='content'))
        gene=row.get('gene')
        if not _nonempty(gene) or gene!=gene.upper(): issues.append(ValidationIssue(f'{path}.gene',f'invalid gene {gene!r}','use uppercase reported gene symbol',repair_class='content'))
        desc=row.get('description')
        if not _nonempty(desc):
            cls='serialization' if _scalar_string_repairable(desc) else 'content'
            issues.append(ValidationIssue(f'{path}.description',f'expected non-empty string; received {_type_name(desc)}','quote/reserialize the existing description as one string without changing its words' if cls=='serialization' else 'preserve complete molecular finding description',repair_class=cls,received=_preview(desc),expected='non-empty string'))
        elif require_gene_prefixed_description and isinstance(gene,str) and gene.strip() and not desc.strip().startswith(gene.strip()):
            issues.append(ValidationIssue(f'{path}.description',f'description does not begin with gene {gene!r}',f'prefix the unchanged detailed molecular finding description with exact gene {gene!r}',repair_class='content',received=_preview(desc),expected=f'{gene} + complete reported molecular finding description'))
        event_type=row.get('event_type')
        if event_type not in EVENT_TYPES:
            issues.append(ValidationIssue(f'{path}.event_type',f'expected a closed molecular event type; received {_preview(event_type)}',f'use exactly one of {sorted(EVENT_TYPES)} from the supplied molecular description; use unknown when the case does not permit classification',repair_class='content',received=_preview(event_type),expected=str(sorted(EVENT_TYPES))))
        vaf=row.get('vaf')
        if vaf is not None and not _nonempty(vaf):
            cls='serialization' if _scalar_string_repairable(vaf) else 'content'
            issues.append(ValidationIssue(f'{path}.vaf',f'expected source-faithful non-empty string or null; received {_type_name(vaf)}','quote/reserialize the supplied VAF as one string without changing it' if cls=='serialization' else 'return the explicitly supplied VAF source-faithfully, or null when VAF was not supplied',repair_class=cls,received=_preview(vaf),expected='non-empty string or null'))
    summary=d.get('detected_variants_summary')
    if not _nonempty(summary):
        cls='serialization' if _scalar_string_repairable(summary) else 'content'
        issues.append(ValidationIssue('detected_variants_summary',f'expected non-empty string; received {_type_name(summary)}','quote/reserialize the existing summary as one string without changing its words' if cls=='serialization' else 'return one clean source-faithful sentence',repair_class=cls,received=_preview(summary),expected='non-empty one-line string'))
    elif '\n' in summary or summary!=summary.strip():
        issues.append(ValidationIssue('detected_variants_summary','must be one clean physical line','reserialize the same summary on one physical line without changing its words',repair_class='serialization',received=_preview(summary),expected='one physical-line string'))
    completeness=d.get('ngs_result_completeness')
    if completeness not in {'complete','incomplete'}:
        issues.append(ValidationIssue('ngs_result_completeness',f'expected complete or incomplete; received {_preview(completeness)}','use complete unless the supplied NGS result is explicitly partial, selected, limited, abbreviated, pending, or otherwise incomplete',repair_class='content',received=_preview(completeness),expected="'complete' or 'incomplete'"))
    negatives=d.get('ngs_no_variants_detected')
    if not isinstance(negatives,list):
        issues.append(ValidationIssue('ngs_no_variants_detected',f'expected list; received {_type_name(negatives)}','return a JSON list; during structure extraction use an empty list because core materializes panel negatives deterministically',repair_class='serialization' if isinstance(negatives,str) else 'content',received=_preview(negatives),expected='list of uppercase gene symbols'))
        negatives=[]
    seen_negative=set()
    for i,gene in enumerate(negatives):
        path=f'ngs_no_variants_detected[{i}]'
        if not _nonempty(gene) or gene!=gene.upper() or not re.fullmatch(r'[A-Z0-9]+',gene or ''):
            issues.append(ValidationIssue(path,f'invalid gene {gene!r}','use an uppercase panel gene symbol',repair_class='content',received=_preview(gene),expected='uppercase gene symbol'))
        elif gene in seen_negative:
            issues.append(ValidationIssue(path,f'duplicate gene {gene!r}','list each negative panel gene once',repair_class='content',received=gene,expected='unique gene symbol'))
        seen_negative.add(gene)
    if completeness=='incomplete' and negatives:
        issues.append(ValidationIssue('ngs_no_variants_detected','must be empty when ngs_result_completeness is incomplete','return [] because no panel-wide negative inference is permitted for an explicitly incomplete result',repair_class='content',received=_preview(negatives),expected='[]'))
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
def parse_ngs_panel_genes(text:str)->list[str]:
    """Return the configured gene-level NGS panel scope in source order."""
    genes=re.findall(r"^- `([A-Z0-9]+)`\s*$",str(text),flags=re.MULTILINE)
    if not genes:
        raise ValueError('NGS panel scope contains no parseable gene entries')
    if len(genes)!=len(set(genes)):
        duplicates=sorted({gene for gene in genes if genes.count(gene)>1})
        raise ValueError(f'NGS panel scope contains duplicate gene entries: {duplicates}')
    return genes
def materialize_ngs_no_variants_detected(case:dict,panel_scope_text:str)->dict:
    """Deterministically expand complete panel negatives from detected NGS genes.
    This does not make a clinical inference beyond the configured assay contract:
    the resulting genes are negative only for the variant classes covered by the
    panel scope. Explicitly incomplete results never receive panel-wide negatives.
    """
    panel=parse_ngs_panel_genes(panel_scope_text)
    detected={row.get('gene') for row in case.get('variants') or [] if isinstance(row,dict) and isinstance(row.get('gene'),str)}
    case['ngs_no_variants_detected']=[gene for gene in panel if gene not in detected] if case.get('ngs_result_completeness')=='complete' else []
    return case
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
def has_cmc_expansion(previous:list[str], proposed:list[str])->bool:
    """Return True only when proposed routing adds a CMC absent from bootstrap."""
    prior=set(previous or [])
    return any(cmc not in prior for cmc in (proposed or []))
def ensure_sentence(text:str)->str:
    text=" ".join(str(text or "").split()).strip()
    if not text:
        return ""
    return text if text[-1] in ".!?" else text+"."
def normalize_dx(text:str)->str:
    text=re.sub(r"\s+"," ",str(text or "").strip()).casefold()
    text=re.sub(r"[^a-z0-9]+"," ",text)
    return " ".join(text.split())
