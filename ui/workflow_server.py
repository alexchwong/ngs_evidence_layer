"""Workflow-definition aware wrapper for the batch NEL browser server.

The existing :mod:`ui.batch_server` remains the batch/provider implementation.
This wrapper adds discovery and selection of declarative proforma-v1 workflow
YAMLs without duplicating workflow execution logic in the UI.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse
from ui import batch_server as batch
base = batch.base
from workflows.proforma_v1 import pipeline_registry
_BATCH_BOOTSTRAP = batch.bootstrap
_BATCH_LIST_PIPELINES = batch.list_pipelines
WORKFLOW_DIR = base.ROOT / "workflows" / "proforma_v1" / "workflow"
DEFAULT_WORKFLOW = "default"
OPENROUTER_MODELS_PATH = base.ROOT / "config" / "openrouter_models.json"
MODEL_ACTIVITY_DIR = base.ROOT / ".nel-ui" / "activity"
OPENROUTER_CATEGORIES = {
    "Fast / Cheap",
    "High Quality",
    "Fast & Local-compatible",
}

PROVIDER_CLASSES = {"lmstudio", "openrouter", "other"}
REASONING_LEVELS = ("default", "none", "minimal", "low", "medium", "high", "xhigh")
LMSTUDIO_REASONING_LEVELS = ("default", "low", "medium", "high")
LMSTUDIO_MIN_VERSION = "0.3.29"

_SETUP_CREDENTIAL = threading.local()
_BASE_CHILD_ENV = base.child_env
def _ui_child_env() -> dict[str, str]:
    """Opt UI-launched provider processes into transient live streaming.

    Setup is deterministic and never calls a provider.  When the selected
    profile requires a credential that has not yet been supplied, a per-thread
    sentinel lets the CLI configuration check complete without placing a fake
    credential in shared process state.  Run-time provider calls never receive
    this sentinel.
    """
    env = _BASE_CHILD_ENV()
    env["NEL_MODEL_STREAM"] = "1"
    env["NEL_MODEL_ACTIVITY_DIR"] = str(MODEL_ACTIVITY_DIR)
    setup_env = str(getattr(_SETUP_CREDENTIAL, "env_name", "") or "").strip()
    if setup_env and not str(env.get(setup_env) or "").strip():
        env[setup_env] = "__NEL_UI_SETUP_ONLY__"
    return env

base.child_env = _ui_child_env


def _profile_credential_status(pipeline: str) -> dict[str, Any]:
    pipeline = str(pipeline or "").strip()
    if not pipeline:
        return {
            "pipeline": "", "required": False, "env": "", "set": True,
            "credential_required": False,
        }
    doc = base.read_pipeline(pipeline)
    provider = doc.get("provider") or {}
    if not isinstance(provider, dict):
        provider = {}
    required = bool(provider.get("api_key_required"))
    env_name = str(provider.get("api_key_env") or "").strip()
    value = str(base.SECRETS.get(env_name) or os.environ.get(env_name) or "").strip() if env_name else ""
    return {
        "pipeline": pipeline,
        "required": required,
        "env": env_name,
        "set": bool(value) if required else True,
        "credential_required": bool(required and env_name and not value),
    }


_BASE_CONFIG_CHECK = base.config_check
def _ui_config_check(pipeline: str, cul: str = "") -> dict[str, Any]:
    """Keep credential readiness separate from structural profile validity."""
    doc = dict(_BASE_CONFIG_CHECK(pipeline, cul))
    selected = str(pipeline or doc.get("pipeline") or "").strip()
    try:
        credential = _profile_credential_status(selected)
    except base.UIError:
        credential = {
            "pipeline": selected, "required": False, "env": "", "set": True,
            "credential_required": False,
        }
    errors = [str(item) for item in (doc.get("errors") or [])]
    credential_errors: list[str] = []
    env_name = str(credential.get("env") or "")
    if credential.get("credential_required") and env_name:
        marker = f"requires environment variable {env_name}"
        kept: list[str] = []
        for error in errors:
            if marker in error:
                credential_errors.append(error)
            else:
                kept.append(error)
        errors = kept
    doc["errors"] = errors
    doc["credential_required"] = bool(credential.get("credential_required"))
    doc["credential_env"] = env_name
    doc["credential_errors"] = credential_errors
    doc["ok"] = not errors
    return doc

base.config_check = _ui_config_check


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


def _complete_payload_roles(payload: dict[str, Any]) -> dict[str, Any]:
    """Complete a sparse UI profile from the workflow-agnostic role catalogue."""
    out = copy.deepcopy(payload)
    roles_in = out.get("roles")
    aliases = out.get("aliases")
    if not isinstance(roles_in, dict) or not isinstance(aliases, list):
        return out
    first_alias = ""
    for row in aliases:
        if isinstance(row, dict) and str(row.get("alias") or "").strip():
            first_alias = str(row["alias"]).strip()
            break
    if not first_alias:
        return out
    defaults = pipeline_registry.role_defaults()
    for role in pipeline_registry.ROLES:
        if role in roles_in:
            continue
        default = dict(defaults[role])
        default["model"] = first_alias
        roles_in[role] = default
    return out


def _profile_for_editor(name: str) -> dict[str, Any]:
    """Present sparse profiles with all known role defaults without rewriting disk."""
    return pipeline_registry.with_role_defaults(base.read_pipeline(name))


def _apply_role_reasoning(doc: dict[str, Any], payload: dict[str, Any]) -> None:
    """Copy optional UI reasoning settings into model_roles after base composition."""
    roles_in = payload.get("roles") or {}
    roles_doc = doc.get("model_roles") or {}
    if not isinstance(roles_in, dict) or not isinstance(roles_doc, dict):
        return
    for role, target in roles_doc.items():
        if not isinstance(target, dict):
            continue
        source = roles_in.get(role) or {}
        if not isinstance(source, dict):
            continue
        effort = str(source.get("reasoning") or "default").strip().lower()
        if effort not in REASONING_LEVELS:
            raise base.UIError(
                f"role {role} reasoning must be one of: {', '.join(REASONING_LEVELS)}"
            )
        target["reasoning"] = effort


def _validate_provider_reasoning(doc: dict[str, Any], provider_class: str) -> None:
    rows = doc.get("model_roles") or {}
    if not isinstance(rows, dict):
        return
    for role, row in rows.items():
        if not isinstance(row, dict):
            continue
        effort = str(row.get("reasoning") or "default").strip().lower()
        if provider_class == "openrouter":
            allowed = REASONING_LEVELS
        elif provider_class == "lmstudio":
            allowed = LMSTUDIO_REASONING_LEVELS
        else:
            allowed = ("default",)
        if effort not in allowed:
            if provider_class == "lmstudio":
                raise base.UIError(
                    f"role {role} reasoning {effort!r} is not supported for LM Studio; "
                    f"choose one of: {', '.join(allowed)}. "
                    f"NEL supports LM Studio {LMSTUDIO_MIN_VERSION}+ via /v1/responses."
                )
            raise base.UIError(
                f"role {role} reasoning must be Default for provider class {provider_class}"
            )


def save_pipeline(payload: dict[str, Any]) -> dict[str, Any]:
    """Save a workflow-agnostic profile with missing known roles defaulted."""
    payload = _complete_payload_roles(payload)
    name, doc = base.compose_pipeline(payload)
    _apply_role_reasoning(doc, payload)
    requested = str(payload.get("provider_class") or "").strip().lower()
    provider_class = requested if requested in PROVIDER_CLASSES else _infer_provider_class(name, doc)
    _validate_provider_reasoning(doc, provider_class)
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
    doc["reasoning_levels"] = list(REASONING_LEVELS)
    doc["lmstudio_reasoning_levels"] = list(LMSTUDIO_REASONING_LEVELS)
    doc["lmstudio_min_version"] = LMSTUDIO_MIN_VERSION
    doc["role_defaults"] = pipeline_registry.role_defaults()
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


def _start_setup(argv: list[str], *, run_id: str, pipeline: str, cleanup: list[Path]) -> dict[str, Any]:
    """Start deterministic setup while deferring a missing provider credential."""
    status = _profile_credential_status(pipeline)
    _SETUP_CREDENTIAL.env_name = status.get("env") if status.get("credential_required") else ""
    try:
        return base.REGISTRY.start(
            argv,
            run_id=run_id,
            phase="setup",
            exclusive=base.is_local_pipeline(pipeline),
            cleanup=cleanup,
        )
    finally:
        _SETUP_CREDENTIAL.env_name = ""


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
        return _start_setup(argv, run_id=run_id, pipeline=pipeline, cleanup=cleanup)
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
        return _start_setup(argv, run_id=batch_id, pipeline=pipeline, cleanup=cleanup)
    except base.UIError:
        for path in cleanup:
            try:
                path.unlink()
            except OSError:
                pass
        raise


def run_credential_status(run_ref: str) -> dict[str, Any]:
    """Credential readiness for the frozen pipeline of a run/batch selection."""
    run_ref = str(run_ref or "").strip()
    kind = batch._top_kind(run_ref)
    if kind == "batch":
        pipeline = str(batch._batch_location(run_ref).manifest.get("pipeline") or "")
    elif kind in {"run", "batch-child"}:
        pipeline = str(batch._run_location(run_ref).manifest.get("pipeline") or "")
    else:
        raise base.UIError("credential status is unavailable for legacy/invalid runs", 409)
    return _profile_credential_status(pipeline)


_BATCH_ACTION_RUN = batch.action_run
def action_run(payload: dict[str, Any]) -> dict[str, Any]:
    run_ref = str(payload.get("run_id") or "").strip()
    credential = run_credential_status(run_ref)
    if credential.get("credential_required"):
        env_name = str(credential.get("env") or "API key")
        raise base.UIError(
            f"{env_name} is required before starting pipeline {credential.get('pipeline')!r}",
            401,
        )
    return _BATCH_ACTION_RUN(payload)


# Handler methods in batch_server resolve these names in the batch_server module.
batch.list_pipelines = list_pipelines
batch.bootstrap = bootstrap
batch.save_pipeline = save_pipeline
batch.action_setup = action_setup
batch.action_run = action_run

_RUN_CREDENTIALS_SCRIPT = '<script src="/assets/run-credentials.js"></script>'
_PROVIDER_MODELS_SCRIPT = '<script src="/assets/provider-models.js"></script>'
_ROLE_REASONING_SCRIPT = '<script src="/assets/role-reasoning.js"></script>'
_MODEL_ACTIVITY_SCRIPT = '<script src="/assets/model-activity.js"></script>'

def _serve_page_with_provider_models(self) -> None:
    """Serve the existing page and append provider/model and activity UI enhancements."""
    if not batch.secrets.compare_digest(self._param("t"), batch.Handler.token):
        return self._text(
            "This page needs the session address printed in the terminal that started nel.py ui.\n",
            403,
        )
    try:
        text = batch.PAGE.read_text(encoding="utf-8")
    except OSError:
        return self._text(f"{batch.PAGE.relative_to(base.ROOT)} is missing\n", 500)
    for script in (_RUN_CREDENTIALS_SCRIPT, _PROVIDER_MODELS_SCRIPT, _ROLE_REASONING_SCRIPT, _MODEL_ACTIVITY_SCRIPT):
        if script not in text:
            text = text.replace("</body>", f"{script}\n</body>", 1)
    body = text.replace("__NEL_TOKEN__", batch.Handler.token).encode("utf-8")
    self._send(200, "text/html; charset=utf-8", body)

batch.Handler._serve_page = _serve_page_with_provider_models

def _model_activity_path(run_ref: str) -> Path | None:
    kind = batch._top_kind(run_ref)
    if kind not in {"run", "batch-child"}:
        return None
    # Resolve the run as a validation/containment check before deriving the
    # transient session filename. No run path is exposed to the browser.
    batch._run_location(run_ref)
    digest = hashlib.sha256(run_ref.encode("utf-8")).hexdigest()
    return MODEL_ACTIVITY_DIR / f"{digest}.jsonl"

def model_activity(run_ref: str, offset: int) -> dict[str, Any]:
    path = _model_activity_path(run_ref)
    if path is None:
        return {"offset": 0, "text": "", "size": 0}
    return batch._read_offset(path, offset)

_BATCH_HANDLE = batch.Handler._handle
def _handle_with_provider_models(self, path: str, method: str) -> Any:
    if method == "GET" and path == "/api/model-activity":
        try:
            offset = int(self._param("offset", "0"))
        except ValueError:
            offset = 0
        return model_activity(self._param("run"), offset)
    if method == "GET" and path == "/api/openrouter-models":
        return openrouter_models()
    if method == "GET" and path == "/api/openrouter-providers":
        return openrouter_model_providers(
            self._param("base_url"),
            self._param("model"),
            self._param("api_key_env"),
        )
    if method == "GET" and path == "/api/pipeline":
        name = str(self._param("name") or "")
        return {"name": name, "doc": _profile_for_editor(name), "roles": list(pipeline_registry.ROLES)}
    if method == "GET" and path == "/api/run-credential":
        return run_credential_status(self._param("run"))
    return _BATCH_HANDLE(self, path, method)

batch.Handler._handle = _handle_with_provider_models

def _clear_model_activity() -> None:
    """Remove transient provider reasoning/output from the local UI session."""
    MODEL_ACTIVITY_DIR.mkdir(parents=True, exist_ok=True)
    for path in MODEL_ACTIVITY_DIR.glob("*.jsonl"):
        try:
            path.unlink()
        except OSError:
            pass

def serve(port: int = 8765, open_browser: bool = True) -> int:
    # Model reasoning/output is UI-session state, not a run/provenance artifact.
    _clear_model_activity()
    try:
        return int(batch.serve(port=port, open_browser=open_browser))
    finally:
        _clear_model_activity()
