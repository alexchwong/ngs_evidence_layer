"""Characterisation tests for the validated-model-task runner.

Written *before* the runner moved out of `step.py`, and asserting behaviour that
must be identical afterwards. The extraction is the riskiest change in the
programme because the self-handoff path only fails on the third CLI invocation
of a real run — which no ordinary unit test reaches. Test 8 reaches it.

Each test drives the runner through a fake IO surface, so none of them needs a
model, a corpus, or a real run directory.
"""
from __future__ import annotations

import unittest

from scripts.core import validated_model_task as vmt
from scripts.core.validated_model_task import Budgets, Suspend, TaskFailed, TaskIO, TaskRequest


class FakeIO:
    """A scriptable TaskIO. `responses` is consumed one per model call."""

    def __init__(self, responses, *, self_pipeline=False, syntax_responses=None):
        self.responses = list(responses)
        self.syntax_responses = list(syntax_responses or [])
        self.self_pipeline = self_pipeline
        self.state = {}
        self.output = None
        self.calls = []
        self.syntax_calls = []
        self.statuses = []
        self.attempts = []

    def io(self):
        return TaskIO(
            call_model=self._call_model,
            call_syntax_model=self._call_syntax,
            load_state=lambda k: dict(self.state.get(k) or {}),
            save_state=self._save,
            read_output=lambda: self.output,
            write_output=self._write,
            record_attempt=self.attempts.append,
            status=self.statuses.append,
            is_self=self.self_pipeline,
        )

    def _call_model(self, messages):
        self.calls.append(messages)
        if not self.responses:
            raise AssertionError("model called more times than the test scripted")
        return self.responses.pop(0)

    def _call_syntax(self, prompt, attempt):
        self.syntax_calls.append(prompt)
        if not self.syntax_responses:
            raise AssertionError("syntax model called more times than the test scripted")
        return self.syntax_responses.pop(0)

    def _save(self, key, value):
        if value:
            self.state[key] = dict(value)
        else:
            self.state.pop(key, None)

    def _write(self, text):
        self.output = text


def _request(validate, *, mode="standard", content=3, serialization=2, rewrite=1, fmt="yaml"):
    return TaskRequest(
        task_id="t1",
        messages=[{"role": "user", "content": "task"}],
        validate=validate,
        fmt=fmt,
        mode=mode,
        budgets=Budgets(content=content, serialization=serialization, rewrite=rewrite),
    )


def _ok(text):
    if "bad" in text:
        raise vmt.ValidationFailure("t1", [vmt.ValidationIssue("a", "is bad", "make it good")])
    return "valid"


# 1 -------------------------------------------------------------------------
def test_happy_path_writes_output_and_clears_state():
    fake = FakeIO(["a: good\n"])
    out = vmt.run(_request(_ok), fake.io())
    assert out.strip() == "a: good"
    assert fake.output.strip() == "a: good"
    assert fake.state == {}


# 2 -------------------------------------------------------------------------
def test_content_retry_replays_previous_artifact_then_feedback():
    fake = FakeIO(["a: bad\n", "a: good\n"])
    vmt.run(_request(_ok), fake.io())
    assert len(fake.calls) == 2
    second = fake.calls[1]
    assert second[-2]["role"] == "assistant" and "bad" in second[-2]["content"]
    assert second[-1]["role"] == "user" and "is bad" in second[-1]["content"]


# 3 -------------------------------------------------------------------------
def test_serialization_defects_go_to_the_syntax_model_not_the_clinical_one():
    def validate(text):
        import yaml

        doc = yaml.safe_load(text)
        if isinstance(doc.get("flag"), str):
            raise vmt.ValidationFailure(
                "t1",
                [vmt.ValidationIssue("flag", "quoted boolean", "unquote it", repair_class="serialization")],
            )
        return "valid"

    fake = FakeIO(['flag: "true"\n'], syntax_responses=["flag: true\n"])
    vmt.run(_request(validate), fake.io())
    assert len(fake.calls) == 1, "the clinical model must not be asked to fix serialization"
    assert len(fake.syntax_calls) == 1
    assert "unquote it" in fake.syntax_calls[0]


