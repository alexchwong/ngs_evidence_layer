from __future__ import annotations

import json
import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace

from scripts import model_usage
from scripts.core import validated_model_task
from workflows.proforma_v1 import model_observability, reasoning_guards
from workflows.proforma_v1.engine import control_state
from workflows.proforma_v1.engine.context import WorkflowContext
from workflows.proforma_v1.engine.workflow_runner import WorkflowRunner, TerminalWorkflowFailure, TERMINAL_WORKFLOW_EXIT_CODE


def _step(step_id, *, needs=(), review=None, artifact=None, inputs=None):
    return SimpleNamespace(
        id=step_id,
        type="transform",
        needs=tuple(needs),
        execution={"provider": {"enabled": True}},
        review=review,
        output={"artifact": artifact} if artifact else {},
        inputs=inputs or {},
        when=None,
    )


class _Workflow:
    workflow_id = "hardening-test"
    source = Path("hardening-test.yaml")
    source_sha256 = "hardening-test"
    doc = {}

    def __init__(self, steps):
        self.steps = tuple(steps)
        self._by_id = {step.id: step for step in self.steps}

    def step(self, step_id):
        return self._by_id[step_id]


class _Executor:
    def __init__(self, *, hydrated=None, executed=None):
        self.hydrated = hydrated or {}
        self.executed_results = executed or {}
        self.executed = []
        self.invalidated = []

    def is_complete(self, step_id, context):
        row = self.hydrated.get(step_id)
        if row is None:
            return False
        artifact_name, value = row
        if artifact_name:
            context.put(artifact_name, value)
        return True

    def execute(self, step, context):
        self.executed.append(step.id)
        configured = self.executed_results.get(step.id, {"status": "pass"})
        if isinstance(configured, list):
            value = configured.pop(0) if configured else {"status": "pass"}
        else:
            value = configured
        artifact_name = (step.output or {}).get("artifact")
        if artifact_name:
            context.put(artifact_name, value)
        return {"status": "complete", "artifact": value}

    def invalidate(self, step_ids, context):
        self.invalidated.append(set(step_ids))


