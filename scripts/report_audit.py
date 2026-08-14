#!/usr/bin/env python3
"""Validate the strict Markdown produced by Step 6A.

Step 6A writes one line per reporting rule directly to ``report-draft.md``.
Every line must end in either one or more exact runtime ``[card:xxxxxx]``
markers or the literal ``(no citation required)``. This script enforces the
complete rule checklist, the terminal citation disposition, and exact
membership of every cited tag in ``evidence.md``.
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
CARD_MARKER = re.compile(r"\[card:([0-9a-f]{6})\]")
TERMINAL_CITED = re.compile(r"(?:\[card:[0-9a-f]{6}\])+")
NO_CITATION = "(no citation required)"


def read_text(path):
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc


def evidence_card_tags(evidence_text):
    """Return runtime card tags exposed by evidence.md."""
    tags = CARD_MARKER.findall(evidence_text)
    if not tags:
        raise ValueError("evidence.md contains no runtime card tags")
    return set(tags)


def split_draft_line(line, *, expected_rule_id, line_number):
    """Return ``(text, tags)`` for one strict Step 6A Markdown line."""
    prefix = f"{expected_rule_id} "
    if not line.startswith(prefix):
        found = line.split(" ", 1)[0] if line else "<blank>"
        raise ValueError(
            f"line {line_number} must begin with {expected_rule_id!r}; found {found!r}"
        )

    content = line[len(prefix) :]
    if content.endswith(NO_CITATION):
        separator = content[: -len(NO_CITATION)]
        if not separator.endswith(" "):
            raise ValueError(
                f"{expected_rule_id} must have one space before its citation disposition"
            )
        text = separator[:-1]
        tags = []
    else:
        match = re.search(r"((?:\[card:[0-9a-f]{6}\])+)$", content)
        if match is None:
            raise ValueError(
                f"{expected_rule_id} has no valid terminal citation disposition"
            )
        if match.start() == 0 or content[match.start() - 1] != " ":
            raise ValueError(
                f"{expected_rule_id} must have one space before its citation disposition"
            )
        text = content[: match.start() - 1]
        marker_block = match.group(1)
        if TERMINAL_CITED.fullmatch(marker_block) is None:
            raise ValueError(f"{expected_rule_id} has malformed terminal card tags")
        tags = CARD_MARKER.findall(marker_block)

    if not text:
        raise ValueError(f"{expected_rule_id} answer text must be non-empty")
    if text != text.strip():
        raise ValueError(
            f"{expected_rule_id} answer text must not have leading or trailing whitespace"
        )
    if "[card:" in text or NO_CITATION in text:
        raise ValueError(
            f"{expected_rule_id} contains a citation marker inside answer prose; markers are terminal only"
        )
    if len(tags) != len(set(tags)):
        raise ValueError(f"{expected_rule_id} terminal card tags must not contain duplicates")
    if any(CARD_TAG.fullmatch(tag) is None for tag in tags):
        raise ValueError(
            f"{expected_rule_id} card tags must be six-character lowercase hex strings"
        )
    return text, tags


def validate_draft(draft_text, evidence_text):
    """Validate strict Step 6A Markdown and return parsed rule records."""
    lines = draft_text.splitlines()
    if len(lines) != len(EXPECTED_RULE_IDS):
        raise ValueError(
            f"report-draft.md must contain exactly {len(EXPECTED_RULE_IDS)} lines; found {len(lines)}"
        )

    known_tags = evidence_card_tags(evidence_text)
    unknown = {}
    parsed = []
    for line_number, (line, expected_rule_id) in enumerate(
        zip(lines, EXPECTED_RULE_IDS), start=1
    ):
        text, tags = split_draft_line(
            line, expected_rule_id=expected_rule_id, line_number=line_number
        )
        for tag in tags:
            if tag not in known_tags:
                unknown.setdefault(tag, []).append(expected_rule_id)
        parsed.append(
            {
                "rule_id": expected_rule_id,
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
    args = parser.parse_args()

    try:
        draft_text = read_text(args.draft)
        evidence_text = read_text(args.evidence)
        validate_draft(draft_text, evidence_text)
    except ValueError as exc:
        print(f"REPORT AUDIT VALIDATE FAILED: {exc}", file=sys.stderr)
        return 1
    print(args.draft)
    return 0


if __name__ == "__main__":
    sys.exit(main())
