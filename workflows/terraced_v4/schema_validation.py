"""Strict structural validators for terraced-v4 prototype proformas.

These validators deliberately avoid clinical-semantic judgments.  They enforce
shape, identity, coverage and mutually exclusive negative buckets only.
"""
from __future__ import annotations
from typing import Iterable
import yaml


def _doc(text:str, context:str)->dict:
    try: value=yaml.safe_load(text)
    except yaml.YAMLError as exc: raise ValueError(f'{context}: invalid YAML: {exc}') from exc
    if not isinstance(value,dict): raise ValueError(f'{context}: expected top-level mapping')
    return value

def _exact(row:dict, keys:set[str], path:str):
    if set(row)!=keys: raise ValueError(f'{path}: expected fields {sorted(keys)}, received {sorted(row)}')

def _text(value,path):
    if not isinstance(value,str) or not value.strip(): raise ValueError(f'{path}: expected non-empty string')

def _reasons(value,path):
    if not isinstance(value,list) or not value: raise ValueError(f'{path}: expected non-empty list of reasons')
    for i,x in enumerate(value): _text(x,f'{path}[{i}]')

def validate_diagnosis(text:str, *, allowed_diseases:set[str])->str:
    d=_doc(text,'diagnosis proforma'); _exact(d,{'who5','icc','concordance','concurrent_second_diagnosis'},'diagnosis')
    who=d['who5'];
    if not isinstance(who,dict): raise ValueError('who5: expected mapping')
    _exact(who,{'diagnoses'},'who5')
    rows=who['diagnoses']
    if not isinstance(rows,list) or not rows: raise ValueError('who5.diagnoses: expected non-empty list')
    for i,row in enumerate(rows):
        if not isinstance(row,dict): raise ValueError(f'who5.diagnoses[{i}]: expected mapping')
        _exact(row,{'schema_disease','status','diagnosis','reasons'},f'who5.diagnoses[{i}]')
        if row['schema_disease'] not in allowed_diseases: raise ValueError(f'who5.diagnoses[{i}].schema_disease: unknown value {row["schema_disease"]!r}')
        if row['status'] not in {'established','indeterminate'}: raise ValueError(f'who5.diagnoses[{i}].status: use established or indeterminate')
        _text(row['diagnosis'],f'who5.diagnoses[{i}].diagnosis'); _reasons(row['reasons'],f'who5.diagnoses[{i}].reasons')
    icc=d['icc']
    if not isinstance(icc,dict): raise ValueError('icc: expected mapping')
    _exact(icc,{'diagnoses'},'icc')
    rows=icc['diagnoses']
    if not isinstance(rows,list) or not rows: raise ValueError('icc.diagnoses: expected non-empty list')
    for i,row in enumerate(rows):
        if not isinstance(row,dict): raise ValueError(f'icc.diagnoses[{i}]: expected mapping')
        _exact(row,{'status','diagnosis','reasons'},f'icc.diagnoses[{i}]')
        if row['status'] not in {'established','indeterminate'}: raise ValueError(f'icc.diagnoses[{i}].status: use established or indeterminate')
        _text(row['diagnosis'],f'icc.diagnoses[{i}].diagnosis'); _reasons(row['reasons'],f'icc.diagnoses[{i}].reasons')
    con=d['concordance'];
    if not isinstance(con,dict): raise ValueError('concordance: expected mapping')
    _exact(con,{'answer','reasons'},'concordance'); _text(con['answer'],'concordance.answer'); _reasons(con['reasons'],'concordance.reasons')
    sec=d['concurrent_second_diagnosis'];
    if not isinstance(sec,dict): raise ValueError('concurrent_second_diagnosis: expected mapping')
    _exact(sec,{'answer','reasons'},'concurrent_second_diagnosis'); _text(sec['answer'],'concurrent_second_diagnosis.answer'); _reasons(sec['reasons'],'concurrent_second_diagnosis.reasons')
    return 'diagnosis proforma structurally valid'

