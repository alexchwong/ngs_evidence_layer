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

from phase_validation import phase5 as phase5_validation  # noqa: E402
import prepare_redo  # noqa: E402


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
                },
                {
                    "card_id": f"{paper_key}-C0002",
                    "interpretation": "Second interpretation",
                    "genes": ["FLT3"],
                    "diseases": ["AML"],
                    "category": "treatment",
                },
            ],
            "evidence": [
                {
                    "card_id": f"{paper_key}-C0001",
                    "evidence_type": "contiguous_text",
                    "fragments": [],
                    "support_map": {},
                    "table_relations": [],
                },
                {
                    "card_id": f"{paper_key}-C0002",
                    "evidence_type": "contiguous_text",
                    "fragments": [],
                    "support_map": {},
                    "table_relations": [],
                },
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
                phase=5,
                accept_dir=accept,
                archive_dir=archive,
                work_dir=work,
            )
            destination, supplement = prepare_redo.prepare(args)
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
                phase=5,
                accept_dir=accept,
                archive_dir=archive,
                work_dir=work,
            )
            destination, _ = prepare_redo.prepare(args)
            context = json.loads((destination / "phase5.existing-cards.json").read_text())
            self.assertEqual(context["target_publication_key"], paper_key)
            self.assertEqual(context["cards"][0]["interpretation"], "Existing interpretation")

    def test_prepare_revision_all_authorises_all_accepted_cards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper_key, accept, archive, work, envelope, _census = self.make_state(root)
            args = SimpleNamespace(
                publication_key=paper_key,
                phase=5,
                cards="all",
                accept_dir=accept,
                archive_dir=archive,
                work_dir=work,
            )
            destination, revision = prepare_redo.prepare(args)
            self.assertEqual(revision, 1)
            marker = json.loads((destination / "phase5.json").read_text())
            self.assertEqual(marker["mode"], "revision")
            self.assertEqual(
                marker["target_card_ids"],
                [f"{paper_key}-C0001", f"{paper_key}-C0002"],
            )
            targets = json.loads((destination / "paper.phase5-targets.json").read_text())
            self.assertEqual(
                [item["card"] for item in targets["targets"]],
                envelope["final"]["cards"],
            )

    def test_prepare_refuses_existing_work_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper_key, accept, archive, work, _envelope, _census = self.make_state(root)
            (work / paper_key).mkdir(parents=True)
            args = SimpleNamespace(
                publication_key=paper_key,
                phase=5,
                accept_dir=accept,
                archive_dir=archive,
                work_dir=work,
            )
            with self.assertRaisesRegex(ValueError, "working folder already exists"):
                prepare_redo.prepare(args)


class RevisionChangeSetTests(unittest.TestCase):
    def make_documents(self):
        key = "example-paper"
        paper_id = "11111111-1111-1111-1111-111111111111"
        card1 = {
            "card_id": f"{key}-C0001",
            "interpretation": "Old interpretation one",
            "locator": "old",
            "genes": ["NPM1"],
            "diseases": ["AML"],
            "disease_ancestors": [],
            "category": "diagnosis",
            "evidence_tier": "primary",
            "secondary_citation": None,
        }
        card2 = {**card1, "card_id": f"{key}-C0002", "interpretation": "Old interpretation two"}
        evidence1 = {
            "card_id": card1["card_id"],
            "evidence_type": "contiguous_text",
            "fragments": [{"fragment_id": "F1", "role": "claim", "quote": "New supported text."}],
            "support_map": {"interpretation": ["F1"]},
            "table_relations": [],
        }
        evidence2 = {**evidence1, "card_id": card2["card_id"]}
        target_items = []
        for card, evidence in ((card1, evidence1), (card2, evidence2)):
            target_items.append(
                {
                    "card_id": card["card_id"],
                    "short_id": card["card_id"].rsplit("C", 1)[-1],
                    "card_sha256": phase5_validation.canonical_sha256(card),
                    "evidence_sha256": phase5_validation.canonical_sha256(evidence),
                    "card": card,
                    "evidence": evidence,
                }
            )
        phase5 = {
            "schema_version": "1.1",
            "phase": 5,
            "mode": "revision",
            "publication_key": key,
            "target_card_ids": [item["card_id"] for item in target_items],
        }
        targets = {"paper_id": paper_id, "targets": target_items}
        replacement = {**card1, "interpretation": "New supported interpretation", "locator": "new"}
        revision = {
            "card_id": card1["card_id"],
            "replacement_card": replacement,
            "replacement_evidence": evidence1,
            "revision_sha256": phase5_validation.revision_sha256(replacement, evidence1),
        }
        reason = "Redundant accepted card"
        deletion = {
            "card_id": card2["card_id"],
            "reason": reason,
            "deletion_sha256": phase5_validation.deletion_sha256(
                card2["card_id"],
                target_items[1]["card_sha256"],
                target_items[1]["evidence_sha256"],
                reason,
            ),
        }
        provisional = {
            "schema_version": "1.1",
            "phase": 5,
            "mode": "revision",
            "publication_key": key,
            "paper_id": paper_id,
            "round": 1,
            "extraction_model": "model-a",
            "revisions": [revision],
            "deletions": [deletion],
        }
        return phase5, targets, provisional

    def test_revision_provisional_accepts_modify_and_delete_subset(self):
        phase5, targets, provisional = self.make_documents()
        self.assertEqual(
            phase5_validation.validate_revision_provisional(
                phase5, targets, provisional, "New supported text."
            ),
            [],
        )

    def test_revision_asset_requires_confirmed_change_set(self):
        phase5, targets, provisional = self.make_documents()
        revision = provisional["revisions"][0]
        deletion = provisional["deletions"][0]
        review = {
            "schema_version": "1.1",
            "phase": 5,
            "mode": "revision",
            "publication_key": phase5["publication_key"],
            "paper_id": provisional["paper_id"],
            "round": 1,
            "reviewer_model": "model-b",
            "extraction_model_reviewed": "model-a",
            "results": [
                {
                    "operation": "modify",
                    "card_id": revision["card_id"],
                    "revision_sha256": revision["revision_sha256"],
                    "verdict": "pass",
                },
                {
                    "operation": "delete",
                    "card_id": deletion["card_id"],
                    "deletion_sha256": deletion["deletion_sha256"],
                    "verdict": "pass",
                },
            ],
        }
        phase5["base_final_sha256"] = "base-final"
        phase5["base_census_sha256"] = "base-census"
        asset = {
            "schema_version": "1.1",
            "phase": 5,
            "mode": "revision",
            "operation": "change_cards",
            "publication_key": phase5["publication_key"],
            "paper_id": provisional["paper_id"],
            "base_final_sha256": "base-final",
            "base_census_sha256": "base-census",
            "extraction_model": "model-a",
            "reviewer_model": "model-b",
            "revisions": provisional["revisions"],
            "deletions": provisional["deletions"],
            "confirmed_change_set": {
                "add": [],
                "delete": [deletion["card_id"]],
                "modify": [revision["card_id"]],
            },
        }
        self.assertEqual(
            phase5_validation.validate_revision_asset(
                phase5, targets, provisional, review, asset
            ),
            [],
        )
        asset["confirmed_change_set"]["delete"] = []
        self.assertIn(
            "revision asset confirmed_change_set does not exactly match reviewed changes",
            phase5_validation.validate_revision_asset(
                phase5, targets, provisional, review, asset
            ),
        )


if __name__ == "__main__":
    unittest.main()
