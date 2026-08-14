#!/usr/bin/env python3
"""Tests for the deterministic `scripts/run_case.py` wrapper."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN_CASE = ROOT / "scripts" / "run_case.py"
CORPUS = ROOT / "output" / "corpus" / "nel.corpus.json"
INDEX = ROOT / "output" / "corpus" / "nel.index.json"


def run(*arguments, success=True, cwd=None):
    result = subprocess.run(
        [sys.executable, str(RUN_CASE), *map(str, arguments)],
        capture_output=True, text=True, cwd=cwd,
    )
    output = result.stdout + result.stderr
    if success:
        if result.returncode != 0:
            raise AssertionError(f"unexpected failure:\n{output}")
    else:
        if result.returncode == 0:
            raise AssertionError(f"expected failure but succeeded:\n{output}")
    return output, result.returncode


def write_case_input(path, disease="myeloid neoplasm, unspecified", genes=None, facts=None, category="myeloid neoplasm, unspecified"):
    document = {
        "case_major_category": category,
        "provisional_disease": disease,
        "genes": genes or ["SF3B1"],
        "case_facts": facts or [{"fact_id": "F1", "type": "variant", "gene": "SF3B1"}],
    }
    path.write_text(json.dumps(document), encoding="utf-8")


def write_adjudication(path, disease="myeloid neoplasm, unspecified"):
    document = {
        "status": "indeterminate",
        "provisional_disease": disease,
        "refined_disease": disease,
        "downstream_filter_disease": disease,
        "diagnostic_label": None,
        "driven_by": [],
        "criterion_assessment": [],
        "reason": "Fixture adjudication.",
        "user_review": {
            "decision": "agree",
            "diagnostic_label": None,
            "refined_disease": disease,
            "reason": "Fixture adjudication.",
            "card_ids": [],
        },
    }
    path.write_text(json.dumps(document), encoding="utf-8")


class RunCaseDiagnosisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.work = self.dir / "work"
        self.work.mkdir()
        write_case_input(self.work / "case-input.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_work_directory_filenames(self):
        output, _ = run("diagnosis", "--work-dir", self.work)
        self.assertTrue((self.work / "diagnostic_evidence.md").is_file())
        self.assertTrue((self.work / "diagnostic_evidence.json").is_file())
        self.assertNotIn("diagnostic_evidence.json", output)
        self.assertNotIn(str((self.work / "diagnostic_evidence.json").resolve()), output)

    def test_secure_temp_directory_created_when_omitted(self):
        output, _ = run("diagnosis", "--case-input", self.work / "case-input.json")
        self.assertIn("[run_case] working directory:", output)
        self.assertIn("ngs_evidence_layer_", output)
        self.assertIn("step 2: retrieve diagnosis evidence", output)

    def test_absolute_working_directory_status_output(self):
        output, _ = run("diagnosis", "--work-dir", self.work)
        self.assertIn(f"[run_case] working directory: {self.work.resolve()}", output)

    def test_forwarding_advanced_overrides(self):
        output, _ = run(
            "diagnosis", "--work-dir", self.work,
            "--genes", "NPM1",
            "--provisional-disease", "MDS",
            "--case-major-category", "MDS",
            "--corpus", CORPUS, "--index", INDEX,
        )
        self.assertIn("overriding case-input genes from --genes", output)
        self.assertIn("overriding case-input provisional-disease from --provisional-disease", output)
        self.assertIn("overriding case-input case-major-category from --case-major-category", output)
        text = (self.work / "diagnostic_evidence.md").read_text(encoding="utf-8")
        self.assertIn("- Genes: NPM1", text)
        self.assertIn("- Provisional disease: MDS", text)
        self.assertIn("- Case major category: MDS", text)
        self.assertIn("## Diagnosis cards", text)
        self.assertNotIn("  - Genes:", text)
        step2_json = json.loads((self.work / "diagnostic_evidence.json").read_text(encoding="utf-8"))
        self.assertTrue(all("genes" in card for card in step2_json["diagnosis_cards"]))
        self.assertNotIn("diagnostic_evidence.json", output)

    def test_non_zero_child_exit_propagation(self):
        (self.work / "case-input.json").write_text("{ not json", encoding="utf-8")
        output, _ = run("diagnosis", "--work-dir", self.work, success=False)
        self.assertIn("step 2: retrieve diagnosis evidence failed", output)

    def test_missing_output_detection(self):
        output, _ = run(
            "diagnosis", "--work-dir", self.work,
            "--case-input", self.dir / "missing.json",
            success=False,
        )
        self.assertIn("failed", output)

    def test_operation_from_non_repository_cwd(self):
        run("diagnosis", "--work-dir", self.work, cwd=self.tmp.name)
        self.assertTrue((self.work / "diagnostic_evidence.md").is_file())


class RunCaseFullTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.work = self.dir / "work"
        self.work.mkdir()
        write_case_input(self.work / "case-input.json")
        write_adjudication(self.work / "adjudication.json")
        run("diagnosis", "--work-dir", self.work)

    def tearDown(self):
        self.tmp.cleanup()

    def test_retrieve_full_then_render_execution_order(self):
        output, _ = run("full", "--work-dir", self.work)
        self.assertLess(
            output.index("step 4: retrieve full evidence bundle"),
            output.index("step 5: render evidence"),
        )
        self.assertTrue((self.work / "bundle.json").is_file())
        self.assertTrue((self.work / "evidence.md").is_file())
        self.assertTrue((self.work / "card-tags.json").is_file())

    def test_render_not_called_when_retrieval_fails(self):
        (self.work / "adjudication.json").write_text("{}", encoding="utf-8")
        output, _ = run("full", "--work-dir", self.work, success=False)
        self.assertIn("step 4: retrieve full evidence bundle failed", output)
        self.assertNotIn("step 5: render evidence", output)
        self.assertFalse((self.work / "evidence.md").exists())
        self.assertFalse((self.work / "evidence.md").exists())

    def test_default_input_and_output_paths(self):
        run("full", "--work-dir", self.work)
        self.assertTrue((self.work / "bundle.json").is_file())
        self.assertTrue((self.work / "evidence.md").is_file())
        self.assertTrue((self.work / "card-tags.json").is_file())

    def test_advanced_path_forwarding(self):
        alt = self.dir / "alt"
        alt.mkdir()
        run(
            "full", "--work-dir", self.work,
            "--diagnosis-result", self.work / "diagnostic_evidence.md",
            "--adjudication-result", self.work / "adjudication.json",
            "--bundle-output", alt / "bundle.json",
            "--output", alt / "evidence.md",
            "--card-tag-output", alt / "card-tags.json",
        )
        self.assertTrue((alt / "bundle.json").is_file())
        self.assertTrue((alt / "evidence.md").is_file())
        self.assertTrue((alt / "card-tags.json").is_file())

    def test_token_budget_forwarding(self):
        output, _ = run("full", "--work-dir", self.work, "--token-budget", "1000000")
        self.assertIn("against a budget of 1000000", output)

    def test_non_zero_render_exit_propagation(self):
        output, _ = run(
            "full", "--work-dir", self.work,
            "--token-budget", "not-an-int",
            success=False,
        )
        self.assertIn("invalid int value", output)

    def test_missing_bundle_detection(self):
        output, _ = run(
            "full", "--work-dir", self.work,
            "--diagnosis-result", self.dir / "missing-diagnostic-evidence.md",
            success=False,
        )
        self.assertIn("failed", output)

    def test_stale_block_not_delivered_after_failure(self):
        stale = self.work / "evidence.md"
        stale_tags = self.work / "card-tags.json"
        stale.write_text("stale", encoding="utf-8")
        stale_tags.write_text("stale", encoding="utf-8")
        (self.work / "adjudication.json").write_text("{}", encoding="utf-8")
        run("full", "--work-dir", self.work, success=False)
        self.assertFalse(stale.exists())
        self.assertFalse(stale_tags.exists())

    def test_output_status_names_only_model_readable_evidence_path(self):
        output, _ = run("full", "--work-dir", self.work)
        self.assertIn(
            f"[run_case] output: {(self.work / 'evidence.md').resolve()}",
            output,
        )
        self.assertNotIn(str((self.work / "card-tags.json").resolve()), output)
        self.assertNotIn("card-tags.json", output)


if __name__ == "__main__":
    unittest.main()