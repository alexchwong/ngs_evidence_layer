from __future__ import annotations

import json
import copy
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

    def test_preassigned_global_dispute_ids_are_immutable(self):
        batch = [
            {"dispute_id": "D0009", **self.disputes[0]},
            {"dispute_id": "D0010", **self.disputes[1]},
        ]
        self.assertEqual(
            [row["dispute_id"] for row in evidence.adjudication_disputes(batch)],
            ["D0009", "D0010"],
        )

    def test_mixed_preassigned_and_unassigned_disputes_fail(self):
        mixed = [{"dispute_id": "D0001", **self.disputes[0]}, self.disputes[1]]
        with self.assertRaisesRegex(evidence.EvidenceError, "either all supply"):
            evidence.adjudication_disputes(mixed)

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
        self.assertIn("Copy that supplied ID exactly", prompt)
        self.assertIn("do not derive or renumber IDs from row position", prompt)
        self.assertIn("Do not reproduce evidence IDs or card tags", prompt)
        self.assertIn("may support one complete proposition", prompt)
        self.assertIn("Supporting only a fragment of one proposition is insufficient", prompt)
        self.assertIn("MDS/AML at 10%-19% blasts", prompt)
        self.assertIn("case has 2% blasts", prompt)
        self.assertIn("blast threshold is not met", prompt)
        self.assertNotIn("Preserve evidence IDs, card tags, and order exactly", prompt)

    def test_who1_prompt_uses_the_same_model_owned_identity_contract(self):
        prompt = (HERE / "prompts" / "evidence" / "diagnosis_adjudicate.md").read_text(encoding="utf-8")
        self.assertIn("Copy that supplied ID exactly", prompt)
        self.assertIn("do not derive or renumber IDs from row position", prompt)
        self.assertIn("Do not reproduce evidence IDs or card tags", prompt)
        self.assertIn("defining criterion or threshold can support an exclusion", prompt)
        self.assertNotIn("Preserve the supplied evidence ID, card tag, and order exactly", prompt)


class EvidenceBatchingPrimitiveTests(unittest.TestCase):
    def setUp(self):
        self.units = [{"evidence_id": f"E{index:04d}", "payload": [index]} for index in range(1, 20)]

    def test_partition_empty_below_exact_and_above_threshold(self):
        self.assertEqual(evidence.partition_units([], 8), [])
        self.assertEqual([len(x) for x in evidence.partition_units(self.units[:5], 8)], [5])
        self.assertEqual([len(x) for x in evidence.partition_units(self.units[:8], 8)], [8])
        self.assertEqual([len(x) for x in evidence.partition_units(self.units, 8)], [8, 8, 3])

    def test_partition_is_stable_and_does_not_mutate_source_units(self):
        before = copy.deepcopy(self.units)
        first = evidence.partition_units(self.units, 8)
        second = evidence.partition_units(self.units, 8)
        self.assertEqual(first, second)
        self.assertEqual(self.units, before)
        self.assertIs(first[0][0], self.units[0])

    def test_merge_restores_global_order_without_rewriting_rows(self):
        batches = evidence.partition_units(self.units, 8)
        docs = [{"matches": [
            {"evidence_id": row["evidence_id"], "card_tags": [f"tag-{row['evidence_id']}"]}
            for row in reversed(batch)
        ]} for batch in batches]
        model_rows = {row["evidence_id"]: row for doc in docs for row in doc["matches"]}
        merged = evidence.merge_batch_rows(
            self.units, docs, container="matches", id_field="evidence_id"
        )
        self.assertEqual([row["evidence_id"] for row in merged["matches"]], [row["evidence_id"] for row in self.units])
        for row in merged["matches"]:
            self.assertIs(row, model_rows[row["evidence_id"]])

    def test_merge_rejects_missing_duplicate_and_unknown_ids(self):
        units = self.units[:2]
        with self.assertRaisesRegex(evidence.EvidenceError, "missing"):
            evidence.merge_batch_rows(units, [{"matches": [{"evidence_id": "E0001"}]}], container="matches", id_field="evidence_id")
        with self.assertRaisesRegex(evidence.EvidenceError, "duplicate"):
            evidence.merge_batch_rows(units, [{"matches": [{"evidence_id": "E0001"}]}, {"matches": [{"evidence_id": "E0001"}]}], container="matches", id_field="evidence_id")
        with self.assertRaisesRegex(evidence.EvidenceError, "unknown"):
            evidence.merge_batch_rows(units, [{"matches": [{"evidence_id": "E0001"}, {"evidence_id": "E9999"}]}], container="matches", id_field="evidence_id")


if __name__ == "__main__":
    unittest.main()
