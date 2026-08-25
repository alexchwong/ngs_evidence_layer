from __future__ import annotations
import json
from pathlib import Path
import yaml
import pytest
from scripts.core.validated_model_task import ValidationFailure
from workflows.terraced_v6 import domain_contract, pipeline_registry, runtime, schema_validation, stage_checks, step

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
    text='''schema_disease: AML\ndiagnosis: AML with X\ndiagnostic_effect: refined\nvariants: [v01]\nreason: Molecular findings refine the supplied diagnosis.\n'''
    schema_validation.validate_who5_diagnosis(text,allowed_diseases={'AML'},valid_variants={'v01'})

def test_icc_validator():
    schema_validation.validate_icc_diagnosis('diagnosis: AML\ndiagnostic_effect: unchanged\nvariants: []\nreason: Molecular findings do not alter the supplied diagnosis.\n',valid_variants={'v01'})

def test_second_diagnosis_null_contract():
    schema_validation.validate_second_diagnosis('diagnosis: null\nvariants: []\nreason: null\n',valid_variants={'v01'})
    with pytest.raises(ValueError): schema_validation.validate_second_diagnosis('diagnosis: null\nvariants: [v01]\nreason: null\n',valid_variants={'v01'})

def test_prognosis_flat_contract_requires_one_row_per_variant():
    text=("classification:\n  - variant: v01\n    bucket: favorable\n    reason: favorable\n"
          "  - variant: v02\n    bucket: adverse\n    reason: adverse\nprognostic_score: null\n")
    schema_validation.validate_prognosis(text,{'v01','v02'})


def test_prognosis_reports_missing_and_bad_bucket_together():
    text=("classification:\n  - variant: v01\n    bucket: nonsense\n    reason: x\nprognostic_score: null\n")
    with pytest.raises(ValidationFailure) as exc:
        schema_validation.validate_prognosis(text,{'v01','v02'})
    paths={i.path for i in exc.value.issues}
    assert 'classification' in paths and 'classification[0].bucket' in paths


def test_prognosis_no_not_calculable():
    text=("classification:\n  - variant: v01\n    bucket: favorable\n    reason: favorable\n"
          "prognostic_score:\n  name: score\n  result: not calculable\n  reason: missing data\n")
    with pytest.raises(ValidationFailure): schema_validation.validate_prognosis(text,{'v01'})


def test_treatment_allows_multiple_rows_but_not_alongside_no_drug_implication():
    ok=("classification:\n  - variant: v01\n    bucket: drug_target\n    therapy: drug A\n    reason: target\n"
        "  - variant: v01\n    bucket: drug_sensitive\n    therapy: drug B\n    reason: sensitivity\n"
        "  - variant: v02\n    bucket: no_drug_implication\n    reason: none\n")
    schema_validation.validate_treatment(ok,{'v01','v02'})
    bad=("classification:\n  - variant: v01\n    bucket: drug_target\n    therapy: drug A\n    reason: target\n"
         "  - variant: v01\n    bucket: no_drug_implication\n    reason: none\n"
         "  - variant: v02\n    bucket: no_drug_implication\n    reason: none\n")
    with pytest.raises(ValidationFailure): schema_validation.validate_treatment(bad,{'v01','v02'})


def test_mrd_binary_coverage():
    schema_validation.validate_biomarker(
        "classification:\n  - variant: v01\n    bucket: mrd_marker\n    reason: marker\n"
        "  - variant: v02\n    bucket: not_mrd_marker\n    reason: not marker\n",{'v01','v02'})


def test_germline_integrated_buckets_cover_variants():
    schema_validation.validate_germline(
        "classification:\n  - variant: v01\n    bucket: germline_against\n    reason: argues against\n"
        "  - variant: v02\n    bucket: germline_uncertain\n    reason: insufficient context\n",{'v01','v02'})


def test_finite_membership_context_only_detected_variants():
    reg={'v01':{'gene':'ASXL1'},'v02':{'gene':'TET2'}}
    card={'card_id':'C1','category':'diagnosis','genes':['ASXL1'],'interpretation':'defined by mutation in ASXL1'}
    ctx=step._finite_membership_context(reg,[card])
    assert ctx['finite_gene_set_membership']['C1']=={'qualifying':['v01'],'not_qualifying':['v02']}

