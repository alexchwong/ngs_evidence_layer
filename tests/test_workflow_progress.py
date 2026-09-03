import json
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path

from workflows.proforma_v1.engine.context import WorkflowContext
from workflows.proforma_v1.engine.workflow_progress import ProgressPlanError, WorkflowProgress, load_progress_plan
from workflows.proforma_v1.engine.workflow_runner import WorkflowRunner


@dataclass
class DummyStep:
    id: str
    needs: tuple[str, ...] = ()
    when: dict | None = None
    type: str = "model"
    execution: dict = field(default_factory=dict)
    review: dict | None = None
    output: dict = field(default_factory=dict)
    inputs: dict = field(default_factory=dict)


class DummyWorkflow:
    def __init__(self, root: Path, steps):
        self.workflow_id = "test-workflow"
        self.source = root / "test.yaml"
        self.source.write_text("version: 1\n", encoding="utf-8")
        self.source_sha256 = "test-sha"
        self.steps = list(steps)
        self._steps = {step.id: step for step in self.steps}

    def step(self, step_id):
        return self._steps[step_id]


class DummyExecutor:
    def __init__(self, fail=None):
        self.fail = fail

    def is_complete(self, step_id, context):
        return False

    def execute(self, step, context):
        if step.id == self.fail:
            raise RuntimeError("synthetic failure")
        return {"status": "complete"}


class WorkflowProgressTests(unittest.TestCase):
    def test_missing_sidecar_falls_back_to_workflow_steps(self):
        with tempfile.TemporaryDirectory() as td:
            workflow = DummyWorkflow(Path(td), [DummyStep("alpha"), DummyStep("beta", needs=("alpha",))])
            plan = load_progress_plan(workflow)
            self.assertEqual([p["id"] for p in plan["phases"]], ["alpha", "beta"])
            self.assertEqual([p["steps"] for p in plan["phases"]], [["alpha"], ["beta"]])

    def test_sidecar_must_cover_each_step_exactly_once(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workflow = DummyWorkflow(root, [DummyStep("alpha"), DummyStep("beta")])
            (root / "test.progress.yaml").write_text(
                "version: 1\nphases:\n  - id: first\n    label: First\n    steps: [alpha]\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ProgressPlanError, "does not cover"):
                load_progress_plan(workflow)

    def test_runner_records_completed_and_conditionally_skipped_steps(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workflow = DummyWorkflow(
                root,
                [
                    DummyStep("alpha"),
                    DummyStep("beta", needs=("alpha",), when={"predicate": "never"}),
                ],
            )
            (root / "test.progress.yaml").write_text(
                "version: 1\nphases:\n"
                "  - id: work\n    label: Work\n    steps: [alpha, beta]\n",
                encoding="utf-8",
            )
            work = root / "run"
            context = WorkflowContext(work, executor="provider", data={"predicates": {}})
            result = WorkflowRunner(workflow, DummyExecutor()).run_all(context)
            self.assertEqual(result.status, "complete")
            doc = json.loads((work / "logs" / "workflow-progress.json").read_text(encoding="utf-8"))
            states = {row["id"]: row["status"] for row in doc["steps"]}
            self.assertEqual(states, {"alpha": "completed", "beta": "skipped"})
            self.assertTrue(doc["complete"])
            self.assertEqual(doc["phases"][0]["status"], "completed")

    def test_runner_records_failed_step(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workflow = DummyWorkflow(root, [DummyStep("alpha")])
            work = root / "run"
            context = WorkflowContext(work, executor="provider")
            with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
                WorkflowRunner(workflow, DummyExecutor(fail="alpha")).run_all(context)
            doc = json.loads((work / "logs" / "workflow-progress.json").read_text(encoding="utf-8"))
            self.assertEqual(doc["steps"][0]["status"], "failed")
            self.assertEqual(doc["phases"][0]["status"], "failed")

    def test_resume_resets_stale_running_or_failed_states(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workflow = DummyWorkflow(root, [DummyStep("alpha"), DummyStep("beta")])
            work = root / "run"
            progress = WorkflowProgress(workflow)
            context = WorkflowContext(work, executor="provider")
            progress.bind(context)
            progress.update("alpha", "running")
            progress.update("beta", "failed", error="interrupted")
            restored = WorkflowProgress(workflow)
            restored.bind(context)
            self.assertEqual(restored.status("alpha"), "pending")
            self.assertEqual(restored.status("beta"), "pending")


if __name__ == "__main__":
    unittest.main()
