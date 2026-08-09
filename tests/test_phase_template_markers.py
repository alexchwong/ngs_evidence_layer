from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent.parent

EXPECTED = {
    1: {"PUBLICATION_TYPE_RUBRIC", "REPORTING_RULES", "CENSUS_SCHEMA", "PHASE_VALIDATION_BUNDLE"},
    2: {"REPORTING_RULES", "DISEASE_VOCABULARY", "PACKAGE_SCHEMA", "PHASE_VALIDATION_BUNDLE"},
    3: {"PUBLICATION_TYPE_RUBRIC"},
    4: {"REPORTING_RULES", "DISEASE_VOCABULARY", "PACKAGE_SCHEMA", "PHASE_VALIDATION_BUNDLE"},
}

class PhaseTemplateMarkerTests(unittest.TestCase):
    def test_template_markers_match_build_prompts(self):
        for phase, expected in EXPECTED.items():
            text = (ROOT / "prompts" / "templates" / f"phase{phase}_prompt.md").read_text(encoding="utf-8")
            markers = set(re.findall(r"{{([^{}]+)}}", text))
            self.assertEqual(markers, expected, f"phase {phase}")
            self.assertNotIn("PHASE_VALIDATION_SCRIPT", markers)
            expected_bundle_count = 0 if phase == 3 else 1
            self.assertEqual(
                text.count("{{PHASE_VALIDATION_BUNDLE}}"), expected_bundle_count
            )

if __name__ == "__main__":
    unittest.main()
