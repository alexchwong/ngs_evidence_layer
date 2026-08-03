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

    def test_every_phase_receives_operational_definitions(self):
        for phase in (1, 2, 3):
            with self.subTest(phase=phase):
                prompt = BUILD_PROMPTS.render(phase)
                self.assertNotIn("{{PUBLICATION_TYPE_RUBRIC}}", prompt)
                for value in self.allowed:
                    self.assertIn(f"`{value}`:", prompt)

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


if __name__ == "__main__":
    unittest.main()