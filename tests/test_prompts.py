import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "build_prompts", ROOT / "scripts" / "build_prompts.py"
)
BUILD_PROMPTS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD_PROMPTS)


class PublicationTypePromptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vocabulary = json.loads(
            (ROOT / "schema" / "publication_type_vocabulary.json").read_text()
        )
        cls.allowed = [entry["value"] for entry in cls.vocabulary["types"]]

    def test_publication_type_vocabulary_matches_both_schemas(self):
        census = json.loads((ROOT / "schema" / "census_schema.json").read_text())
        package = json.loads(
            (ROOT / "schema" / "ingestion_package_schema.json").read_text()
        )
        self.assertEqual(
            census["properties"]["publication_type"]["enum"], self.allowed
        )
        self.assertEqual(
            package["properties"]["publication_type"]["enum"], self.allowed
        )
        self.assertEqual(BUILD_PROMPTS.vocabulary_errors(), [])

    def test_assignment_and_audit_phases_receive_operational_definitions(self):
        for phase in (1, 3):
            with self.subTest(phase=phase):
                prompt = BUILD_PROMPTS.render(phase)
                self.assertNotIn("{{PUBLICATION_TYPE_RUBRIC}}", prompt)
                for value in self.allowed:
                    self.assertIn(f"`{value}`:", prompt)

        phase2 = BUILD_PROMPTS.render(2)
        self.assertNotIn("### Publication-type taxonomy", phase2)
        self.assertIn("Phase 2 does not review", phase2)

    def test_only_phase3_receives_audit_stability_policy(self):
        phrase = "Pass when the package value is defensible"
        self.assertNotIn(phrase, BUILD_PROMPTS.render(1))
        self.assertNotIn(phrase, BUILD_PROMPTS.render(2))
        self.assertIn(phrase, BUILD_PROMPTS.render(3))

    def test_phase3_prevents_ambiguous_reclassification(self):
        prompt = BUILD_PROMPTS.render(3)
        normalized = " ".join(prompt.split())
        self.assertIn(
            "When evidence is mixed or multiple values remain defensible, retain and pass the package value.",
            normalized,
        )
        self.assertIn(
            "Fail only when the package value clearly does not satisfy its definition and exactly one different allowed value is better supported.",
            normalized,
        )
        self.assertIn(
            "For an ICC-style expert classification paper, retain `consensus statement`",
            normalized,
        )

    def test_publisher_labels_are_not_additional_values(self):
        self.assertNotIn("special report", self.allowed)
        prompt = BUILD_PROMPTS.render(3)
        normalized = " ".join(prompt.split())
        self.assertIn(
            'Journal labels such as "special report" may be cited in the verdict basis but are never valid `auditor_value` values.',
            normalized,
        )
        self.assertIn('"auditor_value": "<one allowed taxonomy value>"', prompt)

    def test_phase2_requires_minimal_sufficient_evidence_bundles(self):
        prompt = BUILD_PROMPTS.render(2)
        normalized = " ".join(prompt.split())

        self.assertIn("minimal sufficient evidence bundle", normalized)
        self.assertIn(
            '"Minimal" means exclude unrelated material, not choose the shortest fragment',
            normalized,
        )
        self.assertIn(
            "Its sole fragment has role `claim` and may contain multiple contiguous sentences.",
            normalized,
        )
        self.assertIn(
            "freeze the complete candidate evidence bundle before drafting the interpretation",
            normalized,
        )

    def test_phase2_checks_evidence_boundaries_and_atomic_support(self):
        prompt = BUILD_PROMPTS.render(2)
        normalized = " ".join(prompt.split())

        self.assertIn("### Evidence bundle method", prompt)
        self.assertIn(
            "For every `claim` fragment, inspect the sentence immediately before and after it",
            normalized,
        )
        self.assertIn(
            "decompose the proposed interpretation privately into atomic assertions",
            normalized,
        )
        self.assertIn(
            "If any assertion has no supporting span, expand the bundle, narrow the interpretation, split the card, or omit it.",
            normalized,
        )
        self.assertIn("Never join non-contiguous excerpts with ellipses", normalized)

    def test_phase3_audits_relationships_without_receiving_phase2_authoring_method(self):
        phase3 = BUILD_PROMPTS.render(3)

        self.assertNotIn("### Evidence bundle method", phase3)
        self.assertNotIn("minimal sufficient evidence bundle", phase3)
        self.assertNotIn("atomic assertions", phase3)
        self.assertIn("**Scope governance:**", phase3)
        self.assertIn("**Table reconstruction:**", phase3)
        self.assertIn("**No evidence laundering:**", phase3)

    def test_phase2_requires_human_adjudication_before_rework(self):
        prompt = BUILD_PROMPTS.render(2)
        normalized = " ".join(prompt.split())

        self.assertIn("### Mandatory human adjudication before rework", prompt)
        self.assertIn("the exact paired evidence bundle", normalized)
        self.assertIn("the current card interpretation", normalized)
        self.assertIn("Phase 3's exact failure reason", normalized)
        self.assertIn("suggested_action.category", normalized)
        self.assertIn("affirm Phase 3's suggested action or provide alternate amendment instructions", normalized)
        self.assertIn("Do not create any file in the same response", normalized)

    def test_phase2_requires_both_matching_rework_artefacts(self):
        prompt = BUILD_PROMPTS.render(2)
        normalized = " ".join(prompt.split())

        self.assertIn("require both `paper.review-NNN.json` and its exact prior `paper.provisional-NNN.json`", normalized)
        self.assertIn("their filename rounds, `round` values, and `paper_id` values must match", normalized)
        self.assertIn("neither rework artefact is optional", normalized)
        self.assertIn("missing, mismatched, or malformed rework artefact stops the session", normalized)
        self.assertNotIn("an optional review file", normalized)

    def test_publication_type_is_verified_once_by_phase3(self):
        phase1 = " ".join(BUILD_PROMPTS.render(1).split())
        phase2 = " ".join(BUILD_PROMPTS.render(2).split())
        phase3 = " ".join(BUILD_PROMPTS.render(3).split())

        self.assertIn("publication-type verification belongs only to Phase 3", phase1)
        self.assertIn("publication_type_verified_by_phase3` to `false", phase2)
        self.assertIn("When `publication_type_verified_by_phase3` is already `true`, do not review", phase3)
        self.assertIn('"verified_by_phase3": true', phase3)

    def test_escalates_to_is_absent_from_active_phase_prompts(self):
        self.assertNotIn("escalates_to", BUILD_PROMPTS.render(2))
        self.assertNotIn("escalates_to", BUILD_PROMPTS.render(3))


if __name__ == "__main__":
    unittest.main()