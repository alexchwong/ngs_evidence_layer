"""Validate the strict Markdown produced by Step 6A.

Step 6A writes one line per reporting rule directly to ``report-draft.md``.
Every line must explicitly classify its rule outcome as ``REPORT:`` or
``OMIT:``, then end in a full stop, one space, and either one or more exact
runtime ``[card:xxxxxx]`` markers or the literal ``(no citation required)``.
For example: ``R1.1 REPORT: Conclusion. [card:a1b2c3]``. This script enforces
the complete rule checklist, classification grammar, obvious report-construction
meta-language leakage, terminal citation disposition, and exact membership of
every cited tag in ``evidence.md``.
"""

import argparse
import re
import sys
from pathlib import Path


RULE_COUNTS = ((1, 13), (2, 8), (3, 11), (4, 11), (5, 9))
EXPECTED_RULE_IDS = tuple(
    f"R{section}.{rule}"
    for section, count in RULE_COUNTS
    for rule in range(1, count + 1)
)
CARD_TAG = re.compile(r"[0-9a-f]{6}")
RULE_ID = re.compile(r"R\d+\.\d+")
RULE_SECTION = re.compile(r"^# R(\d+)\b")
RULE_ITEM = re.compile(r"^(\d+)\.\s")
AUDIT_DIRECTIVE = re.compile(r"^<!--\s*report-audit:\s*(.*?)\s*-->$")
CARD_MARKER = re.compile(r"\[card:([0-9a-f]{6})\]")
TERMINAL_CITED = re.compile(r"(?:\[card:[0-9a-f]{6}\])+")
NO_CITATION = "(no citation required)"
CLASSIFICATIONS = ("REPORT", "OMIT")
REPORT_META_PREFIX = re.compile(
    r"(?:the\s+final\s+report\s+should\b|final\s+report\s+should\b|"
    r"report\b|omit\b|do\s+not\s+(?:mention|report|state|discuss)\b|"
    r"commentary\s+(?:is|should\s+be)\s+not\s+warranted\b)",
    re.IGNORECASE,
)
NON_REPORTABLE_SENTENCE_START = re.compile(r"(?:^|(?<=[.!?])\s+)(No\b|Not applicable\b)", re.IGNORECASE)
REPORT_META_ANYWHERE = re.compile(
    r"\b(?:should|must)\s+be\s+omitted\b|"
    r"\bshould\s+not\s+be\s+(?:mentioned|reported|discussed)\b",
    re.IGNORECASE,
)


def read_text(path):
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc


def evidence_card_tags(evidence_text, *, allow_empty=False):
    """Return runtime card tags exposed by evidence.md."""
    tags = CARD_MARKER.findall(evidence_text)
    if not tags and not allow_empty:
        raise ValueError("evidence.md contains no runtime card tags")
    return set(tags)


def agreed_rule_specs(rules_text):
    """Return canonical rule IDs and optional audit constraints from agreed rules."""
    specs = []
    current_section = None
    current_spec = None
    seen = set()

    for line_number, line in enumerate(rules_text.splitlines(), start=1):
        section_match = RULE_SECTION.match(line)
        if section_match:
            current_section = int(section_match.group(1))
            current_spec = None
            continue
        if line.startswith("# "):
            current_section = None
            current_spec = None
            continue

        if current_section is not None:
            item_match = RULE_ITEM.match(line)
            if item_match:
                rule_id = f"R{current_section}.{int(item_match.group(1))}"
                if rule_id in seen:
                    raise ValueError(
                        f"agreed_reporting_rules.md contains duplicate rule ID {rule_id} "
                        f"at line {line_number}"
                    )
                current_spec = {"rule_id": rule_id, "constraints": {}}
                specs.append(current_spec)
                seen.add(rule_id)
                continue

            directive_match = AUDIT_DIRECTIVE.match(line.strip())
            if directive_match:
                if current_spec is None:
                    raise ValueError(
                        "agreed_reporting_rules.md has a report-audit directive without "
                        f"a preceding rule at line {line_number}"
                    )
                for field in directive_match.group(1).split(";"):
                    field = field.strip()
                    if not field:
                        continue
                    if "=" not in field:
                        raise ValueError(
                            "malformed report-audit directive in agreed_reporting_rules.md "
                            f"at line {line_number}: {field!r}"
                        )
                    key, value = (part.strip() for part in field.split("=", 1))
                    if key not in {"classification", "citation"}:
                        raise ValueError(
                            "unknown report-audit directive key in agreed_reporting_rules.md "
                            f"at line {line_number}: {key!r}"
                        )
                    current_spec["constraints"][key] = value

    if not specs:
        raise ValueError("agreed_reporting_rules.md contains no reporting rules")
    return specs


