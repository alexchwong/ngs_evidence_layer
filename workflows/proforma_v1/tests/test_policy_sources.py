import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import vocab
from workflows.proforma_v1 import default_config, runtime, stage_spec, step


class ReportabilityPolicyTests(unittest.TestCase):
    def test_ptbg_defaults_come_from_stage_specs(self):
        for domain in ("prognosis", "treatment", "biomarker", "germline"):
            for key, expected in stage_spec.load(domain).reportability.items():
                self.assertIs(step._reportability_default(domain, key), expected)

    def test_settings_override_and_germline_compatibility_alias_are_preserved(self):
        base = {
            "reportability": {
                "domains": {
                    "prognosis": {"framework_favorable": False},
                    "germline": {"germline_support": False},
                }
            }
        }
        with patch.object(step, "load_settings", return_value=base):
            self.assertFalse(step._reportable("prognosis", "framework_favorable"))
            self.assertFalse(step._reportable("germline", "germline_suspicious"))

    def test_diagnosis_defaults_are_unchanged(self):
        for key in ("who5", "icc", "concurrent_pathology"):
            self.assertTrue(step._reportability_default("diagnosis", key))


class Who5SchemaDiseasePolicyTests(unittest.TestCase):
    def test_default_policy_excludes_mds_aml(self):
        self.assertIn("MDS/AML", runtime._who5_schema_disease_exclusions())

    def test_disabled_module_has_no_exclusions(self):
        with patch.object(default_config, "module_spec", return_value={"enabled": False, "version": "v1"}):
            self.assertEqual(runtime._who5_schema_disease_exclusions(), set())

    def test_selected_module_asset_controls_exclusions(self):
        with tempfile.TemporaryDirectory() as td:
            asset = Path(td) / "v2.md"
            asset.write_text(
                "## WHO5 schema-disease routing policy\n\n- `MDS/AML`\n- `TEST DISEASE`\n",
                encoding="utf-8",
            )
            with patch.object(default_config, "module_spec", return_value={"enabled": True, "version": "v2"}), \
                 patch.object(default_config, "module_asset_path", return_value=asset):
                self.assertEqual(
                    runtime._who5_schema_disease_exclusions(),
                    {"MDS/AML", "TEST DISEASE"},
                )

    def test_setup_assets_enforces_exclusions_deterministically(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            runtime.setup_assets(work, mode="manual")
            allowed = json.loads((work / "intermediates" / "001_setup" / "allowed-schema-diseases.json").read_text(encoding="utf-8"))
            self.assertNotIn("MDS/AML", allowed["allowed_schema_diseases"])
            self.assertEqual(
                set(allowed["allowed_schema_diseases"]),
                set(vocab.CASE_DISEASES) - {"MDS/AML"},
            )


if __name__ == "__main__":
    unittest.main()
