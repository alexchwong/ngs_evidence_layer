"""Structured YAML report drafting and deterministic rendering for diagnosis-first-v1."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
from scripts.core import citations as report_citations
from workflows.diagnosis_first_v1 import audit_policy as report_audit

SCHEMA_VERSION = 1
NO_CITATION = "(no citation required)"
CARD_DISPOSITION = re.compile(r"(?:\[card:[0-9a-f]{6}\])+")
CARD_MARKER = re.compile(r"\[card:([0-9a-f]{6})\]")
SUMMARY_SECTIONS = (
    "detected_variants",
    "diagnosis",
    "prognosis",
    "treatment",
    "mrd",
    "germline",
)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc


def _load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(_read(path))
    except yaml.YAMLError as exc:
        raise ValueError(f"{path.name} is invalid YAML: {exc}") from exc


class _TemplateSafeDumper(yaml.SafeDumper):
    """Safe YAML dumper that keeps model-editable empty/sentinel scalars explicit."""


def _represent_template_string(dumper: yaml.SafeDumper, value: str) -> yaml.nodes.ScalarNode:
    style = '"' if value in {"", NO_CITATION} else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_TemplateSafeDumper.add_representer(str, _represent_template_string)


def _write_yaml(path: Path, document: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(
            document,
            Dumper=_TemplateSafeDumper,
            sort_keys=False,
            allow_unicode=True,
            width=100,
        ),
        encoding="utf-8",
    )
    return path


def _normalise_omit(value: Any, *, rule_id: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalised = value.strip().lower()
        if normalised in {"yes", "true"}:
            return True
        if normalised in {"no", "false"}:
            return False
    raise ValueError(
        f"{rule_id} field 'omit' must be True/False or Yes/No. "
        "Set omit: false (or No) for reportable content and omit: true (or Yes) for content "
        "that must not enter report-draft.yaml."
    )


def _citation_tags(value: Any, *, context: str) -> tuple[str, list[str]]:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{context} field 'citation' is blank. Use exact runtime card marker(s), e.g. "
            "'[card:a1b2c3]', or '(no citation required)'."
        )
    citation = value.strip()
    if citation == NO_CITATION:
        return citation, []
    if CARD_DISPOSITION.fullmatch(citation) is None:
        raise ValueError(
            f"{context} has invalid citation {citation!r}. Use only adjacent exact runtime card "
            "markers such as '[card:a1b2c3][card:d4e5f6]' or '(no citation required)'."
        )
    tags = CARD_MARKER.findall(citation)
    if len(tags) != len(set(tags)):
        raise ValueError(f"{context} citation contains duplicate runtime card markers; keep each tag once.")
    return citation, tags


def _statement(statement: Any, *, context: str, known_tags: set[str]) -> dict[str, str]:
    if not isinstance(statement, dict):
        raise ValueError(f"{context} must be a YAML mapping with exactly 'text' and 'citation' fields.")
    if set(statement) != {"text", "citation"}:
        raise ValueError(
            f"{context} must contain exactly 'text' and 'citation'; found: "
            + ", ".join(sorted(map(str, statement)))
        )
    text = statement.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"{context} field 'text' is blank. Write one atomic patient-level assertion.")
    text = text.strip()
    if CARD_MARKER.search(text) or NO_CITATION in text:
        raise ValueError(
            f"{context} embeds citation syntax inside 'text'. Remove it from the prose and put the "
            "citation disposition only in the separate 'citation' field."
        )
    citation, tags = _citation_tags(statement.get("citation"), context=context)
    unknown = [tag for tag in tags if tag not in known_tags]
    if unknown:
        raise ValueError(
            f"{context} cites unknown runtime card tag(s): {', '.join(unknown)}. Copy replacement "
            "tag(s) only from the evidence file permitted for this model step."
        )
    return {"text": text, "citation": citation}


def write_rule_template(rules_path: Path, output: Path, *, include_refined_cmc: bool) -> Path:
    specs = report_audit.agreed_rule_specs(_read(rules_path))
    rules = []
    for spec in specs:
        constraints = spec.get("constraints") or {}
        required_classification = constraints.get("classification")
        required_citation = constraints.get("citation")
        omit: bool | None = None
        if required_classification == "REPORT":
            omit = False
        elif required_classification == "OMIT":
            omit = True
        citation = NO_CITATION if required_citation == "no_citation_required" else ""
        rules.append(
            {
                "id": spec["rule_id"],
                "omit": omit,
                "statements": [{"text": "", "citation": citation}],
            }
        )
    document: dict[str, Any] = {"schema_version": SCHEMA_VERSION}
    if include_refined_cmc:
        document["refined_cmc"] = None
    document["rules"] = rules
    return _write_yaml(output, document)


def validate_rule_document(
    path: Path,
    evidence_path: Path,
    rules_path: Path,
    *,
    require_refined_cmc: bool,
    valid_cmcs: set[str] | None = None,
) -> dict[str, Any]:
    document = _load_yaml(path)
    if not isinstance(document, dict):
        raise ValueError(f"{path.name} root must be a YAML mapping.")
    allowed_root = {"schema_version", "rules"} | ({"refined_cmc"} if require_refined_cmc else set())
    extra = set(document) - allowed_root
    missing = allowed_root - set(document)
    if extra or missing:
        details = []
        if missing:
            details.append("missing field(s): " + ", ".join(sorted(missing)))
        if extra:
            details.append("unexpected field(s): " + ", ".join(sorted(extra)))
        raise ValueError(f"{path.name} root structure is invalid: " + "; ".join(details))
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"{path.name} schema_version must be {SCHEMA_VERSION}.")

    specs = report_audit.agreed_rule_specs(_read(rules_path))
    expected_ids = [spec["rule_id"] for spec in specs]
    rows = document.get("rules")
    if not isinstance(rows, list):
        raise ValueError(f"{path.name} field 'rules' must be a YAML list.")
    found_ids = [row.get("id") if isinstance(row, dict) else None for row in rows]
    if found_ids != expected_ids:
        missing_ids = [rule_id for rule_id in expected_ids if rule_id not in found_ids]
        unexpected = [rule_id for rule_id in found_ids if rule_id not in expected_ids]
        duplicates = sorted({rule_id for rule_id in found_ids if rule_id and found_ids.count(rule_id) > 1})
        details = []
        if missing_ids:
            details.append("missing rule(s): " + ", ".join(missing_ids))
        if unexpected:
            details.append("unexpected rule(s): " + ", ".join(map(str, unexpected)))
        if duplicates:
            details.append("duplicate rule(s): " + ", ".join(duplicates))
        if not details:
            details.append("rules are out of canonical order")
        raise ValueError(
            f"{path.name} rule sequence is invalid: " + "; ".join(details)
            + ". Restore the deterministic template rule IDs and order; edit values only."
        )

    known_tags = report_audit.evidence_card_tags(_read(evidence_path), allow_empty=True)
    normalised_rules = []
    for row, spec in zip(rows, specs):
        rule_id = spec["rule_id"]
        if not isinstance(row, dict):
            raise ValueError(f"{rule_id} must be a YAML mapping.")
        if set(row) != {"id", "omit", "statements"}:
            raise ValueError(
                f"{rule_id} must contain exactly 'id', 'omit', and 'statements'; found: "
                + ", ".join(sorted(map(str, row)))
            )
        omit = _normalise_omit(row.get("omit"), rule_id=rule_id)
        constraints = spec.get("constraints") or {}
        required_classification = constraints.get("classification")
        if required_classification == "REPORT" and omit:
            raise ValueError(f"{rule_id} is canonically mandatory REPORT content; set omit: false (or No).")
        if required_classification == "OMIT" and not omit:
            raise ValueError(f"{rule_id} is canonically mandatory OMIT content; set omit: true (or Yes).")

        statements = row.get("statements")
        if not isinstance(statements, list) or not statements:
            raise ValueError(
                f"{rule_id} must contain at least one statement even when omit is true. "
                "Address the rule in one or more atomic statements; omission only controls downstream inclusion."
            )
        parsed_statements = [
            _statement(statement, context=f"{rule_id} statement {index}", known_tags=known_tags)
            for index, statement in enumerate(statements, start=1)
        ]
        required_citation = constraints.get("citation")
        if required_citation == "no_citation_required":
            bad = [s for s in parsed_statements if s["citation"] != NO_CITATION]
            if bad:
                raise ValueError(
                    f"{rule_id} must use '{NO_CITATION}' for every statement as declared by the canonical rule."
                )
        elif required_citation not in {None, "no_citation_required"}:
            raise ValueError(f"{rule_id} has unsupported canonical citation constraint {required_citation!r}.")

        if not omit:
            for index, statement in enumerate(parsed_statements, start=1):
                prose = statement["text"]
                if rule_id != "R0.1" and report_audit.NON_REPORTABLE_SENTENCE_START.search(prose):
                    raise ValueError(
                        f"{rule_id} statement {index} is retained (omit: false) but begins with a generic "
                        "'No ...' or 'Not applicable ...' outcome. Under the reporting policy, set omit: true "
                        "unless the absence itself materially changes the patient-level interpretation; if it does, "
                        "rewrite the retained statement to lead with that clinical effect."
                    )
                meta = report_audit.REPORT_META_PREFIX.match(prose) or report_audit.REPORT_META_ANYWHERE.search(prose)
                if meta:
                    raise ValueError(
                        f"{rule_id} statement {index} is retained but contains report-construction meta-language "
                        f"{meta.group(0)!r}. Write direct patient-level clinical prose or set omit: true."
                    )
        normalised_rules.append({"id": rule_id, "omit": omit, "statements": parsed_statements})

    result: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "rules": normalised_rules}
    if require_refined_cmc:
        refined = document.get("refined_cmc")
        if not isinstance(refined, str) or not refined.strip():
            raise ValueError(
                f"{path.name} field 'refined_cmc' is blank. Replace it with exactly one canonical case-major category."
            )
        refined = refined.strip()
        if valid_cmcs is not None and refined not in valid_cmcs:
            raise ValueError(
                f"refined_cmc value {refined!r} is not canonical. Replace it with exactly one value from "
                "case-major-categories.json."
            )
        result["refined_cmc"] = refined
    return result


def write_report_draft(
    rules: list[dict[str, Any]],
    output: Path,
) -> Path:
    retained = [rule for rule in rules if not rule["omit"]]
    document = {"schema_version": SCHEMA_VERSION, "rules": retained}
    return _write_yaml(output, document)


def write_summary_template(output: Path) -> Path:
    document: dict[str, Any] = {"schema_version": SCHEMA_VERSION}
    for section in SUMMARY_SECTIONS:
        document[section] = {"statements": [{"text": "", "citation": ""}]}
    return _write_yaml(output, document)


def _retained_citation_scope(
    report_draft_path: Path,
) -> tuple[set[str], set[frozenset[str]], bool]:
    document = _load_yaml(report_draft_path)
    if not isinstance(document, dict) or not isinstance(document.get("rules"), list):
        raise ValueError("report-draft.yaml is invalid; rerun deterministic Step 6A assembly.")
    tags: set[str] = set()
    citation_sets: set[frozenset[str]] = set()
    allow_no_citation = False
    for rule in document["rules"]:
        if not isinstance(rule, dict):
            raise ValueError("report-draft.yaml contains a malformed retained rule; rerun Step 6A.")
        if rule.get("omit") is not False:
            raise ValueError("report-draft.yaml contains an omitted rule; rerun Step 6A deterministic filtering.")
        for statement in rule.get("statements") or []:
            citation = statement.get("citation") if isinstance(statement, dict) else None
            if citation == NO_CITATION:
                allow_no_citation = True
            elif isinstance(citation, str):
                statement_tags = frozenset(CARD_MARKER.findall(citation))
                if statement_tags:
                    citation_sets.add(statement_tags)
                    tags.update(statement_tags)
    return tags, citation_sets, allow_no_citation


def _is_union_of_source_citations(target: set[str], source_sets: set[frozenset[str]]) -> bool:
    if not target:
        return False
    usable = [source for source in source_sets if source.issubset(target)]
    if not usable:
        return False
    represented: set[str] = set()
    for source in usable:
        represented.update(source)
    return represented == target


def validate_summary(summary_path: Path, report_draft_path: Path) -> dict[str, list[dict[str, str]]]:
    document = _load_yaml(summary_path)
    if not isinstance(document, dict):
        raise ValueError("report-summary.yaml root must be a YAML mapping.")
    expected_keys = {"schema_version", *SUMMARY_SECTIONS}
    if set(document) != expected_keys:
        missing = expected_keys - set(document)
        extra = set(document) - expected_keys
        details = []
        if missing:
            details.append("missing section(s): " + ", ".join(sorted(missing)))
        if extra:
            details.append("unexpected section(s): " + ", ".join(sorted(extra)))
        raise ValueError(
            "report-summary.yaml structure is invalid: " + "; ".join(details)
            + ". Preserve the deterministic template section names."
        )
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"report-summary.yaml schema_version must be {SCHEMA_VERSION}.")

    allowed_tags, source_citation_sets, allow_no_citation = _retained_citation_scope(report_draft_path)
    parsed: dict[str, list[dict[str, str]]] = {}
    for section in SUMMARY_SECTIONS:
        node = document.get(section)
        if not isinstance(node, dict) or set(node) != {"statements"}:
            raise ValueError(f"report-summary.yaml section {section!r} must contain only a 'statements' list.")
        statements = node.get("statements")
        if not isinstance(statements, list):
            raise ValueError(f"report-summary.yaml section {section!r} field 'statements' must be a list.")
        section_statements: list[dict[str, str]] = []
        for index, statement in enumerate(statements, start=1):
            if not isinstance(statement, dict) or set(statement) != {"text", "citation"}:
                raise ValueError(
                    f"{section} statement {index} must contain exactly 'text' and 'citation'."
                )
            text = statement.get("text")
            citation = statement.get("citation")
            if text in {None, ""} and citation in {None, ""}:
                continue
            parsed_statement = _statement(
                statement,
                context=f"{section} statement {index}",
                known_tags=allowed_tags,
            )
            if parsed_statement["citation"] == NO_CITATION:
                if not allow_no_citation:
                    raise ValueError(
                        f"{section} statement {index} uses '{NO_CITATION}', but no retained source statement "
                        "in report-draft.yaml has that disposition."
                    )
            else:
                summary_tags = set(CARD_MARKER.findall(parsed_statement["citation"]))
                if not _is_union_of_source_citations(summary_tags, source_citation_sets):
                    raise ValueError(
                        f"{section} statement {index} citation {parsed_statement['citation']!r} is not an exact "
                        "union of retained source-statement citation sets from report-draft.yaml. Preserve each "
                        "source statement's complete citation set when merging or splitting facts; do not drop "
                        "one marker from a multi-card source citation."
                    )
            if not parsed_statement["text"].endswith("."):
                raise ValueError(
                    f"{section} statement {index} must be a complete sentence ending in a full stop."
                )
            section_statements.append(parsed_statement)
        parsed[section] = section_statements

    return parsed


def render_summary(
    summary_path: Path,
    report_draft_path: Path,
    evidence_path: Path,
    card_tags_path: Path,
    output: Path,
) -> Path:
    sections = validate_summary(summary_path, report_draft_path)
    paragraphs = []
    for section in SUMMARY_SECTIONS:
        statements = sections[section]
        if not statements:
            continue
        paragraphs.append(" ".join(f"{item['text']} {item['citation']}" for item in statements))
    model_facing = "\n\n".join(paragraphs).rstrip() + "\n"
    try:
        rendered = report_citations.render(
            model_facing,
            _read(evidence_path),
            _read(card_tags_path),
            require_citation_after_full_stop=False,
        )
    except ValueError as exc:
        detail = str(exc).replace("report-draft.md", "report-summary.yaml citation field")
        detail = detail.replace("report-final.md", "report-summary.yaml")
        raise ValueError(
            "report-summary.yaml passed structural checks but cannot be deterministically rendered: "
            + detail
            + " Repair only the affected Step-6B summary statement or rerun the upstream deterministic "
              "evidence/card-tag stage when the error identifies an evidence/card-tag artifact problem."
        ) from exc
    report_citations.atomic_write(output, rendered)
    return output


def read_refined_cmc(path: Path, valid_cmcs: set[str]) -> str:
    document = _load_yaml(path)
    if not isinstance(document, dict):
        raise ValueError(f"{path.name} root must be a YAML mapping.")
    refined = document.get("refined_cmc")
    if not isinstance(refined, str) or not refined.strip():
        raise ValueError(f"{path.name} field 'refined_cmc' is blank or missing.")
    refined = refined.strip()
    if refined not in valid_cmcs:
        raise ValueError(
            f"refined_cmc value {refined!r} is not canonical. Replace it with exactly one value from "
            "case-major-categories.json."
        )
    return refined
