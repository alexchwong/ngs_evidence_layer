#!/usr/bin/env python3
"""Root product CLI for the terraced-v6 NGS Evidence Layer workflow.

End users interact with this file, root configuration, and ``runs/`` only.
``workflows/terraced_v6`` remains an implementation detail and is not modified by
this facade.
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
PANEL_SCOPE_PATH = CONFIG_DIR / "ngs-panel-scope.md"
PIPELINES_DIR = ROOT / "pipelines"
VERSION_PATH = ROOT / "release" / "VERSION"
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SUPPORTED_MODES = (
    "ngs-report",
    "nel-demo",
    "nel-validate",
    "nel-validate-function",
    "nel-validate-brief",
)
VALIDATION_MODES = {"nel-validate", "nel-validate-function", "nel-validate-brief"}


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


def _bind_v6(*, settings_path: Path = SETTINGS_PATH, pipelines_dir: Path = PIPELINES_DIR):
    """Bind public/snapshotted config to unchanged terraced-v6 modules."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from workflows.terraced_v6 import pipeline_registry, step

    step.SETTINGS_PATH = Path(settings_path).resolve()
    pipeline_registry.ROOT = Path(pipelines_dir).resolve()
    return step, pipeline_registry


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


def _artifact(run: Path, group: str, name: str) -> Path | None:
    parent = run / "intermediates"
    if not parent.is_dir():
        return None
    suffix = "_" + re.sub(r"[^a-z0-9]+", "_", group.lower()).strip("_")
    for directory in sorted(parent.iterdir()):
        if directory.is_dir() and directory.name.endswith(suffix):
            candidate = directory / name
            if candidate.is_file():
                return candidate
    return None


def _has(run: Path, group: str, name: str) -> bool:
    return _artifact(run, group, name) is not None


def _run_pipeline(run: Path) -> str | None:
    manifest = run / "run-config" / "manifest.json"
    if manifest.is_file():
        try:
            value = _json_load(manifest).get("pipeline")
            if isinstance(value, str) and value:
                return value
        except CLIError:
            pass
    state = _artifact(run, "run_state", "terraced-v6-run.json")
    if state:
        try:
            value = _json_load(state).get("pipeline")
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


def _run_mode(run: Path) -> str | None:
    manifest = run / "run-config" / "manifest.json"
    if manifest.is_file():
        try:
            value = _json_load(manifest).get("mode")
            if isinstance(value, str):
                return value
        except CLIError:
            pass
    state = run / "workflow.json"
    if state.is_file():
        try:
            value = _json_load(state).get("mode")
            if isinstance(value, str):
                return value
        except CLIError:
            pass
    return None


def inspect_run(run: Path) -> dict[str, Any]:
    """Infer progress from v6 artifacts. No mutable status ledger is consulted."""
    run = Path(run)
    pipeline = _run_pipeline(run)
    if (run / "report-final.md").is_file():
        label, stage, nxt, complete = "Complete", "complete", None, True
    elif _has(run, "report_write", "report-write.yaml") or _has(run, "report_blocks", "report-blocks.yaml") or _has(run, "evidence_enriched", "reportable-elements.yaml"):
        label, stage, nxt, complete = "At report synthesis", "report_synthesis", "complete report", False
    elif any(
        _has(run, group, name)
        for group, name in (
            ("evidence_matches", "self-resolution.yaml"),
            ("evidence_audits", "self-audit.yaml"),
            ("self_evidence", "state.yaml"),
            ("evidence_adjudication", "adjudication.yaml"),
        )
    ):
        label, stage, nxt, complete = "At evidence review", "evidence_review", "continue evidence review", False
    elif _has(run, "germline_state", "proforma.yaml"):
        label, stage, nxt, complete = "At evidence review", "evidence_review", "resolve evidence", False
    elif pipeline == "self" and _has(run, "diagnosis", "diagnosis-final.yaml"):
        label, stage, nxt, complete = "At PTBG", "ptbg", "complete PTBG", False
    elif pipeline == "self" and any(
        _has(run, f"{domain}_state", "model-classification.yaml")
        for domain in ("prognosis", "treatment", "biomarker", "germline")
    ):
        label, stage, nxt, complete = "At PTBG", "ptbg", "complete PTBG", False
    elif _has(run, "biomarker_state", "proforma.yaml"):
        label, stage, nxt, complete = "At germline", "germline", "complete germline", False
    elif _has(run, "treatment_state", "proforma.yaml"):
        label, stage, nxt, complete = "At biomarker", "biomarker", "complete biomarker", False
    elif _has(run, "prognosis_state", "proforma.yaml"):
        label, stage, nxt, complete = "At treatment", "treatment", "complete treatment", False
    elif _has(run, "diagnosis", "diagnosis-final.yaml"):
        label, stage, nxt, complete = "At prognosis", "prognosis", "complete prognosis", False
    elif any(
        _has(run, group, name)
        for group, name in (
            ("diagnosis_who5_pass1", "who5.yaml"),
            ("diagnosis_icc", "icc.yaml"),
            ("diagnosis_who5_pass2", "who5.yaml"),
            ("structured_case", "case.json"),
        )
    ):
        label, stage, nxt, complete = "At diagnosis", "diagnosis", "complete diagnosis", False
    elif (run / "workflow.json").is_file() and (run / "case.md").is_file():
        label, stage, nxt, complete = "Setup only", "setup", "structure case", False
    else:
        label, stage, nxt, complete = "Unrecognized", "unknown", "inspect run", False
    return {
        "label": label,
        "stage": stage,
        "next": nxt,
        "complete": complete,
        "pipeline": pipeline,
        "mode": _run_mode(run),
    }


