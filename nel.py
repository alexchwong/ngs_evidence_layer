#!/usr/bin/env python3
"""Root product CLI for the canonical proforma-v1 NGS Evidence Layer workflow.

End users interact with this file, root configuration, and ``runs/`` only. New
runs use ``workflows/proforma_v1``. The previous terraced-v6 workflow is available
only through an explicit ``--legacy`` setup/configuration path or a frozen run manifest.
Run layout is explicit: single runs require ``run.json``; batch roots require
``batch.json`` and contain manifested child runs. Legacy unmanifested run folders
are intentionally unsupported.
"""
from __future__ import annotations
import argparse
import contextlib
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from collections import OrderedDict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
ROOT = Path(__file__).resolve().parent
RUNS_DIR = ROOT / "runs"
LATEST_PATH = RUNS_DIR / "LATEST"
CONFIG_DIR = ROOT / "config"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
SETTINGS_TEMPLATE_PATH = CONFIG_DIR / "settings.json.template"
PANEL_SCOPE_PATH = CONFIG_DIR / "ngs-panel-scope.md"
PIPELINES_DIR = CONFIG_DIR / "pipelines"
LEGACY_WORKFLOW_DIR = ROOT / "workflows" / "terraced_v6"
LEGACY_SETTINGS_PATH = LEGACY_WORKFLOW_DIR / "settings.json"
LEGACY_SETTINGS_TEMPLATE_PATH = LEGACY_WORKFLOW_DIR / "settings.json.template"
LEGACY_PIPELINES_DIR = LEGACY_WORKFLOW_DIR / "pipelines"
CUL_DIR = CONFIG_DIR / "cul"
VERSION_PATH = ROOT / "release" / "VERSION"
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
CANONICAL_WORKFLOW = "proforma-v1"
LEGACY_WORKFLOW = "terraced-v6"
SUPPORTED_RUN_WORKFLOWS = {CANONICAL_WORKFLOW, LEGACY_WORKFLOW}
PROFORMA_WORKFLOW_DIR = ROOT / "workflows" / "proforma_v1" / "workflow"
DEFAULT_WORKFLOW_DEFINITION = "default"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
DEFAULT_CLOUD_PARALLEL = 4
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import run_layout


class CLIError(RuntimeError):
    pass


def _layout_error(exc: Exception) -> CLIError:
    return CLIError(str(exc))

