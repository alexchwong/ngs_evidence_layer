"""Deterministic boundaries for diagnosis-lab report synthesis.

Models write the report prose, supporting reasons, and evidence dispositions.
This module assigns stable IDs, prevents later passes from changing prose, and
renders the final cited report without another generative rewrite.
"""
from __future__ import annotations

import re


HEADING = "**Diagnosis**"
FACT_ID_PREFIX = "diagnosis-summary-"
CARD_TAG_RE = re.compile(r"\[card:([0-9a-f]{6})\]")
CARD_TAGS_RE = re.compile(r"(?:\[card:[0-9a-f]{6}\])+")
FORBIDDEN_MACHINE_TERMS = {
    "indeterminate",
    "not_established",
    "not_applicable",
    "schema_disease",
    "provisional_cmcs",
}


def _raise_issues(context: str, issues: list[str]) -> None:
    if issues:
        rendered = "\n".join(f"{index}. {issue}" for index, issue in enumerate(issues, 1))
        raise ValueError(f"{context} failed validation with {len(issues)} issue(s):\n{rendered}")


def diagnostic_sources(final_doc: dict) -> dict:
    """Assign deterministic IDs to the reviewed diagnostic state."""
    diagnoses = []
    for index, row in enumerate(final_doc.get("diagnoses") or [], 1):
        diagnoses.append(
            {
                "diagnosis_id": f"D{index}",
                "schema_disease": row["schema_disease"],
                "WHO5": dict(row["WHO5"], outcome_id=f"D{index}-WHO5"),
                "ICC": dict(row["ICC"], outcome_id=f"D{index}-ICC"),
                "materially_different": row["materially_different"],
            }
        )
    return {
        "routing": {
            "routing_id": "ROUTING-1",
            "provisional_cmcs": list(final_doc.get("provisional_cmcs") or []),
        },
        "diagnoses": diagnoses,
        "supporting_facts": [
            dict(row, diagnostic_fact_id=f"DX-FINAL-F{index}")
            for index, row in enumerate(final_doc.get("supporting_facts") or [], 1)
        ],
        "uncertainties": [
            dict(row, diagnostic_uncertainty_id=f"DX-FINAL-U{index}")
            for index, row in enumerate(final_doc.get("uncertainties") or [], 1)
        ],
    }


def source_id_sets(structured_case: dict, sources: dict) -> tuple[set[str], set[str]]:
    """Return permitted case and reviewed-diagnostic source IDs."""
    case_ids = {
        row["fact_id"]
        for row in structured_case.get("case_facts") or []
        if isinstance(row, dict) and isinstance(row.get("fact_id"), str)
    }
    diagnostic_ids = {sources["routing"]["routing_id"]}
    for row in sources["diagnoses"]:
        diagnostic_ids.update(
            [row["diagnosis_id"], row["WHO5"]["outcome_id"], row["ICC"]["outcome_id"]]
        )
    diagnostic_ids.update(row["diagnostic_fact_id"] for row in sources["supporting_facts"])
    diagnostic_ids.update(row["diagnostic_uncertainty_id"] for row in sources["uncertainties"])
    return case_ids, diagnostic_ids


