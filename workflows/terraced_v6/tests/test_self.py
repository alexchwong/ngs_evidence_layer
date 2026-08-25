from pathlib import Path
import tempfile
import unittest

from workflows.terraced_v6 import self_runtime as sr


class NativeSelfEvidenceTests(unittest.TestCase):
    def test_audit_selected_cards_but_full_candidate_set_for_zero(self):
        items = [
            {"evidence_id": "E0001", "schema_id": "PX-A", "reason": "r1", "candidate_card_tags": ["[card:111111111111]", "[card:222222222222]"]},
            {"evidence_id": "E0002", "schema_id": "PX-B", "reason": "r2", "candidate_card_tags": ["[card:333333333333]", "[card:444444444444]"]},
        ]
        matches = {"matches": [
            {"evidence_id": "E0001", "card_tags": ["[card:111111111111]"]},
            {"evidence_id": "E0002", "card_tags": []},
        ]}
        targets = sr.audit_targets(items, matches)
        self.assertEqual(targets[0]["selected_card_tags"], ["[card:111111111111]"])
        self.assertEqual(targets[0]["audit_scope"], "resolver_selected")
        self.assertEqual(targets[1]["selected_card_tags"], ["[card:333333333333]", "[card:444444444444]"])
        self.assertEqual(targets[1]["audit_scope"], "zero_card_full_candidate_check")

    def test_compare_crops_only_disagreements(self):
        items = [
            {"evidence_id": "E0001", "schema_id": "PX-A", "reason": "r1", "candidate_card_tags": ["[card:111111111111]", "[card:222222222222]"]},
            {"evidence_id": "E0002", "schema_id": "PX-B", "reason": "r2", "candidate_card_tags": ["[card:333333333333]"]},
        ]
        matches = {"matches": [
            {"evidence_id": "E0001", "card_tags": ["[card:111111111111]", "[card:222222222222]"]},
            {"evidence_id": "E0002", "card_tags": []},
        ]}
        targets = sr.audit_targets(items, matches)
        audits = {"audits": [
            {"evidence_id": "E0001", "card_audits": [
                {"card_tag": "[card:111111111111]", "card_is_element_of_reason": True, "risk": "none", "comments": []},
                {"card_tag": "[card:222222222222]", "card_is_element_of_reason": False, "risk": "none", "comments": ["wrong clinical function"]},
            ]},
            {"evidence_id": "E0002", "card_audits": [
                {"card_tag": "[card:333333333333]", "card_is_element_of_reason": True, "risk": "none", "comments": []},
            ]},
        ]}
        agreed, disputes = sr.compare_evidence(items, matches, audits, targets)
        self.assertEqual([(x["evidence_id"], x["card_tag"]) for x in agreed], [("E0001", "[card:111111111111]")])
        self.assertEqual([x["dispute_type"] for x in disputes], ["resolver_include_auditor_exclude", "resolver_zero_auditor_include"])

    def test_adjudication_requires_exact_cropped_rows(self):
        disputes = [
            {"evidence_id": "E0001", "card_tag": "[card:111111111111]"},
            {"evidence_id": "E0002", "card_tag": "[card:222222222222]"},
        ]
        good = {"adjudications": [
            {"evidence_id": "E0001", "card_tag": "[card:111111111111]", "decision": "exclude", "reason": "not an element"},
            {"evidence_id": "E0002", "card_tag": "[card:222222222222]", "decision": "include", "reason": "directly supports the reason"},
        ]}
        sr.validate_adjudication(good, disputes)
        bad = {"adjudications": list(reversed(good["adjudications"]))}
        with self.assertRaises(ValueError):
            sr.validate_adjudication(bad, disputes)

    def test_shared_contracts_are_existing_v6_contracts(self):
        for stage in ("structure_case", "diagnosis_who5", "diagnosis_icc", "prognosis", "treatment", "biomarker", "germline", "evidence_match", "evidence_audit", "report_write"):
            path = sr.contract_path(stage)
            self.assertTrue(path.is_file(), stage)
            self.assertEqual(path.parent.name, "prompts")
        self.assertEqual(sr.contract_path("diagnosis_who5").name, "diagnosis_who5.md")

    def test_pass_order_marks_only_adjudication_conditional(self):
        self.assertEqual(sr.SELF_PASS_ORDER[:6], ("who1", "icc", "who2", "ptbg", "evidence_resolution", "evidence_audit"))
        self.assertEqual(sr.SELF_PASS_ORDER[-1], "report_synthesis")


