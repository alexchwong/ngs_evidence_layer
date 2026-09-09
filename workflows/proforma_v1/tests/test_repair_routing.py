from __future__ import annotations

import unittest

import yaml

from scripts.core import schema_preserving_repair
from scripts.core.validated_model_task import (
    Budgets,
    TaskIO,
    TaskRequest,
    ValidationFailure,
    ValidationIssue,
    run,
)


class _Harness:
    def __init__(self, owner_output: str, *, schema_outputs=(), content_outputs=()):
        self.owner_output = owner_output
        self.schema_outputs = list(schema_outputs)
        self.content_outputs = list(content_outputs)
        self.owner_calls = 0
        self.schema_calls = 0
        self.content_calls = 0
        self.output = None
        self.state = {}
        self.content_messages = []

    def io(self):
        def owner(messages):
            self.owner_calls += 1
            return self.owner_output

        def schema(prompt, attempt):
            self.schema_calls += 1
            return self.schema_outputs.pop(0)

        def content(messages, attempt):
            self.content_calls += 1
            self.content_messages.append(messages)
            return self.content_outputs.pop(0)

        return TaskIO(
            call_model=owner,
            call_syntax_model=None,
            call_schema_model=schema,
            call_content_model=content,
            load_state=lambda key: dict(self.state),
            save_state=lambda key, value: setattr(self, "state", dict(value)),
            read_output=lambda: self.output,
            write_output=lambda text: setattr(self, "output", text),
        )


class SchemaPreservingCanonicalizationTests(unittest.TestCase):
    def test_germline_camelcase_and_rendered_card_are_canonicalized(self):
        raw = """classification:\n- variant: V1\n  eligibility: assess\n  predispositionEvidence:\n    mechanism: DDX41 predisposition\n    evidenceCardTags:\n    - '[card:abcdef123456] DDX41 predisposition evidence'\n"""
        rendered, records = schema_preserving_repair.normalize_text(raw, format_name="yaml")
        doc = yaml.safe_load(rendered)
        row = doc["classification"][0]
        self.assertNotIn("predispositionEvidence", row)
        self.assertIn("predisposition_evidence", row)
        self.assertEqual(row["predisposition_evidence"]["evidence_card_tags"], ["[card:abcdef123456]"])
        transforms = {record["transform"] for record in records}
        self.assertIn("canonicalize_field_alias", transforms)
        self.assertIn("extract_exact_card_tag", transforms)

    def test_skip_branch_materializes_only_missing_structural_defaults(self):
        raw = """classification:\n- variant: V1\n  eligibility: skip_no_predisposition_evidence\n  reason: no supplied predisposition evidence\n"""
        rendered, _ = schema_preserving_repair.normalize_text(raw, format_name="yaml")
        row = yaml.safe_load(rendered)["classification"][0]
        for key in (
            "predisposition_evidence", "event_compatibility", "age", "vaf",
            "personal_history", "family_history", "phenotype", "bucket",
        ):
            self.assertIsNone(row[key])
        self.assertEqual(row["evidence_card_tags"], [])

        conflict = """classification:\n- variant: V1\n  eligibility: skip_no_predisposition_evidence\n  age:\n    status: supportive\n    reason: young age\n"""
        rendered, _ = schema_preserving_repair.normalize_text(conflict, format_name="yaml")
        row = yaml.safe_load(rendered)["classification"][0]
        self.assertEqual(row["age"]["status"], "supportive")

    def test_ambiguous_rendered_card_is_not_guessed(self):
        value = "supported by [card:aaaaaaaaaaaa] and [card:bbbbbbbbbbbb]"
        raw = f"evidence_card_tags:\n- '{value}'\n"
        rendered, records = schema_preserving_repair.normalize_text(raw, format_name="yaml")
        self.assertEqual(yaml.safe_load(rendered)["evidence_card_tags"], [value])
        self.assertEqual(records, [])


