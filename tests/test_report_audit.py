#!/usr/bin/env python3
"""Tests for strict Markdown Step 6A reporting-analysis validation."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from workflows.legacy_v1 import audit_policy as report_audit  # noqa: E402


def draft_text():
    return "\n".join(
        f"{rule_id} REPORT: Answer for {rule_id}. (no citation required)"
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
            "R1.1 REPORT: Answer for R1.1. (no citation required)",
            "R1.1 REPORT: Answer for R1.1. [card:a1b2c3]",
        )
        result = report_audit.validate_draft(text, EVIDENCE)
        self.assertEqual(result[0]["rule_id"], "R1.1")
        self.assertEqual(result[0]["card_tags"], ["a1b2c3"])
        self.assertEqual(result[0]["citation_status"], "cited")
        self.assertEqual(result[1]["citation_status"], "no_citation_required")

    def test_requires_report_or_omit_classification(self):
        text = draft_text().replace(
            "R1.1 REPORT: Answer for R1.1. (no citation required)",
            "R1.1 Answer for R1.1. (no citation required)",
        )
        with self.assertRaisesRegex(ValueError, "must classify the rule immediately"):
            report_audit.validate_draft(text, EVIDENCE)

    def test_accepts_omit_classification(self):
        text = draft_text().replace(
            "R1.1 REPORT: Answer for R1.1. (no citation required)",
            "R1.1 OMIT: Germline commentary. (no citation required)",
        )
        result = report_audit.validate_draft(text, EVIDENCE)
        self.assertEqual(result[0]["classification"], "OMIT")
        self.assertEqual(result[0]["text"], "Germline commentary.")

    def test_parses_report_classification(self):
        result = report_audit.validate_draft(draft_text(), EVIDENCE)
        self.assertEqual(result[0]["classification"], "REPORT")

    def test_r0_1_allows_mandatory_no_pathogenic_variants_sentence(self):
        classification, text, tags = report_audit.split_draft_line(
            "R0.1 REPORT: No pathogenic variants were detected on NGS. (no citation required)",
            expected_rule_id="R0.1",
            line_number=1,
        )
        self.assertEqual(classification, "REPORT")
        self.assertEqual(text, "No pathogenic variants were detected on NGS.")
        self.assertEqual(tags, [])

    def test_rejects_report_sentence_beginning_no(self):
        text = draft_text().replace(
            "R1.1 REPORT: Answer for R1.1. (no citation required)",
            "R1.1 REPORT: No reportable implication is present. (no citation required)",
        )
        with self.assertRaisesRegex(ValueError, "sentence beginning 'No'"):
            report_audit.validate_draft(text, EVIDENCE)

    def test_rejects_later_report_sentence_beginning_not_applicable(self):
        text = draft_text().replace(
            "R1.1 REPORT: Answer for R1.1. (no citation required)",
            "R1.1 REPORT: The assay result is available. Not applicable to this case. (no citation required)",
        )
        with self.assertRaisesRegex(ValueError, "sentence beginning 'Not applicable'"):
            report_audit.validate_draft(text, EVIDENCE)

    def test_rejects_report_meta_instruction_with_actionable_message(self):
        text = draft_text().replace(
            "R1.1 REPORT: Answer for R1.1. (no citation required)",
            "R1.1 REPORT: The final report should state AML with mutated NPM1. (no citation required)",
        )
        with self.assertRaisesRegex(ValueError, "classified REPORT but contains report-construction meta-language"):
            report_audit.validate_draft(text, EVIDENCE)

    def test_rejects_report_omit_instruction(self):
        text = draft_text().replace(
            "R1.1 REPORT: Answer for R1.1. (no citation required)",
            "R1.1 REPORT: Omit germline commentary. (no citation required)",
        )
        with self.assertRaisesRegex(ValueError, "rewrite it as 'R1.1 OMIT:"):
            report_audit.validate_draft(text, EVIDENCE)

    def test_allows_clinically_meaningful_negative_report(self):
        text = draft_text().replace(
            "R1.1 REPORT: Answer for R1.1. (no citation required)",
            "R1.1 REPORT: FLT3-ITD was not detected and the case remains favourable risk. (no citation required)",
        )
        result = report_audit.validate_draft(text, EVIDENCE)
        self.assertEqual(result[0]["classification"], "REPORT")

    def test_requires_every_rule_in_order(self):
        text = draft_text().replace(
            "R1.2 REPORT: Answer for R1.2.", "R1.3 REPORT: Answer for R1.2.", 1
        )
        with self.assertRaisesRegex(ValueError, r"missing rule line\(s\): R1.2"):
            report_audit.validate_draft(text, EVIDENCE)

    def test_rejects_missing_rule(self):
        lines = draft_text().splitlines()
        text = "\n".join(lines[:-1]) + "\n"
        with self.assertRaisesRegex(ValueError, r"missing rule line\(s\): R5.9"):
            report_audit.validate_draft(text, EVIDENCE)

    def test_rejects_blank_line_or_extra_markdown(self):
        text = draft_text().replace("\nR1.2", "\n\nR1.2", 1)
        with self.assertRaisesRegex(ValueError, r"line\(s\) without a valid rule ID: line 2"):
            report_audit.validate_draft(text, EVIDENCE)


    def test_rejects_nonexistent_rule_with_line_number(self):
        lines = draft_text().splitlines()
        lines[1] = lines[1].replace("R1.2", "R9.9", 1)
        with self.assertRaisesRegex(ValueError, r"non-existent rule ID\(s\): line 2=R9.9"):
            report_audit.validate_draft("\n".join(lines) + "\n", EVIDENCE)

    def test_requires_explicit_terminal_citation_disposition(self):
        text = draft_text().replace(
            "R1.1 REPORT: Answer for R1.1. (no citation required)",
            "R1.1 REPORT: Answer for R1.1.",
        )
        with self.assertRaisesRegex(ValueError, r"Expected exactly: '<conclusion>\. \[card:a1b2c3\]'"):
            report_audit.validate_draft(text, EVIDENCE)

    def test_rejects_marker_before_full_stop_with_actionable_message(self):
        text = draft_text().replace(
            "R1.1 REPORT: Answer for R1.1. (no citation required)",
            "R1.1 REPORT: Answer for R1.1 [card:a1b2c3].",
        )
        with self.assertRaisesRegex(ValueError, "citation disposition must follow the full stop"):
            report_audit.validate_draft(text, EVIDENCE)

    def test_requires_full_stop_before_no_citation_disposition(self):
        text = draft_text().replace(
            "R1.1 REPORT: Answer for R1.1. (no citation required)",
            "R1.1 REPORT: Answer for R1.1 (no citation required)",
        )
        with self.assertRaisesRegex(ValueError, "full stop must come before the citation disposition"):
            report_audit.validate_draft(text, EVIDENCE)

    def test_accepts_multiple_adjacent_terminal_tags(self):
        text = draft_text().replace(
            "R1.1 REPORT: Answer for R1.1. (no citation required)",
            "R1.1 REPORT: Answer for R1.1. [card:a1b2c3][card:d4e5f6]",
        )
        result = report_audit.validate_draft(text, EVIDENCE)
        self.assertEqual(result[0]["card_tags"], ["a1b2c3", "d4e5f6"])

    def test_rejects_unknown_tag_with_rule_id(self):
        text = draft_text().replace(
            "R1.1 REPORT: Answer for R1.1. (no citation required)",
            "R1.1 REPORT: Answer for R1.1. [card:ffffff]",
        )
        with self.assertRaisesRegex(
            ValueError,
            r"unknown evidence card tag\(s\): ffffff \(R1.1\)",
        ):
            report_audit.validate_draft(text, EVIDENCE)

    def test_rejects_duplicate_tags(self):
        text = draft_text().replace(
            "R1.1 REPORT: Answer for R1.1. (no citation required)",
            "R1.1 REPORT: Answer for R1.1. [card:a1b2c3][card:a1b2c3]",
        )
        with self.assertRaisesRegex(ValueError, "R1.1 terminal card tags must not contain duplicates"):
            report_audit.validate_draft(text, EVIDENCE)

    def test_rejects_inline_card_marker(self):
        text = draft_text().replace(
            "R1.1 REPORT: Answer for R1.1. (no citation required)",
            "R1.1 REPORT: Answer [card:a1b2c3] for R1.1. [card:d4e5f6]",
        )
        with self.assertRaisesRegex(ValueError, "marker inside answer prose"):
            report_audit.validate_draft(text, EVIDENCE)


    def test_inline_citation_error_instructs_terminal_union_repair(self):
        text = draft_text().replace(
            "R1.1 REPORT: Answer for R1.1. (no citation required)",
            "R1.1 REPORT: First claim. [card:a1b2c3] Second claim. [card:d4e5f6]",
        )
        with self.assertRaises(ValueError) as ctx:
            report_audit.validate_draft(text, EVIDENCE)
        message = str(ctx.exception)
        self.assertIn("remove every internal [card:...]", message)
        self.assertIn("union of every directly supporting card tag", message)
        self.assertIn("exactly one citation disposition after the final full stop", message)

    def test_rejects_no_citation_marker_inside_prose(self):
        text = draft_text().replace(
            "R1.1 REPORT: Answer for R1.1. (no citation required)",
            "R1.1 REPORT: Say (no citation required) in prose. [card:a1b2c3]",
        )
        with self.assertRaisesRegex(ValueError, "marker inside answer prose"):
            report_audit.validate_draft(text, EVIDENCE)

    def test_rejects_space_between_terminal_tags(self):
        text = draft_text().replace(
            "R1.1 REPORT: Answer for R1.1. (no citation required)",
            "R1.1 REPORT: Answer for R1.1. [card:a1b2c3] [card:d4e5f6]",
        )
        with self.assertRaisesRegex(ValueError, "Expected exactly"):
            report_audit.validate_draft(text, EVIDENCE)

    def test_evidence_requires_runtime_card_tags(self):
        with self.assertRaisesRegex(ValueError, "contains no runtime card tags"):
            report_audit.validate_draft(draft_text(), "# Evidence\n")

    def test_prototype_may_allow_empty_evidence_when_draft_cites_no_cards(self):
        rules = "# R2 — Prognosis\n\n1. **Question?**\n"
        draft = "R2.1 OMIT: No reportable implication. (no citation required)\n"
        parsed = report_audit.validate_draft(
            draft,
            "# Evidence\n",
            rules,
            allow_no_evidence_tags=True,
        )
        self.assertEqual(parsed[0]["card_tags"], [])


if __name__ == "__main__":
    unittest.main()
