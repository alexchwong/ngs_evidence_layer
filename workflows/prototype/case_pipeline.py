"""Diagnosis-first prototype deterministic case pipeline used by scripts/run_case.py."""
import subprocess
import sys
import tempfile
from pathlib import Path

from .runtime import extract_refined_cmc

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"

def resolve_work_dir(path):
    """Return an absolute, writable working directory.

    If *path* is supplied, it must resolve to a directory (creating it if
    necessary) and be writable. If not, create a retained secure system
    temporary directory.
    """
    if path:
        work = Path(path).resolve()
        if work.exists() and not work.is_dir():
            raise ValueError(f"work directory path exists but is not a directory: {work}")
        work.mkdir(parents=True, exist_ok=True)
        probe = work / ".run_case_writable"
        try:
            probe.write_text("", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            raise ValueError(f"work directory is not writable: {work}") from exc
    else:
        work = Path(tempfile.mkdtemp(prefix="ngs_evidence_layer_"))
    return work

def announce(work_dir):
    print(f"[run_case] working directory: {work_dir}", file=sys.stderr)

def run_command(command, stage):
    """Run a command array and fail closed on non-zero exit."""
    print(f"[run_case] {stage}", file=sys.stderr)
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as exc:
        print(f"[run_case] {stage} failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as exc:
        print(f"[run_case] {stage} failed: interpreter or script not found: {exc}", file=sys.stderr)
        sys.exit(1)

def require_file(path, description):
    if not path.is_file():
        print(f"[run_case] expected output not produced: {description} ({path})", file=sys.stderr)
        sys.exit(1)

def remove_if_present(*paths):
    for path in paths:
        if path.exists():
            path.unlink()

def prototype_diagnosis(args):
    work_dir = resolve_work_dir(args.work_dir)
    announce(work_dir)

    case_input = args.case_input or (work_dir / "case-input.json")
    evidence = args.output or (work_dir / "diagnostic_evidence.md")
    bundle = args.bundle_output or (work_dir / "diagnostic_evidence.json")
    bundle_tmp = bundle.with_suffix(bundle.suffix + ".tmp")
    evidence_tmp = evidence.with_suffix(evidence.suffix + ".tmp")
    remove_if_present(bundle, evidence, bundle_tmp, evidence_tmp)

    retrieve_command = [
        args.python, str(SCRIPTS / "retrieve.py"), "prototype-diagnosis",
        "--case-input", str(case_input),
        "--output", str(bundle_tmp),
    ]
    if args.corpus:
        retrieve_command.extend(["--corpus", str(args.corpus)])
    if args.index:
        retrieve_command.extend(["--index", str(args.index)])
    if args.blacklist:
        retrieve_command.extend(["--blacklist", str(args.blacklist)])
    run_command(retrieve_command, "prototype step 2: retrieve diagnosis and germline evidence")
    require_file(bundle_tmp, "prototype diagnostic machine boundary")
    bundle_tmp.replace(bundle)

    render_command = [
        args.python, str(SCRIPTS / "render.py"),
        "--bundle", str(bundle),
        "--output", str(evidence_tmp),
    ]
    if args.token_budget is not None:
        render_command.extend(["--token-budget", str(args.token_budget)])
    run_command(render_command, "prototype step 2: render diagnostic evidence")
    require_file(evidence_tmp, "diagnostic_evidence.md")
    evidence_tmp.replace(evidence)
    print(f"[run_case] output: {evidence}", file=sys.stderr)

def prototype_downstream(args):
    work_dir = resolve_work_dir(args.work_dir)
    announce(work_dir)

    diagnosis_result = args.diagnosis_result or (work_dir / "diagnostic_evidence.json")
    diagnosis_draft = args.diagnosis_draft or (work_dir / "report-draft-dx.md")
    bundle = args.bundle_output or (work_dir / "bundle.json")
    downstream = args.output or (work_dir / "downstream_evidence.md")
    evidence = args.combined_output or (work_dir / "evidence.md")
    card_tags = args.card_tag_output or (work_dir / "card-tags.json")
    bundle_tmp = bundle.with_suffix(bundle.suffix + ".tmp")
    downstream_tmp = downstream.with_suffix(downstream.suffix + ".tmp")
    evidence_tmp = evidence.with_suffix(evidence.suffix + ".tmp")
    card_tags_tmp = card_tags.with_suffix(card_tags.suffix + ".tmp")
    remove_if_present(
        bundle, downstream, evidence, card_tags,
        bundle_tmp, downstream_tmp, evidence_tmp, card_tags_tmp,
    )

    refined_cmc = extract_refined_cmc(diagnosis_draft)
    retrieve_command = [
        args.python, str(SCRIPTS / "retrieve.py"), "prototype-downstream",
        "--diagnosis-result", str(diagnosis_result),
        "--refined-case-major-category", refined_cmc,
        "--output", str(bundle_tmp),
    ]
    if args.genes:
        retrieve_command.extend(["--genes", *args.genes])
    if args.corpus:
        retrieve_command.extend(["--corpus", str(args.corpus)])
    if args.index:
        retrieve_command.extend(["--index", str(args.index)])
    if args.blacklist:
        retrieve_command.extend(["--blacklist", str(args.blacklist)])
    run_command(retrieve_command, "prototype step 4: retrieve downstream evidence")
    require_file(bundle_tmp, "bundle.json")
    bundle_tmp.replace(bundle)

    downstream_command = [
        args.python, str(SCRIPTS / "render.py"),
        "--bundle", str(bundle),
        "--retrieved-only",
        "--output", str(downstream_tmp),
    ]
    combined_command = [
        args.python, str(SCRIPTS / "render.py"),
        "--bundle", str(bundle),
        "--output", str(evidence_tmp),
        "--card-tag-output", str(card_tags_tmp),
    ]
    if args.token_budget is not None:
        downstream_command.extend(["--token-budget", str(args.token_budget)])
        combined_command.extend(["--token-budget", str(args.token_budget)])
    run_command(downstream_command, "prototype step 4: render downstream evidence")
    require_file(downstream_tmp, "downstream_evidence.md")
    downstream_tmp.replace(downstream)
    run_command(combined_command, "prototype step 4: render combined citation evidence")
    require_file(evidence_tmp, "evidence.md")
    require_file(card_tags_tmp, "card-tags.json")
    evidence_tmp.replace(evidence)
    card_tags_tmp.replace(card_tags)

    # Surface only the evidence file intended for the next model step.
    print(f"[run_case] output: {downstream}", file=sys.stderr)

