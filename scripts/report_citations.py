#!/usr/bin/env python3
"""Deterministically prepare and finalize citations in generated NGS reports.

``prepare`` resolves Step 6A ``(refs: N[,N...])`` markers against the numbered
bibliography in ``block.md``, converts them to report-local square-bracket
citations in order of first appearance, and appends the cited Vancouver entries.

``finalize`` runs after Step 6B. It verifies every square-bracket citation against
the supplied bibliography, removes uncited entries, and renumbers citations and
entries in order of first appearance. Both commands replace their output
atomically and fail without modifying it when validation fails.
"""

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path


REFERENCES_HEADING = "## References"
REFERENCE_START = re.compile(r"^(\d+)\.\s+(.+)$")
SOURCE_MARKER = re.compile(r"\(refs:\s*([0-9]+(?:\s*,\s*[0-9]+)*)\)")
REPORT_MARKER = re.compile(r"\[([0-9]+(?:\s*,\s*[0-9]+)*)\]")
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


def render_document(body, references):
    lines = [body.rstrip()]
    if references:
        lines.extend(["", REFERENCES_HEADING, ""])
        lines.extend(f"{number}. {display}" for number, display in references.items())
    return "\n".join(lines).rstrip() + "\n"


def prepare(draft_text, block_text):
    """Resolve Step 6A source-reference markers and append cited entries."""
    if REFERENCES_HEADING in draft_text.splitlines():
        raise ValueError("report draft already contains a References section")
    _block_body, source_references = split_references(block_text, source="block")
    report_number_by_source = {}

    def replace_marker(match):
        source_numbers = ordered_unique(
            int(value.strip()) for value in match.group(1).split(",")
        )
        unknown = [number for number in source_numbers if number not in source_references]
        if unknown:
            raise ValueError(
                "report draft cites unknown block reference(s): "
                + ", ".join(map(str, unknown))
            )
        report_numbers = []
        for source_number in source_numbers:
            if source_number not in report_number_by_source:
                report_number_by_source[source_number] = len(report_number_by_source) + 1
            report_numbers.append(report_number_by_source[source_number])
        return "[" + ",".join(map(str, report_numbers)) + "]"

    prepared = SOURCE_MARKER.sub(replace_marker, draft_text)
    if "(refs:" in prepared:
        raise ValueError("report draft contains a malformed (refs: N[,N...]) marker")
    prepared = NO_CITATION_MARKER.sub("", prepared)
    report_references = {
        report_number: source_references[source_number]
        for source_number, report_number in report_number_by_source.items()
    }
    return render_document(prepared, report_references)


def finalize(report_text):
    """Validate and normalize a Step 6B report's retained citations."""
    body, supplied_references = split_references(report_text, source="report")
    new_number_by_old = {}

    def replace_marker(match):
        old_numbers = ordered_unique(
            int(value.strip()) for value in match.group(1).split(",")
        )
        unknown = [number for number in old_numbers if number not in supplied_references]
        if unknown:
            raise ValueError(
                "report cites unknown supplied reference(s): "
                + ", ".join(map(str, unknown))
            )
        new_numbers = []
        for old_number in old_numbers:
            if old_number not in new_number_by_old:
                new_number_by_old[old_number] = len(new_number_by_old) + 1
            new_numbers.append(new_number_by_old[old_number])
        return "[" + ",".join(map(str, new_numbers)) + "]"

    normalized_body = REPORT_MARKER.sub(replace_marker, body)
    normalized_references = {
        new_number: supplied_references[old_number]
        for old_number, new_number in new_number_by_old.items()
    }
    return render_document(normalized_body, normalized_references)


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
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--draft", type=Path, required=True)
    prepare_parser.add_argument("--block", type=Path, required=True)
    prepare_parser.add_argument("--output", type=Path)
    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--report", type=Path, required=True)
    finalize_parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            result = prepare(
                args.draft.read_text(encoding="utf-8"),
                args.block.read_text(encoding="utf-8"),
            )
            output = args.output or args.draft
        else:
            result = finalize(args.report.read_text(encoding="utf-8"))
            output = args.output or args.report
        atomic_write(output, result)
    except (OSError, ValueError) as exc:
        print(f"REPORT CITATION {args.command.upper()} FAILED: {exc}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())