#!/usr/bin/env python3
"""Deterministic helpers for the parallel 0.2.2 diagnosis-first prototype.

This module renders purpose-built prototype reporting-rule views from canonical
rules, validates/extracts the terminal Step-3 CMC routing decision, and assembles
the conventional ``report-draft.md`` while keeping authored prompt prose outside Python.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import report_audit  # noqa: E402
import vocab  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RULES = REPO_ROOT / "rules" / "agreed_reporting_rules.md"
REPORTING_RULE_POLICY = REPO_ROOT / "prompts" / "workflow" / "reporting_rule_policy.md"
PROTOTYPE_PROMPT_DIR = REPO_ROOT / "workflows" / "prototype" / "prompts" / "rule_views"
PROTOTYPE_RULE_TEMPLATES = {
    "diagnosis": PROTOTYPE_PROMPT_DIR / "diagnosis_rule_view.md",
    "remainder": PROTOTYPE_PROMPT_DIR / "remainder_rule_view.md",
    "full": PROTOTYPE_PROMPT_DIR / "full_rule_view.md",
}
SECTION_HEADING = re.compile(r"^# R(\d+)\b")
REFINED_CMC_LINE = re.compile(r"^REFINED_CMC: (.+)$")
DEMO_EXAMPLES = {
    1: "01-escalation-fires.md",
    2: "02-escalation-does-not-fire.md",
    3: "03-ambiguous-disease.md",
    4: "04-genes-the-corpus-cannot-address.md",
    5: "05-germline-architecture.md",
    6: "06-sf3b1-diagnostic-adjudication.md",
}
CASE_MAJOR_CATEGORY_INSTRUCTION = (
    "Select exactly one case_major_category representing the supplied starting "
    "clinicomorphological major category; do not revise it using molecular results."
)


def _create_or_resolve_work_dir(work_dir: Path | None, project: bool) -> Path:
    """Create or resolve a prototype work directory without touching legacy helpers."""
    if work_dir is not None:
        work_dir = work_dir.expanduser().resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        return work_dir
    if project:
        root = REPO_ROOT / "temp"
        root.mkdir(exist_ok=True)
        return Path(tempfile.mkdtemp(prefix="ngs-evidence-layer-", dir=root)).resolve()
    return Path(tempfile.mkdtemp(prefix="ngs-evidence-layer-")).resolve()


def write_case_major_categories(output: Path) -> Path:
    payload = {
        "case_major_categories": list(vocab.CASE_MAJOR_CATEGORIES),
        "instruction": CASE_MAJOR_CATEGORY_INSTRUCTION,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output


def _demo_paths(example: int) -> tuple[Path, Path]:
    try:
        name = DEMO_EXAMPLES[example]
    except KeyError as exc:
        raise ValueError(
            "example must be one of: " + ", ".join(map(str, sorted(DEMO_EXAMPLES)))
        ) from exc
    return REPO_ROOT / "examples" / "cases" / name, REPO_ROOT / "examples" / "expected" / name


def _validation_case_text(mode: str, case_id: str) -> str:
    # Lazy import is deliberate: validation code must not enter the legacy import chain.
    repo_text = str(REPO_ROOT)
    inserted = repo_text not in sys.path
    if inserted:
        sys.path.insert(0, repo_text)
    try:
        from validation.cases import retrieve_case

        case_file = "case_functional.md" if mode == "nel-validate-function" else "case_summary.md"
        return retrieve_case(case_id, case_file)
    finally:
        if inserted and sys.path and sys.path[0] == repo_text:
            sys.path.pop(0)


def _write_case_if_absent(work_dir: Path, text: str) -> Path:
    output = work_dir / "case.md"
    payload = text.rstrip() + "\n"
    if output.exists():
        existing = output.read_text(encoding="utf-8")
        if existing != payload:
            raise ValueError(
                f"{output} already exists and differs from the requested validation case; "
                "setup will not overwrite case.md. Use a new work directory or remove the stale "
                "case.md deliberately before rerunning setup."
            )
        return output
    output.write_text(payload, encoding="utf-8")
    return output


def setup_prototype(
    *,
    mode: str = "ngs-report",
    work_dir: Path | None = None,
    project: bool = False,
    example: int | None = None,
    case_id: str | None = None,
) -> tuple[Path, Path | None, Path | None]:
    """Prepare branch-independent prototype assets and optional mode-specific case inputs."""
    if mode == "nel-demo":
        if example is None:
            raise ValueError("--example is required when --mode nel-demo")
        if case_id is not None:
            raise ValueError("--case-id is not valid when --mode nel-demo")
        demo_case, demo_expected = _demo_paths(example)
    elif mode in {"nel-validate", "nel-validate-function"}:
        if case_id is None:
            raise ValueError(f"--case-id is required when --mode {mode}")
        if example is not None:
            raise ValueError(f"--example is not valid when --mode {mode}")
        demo_case = demo_expected = None
    elif mode == "ngs-report":
        if example is not None or case_id is not None:
            raise ValueError("--example and --case-id are not valid when --mode ngs-report")
        demo_case = demo_expected = None
    else:  # pragma: no cover - argparse constrains CLI mode values
        raise ValueError(f"unsupported prototype mode: {mode}")

    validation_case_text = (
        _validation_case_text(mode, case_id)
        if mode in {"nel-validate", "nel-validate-function"}
        else None
    )
    resolved = _create_or_resolve_work_dir(work_dir, project)
    if validation_case_text is not None:
        _write_case_if_absent(resolved, validation_case_text)
    write_case_major_categories(resolved / "case-major-categories.json")
    write_rule_slice(DEFAULT_RULES, resolved / "reporting-rules-dx.md", {0, 1})

    return resolved, demo_case, demo_expected


def _read(path: Path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc


def _render_prompt_template(path: Path, replacements: dict[str, str]) -> str:
    """Render one prompt-owned prototype template with strict named placeholders."""
    text = _read(path)
    for marker, value in replacements.items():
        placeholder = "{{" + marker + "}}"
        if placeholder not in text:
            raise ValueError(f"prototype prompt template {path} is missing required placeholder {placeholder}")
        text = text.replace(placeholder, value.rstrip())
    unresolved = sorted(set(re.findall(r"{{[A-Z0-9_]+}}", text)))
    if unresolved:
        raise ValueError(
            f"prototype prompt template {path} contains unresolved placeholder(s): "
            + ", ".join(unresolved)
        )
    return text.rstrip() + "\n"


def _rule_view_kind(sections: set[int]) -> str:
    mapping = {
        frozenset({0, 1}): "diagnosis",
        frozenset({2, 3, 4, 5}): "remainder",
        frozenset(range(0, 6)): "full",
    }
    kind = mapping.get(frozenset(sections))
    if kind is None:
        allowed = "0 1 (diagnosis), 2 3 4 5 (downstream), or 0 1 2 3 4 5 (full re-analysis)"
        raise ValueError(
            "unsupported prototype reporting-rule section combination. Expected exactly " + allowed
        )
    return kind


def _render_rule_view(kind: str, rules: str) -> str:
    template = PROTOTYPE_RULE_TEMPLATES.get(kind)
    if template is None:  # pragma: no cover - internal programming error
        raise ValueError(f"unsupported prototype rule-view kind: {kind}")
    return _render_prompt_template(
        template,
        {
            "REPORTING_RULE_POLICY": _read(REPORTING_RULE_POLICY),
            "CANONICAL_RULES": rules,
        },
    )


def _canonical_rule_sections(rules_text: str, sections: set[int]) -> str:
    """Return only the requested canonical R sections, without generic pre/postamble."""
    lines = rules_text.splitlines()
    first_rule = next((i for i, line in enumerate(lines) if SECTION_HEADING.match(line)), None)
    if first_rule is None:
        raise ValueError("agreed_reporting_rules.md contains no # R<section> headings")
    out = []
    current_section = None
    for line in lines[first_rule:]:
        match = SECTION_HEADING.match(line)
        if match:
            current_section = int(match.group(1))
        elif line.startswith("# "):
            current_section = None
        if current_section in sections:
            out.append(line)
    return "\n".join(out).rstrip() + "\n"


def slice_rules_text(rules_text: str, sections: set[int]) -> str:
    """Render one prototype rule view with a purpose-built analysis contract."""
    if not sections:
        raise ValueError("at least one reporting-rule section is required")
    unknown = sorted(sections - set(range(0, 6)))
    if unknown:
        raise ValueError("unsupported reporting-rule section(s): " + ", ".join(map(str, unknown)))

    kind = _rule_view_kind(sections)
    rules = _canonical_rule_sections(rules_text, sections)
    result = _render_rule_view(kind, rules)
    specs = report_audit.agreed_rule_specs(result)
    found_sections = {int(spec["rule_id"].split(".", 1)[0][1:]) for spec in specs}
    missing = sorted(sections - found_sections)
    if missing:
        raise ValueError(
            "canonical reporting rules contain no rules for requested section(s): "
            + ", ".join(map(str, missing))
        )
    return result


def write_rule_slice(source: Path, output: Path, sections: set[int]) -> Path:
    payload = slice_rules_text(_read(source), sections)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload, encoding="utf-8")
    return output


def split_diagnosis_draft(draft_text: str) -> tuple[str, str]:
    """Return (R0-R1 draft, refined CMC) after validating terminal-line shape."""
    lines = draft_text.splitlines()
    if not lines:
        raise ValueError("report-draft-dx.md is empty")
    match = REFINED_CMC_LINE.fullmatch(lines[-1])
    if match is None:
        raise ValueError(
            "report-draft-dx.md must end with exactly one routing line in the form "
            "'REFINED_CMC: <canonical case major category>'. No text, citation marker, "
            "or punctuation may follow that line."
        )
    refined = match.group(1)
    if refined not in vocab.CASE_MAJOR_CATEGORY_SET:
        raise ValueError(
            f"REFINED_CMC value {refined!r} is not canonical. Replace it with exactly one of: "
            + " | ".join(vocab.CASE_MAJOR_CATEGORIES)
        )
    rule_text = "\n".join(lines[:-1])
    if not rule_text:
        raise ValueError("report-draft-dx.md contains no reporting-rule lines before REFINED_CMC")
    return rule_text + "\n", refined


def extract_refined_cmc(path: Path) -> str:
    return split_diagnosis_draft(_read(path))[1]


def prototype_branch(case_input: Path, diagnosis_draft: Path) -> tuple[str, str, bool]:
    try:
        case_document = json.loads(_read(case_input))
    except json.JSONDecodeError as exc:
        raise ValueError(f"case-input.json is invalid JSON: {exc}") from exc
    initial = case_document.get("case_major_category")
    if initial not in vocab.CASE_MAJOR_CATEGORY_SET:
        raise ValueError(
            "case-input.json case_major_category is missing or non-canonical; rerun Step 1B"
        )
    refined = extract_refined_cmc(diagnosis_draft)
    return initial, refined, refined != initial


def validate_diagnosis_draft(draft: Path, evidence: Path, rules: Path) -> str:
    rule_draft, refined = split_diagnosis_draft(_read(draft))
    report_audit.validate_draft(
        rule_draft,
        _read(evidence),
        _read(rules),
        allow_no_evidence_tags=True,
    )
    return refined


def assemble_report_draft(
    case_input: Path,
    diagnosis_draft: Path,
    remainder_draft: Path,
    output: Path,
    evidence: Path,
    rules: Path,
) -> tuple[Path, bool, str]:
    initial, refined, changed = prototype_branch(case_input, diagnosis_draft)
    dx_rules, refined = split_diagnosis_draft(_read(diagnosis_draft))
    remainder = _read(remainder_draft)
    if not remainder.strip():
        raise ValueError("report-draft-remainder.md is empty")

    assembled = remainder if changed else dx_rules.rstrip() + "\n" + remainder.lstrip()
    if not assembled.endswith("\n"):
        assembled += "\n"
    report_audit.validate_draft(
        assembled,
        _read(evidence),
        _read(rules),
        allow_no_evidence_tags=True,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(assembled, encoding="utf-8")
    return output, changed, refined


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    setup = sub.add_parser(
        "setup",
        help="prepare one prototype work directory and all branch-independent procedural assets",
    )
    work_group = setup.add_mutually_exclusive_group()
    work_group.add_argument("--work-dir", type=Path, help="reuse/create this work directory")
    work_group.add_argument("--project", action="store_true", help="create the work directory under repo temp/")
    setup.add_argument(
        "--mode",
        choices=("ngs-report", "nel-demo", "nel-validate", "nel-validate-function"),
        default="ngs-report",
    )
    setup.add_argument("--example", type=int, choices=sorted(DEMO_EXAMPLES))
    setup.add_argument("--case-id")

    rules = sub.add_parser("rules", help="write a deterministic subset of agreed reporting rules")
    rules.add_argument("--source", type=Path, default=DEFAULT_RULES)
    rules.add_argument("--sections", type=int, nargs="+", required=True)
    rules.add_argument("--output", type=Path, required=True)

    cmc = sub.add_parser("cmc", help="validate report-draft-dx.md and print its refined CMC")
    cmc.add_argument("--draft", type=Path, required=True)
    cmc.add_argument("--evidence", type=Path, required=True)
    cmc.add_argument("--rules", type=Path, required=True)

    remainder_rules = sub.add_parser(
        "remainder-rules",
        help="write R2-R5 when CMC is stable or R0-R5 when the Step-3 CMC changed",
    )
    remainder_rules.add_argument("--source", type=Path, default=DEFAULT_RULES)
    remainder_rules.add_argument("--case-input", type=Path, required=True)
    remainder_rules.add_argument("--diagnosis-draft", type=Path, required=True)
    remainder_rules.add_argument("--output", type=Path, required=True)

    assemble = sub.add_parser("assemble", help="assemble and validate the conventional report-draft.md")
    assemble.add_argument("--case-input", type=Path, required=True)
    assemble.add_argument("--diagnosis-draft", type=Path, required=True)
    assemble.add_argument("--remainder-draft", type=Path, required=True)
    assemble.add_argument("--evidence", type=Path, required=True)
    assemble.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    assemble.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    try:
        if args.command == "setup":
            work_dir, demo_case, demo_expected = setup_prototype(
                mode=args.mode,
                work_dir=args.work_dir,
                project=args.project,
                example=args.example,
                case_id=args.case_id,
            )
            print(work_dir)
            if demo_case is not None:
                print(demo_case.relative_to(REPO_ROOT))
                print(demo_expected.relative_to(REPO_ROOT))
        elif args.command == "rules":
            path = write_rule_slice(args.source, args.output, set(args.sections))
            print(path)
        elif args.command == "cmc":
            refined = validate_diagnosis_draft(args.draft, args.evidence, args.rules)
            print(refined)
        elif args.command == "remainder-rules":
            initial, refined, changed = prototype_branch(args.case_input, args.diagnosis_draft)
            sections = set(range(0, 6)) if changed else {2, 3, 4, 5}
            path = write_rule_slice(args.source, args.output, sections)
            print(path)
            print(f"INITIAL_CMC={initial}")
            print(f"REFINED_CMC={refined}")
            print(f"CMC_CHANGED={'yes' if changed else 'no'}")
        else:
            path, changed, refined = assemble_report_draft(
                args.case_input,
                args.diagnosis_draft,
                args.remainder_draft,
                args.output,
                args.evidence,
                args.rules,
            )
            print(path)
            print(f"REFINED_CMC={refined}")
            print(f"CMC_CHANGED={'yes' if changed else 'no'}")
    except (OSError, ValueError, KeyError) as exc:
        message = exc.args[0] if isinstance(exc, KeyError) and exc.args else str(exc)
        if args.command == "setup":
            parser.exit(1, f"{message}\n")
        parser.exit(1, f"PROTOTYPE WORKFLOW FAILED: {message}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
