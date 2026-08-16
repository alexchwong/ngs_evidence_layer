#!/usr/bin/env python3
"""Unit tests for the phase-validation compatibility facade."""
import importlib.util
import sys
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
    def test_phase_1_delegates_to_phase1_module(self):
        expected = ([], [], {"phase": 1})
        with mock.patch.object(
            final_validation.phase1, "validate_phase_files", return_value=expected
        ) as validator:
            actual = final_validation.validate_phase_files(
                phase=1, metadata_path=Path("m"), census_path=Path("c")
            )
        self.assertEqual(actual, expected)
        validator.assert_called_once_with(metadata_path=Path("m"), census_path=Path("c"))

    def test_phase_2_delegates_to_phase2_module(self):
        expected = ([], [], {"phase": 2})
        with mock.patch.object(
            final_validation.phase2, "validate_phase_files", return_value=expected
        ) as validator:
            actual = final_validation.validate_phase_files(
                phase=2,
                metadata_path=Path("m"),
                census_path=Path("c"),
                source_path=Path("s"),
                provisional_path=Path("p"),
            )
        self.assertEqual(actual, expected)
        validator.assert_called_once_with(
            metadata_path=Path("m"),
            census_path=Path("c"),
            source_path=Path("s"),
            provisional_path=Path("p"),
            base_final_path=None,
        )

    def test_phase_3_is_owned_by_phase4_entry_validator(self):
        expected = ([], [], {"phase": 3})
        with mock.patch.object(
            final_validation.phase4, "validate_review_files", return_value=expected
        ) as validator:
            actual = final_validation.validate_phase_files(
                phase=3, provisional_path=Path("p"), review_path=Path("r")
            )
        self.assertEqual(actual, expected)
        validator.assert_called_once_with(
            provisional_path=Path("p"), review_path=Path("r")
        )

    def test_phase_4_delegates_to_phase4_module(self):
        expected = ([], [], {"phase": 4})
        with mock.patch.object(
            final_validation.phase4, "validate_phase_files", return_value=expected
        ) as validator:
            actual = final_validation.validate_phase_files(
                phase=4,
                metadata_path=Path("m"),
                census_path=Path("c"),
                source_path=Path("s"),
                provisional_path=Path("p"),
                review_path=Path("r"),
                final_path=Path("f"),
            )
        self.assertEqual(actual, expected)
        validator.assert_called_once_with(
            metadata_path=Path("m"),
            census_path=Path("c"),
            source_path=Path("s"),
            provisional_path=Path("p"),
            review_path=Path("r"),
            final_path=Path("f"),
        )

    def test_cli_accepts_phase_specific_arguments(self):
        cases = (
            (1, ["--phase", "1", "--metadata", "m", "--census", "c"]),
            (
                2,
                [
                    "--phase", "2", "--metadata", "m", "--census", "c",
                    "--source", "s", "--provisional", "p", "--base-final", "b",
                ],
            ),
            (3, ["--phase", "3", "--provisional", "p", "--review", "r"]),
            (
                4,
                [
                    "--phase", "4", "--metadata", "m", "--census", "c",
                    "--source", "s", "--provisional", "p", "--review", "r",
                    "--final", "f",
                ],
            ),
        )
        for phase, argv in cases:
            with self.subTest(phase=phase):
                self.assertEqual(final_validation.parse_args(argv).phase, phase)


if __name__ == "__main__":
    unittest.main()
