#!/usr/bin/env python3
"""Proforma-v1 native self executor.

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
from workflows.proforma_v1 import layout
from workflows.proforma_v1 import self_runtime as sr
from workflows.proforma_v1 import step as staged
from workflows.proforma_v1.engine.context import WorkflowContext
from workflows.proforma_v1.engine.workflow_compiler import compile_workflow
from workflows.proforma_v1.engine.workflow_runner import WorkflowRunner
from workflows.proforma_v1.executors.self_executor import SelfExecutor
from workflows.proforma_v1.trace import TraceRecorder

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
    compile_workflow()
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


def _self_step_complete(step_id: str, context: WorkflowContext) -> bool:
    work = context.work
    checks = {
        'structure': staged.has_artifact(work, 'structured_case', 'case.json'),
        'corpus': staged.has_artifact(work, 'card_identity', 'manifest.json'),
        'diagnosis.who1': staged.has_artifact(work, 'diagnosis_who5_pass_1', 'who5.yaml'),
        'diagnosis.icc': staged.has_artifact(work, 'diagnosis_icc', 'icc.yaml'),
        'diagnosis.who2': staged.has_artifact(work, 'diagnosis_who5_pass_2', 'who5.yaml'),
        'diagnosis.other': staged.has_artifact(work, 'diagnosis', 'diagnosis-final.yaml'),
        'diagnosis.finalize': staged.has_artifact(work, 'diagnosis', 'diagnosis-final.yaml'),
        'prognosis': staged.has_artifact(work, 'prognosis_state', 'model-classification.yaml'),
        'treatment': staged.has_artifact(work, 'treatment_state', 'model-classification.yaml'),
        'biomarker': staged.has_artifact(work, 'biomarker_state', 'model-classification.yaml'),
        'germline': staged.has_artifact(work, 'germline_state', 'model-classification.yaml'),
        'evidence.assignment': staged.has_artifact(work, 'evidence_matches', 'self-resolution.yaml'),
        'evidence.audit': staged.has_artifact(work, 'evidence_audits', 'self-audit.yaml'),
        'evidence.adjudication': staged.has_artifact(work, 'evidence_enriched', 'reportable-elements.yaml') or staged.has_artifact(work, 'evidence_adjudication', 'adjudication.yaml'),
        'evidence.finalize': staged.has_artifact(work, 'evidence_enriched', 'reportable-elements.yaml'),
        'report.blocks': staged.has_artifact(work, 'report_blocks', 'report-blocks.yaml'),
        'report': (work / 'report-final.md').is_file(),
    }
    return bool(checks.get(step_id, False))


def _handoff(stage: str, manifest: dict) -> dict:
    return {'status': 'handoff', 'handoff': {'stage': stage, 'manifest': manifest}}


def _self_handlers():
    def structure(step, ctx):
        return _handoff('case_structure', _structure_manifest(ctx.work))

    def corpus(step, ctx):
        sr.accept_structured_case(ctx.work)
        staged.stage_corpus(ctx.work)
        return {'status': 'complete'}

    def who1(step, ctx):
        return _handoff('diagnosis', sr.prepare_who(ctx.work, pass_number=1))

    def icc(step, ctx):
        sr.accept_who(ctx.work, pass_number=1)
        return _handoff('diagnosis', sr.prepare_icc(ctx.work))

    def who2(step, ctx):
        sr.accept_icc(ctx.work)
        return _handoff('diagnosis', sr.prepare_who(ctx.work, pass_number=2))

    def diagnosis_other_default(step, ctx):
        sr.accept_who(ctx.work, pass_number=2)
        sr.finalize_diagnosis(ctx.work)
        return {'status': 'complete', 'reason': 'v6_self_second_diagnosis_default'}

    def diagnosis_finalize(step, ctx):
        sr.finalize_diagnosis(ctx.work)
        return {'status': 'complete'}

    def ptbg(step, ctx):
        sr.finalize_diagnosis(ctx.work)
        return _handoff('ptbg', sr.prepare_ptbg(ctx.work))

    def evidence_assignment(step, ctx):
        sr.accept_ptbg(ctx.work)
        return _handoff('evidence_resolution', sr.prepare_evidence_resolution(ctx.work))

    def evidence_audit(step, ctx):
        return _handoff('evidence_audit', sr.prepare_evidence_audit(ctx.work))

    def evidence_adjudication(step, ctx):
        manifest = sr.prepare_evidence_adjudication(ctx.work)
        if not manifest.get('required'):
            return {'status': 'complete', 'reason': 'no_disagreement'}
        return _handoff('evidence_adjudication', manifest)

    def evidence_finalize(step, ctx):
        sr.finalize_evidence(ctx.work)
        return {'status': 'complete'}

    def report_blocks(step, ctx):
        if not staged.has_artifact(ctx.work, 'evidence_enriched', 'reportable-elements.yaml'):
            sr.finalize_evidence(ctx.work)
        # finalize_evidence deterministically writes report blocks.
        return {'status': 'complete'}

    def report(step, ctx):
        if not staged.has_artifact(ctx.work, 'report_write', 'report-write.yaml'):
            return _handoff('report_synthesis', sr.prepare_report(ctx.work))
        sr.finalize_report(ctx.work); sr.package_debug_bundle(ctx.work)
        return {'status': 'complete'}

    return {
        'structure': structure,
        'corpus': corpus,
        'diagnosis_who1': who1,
        'diagnosis_icc': icc,
        'diagnosis_who2': who2,
        'diagnosis_other_default': diagnosis_other_default,
        'diagnosis_finalize': diagnosis_finalize,
        'ptbg': ptbg,
        'evidence_assignment': evidence_assignment,
        'evidence_audit': evidence_audit,
        'evidence_adjudication': evidence_adjudication,
        'evidence_finalize': evidence_finalize,
        'report_blocks': report_blocks,
        'report': report,
    }


def _write_self_trace(work: Path, workflow, context: WorkflowContext, current=None) -> None:
    trace = TraceRecorder(staged.WORKFLOW_ID)
    for step in workflow.steps:
        if step.id in context.completed or _self_step_complete(step.id, context):
            trace.record(step.id, step.type, 'complete', dependencies=list(step.needs), executor='self')
        elif current == step.id:
            trace.record(step.id, step.type, 'handoff', dependencies=list(step.needs), executor='self')
        else:
            trace.record(step.id, step.type, 'pending', dependencies=list(step.needs), executor='self')
    trace.write(layout.logs(work) / 'workflow-trace.json')


def advance(work: Path) -> dict:
    """Advance native self by one bounded handoff using the shared workflow graph."""
    work = Path(work).resolve()
    staged._require_work(work); layout.ensure_dirs(work)
    workflow = compile_workflow()
    context = WorkflowContext(work, executor='self', profile='self', data={'settings': staged.load_settings()})
    runner = WorkflowRunner(workflow, SelfExecutor(_self_handlers(), completion=_self_step_complete))
    result = runner.advance(context)
    _write_self_trace(work, workflow, context, result.step_id)
    if result.status == 'handoff':
        payload = result.handoff or {}
        return {'status': 'handoff', 'stage': payload.get('stage') or result.step_id, 'manifest': payload.get('manifest')}
    if result.status == 'complete':
        if not (work / sr.DEBUG_ZIP_NAME).is_file() and (work / 'report-final.md').is_file():
            sr.package_debug_bundle(work)
        return {'status': 'complete', 'stage': 'complete', 'artifacts': sr.final_artifacts(work)}
    return {'status': 'pending', 'stage': result.step_id or 'workflow'}

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
        print(f"proforma-v1 self failed: {exc}", file=sys.stderr)
        return EXIT_FAILURE


if __name__ == "__main__":
    raise SystemExit(main())
