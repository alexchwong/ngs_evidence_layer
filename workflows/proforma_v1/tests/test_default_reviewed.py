from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

HERE = Path(__file__).resolve().parents[1]
WORKFLOW = HERE / "workflow" / "default_reviewed.yaml"
DEFAULT = HERE / "workflow" / "default.yaml"
PROMPTS = HERE / "prompts" / "default_reviewed"
SCHEMAS = HERE / "schemas" / "default_reviewed"
STAGES = HERE / "stages" / "default_reviewed"


class DefaultReviewedArchitectureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        cls.steps = cls.doc["steps"]
        cls.order = list(cls.steps)

    def test_workflow_compiles_in_real_compiler(self):
        try:
            from workflows.proforma_v1.engine.workflow_compiler import compile_workflow
        except ModuleNotFoundError as exc:
            self.skipTest(f"partial changed-file overlay lacks unchanged compiler modules: {exc}")
        compiled = compile_workflow(WORKFLOW)
        self.assertEqual(compiled.workflow_id, "proforma-v1-default-reviewed")

    def test_all_dependencies_review_targets_and_progress_entries_exist(self):
        known = set(self.steps)
        for step_id, step in self.steps.items():
            with self.subTest(step=step_id):
                self.assertFalse(set(step.get("needs") or []) - known)
                if step.get("review"):
                    self.assertIn(step["review"]["target"], known)
        assigned = [s for phase in self.doc["presentation"]["progress_phases"] for s in phase["steps"]]
        self.assertEqual(len(assigned), len(set(assigned)))
        self.assertEqual(set(assigned), known)

    def test_default_workflow_is_not_replaced_by_reviewed_reasoning(self):
        if not DEFAULT.is_file():
            self.skipTest("partial changed-file overlay lacks unchanged default.yaml")
        text = DEFAULT.read_text(encoding="utf-8")
        self.assertNotIn("default_reviewed_owner_packet", text)
        self.assertNotIn("reasoning_precheck.md", text)
        self.assertNotIn("default_reviewed_postcheck_prepare", text)

    def test_who1_r1_precedes_routing_and_blocking_evidence(self):
        self.assertLess(self.order.index("diagnosis.who1"), self.order.index("who1.secretary"))
        self.assertLess(self.order.index("who1.secretary"), self.order.index("who1.precheck"))
        self.assertLess(self.order.index("who1.precheck.coherence"), self.order.index("diagnosis.who1.routing_change"))
        self.assertLess(self.order.index("diagnosis.who1.routing_change"), self.order.index("diagnosis.who1.evidence.assignment"))

    def test_each_owner_has_secretary_and_pre_evidence_reasoning_gate(self):
        owners = ("who1", "who2", "icc", "prognosis", "treatment", "biomarker", "germline")
        for owner in owners:
            with self.subTest(owner=owner):
                self.assertIn(f"{owner}.packet", self.steps)
                self.assertIn(f"{owner}.secretary", self.steps)
                self.assertIn(f"{owner}.secretary.compile", self.steps)
                self.assertIn(f"{owner}.precheck", self.steps)
                self.assertIn(f"{owner}.precheck.validate", self.steps)
                self.assertIn(f"{owner}.precheck.representation", self.steps)
                self.assertIn(f"{owner}.precheck.coherence", self.steps)

    def test_secretary_failure_retries_secretary_and_coherence_failure_retries_ceo(self):
        ceo_step = {
            "who1": "diagnosis.who1", "who2": "diagnosis.who2", "icc": "diagnosis.icc",
            "prognosis": "prognosis", "treatment": "treatment", "biomarker": "biomarker", "germline": "germline",
        }
        for owner, ceo in ceo_step.items():
            with self.subTest(owner=owner):
                self.assertEqual(self.steps[f"{owner}.secretary.compile"]["review"]["target"], f"{owner}.secretary")
                self.assertEqual(self.steps[f"{owner}.precheck.validate"]["review"]["target"], f"{owner}.precheck")
                self.assertEqual(self.steps[f"{owner}.precheck.representation"]["review"]["target"], f"{owner}.secretary")
                self.assertEqual(self.steps[f"{owner}.precheck.coherence"]["review"]["target"], ceo)

    def test_secretary_r1_and_r2_use_reasoning_aware_model_handler(self):
        model_steps = [
            *(f"{o}.secretary" for o in ("who1","who2","icc","prognosis","treatment","biomarker","germline")),
            *(f"{o}.precheck" for o in ("who1","who2","icc","prognosis","treatment","biomarker","germline")),
            "who1.postcheck", "postcheck.reasoning",
        ]
        for step_id in model_steps:
            with self.subTest(step=step_id):
                self.assertEqual(self.steps[step_id]["execution"]["provider_handler"], "reasoning_model")
                self.assertEqual(self.steps[step_id]["execution"]["self_handler"], "reasoning_model")

    def test_ptbg_evidence_waits_for_all_r1_gates(self):
        self.assertEqual(
            set(self.steps["evidence.assignment"]["needs"]),
            {f"{d}.precheck.coherence" for d in ("prognosis", "treatment", "biomarker", "germline")},
        )

    def test_r2_is_post_evidence_and_conditionally_called(self):
        self.assertEqual(self.steps["postcheck.prepare"]["needs"], ["evidence.finalize"])
        self.assertEqual(self.steps["postcheck.validate"]["review"]["target"], "postcheck.reasoning")
        self.assertEqual(self.steps["who1.postcheck.validate"]["review"]["target"], "who1.postcheck")
        self.assertEqual(
            self.steps["postcheck.reasoning"]["when"],
            {"has_items": {"artifact": "default_reviewed_postcheck_items"}},
        )
        self.assertEqual(
            self.steps["who1.postcheck"]["when"],
            {"has_items": {"artifact": "default_reviewed_who1_postcheck_items"}},
        )
        self.assertNotIn("clinical.packet", self.steps)
        self.assertNotIn("clinical.audit", self.steps)

    def test_r2_review_is_affected_owner_only(self):
        targets = {
            "postcheck.who1": "diagnosis.who1", "postcheck.who2": "diagnosis.who2",
            "postcheck.icc": "diagnosis.icc", "postcheck.prognosis": "prognosis",
            "postcheck.treatment": "treatment", "postcheck.biomarker": "biomarker",
            "postcheck.germline": "germline",
        }
        for step_id, target in targets.items():
            self.assertEqual(self.steps[step_id]["review"]["target"], target)

    def test_reasoning_trace_is_explicit_artifact_before_report(self):
        self.assertIn("reasoning.trace", self.steps)
        self.assertEqual(self.steps["report.blocks"]["needs"], ["reasoning.trace"])
        self.assertLess(self.order.index("reasoning.trace"), self.order.index("report.blocks"))


