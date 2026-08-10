import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "quarantine.py"
SPEC = importlib.util.spec_from_file_location("quarantine", SCRIPT)
quarantine = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(quarantine)


class QuarantineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.work = self.root / "work"
        self.held = self.root / "quarantine"
        self.accept = self.root / "accept"
        self.key = "fixture-2026-example"

    def tearDown(self):
        self.temporary.cleanup()

    def make_work(self, key=None):
        key = key or self.key
        folder = self.work / key
        folder.mkdir(parents=True)
        (folder / "metadata.json").write_text(
            json.dumps({"publication_key": key}), encoding="utf-8"
        )
        (folder / "paper.md").write_text("paper", encoding="utf-8")
        (folder / "paper.review-001.json").write_text("{}", encoding="utf-8")
        return folder

    def test_hold_and_return_preserve_history_and_append_audit(self):
        working = self.make_work()
        destination = quarantine.quarantine_paper(
            self.key,
            "Not currently in corpus scope",
            work_dir=self.work,
            quarantine_dir=self.held,
            accept_dir=self.accept,
            event_time="2026-08-10T00:00:00+00:00",
        )

        self.assertEqual(destination, self.held / self.key)
        self.assertFalse(working.exists())
        self.assertTrue((destination / "paper.review-001.json").is_file())
        audit = json.loads((destination / "quarantine.json").read_text())
        self.assertEqual(audit["status"], "quarantined")
        self.assertEqual(audit["events"][0]["reason"], "Not currently in corpus scope")
        self.assertEqual(quarantine.list_quarantined(quarantine_dir=self.held), [audit])

        restored = quarantine.return_to_work(
            self.key,
            work_dir=self.work,
            quarantine_dir=self.held,
            review_note="Scope policy changed",
            event_time="2026-08-11T00:00:00+00:00",
        )

        self.assertEqual(restored, self.work / self.key)
        self.assertFalse(destination.exists())
        self.assertTrue((restored / "paper.review-001.json").is_file())
        audit = json.loads((restored / "quarantine.json").read_text())
        self.assertEqual(audit["status"], "returned-to-work")
        self.assertEqual([event["action"] for event in audit["events"]], [
            "quarantined", "returned-to-work"
        ])
        self.assertEqual(audit["events"][1]["note"], "Scope policy changed")

    def test_paper_can_be_quarantined_again_after_return(self):
        self.make_work()
        quarantine.quarantine_paper(
            self.key, "first", work_dir=self.work,
            quarantine_dir=self.held, accept_dir=self.accept,
        )
        quarantine.return_to_work(
            self.key, work_dir=self.work, quarantine_dir=self.held,
        )
        quarantine.quarantine_paper(
            self.key, "second", work_dir=self.work,
            quarantine_dir=self.held, accept_dir=self.accept,
        )
        audit = json.loads((self.held / self.key / "quarantine.json").read_text())
        self.assertEqual(len(audit["events"]), 3)
        self.assertEqual(audit["events"][-1]["reason"], "second")

    def test_hold_rejects_accepted_paper_without_changing_work(self):
        working = self.make_work()
        self.accept.mkdir()
        (self.accept / f"{self.key}.final.json").write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "already has accepted state"):
            quarantine.quarantine_paper(
                self.key, "reason", work_dir=self.work,
                quarantine_dir=self.held, accept_dir=self.accept,
            )

        self.assertTrue(working.is_dir())
        self.assertFalse((working / "quarantine.json").exists())

    def test_hold_rejects_metadata_mismatch(self):
        working = self.make_work()
        (working / "metadata.json").write_text(
            json.dumps({"publication_key": "other-key"}), encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "metadata publication_key"):
            quarantine.quarantine_paper(
                self.key, "reason", work_dir=self.work,
                quarantine_dir=self.held, accept_dir=self.accept,
            )

    def test_transitions_never_overwrite_destination(self):
        working = self.make_work()
        (self.held / self.key).mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "destination already exists"):
            quarantine.quarantine_paper(
                self.key, "reason", work_dir=self.work,
                quarantine_dir=self.held, accept_dir=self.accept,
            )
        self.assertTrue(working.is_dir())
        self.assertFalse((working / "quarantine.json").exists())

    def test_unsafe_key_and_blank_reason_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsafe publication key"):
            quarantine.quarantine_paper("../escape", "reason")
        with self.assertRaisesRegex(ValueError, "non-empty quarantine reason"):
            quarantine.quarantine_paper(self.key, "  ")

    def test_cli_hold_list_and_review(self):
        self.make_work()
        common = [
            "--work-dir", str(self.work),
            "--quarantine-dir", str(self.held),
        ]
        held = subprocess.run(
            [sys.executable, str(SCRIPT), "hold", "--key", self.key,
             "--reason", "needs review", "--accept-dir", str(self.accept), *common],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(held.returncode, 0, held.stderr)
        self.assertIn("QUARANTINED", held.stdout)

        listed = subprocess.run(
            [sys.executable, str(SCRIPT), "list", "--quarantine-dir", str(self.held)],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn(f"{self.key}\t", listed.stdout)
        self.assertIn("needs review", listed.stdout)

        reviewed = subprocess.run(
            [sys.executable, str(SCRIPT), "review", "--key", self.key,
             "--note", "retry", *common],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(reviewed.returncode, 0, reviewed.stderr)
        self.assertIn("RETURNED FOR REVIEW", reviewed.stdout)
        self.assertTrue((self.work / self.key).is_dir())

    def test_cli_hold_uses_default_reason(self):
        self.make_work()
        result = subprocess.run(
            [
                sys.executable, str(SCRIPT), "hold", "--key", self.key,
                "--work-dir", str(self.work),
                "--quarantine-dir", str(self.held),
                "--accept-dir", str(self.accept),
            ],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        audit = json.loads((self.held / self.key / "quarantine.json").read_text())
        self.assertEqual(audit["events"][0]["reason"], "Out of scope for the corpus")


if __name__ == "__main__":
    unittest.main()