#!/usr/bin/env python3
"""Tests for deterministic Step 3C integrated-diagnosis rendering."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "workflows" / "legacy_v1" / "append_integrated_diagnosis.py"
sys.path.insert(0, str(ROOT))
from scripts.core import retrieval as retrieval_core  # noqa: E402


class AppendIntegratedDiagnosisTests(unittest.TestCase):
    def test_automatic_append_uses_model_label_without_model_generated_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = root / "case.md"
            step2 = root / "diagnostic_evidence.md"
            adj = root / "adjudication.json"
            case.write_text("Case text.\n", encoding="utf-8")
            step2_result = {
                "step": 2,
                "case_major_category": "MDS",
                "provisional_disease": "MDS",
                "genes": [],
                "case_facts": [],
                "diagnosis_cards": [],
                "allowed_refined_diseases": ["MDS"],
                "genes_with_no_diagnosis_card": [],
                "corpus": {"path": "corpus.json", "index": "index.json"},
            }
            step2.write_text(retrieval_core.render_step_markdown(step2_result), encoding="utf-8")
            retrieval_core.write_step_json(step2_result, step2.with_suffix(".json"))
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