class RepairRoutingTests(unittest.TestCase):
    def _request(self, validator):
        return TaskRequest(
            task_id="fixture",
            messages=[
                {"role": "system", "content": "clinical system"},
                {"role": "user", "content": "original case and task"},
            ],
            validate=validator,
            budgets=Budgets(content=2, serialization=0, rewrite=1, schema=1),
            fmt="yaml",
        )

    def test_schema_preserving_issue_routes_to_schema_repair_not_content(self):
        def validator(text):
            doc = yaml.safe_load(text)
            if "new_key" not in doc:
                raise ValidationFailure("fixture", [ValidationIssue(
                    path="$.new_key", problem="non-canonical key", required_fix="rename old_key to new_key",
                    repair_class="schema_preserving",
                )])
            return "ok"

        h = _Harness("old_key: explicit\n", schema_outputs=["new_key: explicit\n"])
        result = run(self._request(validator), h.io())
        self.assertEqual(result, "new_key: explicit\n")
        self.assertEqual((h.owner_calls, h.schema_calls, h.content_calls), (1, 1, 0))

    def test_unclassified_issue_routes_to_content_not_schema(self):
        def validator(text):
            doc = yaml.safe_load(text)
            if doc.get("decision") != "corrected":
                raise ValidationFailure("fixture", [ValidationIssue(
                    path="$.decision", problem="substantive decision rejected", required_fix="reconsider decision",
                )])
            return "ok"

        h = _Harness("decision: original\n", content_outputs=["decision: corrected\n"])
        result = run(self._request(validator), h.io())
        self.assertEqual(result, "decision: corrected\n")
        self.assertEqual((h.owner_calls, h.schema_calls, h.content_calls), (1, 0, 1))
        flattened = "\n".join(str(message.get("content", "")) for message in h.content_messages[0])
        self.assertIn("original case and task", flattened)
        self.assertIn("decision: original", flattened)

    def test_germline_assess_without_predisposition_evidence_routes_to_content(self):
        def validator(text):
            doc = yaml.safe_load(text)
            row = doc["classification"][0]
            if row.get("eligibility") == "assess" and row.get("predisposition_evidence") is None:
                raise ValidationFailure("fixture", [ValidationIssue(
                    path="$.classification[0].predisposition_evidence",
                    problem="assess branch lacks a clinical predisposition-evidence proposition",
                    required_fix="supply or reconsider the clinical predisposition-evidence assessment",
                    repair_class="content",
                )])
            return "ok"

        original = "classification:\n- variant: V1\n  eligibility: assess\n  predisposition_evidence: null\n"
        corrected = "classification:\n- variant: V1\n  eligibility: skip_no_predisposition_evidence\n  predisposition_evidence: null\n"
        h = _Harness(original, content_outputs=[corrected])
        result = run(self._request(validator), h.io())
        self.assertIn("skip_no_predisposition_evidence", result)
        self.assertEqual((h.owner_calls, h.schema_calls, h.content_calls), (1, 0, 1))

    def test_mixed_schema_and_content_routes_in_sequence(self):
        def validator(text):
            doc = yaml.safe_load(text)
            issues = []
            if "new_key" not in doc:
                issues.append(ValidationIssue(
                    path="$.new_key", problem="non-canonical key", required_fix="rename old_key to new_key",
                    repair_class="schema_preserving",
                ))
            if doc.get("decision") != "corrected":
                issues.append(ValidationIssue(
                    path="$.decision", problem="substantive decision rejected", required_fix="reconsider decision",
                    repair_class="content",
                ))
            if issues:
                raise ValidationFailure("fixture", issues)
            return "ok"

        h = _Harness(
            "old_key: explicit\ndecision: original\n",
            schema_outputs=["new_key: explicit\ndecision: original\n"],
            content_outputs=["new_key: explicit\ndecision: corrected\n"],
        )
        result = run(self._request(validator), h.io())
        self.assertIn("decision: corrected", result)
        self.assertEqual((h.owner_calls, h.schema_calls, h.content_calls), (1, 1, 1))

    def test_schema_repair_cannot_change_scalar_meaning(self):
        def validator(text):
            doc = yaml.safe_load(text)
            if "new_key" not in doc:
                raise ValidationFailure("fixture", [ValidationIssue(
                    path="$.new_key", problem="non-canonical key", required_fix="rename key",
                    repair_class="schema_preserving",
                )])
            return "ok"

        h = _Harness("old_key: explicit\n", schema_outputs=["new_key: changed\n"])
        with self.assertRaises(Exception):
            run(self._request(validator), h.io())
        self.assertEqual(h.schema_calls, 1)
        self.assertEqual(h.content_calls, 0)


if __name__ == "__main__":
    unittest.main()
