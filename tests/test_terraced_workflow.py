from pathlib import Path
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import yaml

from scripts.workflow_registry import load_registry, normalise_selector
from workflows.terraced_v1 import model_registry, retrieval, runtime


class TerracedWorkflowTests(unittest.TestCase):
    def test_terraced_alias_is_registered_without_changing_default(self):
        registry = load_registry()
        self.assertEqual(normalise_selector(None, registry), "categorical-v1")
        self.assertEqual(normalise_selector("--terraced", registry), "terraced-v1")
        self.assertEqual(normalise_selector("--terraced-v1", registry), "terraced-v1")

    def test_question_profiles_preserve_every_question_once_in_order(self):
        config = runtime.load_questions()
        for domain, data in config["domains"].items():
            expected = [row["id"] for row in data["questions"]]
            for profile in config["execution_profiles"].values():
                flattened = [qid for group in profile["groups"][domain] for qid in group]
                self.assertEqual(flattened, expected)

    def test_all_shipped_provider_profiles_resolve_all_roles(self):
        registry = model_registry.load_registry()
        self.assertLessEqual(
            {"self", "lmstudio", "ollama", "openrouter"},
            set(registry["profiles"]),
        )
        for profile in registry["profiles"]:
            for role in registry["roles"]:
                binding = model_registry.resolve(role, profile, None, registry)
                self.assertTrue(binding.model)

    def test_final_diagnosis_rejects_icc_mds_aml(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "dx.yaml"
            path.write_text(
                yaml.safe_dump(
                    {
                        "provisional_cmcs": ["AML"],
                        "diagnoses": [
                            {
                                "schema_disease": "MDS/AML",
                                "narrow_diagnosis": "MDS/AML",
                            }
                        ],
                        "facts": [{"fact": "x", "reason": "y"}],
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "ICC-only"):
                runtime.validate_category_answer(
                    path, "diagnosis", final=True, aligned=False
                )

    def test_narrow_retrieval_does_not_inherit_parent_disease_treatment_cards(self):
        self.assertEqual(
            retrieval._disease_matches({"diseases": ["APL"]}, ["APL"], "treatment"),
            ["APL"],
        )
        self.assertEqual(
            retrieval._disease_matches({"diseases": ["AML"]}, ["APL"], "treatment"),
            [],
        )
        self.assertEqual(
            retrieval._disease_matches({"diseases": ["CML"]}, ["CML"], "treatment"),
            ["CML"],
        )
        self.assertEqual(
            retrieval._disease_matches({"diseases": ["MPN"]}, ["CML"], "treatment"),
            [],
        )

    def test_dual_pathology_routes_each_schema_disease_independently(self):
        card = {"diseases": ["CML", "MPN"]}
        self.assertEqual(
            retrieval._disease_matches(card, ["CML", "MPN"], "prognosis"),
            ["CML", "MPN"],
        )

    def test_alignment_allows_null_citation_and_preserves_fact_reason(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source = tmp_path / "answer-prognosis.yaml"
            aligned = tmp_path / "category-prognosis.yaml"
            evidence = tmp_path / "evidence-prognosis.md"
            source.write_text(
                '- fact: "TET2 has no established prognostic assignment in this context."\n'
                '  reason: "No applicable prognostic role is identified in the supplied evidence."\n',
                encoding="utf-8",
            )
            aligned.write_text(
                '- fact: "TET2 has no established prognostic assignment in this context."\n'
                '  reason: "No applicable prognostic role is identified in the supplied evidence."\n'
                "  citation: null\n",
                encoding="utf-8",
            )
            evidence.write_text("# Evidence\n\nNo cards.\n", encoding="utf-8")
            self.assertIn(
                "validated",
                runtime.validate_alignment(source, aligned, "prognosis", evidence),
            )


if __name__ == "__main__":
    unittest.main()
