"""Categorical-v1 deterministic case pipeline used by scripts/run_case.py."""
from pathlib import Path

from workflows.common import announce, remove_if_present, require_file, run_command
from workflows.categorical_v1 import report_yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"


def diagnosis(work_dir: Path, python: str) -> None:
    work_dir = work_dir.resolve()
    announce(work_dir)
    bundle = work_dir / "diagnostic_evidence.json"
    evidence = work_dir / "diagnostic_evidence.md"
    evidence_tmp = evidence.with_suffix(evidence.suffix + ".tmp")
    draft = work_dir / "report-draft-dx.yaml"
    remove_if_present(bundle, evidence, evidence_tmp, draft)

    run_command(
        [python, str(SCRIPTS / "retrieve.py"), "diagnosis", "--work-dir", str(work_dir)],
        "categorical step 2: retrieve diagnosis and germline evidence",
    )
    require_file(bundle, "diagnostic_evidence.json")

    run_command(
        [python, str(SCRIPTS / "render.py"), "--bundle", str(bundle), "--output", str(evidence_tmp)],
        "categorical step 2: render diagnostic evidence",
    )
    require_file(evidence_tmp, "diagnostic_evidence.md")
    evidence_tmp.replace(evidence)
    report_yaml.write_rule_template(
        work_dir / "reporting-rules-dx.md", draft, include_refined_cmc=True
    )
    print(f"[run_case] output: {evidence}", file=__import__('sys').stderr)
    print(f"[run_case] output: {draft}", file=__import__('sys').stderr)


def downstream(work_dir: Path, python: str) -> None:
    work_dir = work_dir.resolve()
    announce(work_dir)
    bundle = work_dir / "bundle.json"
    downstream_evidence = work_dir / "downstream_evidence.md"
    evidence = work_dir / "evidence.md"
    card_tags = work_dir / "card-tags.json"
    draft = work_dir / "report-draft-remainder.yaml"
    downstream_tmp = downstream_evidence.with_suffix(downstream_evidence.suffix + ".tmp")
    evidence_tmp = evidence.with_suffix(evidence.suffix + ".tmp")
    card_tags_tmp = card_tags.with_suffix(card_tags.suffix + ".tmp")
    remove_if_present(
        bundle, downstream_evidence, evidence, card_tags, draft,
        downstream_tmp, evidence_tmp, card_tags_tmp,
    )

    run_command(
        [python, str(SCRIPTS / "retrieve.py"), "downstream", "--work-dir", str(work_dir)],
        "categorical step 4: retrieve downstream evidence",
    )
    require_file(bundle, "bundle.json")

    run_command(
        [
            python, str(SCRIPTS / "render.py"),
            "--bundle", str(bundle), "--retrieved-only", "--output", str(downstream_tmp),
        ],
        "categorical step 4: render downstream evidence",
    )
    require_file(downstream_tmp, "downstream_evidence.md")
    downstream_tmp.replace(downstream_evidence)

    run_command(
        [
            python, str(SCRIPTS / "render.py"),
            "--bundle", str(bundle), "--output", str(evidence_tmp),
            "--card-tag-output", str(card_tags_tmp),
        ],
        "categorical step 4: render combined citation evidence",
    )
    require_file(evidence_tmp, "evidence.md")
    require_file(card_tags_tmp, "card-tags.json")
    evidence_tmp.replace(evidence)
    card_tags_tmp.replace(card_tags)
    report_yaml.write_rule_template(
        work_dir / "reporting-rules-remainder.md", draft, include_refined_cmc=False
    )
    print(f"[run_case] output: {downstream_evidence}", file=__import__('sys').stderr)
    print(f"[run_case] output: {draft}", file=__import__('sys').stderr)
