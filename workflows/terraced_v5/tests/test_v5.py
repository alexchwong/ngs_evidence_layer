from __future__ import annotations
from pathlib import Path
import json, yaml
import pytest
from scripts.core.validated_model_task import ValidationFailure
from workflows.terraced_v5 import pipeline_registry, prompt_loader, runtime, schema_validation, step

ROOT=Path(__file__).resolve().parents[1]

def test_pipelines_load_new_roles():
    assert {'self','lmstudio','openrouter'} <= set(pipeline_registry.names())
    for name in pipeline_registry.names():
        plan=pipeline_registry.load(name)
        assert plan.pipeline_id==name
        for role in pipeline_registry.ROLES: assert pipeline_registry.binding(plan,role).role==role
    assert 'statement_generation' in pipeline_registry.ROLES
    assert 'statement_audit' in pipeline_registry.ROLES
    assert 'reportable_sentences' not in pipeline_registry.ROLES

def test_settings_put_authorities_and_hyperparameters_outside_python():
    s=step.load_settings()
    assert s['schema_version']==2
    assert s['diagnosis']['who5']['publication_keys']==['khoury-2022-leukemia-36-1703']
    assert s['diagnosis']['icc']['publication_keys']==['arber-2022-blood-140-1200']
    assert s['diagnosis']['who5']['max_cmc_passes']==2
    assert s['retries']['syntax_repair_attempts']==5
    assert s['retries']['proforma_rewrite_attempts']==3
    assert s['retries']['evidence_match_rounds']==3

def test_authority_publications_read_from_settings(monkeypatch):
    base=step.load_settings()
    base['diagnosis']['who5']['publication_keys']=['khoury','alaggio']
    monkeypatch.setattr(step,'load_settings',lambda:base)
    assert step._diagnosis_authority_publications('who5')=={'khoury','alaggio'}

def test_prompt_loader_recursive_include():
    text=step._prompt('biomarker')
    assert 'Shared PTBG interpretation discipline' in text
    assert 'Biomarker / MRD interpretation boundaries' in text
    assert '{{ include' not in text

def test_prompt_loader_rejects_cycle(tmp_path):
    (tmp_path/'a.md').write_text('{{ include "b.md" }}\n')
    (tmp_path/'b.md').write_text('{{ include "a.md" }}\n')
    with pytest.raises(prompt_loader.PromptIncludeError): prompt_loader.render(Path('a.md'),root=tmp_path)

def test_audit_prompts_inject_shared_general_principles():
    for name in ('statement_audit','evidence_audit','summary_plan_audit','paraphrase_audit'):
        text=step._prompt(name)
        assert 'missing exclusion/discriminator information' in text
        assert 'must not invent a missing positive feature' in text
        assert '{{ include' not in text

def test_statement_generation_validator():
    items=[{'schema_id':'PX-A'}]
    text=yaml.safe_dump({'statements':[{'schema_id':'PX-A','statement':'FLT3-ITD has an adverse association in this setting.'}]})
    assert 'valid' in schema_validation.validate_statement_generation_batch(text,items)

def test_statement_audit_validator_supports_three_states():
    items=[{'schema_id':'PX-A'}]
    for status in ('supported','supported_if','unsupported'):
        doc={'audits':[{'schema_id':'PX-A','statement_represents_proforma':True,'reasoning_status':status,'issues':[] if status!='unsupported' else ['Reason does not justify conclusion.'],'negative_guidance':[] if status!='unsupported' else ['Do not infer a positive effect from absence of contrary evidence.']}]}
        assert 'valid' in schema_validation.validate_statement_audit_batch(yaml.safe_dump(doc),items)

def test_statement_audit_requires_negative_guidance_for_failure():
    items=[{'schema_id':'MRD-A'}]
    doc={'audits':[{'schema_id':'MRD-A','statement_represents_proforma':True,'reasoning_status':'unsupported','issues':['bad inference'],'negative_guidance':[]}]}
    with pytest.raises(ValidationFailure): schema_validation.validate_statement_audit_batch(yaml.safe_dump(doc),items)

def test_statement_audit_reason_failure_requests_proforma_regeneration(monkeypatch,tmp_path):
    elements=[{'schema_id':'MRD-A','domain':'biomarker','proposition':'SRSF2 is suitable for MRD.','reasons':['SRSF2 is not excluded from MRD.'],'positive_effect':True}]
    calls=[]
    def fake(work,**kw):
        calls.append(kw['call_id']); kw['output'].parent.mkdir(parents=True,exist_ok=True)
        if 'statement-generation' in kw['call_id']:
            doc={'statements':[{'schema_id':'MRD-A','statement':'SRSF2 is suitable for MRD.'}]}
        else:
            doc={'audits':[{'schema_id':'MRD-A','statement_represents_proforma':True,'reasoning_status':'unsupported','issues':['Not excluded does not imply suitable.'],'negative_guidance':['Do not infer suitability from absence of exclusion.']}]}
        kw['output'].write_text(yaml.safe_dump(doc,sort_keys=False))
    monkeypatch.setattr(step,'_model_call',fake)
    out,need,guidance=step._generate_and_audit_statements(tmp_path,'biomarker',elements,{}, {},'self')
    assert need is True
    assert guidance[0]['reasoning_status']=='unsupported'
    assert calls==['biomarker-statement-generation-a1','biomarker-statement-audit-a1']

