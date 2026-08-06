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
        self.assertIn("python final_validation.py --phase 4", prompt)
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
