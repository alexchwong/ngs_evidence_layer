#!/usr/bin/env python3
"""Root product CLI for the canonical proforma-v1 NGS Evidence Layer workflow.

End users interact with this file, root configuration, and ``runs/`` only. New
runs use ``workflows/proforma_v1``. The previous terraced-v6 workflow is available
only through an explicit ``--legacy`` setup/configuration path or a frozen run manifest.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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

class CLIError(RuntimeError):
    pass


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
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    value = result.stdout.strip()
    return value or None


def _version() -> str | None:
    try:
        value = VERSION_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def _workflow_modules(workflow_id: str = CANONICAL_WORKFLOW):
    """Return executor modules for the canonical workflow or supported legacy runs."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    if workflow_id == CANONICAL_WORKFLOW:
        from workflows.proforma_v1 import pipeline_registry, self as self_executor, step
    elif workflow_id == LEGACY_WORKFLOW:
        from workflows.terraced_v6 import pipeline_registry, self as self_executor, step
    else:
        raise CLIError(f"unsupported run workflow: {workflow_id}")
    return step, self_executor, pipeline_registry


def _workflow_config_paths(workflow_id: str) -> tuple[Path, Path, Path]:
    """Return settings, settings-template and pipeline paths for one root-facing workflow."""
    if workflow_id == CANONICAL_WORKFLOW:
        return SETTINGS_PATH, SETTINGS_TEMPLATE_PATH, PIPELINES_DIR
    if workflow_id == LEGACY_WORKFLOW:
        return LEGACY_SETTINGS_PATH, LEGACY_SETTINGS_TEMPLATE_PATH, LEGACY_PIPELINES_DIR
    raise CLIError(f"unsupported run workflow: {workflow_id}")


def _configure_workflow(
    workflow_id: str = CANONICAL_WORKFLOW,
    *,
    settings_path: Path | None = None,
    pipelines_dir: Path | None = None,
):
    """Configure one supported workflow through its public executor hook."""
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
    value = str(value).strip()
    if not RUN_ID_RE.fullmatch(value):
        raise CLIError(
            "invalid run ID; use only letters, numbers, '.', '_' and '-', and start with a letter or number"
        )
    if value in {".", "..", "LATEST"}:
        raise CLIError(f"reserved run ID: {value}")
    return value


def _slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return value or "run"


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


def _run_dir(run_id: str) -> Path:
    return RUNS_DIR / _validate_run_id(run_id)


def _latest_run_id() -> str:
    try:
        value = LATEST_PATH.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise CLIError("no latest run is recorded; run 'python nel.py setup ...' first") from exc
    run_id = _validate_run_id(value)
    if not _run_dir(run_id).is_dir():
        raise CLIError(f"LATEST points to missing run: {run_id}")
    return run_id


def _resolve_run(run_id: str | None) -> tuple[str, Path]:
    rid = _validate_run_id(run_id) if run_id else _latest_run_id()
    path = _run_dir(rid)
    if not path.is_dir():
        raise CLIError(f"run not found: {rid}")
    return rid, path


def _run_pipeline(run: Path) -> str | None:
    """Read facade-owned pipeline identity, with workflow.json compatibility fallback."""
    manifest = run / "run-config" / "manifest.json"
    if manifest.is_file():
        try:
            value = _json_load(manifest).get("pipeline")
            if isinstance(value, str) and value:
                return value
        except CLIError:
            pass
    workflow = run / "workflow.json"
    if workflow.is_file():
        try:
            value = _json_load(workflow).get("model_profile")
            if isinstance(value, str) and value:
                return value
        except CLIError:
            pass
    return None


def _run_workflow(run: Path) -> str | None:
    """Resolve a run's workflow from frozen root metadata, with legacy fallback."""
    run = Path(run)
    manifest = run / "run-config" / "manifest.json"
    if manifest.is_file():
        try:
            value = _json_load(manifest).get("workflow")
            if isinstance(value, str) and value:
                return value
        except CLIError:
            pass
    workflow = run / "workflow.json"
    if workflow.is_file():
        try:
            value = _json_load(workflow).get("workflow_id")
            if isinstance(value, str) and value:
                return value
        except CLIError:
            pass
    return None


