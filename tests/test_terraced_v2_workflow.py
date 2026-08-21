import json
from pathlib import Path

import yaml

from scripts.workflow_registry import load_registry, load_workflow_metadata, normalise_selector
from workflows.terraced_v2 import model_registry, runtime

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "workflows" / "terraced_v2"


def test_terraced_v2_is_registered_without_repointing_terraced_alias():
    registry = load_registry()
    assert registry["workflows"]["terraced-v2"]["path"] == "workflows/terraced_v2"
    assert normalise_selector("terraced", registry) == "terraced-v1"
    assert normalise_selector("terraced-v2", registry) == "terraced-v2"
    assert load_workflow_metadata("terraced-v2")["python_package"] == "workflows.terraced_v2"


def test_yaml_pipeline_is_canonical_serial_dependency_order():
    doc = runtime.load_pipeline()
    ids = [row["id"] for row in doc["pipeline"]]
    assert ids == [
        "structure", "corpus", "diagnosis", "diagnosis_report",
        "germline", "prognosis", "biomarker", "treatment", "finalise",
    ]
    treatment = next(row for row in doc["pipeline"] if row["id"] == "treatment")
    assert treatment["context"] == {
        "diagnosis": ["cmc", "who5_diagnosis", "facts"],
        "germline": ["facts"],
        "prognosis": ["facts"],
        "biomarker": ["facts"],
    }
    invariants = doc["invariants"]
    assert invariants["propagate_uncertainty_between_domains"] is False
    assert invariants["allow_downstream_diagnosis_mutation"] is False
    assert invariants["diagnosis_authority"] == "WHO5"
    assert invariants["provider_specific_pipeline_branches"] is False


def test_questions_borrow_diagnosis_lab_and_v1_downstream_terraces():
    q = runtime.load_questions()
    lab = yaml.safe_load((ROOT / "workflows/terraced_v1/diagnosis_lab/questions.yaml").read_text())
    v1 = yaml.safe_load((ROOT / "workflows/terraced_v1/questions.yaml.template").read_text())
    assert [x["question"] for x in q["domains"]["diagnosis"]["questions"]] == [x["question"] for x in lab["questions"]]
    for domain in ("germline", "prognosis", "treatment"):
        assert [x["question"] for x in q["domains"][domain]["questions"]] == [x["question"] for x in v1["domains"][domain]["questions"]]
    assert [x["question"] for x in q["domains"]["biomarker"]["questions"]] == [x["question"] for x in v1["domains"]["mrd"]["questions"]]


def test_all_provider_profiles_share_one_pipeline():
    registry = model_registry.load_registry()
    assert set(registry["profiles"]) == {"self", "lmstudio", "ollama", "openrouter"}
    assert all("provider" not in row for row in runtime.load_pipeline()["pipeline"])
    assert runtime.load_pipeline()["invariants"]["provider_specific_pipeline_branches"] is False
    for profile in registry["profiles"]:
        for role in registry["roles"]:
            binding = model_registry.resolve(role, profile, registry=registry)
            assert binding.profile == profile


def test_diagnosis_context_sheds_uncertainty_and_icc():
    final = {
        "provisional_cmcs": ["AML"],
        "diagnoses": [{
            "schema_disease": "AML",
            "WHO5": {"status": "established", "diagnosis": "AML with NPM1 mutation"},
            "ICC": {"status": "established", "diagnosis": "AML with mutated NPM1"},
            "materially_different": False,
        }, {
            "schema_disease": "MDS",
            "WHO5": {"status": "indeterminate", "diagnosis": "MDS, subtype indeterminate"},
            "ICC": {"status": "indeterminate", "diagnosis": "MDS, subtype indeterminate"},
            "materially_different": False,
        }],
        "supporting_facts": [{"fact": "WHO5 diagnosis is AML.", "reason": "Supported.", "source_fact_ids": ["PRE-FINAL-F1"]}],
        "uncertainties": [{"uncertainty": "Example uncertainty.", "reason": "Example.", "source_ids": ["PRE-FINAL-U1"]}],
    }
    context = runtime.diagnosis_context(final)
    assert set(context) == {"cmc", "who5_diagnosis", "facts"}
    assert "ICC" not in json.dumps(context)
    assert "uncertaint" not in json.dumps(context).lower()
    assert context["who5_diagnosis"] == [{
        "schema_disease": "AML",
        "status": "established",
        "diagnosis": "AML with NPM1 mutation",
    }]
    assert "MDS, subtype indeterminate" not in json.dumps(context)


def test_case_json_contract(tmp_path):
    path = tmp_path / "case.json"
    path.write_text(json.dumps({
        "provisional_cmcs": ["AML"],
        "provisional_disease": "AML",
        "genes": ["NPM1"],
        "detected_variants_summary": "NGS detected NPM1 p.(X).",
        "case_facts": [{"fact_id": "F1", "kind": "morphology", "value": "Blasts 20%."}],
    }))
    assert runtime.validate_case_json(path) == "case.json validated"

def test_release_manifest_includes_terraced_v2_runtime_and_prompts():
    manifest = (ROOT / "release" / "skill.txt").read_text(encoding="utf-8").splitlines()
    assert "workflows/terraced_v2/*" in manifest
    assert "workflows/terraced_v2/prompts/*" in manifest

