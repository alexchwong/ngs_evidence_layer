#!/usr/bin/env python3
"""Tests for the structured Step 6A content and citation-audit boundary."""

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "report_audit.py"
SPEC = importlib.util.spec_from_file_location("report_audit", SCRIPT)
report_audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report_audit)


def content_payload():
    return {
        "schema_version": "1.0",
        "answers": [
            {"rule_id": rule_id, "text": f"Answer for {rule_id}."}
            for rule_id in report_audit.EXPECTED_RULE_IDS
        ],
    }


def audit_payload(content=None):
    content = content or content_payload()
    return {
        "schema_version": "1.0",
        "answers": [
            {**answer, "card_ids": []}
            for answer in content["answers"]
        ],
    }


EVIDENCE = {
    "schema_version": "1.0",
    "cards": [
        {
            "card_id": "paper-a-C0001",
            "interpretation": "A supported assertion.",
        }
    ],
    "not_assessed": [],
    "suppressed": {},
    "provenance": {},
}


class ContentValidationTests(unittest.TestCase):
    def test_accepts_complete_content_document(self):
        payload = content_payload()
        self.assertIs(report_audit.validate_content(payload), payload)

    def test_requires_every_rule_in_order(self):
        payload = content_payload()
        payload["answers"][1]["rule_id"] = "R1.3"
        with self.assertRaisesRegex(ValueError, "must be 'R1.2'"):
            report_audit.validate_content(payload)

    def test_rejects_extra_fields(self):
        payload = content_payload()
        payload["answers"][0]["card_ids"] = []
        with self.assertRaisesRegex(ValueError, "unexpected card_ids"):
            report_audit.validate_content(payload)

    def test_rejects_multiline_text(self):
        payload = content_payload()
        payload["answers"][0]["text"] = "First.\nSecond."
        with self.assertRaisesRegex(ValueError, "must be one line"):
            report_audit.validate_content(payload)


class AuditValidationTests(unittest.TestCase):
    def test_accepts_exact_copy_with_known_and_empty_card_arrays(self):
        content = content_payload()
        audit = audit_payload(content)
        audit["answers"][0]["card_ids"] = ["paper-a-C0001"]
        self.assertIs(report_audit.validate_audit(content, audit, EVIDENCE), audit)

    def test_rejects_any_text_edit(self):
        content = content_payload()
        audit = audit_payload(content)
        audit["answers"][0]["text"] += " Edited."
        with self.assertRaisesRegex(ValueError, "changed text for R1.1"):
            report_audit.validate_audit(content, audit, EVIDENCE)

    def test_rejects_unknown_card_with_rule_id(self):
        content = content_payload()
        audit = audit_payload(content)
        audit["answers"][0]["card_ids"] = ["paper-a"]
        with self.assertRaisesRegex(
            ValueError,
            r"unknown evidence card\(s\): paper-a \(R1.1\)",
        ):
            report_audit.validate_audit(content, audit, EVIDENCE)

    def test_rejects_duplicate_card_ids(self):
        content = content_payload()
        audit = audit_payload(content)
        audit["answers"][0]["card_ids"] = ["paper-a-C0001", "paper-a-C0001"]
        with self.assertRaisesRegex(ValueError, "must not contain duplicates"):
            report_audit.validate_audit(content, audit, EVIDENCE)


class RenderTests(unittest.TestCase):
    def test_renders_markers_and_no_citation_dispositions(self):
        audit = audit_payload()
        audit["answers"][0]["card_ids"] = ["paper-a-C0001"]
        result = report_audit.render_markdown(audit)
        lines = result.splitlines()
        self.assertEqual(
            lines[0],
            "R1.1 Answer for R1.1. [card:paper-a-C0001]",
        )
        self.assertEqual(
            lines[1],
            "R1.2 Answer for R1.2. (no citation required)",
        )
        self.assertEqual(len(lines), len(report_audit.EXPECTED_RULE_IDS))


if __name__ == "__main__":
    unittest.main()