def test_statement_representation_failure_regenerates_statement_not_proforma(monkeypatch,tmp_path):
    elements=[{'schema_id':'DX-A','domain':'diagnosis','proposition':'AML-MR.','reasons':['SRSF2 and ASXL1 qualify.'],'positive_effect':False}]
    calls=[]
    def fake(work,**kw):
        calls.append(kw['call_id']); kw['output'].parent.mkdir(parents=True,exist_ok=True)
        if kw['call_id']=='x-statement-generation-a1': doc={'statements':[{'schema_id':'DX-A','statement':'AML-MR with SRSF2, ASXL1, DNMT3A and TET2 qualifying.'}]}
        elif kw['call_id']=='x-statement-audit-a1': doc={'audits':[{'schema_id':'DX-A','statement_represents_proforma':False,'reasoning_status':'supported','issues':['Added DNMT3A/TET2.'],'negative_guidance':['Do not add qualifying genes absent from the proforma.']}]}
        elif kw['call_id']=='x-statement-generation-a2': doc={'statements':[{'schema_id':'DX-A','statement':'AML-MR with qualifying SRSF2 and ASXL1.'}]}
        elif kw['call_id']=='x-statement-audit-a2': doc={'audits':[{'schema_id':'DX-A','statement_represents_proforma':True,'reasoning_status':'supported','issues':[],'negative_guidance':[]}]}
        else: raise AssertionError(kw['call_id'])
        kw['output'].write_text(yaml.safe_dump(doc,sort_keys=False))
    monkeypatch.setattr(step,'_model_call',fake)
    out,need,_=step._generate_and_audit_statements(tmp_path,'x',elements,{}, {},'self')
    assert need is False
    assert out[0]['statement']=='AML-MR with qualifying SRSF2 and ASXL1.'
    assert calls==['x-statement-generation-a1','x-statement-audit-a1','x-statement-generation-a2','x-statement-audit-a2']

def test_evidence_audit_validator_separates_statement_and_reason_support():
    items=[{'evidence_id':'E0001'}]
    doc={'audits':[{'evidence_id':'E0001','quote_supports_statement':False,'quote_supports_reason':True,'risk':'none','comments':['Quote does not establish MRD suitability.']}]}
    assert 'valid' in schema_validation.validate_evidence_audit_batch(yaml.safe_dump(doc),items)

def test_evidence_audit_prompt_receives_statement():
    item={'evidence_id':'E0001','schema_id':'MRD-A','statement':'SRSF2 is suitable for MRD.','reason':'SRSF2 is not excluded.','candidate_card_ids':['C1']}
    card={'card_id':'C1','category':'biomarker','genes':['SRSF2'],'diseases':['AML'],'interpretation':'Testing at diagnosis for risk classification.'}
    match={'evidence_id':'E0001','card_id':'C1','source':'ELN','quote':'Testing at diagnosis.'}
    prompt=step._batch_audit_prompt([item],[match],{'C1':card})
    assert 'statement: SRSF2 is suitable for MRD.' in prompt
    assert 'reason: SRSF2 is not excluded.' in prompt

def test_positive_ptbg_unresolved_evidence_is_suppressed(tmp_path):
    elements=[{'schema_id':'MRD-A','domain':'biomarker','statement':'SRSF2 is suitable for MRD.','reasons':['r'],'semantic_status':'supported','positive_effect':True,'evidence':[{'status':'unresolved','card_tag':None}]}]
    statements=step.stage_reportable_sentences(tmp_path,elements)
    assert statements==[]
    doc=yaml.safe_load((tmp_path/'logs'/'risk_log.yaml').read_text())
    assert any(r['type']=='positive_ptbg_unresolved_suppressed' for r in doc['risks'])

def test_negative_or_uncertain_statement_not_suppressed_only_for_missing_evidence(tmp_path):
    elements=[{'schema_id':'MRD-U','domain':'biomarker','statement':'SRSF2 MRD suitability is uncertain.','reasons':['No affirmative MRD evidence.'],'semantic_status':'supported','positive_effect':False,'evidence':[{'status':'unresolved','card_tag':None}]}]
    statements=step.stage_reportable_sentences(tmp_path,elements)
    assert len(statements)==1

def test_summary_plan_validator_respects_cross_domain_setting():
    statements=[{'statement_id':'S1','domain':'diagnosis','statement':'A.'},{'statement_id':'S2','domain':'prognosis','statement':'B.'}]
    plan={'dispositions':[{'statement_id':'S1','decision':'include','reason':None},{'statement_id':'S2','decision':'include','reason':None}], 'parts':[{'statement_id':'S1','group':'G1','split_text':None},{'statement_id':'S2','group':'G1','split_text':None}]}
    with pytest.raises(ValidationFailure): runtime.validate_summary_plan_doc(plan,statements,allow_cross_domain_merge=False)
    assert 'validated' in runtime.validate_summary_plan_doc(plan,statements,allow_cross_domain_merge=True)

def test_summary_plan_audit_has_explicit_omit_split_merge_dimensions():
    audit={'preserved':True,'omission_valid':True,'split_valid':True,'merge_complete':False,'issues':[{'target':'prognosis','issue':'Parallel same-category blocks remain unmerged.'}]}
    assert 'valid' in step._validate_summary_plan_audit(yaml.safe_dump(audit))


def test_case_variant_description_gene_prefix_is_lossless():
    detail='NM_003016.5:c.284C>A, p.(Pro95His), VAF 36%'
    case={'variants':[{'variant_id':'V1','gene':'SRSF2','description':detail}]}
    out=runtime.normalize_case_variant_descriptions(case)
    assert out['variants'][0]['description']==f'SRSF2 {detail}'
    assert detail in out['variants'][0]['description']
    assert runtime.normalize_case_variant_descriptions(out)['variants'][0]['description']==f'SRSF2 {detail}'


