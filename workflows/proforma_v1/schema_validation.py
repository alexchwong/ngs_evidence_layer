"""Deterministic validators for proforma-v1 model artifacts.

All model-facing failures are actionable task instructions.  Raw JSON-Schema
messages are never exposed directly to a model.
"""
from __future__ import annotations
from scripts.core.validated_model_task import ValidationIssue, fail
from workflows.proforma_v1 import domain_contract
from workflows.proforma_v1 import issues as iss


def _parsed(text,context,keys):
    doc,problems=iss.parse(text,fmt='yaml',context=context)
    if problems: fail(context,problems)
    return doc,list(iss.exact_keys(doc,keys,context))

WHO5_LEGACY_KEYS={'schema_disease','diagnosis','diagnostic_effect','variants','reason'}
WHO5_VARIANT_CLASSIFICATIONS=('diagnostic_for_primary','nonspecific','diagnostic_for_other_pathology')

def _validate_who5_legacy_doc(doc,*,allowed_diseases,valid_variants,ctx):
    problems=[]
    problems += iss.enum_field(doc.get('schema_disease'),allowed_diseases,'schema_disease',label='schema disease')
    problems += iss.text_field(doc.get('diagnosis'),'diagnosis')
    problems += iss.enum_field(doc.get('diagnostic_effect'),('unchanged','refined','superseded'),'diagnostic_effect',label='diagnostic effect')
    _,p=iss.id_list(doc.get('variants'),'variants',valid_variants,allow_empty=True); problems += p
    problems += iss.text_field(doc.get('reason'),'reason')
    return problems

def _validate_variant_assessments(rows,*,valid_variants,path='variant_assessments'):
    problems=[]; expected=sorted(valid_variants)
    problems += iss.one_row_per_id(rows,expected,id_field='variant_id',path=path)
    if isinstance(rows,list):
        for i,row in enumerate(rows):
            if not isinstance(row,dict): continue
            rp=f'{path}[{i}]'
            problems += iss.exact_keys(row,{'variant_id','classification','other_pathology','reason'},rp)
            classification=row.get('classification')
            problems += iss.enum_field(classification,WHO5_VARIANT_CLASSIFICATIONS,f'{rp}.classification',label='diagnostic classification')
            other=row.get('other_pathology')
            if classification=='diagnostic_for_other_pathology':
                problems += iss.text_field(other,f'{rp}.other_pathology')
            elif classification in WHO5_VARIANT_CLASSIFICATIONS and other is not None:
                problems.append(ValidationIssue(f'{rp}.other_pathology','This row is not classified diagnostic_for_other_pathology, so other_pathology must be literal null','Set only other_pathology to literal null; keep the diagnostic classification and reason unchanged unless you conclude the classification itself was wrong',repair_class='content',received=iss.preview(other),expected='null'))
            problems += iss.text_field(row.get('reason'),f'{rp}.reason')
    return problems

def _validate_who5_internal_consistency(doc):
    problems=[]; primary=doc.get('variants'); primary_ids=set(primary) if isinstance(primary,list) else set(); rows=doc.get('variant_assessments')
    if isinstance(rows,list):
        by_id={r.get('variant_id'):(i,r) for i,r in enumerate(rows) if isinstance(r,dict) and isinstance(r.get('variant_id'),str)}
        for vid in primary_ids:
            found=by_id.get(vid)
            if found and found[1].get('classification')!='diagnostic_for_primary':
                i,row=found
                problems.append(ValidationIssue(f'variant_assessments[{i}].classification',f'The output gives conflicting clinical statements about {vid}: it is listed in diagnosis-level variants but its assessment is not diagnostic_for_primary',f'Reassess {vid} and make the diagnosis-level variants list and its assessment agree. Python cannot choose which clinical statement is correct. Keep unrelated variant assessments unchanged',repair_class='content',received=iss.preview(row.get('classification')),expected='classification consistent with variants'))
        for i,row in enumerate(rows):
            if not isinstance(row,dict): continue
            vid=row.get('variant_id')
            if row.get('classification')=='diagnostic_for_primary' and vid not in primary_ids:
                problems.append(ValidationIssue(f'variant_assessments[{i}].classification',f'The output gives conflicting clinical statements about {vid}: its assessment says diagnostic_for_primary but it is absent from diagnosis-level variants',f'Reassess {vid} and make the two fields agree. Python cannot decide whether {vid} contributes to the primary diagnosis. Keep unrelated variant assessments unchanged',repair_class='content',received='diagnostic_for_primary',expected='classification consistent with variants'))
    effect=doc.get('diagnostic_effect'); reason=' '.join(str(doc.get('reason') or '').lower().split()); contradiction=False
    if effect=='refined': contradiction=any(x in reason for x in ('not refined','does not refine',"doesn't refine"))
    elif effect=='superseded': contradiction=any(x in reason for x in ('not superseded','does not supersede',"doesn't supersede"))
    if contradiction:
        problems.append(ValidationIssue('reason',f'The reason explicitly contradicts diagnostic_effect={effect}',f'Reassess the diagnosis and return one internally consistent diagnostic_effect and reason. Python cannot decide which clinical conclusion you intended. Preserve unrelated fields',repair_class='content',received=iss.preview(doc.get('reason')),expected=f'reason consistent with diagnostic_effect={effect}'))
    return problems