def split_draft_line(line, *, expected_rule_id, line_number):
    """Return ``(classification, text, tags)`` for one strict Step 6A line."""
    prefix = f"{expected_rule_id} "
    if not line.startswith(prefix):
        found = line.split(" ", 1)[0] if line else "<blank>"
        raise ValueError(
            f"line {line_number} must begin with {expected_rule_id!r}; found {found!r}"
        )

    content = line[len(prefix) :]
    class_match = re.match(r"(REPORT|OMIT): ", content)
    if class_match is None:
        found = content.split(" ", 1)[0] if content else "<missing>"
        raise ValueError(
            f"{expected_rule_id} must classify the rule immediately after the rule ID. "
            "Expected exactly 'REPORT:' for reportable clinical content or 'OMIT:' for "
            "a topic that must not appear in the final report, followed by one space. "
            f"Found {found!r}. Rewrite the line as either "
            f"'{expected_rule_id} REPORT: <report-ready conclusion>. <citation disposition>' "
            f"or '{expected_rule_id} OMIT: <topic to suppress>. <citation disposition>'."
        )
    classification = class_match.group(1)
    content = content[class_match.end() :]

    if content.endswith(NO_CITATION):
        separator = content[: -len(NO_CITATION)]
        if not separator.endswith(" "):
            raise ValueError(
                f"{expected_rule_id} citation disposition must be separated from the answer by exactly one space. "
                "Expected '<conclusion>. [card:a1b2c3]' or '<conclusion>. (no citation required)'. "
                "Keep exactly one terminal citation disposition at the end of the rule line."
            )
        text = separator[:-1]
        tags = []
    else:
        match = re.search(r"((?:\[card:[0-9a-f]{6}\])+)$", content)
        if match is None:
            raise ValueError(
                f"{expected_rule_id} has no valid terminal citation disposition. "
                "Expected exactly: '<conclusion>. [card:a1b2c3]' (or adjacent card tags), "
                "or '<conclusion>. (no citation required)'. The citation disposition must "
                "follow the full stop; do not write '<conclusion> [card:a1b2c3].'"
            )
        if match.start() == 0 or content[match.start() - 1] != " ":
            raise ValueError(
                f"{expected_rule_id} citation disposition must be separated from the answer by exactly one space. "
                "Expected '<conclusion>. [card:a1b2c3]' (or adjacent card tags). "
                "Keep all directly supporting card tags together in this one terminal citation disposition."
            )
        text = content[: match.start() - 1]
        marker_block = match.group(1)
        if TERMINAL_CITED.fullmatch(marker_block) is None:
            raise ValueError(f"{expected_rule_id} has malformed terminal card tags")
        tags = CARD_MARKER.findall(marker_block)

    if not text:
        raise ValueError(f"{expected_rule_id} answer text must be non-empty after {classification}:")
    if not text.endswith("."):
        raise ValueError(
            f"{expected_rule_id} citation disposition is misplaced. Expected exactly: "
            "'<conclusion>. [card:a1b2c3]' (or adjacent card tags), or "
            "'<conclusion>. (no citation required)'. The full stop must come before the "
            "citation disposition."
        )
    if text != text.strip():
        raise ValueError(
            f"{expected_rule_id} answer text must not have leading or trailing whitespace"
        )
    if "[card:" in text or NO_CITATION in text:
        raise ValueError(
            f"{expected_rule_id} contains a citation marker inside answer prose. Rule-draft citations are terminal only: "
            "remove every internal [card:...] or (no citation required) marker, preserve the answer prose, then place "
            "exactly one citation disposition after the final full stop. If different cards support different clauses "
            "or sentences, put the union of every directly supporting card tag there, e.g. "
            "'<conclusion>. [card:a1b2c3][card:d4e5f6]'."
        )
    if len(tags) != len(set(tags)):
        raise ValueError(
            f"{expected_rule_id} terminal card tags must not contain duplicates. "
            "Keep each supporting tag once, after the full stop, e.g. "
            "'<conclusion>. [card:a1b2c3][card:d4e5f6]'"
        )
    if any(CARD_TAG.fullmatch(tag) is None for tag in tags):
        raise ValueError(
            f"{expected_rule_id} card tags must be six-character lowercase hex strings"
        )

    if classification == "REPORT":
        prose = text[:-1].strip()
        non_reportable = NON_REPORTABLE_SENTENCE_START.search(prose)
        if expected_rule_id != "R0.1" and non_reportable:
            phrase = non_reportable.group(1)
            raise ValueError(
                f"{expected_rule_id} is classified REPORT but contains a sentence beginning "
                f"{phrase!r}. Under prompts/workflow/reporting_rule_policy.md, generic "
                "'No ...' and 'Not applicable ...' outcomes must be classified OMIT, except "
                "for mandatory R0.1. If an absent finding is itself clinically material, "
                "rewrite the REPORT line to lead with its patient-level clinical effect rather "
                "than a generic absence sentence; otherwise change the line to "
                f"'{expected_rule_id} OMIT: <non-reportable outcome>. <citation disposition>'."
            )
        meta = REPORT_META_PREFIX.match(prose) or REPORT_META_ANYWHERE.search(prose)
        if meta:
            phrase = meta.group(0)
            raise ValueError(
                f"{expected_rule_id} is classified REPORT but contains report-construction "
                f"meta-language {phrase!r}. REPORT text must be direct, report-ready clinical "
                "prose. If the rule means the topic should be absent from the final report, "
                f"rewrite it as '{expected_rule_id} OMIT: <topic to suppress>. <citation disposition>'. "
                "If the negative finding itself is clinically reportable, keep REPORT but rewrite "
                "the sentence as the clinical finding rather than an instruction to the formatter."
            )

    return classification, text, tags


