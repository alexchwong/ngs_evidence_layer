from pathlib import Path
from scripts.core import validated_model_task
from workflows.terraced_v3 import runtime


def test_safe_representation_repair_removes_fence():
    text, repairs = validated_model_task.safe_representation_repair("```yaml\na: 1  \n```\n")
    assert text == "a: 1\n"
    assert repairs


def test_who5_multiple_diagnoses_derive_multiple_primary_cmcs():
    doc = {
        "diagnoses": [
            {"diagnosis_id": "DX1", "schema_disease": "MDS", "status": "established", "diagnosis": "MDS", "fact": "x.", "reason": "x", "candidate_card_tags": []},
            {"diagnosis_id": "DX2", "schema_disease": "CLL/SLL", "status": "established", "diagnosis": "CLL/SLL", "fact": "y.", "reason": "y", "candidate_card_tags": []},
        ],
        "supporting_facts": [],
        "contradicting_facts": [],
    }
    assert runtime.derive_cmcs(doc) == ["MDS", "mature B-cell neoplasm"]


def test_prognosis_validator_requires_variant_diagnosis_cartesian_scope():
    text = """decisions:
  - variant_id: V1
    diagnosis_id: DX1
    effect: neither
    scoring_system: null
    surface: false
    fact: null
    reason: null
    candidate_card_tags: []
  - variant_id: V1
    diagnosis_id: DX2
    effect: adverse
    scoring_system: CLL-IPI
    surface: true
    fact: "Variant V1 is adverse in this disease context."
    reason: "The supplied evidence classifies it as adverse."
    candidate_card_tags: []
"""
    spec = {"required_pairs": [("V1", "DX1"), ("V1", "DX2")]}
    assert runtime.validate_domain_text(text, domain="prognosis", spec=spec, permitted_tags=set())


def test_alignment_enforces_diagnosis_scoped_permitted_tags():
    facts = [{"fact_id": "f1", "domain": "prognosis", "subject": {"diagnosis_ids": ["DX1"]}}]
    bad = "alignments:\n  - fact_id: f1\n    citation: \"[card:aaaaaaaaaaaa]\"\n"
    try:
        runtime.validate_evidence_alignment_text(bad, facts, {"f1": {"bbbbbbbbbbbb"}})
    except ValueError as exc:
        assert "not permitted for this fact scope" in str(exc)
    else:
        raise AssertionError("expected scoped citation validation failure")


def test_yaml_parser_failure_is_actionable():
    try:
        runtime.parse_yaml_mapping("decisions: [\n", "prognosis")
    except validated_model_task.ValidationFailure as exc:
        retry = validated_model_task.retry_instruction(exc)
        assert "parser error" in retry
        assert "line" in retry
        assert "complete syntactically valid YAML mapping" in retry
        assert "Return the complete artifact again" in retry
    else:
        raise AssertionError("expected structured parser validation failure")


def test_domain_scheduler_scopes_treatment_across_concurrent_diagnoses():
    from workflows.terraced_v3 import scheduler_primitives

    case = {
        "variants": [
            {"variant_id": "V1", "gene": "SF3B1", "description": "x"},
            {"variant_id": "V2", "gene": "TP53", "description": "y"},
        ]
    }
    diagnoses = [
        {"diagnosis_id": "DX1", "schema_disease": "MDS"},
        {"diagnosis_id": "DX2", "schema_disease": "CLL/SLL"},
    ]
    specs = scheduler_primitives.task_specs(case, diagnoses)
    assert specs["treatment"]["required_pairs"] == [
        ("SF3B1", "DX1"), ("SF3B1", "DX2"),
        ("TP53", "DX1"), ("TP53", "DX2"),
    ]


def test_phase_scheduler_registries_have_invariant_sets():
    from workflows.terraced_v3 import scheduler_registry

    assert scheduler_registry.names("diagnosis") == ("default-diagnosis", "minimal-diagnosis")
    assert scheduler_registry.names("ptbg") == (
        "domain", "evidence-first", "variant-centric", "global-ledger", "adaptive-microtask",
    )
    assert scheduler_registry.names("summarization") == ("default-summarization", "minimal-summarization")
    for phase in scheduler_registry.PHASES:
        for name in scheduler_registry.names(phase):
            plan = scheduler_registry.load(name, phase)
            assert plan.scheduler_id == name
            assert plan.phase == phase
            assert plan.path.name == "scheduler.yaml"