class DefaultReviewedOwnerContractTests(unittest.TestCase):
    def test_reviewed_ceo_schemas_have_no_card_bookkeeping_fields(self):
        for name in ("prognosis.json", "treatment.json", "biomarker.json", "germline.json"):
            with self.subTest(schema=name):
                text = (SCHEMAS / name).read_text(encoding="utf-8")
                self.assertNotIn("evidence_card_tags", text)
                self.assertNotIn("other_evidence_card_tags", text)

    def test_reviewed_prompts_have_no_card_output_contract(self):
        for name in ("prognosis.md", "treatment.md", "biomarker.md", "germline.md"):
            with self.subTest(prompt=name):
                text = (PROMPTS / name).read_text(encoding="utf-8")
                self.assertIn("downstream", text.lower())
                self.assertNotIn("evidence_card_tags:", text)
                self.assertNotIn("other_evidence_card_tags:", text)

    def test_reviewed_stage_contracts_use_clinical_only_schemas(self):
        for domain in ("prognosis", "treatment", "biomarker", "germline"):
            with self.subTest(domain=domain):
                doc = yaml.safe_load((STAGES / f"{domain}.yaml").read_text(encoding="utf-8"))
                self.assertEqual(doc["output"]["schema"], f"default_reviewed/{domain}.json")
                self.assertFalse(any((r or {}).get("rule") == "owner_evidence_card_tags" for r in doc.get("rules") or []))


    def test_reviewed_contract_moves_assignment_downstream_and_pivot_restores_slots(self):
        try:
            from workflows.proforma_v1 import domain_contract, stage_spec
        except ImportError as exc:
            self.skipTest(f"partial changed-file overlay lacks unchanged stage modules: {exc}")
        for domain in ("prognosis", "treatment", "biomarker", "germline"):
            with self.subTest(domain=domain):
                spec = stage_spec.load_path(STAGES / f"{domain}.yaml", expected_stage=domain)
                contract = domain_contract.from_spec(spec)
                self.assertFalse(contract.owner_evidence_assignment)
                rendered = domain_contract.skeleton(
                    contract, ["v01"],
                    registry={"v01": {"gene": "TP53", "event_type": "sequence_variant", "vaf": "12%"}},
                    applicable_disease="MDS",
                )
                self.assertIn("downstream evidence matcher owns", rendered)
                self.assertNotIn("evidence_card_tags:", rendered)

        treatment_spec = stage_spec.load_path(STAGES / "treatment.yaml", expected_stage="treatment")
        treatment_contract = domain_contract.from_spec(treatment_spec)
        pivoted = domain_contract.pivot({
            "applicable_disease": "MDS",
            "classification": [{
                "variant": "v01", "gene": "TP53",
                "treatment_category": "no_drug_implication",
                "reason": "No reportable treatment implication."
            }],
        }, treatment_contract)
        self.assertEqual(pivoted["no_drug_implication"][0]["evidence_card_tags"], [])

    def test_default_contract_still_renders_owner_assignment(self):
        try:
            from workflows.proforma_v1 import domain_contract
        except ImportError as exc:
            self.skipTest(f"partial changed-file overlay lacks unchanged stage modules: {exc}")
        contract = domain_contract.contract("treatment")
        self.assertTrue(contract.owner_evidence_assignment)
        rendered = domain_contract.skeleton(
            contract, ["v01"], registry={"v01": {"gene": "TP53"}}, applicable_disease="MDS"
        )
        self.assertIn("evidence_card_tags:", rendered)
        self.assertIn("[card:0123456789ab]", rendered)
        self.assertNotIn("downstream evidence matcher owns", rendered)

    def test_generic_reasoning_prompts_do_not_embed_disease_rules(self):
        text = (PROMPTS / "reasoning_precheck.md").read_text(encoding="utf-8").lower()
        for forbidden in ("tp53", "cml", "ipss", "who5", "icc", "eln 2022"):
            self.assertNotIn(forbidden, text)
        self.assertIn("no corpus", text)
        self.assertIn("internally coherent", text)


