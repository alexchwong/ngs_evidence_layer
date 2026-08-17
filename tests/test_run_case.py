#!/usr/bin/env python3
"""Tests for workflow-state-driven ``scripts/run_case.py``."""
import json
import subprocess
import sys
import tempfile
import unittest

from pathlib import Path

from scripts.setup_workflow import setup_workflow

ROOT = Path(__file__).resolve().parent.parent
RUN_CASE = ROOT / "scripts" / "run_case.py"
WORKFLOW_RUNTIME = ROOT / "scripts" / "workflow_runtime.py"


def run(*arguments, success=True, cwd=None):
    result = subprocess.run(
        [sys.executable, str(RUN_CASE), *map(str, arguments)],
        capture_output=True, text=True, cwd=cwd,
    )
    output = result.stdout + result.stderr
    if success and result.returncode != 0:
        raise AssertionError(f"unexpected failure:\n{output}")
    if not success and result.returncode == 0:
        raise AssertionError(f"expected failure but succeeded:\n{output}")
    return output


def write_case_input(path):
    path.write_text(json.dumps({
        "case_major_category": "myeloid neoplasm, unspecified",
        "provisional_disease": "myeloid neoplasm, unspecified",
        "genes": ["SF3B1"],
        "case_facts": [{"fact_id": "F1", "type": "variant", "gene": "SF3B1"}],
    }), encoding="utf-8")


def write_adjudication(path):
    disease = "myeloid neoplasm, unspecified"
    path.write_text(json.dumps({
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
    }), encoding="utf-8")


class RunCaseTests(unittest.TestCase):
    def test_missing_workflow_state_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            write_case_input(work / "case-input.json")
            output = run("diagnosis", "--work-dir", work, success=False)
            self.assertIn("workflow state is missing", output)

    def test_legacy_diagnosis_and_downstream_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            setup_workflow(workflow="legacy-v1", mode="ngs-report", work_dir=work)
            write_case_input(work / "case-input.json")
            output = run("diagnosis", "--work-dir", work)
            self.assertIn("step 2: retrieve diagnosis evidence", output)
            self.assertTrue((work / "diagnostic_evidence.md").is_file())
            write_adjudication(work / "adjudication.json")
            output = run("downstream", "--work-dir", work)
            self.assertIn("step 4: retrieve full evidence bundle", output)
            self.assertTrue((work / "evidence.md").is_file())
            self.assertTrue((work / "card-tags.json").is_file())

    def test_legacy_setup_and_retrieval_do_not_require_pyyaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work = base / "work"
            blocker = base / "blocker"
            blocker.mkdir()
            (blocker / "yaml.py").write_text(
                'raise ModuleNotFoundError("No module named \'yaml\'")\n',
                encoding="utf-8",
            )
            env = dict(__import__("os").environ)
            existing = env.get("PYTHONPATH")
            env["PYTHONPATH"] = str(blocker) + ((":" + existing) if existing else "")

            setup = subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts" / "setup_workflow.py"),
                    "--workflow", "legacy-v1", "--mode", "ngs-report",
                    "--work-dir", str(work),
                ],
                capture_output=True, text=True, env=env, cwd=ROOT,
            )
            self.assertEqual(setup.returncode, 0, setup.stdout + setup.stderr)
            write_case_input(work / "case-input.json")

            diagnosis = subprocess.run(
                [sys.executable, str(RUN_CASE), "diagnosis", "--work-dir", str(work)],
                capture_output=True, text=True, env=env, cwd=ROOT,
            )
            self.assertEqual(diagnosis.returncode, 0, diagnosis.stdout + diagnosis.stderr)
            write_adjudication(work / "adjudication.json")

            downstream = subprocess.run(
                [sys.executable, str(RUN_CASE), "downstream", "--work-dir", str(work)],
                capture_output=True, text=True, env=env, cwd=ROOT,
            )
            self.assertEqual(downstream.returncode, 0, downstream.stdout + downstream.stderr)

    def test_diagnosis_first_diagnosis_and_downstream_run(self):
        import yaml

        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            setup_workflow(workflow="diagnosis-first-v1", mode="ngs-report", work_dir=work)
            write_case_input(work / "case-input.json")
            output = run("diagnosis", "--work-dir", work)
            self.assertIn("diagnosis-first step 2", output)
            self.assertTrue((work / "diagnostic_evidence.md").is_file())
            self.assertTrue((work / "report-draft-dx.yaml").is_file())
            draft_path = work / "report-draft-dx.yaml"
            draft = yaml.safe_load(draft_path.read_text(encoding="utf-8"))
            draft["refined_cmc"] = "myeloid neoplasm, unspecified"
            draft_path.write_text(yaml.safe_dump(draft, sort_keys=False), encoding="utf-8")
            generated = subprocess.run(
                [sys.executable, str(WORKFLOW_RUNTIME), "remainder-rules", "--work-dir", str(work)],
                capture_output=True, text=True,
            )
            self.assertEqual(generated.returncode, 0, generated.stdout + generated.stderr)
            output = run("downstream", "--work-dir", work)
            self.assertIn("diagnosis-first step 4", output)
            self.assertTrue((work / "downstream_evidence.md").is_file())
            self.assertTrue((work / "evidence.md").is_file())
            self.assertTrue((work / "report-draft-remainder.yaml").is_file())

    def test_run_case_uses_same_cli_for_both_workflows(self):
        source = RUN_CASE.read_text(encoding="utf-8")
        self.assertIn('choices=("diagnosis", "downstream")', source)
        self.assertNotIn("prototype-diagnosis", source)
        self.assertNotIn("legacy-diagnosis", source)

    def test_shared_runtime_layers_do_not_name_registered_workflows(self):
        paths = [
            ROOT / "scripts" / "retrieve.py",
            ROOT / "scripts" / "render.py",
            ROOT / "scripts" / "run_case.py",
            ROOT / "scripts" / "package_run.py",
            ROOT / "scripts" / "report_audit.py",
            ROOT / "scripts" / "report_citations.py",
            ROOT / "scripts" / "workflow_runtime.py",
            ROOT / "scripts" / "workflow_registry.py",
            *sorted((ROOT / "scripts" / "core").glob("*.py")),
        ]
        forbidden = ("legacy-v1", "legacy_v1", "diagnosis-first-v1", "diagnosis_first_v1")
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, text, f"{path.relative_to(ROOT)} names workflow {token}")


if __name__ == "__main__":
    unittest.main()