def test_mixed_defects_report_remaining_content_issues_after_serialization_repair():
    seen = []

    def validate(text):
        import yaml

        doc = yaml.safe_load(text)
        found = []
        if isinstance(doc.get("flag"), str):
            found.append(
                vmt.ValidationIssue("flag", "quoted boolean", "unquote it", repair_class="serialization")
            )
        if doc.get("name") == "wrong":
            found.append(vmt.ValidationIssue("name", "wrong value", "use the right one"))
        seen.append([i.repair_class for i in found])
        if found:
            raise vmt.ValidationFailure("t1", found)
        return "valid"

    fake = FakeIO(
        ['flag: "true"\nname: wrong\n', "flag: true\nname: right\n"],
        syntax_responses=["flag: true\nname: wrong\n"],
    )
    vmt.run(_request(validate), fake.io())
    # The clinical retry must carry the content issue, never the serialization one.
    retry_feedback = fake.calls[1][-1]["content"]
    assert "use the right one" in retry_feedback
    assert "unquote it" not in retry_feedback


# 4 -------------------------------------------------------------------------
def test_syntax_exhaustion_inside_a_proforma_triggers_a_fresh_restart():
    def validate(text):
        if "unfixable" in text:
            raise vmt.ValidationFailure(
                "t1",
                [vmt.ValidationIssue("a", "mis-serialized", "reserialize", repair_class="serialization")],
            )
        return "valid"

    fake = FakeIO(
        ["a: unfixable\n", "a: good\n"],
        syntax_responses=["a: unfixable\n", "a: unfixable\n"],
    )
    vmt.run(_request(validate, mode="proforma", serialization=2, rewrite=1), fake.io())
    restart = fake.calls[1]
    # A fresh restart regenerates from the original task and must NOT replay the
    # damaged artifact back to the model.
    assert all(m["role"] != "assistant" for m in restart)
    assert "from scratch" in restart[-1]["content"]


def test_content_failure_inside_a_proforma_triggers_a_repair_restart():
    fake = FakeIO(["a: bad\n", "a: good\n"])
    vmt.run(_request(_ok, mode="proforma", rewrite=1), fake.io())
    restart = fake.calls[1]
    assert restart[-2]["role"] == "assistant" and "bad" in restart[-2]["content"]


# 5 -------------------------------------------------------------------------
def test_rewrite_budget_exhaustion_raises_with_the_last_feedback():
    fake = FakeIO(["a: bad\n", "a: bad2\n"])
    with unittest.TestCase().assertRaises(TaskFailed) as exc:
        vmt.run(_request(_ok, mode="proforma", rewrite=1), fake.io())
    assert "is bad" in str(exc.exception)


def test_content_budget_exhaustion_raises():
    fake = FakeIO(["a: bad\n", "a: bad2\n", "a: bad3\n"])
    with unittest.TestCase().assertRaises(TaskFailed):
        vmt.run(_request(_ok, content=3), fake.io())


# 6 -------------------------------------------------------------------------
def test_truncation_asks_for_a_complete_regeneration_not_a_patch():
    fake = FakeIO([vmt.Truncated("a: partial", max_tokens=128), "a: good\n"])
    vmt.run(_request(_ok), fake.io())
    feedback = fake.calls[1][-1]["content"]
    assert "complete" in feedback.lower() and "128" in feedback
    assert "patch" not in feedback.lower() or "not a patch" in feedback.lower()


# 7 -------------------------------------------------------------------------
def test_identical_repeats_escalate_then_stop_early():
    fake = FakeIO(["a: bad\n", "a: bad\n", "a: bad\n", "a: bad\n", "a: bad\n"])
    with unittest.TestCase().assertRaises(TaskFailed) as exc:
        vmt.run(_request(_ok, content=5), fake.io())
    assert "same rejected artifact" in str(exc.exception)
    # Stopped early rather than spending the whole budget.
    assert len(fake.calls) < 5


