#!/usr/bin/env python3
"""Tests for deterministic runtime-tag citation handling."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "report_citations.py"
sys.path.insert(0, str(ROOT))
from scripts.core import card_tags  # noqa: E402

SPEC = importlib.util.spec_from_file_location("report_citations", SCRIPT)
report_citations = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report_citations)

EVIDENCE = """# Evidence

## Refs

a1b2c3,d4e5f6: primary ref 1
b1c2d3: primary ref 2; secondary ref 4
c1d2e3: primary ref 3

## References

1. Alpha A. First paper. Blood. 2020;1(1):1-2.
2. Beta B. Second paper. Leukemia. 2021;2(2):3-4.
3. Gamma C. Third paper. J Clin Oncol. 2022;3(3):5-6.
4. Delta D. Secondary paper. Nature. 2019;4(4):7-8.
"""

CARD_TAGS = json.dumps({
    "schema_version": "1.0",
    "algorithm": card_tags.ALGORITHM,
    "tags": [
        {"card_tag": "a1b2c3", "card_id": "paper-a-C0001"},
        {"card_tag": "d4e5f6", "card_id": "paper-a-C0002"},
        {"card_tag": "b1c2d3", "card_id": "paper-b-C0001"},
        {"card_tag": "c1d2e3", "card_id": "paper-c-C0001"},
    ],
})


class ValidateTests(unittest.TestCase):
    def test_accepts_tag_map_emitted_by_shared_producer(self):
        produced = card_tags.build_card_tags(["paper-a-C0001", "paper-b-C0001"])
        expected = {
            row["card_tag"]: row["card_id"]
            for row in produced["tags"]
        }
        self.assertEqual(
            report_citations.parse_card_tags(json.dumps(produced)),
            expected,
        )

    def test_rejects_legacy_algorithm_identifier(self):
        legacy = json.loads(CARD_TAGS)
        legacy["algorithm"] = "sha256-6hex-collision-resolved"
        with self.assertRaisesRegex(ValueError, "algorithm is unsupported"):
            report_citations.parse_card_tags(json.dumps(legacy))

    def test_accepts_known_markers_without_modifying_document(self):
        document = "First. [card:b1c2d3][card:a1b2c3]\nPatient fact. (no citation required)\n"
        self.assertEqual(report_citations.validate(document, EVIDENCE, CARD_TAGS), document)

    def test_unknown_marker_fails(self):
        with self.assertRaisesRegex(ValueError, "unknown runtime card tag"):
            report_citations.validate("Finding. [card:ffffff]\n", EVIDENCE, CARD_TAGS)

    def test_malformed_marker_fails(self):
        with self.assertRaisesRegex(ValueError, "malformed card marker"):
            report_citations.validate("Finding. [card:bad tag]\n", EVIDENCE, CARD_TAGS)

    def test_legacy_numeric_source_marker_fails(self):
        with self.assertRaisesRegex(ValueError, r"legacy '\(refs: \.\.\.\)' citation syntax"):
            report_citations.validate("Finding. (refs: 1)\n", EVIDENCE, CARD_TAGS)

    def test_model_generated_numeric_citation_fails(self):
        with self.assertRaisesRegex(ValueError, "model-generated numeric"):
            report_citations.validate("Finding. [1]\n", EVIDENCE, CARD_TAGS)

    def test_references_section_fails(self):
        with self.assertRaisesRegex(ValueError, "contains a model-written '## References' section"):
            report_citations.validate("Finding.\n\n## References\n\n1. Alpha.\n", EVIDENCE, CARD_TAGS)

    def test_incomplete_evidence_refs_mapping_fails(self):
        evidence = EVIDENCE.replace("c1d2e3: primary ref 3\n", "")
        with self.assertRaisesRegex(ValueError, r"omits reference\(s\): 3"):
            report_citations.validate("Patient fact.\n", evidence, CARD_TAGS)

    def test_duplicate_card_mapping_fails(self):
        evidence = EVIDENCE.replace("c1d2e3: primary ref 3", "a1b2c3: primary ref 3")
        with self.assertRaisesRegex(ValueError, "duplicate card mapping"):
            report_citations.validate("Patient fact.\n", evidence, CARD_TAGS)

    def test_multiple_primary_references_for_one_card_fail(self):
        evidence = EVIDENCE.replace("c1d2e3: primary ref 3", "c1d2e3: primary ref 2,3")
        with self.assertRaisesRegex(ValueError, "exactly one primary reference"):
            report_citations.validate("Patient fact.\n", evidence, CARD_TAGS)

    def test_step6b_accepts_citation_disposition_after_full_stop(self):
        document = (
            "Finding. [card:b1c2d3][card:a1b2c3]\n"
            "Patient fact. (no citation required)\n"
        )
        self.assertEqual(
            report_citations.validate(
                document,
                EVIDENCE,
                CARD_TAGS,
                require_citation_after_full_stop=True,
            ),
            document,
        )

    def test_step6b_rejects_uncited_sentence_ending_full_stop_with_actionable_message(self):
        with self.assertRaisesRegex(
            ValueError,
            r"full stop is followed immediately by exactly one space",
        ):
            report_citations.validate(
                "Uncited sentence.\n",
                EVIDENCE,
                CARD_TAGS,
                require_citation_after_full_stop=True,
            )

    def test_step6b_rejects_marker_before_full_stop_with_actionable_message(self):
        with self.assertRaisesRegex(ValueError, "move it after the full stop"):
            report_citations.validate(
                "Finding [card:a1b2c3].\n",
                EVIDENCE,
                CARD_TAGS,
                require_citation_after_full_stop=True,
            )

    def test_step6b_requires_one_space_before_disposition(self):
        with self.assertRaisesRegex(ValueError, "full stop is followed immediately by exactly one space"):
            report_citations.validate(
                "Finding.[card:a1b2c3]\n",
                EVIDENCE,
                CARD_TAGS,
                require_citation_after_full_stop=True,
            )

    def test_step6b_does_not_treat_variant_or_decimal_dots_as_full_stops(self):
        document = "Variant p.Arg882His at 1.5% VAF. [card:a1b2c3]\n"
        self.assertEqual(
            report_citations.validate(
                document,
                EVIDENCE,
                CARD_TAGS,
                require_citation_after_full_stop=True,
            ),
            document,
        )


class RenderTests(unittest.TestCase):
    def test_render_default_still_requires_disposition_after_every_sentence_full_stop(self):
        with self.assertRaisesRegex(ValueError, "required citation disposition"):
            report_citations.render(
                "First sentence. Second sentence. [card:a1b2c3]\n",
                EVIDENCE,
                CARD_TAGS,
            )

    def test_assigns_numbers_in_first_appearance_order_and_reuses_them(self):
        report = "Second then first. [card:b1c2d3][card:a1b2c3]\n\nSecond again. [card:b1c2d3]\n"
        result = report_citations.render(report, EVIDENCE, CARD_TAGS)
        self.assertIn("Second then first [1,2].", result)
        self.assertIn("Second again [1].", result)
        self.assertIn("1. Beta B. Second paper.", result)
        self.assertIn("2. Alpha A. First paper.", result)
        self.assertNotIn("Gamma C", result)

    def test_removes_no_citation_required_and_deduplicates_one_marker(self):
        report = "Patient fact. (no citation required)\nFinding. [card:c1d2e3][card:c1d2e3]\n"
        result = report_citations.render(report, EVIDENCE, CARD_TAGS)
        self.assertIn("Patient fact.", result)
        self.assertNotIn("no citation required", result)
        self.assertIn("Finding [1].", result)
        self.assertEqual(result.count("Gamma C. Third paper."), 1)

    def test_two_cards_from_one_publication_deduplicate(self):
        result = report_citations.render("Finding. [card:a1b2c3][card:d4e5f6]\n", EVIDENCE, CARD_TAGS)
        self.assertIn("Finding [1].", result)
        self.assertEqual(result.count("Alpha A. First paper."), 1)

    def test_card_marker_selects_primary_not_secondary_reference(self):
        result = report_citations.render("Finding. [card:b1c2d3]\n", EVIDENCE, CARD_TAGS)
        self.assertIn("1. Beta B. Second paper.", result)
        self.assertNotIn("Delta D. Secondary paper.", result)

    def test_render_moves_model_marker_before_full_stop_in_final_output(self):
        result = report_citations.render("Finding. [card:a1b2c3]\n", EVIDENCE, CARD_TAGS)
        self.assertIn("Finding [1].", result)
        self.assertNotIn("Finding. [1]", result)

    def test_render_moves_multiple_model_markers_before_full_stop_in_final_output(self):
        result = report_citations.render(
            "Finding. [card:b1c2d3] [card:a1b2c3]\n",
            EVIDENCE,
            CARD_TAGS,
        )
        self.assertIn("Finding [1,2].", result)
        self.assertNotIn("Finding. [1,2]", result)

    def test_render_removes_model_no_citation_disposition(self):
        result = report_citations.render(
            "Patient fact. (no citation required)\n",
            EVIDENCE,
            CARD_TAGS,
        )
        self.assertIn("Patient fact.", result)
        self.assertNotIn("no citation required", result)


class CommandTests(unittest.TestCase):
    def test_validate_success_does_not_overwrite_report(self):
        completed, report, original = self.run_command("validate", "Finding. [card:a1b2c3]\n")
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(report, original)

    def test_validate_failure_does_not_overwrite_report(self):
        completed, report, original = self.run_command("validate", "Bad citation. [card:ffffff]\n")
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(report, original)

    def test_render_failure_does_not_overwrite_report(self):
        completed, report, original = self.run_command("render", "Bad citation. [card:ffffff]\n")
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(report, original)

    def test_step6b_cli_flag_rejects_uncited_full_stop_without_overwrite(self):
        completed, report, original = self.run_command(
            "validate",
            "Uncited sentence.\n",
            strict_step6b=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("sentence-ending full stop", completed.stderr)
        self.assertEqual(report, original)

    def test_step6b_cli_flag_accepts_cited_full_stop(self):
        completed, report, original = self.run_command(
            "validate",
            "Finding. [card:a1b2c3]\n",
            strict_step6b=True,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(report, original)

    def test_step6b_cli_flag_rejects_marker_before_full_stop(self):
        completed, report, original = self.run_command(
            "validate",
            "Finding [card:a1b2c3].\n",
            strict_step6b=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("move it after the full stop", completed.stderr)
        self.assertEqual(report, original)

    def run_command(self, command, original, *, strict_step6b=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "report.md"
            evidence = root / "evidence.md"
            tags = root / "card-tags.json"
            report_path.write_text(original, encoding="utf-8")
            evidence.write_text(EVIDENCE, encoding="utf-8")
            tags.write_text(CARD_TAGS, encoding="utf-8")
            command_line = [
                sys.executable,
                str(SCRIPT),
                command,
                "--report",
                str(report_path),
                "--evidence",
                str(evidence),
                "--card-tags",
                str(tags),
            ]
            if strict_step6b:
                command_line.append("--require-citation-after-full-stop")
            completed = subprocess.run(
                command_line,
                capture_output=True,
                text=True,
            )
            report = report_path.read_text(encoding="utf-8")
        return completed, report, original


if __name__ == "__main__":
    unittest.main()
