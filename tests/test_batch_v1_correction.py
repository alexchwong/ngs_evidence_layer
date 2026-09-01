from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import nel


class BatchV1CorrectionTests(unittest.TestCase):
    def test_legacy_top_level_run_is_deletable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runs"
            root.mkdir()
            legacy = root / "old-run"
            legacy.mkdir()
            (legacy / "report-final.md").write_text("old", encoding="utf-8")
            latest = root / "LATEST"
            latest.write_text("old-run\n", encoding="utf-8")
            with mock.patch.object(nel, "RUNS_DIR", root), mock.patch.object(nel, "LATEST_PATH", latest):
                rc = nel.cmd_delete(argparse.Namespace(run_id="old-run"))
            self.assertEqual(rc, 0)
            self.assertFalse(legacy.exists())
            self.assertFalse(latest.exists())

    def test_demo_batch_uses_case_ids_as_examples(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runs"
            root.mkdir()
            captured = []

            def fake_prepare(path, **kwargs):
                path.mkdir(parents=True)
                captured.append(kwargs)
                return 0

            args = argparse.Namespace(
                mode="nel-demo", case=None, case_ids="1,2,5", pipeline="lmstudio",
                cul=None, run_id="demo-batch",
            )
            with (
                mock.patch.object(nel, "RUNS_DIR", root),
                mock.patch.object(nel, "_supported_modes", return_value=("ngs-report", "nel-demo")),
                mock.patch.object(nel, "_initialize_user_settings"),
                mock.patch.object(nel, "_ensure_config_ok", return_value={"pipeline": "lmstudio"}),
                mock.patch.object(nel, "_pipeline_parallelism", return_value=1),
                mock.patch.object(nel, "_prepare_run_at", side_effect=fake_prepare),
            ):
                rc = nel.cmd_batch_setup(args)
            self.assertEqual(rc, 0)
            self.assertEqual([row.get("example") for row in captured], [1, 2, 5])
            self.assertTrue(all("validation_case_id" not in row for row in captured))
            self.assertTrue((root / "demo-batch" / "batch.json").is_file())

    def test_native_ui_contains_explicit_batch_mode_contract(self):
        root = Path(__file__).resolve().parents[1]
        page = (root / "ui" / "index.html").read_text(encoding="utf-8")
        server = (root / "ui" / "batch_server.py").read_text(encoding="utf-8")
        self.assertIn('id="batchToggle"', page)
        self.assertIn('batch_mode:state.batchMode', page)
        self.assertIn("Preparing…", page)
        self.assertIn("Resume batch", page)
        self.assertIn("legacy layout · cleanup only", page)
        self.assertNotIn('id="batchCaseSelect"', page)
        self.assertIn('id="casePaneSelect"', page)
        self.assertIn('id="batchPreviewCaseSelect"', page)
        self.assertIn('id="batchCasePickerBtn"', page)
        self.assertIn('id="batchCaseMenu"', page)
        self.assertIn('function renderProgress()', page)
        self.assertIn('progress-phase', page)
        self.assertIn('function progressSegments(', page)
        self.assertIn('id="progressRows"', page)
        self.assertIn("# Case 1", page)
        self.assertIn(">Freetext</button>", page)
        self.assertIn('id="sourceBundled">Examples</button>', page)
        self.assertIn("target=r?.kind==='batch-child'?batchOwnerRow(r):r", page)
        self.assertNotIn("batch-v1.js", server)
        self.assertIn('batch_mode = bool(payload.get("batch_mode"))', server)
        self.assertIn('run_ref = str(batch_id)', server)



if __name__ == "__main__":
    unittest.main()