def test_parallel_rows_consolidate_only_same_normalized_proposition():
    reg={'v01':{'gene':'ASXL1','description':'ASXL1 p.X'},'v02':{'gene':'SRSF2','description':'SRSF2 p.Y'}}
    doc={'favorable':[],'adverse':[{'variants':['v01'],'reason':'ASXL1 mutation confers adverse prognosis.'},{'variants':['v02'],'reason':'SRSF2 mutation confers adverse prognosis.'}],'neutral':[],'uncertain':[],'prognostic_score':None}
    out,merges=step._consolidate_rows('prognosis',doc,reg)
    assert len(merges)==1 and merges[0]['merged_variants']==['v02']
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


# --- Phase 0: canonical downstream model context -----------------------------

from workflows.terraced_v6 import model_context

_REG={'v01':{'variant_id':'V1','gene':'SRSF2','description':'SRSF2 p.P95H'},
      'v02':{'variant_id':'V2','gene':'ASXL1','description':'ASXL1 p.G646fs'}}
_CASE={'provisional_disease':'MDS','morphologic_diagnosis_origin':'supplied','bootstrap_cmcs':['MDS'],
       'variants':[{'variant_id':'V1','gene':'SRSF2','description':'SRSF2 p.P95H'}],
       'detected_variants_summary':'Two variants detected.',
       'case_facts':[{'fact_id':'C1','kind':'blast percentage','value':'4%'}]}
_DX={'who5':{'schema_disease':'MDS','diagnosis':'MDS with SF3B1','variants':['v01'],'reason':'long paragraph'},
     'icc':{'diagnosis':'MDS-SF3B1','variants':['v01'],'reason':'another long paragraph'},
     'second_diagnosis':{'diagnosis':None,'variants':[],'reason':None},
     'relationship':'different'}


def test_registry_context_strips_source_case_ids():
    text=model_context.registry_context(_REG)
    assert 'v01' in text and 'v02' in text
    assert 'V1' not in text and 'V2' not in text
    assert 'variant_id' not in text


def test_case_projection_never_emits_variants():
    doc=model_context.case_projection(_CASE,fields=model_context.DOMAIN_CASE_FIELDS)
    assert 'variants' not in doc
    assert doc['provisional_disease']=='MDS'
    assert doc['case_facts'][0]['fact_id']=='C1'


def test_case_projection_rejects_unknown_field():
    with pytest.raises(ValueError): model_context.case_projection(_CASE,fields=('variants',))


def test_diagnosis_projection_drops_reason_but_keeps_relationship():
    doc=model_context.diagnosis_projection(_DX)
    assert doc['who5']=={'schema_disease':'MDS','diagnosis':'MDS with SF3B1','variants':['v01']}
    assert 'reason' not in doc['icc']
    assert doc['relationship']=='different'


def test_assert_canonical_detects_a_leak():
    ids=model_context.source_ids(_REG)
    assert ids==['V1','V2']
    model_context.assert_canonical('variants: [v01, v02]',source_ids=ids)
    with pytest.raises(AssertionError):
        model_context.assert_canonical('variant_id: V1',source_ids=ids)


def test_assert_canonical_ignores_substring_matches():
    # V1 must not match inside V10 or inside an unrelated token.
    model_context.assert_canonical('variants: [V10, HGVSV1X]',source_ids=['V1'])


def test_step_no_longer_dumps_the_raw_structured_case_into_prompts():
    source=(HERE/'step.py').read_text()
    # The case artifact is still written to disk with its V-namespace intact;
    # what must not recur is splicing it into a model-facing prompt block.
    assert "```json\\n'+json.dumps(case" not in source
    assert 'def _variant_context(' not in source


def test_removed_v5_era_helpers_are_absent():
    for name in ('validate_no_false_missing_case_claims','diagnostic_result_context','panel_genes_from_scope'):
        assert not hasattr(runtime,name)
    assert 'fatal=' not in (HERE/'step.py').read_text()


# --- Phase 1: accumulated, bounded, actionable feedback ----------------------

def test_issues_render_over_multiple_labelled_lines():
    from scripts.core.validated_model_task import ValidationIssue
    text=ValidationIssue('a.b','p','f',received='r',expected='e').render(1)
    assert text.splitlines()[0]=='1. a.b'
    assert '   Problem: p.' in text and '   Required fix: f.' in text