def test_case_validator_can_enforce_gene_prefixed_description():
    base={
        'provisional_disease':'AML',
        'bootstrap_cmcs':['AML'],
        'variants':[{'variant_id':'V1','gene':'SRSF2','description':'NM_003016.5:c.284C>A'}],
        'detected_variants_summary':'SRSF2 variant detected.',
        'case_facts':[{'fact_id':'C1','kind':'age','value':'58 years'}],
    }
    assert 'validated' in runtime.validate_case_text(json.dumps(base))
    with pytest.raises(ValidationFailure):
        runtime.validate_case_text(json.dumps(base),require_gene_prefixed_description=True)
    runtime.normalize_case_variant_descriptions(base)
    assert 'validated' in runtime.validate_case_text(json.dumps(base),require_gene_prefixed_description=True)

def test_paraphrase_audit_requires_negative_guidance_on_failure():
    blocks=[{'block_id':'prognosis-1'}]
    bad={'audits':[{'block_id':'prognosis-1','preserved':False,'issue':'Dropped treatment-context qualifier.','negative_guidance':[]}]}
    with pytest.raises(ValidationFailure): runtime.validate_paraphrase_audit_batch_text(yaml.safe_dump(bad),blocks)
    good={'audits':[{'block_id':'prognosis-1','preserved':False,'issue':'Dropped treatment-context qualifier.','negative_guidance':['Do not generalize the treatment-specific association.']}]}
    assert 'validated' in runtime.validate_paraphrase_audit_batch_text(yaml.safe_dump(good),blocks)

def test_ptbg_cards_are_category_specific(monkeypatch):
    s=step.load_settings(); assert s['ptbg']['domains']['treatment']['card_category']=='treatment'; assert s['ptbg']['domains']['prognosis']['card_category']=='prognosis'

def test_model_usage_tally_still_available(tmp_path):
    step._record_usage(tmp_path,'a','m',1,{'prompt_tokens':10,'completion_tokens':2,'total_tokens':12},role='statement_generation')
    step._record_usage(tmp_path,'b','self',1,None,role='statement_audit')
    summary=step._usage_summary(tmp_path); assert summary['totals']['total_tokens']==12; assert summary['unreported_calls']==1

def test_workflow_registry_contains_v5():
    d=json.loads((ROOT.parent/'registry.json').read_text())
    assert d['workflows']['terraced-v5']['path']=='workflows/terraced_v5'

def test_stage_domain_reasoning_failure_regenerates_proforma_de_novo(monkeypatch,tmp_path):
    reg={'v01':{'variant_id':'V1','gene':'SRSF2','description':'SRSF2 p.P95H'}}
    case={'variants':[{'variant_id':'V1','gene':'SRSF2','description':'SRSF2 p.P95H'}]}
    diagnosis={'who5':{'diagnoses':[{'schema_disease':'AML','status':'established','diagnosis':'AML','reasons':['r']} ]}}
    card={'card_id':'C1','category':'biomarker','genes':['SRSF2'],'diseases':['AML'],'interpretation':'Testing at diagnosis for risk classification.'}
    monkeypatch.setattr(step,'_draw_domain_cards',lambda *args,**kwargs:[card])
    calls=[]
    def fake(work,**kw):
        calls.append(kw['call_id']); kw['output'].parent.mkdir(parents=True,exist_ok=True)
        cid=kw['call_id']
        if cid=='biomarker':
            doc={'suitable_mrd':[{'variants':['v01'],'reason':'SRSF2 is not excluded from MRD use.'}],'unsuitable_mrd':[],'uncertain':[],'no_effect':[]}
        elif cid=='biomarker-proforma-00-statement-generation-a1':
            doc={'statements':[{'schema_id':'MRD-SUITABLE_MRD-01','statement':'SRSF2 is suitable for MRD monitoring.'}]}
        elif cid=='biomarker-proforma-00-statement-audit-a1':
            doc={'audits':[{'schema_id':'MRD-SUITABLE_MRD-01','statement_represents_proforma':True,'reasoning_status':'unsupported','issues':['Absence of exclusion does not establish suitability.'],'negative_guidance':['Do not infer MRD suitability from absence of exclusion.']}]}
        elif cid=='biomarker-semantic-rewrite-01':
            assert 'Do not infer MRD suitability from absence of exclusion.' in kw['prompt']
            doc={'suitable_mrd':[],'unsuitable_mrd':[],'uncertain':[{'variants':['v01'],'reason':'No affirmative MRD-specific support is supplied.'}],'no_effect':[]}
        elif cid=='biomarker-proforma-01-statement-generation-a1':
            doc={'statements':[{'schema_id':'MRD-UNCERTAIN-01','statement':'The suitability of SRSF2 for MRD monitoring is uncertain.'}]}
        elif cid=='biomarker-proforma-01-statement-audit-a1':
            doc={'audits':[{'schema_id':'MRD-UNCERTAIN-01','statement_represents_proforma':True,'reasoning_status':'supported','issues':[],'negative_guidance':[]}]}
        else: raise AssertionError(cid)
        kw['output'].write_text(yaml.safe_dump(doc,sort_keys=False))
    monkeypatch.setattr(step,'_model_call',fake)
    proforma,cards,elements=step.stage_domain(tmp_path,'biomarker',case,reg,diagnosis,[],profile='self')
    assert proforma['suitable_mrd']==[]
    assert elements[0]['schema_id']=='MRD-UNCERTAIN-01'
    assert elements[0]['semantic_status']=='supported'
    assert calls==[
        'biomarker','biomarker-proforma-00-statement-generation-a1','biomarker-proforma-00-statement-audit-a1',
        'biomarker-semantic-rewrite-01','biomarker-proforma-01-statement-generation-a1','biomarker-proforma-01-statement-audit-a1'
    ]


