#!/usr/bin/env python3
"""Workflow tests for v0.1.3 folder-as-state ingestion."""
import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
PAPER_ID = "aaaaaaaa-0000-0000-0000-000000000001"
PUBLICATION_KEY = "fixture-2020-fixture-journal-1-1"
STEM = "fixture-alpha--aaaaaaaa"
WORK_FIXTURE = FIXTURES / "work" / PAPER_ID


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_prompts = load("build_prompts")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class FolderStateWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.input_dir = self.root / "input"
        self.corpus = self.input_dir / "fixtures"
        self.work = self.root / "work"
        self.accept = self.root / "accept"
        self.archive = self.root / "archive"
        (self.corpus / "index").mkdir(parents=True)
        (self.corpus / "markdown").mkdir()
        shutil.copy(WORK_FIXTURE / "paper.md", self.corpus / "markdown" / f"{STEM}.md")
        self.source = self.corpus / "markdown" / f"{STEM}.md"
        self.record = {
            "id": PAPER_ID, "markdown_path": f"markdown/{STEM}.md",
            "source_filename": "fixture-alpha.md",
            "sha256": hashlib.sha256(self.source.read_bytes()).hexdigest(),
            "status": "ingested", "citation_source": "operator",
            "citation_resolved_at": "2026-08-02T00:00:00+00:00",
            "citation": {
                "authors": ["Fixture A", "Fixture B"],
                "title": "Fixture Classifier, first edition",
                "journal": "Fixture Journal", "year": 2020, "volume": "1",
                "issue": "1", "pages": "1-10", "doi": "",
            },
            "publication_key": PUBLICATION_KEY,
        }
        self.write_index([self.record])

    def tearDown(self):
        self.tmp.cleanup()

    def write_index(self, records):
        (self.corpus / "index" / "papers.jsonl").write_text(
            "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
        )

    def run_script(self, script, *arguments, success=True):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / script), *map(str, arguments)],
            capture_output=True, text=True,
        )
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def fanout(self):
        return self.run_script(
            "fanout.py", "--corpus", "fixtures", "--input-dir", self.input_dir,
            "--work-dir", self.work, "--created-at", "2026-08-02T00:00:00+00:00",
        )

    def prepare_complete_work(self):
        self.fanout()
        working = self.work / PUBLICATION_KEY
        for name in ("paper.census.json", "paper.provisional-001.json", "paper.final.json"):
            shutil.copy(WORK_FIXTURE / name, working / name)
        return working

    def test_fanout_creates_identity_and_is_idempotent(self):
        output = self.fanout()
        working = self.work / PUBLICATION_KEY
        self.assertIn("Created 1", output)
        self.assertEqual((working / "paper.md").read_bytes(), self.source.read_bytes())
        metadata = read(working / "metadata.json")
        self.assertEqual(metadata["paper_id"], PAPER_ID)
        self.assertEqual(metadata["publication_key"], PUBLICATION_KEY)
        self.assertEqual(metadata["citation_source"], "operator")
        self.assertNotIn("publication_type", metadata)
        first = (working / "metadata.json").read_bytes()
        self.assertIn("left 1 existing", self.fanout())
        self.assertEqual((working / "metadata.json").read_bytes(), first)

    def test_fanout_preflight_prevents_partial_work(self):
        invalid = dict(self.record)
        invalid.update(id="bbbbbbbb-0000-0000-0000-000000000002", markdown_path="markdown/missing--bbbbbbbb.md")
        invalid["citation"] = dict(self.record["citation"], title="Other")
        self.write_index([self.record, invalid])
        output = self.run_script(
            "fanout.py", "--corpus", "fixtures", "--input-dir", self.input_dir,
            "--work-dir", self.work, success=False,
        )
        self.assertIn("indexed Markdown not found", output)
        self.assertFalse((self.work / PUBLICATION_KEY).exists())

    def test_confirm_accepts_approved_round_and_archives(self):
        self.prepare_complete_work()
        output = self.run_script(
            "confirm.py", "--key", PUBLICATION_KEY, "--work-dir", self.work,
            "--accept-dir", self.accept, "--archive-dir", self.archive,
        )
        self.assertIn("CONFIRMED", output)
        self.assertFalse((self.work / PUBLICATION_KEY).exists())
        self.assertTrue((self.archive / PUBLICATION_KEY / "paper.provisional-001.json").is_file())
        accepted = read(self.accept / f"{PUBLICATION_KEY}.final.json")
        self.assertEqual(accepted["acceptance_path"], "confirmed")
        self.assertEqual(accepted["accepted_at_source"], "confirm")
        self.assertTrue(accepted["accepted_at"])

    def test_confirm_accepts_and_archives_zero_card_package(self):
        working = self.prepare_complete_work()
        provisional = read(working / "paper.provisional-001.json")
        provisional.update(
            genes_covered=[], diseases_covered=[], cards=[], evidence=[]
        )
        (working / "paper.provisional-001.json").write_text(
            json.dumps(provisional), encoding="utf-8"
        )

        final = copy.deepcopy(provisional)
        final["publication_type_verified_by_phase3"] = True
        final["audit"] = {
            "audit_date": "2026-08-02",
            "audit_model": "fixture-audit-model",
            "extraction_model_reviewed": provisional["extraction_model"],
            "approved_round": provisional["round"],
            "publication_type_verdict": {
                "verdict": "pass", "verified_by_phase3": True,
            },
            "results": [],
        }
        (working / "paper.final.json").write_text(json.dumps(final), encoding="utf-8")

        output = self.run_script(
            "confirm.py", "--key", PUBLICATION_KEY, "--work-dir", self.work,
            "--accept-dir", self.accept, "--archive-dir", self.archive,
        )
        self.assertIn("CONFIRMED", output)
        self.assertIn("Cards: 0", output)
        accepted = read(self.accept / f"{PUBLICATION_KEY}.final.json")
        self.assertEqual(accepted["final"]["cards"], [])
        self.assertEqual(accepted["final"]["audit"]["results"], [])
        self.assertTrue((self.archive / PUBLICATION_KEY / "paper.final.json").is_file())

    def test_fanout_rejects_pending_and_incomplete_citations(self):
        pending = copy.deepcopy(self.record)
        pending["status"] = "citation-pending"
        pending["parse"] = {"error": "awaiting citation repair"}
        self.write_index([pending])
        output = self.run_script(
            "fanout.py", "--corpus", "fixtures", "--input-dir", self.input_dir,
            "--work-dir", self.work, success=False,
        )
        self.assertIn("awaiting citation repair", output)

        incomplete = copy.deepcopy(self.record)
        incomplete["citation"]["authors"] = []
        self.write_index([incomplete])
        output = self.run_script(
            "fanout.py", "--corpus", "fixtures", "--input-dir", self.input_dir,
            "--work-dir", self.work, success=False,
        )
        self.assertIn("lacks authors, title, or year", output)

    def test_confirm_rejects_extraction_change_without_moving(self):
        working = self.prepare_complete_work()
        final = read(working / "paper.final.json")
        final["cards"][0]["interpretation"] += " Changed by auditor."
        (working / "paper.final.json").write_text(json.dumps(final), encoding="utf-8")
        output = self.run_script(
            "confirm.py", "--key", PUBLICATION_KEY, "--work-dir", self.work,
            "--accept-dir", self.accept, "--archive-dir", self.archive, success=False,
        )
        self.assertIn("only audit may change", output)
        self.assertTrue(working.is_dir())
        self.assertFalse(self.accept.exists())

    def test_incorporate_strips_evidence_and_reports_bad_pair(self):
        self.prepare_complete_work()
        self.run_script(
            "confirm.py", "--key", PUBLICATION_KEY, "--work-dir", self.work,
            "--accept-dir", self.accept, "--archive-dir", self.archive,
        )
        (self.accept / "bad.census.json").write_text("{}", encoding="utf-8")
        output_dir = self.root / "output" / "corpus"
        report = self.root / "output" / "reports" / "build-report.json"
        output = self.run_script(
            "incorporate.py", "--accept-dir", self.accept, "--output-dir", output_dir,
            "--report", report, "--generated-at", "2026-08-02T00:00:00+00:00",
        )
        self.assertIn("Rejected: 1", output)
        corpus_text = (output_dir / "nel.corpus.json").read_text(encoding="utf-8")
        self.assertNotIn('"evidence"', corpus_text)
        self.assertNotIn('"fragments"', corpus_text)
        self.assertNotIn('"quote"', corpus_text)
        self.assertNotIn('"provisional"', corpus_text)
        self.assertIn("bad", read(report)["rejected"])

    def test_generated_prompts_match_and_starve_phase3(self):
        for phase in (1, 2, 3):
            self.assertEqual(
                (ROOT / "prompts" / f"phase{phase}_prompt.md").read_text(encoding="utf-8"),
                build_prompts.render(phase),
            )
        phase3 = build_prompts.render(3)
        self.assertNotIn("agreed_reporting_rules", phase3)
        self.assertNotIn('"$schema"', phase3)
        self.assertNotIn("paper.census.json", phase3)

    def test_review_guidance_contract_is_actionable_and_backward_compatible(self):
        phase2 = build_prompts.render(2)
        phase3 = build_prompts.render(3)

        self.assertIn("older reviews without it remain valid", phase2)
        self.assertIn("Mandatory human adjudication before rework", phase2)
        self.assertIn("affirm Phase 3's suggested action", phase2)
        self.assertIn("every specific disease value must be grounded", phase2)
        self.assertIn("work-up recommendation supports a conditional germline card", phase2)
        self.assertIn("Never construct card IDs from `paper_id`", phase2)
        self.assertIn("mandatory normalization", phase2)

        self.assertIn('"suggested_action"', phase3)
        self.assertIn("narrow_disease_scope", phase3)
        self.assertNotIn("correct_escalates_to", phase3)
        self.assertIn("source-bounded detail", phase3)
        self.assertIn("Pass an explicit work-up recommendation", phase3)
        self.assertIn("fragment reuse alone", phase3)
        self.assertIn('"audit_model"', phase3)
        self.assertIn('"results"', phase3)
        self.assertIn("must not contain `reviewer_model`", phase3)


if __name__ == "__main__":
    unittest.main()