from __future__ import annotations
from contextlib import ExitStack
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml
from scripts.core.validated_model_task import ValidationFailure
from workflows.terraced_v6 import card_identity, domain_contract, model_client, pipeline_registry, rendering, runtime, schema_validation, stage_checks, step

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parents[1]


def _assert_raises(exception):
    return unittest.TestCase().assertRaises(exception)


class _MonkeyPatch:
    """Minimal standard-library replacement for the setattr fixture used here."""

    def __init__(self, stack):
        self._stack = stack

    def setattr(self, target, name, value):
        self._stack.enter_context(patch.object(target, name, value))

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
    assert d['rendering']['cards']=='compact'
    for authority in ('who5','icc'):
        assert isinstance(d['diagnosis'][authority]['included_publication_keys'],list)
        assert isinstance(d['diagnosis'][authority]['excluded_publication_keys'],list)
        assert 'publication_keys' not in d['diagnosis'][authority]

def test_removed_prompt_assets_absent():
    for name in ('statement_generation.md','statement_audit.md','summary_plan.md','summary_plan_audit.md','paraphrase.md','paraphrase_audit.md'):
        assert not (HERE/'prompts'/name).exists()

def test_pipeline_roles_are_minimal():
    assert pipeline_registry.ROLES==('structure','diagnosis','ptbg','evidence_match','evidence_audit','report_write','preservation_check','syntax_repair')
    for name in pipeline_registry.names(): pipeline_registry.load(name)

def test_pipeline_filename_is_identity_and_pipeline_id_field_is_absent():
    for name in pipeline_registry.names():
        plan=pipeline_registry.load(name)
        assert plan.pipeline_id==name
        assert plan.path.stem==name
        assert 'id' not in plan.doc['pipeline']

def test_custom_pipeline_name_comes_from_filename():
    with tempfile.TemporaryDirectory() as tmp:
        target=Path(tmp)/'lmstudio-macpro.yaml'
        target.write_bytes((HERE/'pipelines/lmstudio.yaml').read_bytes())
        try:
            pipeline_registry.configure(tmp)
            assert pipeline_registry.names()==('lmstudio-macpro',)
            assert pipeline_registry.load('lmstudio-macpro').pipeline_id=='lmstudio-macpro'
        finally:
            pipeline_registry.configure(HERE/'pipelines')

def test_obsolete_pipeline_id_is_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        target=Path(tmp)/'custom.yaml'
        text=(HERE/'pipelines/lmstudio.yaml').read_text()
        target.write_text(text.replace('pipeline:\n', 'pipeline:\n  id: wrong\n', 1))
        with _assert_raises(ValueError):
            pipeline_registry.load_yaml(target)

def test_public_defaults_are_synced_from_terraced_v6():
    assert (HERE/'settings.json.template').read_bytes()==(ROOT/'config/settings.json.template').read_bytes()
    source={p.name:p.read_bytes() for p in (HERE/'pipelines').glob('*.yaml')}
    public={p.name:p.read_bytes() for p in (ROOT/'config/pipelines').glob('*.yaml')}
    assert source==public

def test_non_self_defaults_use_model_aliases():
    for name in ('lmstudio','openrouter'):
        plan=pipeline_registry.load(name)
        assert 'models' not in plan.doc
        assert set(plan.doc['model_roles'])==set(pipeline_registry.ROLES)
        for role in pipeline_registry.ROLES:
            assert plan.doc['model_roles'][role]['model'] in plan.doc['model_aliases']

def test_alias_binding_resolves_model_and_openrouter_provider_routing():
    with tempfile.TemporaryDirectory() as tmp:
        target=Path(tmp)/'custom.yaml'
        doc=yaml.safe_load((HERE/'pipelines/openrouter.yaml').read_text())
        doc['model_aliases']={
            'fast':'qwen/qwen3-coder-next',
            'reasoning':{
                'model':'openai/gpt-oss-20b',
                'provider':{'order':['groq'],'allow_fallbacks':False},
            },
        }
        for role,row in doc['model_roles'].items(): row['model']='fast'
        doc['model_roles']['diagnosis']['model']='reasoning'
        target.write_text(yaml.safe_dump(doc,sort_keys=False))
        plan=pipeline_registry.load_yaml(target)
        structure=pipeline_registry.binding(plan,'structure')
        diagnosis=pipeline_registry.binding(plan,'diagnosis')
        assert structure.model=='qwen/qwen3-coder-next'
        assert structure.provider_routing is None
        assert diagnosis.model=='openai/gpt-oss-20b'
        assert diagnosis.provider_routing=={'order':['groq'],'allow_fallbacks':False}

