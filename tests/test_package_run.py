from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.package_run import artifact_allowlist, package_run_bundle
from scripts.setup_workflow import setup_workflow


class PackageRunTests(unittest.TestCase):
    def _work(self, tmp, workflow):
        work = Path(tmp) / workflow
        setup_workflow(workflow=workflow, mode="ngs-report", work_dir=work)
        artifacts = artifact_allowlist(work)
        for name in artifacts:
            path = work / name
            if not path.exists():
                path.write_text(f"content for {name}\n", encoding="utf-8")
        return work, artifacts

    def test_package_run_contains_declared_current_workflow_artifacts_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            work, artifacts = self._work(tmp, "diagnosis-first-v1")
            (work / "unrelated-private-file.txt").write_text("do not package\n", encoding="utf-8")
            output = work / "debug.zip"
            package_run_bundle(work, output)
            with zipfile.ZipFile(output) as zf:
                self.assertEqual(zf.namelist(), list(artifacts))
                self.assertNotIn("unrelated-private-file.txt", zf.namelist())

    def test_package_run_uses_legacy_manifest_from_workflow_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            work, artifacts = self._work(tmp, "legacy-v1")
            output = work / "debug.zip"
            package_run_bundle(work, output)
            with zipfile.ZipFile(output) as zf:
                self.assertEqual(zf.namelist(), list(artifacts))
                self.assertIn("adjudication.json", zf.namelist())
                self.assertNotIn("report-draft-dx.md", zf.namelist())

    def test_package_run_fails_closed_if_declared_artifact_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            work, artifacts = self._work(tmp, "legacy-v1")
            missing = work / artifacts[-1]
            missing.unlink()
            with self.assertRaisesRegex(FileNotFoundError, missing.name):
                package_run_bundle(work, work / "debug.zip")


if __name__ == "__main__":
    unittest.main()