def _variant_list(value,path,valid:set[str], *, allow_empty=False):
    if not isinstance(value,list) or (not value and not allow_empty): raise ValueError(f'{path}: expected {"a" if not allow_empty else ""} list of variant IDs')
    if len(value)!=len(set(value)): raise ValueError(f'{path}: duplicate variant IDs')
    bad=[v for v in value if v not in valid]
    if bad: raise ValueError(f'{path}: unknown variant IDs {bad}; valid IDs are {sorted(valid)}')

def _effect_rows(doc:dict, bucket:str, valid:set[str], extra:set[str]=set()):
    rows=doc[bucket]
    if not isinstance(rows,list): raise ValueError(f'{bucket}: expected list')
    covered=set()
    for i,row in enumerate(rows):
        path=f'{bucket}[{i}]'
        if not isinstance(row,dict): raise ValueError(f'{path}: expected mapping')
        _exact(row,{'variants','reason',*extra},path)
        _variant_list(row['variants'],f'{path}.variants',valid); covered.update(row['variants'])
        _text(row['reason'],f'{path}.reason')
        for field in extra: _text(row[field],f'{path}.{field}')
    return covered

def _coverage(valid:set[str], positive:set[str], negative:list, name:str):
    _variant_list(negative,f'{name}.no_effect',valid,allow_empty=True); neg=set(negative)
    overlap=positive & neg
    if overlap: raise ValueError(f'{name}: variants cannot be both effect and no_effect: {sorted(overlap)}')
    missing=valid-(positive|neg)
    if missing: raise ValueError(f'{name}: every variant must be discussed; missing {sorted(missing)}')

def validate_prognosis(text:str, valid:set[str])->str:
    d=_doc(text,'prognosis'); _exact(d,{'favorable','adverse','other','uncertain','no_effect','overall'},'prognosis')
    positive=set()
    for b in ('favorable','adverse','other','uncertain'): positive |= _effect_rows(d,b,valid)
    _coverage(valid,positive,d['no_effect'],'prognosis')
    overall=d['overall']
    if not isinstance(overall,dict): raise ValueError('overall: expected mapping')
    _exact(overall,{'classification','reason'},'overall'); _text(overall['classification'],'overall.classification'); _text(overall['reason'],'overall.reason')
    return 'prognosis proforma structurally valid'

def validate_treatment(text:str, valid:set[str])->str:
    d=_doc(text,'treatment'); _exact(d,{'drug_target','drug_resistance','other','no_effect'},'treatment')
    positive=set()
    positive |= _effect_rows(d,'drug_target',valid,{'therapy'})
    positive |= _effect_rows(d,'drug_resistance',valid,{'therapy'})
    positive |= _effect_rows(d,'other',valid)
    _coverage(valid,positive,d['no_effect'],'treatment')
    return 'treatment proforma structurally valid'

def validate_biomarker(text:str, valid:set[str])->str:
    d=_doc(text,'biomarker'); _exact(d,{'suitable_mrd','unsuitable_mrd','uncertain','no_effect'},'biomarker')
    positive=set()
    for b in ('suitable_mrd','unsuitable_mrd','uncertain'): positive |= _effect_rows(d,b,valid)
    _coverage(valid,positive,d['no_effect'],'biomarker')
    return 'biomarker proforma structurally valid'

