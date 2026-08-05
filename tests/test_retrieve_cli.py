#!/usr/bin/env python3
"""Corpus-independent CLI smoke tests for ``scripts/retrieve.py``."""

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RETRIEVE = ROOT / "scripts" / "retrieve.py"


def run(*arguments):
    return subprocess.run(
        [sys.executable, str(RETRIEVE), *map(str, arguments)],
        capture_output=True,
        text=True,
        check=False,
    )


class RetrieveCliTests(unittest.TestCase):
    def test_top_level_help(self):
        result = run("--help")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("diagnosis", result.stdout)
        self.assertIn("full", result.stdout)

    def test_diagnosis_help(self):
        result = run("diagnosis", "--help")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("--case-input", result.stdout)
        self.assertIn("--output", result.stdout)

    def test_full_help(self):
        result = run("full", "--help")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("--diagnosis-result", result.stdout)
        self.assertIn("--adjudication-result", result.stdout)
        self.assertIn("--output", result.stdout)


if __name__ == "__main__":
    unittest.main()
