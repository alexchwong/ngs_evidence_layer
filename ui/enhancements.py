"""Focused UX/server enhancements for the NEL browser interface.

This module deliberately layers on top of :mod:`ui.server` rather than copying
workflow or provider logic into the browser.  It adds small read-only endpoints,
clearer profile terminology, masked key status, and bounded same-run retries.
"""
from __future__ import annotations

import os
import re
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

MAX_RUN_ATTEMPTS = 3
ALIAS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def mask_secret(value: str) -> str:
    """Return a useful identifier for a secret without returning the secret."""
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= 8:
        return text[:4] + "…"
    if len(text) <= 12:
        return text[:8] + "…"
    return f"{text[:8]}…{text[-4:]}"


def validate_alias_name(alias: Any, *, index: int | None = None) -> str:
    """Validate the browser's intentionally filename-like model alias syntax."""
    value = str(alias or "").strip()
    where = f"Model alias {index}" if index is not None else "Model alias"
    if not value:
        raise ValueError(f"{where} is required")
    if not ALIAS_RE.fullmatch(value):
        raise ValueError(
            f"{where} {value!r} is invalid: use letters, numbers, '.', '_' or '-' "
            "with no spaces, for example 'gptoss20b' or 'qwen_next'"
        )
    return value


NON_RETRYABLE_RUN_ERRORS = (
    "configuration check failed",
    "current corpus differs from the corpus captured at setup",
    "run configuration snapshot is missing",
    "frozen corpus user layer does not match",
    "unsupported or missing run workflow",
    "cannot determine pipeline for run",
    "failed validation",
)


def should_retry(*, phase: str, returncode: int | None, attempt: int,
                 max_attempts: int = MAX_RUN_ATTEMPTS, stop_requested: bool = False,
                 output: str = "") -> bool:
    """Pure retry policy used by the registry and unit tests.

    Deterministic configuration/frozen-input failures are deliberately not
    retried; they require operator action rather than another provider call.
    """
    text = str(output or "").lower()
    deterministic_failure = any(marker in text for marker in NON_RETRYABLE_RUN_ERRORS)
    return bool(
        phase == "run"
        and returncode not in (None, 0)
        and attempt < max_attempts
        and not stop_requested
        and not deterministic_failure
    )


def _read_artifact(server, run_id: str, relative: str) -> dict[str, Any]:
    run_id = server.check_run_id(run_id)
    path = server.safe_child(server.run_dir(run_id), relative)
    if not path.is_file():
        return {"exists": False, "text": "", "path": relative}
    size = path.stat().st_size
    with open(path, "rb") as handle:
        data = handle.read(server.MAX_FILE_BYTES)
    return {
        "exists": True,
        "text": data.decode("utf-8", errors="replace"),
        "path": relative,
        "size": size,
        "truncated": size > server.MAX_FILE_BYTES,
    }


def _read_dissent(server, run_id: str) -> dict[str, Any]:
    """Read the canonical dissent artifact, tolerating a nested future location."""
    direct = _read_artifact(server, run_id, "dissent.md")
    if direct["exists"]:
        return direct
    base = server.run_dir(server.check_run_id(run_id))
    if not base.is_dir():
        raise server.UIError(f"run not found: {run_id}", 404)
    matches = sorted(path for path in base.rglob("dissent.md") if path.is_file())
    if not matches:
        return {"exists": False, "text": "", "path": "dissent.md"}
    relative = matches[0].relative_to(base).as_posix()
    return _read_artifact(server, run_id, relative)


def _case_preview(server, mode: str, selector: str) -> dict[str, Any]:
    mode = str(mode or "").strip()
    selector = str(selector or "").strip()
    if not mode or not selector:
        raise server.UIError("choose a bundled suite and case before previewing it")
    try:
        bundled = server._bundled()
        if not bundled.is_bundled_mode(mode):
            raise ValueError(f"unsupported bundled mode: {mode}")
        text = bundled.retrieve_case_input(mode, selector)
    except (KeyError, ValueError, FileNotFoundError) as exc:
        raise server.UIError(str(exc)) from exc
    # retrieve_case_input is deliberately the clinical-input-only API.  Never
    # call retrieve_marking_criteria from this UI path.
    return {"mode": mode, "selector": selector, "text": text}


def _key_masks(server) -> dict[str, dict[str, Any]]:
    masks: dict[str, dict[str, Any]] = {}
    env_names = set()
    for row in server.list_pipelines():
        env = str(row.get("api_key_env") or "").strip()
        if env:
            env_names.add(env)
    for env in sorted(env_names):
        value = str(server.SECRETS.get(env) or os.environ.get(env) or "").strip()
        masks[env] = {"set": bool(value), "masked": mask_secret(value)}
    return masks