def prose_to_facts(prose: str) -> dict:
    """Validate line-oriented diagnosis prose and copy each sentence into a fact."""
    lines = prose.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    issues = []
    if not lines or lines[0].strip() != HEADING:
        received = lines[0] if lines else None
        issues.append(
            f"Heading — Problem: expected exact first line {HEADING!r}; received {received!r}. "
            f"Required fix: begin the complete report with exactly {HEADING} on its own line."
        )
    elif lines[0] != HEADING:
        issues.append(
            f"Heading — Problem: contains surrounding whitespace ({lines[0]!r}). Required fix: return exactly "
            f"{HEADING} with no leading/trailing spaces or Markdown hard-break spaces."
        )
    body = lines[1:]
    if not body:
        issues.append("Report body — Problem: contains no diagnosis sentences. Required fix: include at least one full-stop-terminated prose sentence.")
    facts = []
    for index, line in enumerate(body, 1):
        if not line.strip():
            issues.append(f"Sentence {index} — Problem: line is blank. Required fix: remove the blank line.")
            continue
        stripped_line = line.strip()
        if line != line.strip():
            issues.append(
                f"Sentence {index} — Problem: contains surrounding whitespace ({line!r}). Required fix: remove all "
                "leading/trailing spaces, including Markdown two-space hard breaks."
            )
        if stripped_line.startswith(('-', '*', '#', '>')):
            issues.append(f"Sentence {index} — Problem: uses Markdown structure. Required fix: return plain prose without bullets, headings or blockquotes.")
        if not stripped_line.endswith("."):
            issues.append(f"Sentence {index} — Problem: does not end with a full stop. Required fix: end the sentence with '.'.")
        if "[card:" in line:
            issues.append(f"Sentence {index} — Problem: contains a runtime card tag. Required fix: remove every card tag from synthesis prose.")
        lowered = line.lower()
        used = sorted(term for term in FORBIDDEN_MACHINE_TERMS if term in lowered)
        if used:
            issues.append(
                f"Sentence {index} — Problem: exposes machine-state term(s): {', '.join(used)}. "
                "Required fix: replace them with natural clinical wording without changing the supported meaning."
            )
        facts.append({"fact_id": f"{FACT_ID_PREFIX}{index}", "fact": line})
    _raise_issues("diagnosis report synthesis", issues)
    return {"facts": facts}


def _validate_immutable_rows(document: dict, immutable: dict, *, aligned: bool) -> tuple[list[dict], list[str]]:
    expected_top = {"facts"}
    issues = []
    if not isinstance(document, dict) or set(document) != expected_top:
        received = sorted(document) if isinstance(document, dict) else type(document).__name__
        raise ValueError(
            f"Grounded report — Problem: expected one YAML object containing exactly facts; received {received!r}. "
            "Required fix: return the complete object with only the facts field."
        )
    rows = document["facts"]
    expected_rows = immutable["facts"]
    if not isinstance(rows, list) or len(rows) != len(expected_rows):
        raise ValueError(
            f"Grounded report.facts — Problem: expected {len(expected_rows)} rows, received "
            f"{len(rows) if isinstance(rows, list) else type(rows).__name__}. Required fix: return every immutable fact exactly once in supplied order."
        )
    required = {
        "fact_id",
        "fact",
        "reason",
        "source_case_fact_ids",
        "source_diagnostic_ids",
    }
    if aligned:
        required.add("citation")
    for index, (row, expected) in enumerate(zip(rows, expected_rows), 1):
        if not isinstance(row, dict) or set(row) != required:
            received = sorted(row) if isinstance(row, dict) else type(row).__name__
            issues.append(
                f"Fact {index} — Problem: expected fields {sorted(required)}, received {received!r}. "
                "Required fix: return exactly the configured fields."
            )
            continue
        for key in ("fact_id", "fact"):
            if row[key] != expected[key]:
                issues.append(
                    f"Fact {index}.{key} — Problem: changed immutable supplied value. Required fix: copy {key} character-for-character."
                )
        if not isinstance(row["reason"], str) or not row["reason"].strip():
            issues.append(f"Fact {index}.reason — Problem: blank or not a string. Required fix: supply a non-empty source-grounded reason.")
        for key in ("source_case_fact_ids", "source_diagnostic_ids"):
            if not isinstance(row[key], list) or any(not isinstance(x, str) for x in row[key]):
                issues.append(f"Fact {index}.{key} — Problem: expected a list of source-ID strings. Required fix: return a YAML list of supplied IDs.")
        if not row["source_case_fact_ids"] and not row["source_diagnostic_ids"]:
            issues.append(f"Fact {index} — Problem: has no source ID. Required fix: map it to at least one supplied case or diagnostic source ID.")
    return rows, issues


