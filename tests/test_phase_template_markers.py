import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = json.loads(
    (ROOT / "prompts" / "assets" / "manifest.json").read_text(encoding="utf-8")
)["assets"]
MARKER_RE = re.compile(r"{{([^{}]+)}}")


class PhaseTemplateMarkerTests(unittest.TestCase):
    def template_markers(self, path):
        return set(MARKER_RE.findall(path.read_text(encoding="utf-8")))

    def test_every_template_marker_exists_in_manifest(self):
        templates = sorted((ROOT / "prompts" / "templates").glob("phase*_prompt.md"))
        self.assertTrue(templates)
        for path in templates:
            with self.subTest(template=path.name):
                markers = self.template_markers(path)
                self.assertTrue(markers)
                self.assertEqual(markers - set(MANIFEST), set())

    def test_every_file_asset_exists(self):
        for keyword, spec in MANIFEST.items():
            if spec.get("type") != "file":
                continue
            with self.subTest(asset=keyword):
                path = ROOT / spec["path"]
                self.assertTrue(path.is_file(), spec["path"])

    def test_every_bundle_asset_resolves_files(self):
        for keyword, spec in MANIFEST.items():
            if spec.get("type") != "bundle":
                continue
            with self.subTest(asset=keyword):
                resolved = []
                for relative in spec.get("paths", []):
                    path = ROOT / relative
                    self.assertTrue(path.is_file(), relative)
                    resolved.append(path)
                for pattern in spec.get("globs", []):
                    matches = sorted(ROOT.glob(pattern))
                    self.assertTrue(matches, pattern)
                    resolved.extend(matches)
                self.assertTrue(resolved)

    def test_phase_specific_validation_bundle_marker_scope(self):
        expected = {
            1: "PHASE1_VALIDATION_BUNDLE",
            2: "PHASE2_VALIDATION_BUNDLE",
            4: "PHASE4_VALIDATION_BUNDLE",
            5: "PHASE5_VALIDATION_BUNDLE",
        }
        for phase in (1, 2, 3, 4, 5):
            path = ROOT / "prompts" / "templates" / f"phase{phase}_prompt.md"
            markers = self.template_markers(path)
            validation_markers = {m for m in markers if m.endswith("_VALIDATION_BUNDLE")}
            wanted = {expected[phase]} if phase in expected else set()
            self.assertEqual(validation_markers, wanted, f"phase {phase}")
        review_markers = self.template_markers(
            ROOT / "prompts" / "templates" / "phase5_review_prompt.md"
        )
        self.assertFalse({m for m in review_markers if m.endswith("_VALIDATION_BUNDLE")})

    def test_card_handling_prompts_use_phase_appropriate_shared_assets(self):
        common = {
            "CLINICAL_REPORTING_GATE",
            "SOURCE_DISEASE_ALIAS_POLICY",
            "SOURCE_DISEASE_ALIASES",
        }
        expected_evidence_asset = {
            "phase2_prompt.md": "EVIDENCE_BUNDLE_RULES",
            "phase3_prompt.md": "EVIDENCE_REVIEW_RULES",
            "phase4_prompt.md": "EVIDENCE_BUNDLE_RULES",
            "phase5_prompt.md": "EVIDENCE_BUNDLE_RULES",
            "phase5_review_prompt.md": "EVIDENCE_REVIEW_RULES",
        }
        for name, evidence_asset in expected_evidence_asset.items():
            path = ROOT / "prompts" / "templates" / name
            with self.subTest(template=name):
                markers = self.template_markers(path)
                self.assertTrue(common | {evidence_asset} <= markers)
                other_evidence_asset = (
                    "EVIDENCE_REVIEW_RULES"
                    if evidence_asset == "EVIDENCE_BUNDLE_RULES"
                    else "EVIDENCE_BUNDLE_RULES"
                )
                self.assertNotIn(other_evidence_asset, markers)


if __name__ == "__main__":
    unittest.main()