def test_structured_case_requires_source_faithful_variant_summary_tokens():
    import json

    case = {
        "provisional_disease": "MDS-IB2",
        "bootstrap_cmcs": ["MDS"],
        "variants": [
            {
                "variant_id": "V1",
                "gene": "NPM1",
                "description": "NM_002520.7:c.860_863dup, p.(Trp288CysfsTer12), VAF 38%",
            },
            {
                "variant_id": "V2",
                "gene": "FLT3",
                "description": "NM_004119.3:c.2503G>T, p.(Asp835Tyr), VAF 24%",
            },
        ],
        "detected_variants_summary": "NGS detected NPM1 NM_002520.7:c.860_863dup, p.(Trp288CysfsTer12), VAF 38% and FLT3 NM_004119.3:c.2503G>T, p.(Asp835Tyr), VAF 24%.",
        "case_facts": [{"fact_id": "C1", "kind": "blasts", "value": "Marrow blasts are 12%."}],
    }
    assert runtime.validate_case_text(json.dumps(case)) == "structured case validated"
    case["detected_variants_summary"] = "NGS detected NPM1 and FLT3."
    try:
        runtime.validate_case_text(json.dumps(case))
    except ValueError as exc:
        assert "does not preserve supplied coding HGVS" in str(exc)
        assert "does not preserve supplied VAF" in str(exc)
    else:
        raise AssertionError("expected invariant variant summary validation failure")


def test_adaptive_scheduler_only_escalates_high_impact_cells():
    from workflows.terraced_v3 import scheduler_primitives

    prognosis = {"decisions": [
        {"variant_id": "V1", "diagnosis_id": "DX1", "effect": "neither"},
        {"variant_id": "V2", "diagnosis_id": "DX1", "effect": "adverse"},
    ]}
    cells = scheduler_primitives.high_impact_cells({"prognosis": prognosis})
    assert [(cell["domain"], cell["key"]) for cell in cells] == [("prognosis", "V2|DX1")]


def test_generic_yaml_syntax_repair_preserves_content_and_fixes_quote():
    from scripts.core import syntax_repair

    broken = 'diagnosis: "AML with NPM1 mutation\nreason: supplied evidence\n'
    calls = []

    def repair(prompt, attempt):
        calls.append((attempt, prompt))
        return 'diagnosis: "AML with NPM1 mutation"\nreason: supplied evidence\n'

    result = syntax_repair.repair_structured_output(
        broken,
        format_name="yaml",
        model_repair=repair,
        model_attempts=2,
    )
    assert result.text == 'diagnosis: "AML with NPM1 mutation"\nreason: supplied evidence\n'
    assert len(result.model_attempts) == 1
    assert "Do not add, remove, correct, reinterpret" in calls[0][1]
    assert "AML with NPM1 mutation" in calls[0][1]


def test_generic_json_syntax_repair_supports_missing_comma():
    from scripts.core import syntax_repair

    broken = '{"gene":"NPM1" "vaf":"38%"}'

    def repair(prompt, attempt):
        assert attempt == 1
        assert "Repair JSON syntax only" in prompt
        return '{"gene":"NPM1", "vaf":"38%"}'

    result = syntax_repair.repair_structured_output(
        broken,
        format_name="json",
        model_repair=repair,
    )
    assert result.format_name == "json"
    assert '"vaf":"38%"' in result.text


def test_generic_syntax_repair_rejects_factual_change_then_accepts_second_attempt():
    from scripts.core import syntax_repair

    broken = 'gene: NPM1\nvaf: "38%\n'

    def repair(prompt, attempt):
        if attempt == 1:
            return 'gene: NPM1\nvaf: "34%"\n'
        assert "changed content and was rejected" in prompt
        return 'gene: NPM1\nvaf: "38%"\n'

    result = syntax_repair.repair_structured_output(
        broken,
        format_name="yaml",
        model_repair=repair,
        model_attempts=2,
    )
    assert len(result.model_attempts) == 2
    assert result.model_attempts[0].preservation_error
    assert '38%' in result.text
    assert '34%' not in result.text


def test_generic_syntax_repair_exhausts_after_two_model_attempts():
    from scripts.core import syntax_repair

    broken = 'a: "unterminated\n'

    def repair(prompt, attempt):
        return 'a: "still unterminated\n'

    try:
        syntax_repair.repair_structured_output(
            broken,
            format_name="yaml",
            model_repair=repair,
            model_attempts=2,
        )
    except syntax_repair.SyntaxRepairExhausted as exc:
        assert len(exc.attempts) == 2
        assert "YAML syntax repair exhausted" in str(exc)
    else:
        raise AssertionError("expected syntax repair exhaustion")


