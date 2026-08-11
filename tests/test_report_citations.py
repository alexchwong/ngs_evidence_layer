#!/usr/bin/env python3
"""Tests for deterministic Step 6 report citation handling."""

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "report_citations.py"
SPEC = importlib.util.spec_from_file_location("report_citations", SCRIPT)
report_citations = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report_citations)


BLOCK = """# Evidence block

## Refs

paper-a-C0001,paper-a-C0002: primary ref 1
paper-b-C0001: primary ref 2; secondary ref 4
paper-c-C0001: primary ref 3

## References

1. Alpha A. First paper. Blood. 2020;1(1):1-2.
2. Beta B. Second paper. Leukemia. 2021;2(2):3-4.
3. Gamma C. Third paper. J Clin Oncol. 2022;3(3):5-6.
4. Delta D. Secondary paper. Nature. 2019;4(4):7-8.
"""


class ValidateTests(unittest.TestCase):
    def test_accepts_known_markers_without_modifying_document(self):
        document = (
            "First. [card:paper-b-C0001][card:paper-a-C0001]\n"
            "Patient fact. (no citation required)\n"
        )
        self.assertEqual(report_citations.validate(document, BLOCK), document)

    def test_unknown_marker_fails(self):
        with self.assertRaisesRegex(ValueError, "unknown block card"):
            report_citations.validate("Finding. [card:unknown-C0001]\n", BLOCK)

    def test_malformed_marker_fails(self):
        with self.assertRaisesRegex(ValueError, "malformed card-ID"):
            report_citations.validate("Finding. [card:bad card]\n", BLOCK)

    def test_legacy_numeric_source_marker_fails(self):
        with self.assertRaisesRegex(ValueError, "legacy numeric"):
            report_citations.validate("Finding. (refs: 1)\n", BLOCK)

    def test_model_generated_numeric_citation_fails(self):
        with self.assertRaisesRegex(ValueError, "model-generated numeric"):
            report_citations.validate("Finding. [1]\n", BLOCK)

    def test_references_section_fails(self):
        with self.assertRaisesRegex(ValueError, "already contains"):
            report_citations.validate(
                "Finding.\n\n## References\n\n1. Alpha.\n", BLOCK
            )

    def test_incomplete_block_refs_mapping_fails(self):
        block = BLOCK.replace("paper-c-C0001: primary ref 3\n", "")
        with self.assertRaisesRegex(ValueError, r"omits reference\(s\): 3"):
            report_citations.validate("Patient fact.\n", block)

    def test_duplicate_card_mapping_fails(self):
        block = BLOCK.replace(
            "paper-c-C0001: primary ref 3",
            "paper-a-C0001: primary ref 3",
        )
        with self.assertRaisesRegex(ValueError, "duplicate card mapping"):
            report_citations.validate("Patient fact.\n", block)

    def test_multiple_primary_references_for_one_card_fail(self):
        block = BLOCK.replace(
            "paper-c-C0001: primary ref 3",
            "paper-c-C0001: primary ref 2,3",
        )
        with self.assertRaisesRegex(ValueError, "exactly one primary reference"):
            report_citations.validate("Patient fact.\n", block)


class RenderTests(unittest.TestCase):
    def test_assigns_numbers_in_first_appearance_order_and_reuses_them(self):
        report = (
            "Second then first. [card:paper-b-C0001][card:paper-a-C0001]\n\n"
            "Second again. [card:paper-b-C0001]\n"
        )
        result = report_citations.render(report, BLOCK)

        self.assertIn("Second then first. [1,2]", result)
        self.assertIn("Second again. [1]", result)
        self.assertIn("1. Beta B. Second paper.", result)
        self.assertIn("2. Alpha A. First paper.", result)
        self.assertNotIn("Gamma C", result)

    def test_removes_no_citation_required_and_deduplicates_one_marker(self):
        report = (
            "Patient fact. (no citation required)\n"
            "Finding. [card:paper-c-C0001][card:paper-c-C0001]\n"
        )
        result = report_citations.render(report, BLOCK)

        self.assertIn("Patient fact.", result)
        self.assertNotIn("no citation required", result)
        self.assertIn("Finding. [1]", result)
        self.assertEqual(result.count("Gamma C. Third paper."), 1)

    def test_two_cards_from_one_publication_deduplicate(self):
        result = report_citations.render(
            "Finding. [card:paper-a-C0001][card:paper-a-C0002]\n",
            BLOCK,
        )
        self.assertIn("Finding. [1]", result)
        self.assertEqual(result.count("Alpha A. First paper."), 1)

    def test_card_marker_selects_primary_not_secondary_reference(self):
        result = report_citations.render(
            "Finding. [card:paper-b-C0001]\n", BLOCK
        )
        self.assertIn("1. Beta B. Second paper.", result)
        self.assertNotIn("Delta D. Secondary paper.", result)


class CommandTests(unittest.TestCase):
    def test_validate_success_does_not_overwrite_report(self):
        completed, report, original = self.run_command(
            "validate", "Finding. [card:paper-a-C0001]\n"
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(report, original)

    def test_validate_failure_does_not_overwrite_report(self):
        completed, report, original = self.run_command(
            "validate", "Bad citation. [card:unknown-C9999]\n"
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(report, original)

    def test_render_failure_does_not_overwrite_report(self):
        completed, report, original = self.run_command(
            "render", "Bad citation. [card:unknown-C9999]\n"
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(report, original)

    def run_command(self, command, original):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "report.md"
            block = root / "block.md"
            report_path.write_text(original, encoding="utf-8")
            block.write_text(BLOCK, encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    command,
                    "--report",
                    str(report_path),
                    "--block",
                    str(block),
                ],
                capture_output=True,
                text=True,
            )
            report = report_path.read_text(encoding="utf-8")
        return completed, report, original


if __name__ == "__main__":
    unittest.main()
