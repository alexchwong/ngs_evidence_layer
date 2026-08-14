import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "phase1_validation", ROOT / "scripts" / "phase_validation" / "phase1.py"
)
PHASE1 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PHASE1)


class Phase1CategoryScopeValidationTests(unittest.TestCase):
    def census(self, **updates):
        doc = {
            "schema_version": "3.2",
            "paper_id": "11111111-1111-1111-1111-111111111111",
            "census_date": "2026-08-14",
            "census_model": "test",
            "publication_type": "guideline",
            "publication_type_basis": "Guideline structure.",
            "entries": [
                {
                    "claim_id": "Q001",
                    "genes": [],
                    "category": "diagnosis",
                    "locator": "p1",
                    "summary": "Diagnosis claim",
                }
            ],
            "validation_unresolved": [],
        }
        doc.update(updates)
        return doc

    def test_scope_is_optional_for_backward_compatibility(self):
        self.assertEqual(PHASE1.validate_census(self.census()), [])

    def test_restricted_scope_accepts_in_scope_entries(self):
        self.assertEqual(
            PHASE1.validate_census(self.census(category_scope=["diagnosis"])), []
        )

    def test_restricted_scope_rejects_entry_outside_scope(self):
        census = self.census(category_scope=["biomarker"])
        errors = PHASE1.validate_census(census)
        self.assertTrue(any("outside census category_scope" in error for error in errors))

    def test_scope_rejects_unknown_or_duplicate_categories(self):
        unknown = PHASE1.validate_census(self.census(category_scope=["unknown"]))
        duplicate = PHASE1.validate_census(
            self.census(category_scope=["diagnosis", "diagnosis"])
        )
        self.assertTrue(any("schema" in error for error in unknown))
        self.assertTrue(any("schema" in error for error in duplicate))


if __name__ == "__main__":
    unittest.main()
