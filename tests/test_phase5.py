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

import prepare_phase5  # noqa: E402


class PreparePhase5Tests(unittest.TestCase):
    def make_state(self, root):
        accept = root / "accept"
        archive = root / "archive"
        work = root / "work"
        accept.mkdir()
        paper_key = "example-paper"
        paper_id = "11111111-1111-1111-1111-111111111111"
        final = {
            "paper_id": paper_id,
            "cards": [
                {
                    "card_id": f"{paper_key}-C0001",
                    "interpretation": "Existing interpretation",
                    "genes": ["NPM1"],
                    "diseases": ["AML"],
                    "category": "diagnosis",
                }
            ],
        }
        envelope = {
            "schema_version": "1.3",
            "acceptance_path": "confirmed",
            "accepted_at": "2026-08-01T00:00:00+00:00",
            "accepted_at_source": "confirm",
            "accepted_in_version": "0.1.5",
            "metadata": {"publication_key": paper_key, "paper_id": paper_id},
            "final": final,
            "supplements": [{"supplement": 1}],
        }
        census = {"paper_id": paper_id, "entries": []}
        (accept / f"{paper_key}.final.json").write_text(json.dumps(envelope))
        (accept / f"{paper_key}.census.json").write_text(json.dumps(census))
        archive_paper = archive / paper_key
        archive_paper.mkdir(parents=True)
        (archive_paper / "paper.md").write_text("source text")
        (archive_paper / "metadata.json").write_text(json.dumps(envelope["metadata"]))
        (archive_paper / "paper.final.json").write_text(json.dumps({"old": True}))
        (archive_paper / "phase5").mkdir()
        (archive_paper / "phase5" / "001").mkdir()
        (archive_paper / "phase5" / "001" / "old.txt").write_text("old supplement")
        return paper_key, accept, archive, work, envelope, census

    def test_prepare_restores_archive_and_current_accepted_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper_key, accept, archive, work, envelope, census = self.make_state(root)
            args = SimpleNamespace(
                publication_key=paper_key,
                accept_dir=accept,
                archive_dir=archive,
                work_dir=work,
            )
            destination, supplement = prepare_phase5.prepare(args)
            self.assertEqual(supplement, 2)
            self.assertEqual(destination, work / paper_key)
            self.assertTrue((destination / "paper.md").is_file())
            self.assertEqual(
                json.loads((destination / "paper.final.json").read_text()),
                envelope["final"],
            )
            self.assertEqual(
                json.loads((destination / "paper.base.final.json").read_text()),
                envelope["final"],
            )
            self.assertEqual(
                json.loads((destination / "paper.census.json").read_text()), census
            )
            marker = json.loads((destination / "phase5.json").read_text())
            self.assertEqual(marker["phase"], 5)
            self.assertEqual(marker["supplement"], 2)
            self.assertNotIn("phase5", [p.name for p in destination.iterdir() if p.is_dir()])

    def test_prepare_writes_semantic_search_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper_key, accept, archive, work, _envelope, _census = self.make_state(root)
            args = SimpleNamespace(
                publication_key=paper_key,
                accept_dir=accept,
                archive_dir=archive,
                work_dir=work,
            )
            destination, _ = prepare_phase5.prepare(args)
            context = json.loads((destination / "phase5.existing-cards.json").read_text())
            self.assertEqual(context["target_publication_key"], paper_key)
            self.assertEqual(context["cards"][0]["interpretation"], "Existing interpretation")

    def test_prepare_refuses_existing_work_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper_key, accept, archive, work, _envelope, _census = self.make_state(root)
            (work / paper_key).mkdir(parents=True)
            args = SimpleNamespace(
                publication_key=paper_key,
                accept_dir=accept,
                archive_dir=archive,
                work_dir=work,
            )
            with self.assertRaisesRegex(ValueError, "working folder already exists"):
                prepare_phase5.prepare(args)


if __name__ == "__main__":
    unittest.main()
