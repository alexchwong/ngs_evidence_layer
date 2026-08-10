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


class PromptIntegrationTests(unittest.TestCase):
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

    def test_all_phase_templates_render_without_unresolved_markers(self):
        for phase in (1, 2, 3, 4):
            with self.subTest(phase=phase):
                prompt = BUILD_PROMPTS.render(phase)
                self.assertTrue(prompt.strip())
                self.assertNotRegex(prompt, r"\{\{[^{}]+\}\}")

    def test_phase2_allows_multi_claim_composite_text(self):
        prompt = " ".join(BUILD_PROMPTS.render(2).split())
        self.assertIn(
            "use one or more `claim` fragments for substantive prose", prompt
        )
        self.assertIn(
            "every `claim` fragment contributes to the same source assertion", prompt
        )
        self.assertNotIn(
            "Include one `claim` fragment and only necessary", prompt
        )

    def test_all_card_handling_prompts_use_canonical_source_disease_alias_policy(self):
        prompts = {
            f"phase{phase}": BUILD_PROMPTS.render(phase)
            for phase in (2, 3, 4, 5)
        }
        prompts["phase5-review"] = BUILD_PROMPTS.render_phase5_review()
        for name, rendered in prompts.items():
            with self.subTest(prompt=name):
                prompt = " ".join(rendered.split())
                self.assertIn("`clonal haematopoiesis` → `CHIP`", prompt)
                self.assertIn("`clonal haemopoiesis` → `CHIP`", prompt)
                self.assertIn(
                    "Do not use fuzzy matching, stemming, punctuation substitution, "
                    "semantic inference, or nearest-term mapping.",
                    prompt,
                )
                self.assertNotIn("{{SOURCE_DISEASE_ALIAS_POLICY}}", rendered)

    def test_source_disease_alias_policy_partial_renders_canonical_alias_data(self):
        policy = BUILD_PROMPTS.source_disease_alias_policy()
        self.assertIn("`clonal haematopoiesis` → `CHIP`", policy)
        self.assertIn("`clonal haemopoiesis` → `CHIP`", policy)
        self.assertNotRegex(policy, r"\{\{[^{}]+\}\}")

    def test_phase1_does_not_apply_card_disease_alias_policy(self):
        prompt = BUILD_PROMPTS.render(1)
        self.assertNotIn("Source disease alias policy", prompt)
        self.assertNotIn("`clonal haematopoiesis` → `CHIP`", prompt)

    def test_phase3_audits_multi_claim_composites_without_auto_failure(self):
        prompt = " ".join(BUILD_PROMPTS.render(3).split())
        self.assertIn("Multiple `claim` fragments are valid.", prompt)
        self.assertIn("**Single assertion:**", prompt)
        self.assertIn("**Necessary composition:**", prompt)
        self.assertIn(
            "Do not use `evidence_relationship` solely because a valid bundle "
            "contains multiple substantive `claim` fragments.",
            prompt,
        )

    def test_phase3_omits_deterministic_validation_bundle(self):
        prompt = BUILD_PROMPTS.render(3)
        self.assertNotIn("{{PHASE_VALIDATION_BUNDLE}}", prompt)
        self.assertNotIn("<!-- BEGIN VERBATIM scripts/final_validation.py -->", prompt)
        self.assertNotIn("validation_bundle/scripts/final_validation.py", prompt)
        self.assertNotIn("## Deterministic exit validation", prompt)

    def test_validation_occurs_at_phase2_exit_and_phase4_entry(self):
        phase2 = BUILD_PROMPTS.render(2)
        self.assertIn("## Deterministic exit validation", phase2)
        self.assertIn(
            "python validation_bundle/scripts/final_validation.py --phase 2",
            phase2,
        )

        phase4 = BUILD_PROMPTS.render(4)
        entry = phase4.split("## Entry validation", 1)[1].split(
            "## Mandatory human adjudication", 1
        )[0]
        self.assertIn(
            "python validation_bundle/scripts/final_validation.py --phase 3",
            entry,
        )
        self.assertIn("Before any adjudication or finalization", entry)

    def test_phase4_embeds_canonical_final_validator_verbatim(self):
        rendered = BUILD_PROMPTS.render(4)
        start_marker = "<!-- BEGIN VERBATIM scripts/final_validation.py -->\n```python\n"
        end_marker = "\n```\n<!-- END VERBATIM scripts/final_validation.py -->"
        embedded = rendered.split(start_marker, 1)[1].split(end_marker, 1)[0]
        expected = (ROOT / "scripts" / "final_validation.py").read_text(
            encoding="utf-8"
        ).rstrip()
        self.assertEqual(embedded, expected)

    def test_phase4_requires_successful_validation_as_final_action(self):
        prompt = BUILD_PROMPTS.render(4)
        self.assertIn(
            "python validation_bundle/scripts/final_validation.py --phase 4",
            prompt,
        )
        self.assertNotIn("python final_validation.py --phase 4", prompt)
        self.assertNotIn("python scripts/final_validation.py", prompt)
        self.assertIn(
            "The final action before returning `paper.final.json` must be a "
            "successful run",
            " ".join(prompt.split()),
        )
        self.assertIn(
            "Do not edit `paper.final.json` after the successful run.",
            " ".join(prompt.split()),
        )


if __name__ == "__main__":
    unittest.main()