def test_generic_yaml_deterministically_quotes_colon_in_plain_text_scalar():
    from scripts.core import syntax_repair
    import yaml

    broken = (
        "supporting_facts:\n"
        "  - diagnosis_ids: [DX1]\n"
        "    fact: Bone marrow morphology shows 30% myeloid blasts.\n"
        "    reason: Case fact C2: 30% myeloid blasts.\n"
        "    candidate_card_tags: []\n"
    )
    result = syntax_repair.repair_structured_output(
        broken,
        format_name="yaml",
        model_attempts=0,
    )
    parsed = yaml.safe_load(result.text)
    assert parsed["supporting_facts"][0]["reason"] == "Case fact C2: 30% myeloid blasts."
    assert any("quoted YAML plain scalar" in repair for repair in result.deterministic_repairs)


def test_retry_stagnation_guard_detects_three_identical_invalid_artifacts():
    from scripts.core.validated_model_task import RetryStagnationGuard

    guard = RetryStagnationGuard()
    assert guard.observe("same\n", "same error") == 0
    assert guard.observe("same\n", "same error") == 1
    assert guard.observe("same\n", "same error") == 2
    assert guard.observe("changed\n", "same error") == 0


def test_run_layout_keeps_true_case_at_root_and_numbers_generated_namespaces(tmp_path):
    from workflows.terraced_v3 import layout

    layout.ensure_dirs(tmp_path)
    assert layout.input(tmp_path, "case.md", existing=False) == tmp_path / "case.md"

    setup_path = layout.setup(tmp_path, "ngs-panel-scope.md", existing=False)
    run_state = layout.state(tmp_path, "terraced-v3-run.json", existing=False)
    case_json = layout.input(tmp_path, "case.json", existing=False)
    assert setup_path == tmp_path / "intermediates" / "001_setup" / "ngs-panel-scope.md"
    assert run_state == tmp_path / "intermediates" / "002_run_state" / "terraced-v3-run.json"
    assert case_json == tmp_path / "intermediates" / "003_structured_case" / "case.json"

    first = layout.model_step_dir(tmp_path, "structure-case", existing=False)
    second = layout.model_step_dir(tmp_path, "icc-independent", existing=False)
    resumed = layout.model_step_dir(tmp_path, "structure-case", existing=False)
    assert first.name == "001_structure_case"
    assert second.name == "002_icc_independent"
    assert resumed == first


def test_layout_read_does_not_allocate_numbered_directory(tmp_path):
    from workflows.terraced_v3 import layout

    layout.ensure_dirs(tmp_path)
    missing = layout.domain(tmp_path, "prognosis", "FINAL_STATE.yaml")
    assert not missing.exists()
    assert list((tmp_path / "intermediates").iterdir()) == []

    created = layout.evidence(tmp_path, "prognosis-bundle.json", existing=False)
    assert created.parent.name == "001_prognosis_evidence"


def test_scheduler_yaml_prompt_slots_compile_for_all_phases():
    from workflows.terraced_v3 import scheduler_registry
    for phase in scheduler_registry.PHASES:
        for name in scheduler_registry.names(phase):
            assert scheduler_registry.check(name, phase).scheduler_id == name


def test_scheduler_directories_are_declarative_not_python():
    from workflows.terraced_v3 import scheduler_registry
    for phase in scheduler_registry.PHASES:
        for name in scheduler_registry.names(phase):
            folder = scheduler_registry.load(name, phase).path.parent
            assert (folder / "scheduler.yaml").is_file()
            assert not list(folder.glob("*.py"))


def test_scheduler_prompt_injection_rejects_undeclared_slot(tmp_path):
    from workflows.terraced_v3 import scheduler_engine
    (tmp_path / "prompt.md").write_text("{{missing}}\n", encoding="utf-8")
    (tmp_path / "scheduler.yaml").write_text(
        """scheduler:
  id: broken
  phase: ptbg
  version: 1
  description: broken
steps:
  - id: x
    kind: model
    inputs: {}
    prompt:
      template: prompt.md
      inject: {}
    output:
      format: yaml
      validator: global_ledger
outputs:
  prognosis: steps.x.prognosis
  treatment: steps.x.treatment
  biomarker: steps.x.biomarker
  germline: steps.x.germline
""", encoding="utf-8")
    try:
        scheduler_engine.load_yaml(tmp_path / "scheduler.yaml")
    except ValueError as exc:
        assert "prompt slots mismatch" in str(exc)
    else:
        raise AssertionError("expected scheduler compile failure")


