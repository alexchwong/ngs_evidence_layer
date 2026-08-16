#!/usr/bin/env python3
"""CLI smoke tests for workflow-dispatched ``scripts/retrieve.py``."""

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
    def test_top_level_help_exposes_only_workflow_neutral_stages(self):
        result = run("--help")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("diagnosis", result.stdout)
        self.assertIn("downstream", result.stdout)
        self.assertNotIn("prototype", result.stdout)

    def test_stage_requires_work_dir(self):
        result = run("diagnosis")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--work-dir", result.stderr)

    def test_missing_workflow_state_fails_informatively(self):
        result = run("diagnosis", "--work-dir", ROOT)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("workflow state is missing", result.stderr)


if __name__ == "__main__":
    unittest.main()
