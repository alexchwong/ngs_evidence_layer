from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

import yaml

from workflows.proforma_v1 import reasoning_runtime as rr
from workflows.proforma_v1.executors.self_executor import SelfExecutor


CARD = "[card:aaaaaaaaaaaa]"


class FakeContext:
    def __init__(self, data=None):
        self.data = dict(data or {})
        self.work = None
        self.executor = "self"
    def get(self, key, default=None):
        return self.data.get(key, default)
    def put(self, key, value):
        self.data[key] = value


def _pack(authority):
    return {
        "authority": authority,
        "structured_case": {
            "provisional_disease": "MDS",
            "case_facts": [
                {"fact_id": "C1", "kind": "marrow", "value": "12% blasts with dysplasia"},
            ],
        },
        "case_fact_registry": {"C1": {"fact_id": "C1", "kind": "marrow", "value": "12% blasts with dysplasia"}},
        "variant_registry": {
            "v01": {"variant_id": "v01", "gene": "NPM1", "description": "NPM1 frameshift"},
            "v02": {"variant_id": "v02", "gene": "DNMT3A", "description": "DNMT3A R882H"},
            "v03": {"variant_id": "v03", "gene": "FLT3", "description": "FLT3-ITD"},
        },
        "candidate_cards": [{"card_tag": CARD, "card_id": "demo", "claim": "NPM1-mutated AML diagnostic rule"}],
    }


def _owner(authority, prefix, label, *, schema_disease=None, second_status="established"):
    is_second = authority == "second_diagnosis"
    if is_second:
        return {
            "authority": authority,
            "proposal": {
                "proposal_id": f"{prefix}P1", "label": "No concurrent neoplasm", "kind": "second_diagnosis",
                "schema_disease": None, "diagnostic_effect": "unchanged", "variant_ids": [],
                "variant_assessments": [
                    {"variant_id": v, "classification": "nonspecific", "other_pathology": None, "reason": "No independent second diagnosis."}
                    for v in ("v01", "v02", "v03")
                ],
                "status": "none",
            },
            "rules": [], "derived_states": [], "criteria": [], "logic": [], "root_id": None,
            "reason": "No concurrent diagnosis is established from the supplied facts and cards.",
        }
    return {
        "authority": authority,
        "proposal": {
            "proposal_id": f"{prefix}P1", "label": label, "kind": "diagnosis",
            "schema_disease": schema_disease, "diagnostic_effect": "superseded", "variant_ids": ["v01"],
            "variant_assessments": [
                {"variant_id": "v01", "classification": "diagnostic_for_primary", "other_pathology": None, "reason": "NPM1 is diagnosis-defining in the proposed classifier."},
                {"variant_id": "v02", "classification": "nonspecific", "other_pathology": None, "reason": "Not diagnosis-defining."},
                {"variant_id": "v03", "classification": "nonspecific", "other_pathology": None, "reason": "Not independently diagnosis-defining."},
            ],
            "status": "established",
        },
        "rules": [{"rule_id": f"{prefix}R1", "statement": "NPM1 mutation can define AML in this classifier.", "evidence_required": True, "evidence_card_tags": [CARD]}],
        "derived_states": [],
        "criteria": [{"criterion_id": f"{prefix}C1", "rule_ids": [f"{prefix}R1"], "case_fact_ids": [], "variant_ids": ["v01"], "state_ids": [], "proposed_status": "met"}],
        "logic": [], "root_id": f"{prefix}C1",
        "reason": "The supplied NPM1 mutation satisfies the evidence-backed defining rule.",
    }


