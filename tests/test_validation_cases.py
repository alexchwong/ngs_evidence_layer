import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.setup_workflow import setup_workflow
from scripts.workflow_registry import load_registry, load_workflow_metadata
from validation.scripts.package_marking import package_marking_bundle
from validation.scripts.bundled_cases import (
    bundled_modes,
    case_source_path,
    is_validation_mode,
    list_case_ids,
    marking_bundle_filename,
    retrieve_case_input,
    retrieve_marking_criteria,
    write_demo_marking_criteria_after_report,
)

ROOT = Path(__file__).resolve().parents[1]


class BundledCaseRegistryTests(unittest.TestCase):
    def test_expected_public_suites_are_registered(self):
        self.assertEqual(
            set(bundled_modes()),
            {
                "nel-demo",
                "nel-validate",
                "nel-validate-function",
                "nel-validate-brief",
                "nel-validate-dual",
                "nel-validate-dublin",
            },
        )
        self.assertTrue(is_validation_mode("nel-validate"))
        self.assertFalse(is_validation_mode("nel-demo"))

    def test_dual_suite_has_six_standalone_cases(self):
        self.assertEqual(list_case_ids("nel-validate-dual"), ("1", "2", "3", "4", "5", "6"))
        self.assertEqual(case_source_path("nel-validate-dual"), ROOT / "validation" / "validate_dual.md")

    def test_dublin_suite_has_ten_standalone_cases(self):
        self.assertEqual(list_case_ids("nel-validate-dublin"), tuple(str(number) for number in range(1, 11)))
        self.assertEqual(
            case_source_path("nel-validate-dublin"),
            ROOT / "validation" / "validation_dublin.md",
        )

    def test_demo_is_one_file_with_six_cases_and_marking_criteria(self):
        self.assertEqual(list_case_ids("nel-demo"), ("1", "2", "3", "4", "5", "6"))
        self.assertEqual(case_source_path("nel-demo"), ROOT / "validation" / "demo.md")
        for selector in list_case_ids("nel-demo"):
            clinical = retrieve_case_input("nel-demo", selector)
            criteria = retrieve_marking_criteria("nel-demo", selector)
            self.assertTrue(clinical.strip())
            self.assertTrue(criteria.strip())
            self.assertNotIn("Marking criteria", clinical)
            self.assertNotIn("NEL task", clinical)

    def test_all_registered_production_selectors_retrieve_clinical_and_marking_content(self):
        for mode in bundled_modes():
            selectors = list_case_ids(mode)
            self.assertTrue(selectors, mode)
            for selector in selectors:
                with self.subTest(mode=mode, selector=selector):
                    clinical = retrieve_case_input(mode, selector)
                    criteria = retrieve_marking_criteria(mode, selector)
                    self.assertTrue(clinical.strip())
                    self.assertTrue(criteria.strip())
                    self.assertNotIn("## NEL task", clinical)
                    self.assertNotIn("## Marking criteria", clinical)
                    self.assertNotIn("### NEL task", clinical)
                    self.assertNotIn("### Marking criteria", clinical)

    def test_shared_stem_variant_retrieval_preserves_stem(self):
        stem = retrieve_case_input("nel-validate", "1")
        variant = retrieve_case_input("nel-validate", "1A")
        self.assertTrue(variant.startswith(stem))
        self.assertGreater(len(variant), len(stem))

    def test_standalone_suite_rejects_variant_selector(self):
        with self.assertRaises(KeyError):
            retrieve_case_input("nel-validate-brief", "8A")
        with self.assertRaises(KeyError):
            retrieve_case_input("nel-validate-dublin", "1A")

    def test_marking_bundle_names_are_centralised(self):
        self.assertEqual(marking_bundle_filename("nel-validate", "1A"), "nel-validation-1A.zip")
        self.assertEqual(
            marking_bundle_filename("nel-validate-function", "1H"),
            "nel-validation-function-1H.zip",
        )
        self.assertEqual(
            marking_bundle_filename("nel-validate-brief", "8"),
            "nel-validation-brief-8.zip",
        )
        self.assertEqual(
            marking_bundle_filename("nel-validate-dual", "1"),
            "nel-validation-dual-1.zip",
        )
        self.assertEqual(
            marking_bundle_filename("nel-validate-dublin", "1"),
            "nel-validation-dublin-1.zip",
        )
        with self.assertRaises(ValueError):
            marking_bundle_filename("nel-demo", "1")

    def test_dublin_marking_bundle_uses_registered_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report-final.md"
            report.write_text("# Report\n", encoding="utf-8")
            output = package_marking_bundle("nel-validate-dublin", "1", report)
            self.assertEqual(output.name, "nel-validation-dublin-1.zip")
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(
                    archive.namelist(),
                    ["marking-prompt.md", "validation-case.md", "report-final.md"],
                )
                case = archive.read("validation-case.md").decode("utf-8")
                prompt = archive.read("marking-prompt.md").decode("utf-8")
            self.assertIn("FLT3-ITD", case)
            self.assertNotIn("Marking criteria", case)
            self.assertIn("familial platelet disorder", prompt)

    def test_demo_marking_materialisation_requires_completed_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            output = tmp / "demo-expected.md"
            report = tmp / "report-final.md"
            with self.assertRaises(ValueError):
                write_demo_marking_criteria_after_report(1, report_path=report, output_path=output)
            report.write_text("\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                write_demo_marking_criteria_after_report(1, report_path=report, output_path=output)
            report.write_text("# Report\n", encoding="utf-8")
            write_demo_marking_criteria_after_report(1, report_path=report, output_path=output)
            self.assertEqual(output.read_text(encoding="utf-8").strip(), retrieve_marking_criteria("nel-demo", 1))


class WorkflowBundledCaseRegressionTests(unittest.TestCase):
    def _assert_setup_case(self, workflow_id: str, mode: str, *, example=None, case_id=None):
        with tempfile.TemporaryDirectory() as tmp:
            work = setup_workflow(
                workflow=workflow_id,
                mode=mode,
                work_dir=Path(tmp) / "run",
                example=example,
                case_id=case_id,
            )
            cases = list(work.rglob("case.md"))
            self.assertEqual(len(cases), 1, f"{workflow_id} {mode}: {cases}")
            selector = example if mode == "nel-demo" else case_id
            expected = retrieve_case_input(mode, selector).rstrip() + "\n"
            self.assertEqual(cases[0].read_text(encoding="utf-8"), expected)
            self.assertFalse(list(work.rglob("demo-expected.md")), "marking criteria leaked during setup")

    def test_every_workflow_uses_same_demo_and_validation_retrieval(self):
        registry = load_registry()
        for workflow_id, row in registry["workflows"].items():
            if not row.get("enabled", True):
                continue
            metadata = load_workflow_metadata(workflow_id, registry)
            supported = set(metadata.get("supported_modes") or [])
            if "nel-demo" in supported:
                with self.subTest(workflow=workflow_id, mode="nel-demo"):
                    self._assert_setup_case(workflow_id, "nel-demo", example=1)
            validation_examples = {
                "nel-validate": "1A",
                "nel-validate-function": "1H",
                "nel-validate-brief": "8",
                "nel-validate-dual": "1",
                "nel-validate-dublin": "1",
            }
            for mode, selector in validation_examples.items():
                if mode in supported:
                    with self.subTest(workflow=workflow_id, mode=mode):
                        self._assert_setup_case(workflow_id, mode, case_id=selector)

    def test_dual_validation_is_proforma_only(self):
        registry = load_registry()
        for workflow_id, row in registry["workflows"].items():
            if not row.get("enabled", True):
                continue
            supported = set(load_workflow_metadata(workflow_id, registry).get("supported_modes") or [])
            if workflow_id == "proforma-v1":
                self.assertIn("nel-validate-dual", supported)
            else:
                self.assertNotIn("nel-validate-dual", supported, workflow_id)

    def test_dublin_validation_is_supported_by_proforma_and_terraced_v6(self):
        registry = load_registry()
        supporting = set()
        for workflow_id, row in registry["workflows"].items():
            if not row.get("enabled", True):
                continue
            supported = set(load_workflow_metadata(workflow_id, registry).get("supported_modes") or [])
            if "nel-validate-dublin" in supported:
                supporting.add(workflow_id)
        self.assertEqual(supporting, {"proforma-v1", "terraced-v6"})

    def test_workflow_code_and_docs_have_no_bundled_asset_sources_or_legacy_registry_constants(self):
        forbidden = (
            "VALIDATION_CASE_FILES",
            "VALIDATION_MODES",
            "MARKING_PREFIX",
            "DEMO_EXAMPLES",
            "demo_paths",
            "examples/cases",
            "examples/expected",
            "case_summary.md",
            "case_functional.md",
            "validation_brief.md",
            "validate_dual.md",
            "validation_dublin.md",
            "from validation.cases",
            "validation.package_marking",
        )
        offenders = []
        for path in (ROOT / "workflows").rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".md"}:
                continue
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in text:
                    offenders.append(f"{path.relative_to(ROOT)}: {token}")
        self.assertEqual(offenders, [])

    def test_every_runtime_setup_hook_calls_central_case_retrieval(self):
        registry = load_registry()
        missing = []
        for workflow_id, row in registry["workflows"].items():
            if not row.get("enabled", True):
                continue
            metadata = load_workflow_metadata(workflow_id, registry)
            runtime_name = (metadata.get("entrypoints") or {}).get("runtime")
            if not runtime_name:
                continue
            package = metadata["python_package"].replace(".", "/")
            path = ROOT / package / f"{runtime_name}.py"
            text = path.read_text(encoding="utf-8")
            if "nel-demo" in set(metadata.get("supported_modes") or []) and "retrieve_case_input" not in text:
                missing.append(str(path.relative_to(ROOT)))
        self.assertEqual(missing, [])
