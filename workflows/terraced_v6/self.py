#!/usr/bin/env python3
"""Terraced-v6 native self executor.

The current/session model performs the model reasoning directly. This module is
also the single source of truth for native-self progression: callers may invoke
``advance()`` (or the ``run`` CLI command) to obtain the next bounded handoff.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.setup_workflow import setup_workflow
from scripts.workflow_registry import write_workflow_state
from workflows.terraced_v6 import layout
from workflows.terraced_v6 import self_runtime as sr
from workflows.terraced_v6 import step as staged

EXIT_OK = 0
EXIT_FAILURE = 1


def configure_runtime(*, settings_path=None, pipelines_dir=None):
    """Bind public or frozen per-run configuration through the staged core."""
    return staged.configure_runtime(settings_path=settings_path, pipelines_dir=pipelines_dir)


def _print_manifest(data):
    def convert(value):
        if isinstance(value, Path):
            return str(value.resolve())
        if isinstance(value, dict):
            return {k: convert(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [convert(v) for v in value]
        return value
    print(json.dumps(convert(data), indent=2, ensure_ascii=False))


def _structure_manifest(work: Path) -> dict:
    work = Path(work).resolve()
    return {
        "pass": "who1",
        "phase": "structure_case",
        "note": "Complete this structure subtask and WHO1 in one continuous self reasoning pass; do not treat this deterministic interleave as another model pass.",
        "contract": sr.contract_path("structure_case"),
        "inputs": {
            "case": layout.input(work, "case.md"),
            "allowed_bootstrap_cmcs": layout.setup(work, "case-major-categories.json"),
        },
        "output": staged.artifact_path(work, "structured_case", "case.json", create=True),
    }


def cmd_setup(args):
    # Native-self owns the established work-location policy independently of
    # staged execution: default -> system temp; --project -> <repo-root>/temp;
    # explicit --work-dir -> that directory.
    plan = staged.pipeline_registry.load("self")
    work, demo_case, demo_expected = setup_workflow(
        workflow=staged.WORKFLOW_ID,
        mode=args.mode,
        work_dir=args.work_dir,
        project=bool(args.project),
        example=args.example,
        case_id=args.case_id,
    )
    write_workflow_state(work, staged.WORKFLOW_ID, args.mode, model_profile=plan.pipeline_id)

    case_path = layout.input(work, "case.md", existing=False)
    if args.case_file:
        shutil.copyfile(args.case_file.expanduser().resolve(), case_path)
    elif args.mode == "nel-demo" and demo_case:
        shutil.copyfile(demo_case, case_path)
    if not case_path.is_file() or not staged._read(case_path).strip():
        raise staged.StepFailure(f"case.md missing or empty: {case_path}")
    if demo_expected:
        shutil.copyfile(demo_expected, staged.artifact_path(work, "setup", "demo-expected.md", create=True))

    staged._save_run_state(work, {
        "schema_version": staged.RUN_STATE_SCHEMA_VERSION,
        "workflow_id": staged.WORKFLOW_ID,
        "mode": args.mode,
        "validation_case": args.case_id,
        "pipeline": plan.pipeline_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    with staged._cli_logging(work):
        print(work)
        print(f"PIPELINE={plan.pipeline_id}")
    return EXIT_OK


def inspect_run(work: Path) -> dict:
    """Return canonical native-self progress without exposing internals to callers."""
    work = Path(work).resolve()
    try:
        meta = staged.run_metadata(work)
    except Exception:
        meta = {"pipeline": "self", "mode": None}

    if (work / "report-final.md").is_file():
        label, stage, nxt, complete = "Complete", "complete", None, True
    elif (
        staged.has_artifact(work, "report_write", "report-write.yaml")
        or staged.has_artifact(work, "report_blocks", "report-blocks.yaml")
        or staged.has_artifact(work, "evidence_enriched", "reportable-elements.yaml")
    ):
        label, stage, nxt, complete = "At report synthesis", "report_synthesis", "complete report", False
    elif any(
        staged.has_artifact(work, group, name)
        for group, name in (
            ("evidence_matches", "self-resolution.yaml"),
            ("evidence_audits", "self-audit.yaml"),
            ("self_evidence", "state.yaml"),
            ("evidence_adjudication", "adjudication.yaml"),
        )
    ):
        label, stage, nxt, complete = "At evidence review", "evidence_review", "continue evidence review", False
    elif (
        staged.has_artifact(work, "diagnosis_who5_pass_2", "who5.yaml")
        or staged.has_artifact(work, "diagnosis", "diagnosis-final.yaml")
        or any(
            staged.has_artifact(work, f"{domain}_state", "model-classification.yaml")
            for domain in ("prognosis", "treatment", "biomarker", "germline")
        )
    ):
        label, stage, nxt, complete = "At PTBG", "ptbg", "complete PTBG", False
    elif staged.has_artifact(work, "structured_case", "case.json"):
        label, stage, nxt, complete = "At diagnosis", "diagnosis", "complete diagnosis", False
    elif (work / "workflow.json").is_file() and (work / "case.md").is_file():
        label, stage, nxt, complete = "Setup only", "setup", "structure case", False
    else:
        label, stage, nxt, complete = "Unrecognized", "unknown", "inspect run", False
    return {"label": label, "stage": stage, "next": nxt, "complete": complete, **meta}


def advance(work: Path) -> dict:
    """Advance deterministic native-self work and return the next model handoff.

    This is the authoritative self state machine. It validates each completed
    model output immediately before preparing the next bounded pass.
    """
    work = Path(work).resolve()
    staged._require_work(work)
    layout.ensure_dirs(work)

    if (work / "report-final.md").is_file():
        if not (work / sr.DEBUG_ZIP_NAME).is_file():
            sr.package_debug_bundle(work)
        return {"status": "complete", "stage": "complete", "artifacts": sr.final_artifacts(work)}

    if not staged.has_artifact(work, "structured_case", "case.json"):
        return {"status": "handoff", "stage": "case_structure", "manifest": _structure_manifest(work)}

    if not staged.has_artifact(work, "diagnosis_who5_pass_1", "who5.yaml"):
        return {"status": "handoff", "stage": "diagnosis", "manifest": sr.prepare_who(work, pass_number=1)}
    if not staged.has_artifact(work, "diagnosis_icc", "icc.yaml"):
        sr.accept_who(work, pass_number=1)
        return {"status": "handoff", "stage": "diagnosis", "manifest": sr.prepare_icc(work)}
    if not staged.has_artifact(work, "diagnosis_who5_pass_2", "who5.yaml"):
        sr.accept_icc(work)
        return {"status": "handoff", "stage": "diagnosis", "manifest": sr.prepare_who(work, pass_number=2)}

    ptbg_outputs = [
        staged.has_artifact(work, f"{domain}_state", "model-classification.yaml")
        for domain in ("prognosis", "treatment", "biomarker", "germline")
    ]
    if not all(ptbg_outputs):
        sr.accept_who(work, pass_number=2)
        return {"status": "handoff", "stage": "ptbg", "manifest": sr.prepare_ptbg(work)}

    if not staged.has_artifact(work, "evidence_matches", "self-resolution.yaml"):
        sr.accept_ptbg(work)
        return {"status": "handoff", "stage": "evidence_resolution", "manifest": sr.prepare_evidence_resolution(work)}
    if not staged.has_artifact(work, "evidence_audits", "self-audit.yaml"):
        return {"status": "handoff", "stage": "evidence_audit", "manifest": sr.prepare_evidence_audit(work)}

    if not staged.has_artifact(work, "evidence_enriched", "reportable-elements.yaml"):
        adjudication = sr.prepare_evidence_adjudication(work)
        if adjudication.get("required") and not staged.has_artifact(work, "evidence_adjudication", "adjudication.yaml"):
            return {"status": "handoff", "stage": "evidence_adjudication", "manifest": adjudication}
        sr.finalize_evidence(work)

    if not staged.has_artifact(work, "report_write", "report-write.yaml"):
        return {"status": "handoff", "stage": "report_synthesis", "manifest": sr.prepare_report(work)}

    sr.finalize_report(work)
    sr.package_debug_bundle(work)
    return {"status": "complete", "stage": "complete", "artifacts": sr.final_artifacts(work)}


def cmd_run(args):
    result = advance(Path(args.work_dir).resolve())
    print(f"STATUS={result['status']}")
    print(f"STAGE={result['stage']}")
    if result["status"] == "handoff":
        _print_manifest(result["manifest"])
    else:
        for key, value in result["artifacts"].items():
            print(f"{key}={value if value is not None else 'none'}")
    return EXIT_OK


def cmd_structure(args):
    work = Path(args.work_dir).resolve()
    staged._require_work(work)
    layout.ensure_dirs(work)
    _print_manifest(_structure_manifest(work))
    return EXIT_OK


def cmd_who1(args):
    _print_manifest(sr.prepare_who(Path(args.work_dir).resolve(), pass_number=1))
    return EXIT_OK


def cmd_icc(args):
    sr.accept_who(Path(args.work_dir).resolve(), pass_number=1)
    _print_manifest(sr.prepare_icc(Path(args.work_dir).resolve()))
    return EXIT_OK


def cmd_who2(args):
    sr.accept_icc(Path(args.work_dir).resolve())
    _print_manifest(sr.prepare_who(Path(args.work_dir).resolve(), pass_number=2))
    return EXIT_OK


def cmd_ptbg(args):
    sr.accept_who(Path(args.work_dir).resolve(), pass_number=2)
    _print_manifest(sr.prepare_ptbg(Path(args.work_dir).resolve()))
    return EXIT_OK


def cmd_evidence_resolution(args):
    sr.accept_ptbg(Path(args.work_dir).resolve())
    _print_manifest(sr.prepare_evidence_resolution(Path(args.work_dir).resolve()))
    return EXIT_OK


def cmd_evidence_audit(args):
    _print_manifest(sr.prepare_evidence_audit(Path(args.work_dir).resolve()))
    return EXIT_OK


def cmd_evidence_adjudication(args):
    _print_manifest(sr.prepare_evidence_adjudication(Path(args.work_dir).resolve()))
    return EXIT_OK


def cmd_finalize_evidence(args):
    work = Path(args.work_dir).resolve()
    elements = sr.finalize_evidence(work)
    print(f"SUPPORTED_ELEMENTS={len(elements)}")
    dissent = work / "dissent.md"
    print(f"DISSENT={dissent}" if dissent.is_file() else "DISSENT=none")
    return EXIT_OK


def cmd_report(args):
    _print_manifest(sr.prepare_report(Path(args.work_dir).resolve()))
    return EXIT_OK


def cmd_finalize_report(args):
    work = Path(args.work_dir).resolve()
    sr.finalize_report(work)
    sr.package_debug_bundle(work)
    for key, value in sr.final_artifacts(work).items():
        print(f"{key}={value if value is not None else 'none'}")
    return EXIT_OK


def build_parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("setup")
    s.add_argument("--mode", required=True, choices=staged.supported_modes())
    s.add_argument("--case-file", type=Path)
    s.add_argument("--example", type=int)
    s.add_argument("--case-id")
    sw = s.add_mutually_exclusive_group()
    sw.add_argument("--work-dir", type=Path)
    sw.add_argument("--project", action="store_true")
    for name in ("run", "structure", "who1", "icc", "who2", "ptbg", "evidence-resolution", "evidence-audit", "evidence-adjudication", "finalize-evidence", "report", "finalize-report"):
        q = sub.add_parser(name)
        q.add_argument("--work-dir", type=Path, required=True)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        fn = globals()["cmd_" + args.command.replace("-", "_")]
        return fn(args)
    except Exception as exc:
        print(f"terraced-v6 self failed: {exc}", file=sys.stderr)
        return EXIT_FAILURE


if __name__ == "__main__":
    raise SystemExit(main())