class ReasoningDiagnosisTests(unittest.TestCase):
    def _context(self):
        ctx = FakeContext()
        ctx.put("diagnosis_who_pack", _pack("who5"))
        ctx.put("diagnosis_icc_pack", _pack("icc"))
        ctx.put("diagnosis_second_pack", _pack("second_diagnosis"))
        ctx.put("diagnosis_who_owner", _owner("who5", "W-", "AML with NPM1 mutation", schema_disease="AML"))
        ctx.put("diagnosis_icc_owner", _owner("icc", "I-", "AML with mutated NPM1"))
        ctx.put("diagnosis_second_owner", _owner("second_diagnosis", "S-", "unused"))
        return ctx


    def test_reasoning_yaml_routes_diagnostic_model_work_through_native_self_handlers(self):
        workflow_path = Path(__file__).resolve().parents[1] / "workflow" / "reasoning.yaml"
        steps = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))["steps"]
        seen = []
        executor = SelfExecutor({"generic_model": lambda step, context: seen.append(step.id) or {"status": "handoff", "handoff": {"stage": step.id, "manifest": {"schema": (step.output or {}).get("schema")}}}})
        context = FakeContext(); context.executor = "self"
        results = {}
        for step_id in ("diagnosis.who", "diagnosis.icc", "diagnosis.second", "diagnosis.evidence.audit", "diagnosis.reasoning.audit", "diagnosis.evidence.adjudication"):
            cfg = steps[step_id]
            step = SimpleNamespace(id=step_id, execution=cfg["execution"], output=cfg.get("output") or {})
            result = executor.execute(step, context)
            self.assertEqual(result["status"], "handoff")
            results[step_id] = result["handoff"]["manifest"]
        self.assertEqual(results["diagnosis.evidence.audit"]["self_pass"], "diagnostic_review")
        self.assertEqual(results["diagnosis.reasoning.audit"]["self_pass"], "diagnostic_review")
        self.assertTrue(results["diagnosis.evidence.audit"]["continue_in_same_frontier_pass"])
        self.assertTrue(results["diagnosis.reasoning.audit"]["continue_in_same_frontier_pass"])
        self.assertEqual(results["diagnosis.evidence.adjudication"]["self_pass"], "diagnostic_adjudication")
        self.assertFalse(results["diagnosis.evidence.adjudication"]["continue_in_same_frontier_pass"])
        self.assertTrue(results["diagnosis.evidence.audit"]["schema"])
        self.assertEqual(seen, ["diagnosis.who", "diagnosis.icc", "diagnosis.second", "diagnosis.evidence.audit", "diagnosis.reasoning.audit", "diagnosis.evidence.adjudication"])

    def test_demo_one_atomic_diagnosis_changes_mds_to_npm1_aml_after_independent_audits(self):
        ctx = self._context()
        payload = {"__workflow_context__": ctx}
        registry = rr.build_diagnostic_registry(payload, {})
        ctx.put("diagnostic_atomic_registry", registry)
        owner_assignments = rr.collect_diagnostic_owner_assignments(payload, {})
        ctx.put("diagnostic_owner_assignments", owner_assignments)
        self.assertEqual(owner_assignments["rescue_items"], [])
        merged = rr.merge_diagnostic_assignments(payload, {})
        ctx.put("diagnostic_assignments", merged)
        audit_items = rr.prepare_diagnostic_evidence_audit(payload, {})
        ctx.put("diagnostic_evidence_audit_items", audit_items)
        ctx.put("diagnostic_evidence_audit", {"audits": [
            {"rule_id": row["rule_id"], "card_tag": row["card_tag"], "supports_rule": True, "comments": ["Exact rule supported."]}
            for row in audit_items
        ]})
        self.assertEqual(rr.validate_diagnostic_evidence_audit(payload, {})["status"], "pass")
        ctx.put("diagnostic_evidence_disputes", [])
        ctx.put("diagnostic_evidence_decisions", rr.finalize_diagnostic_evidence(payload, {}))
        reasoning_items = rr.prepare_diagnostic_reasoning_audit(payload, {})
        ctx.put("diagnostic_reasoning_items", reasoning_items)
        criteria = []
        for item in reasoning_items:
            if item["item_type"] == "criterion":
                criteria.append({"criterion_id": item["criterion"]["criterion_id"], "status": "met", "case_fact_ids": item["criterion"].get("case_fact_ids", []), "comments": ["The supplied NPM1 variant satisfies the rule."]})
        ctx.put("diagnostic_reasoning_audit", {"derived_states": [], "criteria": criteria})
        self.assertEqual(rr.validate_diagnostic_reasoning_audit(payload, {})["status"], "pass")
        result = rr.evaluate_diagnoses(payload, {})
        self.assertEqual(result["owner_status"], {"who5": "pass", "icc": "pass", "second_diagnosis": "pass"})
        self.assertEqual(result["detail"]["who5"]["root_status"], "met")
        self.assertEqual(result["detail"]["icc"]["root_status"], "met")

    def test_valid_owner_card_assignments_make_self_matching_rescue_only(self):
        ctx = self._context(); payload = {"__workflow_context__": ctx}
        ctx.put("diagnostic_atomic_registry", rr.build_diagnostic_registry(payload, {}))
        state = rr.collect_diagnostic_owner_assignments(payload, {})
        self.assertEqual(state["rescue_items"], [])
        self.assertEqual({row["source"] for row in state["pairs"]}, {"owner"})

    def test_owner_validation_reports_namespace_reference_and_card_envelope_errors_together(self):
        ctx = self._context()
        bad = _owner("who5", "W-", "AML with NPM1 mutation", schema_disease="AML")
        bad["rules"][0]["rule_id"] = "BAD-R1"
        bad["rules"][0]["evidence_card_tags"] = ["[card:bbbbbbbbbbbb]"]
        bad["criteria"][0]["rule_ids"] = ["MISSING"]
        bad["criteria"][0]["variant_ids"] = ["v99"]
        ctx.put("diagnosis_who_owner", bad)
        result = rr.validate_diagnostic_owner({"__workflow_context__": ctx}, {"authority": "who5"})
        self.assertEqual(result["status"], "fail")
        codes = {row["code"] for row in result["issues"]}
        self.assertIn("wrong_reasoning_namespace", codes)
        self.assertIn("unknown_rule_id", codes)
        self.assertIn("unknown_variant_id", codes)
        self.assertIn("card_outside_owner_envelope", codes)
        self.assertGreaterEqual(result["feedback"].count("What is wrong:"), 4)

    def test_evidence_audit_validation_reports_every_missing_pair(self):
        ctx = self._context(); payload = {"__workflow_context__": ctx}
        ctx.put("diagnostic_evidence_audit_items", [
            {"rule_id": "W-R1", "card_tag": CARD},
            {"rule_id": "I-R1", "card_tag": CARD},
        ])
        ctx.put("diagnostic_evidence_audit", {"audits": []})
        result = rr.validate_diagnostic_evidence_audit(payload, {})
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["issue_count"], 2)
        self.assertEqual(result["feedback"].count("What is wrong:"), 2)

    def test_unsupported_derived_state_blocks_a_met_criterion_from_committing(self):
        ctx = self._context(); payload = {"__workflow_context__": ctx}
        who = ctx.get("diagnosis_who_owner")
        who["derived_states"] = [{"state_id": "W-S1", "label": "qualifying molecular state", "case_fact_ids": [], "variant_ids": ["v01"], "proposed_value": "qualifying"}]
        who["criteria"][0]["state_ids"] = ["W-S1"]
        ctx.put("diagnostic_atomic_registry", rr.build_diagnostic_registry(payload, {}))
        ctx.put("diagnostic_evidence_decisions", {"rule_support": {"W-R1": True, "I-R1": True}})
        ctx.put("diagnostic_reasoning_audit", {
            "derived_states": [{"state_id": "W-S1", "status": "unsupported", "value": "not_qualifying", "case_fact_ids": [], "comments": ["facts do not support proposed value"]}],
            "criteria": [
                {"criterion_id": "W-C1", "status": "met", "case_fact_ids": [], "comments": ["owner criterion claimed met"]},
                {"criterion_id": "I-C1", "status": "met", "case_fact_ids": [], "comments": ["met"]},
            ],
        })
        result = rr.evaluate_diagnoses(payload, {})
        self.assertEqual(result["owner_status"]["who5"], "fail")
        self.assertEqual(result["detail"]["who5"]["criterion_status"]["W-C1"], "unknown")
        self.assertIn("derived state", result["feedback"]["who5"])

    def test_unsupported_rule_forces_unknown_criterion_and_owner_redo_feedback(self):
        ctx = self._context(); payload = {"__workflow_context__": ctx}
        ctx.put("diagnostic_atomic_registry", rr.build_diagnostic_registry(payload, {}))
        ctx.put("diagnostic_evidence_decisions", {"rule_support": {"W-R1": False, "I-R1": True}})
        ctx.put("diagnostic_reasoning_audit", {"derived_states": [], "criteria": [{"criterion_id": "I-C1", "status": "met", "case_fact_ids": [], "comments": ["met"]}]})
        result = rr.evaluate_diagnoses(payload, {})
        self.assertEqual(result["owner_status"]["who5"], "fail")
        self.assertIn("W-R1", result["feedback"]["who5"])
        self.assertEqual(result["owner_status"]["icc"], "pass")


if __name__ == "__main__":
    unittest.main()