class SecretaryAndR2GuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sys
        root = HERE.parents[1]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from workflows.proforma_v1 import default_reviewed_reasoning as reviewed
        cls.reviewed = reviewed

    def _wrap(self):
        return {"__workflow_context__": {}, "__work__": Path("/tmp/default-reviewed-reasoning-test")}

    def test_secretary_compiler_owns_ids_and_keeps_context_out_of_dependencies(self):
        packet = {
            "owner": "who1",
            "conclusions": [{
                "conclusion_id": "C001", "conclusion": "Diagnosis A", "synthesis": "Rule applies.",
                "evidence_schema_id": "DX-WHO5",
                "source_fragments": [
                    {"fragment_id": "S001", "path": "reason", "value": "Rule applies.", "role": "supporting"},
                    {"fragment_id": "S002", "path": "variant_assessments[0].reason", "value": "No second event.", "role": "context"},
                ],
            }],
        }
        secretary = {"owner": "who1", "conclusions": [{"conclusion_id": "C001", "atoms": [
            {"source_fragment_id": "S001", "text": "Rule applies.", "evidence_class": "literature_rule"},
            {"source_fragment_id": "S002", "text": "No second event.", "evidence_class": "case_fact"},
        ]}]}
        def artifact(_ctx, step_id, _name):
            return packet if step_id == "who1.packet" else secretary if step_id == "who1.secretary" else None
        with patch.object(self.reviewed, "_generic_artifact", side_effect=artifact):
            out = self.reviewed.compile_secretary(self._wrap(), {"step_id": "who1.secretary.compile"})
        self.assertEqual(out["status"], "pass", out)
        conclusion = out["graph"]["conclusions"][0]
        self.assertEqual([x["fact_id"] for x in conclusion["facts"]], ["F001", "F002"])
        self.assertEqual(conclusion["fact_ids"], ["F001"])
        self.assertEqual(conclusion["context_fact_ids"], ["F002"])
        self.assertEqual(conclusion["facts"][0]["source_path"], "reason")
        self.assertEqual(conclusion["facts"][1]["source_path"], "variant_assessments[0].reason")

    def test_secretary_compiler_rejects_omitted_source_fragment(self):
        packet = {"owner":"who1","conclusions":[{"conclusion_id":"C001","conclusion":"A","synthesis":"B","evidence_schema_id":"DX-WHO5","source_fragments":[{"fragment_id":"S001","path":"reason","value":"B","role":"supporting"}]}]}
        secretary = {"owner":"who1","conclusions":[{"conclusion_id":"C001","atoms":[]}]}
        with patch.object(self.reviewed, "_generic_artifact", side_effect=lambda _c, sid, _n: packet if sid=="who1.packet" else secretary):
            out = self.reviewed.compile_secretary(self._wrap(), {"step_id":"who1.secretary.compile"})
        self.assertEqual(out["status"], "fail")
        self.assertIn("omitted source fragment", out["feedback"])

    def test_r2_skips_when_evidence_backed_schema_survives(self):
        compiled = {"graph":{"conclusions":[{"conclusion_id":"C001","conclusion":"Adverse","synthesis":"Rule","evidence_schema_id":"PX-OTHER_EVIDENCE_ADVERSE-01","facts":[{"fact_id":"F001","text":"Rule","dependency_role":"supporting","evidence_class":"literature_rule"}]}]}}
        def artifact(_ctx, sid, _name):
            if sid == "who2.packet": return None
            if sid == "prognosis.secretary.compile": return compiled
            return {"graph":{"conclusions":[]}} if sid.endswith(".secretary.compile") else None
        with patch.object(self.reviewed, "_generic_artifact", side_effect=artifact), patch.object(self.reviewed, "_supported_schema_ids", return_value={"PX-OTHER_EVIDENCE_ADVERSE-01"}):
            out = self.reviewed.postcheck_prepare(self._wrap(), {})
        self.assertEqual(out, [])

    def test_r2_runs_only_after_contributing_literature_fact_is_lost(self):
        compiled = {"graph":{"conclusions":[{"conclusion_id":"C001","conclusion":"Adverse","synthesis":"Rule","evidence_schema_id":"PX-OTHER_EVIDENCE_ADVERSE-01","facts":[
            {"fact_id":"F001","text":"Patient has variant","dependency_role":"supporting","evidence_class":"case_fact"},
            {"fact_id":"F002","text":"Variant is adverse in disease","dependency_role":"supporting","evidence_class":"literature_rule"},
        ]}]}}
        def artifact(_ctx, sid, _name):
            if sid == "who2.packet": return None
            if sid == "prognosis.secretary.compile": return compiled
            return {"graph":{"conclusions":[]}} if sid.endswith(".secretary.compile") else None
        with patch.object(self.reviewed, "_generic_artifact", side_effect=artifact), patch.object(self.reviewed, "_supported_schema_ids", return_value=set()):
            out = self.reviewed.postcheck_prepare(self._wrap(), {})
        row = next(x for x in out if x["owner"] == "prognosis")
        self.assertEqual(row["surviving_facts"], ["Patient has variant"])
        self.assertEqual(row["removed_facts"], ["Variant is adverse in disease"])

    def test_r1_structural_failure_retries_r1_not_secretary_or_ceo(self):
        malformed={"representation":{"status":"faithful","comments":[]}}
        with patch.object(self.reviewed,"_generic_artifact",return_value=malformed):
            out=self.reviewed.validate_precheck(self._wrap(),{"step_id":"prognosis.precheck.validate"})
        self.assertEqual(out["status"],"fail")
        self.assertIn("coherence.status",out["feedback"])

    def test_r2_structural_validator_requires_exact_affected_conclusions(self):
        items=[{"owner":"prognosis","conclusion_id":"C001"},{"owner":"treatment","conclusion_id":"C002"}]
        result={"verdicts":[{"owner":"prognosis","conclusion_id":"C001","verdict":"survives","comments":[]}]}
        with patch.object(self.reviewed,"_generic_artifact",side_effect=lambda _c,sid,_n: items if sid=="postcheck.prepare" else result):
            out=self.reviewed.validate_postcheck(self._wrap(),{})
        self.assertEqual(out["status"],"fail")
        self.assertIn("treatment",out["feedback"])

    def test_r2_qualification_routes_back_to_ceo_in_minimal_pass(self):
        items=[{"owner":"prognosis","conclusion_id":"C001"}]
        result={"verdicts":[{"owner":"prognosis","conclusion_id":"C001","verdict":"survives_with_qualification","comments":["Remove unsupported attribution."]}]}
        with patch.object(self.reviewed, "_generic_artifact", side_effect=lambda _c,sid,_n: items if sid=="postcheck.prepare" else result if sid=="postcheck.reasoning" else None):
            out=self.reviewed.postcheck_review(self._wrap(),{"step_id":"postcheck.prognosis"})
        self.assertEqual(out["status"],"fail")
        self.assertIn("unsupported attribution",out["feedback"])


