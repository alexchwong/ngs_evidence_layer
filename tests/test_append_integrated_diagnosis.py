#!/usr/bin/env python3
"""Tests for deterministic Step 3C integrated-diagnosis rendering."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "append_integrated_diagnosis.py"


class AppendIntegratedDiagnosisTests(unittest.TestCase):
    def test_automatic_append_uses_model_label_without_model_generated_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = root / "case.md"
            step2 = root / "step2.json"
            adj = root / "adjudication.json"
            case.write_text("Case text.\n", encoding="utf-8")
            step2.write_text(json.dumps({
                "case_major_category": "MDS",
                "provisional_disease": "MDS",
                "genes": [],
                "case_facts": [],
                "diagnosis_cards": [],
                "allowed_refined_diseases": ["MDS"],
            }), encoding="utf-8")
            adj.write_text(json.dumps({
                "status": "indeterminate",
                "provisional_disease": "MDS",
                "refined_disease": "MDS",
                "downstream_filter_disease": "MDS",
                "diagnostic_label": "MDS, NOS",
                "driven_by": [],
                "criterion_assessment": [],
                "reason": "No reclassification criterion was established.",
                "user_review": "automatic",
            }), encoding="utf-8")
            completed = subprocess.run([
                sys.executable, str(SCRIPT),
                "--case", str(case),
                "--diagnosis-result", str(step2),
                "--adjudication-result", str(adj),
            ], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(case.read_text(encoding="utf-8").endswith("Integrated diagnosis: MDS, NOS.\n"))


if __name__ == "__main__":
    unittest.main()