class ReasoningResumeHardeningTests(unittest.TestCase):
    def _review_workflow(self):
        target = _step("diagnosis.who.reason")
        review = _step(
            "diagnosis.who.reason.validate",
            needs=(target.id,),
            artifact="diagnosis_who_reasoning_validation",
            review={
                "target": target.id,
                "verdict": {"path": "status", "pass_values": ["pass"]},
                "on_fail": {
                    "retry_target": True,
                    "max_cycles": 0,
                    "exhausted": {"action": "stop"},
                },
            },
        )
        child = _step("diagnosis.who.em.prepare", needs=(review.id,), artifact="child")
        return _Workflow((target, review, child)), target, review, child

    def test_persisted_failed_review_is_not_artifact_complete(self):
        workflow, target, review, _child = self._review_workflow()
        executor = _Executor(hydrated={review.id: ("diagnosis_who_reasoning_validation", {"status": "fail"})})
        with tempfile.TemporaryDirectory() as tmp:
            context = WorkflowContext(Path(tmp), executor="provider", completed={target.id})
            runner = WorkflowRunner(workflow, executor)
            self.assertFalse(runner._step_done(context, review.id))
            self.assertNotIn(review.id, context.completed)

    def test_failed_review_blocks_hydration_of_descendants(self):
        workflow, target, review, child = self._review_workflow()
        executor = _Executor(
            hydrated={
                review.id: ("diagnosis_who_reasoning_validation", {"status": "fail"}),
                child.id: ("child", {"stale": True}),
            },
            executed={review.id: {"status": "fail"}},
        )
        with tempfile.TemporaryDirectory() as tmp:
            context = WorkflowContext(Path(tmp), executor="provider", completed={target.id})
            runner = WorkflowRunner(workflow, executor)
            with self.assertRaisesRegex(TerminalWorkflowFailure, "failed after 0 feedback cycle"):
                runner.advance(context)
            self.assertEqual(executor.executed, [review.id])
            self.assertNotIn(child.id, context.completed)

    def test_exhausted_stop_is_terminal_and_does_not_recount_on_resume(self):
        target = _step("prognosis.reason")
        review = _step(
            "prognosis.reason.validate", needs=(target.id,), artifact="prognosis_reasoning_validation",
            review={
                "target": target.id,
                "verdict": {"path": "status", "pass_values": ["pass"]},
                "on_fail": {"retry_target": True, "max_cycles": 1, "exhausted": {"action": "stop"}},
            },
        )
        child = _step("prognosis.em.prepare", needs=(review.id,), artifact="child")
        workflow = _Workflow((target, review, child))
        executor = _Executor(executed={review.id: [{"status": "fail"}, {"status": "fail"}]})
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            context = WorkflowContext(work, executor="provider", completed={target.id})
            runner = WorkflowRunner(workflow, executor)
            with self.assertRaisesRegex(TerminalWorkflowFailure, "failed after 1 feedback cycle"):
                runner.run_all(context)
            state = json.loads((work / "logs" / "workflow-control.json").read_text(encoding="utf-8"))
            self.assertEqual(state["review_cycles"][review.id], 1)
            self.assertEqual(state["review_terminal"][review.id]["action"], "stop")
            self.assertEqual([x["action"] for x in state["review_events"]], ["retry", "exhausted:stop"])
            failure = json.loads((work / "logs" / "workflow-failure.json").read_text(encoding="utf-8"))
            self.assertFalse(failure["retryable"])
            self.assertEqual(failure["failure_class"], "terminal_review")
            self.assertEqual(failure["exit_code"], TERMINAL_WORKFLOW_EXIT_CODE)

            resumed_executor = _Executor()
            resumed = WorkflowContext(work, executor="provider", completed={target.id})
            resumed_runner = WorkflowRunner(workflow, resumed_executor)
            with self.assertRaisesRegex(TerminalWorkflowFailure, "failed after 1 feedback cycle"):
                resumed_runner.run_all(resumed)
            state2 = json.loads((work / "logs" / "workflow-control.json").read_text(encoding="utf-8"))
            self.assertEqual(state2["review_cycles"][review.id], 1)
            self.assertEqual(len(state2["review_events"]), 2)
            self.assertNotIn(review.id, resumed_executor.executed)
            self.assertNotIn(child.id, resumed_executor.executed)

    def test_semantic_redo_rejects_unrelated_changes_outside_feedback_scope(self):
        target = _step("prognosis.reason", artifact="prognosis_reasoning")
        review = _step(
            "prognosis.reason.validate", needs=(target.id,), artifact="prognosis_reasoning_validation",
            review={
                "target": target.id,
                "verdict": {"path": "status", "pass_values": ["pass"]},
                "on_fail": {"retry_target": True, "max_cycles": 1, "exhausted": {"action": "stop"}},
            },
        )
        workflow = _Workflow((target, review))
        with tempfile.TemporaryDirectory() as tmp:
            context = WorkflowContext(Path(tmp), executor="provider", completed={target.id})
            baseline = {
                "frameworks": [{"name": "IPSS-M", "reasoning": [{"assessment": "unknown", "supports_conclusion": True, "reason": "x"}]}],
                "variant_assessments": [{"variant_id": "V1", "other_evidence": {"effect": "adverse"}}],
            }
            context.put("prognosis_reasoning", baseline)
            runner = WorkflowRunner(workflow, _Executor())
            failed_review = {
                "status": "fail",
                "issues": [{"path": "$.frameworks[0].reasoning[0].supports_conclusion", "code": "x"}],
            }
            runner._set_redo_preservation(review, context, {"artifact": failed_review})
            context.put("prognosis_reasoning", {
                "frameworks": [{"name": "MDS", "reasoning": [{"assessment": "unknown", "supports_conclusion": False, "reason": "x"}]}],
                "variant_assessments": [{"variant_id": "V1", "other_evidence": {"effect": "neutral"}}],
            })
            result = runner._apply_preservation_review(review, context, {"artifact": {"status": "pass", "issues": []}})
            self.assertEqual(result["artifact"]["status"], "fail")
            paths = [row["path"] for row in result["artifact"]["issues"] if row.get("code") == "unexpected_redo_change"]
            self.assertIn("$.frameworks[0].name", paths)
            self.assertIn("$.variant_assessments[0].other_evidence.effect", paths)
            self.assertNotIn("$.frameworks[0].reasoning[0].supports_conclusion", paths)

    def test_semantic_redo_allows_changes_within_reported_object(self):
        target = _step("prognosis.reason", artifact="prognosis_reasoning")
        review = _step(
            "prognosis.reason.validate", needs=(target.id,), artifact="prognosis_reasoning_validation",
            review={
                "target": target.id,
                "verdict": {"path": "status", "pass_values": ["pass"]},
                "on_fail": {"retry_target": True, "max_cycles": 1, "exhausted": {"action": "stop"}},
            },
        )
        workflow = _Workflow((target, review))
        with tempfile.TemporaryDirectory() as tmp:
            context = WorkflowContext(Path(tmp), executor="provider", completed={target.id})
            baseline = {"reasoning": [{"assessment": "unknown", "supports_conclusion": True, "reason": "old"}], "fixed": 1}
            context.put("prognosis_reasoning", baseline)
            runner = WorkflowRunner(workflow, _Executor())
            runner._set_redo_preservation(review, context, {"artifact": {
                "status": "fail", "issues": [{"path": "$.reasoning[0].supports_conclusion"}],
            }})
            context.put("prognosis_reasoning", {"reasoning": [{"assessment": "met", "supports_conclusion": True, "reason": "corrected"}], "fixed": 1})
            result = runner._apply_preservation_review(review, context, {"artifact": {"status": "pass", "issues": []}})
            self.assertEqual(result["artifact"]["status"], "pass")

    def test_redo_preservation_is_generic_across_reviewable_model_classes(self):
        target_ids = (
            "diagnosis.who.reason",
            "diagnosis.who.em",
            "diagnosis.evidence.audit",
            "diagnosis.evidence.adjudication",
            "diagnosis.reasoning.audit",
            "prognosis.reason",
            "prognosis.em",
            "treatment.reason",
            "biomarker.reason",
            "germline.reason",
            "ptbg.evidence.audit",
            "ptbg.evidence.adjudication",
            "ptbg.reasoning.audit",
        )
        for target_id in target_ids:
            with self.subTest(target_id=target_id), tempfile.TemporaryDirectory() as tmp:
                artifact_name = target_id.replace(".", "_")
                target = _step(target_id, artifact=artifact_name)
                review = _step(
                    target_id + ".review", needs=(target.id,), artifact=artifact_name + "_review",
                    review={
                        "target": target.id,
                        "verdict": {"path": "status", "pass_values": ["pass"]},
                        "on_fail": {"retry_target": True, "max_cycles": 1, "exhausted": {"action": "stop"}},
                    },
                )
                runner = WorkflowRunner(_Workflow((target, review)), _Executor())
                context = WorkflowContext(Path(tmp), executor="provider", completed={target.id})
                context.put(artifact_name, {"decision": "keep", "reasoning": [{"supports_conclusion": True}]})
                runner._set_redo_preservation(review, context, {"artifact": {
                    "status": "fail", "issues": [{"path": "$.reasoning[0].supports_conclusion"}],
                }})
                context.put(artifact_name, {"decision": "changed", "reasoning": [{"supports_conclusion": False}]})
                result = runner._apply_preservation_review(review, context, {"artifact": {"status": "pass", "issues": []}})
                paths = [row["path"] for row in result["artifact"]["issues"] if row.get("code") == "unexpected_redo_change"]
                self.assertIn("$.decision", paths)

    def test_continue_with_dissent_is_terminal_complete_and_unblocks_child(self):
        target = _step("prognosis.em")
        review = _step(
            "prognosis.em.review", needs=(target.id,), artifact="prognosis_em_review",
            review={
                "target": target.id,
                "verdict": {"path": "status", "pass_values": ["pass"]},
                "on_fail": {"retry_target": True, "max_cycles": 0, "exhausted": {"action": "continue_with_dissent"}},
            },
        )
        child = _step("ptbg.evidence.disputes", needs=(review.id,), artifact="child")
        workflow = _Workflow((target, review, child))
        executor = _Executor(executed={review.id: {"status": "fail"}})
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            context = WorkflowContext(work, executor="provider", completed={target.id})
            result = WorkflowRunner(workflow, executor).run_all(context)
            self.assertEqual(result.status, "complete")
            self.assertTrue(context.get(f"{review.id}__dissent"))
            self.assertIn(review.id, context.completed)
            self.assertIn(child.id, executor.executed)
            state = control_state.load(work)
            self.assertEqual(state["review_terminal"][review.id]["action"], "continue_with_dissent")

    def test_suppress_is_terminal_complete_and_restores_on_resume(self):
        target = _step("owner")
        review = _step(
            "owner.review", needs=(target.id,), artifact="owner_review",
            review={
                "target": target.id,
                "verdict": {"path": "status", "pass_values": ["pass"]},
                "on_fail": {"retry_target": True, "max_cycles": 0, "exhausted": {"action": "suppress"}},
            },
        )
        child = _step("final", needs=(review.id,), artifact="final")
        workflow = _Workflow((target, review, child))
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            first = WorkflowContext(work, executor="provider", completed={target.id})
            WorkflowRunner(workflow, _Executor(executed={review.id: {"status": "fail"}})).run_all(first)
            self.assertTrue(first.get(f"{target.id}__suppressed"))

            resumed = WorkflowContext(work, executor="provider", completed={target.id})
            runner = WorkflowRunner(workflow, _Executor())
            control_state.hydrate(resumed)
            self.assertTrue(runner._step_done(resumed, review.id))
            self.assertTrue(resumed.get(f"{target.id}__suppressed"))

    def test_clinical_owner_redo_budget_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            first = WorkflowContext(work, executor="provider")
            first.put("clinical_owner_redo_used", {"prognosis": True, "who5": True})
            control_state.save(first)
            resumed = WorkflowContext(work, executor="provider")
            control_state.hydrate(resumed)
            self.assertEqual(resumed.get("clinical_owner_redo_used"), {"prognosis": True, "who5": True})

    def test_failed_run_writes_partial_workflow_trace(self):
        workflow, target, review, _child = self._review_workflow()
        executor = _Executor(executed={review.id: {"status": "fail"}})

        class Trace:
            def __init__(self): self.rows = []
            def record(self, *args, **kwargs): self.rows.append((args, kwargs))
            def write(self, path):
                Path(path).parent.mkdir(parents=True, exist_ok=True)
                Path(path).write_text("partial trace", encoding="utf-8")

        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            context = WorkflowContext(work, executor="provider", completed={target.id})
            with self.assertRaises(TerminalWorkflowFailure):
                WorkflowRunner(workflow, executor, trace=Trace()).run_all(context)
            self.assertEqual((work / "logs" / "workflow-trace.json").read_text(encoding="utf-8"), "partial trace")


