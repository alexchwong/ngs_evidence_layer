from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from workflows.proforma_v1.engine import evidence


HERE = Path(__file__).resolve().parents[1]


class EvidenceAdjudicationIdentityTests(unittest.TestCase):
    def setUp(self):
        self.disputes = [
            {"evidence_id": "E0002", "card_tag": "[card:111111111111]", "reason": "first"},
            {"evidence_id": "E0002", "card_tag": "[card:222222222222]", "reason": "second"},
            {"evidence_id": "E0003", "card_tag": "[card:333333333333]", "reason": "third"},
        ]

    def test_dispute_ids_are_deterministic_and_do_not_replace_source_identity(self):
        numbered = evidence.adjudication_disputes(self.disputes)
        self.assertEqual([row["dispute_id"] for row in numbered], ["D0001", "D0002", "D0003"])
        self.assertEqual(numbered[1]["evidence_id"], "E0002")
        self.assertEqual(numbered[1]["card_tag"], "[card:222222222222]")
        self.assertNotIn("dispute_id", self.disputes[0])

    def test_shuffled_model_answers_are_restored_to_canonical_dispute_order(self):
        doc = {
            "adjudications": [
                {"dispute_id": "D0003", "decision": "exclude", "reason": "third answer"},
                {"dispute_id": "D0001", "decision": "include", "reason": "first answer"},
                {"dispute_id": "D0002", "decision": "exclude", "reason": "second answer"},
            ]
        }
        result = evidence.validate_adjudication(doc, self.disputes)
        self.assertIs(result, doc)
        self.assertEqual(
            result["adjudications"],
            [
                {"evidence_id": "E0002", "card_tag": "[card:111111111111]", "decision": "include", "reason": "first answer"},
                {"evidence_id": "E0002", "card_tag": "[card:222222222222]", "decision": "exclude", "reason": "second answer"},
                {"evidence_id": "E0003", "card_tag": "[card:333333333333]", "decision": "exclude", "reason": "third answer"},
            ],
        )

    def test_missing_dispute_id_fails(self):
        doc = {"adjudications": [
            {"dispute_id": "D0001", "decision": "include", "reason": "first"},
            {"dispute_id": "D0003", "decision": "exclude", "reason": "third"},
        ]}
        with self.assertRaisesRegex(evidence.EvidenceError, "missing dispute_id"):
            evidence.validate_adjudication(doc, self.disputes)

    def test_duplicate_dispute_id_fails(self):
        doc = {"adjudications": [
            {"dispute_id": "D0001", "decision": "include", "reason": "first"},
            {"dispute_id": "D0001", "decision": "exclude", "reason": "duplicate"},
            {"dispute_id": "D0003", "decision": "exclude", "reason": "third"},
        ]}
        with self.assertRaisesRegex(evidence.EvidenceError, "duplicates dispute_id 'D0001'"):
            evidence.validate_adjudication(doc, self.disputes)

    def test_unknown_dispute_id_fails(self):
        doc = {"adjudications": [
            {"dispute_id": "D0001", "decision": "include", "reason": "first"},
            {"dispute_id": "D0002", "decision": "exclude", "reason": "second"},
            {"dispute_id": "D9999", "decision": "exclude", "reason": "unknown"},
        ]}
        with self.assertRaisesRegex(evidence.EvidenceError, "unknown dispute_id 'D9999'"):
            evidence.validate_adjudication(doc, self.disputes)

    def test_legacy_full_rows_are_accepted_and_canonicalised_for_existing_runs(self):
        doc = {"adjudications": [
            {"evidence_id": "E0003", "card_tag": "[card:333333333333]", "decision": "exclude", "reason": "third"},
            {"evidence_id": "E0002", "card_tag": "[card:111111111111]", "decision": "include", "reason": "first"},
            {"evidence_id": "E0002", "card_tag": "[card:222222222222]", "decision": "exclude", "reason": "second"},
        ]}
        evidence.validate_adjudication(doc, self.disputes)
        self.assertEqual(
            [(row["evidence_id"], row["card_tag"]) for row in doc["adjudications"]],
            [("E0002", "[card:111111111111]"), ("E0002", "[card:222222222222]"), ("E0003", "[card:333333333333]")],
        )


class EvidenceAdjudicationContractTests(unittest.TestCase):
    def test_model_schema_owns_only_dispute_id_decision_and_reason(self):
        schema = json.loads((HERE / "schemas" / "evidence_adjudicate.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        self.assertTrue(validator.is_valid({"adjudications": [
            {"dispute_id": "D0001", "decision": "include", "reason": "supported"}
        ]}))
        self.assertFalse(validator.is_valid({"adjudications": [
            {"evidence_id": "E0002", "card_tag": "[card:111111111111]", "decision": "include", "reason": "supported"}
        ]}))

    def test_general_prompt_keeps_threshold_and_partial_support_regression_rules(self):
        prompt = (HERE / "prompts" / "evidence_adjudicate.md").read_text(encoding="utf-8")
        self.assertIn("first dispute is `D0001`", prompt)
        self.assertIn("Do not reproduce evidence IDs or card tags", prompt)
        self.assertIn("may support one genuine element", prompt)
        self.assertIn("MDS/AML at 10%-19% blasts", prompt)
        self.assertIn("case has 2% blasts", prompt)
        self.assertIn("blast threshold is not met", prompt)
        self.assertNotIn("Preserve evidence IDs, card tags, and order exactly", prompt)

    def test_who1_prompt_uses_the_same_model_owned_identity_contract(self):
        prompt = (HERE / "prompts" / "evidence" / "diagnosis_adjudicate.md").read_text(encoding="utf-8")
        self.assertIn("first dispute is `D0001`", prompt)
        self.assertIn("Do not reproduce evidence IDs or card tags", prompt)
        self.assertIn("defining criterion or threshold can support an exclusion", prompt)
        self.assertNotIn("Preserve the supplied evidence ID, card tag, and order exactly", prompt)


if __name__ == "__main__":
    unittest.main()
