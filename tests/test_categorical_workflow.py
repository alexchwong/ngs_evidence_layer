import json
from pathlib import Path

import yaml

from scripts.workflow_registry import load_registry, normalise_selector
from workflows.categorical_v1 import report_yaml


def write_yaml(path: Path, document: dict) -> None:
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


def test_default_and_diagnosis_first_alias():
    registry = load_registry()
    assert normalise_selector(None, registry) == "categorical-v1"
    assert normalise_selector("--diagnosis-first", registry) == "diagnosis-first-v1"
    assert normalise_selector("--legacy", registry) == "legacy-v1"


def test_category_mapping_and_deterministic_empty_template(tmp_path):
    report = {
        "schema_version": 1,
        "rules": [
            {"id": "R0.1", "omit": False, "statements": [{"text": "Variant detected.", "citation": "(no citation required)"}]},
            {"id": "R1.1", "omit": False, "statements": [{"text": "Diagnosis conclusion.", "citation": "[card:a1b2c3]"}]},
            {"id": "R2.1", "omit": False, "statements": [{"text": "Prognostic conclusion.", "citation": "[card:d4e5f6]"}]},
        ],
    }
    path = tmp_path / "report-draft.yaml"
    write_yaml(path, report)
    assert [r["id"] for r in report_yaml.category_rules(path, "diagnosis")] == ["R0.1", "R1.1"]
    assert [r["id"] for r in report_yaml.category_rules(path, "prognosis")] == ["R2.1"]
    assert report_yaml.category_rules(path, "treatment") == []

    empty = report_yaml.write_category_template(tmp_path / "report-summary-treatment.yaml", "treatment", omitted=True)
    document = yaml.safe_load(empty.read_text(encoding="utf-8"))
    assert document == {"schema_version": 1, "category": "treatment", "statements": []}


def test_category_word_limit_is_enforced(tmp_path):
    source_rules = [
        {"id": "R2.1", "omit": False, "statements": [{"text": "Source.", "citation": "[card:a1b2c3]"}]}
    ]
    summary = {
        "schema_version": 1,
        "category": "prognosis",
        "statements": [{"text": " ".join(["word"] * 51) + ".", "citation": "[card:a1b2c3]"}],
    }
    path = tmp_path / "report-summary-prognosis.yaml"
    write_yaml(path, summary)
    try:
        report_yaml.validate_category_summary(path, source_rules, category="prognosis", require_content=True)
    except ValueError as exc:
        assert "maximum is 50" in str(exc)
    else:
        raise AssertionError("expected prognosis word-limit failure")
