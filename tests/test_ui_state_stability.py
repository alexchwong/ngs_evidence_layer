"""Regression contracts for browser selection/progress stability."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "ui" / "marking_server.py"
CONTROLS = ROOT / "ui" / "assets" / "marking-controls.js"
INDEX = ROOT / "ui" / "index.html"


class UIStateStabilityTests(unittest.TestCase):
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
        self.assertIn("setSelectedRun(d.run_id)", patched)
        self.assertIn("if(state.midMode==='dissent')tasks.push(loadDissent())", patched)
        self.assertNotIn("btn.textContent='Retry marking'", patched)
        self.assertNotIn(
            "batch.status==='marking_incomplete'?unresolved:[]",
            patched,
        )


if __name__ == "__main__":
    unittest.main()
