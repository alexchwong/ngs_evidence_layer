#!/usr/bin/env python3
"""Focused tests for the portable, bounded ingestion workflow."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "ingest.py"
FIXTURES = ROOT / "tests" / "fixtures"
STEMS = ("fixture-alpha--aaaaaaaa", "fixture-beta--bbbbbbbb")
ALPHA_ID = "aaaaaaaa-0000-0000-0000-000000000001"

sys.path.insert(0, str(ROOT / "scripts"))
import next_paper  # noqa: E402


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class IngestWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.input_root = self.root / "input" / "fixtures"
        self.output_root = self.root / "output"
        self.exchange_root = self.root / "exchange"
        (self.input_root / "index").mkdir(parents=True)
        (self.input_root / "markdown").mkdir()
        shutil.copy(FIXTURES / "index" / "papers.jsonl", self.input_root / "index")
        for stem in STEMS:
            shutil.copy(FIXTURES / "markdown" / f"{stem}.md", self.input_root / "markdown")
        (self.output_root / "reports").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def run_ingest(self, job, expect_success=True, extra=None):
        command = [
            sys.executable, str(SCRIPT), job,
            "--input-root", str(self.input_root),
            "--output-root", str(self.output_root),
            "--exchange-root", str(self.exchange_root),
        ]
        command.extend(extra or [])
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
        )
        output = result.stdout + result.stderr
        if expect_success:
            self.assertEqual(result.returncode, 0, output)
        else:
            self.assertNotEqual(result.returncode, 0, output)
        return output

    def portable_path(self, stem, phase, area="inbox"):
        suffix = "context.md" if area == "outbox" else "json"
        middle = f"phase{phase}-" if area == "outbox" else f"phase{phase}."
        return (
            self.exchange_root / "ingest" / f"phase{phase}" / area /
            f"{stem}.{middle}{suffix}"
        )

    def accepted_path(self, stem, phase):
        return self.output_root / f"phase{phase}" / f"{stem}.phase{phase}.json"

    def outbox_source_path(self, stem, phase):
        return self.exchange_root / "ingest" / f"phase{phase}" / "outbox" / f"{stem}.md"

    def write_phase1_response(self, stem):
        destination = self.portable_path(stem, 1)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(FIXTURES / "census" / f"{stem}.census.json", destination)

    def phase2_package(self, stem):
        cards = read(FIXTURES / "papers" / f"{stem}.cards.json")
        quotes = read(FIXTURES / "quotes" / f"{stem}.quotes.json")
        cards.pop("audit_model", None)
        cards["schema_version"] = "3.0"
        cards["quotes"] = quotes["quotes"]
        cards["audited"] = False
        cards["audit"] = None
        return cards

    def write_package_response(self, stem, phase, package):
        destination = self.portable_path(stem, phase)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(package), encoding="utf-8")

    def accept_portable_phase1(self, stem):
        self.run_ingest("pre-phase1")
        self.write_phase1_response(stem)
        return self.run_ingest("pre-phase1")

    def accept_portable_phase2(self, stem):
        self.accept_portable_phase1(stem)
        self.run_ingest("pre-phase2")
        package = self.phase2_package(stem)
        self.write_package_response(stem, 2, package)
        self.run_ingest("pre-phase2")
        return package

    def audited_package(self, package):
        audited = json.loads(json.dumps(package))
        audited["audited"] = True
        audited["audit"] = {
            "audit_date": "2025-02-03",
            "audit_model": "fixture-auditor",
            "extraction_model_reviewed": audited["extraction_model"],
            "results": [
                {"card_id": card["card_id"], "verdict": "pass"}
                for card in audited["cards"]
            ],
        }
        return audited

    def failed_audited_package(self, package):
        audited = self.audited_package(package)
        audited["audit"]["results"][0] = {
            "card_id": audited["cards"][0]["card_id"],
            "verdict": "fail",
            "reason": "The interpretation states material absent from its paired quote.",
        }
        return audited

    def rework_root(self, stem, round_number=1):
        return (
            self.exchange_root / "ingest" / "phase2" / "rework" / stem /
            f"round-{round_number:03d}"
        )

    def test_central_handoff_paths_preserve_the_portable_layout(self):
        record = {"markdown_path": f"markdown/{STEMS[0]}.md"}
        paths = next_paper.portable_paths_for(record, self.input_root, self.output_root)
        handoff = next_paper.phase_handoff_paths(paths, 2, self.exchange_root)

        self.assertEqual(handoff["source"], self.outbox_source_path(STEMS[0], 2))
        self.assertEqual(handoff["context"], self.portable_path(STEMS[0], 2, "outbox"))
        self.assertEqual(handoff["inbox"], self.portable_path(STEMS[0], 2))
        self.assertEqual(handoff["archive"], self.portable_path(STEMS[0], 2, "archive"))
        self.assertEqual(handoff["accepted"], self.accepted_path(STEMS[0], 2))

    def test_removed_legacy_jobs_are_not_accepted(self):
        for job in ("phase1", "phase2", "rebuild"):
            output = self.run_ingest(job, expect_success=False)
            self.assertIn("invalid choice", output)

    def test_portable_phase1_context_requires_script_validation(self):
        stem = STEMS[0]
        output = self.run_ingest("pre-phase1")
        self.assertIn("deterministic validation pending", output)
        context = self.portable_path(stem, 1, "outbox").read_text(encoding="utf-8")
        self.assertIn("Required census schema", context)
        self.assertIn("Reporting rules", context)
        self.assertIn("validate-phase1", context)
        self.assertIn("PHASE 1 COMPLETE — VALIDATION PASS", context)
        self.assertNotIn("fixture-beta", context)
        source_copy = self.outbox_source_path(stem, 1)
        self.assertIn(f"Upload source:  {source_copy}", output)
        self.assertEqual(
            source_copy.read_bytes(),
            (self.input_root / "markdown" / f"{stem}.md").read_bytes(),
        )

    def test_portable_phases_accept_one_file_and_preserve_phase2_for_audit(self):
        stem = STEMS[0]
        phase1_output = self.accept_portable_phase1(stem)
        self.assertIn("PHASE 1 COMPLETE — VALIDATION PASS", phase1_output)
        self.assertTrue(self.accepted_path(stem, 1).is_file())
        for obsolete in ("census", "papers", "quotes", "audit"):
            self.assertFalse((self.output_root / obsolete).exists())
        package = self.accept_portable_phase2(stem)
        accepted_phase2 = read(self.accepted_path(stem, 2))
        self.assertEqual(accepted_phase2, package)
        self.assertFalse(accepted_phase2["audited"])
        self.assertIsNone(accepted_phase2["audit"])

        output = self.run_ingest("pre-phase3")
        self.assertIn("READY FOR PHASE 3 MODEL WORK", output)
        context = self.portable_path(stem, 3, "outbox").read_text(encoding="utf-8")
        self.assertIn("Accepted Phase 2 package", context)
        self.assertNotIn("Reporting rules", context)
        self.assertTrue(self.outbox_source_path(stem, 3).is_file())
        audited = self.audited_package(package)
        self.write_package_response(stem, 3, audited)
        output = self.run_ingest("pre-phase3")
        self.assertIn("PHASE 3 COMPLETE — VALIDATION PASS", output)
        self.assertTrue(read(self.accepted_path(stem, 3))["audited"])

    def test_portable_contexts_require_redundancy_review(self):
        stem = STEMS[0]
        self.accept_portable_phase1(stem)
        self.run_ingest("pre-phase2")
        phase2_context = self.portable_path(stem, 2, "outbox").read_text(encoding="utf-8")
        self.assertIn("Mandatory Phase 2 self-audit — simulate Phase 3", phase2_context)
        self.assertIn("paired quote itself", phase2_context)
        self.assertIn("requires nearby text, a table footnote", phase2_context)
        self.assertIn("rerun the self-audit over the **entire", phase2_context)
        self.assertIn("until every card receives an internal", phase2_context)
        self.assertIn("internal self-audit is not independent Phase 3 audit", phase2_context)
        self.assertIn("Identical quote text alone is not a failure", phase2_context)
        self.assertIn("also audit **metadata fidelity**", phase2_context)
        self.assertIn("missing, incorrect or over-inferred value", phase2_context)
        self.assertIn('"irrespective of blast count" is a review trigger', phase2_context)

        package = self.phase2_package(stem)
        self.write_package_response(stem, 2, package)
        self.run_ingest("pre-phase2")
        self.run_ingest("pre-phase3")
        phase3_context = self.portable_path(stem, 3, "outbox").read_text(encoding="utf-8")
        self.assertIn("Also fail materially redundant carding", phase3_context)
        self.assertIn("Do not fail cards merely because their quote text is identical", phase3_context)
        self.assertIn("also compare the paired quote and interpretation", phase3_context)
        self.assertIn("but `escalates_to` is null or names the wrong category", phase3_context)
        self.assertIn('"irrespective of blast count" is a review trigger', phase3_context)

    def test_phase3_rejects_changes_to_extraction(self):
        stem = STEMS[0]
        package = self.accept_portable_phase2(stem)
        audited = self.audited_package(package)
        audited["cards"][0]["interpretation"] += " Changed."
        self.write_package_response(stem, 3, audited)
        output = self.run_ingest("pre-phase3", expect_success=False)
        self.assertIn("only audited and audit may change", output)
        self.assertTrue(self.portable_path(stem, 3).is_file())
        self.assertFalse(self.accepted_path(stem, 3).exists())

    def test_failed_phase3_audit_prepares_and_accepts_phase2_rework(self):
        stem = STEMS[0]
        package = self.accept_portable_phase2(stem)
        self.run_ingest("pre-phase3")
        failed_audit = self.failed_audited_package(package)
        self.write_package_response(stem, 3, failed_audit)

        output = self.run_ingest("pre-phase3", expect_success=False)
        self.assertIn("failed cards block acceptance", output)
        output = self.run_ingest(
            "pre-phase2-rework", extra=["--id", ALPHA_ID]
        )
        self.assertIn("READY FOR PHASE 2 REWORK MODEL WORK", output)
        self.assertIn("Failed cards:   1", output)
        round_root = self.rework_root(stem)
        context = (
            round_root / "outbox" / f"{stem}.phase2-rework-context.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Superseded accepted Phase 2 package", context)
        self.assertIn("Failed independent Phase 3 audit", context)
        self.assertIn(failed_audit["audit"]["results"][0]["reason"], context)
        self.assertIn("validate-phase2-rework", context)
        self.assertIn("known defects but are not the limit of review", context)
        self.assertIn("Mandatory Phase 2 self-audit — simulate Phase 3", context)
        self.assertIn("rerun the self-audit over the **entire", context)
        self.assertIn("Do not include the internal verdicts", context)
        self.assertIn("also audit **metadata fidelity**", context)
        self.assertIn("missing, incorrect or over-inferred value", context)

        corrected = json.loads(json.dumps(package))
        corrected["extraction_model"] = "fixture-reworker"
        corrected["cards"][0]["interpretation"] = (
            "In the source cohort, GENEA was associated with AML diagnosis; the source "
            "does not state a numeric threshold or an exclusion criterion."
        )
        inbox = round_root / "inbox" / f"{stem}.phase2-rework.json"
        inbox.parent.mkdir(parents=True, exist_ok=True)
        inbox.write_text(json.dumps(corrected), encoding="utf-8")
        output = self.run_ingest(
            "validate-phase2-rework",
            extra=["--id", ALPHA_ID, "--response", str(inbox)],
        )
        self.assertIn("PHASE 2 REWORK RESPONSE VALID", output)

        (self.output_root / "corpus").mkdir(parents=True)
        (self.output_root / "corpus" / "stale.json").write_text("{}", encoding="utf-8")
        output = self.run_ingest(
            "pre-phase2-rework", extra=["--id", ALPHA_ID]
        )
        self.assertIn("PHASE 2 REWORK COMPLETE — VALIDATION PASS", output)
        self.assertEqual(read(self.accepted_path(stem, 2)), corrected)
        self.assertFalse(self.accepted_path(stem, 3).exists())
        self.assertFalse(self.portable_path(stem, 3).exists())
        self.assertFalse((self.output_root / "corpus").exists())
        archive = round_root / "archive"
        self.assertEqual(read(archive / f"{stem}.phase2.superseded.json"), package)
        self.assertEqual(read(archive / f"{stem}.phase3.failed.json"), failed_audit)
        self.assertEqual(read(archive / f"{stem}.phase2-rework.json"), corrected)

        output = self.run_ingest("pre-phase3", extra=["--id", ALPHA_ID])
        self.assertIn("READY FOR PHASE 3 MODEL WORK", output)
        self.write_package_response(stem, 3, self.audited_package(corrected))
        output = self.run_ingest("pre-phase3", extra=["--id", ALPHA_ID])
        self.assertIn("PHASE 3 COMPLETE — VALIDATION PASS", output)

    def test_phase2_rework_rejects_changed_identity_and_invalid_audit(self):
        stem = STEMS[0]
        package = self.accept_portable_phase2(stem)
        changed_audit = self.failed_audited_package(package)
        changed_audit["cards"][0]["interpretation"] += " Changed by auditor."
        self.write_package_response(stem, 3, changed_audit)
        output = self.run_ingest(
            "pre-phase2-rework", expect_success=False,
            extra=["--id", ALPHA_ID],
        )
        self.assertIn("only audited and audit may change", output)

        self.portable_path(stem, 3).unlink()
        self.write_package_response(stem, 3, self.failed_audited_package(package))
        self.run_ingest("pre-phase2-rework", extra=["--id", ALPHA_ID])
        round_root = self.rework_root(stem)
        invalid = json.loads(json.dumps(package))
        invalid["publication_type"] = "other"
        inbox = round_root / "inbox" / f"{stem}.phase2-rework.json"
        inbox.parent.mkdir(parents=True, exist_ok=True)
        inbox.write_text(json.dumps(invalid), encoding="utf-8")
        output = self.run_ingest(
            "pre-phase2-rework", expect_success=False,
            extra=["--id", ALPHA_ID],
        )
        self.assertIn("immutable publication fields: publication_type", output)
        self.assertEqual(read(self.accepted_path(stem, 2)), package)

    def test_phase2_incorporation_is_explicitly_provisional(self):
        stem = STEMS[0]
        self.accept_portable_phase2(stem)
        output = self.run_ingest("incorporate", extra=["--after-phase", "2"])
        self.assertIn("Provisional corpus:   true", output)
        corpus = read(self.output_root / "corpus" / "nel.corpus.json")
        self.assertTrue(corpus["provisional"])
        self.assertFalse(corpus["audited"])
        self.assertTrue(corpus["publications"][0]["source"]["provisional"])

    def test_phase3_incorporation_is_audited_and_not_provisional(self):
        stem = STEMS[0]
        package = self.accept_portable_phase2(stem)
        self.run_ingest("pre-phase3")
        self.write_package_response(stem, 3, self.audited_package(package))
        self.run_ingest("pre-phase3")

        output = self.run_ingest("incorporate", extra=["--after-phase", "3"])
        self.assertIn("Provisional corpus:   false", output)
        corpus = read(self.output_root / "corpus" / "nel.corpus.json")
        self.assertFalse(corpus["provisional"])
        self.assertTrue(corpus["audited"])
        self.assertTrue(corpus["publications"][0]["source"]["audited"])
        self.assertFalse(corpus["publications"][0]["source"]["provisional"])


if __name__ == "__main__":
    unittest.main()