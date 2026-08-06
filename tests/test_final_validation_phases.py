#!/usr/bin/env python3
"""Unit tests for phase-scoped deterministic validation."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

SPEC = importlib.util.spec_from_file_location(
    "nel_phase_final_validation", SCRIPTS / "final_validation.py"
)
final_validation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(final_validation)


class PhaseValidationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()

    def write(self, name, text="{}"):
        path = self.tmp_path / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_phase_1_only_validates_metadata_and_census(self):
        calls = []

        def unexpected_package_validator(*_args, **_kwargs):
            self.fail("package validator called")

        with (
            mock.patch.object(
                final_validation.validation,
                "read_json",
                side_effect=lambda path, label: {"entries": []},
            ),
            mock.patch.object(
                final_validation.validation,
                "validate_metadata",
                side_effect=lambda document: calls.append("metadata") or [],
            ),
            mock.patch.object(
                final_validation.validation,
                "validate_census",
                side_effect=lambda document, metadata: calls.append("census") or [],
            ),
            mock.patch.object(
                final_validation.validation,
                "validate_package",
                side_effect=unexpected_package_validator,
            ),
        ):
            errors, warnings, report = final_validation.validate_phase_files(
                phase=1,
                metadata_path=self.write("metadata.json"),
                census_path=self.write("paper.census.json"),
            )

        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertEqual(calls, ["metadata", "census"])
        self.assertEqual(report, {"phase": 1, "census_entries": 0})

    def test_phase_2_passes_paper_text_to_package_validator(self):
        seen = {}

        def validate_package(package, metadata, census, source_text, require_final):
            seen.update(source_text=source_text, require_final=require_final)
            return ["bad quote"], [], {"cards": 1}

        with (
            mock.patch.object(
                final_validation.validation,
                "read_json",
                return_value={},
            ),
            mock.patch.object(
                final_validation.validation,
                "validate_package",
                side_effect=validate_package,
            ),
        ):
            errors, _warnings, report = final_validation.validate_phase_files(
                phase=2,
                metadata_path=self.write("metadata.json"),
                census_path=self.write("paper.census.json"),
                source_path=self.write("paper.md", "verbatim source"),
                provisional_path=self.write("paper.provisional-001.json"),
            )

        self.assertEqual(
            seen, {"source_text": "verbatim source", "require_final": False}
        )
        self.assertEqual(errors, ["provisional: bad quote"])
        self.assertEqual(report["cards"], 1)

    def test_phase_3_only_validates_review(self):
        documents = iter(
            (
                {"cards": [{"card_id": "C1"}]},
                {"card_results": [{"card_id": "C1"}]},
            )
        )

        def unexpected_package_validator(*_args, **_kwargs):
            self.fail("package validator called")

        with (
            mock.patch.object(
                final_validation.validation,
                "read_json",
                side_effect=lambda path, label: next(documents),
            ),
            mock.patch.object(
                final_validation.validation,
                "validate_review",
                return_value=["lineage"],
            ),
            mock.patch.object(
                final_validation.validation,
                "validate_package",
                side_effect=unexpected_package_validator,
            ),
        ):
            errors, warnings, report = final_validation.validate_phase_files(
                phase=3,
                provisional_path=self.write("paper.provisional-001.json"),
                review_path=self.write("paper.review-001.json"),
            )

        self.assertEqual(errors, ["review: lineage"])
        self.assertEqual(warnings, [])
        self.assertEqual(report["cards"], 1)
        self.assertEqual(report["review_results"], 1)

    def test_phase_4_does_not_revalidate_census_provisional_or_review(self):
        documents = {
            "metadata": {},
            "census": {"entries": []},
            "approved provisional package": {
                "round": 1,
                "extraction_model": "phase2",
            },
            "Phase 3 review": {"round": 1, "reviewer_model": "phase3"},
            "final package": {
                "audit": {
                    "approved_round": 1,
                    "audit_model": "phase3",
                    "extraction_model_reviewed": "phase2",
                }
            },
        }
        calls = []

        def unexpected_census_validator(*_args, **_kwargs):
            self.fail("census validator called")

        def unexpected_review_validator(*_args, **_kwargs):
            self.fail("review validator called")

        def validate_package(package, metadata, census, source_text, require_final):
            calls.append(require_final)
            return [], [], {"cards": 0, "ratio": None}

        with (
            mock.patch.object(
                final_validation.validation,
                "read_json",
                side_effect=lambda path, label: documents[label],
            ),
            mock.patch.object(
                final_validation.validation,
                "validate_census",
                side_effect=unexpected_census_validator,
            ),
            mock.patch.object(
                final_validation.validation,
                "validate_review",
                side_effect=unexpected_review_validator,
            ),
            mock.patch.object(
                final_validation.validation,
                "validate_final_against_provisional",
                return_value=[],
            ),
            mock.patch.object(
                final_validation.validation,
                "validate_package",
                side_effect=validate_package,
            ),
        ):
            errors, _warnings, _report = final_validation.validate_phase_files(
                phase=4,
                metadata_path=self.write("metadata.json"),
                census_path=self.write("paper.census.json"),
                source_path=self.write("paper.md"),
                provisional_path=self.write("paper.provisional-001.json"),
                review_path=self.write("paper.review-001.json"),
                final_path=self.write("paper.final.json"),
            )

        self.assertEqual(errors, [])
        self.assertEqual(calls, [True])

    def test_cli_accepts_phase_specific_arguments(self):
        cases = (
            (1, ["--phase", "1", "--metadata", "m", "--census", "c"]),
            (
                2,
                [
                    "--phase",
                    "2",
                    "--metadata",
                    "m",
                    "--census",
                    "c",
                    "--source",
                    "s",
                    "--provisional",
                    "p",
                ],
            ),
            (3, ["--phase", "3", "--provisional", "p", "--review", "r"]),
            (
                4,
                [
                    "--phase",
                    "4",
                    "--metadata",
                    "m",
                    "--census",
                    "c",
                    "--source",
                    "s",
                    "--provisional",
                    "p",
                    "--review",
                    "r",
                    "--final",
                    "f",
                ],
            ),
        )
        for phase, argv in cases:
            with self.subTest(phase=phase):
                self.assertEqual(final_validation.parse_args(argv).phase, phase)


if __name__ == "__main__":
    unittest.main()