def test_alias_pipeline_rejects_unknown_role_alias():
    with tempfile.TemporaryDirectory() as tmp:
        target=Path(tmp)/'custom.yaml'
        doc=yaml.safe_load((HERE/'pipelines/lmstudio.yaml').read_text())
        doc['model_roles']['diagnosis']['model']='missing'
        target.write_text(yaml.safe_dump(doc,sort_keys=False))
        with _assert_raises(ValueError): pipeline_registry.load_yaml(target)

def test_alias_pipeline_rejects_unsupported_provider_routing_field():
    with tempfile.TemporaryDirectory() as tmp:
        target=Path(tmp)/'custom.yaml'
        doc=yaml.safe_load((HERE/'pipelines/openrouter.yaml').read_text())
        doc['model_aliases']['default']={
            'model':'qwen/qwen3-coder-next',
            'provider':{'order':['groq'],'made_up':True},
        }
        target.write_text(yaml.safe_dump(doc,sort_keys=False))
        with _assert_raises(ValueError): pipeline_registry.load_yaml(target)

def test_legacy_non_self_models_remain_supported():
    with tempfile.TemporaryDirectory() as tmp:
        target=Path(tmp)/'legacy.yaml'
        doc=yaml.safe_load((HERE/'pipelines/lmstudio.yaml').read_text())
        aliases=doc.pop('model_aliases')
        roles=doc.pop('model_roles')
        model=aliases['default']
        doc['models']={role:{**row,'model':model} for role,row in roles.items()}
        target.write_text(yaml.safe_dump(doc,sort_keys=False))
        plan=pipeline_registry.load_yaml(target)
        assert pipeline_registry.binding(plan,'diagnosis').model=='qwen3-coder-next'

def test_model_client_adds_provider_routing_to_request_payload():
    class Response:
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def read(self): return b'{"choices":[{"message":{"content":"ok"},"finish_reason":"stop"}]}'
    captured={}
    def fake_urlopen(request,timeout):
        captured['payload']=json.loads(request.data.decode('utf-8'))
        captured['timeout']=timeout
        return Response()
    binding=pipeline_registry.binding(pipeline_registry.load('openrouter'),'structure')
    binding=type(binding)(**{**binding.__dict__,'provider_routing':{'order':['groq'],'allow_fallbacks':False}})
    with patch.object(model_client.urllib.request,'urlopen',fake_urlopen):
        completion=model_client.complete_messages(binding,[{'role':'user','content':'Hello'}])
    assert completion.content=='ok'
    assert captured['payload']['provider']=={'order':['groq'],'allow_fallbacks':False}

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
    with _assert_raises(ValueError): schema_validation.validate_second_diagnosis('diagnosis: null\nvariants: [v01]\nreason: null\n',valid_variants={'v01'})

def test_prognosis_flat_contract_requires_one_row_per_variant():
    text=("classification:\n  - variant: v01\n    bucket: favorable\n    reason: favorable\n"
          "  - variant: v02\n    bucket: adverse\n    reason: adverse\nprognostic_score: null\n")
    schema_validation.validate_prognosis(text,{'v01','v02'})


def test_prognosis_reports_missing_and_bad_bucket_together():
    text=("classification:\n  - variant: v01\n    bucket: nonsense\n    reason: x\nprognostic_score: null\n")
    with _assert_raises(ValidationFailure) as exc:
        schema_validation.validate_prognosis(text,{'v01','v02'})
    paths={i.path for i in exc.exception.issues}
    assert 'classification' in paths and 'classification[0].bucket' in paths


def test_prognosis_no_not_calculable():
    text=("classification:\n  - variant: v01\n    bucket: favorable\n    reason: favorable\n"
          "prognostic_score:\n  name: score\n  result: not calculable\n  reason: missing data\n")
    with _assert_raises(ValidationFailure): schema_validation.validate_prognosis(text,{'v01'})


