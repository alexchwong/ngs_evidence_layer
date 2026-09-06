from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from validation.scripts.bundled_cases import retrieve_case_input
from workflows.proforma_v1 import pipeline_registry, reasoning_runtime, self as self_executor, step as staged
from workflows.proforma_v1.engine.workflow_compiler import compile_workflow
from workflows.proforma_v1.engine.workflow_progress import load_progress_plan


HERE = Path(__file__).resolve().parents[1]
DEFAULT = HERE / "workflow" / "default.yaml"
REASONING = HERE / "workflow" / "reasoning.yaml"
ATOMIC_SCHEMA = HERE / "schemas" / "reasoning" / "atomic_owner.json"


class ReasoningWorkflowTests(unittest.TestCase):
    def test_reasoning_workflow_diverges_without_mutating_default_diagnosis_graph(self):
        default_doc = yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))
        reasoning_doc = yaml.safe_load(REASONING.read_text(encoding="utf-8"))
        default_steps = default_doc["steps"]
        reasoning_steps = reasoning_doc["steps"]
        self.assertIn("diagnosis.who1", default_steps)
        self.assertIn("diagnosis.who1.evidence.audit", default_steps)
        self.assertNotIn("diagnosis.who", default_steps)
        self.assertNotIn("diagnosis.second", default_steps)
        self.assertIn("diagnosis.who", reasoning_steps)
        self.assertIn("diagnosis.icc", reasoning_steps)
        self.assertIn("diagnosis.second", reasoning_steps)
        self.assertIn("diagnosis.reasoning.audit", reasoning_steps)
        self.assertEqual(reasoning_steps["structure"], default_steps["structure"])
        self.assertEqual(default_steps["prognosis"]["prompt"], "prompts/prognosis.md")
        self.assertEqual(reasoning_steps["prognosis"]["prompt"], "prompts/reasoning/prognosis.md")
        self.assertEqual(reasoning_steps["prognosis"]["execution"]["self_group"], "ptbg_owners")

    def test_reasoning_diagnosis_uses_executor_native_generic_handlers_and_rescue_only_matching(self):
        reasoning_doc = yaml.safe_load(REASONING.read_text(encoding="utf-8"))
        steps = reasoning_doc["steps"]
        for owner in ("diagnosis.who", "diagnosis.icc", "diagnosis.second"):
            self.assertEqual(steps[owner]["execution"]["provider_handler"], "reasoning_model")
            self.assertEqual(steps[owner]["execution"]["self_handler"], "reasoning_model")
        self.assertEqual(steps["diagnosis.registry"]["execution"]["self_handler"], "generic_transform")
        self.assertEqual(
            steps["diagnosis.evidence.assignment"]["when"],
            {"has_items": {"artifact": "diagnostic_rescue_items"}},
        )
        self.assertEqual(steps["diagnosis.who.review"]["review"]["target"], "diagnosis.who")
        self.assertEqual(steps["diagnosis.icc.review"]["review"]["target"], "diagnosis.icc")
        self.assertEqual(steps["diagnosis.second.review"]["review"]["target"], "diagnosis.second")
        self.assertNotIn("diagnosis.who", steps["diagnosis.icc.prepare"].get("needs", []))
        self.assertNotIn("diagnosis.who", steps["diagnosis.second.prepare"].get("needs", []))

    def test_reasoning_progress_groups_cover_each_logical_step_once(self):
        workflow = compile_workflow(REASONING)
        plan = load_progress_plan(workflow)
        assigned = [step_id for phase in plan["phases"] for step_id in phase["steps"]]
        self.assertEqual(len(assigned), len(set(assigned)))
        self.assertEqual(set(assigned), {step.id for step in workflow.steps})
        self.assertEqual(plan["phases"][0]["label"], "Case preparation")
        self.assertEqual(plan["phases"][-1]["label"], "Report verification")

    def test_reasoning_model_role_is_optional_for_legacy_profiles(self):
        source = yaml.safe_load((HERE / "pipelines" / "self.yaml").read_text(encoding="utf-8"))
        source["models"].pop("reasoning_audit")
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "legacy-self.yaml"
            path.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
            plan = pipeline_registry.load_yaml(path)
            self.assertEqual(plan.pipeline_id, "legacy-self")
            with self.assertRaisesRegex(ValueError, "does not configure optional model role 'reasoning_audit'"):
                pipeline_registry.binding(plan, "reasoning_audit")

    def test_shipped_profiles_configure_reasoning_and_dissent_roles(self):
        for name in ("openrouter", "lmstudio", "self"):
            with self.subTest(pipeline=name):
                plan = pipeline_registry.load(name)
                reasoning = pipeline_registry.binding(plan, "reasoning_audit")
                summary = pipeline_registry.binding(plan, "dissent_summary")
                self.assertEqual(reasoning.reasoning, "high")
                self.assertEqual(summary.reasoning, "low")
                self.assertGreater(reasoning.max_tokens, 0)
                self.assertGreater(summary.max_tokens, 0)

    def test_validation_reports_all_deterministic_contract_problems(self):
        bad = """
authority: who5
proposal:
  proposal_id: P1
  label: Example
  kind: diagnosis
rules:
  - rule_id: R1
    statement: Rule one
    evidence_required: true
  - rule_id: R1
    statement: Rule duplicate
    evidence_required: true
derived_states:
  - state_id: S1
    label: State
    case_fact_ids: [C999]
    variant_ids: [v99]
    proposed_value: example
criteria:
  - criterion_id: C1
    rule_ids: [R1]
    case_fact_ids: [C999]
    variant_ids: [v99]
    state_ids: [S1]
    proposed_status: invalid_status
logic: []
root_id: null
reason: Example reason
"""
        result = reasoning_runtime.audit_atomic_artifact(
            bad,
            fmt="yaml",
            schema=ATOMIC_SCHEMA,
            case_fact_ids={"C1"},
            variant_ids={"v01"},
        )
        self.assertFalse(result.ok)
        codes = [issue.code for issue in result.issues]
        self.assertIn("duplicate_reasoning_id", codes)
        self.assertIn("unknown_case_fact_id", codes)
        self.assertIn("unknown_variant_id", codes)
        self.assertTrue(any(code.startswith("schema_") for code in codes))
        feedback = result.feedback()
        self.assertIn("Fix all of them in one complete redo", feedback)
        self.assertGreaterEqual(feedback.count("What is wrong:"), 5)
        self.assertGreaterEqual(feedback.count("What to fix:"), 5)

    def test_safe_fence_repair_preserves_semantic_values(self):
        payload = """authority: who5
proposal: {proposal_id: P1, label: Example, kind: diagnosis}
rules: []
derived_states: []
criteria: []
logic: []
root_id: null
reason: keep-this-exact-value
"""
        fenced = "```yaml\n" + payload.rstrip() + "\n```\n"
        result = reasoning_runtime.audit_atomic_artifact(
            fenced,
            fmt="yaml",
            schema=ATOMIC_SCHEMA,
            case_fact_ids=set(),
            variant_ids=set(),
        )
        self.assertTrue(result.ok, result.feedback())
        self.assertEqual(result.document["reason"], "keep-this-exact-value")
        self.assertEqual([r.code for r in result.repairs], ["strip_outer_markdown_fence"])

    def test_reasoning_batches_respect_configured_limit(self):
        batches = reasoning_runtime.batch_items(list(range(37)), 16)
        self.assertEqual([len(batch) for batch in batches], [16, 16, 5])
        self.assertEqual([item for batch in batches for item in batch], list(range(37)))

    def test_demo_example_one_prepares_reasoning_workflow_and_emits_case_preparation_progress(self):
        # This is a no-provider smoke test. It uses the repository's real bundled
        # demo case and advances native-self only as far as the first model handoff.
        clinical = retrieve_case_input("nel-demo", 1)
        self.assertIn("NPM1", clinical)
        self.assertIn("FLT3-ITD", clinical)
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "demo-1-reasoning"
            code = staged.main([
                "setup",
                "--mode", "nel-demo",
                "--example", "1",
                "--pipeline", "self",
                "--workflow", str(REASONING),
                "--work-dir", str(work),
            ])
            self.assertEqual(code, 0)
            self.assertIn("NPM1", (work / "case.md").read_text(encoding="utf-8"))
            result = self_executor.advance(work)
            self.assertEqual(result["status"], "handoff")
            progress = json.loads((work / "logs" / "workflow-progress.json").read_text(encoding="utf-8"))
            self.assertEqual(progress["current_phase"], "case_preparation")
            self.assertEqual(progress["current_step"], "structure")
            self.assertEqual(progress["phases"][0]["label"], "Case preparation")


if __name__ == "__main__":
    unittest.main()