def validate_who5_legacy_diagnosis(text,*,allowed_diseases,valid_variants):
    ctx='WHO5 diagnosis'; doc,problems=_parsed(text,ctx,WHO5_LEGACY_KEYS); problems += _validate_who5_legacy_doc(doc,allowed_diseases=allowed_diseases,valid_variants=valid_variants,ctx=ctx); fail(ctx,problems); return 'WHO5 diagnosis valid'

def validate_who5_diagnosis(text,*,allowed_diseases,valid_variants):
    ctx='WHO5 diagnosis'; doc,problems=_parsed(text,ctx,WHO5_LEGACY_KEYS|{'variant_assessments'}); problems += _validate_who5_legacy_doc(doc,allowed_diseases=allowed_diseases,valid_variants=valid_variants,ctx=ctx); problems += _validate_variant_assessments(doc.get('variant_assessments'),valid_variants=valid_variants); problems += _validate_who5_internal_consistency(doc); fail(ctx,problems); return 'WHO5 diagnosis valid'

def validate_icc_diagnosis(text,*,valid_variants):
    ctx='ICC diagnosis'; doc,problems=_parsed(text,ctx,{'diagnosis','diagnostic_effect','variants','reason','variant_assessments'}); problems += iss.text_field(doc.get('diagnosis'),'diagnosis'); problems += iss.enum_field(doc.get('diagnostic_effect'),('unchanged','refined','superseded'),'diagnostic_effect',label='diagnostic effect'); _,p=iss.id_list(doc.get('variants'),'variants',valid_variants,allow_empty=True); problems += p; problems += iss.text_field(doc.get('reason'),'reason'); problems += _validate_variant_assessments(doc.get('variant_assessments'),valid_variants=valid_variants); fail(ctx,problems); return 'ICC diagnosis valid'

def validate_domain(text,domain,valid_variants,*,registry=None,authoritative_disease=None):
    return domain_contract.validate(text,domain_contract.contract(domain),{'variants':sorted(valid_variants),'registry':registry or {},'authoritative_disease':authoritative_disease})
def validate_prognosis(text,valid): return validate_domain(text,'prognosis',valid)
def validate_treatment(text,valid): return validate_domain(text,'treatment',valid)
def validate_biomarker(text,valid): return validate_domain(text,'biomarker',valid)
def validate_germline(text,valid): return validate_domain(text,'germline',valid)

def validate_evidence_match_batch(text,items):
    ctx='evidence match'; doc,problems=_parsed(text,ctx,{'matches'}); rows=doc.get('matches'); expected=[x['evidence_id'] for x in items]; problems += iss.one_row_per_id(rows,expected,id_field='evidence_id',path='matches'); by_id={x['evidence_id']:x for x in items}
    if isinstance(rows,list):
        for i,row in enumerate(rows):
            if not isinstance(row,dict): continue
            p=f'matches[{i}]'; problems += iss.exact_keys(row,{'evidence_id','card_tags'},p); tags=row.get('card_tags')
            if not isinstance(tags,list):
                problems.append(ValidationIssue(f'{p}.card_tags',f'card_tags must be a YAML/JSON list, not {iss.type_name(tags)}','Return selected card tags as a list. Use [] when no supplied candidate supports this evidence item. If you intended one exact supplied tag, wrap that tag in a one-item list. Do not change the proposition',repair_class='serialization' if isinstance(tags,str) else 'content',received=iss.preview(tags),expected='list of candidate card tags')); continue
            item=by_id.get(row.get('evidence_id'))
            for j,tag in enumerate(tags):
                if item is not None and tag not in item.get('candidate_card_tags',[]):
                    problems.append(ValidationIssue(f'{p}.card_tags[{j}]',f'{tag!r} was not supplied as a candidate for evidence item {row.get("evidence_id")}',f'Reassess only the evidence selection for {row.get("evidence_id")} using its supplied candidate cards. Remove this out-of-envelope tag; do not alter the proposition itself',repair_class='content',received=iss.preview(tag),expected=f'one of {item.get("candidate_card_tags",[])}'))
    fail(ctx,problems); return 'evidence matches valid'