def _all_runs() -> list[tuple[str, Path, dict[str, Any]]]:
    if not RUNS_DIR.is_dir():
        return []
    rows = []
    for path in sorted(RUNS_DIR.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_dir():
            continue
        rows.append((path.name, path, inspect_run(path)))
    return rows


def _config_check(pipeline: str | None = None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    selected = pipeline
    plans: dict[str, Any] = {}

    try:
        if not SETTINGS_PATH.is_file():
            raise CLIError(f"settings file is missing: {SETTINGS_PATH}")
        step, registry = _bind_v6()
        settings = step.load_settings()
        selected = selected or str(settings.get("pipeline") or "self")
        names = registry.names()
        if not names:
            raise CLIError(f"no pipeline YAML files found in {PIPELINES_DIR}")
        for name in names:
            plans[name] = registry.load(name)
        if selected not in plans:
            raise CLIError(f"configured pipeline {selected!r} is unavailable; choose one of: {', '.join(names)}")
        plan = plans[selected]
        provider = plan.doc.get("provider") or {}
        env_name = str(provider.get("api_key_env") or "")
        if provider.get("api_key_required") is True and env_name and not os.environ.get(env_name, "").strip():
            errors.append(f"pipeline {selected!r} requires environment variable {env_name}")
    except Exception as exc:
        errors.append(str(exc))

    if not PANEL_SCOPE_PATH.is_file() or not PANEL_SCOPE_PATH.read_text(encoding="utf-8").strip():
        errors.append(f"NGS panel scope is missing or empty: {PANEL_SCOPE_PATH}")

    corpus_sha = None
    try:
        from scripts.core import corpus as corpus_core
        corpus_doc, _index, corpus_sha = corpus_core.load_corpus(corpus_core.DEFAULT_CORPUS, corpus_core.DEFAULT_INDEX)
        cards = corpus_core.flatten(corpus_doc)
        corpus_core.blacklist_cards(cards, corpus_core.DEFAULT_BLACKLIST)
    except Exception as exc:
        errors.append(f"corpus check failed: {exc}")

    workflow_path = ROOT / "workflows" / "terraced_v6" / "workflow.json"
    if not workflow_path.is_file():
        errors.append(f"terraced-v6 implementation is missing: {workflow_path}")

    try:
        from scripts.workflow_registry import load_registry
        workflow_registry = load_registry()
        if workflow_registry.get("default_workflow") != "terraced-v6":
            warnings.append("workflow registry default is not terraced-v6")
    except Exception as exc:
        errors.append(f"workflow registry check failed: {exc}")

    return {
        "ok": not errors,
        "pipeline": selected,
        "pipelines": sorted(plans),
        "corpus_sha256": corpus_sha,
        "errors": errors,
        "warnings": warnings,
    }


def _ensure_config_ok(pipeline: str | None) -> dict[str, Any]:
    result = _config_check(pipeline)
    if not result["ok"]:
        raise CLIError("configuration check failed:\n- " + "\n- ".join(result["errors"]))
    return result


def _snapshot_run_config(run: Path, *, run_id: str, mode: str, pipeline: str, config_result: dict[str, Any]) -> None:
    target = run / "run-config"
    target.mkdir(parents=True, exist_ok=False)
    settings = _json_load(SETTINGS_PATH)
    settings["pipeline"] = pipeline
    (target / "settings.json").write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    pipeline_target = target / "pipelines"
    pipeline_target.mkdir()
    source_pipeline = PIPELINES_DIR / f"{pipeline}.yaml"
    if not source_pipeline.is_file():
        raise CLIError(f"selected pipeline file is missing: {source_pipeline}")
    (pipeline_target / source_pipeline.name).write_bytes(source_pipeline.read_bytes())
    (target / "ngs-panel-scope.md").write_bytes(PANEL_SCOPE_PATH.read_bytes())
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "workflow": "terraced-v6",
        "mode": mode,
        "pipeline": pipeline,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "nel_version": _version(),
        "git_commit": _git_commit(),
        "corpus_sha256": config_result.get("corpus_sha256"),
    }
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _bind_run_config(run: Path):
    config = run / "run-config"
    settings = config / "settings.json"
    pipelines = config / "pipelines"
    manifest_path = config / "manifest.json"
    if not settings.is_file() or not pipelines.is_dir() or not manifest_path.is_file():
        raise CLIError(f"run configuration snapshot is missing: {config}")

    manifest = _json_load(manifest_path)
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
    return _bind_v6(settings_path=settings, pipelines_dir=pipelines)


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
    mode = args.mode
    case = args.case.expanduser().resolve() if args.case else None
    if mode == "ngs-report" and case is None:
        raise CLIError("ngs-report setup requires --case <case.md>")
    if mode == "ngs-report" and (not case.is_file() or not case.read_text(encoding="utf-8").strip()):
        raise CLIError(f"case file is missing or empty: {case}")
    if mode == "nel-demo" and args.example is None:
        raise CLIError("nel-demo setup requires --example <N>")
    if mode != "nel-demo" and args.example is not None:
        raise CLIError("--example is valid only with --mode nel-demo")
    if mode in VALIDATION_MODES and not args.case_id:
        raise CLIError(f"{mode} setup requires --case-id <ID>")
    if mode not in VALIDATION_MODES and args.case_id:
        raise CLIError("--case-id is valid only with a validation mode")

    config_result = _ensure_config_ok(args.pipeline)
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

    step, _registry = _bind_v6()
    argv = ["setup", "--mode", mode, "--work-dir", str(run), "--pipeline", pipeline]
    if case is not None:
        argv += ["--case-file", str(case)]
    if args.example is not None:
        argv += ["--example", str(args.example)]
    if args.case_id:
        argv += ["--case-id", str(args.case_id)]
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        code = int(step.main(argv))
    if code != 0:
        shutil.rmtree(run, ignore_errors=True)
        return code
    try:
        _snapshot_run_config(run, run_id=run_id, mode=mode, pipeline=pipeline, config_result=config_result)
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


def _self_run(run_id: str, run: Path) -> int:
    step, _registry = _bind_run_config(run)
    from workflows.terraced_v6 import layout, self_runtime as sr

    step._require_work(run)
    layout.ensure_dirs(run)
    if (run / "report-final.md").is_file():
        _print_run_header(run_id, run, inspect_run(run))
        return 0

    if not _has(run, "structured_case", "case.json"):
        manifest = {
            "pass": "who1",
            "phase": "structure_case",
            "note": "Complete the structure subtask, write the required output, then run nel.py run again. WHO1 remains part of the same current-session reasoning sequence.",
            "contract": sr.contract_path("structure_case"),
            "inputs": {
                "case": layout.input(run, "case.md"),
                "allowed_bootstrap_cmcs": layout.setup(run, "case-major-categories.json"),
            },
            "output": sr.case_path(run),
        }
        return _print_handoff(run_id, run, "case_structure", manifest)

    if not _has(run, "diagnosis_who5_pass1", "who5.yaml"):
        return _print_handoff(run_id, run, "diagnosis", sr.prepare_who(run, pass_number=1))
    if not _has(run, "diagnosis_icc", "icc.yaml"):
        sr.accept_who(run, pass_number=1)
        return _print_handoff(run_id, run, "diagnosis", sr.prepare_icc(run))
    if not _has(run, "diagnosis_who5_pass2", "who5.yaml"):
        sr.accept_icc(run)
        return _print_handoff(run_id, run, "diagnosis", sr.prepare_who(run, pass_number=2))

    ptbg_outputs = [
        _has(run, f"{domain}_state", "model-classification.yaml")
        for domain in ("prognosis", "treatment", "biomarker", "germline")
    ]
    if not all(ptbg_outputs):
        sr.accept_who(run, pass_number=2)
        return _print_handoff(run_id, run, "ptbg", sr.prepare_ptbg(run))

    if not _has(run, "evidence_matches", "self-resolution.yaml"):
        sr.accept_ptbg(run)
        return _print_handoff(run_id, run, "evidence_resolution", sr.prepare_evidence_resolution(run))
    if not _has(run, "evidence_audits", "self-audit.yaml"):
        return _print_handoff(run_id, run, "evidence_audit", sr.prepare_evidence_audit(run))

    enriched = _has(run, "evidence_enriched", "reportable-elements.yaml")
    if not enriched:
        adjudication = sr.prepare_evidence_adjudication(run)
        if adjudication.get("required"):
            if not _has(run, "evidence_adjudication", "adjudication.yaml"):
                return _print_handoff(run_id, run, "evidence_adjudication", adjudication)
        sr.finalize_evidence(run)

    if not _has(run, "report_write", "report-write.yaml"):
        return _print_handoff(run_id, run, "report_synthesis", sr.prepare_report(run))

    sr.finalize_report(run)
    sr.package_debug_bundle(run)
    artifacts = sr.final_artifacts(run)
    _print_run_header(run_id, run, inspect_run(run))
    for key, value in artifacts.items():
        print(f"{key}={value if value is not None else 'none'}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    run_id, run = _resolve_run(args.run_id)
    pipeline = _run_pipeline(run)
    if not pipeline:
        raise CLIError(f"cannot determine pipeline for run: {run_id}")
    if pipeline == "self":
        return _self_run(run_id, run)
    step, _registry = _bind_run_config(run)
    code = int(step.main(["run", "--work-dir", str(run)]))
    status = inspect_run(run)
    _print_run_header(run_id, run, status)
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
    result = _config_check(args.pipeline)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"STATUS={'ok' if result['ok'] else 'error'}")
        if result.get("pipeline"):
            print(f"PIPELINE={result['pipeline']}")
        if result.get("corpus_sha256"):
            print(f"CORPUS_SHA256={result['corpus_sha256']}")
        for warning in result["warnings"]:
            print(f"WARNING={warning}")
        for error in result["errors"]:
            print(f"ERROR={error}")
    return 0 if result["ok"] else 1


def cmd_pipelines(args: argparse.Namespace) -> int:
    _ensure_config_ok(None)
    _step, registry = _bind_v6()
    for name in registry.names():
        print(f"{name}: {registry.descriptions()[name]}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    setup = sub.add_parser("setup", help="create a new root run bound to terraced-v6")
    setup.add_argument("--mode", choices=SUPPORTED_MODES, default="ngs-report")
    setup.add_argument("--case", type=Path, help="clinical case markdown for ngs-report")
    setup.add_argument("--pipeline", help="pipeline ID from root pipelines/")
    setup.add_argument("--run-id", help="stable filesystem-safe run identifier")
    setup.add_argument("--example", type=int, help="demo example number")
    setup.add_argument("--case-id", help="validation case identifier")
    setup.set_defaults(func=cmd_setup)

    run = sub.add_parser("run", help="continue one run; defaults to runs/LATEST")
    run.add_argument("--run-id")
    run.set_defaults(func=cmd_run)

    status = sub.add_parser("status", help="show artifact-derived status for one run")
    status.add_argument("--run-id")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    runs = sub.add_parser("runs", help="survey runs/ and group runs by progress")
    runs.add_argument("--incomplete", action="store_true", help="show incomplete runs only")
    runs.add_argument("--json", action="store_true")
    runs.set_defaults(func=cmd_runs)

    check = sub.add_parser("config-check", help="validate public configuration and corpus integrity")
    check.add_argument("--pipeline")
    check.add_argument("--json", action="store_true")
    check.set_defaults(func=cmd_config_check)

    pipelines = sub.add_parser("pipelines", help="list public pipeline configurations")
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
