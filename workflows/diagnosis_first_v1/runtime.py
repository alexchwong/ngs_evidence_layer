"""Deterministic rule-view and draft-assembly helpers for diagnosis-first-v1."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import report_audit  # noqa: E402
import vocab  # noqa: E402

DEFAULT_RULES = REPO_ROOT / "rules" / "agreed_reporting_rules.md"
REPORTING_RULE_POLICY = REPO_ROOT / "prompts" / "workflow" / "reporting_rule_policy.md"
PROMPT_DIR = REPO_ROOT / "workflows" / "diagnosis_first_v1" / "prompts" / "rule_views"
RULE_TEMPLATES = {
    "diagnosis": PROMPT_DIR / "diagnosis_rule_view.md",
    "remainder": PROMPT_DIR / "remainder_rule_view.md",
    "full": PROMPT_DIR / "full_rule_view.md",
}
SECTION_HEADING = re.compile(r"^# R(\d+)\b")
REFINED_CMC_LINE = re.compile(r"^REFINED_CMC: (.+)$")


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
    initial, refined, changed = diagnosis_first_branch(case_input, diagnosis_draft)
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
