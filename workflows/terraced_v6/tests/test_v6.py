from __future__ import annotations
import json
from pathlib import Path
import yaml
import pytest
from workflows.terraced_v6 import pipeline_registry, runtime, schema_validation, step

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parents[1]

def test_registered():
    d=json.loads((ROOT/'workflows/registry.json').read_text())
    assert d['workflows']['terraced-v6']['path']=='workflows/terraced_v6'

def test_workflow_architecture():
    d=json.loads((HERE/'workflow.json').read_text())
    assert d['workflow_id']=='terraced-v6'
    assert d['architecture']=='owner-proforma-evidence-deterministic-blocks-single-writer'

def test_settings_are_lean():
    d=json.loads((HERE/'settings.json.template').read_text())
    assert d['schema_version']==1
    old={'statement_generation_attempts','statement_audit_attempts','summary_plan_attempts','paraphrase_attempts','semantic_proforma_regenerations'}
    assert not old & set(d['retries'])
    assert set(d['prompts'])=={'structure_case','diagnosis_who5','diagnosis_icc','diagnosis_other','prognosis','treatment','biomarker','germline','evidence_match','evidence_audit','report_write','report_preservation'}

def test_removed_prompt_assets_absent():
    for name in ('statement_generation.md','statement_audit.md','summary_plan.md','summary_plan_audit.md','paraphrase.md','paraphrase_audit.md'):
        assert not (HERE/'prompts'/name).exists()

def test_pipeline_roles_are_minimal():
    assert pipeline_registry.ROLES==('structure','diagnosis','ptbg','evidence_match','evidence_audit','report_write','preservation_check','syntax_repair')
    for name in pipeline_registry.names(): pipeline_registry.load(name)

def test_reportability_defaults():
    assert step._reportable('prognosis','uncertain') is False
    assert step._reportable('treatment','no_drug_implication') is False
    assert step._reportable('biomarker','not_mrd_marker') is False
    assert step._reportable('germline','germline_against') is False

def test_who5_validator():
    text='''schema_disease: AML\ndiagnosis: AML with X\nvariants: [v01]\nreason: Molecular findings refine the supplied diagnosis.\n'''
    schema_validation.validate_who5_diagnosis(text,allowed_diseases={'AML'},valid_variants={'v01'})

def test_icc_validator():
    schema_validation.validate_icc_diagnosis('diagnosis: AML\nvariants: []\nreason: Molecular findings do not alter the supplied diagnosis.\n',valid_variants={'v01'})

def test_second_diagnosis_null_contract():
    schema_validation.validate_second_diagnosis('diagnosis: null\nvariants: []\nreason: null\n',valid_variants={'v01'})
    with pytest.raises(ValueError): schema_validation.validate_second_diagnosis('diagnosis: null\nvariants: [v01]\nreason: null\n',valid_variants={'v01'})

def test_prognosis_every_variant_once():
    text='''favorable:\n  - variants: [v01]\n    reason: favorable\nadverse:\n  - variants: [v02]\n    reason: adverse\nneutral: []\nuncertain: []\nprognostic_score: null\n'''
    schema_validation.validate_prognosis(text,{'v01','v02'})

def test_prognosis_no_not_calculable():
    text='''favorable:\n  - variants: [v01]\n    reason: favorable\nadverse: []\nneutral: []\nuncertain: []\nprognostic_score:\n  name: score\n  result: not calculable\n  reason: missing data\n'''
    with pytest.raises(ValueError): schema_validation.validate_prognosis(text,{'v01'})

def test_treatment_target_sensitive_are_distinct_and_can_overlap():
    text='''drug_target:\n  - variants: [v01]\n    therapy: drug A\n    reason: target\ndrug_sensitive:\n  - variants: [v01]\n    therapy: drug B\n    reason: sensitivity\ndrug_resistant: []\nno_drug_implication:\n  - variants: [v02]\n    reason: none\n'''
    schema_validation.validate_treatment(text,{'v01','v02'})

def test_mrd_binary_coverage():
    schema_validation.validate_biomarker('''mrd_marker:\n  - variants: [v01]\n    reason: marker\nnot_mrd_marker:\n  - variants: [v02]\n    reason: not marker\n''',{'v01','v02'})

