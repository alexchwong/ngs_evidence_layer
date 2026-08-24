"""Lean validators for terraced-v6 owner-model proformas."""
from __future__ import annotations
import re
import yaml


def _doc(text, name):
    try:
        d=yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f'{name}: invalid YAML: {exc}') from exc
    if not isinstance(d,dict): raise ValueError(f'{name}: expected top-level mapping')
    return d

def _exact(d, keys, path):
    missing=set(keys)-set(d); extra=set(d)-set(keys)
    if missing or extra: raise ValueError(f'{path}: expected exactly {sorted(keys)}; missing={sorted(missing)} extra={sorted(extra)}')

def _text(v,path,nullable=False):
    if nullable and v is None: return
    if not isinstance(v,str) or not v.strip(): raise ValueError(f'{path}: expected non-empty string'+(' or null' if nullable else ''))

def _variants(v,path,valid,allow_empty=False):
    if not isinstance(v,list): raise ValueError(f'{path}: expected variant-ID list')
    if not allow_empty and not v: raise ValueError(f'{path}: must not be empty')
    if any(not isinstance(x,str) or x not in valid for x in v): raise ValueError(f'{path}: use only supplied variant IDs {sorted(valid)}')
    if len(v)!=len(set(v)): raise ValueError(f'{path}: duplicate variant IDs')
    return set(v)

def validate_who5_diagnosis(text,*,allowed_diseases,valid_variants):
    d=_doc(text,'WHO5 diagnosis'); _exact(d,{'schema_disease','diagnosis','variants','reason'},'WHO5 diagnosis')
    if d['schema_disease'] not in allowed_diseases: raise ValueError(f'WHO5 schema_disease: use one exact allowed value from {sorted(allowed_diseases)}')
    _text(d['diagnosis'],'diagnosis'); _variants(d['variants'],'variants',valid_variants,allow_empty=True); _text(d['reason'],'reason')
    return 'WHO5 diagnosis valid'

def validate_icc_diagnosis(text,*,valid_variants):
    d=_doc(text,'ICC diagnosis'); _exact(d,{'diagnosis','variants','reason'},'ICC diagnosis')
    _text(d['diagnosis'],'diagnosis'); _variants(d['variants'],'variants',valid_variants,allow_empty=True); _text(d['reason'],'reason')
    return 'ICC diagnosis valid'

def validate_second_diagnosis(text,*,valid_variants):
    d=_doc(text,'second diagnosis'); _exact(d,{'diagnosis','variants','reason'},'second diagnosis')
    if d['diagnosis'] is None:
        if d['variants'] not in ([],None) or d['reason'] is not None: raise ValueError('second diagnosis: when diagnosis is null, variants must be [] and reason null')
    else:
        _text(d['diagnosis'],'diagnosis'); _variants(d['variants'],'variants',valid_variants,allow_empty=True); _text(d['reason'],'reason')
    return 'second diagnosis valid'

def _effect_rows(d,bucket,valid,*,therapy=False):
    rows=d.get(bucket)
    if not isinstance(rows,list): raise ValueError(f'{bucket}: expected list')
    covered=set()
    for i,row in enumerate(rows):
        if not isinstance(row,dict): raise ValueError(f'{bucket}[{i}]: expected mapping')
        keys={'variants','reason'}|({'therapy'} if therapy else set()); _exact(row,keys,f'{bucket}[{i}]')
        covered |= _variants(row['variants'],f'{bucket}[{i}].variants',valid)
        _text(row['reason'],f'{bucket}[{i}].reason')
        if therapy: _text(row['therapy'],f'{bucket}[{i}].therapy')
    return covered

def validate_prognosis(text,valid):
    d=_doc(text,'prognosis'); _exact(d,{'favorable','adverse','neutral','uncertain','prognostic_score'},'prognosis')
    seen={}
    for bucket in ('favorable','adverse','neutral','uncertain'):
        for v in _effect_rows(d,bucket,valid):
            if v in seen: raise ValueError(f'prognosis: {v} appears in both {seen[v]} and {bucket}; choose one primary prognostic bucket')
            seen[v]=bucket
    missing=valid-set(seen)
    if missing: raise ValueError(f'prognosis: every variant must be classified; missing {sorted(missing)}')
    score=d['prognostic_score']
    if score is not None:
        if not isinstance(score,dict): raise ValueError('prognostic_score: expected mapping or null')
        _exact(score,{'name','result','reason'},'prognostic_score'); _text(score['name'],'prognostic_score.name'); _text(score['result'],'prognostic_score.result'); _text(score['reason'],'prognostic_score.reason')
        combined=' '.join(str(score[k]) for k in ('name','result','reason'))
        if re.search(r'not\s+calculable|cannot\s+be\s+calculated|unable\s+to\s+calculate|insufficient.*(?:score|calculate)',combined,re.I):
            raise ValueError('prognostic_score: use null when the score is not actually derivable; do not report inability to calculate it')
    return 'prognosis valid'

def validate_treatment(text,valid):
    d=_doc(text,'treatment'); _exact(d,{'drug_target','drug_sensitive','drug_resistant','no_drug_implication'},'treatment')
    positive=set()
    for bucket in ('drug_target','drug_sensitive','drug_resistant'): positive |= _effect_rows(d,bucket,valid,therapy=True)
    negative=_effect_rows(d,'no_drug_implication',valid)
    overlap=positive&negative
    if overlap: raise ValueError(f'treatment: variants cannot have a positive treatment implication and no_drug_implication: {sorted(overlap)}')
    missing=valid-(positive|negative)
    if missing: raise ValueError(f'treatment: every variant must be addressed; missing {sorted(missing)}')
    return 'treatment valid'

