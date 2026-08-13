import importlib.util
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "build_prompts", ROOT / "scripts" / "build_prompts.py"
)
BUILD_PROMPTS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD_PROMPTS)
MARKER_RE = re.compile(r"{{([A-Z0-9_]+)}}")


class PromptIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vocabulary = json.loads(
            (ROOT / "schema" / "publication_type_vocabulary.json").read_text()
        )
        cls.allowed = [entry["value"] for entry in cls.vocabulary["types"]]
        cls.manifest = BUILD_PROMPTS.load_manifest()["assets"]

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
        for phase in (1, 2, 3, 4, 5):
            with self.subTest(phase=phase):
                prompt = BUILD_PROMPTS.render(phase)
                self.assertTrue(prompt.strip())
                self.assertNotRegex(prompt, r"\{\{[^{}]+\}\}")
        review = BUILD_PROMPTS.render_phase5_review()
        self.assertTrue(review.strip())
        self.assertNotRegex(review, r"\{\{[^{}]+\}\}")

    def test_file_assets_are_injected_whole(self):
        templates = {
            f"phase{phase}": ROOT / "prompts" / "templates" / f"phase{phase}_prompt.md"
            for phase in (1, 2, 3, 4, 5)
        }
        templates["phase5-review"] = (
            ROOT / "prompts" / "templates" / "phase5_review_prompt.md"
        )
        rendered = {
            f"phase{phase}": BUILD_PROMPTS.render(phase) for phase in (1, 2, 3, 4, 5)
        }
        rendered["phase5-review"] = BUILD_PROMPTS.render_phase5_review()
        for name, template_path in templates.items():
            markers = set(MARKER_RE.findall(template_path.read_text(encoding="utf-8")))
            for marker in markers:
                spec = self.manifest[marker]
                if spec.get("type") != "file":
                    continue
                expected = (ROOT / spec["path"]).read_text(encoding="utf-8").rstrip()
                with self.subTest(prompt=name, asset=marker):
                    self.assertIn(expected, rendered[name])

    def test_phase_validation_assets_contain_declared_file_whole(self):
        for phase in (1, 2, 4, 5):
            keyword = f"PHASE{phase}_VALIDATION_BUNDLE"
            content = BUILD_PROMPTS.asset_content(keyword)
            spec = self.manifest[keyword]
            if spec.get("type") == "bundle":
                for relative in spec.get("paths", []):
                    path = ROOT / relative
                    self.assertIn(f"<!-- BEGIN VERBATIM {relative} -->", content)
                    self.assertIn(path.read_text(encoding="utf-8").rstrip(), content)
            else:
                path = ROOT / spec["path"]
                self.assertIn(path.read_text(encoding="utf-8").rstrip(), content)

    def test_phase2_and_phase4_validators_load_canonical_json_assets(self):
        for phase in (2, 4):
            with self.subTest(phase=phase):
                script = (ROOT / "scripts" / "phase_validation" / f"phase{phase}.py").read_text(encoding="utf-8")
                template = (ROOT / "prompts" / "templates" / f"phase{phase}_prompt.md").read_text(encoding="utf-8")
                self.assertIn('load_json_asset("ingestion_package_schema.json")', script)
                self.assertIn('load_json_asset("disease_vocabulary.json")', script)
                self.assertNotIn("PACKAGE_SCHEMA = json.loads(", script)
                self.assertNotIn("UMBRELLA = json.loads(", script)
                self.assertNotIn("{{PACKAGE_SCHEMA}}", template)
                self.assertNotIn("{{DISEASE_VOCABULARY}}", template)
        phase4 = (ROOT / "scripts" / "phase_validation" / "phase4.py").read_text(encoding="utf-8")
        self.assertIn('load_json_asset("review_schema.json")', phase4)
        self.assertNotIn("REVIEW_SCHEMA = json.loads(", phase4)

    def test_phase2_allows_multi_claim_composite_text(self):
        prompt = " ".join(BUILD_PROMPTS.render(2).split())
        self.assertIn(
            "One or more `claim` fragments may jointly support one source assertion",
            prompt,
        )
        self.assertIn(
            "every `claim` fragment contributes to the same source assertion", prompt
        )

    def test_source_disease_alias_prompt_view_is_derived_from_terms(self):
        vocabulary = json.loads(
            (ROOT / "schema" / "disease_vocabulary.json").read_text(encoding="utf-8")
        )
        expected = {
            alias: term["name"]
            for term in vocabulary["terms"]
            for alias in term.get("aliases", [])
        }
        rendered = json.loads(BUILD_PROMPTS.asset_content("SOURCE_DISEASE_ALIASES"))
        self.assertEqual(rendered, expected)
        self.assertEqual(self.manifest["SOURCE_DISEASE_ALIASES"]["type"], "derived")

    def test_all_card_handling_prompts_use_canonical_source_disease_alias_policy(self):
        prompts = {
            f"phase{phase}": BUILD_PROMPTS.render(phase)
            for phase in (2, 3, 4, 5)
        }
        prompts["phase5-review"] = BUILD_PROMPTS.render_phase5_review()
        for name, rendered in prompts.items():
            with self.subTest(prompt=name):
                prompt = " ".join(rendered.split())
                self.assertIn('"clonal haematopoiesis": "CHIP"', rendered)
                self.assertIn('"clonal haemopoiesis": "CHIP"', rendered)
                self.assertIn(
                    "Do not use fuzzy matching, stemming, punctuation substitution, "
                    "semantic inference, or nearest-term mapping.",
                    prompt,
                )
                self.assertNotIn("{{SOURCE_DISEASE_ALIAS_POLICY}}", rendered)
                self.assertNotIn("{{SOURCE_DISEASE_ALIASES}}", rendered)

    def test_phase1_does_not_apply_card_disease_alias_policy(self):
        prompt = BUILD_PROMPTS.render(1)
        self.assertNotIn("Source disease alias policy", prompt)
        self.assertNotIn('"clonal haematopoiesis": "CHIP"', prompt.split(
            "<!-- BEGIN VERBATIM", 1
        )[0])

    def test_phase3_audits_multi_claim_composites_without_auto_failure(self):
        prompt = " ".join(BUILD_PROMPTS.render(3).split())
        self.assertIn(
            "Multiple `claim` fragments are valid when they jointly support one "
            "source assertion.",
            prompt,
        )
        self.assertIn(
            "a `composite_text` bundle supports one coherent source assertion, "
            "uses compatible scope, and contains only necessary fragments",
            prompt,
        )
        self.assertIn(
            "Fail evidence that combines separate findings, populations, analyses, "
            "classifier branches or independently useful conclusions",
            prompt,
        )

    def test_phase3_uses_separate_publication_type_audit_policy(self):
        prompt = BUILD_PROMPTS.render(3)
        expected = (
            ROOT / "prompts" / "assets" / "publication_type_audit_policy.md"
        ).read_text(encoding="utf-8").rstrip()
        self.assertIn(expected, prompt)
        self.assertNotIn("audit_stability", prompt)

    def test_phase3_omits_deterministic_validation_bundle(self):
        prompt = BUILD_PROMPTS.render(3)
        self.assertNotIn("_VALIDATION_BUNDLE}}", prompt)
        self.assertNotIn("<!-- BEGIN VERBATIM scripts/phase_validation/", prompt)
        self.assertNotIn("validation_bundle/scripts/phase_validation/", prompt)
        self.assertNotIn("## Deterministic exit validation", prompt)

    def test_validation_occurs_at_phase2_exit_and_phase4_entry(self):
        phase2 = BUILD_PROMPTS.render(2)
        self.assertIn("## Deterministic exit validation", phase2)
        self.assertIn(
            "python validation_bundle/scripts/phase_validation/phase2.py",
            phase2,
        )
        phase4 = BUILD_PROMPTS.render(4)
        entry = phase4.split("## Entry validation", 1)[1].split(
            "## Mandatory human adjudication", 1
        )[0]
        self.assertIn(
            "python validation_bundle/scripts/phase_validation/phase4.py --review-only",
            entry,
        )
        self.assertIn("Before any adjudication or finalization", entry)

    def test_phase4_embeds_canonical_phase4_validator_verbatim(self):
        rendered = BUILD_PROMPTS.render(4)
        relative = "scripts/phase_validation/phase4.py"
        start_marker = f"<!-- BEGIN VERBATIM {relative} -->\n```python\n"
        end_marker = f"\n```\n<!-- END VERBATIM {relative} -->"
        embedded = rendered.split(start_marker, 1)[1].split(end_marker, 1)[0]
        expected = (ROOT / relative).read_text(encoding="utf-8").rstrip()
        self.assertEqual(embedded, expected)

    def test_phase4_requires_successful_validation_as_final_action(self):
        prompt = BUILD_PROMPTS.render(4)
        self.assertIn(
            "python validation_bundle/scripts/phase_validation/phase4.py",
            prompt,
        )
        self.assertNotIn("validation_bundle/scripts/final_validation.py", prompt)
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