def test_card_tag_syntax_normalizer_accepts_bare_hash_lists_and_canonicalizes():
    import yaml

    text = '''decisions:
  - candidate_card_tags: [abcdefabcdef]
  - candidate_card_tags: ["abcdefabcdef"]
  - target_candidate_card_tags: [abcdefabcdef, "1234567890ab"]
  - resistance_candidate_card_tags: [card:abcdefabcdef]
evidence_items:
  - card_tag: 1234567890ab
'''
    repaired, repairs = runtime.normalize_model_card_tag_syntax(text, format_name="yaml")
    doc = yaml.safe_load(repaired)
    assert doc["decisions"][0]["candidate_card_tags"] == ["[card:abcdefabcdef]"]
    assert doc["decisions"][1]["candidate_card_tags"] == ["[card:abcdefabcdef]"]
    assert doc["decisions"][2]["target_candidate_card_tags"] == ["[card:abcdefabcdef]", "[card:1234567890ab]"]
    assert doc["decisions"][3]["resistance_candidate_card_tags"] == ["[card:abcdefabcdef]"]
    assert doc["evidence_items"][0]["card_tag"] == "[card:1234567890ab]"
    assert len(repairs) == 6


def test_bare_card_hash_is_only_accepted_when_exactly_supplied_after_normalization():
    text = '''decisions:
  - variant_id: V1
    diagnosis_id: DX1
    effect: adverse
    scoring_system: ELN 2022
    surface: true
    fact: "Variant V1 is adverse in this disease context."
    reason: "The supplied evidence supports this conclusion."
    candidate_card_tags: [abcdefabcdef]
'''
    repaired, repairs = runtime.normalize_model_card_tag_syntax(text, format_name="yaml")
    assert repairs
    spec = {"required_pairs": [("V1", "DX1")]}
    assert runtime.validate_domain_text(repaired, domain="prognosis", spec=spec, permitted_tags={"abcdefabcdef"})
    try:
        runtime.validate_domain_text(repaired, domain="prognosis", spec=spec, permitted_tags={"1234567890ab"})
    except ValueError as exc:
        assert "was not supplied to this task" in str(exc)
    else:
        raise AssertionError("expected undrawn bare hash to remain invalid after syntax normalization")



def test_pipeline_registry_ships_three_defaults_and_resolves_roles():
    from workflows.terraced_v3 import pipeline_registry, scheduler_registry
    assert pipeline_registry.names() == ("self", "lmstudio", "openrouter")
    for name in pipeline_registry.names():
        plan = pipeline_registry.load(name)
        assert set(plan.schedulers) == {"diagnosis", "ptbg", "summarization"}
        for phase, scheduler in plan.schedulers.items():
            assert scheduler in scheduler_registry.names(phase)
        for role in pipeline_registry.ROLES:
            binding = pipeline_registry.binding(plan, role)
            assert binding.max_tokens > 0
            assert binding.role == role


def test_canonical_summary_requires_card_tags_derived_from_fact_citations():
    facts = [{
        "fact_id": "prognosis-V1-DX1", "domain": "prognosis", "fact": "x", "reason": "y",
        "citation": "[card:abcdefabcdef]", "subject": {}, "decision": {}, "candidate_card_tags": [],
    }]
    good = {"sentences": [{
        "sentence_id": "prognosis-1", "domain": "prognosis", "sentence": "This is favorable.",
        "fact_ids": ["prognosis-V1-DX1"], "card_tags": ["[card:abcdefabcdef]"],
    }]}
    assert runtime.validate_canonical_summary_doc(good, facts)
    bad = {"sentences": [dict(good["sentences"][0], card_tags=[])]}
    try:
        runtime.validate_canonical_summary_doc(bad, facts)
    except ValueError as exc:
        assert "card_tags are deterministic" in str(exc)
    else:
        raise AssertionError("expected canonical summary tag mismatch")


def test_sentence_card_interpretations_are_created_deterministically():
    summary = {"sentences": [{
        "sentence_id": "treatment-1", "domain": "treatment", "sentence": "FLT3 is targetable.",
        "fact_ids": ["f1"], "card_tags": ["[card:abcdefabcdef]"],
    }]}
    paired = runtime.sentence_card_interpretations(summary, {"[card:abcdefabcdef]": "FLT3 alterations can be therapeutically targeted in AML."})
    assert paired["sentences"][0]["cards"] == [{
        "card_tag": "[card:abcdefabcdef]",
        "interpretation": "FLT3 alterations can be therapeutically targeted in AML.",
    }]


