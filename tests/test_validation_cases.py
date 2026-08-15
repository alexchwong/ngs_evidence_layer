from pathlib import Path
import re
import tempfile
import unittest

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


class ValidationCaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.synthetic_case_file = Path(self.temp_dir.name) / "case_summary.md"
        self.synthetic_case_file.write_text(SYNTHETIC_CASES, encoding="utf-8")

    def test_stem_only(self):
        self.assertEqual(
            retrieve_case("7", case_file=str(self.synthetic_case_file)),
            "Shared clinical stem for case 7.",
        )

    def test_stem_plus_variant_excludes_task_and_marking_criteria(self):
        result = retrieve_case("7A", case_file=str(self.synthetic_case_file))

        self.assertEqual(
            result,
            "Shared clinical stem for case 7.\n\n"
            "Variant A clinical information with GENE_A.",
        )
        self.assertNotIn("NEL task", result)
        self.assertNotIn("Task text", result)
        self.assertNotIn("Marking criteria", result)
        self.assertNotIn("Criterion", result)

    def test_marking_criteria_only(self):
        result = retrieve_MC("7A", case_file=str(self.synthetic_case_file))

        self.assertEqual(
            result,
            "- **R1C1:** Criterion for variant A.\n"
            "- **R2C1:** Second criterion for variant A.",
        )
        self.assertNotIn("Clinical information", result)
        self.assertNotIn("GENE_A", result)
        self.assertNotIn("NEL task", result)

    def test_case_identifier_is_case_insensitive(self):
        case_file = str(self.synthetic_case_file)
        self.assertEqual(
            retrieve_case("7c", case_file=case_file),
            retrieve_case("7C", case_file=case_file),
        )
        self.assertEqual(
            retrieve_MC("7c", case_file=case_file),
            retrieve_MC("7C", case_file=case_file),
        )

    def test_retrieve_case_rejects_malformed_identifiers(self):
        for case_id in ["", "A7", "7AA", "7-A", "case 7A"]:
            with self.subTest(case_id=case_id), self.assertRaises(ValueError):
                retrieve_case(case_id, case_file=str(self.synthetic_case_file))

    def test_retrieve_mc_requires_variant_identifier(self):
        for case_id in ["7", "", "A7", "7AA"]:
            with self.subTest(case_id=case_id), self.assertRaises(ValueError):
                retrieve_MC(case_id, case_file=str(self.synthetic_case_file))

    def test_missing_case_raises_key_error(self):
        with self.assertRaisesRegex(KeyError, "Case 99 not found"):
            retrieve_case("99", case_file=str(self.synthetic_case_file))

    def test_missing_variant_raises_key_error(self):
        with self.assertRaisesRegex(KeyError, "Case variant 7B not found"):
            retrieve_case("7B", case_file=str(self.synthetic_case_file))

    def test_missing_marking_criteria_raises_key_error(self):
        path = Path(self.temp_dir.name) / "missing_criteria.md"
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

        with self.assertRaisesRegex(
            KeyError, "Marking criteria for case variant 1A not found"
        ):
            retrieve_MC("1A", case_file=str(path))

    def test_missing_shared_stem_raises_value_error(self):
        path = Path(self.temp_dir.name) / "missing_stem.md"
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

        with self.assertRaisesRegex(ValueError, "Case 1 has no shared stem"):
            retrieve_case("1", case_file=str(path))

    def test_production_case_summary_is_structurally_retrievable(self):
        """Integration check: validate structure without asserting clinical content."""
        case_file = Path(__file__).resolve().parents[1] / "validation" / "case_summary.md"
        text = case_file.read_text(encoding="utf-8")

        case_numbers = re.findall(r"^# Case (\d+)\b", text, flags=re.MULTILINE)
        variant_ids = re.findall(r"^## Case (\d+[A-Z])\b", text, flags=re.MULTILINE)

        self.assertTrue(case_numbers, "Production case_summary.md contains no cases")
        self.assertTrue(variant_ids, "Production case_summary.md contains no case variants")

        for case_number in case_numbers:
            with self.subTest(case_number=case_number):
                self.assertTrue(retrieve_case(case_number, case_file=str(case_file)))

        for variant_id in variant_ids:
            with self.subTest(variant_id=variant_id):
                clinical = retrieve_case(variant_id, case_file=str(case_file))
                criteria = retrieve_MC(variant_id, case_file=str(case_file))
                self.assertTrue(clinical)
                self.assertTrue(criteria)
                self.assertNotIn("### NEL task", clinical)
                self.assertNotIn("### Marking criteria", clinical)