def test_treatment_allows_multiple_rows_but_not_alongside_no_drug_implication():
    ok=("classification:\n  - variant: v01\n    bucket: drug_target\n    therapy: drug A\n    reason: target\n"
        "  - variant: v01\n    bucket: drug_sensitive\n    therapy: drug B\n    reason: sensitivity\n"
        "  - variant: v02\n    bucket: no_drug_implication\n    reason: none\n")
    schema_validation.validate_treatment(ok,{'v01','v02'})
    bad=("classification:\n  - variant: v01\n    bucket: drug_target\n    therapy: drug A\n    reason: target\n"
         "  - variant: v01\n    bucket: no_drug_implication\n    reason: none\n"
         "  - variant: v02\n    bucket: no_drug_implication\n    reason: none\n")
    with _assert_raises(ValidationFailure): schema_validation.validate_treatment(bad,{'v01','v02'})


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
    ctx=step._finite_membership_context(reg,[card],{'C1':'aaaaaaaaaaaa'})
    assert ctx['finite_gene_set_membership']['[card:aaaaaaaaaaaa]']=={'qualifying':['v01'],'not_qualifying':['v02']}

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



def test_ngs_panel_negatives_are_materialized_deterministically():
    scope = "# Genes assessed\n\n- `ASXL1`\n- `DNMT3A`\n- `TP53`\n"
    case = {
        'ngs_result_completeness': 'complete',
        'ngs_no_variants_detected': [],
        'variants': [{'gene': 'DNMT3A'}],
    }
    runtime.materialize_ngs_no_variants_detected(case, scope)
    assert case['ngs_no_variants_detected'] == ['ASXL1', 'TP53']


def test_incomplete_ngs_result_has_no_panel_wide_negatives():
    scope = "# Genes assessed\n\n- `ASXL1`\n- `DNMT3A`\n- `TP53`\n"
    case = {
        'ngs_result_completeness': 'incomplete',
        'ngs_no_variants_detected': ['ASXL1'],
        'variants': [{'gene': 'DNMT3A'}],
    }
    runtime.materialize_ngs_no_variants_detected(case, scope)
    assert case['ngs_no_variants_detected'] == []


def test_configured_ngs_panel_has_52_unique_genes():
    scope = (HERE.parents[1] / 'config' / 'ngs-panel-scope.md').read_text()
    genes = runtime.parse_ngs_panel_genes(scope)
    assert len(genes) == 52
    assert len(set(genes)) == 52
    assert 'TP53' in genes and 'NPM1' in genes

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
       'ngs_result_completeness':'complete',
       'ngs_no_variants_detected':['TP53'],
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
    assert doc['ngs_result_completeness']=='complete'
    assert doc['ngs_no_variants_detected']==['TP53']


def test_case_projection_rejects_unknown_field():
    with _assert_raises(ValueError): model_context.case_projection(_CASE,fields=('variants',))


def test_diagnosis_projection_drops_reason_but_keeps_relationship():
    doc=model_context.diagnosis_projection(_DX)
    assert doc['who5']=={'schema_disease':'MDS','diagnosis':'MDS with SF3B1','variants':['v01']}
    assert 'reason' not in doc['icc']
    assert doc['relationship']=='different'


def test_assert_canonical_detects_a_leak():
    ids=model_context.source_ids(_REG)
    assert ids==['V1','V2']
    model_context.assert_canonical('variants: [v01, v02]',source_ids=ids)
    with _assert_raises(AssertionError):
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
    with _assert_raises(ValidationFailure) as exc:
        schema_validation.validate_report_write('blocks:\n  - block_id: WRONG\n    text: ""\n',
                                                [{'block_id':'DX'}])
    assert len(exc.exception.issues)>=2


# --- Phase 2: fixtures and standalone stage checking -------------------------

FIXTURES=HERE/'tests'/'fixtures'
_FIXTURE_CASES=[(d.name,f) for d in sorted(FIXTURES.iterdir()) if d.is_dir()
                for f in sorted(d.iterdir()) if f.name.startswith('invalid_') and not f.name.endswith('.expected.txt')]


def test_every_registered_stage_has_a_fixture_directory():
    for stage in stage_checks.names():
        assert (FIXTURES/stage).is_dir(), f'stage {stage} has no fixtures'
        assert list((FIXTURES/stage).glob('valid.*')), f'stage {stage} has no valid fixture'


