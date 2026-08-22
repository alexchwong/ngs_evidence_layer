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
    from workflows.terraced_v3.schedulers import domain

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
    specs = {row["domain"]: row for row in domain.task_specs(case, diagnoses)}
    assert specs["treatment"]["required_pairs"] == [
        ("SF3B1", "DX1"), ("SF3B1", "DX2"),
        ("TP53", "DX1"), ("TP53", "DX2"),
    ]


def test_all_five_schedulers_registered():
    from workflows.terraced_v3 import schedulers

    assert schedulers.names() == (
        "domain",
        "evidence-first",
        "variant-centric",
        "global-ledger",
        "adaptive-microtask",
    )
    for name in schedulers.names():
        module = schedulers.load(name)
        assert module.SCHEDULER_ID == name
        assert callable(module.run)


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
    from workflows.terraced_v3.schedulers import adaptive_microtask

    prognosis = {"decisions": [
        {"variant_id": "V1", "diagnosis_id": "DX1", "effect": "neither"},
        {"variant_id": "V2", "diagnosis_id": "DX1", "effect": "adverse"},
    ]}
    assert [key for key, _ in adaptive_microtask._high_impact("prognosis", prognosis)] == ["V2|DX1"]


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
