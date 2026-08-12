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

from phase_validation import phase5 as chat_validation  # noqa: E402
import prepare_redo  # noqa: E402


class Phase5RevisionPrepareTests(unittest.TestCase):
    def make_state(self, root):
        accept = root / "accept"
        archive = root / "archive"
        work = root / "work"
        accept.mkdir()
        paper_key = "example-paper"
        paper_id = "11111111-1111-1111-1111-111111111111"
        card = {
            "card_id": f"{paper_key}-C0001",
            "genes": ["NPM1"],
            "diseases": ["AML"],
            "disease_ancestors": [],
            "category": "diagnosis",
            "interpretation": "Existing interpretation",
            "locator": "line 1",
            "evidence_tier": "univariable or descriptive",
            "secondary_citation": None,
        }
        evidence = {
            "card_id": card["card_id"],
            "evidence_type": "contiguous_text",
            "fragments": [
                {"fragment_id": "F01", "role": "claim", "quote": "source text", "locator": "line 1"}
            ],
            "support_map": {"effect": ["F01"]},
        }
        final = {"paper_id": paper_id, "cards": [card], "evidence": [evidence]}
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
        return paper_key, accept, archive, work, envelope, census

    def test_prepare_revision_writes_target_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper_key, accept, archive, work, envelope, _ = self.make_state(root)
            args = SimpleNamespace(
                publication_key=paper_key,
                phase=5,
                cards="0001",
                accept_dir=accept,
                archive_dir=archive,
                work_dir=work,
            )
            destination, revision = prepare_redo.prepare(args)
            self.assertEqual(revision, 1)
            marker = json.loads((destination / "phase5.json").read_text())
            self.assertEqual(marker["mode"], "revision")
            self.assertEqual(marker["target_card_ids"], [f"{paper_key}-C0001"])
            targets = json.loads((destination / "paper.phase5-targets.json").read_text())
            self.assertEqual(targets["targets"][0]["short_id"], "0001")
            self.assertEqual(targets["targets"][0]["card"], envelope["final"]["cards"][0])

    def test_prepare_revision_rejects_unknown_card(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper_key, accept, archive, work, _, _ = self.make_state(root)
            args = SimpleNamespace(
                publication_key=paper_key,
                phase=5,
                cards="0002",
                accept_dir=accept,
                archive_dir=archive,
                work_dir=work,
            )
            with self.assertRaisesRegex(ValueError, "requested card not found"):
                prepare_redo.prepare(args)


class Phase5ChatValidationTests(unittest.TestCase):
    def fixture(self):
        card_id = "example-paper-C0001"
        original_card = {
            "card_id": card_id,
            "genes": ["NPM1"],
            "diseases": ["AML"],
            "disease_ancestors": [],
            "category": "diagnosis",
            "interpretation": "Old",
            "locator": "line 1",
            "evidence_tier": "univariable or descriptive",
            "secondary_citation": None,
        }
        evidence = {
            "card_id": card_id,
            "evidence_type": "contiguous_text",
            "fragments": [
                {"fragment_id": "F01", "role": "claim", "quote": "new source", "locator": "line 2"}
            ],
            "support_map": {"effect": ["F01"]},
        }
        replacement = dict(original_card, interpretation="New", locator="line 2")
        phase5 = {
            "phase": 5,
            "mode": "revision",
            "publication_key": "example-paper",
            "target_card_ids": [card_id],
        }
        targets = {
            "paper_id": "11111111-1111-1111-1111-111111111111",
            "targets": [{"card_id": card_id, "card": original_card, "evidence": evidence}],
        }
        item = {
            "card_id": card_id,
            "replacement_card": replacement,
            "replacement_evidence": evidence,
            "revision_sha256": chat_validation.revision_sha256(replacement, evidence),
        }
        provisional = {
            "schema_version": "1.1",
            "phase": 5,
            "mode": "revision",
            "publication_key": "example-paper",
            "paper_id": targets["paper_id"],
            "round": 1,
            "extraction_model": "ChatGPT",
            "revisions": [item],
            "deletions": [],
        }
        return phase5, targets, provisional

    def test_revision_provisional_passes(self):
        phase5, targets, provisional = self.fixture()
        self.assertEqual(
            chat_validation.validate_revision_provisional(
                phase5, targets, provisional, "new source"
            ),
            [],
        )

    def test_off_target_revision_fails(self):
        phase5, targets, provisional = self.fixture()
        provisional["revisions"][0]["card_id"] = "example-paper-C0002"
        errors = chat_validation.validate_revision_provisional(
            phase5, targets, provisional, "new source"
        )
        self.assertTrue(any("off-target" in error for error in errors))

    def test_structural_field_change_fails(self):
        phase5, targets, provisional = self.fixture()
        provisional["revisions"][0]["replacement_card"]["genes"] = ["FLT3"]
        provisional["revisions"][0]["revision_sha256"] = chat_validation.revision_sha256(
            provisional["revisions"][0]["replacement_card"],
            provisional["revisions"][0]["replacement_evidence"],
        )
        errors = chat_validation.validate_revision_provisional(
            phase5, targets, provisional, "new source"
        )
        self.assertTrue(any("immutable card field changed: genes" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