def test_invalid_fixture_produces_exactly_the_recorded_feedback():
    case=unittest.TestCase()
    for stage,path in _FIXTURE_CASES:
        with case.subTest(stage=stage,path=path.name):
            expected=path.with_suffix(path.suffix+'.expected.txt')
            assert expected.is_file(), f'{path.name} has no recorded feedback'
            with _assert_raises(ValidationFailure) as exc:
                stage_checks.check(stage,path.read_text(),stage_checks.fixture_context(stage))
            assert str(exc.exception)+'\n'==expected.read_text()


def test_valid_fixture_passes():
    case=unittest.TestCase()
    for stage in sorted(stage_checks.names()):
        for f in (FIXTURES/stage).glob('valid.*'):
            with case.subTest(stage=stage,path=f.name):
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

# --- Diagnosis retrieval and shared card rendering -----------------------------

def test_diagnosis_retrieval_is_cmc_or_gene():
    cards=[
        {'card_id':'CMC','category':'diagnosis','genes':['OTHER'],'diseases':['AML']},
        {'card_id':'GENE','category':'diagnosis','genes':['BCR'],'diseases':['unrelated disease']},
        {'card_id':'NOPE','category':'diagnosis','genes':['OTHER'],'diseases':['unrelated disease']},
    ]
    found=step._draw_diagnosis_cards(cards,['BCR'],['AML'])
    assert [c['card_id'] for c in found]==['CMC','GENE']


def test_diagnosis_authority_filter_is_preserved(monkeypatch):
    cards=[
        {'card_id':'WHO','publication_key':'who5'},
        {'card_id':'ICC','publication_key':'icc'},
    ]
    monkeypatch.setattr(step,'_diagnosis_authority_publications',lambda authority:{'who5'} if authority=='who5' else {'icc'})
    monkeypatch.setattr(step,'_diagnosis_authority_excluded_publications',lambda authority:set())
    assert [c['card_id'] for c in step._filter_diagnosis_authority(cards,'who5')]==['WHO']
    assert [c['card_id'] for c in step._filter_diagnosis_authority(cards,'icc')]==['ICC']


def test_diagnosis_authority_exclusion_takes_precedence(monkeypatch):
    cards=[
        {'card_id':'KEEP','publication_key':'keep'},
        {'card_id':'DROP','publication_key':'overlap'},
    ]
    monkeypatch.setattr(step,'_diagnosis_authority_publications',lambda authority:{'keep','overlap'})
    monkeypatch.setattr(step,'_diagnosis_authority_excluded_publications',lambda authority:{'overlap'})
    assert [c['card_id'] for c in step._filter_diagnosis_authority(cards,'who5')]==['KEEP']


def test_stage8_diagnosis_candidates_do_not_refilter_by_proposition_gene():
    cards=[
        _test_card('BCR-CARD',gene='BCR',category='diagnosis'),
        _test_card('ANKRD26-CARD',gene='ANKRD26',category='diagnosis'),
    ]
    el={'domain':'diagnosis','evidence_domain':'diagnosis_who5','variants':['v01']}
    reg={'v01':{'gene':'ANKRD26'}}
    assert [c['card_id'] for c in step._candidate_cards(el,{'diagnosis_who5':cards},reg)]==['BCR-CARD','ANKRD26-CARD']


def test_ptbg_candidates_keep_existing_proposition_gene_filter():
    cards=[
        _test_card('FLT3',gene='FLT3'),
        _test_card('NPM1',gene='NPM1'),
        _test_card('GENELESS',gene=None),
    ]
    el={'domain':'prognosis','evidence_domain':'prognosis','variants':['v01']}
    reg={'v01':{'gene':'FLT3'}}
    assert [c['card_id'] for c in step._candidate_cards(el,{'prognosis':cards},reg)]==['FLT3','GENELESS']


