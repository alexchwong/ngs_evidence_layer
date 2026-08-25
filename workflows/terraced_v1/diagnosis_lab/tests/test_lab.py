from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from workflows.terraced_v1.diagnosis_lab import connector

HERE = Path(__file__).resolve().parents[1]


def _load_run_module():
    path = HERE / "run.py"
    spec = importlib.util.spec_from_file_location("diagnosis_lab_run", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _paired_diagnosis():
    return {
        "schema_disease": "MDS",
        "WHO5": {"status": "not_established", "diagnosis": "MDS with SF3B1 mutation"},
        "ICC": {"status": "indeterminate", "diagnosis": "MDS-SF3B1"},
        "materially_different": True,
    }


class DiagnosisLabTests(unittest.TestCase):
    def test_profiles_group_only_terrace_questions_and_runtime_appends_final(self):
        run = _load_run_module()
        doc = run._load_questions()
        self.assertEqual(doc["execution_profiles"]["frontier"]["terrace_groups"], [["DX1", "DX2", "DX3"], ["DX4"]])
        self.assertEqual(doc["execution_profiles"]["balanced"]["terrace_groups"], [["DX1"], ["DX2", "DX3"], ["DX4"]])
        self.assertEqual(run._question_plan(doc, "frontier"), [["DX1", "DX2", "DX3"], ["DX4"], ["DX-final"]])
        self.assertEqual([row["kind"] for row in doc["questions"]], ["terrace", "terrace", "terrace", "terrace", "final"])
        self.assertEqual([row["question"] for row in doc["questions"]], [
            "What diagnosis does WHO5 assign, and what diagnosis does ICC assign?",
            "Is there evidence for a different diagnosis or a concurrent second pathology?",
            "Is this overt disease, a precursor clonal state, germline predisposition, or a combination?",
            "What could make the current diagnoses wrong or uncertain?",
            "What is the final diagnostic state?",
        ])

    def test_question_plan_supports_any_number_of_terrace_questions(self):
        run = _load_run_module()
        config = {
            "execution_profiles": {"custom": {"terrace_groups": [["A", "B"], ["C"]]}},
            "questions": [
                {"id": "A", "kind": "terrace"},
                {"id": "B", "kind": "terrace"},
                {"id": "C", "kind": "terrace"},
                {"id": "terminal", "kind": "final"},
            ],
        }
        self.assertEqual(run._question_plan(config, "custom"), [["A", "B"], ["C"], ["terminal"]])

    def test_all_six_fixtures_are_complete(self):
        for number in range(1, 7):
            path = HERE / "fixtures" / f"example-{number:02d}" / "input.json"
            doc = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(doc["example"], number)
            self.assertTrue(doc["case_notes"].strip())
            self.assertTrue(doc["structured_case"]["provisional_cmcs"])
            self.assertIsInstance(doc["diagnosis_evidence_cards"], list)
            self.assertIn("no_haematological_malignancy", doc["allowed_schema_diseases"])

    def test_final_validator_protects_paired_state_and_uncertainty(self):
        run = _load_run_module()
        reviewed = {
            "provisional_cmcs": ["MDS"],
            "diagnoses": [_paired_diagnosis()],
            "facts": [{"fact": "SF3B1 supports the ICC candidate.", "reason": "Classifier-specific support.", "fact_id": "PRE-FINAL-F1"}],
            "uncertainties": [{"uncertainty": "Required exclusion remains unresolved.", "reason": "Material limitation.", "uncertainty_id": "PRE-FINAL-U1"}],
        }
        good = {
            "provisional_cmcs": ["MDS"],
            "diagnoses": [_paired_diagnosis()],
            "supporting_facts": [{"fact": "SF3B1 supports the ICC candidate.", "reason": "Classifier-specific support.", "source_fact_ids": ["PRE-FINAL-F1"]}],
            "uncertainties": [{"uncertainty": "Required exclusion remains unresolved.", "reason": "Material limitation.", "source_ids": ["PRE-FINAL-U1"]}],
        }
        final_config = next(row for row in run._load_questions()["questions"] if row["kind"] == "final")
        run._validate_final(good, reviewed, final_config)

    def test_state_requires_paired_who5_and_icc_outcomes(self):
        run = _load_run_module()
        state = {"provisional_cmcs": ["MDS"], "diagnoses": [_paired_diagnosis()], "facts": [], "uncertainties": []}
        run._validate_state(state, ["DX1"])
        unpaired = dict(state, diagnoses=[{"schema_disease": "MDS", "WHO5": state["diagnoses"][0]["WHO5"]}])
        with self.assertRaisesRegex(ValueError, r"diagnoses\[0\].*Required fix"):
            run._validate_state(unpaired, ["DX1"])

    def test_case_6_classifier_difference_can_be_represented_in_one_row(self):
        run = _load_run_module()
        state = {
            "provisional_cmcs": ["myeloid neoplasm, unspecified"],
            "diagnoses": [_paired_diagnosis()],
            "facts": [],
            "uncertainties": [{
                "uncertainty": "ICC MDS-SF3B1 exclusion status is unresolved.",
                "reason": "The paired ICC outcome remains indeterminate rather than disappearing.",
            }],
        }
        run._validate_state(state, ["DX4"])
        self.assertEqual(state["diagnoses"][0]["WHO5"]["status"], "not_established")
        self.assertEqual(state["diagnoses"][0]["ICC"]["diagnosis"], "MDS-SF3B1")
        self.assertTrue(state["diagnoses"][0]["materially_different"])

    def test_negative_ngs_and_no_pathology_are_explicitly_independent(self):
        text = (HERE / "prompts" / "terrace.md").read_text(encoding="utf-8")
        questions = (HERE / "questions.yaml").read_text(encoding="utf-8")
        self.assertIn("negative NGS never proves no pathology by itself", text)
        self.assertIn("negative NGS result", questions)
        self.assertIn("no_haematological_malignancy", questions)

    def test_run_layout_is_call_centric_and_input_output_labelled(self):
        run = _load_run_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            args = SimpleNamespace(
                profile="balanced", dry_run=True, provider="lmstudio", model="qwen3-coder-next",
                base_url=None, api_key=None, temperature=0.0, max_tokens=16384, timeout=900.0,
                output_dir=Path(temp_dir),
                structural_attempts=10,
            )
            run_dir = run._run_one(args, 1)
            self.assertTrue((run_dir / "RUN_INPUT_fixture.json").is_file())
            self.assertTrue((run_dir / "RUN_metadata.json").is_file())
            call = run_dir / "call_01_DX1"
            self.assertTrue(call.is_dir())
            for name in (
                "CALL_metadata.json", "INPUT_overview.md", "INPUT_questions.md", "INPUT_case_notes.md",
                "INPUT_previous_state.yaml", "INPUT_prior_transcript.json", "INPUT_evidence_cards.json",
                "INPUT_messages.json", "INPUT_messages_readable.md", "OUTPUT_not_run.txt",
            ):
                self.assertTrue((call / name).is_file(), name)
            self.assertFalse((run_dir / "prompt-01.json").exists())
            self.assertFalse((run_dir / "terrace-01.yaml").exists())

    def test_output_schema_prompt_does_not_seed_a_concrete_diagnosis(self):
        text = (HERE / "prompts" / "terrace.md").read_text(encoding="utf-8")
        self.assertNotIn("AML with mutated NPM1", text)
        self.assertNotIn("schema_disease: AML", text)
        self.assertNotIn("  - AML\n", text)
        self.assertIn("angle-bracketed text below describes the required field content", text)
        self.assertNotIn("icc_diagnoses", text)
        self.assertIn("WHO5:", text)
        self.assertIn("ICC:", text)

    def test_connector_deterministically_turns_lines_into_immutable_facts(self):
        prose = (
            "**Diagnosis**\n"
            "An SF3B1-defined MDS is raised as a diagnostic possibility.\n"
            "The current broad designation should be retained while material uncertainty remains.\n"
        )
        self.assertEqual(
            connector.prose_to_facts(prose),
            {
                "facts": [
                    {
                        "fact_id": "diagnosis-summary-1",
                        "fact": "An SF3B1-defined MDS is raised as a diagnostic possibility.",
                    },
                    {
                        "fact_id": "diagnosis-summary-2",
                        "fact": "The current broad designation should be retained while material uncertainty remains.",
                    },
                ]
            },
        )

    def test_connector_rejects_machine_status_in_report_prose(self):
        with self.assertRaisesRegex(ValueError, "machine-state"):
            connector.prose_to_facts(
                "**Diagnosis**\nThe WHO5 diagnosis remains indeterminate.\n"
            )

    def test_connector_grounding_is_closed_world_and_fact_immutable(self):
        immutable = {
            "facts": [{"fact_id": "diagnosis-summary-1", "fact": "A candidate diagnosis is raised."}]
        }
        good = {
            "facts": [
                {
                    "fact_id": "diagnosis-summary-1",
                    "fact": "A candidate diagnosis is raised.",
                    "reason": "The reviewed paired classifier outcomes retain a candidate label.",
                    "source_case_fact_ids": [],
                    "source_diagnostic_ids": ["D1-WHO5"],
                }
            ]
        }
        connector.validate_grounded(
            good,
            immutable,
            case_source_ids={"F1"},
            diagnostic_source_ids={"D1-WHO5"},
        )
        changed = yaml.safe_load(yaml.safe_dump(good))
        changed["facts"][0]["fact"] = "A diagnosis is established."
        with self.assertRaisesRegex(ValueError, "changed immutable supplied value"):
            connector.validate_grounded(
                changed,
                immutable,
                case_source_ids={"F1"},
                diagnostic_source_ids={"D1-WHO5"},
            )
        unknown = yaml.safe_load(yaml.safe_dump(good))
        unknown["facts"][0]["source_diagnostic_ids"] = ["UNKNOWN"]
        with self.assertRaisesRegex(ValueError, "unknown source"):
            connector.validate_grounded(
                unknown,
                immutable,
                case_source_ids={"F1"},
                diagnostic_source_ids={"D1-WHO5"},
            )

    def test_connector_alignment_only_adds_permitted_cards_and_render_is_deterministic(self):
        grounded = {
            "facts": [
                {
                    "fact_id": "diagnosis-summary-1",
                    "fact": "A candidate diagnosis is raised.",
                    "reason": "The reviewed state supports consideration of the candidate.",
                    "source_case_fact_ids": [],
                    "source_diagnostic_ids": ["D1-WHO5"],
                }
            ]
        }
        aligned = yaml.safe_load(yaml.safe_dump(grounded))
        aligned["facts"][0]["citation"] = "[card:000001]"
        connector.validate_aligned(aligned, grounded, permitted_card_tags={"000001"})
        self.assertEqual(
            connector.render_report(aligned),
            "**Diagnosis**\nA candidate diagnosis is raised. [card:000001]\n",
        )
        aligned["facts"][0]["citation"] = "[card:ffffff]"
        with self.assertRaisesRegex(ValueError, "unpermitted"):
            connector.validate_aligned(aligned, grounded, permitted_card_tags={"000001"})

    def test_synthesis_validator_reports_every_surrounding_whitespace_defect(self):
        prose = (
            "**Diagnosis**  \n"
            "Assigned diagnosis.  \n"
            "Supporting statement.  \n"
            "Material limitation.  \n"
            "Retained designation.\n"
        )
        with self.assertRaises(ValueError) as raised:
            connector.prose_to_facts(prose)
        message = str(raised.exception)
        self.assertIn("failed validation with 4 issue(s)", message)
        self.assertIn("Heading — Problem", message)
        self.assertIn("Sentence 1 — Problem", message)
        self.assertIn("Sentence 2 — Problem", message)
        self.assertIn("Sentence 3 — Problem", message)
        self.assertEqual(message.count("Required fix:"), 4)

    def test_validated_model_call_retries_with_complete_feedback_and_audit_trail(self):
        run = _load_run_module()
        calls = []

        def complete(_provider, messages):
            calls.append(messages)
            return "bad\n" if len(calls) == 1 else "good\n"

        def validate(value):
            if value == "bad":
                raise ValueError(
                    "artifact failed validation with 2 issue(s):\n"
                    "1. first — Problem: broken. Required fix: repair first.\n"
                    "2. second — Problem: broken. Required fix: repair second."
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            call_dir = Path(temp_dir) / "call"
            call_dir.mkdir()
            with patch.object(run, "complete", side_effect=complete):
                result = run._validated_model_call(
                    call_dir,
                    object(),
                    messages=[{"role": "user", "content": "produce artifact"}],
                    parse=lambda raw: raw.strip(),
                    validate=validate,
                    validator_name="test_validator",
                    attempts=3,
                )
            self.assertEqual(result, "good")
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[1][-2], {"role": "assistant", "content": "bad\n"})
            feedback = calls[1][-1]["content"]
            self.assertIn("first — Problem", feedback)
            self.assertIn("second — Problem", feedback)
            self.assertTrue((call_dir / "attempt_01" / "OUTPUT_raw.txt").is_file())
            failed = json.loads((call_dir / "attempt_01" / "OUTPUT_validation.json").read_text())
            passed = json.loads((call_dir / "attempt_02" / "OUTPUT_validation.json").read_text())
            self.assertFalse(failed["passed"])
            self.assertTrue(passed["passed"])

    def test_validated_model_call_stops_at_configured_attempt_bound(self):
        run = _load_run_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            call_dir = Path(temp_dir) / "call"
            call_dir.mkdir()
            with patch.object(run, "complete", return_value="bad\n") as complete:
                with self.assertRaisesRegex(ValueError, "after 2 attempt.*Required fix"):
                    run._validated_model_call(
                        call_dir,
                        object(),
                        messages=[{"role": "user", "content": "produce artifact"}],
                        parse=lambda raw: raw.strip(),
                        validate=lambda _value: (_ for _ in ()).throw(
                            ValueError("Artifact — Problem: invalid. Required fix: return valid output.")
                        ),
                        validator_name="test_validator",
                        attempts=2,
                    )
            self.assertEqual(complete.call_count, 2)
            self.assertTrue((call_dir / "attempt_02" / "OUTPUT_validation.json").is_file())


if __name__ == "__main__":
    unittest.main()

