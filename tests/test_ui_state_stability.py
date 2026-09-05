"""Regression contracts for browser selection/progress stability."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "ui" / "marking_server.py"
CONTROLS = ROOT / "ui" / "assets" / "marking-controls.js"
INDEX = ROOT / "ui" / "index.html"


class UIStateStabilityTests(unittest.TestCase):
    def test_marking_extension_no_longer_competes_with_base_progress_renderer(self) -> None:
        source = CONTROLS.read_text(encoding="utf-8")
        self.assertNotIn("function applyRunButton", source)
        self.assertNotIn("function applyProgressPolicy", source)
        self.assertNotIn(".progress-seg[title=\"Marking\"]", source)
        self.assertIn("'Mark validation'", source)

    def test_model_activity_header_wraps_metadata_below_fixed_actions(self) -> None:
        source = CONTROLS.read_text(encoding="utf-8")
        self.assertIn(".model-activity-head{display:grid!important", source)
        self.assertIn("grid-template-rows:auto auto", source)
        self.assertIn(".model-activity-tabs{grid-column:2;grid-row:1", source)
        self.assertIn(".model-activity-meta{grid-column:1/-1;grid-row:2", source)
        self.assertIn("white-space:normal!important", source)
        self.assertIn("overflow-wrap:anywhere", source)

    def test_setup_console_can_be_read_before_run_manifest_exists(self) -> None:
        source = SERVER.read_text(encoding="utf-8")
        self.assertIn('if method == "GET" and path == "/api/console"', source)
        self.assertIn('base.REGISTRY.is_active(run_ref)', source)
        self.assertIn('return base.read_console(run_ref, offset)', source)

    def test_runtime_ui_patch_contains_agreed_stability_contracts(self) -> None:
        source = SERVER.read_text(encoding="utf-8")
        required = [
            "selectionGeneration:0",
            "selectedSnapshotCurrent(snapshot)",
            "setConsoleTarget(d.run_id)",
            "state.runs=mergePendingRuns(state.runs||[])",
            "['complete','marking_incomplete'].includes(target.status)",
            "btn.textContent=target.archived?'Archived':'Run complete'",
            "return mark.status==='running'?'Marking':'Marking pending'",
            "markingActive:markingActiveFor(r.run_id)",
            "if(state.midMode==='dissent')tasks.push(loadDissent())",
            "dissent stale guard",
            "case stale guard",
            "report stale guard",
            "usage stale guard",
            "workflow progress stale guard",
            "model text stale guard",
            "files stale guard",
        ]
        for token in required:
            self.assertIn(token, source)

    def test_patch_applies_cleanly_to_current_base_page(self) -> None:
        if not INDEX.is_file():
            self.skipTest("base ui/index.html is not present in this partial changed-files checkout")
        try:
            from ui import marking_server
        except ImportError as exc:
            self.skipTest(f"full UI server modules are not present: {exc}")

        original = INDEX.read_text(encoding="utf-8")
        patched = marking_server._patch_page_text(original)
        self.assertNotEqual(patched, original)
        self.assertIn("selectionGeneration:0", patched)
        self.assertIn("Marking pending", patched)
        self.assertIn("setConsoleTarget(d.run_id)", patched)
        self.assertIn("if(state.midMode==='dissent')tasks.push(loadDissent())", patched)
        self.assertNotIn("btn.textContent='Retry marking'", patched)
        self.assertNotIn(
            "batch.status==='marking_incomplete'?unresolved:[]",
            patched,
        )


if __name__ == "__main__":
    unittest.main()
