#!/usr/bin/env python3
"""Terraced-v6 native self executor.

The current/session model performs the model reasoning directly.  This script
only prepares bounded file inputs, validates machine-critical outputs, performs
deterministic retrieval/provenance, crops evidence disagreements, and renders
the final report.  It never calls an LLM.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from workflows.terraced_v6 import layout
from workflows.terraced_v6 import self_runtime as sr
from workflows.terraced_v6 import step as staged

EXIT_OK = 0
EXIT_FAILURE = 1


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


def cmd_setup(args):
    ns = SimpleNamespace(
        mode=args.mode,
        case_file=args.case_file,
        example=args.example,
        case_id=args.case_id,
        work_dir=args.work_dir,
        project=args.project,
        pipeline="self",
    )
    return staged.run_setup(ns)


def cmd_structure(args):
    work = Path(args.work_dir).resolve()
    staged._require_work(work)
    layout.ensure_dirs(work)
    _print_manifest({
        "pass": "who1",
        "phase": "structure_case",
        "note": "Complete this structure subtask and WHO1 in one continuous self reasoning pass; do not treat this deterministic interleave as another model pass.",
        "contract": sr.contract_path("structure_case"),
        "inputs": {
            "case": layout.input(work, "case.md"),
            "allowed_bootstrap_cmcs": layout.setup(work, "case-major-categories.json"),
            "assay_scope": layout.setup(work, "ngs-panel-scope.md"),
        },
        "output": sr.case_path(work),
        "next": f"{Path(__file__).resolve()} who1 --work-dir {work}",
    })
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
    s.add_argument("--mode", required=True, choices=["ngs-report", "nel-demo", "nel-validate", "nel-validate-function", "nel-validate-brief"])
    s.add_argument("--case-file", type=Path)
    s.add_argument("--example", type=int)
    s.add_argument("--case-id")
    sw = s.add_mutually_exclusive_group()
    sw.add_argument("--work-dir", type=Path)
    sw.add_argument("--project", action="store_true")
    for name in ("structure", "who1", "icc", "who2", "ptbg", "evidence-resolution", "evidence-audit", "evidence-adjudication", "finalize-evidence", "report", "finalize-report"):
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
