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

    def test_default_structural_attempts_is_ten(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing = Path(tmp_dir) / "missing.json"
            with (
                patch.object(step, "SETTINGS_PATH", missing),
                patch.object(step, "SETTINGS_TEMPLATE_PATH", missing),
            ):
                self.assertEqual(step.load_settings()["structural_attempts"], 10)

    def test_terraced_alias_is_registered_without_changing_default(self):
        registry = load_registry()
        self.assertEqual(normalise_selector(None, registry), "categorical-v1")
        self.assertEqual(normalise_selector("--terraced", registry), "terraced-v1")
        self.assertEqual(normalise_selector("--terraced-v1", registry), "terraced-v1")

    def test_question_profiles_preserve_every_question_once_in_order(self):
        config = runtime.load_questions()
        for domain, data in config["domains"].items():
            expected = [row["id"] for row in data["questions"]]
            for profile in config["execution_profiles"].values():
                flattened = [qid for group in profile["groups"][domain] for qid in group]
                self.assertEqual(flattened, expected)

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
                    (configured_work / "terraced-run.json").read_text(encoding="utf-8")
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
                    (overridden_work / "terraced-run.json").read_text(encoding="utf-8")
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

    def test_case_validation_reports_all_independent_defects(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            work = Path(tmp_dir)
            (work / "case-input.json").write_text(
                json.dumps(
                    {
                        "provisional_cmcs": ["NOT-A-CMC", "NOT-A-CMC"],
                        "provisional_disease": "",
                        "genes": ["tp53", "tp53"],
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
            self.assertIn("case_facts[0].fact_id", message)
            self.assertIn("case_facts[1].fact_id", message)

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

            with (
                patch.object(step, "_profile", return_value=binding),
                patch.object(step.model_client, "complete_messages", side_effect=complete),
                patch.object(step, "load_settings", return_value={"structural_attempts": 10}),
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
            retry = calls[1][-1]["content"]
            self.assertIn("first defect", retry)
            self.assertIn("second defect", retry)
            folders = [path.name for path in (work / step.BUNDLE_DIR).iterdir()]
            self.assertEqual(folders, ["001-test-operation"])
            feedback = work / step.BUNDLE_DIR / folders[0] / "attempt-1.validation.txt"
            self.assertIn("second defect", feedback.read_text(encoding="utf-8"))
            usage = json.loads((work / step.USAGE_FILE).read_text(encoding="utf-8"))
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
                {"sentence_id": "diagnosis-2", "fact_ids": ["diagnosis-2"]},
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
            (work / "report-facts.yaml").write_text("germline: []\n", encoding="utf-8")
            captured_summary_messages = []

            def model_call(_work, *, call_id, messages, output, **_kwargs):
                if call_id.startswith("summary-"):
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
                else:
                    output.write_text("alignments: []\n", encoding="utf-8")
                return "validated"

            with (
                patch.object(step.runtime, "facts_only"),
                patch.object(step.runtime, "prepare_combined_evidence"),
                patch.object(step.runtime, "render_final"),
                patch.object(step, "_citation_alignment_input", return_value="manifest: true\n"),
                patch.object(step, "_model_call", side_effect=model_call),
            ):
                self.assertEqual(step.step_6(work, None), step.EXIT_OK)

            self.assertEqual(len(captured_summary_messages), 2)
            correction = captured_summary_messages[1][1]["content"]
            self.assertIn("germline-1", correction)
            self.assertIn("No germline fact is reportable.", correction)
            self.assertIn("does not support the drafted sentence", correction)

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
            (work / step.USAGE_FILE).write_text(
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
            self.assertIn("Step 4 of 7 — review and align diagnosis evidence", output)
            self.assertIn("Step 4 of 7 — complete", output)
            self.assertIn("prompt 100, completion 20, total 120", output)

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
