"""Post-report automatic validation marking for proforma-v1 executors.

Validation owns the evaluator contract and deterministic artifacts. This module
owns model execution so provider/self mechanics never leak into validation code.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.core import validated_model_task
from validation.scripts import package_marking as marking
from workflows.proforma_v1 import layout, model_client, model_observability, step as staged

LOGICAL_OPERATION = "validation.marking"


def _state(work: Path) -> tuple[str, str]:
    state = staged._load_run_state(work)
    mode = str(state.get("mode") or "")
    case_id = state.get("validation_case")
    return mode, case_id


def _self_handoff(work: Path, prep: dict, *, binding) -> dict:
    mode = prep["suite"]
    case_id = prep["case"]
    digest = prep["report_sha256"]
    call_id = prep["call_id"]
    output = Path(prep["output"])
    prompt = str(prep["prompt"])
    if not binding.is_self:
        raise staged.StepFailure("self marking handoff requires the self pipeline")

    status = marking.read_marking_status(work)
    attempt = max(1, int(status.get("attempt") or 1))
    root = layout.model_step_dir(work, call_id, existing=False)
    observed = model_observability.attempt_dir(root, attempt, create=False)
    previous = None
    feedback = None

    # Re-entering before the host has written an answer must replay the existing
    # handoff rather than overwrite attempt metadata/start time.
    if not output.is_file() and (observed / "call.json").is_file():
        prompt_path = observed / "prompt.md"
        if not prompt_path.is_file():
            raise staged.StepFailure(f"marking attempt metadata exists without prompt for {call_id}")
        marking.set_automatic_marking_pending(work, mode, case_id, digest, call_id, attempt)
        staged._refresh_model_operation_index(work)
        raise staged.Handoff(call_id, prompt_path, output)

    if output.is_file():
        previous = output.read_text(encoding="utf-8")
        if not (observed / "call.json").is_file():
            # A manually materialised output without its handoff metadata is not
            # accepted as an unobserved model attempt.
            output.unlink(missing_ok=True)
            raise staged.StepFailure(f"marking output exists without attempt metadata for {call_id}")
        model_observability.write_raw_output(observed, previous)
        try:
            result = marking.complete_automatic_marking(
                work, mode, case_id, previous, digest, call_id
            )
        except Exception as exc:
            feedback = validated_model_task.retry_instruction(exc)
            model_observability.write_validation(observed, accepted=False, detail=str(exc))
            model_observability.finish_attempt(observed, status="rejected", validation_error=str(exc))
            model_observability.sync_root_compatibility_view(root, observed)
            staged._refresh_model_operation_index(work)
            output.unlink(missing_ok=True)
            limit = staged._retry("fatal_model_attempts")
            if attempt >= limit:
                marking.fail_automatic_marking(work, mode, case_id, digest, call_id, exc)
                raise staged.StepFailure(
                    f"{call_id} failed validation after {limit} attempt(s): {exc}"
                ) from exc
            attempt += 1
        else:
            model_observability.write_validation(observed, accepted=True)
            model_observability.finish_attempt(observed, status="accepted")
            model_observability.sync_root_compatibility_view(root, observed)
            staged._refresh_model_operation_index(work)
            return result

    messages = [
        {"role": "system", "content": model_client.SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    if previous is not None and feedback:
        messages += [
            {"role": "assistant", "content": previous},
            {"role": "user", "content": feedback},
        ]
    rendered = staged._render_bundle(call_id, messages, output, feedback)
    observed = model_observability.begin_attempt(
        root,
        attempt,
        messages=messages,
        prompt=rendered,
        metadata={
            "logical_operation": LOGICAL_OPERATION,
            "call_id": call_id,
            "call_kind": "model",
            "role": "marking",
            "provider": "self",
            "model": binding.model,
        },
    )
    model_observability.sync_root_compatibility_view(root, observed)
    staged._refresh_model_operation_index(work)
    marking.set_automatic_marking_pending(work, mode, case_id, digest, call_id, attempt)
    raise staged.Handoff(call_id, root / "prompt.md", output)



def _run_provider_marking(work: Path, prep: dict, *, binding, profile: str | None, validator):
    """Run marking through the shared task runner while preserving Markdown fences.

    Marking is a mixed Markdown document whose contract deliberately includes a
    fenced JSON block. The generic unstructured model path strips a surrounding
    fence and can therefore consume the closing fence of the required JSON block
    when a model wraps the whole response in ```markdown. This adapter keeps the
    response byte-for-byte apart from normal trailing-newline normalization.
    """
    call_id = str(prep["call_id"])
    output = Path(prep["output"])
    prompt = str(prep["prompt"])
    syntax_binding = staged._profile(work, profile, "syntax_repair")
    root = layout.model_step_dir(work, call_id, existing=False)
    messages = [
        {"role": "system", "content": model_client.SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    request = validated_model_task.TaskRequest(
        task_id=call_id,
        messages=messages,
        validate=validator,
        fmt=None,
        mode="standard",
        prepare=lambda raw: str(raw).rstrip() + "\n",
        budgets=validated_model_task.Budgets(
            content=staged._retry("fatal_model_attempts"),
            serialization=staged._retry("syntax_repair_attempts"),
            rewrite=staged._retry("proforma_rewrite_attempts"),
        ),
    )
    io = staged._task_io(
        work,
        call_id=call_id,
        role="marking",
        binding=binding,
        syntax_binding=syntax_binding,
        output=output,
        root=root,
    )
    try:
        candidate = validated_model_task.run(request, io)
    except validated_model_task.Suspend as suspend:
        # A non-self binding must not suspend, but preserve the standard failure
        # shape if a provider profile is malformed.
        staged._write(root / "messages.json", json.dumps(suspend.messages, indent=2, ensure_ascii=False) + "\n")
        staged._write(root / "prompt.md", staged._render_bundle(call_id, suspend.messages, output, suspend.feedback or None))
        raise staged.Handoff(call_id, root / "prompt.md", output) from suspend
    except validated_model_task.TaskFailed as exc:
        raise staged.StepFailure(str(exc)) from exc
    staged._write(root / "validated.txt", "accepted\n")
    return candidate

def run(work: Path, *, profile: str | None = None) -> dict:
    """Advance automatic marking without changing clinical completion semantics."""
    work = Path(work).resolve()
    mode, case_id = _state(work)
    try:
        prep = marking.prepare_automatic_marking(work, mode, case_id)
    except Exception as exc:
        # Preparation errors occur only after the report gate for validation
        # suites. Record them as sidecar failure where enough identity exists.
        try:
            if marking.is_validation_mode(mode):
                digest = marking.report_sha256(work / "report-final.md")
                call_id = marking.next_call_id(work, digest)
                marking.fail_automatic_marking(work, mode, str(case_id), digest, call_id, exc)
        except Exception:
            pass
        raise
    if prep.get("status") != "pending":
        return prep

    call_id = prep["call_id"]
    digest = prep["report_sha256"]
    try:
        binding = staged._profile(work, profile, "marking")
    except Exception as exc:
        marking.fail_automatic_marking(work, mode, prep["case"], digest, call_id, exc)
        raise
    if binding.is_self:
        return _self_handoff(work, prep, binding=binding)

    output = Path(prep["output"])

    def validator(text: str) -> str:
        marking.validate_marking_output(mode, prep["case"], text, report_digest=digest)
        return f"{mode} case {prep['case']} marking valid"

    try:
        _run_provider_marking(
            work, prep, binding=binding, profile=profile, validator=validator
        )
        return marking.complete_automatic_marking(
            work, mode, prep["case"], output.read_text(encoding="utf-8"), digest, call_id
        )
    except staged.Handoff:
        raise
    except Exception as exc:
        marking.fail_automatic_marking(work, mode, prep["case"], digest, call_id, exc)
        raise