def test_stage_evidence_batches_statement_reason_and_quote_audit(monkeypatch,tmp_path):
    elements=[{'schema_id':'PX-A','domain':'prognosis','statement':'FLT3-ITD has an adverse prognostic association in this treatment setting.','proposition':'adverse prognostic contribution for v01','reasons':['Treatment-specific adverse association.'],'variants':['v01'],'evidence_domain':'prognosis','positive_effect':True,'semantic_status':'supported'}]
    card={'card_id':'C1','category':'prognosis','genes':['FLT3'],'diseases':['AML'],'interpretation':'FLT3-ITD was associated with adverse outcome in this treatment setting.'}
    monkeypatch.setattr(step.card_identity,'tag_by_id',lambda manifest:{'C1':'T1'})
    calls=[]
    def fake(work,**kw):
        calls.append(kw['call_id']); kw['output'].parent.mkdir(parents=True,exist_ok=True)
        if kw['call_id']=='evidence-match-batch-a1':
            assert 'statement: FLT3-ITD has an adverse prognostic association' in kw['prompt']
            doc={'matches':[{'evidence_id':'E0001','card_id':'C1','source':'Study','quote':'FLT3-ITD was associated with adverse outcome.'}]}
        elif kw['call_id']=='evidence-audit-batch-a1':
            assert 'statement: FLT3-ITD has an adverse prognostic association' in kw['prompt']
            doc={'audits':[{'evidence_id':'E0001','quote_supports_statement':True,'quote_supports_reason':True,'risk':'none','comments':[]}]}
        else: raise AssertionError(kw['call_id'])
        kw['output'].write_text(yaml.safe_dump(doc,sort_keys=False))
    monkeypatch.setattr(step,'_model_call',fake)
    enriched=step.stage_evidence(tmp_path,elements,{'prognosis':[card]},{'v01':{'gene':'FLT3'}},{},'self')
    assert calls==['evidence-match-batch-a1','evidence-audit-batch-a1']
    assert enriched[0]['evidence'][0]['status']=='matched'


def test_stage_summary_is_one_plan_and_one_whole_report_paraphrase_when_clean(monkeypatch,tmp_path):
    (tmp_path/'case.md').write_text('Example case.\n')
    statements=[
        {'statement_id':'S0001','schema_id':'DX-A','domain':'diagnosis','statement':'Diagnosis A.','reason':'r','card_tags':['[card:1]'],'semantic_status':'supported'},
        {'statement_id':'S0002','schema_id':'PX-A','domain':'prognosis','statement':'Risk B.','reason':'r','card_tags':['[card:2]'],'semantic_status':'supported'},
    ]
    calls=[]
    def fake(work,**kw):
        calls.append(kw['call_id']); kw['output'].parent.mkdir(parents=True,exist_ok=True)
        cid=kw['call_id']
        if cid=='summary-plan':
            doc={'dispositions':[{'statement_id':'S0001','decision':'include','reason':None},{'statement_id':'S0002','decision':'include','reason':None}], 'parts':[{'statement_id':'S0001','group':'G1','split_text':None},{'statement_id':'S0002','group':'G2','split_text':None}]}
        elif cid=='summary-plan-audit': doc={'preserved':True,'omission_valid':True,'split_valid':True,'merge_complete':True,'issues':[]}
        elif cid=='paraphrase-batch':
            assert 'case.md — context only' in kw['prompt']; doc={'sentences':[{'block_id':'diagnosis-1','sentence':'Diagnosis A.'},{'block_id':'prognosis-1','sentence':'Risk B.'}]}
        elif cid=='paraphrase-batch-audit':
            doc={'audits':[{'block_id':'diagnosis-1','preserved':True,'issue':None,'negative_guidance':[]},{'block_id':'prognosis-1','preserved':True,'issue':None,'negative_guidance':[]}]}
        else: raise AssertionError(cid)
        kw['output'].write_text(yaml.safe_dump(doc,sort_keys=False))
    monkeypatch.setattr(step,'_model_call',fake)
    final=step.stage_summary(tmp_path,statements,{},'self')
    assert calls==['summary-plan','summary-plan-audit','paraphrase-batch','paraphrase-batch-audit']
    assert [x['sentence_id'] for x in final['sentences']]==['diagnosis-1','prognosis-1']




