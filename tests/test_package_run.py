from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.package_run import PROTOTYPE_RUN_ARTIFACTS, RUN_ARTIFACTS, package_run_bundle


class PackageRunTests(unittest.TestCase):
    def test_package_run_contains_every_full_workflow_artifact_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "work"
            work.mkdir()
            for name in RUN_ARTIFACTS:
                (work / name).write_text(f"content for {name}\n", encoding="utf-8")

            # Must not leak unrelated pre-existing files from a supplied work directory.
            (work / "unrelated-private-file.txt").write_text(
                "do not package\n", encoding="utf-8"
            )
            output = work / "ngs-report-debug.zip"

            package_run_bundle(work, output)

            with zipfile.ZipFile(output) as zf:
                self.assertEqual(zf.namelist(), list(RUN_ARTIFACTS))
                self.assertNotIn("unrelated-private-file.txt", zf.namelist())
                self.assertNotIn(output.name, zf.namelist())

    def test_package_run_fails_closed_if_full_run_artifact_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            for name in RUN_ARTIFACTS[:-1]:
                (work / name).write_text("x\n", encoding="utf-8")

            with self.assertRaisesRegex(FileNotFoundError, "report-final.md"):
                package_run_bundle(work, work / "debug.zip")

    def test_package_run_detects_prototype_without_changing_legacy_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            for name in PROTOTYPE_RUN_ARTIFACTS:
                if name == "diagnostic_evidence.json":
                    (work / name).write_text(
                        '{"workflow_profile":"0.2.2_prototype"}\n', encoding="utf-8"
                    )
                else:
                    (work / name).write_text(f"content for {name}\n", encoding="utf-8")
            (work / "adjudication.json").write_text("legacy stale file\n", encoding="utf-8")
            output = work / "debug.zip"

            package_run_bundle(work, output)

            with zipfile.ZipFile(output) as zf:
                self.assertEqual(zf.namelist(), list(PROTOTYPE_RUN_ARTIFACTS))
                self.assertNotIn("adjudication.json", zf.namelist())


if __name__ == "__main__":
    unittest.main()
