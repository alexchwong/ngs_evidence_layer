from __future__ import annotations

import copy
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

import yaml

from scripts.core import validated_model_task as vmt
from workflows.proforma_v1 import domain_contract, layout, self_runtime
from workflows.proforma_v1.engine import bindings, artifacts as workflow_artifacts
from workflows.proforma_v1.engine.context import WorkflowContext
from workflows.proforma_v1.engine.workflow_compiler import WorkflowCompileError, compile_workflow
from workflows.proforma_v1.engine.workflow_runner import WorkflowRunner, executor_enabled
from workflows.proforma_v1.executors.provider import ProviderExecutor

HERE = Path(__file__).resolve().parents[1]
DEFAULT = HERE / "workflow" / "default.yaml"


class Phase2BDefaultWorkflowTests(unittest.TestCase):
    def test_default_file_and_executor_policy(self):
        self.assertTrue(DEFAULT.is_file())
        self.assertFalse((HERE / "workflow.yaml").exists())
        workflow = compile_workflow()
        self.assertEqual(workflow.source, DEFAULT.resolve())
        self.assertFalse(executor_enabled(workflow.step("report.preservation"), "self"))
        self.assertTrue(executor_enabled(workflow.step("report.preservation"), "provider"))

    def test_ptbg_needs_are_real_dependencies_and_group_membership_is_yaml(self):
        workflow = compile_workflow()
        for domain in ("prognosis", "treatment", "biomarker", "germline"):
            step = workflow.step(domain)
            self.assertEqual(step.needs, ("diagnosis.finalize",))
            self.assertEqual(step.execution.get("self_group"), "ptbg")

    def test_dependent_steps_cannot_share_self_group(self):
        doc = yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))
        doc["steps"]["treatment"]["needs"] = ["prognosis"]
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", dir=HERE / "workflow", delete=False) as fh:
            yaml.safe_dump(doc, fh, sort_keys=False)
            path = Path(fh.name)
        try:
            with self.assertRaisesRegex(WorkflowCompileError, "contains dependent steps"):
                compile_workflow(path)
        finally:
            path.unlink(missing_ok=True)


