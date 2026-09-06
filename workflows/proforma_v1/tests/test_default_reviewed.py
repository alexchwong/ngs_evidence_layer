from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml

from workflows.proforma_v1 import domain_contract, stage_spec
from workflows.proforma_v1.engine.workflow_compiler import compile_workflow


HERE = Path(__file__).resolve().parents[1]
WORKFLOW = HERE / "workflow" / "default_reviewed.yaml"


class DefaultReviewedWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = compile_workflow(WORKFLOW)

    def test_workflow_compiles_and_is_selectable(self):
        self.assertEqual(self.workflow.workflow_id, "proforma-v1-default-reviewed")
        self.assertEqual(self.workflow.source.name, "default_reviewed.yaml")

    def test_no_ceo_card_filter_or_owner_assignment(self):
        for domain in ("prognosis", "treatment", "biomarker", "germline"):
            step = self.workflow.step(domain)
            self.assertFalse(step.evidence.get("owner_assignment"))
            self.assertEqual(step.evidence["cards"]["from"], "owner.cards")
            spec = step.stage_spec_obj
            self.assertFalse(any(row.get("rule") == "owner_evidence_card_tags" for row in spec.rules))

    def test_reviewed_contract_moves_assignment_downstream(self):
        for domain in ("prognosis", "treatment", "biomarker", "germline"):
            step = self.workflow.step(domain)
            contract = domain_contract.from_spec(step.stage_spec_obj)
            self.assertFalse(contract.owner_evidence_assignment)
            rendered = domain_contract.skeleton(
                contract,
                ["v01"],
                registry={"v01": {"gene": "TP53", "event_type": "sequence_variant", "vaf": "12%"}},
                applicable_disease="MDS",
            )
            self.assertIn("downstream evidence matcher owns", rendered)
            self.assertNotIn('[card:0123456789ab]', rendered)

    def test_default_contract_still_renders_owner_assignment(self):
        contract = domain_contract.contract("treatment")
        self.assertTrue(contract.owner_evidence_assignment)
        rendered = domain_contract.skeleton(
            contract,
            ["v01"],
            registry={"v01": {"gene": "TP53"}},
            applicable_disease="MDS",
        )
        self.assertIn('[card:0123456789ab]', rendered)
        self.assertNotIn("downstream evidence matcher owns", rendered)

    def test_one_cross_domain_audit_rewinds_whole_clinical_path(self):
        audit = self.workflow.step("clinical.audit")
        self.assertEqual(audit.role, "reasoning_audit")
        self.assertEqual(audit.review["target"], "diagnosis.who1")
        self.assertEqual(audit.review["on_fail"]["max_cycles"], 2)
        feedback_ref = "feedback.default_reviewed.clinical_audit"
        for sid in (
            "diagnosis.who1", "diagnosis.who2", "diagnosis.icc",
            "prognosis", "treatment", "biomarker", "germline",
        ):
            step = self.workflow.step(sid)
            self.assertEqual(step.inputs["clinical_audit_feedback"]["from"], feedback_ref)

    def test_audit_is_after_evidence_and_before_report(self):
        audit = self.workflow.step("clinical.audit")
        self.assertEqual(self.workflow.step("clinical.packet").needs, ("evidence.finalize",))
        self.assertEqual(audit.needs, ("clinical.packet",))
        self.assertEqual(self.workflow.step("report.blocks").needs, ("clinical.audit",))
        self.assertEqual(audit.inputs["clinical_packet"]["from"], "artifacts.default_reviewed_clinical_packet")

    def test_germline_reviewed_schema_allows_empty_predisposition_tags(self):
        path = HERE / "schemas" / "default_reviewed" / "germline.json"
        schema = json.loads(path.read_text(encoding="utf-8"))
        tags = schema["$defs"]["predispositionEvidence"]["properties"]["evidence_card_tags"]
        self.assertEqual(tags.get("maxItems"), 0)

    def test_audit_prompt_contains_generic_dublin_class_guard(self):
        prompt = (HERE / "prompts" / "default_reviewed" / "clinical_audit.md").read_text(encoding="utf-8")
        self.assertIn("defining criterion", prompt)
        self.assertIn("do not special-case TP53", prompt)
        self.assertIn("Post-evidence soundness", prompt)
        self.assertIn("prognostic_frameworks.md", prompt)


if __name__ == "__main__":
    unittest.main()
