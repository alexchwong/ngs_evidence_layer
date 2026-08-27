from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import yaml

from workflows.proforma_v1.engine import assemblers, checks, evidence, prompt_renderer, schema_validation
from workflows.proforma_v1.engine.context import WorkflowContext
from workflows.proforma_v1.engine.workflow_compiler import WorkflowCompileError, compile_workflow
from workflows.proforma_v1.engine.workflow_runner import WorkflowRunner
from workflows.proforma_v1.executors.provider import ProviderExecutor
from workflows.proforma_v1.executors.self_executor import SelfExecutor
from workflows.proforma_v1.trace import TraceRecorder


HERE = Path(__file__).resolve().parents[1]
WORKFLOW = HERE / "workflow.yaml"


class WorkflowCompilerTests(unittest.TestCase):
    def setUp(self):
        self.doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))

    def _compile_doc(self, doc):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", encoding="utf-8", delete=False) as fh:
            yaml.safe_dump(doc, fh, sort_keys=False)
            path = Path(fh.name)
        try:
            return compile_workflow(path)
        finally:
            path.unlink(missing_ok=True)

    def test_canonical_workflow_compiles_to_expected_logical_graph(self):
        workflow = compile_workflow()
        self.assertEqual(workflow.workflow_id, "proforma-v1")
        self.assertEqual(len(workflow.steps), 17)
        self.assertEqual(
            [x.id for x in workflow.steps],
            [
                "structure", "corpus", "diagnosis.who1", "diagnosis.icc", "diagnosis.who2",
                "diagnosis.other", "diagnosis.finalize", "prognosis", "treatment", "biomarker",
                "germline", "evidence.assignment", "evidence.audit", "evidence.adjudication",
                "evidence.finalize", "report.blocks", "report",
            ],
        )
        self.assertEqual(workflow.step("report").needs, ("report.blocks",))

    def test_dependency_cycle_is_rejected(self):
        doc = copy.deepcopy(self.doc)
        doc["steps"]["structure"]["needs"] = ["report"]
        with self.assertRaisesRegex(WorkflowCompileError, "dependency cycle"):
            self._compile_doc(doc)

    def test_duplicate_step_id_and_malformed_yaml_are_rejected_before_compile(self):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", encoding="utf-8", delete=False) as fh:
            fh.write("version: 1\nworkflow_id: proforma-v1\nevidence_policies: {}\nsteps:\n  x: {type: transform}\n  x: {type: model}\n")
            duplicate = Path(fh.name)
        try:
            with self.assertRaisesRegex(WorkflowCompileError, "duplicate YAML key"):
                compile_workflow(duplicate)
        finally:
            duplicate.unlink(missing_ok=True)

        with tempfile.NamedTemporaryFile("w", suffix=".yaml", encoding="utf-8", delete=False) as fh:
            fh.write("steps: [unterminated\n")
            malformed = Path(fh.name)
        try:
            with self.assertRaises(WorkflowCompileError):
                compile_workflow(malformed)
        finally:
            malformed.unlink(missing_ok=True)

    def test_static_compile_rejects_invalid_references_and_registries(self):
        mutations = []
        doc = copy.deepcopy(self.doc); doc["steps"]["corpus"]["transform"] = "not_registered"; mutations.append((doc, "unknown transform"))
        doc = copy.deepcopy(self.doc); doc["steps"]["structure"]["checks"] = [{"rule": "not_registered"}]; mutations.append((doc, "unknown check"))
        doc = copy.deepcopy(self.doc); doc["steps"]["structure"]["checks"] = [{"rule": "custom", "handler": "not_registered"}]; mutations.append((doc, "unknown custom check"))
        doc = copy.deepcopy(self.doc); doc["steps"]["structure"]["role"] = "not_registered"; mutations.append((doc, "unknown model role"))
        doc = copy.deepcopy(self.doc); doc["steps"]["structure"]["when"] = {"expression": "a and b"}; mutations.append((doc, "unsupported condition"))
        doc = copy.deepcopy(self.doc); doc["steps"]["structure"]["inputs"]["bad"] = {"from": "artifacts.future"}; mutations.append((doc, "before it can exist"))
        for mutated, expected in mutations:
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(WorkflowCompileError, expected):
                    self._compile_doc(mutated)

    def test_undeclared_runtime_placeholder_fails_compilation(self):
        prompt = HERE / "prompts" / "_phase2_placeholder_test.md"
        prompt.write_text("Known {{ input.case_text }} unknown {{ input.not_declared }}\n", encoding="utf-8")
        doc = copy.deepcopy(self.doc)
        doc["steps"]["structure"]["prompt"] = "prompts/_phase2_placeholder_test.md"
        try:
            with self.assertRaisesRegex(WorkflowCompileError, "undeclared runtime placeholder"):
                self._compile_doc(doc)
        finally:
            prompt.unlink(missing_ok=True)

    def test_deferred_evidence_cannot_cross_adjudication_barrier(self):
        doc = copy.deepcopy(self.doc)
        doc["steps"]["evidence.finalize"]["needs"] = ["evidence.audit"]
        with self.assertRaisesRegex(WorkflowCompileError, "without its adjudication barrier"):
            self._compile_doc(doc)

        doc = copy.deepcopy(self.doc)
        doc["steps"]["evidence.adjudication"]["barrier_for"] = ["evidence.audit"]
        with self.assertRaisesRegex(WorkflowCompileError, "no adjudication barrier"):
            self._compile_doc(doc)