class ModelAttemptHistoryTests(unittest.TestCase):
    def test_semantic_reentry_appends_attempt_instead_of_overwriting_attempt_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            root = work / "model_steps" / "001_workflow_diagnosis_who_reason"
            metadata = {
                "logical_operation": "diagnosis.who.reason",
                "call_id": "workflow-diagnosis-who-reason",
                "call_kind": "model",
                "role": "diagnosis",
            }
            first = model_observability.begin_attempt(root, 1, messages=[], prompt="first prompt", metadata=metadata)
            model_observability.write_raw_output(first, "first output")
            model_observability.write_validation(first, accepted=False, detail="first rejected")
            model_observability.finish_attempt(first, status="rejected")

            second = model_observability.begin_attempt(root, 1, messages=[], prompt="retry prompt", metadata=metadata)
            model_observability.write_raw_output(second, "second output")
            model_observability.write_validation(second, accepted=True)
            model_observability.finish_attempt(second, status="accepted")

            self.assertEqual(first.name, "01")
            self.assertEqual(second.name, "02")
            self.assertEqual((first / "output.txt").read_text(encoding="utf-8"), "first output")
            self.assertEqual((second / "output.txt").read_text(encoding="utf-8"), "second output")
            second_meta = json.loads((second / "call.json").read_text(encoding="utf-8"))
            self.assertTrue(second_meta["resumed_attempt"])
            self.assertEqual(second_meta["attempt_kind"], "semantic_redo")
            index = model_observability.build_model_operation_index(work, workflow_steps=["diagnosis.who.reason"])
            call = index["operations"][0]["calls"][0]
            attempts = call["attempts"]
            self.assertEqual([row["attempt"] for row in attempts], [1, 2])
            self.assertEqual([row["attempt_kind"] for row in attempts], ["initial", "semantic_redo"])
            self.assertEqual(call["status"], "complete")

            # Invalidation clears only mutable root compatibility files.
            (root / "accepted-output.txt").write_text("current", encoding="utf-8")
            (root / "output.txt").write_text("current", encoding="utf-8")
            model_observability.invalidate_compatibility_view(work, "diagnosis.who.reason")
            self.assertFalse((root / "accepted-output.txt").exists())
            self.assertFalse((root / "output.txt").exists())
            self.assertTrue((first / "output.txt").is_file())
            self.assertTrue((second / "output.txt").is_file())

    def test_task_retry_after_semantic_reentry_is_not_mislabeled_as_semantic_redo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "model_steps" / "001_test"
            metadata = {"logical_operation": "prognosis.reason", "call_id": "workflow-prognosis-reason", "call_kind": "model", "role": "prognosis"}
            first = model_observability.begin_attempt(root, 1, messages=[], prompt="first", metadata=metadata)
            model_observability.finish_attempt(first, status="rejected")
            semantic = model_observability.begin_attempt(root, 1, messages=[], prompt="semantic", metadata=metadata)
            model_observability.finish_attempt(semantic, status="rejected")
            task_retry = model_observability.begin_attempt(root, 2, messages=[], prompt="task retry", metadata=metadata)
            meta = json.loads((task_retry / "call.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["attempt"], 3)
            self.assertEqual(meta["logical_attempt"], 2)
            self.assertEqual(meta["attempt_kind"], "task_retry")

    def test_observability_log_names_physical_initial_semantic_and_task_retry_attempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "model_steps" / "001_test"
            metadata = {"logical_operation": "prognosis.reason", "call_id": "workflow-prognosis-reason", "call_kind": "model", "role": "prognosis"}
            stream = io.StringIO()
            with redirect_stderr(stream):
                first = model_observability.begin_attempt(root, 1, messages=[], prompt="first", metadata=metadata)
                model_observability.finish_attempt(first, status="rejected")
                semantic = model_observability.begin_attempt(root, 1, messages=[], prompt="semantic", metadata=metadata)
                model_observability.finish_attempt(semantic, status="rejected")
                task_retry = model_observability.begin_attempt(root, 2, messages=[], prompt="retry", metadata=metadata)
                model_observability.finish_attempt(task_retry, status="accepted")
            log = stream.getvalue()
            self.assertIn("initial · physical attempt 1", log)
            self.assertIn("semantic redo · physical attempt 2", log)
            self.assertIn("task retry · physical attempt 3", log)
            self.assertNotIn(": answering", log)

    def test_operation_status_follows_latest_attempt_not_stale_historical_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            root = work / "model_steps" / "001_test"
            metadata = {"logical_operation": "diagnosis.who.reason", "call_id": "x", "call_kind": "model", "role": "diagnosis"}
            first = model_observability.begin_attempt(root, 1, messages=[], prompt="first", metadata=metadata)
            model_observability.finish_attempt(first, status="accepted")
            second = model_observability.begin_attempt(root, 1, messages=[], prompt="second", metadata=metadata)
            model_observability.finish_attempt(second, status="provider_error", error="down")
            index = model_observability.build_model_operation_index(work, workflow_steps=["diagnosis.who.reason"])
            self.assertEqual(index["operations"][0]["calls"][0]["status"], "provider_error")


    def test_task_runner_does_not_emit_misleading_model_answering_status(self):
        statuses = []
        request = validated_model_task.TaskRequest(
            task_id="workflow-prognosis-reason", messages=[], validate=lambda text: "ok",
            budgets=validated_model_task.Budgets(content=1, serialization=0, rewrite=0),
        )
        io = validated_model_task.TaskIO(
            call_model=lambda messages: "ok", load_state=lambda key: {}, save_state=lambda key, value: None,
            read_output=lambda: None, write_output=lambda text: None, status=statuses.append, is_self=False,
        )
        self.assertEqual(validated_model_task.run(request, io), "ok")
        self.assertFalse(any("answering" in value for value in statuses))

    def test_usage_ledger_uses_append_only_physical_attempt_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model-usage.json"
            for requested in (1, 1, 2):
                model_usage.record_call(
                    path, "workflow-prognosis-reason", "example/model", requested, None,
                    role="prognosis", provider="openrouter", logical_operation="prognosis.reason",
                )
            calls = model_usage.load_ledger(path)["calls"]
            self.assertEqual([row["attempt"] for row in calls], [1, 2, 3])
            self.assertNotIn("logical_attempt", calls[0])
            self.assertEqual([row.get("logical_attempt") for row in calls[1:]], [1, 2])
            self.assertTrue(all(row.get("resumed_attempt") for row in calls[1:]))


class DiagnosticReasoningGuardTests(unittest.TestCase):
    def test_unmet_defining_requirement_cannot_establish_proposed_diagnosis(self):
        document = {
            "authority": "who5",
            "diagnosis": {
                "label": "MDS with biallelic TP53 inactivation",
                "schema_disease": "MDS with biallelic TP53 inactivation",
                "diagnostic_effect": "refined",
                "status": "established",
                "variant_assessments": [],
            },
            "reasoning": [
                {
                    "rule": "MDS with biallelic TP53 inactivation requires multiple TP53 hits or TP53 loss.",
                    "case_fact_ids": [], "variant_ids": [], "assessment": "unknown",
                    "supports_conclusion": False, "reason": "A required second hit is not established.",
                },
                {
                    "rule": "MDS requires cytopenia and dysplasia.",
                    "case_fact_ids": [], "variant_ids": [], "assessment": "met",
                    "supports_conclusion": True, "reason": "MDS is established.",
                },
            ],
            "conclusion": {"operator": "all_of"},
            "reason": "test",
        }
        context = {"case": {"provisional_disease": "MDS"}, "diagnosis_who_reasoning": document}
        base = {"authority": "who5", "status": "pass", "issue_count": 0, "feedback": "", "issues": []}
        result = reasoning_guards.after_diagnostic_transform(
            "reasoning_validate_diagnostic_reasoning_v2", base, context, {"authority": "who5"}
        )
        self.assertEqual(result["status"], "fail")
        self.assertIn("unmet_defining_criterion", [row["code"] for row in result["issues"]])

    def test_refined_effect_requires_changed_named_diagnosis(self):
        document = {
            "authority": "who5",
            "diagnosis": {"label": "MDS", "diagnostic_effect": "refined", "status": "established"},
            "reasoning": [],
        }
        issues = reasoning_guards.diagnostic_coherence_issues(document, case={"provisional_disease": "MDS"})
        self.assertIn("incoherent_diagnostic_effect", [row["code"] for row in issues])

    def test_retry_returning_to_authoritative_starting_diagnosis_requires_unchanged(self):
        # A prior failed answer is intentionally not part of the baseline.  The
        # corrected diagnosis must still be compared with the immutable case
        # diagnosis supplied to the owner pack.
        corrected = {
            "authority": "who5",
            "diagnosis": {
                "label": "myelodysplastic neoplasm with low blasts and multilineage dysplasia",
                "diagnostic_effect": "refined",
                "status": "established",
            },
            "reasoning": [],
        }
        starting = "myelodysplastic neoplasm with low blasts and multilineage dysplasia"
        issues = reasoning_guards.diagnostic_coherence_issues(
            corrected, case={"provisional_disease": starting}
        )
        issue = next(row for row in issues if row["code"] == "incoherent_diagnostic_effect")
        self.assertIn(starting, issue["message"])
        self.assertIn("authoritative starting diagnosis", issue["fix"])
        self.assertIn("'unchanged'", issue["fix"])

    def test_supports_conclusion_requires_met_across_all_owner_domains(self):
        diagnostic = {
            "authority": "who5",
            "diagnosis": {"label": "MDS", "diagnostic_effect": "unchanged", "status": "established"},
            "reasoning": [{
                "rule": "x", "case_fact_ids": [], "variant_ids": [], "assessment": "unknown",
                "supports_conclusion": True, "reason": "x",
            }],
        }
        context = {"case": {"provisional_disease": "MDS"}, "diagnosis_who_reasoning": diagnostic}
        result = reasoning_guards.after_diagnostic_transform(
            "reasoning_validate_diagnostic_reasoning_v2",
            {"status": "pass", "issues": []}, context, {"authority": "who5"},
        )
        self.assertIn("non_supporting_conclusion_item", [x["code"] for x in result["issues"]])

        for domain in ("prognosis", "treatment", "biomarker", "germline"):
            document = {"reasoning": [{
                "rule": "x", "case_fact_ids": [], "variant_ids": [], "assessment": "not_met",
                "supports_conclusion": True, "reason": "x",
            }]}
            ctx = {f"{domain}_reasoning": document}
            if domain == "prognosis":
                ctx["prognosis_reasoning_pack"] = {"authoritative_diagnosis": {"who5": {"schema_disease": "AML"}}}
            result = reasoning_guards.after_ptbg_transform(
                "reasoning_validate_ptbg_reasoning_v2", {"status": "pass", "issues": []}, ctx,
                {"domain": domain, "step_id": f"{domain}.reason.validate"},
            )
            self.assertIn("non_supporting_conclusion_item", [x["code"] for x in result["issues"]], domain)

    def test_every_reasoning_row_requires_complete_atomic_shape(self):
        document = {"reasoning": [{"rule": "x", "assessment": "met", "supports_conclusion": True}]}
        issues = reasoning_guards.reasoning_contract_issues(document)
        missing = {row["path"] for row in issues if row["code"] == "missing_reasoning_field"}
        self.assertIn("$.reasoning[0].case_fact_ids", missing)
        self.assertIn("$.reasoning[0].variant_ids", missing)
        self.assertIn("$.reasoning[0].reason", missing)

    def test_mds_prognosis_framework_is_exactly_ipss_m(self):
        document = {"frameworks": [{"name": "MDS", "reasoning": []}], "variant_assessments": []}
        context = {
            "prognosis_reasoning": document,
            "prognosis_reasoning_pack": {"authoritative_diagnosis": {"who5": {"schema_disease": "MDS"}}},
        }
        result = reasoning_guards.after_ptbg_transform(
            "reasoning_validate_ptbg_reasoning_v2", {"status": "pass", "issues": []}, context,
            {"domain": "prognosis", "step_id": "prognosis.reason.validate"},
        )
        codes = [row["code"] for row in result["issues"]]
        self.assertIn("missing_required_prognostic_framework", codes)
        self.assertIn("unknown_prognostic_framework", codes)

    def test_compiler_requires_both_reason_and_evidence_match_reviews_to_pass(self):
        context = {
            "diagnosis_who_reasoning_validation": {"status": "fail"},
            "diagnosis_who_evidence_match_validation": {"status": "pass"},
        }
        with self.assertRaisesRegex(ValueError, "diagnosis.who.reason.validate"):
            reasoning_guards.before_diagnostic_transform(
                "reasoning_compile_diagnostic_reasoning", context,
                {"authority": "who5", "step_id": "diagnosis.who.compile"},
            )
        context["diagnosis_who_reasoning_validation"] = {"status": "pass"}
        reasoning_guards.before_diagnostic_transform(
            "reasoning_compile_diagnostic_reasoning", context,
            {"authority": "who5", "step_id": "diagnosis.who.compile"},
        )

    def test_ptbg_compiler_requires_reason_and_evidence_match_reviews_to_pass(self):
        context = {
            "prognosis_reasoning_validation": {"status": "pass"},
            "prognosis_evidence_match_validation": {"status": "fail"},
        }
        with self.assertRaisesRegex(ValueError, "prognosis.em.validate"):
            reasoning_guards.before_ptbg_transform(
                "reasoning_compile_ptbg_reasoning", context,
                {"domain": "prognosis", "step_id": "prognosis.compile"},
            )
        context["prognosis_evidence_match_validation"] = {"status": "pass"}
        reasoning_guards.before_ptbg_transform(
            "reasoning_compile_ptbg_reasoning", context,
            {"domain": "prognosis", "step_id": "prognosis.compile"},
        )


if __name__ == "__main__":
    unittest.main()
