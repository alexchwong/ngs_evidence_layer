"""Regression coverage for reasoning progress and run-selection stability."""
from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from workflows.proforma_v1.engine.workflow_progress import WorkflowProgress

ROOT = Path(__file__).resolve().parents[1]
MARKING_SERVER = ROOT / "ui" / "marking_server.py"


class UIProgressSelectionFixTests(unittest.TestCase):
    def _workflow(self):
        steps = tuple(SimpleNamespace(id=x) for x in ("a.one", "b.one", "c.one"))
        return SimpleNamespace(
            workflow_id="test",
            source=Path("test.yaml"),
            source_sha256="abc",
            steps=steps,
            doc={"presentation": {"progress_phases": [
                {"id": "phase-a", "label": "A", "steps": ["a.one"]},
                {"id": "phase-b", "label": "B", "steps": ["b.one"]},
                {"id": "phase-c", "label": "C", "steps": ["c.one"]},
            ]}},
        )

    def test_execution_phase_can_move_back_while_high_water_remains_forward(self):
        progress = WorkflowProgress(self._workflow())
        progress.update("a.one", "completed")
        progress.update("b.one", "completed")
        progress.update("c.one", "running")
        progress.invalidate({"a.one", "b.one", "c.one"})
        progress.update("a.one", "running")
        snapshot = progress.snapshot()
        self.assertEqual(snapshot["visible_high_water_phase"], "phase-c")
        self.assertEqual(snapshot["execution_current_phase"], "phase-a")
        self.assertEqual(snapshot["execution_current_step"], "a.one")

    def test_runtime_patch_makes_run_refresh_selection_neutral(self):
        source = MARKING_SERVER.read_text(encoding="utf-8")
        self.assertIn("async function refreshRuns(){const snapshot=selectedSnapshot();", source)
        self.assertIn("if(Math.random()<.25)await refreshRuns()", source)
        self.assertIn("$('refreshRuns').addEventListener('click',()=>refreshRuns());", source)
        self.assertIn("await refreshRuns();await pollRunner()", source)

    def test_prepared_and_manual_selection_share_one_transition(self):
        source = MARKING_SERVER.read_text(encoding="utf-8")
        self.assertIn("function setSelectedRun(id)", source)
        self.assertIn("function selectRun(id){if(state.selected===id){setConsoleTarget(id);return}setSelectedRun(id);", source)
        self.assertIn("const d=await api('/api/setup',{method:'POST',body:payload});setSelectedRun(d.run_id);", source)

    def test_retry_child_constructor_preserves_argv_for_layered_ui(self):
        source = MARKING_SERVER.read_text(encoding="utf-8")
        self.assertIn("def _new_registry_child(proc, run_id: str, phase: str, exclusive: bool, cleanup, argv: list[str]):", source)
        self.assertIn("params = inspect.signature(base._Child).parameters", source)
        self.assertIn('if "argv" in params:', source)
        self.assertIn("argv=list(argv)", source)
        self.assertIn("child = _new_registry_child(proc, run_id, phase, exclusive, cleanup, argv)", source)

    def test_ui_run_retry_stops_on_terminal_workflow_exit(self):
        source = MARKING_SERVER.read_text(encoding="utf-8")
        self.assertIn("_TERMINAL_WORKFLOW_EXIT_CODE = 3", source)
        self.assertIn("if code == _TERMINAL_WORKFLOW_EXIT_CODE or _terminal_failure_present(child.run_id):", source)
        self.assertIn("terminal workflow failure; outer retry suppressed", source)
        self.assertIn("doc.get(\"retryable\") is False", source)
        self.assertIn("if code != 1 or attempt >= child.max_attempts:", source)
        self.assertIn('doc["attempt"] = int(getattr(self, "attempt", 1) or 1)', source)
        self.assertIn('doc["retry_pending"] = bool(getattr(self, "retry_pending", False))', source)

    def test_ui_uses_execution_phase_for_text_and_current_highlight(self):
        source = MARKING_SERVER.read_text(encoding="utf-8")
        self.assertIn("\"current=doc?.current_phase||c.stage||'setup'\"", source)
        self.assertIn("\"current=doc?.current_phase||st?.stage||r.stage||'setup'\"", source)
        self.assertIn("doc?.execution_current_phase||doc?.current_phase", source)
        self.assertIn("phase.id===(doc.execution_current_phase||doc.current_phase)", source)
        self.assertIn("const id=doc.execution_current_phase||stage||doc.current_phase", source)


if __name__ == "__main__":
    unittest.main()