def test_compact_prompt_cards_group_metadata_and_use_only_12hex_tags():
    cards=[
        {'card_id':'LONG-CARD-1','category':'diagnosis','genes':['BCR','ABL1'],'diseases':['AML'],
         'evidence_tier':'guideline criterion','interpretation':'AML with BCR::ABL1 is defined here.',
         'paper_nickname':'WHO5 2022 Myeloid Classification'},
        {'card_id':'LONG-CARD-2','category':'diagnosis','genes':['NPM1'],'diseases':['AML'],
         'evidence_tier':'guideline criterion','interpretation':'AML with NPM1 is defined here.',
         'paper_nickname':'WHO5 2022 Myeloid Classification'},
    ]
    tags={'LONG-CARD-1':'111111111111','LONG-CARD-2':'222222222222'}
    text=rendering.render_prompt_cards(cards,tags,mode='compact')
    assert text.count('## WHO5 2022 Myeloid Classification')==1
    assert text.count('### diagnosis')==1
    assert text.count('#### AML')==1
    assert '[card:111111111111] AML with BCR::ABL1 is defined here. (evidence_tier: guideline criterion)' in text
    assert '[card:222222222222] AML with NPM1 is defined here. (evidence_tier: guideline criterion)' in text
    assert 'genes:' not in text and 'LONG-CARD-' not in text
    assert all(line.count('[card:')<=1 for line in text.splitlines())


def test_verbose_prompt_cards_use_tags_but_preserve_metadata():
    card={'card_id':'LONG-CARD','category':'diagnosis','genes':['BCR'],'diseases':['AML'],
          'evidence_tier':'guideline criterion','interpretation':'Interpretation.',
          'paper_nickname':'WHO5'}
    text=rendering.render_prompt_cards([card],{'LONG-CARD':'abcdef123456'},mode='verbose')
    assert '### [card:abcdef123456]' in text
    assert 'genes: BCR' in text
    assert 'source_hint: WHO5' in text
    assert 'LONG-CARD' not in text


def test_runtime_card_tags_are_unique_12hex_and_resolve_to_canonical_ids():
    cards=[{'card_id':'A'},{'card_id':'B'},{'card_id':'C'}]
    manifest=card_identity.build_manifest(cards)
    tags=card_identity.tag_by_id(manifest)
    assert set(tags)=={'A','B','C'}
    assert len(set(tags.values()))==3
    assert all(len(tag)==12 and all(ch in '0123456789abcdef' for ch in tag) for tag in tags.values())
    reverse={tag:cid for cid,tag in tags.items()}
    assert all(reverse[tag]==cid for cid,tag in tags.items())


def test_card_render_setting_accepts_compact_and_verbose(monkeypatch):
    monkeypatch.setattr(step,'load_settings',lambda:{'rendering':{'cards':'compact'}})
    assert step._card_render_mode()=='compact'
    monkeypatch.setattr(step,'load_settings',lambda:{'rendering':{'cards':'verbose'}})
    assert step._card_render_mode()=='verbose'
    monkeypatch.setattr(step,'load_settings',lambda:{})
    assert step._card_render_mode()=='compact'
    monkeypatch.setattr(step,'load_settings',lambda:{'rendering':{'cards':'yaml'}})
    with _assert_raises(step.StepFailure): step._card_render_mode()


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


def test_evidence_match_allows_zero_or_multiple_cards_per_reason():
    items=[{'evidence_id':'E0001','candidate_card_tags':['[card:aaaaaaaaaaa1]','[card:aaaaaaaaaaa2]']}]
    schema_validation.validate_evidence_match_batch(
        'matches:\n  - evidence_id: E0001\n    card_tags: []\n', items
    )
    schema_validation.validate_evidence_match_batch(
        'matches:\n  - evidence_id: E0001\n    card_tags: ["[card:aaaaaaaaaaa1]", "[card:aaaaaaaaaaa2]"]\n', items
    )
    with _assert_raises(ValidationFailure):
        schema_validation.validate_evidence_match_batch(
            'matches:\n  - evidence_id: E0001\n    card_tags: ["[card:aaaaaaaaaaa9]"]\n', items
        )


def test_proforma_card_assignment_is_silently_stripped_before_validation(tmp_path):
    raw=('classification:\n  - variant: v01\n    bucket: adverse\n'
         '    reason: "FLT3 confers adverse prognosis. [card:aaaaaaaaaaa1]"\n'
         '    card_tags: ["[card:aaaaaaaaaaa1]"]\nprognostic_score: null\n')
    cleaned=step._sanitize_proforma_text(tmp_path,'prognosis',raw)
    doc=yaml.safe_load(cleaned)
    assert 'card_tags' not in doc['classification'][0]
    assert doc['classification'][0]['reason']=='FLT3 confers adverse prognosis.'
    schema_validation.validate_prognosis(cleaned,{'v01'})
    transforms=yaml.safe_load(step._transform_log_path(tmp_path).read_text())['transforms']
    assert {x['transform'] for x in transforms}=={'strip_proforma_card_assignment','strip_runtime_card_tag_from_reason'}