def test_rendered_issue_list_is_capped_and_says_so():
    from scripts.core.validated_model_task import ValidationIssue, render_issues, MAX_RENDERED_ISSUES
    many=[ValidationIssue(f'p{i}','problem','fix') for i in range(MAX_RENDERED_ISSUES+5)]
    out=render_issues(many)
    assert f'{MAX_RENDERED_ISSUES+1}.' not in out
    assert '5 further issue(s)' in out


def test_large_enum_reports_nearest_values_not_the_whole_vocabulary():
    from workflows.terraced_v6 import issues as iss
    allowed=[f'DISEASE-{i:03d}' for i in range(200)]+['MDS','MDS/MPN']
    found=iss.enum_field('MDs',allowed,'schema_disease',label='schema disease')
    assert len(found)==1
    rendered=found[0].render(1)
    assert 'MDS' in rendered
    assert 'DISEASE-000' not in rendered
    assert len(rendered)<600


def test_small_enum_still_lists_every_allowed_value():
    from workflows.terraced_v6 import issues as iss
    found=iss.enum_field('severe',('none','warning'),'risk',label='risk level')
    assert "['none', 'warning']" in found[0].render(1)


def test_one_row_per_id_names_missing_duplicate_and_unexpected():
    from workflows.terraced_v6 import issues as iss
    rows=[{'id':'A'},{'id':'A'},{'id':'Z'}]
    found=iss.one_row_per_id(rows,['A','B'],id_field='id',path='rows')
    text=' '.join(i.render(1) for i in found)
    assert "missing ['B']" in text and "duplicated ['A']" in text and "unexpected ['Z']" in text


def test_every_validator_accumulates_rather_than_stopping_at_the_first_defect():
    with pytest.raises(ValidationFailure) as exc:
        schema_validation.validate_report_write('blocks:\n  - block_id: WRONG\n    text: ""\n',
                                                [{'block_id':'DX'}])
    assert len(exc.value.issues)>=2


# --- Phase 2: fixtures and standalone stage checking -------------------------

FIXTURES=HERE/'tests'/'fixtures'
_FIXTURE_CASES=[(d.name,f) for d in sorted(FIXTURES.iterdir()) if d.is_dir()
                for f in sorted(d.iterdir()) if f.name.startswith('invalid_') and not f.name.endswith('.expected.txt')]


def test_every_registered_stage_has_a_fixture_directory():
    for stage in stage_checks.names():
        assert (FIXTURES/stage).is_dir(), f'stage {stage} has no fixtures'
        assert list((FIXTURES/stage).glob('valid.*')), f'stage {stage} has no valid fixture'


@pytest.mark.parametrize('stage,path',[(s,f) for s,f in _FIXTURE_CASES],ids=lambda x:getattr(x,'name',x))
def test_invalid_fixture_produces_exactly_the_recorded_feedback(stage,path):
    expected=path.with_suffix(path.suffix+'.expected.txt')
    assert expected.is_file(), f'{path.name} has no recorded feedback'
    with pytest.raises(ValidationFailure) as exc:
        stage_checks.check(stage,path.read_text(),stage_checks.fixture_context(stage))
    assert str(exc.value)+'\n'==expected.read_text()


@pytest.mark.parametrize('stage',sorted(stage_checks.names()))
def test_valid_fixture_passes(stage):
    for f in (FIXTURES/stage).glob('valid.*'):
        stage_checks.check(stage,f.read_text(),stage_checks.fixture_context(stage))


def test_check_stage_cli_reports_invalid_with_a_failure_exit_code():
    path=FIXTURES/'prognosis'/'invalid_missing_variant.yaml'
    assert step.main(['check-stage','--stage','prognosis','--file',str(path)])==step.EXIT_FAILURE
    assert step.main(['check-stage','--stage','prognosis','--file',str(FIXTURES/'prognosis'/'valid.yaml')])==step.EXIT_OK


# --- Phase 3: stagnation and transform audit ---------------------------------

# Stagnation now lives in the shared runner; see tests/test_runner.py tests 7 and 8,
# which also cover survival across a simulated self-handoff process boundary.


def test_transform_log_is_written_and_idempotent(tmp_path):
    record={'domain':'prognosis','bucket':'adverse','transform':'consolidate_parallel_variant_rows','merged_variants':['v02']}
    step._log_transforms(tmp_path,[record]); step._log_transforms(tmp_path,[record])
    doc=yaml.safe_load(step._transform_log_path(tmp_path).read_text())
    assert doc['transforms']==[record]