def test_summary_fragmentation_retry_budget_survives_semantic_retries(monkeypatch,tmp_path):
    (tmp_path/'case.md').write_text('Example case.\n')
    statements=[
        {'statement_id':'S0001','schema_id':'PX-A','domain':'prognosis','statement':'Gene A has adverse risk.','reason':'r','card_tags':['[card:1]'],'semantic_status':'supported'},
        {'statement_id':'S0002','schema_id':'PX-B','domain':'prognosis','statement':'Gene B has adverse risk.','reason':'r','card_tags':['[card:1]'],'semantic_status':'supported'},
    ]
    calls=[]; audit_round=0
    def fake(work,**kw):
        nonlocal audit_round
        calls.append(kw['call_id']); kw['output'].parent.mkdir(parents=True,exist_ok=True)
        cid=kw['call_id']
        if cid.startswith('summary-plan') and not cid.endswith('-audit'):
            merged=cid=='summary-plan-regenerate-03'
            doc={
                'dispositions':[{'statement_id':'S0001','decision':'include','reason':None},{'statement_id':'S0002','decision':'include','reason':None}],
                'parts':[{'statement_id':'S0001','group':'G1','split_text':None},{'statement_id':'S0002','group':'G1' if merged else 'G2','split_text':None}],
            }
        elif cid.startswith('summary-plan') and cid.endswith('-audit'):
            audit_round+=1
            if audit_round<=2:
                doc={'preserved':False,'omission_valid':False,'split_valid':True,'merge_complete':False,'issues':[{'target':'S0001','issue':'Material planning defect.'}]}
            elif audit_round==3:
                doc={'preserved':True,'omission_valid':True,'split_valid':True,'merge_complete':False,'issues':[{'target':'prognosis','issue':'Parallel blocks remain unmerged.'}]}
            else:
                doc={'preserved':True,'omission_valid':True,'split_valid':True,'merge_complete':True,'issues':[]}
        elif cid=='paraphrase-batch':
            doc={'sentences':[{'block_id':'prognosis-1','sentence':'Gene A and Gene B have adverse risk.'}]}
        elif cid=='paraphrase-batch-audit':
            doc={'audits':[{'block_id':'prognosis-1','preserved':True,'issue':None,'negative_guidance':[]}]}
        else:
            raise AssertionError(cid)
        kw['output'].write_text(yaml.safe_dump(doc,sort_keys=False))
    monkeypatch.setattr(step,'_model_call',fake)
    final=step.stage_summary(tmp_path,statements,{},'self')
    assert 'summary-plan-regenerate-03' in calls
    assert calls.count('summary-plan-regenerate-03')==1
    assert [x['sentence_id'] for x in final['sentences']]==['prognosis-1']

def test_statement_public_separates_internal_variant_ids_from_reportable_display():
    reg={
        'v01':{'variant_id':'V1','gene':'SRSF2','description':'SRSF2 p.Pro95His'},
        'v02':{'variant_id':'V2','gene':'ASXL1','description':'ASXL1 p.Gly646Trpfs*12'},
    }
    elements=[{
        'schema_id':'PX-ADVERSE-01','domain':'prognosis',
        'proposition':'adverse prognostic contribution for v01, v02',
        'reasons':['v01 and v02 are adverse in the supplied framework.'],
        'variants':['v01','v02'],
    }]
    public=step._statement_public(elements,reg)
    dumped=yaml.safe_dump(public,sort_keys=False)
    assert 'v01' not in dumped
    assert 'v02' not in dumped
    assert public[0]['variant_display']==['SRSF2 p.Pro95His','ASXL1 p.Gly646Trpfs*12']
    assert public[0]['proposition']=='adverse prognostic contribution for SRSF2 p.Pro95His, ASXL1 p.Gly646Trpfs*12'
    assert public[0]['reasons']==['SRSF2 p.Pro95His and ASXL1 p.Gly646Trpfs*12 are adverse in the supplied framework.']


def test_statement_generation_prompt_does_not_expose_internal_variant_ids(monkeypatch,tmp_path):
    reg={'v01':{'variant_id':'V1','gene':'SRSF2','description':'SRSF2 p.Pro95His'}}
    elements=[{
        'schema_id':'PX-ADVERSE-01','domain':'prognosis',
        'proposition':'adverse prognostic contribution for v01',
        'reasons':['v01 has an adverse prognostic association.'],
        'variants':['v01'],'evidence_domain':'prognosis','positive_effect':True,
    }]
    seen=[]
    def fake(work,**kw):
        seen.append((kw['call_id'],kw['prompt']))
        kw['output'].parent.mkdir(parents=True,exist_ok=True)
        if 'statement-generation' in kw['call_id']:
            assert 'v01' not in kw['prompt']
            assert 'SRSF2 p.Pro95His' in kw['prompt']
            doc={'statements':[{'schema_id':'PX-ADVERSE-01','statement':'SRSF2 p.Pro95His has an adverse prognostic association.'}]}
        elif 'statement-audit' in kw['call_id']:
            assert 'v01' not in kw['prompt']
            doc={'audits':[{'schema_id':'PX-ADVERSE-01','statement_represents_proforma':True,'reasoning_status':'supported','issues':[],'negative_guidance':[]}]}
        else:
            raise AssertionError(kw['call_id'])
        kw['output'].write_text(yaml.safe_dump(doc,sort_keys=False))
    monkeypatch.setattr(step,'_model_call',fake)
    out,need,guidance=step._generate_and_audit_statements(tmp_path,'prognosis-proforma-00',elements,{},reg,'self')
    assert need is False
    assert guidance==[]
    assert out[0]['variants']==['v01']  # provenance remains internal and unchanged
    assert out[0]['statement'].startswith('SRSF2 p.Pro95His')


def test_variant_display_policy_is_configured_in_settings():
    assert step.load_settings()['reporting']['variant_display_fields']==['description','gene']

def _criterion_case_fixture():
    case={
        'provisional_disease':'AML','bootstrap_cmcs':['AML'],
        'variants':[
            {'variant_id':'V1','gene':'ASXL1','description':'ASXL1 p.X'},
            {'variant_id':'V2','gene':'SRSF2','description':'SRSF2 p.Y'},
            {'variant_id':'V3','gene':'TET2','description':'TET2 p.Z'},
        ],
        'detected_variants_summary':'Variants detected.',
        'case_facts':[{'fact_id':'C1','kind':'blast count','value':'30% marrow blasts'}],
    }
    reg={
        'v01':{'variant_id':'V1','gene':'ASXL1','description':'ASXL1 p.X'},
        'v02':{'variant_id':'V2','gene':'SRSF2','description':'SRSF2 p.Y'},
        'v03':{'variant_id':'V3','gene':'TET2','description':'TET2 p.Z'},
    }
    card={'card_id':'C-DX','category':'diagnosis','genes':['ASXL1','SRSF2'],'diseases':['AML'],'evidence_tier':'guideline criterion','interpretation':'The category is defined by mutation in ASXL1 or SRSF2.'}
    return case,reg,card


