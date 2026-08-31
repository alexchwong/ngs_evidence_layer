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
    def make_state(self, root, *, legacy=True):
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
        old_final = {"paper_id": paper_id, "round": 1, "generation": 1}
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
        census_name = "paper.census.json" if legacy else "paper.census-v003.json"
        (archive_paper / census_name).write_text(json.dumps(census))
        provisional_name = "paper.provisional-001.json" if legacy else "paper.provisional-v004.json"
        review_name = "paper.review-001.json" if legacy else "paper.review-v004.json"
        (archive_paper / provisional_name).write_text(json.dumps({"round": 1}))
        (archive_paper / review_name).write_text(json.dumps({"round": 1}))
        (archive_paper / "phase5").mkdir()
        (archive_paper / "phase5" / "001").mkdir()
        (archive_paper / "phase5" / "001" / "old.txt").write_text("old supplement")
        return key, paper_id, accept, archive, work, envelope, census

    def prepare(self, root, mode, *, legacy=True):
        key, paper_id, accept, archive, work, envelope, census = self.make_state(root, legacy=legacy)
        args = SimpleNamespace(
            publication_key=key,
            mode=mode,
            accept_dir=accept,
            archive_dir=archive,
            work_dir=work,
        )
        destination, marker = prepare_redo.prepare(args)
        return key, paper_id, accept, archive, work, envelope, census, destination, marker

    def prepare_archive_only(self, root, mode="census"):
        key, paper_id, accept, archive, work, envelope, census = self.make_state(root)
        (accept / f"{key}.final.json").unlink()
        (accept / f"{key}.census.json").unlink()
        args = SimpleNamespace(
            publication_key=key,
            mode=mode,
            accept_dir=accept,
            archive_dir=archive,
            work_dir=work,
        )
        destination, marker = prepare_redo.prepare(args)
        return key, paper_id, accept, archive, work, envelope, census, destination, marker

    def test_census_redo_uses_new_filename_after_legacy_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            values = self.prepare(Path(tmp), "census", legacy=True)
            destination, marker = values[-2:]
            self.assertTrue((destination / "paper.census.json").is_file())
            self.assertEqual(marker["mode"], "census")
            self.assertEqual(marker["census_filename"], "paper.census.json")
            self.assertEqual(marker["next_outputs"]["census"], "paper.census-v002.json")
            self.assertEqual(marker["next_outputs"]["provisional"], "paper.provisional-v002.json")

    def test_versioned_archive_advances_attempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            values = self.prepare(Path(tmp), "census", legacy=False)
            marker = values[-1]
            self.assertEqual(marker["next_outputs"]["census"], "paper.census-v004.json")
            self.assertEqual(marker["next_outputs"]["provisional"], "paper.provisional-v005.json")
            self.assertEqual(marker["next_outputs"]["review"], "paper.review-v005.json")

    def test_provisional_redo_restores_archived_census_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            values = self.prepare(Path(tmp), "provisional")
            destination, marker = values[-2:]
            self.assertTrue((destination / "paper.census.json").is_file())
            self.assertFalse((destination / "paper.final.json").exists())
            self.assertEqual(marker["mode"], "provisional")

    def test_cards_review_restores_final_and_uses_separate_revision_namespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            values = self.prepare(Path(tmp), "cards")
            destination, marker = values[-2:]
            self.assertTrue((destination / "paper.census.json").is_file())
            self.assertTrue((destination / "paper.final.json").is_file())
            self.assertEqual(marker["revision"], 1)
            self.assertEqual(
                marker["next_outputs"]["provisional"],
                "paper.provisional-rev001-v001.json",
            )
            self.assertEqual(
                marker["next_outputs"]["phase2r_decisions"],
                "paper.phase2r-decisions-rev001-v001.json",
            )
            self.assertNotIn("targets", marker)
            self.assertFalse((destination / "paper.phase5-targets.json").exists())

    def test_archive_only_preparation_supports_all_modes(self):
        for mode in ("census", "provisional", "cards"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                values = self.prepare_archive_only(Path(tmp), mode)
                destination, marker = values[-2:]
                self.assertEqual(marker["schema_version"], "2.1")
                self.assertEqual(marker["baseline_source"], "archive")
                self.assertTrue((destination / "paper.census.json").is_file())
                self.assertEqual((destination / "paper.final.json").is_file(), mode == "cards")

    def test_preparation_rejects_partial_accepted_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key, _paper_id, accept, archive, work, _envelope, _census = self.make_state(root)
            (accept / f"{key}.census.json").unlink()
            args = SimpleNamespace(
                publication_key=key,
                mode="census",
                accept_dir=accept,
                archive_dir=archive,
                work_dir=work,
            )
            with self.assertRaisesRegex(ValueError, "accepted final/census state is incomplete"):
                prepare_redo.prepare(args)

    def _finish_and_confirm(self, root, mode="provisional", mutate=None):
        (
            key,
            paper_id,
            accept,
            archive,
            work,
            envelope,
            census,
            destination,
            marker,
        ) = self.prepare(root, mode)
        if mode == "census":
            census_name = marker["next_outputs"]["census"]
            (destination / census_name).write_text(
                json.dumps({"paper_id": paper_id, "entries": [{"claim_id": "Q999"}]})
            )
        if mode == "cards":
            provisional_name = marker["next_outputs"]["provisional"]
            revision = marker["revision"]
            round_number = 2
            review_name = f"paper.review-rev{revision:03d}-v001.json"
        else:
            provisional_name = marker["next_outputs"]["provisional"]
            round_number = int(provisional_name.split("-v")[-1].split(".")[0])
            review_name = f"paper.review-v{round_number:03d}.json"
        (destination / provisional_name).write_text(json.dumps({"round": round_number}))
        (destination / review_name).write_text(json.dumps({"round": round_number}))
        new_final = {
            "paper_id": paper_id,
            "round": round_number,
            "generation": 2,
            "audit": {"approved_round": round_number},
        }
        (destination / "paper.final.json").write_text(json.dumps(new_final))
        if mutate is not None:
            mutate(key, accept, archive, destination)
        version_file = root / "VERSION"
        version_file.write_text("0.2.3\n")
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

    def test_confirm_redo_preserves_legacy_history_and_snapshots_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key, accept, archive, work, old_envelope, old_census, result = self._finish_and_confirm(root)
            accepted = json.loads((accept / f"{key}.final.json").read_text())
            self.assertEqual(result[3], "redo")
            self.assertEqual(accepted["schema_version"], "1.5")
            self.assertEqual(accepted["accepted_in_version"], "0.1.0")
            self.assertEqual(accepted["final"]["generation"], 2)
            self.assertEqual(accepted["redos"][0]["mode"], "provisional")
            self.assertIn("supplements", accepted)
            self.assertIn("revisions", accepted)
            snapshot = archive / key / "redo" / "001"
            self.assertEqual(json.loads((snapshot / "accepted.final.json").read_text()), old_envelope)
            self.assertEqual(json.loads((snapshot / "accepted.census.json").read_text()), old_census)
            self.assertEqual((snapshot / "phase5" / "001" / "old.txt").read_text(), "old supplement")
            self.assertFalse((archive / key / "redo.json").exists())
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

    def test_provisional_redo_rejects_census_change_but_census_mode_allows_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def mutate(_key, _accept, _archive, destination):
                path = destination / "paper.census.json"
                census = json.loads(path.read_text())
                census["entries"] = [{"claim_id": "Q999"}]
                path.write_text(json.dumps(census))

            with self.assertRaisesRegex(ValueError, "provisional redo must preserve"):
                self._finish_and_confirm(root, mode="provisional", mutate=mutate)

        with tempfile.TemporaryDirectory() as tmp:
            self._finish_and_confirm(Path(tmp), mode="census")

    def _finish_archive_only(self, root, mutate=None):
        (
            key,
            paper_id,
            accept,
            archive,
            work,
            _envelope,
            _census,
            destination,
            marker,
        ) = self.prepare_archive_only(root, "census")
        (destination / marker["next_outputs"]["census"]).write_text(
            json.dumps({"paper_id": paper_id, "entries": [{"claim_id": "Q002"}]})
        )
        provisional_name = marker["next_outputs"]["provisional"]
        round_number = int(provisional_name.split("-v")[-1].split(".")[0])
        (destination / provisional_name).write_text(json.dumps({"round": round_number}))
        (destination / marker["next_outputs"]["review"]).write_text(
            json.dumps({"round": round_number})
        )
        (destination / "paper.final.json").write_text(
            json.dumps({
                "paper_id": paper_id,
                "round": round_number,
                "generation": 2,
                "audit": {"approved_round": round_number},
            })
        )
        if mutate is not None:
            mutate(key, accept, archive, destination)
        version_file = root / "VERSION"
        version_file.write_text("0.2.3\n")
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
        return key, accept, archive, work, result

    def test_archive_only_redo_reaccepts_and_preserves_archive_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            key, accept, archive, work, result = self._finish_archive_only(Path(tmp))
            accepted = json.loads((accept / f"{key}.final.json").read_text())
            self.assertEqual(result[3], "redo")
            self.assertEqual(accepted["accepted_in_version"], "0.2.3")
            self.assertEqual(accepted["redos"][0]["baseline_source"], "archive")
            snapshot = archive / key / "redo" / "001"
            self.assertTrue((snapshot / "paper.final.json").is_file())
            self.assertFalse((snapshot / "accepted.final.json").exists())
            self.assertFalse(work.joinpath(key).exists())

    def test_archive_only_redo_rejects_stale_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            def mutate(_key, _accept, archive, _destination):
                path = archive / "example-paper" / "paper.final.json"
                final = json.loads(path.read_text())
                final["generation"] = 99
                path.write_text(json.dumps(final))

            with self.assertRaisesRegex(ValueError, "redo baseline is stale"):
                self._finish_archive_only(Path(tmp), mutate=mutate)

    def test_archive_only_redo_rejects_new_accepted_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            def mutate(key, accept, _archive, _destination):
                (accept / f"{key}.final.json").write_text("{}")

            with self.assertRaisesRegex(ValueError, "accepted destinations to remain absent"):
                self._finish_archive_only(Path(tmp), mutate=mutate)


if __name__ == "__main__":
    unittest.main()