def test_semantic_retry_carries_all_prior_audit_feedback_and_resolves_dissent(tmp_path,monkeypatch):
    cards=[_test_card('C1'),_test_card('C2'),_test_card('C3')]
    el={'schema_id':'PX-ADVERSE-01','domain':'prognosis','bucket':'adverse',
        'statement':'FLT3-ITD confers adverse prognosis in AML.',
        'reason':'FLT3-ITD confers adverse prognosis in AML.','variants':['v01'],
        'evidence_domain':'prognosis','required':False,'source':{'variants':['v01']}}
    reg={'v01':{'gene':'FLT3'}}
    script={
        'evidence-match-batch-01':'matches:\n  - evidence_id: E0001\n    card_tags: ["[card:aaaaaaaaaaa1]"]\n',
        'evidence-audit-batch-01':'audits:\n  - evidence_id: E0001\n    card_audits:\n      - card_tag: "[card:aaaaaaaaaaa1]"\n        card_is_element_of_reason: false\n        risk: none\n        comments: ["wrong disease context"]\n',
        'evidence-match-batch-02':'matches:\n  - evidence_id: E0001\n    card_tags: ["[card:aaaaaaaaaaa2]"]\n',
        'evidence-audit-batch-02':'audits:\n  - evidence_id: E0001\n    card_audits:\n      - card_tag: "[card:aaaaaaaaaaa2]"\n        card_is_element_of_reason: false\n        risk: none\n        comments: ["wrong clinical function"]\n',
        'evidence-match-batch-03':'matches:\n  - evidence_id: E0001\n    card_tags: ["[card:aaaaaaaaaaa3]"]\n',
        'evidence-audit-batch-03':'audits:\n  - evidence_id: E0001\n    card_audits:\n      - card_tag: "[card:aaaaaaaaaaa3]"\n        card_is_element_of_reason: true\n        risk: none\n        comments: []\n',
    }
    def check2(prompt):
        assert "rejected_card_tag: '[card:aaaaaaaaaaa1]'" in prompt
        assert 'wrong disease context' in prompt
        assert "candidate_card_tags:\n  - '[card:aaaaaaaaaaa2]'\n  - '[card:aaaaaaaaaaa3]'" in prompt
        evidence_input=prompt.split('# Evidence items',1)[1].split('# Candidate card catalog',1)[0]
        assert 'statement:' not in evidence_input
    def check3(prompt):
        assert "rejected_card_tag: '[card:aaaaaaaaaaa1]'" in prompt and "rejected_card_tag: '[card:aaaaaaaaaaa2]'" in prompt
        assert 'wrong disease context' in prompt and 'wrong clinical function' in prompt
        assert "candidate_card_tags:\n  - '[card:aaaaaaaaaaa3]'" in prompt
    monkeypatch.setattr(step,'_model_call',_scripted_model_call(script,{
        'evidence-match-batch-02':check2,'evidence-match-batch-03':check3}))
    monkeypatch.setattr(step,'_retry',lambda name: 3 if name=='evidence_resolution_attempts' else 2)
    monkeypatch.setattr(step.card_identity,'tag_by_id',lambda manifest:{'C1':'aaaaaaaaaaa1','C2':'aaaaaaaaaaa2','C3':'aaaaaaaaaaa3'})
    out=step.stage_evidence(tmp_path,[el],{'prognosis':cards},reg,{},None)
    assert len(out)==1 and out[0]['evidence'][0]['card_id']=='C3'
    assert out[0]['evidence'][0]['semantic_attempt']==3
    issue=step._semantic_dissent_issue(tmp_path,'evidence:PX-ADVERSE-01')
    assert issue['status']=='resolved'
    raised=[h for h in issue['history'] if h['event']=='raised']
    assert [h['stage'] for h in raised]==['evidence audit attempt 1','evidence audit attempt 2']
    dissent=(tmp_path/'dissent.md').read_text()
    assert 'wrong disease context' in dissent and 'wrong clinical function' in dissent


