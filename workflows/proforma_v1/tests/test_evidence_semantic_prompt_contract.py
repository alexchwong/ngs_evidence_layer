from __future__ import annotations

import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parents[1]
PROMPTS = HERE / "prompts"
REVIEWED = PROMPTS / "default_reviewed"
DIAGNOSIS = PROMPTS / "evidence"


class EvidenceSemanticPromptContractTests(unittest.TestCase):
    """Freeze the semantic evidence contract without adding a medical validator."""

    def _text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8").lower()

    def test_generic_match_audit_and_adjudication_require_complete_proposition_support(self):
        for name in ("evidence_match.md", "evidence_audit.md", "evidence_adjudicate.md"):
            with self.subTest(prompt=name):
                text = self._text(PROMPTS / name)
                self.assertIn("complete", text)
                self.assertIn("proposition", text)
                self.assertIn("material restriction", text)
                self.assertIn("ordinary paraphrase", text)
                self.assertIn("atomic proposition", text)
                self.assertIn("multiple independent propositions", text)

    def test_generic_contract_covers_known_semantic_failure_classes(self):
        required_dimensions = (
            "allelic state",
            "variant class",
            "threshold",
            "disease/subtype",
            "therapy or exposure context",
            "co-mutation or exclusion context",
            "cytogenetic context",
            "population",
            "endpoint",
            "framework/source attribution",
            "polarity",
            "uncertainty",
            "evidentiary strength",
        )
        for name in ("evidence_match.md", "evidence_audit.md", "evidence_adjudicate.md"):
            text = self._text(PROMPTS / name)
            for dimension in required_dimensions:
                with self.subTest(prompt=name, dimension=dimension):
                    self.assertIn(dimension, text)

    def test_matcher_rejects_narrower_or_differently_scoped_support(self):
        text = self._text(PROMPTS / "evidence_match.md")
        self.assertIn("narrower", text)
        self.assertIn("differently scoped", text)
        self.assertIn("supporting only a fragment", text)
        self.assertNotIn("do not require one card to support the whole fact", text)

    def test_auditor_treats_material_scope_or_strength_mismatch_as_failure(self):
        text = self._text(PROMPTS / "evidence_audit.md")
        self.assertIn("failed card, not a warning", text)
        self.assertIn("supporting only a fragment", text)
        self.assertIn("card_is_element_of_reason", text)
        # Keep the existing compact schema surface; semantic dimensions stay prompt-side.
        for forbidden_field in (
            "allelic_state:", "variant_class:", "claim_scope:",
            "evidence_strength:", "entailment_dimensions:",
        ):
            self.assertNotIn(forbidden_field, text)

    def test_adjudicator_cannot_restore_partial_support(self):
        text = self._text(PROMPTS / "evidence_adjudicate.md")
        self.assertIn("supporting only a fragment", text)
        self.assertIn("include the card only when it supports that complete proposition", text)
        self.assertNotIn("a card need not support the whole reason", text)

    def test_generic_evidence_contract_is_not_tp53_or_framework_specific(self):
        combined = "\n".join(
            self._text(PROMPTS / name)
            for name in ("evidence_match.md", "evidence_audit.md", "evidence_adjudicate.md")
        )
        for forbidden in ("tp53", "ipss-m", "r175", "biallelic tp53", "multihit tp53"):
            with self.subTest(term=forbidden):
                self.assertNotIn(forbidden, combined)

    def test_diagnosis_policy_uses_same_qualifier_preservation_standard(self):
        for name in ("diagnosis_match.md", "diagnosis_audit.md", "diagnosis_adjudicate.md"):
            with self.subTest(prompt=name):
                text = self._text(DIAGNOSIS / name)
                self.assertIn("material restrictions", text)
                self.assertIn("allelic state", text)
                self.assertIn("variant class", text)
                self.assertIn("threshold", text)
                self.assertIn("framework/classification system", text)
                self.assertIn("ordinary paraphrase", text)

    def test_reviewed_ptbg_owners_receive_light_qualifier_preservation_guard(self):
        for name in ("prognosis.md", "treatment.md", "biomarker.md", "germline.md"):
            with self.subTest(prompt=name):
                text = self._text(REVIEWED / name)
                self.assertIn("preserve material restrictions", text)
                self.assertIn("do not broaden a rule", text)
                self.assertIn("allelic state", text)
                self.assertIn("evidentiary strength", text)


if __name__ == "__main__":
    unittest.main()
