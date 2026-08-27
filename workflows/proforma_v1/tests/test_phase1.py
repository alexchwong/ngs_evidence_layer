from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from scripts.setup_workflow import setup_workflow
from scripts.workflow_registry import load_registry, load_workflow_metadata, normalise_selector, read_workflow_state
from workflows.proforma_v1 import replay
from workflows.proforma_v1.trace import TraceRecorder


class Phase1CloneTests(unittest.TestCase):
    def test_proforma_is_registered_and_independently_selectable(self):
        registry = load_registry()
        self.assertEqual(normalise_selector("proforma-v1", registry), "proforma-v1")
        self.assertEqual(normalise_selector("proforma", registry), "proforma-v1")
        self.assertEqual(normalise_selector("proforma_v1", registry), "proforma-v1")
        metadata = load_workflow_metadata("proforma-v1", registry)
        self.assertEqual(metadata["python_package"], "workflows.proforma_v1")
        self.assertEqual(metadata["cloned_from"], "terraced-v6")
        self.assertEqual(metadata["phase"], 1)

    def test_setup_binds_work_directory_to_proforma(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "run"
            resolved, _case, _expected = setup_workflow(
                workflow="proforma-v1",
                mode="nel-validate-brief",
                work_dir=work,
                case_id="7",
            )
            self.assertEqual(resolved, work.resolve())
            state = read_workflow_state(work)
            self.assertEqual(state["workflow_id"], "proforma-v1")
            self.assertEqual(state["mode"], "nel-validate-brief")

    def test_clinical_clone_files_match_reference_after_identity_substitution(self):
        root = Path(__file__).resolve().parents[3]
        reference = root / "workflows" / "terraced_v6"
        clone = root / "workflows" / "proforma_v1"
        excluded = {
            "README.md",
            "workflow.json",
            "replay.py",
            "trace.py",
        }
        reference_files = {
            p.relative_to(reference)
            for p in reference.rglob("*")
            if p.is_file()
            and "__pycache__" not in p.parts
            and p.relative_to(reference).parts[0] != "runs"
            and not (p.relative_to(reference).parts[0] == "tests" and p.suffix == ".py")
            and p.name not in excluded
        }
        for rel in sorted(reference_files):
            with self.subTest(file=str(rel)):
                source = (reference / rel).read_text(encoding="utf-8")
                expected = (
                    source.replace("workflows.terraced_v6", "workflows.proforma_v1")
                    .replace("workflows/terraced_v6", "workflows/proforma_v1")
                    .replace("terraced_v6", "proforma_v1")
                    .replace("terraced-v6", "proforma-v1")
                    .replace("Terraced-v6", "Proforma-v1")
                )
                if rel.as_posix() == "stage_checks.py":
                    expected = re.sub(
                        r"`[^`]+ workflows/proforma_v1/tests/` walks",
                        "`python -m unittest discover -s workflows/proforma_v1/tests` walks",
                        expected,
                        count=1,
                    )
                self.assertEqual((clone / rel).read_text(encoding="utf-8"), expected)


class Phase1ReplayTests(unittest.TestCase):
    def test_fixture_set_is_representative_and_frozen(self):
        cases = replay.load_cases()
        self.assertGreaterEqual(len(cases), 18)
        stages = {case.stage for case in cases}
        self.assertTrue({
            "structure_case", "diagnosis_who5", "diagnosis_icc", "prognosis",
            "treatment", "biomarker", "germline", "evidence_match",
            "evidence_audit", "report_write",
        }.issubset(stages))
        self.assertGreaterEqual(sum(not case.expected["accepted"] for case in cases), 8)
        self.assertGreaterEqual(sum(case.expected["accepted"] for case in cases), 6)
        for case in cases:
            with self.subTest(case=case.case_id):
                self.assertEqual(case.expected["source_workflow"], "terraced-v6")
                self.assertEqual(case.expected["operation_id"], case.operation_id)
                self.assertTrue(case.expected["response_sha256"])
                self.assertTrue(case.expected["context_sha256"])
                if case.prompt_asset:
                    self.assertTrue(case.expected["prompt_sha256"])

    def test_reference_capture_can_be_regenerated_without_a_model(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "replay"
            index = replay.capture_reference_fixtures(destination=root)
            self.assertTrue(index.is_file())
            cases = replay.load_cases(root)
            self.assertGreaterEqual(len(cases), 18)
            self.assertEqual(replay.run_suite(workflow_id="terraced-v6", root=root)["failures"], [])

    def test_reference_replay_still_matches_recorded_oracle(self):
        result = replay.run_suite(workflow_id="terraced-v6")
        self.assertEqual(result["failures"], [])

    def test_proforma_replay_matches_terraced_v6_oracle(self):
        result = replay.run_suite(workflow_id="proforma-v1")
        self.assertEqual(result["failures"], [])

    def test_malformed_outputs_preserve_reference_accept_reject_and_feedback(self):
        cases = [case for case in replay.load_cases() if not case.expected["accepted"]]
        self.assertGreaterEqual(len(cases), 8)
        for case in cases:
            with self.subTest(case=case.case_id):
                actual = replay.replay_case(case, workflow_id="proforma-v1")
                self.assertFalse(actual["accepted"])
                self.assertEqual(actual["message_sha256"], case.expected["message_sha256"])

    def test_replay_executor_returns_frozen_response_by_logical_operation(self):
        cases = replay.load_cases()
        first = cases[0]
        executor = replay.ReplayExecutor([first])
        self.assertEqual(executor.complete(first.operation_id), first.response)
        with self.assertRaises(KeyError):
            executor.complete(first.operation_id)

    def test_structured_trace_is_machine_readable_and_stable(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "workflow-trace.json"
            result = replay.run_suite(workflow_id="proforma-v1", trace_path=path)
            self.assertEqual(result["failures"], [])
            doc = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(doc["workflow"], "proforma-v1")
            self.assertEqual(len(doc["operations"]), len(replay.load_cases()))
            self.assertTrue(all(row["id"] and row["type"] == "model" for row in doc["operations"]))
            self.assertTrue(all(row["status"] in {"complete", "rejected"} for row in doc["operations"]))


if __name__ == "__main__":
    unittest.main()
