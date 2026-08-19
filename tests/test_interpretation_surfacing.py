import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATORS = ROOT / "scripts" / "phase_validation"
sys.path.insert(0, str(VALIDATORS))


def load_validator(name):
    spec = importlib.util.spec_from_file_location(name, VALIDATORS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def package(interpretation):
    return {
        "schema_version": "5.1",
        "cards": [
            {
                "card_id": "paper-C0001",
                "genes": ["NPM1"],
                "diseases": ["AML"],
                "interpretation": interpretation,
            },
            {
                "card_id": "paper-C0002",
                "genes": ["TP53"],
                "diseases": ["MDS"],
                "interpretation": "Legacy wording without surfaced metadata.",
            },
        ],
    }


def test_phase2_requires_tagged_gene_and_disease_in_interpretation():
    phase2 = load_validator("phase2")
    errors = phase2.interpretation_surfacing_errors(
        package("This mutation is favourable in this disease."), {"paper-C0001"}
    )
    assert any("missing: NPM1" in error for error in errors)
    assert any("missing: AML" in error for error in errors)


def test_phase2_accepts_canonical_gene_and_disease_alias_and_scopes_delta():
    phase2 = load_validator("phase2")
    errors = phase2.interpretation_surfacing_errors(
        package("NPM1 mutation is favourable in acute myeloid leukaemia."),
        {"paper-C0001"},
    )
    assert errors == []


def test_phase4_uses_same_surfacing_rule():
    phase4 = load_validator("phase4")
    errors = phase4.interpretation_surfacing_errors(
        package("NPM1 mutation is favourable in AML."), {"paper-C0001"}
    )
    assert errors == []
