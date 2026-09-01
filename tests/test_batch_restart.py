from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import nel
from scripts import run_layout


class BatchRestartSelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / "batch-1"
        path.mkdir()
        self.children = [
            {"case_id": "001-a", "run_id": "batch-1:001-a", "title": "Case A"},
            {"case_id": "002-b", "run_id": "batch-1:002-b", "title": "Case B"},
            {"case_id": "003-c", "run_id": "batch-1:003-c", "title": "Case C"},
        ]
        self.batch = run_layout.BatchLocation(
            batch_id="batch-1",
            path=path,
            manifest={"children": self.children},
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _state(self, parent: str, statuses: list[str]):
        return {
            "status": parent,
            "children": {
                row["case_id"]: {"status": status}
                for row, status in zip(self.children, statuses)
            },
        }

    def test_complete_with_errors_restarts_failed_only(self):
        selected = nel._selected_batch_children(
            self.batch,
            self._state("complete_with_errors", ["complete", "failed", "complete"]),
        )
        self.assertEqual([row["case_id"] for row in selected], ["002-b"])


    def test_complete_with_errors_skips_non_retryable_provider_failure(self):
        state = self._state("complete_with_errors", ["complete", "failed", "complete"])
        state["children"]["002-b"]["retry_eligible"] = False
        selected = nel._selected_batch_children(self.batch, state)
        self.assertEqual(selected, [])

    def test_blocked_restarts_all_noncomplete_children_after_user_resume(self):
        selected = nel._selected_batch_children(
            self.batch,
            self._state("blocked", ["complete", "blocked", "prepared"]),
        )
        self.assertEqual([row["case_id"] for row in selected], ["002-b", "003-c"])

    def test_stopped_restarts_every_noncomplete_child(self):
        selected = nel._selected_batch_children(
            self.batch,
            self._state("stopped", ["complete", "stopped", "failed"]),
        )
        self.assertEqual([row["case_id"] for row in selected], ["002-b", "003-c"])

    def test_complete_has_no_work(self):
        self.assertEqual(
            nel._selected_batch_children(
                self.batch,
                self._state("complete", ["complete", "complete", "complete"]),
            ),
            [],
        )

    def test_running_rejects_second_runner(self):
        with self.assertRaisesRegex(nel.CLIError, "already running"):
            nel._selected_batch_children(
                self.batch,
                self._state("running", ["running", "prepared", "prepared"]),
            )


if __name__ == "__main__":
    unittest.main()
