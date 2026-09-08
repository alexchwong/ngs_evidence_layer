"""Shared logical workflow runner consumed by provider and self executors."""
from __future__ import annotations

from dataclasses import dataclass
import copy
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, NoReturn

from workflows.proforma_v1.engine import control_state
from workflows.proforma_v1.engine.context import WorkflowContext
from workflows.proforma_v1.engine.workflow_progress import WorkflowProgress


def _dig(value: Any, path: str) -> Any:
    cur = value
    for part in path.split(".") if path else []:
        cur = cur.get(part) if isinstance(cur, dict) else None
    return cur


def condition_applies(condition: dict | None, context: WorkflowContext) -> bool:
    if not condition:
        return True
    if "has_items" in condition:
        return bool(context.get(condition["has_items"].get("artifact")))
    if "artifact_true" in condition:
        value = condition["artifact_true"]
        name = value if isinstance(value, str) else value.get("artifact")
        return bool(context.get(name))
    if "artifact_changed" in condition:
        value = condition["artifact_changed"]
        name = value if isinstance(value, str) else value.get("artifact")
        return bool(context.get(f"{name}__changed"))
    if "setting" in condition:
        spec = condition["setting"]
        return _dig(context.get("settings", {}), spec.get("path", "")) == spec.get("equals")
    if "predicate" in condition:
        predicates = context.get("predicates", {}) or {}
        fn = predicates.get(condition["predicate"])
        return bool(fn(context) if callable(fn) else False)
    return False


def executor_enabled(step, executor_name: str) -> bool:
    cfg = (step.execution or {}).get(executor_name) or {}
    return cfg.get("enabled", True) is not False



TERMINAL_WORKFLOW_EXIT_CODE = 3


class TerminalWorkflowFailure(SystemExit):
    """Non-retryable workflow failure after an explicit terminal review policy.

    ``step.main`` catches ordinary ``Exception`` and maps it to exit 1.  A
    ``SystemExit`` subclass deliberately bypasses that generic mapping so the
    UI/CLI launcher can distinguish a persisted semantic terminal from a
    transient/retryable run failure.
    """

    retryable = False

    def __init__(self, message: str, *, reviewer: str | None = None):
        self.message = str(message)
        self.reviewer = reviewer
        super().__init__(TERMINAL_WORKFLOW_EXIT_CODE)

    def __str__(self) -> str:
        return self.message


def raise_terminal_failure(
    context: WorkflowContext, *, reviewer: str, message: str
) -> NoReturn:
    """Record a non-retryable terminal failure, then raise it.

    Any caller that stops a run for a semantic reason must go through here, not
    raise :class:`TerminalWorkflowFailure` directly.  The exception carries the
    failure to the current process; ``logs/workflow-failure.json`` lets the UI
    and batch layers recognise it as non-retryable afterwards.
    """
    path = Path(context.work) / "logs" / "workflow-failure.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({
        "schema_version": 1,
        "failure_class": "terminal_review",
        "retryable": False,
        "reviewer": reviewer,
        "message": str(message),
        "exit_code": TERMINAL_WORKFLOW_EXIT_CODE,
    }, indent=2, ensure_ascii=False) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with open(descriptor, "w", encoding="utf-8", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    control_state.save(context)
    print(f"proforma-v1 terminal failure: {message}", file=sys.stderr, flush=True)
    raise TerminalWorkflowFailure(message, reviewer=reviewer)


def _jsonable_copy(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False))
    except Exception:
        return copy.deepcopy(value)


def _issue_paths(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    out = []
    for row in value.get("issues") or []:
        if isinstance(row, dict) and isinstance(row.get("path"), str) and row["path"].strip():
            out.append(row["path"].strip())
    return out


def _path_parent(path: str) -> str:
    """Return the immediate object scope that owns one reported field defect."""
    value = str(path or "$").strip() or "$"
    if value == "$":
        return "$"
    # Remove one final '.field' or '[index]' segment.  If a validator points at
    # an object itself (common for schema-required), allowing that object is the
    # narrowest useful repair scope.
    m = re.match(r"^(.*?)(?:\.[A-Za-z_][A-Za-z0-9_]*|\[[0-9]+\])$", value)
    return (m.group(1) if m else value) or "$"


def _join_path(base: str, key: Any) -> str:
    if isinstance(key, int):
        return f"{base}[{key}]"
    name = str(key)
    return f"{base}.{name}" if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) else f"{base}[{name!r}]"