# --- Phase 4: one-row-per-variant contract -----------------------------------

def test_skeleton_prefills_every_supplied_variant():
    text=domain_contract.skeleton(domain_contract.PROGNOSIS,['v01','v02','v03'])
    assert text.count('- variant: v')==3
    for vid in ('v01','v02','v03'): assert f'- variant: {vid}' in text
    assert '<favorable|adverse|neutral|uncertain>' in text


def test_pivot_restores_the_legacy_bucket_artifact():
    flat={'classification':[{'variant':'v01','bucket':'adverse','reason':'a'},
                            {'variant':'v02','bucket':'favorable','reason':'b'}],
          'prognostic_score':None}
    doc=domain_contract.pivot(flat,domain_contract.PROGNOSIS)
    assert set(doc)=={'favorable','adverse','neutral','uncertain','prognostic_score'}
    assert doc['adverse']==[{'variants':['v01'],'reason':'a'}]
    assert doc['prognostic_score'] is None


def test_pivot_keeps_therapy_on_positive_treatment_buckets_only():
    flat={'classification':[{'variant':'v01','bucket':'drug_target','therapy':'T','reason':'a'},
                            {'variant':'v02','bucket':'no_drug_implication','reason':'b'}]}
    doc=domain_contract.pivot(flat,domain_contract.TREATMENT)
    assert doc['drug_target']==[{'variants':['v01'],'therapy':'T','reason':'a'}]
    assert doc['no_drug_implication']==[{'variants':['v02'],'reason':'b'}]


def test_pivot_output_still_satisfies_downstream_consolidation():
    reg={'v01':{'gene':'ASXL1','description':'ASXL1 p.X'},'v02':{'gene':'SRSF2','description':'SRSF2 p.Y'}}
    flat={'classification':[{'variant':'v01','bucket':'adverse','reason':'ASXL1 mutation confers adverse prognosis.'},
                            {'variant':'v02','bucket':'adverse','reason':'SRSF2 mutation confers adverse prognosis.'}],
          'prognostic_score':None}
    doc=domain_contract.pivot(flat,domain_contract.PROGNOSIS)
    out,merges=step._consolidate_rows('prognosis',doc,reg)
    assert out['adverse'][0]['variants']==['v01','v02'] and len(merges)==1


def test_bucket_vocabulary_has_exactly_one_definition():
    # Reportability defaults, element assembly and consolidation must all agree
    # with domain_contract rather than carrying their own literal tuples.
    for domain,contract in domain_contract.CONTRACTS.items():
        defaults=set(step._REPORTABILITY_DEFAULTS[domain])-{'prognostic_score'}
        assert defaults==set(contract.buckets), domain
    source=(HERE/'step.py').read_text()
    assert "'favorable','adverse','neutral','uncertain'" not in source
    assert "'mrd_marker','not_mrd_marker'" not in source


def test_domain_prompts_no_longer_carry_their_own_output_shape():
    for name in ('prognosis','treatment','biomarker','germline'):
        text=(HERE/'prompts'/f'{name}.md').read_text()
        assert 'Return YAML only' not in text
        assert '```yaml' not in text

# --- Semantic evidence-resolution retries ------------------------------------

def _test_card(card_id, *, gene='FLT3', category='prognosis'):
    return {
        'card_id': card_id,
        'category': category,
        'genes': [gene] if gene else [],
        'diseases': ['AML'],
        'evidence_tier': 'tier-1',
        'interpretation': f'{card_id} interpretation',
        'paper_nickname': card_id,
    }


def _scripted_model_call(script, prompt_checks=None):
    prompt_checks = prompt_checks or {}
    def call(work, *, call_id, prompt, output, validator, **kwargs):
        if call_id in prompt_checks:
            prompt_checks[call_id](prompt)
        text = script[call_id]
        step._write(output, text)
        validator(text)
        return text
    return call


def test_evidence_match_allows_explicit_no_citation_support():
    items=[{'evidence_id':'E0001','candidate_card_ids':['C1']}]
    schema_validation.validate_evidence_match_batch(
        'matches:\n  - evidence_id: E0001\n    card_id: null\n    source: null\n    quote: null\n', items
    )
    with pytest.raises(ValidationFailure):
        schema_validation.validate_evidence_match_batch(
            'matches:\n  - evidence_id: E0001\n    card_id: null\n    source: study\n    quote: null\n', items
        )


