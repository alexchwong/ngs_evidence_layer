"""Legacy-v1 deterministic case pipeline used by scripts/run_case.py."""
from pathlib import Path

from workflows.common import announce, remove_if_present, require_file, run_command

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"


def diagnosis(work_dir: Path, python: str) -> None:
    work_dir = work_dir.resolve()
    announce(work_dir)
    output = work_dir / "diagnostic_evidence.md"
    machine = work_dir / "diagnostic_evidence.json"
    remove_if_present(output, machine)
    run_command(
        [python, str(SCRIPTS / "retrieve.py"), "diagnosis", "--work-dir", str(work_dir)],
        "step 2: retrieve diagnosis evidence",
    )
    require_file(output, "diagnostic_evidence.md")
    require_file(machine, "Step-2 machine boundary")
    print(f"[run_case] output: {output}", file=__import__('sys').stderr)


def downstream(work_dir: Path, python: str) -> None:
    work_dir = work_dir.resolve()
    announce(work_dir)
    bundle = work_dir / "bundle.json"
    evidence = work_dir / "evidence.md"
    card_tags = work_dir / "card-tags.json"
    evidence_tmp = evidence.with_suffix(evidence.suffix + ".tmp")
    card_tags_tmp = card_tags.with_suffix(card_tags.suffix + ".tmp")
    remove_if_present(bundle, evidence, card_tags, evidence_tmp, card_tags_tmp)

    run_command(
        [python, str(SCRIPTS / "retrieve.py"), "downstream", "--work-dir", str(work_dir)],
        "step 4: retrieve full evidence bundle",
    )
    require_file(bundle, "bundle.json")

    render_command = [
        python,
        str(SCRIPTS / "render.py"),
        "--bundle", str(bundle),
        "--output", str(evidence_tmp),
        "--card-tag-output", str(card_tags_tmp),
    ]
    run_command(render_command, "step 5: render evidence")
    require_file(evidence_tmp, "evidence.md")
    require_file(card_tags_tmp, "card-tags.json")
    evidence_tmp.replace(evidence)
    card_tags_tmp.replace(card_tags)
    print(f"[run_case] output: {evidence}", file=__import__('sys').stderr)