class PromptAndValidationTests(unittest.TestCase):
    def test_prompt_includes_and_runtime_placeholders_are_bounded(self):
        with tempfile.TemporaryDirectory(dir=HERE / "prompts") as td:
            root = Path(td)
            (root / "inc.md").write_text("Included.\n", encoding="utf-8")
            (root / "main.md").write_text('{{ include "inc.md" }}\nCase: {{ input.case }}\n{{ output.template }}\n', encoding="utf-8")
            rendered = prompt_renderer.render(root / "main.md", root=root, inputs={"case": {"x": 1}}, output_template="OUTPUT")
            self.assertIn("Included.", rendered)
            self.assertIn("x: 1", rendered)
            self.assertIn("OUTPUT", rendered)
            (root / "bad.md").write_text("{{ input.unknown }}\n", encoding="utf-8")
            with self.assertRaises(prompt_renderer.PromptRenderError):
                prompt_renderer.render(root / "bad.md", root=root, inputs={"case": "x"})

    def test_generic_schema_checks_and_keyed_rows_assembly(self):
        model_schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["answers"],
            "properties": {"answers": {"type": "object"}},
        }
        final_schema = {
            "type": "object", "required": ["classification"],
            "properties": {"classification": {"type": "array", "minItems": 2}},
        }
        context = {"registry": [{"id": "v01", "gene": "ASXL1"}, {"id": "v02", "gene": "TET2"}]}
        raw = json.dumps({"answers": {"v01": {"effect": "adverse"}, "v02": {"effect": "neutral"}}})
        assembled = schema_validation.validate(
            raw, fmt="json", schema=model_schema, context=context,
            assembly={
                "type": "keyed_rows", "source": "registry", "source_key": "id", "answers_path": "answers",
                "deterministic_fields": {"variant": {"from_row": "id"}, "gene": {"from_row": "gene"}},
                "model_fields": ["effect"], "output_path": "classification",
            }, final_schema=final_schema,
        )
        self.assertEqual([r["variant"] for r in assembled["classification"]], ["v01", "v02"])
        with self.assertRaises(assemblers.AssemblyError):
            assemblers.assemble("keyed_rows", {"answers": {"v99": {"effect": "x"}}}, spec={"source": "registry", "source_key": "id"}, context=context)
        checks.apply({"ids": ["a", "b"]}, [{"rule": "subset", "path": "ids", "source": "allowed"}], context={"allowed": ["a", "b", "c"]})