def _diff_paths(before: Any, after: Any, path: str = "$") -> list[str]:
    if type(before) is not type(after):
        return [path]
    if isinstance(before, dict):
        out = []
        for key in sorted(set(before) | set(after), key=str):
            child = _join_path(path, key)
            if key not in before or key not in after:
                out.append(child)
            else:
                out.extend(_diff_paths(before[key], after[key], child))
        return out
    if isinstance(before, list):
        out = []
        n = max(len(before), len(after))
        for index in range(n):
            child = _join_path(path, index)
            if index >= len(before) or index >= len(after):
                out.append(child)
            else:
                out.extend(_diff_paths(before[index], after[index], child))
        return out
    return [] if before == after else [path]


def _within_scope(path: str, scope: str) -> bool:
    if scope == "$":
        return True
    return path == scope or path.startswith(scope + ".") or path.startswith(scope + "[")

@dataclass(frozen=True)
class RunResult:
    status: str
    step_id: str | None = None
    handoff: Any = None


class WorkflowRunner:
    def __init__(self, workflow, executor, *, trace=None):
        self.workflow = workflow
        self.executor = executor
        self.trace = trace
        # Construction validates the workflow-specific progress presentation plan
        # before an executor can make a model call.
        self.progress = WorkflowProgress(workflow)

    def _bind_progress(self, context: WorkflowContext) -> None:
        self.progress.bind(context)

    def _record(self, step, status: str, **fields):
        if self.trace is not None:
            self.trace.record(step.id, step.type, status, dependencies=list(step.needs), **fields)

    def _step_done(self, context: WorkflowContext, step_id: str) -> bool:
        """Hydrate completion while respecting persisted terminal review state."""
        self._bind_progress(context)
        step = self.workflow.step(step_id)
        terminal = self._review_terminal(context, step_id) if step.review else None
        if terminal:
            action = terminal.get("action")
            if action == "stop":
                message = terminal.get("message") or f"review {step_id!r} is terminally failed"
                self.progress.update(step_id, "failed", reason="review_terminal_stop", error=message)
                self._raise_terminal(context, step_id, message)
            self._restore_terminal_effects(step, context, terminal)
            context.completed.add(step_id)
            self.progress.update(step_id, "completed", reason=f"review_terminal_{action or 'continue'}")
            return True
        if step_id in context.completed:
            if self.progress.status(step_id) not in {"completed", "skipped"}:
                self.progress.update(step_id, "completed", reason="already_complete")
            return True
        complete = getattr(self.executor, "is_complete", None)
        if not callable(complete) or not complete(step_id, context):
            return False
        if step.review:
            artifact_name = (step.output or {}).get("artifact")
            artifact = context.get(artifact_name) if artifact_name else None
            if not self._review_passed(step, context, {"artifact": artifact}):
                self.progress.update(step_id, "failed", reason="persisted_review_failed")
                return False
        context.completed.add(step_id)
        self.progress.update(step_id, "completed", reason="artifact_complete")
        return True

    def _ready(self, step, context: WorkflowContext) -> bool:
        return all(self._step_done(context, need) for need in step.needs)

    def _ready_group(self, step, context: WorkflowContext) -> list:
        group = (step.execution or {}).get("self_group")
        if not group or context.executor != "self":
            return [step]
        members = []
        for candidate in self.workflow.steps:
            if candidate.id in context.completed:
                continue
            if (candidate.execution or {}).get("self_group") != group:
                continue
            if not executor_enabled(candidate, context.executor):
                continue
            if self._ready(candidate, context) and condition_applies(candidate.when, context):
                members.append(candidate)
        return members or [step]

    def _review_passed(self, step, context: WorkflowContext, result: dict) -> bool:
        review = step.review
        if not review:
            return True
        verdict = review["verdict"]
        if "predicate" in verdict:
            predicates = context.get("review_predicates", {}) or context.get("predicates", {}) or {}
            fn = predicates.get(verdict["predicate"])
            if not callable(fn):
                raise RuntimeError(f"review predicate {verdict['predicate']!r} is unavailable for {step.id!r}")
            return bool(fn(step, context, result))
        artifact = result.get("artifact")
        if artifact is None:
            artifact_name = (step.output or {}).get("artifact")
            artifact = context.get(artifact_name) if artifact_name else None
        return _dig(artifact, verdict.get("path", "")) in verdict.get("pass_values", [])

    def _descendants_through(self, target_id: str, reviewer_id: str) -> set[str]:
        invalid = {target_id}
        changed = True
        while changed:
            changed = False
            for step in self.workflow.steps:
                if step.id == reviewer_id:
                    continue
                if step.id in invalid:
                    continue
                if any(need in invalid for need in step.needs):
                    invalid.add(step.id)
                    changed = True
        invalid.add(reviewer_id)
        return invalid

    def _append_review_event(self, context: WorkflowContext, **event) -> None:
        events = list(context.get("review_events", []) or [])
        events.append(event)
        context.put("review_events", events)

    def _set_redo_preservation(self, step, context: WorkflowContext, result: dict) -> None:
        review = step.review or {}
        target = self.workflow.step(review["target"])
        artifact_name = (target.output or {}).get("artifact")
        baseline = context.get(artifact_name) if artifact_name else None
        review_artifact = result.get("artifact")
        if review_artifact is None:
            review_name = (step.output or {}).get("artifact")
            review_artifact = context.get(review_name) if review_name else None
        paths = _issue_paths(review_artifact)
        if baseline is None or not paths:
            return
        scopes = sorted(set(_path_parent(path) for path in paths))
        values = dict(context.get("redo_preservation", {}) or {})
        values[step.id] = {
            "reviewer": step.id,
            "target": target.id,
            "artifact": artifact_name,
            "baseline": _jsonable_copy(baseline),
            "issue_paths": paths,
            "allowed_scopes": scopes,
        }
        context.put("redo_preservation", values)

    def _preservation_issues(self, step, context: WorkflowContext) -> list[dict]:
        values = context.get("redo_preservation", {}) or {}
        record = values.get(step.id) if isinstance(values, dict) else None
        if not isinstance(record, dict):
            return []
        artifact_name = record.get("artifact")
        current = context.get(artifact_name) if artifact_name else None
        baseline = record.get("baseline")
        if current is None or baseline is None:
            return []
        scopes = [str(x) for x in record.get("allowed_scopes") or []]
        unexpected = [path for path in _diff_paths(baseline, current) if not any(_within_scope(path, scope) for scope in scopes)]
        return [
            {
                "code": "unexpected_redo_change",
                "path": path,
                "message": "semantic redo changed content outside the scope of the deterministic feedback",
                "fix": "restore the prior value outside the reported repair scope; change unrelated clinical content only when the reported defect requires that same object to change",
            }
            for path in unexpected
        ]

    def _apply_preservation_review(self, step, context: WorkflowContext, result: dict) -> dict:
        issues = self._preservation_issues(step, context)
        if not issues:
            if self._review_passed(step, context, result):
                values = dict(context.get("redo_preservation", {}) or {})
                if step.id in values:
                    values.pop(step.id, None)
                    context.put("redo_preservation", values)
            return result
        artifact = result.get("artifact")
        if artifact is None:
            artifact_name = (step.output or {}).get("artifact")
            artifact = context.get(artifact_name) if artifact_name else None
        if not isinstance(artifact, dict):
            artifact = {}
        merged = [*(artifact.get("issues") or []), *issues]
        updated = dict(artifact)
        updated["status"] = "fail"
        updated["issue_count"] = len(merged)
        updated["issues"] = merged
        lines = [
            f"The semantic redo changed {len(issues)} unrelated path{'s' if len(issues) != 1 else ''}. "
            "Repair only within the objects named by the original deterministic feedback:"
        ]
        for index, issue in enumerate(issues, 1):
            lines.append(f"{index}. {issue['path']}: {issue['message']}. {issue['fix']}.")
        updated["feedback"] = "\n".join(lines) + "\n"
        result = {**result, "artifact": updated}
        artifact_name = (step.output or {}).get("artifact")
        if artifact_name:
            context.put(artifact_name, updated)
        return result

    def _raise_terminal(self, context: WorkflowContext, step_id: str, message: str) -> None:
        raise_terminal_failure(context, reviewer=step_id, message=message)

    def _review_terminal(self, context: WorkflowContext, step_id: str) -> dict | None:
        values = context.get("review_terminal", {}) or {}
        row = values.get(step_id) if isinstance(values, dict) else None
        if isinstance(row, str):
            return {"action": row}
        return row if isinstance(row, dict) else None

    def _set_review_terminal(self, context: WorkflowContext, step, *, action: str, **fields) -> dict:
        values = dict(context.get("review_terminal", {}) or {})
        row = {
            "action": action,
            "target": (step.review or {}).get("target"),
            **{key: value for key, value in fields.items() if value is not None},
        }
        values[step.id] = row
        context.put("review_terminal", values)
        return row

    def _clear_review_terminals(self, context: WorkflowContext, step_ids) -> None:
        values = dict(context.get("review_terminal", {}) or {})
        changed = False
        for step_id in step_ids:
            if step_id in values:
                values.pop(step_id, None)
                changed = True
        if changed:
            context.put("review_terminal", values)

    def _restore_terminal_effects(self, step, context: WorkflowContext, terminal: dict) -> None:
        action = terminal.get("action")
        target = terminal.get("target") or (step.review or {}).get("target")
        if action == "continue_with_dissent":
            context.put(f"{step.id}__dissent", True)
        elif action == "suppress" and target:
            context.put(f"{target}__suppressed", True)

    def _complete_terminal_review(self, step, context: WorkflowContext, terminal: dict) -> None:
        self._restore_terminal_effects(step, context, terminal)
        context.completed.add(step.id)
        self.progress.update(step.id, "completed", reason=f"review_terminal_{terminal.get('action')}")
        self._record(
            step, "complete", reason=f"review_terminal_{terminal.get('action')}",
            executor=context.executor, review_terminal=terminal,
        )

    def _handle_review_failure(self, step, context: WorkflowContext, result: dict) -> RunResult | None:
        review = step.review
        on_fail = review["on_fail"]

        persisted = self._review_terminal(context, step.id)
        if persisted:
            if persisted.get("action") == "stop":
                message = persisted.get("message") or f"review {step.id!r} is terminally failed"
                self._raise_terminal(context, step.id, message)
            self._complete_terminal_review(step, context, persisted)
            control_state.save(context)
            if persisted.get("action") == "route_to" and persisted.get("route_to"):
                if not context.get("forced_route"):
                    context.put("forced_route", persisted["route_to"])
                return RunResult("pending", persisted["route_to"])
            return None

        if on_fail.get("retry_target"):
            cycles = dict(context.get("review_cycles", {}) or {})
            used_cycles = int(cycles.get(step.id, 0))
            max_cycles = int(on_fail["max_cycles"])
            if used_cycles < max_cycles:
                count = used_cycles + 1
                cycles[step.id] = count
                context.put("review_cycles", cycles)
                feedback = on_fail.get("feedback") or {}
                if feedback:
                    source = feedback["from"]
                    if source.startswith("artifacts."):
                        value = context.get(source.split(".", 1)[1])
                    else:
                        value = result.get("artifact")
                    # An optional ``path`` narrows what the target actually
                    # receives.  A reviewer artifact usually carries routing and
                    # control fields alongside the material the target needs;
                    # sending the whole object would leak the verdict into the
                    # prompt of the model being asked to reconsider.
                    if feedback.get("path"):
                        value = _dig(value, str(feedback["path"]))
                    target = self.workflow.step(review["target"])
                    binding = (target.inputs or {}).get(feedback["as"]) or {}
                    ref = binding.get("from")
                    if not isinstance(ref, str) or not ref.startswith("feedback."):
                        raise RuntimeError(
                            f"review feedback alias {feedback['as']!r} on {target.id!r} is not bound to feedback.*"
                        )
                    fb = dict(context.get("feedback_values", {}) or {})
                    fb[ref] = value
                    context.put("feedback_values", fb)
                self._set_redo_preservation(step, context, result)
                invalid = self._descendants_through(review["target"], step.id)
                context.completed.difference_update(invalid)
                self._clear_review_terminals(context, invalid)
                self.progress.invalidate(invalid)
                invalidate = getattr(self.executor, "invalidate", None)
                if callable(invalidate):
                    invalidate(invalid, context)
                self._append_review_event(
                    context,
                    reviewer=step.id,
                    target=review["target"],
                    cycle=count,
                    max_cycles=max_cycles,
                    action="retry",
                    invalidated_steps=sorted(invalid),
                )
                self._record(
                    step, "feedback", reason="review_failed_retry", target=review["target"],
                    cycle=count, invalidated_steps=sorted(invalid),
                )
                control_state.save(context)
                return RunResult("pending", review["target"])

            exhausted = on_fail.get("exhausted") or {"action": "stop"}
            action = exhausted.get("action", "stop")
            message = (
                f"review {step.id!r} failed after {max_cycles} feedback cycle(s)"
                if action == "stop" else None
            )
            terminal = self._set_review_terminal(
                context, step, action=action, cycle=used_cycles, max_cycles=max_cycles,
                route_to=exhausted.get("route_to"), message=message,
            )
            self._append_review_event(
                context,
                reviewer=step.id,
                target=review["target"],
                cycle=used_cycles,
                max_cycles=max_cycles,
                action=f"exhausted:{action}",
                invalidated_steps=[],
            )
            if action == "stop":
                self._raise_terminal(context, step.id, message)
            if action == "route_to":
                route = exhausted.get("route_to")
                context.put("forced_route", route)
            elif action == "suppress":
                context.put(f"{review['target']}__suppressed", True)
            elif action == "continue_with_dissent":
                context.put(f"{step.id}__dissent", True)
            else:
                raise RuntimeError(f"review {step.id!r} has unsupported exhausted action {action!r}")
            self._complete_terminal_review(step, context, terminal)
            control_state.save(context)
            if action == "route_to" and exhausted.get("route_to"):
                return RunResult("pending", exhausted["route_to"])
            return None

        if on_fail.get("route_to"):
            route = on_fail["route_to"]
            terminal = self._set_review_terminal(context, step, action="route_to", route_to=route, cycle=0, max_cycles=0)
            context.put("forced_route", route)
            self._append_review_event(
                context, reviewer=step.id, target=review.get("target"), cycle=0,
                max_cycles=0, action=f"route_to:{route}", invalidated_steps=[],
            )
            self._complete_terminal_review(step, context, terminal)
            self._record(step, "review_failed", reason="route_to", route_to=route)
            control_state.save(context)
            return RunResult("pending", route)
        raise RuntimeError(f"review {step.id!r} has no executable on_fail policy")

    def _execute_one(self, step, context: WorkflowContext) -> RunResult | None:
        self._bind_progress(context)
        if not executor_enabled(step, context.executor):
            context.completed.add(step.id)
            self.progress.update(step.id, "skipped", reason="executor_disabled")
            self._record(step, "skipped", reason="executor_disabled", executor=context.executor)
            return None
        if not condition_applies(step.when, context):
            context.completed.add(step.id)
            self.progress.update(step.id, "skipped", reason="condition_false")
            self._record(step, "skipped", reason="condition_false", executor=context.executor)
            return None
        group_steps = self._ready_group(step, context)
        if len(group_steps) > 1 and hasattr(self.executor, "execute_group"):
            for member in group_steps:
                self.progress.update(member.id, "running", coalesced_group=(member.execution or {}).get("self_group"))
            try:
                result = self.executor.execute_group(group_steps, context) or {}
            except Exception as exc:
                for member in group_steps:
                    self.progress.update(member.id, "failed", error=str(exc))
                raise
            status = result.get("status", "complete")
            if status == "handoff":
                for member in group_steps:
                    self._record(member, "handoff", executor=context.executor, coalesced_group=(member.execution or {}).get("self_group"))
                return RunResult("handoff", step.id, result.get("handoff"))
            if status not in {"complete", "skipped"}:
                for member in group_steps:
                    self.progress.update(member.id, "failed", error=f"invalid executor status {status!r}")
                raise RuntimeError(f"executor returned invalid group status {status!r}")
            progress_status = "completed" if status == "complete" else "skipped"
            for member in group_steps:
                context.completed.add(member.id)
                self.progress.update(member.id, progress_status, reason=result.get("reason"))
                self._record(member, status, executor=context.executor, coalesced_group=(member.execution or {}).get("self_group"), reason=result.get("reason"))
            return None

        self.progress.update(step.id, "running")
        try:
            result = self.executor.execute(step, context) or {}
            status = result.get("status", "complete")
            if status in {"complete", "skipped"}:
                if status == "complete" and step.review:
                    result = self._apply_preservation_review(step, context, result)
                if status == "complete" and step.review and not self._review_passed(step, context, result):
                    self.progress.update(step.id, "failed", reason="review_failed")
                    return self._handle_review_failure(step, context, result)
                context.completed.add(step.id)
                progress_status = "completed" if status == "complete" else "skipped"
                self.progress.update(step.id, progress_status, reason=result.get("reason"))
                self._record(step, status, reason=result.get("reason"), executor=context.executor, coalesced_group=result.get("coalesced_group"))
                return None
            if status == "handoff":
                self._record(step, "handoff", executor=context.executor)
                return RunResult("handoff", step.id, result.get("handoff"))
            raise RuntimeError(f"executor returned invalid status {status!r} for {step.id!r}")
        except Exception as exc:
            # A review feedback cycle intentionally returns pending above; only
            # true exceptions reach this marker.
            self.progress.update(step.id, "failed", error=str(exc))
            raise

    def advance(self, context: WorkflowContext) -> RunResult:
        self._bind_progress(context)
        forced = context.get("forced_route")
        if forced:
            context.put("forced_route", None)
            step = self.workflow.step(forced)
            if not self._ready(step, context):
                raise RuntimeError(f"forced route {forced!r} is not runnable")
            routed = self._execute_one(step, context)
            if routed:
                return routed
        for step in self.workflow.steps:
            if step.id in context.completed:
                continue
            # Dependencies must be valid before a persisted descendant artifact
            # is allowed to hydrate as complete. This prevents stale descendants
            # from bypassing a failed blocking review on resume.
            if not self._ready(step, context):
                continue
            if self._step_done(context, step.id):
                continue
            result = self._execute_one(step, context)
            if result:
                return result
        if len(context.completed) == len(self.workflow.steps):
            return RunResult("complete")
        return RunResult("pending")

    def run_all(self, context: WorkflowContext) -> RunResult:
        # Provider runs are separate processes across nel.py outer retries. The
        # same review budget/feedback state used by native-self must therefore
        # be hydrated and saved here as well, including on failure.
        control_state.hydrate(context)
        try:
            while True:
                result = self.advance(context)
                if result.status != "pending":
                    if result.status == "handoff":
                        raise RuntimeError(f"provider/full runner cannot stop at self handoff {result.step_id!r}")
                    return result
        finally:
            control_state.save(context)
            if self.trace is not None:
                try:
                    self.trace.write(Path(context.work) / "logs" / "workflow-trace.json")
                except Exception:
                    # Trace persistence must not mask the clinical/workflow error.
                    pass
