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

C1: primary ref 1
C2: primary ref 2
C3: primary ref 3

## References

1. Alpha A. First paper. Blood. 2020;1(1):1-2.
2. Beta B. Second paper. Leukemia. 2021;2(2):3-4.
3. Gamma C. Third paper. J Clin Oncol. 2022;3(3):5-6.
"""


class PrepareTests(unittest.TestCase):
    def test_assigns_numbers_in_first_appearance_order_and_reuses_them(self):
        draft = (
            "R1: Second then first. (refs: 2, 1)\n\n"
            "R2: Second again. (refs: 2)\n"
        )
        result = report_citations.prepare(draft, BLOCK)

        self.assertIn("Second then first. [1,2]", result)
        self.assertIn("Second again. [1]", result)
        self.assertIn("1. Beta B. Second paper.", result)
        self.assertIn("2. Alpha A. First paper.", result)
        self.assertNotIn("Gamma C", result)

    def test_removes_no_citation_required_and_deduplicates_one_marker(self):
        draft = "R1: Patient fact. (no citation required)\nR2: Finding. (refs: 3,3)\n"
        result = report_citations.prepare(draft, BLOCK)

        self.assertIn("R1: Patient fact.", result)
        self.assertNotIn("no citation required", result)
        self.assertIn("R2: Finding. [1]", result)
        self.assertEqual(result.count("Gamma C. Third paper."), 1)

    def test_unknown_reference_fails(self):
        with self.assertRaisesRegex(ValueError, "unknown block reference"):
            report_citations.prepare("R1: Finding. (refs: 4)\n", BLOCK)

    def test_malformed_marker_fails(self):
        with self.assertRaisesRegex(ValueError, "malformed"):
            report_citations.prepare("R1: Finding. (refs: 1; 2)\n", BLOCK)

    def test_already_prepared_draft_fails(self):
        prepared = report_citations.prepare("R1: Finding. (refs: 1)\n", BLOCK)
        with self.assertRaisesRegex(ValueError, "already contains"):
            report_citations.prepare(prepared, BLOCK)


class FinalizeTests(unittest.TestCase):
    def test_removes_unused_and_renumbers_retained_references(self):
        report = """Finding from the third source [3]. Another finding [1,3].

## References

1. Alpha A. First paper. Blood. 2020;1(1):1-2.
2. Beta B. Second paper. Leukemia. 2021;2(2):3-4.
3. Gamma C. Third paper. J Clin Oncol. 2022;3(3):5-6.
"""
        result = report_citations.finalize(report)

        self.assertIn("third source [1]", result)
        self.assertIn("Another finding [2,1]", result)
        self.assertIn("1. Gamma C. Third paper.", result)
        self.assertIn("2. Alpha A. First paper.", result)
        self.assertNotIn("Beta B", result)

    def test_unknown_report_reference_fails(self):
        report = "Finding [2].\n\n## References\n\n1. Alpha A. First paper.\n"
        with self.assertRaisesRegex(ValueError, "unknown supplied reference"):
            report_citations.finalize(report)

    def test_repeated_finalization_is_byte_identical(self):
        report = "Finding [1].\n\n## References\n\n1. Alpha A. First paper.\n"
        first = report_citations.finalize(report)
        self.assertEqual(report_citations.finalize(first), first)


class CommandTests(unittest.TestCase):
    def test_prepare_failure_does_not_overwrite_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            draft = root / "report-draft.md"
            block = root / "block.md"
            original = "R1: Bad citation. (refs: 99)\n"
            draft.write_text(original, encoding="utf-8")
            block.write_text(BLOCK, encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "prepare",
                    "--draft",
                    str(draft),
                    "--block",
                    str(block),
                ],
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(draft.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()