def validate_germline(text:str, valid:set[str])->str:
    d=_doc(text,'germline'); _exact(d,{'suspect','uncertain','not_suspect','clinical_support'},'germline')
    classes={}
    for bucket in ('suspect','uncertain'):
        rows=d[bucket]
        if not isinstance(rows,list): raise ValueError(f'{bucket}: expected list')
        for i,row in enumerate(rows):
            path=f'{bucket}[{i}]'
            if not isinstance(row,dict): raise ValueError(f'{path}: expected mapping')
            _exact(row,{'variants','reason'},path); _variant_list(row['variants'],f'{path}.variants',valid); _text(row['reason'],f'{path}.reason')
            for v in row['variants']:
                if v in classes: raise ValueError(f'germline: {v} classified more than once')
                classes[v]=bucket
    _variant_list(d['not_suspect'],'not_suspect',valid,allow_empty=True)
    for v in d['not_suspect']:
        if v in classes: raise ValueError(f'germline: {v} classified both {classes[v]} and not_suspect')
        classes[v]='not_suspect'
    missing=valid-set(classes)
    if missing: raise ValueError(f'germline: every variant must be classified; missing {sorted(missing)}')
    support=d['clinical_support']
    if not isinstance(support,list): raise ValueError('clinical_support: expected list')
    eligible={v for v,c in classes.items() if c in {'suspect','uncertain'}}; seen=set()
    for i,row in enumerate(support):
        path=f'clinical_support[{i}]'
        if not isinstance(row,dict): raise ValueError(f'{path}: expected mapping')
        _exact(row,{'variants','support','reason'},path); _variant_list(row['variants'],f'{path}.variants',valid)
        if row['support'] not in {'present','absent','unknown'}: raise ValueError(f'{path}.support: use present, absent, or unknown')
        _text(row['reason'],f'{path}.reason')
        bad=set(row['variants'])-eligible
        if bad: raise ValueError(f'{path}: clinical_support should only assess suspect/uncertain variants; invalid {sorted(bad)}')
        seen.update(row['variants'])
    missing_support=eligible-seen
    if missing_support: raise ValueError(f'clinical_support: missing suspect/uncertain variants {sorted(missing_support)}')
    return 'germline proforma structurally valid'

def validate_evidence_match(text:str, candidate_ids:set[str])->str:
    d=_doc(text,'evidence match'); _exact(d,{'card_id','source','quote'},'evidence_match')
    if d['card_id'] not in candidate_ids: raise ValueError(f'evidence_match.card_id: {d["card_id"]!r} was not among supplied candidate cards')
    _text(d['source'],'evidence_match.source'); _text(d['quote'],'evidence_match.quote')
    return 'evidence match structurally valid'

def validate_evidence_audit(text:str)->str:
    d=_doc(text,'evidence audit'); _exact(d,{'obvious_mismatch','risk','comments'},'evidence_audit')
    if not isinstance(d['obvious_mismatch'],bool): raise ValueError('evidence_audit.obvious_mismatch: expected boolean')
    if d['risk'] not in {'none','warning'}: raise ValueError('evidence_audit.risk: use none or warning')
    if not isinstance(d['comments'],list) or any(not isinstance(x,str) or not x.strip() for x in d['comments']): raise ValueError('evidence_audit.comments: expected list of non-empty strings (may be empty)')
    return 'evidence audit structurally valid'

def validate_reportable_sentences(text:str, elements:list[dict])->str:
    d=_doc(text,'reportable sentences'); _exact(d,{'sentences'},'reportable_sentences')
    rows=d['sentences']
    if not isinstance(rows,list) or len(rows)!=len(elements): raise ValueError(f'reportable_sentences.sentences: expected {len(elements)} rows, received {len(rows) if isinstance(rows,list) else type(rows).__name__}')
    for i,(row,element) in enumerate(zip(rows,elements)):
        path=f'sentences[{i}]'
        if not isinstance(row,dict): raise ValueError(f'{path}: expected mapping')
        _exact(row,{'schema_id','sentence'},path)
        if row['schema_id']!=element['schema_id']: raise ValueError(f'{path}.schema_id: expected {element["schema_id"]!r}, received {row["schema_id"]!r}')
        _text(row['sentence'],f'{path}.sentence')
        if '\n' in row['sentence']: raise ValueError(f'{path}.sentence: must be one physical line')
    return 'reportable sentences structurally valid'