def validate_biomarker(text,valid):
    d=_doc(text,'MRD'); _exact(d,{'mrd_marker','not_mrd_marker'},'MRD')
    yes=_effect_rows(d,'mrd_marker',valid); no=_effect_rows(d,'not_mrd_marker',valid)
    if yes&no: raise ValueError(f'MRD: variants cannot be both marker and not marker: {sorted(yes&no)}')
    missing=valid-(yes|no)
    if missing: raise ValueError(f'MRD: every variant must be addressed; missing {sorted(missing)}')
    return 'MRD valid'

def validate_germline(text,valid):
    d=_doc(text,'germline'); _exact(d,{'germline_support','germline_against','germline_uncertain'},'germline')
    seen={}
    for bucket in ('germline_support','germline_against','germline_uncertain'):
        for v in _effect_rows(d,bucket,valid):
            if v in seen: raise ValueError(f'germline: {v} appears in both {seen[v]} and {bucket}; choose one integrated bucket')
            seen[v]=bucket
    missing=valid-set(seen)
    if missing: raise ValueError(f'germline: every variant must be addressed; missing {sorted(missing)}')
    return 'germline valid'

def validate_evidence_match_batch(text,items):
    d=_doc(text,'evidence match'); _exact(d,{'matches'},'evidence match')
    rows=d['matches']
    if not isinstance(rows,list) or len(rows)!=len(items): raise ValueError('evidence match: one match required for every evidence item')
    expected=[x['evidence_id'] for x in items]
    for i,(row,eid) in enumerate(zip(rows,expected)):
        if not isinstance(row,dict): raise ValueError(f'matches[{i}]: expected mapping')
        _exact(row,{'evidence_id','card_id','source','quote'},f'matches[{i}]')
        if row['evidence_id']!=eid: raise ValueError(f'matches[{i}].evidence_id must be {eid}')
        if row['card_id'] not in items[i]['candidate_card_ids']: raise ValueError(f'matches[{i}].card_id must be one of supplied candidates')
        _text(row['source'],f'matches[{i}].source'); _text(row['quote'],f'matches[{i}].quote')
    return 'evidence matches valid'

def validate_evidence_audit_batch(text,items):
    d=_doc(text,'evidence audit'); _exact(d,{'audits'},'evidence audit')
    rows=d['audits']
    if not isinstance(rows,list) or len(rows)!=len(items): raise ValueError('evidence audit: one audit required for every evidence item')
    for i,(row,item) in enumerate(zip(rows,items)):
        if not isinstance(row,dict): raise ValueError(f'audits[{i}]: expected mapping')
        _exact(row,{'evidence_id','quote_supports_statement','quote_supports_reason','risk','comments'},f'audits[{i}]')
        if row['evidence_id']!=item['evidence_id']: raise ValueError(f'audits[{i}].evidence_id must be {item["evidence_id"]}')
        for k in ('quote_supports_statement','quote_supports_reason'):
            if not isinstance(row[k],bool): raise ValueError(f'audits[{i}].{k}: expected boolean')
        if row['risk'] not in {'none','warning'}: raise ValueError(f'audits[{i}].risk: expected none|warning')
        if not isinstance(row['comments'],list) or any(not isinstance(x,str) for x in row['comments']): raise ValueError(f'audits[{i}].comments: expected string list')
    return 'evidence audits valid'

def validate_report_write(text,blocks):
    d=_doc(text,'report writer'); _exact(d,{'blocks'},'report writer')
    rows=d['blocks']; expected=[b['block_id'] for b in blocks]
    if not isinstance(rows,list) or len(rows)!=len(expected): raise ValueError('report writer: return exactly one row per supplied block')
    for i,(row,bid) in enumerate(zip(rows,expected)):
        if not isinstance(row,dict): raise ValueError(f'blocks[{i}]: expected mapping')
        _exact(row,{'block_id','text'},f'blocks[{i}]')
        if row['block_id']!=bid: raise ValueError(f'blocks[{i}].block_id must be {bid}')
        _text(row['text'],f'blocks[{i}].text')
    return 'report writer output valid'

def validate_preservation(text,blocks):
    d=_doc(text,'preservation audit'); _exact(d,{'audits'},'preservation audit')
    rows=d['audits']; expected=[b['block_id'] for b in blocks]
    if not isinstance(rows,list) or len(rows)!=len(expected): raise ValueError('preservation audit: one row per block required')
    for i,(row,bid) in enumerate(zip(rows,expected)):
        if not isinstance(row,dict): raise ValueError(f'audits[{i}]: expected mapping')
        _exact(row,{'block_id','preserved','issue'},f'audits[{i}]')
        if row['block_id']!=bid: raise ValueError(f'audits[{i}].block_id must be {bid}')
        if not isinstance(row['preserved'],bool): raise ValueError(f'audits[{i}].preserved must be boolean')
        if row['preserved']:
            if row['issue'] is not None: raise ValueError(f'audits[{i}].issue must be null when preserved=true')
        else: _text(row['issue'],f'audits[{i}].issue')
    return 'preservation audit valid'
