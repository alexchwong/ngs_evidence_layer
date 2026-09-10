from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from workflows.proforma_v1 import default_config, model_context, prompt_loader


ROOT = Path(__file__).resolve().parents[1]


class DefaultConfigTests(unittest.TestCase):
    def test_shipped_default_preserves_existing_assets_and_alias_but_disables_new_modules(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(default_config.ENV_DEFAULT_CONFIG, None)
            doc = default_config.load()
            self.assertTrue(doc["prompt_modules"]["case_context"]["enabled"])
            self.assertTrue(doc["prompt_modules"]["prognostic_frameworks"]["enabled"])
            for name in (
                "deliberate",
                "foundational_genetics",
                "premise_before_consequence",
                "qualifier_check",
                "limiting_evidence",
            ):
                self.assertFalse(doc["prompt_modules"][name]["enabled"])
            self.assertTrue(doc["deterministic_enrichments"]["protein_hgvs_one_letter_alias"]["enabled"])

    def test_disabled_module_renders_intentional_blank_without_section_name(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(default_config.ENV_DEFAULT_CONFIG, None)
            text = prompt_loader.render(Path("prompts/diagnosis_who5.md"), root=ROOT)
        self.assertIn(default_config.BLANK_SECTION, text)
        self.assertNotIn("## Deliberate before committing", text)
        self.assertIn("## 2. Determine case context", text)

    def test_versioned_module_and_alias_switch_can_be_selected_by_absolute_config(self):
        base = default_config.load()
        for name in (
            "deliberate",
            "foundational_genetics",
            "premise_before_consequence",
            "qualifier_check",
            "limiting_evidence",
        ):
            base["prompt_modules"][name]["enabled"] = True
        base["deterministic_enrichments"]["protein_hgvs_one_letter_alias"]["enabled"] = False
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "selected.yaml"
            path.write_text(yaml.safe_dump(base, sort_keys=False), encoding="utf-8")
            with patch.dict(os.environ, {default_config.ENV_DEFAULT_CONFIG: str(path)}):
                text = prompt_loader.render(Path("prompts/prognosis.md"), root=ROOT)
                registry = model_context.canonical_registry(
                    {"v01": {"gene": "TP53", "description": "TP53 p.Arg175His"}},
                    fields=model_context.DEFAULT_REGISTRY_FIELDS,
                )
        self.assertIn("## Foundational genetics sanity check", text)
        self.assertIn("## Establish prerequisites before consequences", text)
        self.assertNotIn(default_config.BLANK_SECTION, text)
        self.assertNotIn("protein_alias", registry["v01"])


    def test_default_reviewed_prompts_render_versioned_prognostic_framework_module(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(default_config.ENV_DEFAULT_CONFIG, None)
            for rel in (
                "prompts/default_reviewed/prognosis.md",
                "prompts/default_reviewed/clinical_audit.md",
                "prompts/default_reviewed_v2/prognosis.md",
            ):
                with self.subTest(prompt=rel):
                    text = prompt_loader.render(Path(rel), root=ROOT)
                    self.assertIn("ELN 2022 genetic risk classification", text)
                    self.assertNotIn('{{ module "prognostic_frameworks" }}', text)

    def test_module_asset_path_tracks_configured_version(self):
        path = default_config.module_asset_path("prognostic_frameworks")
        self.assertEqual(path.name, "v1.md")
        self.assertTrue(path.is_file())

    def test_simple_three_letter_protein_substitution_alias_is_unchanged(self):
        self.assertEqual(model_context.protein_substitution_alias("TP53 p.Arg175His"), "R175H")
        self.assertIsNone(model_context.protein_substitution_alias("TP53 exon 5 deletion"))


if __name__ == "__main__":
    unittest.main()
