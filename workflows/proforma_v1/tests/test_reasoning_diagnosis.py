from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from workflows.proforma_v1 import reasoning_runtime as rr


CASE = {
    "provisional_disease": "MDS",
    "bootstrap_cmcs": ["MDS"],
    "case_facts": [
        {"fact_id": "C1", "kind": "morphology", "value": "Dysplasia present"},
        {"fact_id": "C2", "kind": "copy_number", "value": "No 17p loss or cnLOH"},
    ],
}
REGISTRY = {"v01": {"variant_id": "V1", "gene": "TP53", "description": "TP53 variant"}}
CARDS = [
    {"card_tag": "[card:aaaaaaaaaaaa]", "card_id": "c1", "interpretation": "MDS requires cytopenia and dysplasia."},
    {"card_tag": "[card:bbbbbbbbbbbb]", "card_id": "c2", "interpretation": "Biallelic TP53 requires multi-hit TP53."},
]


def reasoning(authority="who5"):
    return {
        "authority": authority,
        "diagnosis": {
            "label": "MDS",
            "schema_disease": "MDS" if authority == "who5" else None,
            "diagnostic_effect": "unchanged",
            "status": "established" if authority != "second_diagnosis" else "none",
            "variant_assessments": [{
                "variant_id": "V1", "classification": "nonspecific",
                "other_pathology": None, "reason": "Does not define the proposed diagnosis."
            }],
        },
        "reasoning": [
            {"rule": "MDS requires cytopenia and dysplasia.", "case_fact_ids": ["C1"], "variant_ids": [], "assessment": "met", "supports_conclusion": True, "reason": "Dysplasia is supplied."},
            {"rule": "Biallelic TP53 requires multi-hit TP53.", "case_fact_ids": ["C2"], "variant_ids": ["V1"], "assessment": "not_met", "supports_conclusion": False, "reason": "No second hit is supplied."},
        ],
        "conclusion": {"operator": "all_of"},
        "reason": "MDS remains the diagnosis.",
    }


class ReasoningDiagnosisTests(unittest.TestCase):
    def setUp(self):
        self.ctx = {}
        self.wrap = {"__workflow_context__": self.ctx, "__work__": Path("/tmp/reasoning-test")}
        self.cards_patch = patch.object(rr, "_diagnostic_cards_for", lambda authority, work: (CASE, REGISTRY, CARDS, {}))
        self.envelope_patch = patch.object(rr, "_candidate_card_envelope", lambda cards, manifest: cards)
        self.cards_patch.start(); self.envelope_patch.start()
        self.addCleanup(self.cards_patch.stop); self.addCleanup(self.envelope_patch.stop)

    def test_owner_pack_hides_evidence_identifiers_and_internal_variant_ids(self):
        pack = rr.prepare_diagnostic_reasoning(self.wrap, {"authority": "who5"})
        self.assertEqual(set(pack["variant_registry"]), {"V1"})
        self.assertNotIn("v01", str(pack["variant_registry"]))
        self.assertTrue(pack["reference_material"])
        self.assertNotIn("card_tag", pack["reference_material"][0])
        self.assertNotIn("card_id", pack["reference_material"][0])

    def test_simple_clinical_reasoning_validates_without_atomic_graph_fields(self):
        self.ctx["diagnosis_who_reasoning"] = reasoning()
        result = rr.validate_diagnostic_reasoning_v2(self.wrap, {"authority": "who5"})
        self.assertEqual(result["status"], "pass", result)
        self.assertNotIn("root_id", self.ctx["diagnosis_who_reasoning"])
        self.assertNotIn("rules", self.ctx["diagnosis_who_reasoning"])

    def test_python_compiler_owns_aliases_ids_logic_and_schema_fields(self):
        self.ctx["diagnosis_who_reasoning"] = reasoning()
        owner = rr.compile_diagnostic_reasoning(self.wrap, {"authority": "who5"})
        self.assertEqual(owner["proposal"]["variant_assessments"][0]["variant_id"], "v01")
        self.assertEqual(owner["criteria"][1]["variant_ids"], ["v01"])
        self.assertEqual(owner["derived_states"], [])
        self.assertTrue(owner["rules"][0]["rule_id"].startswith("W-RULE-"))
        self.assertEqual(owner["rules"][0]["evidence_card_tags"], [])

    def test_evidence_match_is_separate_and_may_not_reference_unknown_cards(self):
        self.ctx["diagnosis_who_reasoning"] = reasoning()
        items = rr.prepare_diagnostic_evidence_match(self.wrap, {"authority": "who5"})
        self.ctx["diagnosis_who_evidence_match_items"] = items
        self.ctx["diagnosis_who_evidence_match"] = {"assignments": [
            {"reasoning_id": "R1", "card_tags": ["[card:aaaaaaaaaaaa]"]},
            {"reasoning_id": "R2", "card_tags": []},
        ]}
        self.assertEqual(rr.validate_diagnostic_evidence_match(self.wrap, {"authority": "who5"})["status"], "pass")
        self.ctx["diagnosis_who_evidence_match"]["assignments"][0]["card_tags"] = ["[card:cccccccccccc]"]
        result = rr.validate_diagnostic_evidence_match(self.wrap, {"authority": "who5"})
        self.assertEqual(result["status"], "fail")
        self.assertIn("outside the supplied candidate envelope", result["feedback"])

    def test_bad_card_audit_routes_feedback_to_local_em_reasoning_id(self):
        self.ctx["diagnosis_who_reasoning"] = reasoning()
        self.ctx["diagnosis_who_owner"] = rr.compile_diagnostic_reasoning(self.wrap, {"authority": "who5"})
        self.ctx["diagnostic_evidence_audit"] = {"audits": [{
            "rule_id": "W-RULE-002", "card_tag": "[card:bbbbbbbbbbbb]",
            "supports_rule": False, "comments": ["not actually supportive"],
        }]}
        result = rr.diagnostic_em_audit_review(self.wrap, {"authority": "who5"})
        self.assertEqual(result["status"], "fail")
        self.assertIn("R2", result["feedback"])
        self.assertNotIn("W-RULE", result["feedback"])

    def test_unknown_source_variant_is_clinical_input_reference_error_not_alias_guessing(self):
        bad = reasoning(); bad["reasoning"][1]["variant_ids"] = ["v01"]
        self.ctx["diagnosis_who_reasoning"] = bad
        result = rr.validate_diagnostic_reasoning_v2(self.wrap, {"authority": "who5"})
        self.assertEqual(result["status"], "fail")
        self.assertIn("source variant", result["feedback"])


if __name__ == "__main__":
    unittest.main()
