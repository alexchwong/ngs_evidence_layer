#!/usr/bin/env python3
"""Tests for strict Markdown Step 6A reporting-analysis validation."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import report_audit  # noqa: E402


def draft_text():
    return "\n".join(
        f"{rule_id} Answer for {rule_id}. (no citation required)"
        for rule_id in report_audit.EXPECTED_RULE_IDS
    ) + "\n"


EVIDENCE = """# Evidence

### Fixture

- Citation marker: [card:a1b2c3]
- Citation marker: [card:d4e5f6]

## Refs

a1b2c3: primary ref 1
d4e5f6: primary ref 2

## References

1. Fixture reference.
2. Second fixture reference.
"""


class DraftValidationTests(unittest.TestCase):
    def test_accepts_complete_document(self):
        text = draft_text().replace(
            "R1.1 Answer for R1.1. (no citation required)",
            "R1.1 Answer for R1.1. [card:a1b2c3]",
        )
        result = report_audit.validate_draft(text, EVIDENCE)
        self.assertEqual(result[0]["rule_id"], "R1.1")
        self.assertEqual(result[0]["card_tags"], ["a1b2c3"])
        self.assertEqual(result[0]["citation_status"], "cited")
        self.assertEqual(result[1]["citation_status"], "no_citation_required")

    def test_requires_every_rule_in_order(self):
        text = draft_text().replace(
            "R1.2 Answer for R1.2.", "R1.3 Answer for R1.2.", 1
        )
        with self.assertRaisesRegex(ValueError, "must begin with 'R1.2'"):
            report_audit.validate_draft(text, EVIDENCE)

    def test_rejects_missing_rule(self):
        lines = draft_text().splitlines()
        text = "\n".join(lines[:-1]) + "\n"
        with self.assertRaisesRegex(ValueError, "exactly 52 lines; found 51"):
            report_audit.validate_draft(text, EVIDENCE)

    def test_rejects_blank_line_or_extra_markdown(self):
        text = draft_text().replace("\nR1.2", "\n\nR1.2", 1)
        with self.assertRaisesRegex(ValueError, "exactly 52 lines; found 53"):
            report_audit.validate_draft(text, EVIDENCE)

    def test_requires_explicit_terminal_citation_disposition(self):
        text = draft_text().replace(
            "R1.1 Answer for R1.1. (no citation required)",
            "R1.1 Answer for R1.1.",
        )
        with self.assertRaisesRegex(ValueError, "R1.1 has no valid terminal citation disposition"):
            report_audit.validate_draft(text, EVIDENCE)

    def test_accepts_multiple_adjacent_terminal_tags(self):
        text = draft_text().replace(
            "R1.1 Answer for R1.1. (no citation required)",
            "R1.1 Answer for R1.1. [card:a1b2c3][card:d4e5f6]",
        )
        result = report_audit.validate_draft(text, EVIDENCE)
        self.assertEqual(result[0]["card_tags"], ["a1b2c3", "d4e5f6"])

    def test_rejects_unknown_tag_with_rule_id(self):
        text = draft_text().replace(
            "R1.1 Answer for R1.1. (no citation required)",
            "R1.1 Answer for R1.1. [card:ffffff]",
        )
        with self.assertRaisesRegex(
            ValueError,
            r"unknown evidence card tag\(s\): ffffff \(R1.1\)",
        ):
            report_audit.validate_draft(text, EVIDENCE)

    def test_rejects_duplicate_tags(self):
        text = draft_text().replace(
            "R1.1 Answer for R1.1. (no citation required)",
            "R1.1 Answer for R1.1. [card:a1b2c3][card:a1b2c3]",
        )
        with self.assertRaisesRegex(ValueError, "R1.1 terminal card tags must not contain duplicates"):
            report_audit.validate_draft(text, EVIDENCE)

    def test_rejects_inline_card_marker(self):
        text = draft_text().replace(
            "R1.1 Answer for R1.1. (no citation required)",
            "R1.1 Answer [card:a1b2c3] for R1.1. [card:d4e5f6]",
        )
        with self.assertRaisesRegex(ValueError, "marker inside answer prose"):
            report_audit.validate_draft(text, EVIDENCE)

    def test_rejects_no_citation_marker_inside_prose(self):
        text = draft_text().replace(
            "R1.1 Answer for R1.1. (no citation required)",
            "R1.1 Say (no citation required) in prose. [card:a1b2c3]",
        )
        with self.assertRaisesRegex(ValueError, "marker inside answer prose"):
            report_audit.validate_draft(text, EVIDENCE)

    def test_rejects_space_between_terminal_tags(self):
        text = draft_text().replace(
            "R1.1 Answer for R1.1. (no citation required)",
            "R1.1 Answer for R1.1. [card:a1b2c3] [card:d4e5f6]",
        )
        with self.assertRaisesRegex(ValueError, "marker inside answer prose"):
            report_audit.validate_draft(text, EVIDENCE)

    def test_evidence_requires_runtime_card_tags(self):
        with self.assertRaisesRegex(ValueError, "contains no runtime card tags"):
            report_audit.validate_draft(draft_text(), "# Evidence\n")


if __name__ == "__main__":
    unittest.main()
