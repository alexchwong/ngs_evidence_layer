from pathlib import Path
import re

import pytest

from validation.cases import retrieve_case, retrieve_MC


SYNTHETIC_CASES = """\
# Case 7 — Synthetic parser case

## Shared stem

Shared clinical stem for case 7.

## Case 7A — First variant

### Clinical information

Variant A clinical information with GENE_A.

### NEL task

Task text that must not leak into retrieved clinical information.

### Marking criteria

- **R1C1:** Criterion for variant A.
- **R2C1:** Second criterion for variant A.

## Case 7C — Third variant

### Clinical information

Variant C clinical information with GENE_C.

### NEL task

Another task that must not leak.

### Marking criteria

- **R1C1:** Criterion for variant C.

---

# Case 8 — Another synthetic parser case

## Shared stem

Shared clinical stem for case 8.

## Case 8A — Only variant

### Clinical information

Variant 8A clinical information.

### NEL task

Task for 8A.

### Marking criteria

- **R1C1:** Criterion for 8A.
"""


@pytest.fixture
def synthetic_case_file(tmp_path):
    path = tmp_path / "case_summary.md"
    path.write_text(SYNTHETIC_CASES, encoding="utf-8")
    return str(path)


def test_stem_only(synthetic_case_file):
    assert retrieve_case("7", case_file=synthetic_case_file) == "Shared clinical stem for case 7."


def test_stem_plus_variant_excludes_task_and_marking_criteria(synthetic_case_file):
    result = retrieve_case("7A", case_file=synthetic_case_file)

    assert result == (
        "Shared clinical stem for case 7.\n\n"
        "Variant A clinical information with GENE_A."
    )
    assert "NEL task" not in result
    assert "Task text" not in result
    assert "Marking criteria" not in result
    assert "Criterion" not in result


def test_marking_criteria_only(synthetic_case_file):
    result = retrieve_MC("7A", case_file=synthetic_case_file)

    assert result == (
        "- **R1C1:** Criterion for variant A.\n"
        "- **R2C1:** Second criterion for variant A."
    )
    assert "Clinical information" not in result
    assert "GENE_A" not in result
    assert "NEL task" not in result


def test_case_identifier_is_case_insensitive(synthetic_case_file):
    assert retrieve_case("7c", case_file=synthetic_case_file) == retrieve_case(
        "7C", case_file=synthetic_case_file
    )
    assert retrieve_MC("7c", case_file=synthetic_case_file) == retrieve_MC(
        "7C", case_file=synthetic_case_file
    )


@pytest.mark.parametrize("case_id", ["", "A7", "7AA", "7-A", "case 7A"])
def test_retrieve_case_rejects_malformed_identifiers(case_id, synthetic_case_file):
    with pytest.raises(ValueError):
        retrieve_case(case_id, case_file=synthetic_case_file)


@pytest.mark.parametrize("case_id", ["7", "", "A7", "7AA"])
def test_retrieve_mc_requires_variant_identifier(case_id, synthetic_case_file):
    with pytest.raises(ValueError):
        retrieve_MC(case_id, case_file=synthetic_case_file)


def test_missing_case_raises_key_error(synthetic_case_file):
    with pytest.raises(KeyError, match="Case 99 not found"):
        retrieve_case("99", case_file=synthetic_case_file)


def test_missing_variant_raises_key_error(synthetic_case_file):
    with pytest.raises(KeyError, match="Case variant 7B not found"):
        retrieve_case("7B", case_file=synthetic_case_file)


def test_missing_marking_criteria_raises_key_error(tmp_path):
    path = tmp_path / "case_summary.md"
    path.write_text(
        """\
# Case 1 — Missing criteria

## Shared stem

Stem.

## Case 1A — Variant

### Clinical information

Clinical information.

### NEL task

Task.
""",
        encoding="utf-8",
    )

    with pytest.raises(KeyError, match="Marking criteria for case variant 1A not found"):
        retrieve_MC("1A", case_file=str(path))


def test_missing_shared_stem_raises_value_error(tmp_path):
    path = tmp_path / "case_summary.md"
    path.write_text(
        """\
# Case 1 — Missing stem

## Case 1A — Variant

### Clinical information

Clinical information.

### NEL task

Task.

### Marking criteria

- **R1C1:** Criterion.
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Case 1 has no shared stem"):
        retrieve_case("1", case_file=str(path))


def test_production_case_summary_is_structurally_retrievable():
    """Integration check: validate structure without asserting clinical content."""
    case_file = Path(__file__).resolve().parents[1] / "validation" / "case_summary.md"
    text = case_file.read_text(encoding="utf-8")

    case_numbers = re.findall(r"^# Case (\d+)\b", text, flags=re.MULTILINE)
    variant_ids = re.findall(r"^## Case (\d+[A-Z])\b", text, flags=re.MULTILINE)

    assert case_numbers, "Production case_summary.md contains no cases"
    assert variant_ids, "Production case_summary.md contains no case variants"

    for case_number in case_numbers:
        assert retrieve_case(case_number, case_file=str(case_file))

    for variant_id in variant_ids:
        clinical = retrieve_case(variant_id, case_file=str(case_file))
        criteria = retrieve_MC(variant_id, case_file=str(case_file))
        assert clinical
        assert criteria
        assert "### NEL task" not in clinical
        assert "### Marking criteria" not in clinical