def test_multiple_cards_for_one_reason_are_audited_independently(tmp_path,monkeypatch):
    cards=[_test_card('C1'),_test_card('C2')]
    el={'schema_id':'PX-ADVERSE-01','domain':'prognosis','bucket':'adverse','statement':'claim','reason':'A and B.',
        'variants':['v01'],'evidence_domain':'prognosis','required':False,'source':{'variants':['v01'],'reason':'A and B.'}}
    reg={'v01':{'gene':'FLT3'}}
    script={
        'evidence-match-batch-01':'matches:\n  - evidence_id: E0001\n    card_tags: ["[card:aaaaaaaaaaa1]", "[card:aaaaaaaaaaa2]"]\n',
        'evidence-audit-batch-01':'audits:\n  - evidence_id: E0001\n    card_audits:\n      - card_tag: "[card:aaaaaaaaaaa1]"\n        card_is_element_of_reason: true\n        risk: none\n        comments: []\n      - card_tag: "[card:aaaaaaaaaaa2]"\n        card_is_element_of_reason: false\n        risk: none\n        comments: ["only topically related"]\n',
    }
    monkeypatch.setattr(step,'_model_call',_scripted_model_call(script))
    monkeypatch.setattr(step,'_retry',lambda name: 3 if name=='evidence_resolution_attempts' else 2)
    monkeypatch.setattr(step.card_identity,'tag_by_id',lambda manifest:{'C1':'aaaaaaaaaaa1','C2':'aaaaaaaaaaa2'})
    out=step.stage_evidence(tmp_path,[el],{'prognosis':cards},reg,{},None)
    assert [x['card_id'] for x in out[0]['evidence']]==['C1']
    blocks=step.stage_blocks(tmp_path,{},out,reg)
    assert blocks[0]['components'][0]['card_tags']==['[card:aaaaaaaaaaa1]']
    issue=step._semantic_dissent_issue(tmp_path,'evidence:PX-ADVERSE-01')
    assert issue['status']=='resolved'


def test_multiple_passing_cards_propagate_to_report_block(tmp_path,monkeypatch):
    cards=[_test_card('C1'),_test_card('C2')]
    el={'schema_id':'PX-ADVERSE-01','domain':'prognosis','bucket':'adverse','statement':'claim','reason':'A and B.',
        'variants':['v01'],'evidence_domain':'prognosis','required':False,'source':{'variants':['v01'],'reason':'A and B.'}}
    reg={'v01':{'gene':'FLT3'}}
    script={
        'evidence-match-batch-01':'matches:\n  - evidence_id: E0001\n    card_tags: ["[card:aaaaaaaaaaa1]", "[card:aaaaaaaaaaa2]"]\n',
        'evidence-audit-batch-01':'audits:\n  - evidence_id: E0001\n    card_audits:\n      - card_tag: "[card:aaaaaaaaaaa1]"\n        card_is_element_of_reason: true\n        risk: none\n        comments: []\n      - card_tag: "[card:aaaaaaaaaaa2]"\n        card_is_element_of_reason: true\n        risk: none\n        comments: []\n',
    }
    monkeypatch.setattr(step,'_model_call',_scripted_model_call(script))
    monkeypatch.setattr(step.card_identity,'tag_by_id',lambda manifest:{'C1':'aaaaaaaaaaa1','C2':'aaaaaaaaaaa2'})
    out=step.stage_evidence(tmp_path,[el],{'prognosis':cards},reg,{},None)
    assert [x['card_id'] for x in out[0]['evidence']]==['C1','C2']
    blocks=step.stage_blocks(tmp_path,{},out,reg)
    assert blocks[0]['components'][0]['card_tags']==['[card:aaaaaaaaaaa1]','[card:aaaaaaaaaaa2]']


