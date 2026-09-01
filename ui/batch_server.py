"""Batch-aware browser server for the NEL UI.

The existing :mod:`ui.server` remains the provider/profile/key implementation.
This module adds batch-aware read/write endpoints while ``ui/index.html`` owns the
first-class single/batch browser state. Every mutating run operation still goes
through the root ``nel.py`` facade.
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import threading
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ui import server as base

if str(base.ROOT) not in sys.path:
    sys.path.insert(0, str(base.ROOT))

from scripts import run_layout

PAGE = base.UI_DIR / "index.html"


def _layout_error(exc: Exception, status: int = 400) -> base.UIError:
    return base.UIError(str(exc), status)


def _top_kind(run_ref: str) -> str:
    try:
        batch_id, case_id = run_layout.split_run_ref(run_ref)
    except run_layout.LayoutError as exc:
        raise _layout_error(exc) from exc
    if batch_id is not None:
        return "batch-child"
    path = base.RUNS_DIR / case_id
    if not path.is_dir():
        raise base.UIError(f"run not found: {case_id}", 404)
    kind = run_layout.classify_top_level(path)
    if kind == "unsupported":
        return "legacy"
    if kind == "invalid":
        return "invalid"
    return kind


def _run_location(run_ref: str) -> run_layout.RunLocation:
    try:
        return run_layout.resolve_run(base.RUNS_DIR, run_ref)
    except run_layout.LayoutError as exc:
        raise _layout_error(exc, 404 if "not found" in str(exc) else 409) from exc


def _batch_location(batch_id: str) -> run_layout.BatchLocation:
    try:
        return run_layout.resolve_batch(base.RUNS_DIR, batch_id)
    except run_layout.LayoutError as exc:
        raise _layout_error(exc, 404 if "not found" in str(exc) else 409) from exc


def _nel_json(*args: str) -> Any:
    result = base.nel(*args)
    if result.returncode != 0:
        detail = (result.stdout or "").strip()
        raise base.UIError(detail[-1600:] or f"nel.py {' '.join(args)} failed", 409)
    return base.extract_json(result.stdout)


def _safe_read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"exists": False, "text": ""}
    size = path.stat().st_size
    with open(path, "rb") as handle:
        data = handle.read(base.MAX_FILE_BYTES)
    return {
        "exists": True,
        "text": data.decode("utf-8", errors="replace"),
        "size": size,
        "truncated": size > base.MAX_FILE_BYTES,
    }


def _read_offset(path: Path, offset: int) -> dict[str, Any]:
    if not path.is_file():
        return {"offset": 0, "text": "", "size": 0}
    size = path.stat().st_size
    start = 0 if offset < 0 or offset > size else offset
    with open(path, "rb") as handle:
        handle.seek(start)
        data = handle.read()
    return {
        "offset": start + len(data),
        "text": data.decode("utf-8", errors="replace"),
        "size": size,
    }


def _execution_limit(doc: dict[str, Any]) -> int:
    execution = doc.get("execution") or {}
    if isinstance(execution, dict):
        value = execution.get("max_parallel_cases")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    provider = doc.get("provider") or {}
    try:
        from urllib.parse import urlparse
        host = (urlparse(str(provider.get("base_url") or "")).hostname or "").lower()
    except Exception:
        host = ""
    return 1 if host in base.LOCAL_HOSTS else 4


def list_pipelines() -> list[dict[str, Any]]:
    rows = base.list_pipelines()
    for row in rows:
        if not row.get("readable"):
            continue
        try:
            row["max_parallel_cases"] = _execution_limit(base.read_pipeline(str(row["name"])))
        except Exception:
            row["max_parallel_cases"] = None
    return rows


def _key_masks() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in list_pipelines():
        env = str(row.get("api_key_env") or "")
        if not env:
            continue
        value = str(base.SECRETS.get(env) or os.environ.get(env) or "")
        out[env] = {
            "set": bool(value),
            "masked": (value[:8] + "…") if len(value) > 8 else value,
        }
    return out


def _bundled_suites() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    examples = [str(value) for value in base.demo_examples()]
    if examples:
        rows.append({"mode": "nel-demo", "label": "Demo", "cases": examples})
    labels = {
        "nel-validate": "Validation",
        "nel-validate-function": "Validation — function",
        "nel-validate-brief": "Validation — brief",
        "nel-validate-dual": "Validation — dual pathology",
    }
    for mode, cases in base.validation_cases().items():
        rows.append({"mode": mode, "label": labels.get(mode, mode), "cases": list(cases)})
    return rows


def bootstrap() -> dict[str, Any]:
    doc = base.bootstrap()
    doc["pipelines"] = list_pipelines()
    doc["batch"] = {
        "enabled": True,
        "delimiter": "# Case <title>",
        "cloud_default_parallel_cases": 4,
    }
    doc.setdefault("workflows", [{"id": "proforma_v1", "label": "proforma_v1"}])
    doc["bundled_suites"] = _bundled_suites()
    doc["key_masks"] = _key_masks()
    return doc

def runs_list() -> list[dict[str, Any]]:
    rows = _nel_json("runs", "--json")
    if not isinstance(rows, list):
        return []
    flat: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        parent = dict(row)
        if parent.get("kind") == "batch":
            counts = parent.get("counts") or {}
            total = len(parent.get("children") or [])
            complete = int(counts.get("complete") or 0)
            failed = int(counts.get("failed") or 0)
            blocked = int(counts.get("blocked") or 0)
            label = f"{complete}/{total} complete"
            if failed:
                label += f" · {failed} failed"
            if blocked or parent.get("status") == "blocked":
                label += " · blocked"
            parent["label"] = label
            parent["archived"] = False
        flat.append(parent)
        if parent.get("kind") == "batch":
            for child in parent.get("children") or []:
                if not isinstance(child, dict):
                    continue
                item = dict(child)
                item["parent_batch"] = parent.get("run_id")
                item["archived"] = False
                flat.append(item)
    return flat

def status(run_ref: str) -> dict[str, Any]:
    kind = _top_kind(run_ref)
    if kind in {"legacy", "invalid"}:
        return {"available": False, "status": {"kind": kind, "stage": kind, "complete": False, "label": "Legacy run" if kind == "legacy" else "Invalid layout"}, "manifest": {}, "archived": False}
    if kind == "batch":
        doc = _nel_json("batch", "status", "--run-id", run_ref, "--json")
        return {"available": True, "status": doc, "manifest": {}, "archived": False}
    doc = _nel_json("status", "--run-id", run_ref, "--json")
    loc = _run_location(run_ref)
    frozen = loc.path / "run-config" / "manifest.json"
    try:
        manifest = json.loads(frozen.read_text(encoding="utf-8")) if frozen.is_file() else {}
    except (OSError, json.JSONDecodeError):
        manifest = {}
    return {
        "available": True,
        "status": doc,
        "manifest": manifest if isinstance(manifest, dict) else {},
        "archived": (loc.path / base.ARCHIVE_MARKER).is_file(),
    }


def console(run_ref: str, offset: int) -> dict[str, Any]:
    kind = _top_kind(run_ref)
    if kind in {"legacy", "invalid"}:
        return base.read_console(run_ref, offset)
    if kind == "batch":
        return base.read_console(run_ref, offset)
    loc = _run_location(run_ref)
    if loc.is_batch_child:
        return _read_offset(loc.path / "logs" / "batch-run.log", offset)
    return base.read_console(run_ref, offset)


def usage(run_ref: str) -> dict[str, Any]:
    kind = _top_kind(run_ref)
    if kind in {"legacy", "invalid"}:
        return {"available": False, "summary": None}
    if kind == "batch":
        doc = _nel_json("batch", "status", "--run-id", run_ref, "--json")
        summary = doc.get("usage") if isinstance(doc, dict) else None
        return {"available": summary is not None, "summary": summary}
    loc = _run_location(run_ref)
    base._ensure_root_on_path()
    from scripts import model_usage
    summary = model_usage.summarize(loc.path / "logs" / "model-usage.json")
    return {"available": summary is not None, "summary": summary}


def _batch_summary_markdown(batch_id: str) -> str:
    doc = _nel_json("batch", "status", "--run-id", batch_id, "--json")
    counts = doc.get("counts") or {}
    usage_doc = doc.get("usage") or {}
    cost = (usage_doc.get("cost") or {}).get("amount")
    lines = [
        f"# {batch_id}", "",
        f"- Status: **{doc.get('status', 'unknown')}**",
        f"- Pipeline: `{doc.get('pipeline') or ''}`",
        f"- Mode: `{doc.get('mode') or ''}`",
        f"- Effective concurrency: **{doc.get('max_parallel_cases', 1)}**",
        f"- Complete: **{counts.get('complete', 0)}**",
        f"- Running: **{counts.get('running', 0)}**",
        f"- Failed: **{counts.get('failed', 0)}**",
        f"- Blocked: **{counts.get('blocked', 0)}**",
        f"- Pending/stopped: **{counts.get('prepared', 0) + counts.get('stopped', 0)}**",
    ]
    if doc.get("blocked_reason"):
        lines.append(f"- Block reason: **{doc.get('blocked_reason')}**")
    elapsed = doc.get("elapsed_seconds")
    if elapsed is not None:
        lines.append(f"- Elapsed: **{float(elapsed):.1f}s**")
    if cost is not None:
        lines.append(f"- Aggregate cost: **${float(cost):.4f}**")
    lines += ["", "## Cases", ""]
    for child in doc.get("children") or []:
        marker = {"complete": "✓", "failed": "!", "running": "●", "blocked": "⊘", "stopped": "■"}.get(
            str(child.get("batch_status") or ""), "○"
        )
        title = str(child.get("case_title") or child.get("case_id") or "case")
        title = title.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
        ref = str(child.get("run_id") or "")
        lines.append(
            f"- {marker} [{title}](nel-run:{ref}) — "
            f"`{child.get('batch_status') or child.get('stage') or 'prepared'}`"
        )
    return "\n".join(lines) + "\n"


def case_text(run_ref: str) -> dict[str, Any]:
    kind = _top_kind(run_ref)
    if kind in {"legacy", "invalid"}:
        return {"exists": False, "text": ""}
    if kind == "batch":
        return {"exists": True, "text": _batch_summary_markdown(run_ref), "truncated": False}
    return _safe_read(_run_location(run_ref).path / "case.md")


def report(run_ref: str) -> dict[str, Any]:
    kind = _top_kind(run_ref)
    if kind in {"legacy", "invalid"}:
        return {"exists": False, "text": ""}
    if kind == "batch":
        return {"exists": True, "text": _batch_summary_markdown(run_ref), "truncated": False}
    return _safe_read(_run_location(run_ref).path / "report-final.md")


def dissent(run_ref: str) -> dict[str, Any]:
    kind = _top_kind(run_ref)
    if kind in {"batch", "legacy", "invalid"}:
        return {"exists": False, "text": ""}
    run = _run_location(run_ref).path
    candidates = [run / "dissent.md", run / "intermediates" / "dissent.md"]
    for path in candidates:
        if path.is_file():
            return _safe_read(path)
    return {"exists": False, "text": ""}


def run_files(run_ref: str) -> list[dict[str, Any]]:
    kind = _top_kind(run_ref)
    if kind == "batch":
        base_path = _batch_location(run_ref).path
        names = [run_layout.BATCH_MANIFEST, run_layout.BATCH_STATE, run_layout.BATCH_SOURCE]
        paths = [base_path / name for name in names if (base_path / name).is_file()]
    else:
        base_path = _run_location(run_ref).path
        paths = [p for p in sorted(base_path.rglob("*")) if p.is_file() and "__pycache__" not in p.parts]
    return [{"path": p.relative_to(base_path).as_posix(), "size": p.stat().st_size} for p in paths]


def read_run_file(run_ref: str, relative: str) -> dict[str, Any]:
    kind = _top_kind(run_ref)
    base_path = _batch_location(run_ref).path if kind == "batch" else _run_location(run_ref).path
    path = base.safe_child(base_path, relative)
    if not path.is_file():
        raise base.UIError(f"no such file in this run: {relative}", 404)
    payload = _safe_read(path)
    payload["path"] = relative
    return payload


def _validate_pipeline(name: str) -> None:
    readable = {str(row["name"]) for row in list_pipelines() if row.get("readable")}
    if not name:
        raise base.UIError("choose a provider profile before preparing a run")
    if name in base.HIDDEN_PIPELINES:
        raise base.UIError("batch processing requires an unattended provider profile")
    if name not in readable:
        raise base.UIError(f"no usable profile named {name}", 404)


def _new_batch_id(payload: dict[str, Any], label: str) -> str:
    supplied = str(payload.get("run_id") or "").strip()
    batch_id = base.check_run_id(supplied) if supplied else base.generated_run_id(f"batch-{label}")
    if (base.RUNS_DIR / batch_id).exists():
        raise base.UIError(f"a run named {batch_id} already exists; choose another identifier", 409)
    return batch_id


def action_setup(payload: dict[str, Any]) -> dict[str, Any]:
    mode = str(payload.get("mode") or "").strip()
    pipeline = str(payload.get("pipeline") or "").strip()
    batch_mode = bool(payload.get("batch_mode"))
    _validate_pipeline(pipeline)

    if not batch_mode:
        return base.action_setup(payload)

    cul = str(payload.get("cul") or "").strip()
    args = ["batch", "setup", "--mode", mode, "--pipeline", pipeline]
    cleanup: list[Path] = []
    if cul:
        args += ["--cul", cul]

    if mode == "ngs-report":
        case_text_value = str(payload.get("case_text") or "")
        try:
            parsed = run_layout.parse_case_markdown(case_text_value)
        except run_layout.LayoutError as exc:
            raise base.UIError(str(exc)) from exc
        batch_id = _new_batch_id(payload, f"cases-{len(parsed)}")
        source = base.case_path(batch_id)
        source.write_text(
            case_text_value if case_text_value.endswith("\n") else case_text_value + "\n",
            encoding="utf-8",
        )
        cleanup.append(source)
        args += ["--case", str(source), "--run-id", batch_id]
    else:
        suites = {row["mode"]: set(row.get("cases") or []) for row in _bundled_suites()}
        if mode not in suites:
            raise base.UIError(f"unsupported bundled batch series {mode!r}")
        raw_ids = payload.get("case_ids") or []
        if not isinstance(raw_ids, list):
            raise base.UIError("bundled case_ids must be a list")
        case_ids = [str(value).strip() for value in raw_ids if str(value).strip()]
        if not case_ids:
            raise base.UIError("select at least one case from this bundled series")
        missing = [case_id for case_id in case_ids if case_id not in suites[mode]]
        if missing:
            raise base.UIError(
                f"case(s) not in {mode}: {', '.join(missing)}; select cases from one series only"
            )
        try:
            joined = ",".join(run_layout.parse_case_ids(",".join(case_ids)))
        except run_layout.LayoutError as exc:
            raise base.UIError(str(exc)) from exc
        batch_id = _new_batch_id(payload, f"{mode.removeprefix('nel-')}-{len(case_ids)}")
        args += ["--case-ids", joined, "--run-id", batch_id]

    argv = [sys.executable, "-u", str(base.ROOT / "nel.py"), *args]
    try:
        return base.REGISTRY.start(
            argv, run_id=batch_id, phase="setup",
            exclusive=base.is_local_pipeline(pipeline), cleanup=cleanup,
        )
    except base.UIError:
        for path in cleanup:
            try:
                path.unlink()
            except OSError:
                pass
        raise

def action_run(payload: dict[str, Any]) -> dict[str, Any]:
    run_ref = str(payload.get("run_id") or "").strip()
    kind = _top_kind(run_ref)
    if kind == "batch-child":
        batch_id, _case_id = run_layout.split_run_ref(run_ref)
        run_ref = str(batch_id)
        kind = "batch"
    if kind in {"legacy", "invalid"}:
        raise base.UIError("legacy/invalid run folders are cleanup-only; delete them or prepare a new run", 409)
    if kind == "run":
        return base.action_run({"run_id": run_ref})
    batch = _batch_location(run_ref)
    pipeline = str(batch.manifest.get("pipeline") or "")
    argv = [sys.executable, "-u", str(base.ROOT / "nel.py"), "batch", "run", "--run-id", run_ref]
    return base.REGISTRY.start(
        argv,
        run_id=run_ref,
        phase="run",
        exclusive=base.is_local_pipeline_safe(pipeline) if pipeline else True,
    )


def action_stop(payload: dict[str, Any]) -> dict[str, Any]:
    run_ref = str(payload.get("run_id") or "").strip()
    if _top_kind(run_ref) == "batch-child":
        batch_id, _case_id = run_layout.split_run_ref(run_ref)
        run_ref = str(batch_id)
    return base.REGISTRY.stop(run_ref)


def action_delete(payload: dict[str, Any]) -> dict[str, Any]:
    run_ref = str(payload.get("run_id") or "").strip()
    try:
        batch_id, _case_id = run_layout.split_run_ref(run_ref)
    except run_layout.LayoutError as exc:
        raise base.UIError(str(exc)) from exc
    owner = batch_id or run_ref
    if base.REGISTRY.is_active(owner):
        raise base.UIError(f"run {owner} is active; stop it before deleting", 409)
    result = base.nel("delete", "--run-id", run_ref)
    if result.returncode != 0:
        raise base.UIError((result.stdout or "").strip()[-1200:] or f"delete failed: {run_ref}", 409)
    for extra in (base.console_path(owner), base.case_path(owner)):
        try:
            extra.unlink()
        except OSError:
            pass
    return {"deleted": run_ref}


def action_archive(payload: dict[str, Any]) -> dict[str, Any]:
    run_ref = str(payload.get("run_id") or "").strip()
    if _top_kind(run_ref) != "run":
        raise base.UIError("archiving is available only for ordinary single runs in batch v1", 409)
    return base.action_archive({"run_id": run_ref})


def save_pipeline(payload: dict[str, Any]) -> dict[str, Any]:
    name, doc = base.compose_pipeline(payload)
    # Execution settings are not a model role. Preserve an existing explicit
    # value; otherwise add the deterministic v1 default (local=1, cloud=4).
    try:
        existing = base.read_pipeline(name)
    except base.UIError:
        existing = {}
    execution = existing.get("execution") if isinstance(existing, dict) else None
    if isinstance(execution, dict) and "max_parallel_cases" in execution:
        doc["execution"] = {"max_parallel_cases": execution["max_parallel_cases"]}
    else:
        doc["execution"] = {"max_parallel_cases": _execution_limit(doc)}
    saved = base.save_pipeline(name, doc, overwrite=bool(payload.get("overwrite")))
    return {"name": name, "path": str(saved), "pipelines": list_pipelines()}


def case_preview(mode: str, selector: str) -> dict[str, Any]:
    try:
        bundled = base._bundled()
        text = bundled.retrieve_case_input(mode, selector)
    except Exception as exc:
        raise base.UIError(str(exc), 404) from exc
    return {"text": text}


class Handler(base.Handler):
    token = ""

    def _authorised_api(self) -> bool:
        supplied = self.headers.get("X-NEL-Token") or ""
        return secrets.compare_digest(supplied, Handler.token)

    def _serve_page(self) -> None:
        if not secrets.compare_digest(self._param("t"), Handler.token):
            return self._text(
                "This page needs the session address printed in the terminal that started nel.py ui.\n",
                403,
            )
        try:
            text = PAGE.read_text(encoding="utf-8")
        except OSError:
            return self._text(f"{PAGE.relative_to(base.ROOT)} is missing\n", 500)
        body = text.replace("__NEL_TOKEN__", Handler.token).encode("utf-8")
        self._send(200, "text/html; charset=utf-8", body)

    def _handle(self, path: str, method: str) -> Any:
        if method == "GET":
            if path == "/api/bootstrap":
                return bootstrap()
            if path == "/api/runs":
                return {"runs": runs_list()}
            if path == "/api/status":
                return status(self._param("run"))
            if path == "/api/console":
                try:
                    offset = int(self._param("offset", "0"))
                except ValueError:
                    offset = 0
                return console(self._param("run"), offset)
            if path == "/api/usage":
                return usage(self._param("run"))
            if path == "/api/report":
                return report(self._param("run"))
            if path == "/api/case":
                return case_text(self._param("run"))
            if path == "/api/case-preview":
                return case_preview(self._param("mode"), self._param("selector"))
            if path == "/api/key-status":
                return {"keys": _key_masks()}
            if path == "/api/dissent":
                return dissent(self._param("run"))
            if path == "/api/files":
                return {"files": run_files(self._param("run"))}
            if path == "/api/file":
                return read_run_file(self._param("run"), self._param("path"))
            if path == "/api/pipelines":
                name, note = base.default_pipeline()
                return {"pipelines": list_pipelines(), "default_pipeline": name, "default_pipeline_note": note}
            return super()._handle(path, method)

        body = self._body()
        if path == "/api/setup":
            return action_setup(body)
        if path == "/api/run":
            return action_run(body)
        if path == "/api/stop":
            return action_stop(body)
        if path == "/api/delete":
            return action_delete(body)
        if path == "/api/archive":
            return action_archive(body)
        if path == "/api/pipeline":
            return save_pipeline(body)
        # base._handle expects to consume the request body itself for POST, so
        # handle the remaining current base POST endpoints here.
        if path == "/api/key":
            env = str(body.get("env") or "").strip()
            if not env:
                raise base.UIError("name the environment variable the key belongs to")
            value = str(body.get("value") or "").strip()
            if value:
                base.SECRETS[env] = value
            else:
                base.SECRETS.pop(env, None)
            return {"keys": base.env_status()}
        if path == "/api/provider-models":
            key = str(body.get("api_key") or "").strip()
            if not key:
                key = base.SECRETS.get(str(body.get("api_key_env") or ""), "")
            return base.provider_catalogue(str(body.get("base_url") or ""), key)
        raise base.UIError("no such endpoint", 404)


def serve(port: int = 8765, open_browser: bool = True) -> int:
    if not PAGE.is_file():
        print(f"{PAGE.relative_to(base.ROOT)} is missing: {PAGE}", file=sys.stderr)
        return 1
    base.CONSOLE_DIR.mkdir(parents=True, exist_ok=True)
    base.CASE_DIR.mkdir(parents=True, exist_ok=True)
    swept = base.sweep_case_files()
    Handler.token = secrets.token_urlsafe(24)
    httpd = None
    last_error: Exception | None = None
    for candidate in range(port, port + 20):
        try:
            httpd = ThreadingHTTPServer((base.BIND_HOST, candidate), Handler)
            break
        except OSError as exc:
            last_error = exc
    if httpd is None:
        raise SystemExit(f"no free port in {port}-{port + 19}: {last_error}")
    bound = httpd.server_address[1]
    url = f"http://{base.BIND_HOST}:{bound}/?t={Handler.token}"
    if swept:
        print(f"[nel-ui] removed {swept} orphaned case file(s) from .nel-ui/cases")
    print(f"[nel-ui] {url}")
    print("[nel-ui] batch v1 enabled; this machine only; the address carries a one-time session token")
    print("[nel-ui] press Ctrl-C to stop")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[nel-ui] stopping active runs")
        base.REGISTRY.stop_all()
    finally:
        httpd.server_close()
    return 0