def test_diagnosis_prompt_uses_compact_criterion_checks():
    text=step._prompt('diagnosis_who5')
    assert 'Diagnostic criterion-check discipline' in text
    assert 'positive_supportive' in text
    assert 'negative_supportive' in text
    assert 'not_contributory' in text
    assert 'verified_negative' in text
    assert 'presumed_negative' in text
    assert 'checks as short subject-ID arrays' in text
    assert 'result_status: positive' not in text


def test_diagnostic_result_context_does_not_materialize_panel_wide_negatives():
    case,reg,_=_criterion_case_fixture()
    scope='## Genes assessed\n- `ASXL1`\n- `SRSF2`\n- `TET2`\n- `TP53`\n'
    ctx=runtime.diagnostic_result_context(case,reg,scope)
    assert 'verified_negative_genes' not in ctx['ngs']
    assert ctx['ngs']['panel_gene_count']==4
    assert {r['subject'] for r in ctx['ngs']['detected_variants']}=={'v01','v02','v03'}
    assert 'TP53' not in yaml.safe_dump(ctx,sort_keys=False)


def test_diagnostic_prompt_context_size_is_independent_of_panel_gene_enumeration():
    case,reg,card=_criterion_case_fixture()
    genes=['ASXL1','SRSF2','TET2']+[f'G{i:04d}' for i in range(500)]
    scope='## Genes assessed\n'+''.join(f'- `{g}`\n' for g in genes)
    ctx=step._diagnosis_prompt_context(case,reg,scope,[card])
    rendered=yaml.safe_dump(ctx,sort_keys=False)
    assert len(rendered)<1500
    assert 'G0499' not in rendered
    assert ctx['finite_gene_set_membership']['C-DX']=={
        'in_gene_set':['v01','v02'],
        'outside_gene_set':['v03'],
    }


def test_closed_gene_set_bad_variant_is_pruned_locally_not_parent_diagnosis():
    case,reg,card=_criterion_case_fixture()
    doc={'diagnoses':[{'schema_disease':'AML','status':'established','diagnosis':'AML-MR','criteria':[{
        'authority_card_id':'C-DX','criterion_type':'molecular_membership','criterion':'Finite molecular criterion','reason':'The molecular criterion is satisfied.',
        'checks':{
            'positive_supportive':['v01','v02','v03'],
            'negative_supportive':[],'indeterminate':[],'not_contributory':[],
        }}]}]}
    kwargs=step._diagnosis_validation_kwargs([card],reg,case,{'ASXL1','SRSF2','TET2','TP53'})
    assert 'valid' in schema_validation.validate_who5_diagnosis(yaml.safe_dump(doc),allowed_diseases={'AML'},**kwargs)
    normalized,corrections=step._normalize_diagnosis_checks(doc,case,reg,[card],{'ASXL1','SRSF2','TET2','TP53'})
    checks=normalized['diagnoses'][0]['criteria'][0]['checks']
    assert [x['subject'] for x in checks['positive_supportive']]==['v01','v02']
    assert [x['subject'] for x in checks['not_contributory']]==['v03']
    assert normalized['diagnoses'][0]['diagnosis']=='AML-MR'
    assert any(x.get('subject')=='v03' and x.get('to')=='not_contributory' for x in corrections)


def test_molecular_membership_rejects_panel_negative_enumeration():
    case,reg,card=_criterion_case_fixture()
    doc={'diagnoses':[{'schema_disease':'AML','status':'established','diagnosis':'AML-MR','criteria':[{
        'authority_card_id':'C-DX','criterion_type':'molecular_membership','criterion':'Finite molecular criterion','reason':'The criterion is satisfied.',
        'checks':{'positive_supportive':['v01','v02'],'negative_supportive':['TP53'],'indeterminate':[],'not_contributory':['v03']},
    }]}]}
    kwargs=step._diagnosis_validation_kwargs([card],reg,case,{'ASXL1','SRSF2','TET2','TP53'})
    try:
        schema_validation.validate_who5_diagnosis(yaml.safe_dump(doc),allowed_diseases={'AML'},**kwargs)
    except Exception as exc:
        assert 'non-variant subjects' in str(exc)
    else:
        raise AssertionError('molecular_membership must reject bare panel-gene enumeration')


def test_verified_and_presumed_negatives_are_derived_after_compact_model_output():
    case,reg,card=_criterion_case_fixture()
    doc={'diagnoses':[{'schema_disease':'AML','status':'established','diagnosis':'Conditional diagnosis','criteria':[{
        'authority_card_id':'C-DX','criterion_type':'other','criterion':'Authority-backed exclusion criterion','reason':'The supplied authority makes both negative results relevant.',
        'checks':{
            'positive_supportive':[],
            'negative_supportive':['TP53','cytogenetics'],
            'indeterminate':[],'not_contributory':[],
        }}]}]}
    kwargs=step._diagnosis_validation_kwargs([card],reg,case,{'ASXL1','SRSF2','TET2','TP53'})
    assert 'valid' in schema_validation.validate_who5_diagnosis(yaml.safe_dump(doc),allowed_diseases={'AML'},**kwargs)
    normalized,_=step._normalize_diagnosis_checks(doc,case,reg,[card],{'ASXL1','SRSF2','TET2','TP53'})
    assert normalized['diagnoses'][0]['status']=='conditional'
    neg=normalized['diagnoses'][0]['criteria'][0]['checks']['negative_supportive']
    assert [(x['subject'],x['result_status']) for x in neg]==[('TP53','verified_negative'),('cytogenetics','presumed_negative')]


