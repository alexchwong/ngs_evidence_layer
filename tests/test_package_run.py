from pathlib import Path
import tempfile
import zipfile

import pytest

from scripts.package_run import RUN_ARTIFACTS, package_run_bundle


def test_package_run_contains_every_full_workflow_artifact_only():
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "work"
        work.mkdir()
        for name in RUN_ARTIFACTS:
            (work / name).write_text(f"content for {name}\n", encoding="utf-8")

        # Must not leak unrelated pre-existing files from a supplied work directory.
        (work / "unrelated-private-file.txt").write_text("do not package\n", encoding="utf-8")
        output = work / "ngs-report-debug.zip"

        package_run_bundle(work, output)

        with zipfile.ZipFile(output) as zf:
            assert zf.namelist() == list(RUN_ARTIFACTS)
            assert "unrelated-private-file.txt" not in zf.namelist()
            assert output.name not in zf.namelist()


def test_package_run_fails_closed_if_full_run_artifact_is_missing():
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for name in RUN_ARTIFACTS[:-1]:
            (work / name).write_text("x\n", encoding="utf-8")

        with pytest.raises(FileNotFoundError, match="report-final.md"):
            package_run_bundle(work, work / "debug.zip")