def _json_load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CLIError(f"required file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CLIError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CLIError(f"expected JSON object: {path}")
    return value

def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None

def _version() -> str | None:
    try:
        value = VERSION_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None

def _workflow_modules(workflow_id: str = CANONICAL_WORKFLOW):
    if workflow_id == CANONICAL_WORKFLOW:
        from workflows.proforma_v1 import pipeline_registry, self as self_executor, step
    elif workflow_id == LEGACY_WORKFLOW:
        from workflows.terraced_v6 import pipeline_registry, self as self_executor, step
    else:
        raise CLIError(f"unsupported run workflow: {workflow_id}")
    return step, self_executor, pipeline_registry

def _workflow_config_paths(workflow_id: str) -> tuple[Path, Path, Path]:
    if workflow_id == CANONICAL_WORKFLOW:
        return SETTINGS_PATH, SETTINGS_TEMPLATE_PATH, PIPELINES_DIR
    if workflow_id == LEGACY_WORKFLOW:
        return LEGACY_SETTINGS_PATH, LEGACY_SETTINGS_TEMPLATE_PATH, LEGACY_PIPELINES_DIR
    raise CLIError(f"unsupported run workflow: {workflow_id}")

def _workflow_definitions() -> tuple[str, ...]:
    return tuple(
        sorted(
            path.stem
            for path in PROFORMA_WORKFLOW_DIR.glob("*.yaml")
            if path.is_file() and RUN_ID_RE.fullmatch(path.stem)
        )
    )


def _resolve_workflow_definition(value: str | None) -> tuple[str, Path]:
    name = str(value or DEFAULT_WORKFLOW_DEFINITION).strip()
    if not RUN_ID_RE.fullmatch(name):
        raise CLIError(
            "workflow definition must be a filename stem using letters, numbers, dot, underscore or hyphen"
        )
    path = PROFORMA_WORKFLOW_DIR / f"{name}.yaml"
    if not path.is_file():
        available = _workflow_definitions()
        raise CLIError(
            f"unknown workflow definition {name!r}; available: "
            + (", ".join(available) if available else "none")
        )
    return name, path.resolve()


def _configure_workflow(
    workflow_id: str = CANONICAL_WORKFLOW,
    *, settings_path: Path | None = None, pipelines_dir: Path | None = None,
):
    default_settings, _template, default_pipelines = _workflow_config_paths(workflow_id)
    settings_path = Path(settings_path) if settings_path is not None else default_settings
    pipelines_dir = Path(pipelines_dir) if pipelines_dir is not None else default_pipelines
    step, self_executor, pipeline_registry = _workflow_modules(workflow_id)
    step.configure_runtime(settings_path=settings_path, pipelines_dir=pipelines_dir)
    return step, self_executor, pipeline_registry

def _supported_modes(workflow_id: str = CANONICAL_WORKFLOW) -> tuple[str, ...]:
    step, _self_executor, _registry = _workflow_modules(workflow_id)
    return tuple(step.supported_modes())


def _validation_modes(workflow_id: str = CANONICAL_WORKFLOW) -> set[str]:
    return {mode for mode in _supported_modes(workflow_id) if mode.startswith("nel-validate")}

def _validate_run_id(value: str) -> str:
    try:
        return run_layout.validate_id(value, label="run ID")
    except run_layout.LayoutError as exc:
        raise _layout_error(exc) from exc


def _slug(value: str) -> str:
    return run_layout.slug(value)

def _generated_run_id(mode: str, *, case: Path | None, example: int | None, case_id: str | None) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if mode == "ngs-report" and case is not None:
        label = case.stem
    elif mode == "nel-demo" and example is not None:
        label = f"demo-{example}"
    elif case_id:
        label = f"{mode.removeprefix('nel-')}-{case_id}"
    else:
        label = mode
    return f"{stamp}-{_slug(label)}"

def _generated_batch_id(label: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"batch-{stamp}-{_slug(label)}"


def _top_dir(run_id: str) -> Path:
    return RUNS_DIR / _validate_run_id(run_id)

def _latest_run_id() -> str:
    try:
        value = LATEST_PATH.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise CLIError("no latest run is recorded; run 'python nel.py setup ...' first") from exc
    run_id = _validate_run_id(value)
    try:
        run_layout.resolve_run(RUNS_DIR, run_id)
    except run_layout.LayoutError as exc:
        raise CLIError(f"LATEST is invalid: {exc}") from exc
    return run_id

def _resolve_run(run_id: str | None) -> tuple[str, Path]:
    ref = str(run_id).strip() if run_id else _latest_run_id()
    try:
        location = run_layout.resolve_run(RUNS_DIR, ref)
    except run_layout.LayoutError as exc:
        raise _layout_error(exc) from exc
    return location.run_id, location.path

def _resolve_batch(batch_id: str) -> run_layout.BatchLocation:
    try:
        return run_layout.resolve_batch(RUNS_DIR, batch_id)
    except run_layout.LayoutError as exc:
        raise _layout_error(exc) from exc


def _run_identity(run: Path) -> dict[str, Any]:
    try:
        return run_layout.load_run_manifest(run)
    except run_layout.LayoutError as exc:
        raise _layout_error(exc) from exc

def _run_pipeline(run: Path) -> str | None:
    identity = _run_identity(run)
    value = identity.get("pipeline")
    return str(value) if isinstance(value, str) and value else None


def _run_workflow(run: Path) -> str | None:
    identity = _run_identity(run)
    value = identity.get("workflow")
    return str(value) if isinstance(value, str) and value else None


def _run_workflow_definition(run: Path) -> str | None:
    if _run_workflow(run) != CANONICAL_WORKFLOW:
        return None
    manifest = _json_load(Path(run) / "run-config" / "manifest.json")
    value = manifest.get("workflow_definition")
    return str(value) if isinstance(value, str) and value else DEFAULT_WORKFLOW_DEFINITION

def _marking_state(run: Path) -> dict[str, Any]:
    """Return non-blocking automatic-marking state for a canonical run."""
    if _run_workflow(run) != CANONICAL_WORKFLOW:
        return {"applicable": False, "status": "not_applicable"}
    try:
        from validation.scripts.package_marking import inspect_marking
        return inspect_marking(run)
    except Exception as exc:
        return {"applicable": False, "status": "unavailable", "error": str(exc)}


def inspect_run(run: Path) -> dict[str, Any]:
    run = Path(run)
    pipeline = _run_pipeline(run)
    workflow_id = _run_workflow(run)
    if not pipeline or workflow_id not in SUPPORTED_RUN_WORKFLOWS:
        return {
            "label": "Unrecognized", "stage": "unknown", "next": "inspect run",
            "complete": False, "pipeline": pipeline, "mode": None,
        }
    step, self_executor, _registry = _workflow_modules(workflow_id)
    status = self_executor.inspect_run(run) if pipeline == "self" else step.inspect_run(run)
    status = dict(status)
    if workflow_id == CANONICAL_WORKFLOW:
        status["workflow_definition"] = _run_workflow_definition(run)
        status["marking"] = _marking_state(run)
    return status

def corpus_core_blacklist_path() -> str:
    from scripts.core import corpus as corpus_core
    return str(corpus_core.DEFAULT_BLACKLIST)

def _resolve_cul(name: str | None, corpus_doc, cards) -> tuple[dict, list[str]]:
    from scripts.core import cul as cul_core
    warnings: list[str] = []
    requested = (name or "").strip() or cul_core.DEFAULT_PROFILE
    path = cul_core.profile_path(requested, cul_dir=CUL_DIR)
    if not path.is_file():
        if name:
            available = cul_core.available_profiles(cul_dir=CUL_DIR)
            raise CLIError(
                f"unknown CUL profile {requested!r}; available: "
                + (", ".join(available) if available else "none")
            )
        legacy = Path(corpus_core_blacklist_path())
        if legacy.is_file():
            warnings.append(
                f"no CUL profile at {path}; falling back to the deprecated {legacy.name}. "
                "Run 'python scripts/cul.py new --cul default' to migrate."
            )
            raw = {
                "schema_version": cul_core.SCHEMA_VERSION,
                "profile": cul_core.DEFAULT_PROFILE,
                "description": "Compatibility layer derived from legacy blacklist.json.",
                "scope": json.loads(legacy.read_text(encoding="utf-8")),
                "amendments": {},
            }
            return cul_core.resolve_profile(
                raw, corpus_document=corpus_doc, cards=cards, source=str(legacy)
            ), warnings
        return cul_core.empty_layer(), warnings
    layer = cul_core.load_profile(path, corpus_document=corpus_doc, cards=cards, strict=False)
    if layer.get("stale"):
        raise CLIError(
            f"CUL profile {requested!r} has stale amendment(s): " + ", ".join(layer["stale"])
            + "\nThese were authored against corpus cards that have since changed. "
            "Review them in the card browser, or run: "
            f"python scripts/cul.py check --cul {requested}"
        )
    return layer, warnings

def _legacy_settings_warnings(settings: dict[str, Any]) -> list[str]:
    found: list[str] = []
    diagnosis = settings.get("diagnosis") or {}
    who5 = diagnosis.get("who5") or {} if isinstance(diagnosis, dict) else {}
    if isinstance(who5, dict) and "max_cmc_passes" in who5:
        found.append("diagnosis.who5.max_cmc_passes")
    if isinstance(diagnosis, dict) and "other" in diagnosis:
        found.append("diagnosis.other")
    reportability = settings.get("reportability") or {}
    domains = reportability.get("domains") or {} if isinstance(reportability, dict) else {}
    if isinstance(domains, dict):
        dx = domains.get("diagnosis") or {}
        if isinstance(dx, dict) and "second_diagnosis" in dx:
            found.append("reportability.domains.diagnosis.second_diagnosis")
        prognosis = domains.get("prognosis") or {}
        if isinstance(prognosis, dict):
            for key in ("favorable", "adverse", "neutral", "uncertain", "prognostic_score"):
                if key in prognosis:
                    found.append(f"reportability.domains.prognosis.{key}")
        germline = domains.get("germline") or {}
        if isinstance(germline, dict) and "germline_support" in germline:
            found.append("reportability.domains.germline.germline_support")
    prompts = settings.get("prompts") or {}
    if isinstance(prompts, dict) and "diagnosis_other" in prompts:
        found.append("prompts.diagnosis_other")
    if not found:
        return []
    return [
        "config/settings.json contains legacy terraced-v6 key(s): " + ", ".join(found)
        + ". The file was not modified; review it against config/settings.json.template before relying on custom behavior."
    ]

def _config_check(
    workflow_id: str = CANONICAL_WORKFLOW,
    pipeline: str | None = None,
    cul: str | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    selected = pipeline
    names: tuple[str, ...] = ()
    plans: dict[str, Any] = {}
    settings_path, settings_template, pipelines_dir = _workflow_config_paths(workflow_id)
    try:
        if workflow_id == CANONICAL_WORKFLOW and not settings_path.is_file():
            raise CLIError(f"settings file is missing: {settings_path}")
        if not settings_path.is_file() and not settings_template.is_file():
            raise CLIError(f"settings template is missing: {settings_template}")
        step, _self_executor, registry = _configure_workflow(workflow_id)
        settings = step.load_settings()
        if workflow_id == CANONICAL_WORKFLOW and settings_path.is_file():
            warnings.extend(_legacy_settings_warnings(_json_load(settings_path)))
        selected = selected or str(settings.get("pipeline") or "self")
        names = tuple(sorted(path.stem for path in pipelines_dir.glob("*.yaml")))
        if not names:
            raise CLIError(f"no pipeline YAML files found in {pipelines_dir}")
        if selected not in names:
            raise CLIError(
                f"configured pipeline {selected!r} is unavailable; choose one of: {', '.join(names)}"
            )
        selected_path = pipelines_dir / f"{selected}.yaml"
        try:
            plan = registry.load_yaml(selected_path)
        except Exception as exc:
            raise CLIError(f"pipeline {selected!r} failed validation ({selected_path}): {exc}") from exc
        plans[selected] = plan
        for warning in getattr(plan, "warnings", ()):
            if warning not in warnings:
                warnings.append(warning)
        provider = plan.doc.get("provider") or {}
        env_name = str(provider.get("api_key_env") or "")
        if provider.get("api_key_required") is True and env_name and not os.environ.get(env_name, "").strip():
            errors.append(f"pipeline {selected!r} requires environment variable {env_name}")
    except Exception as exc:
        errors.append(str(exc))
    if not PANEL_SCOPE_PATH.is_file() or not PANEL_SCOPE_PATH.read_text(encoding="utf-8").strip():
        errors.append(f"NGS panel scope is missing or empty: {PANEL_SCOPE_PATH}")
    corpus_sha = None
    cul_layer = None
    try:
        from scripts.core import corpus as corpus_core
        from scripts.core import cul as cul_core
        corpus_doc, _index, corpus_sha = corpus_core.load_corpus(
            corpus_core.DEFAULT_CORPUS, corpus_core.DEFAULT_INDEX
        )
        cards = corpus_core.flatten(corpus_doc)
        cul_layer, cul_warnings = _resolve_cul(cul, corpus_doc, cards)
        warnings.extend(cul_warnings)
        cul_core.eligible_cards(cards, cul_layer, verbose=False)
    except Exception as exc:
        errors.append(f"corpus check failed: {exc}")
    workflow_dir = ROOT / "workflows" / ("proforma_v1" if workflow_id == CANONICAL_WORKFLOW else "terraced_v6")
    workflow_path = workflow_dir / "workflow.json"
    if not workflow_path.is_file():
        errors.append(f"{workflow_id} implementation is missing: {workflow_path}")
    try:
        from scripts.workflow_registry import load_registry
        workflow_registry = load_registry()
        if workflow_registry.get("default_workflow") != CANONICAL_WORKFLOW:
            warnings.append(f"workflow registry default is not {CANONICAL_WORKFLOW}")
    except Exception as exc:
        errors.append(f"workflow registry check failed: {exc}")
    return {
        "ok": not errors, "workflow": workflow_id, "pipeline": selected,
        "pipelines": sorted(names), "corpus_sha256": corpus_sha,
        "cul_profile": (cul_layer or {}).get("profile"),
        "cul_sha256": (cul_layer or {}).get("cul_sha256"),
        "cul_layer": cul_layer, "errors": errors, "warnings": warnings,
    }

def _ensure_config_ok(workflow_id: str, pipeline: str | None, cul: str | None = None) -> dict[str, Any]:
    result = _config_check(workflow_id, pipeline, cul)
    if not result["ok"]:
        raise CLIError("configuration check failed:\n- " + "\n- ".join(result["errors"]))
    return result

def _initialize_user_settings(workflow_id: str = CANONICAL_WORKFLOW) -> bool:
    settings_path, settings_template, _pipelines_dir = _workflow_config_paths(workflow_id)
    if settings_path.is_file():
        return False
    if not settings_template.is_file():
        raise CLIError(f"settings template is missing: {settings_template}")
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(settings_template, settings_path)
    return True

def cmd_init(args: argparse.Namespace) -> int:
    workflow_id = LEGACY_WORKFLOW if getattr(args, "legacy", False) else CANONICAL_WORKFLOW
    created = _initialize_user_settings(workflow_id)
    settings_path, _settings_template, pipelines_dir = _workflow_config_paths(workflow_id)
    print(f"STATUS={'created' if created else 'existing'}")
    print(f"WORKFLOW={workflow_id}")
    print(f"SETTINGS={settings_path.resolve()}")
    print(f"PIPELINES={pipelines_dir.resolve()}")
    return 0

def _snapshot_run_config(
    run: Path, *, run_id: str, workflow_id: str, mode: str, pipeline: str,
    config_result: dict[str, Any], workflow_definition: str | None = None,
) -> None:
    from scripts.core import cul as cul_core
    target = run / "run-config"
    target.mkdir(parents=True, exist_ok=False)
    settings_path, settings_template, pipelines_dir = _workflow_config_paths(workflow_id)
    settings = _json_load(settings_path if settings_path.is_file() else settings_template)
    settings["pipeline"] = pipeline
    (target / "settings.json").write_text(
        json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    pipeline_target = target / "pipelines"
    pipeline_target.mkdir()
    source_pipeline = pipelines_dir / f"{pipeline}.yaml"
    if not source_pipeline.is_file():
        raise CLIError(f"selected pipeline file is missing: {source_pipeline}")
    (pipeline_target / source_pipeline.name).write_bytes(source_pipeline.read_bytes())
    (target / "ngs-panel-scope.md").write_bytes(PANEL_SCOPE_PATH.read_bytes())
    cul_layer = config_result.get("cul_layer") or cul_core.empty_layer()
    cul_core.freeze(cul_layer, target / "cul.json")
    manifest = {
        "schema_version": 1, "run_id": run_id, "workflow": workflow_id,
        "mode": mode, "pipeline": pipeline,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "nel_version": _version(), "git_commit": _git_commit(),
        "corpus_sha256": config_result.get("corpus_sha256"),
        "cul_profile": cul_layer.get("profile"), "cul_sha256": cul_layer.get("cul_sha256"),
    }
    if workflow_id == CANONICAL_WORKFLOW:
        manifest["workflow_definition"] = workflow_definition or DEFAULT_WORKFLOW_DEFINITION
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

def _bind_frozen_cul(config: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    from scripts.core import cul as cul_core
    path = config / "cul.json"
    if not path.is_file():
        os.environ.pop(cul_core.ENV_ACTIVE_LAYER, None)
        return cul_core.empty_layer()
    layer = cul_core.load_frozen(path)
    expected = manifest.get("cul_sha256")
    if expected and expected != layer.get("cul_sha256"):
        raise CLIError(
            "frozen corpus user layer does not match the digest recorded at setup; start a new run"
        )
    os.environ[cul_core.ENV_ACTIVE_LAYER] = str(path.resolve())
    return layer

def _bind_run_config(run: Path):
    config = run / "run-config"
    settings = config / "settings.json"
    pipelines = config / "pipelines"
    manifest_path = config / "manifest.json"
    if not settings.is_file() or not pipelines.is_dir() or not manifest_path.is_file():
        raise CLIError(f"run configuration snapshot is missing: {config}")
    manifest = _json_load(manifest_path)
    _bind_frozen_cul(config, manifest)
    expected_corpus = manifest.get("corpus_sha256")
    if expected_corpus:
        from scripts.core import corpus as corpus_core
        _doc, _index, current_corpus = corpus_core.load_corpus(
            corpus_core.DEFAULT_CORPUS, corpus_core.DEFAULT_INDEX
        )
        if current_corpus != expected_corpus:
            raise CLIError(
                "current corpus differs from the corpus captured at setup; "
                "restore the recorded corpus or start a new run"
            )
    workflow_id = manifest.get("workflow") or _run_workflow(run)
    if workflow_id not in SUPPORTED_RUN_WORKFLOWS:
        raise CLIError(f"unsupported or missing run workflow in {manifest_path}: {workflow_id!r}")
    return _configure_workflow(workflow_id, settings_path=settings, pipelines_dir=pipelines)

def _write_identity_manifest(
    run: Path, *, run_id: str, workflow_id: str, mode: str, pipeline: str,
    batch_id: str | None = None, case_id: str | None = None, case_title: str | None = None,
) -> None:
    try:
        run_layout.write_run_manifest(
            run, run_id=run_id, workflow=workflow_id, mode=mode, pipeline=pipeline,
            created_at=datetime.now(timezone.utc).isoformat(), batch_id=batch_id,
            case_id=case_id, case_title=case_title,
        )
    except run_layout.LayoutError as exc:
        raise _layout_error(exc) from exc

def _prepare_run_at(
    run: Path, *, run_id: str, workflow_id: str, mode: str, pipeline: str,
    config_result: dict[str, Any], case: Path | None = None, example: int | None = None,
    validation_case_id: str | None = None, batch_id: str | None = None,
    child_case_id: str | None = None, case_title: str | None = None,
    workflow_definition: str | None = None,
) -> int:
    if run.exists():
        raise CLIError(f"run already exists; refusing to overwrite: {run_id}")
    run.parent.mkdir(parents=True, exist_ok=True)
    step, self_executor, _registry = _configure_workflow(workflow_id)
    argv = ["setup", "--mode", mode, "--work-dir", str(run)]
    if workflow_id == CANONICAL_WORKFLOW:
        workflow_definition, workflow_path = _resolve_workflow_definition(workflow_definition)
        argv += ["--workflow", str(workflow_path)]
    elif workflow_definition is not None:
        raise CLIError("--workflow is valid only for proforma-v1; omit it with --legacy")
    if pipeline != "self":
        argv += ["--pipeline", pipeline]
    if case is not None:
        argv += ["--case-file", str(case)]
    if example is not None:
        argv += ["--example", str(example)]
    if validation_case_id:
        argv += ["--case-id", str(validation_case_id)]
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured):
            code = int((self_executor if pipeline == "self" else step).main(argv))
        if code != 0:
            shutil.rmtree(run, ignore_errors=True)
            return code
        _snapshot_run_config(
            run, run_id=run_id, workflow_id=workflow_id, mode=mode,
            pipeline=pipeline, config_result=config_result,
            workflow_definition=workflow_definition,
        )
        _write_identity_manifest(
            run, run_id=run_id, workflow_id=workflow_id, mode=mode, pipeline=pipeline,
            batch_id=batch_id, case_id=child_case_id, case_title=case_title,
        )
    except Exception:
        shutil.rmtree(run, ignore_errors=True)
        raise
    return 0

def _print_run_header(run_id: str, run: Path, status: dict[str, Any]) -> None:
    print(f"RUN_ID={run_id}")
    print(f"RUN_DIR={run.resolve()}")
    print(f"STATUS={'complete' if status['complete'] else 'incomplete'}")
    print(f"STAGE={status['stage']}")
    if status.get("next"):
        print(f"NEXT={status['next']}")
    if status.get("pipeline"):
        print(f"PIPELINE={status['pipeline']}")
    if status.get("workflow_definition"):
        print(f"WORKFLOW_DEFINITION={status['workflow_definition']}")
    marking = status.get("marking") or {}
    if marking.get("applicable"):
        print(f"MARKING_STATUS={marking.get('status') or 'pending'}")

def cmd_setup(args: argparse.Namespace) -> int:
    workflow_id = LEGACY_WORKFLOW if getattr(args, "legacy", False) else CANONICAL_WORKFLOW
    if workflow_id == LEGACY_WORKFLOW and getattr(args, "workflow", None) is not None:
        raise CLIError("--workflow is valid only for proforma-v1; omit it with --legacy")
    workflow_definition = None
    if workflow_id == CANONICAL_WORKFLOW:
        workflow_definition, _workflow_path = _resolve_workflow_definition(getattr(args, "workflow", None))
    mode = args.mode
    if mode not in _supported_modes(workflow_id):
        raise CLIError(
            f"mode {mode!r} is not supported by {workflow_id}; choose one of: "
            + ", ".join(_supported_modes(workflow_id))
        )
    case = args.case.expanduser().resolve() if args.case else None
    if mode == "ngs-report" and case is None:
        raise CLIError("ngs-report setup requires --case <case.md>")
    if mode == "ngs-report" and (not case.is_file() or not case.read_text(encoding="utf-8").strip()):
        raise CLIError(f"case file is missing or empty: {case}")
    if mode == "nel-demo" and args.example is None:
        raise CLIError("nel-demo setup requires --example <N>")
    if mode != "nel-demo" and args.example is not None:
        raise CLIError("--example is valid only with --mode nel-demo")
    if mode in _validation_modes(workflow_id) and not args.case_id:
        raise CLIError(f"{mode} setup requires --case-id <ID>")
    if mode not in _validation_modes(workflow_id) and args.case_id:
        raise CLIError("--case-id is valid only with a validation mode")
    if workflow_id == CANONICAL_WORKFLOW:
        _initialize_user_settings(CANONICAL_WORKFLOW)
    config_result = _ensure_config_ok(workflow_id, args.pipeline, getattr(args, "cul", None))
    pipeline = str(args.pipeline or config_result["pipeline"])
    if args.run_id:
        run_id = _validate_run_id(args.run_id)
        run = _top_dir(run_id)
        if run.exists():
            raise CLIError(f"run already exists; refusing to overwrite: {run_id}")
    else:
        base_id = _generated_run_id(mode, case=case, example=args.example, case_id=args.case_id)
        run_id, run, suffix = base_id, _top_dir(base_id), 2
        while run.exists():
            run_id = f"{base_id}-{suffix}"; run = _top_dir(run_id); suffix += 1
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    code = _prepare_run_at(
        run, run_id=run_id, workflow_id=workflow_id, mode=mode, pipeline=pipeline,
        config_result=config_result, case=case, example=args.example,
        validation_case_id=args.case_id, workflow_definition=workflow_definition,
    )
    if code != 0:
        return code
    LATEST_PATH.write_text(run_id + "\n", encoding="utf-8")
    _print_run_header(run_id, run, inspect_run(run))
    return 0

def _pathify(value: Any) -> Any:
    if isinstance(value, Path): return str(value.resolve())
    if isinstance(value, dict): return {str(k): _pathify(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [_pathify(v) for v in value]
    return value

def _print_handoff(run_id: str, run: Path, stage: str, manifest: dict[str, Any]) -> int:
    print(f"RUN_ID={run_id}"); print(f"RUN_DIR={run.resolve()}"); print("STATUS=handoff"); print(f"STAGE={stage}")
    output = manifest.get("output")
    if output: print(f"OUTPUT={Path(output).resolve() if isinstance(output, Path) else output}")
    print("MANIFEST="); print(json.dumps(_pathify(manifest), indent=2, ensure_ascii=False)); return 0

def _reseat_cul(run: Path, profile: str) -> None:
    from scripts.core import corpus as corpus_core
    from scripts.core import cul as cul_core
    corpus_doc, _index, _digest = corpus_core.load_corpus(corpus_core.DEFAULT_CORPUS, corpus_core.DEFAULT_INDEX)
    cards = corpus_core.flatten(corpus_doc)
    layer, warnings = _resolve_cul(profile, corpus_doc, cards)
    config = run / "run-config"; manifest_path = config / "manifest.json"; manifest = _json_load(manifest_path)
    previous = manifest.get("cul_profile")
    if previous == layer["profile"] and manifest.get("cul_sha256") == layer["cul_sha256"]: return
    cul_core.freeze(layer, config / "cul.json")
    manifest["cul_profile"] = layer["profile"]; manifest["cul_sha256"] = layer["cul_sha256"]
    history = list(manifest.get("cul_history") or [])
    history.append({"replaced_profile": previous, "profile": layer["profile"], "cul_sha256": layer["cul_sha256"], "at": datetime.now(timezone.utc).isoformat()})
    manifest["cul_history"] = history
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for warning in warnings: print(f"WARNING={warning}")
    print(f"CUL_RESEATED={previous or 'none'} -> {layer['profile']}")

def _automatic_validation_marking(run: Path, pipeline: str, step) -> tuple[str, Any | None]:
    """Run non-blocking post-report validation marking for canonical proforma-v1 runs."""
    if _run_workflow(run) != CANONICAL_WORKFLOW or not (Path(run) / "report-final.md").is_file():
        return "not_applicable", None
    from workflows.proforma_v1 import automatic_marking
    try:
        result = automatic_marking.run(run, profile=pipeline)
    except step.Handoff as handoff:
        manifest = {
            "pass": "validation_marking",
            "phase": "validation_marking",
            "note": "The clinical report is already complete. Complete this evaluator-only marking handoff; marking failure does not invalidate the report.",
            "prompt": handoff.prompt,
            "output": handoff.output,
            "inputs": {"report": Path(run) / "report-final.md", "case": Path(run) / "case.md"},
        }
        return "handoff", {"stage": "validation_marking", "manifest": manifest}
    except Exception as exc:
        print(f"WARNING=automatic validation marking failed; clinical report remains complete: {exc}", file=sys.stderr)
        return "failed", exc
    return str(result.get("status") or "complete"), result


def cmd_run(args: argparse.Namespace) -> int:
    run_id, run = _resolve_run(args.run_id)
    pipeline = _run_pipeline(run)
    if not pipeline: raise CLIError(f"cannot determine pipeline for run: {run_id}")
    if getattr(args, "cul", None): _reseat_cul(run, args.cul)
    step, self_executor, _registry = _bind_run_config(run)
    if pipeline == "self":
        result = self_executor.advance(run)
        if result["status"] == "handoff": return _print_handoff(run_id, run, result["stage"], result["manifest"])
        if result.get("status") == "complete":
            marking_status, marking = _automatic_validation_marking(run, pipeline, step)
            if marking_status == "handoff":
                return _print_handoff(run_id, run, marking["stage"], marking["manifest"])
            if marking_status in {"complete", "failed"}: print(f"MARKING_STATUS={marking_status}")
        status = self_executor.inspect_run(run); _print_run_header(run_id, run, {**status, "workflow_definition": _run_workflow_definition(run)})
        for key, value in result.get("artifacts", {}).items(): print(f"{key}={value if value is not None else 'none'}")
        return 0
    code = int(step.main(["run", "--work-dir", str(run)]))
    if code == 0:
        marking_status, _marking = _automatic_validation_marking(run, pipeline, step)
        if marking_status in {"complete", "failed"}: print(f"MARKING_STATUS={marking_status}")
    _print_run_header(run_id, run, inspect_run(run))
    return code

def cmd_status(args: argparse.Namespace) -> int:
    run_id, run = _resolve_run(args.run_id); status = inspect_run(run)
    if args.json: print(json.dumps({"kind": "run", "run_id": run_id, "run_dir": str(run.resolve()), **status}, indent=2, ensure_ascii=False))
    else: _print_run_header(run_id, run, status)
    return 0

def _child_row(batch: run_layout.BatchLocation, child: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    case_id = str(child["case_id"]); ref = str(child["run_id"]); path = batch.path / case_id
    run_status = inspect_run(path)
    child_state = (state.get("children") or {}).get(case_id) or {}
    return {
        "kind": "batch-child", "run_id": ref, "batch_id": batch.batch_id,
        "case_id": case_id, "case_title": child.get("title") or case_id,
        "run_dir": str(path.resolve()), "batch_status": child_state.get("status", "prepared"),
        "attempt_count": int(child_state.get("attempt_count") or 0),
        "retry_eligible": bool(child_state.get("retry_eligible")),
        "failure_class": child_state.get("failure_class"),
        "blocked_reason": child_state.get("blocked_reason"), **run_status,
    }

def _aggregate_usage(child_paths: list[Path]) -> dict[str, Any] | None:
    try:
        from scripts import model_usage
    except Exception:
        return None
    summaries = []
    for path in child_paths:
        try:
            summary = model_usage.summarize(path / "logs" / "model-usage.json")
        except Exception:
            summary = None
        if summary: summaries.append(summary)
    if not summaries: return None
    calls = retry = repair = duration = tokens = 0
    cost_amount = 0.0; any_cost = False; complete_cost = True
    for s in summaries:
        calls += int(s.get("physical_calls") or 0); retry += int(s.get("retry_calls") or 0); repair += int(s.get("syntax_repair_calls") or 0); duration += int(s.get("duration_ms") or 0)
        totals = s.get("totals") or {}; tokens += int(totals.get("total_tokens") or 0)
        cost = s.get("cost") or {}; amount = cost.get("amount")
        if amount is not None:
            any_cost = True; cost_amount += float(amount); complete_cost = complete_cost and cost.get("complete") is not False
        else: complete_cost = False
    return {
        "physical_calls": calls, "retry_calls": retry, "syntax_repair_calls": repair,
        "duration_ms": duration, "totals": {"total_tokens": tokens},
        "cost": {"amount": cost_amount if any_cost else None, "complete": complete_cost if any_cost else False},
    }

def _write_if_changed(path: Path, text: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        try:
            if path.read_text(encoding="utf-8") == text:
                return path
        except OSError:
            pass
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)
    return path


def _batch_marking_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Batch validation marking",
        "",
        f"- Suite: `{payload.get('suite')}`",
        f"- Marked: {payload.get('marked', 0)}/{payload.get('total', 0)}",
        f"- Status: `{payload.get('status')}`",
        "",
        "## Per-case marking",
        "",
        "| Case | Marking | R1 | R2 | R3 | R4 | R5 |",
        "|---|---|---|---|---|---|---|",
    ]
    for case in payload.get("cases") or []:
        rubrics = case.get("rubrics") or {}
        label = str(case.get("source_case_id") or case.get("case_id") or "")
        cells = [str((rubrics.get(f"R{i}") or {}).get("category") or "—") for i in range(1, 6)]
        lines.append(
            "| " + " | ".join([label, str(case.get("marking_status") or "pending"), *cells]) + " |"
        )
    lines += ["", "## Criterion failure modes", "", "| Failure mode | Count |", "|---|---:|"]
    for mode in ("partial", "omitted", "contradicted"):
        lines.append(f"| {mode} | {int((payload.get('criterion_failure_modes') or {}).get(mode, 0))} |")
    criterion_counts = payload.get("criterion_failure_counts") or {}
    if criterion_counts:
        lines += ["", "## Failed criteria", "", "| Criterion | Total | Partial | Omitted | Contradicted |", "|---|---:|---:|---:|---:|"]
        for criterion_id in sorted(criterion_counts):
            row = criterion_counts[criterion_id] or {}
            lines.append(
                f"| {criterion_id} | {int(row.get('total') or 0)} | {int(row.get('partial') or 0)} | "
                f"{int(row.get('omitted') or 0)} | {int(row.get('contradicted') or 0)} |"
            )

    functional = payload.get("functional") or {}
    if functional:
        definitions = functional.get("function_definitions") or {}
        lines += ["", "## Dublin F1–F9 per case", ""]
        function_ids = [f"F{i}" for i in range(1, 10)]
        lines.append("| Case | " + " | ".join(function_ids) + " |")
        lines.append("|---|" + "---|" * len(function_ids))
        case_functional = functional.get("cases") or {}
        for case in payload.get("cases") or []:
            key = str(case.get("case_id") or "")
            score = case_functional.get(key) or {}
            funcs = score.get("functions") or {}
            values = [str((funcs.get(fid) or {}).get("result") or "—") for fid in function_ids]
            label = str(case.get("source_case_id") or key)
            lines.append("| " + " | ".join([label, *values]) + " |")
        lines += ["", "## Dublin F1–F9 aggregate", "", "| Function | Met | Applicable | Proportion |", "|---|---:|---:|---:|"]
        aggregate = functional.get("aggregate") or {}
        for fid in function_ids:
            row = aggregate.get(fid) or {}
            proportion = row.get("proportion")
            proportion_text = "—" if proportion is None else f"{float(proportion):.3f}"
            description = str(definitions.get(fid) or "").strip()
            label = f"{fid} — {description}" if description else fid
            lines.append(f"| {label} | {int(row.get('met') or 0)} | {int(row.get('applicable') or 0)} | {proportion_text} |")
    return "\n".join(lines).rstrip() + "\n"


def _aggregate_batch_marking(batch: run_layout.BatchLocation, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministically aggregate child marking; never invoke a batch marking model."""
    mode = str(batch.manifest.get("mode") or "")
    try:
        from validation.scripts.bundled_cases import is_validation_mode
    except Exception:
        is_validation_mode = lambda value: str(value).startswith("nel-validate")
    json_path = batch.path / "batch-marking.json"
    markdown_path = batch.path / "batch-marking.md"
    if not is_validation_mode(mode):
        json_path.unlink(missing_ok=True)
        markdown_path.unlink(missing_ok=True)
        return {"applicable": False, "status": "not_applicable", "marked": 0, "total": 0}

    from validation.scripts.package_marking import load_marking_payload

    manifest_rows = {str(item.get("case_id")): item for item in batch.manifest.get("children", [])}
    rubric_categories = {f"R{i}": {} for i in range(1, 6)}
    failure_modes = {"partial": 0, "omitted": 0, "contradicted": 0}
    criterion_failure_counts: dict[str, dict[str, int]] = {}
    cases: list[dict[str, Any]] = []
    marked = 0
    dublin_scores: dict[str, dict[str, Any]] = {}
    dublin_mode = mode == "nel-validate-dublin"

    for row in rows:
        case_id = str(row.get("case_id") or "")
        spec = manifest_rows.get(case_id) or {}
        marking = dict(row.get("marking") or {})
        item: dict[str, Any] = {
            "case_id": case_id,
            "source_case_id": spec.get("source_case_id") or marking.get("case") or case_id,
            "title": row.get("case_title") or spec.get("title") or case_id,
            "run_id": row.get("run_id"),
            "clinical_complete": bool(row.get("complete")),
            "marking_status": marking.get("status") or "pending",
        }
        child_path = batch.path / case_id
        payload = load_marking_payload(child_path) if item["marking_status"] == "complete" else None
        if payload is not None:
            marked += 1
            item["rubrics"] = payload.get("rubrics") or {}
            item["criterion_results"] = payload.get("criterion_results") or {}
            for rubric, outcome in item["rubrics"].items():
                category = str((outcome or {}).get("category") or "")
                if rubric in rubric_categories and category:
                    rubric_categories[rubric][category] = rubric_categories[rubric].get(category, 0) + 1
            for criterion_id, outcome in item["criterion_results"].items():
                if isinstance(outcome, dict) and outcome.get("met") is False:
                    failure = outcome.get("failure_mode")
                    if failure in failure_modes:
                        failure_modes[failure] += 1
                        bucket = criterion_failure_counts.setdefault(criterion_id, {"total": 0, "partial": 0, "omitted": 0, "contradicted": 0})
                        bucket["total"] += 1
                        bucket[failure] += 1
            if dublin_mode:
                try:
                    from validation.scripts.score_functional_dublin import score_case
                    marking_text = (child_path / "marking.md").read_text(encoding="utf-8")
                    dublin_scores[case_id] = score_case(str(item["source_case_id"]), marking_text)
                except Exception as exc:
                    item["functional_error"] = str(exc)
        cases.append(item)

    total = len(rows)
    aggregate_status = "complete" if total and marked == total else "partial" if marked else "pending"
    payload: dict[str, Any] = {
        "schema_version": 1,
        "suite": mode,
        "status": aggregate_status,
        "marked": marked,
        "total": total,
        "complete": bool(total and marked == total),
        "rubric_categories": rubric_categories,
        "criterion_failure_modes": failure_modes,
        "criterion_failure_counts": criterion_failure_counts,
        "cases": cases,
    }
    if dublin_mode:
        from validation.scripts.score_functional_dublin import aggregate, load_spec
        spec = load_spec()
        payload["functional"] = {
            "function_definitions": spec.functions,
            "cases": dublin_scores,
            "aggregate": aggregate(dublin_scores, spec),
        }

    rendered = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    _write_if_changed(json_path, rendered)
    _write_if_changed(markdown_path, _batch_marking_markdown(payload))
    return {
        "applicable": True,
        "status": aggregate_status,
        "marked": marked,
        "total": total,
        "complete": bool(total and marked == total),
        "artifacts": {"markdown": str(markdown_path), "json": str(json_path)},
        "criterion_failure_modes": failure_modes,
        "criterion_failure_counts": criterion_failure_counts,
        "rubric_categories": rubric_categories,
        "functional": payload.get("functional"),
    }


def _batch_elapsed_seconds(state: dict[str, Any]) -> float | None:
    started = state.get("started_at")
    if not isinstance(started, str) or not started:
        return None
    try:
        start_dt = datetime.fromisoformat(started)
        terminal = state.get("finished_at") or state.get("stopped_at") or state.get("blocked_at")
        end_dt = datetime.fromisoformat(terminal) if isinstance(terminal, str) and terminal else datetime.now(timezone.utc)
        return max(0.0, (end_dt - start_dt).total_seconds())
    except (TypeError, ValueError):
        return None

def batch_status(batch_id: str) -> dict[str, Any]:
    batch = _resolve_batch(batch_id)
    try: state = run_layout.load_batch_state(batch)
    except run_layout.LayoutError as exc: raise _layout_error(exc) from exc
    rows = [_child_row(batch, row, state) for row in batch.manifest.get("children", [])]
    counts = {name: 0 for name in ("prepared", "running", "complete", "failed", "blocked", "stopped")}
    for row in rows:
        status = str(row.get("batch_status") or "prepared")
        if row.get("complete"): status = "complete"
        if status not in counts: counts[status] = 0
        counts[status] += 1
    usage = _aggregate_usage([batch.path / str(row["case_id"]) for row in batch.manifest.get("children", [])])
    marking = _aggregate_batch_marking(batch, rows)
    stored_status = str(state.get("status") or "prepared")
    operational_status = stored_status
    if stored_status in {"complete", "marking_incomplete"} and marking.get("applicable"):
        operational_status = "complete" if marking.get("complete") else "marking_incomplete"
    return {
        "kind": "batch", "batch_id": batch.batch_id, "run_id": batch.batch_id,
        "run_dir": str(batch.path.resolve()), "workflow": batch.manifest.get("workflow"),
        "workflow_definition": batch.manifest.get("workflow_definition") or DEFAULT_WORKFLOW_DEFINITION,
        "mode": batch.manifest.get("mode"), "pipeline": batch.manifest.get("pipeline"),
        "source": batch.manifest.get("source"), "max_parallel_cases": batch.manifest.get("max_parallel_cases", 1),
        "status": operational_status, "stored_status": stored_status, "complete": operational_status == "complete",
        "label": operational_status.replace("_", " ").title(),
        "stage": "complete" if operational_status == "complete" else "validation_marking" if operational_status == "marking_incomplete" else "batch",
        "counts": counts, "children": rows, "usage": usage, "marking": marking,
        "elapsed_seconds": _batch_elapsed_seconds(state),
        "started_at": state.get("started_at"), "finished_at": state.get("finished_at"), "stopped_at": state.get("stopped_at"),
        "blocked_at": state.get("blocked_at"), "blocked_reason": state.get("blocked_reason"),
    }

def _all_entries() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for kind, path in run_layout.iter_top_level(RUNS_DIR):
        if kind == "run":
            try:
                loc = run_layout.resolve_run(RUNS_DIR, path.name); status = inspect_run(loc.path)
                rows.append({"kind": "run", "run_id": loc.run_id, "run_dir": str(loc.path.resolve()), **status})
            except Exception as exc:
                rows.append({"kind": "invalid", "run_id": path.name, "run_dir": str(path.resolve()), "label": "Invalid layout", "stage": "invalid", "complete": False, "detail": str(exc)})
        elif kind == "batch":
            try: rows.append(batch_status(path.name))
            except Exception as exc: rows.append({"kind": "invalid", "run_id": path.name, "run_dir": str(path.resolve()), "label": "Invalid batch", "stage": "invalid", "complete": False, "detail": str(exc)})
        else:
            rows.append({"kind": "unsupported", "run_id": path.name, "run_dir": str(path.resolve()), "label": "Unsupported legacy layout", "stage": "unsupported", "complete": False, "detail": f"missing {run_layout.RUN_MANIFEST}/{run_layout.BATCH_MANIFEST}"})
    return rows

def cmd_runs(args: argparse.Namespace) -> int:
    rows = _all_entries()
    if args.incomplete: rows = [row for row in rows if not row.get("complete")]
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False)); return 0
    if not rows: print("No runs found."); return 0
    groups: OrderedDict[str, list[str]] = OrderedDict()
    preferred = ["Complete", "Marking Incomplete", "Complete With Errors", "Running", "Stopped", "Prepared", "At report synthesis", "At evidence review", "At germline", "At biomarker", "At treatment", "At prognosis", "At PTBG", "At diagnosis", "Setup only", "Unsupported legacy layout", "Invalid layout", "Unrecognized"]
    for label in preferred:
        names = [str(row["run_id"]) for row in rows if row.get("label") == label]
        if names: groups[label] = names
    leftovers = [str(row["run_id"]) for row in rows if not any(str(row["run_id"]) in v for v in groups.values())]
    if leftovers: groups["Other"] = leftovers
    for label, names in groups.items():
        print(f"{label}:"); [print(f"- {name}") for name in names]; print()
    return 0

def _pipeline_parallelism(pipeline: str, config_result: dict[str, Any]) -> int:
    _step, _self_executor, registry = _configure_workflow(CANONICAL_WORKFLOW)
    plan = registry.load(pipeline)
    provider = plan.doc.get("provider") or {}
    if provider.get("type") == "self":
        raise CLIError("batch execution does not support the self pipeline; choose an unattended provider")
    base = str(provider.get("base_url") or "")
    env_name = str(provider.get("base_url_env") or "")
    if env_name and os.environ.get(env_name, "").strip(): base = os.environ[env_name].strip()
    try: host = (urlparse(base).hostname or "").lower()
    except Exception: host = ""
    execution = plan.doc.get("execution") or {}
    value = execution.get("max_parallel_cases", DEFAULT_CLOUD_PARALLEL) if isinstance(execution, dict) else DEFAULT_CLOUD_PARALLEL
    try: configured = int(value)
    except (TypeError, ValueError) as exc: raise CLIError(f"pipeline execution.max_parallel_cases must be a positive integer; got {value!r}") from exc
    if configured <= 0: raise CLIError("pipeline execution.max_parallel_cases must be greater than zero")
    return 1 if host in LOCAL_HOSTS else configured

def _pipeline_provider(pipeline: str) -> dict[str, Any]:
    _step, _self_executor, registry = _configure_workflow(CANONICAL_WORKFLOW)
    plan = registry.load(pipeline)
    provider = dict(plan.doc.get("provider") or {})
    base = str(provider.get("base_url") or "").strip()
    env_name = str(provider.get("base_url_env") or "").strip()
    if env_name and os.environ.get(env_name, "").strip():
        base = os.environ[env_name].strip()
    provider["resolved_base_url"] = base.rstrip("/")
    return provider

def _provider_preflight(pipeline: str) -> str | None:
    """Return a blocking provider/configuration reason, or ``None`` when reachable.
    Batch restart eligibility is reserved for terminal workflow failures. A provider
    outage must therefore be detected before child work starts whenever possible.
    OpenAI-compatible profiles are probed through ``/models`` with the configured
    session/environment key; an HTTP/network failure blocks the batch without
    consuming case retry eligibility.
    """
    provider = _pipeline_provider(pipeline)
    if provider.get("type") == "self":
        return "the self pipeline cannot run unattended batches"
    base = str(provider.get("resolved_base_url") or "")
    if not base:
        return f"provider profile {pipeline!r} has no base URL"
    headers = {"Accept": "application/json"}
    key_env = str(provider.get("api_key_env") or "").strip()
    key = os.environ.get(key_env, "").strip() if key_env else ""
    if provider.get("api_key_required") is True and key_env and not key:
        return f"provider profile {pipeline!r} requires {key_env}, but no key is available"
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = Request(f"{base}/models", headers=headers, method="GET")
    try:
        with urlopen(request, timeout=8) as response:
            status = int(getattr(response, "status", 200) or 200)
            if status >= 400:
                return f"provider {pipeline!r} is unavailable (HTTP {status} from {base}/models)"
    except HTTPError as exc:
        return f"provider {pipeline!r} is unavailable (HTTP {exc.code} from {base}/models)"
    except (URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", None) or exc
        return f"cannot connect to provider {pipeline!r} at {base}: {reason}"
    return None

_PROVIDER_BLOCK_PATTERNS = (
    "connection refused", "connection reset", "connection error",
    "failed to establish a new connection", "remote end closed connection",
    "network is unreachable", "temporary failure in name resolution",
    "name or service not known", "could not connect", "timed out",
    "timeout while connecting", "unauthorized", "forbidden", "invalid api key",
    "authentication failed", "rate limit", "too many requests", "service unavailable",
    "bad gateway", "gateway timeout", "no model loaded", "model is not loaded",
    "unknown model", "http 401", "http 403", "http 429", "http 500", "http 502",
    "http 503", "http 504", "http error 401", "http error 403", "http error 429",
    "http error 500", "http error 502", "http error 503", "http error 504",
)

def _tail_text(path: Path, limit: int = 65536) -> str:
    if not path.is_file():
        return ""
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            handle.seek(max(0, size - limit))
            return handle.read(limit).decode("utf-8", errors="replace")
    except OSError:
        return ""

def _provider_failure_reason(child_path: Path, pipeline: str) -> str | None:
    text = "\n".join([
        _tail_text(child_path / "logs" / "batch-run.log"),
        _tail_text(child_path / "logs" / "workflow.log"),
    ])
    lower = text.lower()
    matched = next((pattern for pattern in _PROVIDER_BLOCK_PATTERNS if pattern in lower), None)
    if not matched:
        return None
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    detail = next((line for line in reversed(lines) if matched in line.lower()), matched)
    if len(detail) > 320:
        detail = detail[-320:]
    return f"provider interruption for {pipeline}: {detail}"

def _unique_batch_path(requested: str | None, label: str) -> tuple[str, Path]:
    if requested:
        batch_id = _validate_run_id(requested); path = _top_dir(batch_id)
        if path.exists(): raise CLIError(f"run already exists; refusing to overwrite: {batch_id}")
        return batch_id, path
    base = _generated_batch_id(label); batch_id, path, suffix = base, _top_dir(base), 2
    while path.exists(): batch_id = f"{base}-{suffix}"; path = _top_dir(batch_id); suffix += 1
    return batch_id, path

def cmd_batch_setup(args: argparse.Namespace) -> int:
    workflow_id = CANONICAL_WORKFLOW; mode = args.mode
    workflow_definition, _workflow_path = _resolve_workflow_definition(getattr(args, "workflow", None))
    if mode not in _supported_modes(workflow_id): raise CLIError(f"unsupported batch mode {mode!r}")
    is_demo = mode == "nel-demo"
    is_validation = mode in _validation_modes(workflow_id)
    if mode == "ngs-report":
        if args.case is None: raise CLIError("ngs-report batch setup requires --case <cases.md>")
        if args.case_ids: raise CLIError("--case-ids is valid only with nel-demo or a validation mode")
        source_path = args.case.expanduser().resolve()
        if not source_path.is_file(): raise CLIError(f"batch case file not found: {source_path}")
        source_text = source_path.read_text(encoding="utf-8")
        try: parsed = run_layout.parse_case_markdown(source_text)
        except run_layout.LayoutError as exc: raise _layout_error(exc) from exc
        label = source_path.stem
        source_doc = {"type": "freetext", "file": source_path.name, "case_count": len(parsed)}
    elif is_demo or is_validation:
        if args.case is not None: raise CLIError("--case is valid only with --mode ngs-report")
        try: ids = run_layout.parse_case_ids(args.case_ids)
        except run_layout.LayoutError as exc: raise _layout_error(exc) from exc
        parsed = []
        label = mode.removeprefix("nel-")
        source_text = None
        source_doc = {"type": "bundled", "series": mode, "case_ids": ids, "case_count": len(ids)}
    else:
        raise CLIError("batch setup supports ngs-report free text, nel-demo, and validation series")
    _initialize_user_settings(CANONICAL_WORKFLOW)
    config_result = _ensure_config_ok(CANONICAL_WORKFLOW, args.pipeline, getattr(args, "cul", None))
    pipeline = str(args.pipeline or config_result["pipeline"])
    if pipeline == "self": raise CLIError("batch setup requires an unattended provider; the self pipeline is not supported")
    parallel = _pipeline_parallelism(pipeline, config_result)
    batch_id, batch_dir = _unique_batch_path(args.run_id, label)
    RUNS_DIR.mkdir(parents=True, exist_ok=True); batch_dir.mkdir()
    children: list[dict[str, Any]] = []
    created_at = datetime.now(timezone.utc).isoformat()
    try:
        if source_text is not None:
            (batch_dir / run_layout.BATCH_SOURCE).write_text(source_text if source_text.endswith("\n") else source_text + "\n", encoding="utf-8")
            for item in parsed:
                logical = run_layout.child_run_ref(batch_id, item.case_id); child_dir = batch_dir / item.case_id
                handle = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
                try:
                    handle.write(item.text); handle.close()
                    code = _prepare_run_at(
                        child_dir, run_id=logical, workflow_id=workflow_id, mode=mode, pipeline=pipeline,
                        config_result=config_result, case=Path(handle.name), batch_id=batch_id,
                        child_case_id=item.case_id, case_title=f"Case {item.title}",
                        workflow_definition=workflow_definition,
                    )
                finally:
                    try: os.unlink(handle.name)
                    except OSError: pass
                if code != 0: raise CLIError(f"failed to prepare {logical}")
                children.append({"case_id": item.case_id, "title": f"Case {item.title}", "run_id": logical})
        else:
            for index, source_id in enumerate(ids, start=1):
                case_id = f"{index:03d}-{_slug(source_id).lower()}"; logical = run_layout.child_run_ref(batch_id, case_id); child_dir = batch_dir / case_id
                kwargs = {"example": int(source_id)} if is_demo else {"validation_case_id": source_id}
                code = _prepare_run_at(
                    child_dir, run_id=logical, workflow_id=workflow_id, mode=mode, pipeline=pipeline,
                    config_result=config_result, batch_id=batch_id, child_case_id=case_id,
                    case_title=f"Case {source_id}", workflow_definition=workflow_definition, **kwargs,
                )
                if code != 0: raise CLIError(f"failed to prepare bundled case {source_id}")
                children.append({"case_id": case_id, "title": f"Case {source_id}", "source_case_id": source_id, "run_id": logical})
        manifest = {
            "schema_version": run_layout.SCHEMA_VERSION, "kind": "batch", "batch_id": batch_id,
            "workflow": workflow_id, "workflow_definition": workflow_definition,
            "mode": mode, "pipeline": pipeline, "created_at": created_at,
            "source": source_doc, "max_parallel_cases": parallel, "children": children,
        }
        run_layout.write_batch_manifest(batch_dir, manifest)
        batch = run_layout.resolve_batch(RUNS_DIR, batch_id)
        run_layout.write_batch_state(batch, run_layout.initial_batch_state(children, created_at=created_at))
    except Exception:
        shutil.rmtree(batch_dir, ignore_errors=True); raise
    print(f"BATCH_ID={batch_id}"); print(f"BATCH_DIR={batch_dir.resolve()}"); print("STATUS=prepared"); print(f"CASES={len(children)}"); print(f"PIPELINE={pipeline}"); print(f"WORKFLOW_DEFINITION={workflow_definition}"); print(f"MAX_PARALLEL_CASES={parallel}")
    return 0

class _BatchRunner:
    def __init__(self, batch: run_layout.BatchLocation, state: dict[str, Any]):
        self.batch = batch
        self.state = state
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.block_event = threading.Event()
        self.block_reason: str | None = None
        self.active: dict[str, subprocess.Popen] = {}
        self.previous_handlers: dict[int, Any] = {}
    @property
    def halted(self) -> bool:
        return self.stop_event.is_set() or self.block_event.is_set()

    def install_signals(self):
        def handler(_signum, _frame):
            self.stop_event.set()
            self._terminate_active()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                self.previous_handlers[sig] = signal.getsignal(sig)
                signal.signal(sig, handler)
            except (ValueError, OSError):
                pass
    def restore_signals(self):
        for sig, old in self.previous_handlers.items():
            try:
                signal.signal(sig, old)
            except (ValueError, OSError):
                pass

    def _save(self):
        run_layout.write_batch_state(self.batch, self.state)
    def _terminate_active(self, *, exclude: str | None = None):
        with self.lock:
            procs = [(case_id, proc) for case_id, proc in self.active.items() if case_id != exclude]
        for _case_id, proc in procs:
            if proc.poll() is None:
                try:
                    proc.terminate()
                except OSError:
                    pass
        for _case_id, proc in procs:
            if proc.poll() is None:
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    try:
                        proc.kill()
                    except OSError:
                        pass
    def block_provider(self, reason: str, *, source_case: str) -> None:
        with self.lock:
            if self.block_event.is_set():
                return
            self.block_reason = str(reason)
            self.block_event.set()
            self.state["blocked_reason"] = self.block_reason
            self.state["blocked_at"] = datetime.now(timezone.utc).isoformat()
            self._save()
        print(f"[batch] provider blocked: {self.block_reason}", file=sys.stderr, flush=True)
        self._terminate_active(exclude=source_case)
    def run_child(self, row: dict[str, Any]) -> tuple[str, str]:
        case_id = str(row["case_id"])
        ref = str(row["run_id"])
        child_path = self.batch.path / case_id
        if self.halted:
            return case_id, "not-started"
        with self.lock:
            child_state = self.state["children"][case_id]
            child_state["status"] = "running"
            child_state["attempt_count"] = int(child_state.get("attempt_count") or 0) + 1
            child_state["last_started_at"] = datetime.now(timezone.utc).isoformat()
            child_state["blocked_reason"] = None
            self._save()
        print(f"[batch] {row.get('title') or case_id} started (attempt {child_state['attempt_count']})", flush=True)
        log_dir = child_path / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "batch-run.log"
        argv = [sys.executable, "-u", str(ROOT / "nel.py"), "run", "--run-id", ref]
        with open(log_path, "ab") as handle:
            handle.write(("\n$ python nel.py run --run-id " + ref + "\n").encode())
            handle.flush()
            proc = subprocess.Popen(argv, cwd=str(ROOT), stdout=handle, stderr=subprocess.STDOUT, env=dict(os.environ))
            with self.lock:
                self.active[case_id] = proc
            code = proc.wait()
            with self.lock:
                self.active.pop(case_id, None)
        try:
            status = inspect_run(child_path)
        except Exception:
            status = {"complete": False, "stage": "unknown"}
        complete = code == 0 and bool(status.get("complete"))
        provider_reason = None if complete or self.stop_event.is_set() else _provider_failure_reason(child_path, str(self.batch.manifest.get("pipeline") or "provider"))
        if provider_reason and not self.block_event.is_set():
            self.block_provider(provider_reason, source_case=case_id)
        now = datetime.now(timezone.utc).isoformat()
        with self.lock:
            child_state = self.state["children"][case_id]
            child_state["last_exit_code"] = code
            child_state["last_finished_at"] = now
            if complete:
                child_state["status"] = "complete"
                child_state["last_failure_stage"] = None
                child_state["retry_eligible"] = False
                child_state["failure_class"] = None
                child_state["blocked_reason"] = None
                outcome = "complete"
            elif self.stop_event.is_set():
                child_state["status"] = "stopped"
                child_state["retry_eligible"] = False
                child_state["failure_class"] = "stopped"
                outcome = "stopped"
            elif provider_reason or self.block_event.is_set():
                child_state["status"] = "blocked"
                child_state["retry_eligible"] = False
                child_state["failure_class"] = "provider"
                child_state["blocked_reason"] = provider_reason or self.block_reason
                outcome = "blocked"
            else:
                child_state["status"] = "failed"
                child_state["last_failure_stage"] = str(status.get("stage") or "unknown")
                child_state["retry_eligible"] = True
                child_state["failure_class"] = "workflow"
                child_state["blocked_reason"] = None
                outcome = "failed"
            self._save()
        label = outcome if outcome != "failed" else f"failed at {status.get('stage') or 'unknown'}"
        print(f"[batch] {row.get('title') or case_id} {label}", flush=True)
        return case_id, outcome

def _child_needs_marking_retry(batch: run_layout.BatchLocation, row: dict[str, Any], state: dict[str, Any]) -> bool:
    case_id = str(row["case_id"])
    child_state = (state.get("children") or {}).get(case_id) or {}
    if child_state.get("status") != "complete":
        return False
    marking = _marking_state(batch.path / case_id)
    return bool(marking.get("applicable")) and marking.get("status") in {"pending", "failed", "stale"}


def _selected_batch_children(batch: run_layout.BatchLocation, state: dict[str, Any]) -> list[dict[str, Any]]:
    parent = str(state.get("status") or "prepared")
    if parent == "running":
        raise CLIError(f"batch {batch.batch_id} is already running")
    children = list(batch.manifest.get("children", []))
    child_state = state.get("children") or {}
    marking_retries = [row for row in children if _child_needs_marking_retry(batch, row, state)]
    if parent in {"complete", "marking_incomplete"}:
        return marking_retries
    if parent == "complete_with_errors":
        clinical_retries = [
            row for row in children
            if (child_state.get(str(row["case_id"])) or {}).get("status") == "failed"
            and (child_state.get(str(row["case_id"])) or {}).get("retry_eligible") is not False
        ]
        seen = {str(row["case_id"]) for row in clinical_retries}
        return clinical_retries + [row for row in marking_retries if str(row["case_id"]) not in seen]
    if parent in {"stopped", "blocked"}:
        clinical = [row for row in children if (child_state.get(str(row["case_id"])) or {}).get("status") != "complete"]
        seen = {str(row["case_id"]) for row in clinical}
        return clinical + [row for row in marking_retries if str(row["case_id"]) not in seen]
    return list(children)

def cmd_batch_run(args: argparse.Namespace) -> int:
    batch = _resolve_batch(args.run_id)
    try:
        state = run_layout.load_batch_state(batch)
    except run_layout.LayoutError as exc:
        raise _layout_error(exc) from exc
    selected = _selected_batch_children(batch, state)
    if not selected:
        doc = batch_status(batch.batch_id)
        if doc.get("status") == "complete":
            if state.get("status") != "complete":
                state["status"] = "complete"
                state["finished_at"] = state.get("finished_at") or datetime.now(timezone.utc).isoformat()
                run_layout.write_batch_state(batch, state)
            marking = doc.get("marking") or {}
            print(f"BATCH_ID={batch.batch_id}\nSTATUS=complete\nDETAIL=batch already complete")
            if marking.get("applicable"):
                print(f"MARKED={marking.get('marked', 0)}/{marking.get('total', 0)}")
                print(f"MARKING_STATUS={marking.get('status') or 'pending'}")
            return 0
        raise CLIError("batch has no retry-eligible failed/incomplete children")
    pipeline = str(batch.manifest.get("pipeline") or "")
    provider_reason = _provider_preflight(pipeline)
    if provider_reason:
        state["status"] = "blocked"
        state["blocked_at"] = datetime.now(timezone.utc).isoformat()
        state["blocked_reason"] = provider_reason
        state["finished_at"] = None
        run_layout.write_batch_state(batch, state)
        print(f"BATCH_ID={batch.batch_id}")
        print("STATUS=blocked")
        print(f"BLOCKED_REASON={provider_reason}")
        return 2
    state["status"] = "running"
    state["started_at"] = datetime.now(timezone.utc).isoformat()
    state["finished_at"] = None
    state["stopped_at"] = None
    state["blocked_at"] = None
    state["blocked_reason"] = None
    run_layout.write_batch_state(batch, state)
    workers = max(1, int(batch.manifest.get("max_parallel_cases") or 1))
    runner = _BatchRunner(batch, state)
    runner.install_signals()
    print(f"BATCH_ID={batch.batch_id}")
    print("STATUS=running")
    print(f"SELECTED_CASES={len(selected)}")
    print(f"MAX_PARALLEL_CASES={workers}", flush=True)
    try:
        pending = iter(selected)
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="nel-batch") as pool:
            futures: dict[Any, dict[str, Any]] = {}
            def submit_next() -> bool:
                if runner.halted:
                    return False
                try:
                    row = next(pending)
                except StopIteration:
                    return False
                futures[pool.submit(runner.run_child, row)] = row
                return True
            for _ in range(workers):
                if not submit_next():
                    break
            while futures:
                done, _pending_futures = wait(tuple(futures), return_when=FIRST_COMPLETED)
                for future in done:
                    row = futures.pop(future)
                    try:
                        future.result()
                    except Exception as exc:
                        case_id = str(row["case_id"])
                        with runner.lock:
                            child_state = state["children"][case_id]
                            child_state["status"] = "failed"
                            child_state["retry_eligible"] = False
                            child_state["failure_class"] = "runner"
                            child_state["last_failure_stage"] = "batch-runner"
                            runner._save()
                        print(f"[batch] worker error for {case_id}: {exc}", file=sys.stderr, flush=True)
                        runner.stop_event.set()
                        runner._terminate_active()
                while len(futures) < workers and not runner.halted and submit_next():
                    pass
        if runner.stop_event.is_set():
            for row in selected:
                case_id = str(row["case_id"])
                c = state["children"][case_id]
                if c.get("status") in {"prepared", "running"}:
                    c["status"] = "stopped"
                    c["retry_eligible"] = False
                    c["failure_class"] = "stopped"
            state["status"] = "stopped"
            state["stopped_at"] = datetime.now(timezone.utc).isoformat()
            final_code = 130
        elif runner.block_event.is_set():
            for row in selected:
                case_id = str(row["case_id"])
                c = state["children"][case_id]
                if c.get("status") == "running":
                    c["status"] = "blocked"
                    c["retry_eligible"] = False
                    c["failure_class"] = "provider"
                    c["blocked_reason"] = runner.block_reason
            state["status"] = "blocked"
            state["blocked_at"] = state.get("blocked_at") or datetime.now(timezone.utc).isoformat()
            state["blocked_reason"] = runner.block_reason or state.get("blocked_reason")
            state["finished_at"] = None
            final_code = 2
        else:
            statuses = [
                str((state.get("children") or {}).get(str(row["case_id"]), {}).get("status"))
                for row in batch.manifest.get("children", [])
            ]
            if statuses and all(value == "complete" for value in statuses):
                rows = [_child_row(batch, row, state) for row in batch.manifest.get("children", [])]
                marking = _aggregate_batch_marking(batch, rows)
                if marking.get("applicable") and not marking.get("complete"):
                    state["status"] = "marking_incomplete"
                    state["finished_at"] = None
                    final_code = 0
                else:
                    state["status"] = "complete"
                    state["finished_at"] = datetime.now(timezone.utc).isoformat()
                    final_code = 0
            elif any(value == "failed" for value in statuses):
                state["status"] = "complete_with_errors"
                state["finished_at"] = datetime.now(timezone.utc).isoformat()
                final_code = 1
            else:
                state["status"] = "stopped"
                state["finished_at"] = datetime.now(timezone.utc).isoformat()
                final_code = 1
        run_layout.write_batch_state(batch, state)
    finally:
        runner.restore_signals()
    print(f"STATUS={state['status']}")
    if state.get("blocked_reason"):
        print(f"BLOCKED_REASON={state['blocked_reason']}")
    try:
        final_doc = batch_status(batch.batch_id)
        marking = final_doc.get("marking") or {}
        if marking.get("applicable"):
            print(f"MARKED={marking.get('marked', 0)}/{marking.get('total', 0)}")
            print(f"MARKING_STATUS={marking.get('status') or 'pending'}")
    except Exception as exc:
        print(f"WARNING=batch marking aggregation failed: {exc}", file=sys.stderr)
    return final_code

def cmd_batch_status(args: argparse.Namespace) -> int:
    doc = batch_status(args.run_id)
    if args.json: print(json.dumps(doc, indent=2, ensure_ascii=False))
    else:
        counts = doc["counts"]; print(f"BATCH_ID={doc['batch_id']}"); print(f"BATCH_DIR={doc['run_dir']}"); print(f"STATUS={doc['status']}"); print(f"PIPELINE={doc.get('pipeline') or ''}"); print(f"WORKFLOW_DEFINITION={doc.get('workflow_definition') or DEFAULT_WORKFLOW_DEFINITION}"); print(f"MAX_PARALLEL_CASES={doc.get('max_parallel_cases') or 1}"); print(f"CASES={len(doc['children'])}"); print(f"COMPLETE={counts.get('complete',0)}"); print(f"FAILED={counts.get('failed',0)}"); print(f"RUNNING={counts.get('running',0)}"); print(f"PREPARED={counts.get('prepared',0)}"); print(f"STOPPED={counts.get('stopped',0)}"); print(f"BLOCKED={counts.get('blocked',0)}");
        if doc.get("blocked_reason"): print(f"BLOCKED_REASON={doc['blocked_reason']}")
        marking = doc.get("marking") or {}
        if marking.get("applicable"):
            print(f"MARKED={marking.get('marked', 0)}/{marking.get('total', 0)}")
            print(f"MARKING_STATUS={marking.get('status') or 'pending'}")
    return 0

def cmd_delete(args: argparse.Namespace) -> int:
    ref = str(args.run_id or "").strip()
    if not ref: raise CLIError("delete requires --run-id")
    try: batch_id, component = run_layout.split_run_ref(ref)
    except run_layout.LayoutError as exc: raise _layout_error(exc) from exc
    if batch_id is not None:
        batch = _resolve_batch(batch_id); state = run_layout.load_batch_state(batch)
        if state.get("status") == "running": raise CLIError(f"batch {batch_id} is running; stop it before deleting a child")
        children = list(batch.manifest.get("children", [])); target = next((row for row in children if row.get("case_id") == component), None)
        if target is None: raise CLIError(f"batch {batch_id} does not contain case {component}")
        if len(children) <= 1: raise CLIError("cannot delete the last child; delete the batch instead")
        shutil.rmtree(batch.path / component)
        batch.manifest["children"] = [row for row in children if row.get("case_id") != component]; run_layout.write_batch_manifest(batch.path, batch.manifest)
        state.get("children", {}).pop(component, None); run_layout.write_batch_state(batch.path, state)
        print(f"DELETED={ref}"); return 0
    path = _top_dir(component)
    if not path.is_dir(): raise CLIError(f"run not found: {component}")
    kind = run_layout.classify_top_level(path)
    if kind == "batch":
        batch = _resolve_batch(component); state = run_layout.load_batch_state(batch)
        if state.get("status") == "running": raise CLIError(f"batch {component} is running; stop it before deletion")
    elif kind == "run":
        run_layout.resolve_run(RUNS_DIR, component)
    elif kind in {"unsupported", "invalid"}:
        # Legacy/invalid run folders are unsupported operationally but remain
        # deliberately deletable so pre-manifest development runs can be cleaned up.
        pass
    else:
        raise CLIError(f"unrecognized run layout: {component}")
    shutil.rmtree(path)
    try:
        if LATEST_PATH.read_text(encoding="utf-8").strip() == component: LATEST_PATH.unlink()
    except OSError: pass
    print(f"DELETED={component}"); return 0

def cmd_config_check(args: argparse.Namespace) -> int:
    workflow_id = LEGACY_WORKFLOW if getattr(args, "legacy", False) else CANONICAL_WORKFLOW
    if workflow_id == CANONICAL_WORKFLOW: _initialize_user_settings(CANONICAL_WORKFLOW)
    result = _config_check(workflow_id, args.pipeline, getattr(args, "cul", None))
    if args.json: print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"STATUS={'ok' if result['ok'] else 'error'}"); print(f"WORKFLOW={result['workflow']}")
        if result.get("pipeline"): print(f"PIPELINE={result['pipeline']}")
        if result.get("corpus_sha256"): print(f"CORPUS_SHA256={result['corpus_sha256']}")
        if result.get("cul_profile"): print(f"CUL_PROFILE={result['cul_profile']}"); print(f"CUL_SHA256={result['cul_sha256']}")
        for warning in result["warnings"]: print(f"WARNING={warning}")
        for error in result["errors"]: print(f"ERROR={error}")
    return 0 if result["ok"] else 1

def cmd_pipelines(args: argparse.Namespace) -> int:
    workflow_id = LEGACY_WORKFLOW if getattr(args, "legacy", False) else CANONICAL_WORKFLOW
    if workflow_id == CANONICAL_WORKFLOW: _initialize_user_settings(CANONICAL_WORKFLOW)
    _ensure_config_ok(workflow_id, None); _step, _self_executor, registry = _configure_workflow(workflow_id)
    for name in registry.names(): print(f"{name}: {registry.descriptions()[name]}")
    return 0

def cmd_ui(args: argparse.Namespace) -> int:
    try:
        from ui import marking_server as server
    except ImportError as exc:
        raise CLIError(f"the browser interface is not installed in this checkout: {exc}") from exc
    return int(server.serve(port=args.port, open_browser=not args.no_browser))

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="create canonical settings from the shipped template if missing"); init.add_argument("--legacy", action="store_true", help="initialize workflow-local terraced-v6 settings instead"); init.set_defaults(func=cmd_init)
    setup = sub.add_parser("setup", help="create a new single-case root run; canonical proforma-v1 unless --legacy")
    setup.add_argument("--legacy", action="store_true", help="create a terraced-v6 legacy run with workflow-local settings/pipelines"); setup.add_argument("--workflow", help="proforma-v1 workflow definition name from workflows/proforma_v1/workflow/<name>.yaml (default: default)"); setup.add_argument("--mode", choices=_supported_modes(), default="ngs-report"); setup.add_argument("--case", type=Path, help="clinical case markdown for ngs-report"); setup.add_argument("--pipeline", help="pipeline name for the selected canonical/legacy workflow"); setup.add_argument("--cul", help="corpus user layer profile from config/cul/<name>.json"); setup.add_argument("--run-id", help="stable filesystem-safe run identifier"); setup.add_argument("--example", type=int, help="demo example number"); setup.add_argument("--case-id", help="validation case identifier"); setup.set_defaults(func=cmd_setup)
    run = sub.add_parser("run", help="continue one single/child run; defaults to runs/LATEST"); run.add_argument("--run-id"); run.add_argument("--cul", help="override the frozen corpus user layer for this invocation"); run.set_defaults(func=cmd_run)
    status = sub.add_parser("status", help="show artifact-derived status for one single/child run"); status.add_argument("--run-id"); status.add_argument("--json", action="store_true"); status.set_defaults(func=cmd_status)
    runs = sub.add_parser("runs", help="survey manifested single runs and batches"); runs.add_argument("--incomplete", action="store_true"); runs.add_argument("--json", action="store_true"); runs.set_defaults(func=cmd_runs)
    delete = sub.add_parser("delete", help="delete a single run, a batch, or one batch child"); delete.add_argument("--run-id", required=True); delete.set_defaults(func=cmd_delete)
    batch = sub.add_parser("batch", help="prepare, run/resume, or inspect a batch"); batch_sub = batch.add_subparsers(dest="batch_command", required=True)
    bsetup = batch_sub.add_parser("setup", help="prepare a free-text or validation batch"); bsetup.add_argument("--workflow", help="proforma-v1 workflow definition name from workflows/proforma_v1/workflow/<name>.yaml (default: default)"); bsetup.add_argument("--mode", choices=_supported_modes(), default="ngs-report"); bsetup.add_argument("--case", type=Path, help="markdown file containing '# Case <title>' sections"); bsetup.add_argument("--case-ids", help="comma-delimited validation case IDs, e.g. 1,2,5"); bsetup.add_argument("--pipeline"); bsetup.add_argument("--cul"); bsetup.add_argument("--run-id", help="stable filesystem-safe batch identifier"); bsetup.set_defaults(func=cmd_batch_setup)
    brun = batch_sub.add_parser("run", help="run/resume a batch; failed finished children resume from workflow checkpoints"); brun.add_argument("--run-id", required=True); brun.set_defaults(func=cmd_batch_run)
    bstatus = batch_sub.add_parser("status", help="show batch and child status"); bstatus.add_argument("--run-id", required=True); bstatus.add_argument("--json", action="store_true"); bstatus.set_defaults(func=cmd_batch_status)
    check = sub.add_parser("config-check", help="validate canonical configuration and corpus integrity"); check.add_argument("--legacy", action="store_true", help="validate terraced-v6 workflow-local settings/pipelines"); check.add_argument("--pipeline"); check.add_argument("--cul"); check.add_argument("--json", action="store_true"); check.set_defaults(func=cmd_config_check)
    pipelines = sub.add_parser("pipelines", help="list canonical pipeline configurations"); pipelines.add_argument("--legacy", action="store_true", help="list terraced-v6 workflow-local pipelines"); pipelines.set_defaults(func=cmd_pipelines)
    ui = sub.add_parser("ui", help="serve the local browser interface on this machine"); ui.add_argument("--port", type=int, default=8765, help="first port to try"); ui.add_argument("--no-browser", action="store_true", help="do not open a browser window"); ui.set_defaults(func=cmd_ui)
    return parser

def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try: return int(args.func(args))
    except (CLIError, run_layout.LayoutError, OSError, ValueError, KeyError) as exc:
        print(f"nel failed: {exc}", file=sys.stderr); return 1


if __name__ == "__main__":
    raise SystemExit(main())
