from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from scripts.core import validated_model_task
from workflows.proforma_v1 import model_observability as observation
from workflows.proforma_v1 import model_client, step


class ModelObservabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.work = Path(self.temp.name)
        self.root = self.work / "model_steps" / "003_diagnosis_who5_pass_01"

    def tearDown(self):
        self.temp.cleanup()

    def _begin(self, attempt: int, *, call_id="diagnosis-who5-pass-01") -> Path:
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": f"request {attempt}"},
        ]
        return observation.begin_attempt(
            self.root,
            attempt,
            messages=messages,
            prompt=f"rendered request {attempt}\n",
            metadata={
                "logical_operation": "diagnosis.who1",
                "call_id": call_id,
                "call_kind": "model",
                "role": "diagnosis",
                "provider": "openrouter",
                "model": "example/model",
            },
        )

    def test_attempts_preserve_independent_exact_inputs_and_outputs(self):
        first = self._begin(1)
        observation.write_raw_output(first, "bad one")
        observation.write_validation(first, accepted=False, detail="first failure")
        observation.finish_attempt(first, status="rejected", validation_error="first failure")
        second = self._begin(2)
        observation.write_raw_output(second, "good two")
        observation.write_reasoning(second, "private telemetry")
        observation.write_validation(second, accepted=True, detail="valid")
        observation.finish_attempt(second, status="accepted", usage={"total_tokens": 9})
        observation.sync_root_compatibility_view(self.root, second)

        self.assertEqual((first / "output.txt").read_text(encoding="utf-8"), "bad one")
        self.assertEqual((first / "messages.json").read_text(encoding="utf-8").count("request 1"), 1)
        self.assertIn("RESULT=rejected", (first / "validation.txt").read_text(encoding="utf-8"))
        self.assertEqual((self.root / "output.txt").read_text(encoding="utf-8"), "good two")
        self.assertEqual((self.root / "reasoning.md").read_text(encoding="utf-8"), "private telemetry")
        self.assertEqual(json.loads((second / "call.json").read_text())["usage"]["total_tokens"], 9)

    def test_unavailable_reasoning_is_file_absence_and_clears_compatibility_view(self):
        first = self._begin(1)
        observation.write_reasoning(first, "reason")
        observation.sync_root_compatibility_view(self.root, first)
        second = self._begin(2)
        observation.write_reasoning(second, None)
        observation.sync_root_compatibility_view(self.root, second)
        self.assertFalse((second / "reasoning.md").exists())
        self.assertFalse((self.root / "reasoning.md").exists())

    def test_syntax_repairs_are_nested_below_parent_attempt(self):
        primary = self._begin(2)
        repair = observation.begin_attempt(
            self.root,
            1,
            parent_attempt=2,
            messages=[{"role": "user", "content": "repair"}],
            prompt="repair prompt",
            metadata={
                "logical_operation": "diagnosis.who1",
                "call_id": "diagnosis-who5-pass-01-syntax-1",
                "parent_call_id": "diagnosis-who5-pass-01",
                "call_kind": "syntax_repair",
            },
        )
        observation.write_raw_output(repair, "fixed")
        observation.write_validation(repair, accepted=True)
        observation.finish_attempt(repair, status="accepted")
        observation.finish_attempt(primary, status="accepted")

        index = observation.build_model_operation_index(
            self.work, workflow_steps=["structure", "diagnosis.who1"]
        )
        attempts = index["operations"][0]["calls"][0]["attempts"]
        self.assertEqual([row["attempt"] for row in attempts], [2])
        self.assertEqual(attempts[0]["syntax_repairs"][0]["attempt"], 1)
        self.assertIn("attempts/02/syntax_repairs/01", attempts[0]["syntax_repairs"][0]["path"])

    def test_index_groups_calls_and_follows_workflow_order(self):
        other_root = self.work / "model_steps" / "001_evidence_match_batch_01"
        for root, call_id, logical in (
            (other_root, "evidence-match-batch-01", "evidence.assignment"),
            (self.root, "diagnosis-who5-pass-01", "diagnosis.who1"),
            (self.work / "model_steps" / "004_evidence_match_batch_02", "evidence-match-batch-02", "evidence.assignment"),
        ):
            path = observation.begin_attempt(
                root, 1,
                messages=[], prompt="",
                metadata={"logical_operation": logical, "call_id": call_id, "call_kind": "model"},
            )
            observation.finish_attempt(path, status="accepted")
        index = observation.build_model_operation_index(
            self.work,
            workflow_steps=["diagnosis.who1", "evidence.assignment"],
            labels={"diagnosis.who1": "Diagnosis · WHO5"},
        )
        self.assertEqual([row["id"] for row in index["operations"]], ["diagnosis.who1", "evidence.assignment"])
        self.assertEqual(index["operations"][0]["label"], "Diagnosis · WHO5")
        self.assertEqual(len(index["operations"][1]["calls"]), 2)
        persisted = json.loads((self.work / "logs" / observation.INDEX_NAME).read_text(encoding="utf-8"))
        self.assertEqual(persisted, index)

    def test_provider_error_keeps_input_without_inventing_output(self):
        path = self._begin(1)
        observation.finish_attempt(path, status="provider_error", error="network down")
        metadata = json.loads((path / "call.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["status"], "provider_error")
        self.assertEqual(metadata["error"], "network down")
        self.assertFalse((path / "output.txt").exists())

    def test_real_adapter_preserves_two_rejections_then_accepted_third_attempt(self):
        root = self.work / "model_steps" / "001_test_call"
        output = self.work / "intermediates" / "result.txt"
        binding = SimpleNamespace(
            model="example/model", base_url="https://openrouter.ai/api/v1",
            pipeline="test", is_self=False,
        )
        responses = [
            model_client.Completion("bad one", reasoning="thought one"),
            model_client.Completion("bad two", reasoning="thought two"),
            model_client.Completion("good", reasoning="thought three"),
        ]
        request = validated_model_task.TaskRequest(
            task_id="test-call",
            messages=[{"role": "user", "content": "original"}],
            validate=lambda text: "valid" if text == "good" else (_ for _ in ()).throw(ValueError(f"rejected {text}")),
            budgets=validated_model_task.Budgets(content=3, serialization=0, rewrite=0),
        )
        io = step._task_io(
            self.work, call_id="test-call", role="diagnosis", binding=binding,
            syntax_binding=binding, output=output, root=root,
        )
        with mock.patch.object(step.model_client, "complete_messages", side_effect=responses):
            accepted = validated_model_task.run(request, io)

        self.assertEqual(accepted, "good")
        self.assertEqual(output.read_text(encoding="utf-8"), "good")
        attempts = [root / "attempts" / f"{index:02d}" for index in (1, 2, 3)]
        self.assertEqual([p.joinpath("output.txt").read_text(encoding="utf-8") for p in attempts], ["bad one", "bad two", "good"])
        self.assertEqual([p.joinpath("reasoning.md").read_text(encoding="utf-8") for p in attempts], ["thought one", "thought two", "thought three"])
        self.assertIn("RESULT=rejected", (attempts[0] / "validation.txt").read_text(encoding="utf-8"))
        self.assertIn("rejected bad two", (attempts[1] / "validation.txt").read_text(encoding="utf-8"))
        self.assertEqual((attempts[2] / "validation.txt").read_text(encoding="utf-8"), "RESULT=accepted\n")
        self.assertEqual((root / "output.txt").read_text(encoding="utf-8"), "good")
        self.assertEqual((root / "accepted-output.txt").read_text(encoding="utf-8"), "good")
        index = json.loads((self.work / "logs" / observation.INDEX_NAME).read_text(encoding="utf-8"))
        self.assertEqual(index["operations"][0]["calls"][0]["status"], "complete")
        self.assertEqual([row["status"] for row in index["operations"][0]["calls"][0]["attempts"]], ["rejected", "rejected", "accepted"])

    def test_truncated_attempt_retains_partial_output_and_reasoning_before_retry(self):
        root = self.work / "model_steps" / "001_truncated"
        output = self.work / "intermediates" / "result.txt"
        binding = SimpleNamespace(
            model="example/model", base_url="https://openrouter.ai/api/v1",
            pipeline="test", is_self=False,
        )
        responses = [
            model_client.TruncatedCompletion("partial", 100, reasoning="partial thought"),
            model_client.Completion("complete"),
        ]
        request = validated_model_task.TaskRequest(
            task_id="truncated", messages=[{"role": "user", "content": "task"}],
            validate=lambda text: "valid",
            budgets=validated_model_task.Budgets(content=2, serialization=0, rewrite=0),
        )
        io = step._task_io(
            self.work, call_id="truncated", role="diagnosis", binding=binding,
            syntax_binding=binding, output=output, root=root,
        )
        with mock.patch.object(step.model_client, "complete_messages", side_effect=responses):
            self.assertEqual(validated_model_task.run(request, io), "complete")
        first = root / "attempts" / "01"
        self.assertEqual((first / "output.txt").read_text(encoding="utf-8"), "partial")
        self.assertEqual((first / "reasoning.md").read_text(encoding="utf-8"), "partial thought")
        self.assertEqual(json.loads((first / "call.json").read_text())["status"], "truncated")

    def test_shared_runner_reports_each_syntax_validation_result(self):
        syntax_results = []
        repairs = iter(("still bad", "good"))
        issue = validated_model_task.ValidationIssue(
            "root", "bad serialization", "repair it", repair_class="serialization"
        )
        def validate(text):
            if text != "good":
                raise validated_model_task.ValidationFailure("syntax-test", [issue])
            return "valid"
        request = validated_model_task.TaskRequest(
            task_id="syntax-test", messages=[], validate=validate,
            budgets=validated_model_task.Budgets(content=1, serialization=2, rewrite=0),
        )
        io = validated_model_task.TaskIO(
            call_model=lambda messages: "bad",
            call_syntax_model=lambda prompt, attempt: next(repairs),
            load_state=lambda key: {}, save_state=lambda key, value: None,
            read_output=lambda: None, write_output=lambda text: None,
            record_syntax_attempt=syntax_results.append,
        )
        self.assertEqual(validated_model_task.run(request, io), "good")
        self.assertEqual([row.index for row in syntax_results], [1, 2])
        self.assertIsNotNone(syntax_results[0].error)
        self.assertIsNone(syntax_results[1].error)


if __name__ == "__main__":
    unittest.main()