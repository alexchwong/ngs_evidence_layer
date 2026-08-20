from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import yaml

HERE = Path(__file__).resolve().parents[1]


def _load_run_module():
    path = HERE / "run.py"
    spec = importlib.util.spec_from_file_location("diagnosis_lab_run", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_profiles_have_protected_dx7_tail():
    doc = yaml.safe_load((HERE / "questions.yaml").read_text(encoding="utf-8"))
    assert doc["execution_profiles"]["frontier"]["groups"] == [["DX1", "DX2", "DX3", "DX4", "DX5"], ["DX6"], ["DX7"]]
    assert doc["execution_profiles"]["balanced"]["groups"] == [["DX1", "DX2", "DX3"], ["DX4", "DX5"], ["DX6"], ["DX7"]]


def test_all_six_fixtures_are_complete():
    for number in range(1, 7):
        path = HERE / "fixtures" / f"example-{number:02d}" / "input.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert doc["example"] == number
        assert doc["case_notes"].strip()
        assert doc["structured_case"]["provisional_cmcs"]
        assert isinstance(doc["diagnosis_evidence_cards"], list)
        assert "no_haematological_malignancy" in doc["allowed_schema_diseases"]


def test_dx7_validator_protects_state_and_uncertainty():
    run = _load_run_module()
    dx6 = {
        "provisional_cmcs": ["MDS"],
        "diagnoses": [{"schema_disease": "AML", "narrow_diagnosis": "AML with mutated NPM1"}],
        "icc_diagnoses": ["AML with mutated NPM1 (ICC)"],
        "facts": [{"fact": "NPM1 supports AML.", "reason": "Established diagnostic fact.", "fact_id": "DX6-F1"}],
        "uncertainties": [{"uncertainty": "Assay uncertainty remains.", "reason": "Material limitation.", "uncertainty_id": "DX6-U1"}],
    }
    good = {
        "provisional_cmcs": ["MDS"],
        "diagnoses": [{"schema_disease": "AML", "narrow_diagnosis": "AML with mutated NPM1"}],
        "icc_diagnoses": ["AML with mutated NPM1 (ICC)"],
        "supporting_facts": [{"fact": "NPM1 supports AML.", "reason": "Established diagnostic fact.", "source_fact_ids": ["DX6-F1"]}],
        "uncertainties": [{"uncertainty": "Assay uncertainty remains.", "reason": "Material limitation.", "source_ids": ["DX6-U1"]}],
    }
    run._validate_dx7(good, dx6)


def test_dx6_cannot_erase_who5_or_material_icc():
    run = _load_run_module()
    previous = {
        "provisional_cmcs": ["MDS"],
        "diagnoses": [{"schema_disease": "AML", "narrow_diagnosis": "AML with mutated NPM1"}],
        "icc_diagnoses": ["AML with mutated NPM1 (ICC comparator)"],
        "facts": [],
        "uncertainties": [],
    }
    no_icc = dict(previous, icc_diagnoses=[])
    try:
        run._validate_transition(previous, no_icc, ["DX6"])
    except ValueError as exc:
        assert "ICC" in str(exc)
    else:
        raise AssertionError("DX6 should not be able to erase a material ICC comparator")


def test_negative_ngs_and_no_pathology_are_explicitly_independent():
    text = (HERE / "prompts" / "terrace.md").read_text(encoding="utf-8")
    questions = (HERE / "questions.yaml").read_text(encoding="utf-8")
    assert "negative NGS never proves no pathology by itself" in text
    assert "negative NGS result" in questions
    assert "no_haematological_malignancy" in questions


def test_run_layout_is_call_centric_and_input_output_labelled(tmp_path):
    run = _load_run_module()
    args = SimpleNamespace(
        profile="balanced",
        dry_run=True,
        provider="lmstudio",
        model="qwen3-coder-next",
        base_url=None,
        api_key=None,
        temperature=0.0,
        max_tokens=16384,
        timeout=900.0,
        output_dir=tmp_path,
    )
    run_dir = run._run_one(args, 1)
    assert (run_dir / "RUN_INPUT_fixture.json").is_file()
    assert (run_dir / "RUN_metadata.json").is_file()
    call = run_dir / "call_01_DX1-DX3"
    assert call.is_dir()
    for name in (
        "CALL_metadata.json",
        "INPUT_overview.md",
        "INPUT_questions.md",
        "INPUT_case_notes.md",
        "INPUT_previous_state.yaml",
        "INPUT_prior_transcript.json",
        "INPUT_evidence_cards.json",
        "INPUT_messages.json",
        "INPUT_messages_readable.md",
        "OUTPUT_not_run.txt",
    ):
        assert (call / name).is_file(), name
    assert not (run_dir / "prompt-01.json").exists()
    assert not (run_dir / "terrace-01.yaml").exists()

def test_output_schema_prompt_does_not_seed_a_concrete_diagnosis():
    text = (HERE / "prompts" / "terrace.md").read_text(encoding="utf-8")
    assert "AML with mutated NPM1" not in text
    assert "schema_disease: AML" not in text
    assert "  - AML\n" not in text
    assert "angle-bracketed text below describes the required field content" in text