class EvidenceEngineTests(unittest.TestCase):
    def test_zero_assignment_audits_full_pool_and_rescued_card_is_disputed(self):
        claim = {"evidence_id": "E0001", "claim": "claim", "candidate_card_tags": ["[card:aaa]", "[card:bbb]"]}
        self.assertEqual(evidence.audit_targets(claim, []), claim["candidate_card_tags"])
        result = evidence.compare(claim=claim, assigned_card_tags=[], audit_rows=[
            {"card_tag": "[card:aaa]", "decision": "exclude"},
            {"card_tag": "[card:bbb]", "decision": "include", "comments": "rescued"},
        ])
        self.assertEqual(result["disputes"][0]["dispute_type"], "resolver_zero_auditor_include")

    def test_positive_assignment_audits_selected_only_and_adjudication_is_cropped(self):
        claim = {"evidence_id": "E0001", "claim": "claim", "candidate_card_tags": ["[card:aaa]", "[card:bbb]"]}
        self.assertEqual(evidence.audit_targets(claim, ["[card:aaa]"]), ["[card:aaa]"])
        result = evidence.compare(claim=claim, assigned_card_tags=["[card:aaa]"], audit_rows=[{"card_tag": "[card:aaa]", "decision": "exclude"}])
        disputes = result["disputes"]
        good = {"adjudications": [{"evidence_id": "E0001", "card_tag": "[card:aaa]", "decision": "exclude", "reason": "not support"}]}
        self.assertIs(evidence.validate_adjudication(good, disputes), good)
        bad = {"adjudications": [{"evidence_id": "E0001", "card_tag": "[card:bbb]", "decision": "include", "reason": "x"}]}
        with self.assertRaises(evidence.EvidenceError):
            evidence.validate_adjudication(bad, disputes)

    def test_declarative_claim_extraction_is_deterministic(self):
        artifact = {"classification": [
            {"variant": "v01", "category": "adverse", "reason": "First claim"},
            {"variant": "v02", "category": "no_evidence", "reason": None},
        ]}
        declarations = [{
            "path": "classification[].reason", "id_from": "classification[].variant",
            "when": {"path": "category", "not_in": ["no_evidence"]},
        }]
        claims = evidence.extract_claims(owner="prognosis", artifact=artifact, declarations=declarations, candidate_card_tags=["[card:aaa]"])
        self.assertEqual(claims, [{
            "evidence_id": "E0001", "owner": "prognosis", "owner_item_id": "v01",
            "claim": "First claim", "candidate_card_tags": ["[card:aaa]"],
        }])


class SharedRunnerTests(unittest.TestCase):
    def test_provider_and_self_adapters_consume_the_same_compiled_graph(self):
        workflow = compile_workflow()
        provider_names = {s.execution.get("provider_handler") for s in workflow.steps}
        self_names = {s.execution.get("self_handler") for s in workflow.steps}
        provider = ProviderExecutor({name: (lambda step, ctx: {"status": "complete"}) for name in provider_names if name})
        self_exec = SelfExecutor({name: (lambda step, ctx: {"status": "complete"}) for name in self_names if name})
        pctx = WorkflowContext(Path("."), "provider")
        sctx = WorkflowContext(Path("."), "self")
        WorkflowRunner(workflow, provider).run_all(pctx)
        WorkflowRunner(workflow, self_exec).run_all(sctx)
        expected = {s.id for s in workflow.steps}
        self.assertEqual(pctx.completed, expected)
        self.assertEqual(sctx.completed, expected)

    def test_real_entrypoints_delegate_ordering_to_shared_runner(self):
        step_source = (HERE / "step.py").read_text(encoding="utf-8")
        self_source = (HERE / "self.py").read_text(encoding="utf-8")
        self.assertIn("WorkflowRunner(compiled", step_source)
        self.assertIn("WorkflowRunner(workflow", self_source)
        self.assertIn("compile_workflow()", step_source)
        self.assertIn("compile_workflow()", self_source)


if __name__ == "__main__":
    unittest.main()
