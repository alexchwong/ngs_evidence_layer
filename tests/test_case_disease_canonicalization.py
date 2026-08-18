#!/usr/bin/env python3
"""Tests for Step-1 case-major categories and free-text provisional diagnoses."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import vocab  # noqa: E402
from scripts.core import retrieval as retrieval_core  # noqa: E402
from workflows.legacy_v1 import retrieval as retrieve  # noqa: E402


class CaseMajorCategoryTests(unittest.TestCase):
    def _case_input(self, category, provisional_disease, genes=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "case-input.json"
        path.write_text(json.dumps({
            "case_major_category": category,
            "provisional_disease": provisional_disease,
            "genes": genes or [],
            "case_facts": [],
        }), encoding="utf-8")
        return path

    def test_specific_provisional_wording_is_preserved(self):
        wording = "myelodysplastic neoplasm with increased blasts-2 (MDS-IB2)"
        result = retrieval_core.validate_case_input(self._case_input("MDS", wording))
        self.assertEqual(result["case_major_category"], "MDS")
        self.assertEqual(result["provisional_disease"], wording)

    def test_case_major_category_must_be_allowed(self):
        with self.assertRaisesRegex(ValueError, "invalid value"):
            retrieval_core.validate_case_input(self._case_input("not-a-category", "MDS-IB2"))

    def test_every_canonical_disease_maps_to_a_major_category(self):
        self.assertEqual(len(vocab.DISEASES), 162)
        for disease in vocab.DISEASES:
            with self.subTest(disease=disease):
                categories = vocab.case_major_categories_for_disease(disease)
                self.assertTrue(categories)
                self.assertTrue(set(categories) <= vocab.CASE_MAJOR_CATEGORY_SET)

    def test_mds_ib2_case_retrieval_no_longer_requires_alias(self):
        wording = "myelodysplastic neoplasm with increased blasts-2 (MDS-IB2)"
        case = retrieval_core.validate_case_input(self._case_input("MDS", wording, ["TP53"]))
        result = retrieve.step2(
            [], case["genes"], case["provisional_disease"], case["case_facts"],
            case_major_category=case["case_major_category"],
        )
        self.assertEqual(result["provisional_disease"], wording)
        self.assertEqual(result["case_major_category"], "MDS")
        self.assertEqual(result["allowed_refined_diseases"], ["MDS"])

    def test_case_only_no_malignancy_still_works(self):
        result = retrieval_core.validate_case_input(self._case_input(
            vocab.NO_HAEMATOLOGICAL_MALIGNANCY,
            vocab.NO_HAEMATOLOGICAL_MALIGNANCY,
        ))
        self.assertEqual(result["case_major_category"], vocab.NO_HAEMATOLOGICAL_MALIGNANCY)

    def test_no_malignancy_still_rejects_reported_variants(self):
        with self.assertRaisesRegex(ValueError, "requires no reported variants"):
            retrieval_core.validate_case_input(self._case_input(
                vocab.NO_HAEMATOLOGICAL_MALIGNANCY,
                vocab.NO_HAEMATOLOGICAL_MALIGNANCY,
                ["DNMT3A"],
            ))


if __name__ == "__main__":
    unittest.main()