def test_not_contributory_checks_do_not_enter_diagnosis_reasons():
    case,reg,card=_criterion_case_fixture()
    compact={'diagnoses':[{'status':'established','diagnosis':'AML-MR','criteria':[{
        'authority_card_id':'C-DX','criterion_type':'molecular_membership','criterion':'Finite molecular criterion','reason':'The criterion is satisfied.',
        'checks':{
            'positive_supportive':['v01','v02'],
            'negative_supportive':[],'indeterminate':[],'not_contributory':['v03'],
        }}]}]}
    normalized,_=step._normalize_diagnosis_checks(compact,case,reg,[card],{'ASXL1','SRSF2','TET2','TP53'})
    row=normalized['diagnoses'][0]
    reasons=step._diagnosis_row_reasons(row,reg,case)
    assert 'ASXL1' in reasons[0] and 'SRSF2' in reasons[0]
    assert 'TET2' not in reasons[0]
    ledger=step._diagnosis_check_ledger('who5',normalized)
    assert len(ledger)==3
    assert all(x['reportable'] is False for x in ledger)


def test_non_contributory_checks_are_hidden_from_downstream_diagnosis_view():
    doc={'who5':{'diagnoses':[{'diagnosis':'AML-MR','criteria':[{'checks':{'positive_supportive':[{'subject':'v01','result_status':'positive'}],'negative_supportive':[],'indeterminate':[],'not_contributory':[{'subject':'v03','result_status':'positive'}]}}]}]}}
    public=step._diagnosis_public_view(doc)
    assert public['who5']['diagnoses'][0]['criteria'][0]['checks']['not_contributory']==[]
    assert doc['who5']['diagnoses'][0]['criteria'][0]['checks']['not_contributory'][0]['subject']=='v03'

def test_explicit_pending_non_ngs_fact_is_presumed_negative_and_conditional_when_supportive():
    case,reg,card=_criterion_case_fixture()
    case['case_facts'].append({'fact_id':'C2','kind':'cytogenetics','value':'pending'})
    doc={'diagnoses':[{'schema_disease':'AML','status':'established','diagnosis':'Conditional diagnosis','criteria':[{
        'authority_card_id':'C-DX','criterion_type':'other','criterion':'Negative dependency','reason':'The authority requires this result to be negative.',
        'checks':{'positive_supportive':[],'negative_supportive':['C2'],'indeterminate':[],'not_contributory':[]},
    }]}]}
    kwargs=step._diagnosis_validation_kwargs([card],reg,case,{'ASXL1','SRSF2','TET2','TP53'})
    assert 'valid' in schema_validation.validate_who5_diagnosis(yaml.safe_dump(doc),allowed_diseases={'AML'},**kwargs)
    normalized,_=step._normalize_diagnosis_checks(doc,case,reg,[card],{'ASXL1','SRSF2','TET2','TP53'})
    assert normalized['diagnoses'][0]['criteria'][0]['checks']['negative_supportive'][0]['result_status']=='presumed_negative'
    assert normalized['diagnoses'][0]['status']=='conditional'


def test_diagnosis_preservation_audit_cannot_request_proforma_regeneration(monkeypatch,tmp_path):
    elements=[{'schema_id':'DX-A','domain':'diagnosis','proposition':'WHO5 classification: AML-MR.','reasons':['Validated criterion supports AML-MR.'],'positive_effect':False,'locked_terms':['AML-MR']}]
    calls=[]
    def fake(work,**kw):
        calls.append((kw['call_id'],kw['prompt'])); kw['output'].parent.mkdir(parents=True,exist_ok=True)
        if 'statement-generation' in kw['call_id']:
            doc={'statements':[{'schema_id':'DX-A','statement':'WHO5 classification: AML-MR.'}]}
        else:
            doc={'audits':[{'schema_id':'DX-A','statement_represents_proforma':True,'reasoning_status':'unsupported','issues':['Model attempted to re-interpret criteria.'],'negative_guidance':['Do not re-diagnose.']}]}
        kw['output'].write_text(yaml.safe_dump(doc,sort_keys=False))
    monkeypatch.setattr(step,'_model_call',fake)
    out,need,guidance=step._generate_and_audit_statements(tmp_path,'dx',elements,{}, {},'self',preservation_only=True,authority_context={'audit_mode':'preservation_only'})
    assert need is False
    assert guidance==[]
    assert out[0]['semantic_status']=='supported'
    assert out[0]['statement']=='WHO5 classification: AML-MR.'
    assert len(calls)==2
    assert 'authoritative for preservation audit' in calls[1][1]


def test_statement_generation_enforces_locked_diagnosis_label():
    items=[{'schema_id':'DX-A','locked_terms':['AML-MR']}]
    bad=yaml.safe_dump({'statements':[{'schema_id':'DX-A','statement':'WHO5 classification: AML, NOS.'}]})
    with pytest.raises(ValidationFailure):
        schema_validation.validate_statement_generation_batch(bad,items)
    good=yaml.safe_dump({'statements':[{'schema_id':'DX-A','statement':'WHO5 classification: AML-MR.'}]})
    assert 'valid' in schema_validation.validate_statement_generation_batch(good,items)


