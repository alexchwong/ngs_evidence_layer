from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

import yaml
from jsonschema import Draft202012Validator

HERE = Path(__file__).resolve().parents[1]
WORKFLOW = HERE / "workflow" / "reasoning.yaml"
DEFAULT = HERE / "workflow" / "default.yaml"
SCHEMA = HERE / "schemas" / "workflow.schema.json"


class ReasoningWorkflowArchitectureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        cls.steps = cls.doc["steps"]

    def test_reasoning_workflow_conforms_to_workflow_schema(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        errors = sorted(Draft202012Validator(schema).iter_errors(self.doc), key=lambda e: list(e.absolute_path))
        self.assertEqual([], [e.message for e in errors])

    def test_every_dependency_and_review_target_exists(self):
        known = set(self.steps)
        for step_id, step in self.steps.items():
            with self.subTest(step=step_id):
                self.assertFalse(set(step.get("needs") or []) - known)
                review = step.get("review") or {}
                if review:
                    self.assertIn(review["target"], known)

    def test_diagnosis_reason_then_em_for_each_owner(self):
        order = list(self.steps)
        for owner in ("who", "icc", "second"):
            reason = f"diagnosis.{owner}.reason"
            em = f"diagnosis.{owner}.em"
            compile_id = f"diagnosis.{owner}.compile"
            self.assertLess(order.index(reason), order.index(em))
            self.assertLess(order.index(em), order.index(compile_id))
            self.assertNotIn("evidence", (self.steps[reason].get("inputs") or {}).keys())
            self.assertEqual(self.steps[em]["role"], "evidence_match")

    def test_diagnosis_grouped_audits_follow_all_owner_em_steps(self):
        order = list(self.steps)
        last_em = max(order.index(f"diagnosis.{owner}.em") for owner in ("who", "icc", "second"))
        self.assertGreater(order.index("diagnosis.evidence.audit"), last_em)
        self.assertGreater(order.index("diagnosis.reasoning.audit"), order.index("diagnosis.evidence.finalize"))

    def test_ptbg_each_domain_has_separate_reason_and_em(self):
        order = list(self.steps)
        for domain in ("prognosis", "treatment", "biomarker", "germline"):
            reason, em, compile_id = f"{domain}.reason", f"{domain}.em", f"{domain}.compile"
            self.assertLess(order.index(reason), order.index(em))
            self.assertLess(order.index(em), order.index(compile_id))
            self.assertEqual(self.steps[reason]["execution"]["self_handler"], "reasoning_model")
            self.assertEqual(self.steps[em]["execution"]["self_handler"], "reasoning_model")
            self.assertNotIn("self_group", self.steps[reason]["execution"])
            self.assertNotIn("self_group", self.steps[em]["execution"])

    def test_ptbg_grouped_audits_follow_all_domain_em_steps(self):
        order = list(self.steps)
        last_em = max(order.index(f"{d}.em") for d in ("prognosis", "treatment", "biomarker", "germline"))
        self.assertGreater(order.index("ptbg.evidence.audit"), last_em)
        self.assertGreater(order.index("ptbg.reasoning.audit"), order.index("ptbg.evidence.finalize"))

    def test_retry_ownership_separates_em_from_clinical_reasoning(self):
        for owner in ("who", "icc", "second"):
            self.assertEqual(self.steps[f"diagnosis.{owner}.em.review"]["review"]["target"], f"diagnosis.{owner}.em")
            self.assertEqual(self.steps[f"diagnosis.{owner}.review"]["review"]["target"], f"diagnosis.{owner}.reason")
        for domain in ("prognosis", "treatment", "biomarker", "germline"):
            self.assertEqual(self.steps[f"{domain}.em.review"]["review"]["target"], f"{domain}.em")
            self.assertEqual(self.steps[f"{domain}.review"]["review"]["target"], f"{domain}.reason")

    def test_self_no_longer_coalesces_clinical_reasoning_or_review_judgements(self):
        self.assertEqual(set(self.doc.get("self_groups") or {}), {"final_presentation"})
        grouped = {
            step_id: step["execution"].get("self_group")
            for step_id, step in self.steps.items()
            if (step.get("execution") or {}).get("self_group")
        }
        self.assertTrue(grouped)
        self.assertEqual(set(grouped.values()), {"final_presentation"})
        self.assertTrue(all(step_id.startswith(("report.", "dissent.")) for step_id in grouped))

    def test_embedded_progress_metadata_has_exact_step_coverage(self):
        phases = self.doc["presentation"]["progress_phases"]
        visible = [p["id"] for p in phases]
        self.assertEqual(visible[:12], [
            "case-preparation", "diagnosis-who", "diagnosis-icc", "diagnosis-second",
            "diagnosis-evidence-audit", "diagnosis-reasoning-audit", "prognosis", "treatment",
            "biomarker", "germline", "ptbg-evidence-audit", "ptbg-reasoning-audit",
        ])
        assigned = [step for phase in phases for step in phase["steps"]]
        self.assertEqual(len(assigned), len(set(assigned)))
        self.assertEqual(set(assigned), set(self.steps))

    def test_visible_progress_high_water_does_not_move_back_on_retry(self):
        from workflows.proforma_v1.engine.workflow_progress import WorkflowProgress
        steps = tuple(SimpleNamespace(id=x) for x in ("a", "b", "c"))
        workflow = SimpleNamespace(
            workflow_id="test", source=Path("test.yaml"), source_sha256="abc", steps=steps,
            doc={"presentation":{"progress_phases":[
                {"id":"phase-a","label":"A","steps":["a"]},
                {"id":"phase-b","label":"B","steps":["b"]},
                {"id":"phase-c","label":"C","steps":["c"]},
            ]}},
        )
        progress = WorkflowProgress(workflow)
        progress.update("a", "completed")
        progress.update("b", "running")
        self.assertEqual(progress.snapshot()["visible_high_water_phase"], "phase-b")
        progress.invalidate({"a", "b"})
        snap = progress.snapshot()
        self.assertEqual(snap["visible_high_water_phase"], "phase-b")
        self.assertEqual(snap["current_phase"], "phase-b")
        self.assertEqual(snap["phases"][0]["status"], "completed")

    def test_progress_sidecars_are_removed(self):
        workflow_dir = HERE / "workflow"
        self.assertFalse((workflow_dir / "reasoning.progress.yaml").exists())
        self.assertFalse((workflow_dir / "default.progress.yaml").exists())

    def test_default_workflow_embeds_presentation_without_reasoning_semantics(self):
        default = yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))
        self.assertIn("presentation", default)
        self.assertIn("progress_phases", default["presentation"])
        self.assertNotIn("reasoning_model", DEFAULT.read_text(encoding="utf-8"))
        self.assertIn("ptbg", default.get("self_groups") or {})


if __name__ == "__main__":
    unittest.main()
