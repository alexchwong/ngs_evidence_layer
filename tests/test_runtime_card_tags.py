#!/usr/bin/env python3
"""Regression tests for opaque runtime tags across diagnosis and report evidence."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.core import card_tags  # noqa: E402
from scripts.core import rendering as rendering_core  # noqa: E402
from scripts.core import retrieval as retrieval_core  # noqa: E402
from workflows.legacy_v1 import adjudication  # noqa: E402
from workflows.legacy_v1 import rendering as render  # noqa: E402
from workflows.legacy_v1 import retrieval as retrieve  # noqa: E402


def card(card_id, category="diagnosis", disease="MDS"):
    return {
        "card_id": card_id,
        "category": category,
        "genes": ["SF3B1"],
        "diseases": [disease],
        "evidence_tier": "guideline criterion",
        "interpretation": "Fixture interpretation.",
        "locator": "fixture",
        "publication_key": "fixture",
        "paper_nickname": "Fixture",
        "publication_year": 2026,
        "citation_display": "Fixture citation.",
        "citation_incomplete": [],
        "secondary_citation": None,
    }


class RuntimeCardTagTests(unittest.TestCase):
    def setUp(self):
        self.d1 = card("fixture-C0001")
        self.d2 = card("fixture-C0002")
        self.p1 = card("fixture-C0003", category="prognosis")
        self.all_cards = [self.d1, self.d2, self.p1]
        self.tag_map = card_tags.build_card_tags(c["card_id"] for c in self.all_cards)
        self.tags = card_tags.tag_by_id(self.tag_map)
        self.step2 = retrieve.step2(
            self.all_cards,
            ["SF3B1"],
            "MDS",
            [{"fact_id": "F1", "type": "variant", "gene": "SF3B1"}],
            case_major_category="MDS",
        )
        self.step2["card_tags"] = self.tag_map

    def test_diagnostic_markdown_exposes_tags_not_stable_ids(self):
        text = retrieval_core.render_step_markdown(self.step2)
        self.assertIn(f"[card:{self.tags['fixture-C0001']}]", text)
        self.assertIn(f"[card:{self.tags['fixture-C0002']}]", text)
        self.assertNotIn("fixture-C0001", text)
        self.assertNotIn("fixture-C0002", text)

    def test_step3_tags_deconvolve_to_private_stable_ids(self):
        raw = {
            "status": "criteria_met",
            "provisional_disease": "MDS",
            "refined_disease": "MDS",
            "downstream_filter_disease": "MDS",
            "diagnostic_label": "MDS",
            "driven_by": [self.tags["fixture-C0001"]],
            "criterion_assessment": [{
                "criterion": "fixture criterion",
                "required": True,
                "status": "met",
                "card_tags": [self.tags["fixture-C0001"]],
                "case_fact_ids": ["F1"],
            }],
            "reason": "Fixture.",
            "user_review": "automatic",
        }
        normalised = adjudication.normalise_adjudication(
            self.step2, raw, require_completed_review=True
        )
        self.assertEqual(normalised["driven_by"], ["fixture-C0001"])
        self.assertEqual(
            normalised["criterion_assessment"][0]["card_ids"], ["fixture-C0001"]
        )
        self.assertNotIn("card_tags", normalised["criterion_assessment"][0])

    def test_evidence_contains_all_step2_diagnosis_context_with_same_tags(self):
        adjudication = {
            "status": "criteria_met",
            "provisional_disease": "MDS",
            "refined_disease": "MDS",
            "downstream_filter_disease": "MDS",
            "diagnostic_label": "MDS",
            "driven_by": ["fixture-C0001"],
            "criterion_assessment": [],
            "reason": "Fixture.",
            "user_review": "automatic",
        }
        bundle = {
            "step": 4,
            "genes": ["SF3B1"],
            "case_major_category": "MDS",
            "provisional_disease": "MDS",
            "refined_disease": "MDS",
            "diagnostic_adjudication": adjudication,
            "diagnostic_context": [self.d1, self.d2],
            # True Step-4 retrieval deliberately omits unused d2.
            "retrieved": [self.d1, self.p1],
            "runtime_card_tags": self.tag_map,
            "provenance": {
                "corpus_version": "fixture",
                "corpus_sha256": "0" * 64,
                "retrieved_at": "2026-08-14T00:00:00+00:00",
            },
            "suppressed": {"count": 0, "by_disease": {}, "cards": []},
            "not_assessed": [],
        }
        result = render.render(bundle, token_budget=100000)
        subset = card_tags.subset_tag_map(
            self.tag_map, [c["card_id"] for c in result["rendered_cards"]]
        )
        text = rendering_core.evidence_markdown(result, subset)
        self.assertEqual({c["card_id"] for c in bundle["retrieved"]}, {"fixture-C0001", "fixture-C0003"})
        self.assertIn(f"[card:{self.tags['fixture-C0002']}]", text)
        self.assertIn(f"[card:{self.tags['fixture-C0001']}]", text)
        self.assertNotIn("fixture-C0001", text)
        self.assertNotIn("fixture-C0002", text)
        self.assertNotIn("fixture-C0003", text)


if __name__ == "__main__":
    unittest.main()
