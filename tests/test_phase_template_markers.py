from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent.parent

EXPECTED = {
    1: {"PUBLICATION_TYPE_RUBRIC", "REPORTING_RULES", "CENSUS_SCHEMA", "PHASE_VALIDATION_BUNDLE"},
    2: {"SOURCE_DISEASE_ALIAS_POLICY", "REPORTING_RULES", "DISEASE_VOCABULARY", "PACKAGE_SCHEMA", "PHASE_VALIDATION_BUNDLE"},
    3: {"SOURCE_DISEASE_ALIAS_POLICY", "PUBLICATION_TYPE_RUBRIC"},
    4: {"SOURCE_DISEASE_ALIAS_POLICY", "REPORTING_RULES", "DISEASE_VOCABULARY", "PACKAGE_SCHEMA", "PHASE_VALIDATION_BUNDLE"},
    5: {"SOURCE_DISEASE_ALIAS_POLICY", "PHASE5_CHAT_VALIDATION"},
}

class PhaseTemplateMarkerTests(unittest.TestCase):
    def test_template_markers_match_build_prompts(self):
        for phase, expected in EXPECTED.items():
            text = (ROOT / "prompts" / "templates" / f"phase{phase}_prompt.md").read_text(encoding="utf-8")
            markers = set(re.findall(r"{{([^{}]+)}}", text))
            self.assertEqual(markers, expected, f"phase {phase}")
            self.assertNotIn("PHASE_VALIDATION_SCRIPT", markers)
            expected_bundle_count = 1 if phase in (1, 2, 4) else 0
            self.assertEqual(
                text.count("{{PHASE_VALIDATION_BUNDLE}}"), expected_bundle_count
            )

    def test_phase5_review_uses_source_disease_alias_policy_marker(self):
        text = (
            ROOT / "prompts" / "templates" / "phase5_review_prompt.md"
        ).read_text(encoding="utf-8")
        markers = set(re.findall(r"{{([^{}]+)}}", text))
        self.assertEqual(markers, {"SOURCE_DISEASE_ALIAS_POLICY"})

    def test_source_disease_alias_policy_partial_uses_alias_data_marker(self):
        text = (
            ROOT / "prompts" / "templates" / "source_disease_alias_policy.md"
        ).read_text(encoding="utf-8")
        markers = set(re.findall(r"{{([^{}]+)}}", text))
        self.assertEqual(markers, {"SOURCE_DISEASE_ALIASES"})

if __name__ == "__main__":
    unittest.main()