if __name__ == "__main__":
    unittest.main()

class NativeSelfDeliveryTests(unittest.TestCase):
    def test_debug_bundle_contains_run_files_but_not_zip_outputs(self):
        import zipfile

        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            (work / "report-final.md").write_text("report\n", encoding="utf-8")
            nested = work / "intermediates" / "001_test"
            nested.mkdir(parents=True)
            (nested / "state.yaml").write_text("x: 1\n", encoding="utf-8")
            (work / "nel-validation-brief-7.zip").write_bytes(b"external")
            out = sr.package_debug_bundle(work)
            self.assertEqual(out.name, "ngs-report-debug.zip")
            with zipfile.ZipFile(out) as zf:
                names = zf.namelist()
            self.assertIn("report-final.md", names)
            self.assertIn("intermediates/001_test/state.yaml", names)
            self.assertNotIn("nel-validation-brief-7.zip", names)
            self.assertNotIn("ngs-report-debug.zip", names)

    def test_final_artifacts_reports_only_existing_dissent_and_marking(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            for name in ("report-final.md", "report-final.json", "ngs-report-debug.zip", "nel-validation-brief-7.zip"):
                (work / name).write_text("x", encoding="utf-8")
            with patch.object(sr.staged, "_load_run_state", return_value={"mode": "nel-validate-brief", "validation_case": "7"}):
                found = sr.final_artifacts(work)
            self.assertEqual(found["REPORT"], work / "report-final.md")
            self.assertEqual(found["MARKING_ZIP"], work / "nel-validation-brief-7.zip")
            self.assertEqual(found["DEBUG_ZIP"], work / "ngs-report-debug.zip")
            self.assertIsNone(found["DISSENT"])

class NativeSelfSetupTests(unittest.TestCase):
    def test_setup_parser_supports_project_and_keeps_it_exclusive_with_work_dir(self):
        from workflows.terraced_v6 import self as self_cli

        parser = self_cli.build_parser()
        args = parser.parse_args(["setup", "--mode", "ngs-report", "--project"])
        self.assertTrue(args.project)
        self.assertIsNone(args.work_dir)
        with self.assertRaises(SystemExit):
            parser.parse_args(["setup", "--mode", "ngs-report", "--project", "--work-dir", "/tmp/x"])

    def test_setup_delegates_work_location_only_from_self(self):
        import contextlib
        from argparse import Namespace
        from unittest.mock import patch
        from workflows.terraced_v6 import self as self_cli

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "case-source.md"
            source.write_text("case\n", encoding="utf-8")
            work = root / "resolved-work"
            work.mkdir()
            captured = {}

            def fake_setup_workflow(**kwargs):
                captured.update(kwargs)
                # Minimal common setup assets expected by layout.
                (work / "case-major-categories.json").write_text("{}\n", encoding="utf-8")
                (work / "ngs-panel-scope.md").write_text("scope\n", encoding="utf-8")
                return work, None, None

            args = Namespace(
                mode="ngs-report", case_file=source, example=None, case_id=None,
                work_dir=None, project=True,
            )
            with patch.object(self_cli, "setup_workflow", side_effect=fake_setup_workflow), \
                 patch.object(self_cli, "write_workflow_state"), \
                 patch.object(self_cli.staged, "_save_run_state"), \
                 patch.object(self_cli.staged, "_cli_logging", return_value=contextlib.nullcontext()):
                self.assertEqual(self_cli.cmd_setup(args), self_cli.EXIT_OK)
            self.assertIsNone(captured["work_dir"])
            self.assertTrue(captured["project"])
