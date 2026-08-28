from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import yaml

from workflows.proforma_v1.engine import assemblers, checks, evidence, prompt_renderer, schema_validation
from workflows.proforma_v1 import self_runtime as self_runtime
from workflows.proforma_v1.engine.context import WorkflowContext
from workflows.proforma_v1.engine.workflow_compiler import WorkflowCompileError, compile_workflow
from workflows.proforma_v1.engine.workflow_runner import WorkflowRunner
from workflows.proforma_v1.executors.provider import ProviderExecutor
from workflows.proforma_v1.executors.self_executor import SelfExecutor
from workflows.proforma_v1.trace import TraceRecorder


HERE = Path(__file__).resolve().parents[1]
WORKFLOW = HERE / "workflow" / "default.yaml"


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
        self.assertEqual(len(workflow.steps), 24)
        self.assertEqual(
            [x.id for x in workflow.steps],
            [
                "structure", "corpus", "diagnosis.who1", "diagnosis.who1.routing_change",
                "diagnosis.who1.evidence.assignment", "diagnosis.who1.evidence.audit",
                "diagnosis.who1.evidence.adjudication", "diagnosis.who1.commit", "diagnosis.who2", "diagnosis.icc",
                "diagnosis.other", "diagnosis.finalize", "prognosis", "treatment", "biomarker",
                "germline", "evidence.assignment", "evidence.audit", "evidence.adjudication",
                "evidence.finalize", "report.blocks", "report.write", "report.preservation", "report.finalize",
            ],
        )
        self.assertEqual(workflow.step("report.finalize").needs, ("report.preservation",))

    def test_evidence_match_pass_count_is_workflow_configurable(self):
        workflow = compile_workflow()
        self.assertEqual(workflow.step("evidence.assignment").evidence["rescue_match_passes"], 1)

        doc = copy.deepcopy(self.doc)
        doc["steps"]["evidence.assignment"]["evidence"]["rescue_match_passes"] = 3
        custom = self._compile_doc(doc)
        self.assertEqual(custom.step("evidence.assignment").evidence["rescue_match_passes"], 3)

        doc = copy.deepcopy(self.doc)
        doc["steps"]["evidence.assignment"]["evidence"]["rescue_match_passes"] = 0
        custom = self._compile_doc(doc)
        self.assertEqual(custom.step("evidence.assignment").evidence["rescue_match_passes"], 0)

        doc = copy.deepcopy(self.doc)
        doc["steps"]["evidence.assignment"]["evidence"]["rescue_match_passes"] = 11
        with self.assertRaisesRegex(WorkflowCompileError, "maximum of 10"):
            self._compile_doc(doc)

    def test_dependency_cycle_is_rejected(self):
        doc = copy.deepcopy(self.doc)
        doc["steps"]["structure"]["needs"] = ["report.finalize"]
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

    def test_sequential_ids_match_terraced_v6_unpadded_namespace(self):
        variant_spec = {"rule": "sequential_ids", "path": "variants", "field": "variant_id", "prefix": "V"}
        fact_spec = {"rule": "sequential_ids", "path": "case_facts", "field": "fact_id", "prefix": "C"}
        checks.apply({"variants": [{"variant_id": "V1"}, {"variant_id": "V2"}]}, [variant_spec])
        checks.apply({"case_facts": [{"fact_id": "C1"}, {"fact_id": "C2"}]}, [fact_spec])
        with self.assertRaisesRegex(checks.CheckFailure, r"expected \['V1', 'V2'\]"):
            checks.apply({"variants": [{"variant_id": "V01"}, {"variant_id": "V02"}]}, [variant_spec])

        # Padding remains available, but must be an explicit workflow decision.
        padded = dict(variant_spec, width=2)
        checks.apply({"variants": [{"variant_id": "V01"}, {"variant_id": "V02"}]}, [padded])

    def test_default_structure_declared_check_accepts_v6_valid_fixture(self):
        fixture = HERE / "tests" / "fixtures" / "replay" / "structure_case--valid" / "response.json"
        workflow = compile_workflow()
        step = workflow.step("structure")
        schema = schema_validation.load_schema((workflow.asset_root / step.output["schema"]).resolve())
        doc = schema_validation.validate(
            fixture.read_text(encoding="utf-8"),
            fmt=step.output["format"],
            schema=schema,
            check_specs=step.checks,
            context={},
        )
        self.assertEqual([row["variant_id"] for row in doc["variants"]], ["V1"])

    def test_generic_row_checks_do_not_silently_accept_unknown_or_non_mapping_rows(self):
        with self.assertRaisesRegex(checks.CheckFailure, "expected exact row keys"):
            checks.apply(
                {"rows": [None]},
                [{"rule": "one_row_per", "path": "rows", "key": "id", "source": "expected"}],
                context={"expected": []},
            )

        spec = {
            "rule": "field_matches_source", "rows": "rows", "row_key": "id", "path": "gene",
            "source": "registry", "source_key": "id", "source_path": "gene",
        }
        checks.apply(
            {"rows": [{"id": "v01", "gene": "ASXL1"}]}, [spec],
            context={"registry": [{"id": "v01", "gene": "ASXL1"}]},
        )
        with self.assertRaisesRegex(checks.CheckFailure, "unknown source key"):
            checks.apply(
                {"rows": [{"id": "v99", "gene": None}]}, [spec],
                context={"registry": [{"id": "v01", "gene": "ASXL1"}]},
            )

    def test_explicit_empty_model_field_allowlist_rejects_model_owned_fields(self):
        with self.assertRaisesRegex(assemblers.AssemblyError, "non-owned field"):
            assemblers.assemble(
                "object_merge", {"model_field": "x"},
                spec={"source": "base", "model_fields": []}, context={"base": {"locked": 1}},
            )
        with self.assertRaisesRegex(assemblers.AssemblyError, "non-owned field"):
            assemblers.assemble(
                "keyed_rows", {"answers": {"v01": {"model_field": "x"}}},
                spec={"source": "registry", "source_key": "id", "answers_path": "answers", "model_fields": []},
                context={"registry": [{"id": "v01"}]},
            )

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
    def test_zero_assignment_is_not_audited_and_later_match_pass_can_rescue(self):
        claim = {"evidence_id": "E0001", "claim": "claim", "candidate_card_tags": ["[card:aaaaaaaaaaaa]", "[card:bbbbbbbbbbbb]"]}
        self.assertEqual(evidence.audit_targets(claim, []), [])

        items = [
            {"evidence_id": "E0001"},
            {"evidence_id": "E0002"},
        ]
        pass1 = {"matches": [
            {"evidence_id": "E0001", "card_tags": ["[card:aaaaaaaaaaaa]"]},
            {"evidence_id": "E0002", "card_tags": []},
        ]}
        merged, zero = evidence.merge_match_passes(items, [pass1])
        self.assertEqual(zero, ["E0002"])
        self.assertEqual(merged["matches"][0]["card_tags"], ["[card:aaaaaaaaaaaa]"])

        pass2 = {"matches": [
            {"evidence_id": "E0002", "card_tags": ["[card:bbbbbbbbbbbb]"]},
        ]}
        merged, zero = evidence.merge_match_passes(items, [pass1, pass2])
        self.assertEqual(zero, [])
        self.assertEqual(merged["matches"][1]["card_tags"], ["[card:bbbbbbbbbbbb]"])

    def test_match_pass_rejects_already_resolved_fact_on_later_pass(self):
        items = [{"evidence_id": "E0001"}, {"evidence_id": "E0002"}]
        pass1 = {"matches": [
            {"evidence_id": "E0001", "card_tags": ["[card:aaaaaaaaaaaa]"]},
            {"evidence_id": "E0002", "card_tags": []},
        ]}
        bad_pass2 = {"matches": [{"evidence_id": "E0001", "card_tags": []}]}
        with self.assertRaisesRegex(evidence.EvidenceError, "already-resolved"):
            evidence.merge_match_passes(items, [pass1, bad_pass2])

    def test_fact_blocks_are_json_segmented_and_card_local(self):
        rows = [
            {"evidence_id": "E0001", "reason": "first fact", "candidate_card_tags": ["[card:aaaaaaaaaaaa]"]},
            {"evidence_id": "E0002", "reason": "second fact", "candidate_card_tags": ["[card:bbbbbbbbbbbb]"]},
        ]
        catalog = {
            "A": {"card_id": "A", "interpretation": "A only"},
            "B": {"card_id": "B", "interpretation": "B only"},
        }
        from unittest.mock import patch
        with patch.object(self_runtime.staged, "_render_cards", side_effect=lambda cards, tags: cards[0]["interpretation"]):
            text = self_runtime._fact_blocks(
                rows, catalog, {"A": "aaaaaaaaaaaa", "B": "bbbbbbbbbbbb"},
                card_tags_field="candidate_card_tags",
            )
        self.assertIn("<fact-1>", text)
        self.assertIn("</fact-1>", text)
        self.assertIn("<fact-2>", text)
        first = text.split("<fact-1>\n", 1)[1].split("\n</fact-1>", 1)[0]
        second = text.split("<fact-2>\n", 1)[1].split("\n</fact-2>", 1)[0]
        first_doc = json.loads(first)
        second_doc = json.loads(second)
        self.assertEqual(first_doc["fact"], "first fact")
        self.assertEqual([x["card_id"] for x in first_doc["cards"]], ["[card:aaaaaaaaaaaa]"])
        self.assertNotIn("bbbbbbbbbbbb", first)
        self.assertEqual([x["card_id"] for x in second_doc["cards"]], ["[card:bbbbbbbbbbbb]"])
        self.assertNotIn("aaaaaaaaaaaa", second)

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
        common={"predicates":{"who1_routing_changed":lambda c:False,"who2_required":lambda c:False},"review_predicates":{"evidence_audit_resolved":lambda step,c,result:True}}
        pctx = WorkflowContext(Path("."), "provider", data=dict(common))
        sctx = WorkflowContext(Path("."), "self", data=dict(common))
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
        self.assertIn("_workflow_for_run", step_source)
        self.assertIn("_workflow_for_run", self_source)


if __name__ == "__main__":
    unittest.main()