def validate_grounded(
    document: dict,
    immutable: dict,
    *,
    case_source_ids: set[str],
    diagnostic_source_ids: set[str],
) -> None:
    """Ensure reasons preserve facts and use only supplied source IDs."""
    rows, issues = _validate_immutable_rows(document, immutable, aligned=False)
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict) or not {"source_case_fact_ids", "source_diagnostic_ids"} <= set(row):
            continue
        case_row_ids = row["source_case_fact_ids"]
        diagnostic_row_ids = row["source_diagnostic_ids"]
        if not isinstance(case_row_ids, list) or any(not isinstance(x, str) for x in case_row_ids):
            continue
        if not isinstance(diagnostic_row_ids, list) or any(not isinstance(x, str) for x in diagnostic_row_ids):
            continue
        unknown_case = sorted(set(case_row_ids) - case_source_ids)
        unknown_diagnostic = sorted(set(diagnostic_row_ids) - diagnostic_source_ids)
        if unknown_case or unknown_diagnostic:
            unknown = unknown_case + unknown_diagnostic
            issues.append(f"Fact {index} — Problem: uses unknown source ID(s): {', '.join(unknown)}. Required fix: use only exact supplied source IDs.")
        if len(case_row_ids) != len(set(case_row_ids)):
            issues.append(f"Fact {index}.source_case_fact_ids — Problem: repeats an ID. Required fix: list each source ID once.")
        if len(diagnostic_row_ids) != len(set(diagnostic_row_ids)):
            issues.append(f"Fact {index}.source_diagnostic_ids — Problem: repeats an ID. Required fix: list each source ID once.")
    _raise_issues("report grounding", issues)


def runtime_cards(cards: list[dict]) -> tuple[list[dict], set[str]]:
    """Assign stable six-hex runtime tags to the cards visible to alignment."""
    rendered = []
    permitted = set()
    for index, card in enumerate(cards, 1):
        tag = f"{index:06x}"
        permitted.add(tag)
        rendered.append(dict(card, runtime_card_tag=f"[card:{tag}]"))
    return rendered, permitted


def validate_aligned(document: dict, grounded: dict, *, permitted_card_tags: set[str]) -> None:
    """Ensure evidence alignment adds only permitted citation dispositions."""
    rows, issues = _validate_immutable_rows(document, grounded, aligned=True)
    grounded_rows = grounded["facts"]
    protected = ("reason", "source_case_fact_ids", "source_diagnostic_ids")
    for index, (row, source) in enumerate(zip(rows, grounded_rows), 1):
        if not isinstance(row, dict) or not {"reason", "source_case_fact_ids", "source_diagnostic_ids", "citation"} <= set(row):
            continue
        for key in protected:
            if row[key] != source[key]:
                issues.append(f"Fact {index}.{key} — Problem: changed protected grounding content. Required fix: copy it character-for-character.")
        citation = row["citation"]
        if citation is None:
            continue
        if not isinstance(citation, str) or CARD_TAGS_RE.fullmatch(citation) is None:
            issues.append(
                f"Fact {index}.citation — Problem: invalid syntax {citation!r}. Required fix: use null or adjacent exact tags such as [card:000001][card:000002]."
            )
            continue
        tags = CARD_TAG_RE.findall(citation)
        unknown = sorted(set(tags) - permitted_card_tags)
        if unknown:
            issues.append(f"Fact {index}.citation — Problem: uses unpermitted tag(s): {', '.join(unknown)}. Required fix: use only supplied runtime tags or null.")
        if len(tags) != len(set(tags)):
            issues.append(f"Fact {index}.citation — Problem: repeats a card tag. Required fix: include each permitted tag once.")
    _raise_issues("report evidence alignment", issues)


def render_report(aligned: dict) -> str:
    """Render immutable report sentences with their aligned runtime citations."""
    lines = [HEADING]
    for row in aligned["facts"]:
        suffix = f" {row['citation']}" if row["citation"] else ""
        lines.append(row["fact"] + suffix)
    return "\n".join(lines) + "\n"