def test_pipeline_setup_persists_three_scheduler_overrides(tmp_path):
    from workflows.terraced_v3 import pipeline_registry, scheduler_registry
    plan = pipeline_registry.load("self")
    schedulers = dict(plan.schedulers)
    schedulers.update({"diagnosis": "minimal-diagnosis", "ptbg": "evidence-first", "summarization": "minimal-summarization"})
    assert schedulers["diagnosis"] in scheduler_registry.names("diagnosis")
    assert schedulers["ptbg"] in scheduler_registry.names("ptbg")
    assert schedulers["summarization"] in scheduler_registry.names("summarization")


def test_core_contract_reference_resolves_mechanically():
    from workflows.terraced_v3 import contract_registry

    contract = contract_registry.load("core.case.structured")
    expected = Path(__file__).resolve().parents[1] / "contracts" / "core" / "case" / "structured.md"
    assert contract.path == expected
    assert contract.semantic_type == "case.structured"
    assert "```json" in contract.body


def test_all_default_pipeline_dags_validate_and_compile_contract_edges():
    from workflows.terraced_v3 import pipeline_registry

    for name in ("self", "lmstudio", "openrouter"):
        plan = pipeline_registry.load(name)
        assert pipeline_registry.validate(plan) is plan
        compiled = pipeline_registry.compiled_markdown(plan)
        assert "compatibility: PASS" in compiled
        assert "contracts/core/case/structured.md" in compiled
        assert "scheduler.diagnosis.default-diagnosis" in compiled
        assert "scheduler.ptbg.domain" in compiled
        assert "scheduler.summarization.default-summarization" in compiled


def test_pipeline_contract_mismatch_fails_before_execution_with_adapter_guidance(tmp_path):
    import copy
    import yaml
    from workflows.terraced_v3 import pipeline_registry

    source = pipeline_registry.load("self")
    doc = copy.deepcopy(source.doc)
    finalise = next(row for row in doc["modules"] if row["id"] == "finalise")
    # Feed cited facts where a report summary is required.  Both artifacts exist,
    # but their semantic types/contracts are intentionally incompatible.
    finalise["inputs"]["summary"] = "evidence.cited_facts"
    path = tmp_path / "bad-pipeline.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    try:
        pipeline_registry.load_yaml(path)
    except ValueError as exc:
        message = str(exc)
        assert "pipeline contract mismatch" in message
        assert "semantic type mismatch" in message
        assert "explicit adapter module" in message
        assert "Source evidence.cited_facts" in message
        assert "expected contract" in message
    else:
        raise AssertionError("expected setup-time contract incompatibility")


def test_scheduler_interface_output_names_are_scheduler_local(tmp_path):
    from workflows.terraced_v3 import scheduler_engine

    contracts = tmp_path / "contracts"
    contracts.mkdir()
    (contracts / "result.md").write_text(
        """---\nid: local.weird-result\nsemantic_type: ptbg.experimental\nformat: yaml\nprovides: [payload]\nrequires: []\n---\n# Experimental result\n\n```yaml\npayload: {}\n```\n""",
        encoding="utf-8",
    )
    (tmp_path / "prompt.md").write_text("Return the requested YAML.\n", encoding="utf-8")
    (tmp_path / "scheduler.yaml").write_text(
        """scheduler:\n  id: custom-output-name\n  phase: ptbg\n  version: 1\n  description: Demonstrate scheduler-local interface names.\ninterface:\n  inputs: {}\n  outputs:\n    whatever_i_call_it:\n      contract: local.result\nsteps:\n  - id: make\n    kind: model\n    inputs: {}\n    prompt:\n      template: prompt.md\n      inject: {}\n    output:\n      format: yaml\n      validator: global_ledger\n      contract: local.result\noutputs:\n  whatever_i_call_it: steps.make\n""",
        encoding="utf-8",
    )
    plan = scheduler_engine.load_yaml(tmp_path / "scheduler.yaml")
    assert tuple(plan.doc["interface"]["outputs"]) == ("whatever_i_call_it",)
    assert scheduler_engine.output_contract(plan, "whatever_i_call_it").semantic_type == "ptbg.experimental"
