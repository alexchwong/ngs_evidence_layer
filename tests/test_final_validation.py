#!/usr/bin/env python3
"""Tests for shared deterministic Phase 4 and confirmation validation."""
import copy
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
FIXTURE = (
    ROOT
    / "tests"
    / "fixtures"
    / "work"
    / "aaaaaaaa-0000-0000-0000-000000000001"
)
sys.path.insert(0, str(SCRIPTS))


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


final_validation = load("nel_final_validation", "final_validation.py")


class FinalValidationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.work = Path(self.tempdir.name) / "paper"
        shutil.copytree(FIXTURE, self.work)

    def tearDown(self):
        self.tempdir.cleanup()

    def paths(self):
        return {
            "metadata_path": self.work / "metadata.json",
            "census_path": self.work / "paper.census.json",
            "source_path": self.work / "paper.md",
            "provisional_path": self.work / "paper.provisional-001.json",
            "review_path": self.work / "paper.review-001.json",
            "final_path": self.work / "paper.final.json",
        }

    def mutate_json(self, name, mutate):
        path = self.work / name
        document = json.loads(path.read_text(encoding="utf-8"))
        mutate(document)
        path.write_text(json.dumps(document), encoding="utf-8")

    def test_valid_fixture_passes_shared_validator_and_cli(self):
        errors, _warnings, report = final_validation.validate_final_files(
            **self.paths()
        )
        self.assertEqual(errors, [])
        self.assertGreater(report["cards"], 0)
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "final_validation.py"),
                "--phase",
                "4",
                "--metadata",
                str(self.work / "metadata.json"),
                "--census",
                str(self.work / "paper.census.json"),
                "--source",
                str(self.work / "paper.md"),
                "--provisional",
                str(self.work / "paper.provisional-001.json"),
                "--review",
                str(self.work / "paper.review-001.json"),
                "--final",
                str(self.work / "paper.final.json"),
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["valid"])


    def test_final_requires_paper_nickname(self):
        self.mutate_json(
            "paper.final.json",
            lambda final: final.pop("paper_nickname", None),
        )
        errors, _warnings, _report = final_validation.validate_final_files(
            **self.paths()
        )
        self.assertIn("final: final package requires paper_nickname", errors)

    def test_paper_nickname_must_be_trimmed_single_line(self):
        self.mutate_json(
            "paper.final.json",
            lambda final: final.update(paper_nickname="  Fixture\nPaper  "),
        )
        errors, _warnings, _report = final_validation.validate_final_files(
            **self.paths()
        )
        self.assertIn(
            "final: paper_nickname must be a trimmed single-line string", errors
        )

    def test_final_audit_model_must_equal_phase3_reviewer(self):
        self.mutate_json(
            "paper.final.json",
            lambda final: final["audit"].update(audit_model="different-model"),
        )
        errors, _warnings, _report = final_validation.validate_final_files(
            **self.paths()
        )
        self.assertIn(
            "final audit_model does not match Phase 3 reviewer_model", errors
        )

    def test_phase2_and_phase3_models_must_differ(self):
        provisional = json.loads(
            (self.work / "paper.provisional-001.json").read_text(encoding="utf-8")
        )
        extraction_model = provisional["extraction_model"]
        self.mutate_json(
            "paper.review-001.json",
            lambda review: review.update(reviewer_model=extraction_model),
        )
        self.mutate_json(
            "paper.final.json",
            lambda final: final["audit"].update(audit_model=extraction_model),
        )
        errors, _warnings, _report = final_validation.validate_final_files(
            **self.paths()
        )
        self.assertTrue(
            any("reviewer model must differ" in error for error in errors), errors
        )

    def test_approved_round_must_match_review_and_provisional(self):
        self.mutate_json(
            "paper.final.json",
            lambda final: final["audit"].update(approved_round=2),
        )
        errors, _warnings, _report = final_validation.validate_final_files(
            **self.paths()
        )
        self.assertIn(
            "final audit approved_round does not match provisional round", errors
        )
        self.assertIn("final audit approved_round does not match review round", errors)

    def test_source_invalid_final_fails(self):
        def mutate(final):
            final["evidence"][0]["fragments"][0]["quote"] = "not in paper.md"

        self.mutate_json("paper.final.json", mutate)
        errors, _warnings, _report = final_validation.validate_final_files(
            **self.paths()
        )
        self.assertTrue(any("not found verbatim" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
