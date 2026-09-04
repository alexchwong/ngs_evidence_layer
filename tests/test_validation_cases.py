import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.workflow_registry import load_registry, load_workflow_metadata
from validation import case_registry
from validation.scripts import bundled_cases
from validation.scripts.package_marking import package_marking_bundle

ROOT = Path(__file__).resolve().parents[1]
VALIDATION_ROOT = ROOT / "validation"


CANONICAL_TEMP_SUITE = """---
schema_version: 1
suite: nel-validate-registry-test
title: Registry test suite
---

# Registry test suite

## Case alpha — Test case

### Case summary

Synthetic clinical input that is safe to expose to the report workflow.

### Marking criteria

#### R1 — Diagnosis and classification

- **R1C1.** State the synthetic expected diagnosis.
- **R1C2.** State the synthetic diagnostic limitation.

#### R5 — Possible germline flagging

- **R5C1.** Recommend constitutional confirmation when indicated.
"""


class ValidationCaseRegistryTests(unittest.TestCase):
    def test_all_registered_validation_suites_pass_canonical_parser(self):
        suites = case_registry.discover_suites()
        self.assertTrue(suites)
        for mode, suite in suites.items():
            with self.subTest(mode=mode):
                self.assertEqual(suite.suite, mode)
                self.assertTrue(suite.cases)
                self.assertEqual(case_registry.parse_suite(suite.path), suite)

    def test_registered_cases_separate_clinical_input_from_marking_criteria(self):
        for mode in sorted(case_registry.validation_modes()):
            for selector in case_registry.list_case_ids(mode):
                with self.subTest(mode=mode, selector=selector):
                    clinical = case_registry.retrieve_case_input(mode, selector)
                    criteria = case_registry.retrieve_marking_criteria(mode, selector)
                    self.assertTrue(clinical.strip())
                    self.assertTrue(criteria.strip())
                    self.assertNotIn("Marking criteria", clinical)
                    self.assertNotIn("NEL task", clinical)
                    self.assertNotIn("RnCm", clinical)

    def test_drop_in_markdown_registers_without_python_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "anything.md"
            path.write_text(CANONICAL_TEMP_SUITE, encoding="utf-8")
            suites = case_registry.discover_suites(root)
            self.assertEqual(set(suites), {"nel-validate-registry-test"})
            self.assertEqual(
                case_registry.list_case_ids("nel-validate-registry-test", root),
                ("alpha",),
            )
            self.assertIn(
                "Synthetic clinical input",
                case_registry.retrieve_case_input("nel-validate-registry-test", "alpha", root),
            )
            self.assertIn(
                "R5C1",
                case_registry.retrieve_marking_criteria("nel-validate-registry-test", "alpha", root),
            )

    def test_filename_does_not_define_suite_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "unrelated-filename.md").write_text(CANONICAL_TEMP_SUITE, encoding="utf-8")
            suite = case_registry.suite_spec("nel-validate-registry-test", root)
            self.assertEqual(suite.path.name, "unrelated-filename.md")

    def test_duplicate_suite_ids_fail_registration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one.md").write_text(CANONICAL_TEMP_SUITE, encoding="utf-8")
            (root / "two.md").write_text(CANONICAL_TEMP_SUITE, encoding="utf-8")
            with self.assertRaises(case_registry.RegistryError):
                case_registry.discover_suites(root)

    def test_noncanonical_case_sections_fail(self):
        bad = CANONICAL_TEMP_SUITE.replace(
            "### Marking criteria",
            "### NEL task\n\nHidden evaluator hint.\n\n### Marking criteria",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.md"
            path.write_text(bad, encoding="utf-8")
            with self.assertRaises(case_registry.RegistryError):
                case_registry.parse_suite(path)

    def test_malformed_or_nonsequential_criteria_fail(self):
        bad = CANONICAL_TEMP_SUITE.replace("R1C2", "R1C3")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.md"
            path.write_text(bad, encoding="utf-8")
            with self.assertRaises(case_registry.RegistryError):
                case_registry.parse_suite(path)

    def test_wrong_rubric_heading_fails(self):
        bad = CANONICAL_TEMP_SUITE.replace(
            "#### R1 — Diagnosis and classification",
            "#### R1 — Prognosis",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.md"
            path.write_text(bad, encoding="utf-8")
            with self.assertRaises(case_registry.RegistryError):
                case_registry.parse_suite(path)

    def test_bundled_case_api_is_registry_facade_for_validation(self):
        self.assertEqual(bundled_cases.validation_modes(), case_registry.validation_modes())
        for mode in sorted(case_registry.validation_modes()):
            with self.subTest(mode=mode):
                self.assertEqual(bundled_cases.list_case_ids(mode), case_registry.list_case_ids(mode))
                first = case_registry.list_case_ids(mode)[0]
                self.assertEqual(
                    bundled_cases.retrieve_case_input(mode, first),
                    case_registry.retrieve_case_input(mode, first),
                )
                self.assertEqual(
                    bundled_cases.retrieve_marking_criteria(mode, first),
                    case_registry.retrieve_marking_criteria(mode, first),
                )

    def test_demo_remains_outside_validation_registry(self):
        self.assertIn("nel-demo", bundled_cases.bundled_modes())
        self.assertNotIn("nel-demo", case_registry.validation_modes())
        self.assertFalse(bundled_cases.is_validation_mode("nel-demo"))

    def test_bundle_filename_is_derived_from_suite_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "suite.md").write_text(CANONICAL_TEMP_SUITE, encoding="utf-8")
            self.assertEqual(
                case_registry.marking_bundle_filename(
                    "nel-validate-registry-test", "alpha", root
                ),
                "nel-validation-registry-test-alpha.zip",
            )


class ProformaValidationDiscoveryTests(unittest.TestCase):
    def test_proforma_metadata_expands_registry_validation_modes(self):
        registry = load_registry()
        metadata = load_workflow_metadata("proforma-v1", registry)
        supported = set(metadata.get("supported_modes") or [])
        self.assertTrue(case_registry.validation_modes().issubset(supported))
        self.assertIn("ngs-report", supported)
        self.assertIn("nel-demo", supported)

    def test_proforma_workflow_json_contains_no_named_validation_suites(self):
        text = (ROOT / "workflows" / "proforma_v1" / "workflow.json").read_text(
            encoding="utf-8"
        )
        self.assertIn('"validation_case_registry": true', text)
        self.assertNotIn('"nel-validate-', text)
        self.assertNotIn('"nel-validate"', text)

    def test_real_drop_in_suite_is_visible_through_proforma_metadata(self):
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".md",
            prefix="registry-test-",
            dir=VALIDATION_ROOT,
            encoding="utf-8",
            delete=False,
        ) as handle:
            handle.write(CANONICAL_TEMP_SUITE)
            path = Path(handle.name)
        try:
            # 1. Direct registry discovery
            self.assertIn("nel-validate-registry-test", case_registry.validation_modes())
            # 2. Workflow metadata expansion
            metadata = load_workflow_metadata("proforma-v1")
            self.assertIn("nel-validate-registry-test", metadata["supported_modes"])
            # 3. Compatibility facade
            self.assertIn("nel-validate-registry-test", bundled_cases.validation_modes())
            # 4. Canonical workflow boundary
            from workflows.proforma_v1 import step as proforma_step
            self.assertIn("nel-validate-registry-test", proforma_step.supported_modes())
            # 5. Root CLI boundary
            import nel
            self.assertIn("nel-validate-registry-test", nel._supported_modes())
            # 6. Root parser choices
            parser = nel.build_parser()
            setup_parser = parser._subparsers._group_actions[0].choices["setup"]
            mode_action = next(action for action in setup_parser._actions if action.dest == "mode")
            self.assertIn("nel-validate-registry-test", mode_action.choices)
            # 7. UI discovery
            from ui import server as ui_server
            ui_cases = ui_server.validation_cases()
            self.assertIn("nel-validate-registry-test", ui_cases)
            self.assertEqual(ui_cases["nel-validate-registry-test"], ["alpha"])
            # 8. Batch UI discovery
            from ui import batch_server
            bundled_rows = batch_server._bundled_suites()
            registry_row = next(row for row in bundled_rows if row["mode"] == "nel-validate-registry-test")
            self.assertEqual(registry_row["label"], "nel-validate-registry-test")
            self.assertEqual(registry_row["cases"], ["alpha"])
        finally:
            path.unlink(missing_ok=True)


class MarkingBundleRegistryTests(unittest.TestCase):
    def test_every_validation_suite_can_build_post_report_bundle(self):
        for mode in sorted(case_registry.validation_modes()):
            selector = case_registry.list_case_ids(mode)[0]
            with self.subTest(mode=mode, selector=selector), tempfile.TemporaryDirectory() as tmp:
                report = Path(tmp) / "report-final.md"
                report.write_text("# Report\n", encoding="utf-8")
                output = package_marking_bundle(mode, selector, report)
                with zipfile.ZipFile(output) as archive:
                    self.assertEqual(
                        archive.namelist(),
                        ["marking-prompt.md", "validation-case.md", "report-final.md"],
                    )
                    case = archive.read("validation-case.md").decode("utf-8")
                    prompt = archive.read("marking-prompt.md").decode("utf-8")
                self.assertEqual(case.strip(), case_registry.retrieve_case_input(mode, selector).strip())
                self.assertNotIn("Marking criteria", case)
                self.assertIn(
                    case_registry.retrieve_marking_criteria(mode, selector).strip(),
                    prompt,
                )


if __name__ == "__main__":
    unittest.main()
