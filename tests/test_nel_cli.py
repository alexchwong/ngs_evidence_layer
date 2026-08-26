import json
import tempfile
import unittest
from pathlib import Path

import nel


class RunInventoryTests(unittest.TestCase):
    def _run(self, root: Path, pipeline: str) -> Path:
        run = root / "run"
        run.mkdir()
        (run / "case.md").write_text("case\n", encoding="utf-8")
        (run / "workflow.json").write_text(
            json.dumps({
                "schema_version": 1,
                "workflow_id": "terraced-v6",
                "mode": "ngs-report",
                "model_profile": pipeline,
            }),
            encoding="utf-8",
        )
        config = run / "run-config"
        config.mkdir()
        (config / "manifest.json").write_text(
            json.dumps({"pipeline": pipeline, "mode": "ngs-report"}),
            encoding="utf-8",
        )
        return run

    def _artifact(self, run: Path, number: int, group: str, name: str) -> None:
        directory = run / "intermediates" / f"{number:03d}_{group}"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / name).write_text("x: y\n", encoding="utf-8")

    def test_setup_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(Path(tmp), "self")
            self.assertEqual(nel.inspect_run(run)["label"], "Setup only")

    def test_self_diagnosis_advances_to_ptbg(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(Path(tmp), "self")
            self._artifact(run, 4, "diagnosis", "diagnosis-final.yaml")
            status = nel.inspect_run(run)
            self.assertEqual(status["label"], "At PTBG")
            self.assertEqual(status["stage"], "ptbg")

    def test_external_diagnosis_advances_to_prognosis(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(Path(tmp), "lmstudio")
            self._artifact(run, 4, "diagnosis", "diagnosis-final.yaml")
            status = nel.inspect_run(run)
            self.assertEqual(status["label"], "At prognosis")
            self.assertEqual(status["stage"], "prognosis")

    def test_complete_is_report_final(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(Path(tmp), "self")
            (run / "report-final.md").write_text("report\n", encoding="utf-8")
            status = nel.inspect_run(run)
            self.assertTrue(status["complete"])
            self.assertEqual(status["label"], "Complete")

    def test_rejects_path_like_run_id(self):
        with self.assertRaises(nel.CLIError):
            nel._validate_run_id("../outside")


if __name__ == "__main__":
    unittest.main()
