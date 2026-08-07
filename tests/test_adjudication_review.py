#!/usr/bin/env python3
"""Tests for the mandatory Step 3 human-review gate."""
import argparse
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import render  # noqa: E402
import retrieve  # noqa: E402


class AdjudicationReviewTests(unittest.TestCase):
    def setUp(self):
        self.card = {
            "card_id": "classifier-C0001",
            "category": "diagnosis",
            "genes": ["SF3B1"],
            "diseases": ["MDS"],
            "evidence_tier": "guideline criterion",
            "interpretation": "Fixture diagnostic criterion.",
            "locator": "fixture",
            "publication_key": "classifier",
            "publication_year": 2026,
            "citation_display": "Classifier fixture",
            "citation_incomplete": [],
            "secondary_citation": None,
        }
        self.step2 = retrieve.step2(
            [self.card],
            ["SF3B1"],
            "myeloid neoplasm, unspecified",
            [{"fact_id": "F-SF3B1", "type": "variant", "gene": "SF3B1"}],
        )
        self.step2["corpus"] = {"path": "corpus.json", "index": "index.json"}
        self.pending = {
            "status": "criteria_met",
            "provisional_disease": "myeloid neoplasm, unspecified",
            "refined_disease": "MDS",
            "downstream_filter_disease": "MDS",
            "diagnostic_label": "MDS-SF3B1",
            "driven_by": ["classifier-C0001"],
            "criterion_assessment": [{
                "criterion": "SF3B1 criterion",
                "required": True,
                "status": "met",
                "card_ids": ["classifier-C0001"],
                "case_fact_ids": ["F-SF3B1"],
            }],
            "reason": "The supplied SF3B1 result satisfies the cited criterion.",
            "user_review": {
                "decision": "pending",
                "diagnostic_label": None,
                "refined_disease": None,
            },
        }

    def test_pending_review_is_valid_during_step3_but_blocks_step4(self):
        retrieve.validate_adjudication(self.step2, self.pending)
        with self.assertRaisesRegex(ValueError, "Step 4 is blocked"):
            retrieve.validate_adjudication(
                self.step2,
                self.pending,
                require_completed_review=True,
            )

    def test_agreement_copies_model_diagnosis_exactly(self):
        adjudication = copy.deepcopy(self.pending)
        adjudication["user_review"] = {
            "decision": "agree",
            "diagnostic_label": "MDS-SF3B1",
            "refined_disease": "MDS",
        }
        retrieve.validate_adjudication(
            self.step2,
            adjudication,
            require_completed_review=True,
        )

        adjudication["user_review"]["diagnostic_label"] = "MDS, SF3B1-mutated"
        with self.assertRaisesRegex(ValueError, "must copy the model"):
            retrieve.validate_adjudication(
                self.step2,
                adjudication,
                require_completed_review=True,
            )

    def test_disagreement_may_replace_the_downstream_diagnosis(self):
        adjudication = copy.deepcopy(self.pending)
        adjudication["downstream_filter_disease"] = "AML"
        adjudication["user_review"] = {
            "decision": "disagree",
            "diagnostic_label": "AML with myelodysplasia-related changes",
            "refined_disease": "AML",
        }
        retrieve.validate_adjudication(
            self.step2,
            adjudication,
            require_completed_review=True,
        )
        self.assertEqual(adjudication["refined_disease"], "MDS")
        self.assertEqual(adjudication["diagnostic_label"], "MDS-SF3B1")
        self.assertEqual(adjudication["downstream_filter_disease"], "AML")

    def test_disagreement_requires_valid_user_diagnosis(self):
        adjudication = copy.deepcopy(self.pending)
        adjudication["user_review"] = {
            "decision": "disagree",
            "diagnostic_label": None,
            "refined_disease": "MDS",
        }
        with self.assertRaisesRegex(ValueError, "requires the user's integrated"):
            retrieve.validate_adjudication(
                self.step2,
                adjudication,
                require_completed_review=True,
            )

        adjudication["user_review"] = {
            "decision": "disagree",
            "diagnostic_label": "Unsupported category",
            "refined_disease": "not-a-vocabulary-disease",
        }
        adjudication["downstream_filter_disease"] = "not-a-vocabulary-disease"
        with self.assertRaisesRegex(ValueError, "adjudication downstream_filter_disease 'not-a-vocabulary-disease' is outside the case disease vocabulary"):
            retrieve.validate_adjudication(
                self.step2,
                adjudication,
                require_completed_review=True,
            )

    def test_run_full_uses_the_user_reviewed_disease(self):
        adjudication = copy.deepcopy(self.pending)
        adjudication["downstream_filter_disease"] = "AML"
        adjudication["user_review"] = {
            "decision": "disagree",
            "diagnostic_label": "AML with a user-supplied integrated label",
            "refined_disease": "AML",
        }
        aml_card = {
            **self.card,
            "card_id": "classifier-C0002",
            "category": "prognosis",
            "diseases": ["AML"],
            "interpretation": "AML-specific evidence.",
        }
        mds_card = {
            **self.card,
            "card_id": "classifier-C0003",
            "category": "prognosis",
            "diseases": ["MDS"],
            "interpretation": "MDS-specific evidence.",
        }
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            step2_path = tmp / "step2.json"
            adjudication_path = tmp / "adjudication.json"
            step2_path.write_text(json.dumps(self.step2), encoding="utf-8")
            adjudication_path.write_text(json.dumps(adjudication), encoding="utf-8")
            args = argparse.Namespace(
                diagnosis_result=step2_path,
                adjudication_result=adjudication_path,
                corpus=None,
                index=None,
                genes=None,
            )
            with mock.patch.object(
                retrieve,
                "load_corpus",
                return_value=({}, {}, "0" * 64),
            ), mock.patch.object(
                retrieve,
                "flatten",
                return_value=[self.card, aml_card, mds_card],
            ):
                result = retrieve.run_full(args)
        retrieved_ids = {card["card_id"] for card in result["retrieved"]}
        self.assertEqual(result["refined_disease"], "AML")
        self.assertIn("classifier-C0002", retrieved_ids)
        self.assertNotIn("classifier-C0003", retrieved_ids)

    def test_run_full_rejects_pending_before_corpus_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            step2_path = tmp / "step2.json"
            adjudication_path = tmp / "adjudication.json"
            step2_path.write_text(json.dumps(self.step2), encoding="utf-8")
            adjudication_path.write_text(json.dumps(self.pending), encoding="utf-8")
            args = argparse.Namespace(
                diagnosis_result=step2_path,
                adjudication_result=adjudication_path,
                corpus=None,
                index=None,
                genes=None,
            )
            with mock.patch.object(
                retrieve,
                "load_corpus",
                side_effect=AssertionError("corpus must not be read"),
            ):
                with self.assertRaisesRegex(ValueError, "Step 4 is blocked"):
                    retrieve.run_full(args)

    def test_render_distinguishes_model_and_user_diagnoses(self):
        adjudication = copy.deepcopy(self.pending)
        adjudication["downstream_filter_disease"] = "AML"
        adjudication["user_review"] = {
            "decision": "disagree",
            "diagnostic_label": "AML with myelodysplasia-related changes",
            "refined_disease": "AML",
        }
        bundle = {
            "step": 4,
            "genes": ["SF3B1"],
            "provisional_disease": self.step2["provisional_disease"],
            "refined_disease": "AML",
            "diagnostic_adjudication": adjudication,
            "retrieved": [],
            "suppressed": {"count": 0, "by_disease": {}, "cards": []},
            "not_assessed": [],
            "provenance": {
                "corpus_version": "test",
                "corpus_sha256": "0" * 64,
                "retrieved_at": "2026-01-01T00:00:00+00:00",
            },
        }
        text = render.render(bundle)["text"]
        self.assertIn("Source-supported diagnostic label: MDS-SF3B1", text)
        self.assertIn(
            "User-reviewed integrated diagnosis: AML with myelodysplasia-related changes",
            text,
        )
        self.assertIn("User review revised the downstream diagnosis from MDS to AML.", text)


if __name__ == "__main__":
    unittest.main()
