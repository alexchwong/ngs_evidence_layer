#!/usr/bin/env python3
"""Validate and render citations in generated NGS reports.

``validate`` is a read-only Step 6A/6B exit check. It verifies that a report
document contains only well-formed card-ID markers that resolve through the
canonical ``## Refs`` mapping in ``block.md``.

``render`` is mandatory Step 6C processing. It replaces the card-ID markers in
``report-final.md`` with report-local Vancouver-style numeric citations in order
of first appearance and appends the cited primary references. Rendering replaces
its output atomically and fails without modifying it when validation fails.
"""

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path


REFERENCES_HEADING = "## References"
REFS_HEADING = "## Refs"
REFERENCE_START = re.compile(r"^(\d+)\.\s+(.+)$")
CARD_ID = r"[A-Za-z0-9][A-Za-z0-9._-]*"
REFS_MAPPING = re.compile(
    rf"^({CARD_ID}(?:,{CARD_ID})*): primary ref "
    r"([1-9]\d*(?:,[1-9]\d*)*)"
    r"(?:; secondary ref ([1-9]\d*(?:,[1-9]\d*)*))?$"
)
SOURCE_MARKER = re.compile(rf"\[card:({CARD_ID})\]")
CARD_MARKER_LIKE = re.compile(r"\[card:[^\[\]\n]*\]")
REPORT_MARKER = re.compile(r"\[([0-9]+(?:\s*,\s*[0-9]+)*)\]")
ADJACENT_REPORT_MARKERS = re.compile(r"(?:\[(?:[0-9]+(?:\s*,\s*[0-9]+)*)\]){2,}")
NO_CITATION_MARKER = re.compile(r"\s*\(no citation required\)")


def split_references(text, *, source):
    """Return body and a validated numbered Markdown bibliography."""
    lines = text.rstrip().splitlines()
    headings = [index for index, line in enumerate(lines) if line == REFERENCES_HEADING]
    if len(headings) != 1:
        raise ValueError(f"{source} must contain exactly one {REFERENCES_HEADING!r} heading")
    heading = headings[0]
    body = "\n".join(lines[:heading]).rstrip()
    bibliography_lines = lines[heading + 1:]
    while bibliography_lines and not bibliography_lines[0].strip():
        bibliography_lines.pop(0)

    references = {}
    current_number = None
    current_parts = []

    def store_current():
        if current_number is None:
            return
        display = " ".join(current_parts).strip()
        if not display:
            raise ValueError(f"{source} reference {current_number} is empty")
        references[current_number] = display

    for line in bibliography_lines:
        match = REFERENCE_START.match(line)
        if match:
            store_current()
            number = int(match.group(1))
            if number in references:
                raise ValueError(f"{source} contains duplicate reference {number}")
            current_number = number
            current_parts = [match.group(2).strip()]
        elif line.startswith("   ") and current_number is not None:
            current_parts.append(line.strip())
        elif not line.strip():
            continue
        else:
            raise ValueError(f"{source} has malformed bibliography line: {line!r}")
    store_current()
    if not references:
        raise ValueError(f"{source} bibliography contains no numbered references")
    expected = list(range(1, len(references) + 1))
    if list(references) != expected:
        raise ValueError(f"{source} bibliography must be consecutively numbered from 1")
    return body, references


def ordered_unique(numbers):
    result = []
    for number in numbers:
        if number not in result:
            result.append(number)
    return result