def validate_draft(
    draft_text, evidence_text, rules_text=None, *, allow_no_evidence_tags=False
):
    """Validate strict Step 6A Markdown and return parsed rule records."""
    lines = draft_text.splitlines()
    if rules_text is None:
        rule_specs = [
            {"rule_id": rule_id, "constraints": {}}
            for rule_id in EXPECTED_RULE_IDS
        ]
    else:
        rule_specs = agreed_rule_specs(rules_text)
    expected_rule_ids = tuple(spec["rule_id"] for spec in rule_specs)

    # Diagnose rule-sequence defects before enforcing the line count. This gives the
    # model enough information to repair report-draft.md without inspecting code.
    found_rows = []
    unlabelled = []
    for line_number, line in enumerate(lines, start=1):
        first_token = line.split(" ", 1)[0] if line else ""
        if RULE_ID.fullmatch(first_token):
            found_rows.append((line_number, first_token))
        else:
            unlabelled.append((line_number, line))

    found_ids = [rule_id for _, rule_id in found_rows]
    missing = [rule_id for rule_id in expected_rule_ids if rule_id not in found_ids]
    unknown = [(line_number, rule_id) for line_number, rule_id in found_rows if rule_id not in expected_rule_ids]
    duplicates = {}
    for line_number, rule_id in found_rows:
        if found_ids.count(rule_id) > 1:
            duplicates.setdefault(rule_id, []).append(line_number)

    structural = []
    if missing:
        structural.append("missing rule line(s): " + ", ".join(missing))
    if unknown:
        structural.append(
            "non-existent rule ID(s): "
            + ", ".join(f"line {line_number}={rule_id}" for line_number, rule_id in unknown)
        )
    if duplicates:
        structural.append(
            "duplicate rule ID(s): "
            + "; ".join(
                f"{rule_id} on lines {','.join(map(str, line_numbers))}"
                for rule_id, line_numbers in duplicates.items()
            )
        )
    if unlabelled:
        structural.append(
            "line(s) without a valid rule ID: "
            + "; ".join(
                f"line {line_number}={line!r}" for line_number, line in unlabelled
            )
        )

    if not structural and found_ids != list(expected_rule_ids):
        mismatches = []
        for position, (actual, expected) in enumerate(zip(found_ids, expected_rule_ids), start=1):
            if actual != expected:
                line_number = found_rows[position - 1][0]
                mismatches.append(
                    f"line {line_number} has {actual}; expected {expected}"
                )
        structural.append("rule lines are out of order: " + "; ".join(mismatches))

    if structural or len(lines) != len(expected_rule_ids):
        if len(lines) != len(expected_rule_ids):
            structural.append(
                f"line count is {len(lines)} but must be {len(expected_rule_ids)} after repair"
            )
        raise ValueError(
            "report-draft.md rule sequence is invalid. "
            + " | ".join(structural)
            + ". Fix only these rule-line defects: there must be exactly one line for each "
              "rule declared in agreed_reporting_rules.md, in canonical order, with no blank, "
              "heading, or extra lines."
        )

    known_tags = evidence_card_tags(
        evidence_text, allow_empty=allow_no_evidence_tags
    )
    unknown = {}
    parsed = []
    for line_number, (line, rule_spec) in enumerate(
        zip(lines, rule_specs), start=1
    ):
        expected_rule_id = rule_spec["rule_id"]
        classification, text, tags = split_draft_line(
            line, expected_rule_id=expected_rule_id, line_number=line_number
        )
        constraints = rule_spec["constraints"]
        required_classification = constraints.get("classification")
        if required_classification and classification != required_classification:
            raise ValueError(
                f"{expected_rule_id} must be classified {required_classification} as declared "
                "in agreed_reporting_rules.md"
            )
        required_citation = constraints.get("citation")
        if required_citation == "no_citation_required" and tags:
            raise ValueError(
                f"{expected_rule_id} must end with (no citation required) as declared in "
                "agreed_reporting_rules.md"
            )
        if required_citation not in {None, "no_citation_required"}:
            raise ValueError(
                f"{expected_rule_id} has unsupported citation constraint "
                f"{required_citation!r} in agreed_reporting_rules.md"
            )
        for tag in tags:
            if tag not in known_tags:
                unknown.setdefault(tag, []).append(expected_rule_id)
        parsed.append(
            {
                "rule_id": expected_rule_id,
                "classification": classification,
                "text": text,
                "card_tags": tags,
                "citation_status": "cited" if tags else "no_citation_required",
            }
        )

    if unknown:
        details = "; ".join(
            f"{tag} ({','.join(rule_ids)})" for tag, rule_ids in unknown.items()
        )
        raise ValueError(
            f"draft cites unknown evidence card tag(s): {details}. "
            "Repair affected rule(s) by copying replacement runtime tags from evidence.md only."
        )
    return parsed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--draft", type=Path, required=True)
    validate.add_argument("--evidence", type=Path, required=True)
    validate.add_argument(
        "--rules",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "rules" / "agreed_reporting_rules.md",
    )
    validate.add_argument(
        "--allow-no-evidence-tags",
        action="store_true",
        help="allow an evidence view with zero runtime tags when the draft cites no cards",
    )
    args = parser.parse_args()

    try:
        draft_text = read_text(args.draft)
        evidence_text = read_text(args.evidence)
        rules_text = read_text(args.rules)
        validate_draft(
            draft_text,
            evidence_text,
            rules_text,
            allow_no_evidence_tags=args.allow_no_evidence_tags,
        )
    except ValueError as exc:
        print(f"REPORT AUDIT VALIDATE FAILED: {exc}", file=sys.stderr)
        return 1
    print(args.draft)
    return 0


if __name__ == "__main__":
    sys.exit(main())
