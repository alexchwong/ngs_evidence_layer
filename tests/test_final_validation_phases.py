from pathlib import Path
from types import SimpleNamespace

import pytest

import final_validation


def _write(path, text="{}"):
    Path(path).write_text(text, encoding="utf-8")
    return Path(path)


def test_phase_1_only_validates_metadata_and_census(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(final_validation.validation, "read_json", lambda path, label: {"entries": []})
    monkeypatch.setattr(final_validation.validation, "validate_metadata", lambda doc: calls.append("metadata") or [])
    monkeypatch.setattr(final_validation.validation, "validate_census", lambda doc, metadata: calls.append("census") or [])
    monkeypatch.setattr(final_validation.validation, "validate_package", lambda *a, **k: pytest.fail("package validator called"))
    errors, warnings, report = final_validation.validate_phase_files(
        phase=1,
        metadata_path=_write(tmp_path / "metadata.json"),
        census_path=_write(tmp_path / "paper.census.json"),
    )
    assert errors == []
    assert warnings == []
    assert calls == ["metadata", "census"]
    assert report == {"phase": 1, "census_entries": 0}


def test_phase_2_passes_paper_text_to_package_validator(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(final_validation.validation, "read_json", lambda path, label: {})

    def validate_package(package, metadata, census, source_text, require_final):
        seen.update(source_text=source_text, require_final=require_final)
        return ["bad quote"], [], {"cards": 1}

    monkeypatch.setattr(final_validation.validation, "validate_package", validate_package)
    errors, _, report = final_validation.validate_phase_files(
        phase=2,
        metadata_path=_write(tmp_path / "metadata.json"),
        census_path=_write(tmp_path / "paper.census.json"),
        source_path=_write(tmp_path / "paper.md", "verbatim source"),
        provisional_path=_write(tmp_path / "paper.provisional-001.json"),
    )
    assert seen == {"source_text": "verbatim source", "require_final": False}
    assert errors == ["provisional: bad quote"]
    assert report["cards"] == 1


def test_phase_3_only_validates_review(monkeypatch, tmp_path):
    documents = iter(({"cards": [{"card_id": "C1"}]}, {"card_results": [{"card_id": "C1"}]}))
    monkeypatch.setattr(final_validation.validation, "read_json", lambda path, label: next(documents))
    monkeypatch.setattr(final_validation.validation, "validate_review", lambda review, provisional: ["lineage"])
    monkeypatch.setattr(final_validation.validation, "validate_package", lambda *a, **k: pytest.fail("package validator called"))
    errors, warnings, report = final_validation.validate_phase_files(
        phase=3,
        provisional_path=_write(tmp_path / "paper.provisional-001.json"),
        review_path=_write(tmp_path / "paper.review-001.json"),
    )
    assert errors == ["review: lineage"]
    assert warnings == []
    assert report["cards"] == 1
    assert report["review_results"] == 1


def test_phase_4_does_not_revalidate_census_provisional_or_review(monkeypatch, tmp_path):
    docs = {
        "metadata": {},
        "census": {"entries": []},
        "approved provisional package": {"round": 1, "extraction_model": "phase2"},
        "Phase 3 review": {"round": 1, "reviewer_model": "phase3"},
        "final package": {
            "audit": {
                "approved_round": 1,
                "audit_model": "phase3",
                "extraction_model_reviewed": "phase2",
            }
        },
    }
    monkeypatch.setattr(final_validation.validation, "read_json", lambda path, label: docs[label])
    monkeypatch.setattr(final_validation.validation, "validate_census", lambda *a: pytest.fail("census validator called"))
    monkeypatch.setattr(final_validation.validation, "validate_review", lambda *a: pytest.fail("review validator called"))
    monkeypatch.setattr(final_validation.validation, "validate_final_against_provisional", lambda *a: [])
    calls = []

    def validate_package(package, metadata, census, source_text, require_final):
        calls.append(require_final)
        return [], [], {"cards": 0, "ratio": None}

    monkeypatch.setattr(final_validation.validation, "validate_package", validate_package)
    errors, _, _ = final_validation.validate_phase_files(
        phase=4,
        metadata_path=_write(tmp_path / "metadata.json"),
        census_path=_write(tmp_path / "paper.census.json"),
        source_path=_write(tmp_path / "paper.md"),
        provisional_path=_write(tmp_path / "paper.provisional-001.json"),
        review_path=_write(tmp_path / "paper.review-001.json"),
        final_path=_write(tmp_path / "paper.final.json"),
    )
    assert errors == []
    assert calls == [True]


@pytest.mark.parametrize(
    ("phase", "argv"),
    [
        (1, ["--phase", "1", "--metadata", "m", "--census", "c"]),
        (2, ["--phase", "2", "--metadata", "m", "--census", "c", "--source", "s", "--provisional", "p"]),
        (3, ["--phase", "3", "--provisional", "p", "--review", "r"]),
        (4, ["--phase", "4", "--metadata", "m", "--census", "c", "--source", "s", "--provisional", "p", "--review", "r", "--final", "f"]),
    ],
)
def test_cli_accepts_phase_specific_arguments(phase, argv):
    assert final_validation.parse_args(argv).phase == phase
