from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import nel
from scripts import run_layout


class BatchProviderBlockingTests(unittest.TestCase):
    def _batch(self, root: Path) -> run_layout.BatchLocation:
        batch_dir = root / "batch-1"
        batch_dir.mkdir()
        children = [
            {"case_id": "001-a", "run_id": "batch-1:001-a", "title": "Case A"},
            {"case_id": "002-b", "run_id": "batch-1:002-b", "title": "Case B"},
        ]
        manifest = {
            "schema_version": 1,
            "kind": "batch",
            "batch_id": "batch-1",
            "workflow": "proforma-v1",
            "mode": "ngs-report",
            "pipeline": "lmstudio",
            "created_at": "2026-09-01T00:00:00+00:00",
            "max_parallel_cases": 1,
            "children": children,
        }
        run_layout.write_batch_manifest(batch_dir, manifest)
        batch = run_layout.resolve_batch(root, "batch-1")
        run_layout.write_batch_state(
            batch,
            run_layout.initial_batch_state(children, created_at=manifest["created_at"]),
        )
        return batch

    def test_preflight_block_does_not_start_children_or_make_them_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runs"
            root.mkdir()
            batch = self._batch(root)
            with (
                mock.patch.object(nel, "RUNS_DIR", root),
                mock.patch.object(nel, "_provider_preflight", return_value="cannot connect to lmstudio"),
            ):
                rc = nel.cmd_batch_run(argparse.Namespace(run_id="batch-1"))
            self.assertEqual(rc, 2)
            state = run_layout.load_batch_state(batch)
            self.assertEqual(state["status"], "blocked")
            self.assertEqual(state["blocked_reason"], "cannot connect to lmstudio")
            self.assertEqual(
                [state["children"][key]["status"] for key in ("001-a", "002-b")],
                ["prepared", "prepared"],
            )
            self.assertFalse(any(state["children"][key]["retry_eligible"] for key in state["children"]))

    def test_connection_text_is_classified_as_provider_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            child = Path(tmp)
            log = child / "logs" / "batch-run.log"
            log.parent.mkdir()
            log.write_text("RuntimeError: Connection refused while opening http://127.0.0.1:1234/v1\n", encoding="utf-8")
            reason = nel._provider_failure_reason(child, "lmstudio")
            self.assertIsNotNone(reason)
            self.assertIn("Connection refused", reason)

    def test_validation_failure_is_not_misclassified_as_provider_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            child = Path(tmp)
            log = child / "logs" / "batch-run.log"
            log.parent.mkdir()
            log.write_text("report-write failed validation after 3 attempts\n", encoding="utf-8")
            self.assertIsNone(nel._provider_failure_reason(child, "openrouter"))


if __name__ == "__main__":
    unittest.main()
