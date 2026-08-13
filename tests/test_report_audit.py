#!/usr/bin/env python3
"""Tests for merged Step 6A reporting analysis validation."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import report_audit  # noqa: E402


def analysis_payload():
    return {
        "schema_version": "1.0",
        "answers": [
            {
                "rule_id": rule_id,
                "text": f"Answer for {rule_id}.",
                "citation_status": "no_citation_required",
                "card_tags": [],
            }
            for rule_id in report_audit.EXPECTED_RULE_IDS
        ],
    }


EVIDENCE = {
    "schema_version": "1.0",
    "cards": [
        {
            "card_tag": "a1b2c3",
            "category": "prognosis",
            "genes": ["NPM1"],
            "diseases": ["AML"],
            "evidence_tier": "guideline criterion",
            "interpretation": "A supported assertion.",
            "escalates_to": None,
        }
    ],
    "not_assessed": [],
    "suppressed": {},
    "provenance": {},
}


class AnalysisValidationTests(unittest.TestCase):
    def test_accepts_complete_document(self):
        payload = analysis_payload()
        payload["answers"][0]["citation_status"] = "cited"
        payload["answers"][0]["card_tags"] = ["a1b2c3"]
        self.assertIs(report_audit.validate_analysis(payload, EVIDENCE), payload)

    def test_requires_every_rule_in_order(self):
        payload = analysis_payload()
        payload["answers"][1]["rule_id"] = "R1.3"
        with self.assertRaisesRegex(ValueError, "must be 'R1.2'"):
            report_audit.validate_analysis(payload, EVIDENCE)

    def test_rejects_multiline_text(self):
        payload = analysis_payload()
        payload["answers"][0]["text"] = "First.\nSecond."
        with self.assertRaisesRegex(ValueError, "must be one line"):
            report_audit.validate_analysis(payload, EVIDENCE)

    def test_requires_explicit_citation_state(self):
        payload = analysis_payload()
        payload["answers"][0]["citation_status"] = "cited"
        with self.assertRaisesRegex(ValueError, "marked cited but has no card_tags"):
            report_audit.validate_analysis(payload, EVIDENCE)

    def test_no_citation_state_requires_empty_tags(self):
        payload = analysis_payload()
        payload["answers"][0]["card_tags"] = ["a1b2c3"]
        with self.assertRaisesRegex(ValueError, "marked no_citation_required"):
            report_audit.validate_analysis(payload, EVIDENCE)

    def test_rejects_unknown_tag_with_rule_id(self):
        payload = analysis_payload()
        payload["answers"][0]["citation_status"] = "cited"
        payload["answers"][0]["card_tags"] = ["ffffff"]
        with self.assertRaisesRegex(
            ValueError,
            r"unknown evidence card tag\(s\): ffffff \(R1.1\)",
        ):
            report_audit.validate_analysis(payload, EVIDENCE)

    def test_rejects_duplicate_tags(self):
        payload = analysis_payload()
        payload["answers"][0]["citation_status"] = "cited"
        payload["answers"][0]["card_tags"] = ["a1b2c3", "a1b2c3"]
        with self.assertRaisesRegex(ValueError, "must not contain duplicates"):
            report_audit.validate_analysis(payload, EVIDENCE)

    def test_evidence_must_not_expose_full_card_id(self):
        evidence = {**EVIDENCE, "cards": [{**EVIDENCE["cards"][0], "card_id": "paper-C0001"}]}
        with self.assertRaisesRegex(ValueError, "must not expose full card_id"):
            report_audit.validate_analysis(analysis_payload(), evidence)


class RenderTests(unittest.TestCase):
    def test_renders_tags_and_no_citation_dispositions(self):
        analysis = analysis_payload()
        analysis["answers"][0]["citation_status"] = "cited"
        analysis["answers"][0]["card_tags"] = ["a1b2c3"]
        result = report_audit.render_markdown(analysis)
        lines = result.splitlines()
        self.assertEqual(lines[0], "R1.1 Answer for R1.1. [card:a1b2c3]")
        self.assertEqual(lines[1], "R1.2 Answer for R1.2. (no citation required)")
        self.assertEqual(len(lines), len(report_audit.EXPECTED_RULE_IDS))


if __name__ == "__main__":
    unittest.main()
