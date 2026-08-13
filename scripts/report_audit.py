#!/usr/bin/env python3
"""Validate Step 6A JSON artifacts and render the audited Markdown draft.

The content pass writes ``report-content.json`` with rule IDs and text only.
The citation-audit pass copies those values unchanged into ``report-audit.json``
and adds only ``card_ids`` arrays. This script enforces that no-edit boundary,
checks card IDs against ``evidence.json``, and deterministically renders the
marker-bearing ``report-draft.md`` consumed by the existing formatting step.
"""

import argparse
import json
import sys
from pathlib import Path


RULE_COUNTS = ((1, 13), (2, 8), (3, 11), (4, 11), (5, 9))
EXPECTED_RULE_IDS = tuple(
    f"R{section}.{rule}"
    for section, count in RULE_COUNTS
    for rule in range(1, count + 1)
)


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON {path}: {exc}") from exc


def require_exact_keys(value, expected, *, location):
    if not isinstance(value, dict):
        raise ValueError(f"{location} must be an object")
    actual = set(value)
    expected = set(expected)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("unexpected " + ", ".join(extra))
        raise ValueError(f"{location} has invalid fields: {'; '.join(details)}")


def validate_answers(payload, *, audited):
    expected_fields = {"schema_version", "answers"}
    require_exact_keys(payload, expected_fields, location="document")
    if payload["schema_version"] != "1.0":
        raise ValueError("document schema_version must be '1.0'")
    answers = payload["answers"]
    if not isinstance(answers, list):
        raise ValueError("document answers must be an array")
    if len(answers) != len(EXPECTED_RULE_IDS):
        raise ValueError(
            f"document must contain {len(EXPECTED_RULE_IDS)} answers; found {len(answers)}"
        )

    answer_fields = {"rule_id", "text", "card_ids"} if audited else {"rule_id", "text"}
    for index, (answer, expected_rule_id) in enumerate(
        zip(answers, EXPECTED_RULE_IDS), start=1
    ):
        location = f"answers[{index - 1}]"
        require_exact_keys(answer, answer_fields, location=location)
        if answer["rule_id"] != expected_rule_id:
            raise ValueError(
                f"{location}.rule_id must be {expected_rule_id!r}; "
                f"found {answer['rule_id']!r}"
            )
        text = answer["text"]
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"{location}.text must be a non-empty string")
        if text != text.strip():
            raise ValueError(f"{location}.text must not have leading or trailing whitespace")
        if "\n" in text or "\r" in text:
            raise ValueError(f"{location}.text must be one line")
        if audited:
            card_ids = answer["card_ids"]
            if not isinstance(card_ids, list) or any(
                not isinstance(card_id, str) or not card_id
                for card_id in card_ids
            ):
                raise ValueError(f"{location}.card_ids must be an array of non-empty strings")
            if len(card_ids) != len(set(card_ids)):
                raise ValueError(f"{location}.card_ids must not contain duplicates")
    return answers


def evidence_card_ids(evidence):
    require_exact_keys(
        evidence,
        {"schema_version", "cards", "not_assessed", "suppressed", "provenance"},
        location="evidence",
    )
    if evidence["schema_version"] != "1.0":
        raise ValueError("evidence schema_version must be '1.0'")
    cards = evidence["cards"]
    if not isinstance(cards, list):
        raise ValueError("evidence cards must be an array")
    result = []
    for index, card in enumerate(cards):
        if not isinstance(card, dict):
            raise ValueError(f"evidence cards[{index}] must be an object")
        card_id = card.get("card_id")
        if not isinstance(card_id, str) or not card_id:
            raise ValueError(f"evidence cards[{index}].card_id must be a non-empty string")
        result.append(card_id)
    if len(result) != len(set(result)):
        raise ValueError("evidence contains duplicate card_id values")
    return set(result)


def validate_content(payload):
    validate_answers(payload, audited=False)
    return payload


def validate_audit(content, audit, evidence):
    content_answers = validate_answers(content, audited=False)
    audit_answers = validate_answers(audit, audited=True)
    known_cards = evidence_card_ids(evidence)
    unknown = {}
    for content_answer, audit_answer in zip(content_answers, audit_answers):
        rule_id = content_answer["rule_id"]
        if audit_answer["rule_id"] != rule_id:
            raise ValueError(f"citation audit changed rule_id {rule_id}")
        if audit_answer["text"] != content_answer["text"]:
            raise ValueError(f"citation audit changed text for {rule_id}")
        for card_id in audit_answer["card_ids"]:
            if card_id not in known_cards:
                unknown.setdefault(card_id, []).append(rule_id)
    if unknown:
        details = "; ".join(
            f"{card_id} ({','.join(rule_ids)})"
            for card_id, rule_ids in unknown.items()
        )
        raise ValueError(f"citation audit cites unknown evidence card(s): {details}")
    return audit


def render_markdown(audit):
    answers = validate_answers(audit, audited=True)
    lines = []
    for answer in answers:
        markers = "".join(f"[card:{card_id}]" for card_id in answer["card_ids"])
        disposition = markers or "(no citation required)"
        lines.append(f"{answer['rule_id']} {answer['text']} {disposition}")
    return "\n".join(lines) + "\n"


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    content_parser = subparsers.add_parser("validate-content")
    content_parser.add_argument("--content", type=Path, required=True)

    audit_parser = subparsers.add_parser("validate-audit")
    audit_parser.add_argument("--content", type=Path, required=True)
    audit_parser.add_argument("--audit", type=Path, required=True)
    audit_parser.add_argument("--evidence", type=Path, required=True)

    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("--content", type=Path, required=True)
    render_parser.add_argument("--audit", type=Path, required=True)
    render_parser.add_argument("--evidence", type=Path, required=True)
    render_parser.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    try:
        content = read_json(args.content)
        if args.command == "validate-content":
            validate_content(content)
            output = args.content
        else:
            audit = read_json(args.audit)
            evidence = read_json(args.evidence)
            validate_audit(content, audit, evidence)
            if args.command == "render":
                write_text(args.output, render_markdown(audit))
                output = args.output
            else:
                output = args.audit
    except ValueError as exc:
        print(f"REPORT AUDIT {args.command.upper()} FAILED: {exc}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())