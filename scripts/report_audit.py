#!/usr/bin/env python3
"""Validate merged Step 6A analysis and deterministically render report-draft.md.

The model answers every reporting rule and assigns short runtime ``card_tags`` in
one pass. This script enforces the complete rule checklist, explicit citation
state, and exact membership of every tag in ``evidence.json`` before rendering
marker-bearing Markdown for the formatting step.
"""

import argparse
import json
import re
import sys
from pathlib import Path


RULE_COUNTS = ((1, 13), (2, 8), (3, 11), (4, 11), (5, 9))
EXPECTED_RULE_IDS = tuple(
    f"R{section}.{rule}"
    for section, count in RULE_COUNTS
    for rule in range(1, count + 1)
)
CARD_TAG = re.compile(r"^[0-9a-f]{6}$")
CITATION_STATUSES = {"cited", "no_citation_required"}


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


def evidence_card_tags(evidence):
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
    tags = []
    for index, card in enumerate(cards):
        if not isinstance(card, dict):
            raise ValueError(f"evidence cards[{index}] must be an object")
        tag = card.get("card_tag")
        if not isinstance(tag, str) or CARD_TAG.fullmatch(tag) is None:
            raise ValueError(
                f"evidence cards[{index}].card_tag must be exactly six lowercase hex characters"
            )
        if "card_id" in card:
            raise ValueError(f"evidence cards[{index}] must not expose full card_id")
        tags.append(tag)
    if len(tags) != len(set(tags)):
        raise ValueError("evidence contains duplicate card_tag values")
    return set(tags)


def validate_analysis(payload, evidence):
    require_exact_keys(payload, {"schema_version", "answers"}, location="document")
    if payload["schema_version"] != "1.0":
        raise ValueError("document schema_version must be '1.0'")
    answers = payload["answers"]
    if not isinstance(answers, list):
        raise ValueError("document answers must be an array")
    if len(answers) != len(EXPECTED_RULE_IDS):
        raise ValueError(
            f"document must contain {len(EXPECTED_RULE_IDS)} answers; found {len(answers)}"
        )

    known_tags = evidence_card_tags(evidence)
    unknown = {}
    fields = {"rule_id", "text", "citation_status", "card_tags"}
    for index, (answer, expected_rule_id) in enumerate(
        zip(answers, EXPECTED_RULE_IDS), start=1
    ):
        location = f"answers[{index - 1}]"
        require_exact_keys(answer, fields, location=location)
        if answer["rule_id"] != expected_rule_id:
            raise ValueError(
                f"{location}.rule_id must be {expected_rule_id!r}; found {answer['rule_id']!r}"
            )
        text = answer["text"]
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"{location}.text must be a non-empty string")
        if text != text.strip():
            raise ValueError(f"{location}.text must not have leading or trailing whitespace")
        if "\n" in text or "\r" in text:
            raise ValueError(f"{location}.text must be one line")

        status = answer["citation_status"]
        if status not in CITATION_STATUSES:
            raise ValueError(
                f"{location}.citation_status must be 'cited' or 'no_citation_required'"
            )
        tags = answer["card_tags"]
        if not isinstance(tags, list) or any(
            not isinstance(tag, str) or CARD_TAG.fullmatch(tag) is None for tag in tags
        ):
            raise ValueError(
                f"{location}.card_tags must contain only six-character lowercase hex tags"
            )
        if len(tags) != len(set(tags)):
            raise ValueError(f"{location}.card_tags must not contain duplicates")
        if status == "cited" and not tags:
            raise ValueError(f"{location} marked cited but has no card_tags")
        if status == "no_citation_required" and tags:
            raise ValueError(
                f"{location} marked no_citation_required but contains card_tags"
            )
        for tag in tags:
            if tag not in known_tags:
                unknown.setdefault(tag, []).append(answer["rule_id"])

    if unknown:
        details = "; ".join(
            f"{tag} ({','.join(rule_ids)})" for tag, rule_ids in unknown.items()
        )
        raise ValueError(f"analysis cites unknown evidence card tag(s): {details}")
    return payload


def render_markdown(analysis):
    lines = []
    for answer in analysis["answers"]:
        markers = "".join(f"[card:{tag}]" for tag in answer["card_tags"])
        disposition = markers or "(no citation required)"
        lines.append(f"{answer['rule_id']} {answer['text']} {disposition}")
    return "\n".join(lines) + "\n"


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "render"):
        sub = subparsers.add_parser(name)
        sub.add_argument("--analysis", type=Path, required=True)
        sub.add_argument("--evidence", type=Path, required=True)
        if name == "render":
            sub.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        analysis = read_json(args.analysis)
        evidence = read_json(args.evidence)
        validate_analysis(analysis, evidence)
        if args.command == "render":
            write_text(args.output, render_markdown(analysis))
            output = args.output
        else:
            output = args.analysis
    except ValueError as exc:
        print(f"REPORT AUDIT {args.command.upper()} FAILED: {exc}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
