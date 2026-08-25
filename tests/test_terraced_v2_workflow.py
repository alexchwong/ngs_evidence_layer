import json
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.workflow_registry import load_registry, load_workflow_metadata, normalise_selector
from workflows.terraced_v2 import model_registry, runtime

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "workflows" / "terraced_v2"


class TerracedV2WorkflowTests(unittest.TestCase):
    def test_terraced_v2_is_registered(self):
        registry = load_registry()
        self.assertEqual(registry["workflows"]["terraced-v2"]["path"], "workflows/terraced_v2")
        self.assertEqual(normalise_selector("terraced-v2", registry), "terraced-v2")
        self.assertEqual(load_workflow_metadata("terraced-v2")["python_package"], "workflows.terraced_v2")

    def test_yaml_pipeline_is_canonical_serial_dependency_order(self):
        doc = runtime.load_pipeline()
        ids = [row["id"] for row in doc["pipeline"]]
        self.assertEqual(
            ids,
            [
                "structure", "corpus", "diagnosis", "diagnosis_report",
                "germline", "prognosis", "biomarker", "treatment", "finalise",
            ],
        )
        treatment = next(row for row in doc["pipeline"] if row["id"] == "treatment")
        self.assertEqual(
            treatment["context"],
            {
                "diagnosis": ["cmc", "who5_diagnosis", "facts"],
                "germline": ["facts"],
                "prognosis": ["facts"],
                "biomarker": ["facts"],
            },
        )
        invariants = doc["invariants"]
        self.assertFalse(invariants["propagate_uncertainty_between_domains"])
        self.assertFalse(invariants["allow_downstream_diagnosis_mutation"])
        self.assertEqual(invariants["diagnosis_authority"], "WHO5")
        self.assertFalse(invariants["provider_specific_pipeline_branches"])

    def test_questions_borrow_diagnosis_lab_and_v1_downstream_terraces(self):
        q = runtime.load_questions()
        lab = yaml.safe_load((ROOT / "workflows/terraced_v1/diagnosis_lab/questions.yaml").read_text())
        v1 = yaml.safe_load((ROOT / "workflows/terraced_v1/questions.yaml.template").read_text())
        self.assertEqual(
            [x["question"] for x in q["domains"]["diagnosis"]["questions"]],
            [x["question"] for x in lab["questions"]],
        )
        for domain in ("germline", "prognosis", "treatment"):
            self.assertEqual(
                [x["question"] for x in q["domains"][domain]["questions"]],
                [x["question"] for x in v1["domains"][domain]["questions"]],
            )
        self.assertEqual(
            [x["question"] for x in q["domains"]["biomarker"]["questions"]],
            [x["question"] for x in v1["domains"]["mrd"]["questions"]],
        )

    def test_all_provider_profiles_share_one_pipeline(self):
        registry = model_registry.load_registry()
        self.assertEqual(set(registry["profiles"]), {"self", "lmstudio", "ollama", "openrouter"})
        self.assertTrue(all("provider" not in row for row in runtime.load_pipeline()["pipeline"]))
        self.assertFalse(runtime.load_pipeline()["invariants"]["provider_specific_pipeline_branches"])
        for profile in registry["profiles"]:
            for role in registry["roles"]:
                binding = model_registry.resolve(role, profile, registry=registry)
                self.assertEqual(binding.profile, profile)

    def test_diagnosis_context_sheds_uncertainty_and_icc(self):
        final = {
            "provisional_cmcs": ["AML"],
            "diagnoses": [{
                "schema_disease": "AML",
                "WHO5": {"status": "established", "diagnosis": "AML with NPM1 mutation"},
                "ICC": {"status": "established", "diagnosis": "AML with mutated NPM1"},
                "materially_different": False,
            }, {
                "schema_disease": "MDS",
                "WHO5": {"status": "indeterminate", "diagnosis": "MDS, subtype indeterminate"},
                "ICC": {"status": "indeterminate", "diagnosis": "MDS, subtype indeterminate"},
                "materially_different": False,
            }],
            "supporting_facts": [{"fact": "WHO5 diagnosis is AML.", "reason": "Supported.", "source_fact_ids": ["PRE-FINAL-F1"]}],
            "uncertainties": [{"uncertainty": "Example uncertainty.", "reason": "Example.", "source_ids": ["PRE-FINAL-U1"]}],
        }
        context = runtime.diagnosis_context(final)
        self.assertEqual(set(context), {"cmc", "who5_diagnosis", "facts"})
        self.assertNotIn("ICC", json.dumps(context))
        self.assertNotIn("uncertaint", json.dumps(context).lower())
        self.assertEqual(
            context["who5_diagnosis"],
            [{
                "schema_disease": "AML",
                "status": "established",
                "diagnosis": "AML with NPM1 mutation",
            }],
        )
        self.assertNotIn("MDS, subtype indeterminate", json.dumps(context))

    def test_case_json_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case.json"
            path.write_text(json.dumps({
                "provisional_cmcs": ["AML"],
                "provisional_disease": "AML",
                "genes": ["NPM1"],
                "detected_variants_summary": "NGS detected NPM1 p.(X).",
                "case_facts": [{"fact_id": "F1", "kind": "morphology", "value": "Blasts 20%."}],
            }))
            self.assertEqual(runtime.validate_case_json(path), "case.json validated")

    def test_release_manifest_includes_terraced_v2_runtime_and_prompts(self):
        manifest = (ROOT / "release" / "skill.txt").read_text(encoding="utf-8").splitlines()
        self.assertIn("workflows/terraced_v2/*", manifest)
        self.assertIn("workflows/terraced_v2/prompts/*", manifest)


if __name__ == "__main__":
    unittest.main()
