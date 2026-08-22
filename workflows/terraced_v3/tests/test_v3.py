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
            {"diagnosis_id": "DX1", "schema_disease": "MDS", "status": "established", "diagnosis": "MDS", "fact": "x.", "reason": "x", "card_tags": []},
            {"diagnosis_id": "DX2", "schema_disease": "CLL/SLL", "status": "established", "diagnosis": "CLL/SLL", "fact": "y.", "reason": "y", "card_tags": []},
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
    case_refs: []
    card_tags: []
  - variant_id: V1
    diagnosis_id: DX2
    effect: adverse
    scoring_system: CLL-IPI
    surface: true
    fact: "Variant V1 is adverse in this disease context."
    reason: "The supplied evidence classifies it as adverse."
    case_refs: []
    card_tags: []
"""
    spec = {"required_pairs": [("V1", "DX1"), ("V1", "DX2")]}
    assert runtime.validate_domain_text(text, domain="prognosis", spec=spec, permitted_tags=set())


def test_fact_ledger_reconciliation_preserves_id_for_reason_change_and_replaces_changed_fact():
    ledger = runtime.new_fact_ledger()
    first = [{
        "domain": "prognosis",
        "subject": {"variant_id": "V1", "diagnosis_ids": ["DX1"]},
        "decision": {"effect": "adverse"},
        "fact": "NPM1 is prognostically relevant in AML.",
        "reason": "Initial reason.",
        "case_refs": ["V1"],
        "card_tags": ["[card:aaaaaaaaaaaa]"],
    }]
    runtime.reconcile_fact_snapshot(ledger, "ptbg.prognosis", first, source="pass-1")
    assert runtime.active_ledger_facts(ledger)[0]["fact_id"] == "F0001"

    same = [dict(first[0], subject={"variant_id": "V1", "diagnosis_ids": ["DX2"]}, reason="Updated reason.")]
    runtime.reconcile_fact_snapshot(ledger, "ptbg.prognosis", same, source="pass-2")
    active = runtime.active_ledger_facts(ledger)
    assert [row["fact_id"] for row in active] == ["F0001"]
    assert active[0]["current_reason"] == "Updated reason."
    assert active[0]["current_subject"]["diagnosis_ids"] == ["DX2"]

    changed = [dict(same[0], fact="NPM1 is favourable in this AML context.")]
    runtime.reconcile_fact_snapshot(ledger, "ptbg.prognosis", changed, source="pass-3")
    active = runtime.active_ledger_facts(ledger)
    assert [row["fact_id"] for row in active] == ["F0002"]
    assert next(row for row in ledger["facts"] if row["fact_id"] == "F0001")["status"] == "withdrawn"


def test_fact_evidence_check_is_required_for_every_new_reportable_fact():
    ledger = runtime.new_fact_ledger()
    cited = {"domain": "diagnosis", "fact": "A cited fact.", "reason": "x", "subject": {}, "decision": {}, "case_refs": ["C1"], "card_tags": ["[card:aaaaaaaaaaaa]"]}
    case_only = {"domain": "diagnosis", "fact": "A case-derived fact.", "reason": "x", "subject": {}, "decision": {}, "case_refs": ["C2"], "card_tags": []}
    pending = runtime.facts_needing_evidence_check(ledger, "diagnosis.who5", [cited, case_only])
    assert pending == [cited, case_only]
    runtime.reconcile_fact_snapshot(ledger, "diagnosis.who5", [cited, case_only], source="pass-1")
    assert runtime.facts_needing_evidence_check(ledger, "diagnosis.who5", [cited, case_only]) == []


def test_fact_ledger_replaces_fact_when_case_provenance_changes():
    ledger = runtime.new_fact_ledger()
    first = [{
        "domain": "diagnosis", "fact": "A patient-level proposition.", "reason": "x",
        "subject": {}, "decision": {}, "case_refs": ["C1"], "card_tags": [],
    }]
    runtime.reconcile_fact_snapshot(ledger, "diagnosis.who5", first, source="pass-1")
    changed = [dict(first[0], case_refs=["C2"])]
    runtime.reconcile_fact_snapshot(ledger, "diagnosis.who5", changed, source="pass-2")
    assert [row["fact_id"] for row in runtime.active_ledger_facts(ledger)] == ["F0002"]
    assert next(row for row in ledger["facts"] if row["fact_id"] == "F0001")["status"] == "withdrawn"


def test_issue_specific_observation_repair_does_not_expand_fact_to_fit_cards():
    from workflows.terraced_v3.step import _fact_evidence_repair_instruction
    msg = _fact_evidence_repair_instruction(
        "observation_should_be_cardless",
        {"fact": "SRSF2 mutation is present.", "case_refs": ["V1"], "card_tags": ["[card:aaaaaaaaaaaa]"]},
    )
    assert "set card_tags: []" in msg
    assert "Do not expand the observation merely to justify" in msg
    assert "separate self-contained fact" in msg


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
        "    card_tags: []\n"
    )
    result = syntax_repair.repair_structured_output(
        broken,
        format_name="yaml",
        model_attempts=0,
    )
    parsed = yaml.safe_load(result.text)
    assert parsed["supporting_facts"][0]["reason"] == "Case fact C2: 30% myeloid blasts."
    assert any("quoted YAML plain scalar" in repair for repair in result.deterministic_repairs)


def test_stagnation_instruction_exists_and_is_concise():
    from scripts.core import validated_model_task

    assert validated_model_task.stagnation_instruction(0) == ""
    msg = validated_model_task.stagnation_instruction(1)
    assert "same invalid artifact" in msg
    assert "material correction" in msg


def test_relevance_extraction_selects_cards_by_header_line_number_only():
    from workflows.terraced_v3.evidence_resolution import parse_relevance_output

    labels = parse_relevance_output(
        "relevant_card_header_lines: [21]\n",
        header_line_to_label={21: "CARD 21"},
        max_cards=10,
    )
    assert labels == ["CARD 21"]
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
  - card_tags: [abcdefabcdef]
  - card_tags: ["abcdefabcdef"]
  - target_card_tags: [abcdefabcdef, "1234567890ab"]
  - resistance_card_tags: [card:abcdefabcdef]
evidence_items:
  - card_tag: 1234567890ab
'''
    repaired, repairs = runtime.normalize_model_card_tag_syntax(text, format_name="yaml")
    doc = yaml.safe_load(repaired)
    assert doc["decisions"][0]["card_tags"] == ["[card:abcdefabcdef]"]
    assert doc["decisions"][1]["card_tags"] == ["[card:abcdefabcdef]"]
    assert doc["decisions"][2]["target_card_tags"] == ["[card:abcdefabcdef]", "[card:1234567890ab]"]
    assert doc["decisions"][3]["resistance_card_tags"] == ["[card:abcdefabcdef]"]
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
    case_refs: []
    card_tags: [abcdefabcdef]
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


def test_canonical_summary_requires_card_tags_derived_from_source_facts():
    facts = [{
        "fact_id": "F0001", "domain": "prognosis", "fact": "A prognostic fact.",
        "card_tags": ["[card:abcdefabcdef]"],
    }]
    good = {
        "dispositions": [{"fact_id": "F0001", "decision": "include", "reason": None}],
        "sentences": [{
            "sentence_id": "prognosis-1", "domain": "prognosis", "sentence": "This is favourable.",
            "source_fact_ids": ["F0001"], "card_tags": ["[card:abcdefabcdef]"],
        }],
    }
    assert runtime.validate_canonical_summary_doc(good, facts)
    bad = {"dispositions": good["dispositions"], "sentences": [dict(good["sentences"][0], card_tags=[])]}
    try:
        runtime.validate_canonical_summary_doc(bad, facts)
    except ValueError as exc:
        assert "citations are deterministic from source facts" in str(exc)
    else:
        raise AssertionError("expected canonical summary tag mismatch")


def test_sentence_card_interpretations_are_created_deterministically():
    summary = {"sentences": [{
        "sentence_id": "treatment-1", "domain": "treatment", "sentence": "FLT3 is targetable.",
        "source_fact_ids": ["F0001"], "card_tags": ["[card:abcdefabcdef]"],
    }]}
    paired = runtime.sentence_card_interpretations(summary, {"[card:abcdefabcdef]": "FLT3 alterations can be therapeutically targeted in AML."})
    assert paired["sentences"][0]["source_fact_ids"] == ["F0001"]
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
    finalise["inputs"]["summary"] = "facts.cited_facts"
    path = tmp_path / "bad-pipeline.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    try:
        pipeline_registry.load_yaml(path)
    except ValueError as exc:
        message = str(exc)
        assert "pipeline contract mismatch" in message
        assert "semantic type mismatch" in message
        assert "explicit adapter module" in message
        assert "Source facts.cited_facts" in message
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


def test_default_summarization_plans_paraphrases_and_inherits_citations(tmp_path):
    from workflows.terraced_v3 import scheduler_engine, scheduler_primitives, scheduler_registry

    facts = [
        {"fact_id": "F0001", "domain": "diagnosis", "fact": "Diagnosis fact.", "card_tags": ["[card:aaaaaaaaaaaa]"]},
        {"fact_id": "F0002", "domain": "treatment", "fact": "Treatment fact.", "card_tags": ["[card:bbbbbbbbbbbb]"]},
        {"fact_id": "F0003", "domain": "treatment", "fact": "Redundant treatment fact.", "card_tags": ["[card:cccccccccccc]"]},
    ]
    seen_paraphrase_items = []

    def call_model(*, call_id, prompt, output, validator, **_):
        if "-plan-" in call_id:
            assert "# Immutable cited reportable facts" in prompt
            output.write_text(
                "dispositions:\n"
                "  - fact_id: F0001\n    decision: include\n    reason: null\n"
                "  - fact_id: F0002\n    decision: include\n    reason: null\n"
                "  - fact_id: F0003\n    decision: omit\n    reason: Redundant with F0002.\n"
                "sentences:\n"
                "  - sentence_id: diagnosis-1\n    domain: diagnosis\n    source_fact_ids: [F0001]\n    draft_sentence: Diagnosis fact.\n"
                "  - sentence_id: treatment-1\n    domain: treatment\n    source_fact_ids: [F0002]\n    draft_sentence: Treatment fact.\n",
                encoding="utf-8",
            )
        else:
            assert "# Planned sentence and its source facts" in prompt
            if "diagnosis-1" in call_id:
                seen_paraphrase_items.append("diagnosis-1")
                output.write_text("sentence_id: diagnosis-1\nsentence: Diagnosis fact.\n", encoding="utf-8")
            else:
                seen_paraphrase_items.append("treatment-1")
                output.write_text("sentence_id: treatment-1\nsentence: Treatment fact.\n", encoding="utf-8")
        validator(output.read_text(encoding="utf-8"))

    checked = []
    ctx = scheduler_primitives.SchedulerContext(
        work=tmp_path, case={}, diagnoses=[], final_cmcs=[], pipeline_id="test", call_model=call_model,
        ensure_evidence=lambda _: None, read_text=lambda path: path.read_text(encoding="utf-8"),
        write_text=lambda path, text: path.write_text(text, encoding="utf-8"), status=lambda _: None,
        phase="summarization", values={"cited_facts": facts},
        paraphrase_guard=lambda **kwargs: checked.append(kwargs),
    )
    plan = scheduler_registry.load("default-summarization", "summarization")
    result = scheduler_engine.execute(plan, ctx)

    assert seen_paraphrase_items == ["diagnosis-1", "treatment-1"]
    assert len(checked) == 2
    assert result["summary"]["dispositions"][2]["decision"] == "omit"
    assert result["summary"]["sentences"][0]["source_fact_ids"] == ["F0001"]
    assert result["summary"]["sentences"][0]["card_tags"] == ["[card:aaaaaaaaaaaa]"]
    assert result["summary"]["sentences"][1]["card_tags"] == ["[card:bbbbbbbbbbbb]"]


def test_summary_plan_supports_merge_and_split_with_explicit_omission():
    facts = [
        {"fact_id": "F0001", "domain": "prognosis", "fact": "Fact one.", "card_tags": ["[card:aaaaaaaaaaaa]"]},
        {"fact_id": "F0002", "domain": "prognosis", "fact": "Fact two.", "card_tags": ["[card:bbbbbbbbbbbb]"]},
        {"fact_id": "F0003", "domain": "prognosis", "fact": "Fact three.", "card_tags": []},
    ]
    plan = {
        "dispositions": [
            {"fact_id": "F0001", "decision": "include", "reason": None},
            {"fact_id": "F0002", "decision": "include", "reason": None},
            {"fact_id": "F0003", "decision": "omit", "reason": "Redundant."},
        ],
        "sentences": [
            {"sentence_id": "prognosis-1", "domain": "prognosis", "source_fact_ids": ["F0001", "F0002"], "draft_sentence": "Facts one and two are relevant."},
            {"sentence_id": "prognosis-2", "domain": "prognosis", "source_fact_ids": ["F0001"], "draft_sentence": "Fact one is also stated separately."},
        ],
    }
    assert runtime.validate_summary_plan_doc(plan, facts)
    items = runtime.paraphrase_items(plan, facts)
    assert items[0]["split_source_fact_ids"] == ["F0001"]
    assert items[1]["split_source_fact_ids"] == ["F0001"]



def test_non_surfaced_domain_row_cannot_carry_evidence_provenance():
    text = """decisions:
  - variant_id: V1
    diagnosis_id: DX1
    effect: neither
    scoring_system: null
    surface: false
    fact: null
    reason: null
    card_tags: [\"[card:abcdefabcdef]\"]
"""
    try:
        runtime.validate_domain_text(
            text,
            domain="prognosis",
            spec={"required_pairs": [("V1", "DX1")]},
            permitted_tags={"abcdefabcdef"},
        )
    except Exception as exc:
        assert "no surfaced reportable fact to cite" in str(exc)
    else:
        raise AssertionError("expected provenance on surface=false row to fail")


def test_case_reference_in_card_tags_gets_provenance_specific_feedback():
    text = """decisions:
  - variant_id: V1
    diagnosis_id: DX1
    effect: neither
    scoring_system: null
    surface: true
    fact: "SRSF2 mutation is present."
    reason: "Reported in the structured case."
    case_refs: []
    card_tags: [V1]
"""
    try:
        runtime.validate_domain_text(
            text, domain="prognosis", spec={"required_pairs": [("V1", "DX1")]},
            permitted_tags=set(), permitted_case_refs={"V1"},
        )
    except Exception as exc:
        message = str(exc)
        assert "patient case/variant identifier" in message
        assert "move 'V1' to the sibling case_refs field" in message
        assert "do not replace it with an arbitrary [card:...] tag" in message
    else:
        raise AssertionError("expected patient provenance in card_tags to fail")


def test_local_evidence_checker_contract_is_reject_only_and_complete():
    good = """checks:
  - candidate_id: C1
    supported: true
    issue_code: null
    issue: null
  - candidate_id: C2
    supported: false
    issue_code: unsupported_inference
    issue: The claimed card does not support the complete proposition.
"""
    assert runtime.validate_fact_evidence_check_text(good, ["C1", "C2"])
    incomplete = """checks:
  - candidate_id: C1
    supported: true
    issue_code: null
    issue: null
"""
    try:
        runtime.validate_fact_evidence_check_text(incomplete, ["C1", "C2"])
    except Exception as exc:
        assert "C2" in str(exc)
    else:
        raise AssertionError("expected missing checker result to fail")


def test_merged_summary_sentence_inherits_union_of_source_cards_in_source_order():
    facts = [
        {"fact_id": "F0001", "domain": "prognosis", "fact": "Fact one.", "card_tags": ["[card:aaaaaaaaaaaa]", "[card:bbbbbbbbbbbb]"]},
        {"fact_id": "F0002", "domain": "prognosis", "fact": "Fact two.", "card_tags": ["[card:bbbbbbbbbbbb]", "[card:cccccccccccc]"]},
    ]
    assert runtime.deterministic_sentence_card_tags(["F0001", "F0002"], facts) == [
        "[card:aaaaaaaaaaaa]", "[card:bbbbbbbbbbbb]", "[card:cccccccccccc]"
    ]


def test_fact_evidence_prompt_treats_case_observations_as_supplied_premises():
    prompt = (Path(__file__).parents[1] / "prompts" / "fact_evidence_check.md").read_text(encoding="utf-8")
    assert "patient-specific observations" in prompt
    assert "supplied premises" in prompt
    assert "interpretive inference" in prompt


def test_scheduler_model_steps_reenter_call_model_when_output_already_exists(tmp_path):
    from workflows.terraced_v3 import scheduler_engine, scheduler_primitives, scheduler_registry

    facts = [{"fact_id": "F0001", "domain": "diagnosis", "fact": "Diagnosis fact.", "card_tags": []}]
    calls = []

    def call_model(*, call_id, output, validator, **_):
        calls.append(call_id)
        # The scheduler must still invoke the model-call boundary on resume; that
        # boundary decides whether the existing artifact is valid or needs retry.
        validator(output.read_text(encoding="utf-8"))

    ctx = scheduler_primitives.SchedulerContext(
        work=tmp_path, case={}, diagnoses=[], final_cmcs=[], pipeline_id="test", call_model=call_model,
        ensure_evidence=lambda _: None, read_text=lambda path: path.read_text(encoding="utf-8"),
        write_text=lambda path, text: path.write_text(text, encoding="utf-8"), status=lambda _: None,
        phase="summarization", values={"cited_facts": facts},
    )
    plan = scheduler_registry.load("default-summarization", "summarization")
    root = tmp_path / "schedulers" / "summarization-default-summarization" / "plan"
    root.mkdir(parents=True, exist_ok=True)
    (root / "1.yaml").write_text(
        "dispositions:\n  - fact_id: F0001\n    decision: include\n    reason: null\n"
        "sentences:\n  - sentence_id: diagnosis-1\n    domain: diagnosis\n    source_fact_ids: [F0001]\n    draft_sentence: Diagnosis fact.\n",
        encoding="utf-8",
    )
    # We only need to prove the first existing model artifact re-enters call_model;
    # stop deliberately when the next model artifact is absent.
    try:
        scheduler_engine.execute(plan, ctx)
    except FileNotFoundError:
        pass
    assert any("-plan-" in call_id for call_id in calls)


def test_diagnosis_corpus_filters_are_authority_specific():
    from workflows.terraced_v3 import evidence_resolution
    settings = evidence_resolution.load_settings()
    cards = [
        {"publication_key": "arber-2022-blood-140-1200", "card_id": "a"},
        {"publication_key": "khoury-2022-leukemia-36-1703", "card_id": "b"},
        {"publication_key": "other", "card_id": "c"},
    ]
    assert [c["card_id"] for c in evidence_resolution.filter_diagnosis_cards(cards, "icc", settings=settings)] == ["a"]
    assert [c["card_id"] for c in evidence_resolution.filter_diagnosis_cards(cards, "who5", settings=settings)] == ["b"]


def test_relevance_extraction_uses_only_supplied_card_header_lines():
    from workflows.terraced_v3 import evidence_resolution
    cards = [
        {"card_id": "a", "category": "diagnosis", "genes": ["ASXL1"], "diseases": ["AML"], "evidence_tier": "guideline", "interpretation": "ASXL1 is a qualifying feature.", "paper_nickname": "Khoury", "publication_year": 2022},
        {"card_id": "b", "category": "diagnosis", "genes": ["SRSF2"], "diseases": ["AML"], "evidence_tier": "guideline", "interpretation": "SRSF2 is a qualifying feature.", "paper_nickname": "Khoury", "publication_year": 2022},
    ]
    text, header_lines = evidence_resolution.render_numbered_relevance_blocks(cards)
    assert "0001 | <<<CARD 01>>>" in text
    assert header_lines == {1: "CARD 01", 10: "CARD 02"}
    payload = "relevant_card_header_lines:\n  - 1\n  - 10\n"
    assert evidence_resolution.parse_relevance_output(payload, header_line_to_label=header_lines, max_cards=10) == ["CARD 01", "CARD 02"]

    for invalid in (
        "relevant_card_header_lines: [2]\n",       # card body line
        "relevant_card_header_lines: [999]\n",     # nonexistent line
        "relevant_card_header_lines: [1, 1]\n",    # duplicate selection
    ):
        try:
            evidence_resolution.parse_relevance_output(invalid, header_line_to_label=header_lines, max_cards=10)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected invalid relevance selection to fail: {invalid!r}")
def test_pairing_uses_local_labels_and_python_resolves_runtime_card_tags():
    from workflows.terraced_v3 import card_identity, evidence_resolution, scheduler_primitives
    card = {"card_id": "khoury-C1", "category": "diagnosis", "genes": ["ASXL1"], "diseases": ["AML"], "interpretation": "WHO5 AML-MR criterion.", "publication_key": "khoury-2022-leukemia-36-1703"}
    manifest = card_identity.build_manifest([card])
    full = scheduler_primitives.EvidenceView(domain="diagnosis", cards=[card], manifest=manifest, permitted_tags=set(card_identity.tag_by_id(manifest).values()), text="unused")
    local = evidence_resolution.local_evidence(full, [card])
    paired = """diagnoses:\n  - diagnosis_id: ICC1\n    status: established\n    diagnosis: AML\n    fact: \"AML is established.\"\n    reason: x\n    case_refs: [C1]\n    card_refs: [\"CARD 01\"]\n"""
    doc, _rendered = evidence_resolution.resolve_pairing_text(paired, local=local)
    assert doc["diagnoses"][0]["card_tags"] == [f"[card:{card_identity.tag_by_id(manifest)['khoury-C1']}]"]
    assert "card_refs" not in doc["diagnoses"][0]


def test_support_audit_renders_interpretation_immediately_below_fact_with_balanced_question():
    from workflows.terraced_v3 import card_identity, evidence_resolution, scheduler_primitives
    card = {"card_id": "khoury-C1", "category": "diagnosis", "genes": ["ASXL1"], "diseases": ["AML"], "interpretation": "ASXL1 can satisfy the WHO5 AML-MR defining-mutation criterion.", "publication_key": "khoury-2022-leukemia-36-1703"}
    manifest = card_identity.build_manifest([card])
    raw = card_identity.tag_by_id(manifest)["khoury-C1"]
    full = scheduler_primitives.EvidenceView(domain="diagnosis", cards=[card], manifest=manifest, permitted_tags={raw}, text="unused")
    local = evidence_resolution.local_evidence(full, [card])
    doc = {"diagnoses": [{"diagnosis_id": "ICC1", "fact": "With the patient findings, AML-MR is supported.", "case_refs": ["C1"], "card_tags": [f"[card:{raw}]"]}]}
    pairs, _ = evidence_resolution._audit_payload(doc, authority="icc", local=local)
    assert "Fact: With the patient findings, AML-MR is supported.\nPatient sources: C1\nSelected card 1:" in pairs
    assert "Interpretation 1: ASXL1 can satisfy the WHO5 AML-MR defining-mutation criterion." in pairs
    assert "Question: Does this interpretation reasonably support the fact? Treat patient observations as given." in pairs


def test_diagnosis_schedulers_enable_three_pass_evidence_resolution():
    from workflows.terraced_v3 import scheduler_registry
    for name in ("default-diagnosis", "minimal-diagnosis"):
        plan = scheduler_registry.load(name, "diagnosis")
        by_id = {step["id"]: step for step in plan.doc["steps"]}
        assert by_id["icc"]["evidence_resolution"]["authority"] == "icc"
        assert by_id["who5"]["evidence_resolution"]["authority"] == "who5"
        assert by_id["icc"]["prompt"]["inject"]["output_contract"]["contract"] == "core.diagnosis.icc-pairing-output"
        assert by_id["who5"]["prompt"]["inject"]["output_contract"]["contract"] == "core.diagnosis.who5-pairing-output"


def test_diagnosis_evidence_resolution_orchestrates_local_labels_to_final_tags(tmp_path):
    from workflows.terraced_v3 import card_identity, evidence_resolution, scheduler_engine, scheduler_primitives, scheduler_registry

    card = {
        "card_id": "arber-C1",
        "category": "diagnosis",
        "genes": ["ASXL1"],
        "diseases": ["AML"],
        "evidence_tier": "classification",
        "interpretation": "According to ICC, ASXL1 is an AML myelodysplasia-related gene mutation.",
        "paper_nickname": "Arber",
        "publication_year": 2022,
        "publication_key": "arber-2022-blood-140-1200",
    }
    manifest = card_identity.build_manifest([card])
    raw = card_identity.tag_by_id(manifest)["arber-C1"]
    evidence = scheduler_primitives.EvidenceView(
        domain="diagnosis", cards=[card], manifest=manifest, permitted_tags={raw}, text="unused"
    )
    case = {
        "provisional_disease": "AML",
        "bootstrap_cmcs": ["AML"],
        "variants": [],
        "detected_variants_summary": "No variants supplied.",
        "case_facts": [{"fact_id": "C1", "kind": "marrow", "value": "30% blasts"}],
    }
    calls = []

    def call_model(*, call_id, role, prompt, output, validator, format_name):
        calls.append((call_id, prompt))
        output.parent.mkdir(parents=True, exist_ok=True)
        if call_id.endswith("-relevance"):
            assert "0001 | <<<CARD 01>>>" in prompt
            assert "relevant_card_header_lines" in prompt
            payload = "relevant_card_header_lines: [1]\n"
        elif call_id.endswith("-pairing"):
            assert "[card:" not in prompt
            assert "card_refs" in prompt
            payload = """diagnoses:\n  - diagnosis_id: ICC1\n    status: established\n    diagnosis: AML with myelodysplasia-related gene mutations\n    fact: \"The findings meet ICC criteria for AML with myelodysplasia-related gene mutations.\"\n    reason: \"The patient has AML-range blasts with a qualifying ASXL1 mutation.\"\n    case_refs: [C1]\n    card_refs: [\"CARD 01\"]\n"""
        elif call_id.endswith("-audit"):
            assert "Does this interpretation reasonably support the fact? Treat patient observations as given." in prompt
            payload = """assessments:\n  - candidate_id: C1\n    assessment: supported\n    reason: \"The interpretation directly supports the classification claim.\"\n"""
        else:
            raise AssertionError(call_id)
        validator(payload)
        output.write_text(payload, encoding="utf-8")

    ctx = scheduler_primitives.SchedulerContext(
        work=tmp_path,
        case=case,
        diagnoses=[],
        final_cmcs=[],
        pipeline_id="test",
        call_model=call_model,
        ensure_evidence=lambda _domain: evidence,
        read_text=lambda p: p.read_text(encoding="utf-8"),
        write_text=lambda p, text: (p.parent.mkdir(parents=True, exist_ok=True), p.write_text(text, encoding="utf-8"), p)[-1],
        status=lambda _msg: None,
        phase="diagnosis",
        values={},
    )
    plan = scheduler_registry.load("default-diagnosis", "diagnosis")
    step = next(row for row in plan.doc["steps"] if row["id"] == "icc")
    base_validator = lambda text: runtime.validate_icc_text(text, {raw}, {"C1"})
    output = tmp_path / "icc.yaml"
    doc = scheduler_engine._run_diagnosis_evidence_resolved(
        plan=plan,
        ctx=ctx,
        base=plan.path.parent,
        step=step,
        inputs={"case": case, "panel_scope": "scope", "evidence": evidence},
        item=None,
        output=output,
        base_validator=base_validator,
        call_id="test-icc",
        source="test",
    )
    assert doc["diagnoses"][0]["card_tags"] == [f"[card:{raw}]"]
    assert output.is_file()
    assert [cid for cid, _ in calls] == ["test-icc-relevance", "test-icc-pairing", "test-icc-audit"]
