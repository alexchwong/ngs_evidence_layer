import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import confirm  # noqa: E402
import prepare_redo  # noqa: E402


class RedoTests(unittest.TestCase):
    def make_state(self, root):
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
        old_final = {"paper_id": paper_id, "generation": 1}
        envelope = {
            "schema_version": "1.4",
            "acceptance_path": "confirmed",
            "accepted_at": "2026-08-01T00:00:00+00:00",
            "accepted_at_source": "confirm",
            "accepted_in_version": "0.1.0",
            "metadata": metadata,
            "final": old_final,
            "supplements": [{"supplement": 1}],
            "revisions": [{"revision": 1}],
        }
        (accept / f"{key}.final.json").write_text(json.dumps(envelope))
        (accept / f"{key}.census.json").write_text(json.dumps(census))
        (archive_paper / "paper.md").write_text("source text")
        (archive_paper / "metadata.json").write_text(json.dumps(metadata))
        (archive_paper / "paper.final.json").write_text(json.dumps(old_final))
        (archive_paper / "phase5").mkdir()
        (archive_paper / "phase5" / "001").mkdir()
        (archive_paper / "phase5" / "001" / "old.txt").write_text("old supplement")
        return key, paper_id, accept, archive, work, envelope, census

    def prepare(self, root, phase):
        key, paper_id, accept, archive, work, envelope, census = self.make_state(root)
        args = SimpleNamespace(
            publication_key=key,
            phase=phase,
            cards=None,
            accept_dir=accept,
            archive_dir=archive,
            work_dir=work,
        )
        destination, redo = prepare_redo.prepare(args)
        return key, paper_id, accept, archive, work, envelope, census, destination, redo

    def test_phase1_redo_does_not_restore_census(self):
        with tempfile.TemporaryDirectory() as tmp:
            values = self.prepare(Path(tmp), 1)
            destination, redo = values[-2:]
            self.assertEqual(redo, 1)
            self.assertTrue((destination / "paper.md").is_file())
            self.assertTrue((destination / "metadata.json").is_file())
            self.assertFalse((destination / "paper.census.json").exists())
            self.assertTrue((destination / "paper.base.census.json").is_file())
            self.assertTrue((destination / "paper.base.final.json").is_file())
            marker = json.loads((destination / "redo.json").read_text())
            self.assertEqual(marker["start_phase"], 1)
            self.assertEqual(marker["redo"], 1)

    def test_phase2_redo_restores_accepted_census_and_rejects_cards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key, _, accept, archive, work, _, census = self.make_state(root)
            args = SimpleNamespace(
                publication_key=key,
                phase=2,
                cards=None,
                accept_dir=accept,
                archive_dir=archive,
                work_dir=work,
            )
            destination, _ = prepare_redo.prepare(args)
            self.assertEqual(json.loads((destination / "paper.census.json").read_text()), census)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key, _, accept, archive, work, _, _ = self.make_state(root)
            args = SimpleNamespace(
                publication_key=key,
                phase=2,
                cards="0001",
                accept_dir=accept,
                archive_dir=archive,
                work_dir=work,
            )
            with self.assertRaisesRegex(ValueError, "--cards is valid only with --phase 5"):
                prepare_redo.prepare(args)

    def _finish_and_confirm(self, root, phase=2, mutate=None):
        (
            key,
            paper_id,
            accept,
            archive,
            work,
            envelope,
            census,
            destination,
            _,
        ) = self.prepare(root, phase)
        if phase == 1:
            (destination / "paper.census.json").write_text(
                json.dumps({"paper_id": paper_id, "entries": [{"claim_id": "Q999"}]})
            )
        new_final = {"paper_id": paper_id, "generation": 2, "audit": {"approved_round": 1}}
        (destination / "paper.final.json").write_text(json.dumps(new_final))
        (destination / "paper.provisional-001.json").write_text("{}")
        (destination / "paper.review-001.json").write_text("{}")
        if mutate is not None:
            mutate(key, accept, archive, destination)
        version_file = root / "VERSION"
        version_file.write_text("0.2.0\n")
        args = SimpleNamespace(
            publication_key=key,
            work_dir=work,
            accept_dir=accept,
            archive_dir=archive,
            overwrite=False,
        )
        with (
            mock.patch.object(confirm, "VERSION_FILE", version_file),
            mock.patch.object(confirm.validation, "validate_package", return_value=([], [], {})),
            mock.patch.object(
                confirm.final_validation,
                "validate_phase_files",
                return_value=([], [], {"cards": 1, "ratio": 1.0}),
            ),
            mock.patch.object(confirm.validation, "schema_errors", return_value=[]),
        ):
            result = confirm.confirm(args)
        return key, accept, archive, work, envelope, census, result

    def test_confirm_redo_replaces_lineage_and_snapshots_superseded_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key, accept, archive, work, old_envelope, old_census, result = self._finish_and_confirm(root)
            accepted = json.loads((accept / f"{key}.final.json").read_text())
            self.assertEqual(result[3], "redo")
            self.assertEqual(accepted["schema_version"], "1.5")
            self.assertEqual(accepted["accepted_in_version"], "0.1.0")
            self.assertEqual(accepted["final"]["generation"], 2)
            self.assertEqual(accepted["redos"][0]["redo"], 1)
            self.assertEqual(accepted["redos"][0]["start_phase"], 2)
            self.assertEqual(accepted["redos"][0]["accepted_in_version"], "0.2.0")
            self.assertNotIn("supplements", accepted)
            self.assertNotIn("revisions", accepted)
            snapshot = archive / key / "redo" / "001"
            self.assertEqual(
                json.loads((snapshot / "accepted.final.json").read_text()), old_envelope
            )
            self.assertEqual(
                json.loads((snapshot / "accepted.census.json").read_text()), old_census
            )
            self.assertEqual((snapshot / "phase5" / "001" / "old.txt").read_text(), "old supplement")
            self.assertFalse((archive / key / "redo.json").exists())
            self.assertFalse((archive / key / "paper.base.final.json").exists())
            self.assertFalse(work.joinpath(key).exists())

    def test_confirm_rejects_stale_accepted_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def mutate(key, accept, _archive, _destination):
                path = accept / f"{key}.final.json"
                envelope = json.loads(path.read_text())
                envelope["final"]["generation"] = 99
                path.write_text(json.dumps(envelope))

            with self.assertRaisesRegex(ValueError, "redo baseline is stale"):
                self._finish_and_confirm(root, mutate=mutate)

    def test_phase2_redo_rejects_census_change_but_phase1_allows_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def mutate(_key, _accept, _archive, destination):
                census = json.loads((destination / "paper.census.json").read_text())
                census["entries"] = [{"claim_id": "Q999"}]
                (destination / "paper.census.json").write_text(json.dumps(census))

            with self.assertRaisesRegex(ValueError, "Phase 2 redo must preserve"):
                self._finish_and_confirm(root, phase=2, mutate=mutate)

        with tempfile.TemporaryDirectory() as tmp:
            self._finish_and_confirm(Path(tmp), phase=1)


if __name__ == "__main__":
    unittest.main()