def validate_evidence_audit_batch(text,items):
    ctx='evidence audit'; doc,problems=_parsed(text,ctx,{'audits'}); rows=doc.get('audits'); expected=[x['evidence_id'] for x in items]; problems += iss.one_row_per_id(rows,expected,id_field='evidence_id',path='audits'); by_id={x['evidence_id']:x for x in items}
    if isinstance(rows,list):
        for i,row in enumerate(rows):
            if not isinstance(row,dict): continue
            p=f'audits[{i}]'; problems += iss.exact_keys(row,{'evidence_id','card_audits'},p); audits=row.get('card_audits')
            if not isinstance(audits,list):
                problems.append(ValidationIssue(f'{p}.card_audits',f'card_audits must be a list with one audit per selected card, not {iss.type_name(audits)}','Return one card_audits list containing exactly one audit for every selected card tag. Do not change the evidence item or card decisions merely to repair the wrapper',repair_class='serialization' if isinstance(audits,dict) else 'content',received=iss.preview(audits),expected='list of card audit mappings')); continue
            item=by_id.get(row.get('evidence_id')) or {}; selected=list(item.get('selected_card_tags') or []); seen=[a.get('card_tag') for a in audits if isinstance(a,dict)]; missing=[x for x in selected if x not in seen]; unexpected=[x for x in seen if x not in selected]; dup=sorted({x for x in seen if x is not None and seen.count(x)>1})
            if missing or unexpected or dup:
                parts=[]; actions=[]
                if missing: parts.append(f'missing {missing}'); actions.append(f'add an audit for selected card(s) {missing}')
                if unexpected: parts.append(f'unexpected {unexpected}'); actions.append(f'remove audits for card(s) that were not selected: {unexpected}')
                if dup: parts.append(f'duplicated {dup}'); actions.append(f'return one intended audit for each duplicated card {dup}; if duplicate audits disagree, reassess rather than letting Python choose')
                problems.append(ValidationIssue(f'{p}.card_audits','; '.join(parts),'; '.join(actions)+'. Keep unrelated card audits unchanged',repair_class='content',received=f'card tags {seen}',expected=f'card tags {selected}'))
            for j,audit in enumerate(audits):
                if not isinstance(audit,dict): continue
                ap=f'{p}.card_audits[{j}]'; problems += iss.exact_keys(audit,{'card_tag','card_is_element_of_reason','risk','comments'},ap); problems += iss.bool_field(audit.get('card_is_element_of_reason'),f'{ap}.card_is_element_of_reason'); problems += iss.enum_field(audit.get('risk'),('none','warning'),f'{ap}.risk',label='risk level'); comments=audit.get('comments')
                if not isinstance(comments,list) or any(not isinstance(x,str) for x in comments):
                    problems.append(ValidationIssue(f'{ap}.comments',f'comments must be a list of strings, not {iss.type_name(comments)}','Return comments as a YAML/JSON list of strings. Use [] only when there is genuinely nothing to explain. Do not change the audit verdict just to satisfy representation',repair_class='serialization' if isinstance(comments,str) else 'content',received=iss.preview(comments),expected='list of strings'))
                elif (audit.get('card_is_element_of_reason') is False or audit.get('risk')=='warning') and not any(x.strip() for x in comments):
                    problems.append(ValidationIssue(f'{ap}.comments','You returned a negative card/reason membership decision or a warning but gave no explanation','Add a concise comment explaining why the card is not an element of the reason or what the warning is. Keep the verdict unchanged unless, on reassessment, you conclude the verdict itself was wrong',repair_class='content',received=iss.preview(comments),expected='one or more actionable audit comments'))
    fail(ctx,problems); return 'evidence audits valid'

def validate_report_source_blocks(blocks):
    if not isinstance(blocks,list): raise ValueError('report.write requires deterministic report_blocks artifact as a list')
    for i,b in enumerate(blocks):
        if not isinstance(b,dict): raise ValueError(f'report_blocks[{i}] must be an object')
        if not isinstance(b.get('block_id'),str) or not b.get('block_id').strip(): raise ValueError(f'report_blocks[{i}].block_id must be a non-empty string')
    return blocks

def validate_report_write(text,blocks):
    ctx='report writer'; validate_report_source_blocks(blocks); doc,problems=_parsed(text,ctx,{'blocks'}); rows=doc.get('blocks'); expected=[b['block_id'] for b in blocks]; problems += iss.one_row_per_id(rows,expected,id_field='block_id',path='blocks')
    if isinstance(rows,list):
        for i,row in enumerate(rows):
            if isinstance(row,dict): problems += iss.exact_keys(row,{'block_id','text'},f'blocks[{i}]'); problems += iss.text_field(row.get('text'),f'blocks[{i}].text')
    fail(ctx,problems); return 'report writer output valid'

def validate_preservation(text,blocks):
    ctx='preservation audit'; doc,problems=_parsed(text,ctx,{'audits'}); rows=doc.get('audits'); expected=[b['block_id'] for b in blocks]; problems += iss.one_row_per_id(rows,expected,id_field='block_id',path='audits')
    if isinstance(rows,list):
        for i,row in enumerate(rows):
            if not isinstance(row,dict): continue
            p=f'audits[{i}]'; problems += iss.exact_keys(row,{'block_id','preserved','issue'},p); problems += iss.bool_field(row.get('preserved'),f'{p}.preserved')
            if row.get('preserved') is True and row.get('issue') is not None:
                problems.append(ValidationIssue(f'{p}.issue','preserved is true, but issue contains text; these two fields contradict each other','If preservation truly passed, set issue to literal null. If the issue is substantive, reassess preserved instead. Python will not choose between these meanings. Keep other block audits unchanged',repair_class='content',received=iss.preview(row.get('issue')),expected='null when preserved is true'))
            elif row.get('preserved') is False: problems += iss.text_field(row.get('issue'),f'{p}.issue')
    fail(ctx,problems); return 'preservation audit valid'
