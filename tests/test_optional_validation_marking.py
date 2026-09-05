"""Contract and packaging tests for optional validation marking."""
from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


class OptionalValidationMarkingTests(unittest.TestCase):
    def test_cli_exposes_opt_in_and_manual_mark_commands(self) -> None:
        source = (ROOT / "nel.py").read_text(encoding="utf-8")
        self.assertIn('setup.add_argument("--mark-validation", action="store_true"', source)
        self.assertIn('bsetup.add_argument("--mark-validation", action="store_true"', source)
        self.assertIn('sub.add_parser("mark", help="mark a completed validation run or batch', source)
        self.assertIn('"validation_marking": bool(validation_marking)', source)

    def test_clinical_completion_is_decoupled_when_policy_is_off(self) -> None:
        source = (ROOT / "nel.py").read_text(encoding="utf-8")
        self.assertIn('and _validation_marking_enabled(run)', source)
        self.assertIn('if automatic_marking and marking.get("applicable"):', source)
        self.assertIn('automatic_marking = batch.manifest.get("validation_marking", True) is True', source)

    def test_batch_manual_marking_is_process_isolated(self) -> None:
        source = (ROOT / "nel.py").read_text(encoding="utf-8")
        self.assertIn('subprocess.call([sys.executable, "-u", str(ROOT / "nel.py"), "mark", "--run-id", ref])', source)
        self.assertIn('Separate process per child deliberately prevents batch-to-batch model context leakage.', source)

    def test_browser_extension_has_opt_in_and_separate_mark_action(self) -> None:
        source = (ROOT / "ui" / "assets" / "marking-controls.js").read_text(encoding="utf-8")
        server = (ROOT / "ui" / "marking_server.py").read_text(encoding="utf-8")
        self.assertIn('id="markValidation"', source)
        self.assertIn("body.mark_validation", source)
        self.assertIn("mode === 'nel-validate' || mode.startsWith('nel-validate-')", source)
        self.assertIn("id = 'markBtn'", source)
        self.assertIn("'/api/mark'", source)
        self.assertIn('path == "/api/mark"', server)
        self.assertIn('phase="marking"', server)
        self.assertIn('is_validation_mode(mode)', server)

    def test_browser_extension_blocks_automatic_key_modal_and_restores_frozen_profile(self) -> None:
        source = (ROOT / "ui" / "assets" / "marking-controls.js").read_text(encoding="utf-8")
        self.assertIn('dialog.dataset.nelManualOnly', source)
        self.assertIn("if (!userRequested) return undefined", source)
        self.assertIn('restoreFrozenProfile', source)
        self.assertIn("status.pipeline", source)
        self.assertIn("id = 'providerActionError'", source)
        self.assertIn('function gateProviderActions()', source)
        self.assertIn("/^(Start|Resume)/", source)

    def test_batch_bundle_is_single_isolated_deterministic_deliverable(self) -> None:
        try:
            from validation import case_registry
            from validation.scripts.package_marking import (
                BATCH_MARKING_BUNDLE,
                marking_bundle_filename,
                package_batch_marking_bundle,
            )
        except ImportError as exc:
            self.skipTest(f"full validation registry not present in partial checkout: {exc}")

        mode = "nel-validate-dublin"
        case_ids = case_registry.list_case_ids(mode)[:2]
        self.assertEqual(len(case_ids), 2)
        with tempfile.TemporaryDirectory() as tmp:
            batch = Path(tmp)
            cases = []
            for index, case_id in enumerate(case_ids, start=1):
                directory = f"{index:03d}-{case_id}"
                child = batch / directory
                child.mkdir()
                report = child / "report-final.md"
                report.write_text(f"# Report {case_id}\n", encoding="utf-8")
                obsolete = child / marking_bundle_filename(mode, case_id)
                obsolete.write_bytes(b"obsolete")
                cases.append({"case_id": case_id, "directory": directory, "report_path": report})

            output = package_batch_marking_bundle(mode, cases, batch)
            self.assertEqual(output, batch / BATCH_MARKING_BUNDLE)
            first_bytes = output.read_bytes()
            first_mtime = output.stat().st_mtime_ns
            with zipfile.ZipFile(output) as zf:
                names = zf.namelist()
                self.assertIn("MARKING_INSTRUCTIONS.md", names)
                self.assertIn("F1-F9-SCORING.md", names)
                self.assertIn("dublin-functional-criteria.md", names)
                instructions = zf.read("MARKING_INSTRUCTIONS.md").decode("utf-8")
                self.assertIn("one case directory at a time", instructions)
                self.assertIn("Do **not** compare cases", instructions)
                for item in cases:
                    prefix = item["directory"] + "/"
                    self.assertIn(prefix + "marking-prompt.md", names)
                    self.assertIn(prefix + "validation-case.md", names)
                    self.assertIn(prefix + "report-final.md", names)
                    prompt = zf.read(prefix + "marking-prompt.md").decode("utf-8")
                    self.assertIn("Case isolation rule", prompt)
            for item in cases:
                self.assertFalse((batch / item["directory"] / marking_bundle_filename(mode, item["case_id"])).exists())

            output2 = package_batch_marking_bundle(mode, cases, batch)
            self.assertEqual(output2.read_bytes(), first_bytes)
            self.assertEqual(output2.stat().st_mtime_ns, first_mtime)

    def test_batch_bundle_does_not_delete_child_zip_when_replacement_fails(self) -> None:
        try:
            from validation import case_registry
            from validation.scripts import package_marking as marking
        except ImportError as exc:
            self.skipTest(f"full validation registry not present in partial checkout: {exc}")

        mode = "nel-validate-dublin"
        case_id = case_registry.list_case_ids(mode)[0]
        with tempfile.TemporaryDirectory() as tmp:
            batch = Path(tmp)
            child = batch / f"001-{case_id}"
            child.mkdir()
            report = child / "report-final.md"
            report.write_text("# Report\n", encoding="utf-8")
            obsolete = child / marking.marking_bundle_filename(mode, case_id)
            obsolete.write_bytes(b"keep until replacement succeeds")
            missing_spec = batch / "missing-functional-spec.md"
            with mock.patch.object(marking, "DUBLIN_FUNCTIONAL_SPEC", missing_spec):
                with self.assertRaises(FileNotFoundError):
                    marking.package_batch_marking_bundle(
                        mode,
                        [{"case_id": case_id, "directory": child.name, "report_path": report}],
                        batch,
                    )
            self.assertTrue(obsolete.is_file())
            self.assertFalse((batch / marking.BATCH_MARKING_BUNDLE).exists())


if __name__ == "__main__":
    unittest.main()
