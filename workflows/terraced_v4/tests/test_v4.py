from __future__ import annotations
import yaml
from workflows.terraced_v4 import pipeline_registry, schema_validation
from workflows.terraced_v4 import step


def test_pipelines_load():
    assert {'self','lmstudio','openrouter'} <= set(pipeline_registry.names())
    for name in pipeline_registry.names():
        plan=pipeline_registry.load(name)
        assert plan.pipeline_id==name
        for role in pipeline_registry.ROLES:
            assert pipeline_registry.binding(plan,role).role==role


def test_prognosis_allows_multiple_effects_and_requires_coverage():
    doc={
        'favorable':[],
        'adverse':[{'variants':['v01'],'reason':'adverse association'},{'variants':['v01'],'reason':'second distinct adverse proposition'}],
        'other':[], 'uncertain':[], 'no_effect':['v02'],
        'overall':{'classification':'not calculable','reason':'required inputs unavailable'},
    }
    assert 'valid' in schema_validation.validate_prognosis(yaml.safe_dump(doc),{'v01','v02'})


def test_prognosis_rejects_positive_and_no_effect_overlap():
    doc={'favorable':[],'adverse':[{'variants':['v01'],'reason':'x'}],'other':[],'uncertain':[],'no_effect':['v01'],'overall':{'classification':'x','reason':'y'}}
    try: schema_validation.validate_prognosis(yaml.safe_dump(doc),{'v01'})
    except ValueError as exc: assert 'both effect and no_effect' in str(exc)
    else: raise AssertionError('expected overlap failure')


def test_germline_requires_clinical_support_for_suspect_or_uncertain():
    doc={'suspect':[{'variants':['v01'],'reason':'known germline gene and VAF compatible'}],'uncertain':[],'not_suspect':['v02'],'clinical_support':[{'variants':['v01'],'support':'unknown','reason':'family history not supplied'}]}
    assert 'valid' in schema_validation.validate_germline(yaml.safe_dump(doc),{'v01','v02'})


def test_evidence_match_does_not_validate_quote_exactness():
    text=yaml.safe_dump({'card_id':'C1','source':'IPSS-M','quote':'slightly normalized wording'})
    assert 'valid' in schema_validation.validate_evidence_match(text,{'C1'})


def test_evidence_audit_requires_actionable_comment_for_obvious_mismatch():
    text=yaml.safe_dump({'obvious_mismatch':True,'risk':'none','comments':[]})
    try: schema_validation.validate_evidence_audit(text)
    except ValueError as exc: assert 'actionable feedback' in str(exc)
    else: raise AssertionError('expected missing-comment failure')


def test_risk_log_is_idempotent_across_resume(tmp_path):
    kwargs=dict(stage='evidence',risk_type='citation_fidelity',message='same concern',schema_element='PX-01',attempts=1,action='retained_pending_human_review',human_review='recommended')
    first=step._risk(tmp_path,**kwargs); second=step._risk(tmp_path,**kwargs)
    doc=yaml.safe_load((tmp_path/'logs'/'risk_log.yaml').read_text())
    assert first==second=='R001'
    assert len(doc['risks'])==1


def test_summary_plan_audit_structure_and_fallback():
    audit=yaml.safe_dump({'preserved':False,'issues':[{'target':'diagnosis-1','issue':'Dropped qualifying molecular basis.'}]})
    assert 'valid' in step._validate_summary_plan_audit(audit)
    statements=[{'statement_id':'S0001','domain':'diagnosis','statement':'Diagnosis A.','card_tags':[]},{'statement_id':'S0002','domain':'prognosis','statement':'Risk B.','card_tags':[]}]
    plan=step._fallback_summary_plan(statements)
    assert [x['source_statement_ids'] for x in plan['sentences']]==[['S0001'],['S0002']]