def test_ptbg_semantic_exhaustion_suppresses_statement_but_keeps_failed_audits(tmp_path,monkeypatch):
    cards=[_test_card('C1'),_test_card('C2')]
    el={'schema_id':'PX-ADVERSE-01','domain':'prognosis','bucket':'adverse','statement':'claim','reason':'reason',
        'variants':['v01'],'evidence_domain':'prognosis','required':False,'source':{'variants':['v01']}}
    reg={'v01':{'gene':'FLT3'}}
    script={
        'evidence-match-batch-01':'matches:\n  - evidence_id: E0001\n    card_tags: ["[card:aaaaaaaaaaa1]"]\n',
        'evidence-audit-batch-01':'audits:\n  - evidence_id: E0001\n    card_audits:\n      - card_tag: "[card:aaaaaaaaaaa1]"\n        card_is_element_of_reason: false\n        risk: none\n        comments: ["first mismatch"]\n',
        'evidence-match-batch-02':'matches:\n  - evidence_id: E0001\n    card_tags: ["[card:aaaaaaaaaaa2]"]\n',
        'evidence-audit-batch-02':'audits:\n  - evidence_id: E0001\n    card_audits:\n      - card_tag: "[card:aaaaaaaaaaa2]"\n        card_is_element_of_reason: false\n        risk: none\n        comments: ["second mismatch"]\n',
    }
    monkeypatch.setattr(step,'_model_call',_scripted_model_call(script))
    monkeypatch.setattr(step,'_retry',lambda name: 2)
    monkeypatch.setattr(step.card_identity,'tag_by_id',lambda manifest:{'C1':'aaaaaaaaaaa1','C2':'aaaaaaaaaaa2'})
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
        'evidence-match-batch-01':'matches:\n  - evidence_id: E0001\n    card_tags: ["[card:ddddddddddd1]"]\n',
        'evidence-audit-batch-01':'audits:\n  - evidence_id: E0001\n    card_audits:\n      - card_tag: "[card:ddddddddddd1]"\n        card_is_element_of_reason: false\n        risk: none\n        comments: ["does not support subtype X"]\n',
    }
    monkeypatch.setattr(step,'_model_call',_scripted_model_call(script))
    monkeypatch.setattr(step,'_retry',lambda name: 3 if name=='evidence_resolution_attempts' else 2)
    monkeypatch.setattr(step.card_identity,'tag_by_id',lambda manifest:{'D1':'ddddddddddd1'})
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
    items=[{'evidence_id':'E0001','selected_card_tags':['[card:aaaaaaaaaaa1]']}]
    bad='''audits:
  - evidence_id: E0001
    card_audits:
      - card_tag: "[card:aaaaaaaaaaa1]"
        card_is_element_of_reason: false
        risk: none
        comments: []
'''
    with _assert_raises(ValidationFailure) as exc:
        schema_validation.validate_evidence_audit_batch(bad,items)
    assert 'without explanatory feedback' in str(exc.exception)


def test_staged_setup_parser_supports_explicit_work_dir():
    parser = step.build_parser()
    args = parser.parse_args(['setup', '--mode', 'ngs-report', '--work-dir', '/tmp/x'])
    assert args.work_dir == Path('/tmp/x')


def test_staged_run_setup_passes_explicit_work_dir_to_shared_setup(tmp_path, monkeypatch):
    import contextlib
    from types import SimpleNamespace

    case_file = tmp_path / 'case-source.md'
    case_file.write_text('case\n', encoding='utf-8')
    work = tmp_path / 'resolved-work'
    work.mkdir()
    captured = {}

    def fake_setup_workflow(**kwargs):
        captured.update(kwargs)
        return work

    monkeypatch.setattr(step, 'setup_workflow', fake_setup_workflow)
    monkeypatch.setattr(step, 'write_workflow_state', lambda *a, **k: None)
    monkeypatch.setattr(step, '_save_run_state', lambda *a, **k: None)
    monkeypatch.setattr(step, '_cli_logging', lambda *a, **k: contextlib.nullcontext())
    args = SimpleNamespace(
        pipeline='self', mode='ngs-report', case_file=case_file, example=None,
        case_id=None, work_dir=work,
    )
    assert step.run_setup(args) == step.EXIT_OK
    assert captured['work_dir'] == work
    assert captured['project'] is False


def _run_function_test(function):
    """Supply the temporary-path and patch fixtures using only the stdlib."""
    parameters=inspect.signature(function).parameters
    with ExitStack() as stack:
        kwargs={}
        if 'tmp_path' in parameters:
            kwargs['tmp_path']=Path(stack.enter_context(tempfile.TemporaryDirectory()))
        if 'monkeypatch' in parameters:
            kwargs['monkeypatch']=_MonkeyPatch(stack)
        function(**kwargs)


def load_tests(loader, tests, pattern):
    """Expose all workflow test functions to standard-library unittest."""
    suite=unittest.TestSuite()
    for name,value in sorted(globals().items()):
        if name.startswith('test_') and callable(value):
            suite.addTest(unittest.FunctionTestCase(
                lambda function=value: _run_function_test(function),
                description=name,
            ))
    return suite


if __name__ == '__main__':
    unittest.main()
