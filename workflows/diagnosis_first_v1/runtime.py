"""Deterministic rule-view and draft-assembly helpers for diagnosis-first-v1."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
from workflows.diagnosis_first_v1 import audit_policy as report_audit
from scripts import vocab  # noqa: E402
from workflows.diagnosis_first_v1 import report_yaml  # noqa: E402

WORKFLOW_PROMPT_DIR = REPO_ROOT / "workflows" / "diagnosis_first_v1" / "prompts"
DEFAULT_RULES = WORKFLOW_PROMPT_DIR / "agreed_reporting_rules.md"
REPORTING_RULE_POLICY = WORKFLOW_PROMPT_DIR / "reporting_rule_policy.md"
PROMPT_DIR = WORKFLOW_PROMPT_DIR / "rule_views"
RULE_TEMPLATES = {
    "diagnosis": PROMPT_DIR / "diagnosis_rule_view.md",
    "remainder": PROMPT_DIR / "remainder_rule_view.md",
    "full": PROMPT_DIR / "full_rule_view.md",
}
SECTION_HEADING = re.compile(r"^# R(\d+)\b")


def _validation_case_text(mode: str, case_id: str) -> str:
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


def setup_assets(work_dir: Path, *, mode: str, case_id: str | None = None) -> None:
    """Create only diagnosis-first-specific setup assets. Shared setup is external."""
    if mode in {"nel-validate", "nel-validate-function"}:
        if not case_id:
            raise ValueError(f"{mode} requires a validation case ID")
        _write_case_if_absent(work_dir, _validation_case_text(mode, case_id))
    write_rule_slice(DEFAULT_RULES, work_dir / "reporting-rules-dx.md", {0, 1})


def _read(path: Path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc


def _render_prompt_template(path: Path, replacements: dict[str, str]) -> str:
    """Render one prompt-owned diagnosis-first template with strict named placeholders."""
    text = _read(path)
    for marker, value in replacements.items():
        placeholder = "{{" + marker + "}}"
        if placeholder not in text:
            raise ValueError(f"diagnosis-first prompt template {path} is missing required placeholder {placeholder}")
        text = text.replace(placeholder, value.rstrip())
    unresolved = sorted(set(re.findall(r"{{[A-Z0-9_]+}}", text)))
    if unresolved:
        raise ValueError(
            f"diagnosis-first prompt template {path} contains unresolved placeholder(s): "
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
            "unsupported diagnosis-first reporting-rule section combination. Expected exactly " + allowed
        )
    return kind


def _render_rule_view(kind: str, rules: str) -> str:
    template = RULE_TEMPLATES.get(kind)
    if template is None:  # pragma: no cover - internal programming error
        raise ValueError(f"unsupported diagnosis-first rule-view kind: {kind}")
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
    """Render one diagnosis-first rule view with a purpose-built analysis contract."""
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


def extract_refined_cmc(path: Path) -> str:
    return report_yaml.read_refined_cmc(path, vocab.CASE_MAJOR_CATEGORY_SET)


def diagnosis_first_branch(case_input: Path, diagnosis_draft: Path) -> tuple[str, str, bool]:
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
    document = report_yaml.validate_rule_document(
        draft,
        evidence,
        rules,
        require_refined_cmc=True,
        valid_cmcs=vocab.CASE_MAJOR_CATEGORY_SET,
    )
    return document["refined_cmc"]


def validate_remainder_draft(draft: Path, evidence: Path, rules: Path) -> None:
    report_yaml.validate_rule_document(
        draft,
        evidence,
        rules,
        require_refined_cmc=False,
    )


def assemble_report_draft(
    case_input: Path,
    diagnosis_draft: Path,
    remainder_draft: Path,
    output: Path,
    diagnosis_evidence: Path,
    downstream_evidence: Path,
    diagnosis_rules: Path,
    remainder_rules: Path,
) -> tuple[Path, bool, str]:
    initial, refined, changed = diagnosis_first_branch(case_input, diagnosis_draft)
    dx = report_yaml.validate_rule_document(
        diagnosis_draft,
        diagnosis_evidence,
        diagnosis_rules,
        require_refined_cmc=True,
        valid_cmcs=vocab.CASE_MAJOR_CATEGORY_SET,
    )
    remainder = report_yaml.validate_rule_document(
        remainder_draft,
        downstream_evidence,
        remainder_rules,
        require_refined_cmc=False,
    )
    assembled_rules = remainder["rules"] if changed else dx["rules"] + remainder["rules"]
    report_yaml.write_report_draft(assembled_rules, output)
    report_yaml.write_summary_template(output.with_name("report-summary.yaml"))
    return output, changed, refined


def render_report_summary(
    summary: Path,
    report_draft: Path,
    evidence: Path,
    card_tags: Path,
    output: Path,
) -> Path:
    return report_yaml.render_summary(summary, report_draft, evidence, card_tags, output)


def run(command: str, work_dir: Path) -> list[str]:
    """Execute one diagnosis-first deterministic runtime command."""
    work = work_dir.resolve()
    if command == "cmc":
        refined = validate_diagnosis_draft(
            work / "report-draft-dx.yaml",
            work / "diagnostic_evidence.md",
            work / "reporting-rules-dx.md",
        )
        return [refined]
    if command == "remainder-rules":
        initial, refined, changed = diagnosis_first_branch(
            work / "case-input.json", work / "report-draft-dx.yaml"
        )
        sections = set(range(0, 6)) if changed else {2, 3, 4, 5}
        path = write_rule_slice(DEFAULT_RULES, work / "reporting-rules-remainder.md", sections)
        return [str(path), f"INITIAL_CMC={initial}", f"REFINED_CMC={refined}", f"CMC_CHANGED={'yes' if changed else 'no'}"]
    if command == "validate-remainder":
        validate_remainder_draft(
            work / "report-draft-remainder.yaml",
            work / "downstream_evidence.md",
            work / "reporting-rules-remainder.md",
        )
        return [str(work / "report-draft-remainder.yaml")]
    if command == "assemble":
        path, changed, refined = assemble_report_draft(
            work / "case-input.json",
            work / "report-draft-dx.yaml",
            work / "report-draft-remainder.yaml",
            work / "report-draft.yaml",
            work / "diagnostic_evidence.md",
            work / "downstream_evidence.md",
            work / "reporting-rules-dx.md",
            work / "reporting-rules-remainder.md",
        )
        return [str(path), str(path.with_name("report-summary.yaml")), f"REFINED_CMC={refined}", f"CMC_CHANGED={'yes' if changed else 'no'}"]
    if command == "render":
        path = render_report_summary(
            work / "report-summary.yaml",
            work / "report-draft.yaml",
            work / "evidence.md",
            work / "card-tags.json",
            work / "report-final.md",
        )
        return [str(path)]
    raise ValueError(f"diagnosis-first-v1 does not implement runtime command {command!r}")