def parse_card_references(block_text, source_references):
    """Return the block's validated card-ID-to-primary-reference mapping."""
    lines = block_text.rstrip().splitlines()
    headings = [
        index for index, line in enumerate(lines)
        if line == REFS_HEADING
    ]
    if len(headings) != 1:
        raise ValueError(
            f"block must contain exactly one {REFS_HEADING!r} heading"
        )
    start = headings[0] + 1
    end = next(
        (index for index in range(start, len(lines)) if lines[index].startswith("## ")),
        len(lines),
    )
    mapping = {}
    used_references = set()
    for line in lines[start:end]:
        if not line.strip():
            continue
        match = REFS_MAPPING.fullmatch(line)
        if not match:
            raise ValueError(f"block has malformed Refs line: {line!r}")
        card_text, primary_text, secondary_text = match.groups()
        primary_references = [int(value) for value in primary_text.split(",")]
        secondary_references = (
            [int(value) for value in secondary_text.split(",")]
            if secondary_text else []
        )
        if len(primary_references) != 1:
            raise ValueError(
                f"block card mapping must have exactly one primary reference: {line!r}"
            )
        unknown = [
            number for number in primary_references + secondary_references
            if number not in source_references
        ]
        if unknown:
            raise ValueError(
                "block card mapping cites unknown reference(s): "
                + ", ".join(map(str, ordered_unique(unknown)))
            )
        primary_reference = primary_references[0]
        for card_id in card_text.split(","):
            if card_id in mapping:
                raise ValueError(f"block contains duplicate card mapping {card_id}")
            mapping[card_id] = primary_reference
        used_references.update(primary_references + secondary_references)
    if set(source_references) != used_references:
        missing = sorted(set(source_references) - used_references)
        raise ValueError(
            "block Refs mapping omits reference(s): "
            + ", ".join(map(str, missing))
        )
    return mapping


def render_document(body, references):
    lines = [body.rstrip()]
    if references:
        lines.extend(["", REFERENCES_HEADING, ""])
        lines.extend(f"{number}. {display}" for number, display in references.items())
    return "\n".join(lines).rstrip() + "\n"


def validate(document_text, block_text, *, source="report document"):
    """Validate card-ID markers without modifying the supplied document."""
    if REFERENCES_HEADING in document_text.splitlines():
        raise ValueError(f"{source} already contains a References section")
    if REPORT_MARKER.search(document_text):
        raise ValueError(f"{source} contains a model-generated numeric citation")
    _block_body, source_references = split_references(block_text, source="block")
    card_to_source = parse_card_references(block_text, source_references)

    for match in SOURCE_MARKER.finditer(document_text):
        card_id = match.group(1)
        if card_id not in card_to_source:
            raise ValueError(f"{source} cites unknown block card {card_id}")
    if CARD_MARKER_LIKE.search(SOURCE_MARKER.sub("", document_text)):
        raise ValueError(f"{source} contains a malformed card-ID marker")
    if "(refs:" in document_text:
        raise ValueError(f"{source} contains a legacy numeric source marker")
    return document_text


def render(report_text, block_text):
    """Resolve validated Step 6B card-ID markers and append primary entries."""
    validate(report_text, block_text, source="final report")
    _block_body, source_references = split_references(block_text, source="block")
    card_to_source = parse_card_references(block_text, source_references)
    report_number_by_source = {}

    def replace_marker(match):
        card_id = match.group(1)
        source_number = card_to_source[card_id]
        if source_number not in report_number_by_source:
            report_number_by_source[source_number] = len(report_number_by_source) + 1
        return f"[{report_number_by_source[source_number]}]"

    rendered = SOURCE_MARKER.sub(replace_marker, report_text)
    rendered = ADJACENT_REPORT_MARKERS.sub(
        lambda match: "[" + ",".join(map(str, ordered_unique(
            int(number)
            for marker in REPORT_MARKER.findall(match.group(0))
            for number in marker.split(",")
        ))) + "]",
        rendered,
    )
    rendered = NO_CITATION_MARKER.sub("", rendered)
    report_references = {
        report_number: source_references[source_number]
        for source_number, report_number in report_number_by_source.items()
    }
    return render_document(rendered, report_references)


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--report", type=Path, required=True)
    validate_parser.add_argument("--block", type=Path, required=True)
    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("--report", type=Path, required=True)
    render_parser.add_argument("--block", type=Path, required=True)
    render_parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "validate":
            validate(
                args.report.read_text(encoding="utf-8"),
                args.block.read_text(encoding="utf-8"),
            )
            output = args.report
        else:
            result = render(
                args.report.read_text(encoding="utf-8"),
                args.block.read_text(encoding="utf-8"),
            )
            output = args.output or args.report
            atomic_write(output, result)
    except (OSError, ValueError) as exc:
        print(f"REPORT CITATION {args.command.upper()} FAILED: {exc}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())