def test_germline_integrated_buckets_cover_variants():
    schema_validation.validate_germline('''germline_support: []\ngermline_against:\n  - variants: [v01]\n    reason: integrated clinical and molecular picture argues against syndrome\ngermline_uncertain:\n  - variants: [v02]\n    reason: insufficient integrated context\n''',{'v01','v02'})

def test_finite_membership_context_only_detected_variants():
    reg={'v01':{'gene':'ASXL1'},'v02':{'gene':'TET2'}}
    card={'card_id':'C1','category':'diagnosis','genes':['ASXL1'],'interpretation':'defined by mutation in ASXL1'}
    ctx=step._finite_membership_context(reg,[card])
    assert ctx['finite_gene_set_membership']['C1']=={'qualifying':['v01'],'not_qualifying':['v02']}

def test_parallel_rows_consolidate_only_same_normalized_proposition():
    reg={'v01':{'gene':'ASXL1','description':'ASXL1 p.X'},'v02':{'gene':'SRSF2','description':'SRSF2 p.Y'}}
    doc={'favorable':[],'adverse':[{'variants':['v01'],'reason':'ASXL1 mutation confers adverse prognosis.'},{'variants':['v02'],'reason':'SRSF2 mutation confers adverse prognosis.'}],'neutral':[],'uncertain':[],'prognostic_score':None}
    out=step._consolidate_rows('prognosis',doc,reg)
    assert len(out['adverse'])==1
    assert out['adverse'][0]['variants']==['v01','v02']

def test_diagnosis_fallback_combines_equal_labels():
    block={'domain':'diagnosis','relationship':'same','components':[{'role':'who5','diagnosis':'MDS'},{'role':'icc','diagnosis':'MDS'}]}
    text=step._fallback_block_text(block)
    assert 'WHO5' in text and 'ICC' in text and 'both' in text

def test_diagnosis_fallback_contrasts_different_labels():
    block={'domain':'diagnosis','relationship':'different','components':[{'role':'who5','diagnosis':'A'},{'role':'icc','diagnosis':'B'}]}
    text=step._fallback_block_text(block)
    assert 'In contrast' in text

def test_report_writer_contract():
    blocks=[{'block_id':'DX'},{'block_id':'PX-1'}]
    schema_validation.validate_report_write('''blocks:\n  - block_id: DX\n    text: diagnosis\n  - block_id: PX-1\n    text: prognosis\n''',blocks)

def test_preservation_contract():
    blocks=[{'block_id':'DX'}]
    schema_validation.validate_preservation('''audits:\n  - block_id: DX\n    preserved: true\n    issue: null\n''',blocks)

def test_no_old_summary_functions_in_step_source():
    source=(HERE/'step.py').read_text()
    assert 'def stage_summary(' not in source
    assert 'def _generate_and_audit_statements(' not in source
    assert 'summary_plan_regenerations' not in source

def test_case_gene_prefix_normalization():
    case={'variants':[{'gene':'SRSF2','description':'NM_x:c.1A>G'}]}
    runtime.normalize_case_variant_descriptions(case)
    assert case['variants'][0]['description'].startswith('SRSF2 ')


def test_bare_run_resolves_most_recent_v6_run(tmp_path,monkeypatch):
    runs=tmp_path/'runs'; older=runs/'older'; newer=runs/'newer'
    older.mkdir(parents=True); newer.mkdir()
    import os
    os.utime(older,(1,1)); os.utime(newer,(2,2))
    monkeypatch.setattr(step,'HERE',tmp_path)
    assert step._resolve_run_work_dir(None)==newer


def test_explicit_run_work_dir_wins_over_most_recent(tmp_path,monkeypatch):
    runs=tmp_path/'runs'; latest=runs/'latest'; explicit=tmp_path/'explicit'
    latest.mkdir(parents=True); explicit.mkdir()
    monkeypatch.setattr(step,'HERE',tmp_path)
    assert step._resolve_run_work_dir(explicit)==explicit.resolve()
