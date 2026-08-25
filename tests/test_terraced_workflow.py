from pathlib import Path
import argparse
import contextlib
import io
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import yaml

from scripts.workflow_registry import load_registry, normalise_selector
from workflows.terraced_v1 import model_client, model_registry, retrieval, runtime, step


class TerracedWorkflowTests(unittest.TestCase):
    def setUp(self):
        step._EXECUTION_STARTED_AT = None

    def _write_citation_alignment_fixture(self, work: Path) -> str:
        draft = (
            "**Diagnosis**  \n"
            "First diagnosis. Second diagnosis.\n\n"
            "**Prognosis**  \nPrognosis statement.\n\n"
            "**Treatment Implications**  \nTreatment statement.\n\n"
            "**MRD**  \nMRD statement.  \n\n"
            "**Germline**  \nGermline statement.\n"
        )
        (work / "report-draft.md").write_text(draft, encoding="utf-8")
        diagnosis = {
            "provisional_cmcs": ["AML"],
            "diagnoses": [{"schema_disease": "AML", "narrow_diagnosis": "AML"}],
            "facts": [
                {"fact": "First diagnosis.", "reason": "Reason one.", "citation": "[card:a1b2c3]"},
                {"fact": "Second diagnosis part one.", "reason": "Reason two.", "citation": None},
                {"fact": "Second diagnosis part two.", "reason": "Reason three.", "citation": "[card:d4e5f6][card:a1b2c3]"},
            ],
        }
        (work / "category-diagnosis.yaml").write_text(
            yaml.safe_dump(diagnosis, sort_keys=False), encoding="utf-8"
        )
        for domain in ("prognosis", "treatment", "mrd", "germline"):
            citation = None if domain == "mrd" else "[card:a1b2c3]"
            (work / f"category-{domain}.yaml").write_text(
                yaml.safe_dump(
                    [{"fact": f"{domain} fact.", "reason": f"{domain} reason.", "citation": citation}],
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
        return draft

    def _reportability_classifications(self, work: Path, **overrides) -> list[dict]:
        rows = []
        for fact in runtime.accepted_fact_manifest(work):
            row = {
                "fact_id": fact["fact_id"],
                "molecular": True,
                "targets": ["NPM1"],
                "polarity": "not_a_result",
                "negative_consequence": False,
            }
            row.update(overrides.get(fact["fact_id"], {}))
            rows.append(row)
        return rows

    def _write_empty_activated_targets(self, work: Path) -> Path:
        step.layout.ensure_dirs(work)
        path = step.layout.synthesis(work, "activated-targets.yaml")
        path.write_text("schema_version: 1\ndiagnoses: []\nactivated_targets: []\n", encoding="utf-8")
        return path

    def test_default_structural_attempts_is_ten(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing = Path(tmp_dir) / "missing.json"
            with (
                patch.object(step, "SETTINGS_PATH", missing),
                patch.object(step, "SETTINGS_TEMPLATE_PATH", missing),
            ):
                self.assertEqual(step.load_settings()["structural_attempts"], 10)

    def test_terraced_v1_remains_registered(self):
        registry = load_registry()
        self.assertEqual(normalise_selector("--terraced-v1", registry), "terraced-v1")

    def test_question_profiles_preserve_every_question_once_in_order(self):
        config = runtime.load_questions()
        for domain, data in config["domains"].items():
            expected = [row["id"] for row in data["questions"]]
            for profile in config["execution_profiles"].values():
                flattened = [qid for group in profile["groups"][domain] for qid in group]
                self.assertEqual(flattened, expected)

    def test_diagnosis_questions_assign_who5_before_comparing_icc(self):
        config = runtime.load_questions()
        questions = config["domains"]["diagnosis"]["questions"]
        self.assertEqual([row["id"] for row in questions], ["DX1", "DX2", "DX3", "DX4", "DX5", "DX6"])
        self.assertIn("what diagnosis is assigned", questions[2]["question"].lower())
        self.assertIn("under who 5th edition criteria", questions[2]["question"].lower())
        self.assertIn("what diagnosis would be assigned under icc criteria", questions[3]["question"].lower())
        self.assertIn("materially different", questions[3]["question"].lower())
        final_guidance = " ".join(questions[5]["guidance"]).lower()
        self.assertIn("assigned who5 diagnosis", final_guidance)
        self.assertIn("never from the icc comparator", final_guidance)

    def test_answer_prompt_declares_who5_sets_assigned_label(self):
        prompt = (REPO_ROOT / "workflows" / "terraced_v1" / "prompts" / "terrace_answer.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("The assigned diagnostic label is the WHO5 diagnosis.", prompt)
        self.assertIn("use it only as a comparator", prompt)
        self.assertIn("must not set or replace the assigned diagnostic label", prompt)

    def test_all_shipped_provider_profiles_resolve_all_roles(self):
        registry = model_registry.load_registry()
        self.assertLessEqual(
            {"self", "lmstudio", "ollama", "openrouter"},
            set(registry["profiles"]),
        )
        for profile in registry["profiles"]:
            for role in registry["roles"]:
                binding = model_registry.resolve(role, profile, None, registry)
                self.assertTrue(binding.model)

    def test_provider_command_persists_validated_setup_defaults(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings_path = Path(tmp_dir) / "settings.json"
            template_path = Path(tmp_dir) / "settings.json.template"
            template_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "semantic_review_cycles": 2,
                        "structural_attempts": 3,
                        "token_budget": 120000,
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch.object(step, "SETTINGS_PATH", settings_path),
                patch.object(step, "SETTINGS_TEMPLATE_PATH", template_path),
            ):
                self.assertEqual(step.run_provider("openrouter", "balanced"), step.EXIT_OK)
                settings = json.loads(settings_path.read_text(encoding="utf-8"))
                self.assertEqual(settings["model_profile"], "openrouter")
                self.assertEqual(settings["terrace_profile"], "balanced")
                self.assertEqual(step.configured_profiles(), ("openrouter", "balanced"))

    def test_setup_uses_configured_profiles_and_allows_explicit_overrides(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            settings_path = tmp_path / "settings.json"
            settings_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "model_profile": "openrouter",
                        "terrace_profile": "balanced",
                    }
                ),
                encoding="utf-8",
            )

            def args_for(work_dir: Path, **overrides):
                values = {
                    "model_profile": None,
                    "terrace_profile": None,
                    "mode": "ngs-report",
                    "work_dir": work_dir,
                    "project": False,
                    "example": None,
                    "case_id": None,
                    "case_file": None,
                }
                values.update(overrides)
                return argparse.Namespace(**values)

            with (
                patch.object(step, "SETTINGS_PATH", settings_path),
                patch.object(step, "SETTINGS_TEMPLATE_PATH", settings_path),
            ):
                configured_work = tmp_path / "configured"
                step.run_setup(args_for(configured_work))
                configured = json.loads(
                    (configured_work / "state" / "terraced-run.json").read_text(encoding="utf-8")
                )
                self.assertEqual(configured["model_profile"], "openrouter")
                self.assertEqual(configured["terrace_profile"], "balanced")

                overridden_work = tmp_path / "overridden"
                step.run_setup(
                    args_for(
                        overridden_work,
                        model_profile="self",
                        terrace_profile="frontier",
                    )
                )
                overridden = json.loads(
                    (overridden_work / "state" / "terraced-run.json").read_text(encoding="utf-8")
                )
                self.assertEqual(overridden["model_profile"], "self")
                self.assertEqual(overridden["terrace_profile"], "frontier")

    def test_final_diagnosis_rejects_icc_mds_aml(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "dx.yaml"
            path.write_text(
                yaml.safe_dump(
                    {
                        "provisional_cmcs": ["AML"],
                        "diagnoses": [
                            {
                                "schema_disease": "MDS/AML",
                                "narrow_diagnosis": "MDS/AML",
                            }
                        ],
                        "facts": [{"fact": "x", "reason": "y"}],
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "ICC-only"):
                runtime.validate_category_answer(
                    path, "diagnosis", final=True, aligned=False
                )

    def test_diagnosis_prompt_separates_broad_cmcs_from_apl_schema_disease(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            step.layout.ensure_dirs(work)
            fixtures = {
                "case.md": "PML::RARA-positive acute myeloid leukaemia.\n",
                "case-input.json": json.dumps({"provisional_cmcs": ["AML"]}),
                "ngs-panel-scope.md": "Assay scope.\n",
                "case-major-categories.json": json.dumps(["AML", "MDS"]),
                "allowed-schema-diseases.json": json.dumps(["AML", "APL"]),
            }
            for name, content in fixtures.items():
                step.layout.input(work, name, existing=False).write_text(content, encoding="utf-8")
            step.layout.evidence(work, "evidence-diagnosis.md", existing=False).write_text(
                "Diagnostic evidence.\n", encoding="utf-8"
            )

            prompt = (
                (step.PROMPTS / "terrace_answer.md").read_text(encoding="utf-8")
                + "\n\n"
                + step._base_context(work, "diagnosis")
            )
            cmc_heading = prompt.index("## Allowed provisional CMC values")
            schema_heading = prompt.index("## Allowed final schema_disease routing values")
            self.assertLess(cmc_heading, schema_heading)
            self.assertIn('["AML", "MDS"]', prompt[cmc_heading:schema_heading])
            self.assertIn('["AML", "APL"]', prompt[schema_heading:])
            self.assertIn("`schema_disease: APL` is routed under the broad `AML` CMC", prompt)
            self.assertIn("leaves `provisional_cmcs` as `[AML]`", prompt)

            invalid = work / "apl-as-cmc.yaml"
            invalid.write_text(
                yaml.safe_dump(
                    {
                        "provisional_cmcs": ["AML", "APL"],
                        "diagnoses": [
                            {"schema_disease": "APL", "narrow_diagnosis": "APL with PML::RARA"}
                        ],
                        "facts": [{"fact": "APL is diagnosed.", "reason": "PML::RARA is present."}],
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError) as raised:
                runtime.validate_category_answer(invalid, "diagnosis", final=True, aligned=False)
            feedback = str(raised.exception)
            self.assertIn("'APL' is a valid schema_disease but is not an allowed broad CMC", feedback)
            self.assertIn("Allowed provisional CMC values:", feedback)
            self.assertIn("'AML'", feedback)
            self.assertIn("remove 'APL' from provisional_cmcs", feedback)
            self.assertIn("use schema_disease: APL", feedback)
            self.assertIn("retain provisional_cmcs: [AML]", feedback)

            generic = yaml.safe_load(invalid.read_text(encoding="utf-8"))
            generic["provisional_cmcs"] = ["NOT-A-CMC"]
            invalid.write_text(yaml.safe_dump(generic, sort_keys=False), encoding="utf-8")
            with self.assertRaises(ValueError) as raised:
                runtime.validate_category_answer(invalid, "diagnosis", final=True, aligned=False)
            feedback = str(raised.exception)
            self.assertIn("'NOT-A-CMC' is not an allowed broad CMC", feedback)
            self.assertIn("Allowed provisional CMC values:", feedback)
            self.assertIn("replace it with one exact value", feedback)
            self.assertNotIn("APL routes under", feedback)

    def test_case_validation_reports_all_independent_defects(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            (work / "case-input.json").write_text(
                json.dumps(
                    {
                        "provisional_cmcs": ["NOT-A-CMC", "NOT-A-CMC"],
                        "provisional_disease": "",
                        "genes": ["tp53", "tp53"],
                        "detected_variants_summary": "two lines\nwithout a full stop",
                        "case_facts": [{"fact_id": ""}, {}],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError) as raised:
                runtime.validate_case_input(work)
            message = str(raised.exception)
            self.assertIn("genes[0]", message)
            self.assertIn("uppercase gene symbol", message)
            self.assertIn("duplicate CMC", message)
            self.assertIn("not an allowed CMC", message)
            self.assertIn("provisional_disease", message)
            self.assertIn("non-empty string", message)
            self.assertIn("detected_variants_summary", message)
            self.assertIn("exactly one physical line", message)
            self.assertIn("case_facts[0].fact_id", message)
            self.assertIn("case_facts[1].fact_id", message)

    def test_case_validation_requires_one_line_detected_variant_summary(self):
        valid_case = {
            "provisional_cmcs": ["AML"],
            "provisional_disease": "AML",
            "genes": ["NPM1"],
            "detected_variants_summary": "NGS detected NPM1 p.(Trp288CysfsTer12) at 41% VAF.",
            "case_facts": [{"fact_id": "F1"}],
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            path = work / "case-input.json"
            path.write_text(json.dumps(valid_case), encoding="utf-8")
            self.assertEqual(runtime.validate_case_input(work), "case-input.json validated")

            for invalid in (None, "", "NGS detected NPM1\nand FLT3.", "NGS detected NPM1"):
                case = dict(valid_case)
                if invalid is None:
                    case.pop("detected_variants_summary")
                else:
                    case["detected_variants_summary"] = invalid
                path.write_text(json.dumps(case), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "detected_variants_summary"):
                    runtime.validate_case_input(work)

            for canonical in (
                "No pathogenic variants were detected on NGS.",
                "No NGS result was supplied.",
            ):
                case = dict(valid_case, genes=[], detected_variants_summary=canonical)
                path.write_text(json.dumps(case), encoding="utf-8")
                self.assertEqual(runtime.validate_case_input(work), "case-input.json validated")

    def test_final_render_prepends_exact_detected_variant_summary_without_duplication(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            step.layout.ensure_dirs(work)
            summary = "NGS detected NPM1 p.(Trp288CysfsTer12) at 41% VAF."
            (work / "case-input.json").write_text(
                json.dumps(
                    {
                        "provisional_cmcs": ["AML"],
                        "provisional_disease": "AML",
                        "genes": ["NPM1"],
                        "detected_variants_summary": summary,
                        "case_facts": [{"fact_id": "F1"}],
                    }
                ),
                encoding="utf-8",
            )
            step.layout.synthesis(work, "report-cited.md", existing=False).write_text(
                "**Diagnosis**\nFixture diagnosis. (no citation required)\n",
                encoding="utf-8",
            )
            step.layout.evidence(work, "evidence.md", existing=False).write_text(
                "# Evidence\n",
                encoding="utf-8",
            )
            step.layout.evidence(work, "card-tags.json", existing=False).write_text(
                "{}\n",
                encoding="utf-8",
            )
            rendered_body = "**Diagnosis**  \nAML with mutated NPM1 [1].\n\n## References\n\n1. Fixture.\n"
            with (
                patch.object(runtime, "validate_cited_report"),
                patch.object(runtime.report_citations, "render", return_value=rendered_body),
            ):
                first = runtime.render_final(work).read_text(encoding="utf-8")
                second = runtime.render_final(work).read_text(encoding="utf-8")

            expected = summary + "\n\n" + rendered_body
            self.assertEqual(first, expected)
            self.assertEqual(second, expected)
            self.assertEqual(second.count(summary), 1)
            self.assertNotIn(summary + " [", second)

    def test_model_retry_receives_all_errors_and_records_usage(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            output = work / "artifact.txt"
            binding = model_registry.Binding(
                role="answer",
                profile="test",
                kind="openai-compatible",
                model="test-model",
                base_url="http://test",
            )
            calls = []

            def complete(_binding, messages):
                calls.append(messages)
                content = "bad" if len(calls) == 1 else "good"
                return model_client.Completion(
                    content,
                    {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
                )

            def validate(path):
                if path.read_text(encoding="utf-8").strip() == "bad":
                    raise ValueError("artifact failed validation with 2 issue(s):\n1. first defect\n2. second defect")
                return "validated"

            stderr = io.StringIO()
            with (
                patch.object(step, "_profile", return_value=binding),
                patch.object(step.model_client, "complete_messages", side_effect=complete),
                patch.object(step, "load_settings", return_value={"structural_attempts": 10}),
                contextlib.redirect_stderr(stderr),
            ):
                step._model_call(
                    work,
                    call_id="test-operation",
                    role="answer",
                    messages=[{"role": "user", "content": "make it"}],
                    output=output,
                    validator=validate,
                    profile=None,
                )

            self.assertEqual(len(calls), 2)
            status = stderr.getvalue()
            self.assertIn("test-operation: answering", status)
            self.assertIn("test-operation: retry 1/9", status)
            self.assertNotIn("model attempt", status)
            retry = calls[1][-1]["content"]
            self.assertIn("first defect", retry)
            self.assertIn("second defect", retry)
            folders = [path.name for path in (work / step.BUNDLE_DIR).iterdir()]
            self.assertEqual(folders, ["001-test-operation"])
            feedback = work / step.BUNDLE_DIR / folders[0] / "attempt-1.validation.txt"
            self.assertIn("second defect", feedback.read_text(encoding="utf-8"))
            usage = json.loads(step.layout.state(work, step.USAGE_FILE).read_text(encoding="utf-8"))
            self.assertEqual(len(usage["calls"]), 2)
            self.assertEqual(sum(row["usage"]["total_tokens"] for row in usage["calls"]), 24)

    def test_summary_downstream_manifest_failure_retries_with_exact_format_feedback(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            output = work / "report-draft.md"
            binding = model_registry.Binding(
                role="summarisation",
                profile="test",
                kind="openai-compatible",
                model="test-model",
                base_url="http://test",
            )
            calls = []

            def complete(_binding, messages):
                calls.append(messages)
                content = (
                    "# Clinical Interpretative Report\n\nUnheaded diagnosis.\n"
                    if len(calls) == 1
                    else "**Diagnosis**\n\nCorrectly headed diagnosis.\n"
                )
                return model_client.Completion(content, None)

            with (
                patch.object(step, "_profile", return_value=binding),
                patch.object(step.model_client, "complete_messages", side_effect=complete),
                patch.object(step, "load_settings", return_value={"structural_attempts": 10}),
            ):
                step._model_call(
                    work,
                    call_id="summary-1",
                    role="summarisation",
                    messages=[{"role": "user", "content": "summarise"}],
                    output=output,
                    validator=step._summary_validator,
                    profile=None,
                )

            self.assertEqual(len(calls), 2)
            retry = calls[1][-1]["content"]
            self.assertIn("no supported domain heading", retry)
            self.assertIn("**Diagnosis**", retry)
            bundle = work / step.BUNDLE_DIR / "001-summary-1"
            self.assertIn("no supported domain heading", (bundle / "attempt-1.validation.txt").read_text())
            self.assertTrue((bundle / "validated.txt").is_file())
            self.assertEqual(output.read_text(), "**Diagnosis**\n\nCorrectly headed diagnosis.\n")

    def test_final_alignment_deterministic_assembly_failure_does_not_retry_model(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            self._write_citation_alignment_fixture(work)
            output = work / "report-citation-alignment.yaml"
            rows = [
                {"sentence_id": "diagnosis-1", "fact_ids": ["diagnosis-1"]},
                {"sentence_id": "diagnosis-2", "fact_ids": ["diagnosis-2", "diagnosis-3"]},
                {"sentence_id": "prognosis-1", "fact_ids": ["prognosis-1"]},
                {"sentence_id": "treatment-1", "fact_ids": ["treatment-1"]},
                {"sentence_id": "mrd-1", "fact_ids": ["mrd-1"]},
                {"sentence_id": "germline-1", "fact_ids": ["germline-1"]},
            ]
            completion = yaml.safe_dump({"alignments": rows}, sort_keys=False)
            binding = model_registry.Binding(
                role="final_citation_alignment",
                profile="test",
                kind="openai-compatible",
                model="test-model",
                base_url="http://test",
            )
            calls = []

            def complete(_binding, messages):
                calls.append(messages)
                return model_client.Completion(completion, None)

            with (
                patch.object(step, "_profile", return_value=binding),
                patch.object(step.model_client, "complete_messages", side_effect=complete),
                patch.object(step, "load_settings", return_value={"structural_attempts": 10}),
                patch.object(
                    step.runtime,
                    "validate_cited_report",
                    side_effect=ValueError("assembled cited report has invalid disposition"),
                ),
            ):
                with self.assertRaisesRegex(step.StepFailure, "not repairable by changing the alignment model output"):
                    step._model_call(
                        work,
                        call_id="final-citations-1",
                        role="final_citation_alignment",
                        messages=[{"role": "user", "content": "align"}],
                        output=output,
                        validator=lambda path: step._final_alignment_validator(work, path),
                        profile=None,
                    )

            self.assertEqual(len(calls), 1)
            self.assertFalse((work / "report-cited.md").exists())

    def test_unmatched_sentence_details_are_fed_to_next_summary_cycle(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            self._write_citation_alignment_fixture(work)
            (work / "case.md").write_text("Fixture case.\n", encoding="utf-8")
            (work / "case-input.json").write_text('{"genes": []}\n', encoding="utf-8")
            (work / "allowed-schema-diseases.json").write_text(
                json.dumps({"allowed_schema_diseases": ["AML"]}) + "\n", encoding="utf-8"
            )
            captured_summary_messages = []

            def model_call(_work, *, call_id, messages, output, **_kwargs):
                if call_id == "target-activation":
                    output.write_text("direct_targets: []\nstem_diagnoses: []\n", encoding="utf-8")
                elif call_id == "reportability":
                    rows = self._reportability_classifications(_work)
                    for row in rows:
                        if row["fact_id"] != "germline-1":
                            row.update(
                                molecular=False,
                                targets=[],
                                polarity="not_a_result",
                                negative_consequence=False,
                            )
                    output.write_text(
                        yaml.safe_dump({"classifications": rows}, sort_keys=False),
                        encoding="utf-8",
                    )
                elif call_id.startswith("summary-"):
                    captured_summary_messages.append(messages)
                    output.write_text("**Germline**\n\nNo germline fact is reportable.\n", encoding="utf-8")
                elif call_id == "final-citations-1":
                    output.write_text(
                        "unmatched_sentences:\n"
                        "  - sentence_id: germline-1\n"
                        "    sentence: No germline fact is reportable.\n"
                        "    reason: The accepted fact does not support the drafted sentence strongly enough.\n",
                        encoding="utf-8",
                    )
                elif call_id == "final-citations-2":
                    output.write_text(
                        "alignments:\n  - sentence_id: germline-1\n    fact_ids: [germline-1]\n",
                        encoding="utf-8",
                    )
                else:
                    raise AssertionError(call_id)
                return "validated"

            def activation_retrieval(_work, _diagnoses):
                path = step.layout.evidence(_work, "evidence-reportability-activation.json")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('{"retrieved": []}\n', encoding="utf-8")
                return path

            with (
                patch.object(step.runtime, "prepare_combined_evidence"),
                patch.object(step.runtime, "render_final"),
                patch.object(step.retrieval, "reportability_activation", side_effect=activation_retrieval),
                patch.object(step, "_model_call", side_effect=model_call),
            ):
                self.assertEqual(step.step_6(work, None), step.EXIT_OK)

            self.assertEqual(len(captured_summary_messages), 2)
            correction = captured_summary_messages[1][1]["content"]
            self.assertIn("germline-1", correction)
            self.assertIn("No germline fact is reportable.", correction)
            self.assertIn("does not support the drafted sentence", correction)


    def test_reportability_split_quarantines_by_id_without_mutating_categories(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            self._write_citation_alignment_fixture(work)
            step.layout.ensure_dirs(work)
            original = (work / "category-diagnosis.yaml").read_bytes()

            retained_path, quarantine_path = runtime.apply_reportability_review(
                work, {"diagnosis-2", "mrd-1"}
            )

            retained = yaml.safe_load(retained_path.read_text(encoding="utf-8"))
            quarantined = yaml.safe_load(quarantine_path.read_text(encoding="utf-8"))
            self.assertEqual(
                [row["fact"] for row in retained["diagnosis"]],
                ["First diagnosis.", "Second diagnosis part two."],
            )
            self.assertEqual(quarantined["diagnosis"][0]["fact_id"], "diagnosis-2")
            self.assertEqual(quarantined["diagnosis"][0]["reason"], "Reason two.")
            self.assertIsNone(quarantined["diagnosis"][0]["citation"])
            self.assertEqual(quarantined["mrd"][0]["fact_id"], "mrd-1")
            self.assertEqual((work / "category-diagnosis.yaml").read_bytes(), original)

    def test_reportability_classification_requires_every_supplied_fact(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            self._write_citation_alignment_fixture(work)
            classification = work / "classification.yaml"
            rows = self._reportability_classifications(work)
            rows = [row for row in rows if row["fact_id"] != "mrd-1"]
            classification.write_text(
                yaml.safe_dump({"classifications": rows}, sort_keys=False),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError) as raised:
                step._reportability_classification_validator(work, classification)

            message = str(raised.exception)
            self.assertIn("mrd-1", message)
            self.assertIn("every supplied fact", message)

    def test_reportability_classification_rejects_unknown_and_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            self._write_citation_alignment_fixture(work)
            classification = work / "classification.yaml"
            rows = self._reportability_classifications(work)
            unknown = dict(rows[0])
            unknown["fact_id"] = "unknown-1"
            rows.extend([dict(rows[0]), unknown])
            classification.write_text(
                yaml.safe_dump({"classifications": rows}, sort_keys=False),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError) as raised:
                step._reportability_classification_validator(work, classification)

            message = str(raised.exception)
            self.assertIn("duplicate fact_id", message)
            self.assertIn("unknown-1", message)

    def test_reportability_classification_rejects_unknown_polarity(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            self._write_citation_alignment_fixture(work)
            classification = work / "classification.yaml"
            rows = self._reportability_classifications(
                work, **{"mrd-1": {"polarity": "negative"}}
            )
            classification.write_text(
                yaml.safe_dump({"classifications": rows}, sort_keys=False),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError) as raised:
                step._reportability_classification_validator(work, classification)

            message = str(raised.exception)
            self.assertIn("negative", message)
            for polarity in step.REPORTABILITY_POLARITIES:
                self.assertIn(polarity, message)

    def test_reportability_classification_requires_manifest_order(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            self._write_citation_alignment_fixture(work)
            classification = work / "classification.yaml"
            rows = list(reversed(self._reportability_classifications(work)))
            classification.write_text(
                yaml.safe_dump({"classifications": rows}, sort_keys=False), encoding="utf-8"
            )
            with self.assertRaises(ValueError) as raised:
                step._reportability_classification_validator(work, classification)
            self.assertIn("accepted-manifest order", str(raised.exception))

    def test_reportability_review_applies_nonmolecular_and_unactivated_negative_rules(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            self._write_citation_alignment_fixture(work)
            activated = self._write_empty_activated_targets(work)
            classification = step.layout.synthesis(work, "reportability-classification.yaml")
            rows = self._reportability_classifications(
                work,
                **{
                    "diagnosis-2": {
                        "molecular": False,
                        "targets": [],
                        "polarity": "not_a_result",
                        "negative_consequence": False,
                    },
                    "prognosis-1": {
                        "targets": ["TP53"],
                        "polarity": "not_detected",
                        "negative_consequence": True,
                    },
                },
            )
            classification.write_text(
                yaml.safe_dump({"classifications": rows}, sort_keys=False), encoding="utf-8"
            )

            review = step._derive_reportability_review(work, classification, activated)
            self.assertEqual(
                yaml.safe_load(review.read_text(encoding="utf-8"))["quarantine_fact_ids"],
                ["diagnosis-2", "prognosis-1"],
            )
            decisions = yaml.safe_load(
                step.layout.synthesis(work, "reportability-decisions.yaml").read_text(encoding="utf-8")
            )["decisions"]
            by_id = {row["fact_id"]: row for row in decisions}
            self.assertEqual(by_id["diagnosis-2"]["rule"], "R01_NON_MOLECULAR")
            self.assertEqual(by_id["prognosis-1"]["rule"], "R02_UNACTIVATED_NEGATIVE")

    def test_activated_negative_is_retained(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            self._write_citation_alignment_fixture(work)
            step.layout.ensure_dirs(work)
            activated = step.layout.synthesis(work, "activated-targets.yaml")
            activated.write_text(
                yaml.safe_dump(
                    {
                        "schema_version": 1,
                        "diagnoses": [],
                        "activated_targets": [
                            {
                                "target": "TP53",
                                "activated": True,
                                "bases": [
                                    {
                                        "source": "clinical_context_model",
                                        "basis": "explicitly_mentioned_in_stem",
                                    }
                                ],
                            }
                        ],
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            classification = step.layout.synthesis(work, "reportability-classification.yaml")
            rows = self._reportability_classifications(
                work,
                **{
                    "prognosis-1": {
                        "targets": ["TP53"],
                        "polarity": "not_detected",
                        "negative_consequence": True,
                    }
                },
            )
            classification.write_text(
                yaml.safe_dump({"classifications": rows}, sort_keys=False), encoding="utf-8"
            )
            review = step._derive_reportability_review(work, classification, activated)
            self.assertNotIn(
                "prognosis-1",
                yaml.safe_load(review.read_text(encoding="utf-8"))["quarantine_fact_ids"],
            )
            decisions = yaml.safe_load(
                step.layout.synthesis(work, "reportability-decisions.yaml").read_text(encoding="utf-8")
            )["decisions"]
            by_id = {row["fact_id"]: row for row in decisions}
            self.assertEqual(by_id["prognosis-1"]["rule"], "R10_ACTIVATED_NEGATIVE")

    def test_direct_positive_is_quarantined_only_when_result_summary_represents_target(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            self._write_citation_alignment_fixture(work)
            step.layout.ensure_dirs(work)
            (work / "case-input.json").write_text(
                json.dumps({"genes": ["NPM1"], "detected_variants_summary": "NPM1 variant detected."}) + "\n",
                encoding="utf-8",
            )
            activated = self._write_empty_activated_targets(work)
            classification = step.layout.synthesis(work, "reportability-classification.yaml")
            rows = self._reportability_classifications(
                work,
                **{
                    "diagnosis-1": {"targets": ["NPM1"], "polarity": "detected"},
                    "diagnosis-2": {"targets": ["PML::RARA"], "polarity": "detected"},
                },
            )
            classification.write_text(
                yaml.safe_dump({"classifications": rows}, sort_keys=False), encoding="utf-8"
            )
            review = step._derive_reportability_review(work, classification, activated)
            quarantine = yaml.safe_load(review.read_text(encoding="utf-8"))["quarantine_fact_ids"]
            self.assertIn("diagnosis-1", quarantine)
            self.assertNotIn("diagnosis-2", quarantine)
            decisions = yaml.safe_load(
                step.layout.synthesis(work, "reportability-decisions.yaml").read_text(encoding="utf-8")
            )["decisions"]
            by_id = {row["fact_id"]: row for row in decisions}
            self.assertEqual(by_id["diagnosis-1"]["rule"], "R04_REDUNDANT_BARE_POSITIVE_RESULT")
            self.assertEqual(by_id["diagnosis-2"]["rule"], "R13_DIRECT_POSITIVE_NOT_IN_RESULT_SUMMARY")

    def test_negative_consequence_policy_is_domain_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            self._write_citation_alignment_fixture(work)
            (work / "terraced-config.yaml").write_text(
                (REPO_ROOT / "workflows" / "terraced_v1" / "questions.yaml.template").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            activated = self._write_empty_activated_targets(work)
            classification = step.layout.synthesis(work, "reportability-classification.yaml")
            rows = self._reportability_classifications(
                work,
                **{
                    "treatment-1": {"negative_consequence": True},
                    "mrd-1": {"negative_consequence": True},
                },
            )
            classification.write_text(
                yaml.safe_dump({"classifications": rows}, sort_keys=False), encoding="utf-8"
            )
            review = step._derive_reportability_review(work, classification, activated)
            quarantine = yaml.safe_load(review.read_text(encoding="utf-8"))["quarantine_fact_ids"]
            self.assertNotIn("treatment-1", quarantine)
            self.assertIn("mrd-1", quarantine)

    def test_quarantine_artifact_repeats_classification_activation_and_rule(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            self._write_citation_alignment_fixture(work)
            activated = self._write_empty_activated_targets(work)
            classification = step.layout.synthesis(work, "reportability-classification.yaml")
            rows = self._reportability_classifications(
                work,
                **{
                    "prognosis-1": {
                        "targets": ["TP53"],
                        "polarity": "not_detected",
                        "negative_consequence": True,
                    }
                },
            )
            classification.write_text(
                yaml.safe_dump({"classifications": rows}, sort_keys=False), encoding="utf-8"
            )
            step._derive_reportability_review(work, classification, activated)
            _, quarantine_path = runtime.apply_reportability_review(
                work, step._quarantine_fact_ids(work)
            )
            quarantined = yaml.safe_load(quarantine_path.read_text(encoding="utf-8"))
            row = quarantined["prognosis"][0]
            self.assertEqual(row["classification"]["targets"], ["TP53"])
            self.assertFalse(row["activation"][0]["activated"])
            self.assertEqual(row["decision"]["rule"], "R02_UNACTIVATED_NEGATIVE")
            self.assertIn("independently activated", row["decision"]["rationale"])

    def test_target_activation_derivation_unions_case_and_diagnosis_card_targets(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            self._write_citation_alignment_fixture(work)
            step.layout.ensure_dirs(work)
            (work / "case-input.json").write_text('{"genes": ["NPM1"]}\n', encoding="utf-8")
            (work / "allowed-schema-diseases.json").write_text(
                json.dumps({"allowed_schema_diseases": ["AML", "APL"]}) + "\n", encoding="utf-8"
            )
            activation = step.layout.synthesis(work, "activation-context.yaml")
            activation.write_text(
                "direct_targets:\n"
                "  - target: TP53\n"
                "    bases: [explicitly_mentioned_in_stem]\n"
                "stem_diagnoses:\n"
                "  - schema_disease: APL\n",
                encoding="utf-8",
            )
            evidence = step.layout.evidence(work, "evidence-reportability-activation.json")
            evidence.write_text(
                json.dumps(
                    {
                        "retrieved": [
                            {
                                "card_id": "fixture-C0001",
                                "matched_schema_diseases": ["APL"],
                                "genes": ["PML", "RARA"],
                                "interpretation": "APL is defined by PML::RARA in this fixture.",
                            }
                        ]
                    }
                ) + "\n",
                encoding="utf-8",
            )
            output = step._derive_activated_targets(work, activation, evidence)
            doc = yaml.safe_load(output.read_text(encoding="utf-8"))
            targets = {row["target"] for row in doc["activated_targets"]}
            self.assertLessEqual({"TP53", "NPM1", "PML::RARA"}, targets)
            self.assertNotIn("PML", targets)
            self.assertNotIn("RARA", targets)
            diagnoses = {row["schema_disease"]: row["sources"] for row in doc["diagnoses"]}
            self.assertIn("accepted_diagnostic_answer", diagnoses["AML"])
            self.assertIn("explicitly_raised_in_stem", diagnoses["APL"])

    def test_target_activation_diagnostic_context_excludes_accepted_report_facts(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            self._write_citation_alignment_fixture(work)
            diagnosis_path = step.layout.category(work, "category-diagnosis.yaml")
            diagnosis = yaml.safe_load(diagnosis_path.read_text(encoding="utf-8"))
            diagnosis["diagnoses"] = [
                {"schema_disease": "AML", "narrow_diagnosis": "AML with mutated NPM1"}
            ]
            diagnosis["facts"].append(
                {
                    "fact": "No TP53 mutation is detected, excluding AML with mutated TP53.",
                    "reason": "TP53 is absent.",
                    "citation": None,
                }
            )
            diagnosis_path.write_text(
                yaml.safe_dump(diagnosis, sort_keys=False), encoding="utf-8"
            )

            context = step._accepted_diagnosis_activation_context(work)

            self.assertEqual(
                yaml.safe_load(context),
                {
                    "diagnoses": [
                        {
                            "schema_disease": "AML",
                            "narrow_diagnosis": "AML with mutated NPM1",
                        }
                    ]
                },
            )
            self.assertNotIn("TP53", context)
            self.assertNotIn("facts", context)

    def test_diagnosis_card_activation_does_not_activate_every_broad_aml_criterion(self):
        evidence = [
            {
                "card_id": "fixture-npm1",
                "matched_schema_diseases": ["AML"],
                "genes": ["NPM1"],
                "interpretation": "AML with NPM1 mutation is a defining genetic subtype.",
            },
            {
                "card_id": "fixture-tp53",
                "matched_schema_diseases": ["AML"],
                "genes": ["TP53"],
                "interpretation": "AML with mutated TP53 is separately classified in this fixture.",
            },
        ]
        self.assertEqual(step._diagnosis_card_activation_targets(evidence, "AML", ["AML"]), [])
        selected = step._diagnosis_card_activation_targets(
            evidence, "AML", ["AML with mutated NPM1"]
        )
        self.assertEqual([row[0] for row in selected], ["NPM1"])

    def test_diagnosis_card_fusion_partner_does_not_activate_partner_gene_independently(self):
        card = {
            "genes": ["NPM1", "RARA"],
            "interpretation": "A RARA rearrangement involving NPM1 is diagnostic in this fixture.",
        }
        self.assertEqual(step._diagnostic_targets_from_card(card), ["NPM1::RARA"])

    def test_retained_fact_coverage_failure_is_sent_back_to_synthesis(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            self._write_citation_alignment_fixture(work)
            alignment = work / "alignment.yaml"
            rows = [
                {"sentence_id": "diagnosis-1", "fact_ids": ["diagnosis-1"]},
                {"sentence_id": "diagnosis-2", "fact_ids": ["diagnosis-2"]},
                {"sentence_id": "prognosis-1", "fact_ids": ["prognosis-1"]},
                {"sentence_id": "treatment-1", "fact_ids": ["treatment-1"]},
                {"sentence_id": "mrd-1", "fact_ids": ["mrd-1"]},
                {"sentence_id": "germline-1", "fact_ids": ["germline-1"]},
            ]
            alignment.write_text(
                yaml.safe_dump({"alignments": rows}, sort_keys=False), encoding="utf-8"
            )
            feedback = step._unmatched_summary_feedback(work, alignment)
            self.assertIn("diagnosis-3", feedback)
            self.assertIn("omitted retained accepted fact", feedback)

    def test_empty_germline_category_produces_no_germline_heading(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            (work / "category-germline.yaml").write_text("[]\n", encoding="utf-8")
            draft = work / "report-draft.md"
            draft.write_text("**Diagnosis**\n\nFixture diagnosis.\n", encoding="utf-8")

            self.assertEqual(step._summary_validator(draft), "uncited report draft validated")
            self.assertNotIn("**Germline**", draft.read_text(encoding="utf-8"))

    def test_answer_prompt_requires_empty_germline_list_when_no_concern(self):
        prompt = (REPO_ROOT / "workflows" / "terraced_v1" / "prompts" / "terrace_answer.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("For germline specifically, return exactly `[]`", prompt)
        self.assertIn("Do not return a fact stating that no germline concern exists", prompt)

    def test_negative_safety_role_is_removed(self):
        registry = model_registry.load_registry()
        self.assertNotIn("negative_safety_review", registry["roles"])
        self.assertIn("target_activation", registry["roles"])
        self.assertFalse((REPO_ROOT / "workflows" / "terraced_v1" / "prompts" / "negative_safety_review.md").exists())


    def test_case_and_diagnosis_validation_handle_unhashable_cmcs_as_repairable_errors(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            (work / "case-input.json").write_text(
                json.dumps(
                    {
                        "provisional_cmcs": [{"bad": "shape"}],
                        "provisional_disease": "AML",
                        "genes": ["NPM1"],
                        "case_facts": [{"fact_id": "F1"}],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError) as raised:
                runtime.validate_case_input(work)
            self.assertIn("provisional_cmcs[0]", str(raised.exception))
            self.assertIn("Required fix", str(raised.exception))

            diagnosis = work / "dx.yaml"
            diagnosis.write_text(
                yaml.safe_dump(
                    {
                        "provisional_cmcs": [{"bad": "shape"}],
                        "diagnoses": [{"schema_disease": "AML", "narrow_diagnosis": "AML"}],
                        "facts": [{"fact": "x", "reason": "y"}],
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError) as raised:
                runtime.validate_category_answer(diagnosis, "diagnosis", final=True, aligned=False)
            self.assertIn("provisional_cmcs[0]", str(raised.exception))
            self.assertNotIn("unhashable", str(raised.exception))

    def test_semantic_review_rejects_blank_issue_with_actionable_feedback(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "review.json"
            path.write_text('{"pass": false, "issues": [""]}\n', encoding="utf-8")
            with self.assertRaises(ValueError) as raised:
                runtime.validate_review(path)
            message = str(raised.exception)
            self.assertIn("issues[0]", message)
            self.assertIn("non-empty actionable", message)
            self.assertIn("Required fix", message)

    def test_summary_validator_aggregates_preamble_duplicate_heading_markdown_and_trailing_text(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "report-draft.md"
            path.write_text(
                "Preamble. [card:a1b2c3]\n\n"
                "**Diagnosis**\n\nFirst diagnosis.\n\n"
                "**Diagnosis**\n\nSecond diagnosis without stop\n\n"
                "## Prognosis\n\nPrognosis statement.\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError) as raised:
                step._summary_validator(path)
            message = str(raised.exception)
            self.assertIn("runtime card-tag syntax", message)
            self.assertIn("text appears before the first domain heading", message)
            self.assertIn("duplicate supported heading", message)
            self.assertIn("does not end in a full stop", message)
            self.assertIn("Markdown '#' headings are not supported", message)
            self.assertGreaterEqual(message.count("Required fix"), 5)

    def test_unmatched_sentence_rows_must_match_supplied_manifest_exactly(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            self._write_citation_alignment_fixture(work)
            path = work / "report-citation-alignment.yaml"
            path.write_text(
                yaml.safe_dump(
                    {
                        "unmatched_sentences": [
                            {
                                "sentence_id": "fake-99",
                                "sentence": "Invented sentence.",
                                "reason": "Unsupported.",
                            },
                            {
                                "sentence_id": "diagnosis-1",
                                "sentence": "Wrong diagnosis text.",
                                "reason": "Changed wording.",
                            },
                        ]
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError) as raised:
                step._unmatched_summary_feedback(work, path)
            message = str(raised.exception)
            self.assertIn("fake-99", message)
            self.assertIn("not a supplied report sentence ID", message)
            self.assertIn("does not exactly match supplied 'diagnosis-1'", message)
            self.assertIn("Expected 'First diagnosis.'", message)

    def test_final_alignment_reports_multiple_independent_repairs_in_one_pass(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            self._write_citation_alignment_fixture(work)
            path = work / "report-citation-alignment.yaml"
            path.write_text(
                yaml.safe_dump(
                    {
                        "alignments": [
                            {"sentence_id": 123, "fact_ids": []},
                            {"sentence_id": "diagnosis-2", "fact_ids": ["prognosis-1", "bogus", "bogus"]},
                            {"sentence_id": "diagnosis-2", "fact_ids": ["diagnosis-2"]},
                        ]
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError) as raised:
                step._load_sentence_fact_alignment(work, path)
            message = str(raised.exception)
            self.assertIn("set sentence_id to 'diagnosis-1'", message)
            self.assertIn("list is empty", message)
            self.assertIn("duplicate fact_id 'bogus'", message)
            self.assertIn("cross-domain fact", message)
            self.assertIn("not a supplied fact_id", message)
            self.assertIn("duplicate sentence_id", message)
            self.assertIn("missing sentence_id", message)
            self.assertGreaterEqual(message.count("Required fix"), 7)

    def test_bundle_folders_sort_chronologically_and_resume(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            first = step._bundle_paths(work, "later-name")[0]
            second = step._bundle_paths(work, "alpha-name")[0]
            resumed = step._bundle_paths(work, "later-name")[0]
            self.assertEqual(first.name, "001-later-name")
            self.assertEqual(second.name, "002-alpha-name")
            self.assertEqual(resumed, first)

    def test_step_status_and_token_summary_are_concise(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            step.layout.state(work, step.USAGE_FILE, existing=False).parent.mkdir(parents=True, exist_ok=True)
            step.layout.state(work, step.USAGE_FILE, existing=False).write_text(
                json.dumps(
                    {
                        "calls": [
                            {
                                "usage": {
                                    "prompt_tokens": 100,
                                    "completion_tokens": 20,
                                    "total_tokens": 120,
                                }
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            stderr = io.StringIO()
            with (
                patch.object(step, "_require_work", return_value={"workflow_id": step.WORKFLOW_ID}),
                patch.object(step, "step_4", return_value=step.EXIT_OK),
                contextlib.redirect_stderr(stderr),
            ):
                self.assertEqual(step.run_step("4", work, None), step.EXIT_OK)
                step._print_usage(work)
            output = stderr.getvalue()
            self.assertRegex(output, r"\[ \d{4} \] - Step 4 of 7 — review and align diagnosis evidence")
            self.assertRegex(output, r"\[ \d{4} \] - Step 4 of 7 — complete")
            self.assertIn("prompt 100, completion 20, total 120", output)

    def test_cli_log_masks_retrieve_and_render_only_from_terminal(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            terminal_out = io.StringIO()
            terminal_err = io.StringIO()
            with contextlib.redirect_stdout(terminal_out), contextlib.redirect_stderr(terminal_err):
                with step._cli_logging(work):
                    print("VISIBLE-STDOUT")
                    print("VISIBLE-STDERR", file=sys.stderr)
                    print("[retrieve] hidden retrieval detail", file=sys.stderr)
                    print("[terraced render] hidden render detail", file=sys.stderr)
            self.assertIn("VISIBLE-STDOUT", terminal_out.getvalue())
            self.assertIn("VISIBLE-STDERR", terminal_err.getvalue())
            self.assertNotIn("hidden retrieval detail", terminal_err.getvalue())
            self.assertNotIn("hidden render detail", terminal_err.getvalue())
            log = (work / "workflow.log").read_text(encoding="utf-8")
            self.assertIn("VISIBLE-STDOUT", log)
            self.assertIn("VISIBLE-STDERR", log)
            self.assertIn("[retrieve] hidden retrieval detail", log)
            self.assertIn("[terraced render] hidden render detail", log)

    def test_elapsed_status_uses_current_execution_start(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            state_path = step.layout.state(work, "terraced-run.json", existing=False)
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps({"started_at": 63.0}), encoding="utf-8")
            stderr = io.StringIO()
            step._EXECUTION_STARTED_AT = 95.0
            with patch.object(step.time, "time", return_value=100.0), contextlib.redirect_stderr(stderr):
                step._status(work, "hello")
            self.assertEqual(stderr.getvalue(), "[ 0005 ] - hello\n")

    def test_elapsed_status_initializes_at_zero_without_execution_start(self):
        stderr = io.StringIO()
        step._EXECUTION_STARTED_AT = None
        with patch.object(step.time, "time", return_value=100.0), contextlib.redirect_stderr(stderr):
            step._status(Path("unused"), "hello")
        self.assertEqual(stderr.getvalue(), "[ 0000 ] - hello\n")

    def test_setup_keeps_new_project_root_clean(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            work = tmp_path / "work"
            case_file = tmp_path / "case.md"
            case_file.write_text("Test case.\n", encoding="utf-8")
            args = argparse.Namespace(
                model_profile="self", terrace_profile="frontier", mode="ngs-report",
                work_dir=work, project=False, example=None, case_id=None, case_file=case_file,
            )
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(step.run_setup(args), step.EXIT_OK)
            self.assertEqual(
                {path.name for path in work.iterdir()},
                {"workflow.json", "workflow.log", "input", "evidence", "categories", "synthesis", "state"},
            )
            self.assertTrue((work / "input" / "case-source.md").is_file())
            self.assertTrue((work / "input" / "ngs-panel-scope.md").is_file())
            self.assertTrue((work / "state" / "terraced-run.json").is_file())

    def test_layout_reads_existing_legacy_flat_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            legacy = work / "case-input.json"
            legacy.write_text("{}\n", encoding="utf-8")
            self.assertEqual(step.layout.input(work, "case-input.json"), legacy)
            self.assertEqual(
                step.layout.input(work, "new-input.json"),
                work / "input" / "new-input.json",
            )

    def test_narrow_retrieval_does_not_inherit_parent_disease_treatment_cards(self):
        self.assertEqual(
            retrieval._disease_matches({"diseases": ["APL"]}, ["APL"], "treatment"),
            ["APL"],
        )
        self.assertEqual(
            retrieval._disease_matches({"diseases": ["AML"]}, ["APL"], "treatment"),
            [],
        )
        self.assertEqual(
            retrieval._disease_matches({"diseases": ["CML"]}, ["CML"], "treatment"),
            ["CML"],
        )
        self.assertEqual(
            retrieval._disease_matches({"diseases": ["MPN"]}, ["CML"], "treatment"),
            [],
        )

    def test_dual_pathology_routes_each_schema_disease_independently(self):
        card = {"diseases": ["CML", "MPN"]}
        self.assertEqual(
            retrieval._disease_matches(card, ["CML", "MPN"], "prognosis"),
            ["CML", "MPN"],
        )

    def test_alignment_allows_null_citation_and_preserves_fact_reason(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source = tmp_path / "answer-prognosis.yaml"
            aligned = tmp_path / "category-prognosis.yaml"
            evidence = tmp_path / "evidence-prognosis.md"
            source.write_text(
                '- fact: "TET2 has no established prognostic assignment in this context."\n'
                '  reason: "No applicable prognostic role is identified in the supplied evidence."\n',
                encoding="utf-8",
            )
            aligned.write_text(
                '- fact: "TET2 has no established prognostic assignment in this context."\n'
                '  reason: "No applicable prognostic role is identified in the supplied evidence."\n'
                "  citation: null\n",
                encoding="utf-8",
            )
            evidence.write_text("# Evidence\n\nNo cards.\n", encoding="utf-8")
            self.assertIn(
                "validated",
                runtime.validate_alignment(source, aligned, "prognosis", evidence),
            )

    def test_evidence_alignment_reports_all_independent_repairs_in_one_pass(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            source = work / "answer-prognosis.yaml"
            aligned = work / "category-prognosis.yaml"
            evidence = work / "evidence-prognosis.md"
            source.write_text(
                '- fact: "Original fact."\n'
                '  reason: "Original reason."\n',
                encoding="utf-8",
            )
            aligned.write_text(
                '- fact: "Changed fact."\n'
                '  reason: "Changed reason."\n'
                '  citation: "[card:abcdef]"\n',
                encoding="utf-8",
            )
            evidence.write_text("# Evidence\n\n[card:123456]\n", encoding="utf-8")
            with self.assertRaises(ValueError) as raised:
                runtime.validate_alignment(source, aligned, "prognosis", evidence)
            message = str(raised.exception)
            self.assertIn("changed the accepted fact text", message)
            self.assertIn("changed the accepted reason text", message)
            self.assertIn("not present in permitted evidence", message)
            self.assertGreaterEqual(message.count("Required fix"), 3)

    def test_structured_citation_alignment_preserves_exact_draft_prose_and_layout(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            draft = self._write_citation_alignment_fixture(work)
            alignment = work / "report-citation-alignment.yaml"
            alignment.write_text(
                yaml.safe_dump(
                    {
                        "alignments": [
                            {"sentence_id": "diagnosis-1", "fact_ids": ["diagnosis-1"]},
                            {"sentence_id": "diagnosis-2", "fact_ids": ["diagnosis-2", "diagnosis-3"]},
                            {"sentence_id": "prognosis-1", "fact_ids": ["prognosis-1"]},
                            {"sentence_id": "treatment-1", "fact_ids": ["treatment-1"]},
                            {"sentence_id": "mrd-1", "fact_ids": ["mrd-1"]},
                            {"sentence_id": "germline-1", "fact_ids": ["germline-1"]},
                        ]
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            cited = step._assemble_cited_report(work, alignment).read_text(encoding="utf-8")

            self.assertEqual(step._plain_from_cited(cited), draft)
            self.assertIn(
                "First diagnosis. [card:a1b2c3] Second diagnosis. [card:d4e5f6][card:a1b2c3]",
                cited,
            )
            self.assertIn("MRD statement. (no citation required)  \n", cited)

    def test_structured_citation_alignment_rejects_missing_reordered_and_cross_domain_ids(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            self._write_citation_alignment_fixture(work)
            alignment = work / "report-citation-alignment.yaml"
            alignment.write_text(
                "alignments:\n"
                "  - sentence_id: diagnosis-2\n"
                "    fact_ids: [prognosis-1]\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "sentence IDs are not exactly once in report order"):
                step._load_sentence_fact_alignment(work, alignment)

            rows = [
                {"sentence_id": "diagnosis-1", "fact_ids": ["prognosis-1"]},
                {"sentence_id": "diagnosis-2", "fact_ids": ["diagnosis-2"]},
                {"sentence_id": "prognosis-1", "fact_ids": ["prognosis-1"]},
                {"sentence_id": "treatment-1", "fact_ids": ["treatment-1"]},
                {"sentence_id": "mrd-1", "fact_ids": ["mrd-1"]},
                {"sentence_id": "germline-1", "fact_ids": ["germline-1"]},
            ]
            alignment.write_text(
                yaml.safe_dump({"alignments": rows}, sort_keys=False), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "cross-domain fact"):
                step._load_sentence_fact_alignment(work, alignment)


if __name__ == "__main__":
    unittest.main()
