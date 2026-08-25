import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import unconfirm  # noqa: E402


class UnconfirmTests(unittest.TestCase):
    def make_state(self, root):
        """Create a minimal confirmed state with archive and accept files."""
        key = "example-paper"
        paper_id = "11111111-1111-1111-1111-111111111111"
        accept = root / "accept"
        archive = root / "archive"
        work = root / "work"
        accept.mkdir()
        archive_paper = archive / key
        archive_paper.mkdir(parents=True)

        metadata = {"publication_key": key, "paper_id": paper_id}
        census = {"paper_id": paper_id, "entries": [{"claim_id": "Q001"}]}
        final = {"paper_id": paper_id, "round": 1, "generation": 1}
        envelope = {
            "schema_version": "1.2",
            "acceptance_path": "confirmed",
            "accepted_at": "2026-08-01T00:00:00+00:00",
            "accepted_at_source": "confirm",
            "accepted_in_version": "0.1.0",
            "metadata": metadata,
            "final": final,
        }
        (accept / f"{key}.final.json").write_text(json.dumps(envelope))
        (accept / f"{key}.census.json").write_text(json.dumps(census))
        (archive_paper / "paper.md").write_text("source text")
        (archive_paper / "metadata.json").write_text(json.dumps(metadata))
        (archive_paper / "paper.final.json").write_text(json.dumps(final))
        (archive_paper / "paper.census.json").write_text(json.dumps(census))
        return key, paper_id, accept, archive, work

    def test_unconfirm_restores_archive_to_work(self):
        """Unconfirm should copy archive contents to work folder."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key, _, accept, archive, work = self.make_state(root)

            args = SimpleNamespace(
                publication_key=key,
                work_dir=work,
                accept_dir=accept,
                archive_dir=archive,
                dry_run=False,
            )
            result = unconfirm.unconfirm(args)

            # Work folder should be created with archive contents
            work_paper = work / key
            self.assertTrue(work_paper.is_dir())
            self.assertTrue((work_paper / "paper.md").is_file())
            self.assertTrue((work_paper / "metadata.json").is_file())
            self.assertTrue((work_paper / "paper.final.json").is_file())
            self.assertTrue((work_paper / "paper.census.json").is_file())

            # Accept files should be removed
            self.assertFalse((accept / f"{key}.final.json").exists())
            self.assertFalse((accept / f"{key}.census.json").exists())

            # Archive should still exist
            self.assertTrue((archive / key).is_dir())

            # Result should report what was done
            self.assertEqual(result["restored"], work_paper)
            self.assertEqual(len(result["removed"]), 2)
            self.assertFalse(result["dry_run"])

    def test_unconfirm_works_when_accept_files_already_deleted(self):
        """Unconfirm should succeed even if accept files are manually deleted."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key, _, accept, archive, work = self.make_state(root)

            # Manually delete accept files (simulating user's shortcut)
            (accept / f"{key}.final.json").unlink()
            (accept / f"{key}.census.json").unlink()

            args = SimpleNamespace(
                publication_key=key,
                work_dir=work,
                accept_dir=accept,
                archive_dir=archive,
                dry_run=False,
            )
            result = unconfirm.unconfirm(args)

            # Work folder should be restored
            work_paper = work / key
            self.assertTrue(work_paper.is_dir())
            self.assertTrue((work_paper / "paper.md").is_file())

            # No accept files were removed (already gone)
            self.assertEqual(len(result["removed"]), 0)

    def test_unconfirm_dry_run_does_not_modify(self):
        """Dry run should report actions without making changes."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key, _, accept, archive, work = self.make_state(root)

            args = SimpleNamespace(
                publication_key=key,
                work_dir=work,
                accept_dir=accept,
                archive_dir=archive,
                dry_run=True,
            )
            result = unconfirm.unconfirm(args)

            # Work folder should NOT be created
            self.assertFalse((work / key).exists())

            # Accept files should still exist
            self.assertTrue((accept / f"{key}.final.json").is_file())
            self.assertTrue((accept / f"{key}.census.json").is_file())

            # Result should indicate dry run
            self.assertTrue(result["dry_run"])

    def test_unconfirm_fails_when_archive_missing(self):
        """Unconfirm should fail if archive folder doesn't exist."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            accept = root / "accept"
            accept.mkdir()
            archive = root / "archive"  # Not created
            work = root / "work"

            args = SimpleNamespace(
                publication_key="nonexistent-paper",
                work_dir=work,
                accept_dir=accept,
                archive_dir=archive,
                dry_run=False,
            )
            with self.assertRaisesRegex(ValueError, "archive folder not found"):
                unconfirm.unconfirm(args)

    def test_unconfirm_fails_when_work_folder_exists(self):
        """Unconfirm should fail if work folder already exists."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key, _, accept, archive, work = self.make_state(root)

            # Create the work folder (simulating existing work)
            work_paper = work / key
            work_paper.mkdir(parents=True)
            (work_paper / "some_file.txt").write_text("existing work")

            args = SimpleNamespace(
                publication_key=key,
                work_dir=work,
                accept_dir=accept,
                archive_dir=archive,
                dry_run=False,
            )
            with self.assertRaisesRegex(ValueError, "working folder already exists"):
                unconfirm.unconfirm(args)

    def test_unconfirm_preserves_archive_contents(self):
        """Archive should remain intact after unconfirm."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key, _, accept, archive, work = self.make_state(root)

            # Add some extra files to archive
            (archive / key / "extra_file.txt").write_text("extra content")
            (archive / key / "subdir").mkdir()
            (archive / key / "subdir" / "nested.txt").write_text("nested content")

            args = SimpleNamespace(
                publication_key=key,
                work_dir=work,
                accept_dir=accept,
                archive_dir=archive,
                dry_run=False,
            )
            unconfirm.unconfirm(args)

            # Archive should still have all files
            self.assertTrue((archive / key / "paper.md").is_file())
            self.assertTrue((archive / key / "extra_file.txt").is_file())
            self.assertTrue((archive / key / "subdir" / "nested.txt").is_file())

            # Work should have copies
            self.assertTrue((work / key / "extra_file.txt").is_file())
            self.assertTrue((work / key / "subdir" / "nested.txt").is_file())


if __name__ == "__main__":
    unittest.main()