def inspect_run(run: Path) -> dict[str, Any]:
    """Delegate progress inspection to the workflow recorded for the run."""
    run = Path(run)
    pipeline = _run_pipeline(run)
    workflow_id = _run_workflow(run)
    if not pipeline or workflow_id not in SUPPORTED_RUN_WORKFLOWS:
        return {
            "label": "Unrecognized",
            "stage": "unknown",
            "next": "inspect run",
            "complete": False,
            "pipeline": pipeline,
            "mode": None,
        }
    step, self_executor, _registry = _workflow_modules(workflow_id)
    return self_executor.inspect_run(run) if pipeline == "self" else step.inspect_run(run)

def _all_runs() -> list[tuple[str, Path, dict[str, Any]]]:
    if not RUNS_DIR.is_dir():
        return []
    rows = []
    for path in sorted(RUNS_DIR.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_dir():
            continue
        rows.append((path.name, path, inspect_run(path)))
    return rows


def _resolve_cul(name: str | None, corpus_doc, cards) -> tuple[dict, list[str]]:
    """Resolve the requested profile, or the shipped default when none is named.

    A missing default is not an error: it means an installation that predates the
    corpus user layer, which keeps its historical permissive retrieval.
    """
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
            import json as _json
            raw = {
                "schema_version": cul_core.SCHEMA_VERSION,
                "profile": cul_core.DEFAULT_PROFILE,
                "description": "Compatibility layer derived from legacy blacklist.json.",
                "scope": _json.loads(legacy.read_text(encoding="utf-8")),
                "amendments": {},
            }
            return cul_core.resolve_profile(
                raw, corpus_document=corpus_doc, cards=cards, source=str(legacy)
            ), warnings
        return cul_core.empty_layer(), warnings
    layer = cul_core.load_profile(path, corpus_document=corpus_doc, cards=cards, strict=False)
    if layer.get("stale"):
        raise CLIError(
            f"CUL profile {requested!r} has stale amendment(s): "
            + ", ".join(layer["stale"])
            + "\nThese were authored against corpus cards that have since changed. "
            "Review them in the card browser, or run: "
            f"python scripts/cul.py check --cul {requested}"
        )
    return layer, warnings


def corpus_core_blacklist_path() -> str:
    from scripts.core import corpus as corpus_core
    return str(corpus_core.DEFAULT_BLACKLIST)


def _legacy_settings_warnings(settings: dict[str, Any]) -> list[str]:
    """Warn about terraced-era user keys without rewriting user-owned settings."""
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
        "config/settings.json contains legacy terraced-v6 key(s): "
        + ", ".join(found)
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
        # Pipeline discovery must not validate unrelated YAML files. A user may keep
        # additional/custom pipelines in config/pipelines; setup/config-check for an
        # explicitly selected pipeline should fail only if that selected pipeline is
        # unavailable or invalid.
        names = tuple(sorted(path.stem for path in pipelines_dir.glob("*.yaml")))
        if not names:
            raise CLIError(f"no pipeline YAML files found in {pipelines_dir}")
        if selected not in names:
            raise CLIError(f"configured pipeline {selected!r} is unavailable; choose one of: {', '.join(names)}")
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
        corpus_doc, _index, corpus_sha = corpus_core.load_corpus(corpus_core.DEFAULT_CORPUS, corpus_core.DEFAULT_INDEX)
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
        "ok": not errors,
        "workflow": workflow_id,
        "pipeline": selected,
        "pipelines": sorted(names),
        "corpus_sha256": corpus_sha,
        "cul_profile": (cul_layer or {}).get("profile"),
        "cul_sha256": (cul_layer or {}).get("cul_sha256"),
        "cul_layer": cul_layer,
        "errors": errors,
        "warnings": warnings,
    }


def _ensure_config_ok(
    workflow_id: str, pipeline: str | None, cul: str | None = None
) -> dict[str, Any]:
    result = _config_check(workflow_id, pipeline, cul)
    if not result["ok"]:
        raise CLIError("configuration check failed:\n- " + "\n- ".join(result["errors"]))
    return result