class Phase2BRuntimeCompatibilityTests(unittest.TestCase):
    def test_structure_panel_scope_binding_uses_numbered_setup_layout(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            layout.ensure_dirs(work)
            panel = layout.setup(work, "ngs-panel-scope.md", existing=False)
            panel.write_text("TEST PANEL SCOPE\n", encoding="utf-8")
            (work / "case.md").write_text("case\n", encoding="utf-8")
            context = WorkflowContext(work, executor="provider")
            values = bindings.resolve_inputs(compile_workflow().step("structure"), context)
            self.assertEqual(values["panel_scope"], "TEST PANEL SCOPE\n")

    def test_native_self_evidence_match_passes_retry_only_zero_facts_and_audit_only_matches(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            layout.ensure_dirs(work)
            state = {
                "elements": [],
                "items": [
                    {
                        "evidence_id": "E0001", "schema_id": "S1", "reason": "fact one", "statement": "fact one",
                        "candidate_card_ids": ["A", "C"],
                        "candidate_card_tags": ["[card:aaaaaaaaaaaa]", "[card:cccccccccccc]"],
                    },
                    {
                        "evidence_id": "E0002", "schema_id": "S2", "reason": "fact two", "statement": "fact two",
                        "candidate_card_ids": ["B", "D"],
                        "candidate_card_tags": ["[card:bbbbbbbbbbbb]", "[card:dddddddddddd]"],
                    },
                ],
                "no_candidate_schema_ids": [],
                "catalog_card_ids": ["A", "B", "C", "D"],
                "authoritative_disease": "AML",
                "corpus_sha256": "x",
                "max_match_passes": 2,
                "match_pass_by_evidence_id": {},
            }
            cards = [
                {"card_id": "A", "interpretation": "A text"},
                {"card_id": "B", "interpretation": "B text"},
                {"card_id": "C", "interpretation": "C text"},
                {"card_id": "D", "interpretation": "D text"},
            ]
            tags = {"A": "aaaaaaaaaaaa", "B": "bbbbbbbbbbbb", "C": "cccccccccccc", "D": "dddddddddddd"}

            def initialise(path, **kwargs):
                self_runtime.write_yaml(self_runtime._evidence_state_path(path), state)
                return state

            with patch.object(self_runtime, "_initial_evidence_state", side_effect=initialise), \
                 patch.object(self_runtime, "corpus_state", return_value=(cards, [], "x", {})), \
                 patch.object(self_runtime.card_identity, "tag_by_id", return_value=tags), \
                 patch.object(self_runtime.staged, "_render_cards", side_effect=lambda selected, tagmap: selected[0]["interpretation"]), \
                 patch.object(self_runtime, "_assert_audit_targets_applicable", return_value=None):
                first = self_runtime.prepare_evidence_resolution(work, max_match_passes=2)
                self.assertFalse(first["complete"])
                self.assertEqual(first["match_pass"], 1)
                self.assertEqual(first["fact_count"], 2)
                first_text = first["facts"].read_text(encoding="utf-8")
                self.assertIn("fact one", first_text)
                self.assertIn("fact two", first_text)

                self_runtime.write_yaml(first["output"], {"matches": [
                    {"evidence_id": "E0001", "card_tags": ["[card:aaaaaaaaaaaa]"]},
                    {"evidence_id": "E0002", "card_tags": []},
                ]})
                second = self_runtime.prepare_evidence_resolution(work, max_match_passes=2)
                self.assertFalse(second["complete"])
                self.assertEqual(second["match_pass"], 2)
                self.assertEqual(second["fact_count"], 1)
                second_text = second["facts"].read_text(encoding="utf-8")
                self.assertNotIn("E0001", second_text)
                self.assertNotIn("aaaaaaaaaaaa", second_text)
                self.assertIn("E0002", second_text)
                self.assertIn("bbbbbbbbbbbb", second_text)
                self.assertIn("dddddddddddd", second_text)

                self_runtime.write_yaml(second["output"], {"matches": [
                    {"evidence_id": "E0002", "card_tags": ["[card:bbbbbbbbbbbb]"]},
                ]})
                final = self_runtime.prepare_evidence_resolution(work, max_match_passes=2)
                self.assertTrue(final["complete"])
                merged = self_runtime.accept_evidence_resolution(work)
                self.assertEqual(merged["matches"], [
                    {"evidence_id": "E0001", "card_tags": ["[card:aaaaaaaaaaaa]"]},
                    {"evidence_id": "E0002", "card_tags": ["[card:bbbbbbbbbbbb]"]},
                ])

                audit = self_runtime.prepare_evidence_audit(work)
                self.assertTrue(audit["required"])
                audit_text = audit["facts"].read_text(encoding="utf-8")
                self.assertIn("aaaaaaaaaaaa", audit_text)
                self.assertIn("bbbbbbbbbbbb", audit_text)
                self.assertNotIn("cccccccccccc", audit_text)
                self.assertNotIn("dddddddddddd", audit_text)
                self.assertNotIn("cards", audit)


    def test_prognosis_allows_source_direction_conflict_and_normalizes_no_evidence_reason(self):
        contract = domain_contract.contract("prognosis")
        registry = {
            "v01": {"gene": "ASXL1"},
            "v02": {"gene": "DNMT3A"},
            "v03": {"gene": "TET2"},
        }
        doc = {
            "applicable_disease": "AML",
            "prognostic_frameworks": [
                {"name": "ELN 2022", "tier": None, "reason": "Applicable AML framework."}
            ],
            "classification": [
                {
                    "variant": "v01", "gene": "ASXL1",
                    "framework_effects": [
                        {"framework": "ELN 2022", "effect": "adverse", "reason": "Framework adverse."}
                    ],
                    "other_evidence_effect": "favorable",
                    "other_evidence_reason": "Independent treatment-context evidence is favorable.",
                },
                {
                    "variant": "v02", "gene": "DNMT3A", "framework_effects": [],
                    "other_evidence_effect": "no_evidence",
                    "other_evidence_reason": "No qualifying prognostic evidence was found.",
                },
                {
                    "variant": "v03", "gene": "TET2", "framework_effects": [],
                    "other_evidence_effect": "no_evidence",
                    "other_evidence_reason": "No qualifying prognostic evidence was found.",
                },
            ],
        }
        normalized, records = domain_contract.normalize_model_output(
            yaml.safe_dump(doc, sort_keys=False), contract, registry, "AML"
        )
        normalized_doc = yaml.safe_load(normalized)
        self.assertEqual(normalized_doc["classification"][0]["other_evidence_effect"], "favorable")
        self.assertEqual(normalized_doc["classification"][0]["other_evidence_reason"], "Independent treatment-context evidence is favorable.")
        self.assertIsNone(normalized_doc["classification"][1]["other_evidence_reason"])
        self.assertIsNone(normalized_doc["classification"][2]["other_evidence_reason"])
        self.assertEqual(
            [r["transform"] for r in records if r["transform"] == "null_reason_for_no_evidence"],
            ["null_reason_for_no_evidence", "null_reason_for_no_evidence"],
        )
        domain_contract.validate(
            normalized, contract,
            {"variants": ["v01", "v02", "v03"], "registry": registry, "authoritative_disease": "AML"},
        )

    def test_prognosis_positive_other_effect_still_requires_reason(self):
        contract = domain_contract.contract("prognosis")
        registry = {"v01": {"gene": "ASXL1"}}
        doc = {
            "applicable_disease": "AML",
            "prognostic_frameworks": [],
            "classification": [{
                "variant": "v01", "gene": "ASXL1", "framework_effects": [],
                "other_evidence_effect": "favorable", "other_evidence_reason": None,
            }],
        }
        normalized, _ = domain_contract.normalize_model_output(
            yaml.safe_dump(doc, sort_keys=False), contract, registry, "AML"
        )
        with self.assertRaisesRegex(Exception, "missing despite a positive/neutral other-evidence classification"):
            domain_contract.validate(
                normalized, contract,
                {"variants": ["v01"], "registry": registry, "authoritative_disease": "AML"},
            )

    def test_provider_declared_checks_receive_live_runtime_context(self):
        from workflows.proforma_v1 import step as staged_step

        declared = SimpleNamespace(
            output={"format": "json"},
            checks=({"rule": "subset", "path": "ids", "source": "allowed"},),
        )
        context = WorkflowContext(Path("."), executor="provider", data={"allowed": ["A", "B"]})
        old_workflow = staged_step._ACTIVE_COMPILED_WORKFLOW
        old_context = staged_step._ACTIVE_WORKFLOW_CONTEXT
        staged_step._ACTIVE_COMPILED_WORKFLOW = SimpleNamespace(asset_root=HERE)
        staged_step._ACTIVE_WORKFLOW_CONTEXT = context
        try:
            with patch.object(staged_step, "_workflow_step_for_call", return_value=declared):
                validator = staged_step._with_declared_validation("test", lambda text: "legacy valid")
                self.assertEqual(validator('{"ids":["A"]}'), "legacy valid")
                with self.assertRaisesRegex(Exception, "unknown value"):
                    validator('{"ids":["Z"]}')
        finally:
            staged_step._ACTIVE_COMPILED_WORKFLOW = old_workflow
            staged_step._ACTIVE_WORKFLOW_CONTEXT = old_context

    def test_self_declared_checks_receive_live_runtime_context(self):
        import importlib
        self_driver = importlib.import_module("workflows.proforma_v1.self")
        step = SimpleNamespace(
            id="custom.audit", type="model", checks=({"rule": "subset", "path": "ids", "source": "allowed"},),
            output={"artifact": "custom_audit", "format": "json"},
        )
        workflow = SimpleNamespace(asset_root=HERE, step=lambda step_id: step)
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            layout.ensure_dirs(work)
            context = WorkflowContext(work, executor="self", data={"workflow": workflow, "allowed": ["A", "B"]})
            output = workflow_artifacts.generic_output_path(work, step, create=True)
            output.write_text('{"ids":["A"]}', encoding="utf-8")
            self_driver._self_declared_validate(step.id, context)
            output.write_text('{"ids":["Z"]}', encoding="utf-8")
            with self.assertRaisesRegex(Exception, "unknown value"):
                self_driver._self_declared_validate(step.id, context)


class Phase2BCustomWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.created = []

    def tearDown(self):
        for path in self.created:
            path.unlink(missing_ok=True)

    def _write(self, path: Path, text: str):
        path.write_text(text, encoding="utf-8")
        self.created.append(path)
        return path

    def test_custom_workflow_can_swap_prompt_schema_stage_group_and_add_review(self):
        doc = copy.deepcopy(yaml.safe_load(DEFAULT.read_text(encoding="utf-8")))
        doc["workflow_id"] = "phase2b-custom"

        custom_prompt = self._write(
            HERE / "prompts" / "_phase2b_prognosis.md",
            "Custom prognosis. Prior audit: {{ input.previous_audit }}\n",
        )
        custom_stage = HERE / "stages" / "_phase2b_prognosis.yaml"
        stage_doc = yaml.safe_load((HERE / "stages" / "prognosis.yaml").read_text(encoding="utf-8"))
        stage_doc["guidance"] = list(stage_doc.get("guidance") or []) + ["Phase2B custom guidance."]
        self._write(custom_stage, yaml.safe_dump(stage_doc, sort_keys=False))
        custom_schema = HERE / "schemas" / "_phase2b_prognosis.json"
        self._write(custom_schema, (HERE / "schemas" / "prognosis.json").read_text(encoding="utf-8"))
        audit_prompt = self._write(
            HERE / "prompts" / "_phase2b_prognosis_audit.md",
            "Audit this prognosis:\n{{ input.prognosis }}\n",
        )
        audit_schema = HERE / "schemas" / "_phase2b_prognosis_audit.json"
        self._write(audit_schema, json.dumps({
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object", "additionalProperties": False,
            "required": ["accepted"], "properties": {"accepted": {"type": "boolean"}},
        }))

        prognosis = doc["steps"]["prognosis"]
        prognosis["prompt"] = f"prompts/{custom_prompt.name}"
        prognosis["stage"] = f"stages/{custom_stage.name}"
        prognosis["output"]["schema"] = f"schemas/{custom_schema.name}"
        prognosis["inputs"] = {"previous_audit": {"from": "feedback.prognosis_audit", "optional": True}}
        doc["steps"]["treatment"]["execution"].pop("self_group")

        doc["steps"]["prognosis.audit"] = {
            "type": "model", "needs": ["prognosis"], "role": "evidence_audit",
            "prompt": f"prompts/{audit_prompt.name}",
            "inputs": {"prognosis": {"from": "artifacts.prognosis"}},
            "output": {"artifact": "prognosis_audit", "format": "json", "schema": f"schemas/{audit_schema.name}"},
            "review": {
                "target": "prognosis",
                "verdict": {"path": "accepted", "pass_values": [True]},
                "on_pass": {"continue": True},
                "on_fail": {
                    "retry_target": True,
                    "feedback": {"from": "artifacts.prognosis_audit", "as": "previous_audit"},
                    "max_cycles": 2,
                    "exhausted": {"action": "stop"},
                },
            },
            "execution": {"provider_handler": "generic_model", "self_handler": "generic_model", "self_mode": "handoff"},
        }
        # Evidence must consume the reviewed prognosis, not the pre-audit result.
        doc["steps"]["evidence.assignment"]["needs"] = ["prognosis.audit", "treatment", "biomarker", "germline"]

        workflow_path = HERE / "workflow" / "_phase2b_custom.yaml"
        self._write(workflow_path, yaml.safe_dump(doc, sort_keys=False))
        workflow = compile_workflow(workflow_path)
        self.assertEqual(workflow.workflow_id, "phase2b-custom")
        self.assertEqual(workflow.step("prognosis").prompt, custom_prompt.resolve())
        self.assertEqual(workflow.step("prognosis").stage_spec_obj.path, custom_stage.resolve())
        self.assertIsNotNone(workflow.step("prognosis.audit").review)
        self.assertNotIn("self_group", workflow.step("treatment").execution)
        self.assertGreaterEqual(len(workflow.asset_sha256), 4)


class Phase2BReviewRunnerTests(unittest.TestCase):
    @staticmethod
    def _step(step_id, needs=(), review=None, inputs=None):
        return SimpleNamespace(
            id=step_id, type="model", needs=tuple(needs), review=review,
            inputs=inputs or {}, when=None, execution={"provider_handler": step_id},
            output={"artifact": step_id + "_artifact"},
        )

    def test_review_failure_feedback_retries_target_then_continues(self):
        target = self._step("target", inputs={"prior": {"from": "feedback.audit"}})
        audit = self._step("audit", needs=("target",), review={
            "target": "target",
            "verdict": {"path": "accepted", "pass_values": [True]},
            "on_pass": {"continue": True},
            "on_fail": {
                "retry_target": True, "feedback": {"from": "artifacts.audit_artifact", "as": "prior"},
                "max_cycles": 2, "exhausted": {"action": "stop"},
            },
        })
        final = self._step("final", needs=("audit",))

        class WF:
            steps = (target, audit, final)
            def step(self, sid):
                return {s.id: s for s in self.steps}[sid]

        target_runs = []
        invalidated = []
        def target_handler(step, ctx):
            target_runs.append(dict(ctx.get("feedback_values", {}) or {}))
            ctx.put("target_artifact", {"run": len(target_runs)})
            return {"artifact": ctx.get("target_artifact")}
        def audit_handler(step, ctx):
            doc = {"accepted": len(target_runs) > 1, "comment": "retry me"}
            ctx.put("audit_artifact", doc)
            return {"artifact": doc}
        handlers = {"target": target_handler, "audit": audit_handler, "final": lambda s, c: {"artifact": {"done": True}}}
        executor = ProviderExecutor(handlers, invalidator=lambda ids, ctx: invalidated.append(set(ids)))
        ctx = WorkflowContext(Path("."), "provider")
        result = WorkflowRunner(WF(), executor).run_all(ctx)
        self.assertEqual(result.status, "complete")
        self.assertEqual(len(target_runs), 2)
        self.assertEqual(target_runs[1]["feedback.audit"]["accepted"], False)
        self.assertIn({"target", "audit"}, invalidated)


class Phase2BResumeTests(unittest.TestCase):
    def test_self_suspension_does_not_consume_same_invalid_output_twice(self):
        state = {}
        output = {"text": "bad"}
        attempts = []
        request = vmt.TaskRequest(
            task_id="x", messages=[{"role": "user", "content": "task"}],
            validate=lambda text: (_ for _ in ()).throw(ValueError("bad")) if text == "bad" else "ok",
            budgets=vmt.Budgets(content=3, serialization=1, rewrite=1),
        )
        io = vmt.TaskIO(
            call_model=lambda messages: None,
            load_state=lambda task_id: dict(state),
            save_state=lambda task_id, value: (state.clear(), state.update(value)),
            read_output=lambda: output["text"],
            write_output=lambda text: output.__setitem__("text", text),
            record_attempt=lambda row: attempts.append(row),
            is_self=True,
        )
        with self.assertRaises(vmt.Suspend):
            vmt.run(request, io)
        self.assertEqual(state["rewrites"], 1)
        self.assertEqual(len(attempts), 1)
        with self.assertRaises(vmt.Suspend):
            vmt.run(request, io)
        self.assertEqual(state["rewrites"], 1)
        self.assertEqual(len(attempts), 1)
        output["text"] = "good"
        self.assertEqual(vmt.run(request, io), "good")
        self.assertEqual(state, {})

    def test_developer_docs_name_unittest_and_generic_self_loop(self):
        devel = (HERE / "DEVEL.md").read_text(encoding="utf-8")
        skill = (HERE / "SKILL.md").read_text(encoding="utf-8")
        readme = (HERE / "workflow" / "README.md").read_text(encoding="utf-8")
        self.assertIn("python -m unittest discover", devel)
        self.assertIn("self.py run again immediately", skill)
        self.assertNotIn("## Self pass topology", skill)
        self.assertIn("Semantic audit feedback", readme)


class Phase2BReportBlockOwnershipTests(unittest.TestCase):
    def test_finalize_evidence_does_not_generate_report_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            layout.ensure_dirs(work)
            state = {"items": [], "elements": [], "no_candidate_schema_ids": []}
            with patch.object(self_runtime, "_load_evidence_state", return_value=state), \
                 patch.object(self_runtime, "accept_evidence_resolution", return_value={"matches": []}), \
                 patch.object(self_runtime, "accept_evidence_audit", return_value=({"audits": []}, [])), \
                 patch.object(self_runtime, "compare_evidence", return_value=([], [])), \
                 patch.object(self_runtime, "corpus_state", return_value=([], [], "digest", {})), \
                 patch.object(self_runtime.card_identity, "tag_by_id", return_value={}), \
                 patch.object(self_runtime.staged, "stage_blocks") as stage_blocks, \
                 patch.object(self_runtime.staged, "_write_dissent"):
                self.assertEqual(self_runtime.finalize_evidence(work), [])
                stage_blocks.assert_not_called()
            self.assertTrue(self_runtime.output_path(work, "evidence_enriched", "reportable-elements.yaml").is_file())
            self.assertFalse(self_runtime.output_path(work, "report_blocks", "report-blocks.yaml").is_file())

    def test_self_report_blocks_handler_is_sole_block_generator(self):
        import importlib
        self_driver = importlib.import_module("workflows.proforma_v1.self")
        blocks = [{"block_id": "DX", "domain": "diagnosis", "components": []}]
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            layout.ensure_dirs(work)
            elements_path = self_runtime.output_path(work, "evidence_enriched", "reportable-elements.yaml")
            elements_path.parent.mkdir(parents=True, exist_ok=True)
            elements_path.write_text("elements: []\n", encoding="utf-8")
            ctx = WorkflowContext(work, "self")
            with patch.object(self_driver.sr, "finalize_diagnosis", return_value={"who5": {"schema_disease": "AML"}}), \
                 patch.object(self_driver.sr, "load_case_registry", return_value=({}, {})), \
                 patch.object(self_driver.staged, "stage_blocks", return_value=blocks) as stage_blocks:
                result = self_driver._self_handlers()["report_blocks"](SimpleNamespace(id="report.blocks"), ctx)
            stage_blocks.assert_called_once()
            self.assertEqual(result["artifact"], blocks)
            self.assertEqual(ctx.get("blocks"), blocks)

    def test_self_resume_hydrates_existing_report_blocks(self):
        import importlib
        self_driver = importlib.import_module("workflows.proforma_v1.self")
        blocks = [{"block_id": "DX", "domain": "diagnosis", "components": []}]
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            layout.ensure_dirs(work)
            path = self_runtime.output_path(work, "report_blocks", "report-blocks.yaml")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump({"blocks": blocks}, sort_keys=False), encoding="utf-8")
            ctx = WorkflowContext(work, "self")
            self.assertTrue(self_driver._self_step_complete("report.blocks", ctx))
            self.assertEqual(ctx.get("blocks"), blocks)

    def test_report_write_missing_source_blocks_fails_before_model_call(self):
        from workflows.proforma_v1 import step as proforma_step
        with tempfile.TemporaryDirectory() as td, patch.object(proforma_step, "_model_call") as model_call:
            with self.assertRaisesRegex(ValueError, "requires deterministic report_blocks"):
                proforma_step.stage_report_write(Path(td), None, {}, {}, None)
            model_call.assert_not_called()

    def test_report_blocks_are_deterministically_compatible_with_terraced_v6(self):
        from workflows.proforma_v1 import step as proforma_step
        from workflows.terraced_v6 import step as terraced_step
        element = {
            "schema_id": "TX-1", "domain": "treatment", "bucket": "treatment",
            "reason": "Use therapy X.", "variants": ["v01"], "source": {},
            "evidence": [{"card_tag": "[card:aaaaaaaaaaaa]"}],
        }
        registry = {"v01": {"gene": "ASXL1"}}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            proforma_work, terraced_work = root / "proforma", root / "terraced"
            proforma_work.mkdir(); terraced_work.mkdir()
            proforma_step.layout.ensure_dirs(proforma_work); terraced_step.layout.ensure_dirs(terraced_work)
            proforma_blocks = proforma_step.stage_blocks(proforma_work, {}, [element], registry)
            terraced_blocks = terraced_step.stage_blocks(terraced_work, {}, [element], registry)
            self.assertEqual(proforma_blocks, terraced_blocks)
            self.assertEqual(
                yaml.safe_load((proforma_step._existing_or_new(proforma_work, "report_blocks", "report-blocks.yaml")).read_text()),
                yaml.safe_load((terraced_step._existing_or_new(terraced_work, "report_blocks", "report-blocks.yaml")).read_text()),
            )


if __name__ == "__main__":
    unittest.main()