class StructuredOutputHardeningTests(unittest.TestCase):
    def test_duplicate_yaml_mapping_key_is_rejected_without_last_value_wins(self):
        from scripts.core.syntax_repair.adapters import DuplicateMappingKeyError, adapter_for
        with self.assertRaises(DuplicateMappingKeyError):
            adapter_for("yaml").deterministic_cleanup("reason: first\nreason: second\n")

    def test_engine_parser_rejects_duplicate_yaml_mapping_key(self):
        try:
            from workflows.proforma_v1.engine.schema_validation import StructuredValidationError, parse
        except ImportError as exc:
            self.skipTest(f"partial changed-file overlay lacks unchanged engine modules: {exc}")
        with self.assertRaises(StructuredValidationError):
            parse("reason: first\nreason: second\n", "yaml")

    def test_deterministic_prepare_contract_contradiction_stops_without_model_retry(self):
        from scripts.core import validated_model_task as task
        calls=[]
        request=task.TaskRequest(
            task_id="contract-test", messages=[], fmt="yaml", mode="standard", budgets=task.Budgets(content=3,serialization=0,rewrite=0),
            prepare=lambda raw: raw.replace("evidence_card_tags: []\n", ""),
            validate=lambda candidate: (_ for _ in ()).throw(ValueError("'evidence_card_tags' is a required property")),
        )
        io=task.TaskIO(
            call_model=lambda messages: calls.append(messages) or "reason: ok\nevidence_card_tags: []\n",
            load_state=lambda key: {}, save_state=lambda key,value: None,
            read_output=lambda: None, write_output=lambda value: None,
        )
        with self.assertRaisesRegex(task.TaskContractError, "workflow_contract_error"):
            task.run(request,io)
        self.assertEqual(len(calls),1)


if __name__ == "__main__":
    unittest.main()
