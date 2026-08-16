"""Diagnosis-first-v1 deterministic case pipeline used by scripts/run_case.py."""
from pathlib import Path

from workflows.common import announce, remove_if_present, require_file, run_command

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"


def diagnosis(work_dir: Path, python: str) -> None:
    work_dir = work_dir.resolve()
    announce(work_dir)
    bundle = work_dir / "diagnostic_evidence.json"
    evidence = work_dir / "diagnostic_evidence.md"
    evidence_tmp = evidence.with_suffix(evidence.suffix + ".tmp")
    remove_if_present(bundle, evidence, evidence_tmp)

    run_command(
        [python, str(SCRIPTS / "retrieve.py"), "diagnosis", "--work-dir", str(work_dir)],
        "diagnosis-first step 2: retrieve diagnosis and germline evidence",
    )
    require_file(bundle, "diagnostic_evidence.json")

    run_command(
        [python, str(SCRIPTS / "render.py"), "--bundle", str(bundle), "--output", str(evidence_tmp)],
        "diagnosis-first step 2: render diagnostic evidence",
    )
    require_file(evidence_tmp, "diagnostic_evidence.md")
    evidence_tmp.replace(evidence)
    print(f"[run_case] output: {evidence}", file=__import__('sys').stderr)


def downstream(work_dir: Path, python: str) -> None:
    work_dir = work_dir.resolve()
    announce(work_dir)
    bundle = work_dir / "bundle.json"
    downstream_evidence = work_dir / "downstream_evidence.md"
    evidence = work_dir / "evidence.md"
    card_tags = work_dir / "card-tags.json"
    downstream_tmp = downstream_evidence.with_suffix(downstream_evidence.suffix + ".tmp")
    evidence_tmp = evidence.with_suffix(evidence.suffix + ".tmp")
    card_tags_tmp = card_tags.with_suffix(card_tags.suffix + ".tmp")
    remove_if_present(
        bundle, downstream_evidence, evidence, card_tags,
        downstream_tmp, evidence_tmp, card_tags_tmp,
    )

    run_command(
        [python, str(SCRIPTS / "retrieve.py"), "downstream", "--work-dir", str(work_dir)],
        "diagnosis-first step 4: retrieve downstream evidence",
    )
    require_file(bundle, "bundle.json")

    run_command(
        [
            python, str(SCRIPTS / "render.py"),
            "--bundle", str(bundle), "--retrieved-only", "--output", str(downstream_tmp),
        ],
        "diagnosis-first step 4: render downstream evidence",
    )
    require_file(downstream_tmp, "downstream_evidence.md")
    downstream_tmp.replace(downstream_evidence)

    run_command(
        [
            python, str(SCRIPTS / "render.py"),
            "--bundle", str(bundle), "--output", str(evidence_tmp),
            "--card-tag-output", str(card_tags_tmp),
        ],
        "diagnosis-first step 4: render combined citation evidence",
    )
    require_file(evidence_tmp, "evidence.md")
    require_file(card_tags_tmp, "card-tags.json")
    evidence_tmp.replace(evidence)
    card_tags_tmp.replace(card_tags)
    print(f"[run_case] output: {downstream_evidence}", file=__import__('sys').stderr)
