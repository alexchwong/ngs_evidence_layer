from __future__ import annotations
import yaml
from workflows.terraced_v4 import pipeline_registry, schema_validation


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