def test_semantic_retry_carries_all_prior_audit_feedback_and_resolves_dissent(tmp_path,monkeypatch):
    cards=[_test_card('C1'),_test_card('C2'),_test_card('C3')]
    el={'schema_id':'PX-ADVERSE-01','domain':'prognosis','bucket':'adverse',
        'statement':'FLT3-ITD confers adverse prognosis in AML.',
        'reason':'FLT3-ITD confers adverse prognosis in AML.','variants':['v01'],
        'evidence_domain':'prognosis','required':False,'source':{'variants':['v01']}}
    reg={'v01':{'gene':'FLT3'}}
    script={
        'evidence-match-batch-01':'matches:\n  - evidence_id: E0001\n    card_id: C1\n    source: one\n    quote: quote one\n',
        'evidence-audit-batch-01':'audits:\n  - evidence_id: E0001\n    quote_supports_statement: false\n    quote_supports_reason: false\n    risk: none\n    comments: ["wrong disease context"]\n',
        'evidence-match-batch-02':'matches:\n  - evidence_id: E0001\n    card_id: C2\n    source: two\n    quote: quote two\n',
        'evidence-audit-batch-02':'audits:\n  - evidence_id: E0001\n    quote_supports_statement: false\n    quote_supports_reason: false\n    risk: none\n    comments: ["wrong clinical function"]\n',
        'evidence-match-batch-03':'matches:\n  - evidence_id: E0001\n    card_id: C3\n    source: three\n    quote: quote three\n',
        'evidence-audit-batch-03':'audits:\n  - evidence_id: E0001\n    quote_supports_statement: true\n    quote_supports_reason: true\n    risk: none\n    comments: []\n',
    }
    def check2(prompt):
        assert 'rejected_card_id: C1' in prompt
        assert 'wrong disease context' in prompt
        assert 'candidate_card_ids:\n  - C2\n  - C3' in prompt
    def check3(prompt):
        assert 'rejected_card_id: C1' in prompt and 'rejected_card_id: C2' in prompt
        assert 'wrong disease context' in prompt and 'wrong clinical function' in prompt
        assert 'candidate_card_ids:\n  - C3' in prompt
    monkeypatch.setattr(step,'_model_call',_scripted_model_call(script,{
        'evidence-match-batch-02':check2,'evidence-match-batch-03':check3}))
    monkeypatch.setattr(step,'_retry',lambda name: 3 if name=='evidence_resolution_attempts' else 2)
    monkeypatch.setattr(step.card_identity,'tag_by_id',lambda manifest:{'C1':'T1','C2':'T2','C3':'T3'})
    out=step.stage_evidence(tmp_path,[el],{'prognosis':cards},reg,{},None)
    assert len(out)==1 and out[0]['evidence']['card_id']=='C3'
    assert out[0]['evidence']['semantic_attempt']==3
    issue=step._semantic_dissent_issue(tmp_path,'evidence:PX-ADVERSE-01')
    assert issue['status']=='resolved'
    raised=[h for h in issue['history'] if h['event']=='raised']
    assert [h['stage'] for h in raised]==['evidence audit attempt 1','evidence audit attempt 2']
    dissent=(tmp_path/'dissent.md').read_text()
    assert 'wrong disease context' in dissent and 'wrong clinical function' in dissent


def test_ptbg_semantic_exhaustion_suppresses_statement_but_keeps_failed_audits(tmp_path,monkeypatch):
    cards=[_test_card('C1'),_test_card('C2')]
    el={'schema_id':'PX-ADVERSE-01','domain':'prognosis','bucket':'adverse','statement':'claim','reason':'reason',
        'variants':['v01'],'evidence_domain':'prognosis','required':False,'source':{'variants':['v01']}}
    reg={'v01':{'gene':'FLT3'}}
    script={
        'evidence-match-batch-01':'matches:\n  - evidence_id: E0001\n    card_id: C1\n    source: one\n    quote: q1\n',
        'evidence-audit-batch-01':'audits:\n  - evidence_id: E0001\n    quote_supports_statement: false\n    quote_supports_reason: false\n    risk: none\n    comments: ["first mismatch"]\n',
        'evidence-match-batch-02':'matches:\n  - evidence_id: E0001\n    card_id: C2\n    source: two\n    quote: q2\n',
        'evidence-audit-batch-02':'audits:\n  - evidence_id: E0001\n    quote_supports_statement: false\n    quote_supports_reason: false\n    risk: none\n    comments: ["second mismatch"]\n',
    }
    monkeypatch.setattr(step,'_model_call',_scripted_model_call(script))
    monkeypatch.setattr(step,'_retry',lambda name: 2)
    monkeypatch.setattr(step.card_identity,'tag_by_id',lambda manifest:{'C1':'T1','C2':'T2'})
    out=step.stage_evidence(tmp_path,[el],{'prognosis':cards},reg,{},None)
    assert out==[]
    issue=step._semantic_dissent_issue(tmp_path,'evidence:PX-ADVERSE-01')
    assert issue['status']=='resolved'
    raised=[h for h in issue['history'] if h['event']=='raised']
    assert [h['stage'] for h in raised]==['evidence audit attempt 1','evidence audit attempt 2']