def _bundled_suites(server) -> list[dict[str, Any]]:
    labels = {
        "nel-demo": "Demo",
        "nel-validate": "Validation",
        "nel-validate-function": "Validation — functional",
        "nel-validate-brief": "Validation — brief",
        "nel-validate-dual": "Validation — dual pathology",
    }
    supported = set(server.modes())
    rows: list[dict[str, Any]] = []
    try:
        bundled = server._bundled()
        for mode in bundled.bundled_modes():
            if mode not in supported:
                continue
            try:
                cases = list(bundled.list_case_ids(mode))
            except Exception:
                cases = []
            rows.append({"mode": mode, "label": labels.get(mode, mode), "cases": cases})
    except Exception:
        pass
    return rows


def apply(server) -> None:
    """Patch the imported base server once, preserving its existing public API."""
    if getattr(server, "_NEL_UI_ENHANCEMENTS_APPLIED", False):
        return
    server._NEL_UI_ENHANCEMENTS_APPLIED = True

    base_child = server._Child
    base_registry = server.Registry
    original_pipeline_path = server.pipeline_path
    original_compose_pipeline = server.compose_pipeline
    original_bootstrap = server.bootstrap
    original_handle = server.Handler._handle

    class RetryChild(base_child):
        def __init__(self, proc, run_id: str, phase: str, exclusive: bool, cleanup,
                     *, argv: list[str]):
            super().__init__(proc, run_id, phase, exclusive, cleanup)
            self.argv = list(argv)
            self.attempt = 1
            self.max_attempts = MAX_RUN_ATTEMPTS if phase == "run" else 1
            self.stop_requested = False
            self.retry_pending = False
            self.output_tail = bytearray()

        @property
        def active(self) -> bool:
            return bool(
                self.retry_pending
                or (self.proc is not None and self.proc.poll() is None)
            )

        def snapshot(self) -> dict[str, Any]:
            snap = super().snapshot()
            snap.update({
                "attempt": self.attempt,
                "max_attempts": self.max_attempts,
                "retry_pending": self.retry_pending,
                "stop_requested": self.stop_requested,
            })
            return snap

    class RetryRegistry(base_registry):
        """Current concurrency rules plus bounded retry of failed run phases."""

        def _spawn(self, child: RetryChild):
            return subprocess.Popen(
                child.argv,
                cwd=str(server.ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=server.child_env(),
                bufsize=0,
            )

        def start(self, argv: list[str], *, run_id: str, phase: str,
                  exclusive: bool, cleanup=None) -> dict[str, Any]:
            with self._lock:
                self._admit(run_id, exclusive, phase)
                path = server.console_path(run_id)
                handle = open(path, "ab")
                printable = " ".join(["nel.py", *argv[3:]])
                handle.write(f"\n$ python {printable}\n".encode("utf-8"))
                max_attempts = MAX_RUN_ATTEMPTS if phase == "run" else 1
                handle.write(
                    f"[nel-ui] {phase} attempt 1/{max_attempts}\n".encode("utf-8")
                )
                handle.flush()
                try:
                    placeholder = RetryChild(
                        None, run_id, phase, exclusive, cleanup, argv=argv
                    )
                    proc = self._spawn(placeholder)
                    placeholder.proc = proc
                except OSError as exc:
                    handle.close()
                    raise server.UIError(f"could not start nel.py: {exc}", 500) from exc
                child = placeholder
                self._children[run_id] = child
                thread = threading.Thread(
                    target=self._pump, args=(child, handle), daemon=True
                )
                thread.start()
                return child.snapshot()

        def _pump(self, child: RetryChild, handle) -> None:
            try:
                while True:
                    proc = child.proc
                    try:
                        while True:
                            chunk = proc.stdout.read(1)
                            if not chunk:
                                break
                            handle.write(chunk)
                            handle.flush()
                            child.output_tail.extend(chunk)
                            if len(child.output_tail) > 8192:
                                del child.output_tail[:-8192]
                    except (OSError, ValueError, AttributeError):
                        pass

                    code = proc.wait()
                    try:
                        if proc.stdout is not None:
                            proc.stdout.close()
                    except (OSError, ValueError):
                        pass
                    child.returncode = code
                    try:
                        handle.write(
                            f"\n[nel-ui] {child.phase} attempt {child.attempt}/{child.max_attempts} "
                            f"finished with exit code {code}\n".encode("utf-8")
                        )
                        handle.flush()
                    except (OSError, ValueError):
                        pass

                    if not should_retry(
                        phase=child.phase,
                        returncode=code,
                        attempt=child.attempt,
                        max_attempts=child.max_attempts,
                        stop_requested=child.stop_requested,
                        output=child.output_tail.decode("utf-8", errors="replace"),
                    ):
                        break

                    child.retry_pending = True
                    next_attempt = child.attempt + 1
                    try:
                        handle.write(
                            f"[nel-ui] run failed; resuming the same run as attempt "
                            f"{next_attempt}/{child.max_attempts}\n".encode("utf-8")
                        )
                        handle.flush()
                    except (OSError, ValueError):
                        pass

                    # Keep retry_pending true while briefly yielding so the run
                    # retains its concurrency slot and a Stop click can cancel it.
                    time.sleep(0.2)
                    if child.stop_requested:
                        break
                    child.attempt = next_attempt
                    try:
                        child.proc = self._spawn(child)
                        child.returncode = None
                        child.output_tail.clear()
                        child.retry_pending = False
                        try:
                            handle.write(
                                f"[nel-ui] run attempt {child.attempt}/{child.max_attempts}\n".encode("utf-8")
                            )
                            handle.flush()
                        except (OSError, ValueError):
                            pass
                    except OSError as exc:
                        child.retry_pending = False
                        child.returncode = -1
                        try:
                            handle.write(
                                f"[nel-ui] automatic retry could not start: {exc}\n".encode("utf-8")
                            )
                            handle.flush()
                        except (OSError, ValueError):
                            pass
                        break
            finally:
                child.retry_pending = False
                try:
                    handle.close()
                except (OSError, ValueError):
                    pass
                for path in child.cleanup:
                    try:
                        Path(path).unlink()
                    except OSError:
                        pass

        def stop(self, run_id: str) -> dict[str, Any]:
            child = self._children.get(run_id)
            if child is None or not child.active:
                return {"stopped": False, "detail": f"run {run_id} is not active"}
            child.stop_requested = True
            if getattr(child, "retry_pending", False) and child.proc.poll() is not None:
                return {
                    "stopped": True,
                    "detail": f"run {run_id} stopped before automatic retry; it can be resumed",
                }
            try:
                child.proc.send_signal(signal.SIGTERM)
            except OSError as exc:
                if child.proc.poll() is not None:
                    return {
                        "stopped": True,
                        "detail": f"run {run_id} stopped; automatic retry cancelled",
                    }
                return {"stopped": False, "detail": f"could not signal the process: {exc}"}
            try:
                child.proc.wait(timeout=8)
                return {"stopped": True, "detail": f"run {run_id} stopped; it can be resumed"}
            except subprocess.TimeoutExpired:
                pass
            try:
                child.proc.kill()
                child.proc.wait(timeout=8)
                return {"stopped": True, "detail": f"run {run_id} killed; it can be resumed"}
            except Exception as exc:
                return {"stopped": False, "detail": f"process did not exit: {exc}"}

    def pipeline_path(name: str):
        value = str(name or "").strip()
        if not server.RUN_ID_RE.fullmatch(value):
            raise server.UIError(
                "Profile file name is invalid. Use letters, numbers, '.', '_' or '-' only, "
                "starting with a letter or number. This names config/pipelines/<name>.yaml; "
                "it is not an OpenRouter model ID."
            )
        return original_pipeline_path(value)

    def compose_pipeline(payload: dict[str, Any]):
        aliases = payload.get("aliases") or []
        if not isinstance(aliases, list) or not aliases:
            raise server.UIError("Add at least one model alias")
        for index, row in enumerate(aliases, start=1):
            if not isinstance(row, dict):
                raise server.UIError(f"Model alias {index} is malformed")
            try:
                validate_alias_name(row.get("alias"), index=index)
            except ValueError as exc:
                raise server.UIError(str(exc)) from exc
        try:
            return original_compose_pipeline(payload)
        except server.UIError as exc:
            replacements = {
                "model option": "model alias",
                "model options": "model aliases",
                "needs a name": "needs an alias",
            }
            message = exc.message
            for old, new in replacements.items():
                message = message.replace(old, new)
            if message != exc.message:
                raise server.UIError(message, exc.status) from exc
            raise

    def bootstrap():
        doc = original_bootstrap()
        doc["workflows"] = [
            {"id": "proforma_v1", "label": "proforma_v1", "supported": True}
        ]
        doc["bundled_suites"] = _bundled_suites(server)
        doc["key_masks"] = _key_masks(server)
        return doc

    def enhanced_handle(self, path: str, method: str):
        if method == "GET":
            if path == "/api/case":
                return _read_artifact(server, self._param("run"), "case.md")
            if path == "/api/dissent":
                return _read_dissent(server, self._param("run"))
            if path == "/api/case-preview":
                return _case_preview(server, self._param("mode"), self._param("selector"))
            if path == "/api/key-status":
                return {"keys": _key_masks(server)}
        return original_handle(self, path, method)

    server._Child = RetryChild
    server.Registry = RetryRegistry
    server.REGISTRY = RetryRegistry()
    server.pipeline_path = pipeline_path
    server.compose_pipeline = compose_pipeline
    server.bootstrap = bootstrap
    server.Handler._handle = enhanced_handle
    server.HEADER = (
        "# Written by the NEL browser interface.\n"
        "# model_aliases defines local model aliases; model_roles assigns one alias to\n"
        "# each proforma-v1 role. Never store an API key in this file: the key is read\n"
        "# from the environment variable named by provider.api_key_env.\n"
    )
    server.mask_secret = mask_secret
    server.validate_alias_name = validate_alias_name
    server.should_retry = should_retry