def test_supplied_nonpending_case_fact_cannot_remain_indeterminate():
    case,reg,card=_criterion_case_fixture()
    doc={'diagnoses':[{'schema_disease':'AML','status':'established','diagnosis':'AML-MR','criteria':[{
        'authority_card_id':'C-DX','criterion_type':'other','criterion':'Observed threshold','reason':'The supplied fact satisfies the criterion.',
        'checks':{'positive_supportive':[],'negative_supportive':[],'indeterminate':['C1'],'not_contributory':[]},
    }]}]}
    kwargs=step._diagnosis_validation_kwargs([card],reg,case,{'ASXL1','SRSF2','TET2','TP53'})
    with pytest.raises(ValidationFailure):
        schema_validation.validate_who5_diagnosis(yaml.safe_dump(doc),allowed_diseases={'AML'},**kwargs)
    doc['diagnoses'][0]['criteria'][0]['checks']['indeterminate']=[]
    doc['diagnoses'][0]['criteria'][0]['checks']['positive_supportive']=['C1']
    assert 'valid' in schema_validation.validate_who5_diagnosis(yaml.safe_dump(doc),allowed_diseases={'AML'},**kwargs)
    normalized,_=step._normalize_diagnosis_checks(doc,case,reg,[card],{'ASXL1','SRSF2','TET2','TP53'})
    assert normalized['diagnoses'][0]['criteria'][0]['checks']['positive_supportive']==[{'subject':'C1','result_status':'positive'}]


def test_empty_biomarker_placeholder_row_is_structurally_ignored_and_removed():
    valid={'v01'}
    doc={
        'suitable_mrd':[{'variants':[],'reason':''}],
        'unsuitable_mrd':[],
        'uncertain':[],
        'no_effect':['v01'],
    }
    assert 'valid' in schema_validation.validate_biomarker(yaml.safe_dump(doc),valid)
    cleaned=step._drop_empty_effect_rows('biomarker',doc)
    assert cleaned['suitable_mrd']==[]


def test_diagnosis_statement_audit_prompt_is_preservation_only():
    text=step._prompt('statement_audit')
    assert 'Do NOT independently re-diagnose the case' in text
    assert 'do not replace or downgrade the diagnosis label' in text
    assert 'unreported gene on the configured complete NGS panel is a verified negative' in text

def test_diagnosis_preservation_falls_back_to_validated_proposition_if_audit_fails(monkeypatch,tmp_path):
    elements=[{'schema_id':'DX-A','domain':'diagnosis','proposition':'WHO5 classification: AML-MR.','reasons':['Validated criterion supports AML-MR.'],'positive_effect':False,'locked_terms':['AML-MR']}]
    def fake(work,**kw):
        kw['output'].parent.mkdir(parents=True,exist_ok=True)
        if 'statement-generation' in kw['call_id']:
            kw['output'].write_text(yaml.safe_dump({'statements':[{'schema_id':'DX-A','statement':'WHO5 classification: AML-MR with unsupported added qualifier.'}]},sort_keys=False))
            return
        raise step.StepFailure('malformed audit output')
    monkeypatch.setattr(step,'_model_call',fake)
    out,need,_=step._generate_and_audit_statements(tmp_path,'dx-fallback',elements,{}, {},'self',preservation_only=True,authority_context={'audit_mode':'preservation_only'})
    assert need is False
    assert out[0]['statement']=='WHO5 classification: AML-MR.'
    assert out[0]['semantic_status']=='supported'


def test_diagnosis_preservation_dissent_is_retained_for_end_user(monkeypatch,tmp_path):
    elements=[{'schema_id':'DX-A','domain':'diagnosis','proposition':'WHO5 classification: AML-MR.','reasons':['Validated criterion supports AML-MR.'],'positive_effect':False,'locked_terms':['AML-MR']}]
    def fake(work,**kw):
        kw['output'].parent.mkdir(parents=True,exist_ok=True)
        if 'statement-generation' in kw['call_id']:
            doc={'statements':[{'schema_id':'DX-A','statement':'WHO5 classification: AML-MR.'}]}
        else:
            doc={'audits':[{'schema_id':'DX-A','statement_represents_proforma':True,'reasoning_status':'unsupported','issues':['The auditor disputes the validated diagnostic reasoning.'],'negative_guidance':['The auditor would not support this diagnosis.']}]}
        kw['output'].write_text(yaml.safe_dump(doc,sort_keys=False))
    monkeypatch.setattr(step,'_model_call',fake)
    out,need,_=step._generate_and_audit_statements(tmp_path,'dx-dissent',elements,{}, {},'self',preservation_only=True,authority_context={'audit_mode':'preservation_only'})
    assert need is False
    assert out[0]['semantic_status']=='supported'
    assert out[0]['dissent']=={
        'dissent':['The auditor would not support this diagnosis.'],
        'reasoning':['The auditor disputes the validated diagnostic reasoning.'],
    }


def test_dissent_markdown_contains_only_statement_dissent_and_reasoning(tmp_path):
    elements=[{
        'schema_id':'DX-A',
        'statement':'WHO5 classification: AML-MR.',
        'dissent':{
            'dissent':['Do not support this classification.'],
            'reasoning':['A dissenting audit raised a criterion concern.'],
        },
    }]
    path=step._write_dissent(tmp_path,elements)
    assert path==tmp_path/'dissent.md'
    text=path.read_text()
    assert text==(
        '## Statement\n\n'
        'WHO5 classification: AML-MR.\n\n'
        '## Dissent\n\n'
        '- Do not support this classification.\n\n'
        '## Dissent reasoning\n\n'
        '- A dissenting audit raised a criterion concern.\n'
    )
    for forbidden in ('schema_id','risk','action','human_review','attempt'):
        assert forbidden not in text


def test_dissent_markdown_absent_when_no_retained_dissent(tmp_path):
    stale=tmp_path/'dissent.md'
    stale.write_text('stale')
    assert step._write_dissent(tmp_path,[{'schema_id':'DX-A','statement':'WHO5 classification: AML-MR.'}]) is None
    assert not stale.exists()