def _initialize_user_settings(workflow_id: str = CANONICAL_WORKFLOW) -> bool:
    """Create one workflow's optional working settings once, never overwrite them."""
    settings_path, settings_template, pipelines_dir = _workflow_config_paths(workflow_id)
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
    run: Path,
    *,
    run_id: str,
    workflow_id: str,
    mode: str,
    pipeline: str,
    config_result: dict[str, Any],
) -> None:
    from scripts.core import cul as cul_core
    target = run / "run-config"
    target.mkdir(parents=True, exist_ok=False)
    settings_path, settings_template, pipelines_dir = _workflow_config_paths(workflow_id)
    settings = _json_load(settings_path if settings_path.is_file() else settings_template)
    settings["pipeline"] = pipeline
    (target / "settings.json").write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
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
        "schema_version": 1,
        "run_id": run_id,
        "workflow": workflow_id,
        "mode": mode,
        "pipeline": pipeline,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "nel_version": _version(),
        "git_commit": _git_commit(),
        "corpus_sha256": config_result.get("corpus_sha256"),
        "cul_profile": cul_layer.get("profile"),
        "cul_sha256": cul_layer.get("cul_sha256"),
    }
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _bind_frozen_cul(config: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Publish the run's frozen corpus user layer to the workflow.

    The layer is frozen at setup and re-verified here, so a mid-run edit to a
    profile in ``config/cul/`` cannot change what an in-flight run retrieves.
    """
    from scripts.core import cul as cul_core

    path = config / "cul.json"
    if not path.is_file():
        os.environ.pop(cul_core.ENV_ACTIVE_LAYER, None)
        return cul_core.empty_layer()
    layer = cul_core.load_frozen(path)
    expected = manifest.get("cul_sha256")
    if expected and expected != layer.get("cul_sha256"):
        raise CLIError(
            "frozen corpus user layer does not match the digest recorded at setup; "
            "start a new run"
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


def _print_run_header(run_id: str, run: Path, status: dict[str, Any]) -> None:
    print(f"RUN_ID={run_id}")
    print(f"RUN_DIR={run.resolve()}")
    print(f"STATUS={'complete' if status['complete'] else 'incomplete'}")
    print(f"STAGE={status['stage']}")
    if status.get("next"):
        print(f"NEXT={status['next']}")
    if status.get("pipeline"):
        print(f"PIPELINE={status['pipeline']}")


def cmd_setup(args: argparse.Namespace) -> int:
    workflow_id = LEGACY_WORKFLOW if getattr(args, "legacy", False) else CANONICAL_WORKFLOW
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
        run = _run_dir(run_id)
        if run.exists():
            raise CLIError(f"run already exists; refusing to overwrite: {run_id}")
    else:
        base_id = _generated_run_id(mode, case=case, example=args.example, case_id=args.case_id)
        run_id = base_id
        run = _run_dir(run_id)
        suffix = 2
        while run.exists():
            run_id = f"{base_id}-{suffix}"
            run = _run_dir(run_id)
            suffix += 1
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    step, self_executor, _registry = _configure_workflow(workflow_id)
    argv = ["setup", "--mode", mode, "--work-dir", str(run)]
    if pipeline != "self":
        argv += ["--pipeline", pipeline]
    if case is not None:
        argv += ["--case-file", str(case)]
    if args.example is not None:
        argv += ["--example", str(args.example)]
    if args.case_id:
        argv += ["--case-id", str(args.case_id)]
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        code = int((self_executor if pipeline == "self" else step).main(argv))
    if code != 0:
        shutil.rmtree(run, ignore_errors=True)
        return code
    try:
        _snapshot_run_config(run, run_id=run_id, workflow_id=workflow_id, mode=mode, pipeline=pipeline, config_result=config_result)
    except Exception:
        shutil.rmtree(run, ignore_errors=True)
        raise
    LATEST_PATH.write_text(run_id + "\n", encoding="utf-8")
    status = inspect_run(run)
    _print_run_header(run_id, run, status)
    return 0


def _pathify(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value.resolve())
    if isinstance(value, dict):
        return {str(k): _pathify(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_pathify(v) for v in value]
    return value


def _print_handoff(run_id: str, run: Path, stage: str, manifest: dict[str, Any]) -> int:
    print(f"RUN_ID={run_id}")
    print(f"RUN_DIR={run.resolve()}")
    print("STATUS=handoff")
    print(f"STAGE={stage}")
    output = manifest.get("output")
    if output:
        print(f"OUTPUT={Path(output).resolve() if isinstance(output, Path) else output}")
    print("MANIFEST=")
    print(json.dumps(_pathify(manifest), indent=2, ensure_ascii=False))
    return 0


def _reseat_cul(run: Path, profile: str) -> None:
    """Replace a run's frozen corpus user layer, on explicit request only.

    Changing the layer mid-run changes what later stages can retrieve while
    earlier stages keep evidence drawn under the previous layer, so the swap is
    recorded in the manifest and announced rather than performed quietly.
    """
    from scripts.core import corpus as corpus_core
    from scripts.core import cul as cul_core

    corpus_doc, _index, _digest = corpus_core.load_corpus(
        corpus_core.DEFAULT_CORPUS, corpus_core.DEFAULT_INDEX
    )
    cards = corpus_core.flatten(corpus_doc)
    layer, warnings = _resolve_cul(profile, corpus_doc, cards)
    config = run / "run-config"
    manifest_path = config / "manifest.json"
    manifest = _json_load(manifest_path)
    previous = manifest.get("cul_profile")
    if previous == layer["profile"] and manifest.get("cul_sha256") == layer["cul_sha256"]:
        return
    cul_core.freeze(layer, config / "cul.json")
    manifest["cul_profile"] = layer["profile"]
    manifest["cul_sha256"] = layer["cul_sha256"]
    history = list(manifest.get("cul_history") or [])
    history.append({
        "replaced_profile": previous,
        "profile": layer["profile"],
        "cul_sha256": layer["cul_sha256"],
        "at": datetime.now(timezone.utc).isoformat(),
    })
    manifest["cul_history"] = history
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for warning in warnings:
        print(f"WARNING={warning}")
    print(f"CUL_RESEATED={previous or 'none'} -> {layer['profile']}")


def cmd_run(args: argparse.Namespace) -> int:
    run_id, run = _resolve_run(args.run_id)
    pipeline = _run_pipeline(run)
    if not pipeline:
        raise CLIError(f"cannot determine pipeline for run: {run_id}")
    if getattr(args, "cul", None):
        _reseat_cul(run, args.cul)
    step, self_executor, _registry = _bind_run_config(run)
    if pipeline == "self":
        result = self_executor.advance(run)
        if result["status"] == "handoff":
            return _print_handoff(run_id, run, result["stage"], result["manifest"])
        status = self_executor.inspect_run(run)
        _print_run_header(run_id, run, status)
        for key, value in result.get("artifacts", {}).items():
            print(f"{key}={value if value is not None else 'none'}")
        return 0

    code = int(step.main(["run", "--work-dir", str(run)]))
    _print_run_header(run_id, run, step.inspect_run(run))
    return code

def cmd_status(args: argparse.Namespace) -> int:
    run_id, run = _resolve_run(args.run_id)
    status = inspect_run(run)
    if args.json:
        print(json.dumps({"run_id": run_id, "run_dir": str(run.resolve()), **status}, indent=2, ensure_ascii=False))
    else:
        _print_run_header(run_id, run, status)
    return 0


def cmd_runs(args: argparse.Namespace) -> int:
    rows = _all_runs()
    if args.incomplete:
        rows = [row for row in rows if not row[2]["complete"]]
    if args.json:
        print(json.dumps([
            {"run_id": rid, "run_dir": str(path.resolve()), **status}
            for rid, path, status in rows
        ], indent=2, ensure_ascii=False))
        return 0
    if not rows:
        print("No runs found.")
        return 0
    groups: OrderedDict[str, list[str]] = OrderedDict()
    preferred = [
        "Complete",
        "At report synthesis",
        "At evidence review",
        "At germline",
        "At biomarker",
        "At treatment",
        "At prognosis",
        "At PTBG",
        "At diagnosis",
        "Setup only",
        "Unrecognized",
    ]
    for label in preferred:
        names = [rid for rid, _path, status in rows if status["label"] == label]
        if names:
            groups[label] = names
    for label, names in groups.items():
        print(f"{label}:")
        for name in names:
            print(f"- {name}")
        print()
    return 0


def cmd_config_check(args: argparse.Namespace) -> int:
    workflow_id = LEGACY_WORKFLOW if getattr(args, "legacy", False) else CANONICAL_WORKFLOW
    if workflow_id == CANONICAL_WORKFLOW:
        _initialize_user_settings(CANONICAL_WORKFLOW)
    result = _config_check(workflow_id, args.pipeline, getattr(args, "cul", None))
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"STATUS={'ok' if result['ok'] else 'error'}")
        print(f"WORKFLOW={result['workflow']}")
        if result.get("pipeline"):
            print(f"PIPELINE={result['pipeline']}")
        if result.get("corpus_sha256"):
            print(f"CORPUS_SHA256={result['corpus_sha256']}")
        if result.get("cul_profile"):
            print(f"CUL_PROFILE={result['cul_profile']}")
            print(f"CUL_SHA256={result['cul_sha256']}")
        for warning in result["warnings"]:
            print(f"WARNING={warning}")
        for error in result["errors"]:
            print(f"ERROR={error}")
    return 0 if result["ok"] else 1


def cmd_pipelines(args: argparse.Namespace) -> int:
    workflow_id = LEGACY_WORKFLOW if getattr(args, "legacy", False) else CANONICAL_WORKFLOW
    if workflow_id == CANONICAL_WORKFLOW:
        _initialize_user_settings(CANONICAL_WORKFLOW)
    _ensure_config_ok(workflow_id, None)
    _step, _self_executor, registry = _configure_workflow(workflow_id)
    for name in registry.names():
        print(f"{name}: {registry.descriptions()[name]}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="create canonical settings from the shipped template if missing")
    init.add_argument("--legacy", action="store_true", help="initialize workflow-local terraced-v6 settings instead")
    init.set_defaults(func=cmd_init)

    setup = sub.add_parser("setup", help="create a new root run; canonical proforma-v1 unless --legacy")
    setup.add_argument("--legacy", action="store_true", help="create a terraced-v6 legacy run with workflow-local settings/pipelines")
    setup.add_argument("--mode", choices=_supported_modes(), default="ngs-report")
    setup.add_argument("--case", type=Path, help="clinical case markdown for ngs-report")
    setup.add_argument("--pipeline", help="pipeline name for the selected canonical/legacy workflow")
    setup.add_argument("--cul", help="corpus user layer profile from config/cul/<name>.json")
    setup.add_argument("--run-id", help="stable filesystem-safe run identifier")
    setup.add_argument("--example", type=int, help="demo example number")
    setup.add_argument("--case-id", help="validation case identifier")
    setup.set_defaults(func=cmd_setup)

    run = sub.add_parser("run", help="continue one run; defaults to runs/LATEST")
    run.add_argument("--run-id")
    run.add_argument("--cul", help="override the frozen corpus user layer for this invocation")
    run.set_defaults(func=cmd_run)

    status = sub.add_parser("status", help="show artifact-derived status for one run")
    status.add_argument("--run-id")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    runs = sub.add_parser("runs", help="survey runs/ and group runs by progress")
    runs.add_argument("--incomplete", action="store_true", help="show incomplete runs only")
    runs.add_argument("--json", action="store_true")
    runs.set_defaults(func=cmd_runs)

    check = sub.add_parser("config-check", help="validate canonical configuration and corpus integrity")
    check.add_argument("--legacy", action="store_true", help="validate terraced-v6 workflow-local settings/pipelines")
    check.add_argument("--pipeline")
    check.add_argument("--cul")
    check.add_argument("--json", action="store_true")
    check.set_defaults(func=cmd_config_check)

    pipelines = sub.add_parser("pipelines", help="list canonical pipeline configurations")
    pipelines.add_argument("--legacy", action="store_true", help="list terraced-v6 workflow-local pipelines")
    pipelines.set_defaults(func=cmd_pipelines)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (CLIError, OSError, ValueError, KeyError) as exc:
        print(f"nel failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