def test_supplied_morphology_is_fallback_when_diagnosis_evidence_exhausts(tmp_path,monkeypatch):
    card=_test_card('D1',category='diagnosis')
    el={'schema_id':'DX-WHO5','domain':'diagnosis','bucket':'who5','framework_label':'WHO5',
        'statement':'WHO5 classification: AML with subtype X.','reason':'FLT3 refines the diagnosis.',
        'variants':['v01'],'evidence_domain':'diagnosis_who5','required':True,
        'source':{'schema_disease':'AML','diagnosis':'AML with subtype X','diagnostic_effect':'refined','variants':['v01'],'reason':'FLT3 refines the diagnosis.'},
        'morphologic_diagnosis_origin':'supplied','starting_morphologic_diagnosis':'AML'}
    script={
        'evidence-match-batch-01':'matches:\n  - evidence_id: E0001\n    card_id: D1\n    source: dx\n    quote: q\n',
        'evidence-audit-batch-01':'audits:\n  - evidence_id: E0001\n    quote_supports_statement: false\n    quote_supports_reason: false\n    risk: none\n    comments: ["does not support subtype X"]\n',
    }
    monkeypatch.setattr(step,'_model_call',_scripted_model_call(script))
    monkeypatch.setattr(step,'_retry',lambda name: 3 if name=='evidence_resolution_attempts' else 2)
    monkeypatch.setattr(step.card_identity,'tag_by_id',lambda manifest:{'D1':'TD1'})
    out=step.stage_evidence(tmp_path,[el],{'diagnosis_who5':[card]}, {'v01':{'gene':'FLT3'}},{},None)
    assert len(out)==1
    assert out[0]['source']['diagnosis']=='AML'
    assert out[0]['source']['diagnostic_effect']=='unchanged'
    assert out[0]['evidence'] is None
    issue=step._semantic_dissent_issue(tmp_path,'evidence:DX-WHO5')
    assert issue['status']=='resolved'
    assert any('Retained supplied morphology: AML.' in x for h in issue['history'] for x in h.get('outcome',[]))


def test_inferred_primary_diagnosis_without_candidate_support_is_omitted_and_open_dissent(tmp_path,monkeypatch):
    el={'schema_id':'DX-WHO5','domain':'diagnosis','bucket':'who5','framework_label':'WHO5',
        'statement':'WHO5 classification: AML.','reason':'Case facts suggest AML.','variants':[],
        'evidence_domain':'diagnosis_who5','required':True,
        'source':{'schema_disease':'AML','diagnosis':'AML','diagnostic_effect':'unchanged','variants':[],'reason':'Case facts suggest AML.'},
        'morphologic_diagnosis_origin':'inferred','starting_morphologic_diagnosis':'AML'}
    monkeypatch.setattr(step.card_identity,'tag_by_id',lambda manifest:{})
    out=step.stage_evidence(tmp_path,[el],{'diagnosis_who5':[]},{},{},None)
    assert out==[]
    issue=step._semantic_dissent_issue(tmp_path,'evidence:DX-WHO5')
    assert issue['status']=='open'
    assert 'remains unresolved' in (tmp_path/'dissent.md').read_text()


def test_failed_evidence_audit_requires_actionable_feedback():
    items=[{'evidence_id':'E0001'}]
    bad='''audits:\n  - evidence_id: E0001\n    quote_supports_statement: false\n    quote_supports_reason: true\n    risk: none\n    comments: []\n'''
    with pytest.raises(ValidationFailure) as exc:
        schema_validation.validate_evidence_audit_batch(bad,items)
    assert 'without explanatory feedback' in str(exc.value)
