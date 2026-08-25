import tempfile
import unittest
from unittest import mock
from pathlib import Path

import yaml

from workflows.terraced_v2 import diagnosis_connector, runtime, step


class TerracedV2ValidationTests(unittest.TestCase):
    def test_case_json_repairs_fence_bom_and_trailing_commas(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case.json"
            path.write_text(
                "\ufeff```json\n"
                '{\n'
                '  "provisional_cmcs": ["AML",],\n'
                '  "provisional_disease": "AML",\n'
                '  "genes": ["NPM1",],\n'
                '  "detected_variants_summary": "NPM1 variant detected",\n'
                '  "case_facts": [{"fact_id": "F1", "kind": "molecular", "value": "NPM1 variant detected",},],\n'
                '}\n'
                "```\n",
                encoding="utf-8",
            )

            self.assertEqual(runtime.validate_case_json(path), "case.json validated")
            repaired = path.read_text(encoding="utf-8")
            self.assertFalse(repaired.startswith("\ufeff"))
            self.assertNotIn("```", repaired)
            self.assertNotIn('",]', repaired)
            self.assertNotIn('",}', repaired)

    def test_yaml_mapping_repairs_enclosing_code_fence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.yaml"
            path.write_text(
                "```yaml\n"
                "facts: []\n"
                "uncertainties: []\n"
                "upstream_issues: []\n"
                "```\n",
                encoding="utf-8",
            )

            self.assertEqual(runtime.validate_domain_state(path), "downstream terrace state validated")
            self.assertNotIn("```", path.read_text(encoding="utf-8"))

    def test_diagnosis_state_reports_multiple_actionable_issues(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.yaml"
            path.write_text(
                yaml.safe_dump(
                    {
                        "provisional_cmcs": ["NOT_A_CMC", "NOT_A_CMC"],
                        "diagnoses": [
                            {
                                "schema_disease": "MDS/AML",
                                "WHO5": {"status": "bad", "diagnosis": None},
                                "ICC": {"status": "established", "diagnosis": None},
                                "materially_different": "yes",
                            }
                        ],
                        "facts": [{"fact": "", "reason": ""}],
                        "uncertainties": "none",
                        "extra": True,
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError) as context:
                runtime.validate_diagnosis_state(path)
            message = str(context.exception)
            for expected in (
                "failed validation with",
                "unexpected field(s): extra",
                "not an allowed CMC",
                "duplicate CMC",
                "MDS/AML",
                "materially_different",
                "WHO5.status",
                "ICC.diagnosis",
                "facts[0].fact",
                "uncertainties",
            ):
                self.assertIn(expected, message)
            self.assertGreaterEqual(message.count("Required fix:"), 9)

    def test_domain_alignment_reports_row_count_and_row_defects(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.yaml"
            aligned = Path(tmp) / "aligned.yaml"
            state.write_text(
                yaml.safe_dump(
                    {
                        "facts": [
                            {"fact": "Fact one.", "reason": "Reason one"},
                            {"fact": "Fact two.", "reason": "Reason two"},
                        ],
                        "uncertainties": [],
                        "upstream_issues": [],
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            aligned.write_text(
                yaml.safe_dump(
                    {
                        "facts": [
                            {"fact": "Changed.", "reason": "Changed", "citation": "[card:ffffffffffff]"}
                        ],
                        "uncertainties": [],
                        "extra": [],
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError) as context:
                runtime.validate_domain_alignment(aligned, state, {"0123456789ab"})
            message = str(context.exception)
            for expected in (
                "unexpected field(s): extra",
                "expected 2 rows, received 1",
                "clinical text changed",
                "clinical reason changed",
                "unpermitted tag(s): ffffffffffff",
            ):
                self.assertIn(expected, message)
            self.assertGreaterEqual(message.count("Required fix:"), 5)

    def test_grounded_report_aggregates_top_level_and_row_count_errors(self):
        immutable = {"facts": [{"fact_id": "diagnosis-summary-1", "fact": "A."}]}
        document = {"facts": [], "extra": True}

        with self.assertRaises(ValueError) as context:
            diagnosis_connector.validate_grounded(
                document,
                immutable,
                case_source_ids={"F1"},
                diagnostic_source_ids={"D1"},
            )
        message = str(context.exception)
        self.assertIn("unexpected field(s): extra", message)
        self.assertIn("expected 1 rows, received 0", message)
        self.assertGreaterEqual(message.count("Required fix:"), 2)


    def test_diagnosis_synthesis_repairs_markdown_hard_break_whitespace_without_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            output = work / "diagnosis" / "report" / "01-synthesis.md"
            output.parent.mkdir(parents=True)
            output.write_text(
                "**Diagnosis**  \n"
                "The findings support consideration of MDS, NOS per WHO5 criteria.  \n"
                "An NPM1 frameshift mutation raises diagnostic uncertainty.  \n"
                "A normal karyotype excludes a defining cytogenetic abnormality.  \n",
                encoding="utf-8",
            )

            message = step._model_call(
                work,
                call_id="diagnosis-report-synthesis",
                role="summarisation",
                messages=[{"role": "user", "content": "Return diagnosis prose."}],
                output=output,
                validator=step._diagnosis_report_synthesis_validator,
                profile="self",
                normalizer=diagnosis_connector.normalize_prose,
            )

            self.assertEqual(message, "diagnosis report synthesis validated")
            self.assertEqual(
                output.read_text(encoding="utf-8"),
                "**Diagnosis**\n"
                "The findings support consideration of MDS, NOS per WHO5 criteria.\n"
                "An NPM1 frameshift mutation raises diagnostic uncertainty.\n"
                "A normal karyotype excludes a defining cytogenetic abnormality.\n",
            )
            operation = work / "state" / "model-steps" / "001-diagnosis-report-synthesis"
            attempt = operation / "attempt_01"
            self.assertTrue((attempt / "OUTPUT_raw.txt").is_file())
            self.assertTrue((attempt / "OUTPUT_normalized.md").is_file())
            repairs = __import__("json").loads((attempt / "OUTPUT_repairs.json").read_text(encoding="utf-8"))
            self.assertTrue(repairs["changed"])
            self.assertIn("trimmed surrounding whitespace from heading", repairs["repairs"])
            self.assertIn("trimmed surrounding whitespace from sentence 1", repairs["repairs"])
            self.assertIn("trimmed surrounding whitespace from sentence 2", repairs["repairs"])
            self.assertIn("trimmed surrounding whitespace from sentence 3", repairs["repairs"])
            validation = __import__("json").loads((attempt / "OUTPUT_validation.json").read_text(encoding="utf-8"))
            self.assertTrue(validation["passed"])
            self.assertFalse((operation / "attempt_02").exists())

    def test_self_retry_keeps_each_attempt_and_exact_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            output = work / "diagnosis" / "report" / "01-synthesis.md"
            output.parent.mkdir(parents=True)
            output.write_text("**Wrong**\nIncomplete\n", encoding="utf-8")
            kwargs = dict(
                work=work,
                call_id="diagnosis-report-synthesis",
                role="summarisation",
                messages=[{"role": "user", "content": "Return diagnosis prose."}],
                output=output,
                validator=step._diagnosis_report_synthesis_validator,
                profile="self",
                normalizer=diagnosis_connector.normalize_prose,
            )

            with self.assertRaises(step.Handoff):
                step._model_call(**kwargs)
            operation = work / "state" / "model-steps" / "001-diagnosis-report-synthesis"
            first = operation / "attempt_01"
            second = operation / "attempt_02"
            self.assertTrue((first / "OUTPUT_validation.json").is_file())
            self.assertTrue(second.is_dir())
            self.assertTrue((second / "INPUT_messages.json").is_file())
            self.assertTrue((second / "INPUT_messages_readable.md").is_file())
            self.assertFalse(output.exists())

            output.write_text("**Diagnosis**\nValid diagnosis sentence.\n", encoding="utf-8")
            self.assertEqual(step._model_call(**kwargs), "diagnosis report synthesis validated")
            self.assertTrue((second / "OUTPUT_raw.txt").is_file())
            self.assertTrue((second / "OUTPUT_validation.json").is_file())
            self.assertTrue((operation / "OUTPUT_accepted.md").is_file())
            self.assertFalse((operation / "attempt_03").exists())

    def test_model_operation_directories_are_numbered_in_execution_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            for call_id in ("first-operation", "second-operation"):
                output = work / f"{call_id}.md"
                output.write_text("ok\n", encoding="utf-8")
                step._model_call(
                    work,
                    call_id=call_id,
                    role="summarisation",
                    messages=[{"role": "user", "content": call_id}],
                    output=output,
                    validator=lambda path: "validated" if path.read_text(encoding="utf-8").strip() == "ok" else (_ for _ in ()).throw(ValueError("bad")),
                    profile="self",
                )
            names = sorted(path.name for path in (work / "state" / "model-steps").iterdir() if path.is_dir())
            self.assertEqual(names, ["001-first-operation", "002-second-operation"])


    def test_direct_provider_retry_keeps_attempt_subdirectories(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            output = work / "diagnosis" / "report" / "01-synthesis.md"
            binding = step.model_registry.Binding(
                profile="test",
                role="summarisation",
                kind="openai-compatible",
                model="test-model",
                base_url="http://example.invalid",
            )
            completions = [
                step.model_client.Completion("**Wrong**\nIncomplete\n"),
                step.model_client.Completion("**Diagnosis**  \nValid diagnosis sentence.  \n"),
            ]
            with mock.patch.object(step, "_profile", return_value=binding), mock.patch.object(
                step.model_client, "complete_messages", side_effect=completions
            ):
                message = step._model_call(
                    work,
                    call_id="diagnosis-report-synthesis",
                    role="summarisation",
                    messages=[{"role": "user", "content": "Return diagnosis prose."}],
                    output=output,
                    validator=step._diagnosis_report_synthesis_validator,
                    profile="test",
                    normalizer=diagnosis_connector.normalize_prose,
                )

            self.assertEqual(message, "diagnosis report synthesis validated")
            operation = work / "state" / "model-steps" / "001-diagnosis-report-synthesis"
            first = __import__("json").loads((operation / "attempt_01" / "OUTPUT_validation.json").read_text(encoding="utf-8"))
            second = __import__("json").loads((operation / "attempt_02" / "OUTPUT_validation.json").read_text(encoding="utf-8"))
            self.assertFalse(first["passed"])
            self.assertTrue(second["passed"])
            self.assertIn("trimmed surrounding whitespace from heading", (operation / "attempt_02" / "OUTPUT_repairs.json").read_text(encoding="utf-8"))
            self.assertTrue((operation / "OUTPUT_accepted.md").is_file())


    def test_model_operation_resume_reuses_existing_sequence_number(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            first_root, _, _ = step._bundle_paths(work, "same-operation")
            second_root, _, _ = step._bundle_paths(work, "same-operation")
            other_root, _, _ = step._bundle_paths(work, "other-operation")
            self.assertEqual(first_root, second_root)
            self.assertEqual(first_root.name, "001-same-operation")
            self.assertEqual(other_root.name, "002-other-operation")

    def test_new_terrace_state_layout_contains_only_accepted_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            path = step._terrace_state_path(work, "diagnosis", 1, ["DX1", "DX2", "DX3"])
            self.assertEqual(path, work / "diagnosis" / "terraces" / "01-DX1-DX3.yaml")
            self.assertNotIn("call_", str(path))

    def test_setup_cli_keeps_runs_default_and_no_project_flag(self):
        parser = step.build_parser()
        setup_parser = next(
            action.choices["setup"]
            for action in parser._actions
            if hasattr(action, "choices") and action.choices and "setup" in action.choices
        )
        option_strings = {option for action in setup_parser._actions for option in action.option_strings}
        self.assertIn("--work-dir", option_strings)
        self.assertNotIn("--project", option_strings)

        source = Path(step.__file__).read_text(encoding="utf-8")
        self.assertIn('root = HERE / "runs"', source)
        self.assertNotIn('REPO_ROOT / "temp"', source)


if __name__ == "__main__":
    unittest.main()
