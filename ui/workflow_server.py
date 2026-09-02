"""Workflow-definition aware wrapper for the batch NEL browser server.

The existing :mod:`ui.batch_server` remains the batch/provider implementation.
This wrapper adds discovery and selection of declarative proforma-v1 workflow
YAMLs without duplicating workflow execution logic in the UI.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from ui import batch_server as batch
base = batch.base
_BATCH_BOOTSTRAP = batch.bootstrap
_BATCH_LIST_PIPELINES = batch.list_pipelines
WORKFLOW_DIR = base.ROOT / "workflows" / "proforma_v1" / "workflow"
DEFAULT_WORKFLOW = "default"
OPENROUTER_MODELS_PATH = base.ROOT / "config" / "openrouter_models.json"
OPENROUTER_CATEGORIES = {
    "Fast / Cheap",
    "High Quality",
    "Fast & Local-compatible",
}

PROVIDER_CLASSES = {"lmstudio", "openrouter", "other"}


def _infer_provider_class(name: str, doc: dict[str, Any] | None = None, base_url: str = "") -> str:
    """Return the UI provider class without requiring a profile migration."""
    doc = doc if isinstance(doc, dict) else {}
    meta = doc.get("pipeline") or {}
    explicit = str(meta.get("provider_class") or "").strip().lower() if isinstance(meta, dict) else ""
    if explicit in PROVIDER_CLASSES:
        return explicit
    provider = doc.get("provider") or {}
    if isinstance(provider, dict):
        base_url = str(provider.get("base_url") or base_url or "").strip()
    lowered = f"{name} {base_url}".lower()
    if "openrouter" in lowered:
        return "openrouter"
    try:
        host = (urlparse(base_url).hostname or "").lower()
    except Exception:
        host = ""
    if host in base.LOCAL_HOSTS or "lmstudio" in lowered or "lm-studio" in lowered:
        return "lmstudio"
    return "other"


def list_pipelines() -> list[dict[str, Any]]:
    """Annotate existing profiles with a provider class for UI filtering."""
    rows = _BATCH_LIST_PIPELINES()
    for row in rows:
        name = str(row.get("name") or "")
        doc: dict[str, Any] = {}
        if row.get("readable"):
            try:
                loaded = base.read_pipeline(name)
                if isinstance(loaded, dict):
                    doc = loaded
            except Exception:
                doc = {}
        row["provider_class"] = _infer_provider_class(
            name, doc, str(row.get("base_url") or "")
        )
    return rows


def save_pipeline(payload: dict[str, Any]) -> dict[str, Any]:
    """Save a profile with explicit provider-class metadata when edited in the UI."""
    name, doc = base.compose_pipeline(payload)
    requested = str(payload.get("provider_class") or "").strip().lower()
    provider_class = requested if requested in PROVIDER_CLASSES else _infer_provider_class(name, doc)
    pipeline_meta = doc.setdefault("pipeline", {})
    if isinstance(pipeline_meta, dict):
        pipeline_meta["provider_class"] = provider_class

    # Preserve batch execution policy just as batch_server.save_pipeline does.
    try:
        existing = base.read_pipeline(name)
    except base.UIError:
        existing = {}
    execution = existing.get("execution") if isinstance(existing, dict) else None
    if isinstance(execution, dict) and "max_parallel_cases" in execution:
        doc["execution"] = {"max_parallel_cases": execution["max_parallel_cases"]}
    else:
        doc["execution"] = {"max_parallel_cases": batch._execution_limit(doc)}

    saved = base.save_pipeline(name, doc, overwrite=bool(payload.get("overwrite")))
    return {"name": name, "path": str(saved), "pipelines": list_pipelines()}



def workflow_definitions() -> list[dict[str, str]]:
    rows = [
        {"id": path.stem, "label": path.stem}
        for path in sorted(WORKFLOW_DIR.glob("*.yaml"))
        if path.is_file() and base.RUN_ID_RE.fullmatch(path.stem)
    ]
    if not rows:
        raise base.UIError(f"no proforma-v1 workflow YAML files found in {WORKFLOW_DIR}", 500)
    return rows


def _workflow_name(payload: dict[str, Any]) -> str:
    name = str(payload.get("workflow") or DEFAULT_WORKFLOW).strip()
    available = {row["id"] for row in workflow_definitions()}
    if name not in available:
        raise base.UIError(
            f"unknown workflow {name!r}; choose one of: {', '.join(sorted(available))}",
            400,
        )
    return name


def bootstrap() -> dict[str, Any]:
    doc = _BATCH_BOOTSTRAP()
    doc["pipelines"] = list_pipelines()
    doc["workflows"] = workflow_definitions()
    doc["default_workflow"] = DEFAULT_WORKFLOW
    return doc


def openrouter_models() -> dict[str, Any]:
    try:
        doc = json.loads(OPENROUTER_MODELS_PATH.read_text(encoding="utf-8"))
    except OSError as exc:
        raise base.UIError(f"OpenRouter model suggestions are unavailable: {exc}", 500) from exc
    except json.JSONDecodeError as exc:
        raise base.UIError(f"OpenRouter model suggestions are invalid JSON: {exc}", 500) from exc
    rows = doc.get("models") if isinstance(doc, dict) else None
    if not isinstance(rows, list) or not (1 <= len(rows) <= 8):
        raise base.UIError("OpenRouter model suggestions must contain 1-8 models", 500)
    seen: set[str] = set()
    clean: list[dict[str, str]] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise base.UIError(f"OpenRouter model suggestion {index} must be an object", 500)
        model_id = str(row.get("id") or "").strip()
        name = str(row.get("name") or "").strip()
        category = str(row.get("category") or "").strip()
        if not model_id or not name:
            raise base.UIError(f"OpenRouter model suggestion {index} needs id and name", 500)
        if model_id in seen:
            raise base.UIError(f"duplicate OpenRouter model suggestion: {model_id}", 500)
        if category not in OPENROUTER_CATEGORIES:
            raise base.UIError(
                f"OpenRouter model suggestion {model_id} has unknown category {category!r}", 500
            )
        seen.add(model_id)
        clean.append({"id": model_id, "name": name, "category": category})
    return {"version": int(doc.get("version") or 1), "models": clean}



def openrouter_model_providers(base_url: str, model: str, api_key_env: str) -> dict[str, Any]:
    """Return provider endpoint slugs available for one OpenRouter model.

    OpenRouter routing is model-specific.  The endpoint ``tag`` is the exact
    value accepted by provider.order/only/ignore, including variants such as
    ``deepinfra/turbo``.  Secrets remain server-side.
    """
    base_url = str(base_url or "").strip().rstrip("/")
    model = str(model or "").strip()
    api_key_env = str(api_key_env or "").strip()
    if not base_url or not model:
        raise base.UIError("base URL and model are required", 400)
    try:
        host = (urlparse(base_url).hostname or "").lower()
    except Exception:
        host = ""
    if host != "openrouter.ai" and not host.endswith(".openrouter.ai"):
        raise base.UIError("model-specific provider discovery is available only for OpenRouter", 400)
    if "/" not in model:
        raise base.UIError("OpenRouter model IDs must use author/model form", 400)
    author, slug = model.split("/", 1)
    key = str(base.SECRETS.get(api_key_env) or os.environ.get(api_key_env) or "").strip()
    if not key:
        raise base.UIError(f"{api_key_env or 'OpenRouter API key'} is not set", 401)
    url = f"{base_url}/models/{quote(author, safe='')}/{quote(slug, safe='')}/endpoints"
    try:
        doc = base._get_json(url, key)
    except Exception as exc:
        raise base.UIError(f"could not list OpenRouter providers for {model}: {exc}", 502) from exc
    data = doc.get("data") if isinstance(doc, dict) else None
    if not isinstance(data, dict) and isinstance(doc, dict):
        data = doc
    endpoints = data.get("endpoints") if isinstance(data, dict) else None
    rows: dict[str, dict[str, str]] = {}
    for endpoint in endpoints if isinstance(endpoints, list) else []:
        if not isinstance(endpoint, dict):
            continue
        # OpenRouter's endpoint schemas have evolved. Prefer the routing tag,
        # but accept the documented provider_tag/provider_slug names as well.
        tag = str(
            endpoint.get("provider_tag")
            or endpoint.get("tag")
            or endpoint.get("provider_slug")
            or endpoint.get("slug")
            or ""
        ).strip()
        if not tag:
            continue
        name = str(endpoint.get("provider_name") or endpoint.get("name") or tag).strip() or tag
        quant = str(endpoint.get("quantization") or "").strip()
        label = name if not quant else f"{name} · {quant}"
        rows.setdefault(tag, {"id": tag, "label": label})
    return {
        "model": model,
        "providers": [rows[key] for key in sorted(rows, key=str.casefold)],
    }

def _single_setup(payload: dict[str, Any], workflow: str) -> dict[str, Any]:
    pipeline = str(payload.get("pipeline") or "").strip()
    batch._validate_pipeline(pipeline)
    mode = str(payload.get("mode") or "").strip()
    if mode not in set(base.modes()):
        raise base.UIError(f"unsupported mode {mode!r}; choose one of: {', '.join(base.modes())}")
    label = mode
    args: list[str] = ["--workflow", workflow]
    case_text = ""
    if mode == "ngs-report":
        case_text = str(payload.get("case_text") or "")
        if not case_text.strip():
            raise base.UIError("paste the clinical case before preparing a run")
        label = "case"
    elif mode == "nel-demo":
        example = payload.get("example")
        if example in (None, ""):
            raise base.UIError("choose a demo example before preparing a run")
        args += ["--example", str(int(example))]
        label = f"demo-{int(example)}"
    else:
        case_id = str(payload.get("case_id") or "").strip()
        if not case_id:
            raise base.UIError("choose a validation case before preparing a run")
        args += ["--case-id", case_id]
        label = f"{mode.removeprefix('nel-')}-{case_id}"
    cul = str(payload.get("cul") or "").strip()
    if cul:
        args += ["--cul", cul]

    supplied = str(payload.get("run_id") or "").strip()
    run_id = base.check_run_id(supplied) if supplied else base.generated_run_id(label)
    if base.run_dir(run_id).exists():
        raise base.UIError(f"a run named {run_id} already exists; choose another identifier", 409)
    cleanup: list[Path] = []
    if mode == "ngs-report":
        path = base.case_path(run_id)
        text = case_text if case_text.endswith("\n") else case_text + "\n"
        path.write_text(text, encoding="utf-8")
        args += ["--case", str(path)]
        cleanup.append(path)
    argv = [
        sys.executable,
        "-u",
        str(base.ROOT / "nel.py"),
        "setup",
        "--mode",
        mode,
        "--pipeline",
        pipeline,
        "--run-id",
        run_id,
        *args,
    ]
    try:
        return base.REGISTRY.start(
            argv,
            run_id=run_id,
            phase="setup",
            exclusive=base.is_local_pipeline(pipeline),
            cleanup=cleanup,
        )
    except base.UIError:
        for path in cleanup:
            try:
                path.unlink()
            except OSError:
                pass
        raise


def action_setup(payload: dict[str, Any]) -> dict[str, Any]:
    workflow = _workflow_name(payload)
    if not bool(payload.get("batch_mode")):
        return _single_setup(payload, workflow)
    mode = str(payload.get("mode") or "").strip()
    pipeline = str(payload.get("pipeline") or "").strip()
    batch._validate_pipeline(pipeline)
    cul = str(payload.get("cul") or "").strip()
    args = [
        "batch",
        "setup",
        "--workflow",
        workflow,
        "--mode",
        mode,
        "--pipeline",
        pipeline,
    ]
    cleanup: list[Path] = []
    if cul:
        args += ["--cul", cul]
    if mode == "ngs-report":
        case_text_value = str(payload.get("case_text") or "")
        try:
            parsed = batch.run_layout.parse_case_markdown(case_text_value)
        except batch.run_layout.LayoutError as exc:
            raise base.UIError(str(exc)) from exc
        batch_id = batch._new_batch_id(payload, f"cases-{len(parsed)}")
        source = base.case_path(batch_id)
        source.write_text(
            case_text_value if case_text_value.endswith("\n") else case_text_value + "\n",
            encoding="utf-8",
        )
        cleanup.append(source)
        args += ["--case", str(source), "--run-id", batch_id]
    else:
        suites = {row["mode"]: set(row.get("cases") or []) for row in batch._bundled_suites()}
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
            joined = ",".join(batch.run_layout.parse_case_ids(",".join(case_ids)))
        except batch.run_layout.LayoutError as exc:
            raise base.UIError(str(exc)) from exc
        batch_id = batch._new_batch_id(payload, f"{mode.removeprefix('nel-')}-{len(case_ids)}")
        args += ["--case-ids", joined, "--run-id", batch_id]
    argv = [sys.executable, "-u", str(base.ROOT / "nel.py"), *args]
    try:
        return base.REGISTRY.start(
            argv,
            run_id=batch_id,
            phase="setup",
            exclusive=base.is_local_pipeline(pipeline),
            cleanup=cleanup,
        )
    except base.UIError:
        for path in cleanup:
            try:
                path.unlink()
            except OSError:
                pass
        raise


# Handler methods in batch_server resolve these names in the batch_server module.
batch.list_pipelines = list_pipelines
batch.bootstrap = bootstrap
batch.save_pipeline = save_pipeline
batch.action_setup = action_setup

_PROVIDER_MODELS_SCRIPT = '<script src="/assets/provider-models.js"></script>'


def _serve_page_with_provider_models(self) -> None:
    """Serve the existing page and append provider/model UI enhancements."""
    if not batch.secrets.compare_digest(self._param("t"), batch.Handler.token):
        return self._text(
            "This page needs the session address printed in the terminal that started nel.py ui.\n",
            403,
        )
    try:
        text = batch.PAGE.read_text(encoding="utf-8")
    except OSError:
        return self._text(f"{batch.PAGE.relative_to(base.ROOT)} is missing\n", 500)
    if _PROVIDER_MODELS_SCRIPT not in text:
        text = text.replace("</body>", f"{_PROVIDER_MODELS_SCRIPT}\n</body>", 1)
    body = text.replace("__NEL_TOKEN__", batch.Handler.token).encode("utf-8")
    self._send(200, "text/html; charset=utf-8", body)


batch.Handler._serve_page = _serve_page_with_provider_models

_BATCH_HANDLE = batch.Handler._handle

def _handle_with_provider_models(self, path: str, method: str) -> Any:
    if method == "GET" and path == "/api/openrouter-models":
        return openrouter_models()
    if method == "GET" and path == "/api/openrouter-providers":
        return openrouter_model_providers(
            self._param("base_url"),
            self._param("model"),
            self._param("api_key_env"),
        )
    return _BATCH_HANDLE(self, path, method)

batch.Handler._handle = _handle_with_provider_models


def serve(port: int = 8765, open_browser: bool = True) -> int:
    return int(batch.serve(port=port, open_browser=open_browser))