def test_a_changed_artifact_resets_the_stagnation_counter():
    fake = FakeIO(["a: bad\n", "a: bad\n", "a: bad2\n", "a: good\n"])
    vmt.run(_request(_ok, content=5), fake.io())
    assert len(fake.calls) == 4


# 8 — the one that matters ---------------------------------------------------
def test_self_handoff_resumes_correctly_across_three_invocations():
    """Simulate the `self` pipeline: suspend, human writes a file, re-enter."""
    shared_state = {}
    output = {"text": None}

    def invoke(responses=None):
        fake = FakeIO(responses or [], self_pipeline=True)
        fake.state = shared_state
        fake.output = output["text"]
        io = fake.io()
        original_write = io.write_output
        try:
            return vmt.run(_request(_ok, mode="proforma", rewrite=2), io), fake
        finally:
            if fake.output is not None:
                output["text"] = fake.output

    # Invocation 1: nothing on disk, so the runner suspends asking for a response.
    with unittest.TestCase().assertRaises(Suspend) as first:
        invoke()
    assert first.exception.task_id == "t1"

    # A human writes an invalid response.
    output["text"] = "a: bad\n"

    # Invocation 2: finds it, rejects it, suspends again carrying the feedback.
    with unittest.TestCase().assertRaises(Suspend) as second:
        invoke()
    assert "is bad" in second.exception.feedback
    assert shared_state["t1"]["rewrites"] == 1, "rewrite index must survive the process boundary"

    # A human writes a valid response.
    output["text"] = "a: good\n"

    # Invocation 3: accepts, and clears the persisted retry state.
    result, fake = invoke()
    assert result.strip() == "a: good"
    assert shared_state.get("t1") in (None, {})


def test_self_handoff_stagnation_counter_survives_the_process_boundary():
    shared_state = {}
    output = {"text": "a: bad\n"}

    def invoke():
        fake = FakeIO([], self_pipeline=True)
        fake.state = shared_state
        fake.output = output["text"]
        return vmt.run(_request(_ok, mode="proforma", rewrite=5), fake.io())

    with unittest.TestCase().assertRaises(Suspend):
        invoke()
    first = shared_state["t1"].get("stagnation_repeats")
    with unittest.TestCase().assertRaises(Suspend):
        invoke()
    assert shared_state["t1"]["stagnation_repeats"] > first


# 9 -------------------------------------------------------------------------
def test_self_handoff_with_exhausted_budget_fails_rather_than_looping():
    shared_state = {"t1": {"rewrites": 1, "mode": "repair", "feedback": "prior"}}
    fake = FakeIO([], self_pipeline=True)
    fake.state = shared_state
    fake.output = "a: bad\n"
    with unittest.TestCase().assertRaises(TaskFailed):
        vmt.run(_request(_ok, mode="proforma", rewrite=1), fake.io())


# Portability ----------------------------------------------------------------
def test_runner_contains_no_workflow_specific_vocabulary():
    from pathlib import Path

    import re

    source = Path(vmt.__file__).read_text().lower()
    for term in ("diagnosis", "prognosis", "variant", "terraced", "clinical", "card_id"):
        # Word-boundary matched: "invariants" legitimately contains "variant".
        assert not re.search(rf"\b{term}\b", source), f"runner leaked workflow vocabulary: {term}"


def test_runner_performs_no_filesystem_access():
    import ast
    from pathlib import Path

    tree = ast.parse(Path(vmt.__file__).read_text())
    banned = {"open", "Path", "write_text", "read_text", "mkdir", "unlink"}
    used = {
        node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert not (used & banned), f"runner touched the filesystem directly: {sorted(used & banned)}"


def load_tests(loader, tests, pattern):
    """Expose the characterisation functions to standard-library unittest."""
    suite = unittest.TestSuite()
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            suite.addTest(unittest.FunctionTestCase(value, description=name))
    return suite


if __name__ == "__main__":
    unittest.main()
