"""Validate and render citations in generated NGS reports.

``validate`` is a read-only Step 6A/6B exit check. It verifies that a report
document contains only well-formed runtime card-tag markers that deconvolve to
cards through ``card-tags.json`` and resolve through the canonical ``## Refs``
mapping in ``evidence.md``. Step 6B can additionally require every sentence-ending
full stop to be immediately followed by one space and a citation disposition, e.g.
``Sentence. [card:abcdef]`` or ``Sentence. (no citation required)``. ``validate``
remains read-only and reports the exact expected syntax on placement failures.

``render`` is mandatory Step 6C processing. It canonicalizes the model-facing
post-full-stop citation placement into final Vancouver-style placement,
replaces the card-tag markers in ``report-final.md`` with report-local
Vancouver-style numeric citations in order of first appearance, and appends the
cited primary references. Rendering replaces its output atomically and fails
without modifying it when validation fails.
"""

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

from scripts.core import card_tags


REFERENCES_HEADING = "## References"
REFS_HEADING = "## Refs"
REFERENCE_START = re.compile(r"^(\d+)\.\s+(.+)$")
CARD_ID = r"[A-Za-z0-9][A-Za-z0-9._-]*"
CARD_TAG = r"[0-9a-f]{6}(?:[0-9a-f]{6})?"
REFS_MAPPING = re.compile(
    rf"^({CARD_TAG}(?:,{CARD_TAG})*): primary ref "
    r"([1-9]\d*(?:,[1-9]\d*)*)"
    r"(?:; secondary ref ([1-9]\d*(?:,[1-9]\d*)*))?$"
)
SOURCE_MARKER = re.compile(rf"\[card:({CARD_TAG})\]")
CARD_MARKER_LIKE = re.compile(r"\[card:[^\[\]\n]*\]")
REPORT_MARKER = re.compile(r"\[([0-9]+(?:\s*,\s*[0-9]+)*)\]")
ADJACENT_REPORT_MARKERS = re.compile(r"(?:\[(?:[0-9]+(?:\s*,\s*[0-9]+)*)\]){2,}")
NO_CITATION_MARKER = re.compile(r"\s*\(no citation required\)")
SENTENCE_ENDING_FULL_STOP = re.compile(r"\.(?=(?:\s|\[card:|\(no citation required\)|$))")
CITATION_DISPOSITION_AFTER_FULL_STOP = re.compile(
    rf"^(?: \[card:{CARD_TAG}\](?:\[card:{CARD_TAG}\])*"
    rf"| \(no citation required\))(?=\s|$)"
)
LEGACY_DISPOSITION_AFTER_FULL_STOP = re.compile(
    rf"\.(?P<spacing>[ \t]+)(?P<disposition>"
    rf"(?:\[card:{CARD_TAG}\](?:[ \t]*\[card:{CARD_TAG}\])*)"
    rf"|\(no citation required\))"
    rf"(?=(?:\s|$))"
)


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


def format_citation_numbers(numbers):
    """Return sorted unique Vancouver numbers with consecutive values collapsed."""
    values = sorted(set(numbers))
    if not values:
        return ""
    ranges = []
    start = end = values[0]
    for value in values[1:]:
        if value == end + 1:
            end = value
            continue
        ranges.append((start, end))
        start = end = value
    ranges.append((start, end))
    return ",".join(
        str(start) if start == end else f"{start}-{end}"
        for start, end in ranges
    )


def parse_card_references(evidence_text, source_references):
    """Return evidence.md runtime-card-tag to primary-reference mapping."""
    lines = evidence_text.rstrip().splitlines()
    headings = [
        index for index, line in enumerate(lines)
        if line == REFS_HEADING
    ]
    if len(headings) != 1:
        raise ValueError(
            f"evidence must contain exactly one {REFS_HEADING!r} heading"
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
            raise ValueError(f"evidence has malformed Refs line: {line!r}")
        card_text, primary_text, secondary_text = match.groups()
        primary_references = [int(value) for value in primary_text.split(",")]
        secondary_references = (
            [int(value) for value in secondary_text.split(",")]
            if secondary_text else []
        )
        if len(primary_references) != 1:
            raise ValueError(
                f"evidence card mapping must have exactly one primary reference: {line!r}"
            )
        unknown = [
            number for number in primary_references + secondary_references
            if number not in source_references
        ]
        if unknown:
            raise ValueError(
                "evidence card mapping cites unknown reference(s): "
                + ", ".join(map(str, ordered_unique(unknown)))
            )
        primary_reference = primary_references[0]
        for card_tag in card_text.split(","):
            if card_tag in mapping:
                raise ValueError(f"evidence contains duplicate card mapping {card_tag}")
            mapping[card_tag] = primary_reference
        used_references.update(primary_references + secondary_references)
    if set(source_references) != used_references:
        missing = sorted(set(source_references) - used_references)
        raise ValueError(
            "evidence Refs mapping omits reference(s): "
            + ", ".join(map(str, missing))
        )
    return mapping


def parse_card_tags(card_tags_text):
    """Return validated runtime card-tag -> stable card-ID mapping."""
    try:
        payload = json.loads(card_tags_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"card-tags is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "algorithm", "tags"}:
        raise ValueError("card-tags must contain exactly schema_version, algorithm, and tags")
    if payload["schema_version"] != "1.0":
        raise ValueError("card-tags schema_version must be '1.0'")
    supported_algorithms = {
        card_tags.ALGORITHM,
        "sha256-12hex-collision-resolved-global-corpus",
    }
    if payload["algorithm"] not in supported_algorithms:
        raise ValueError("card-tags algorithm is unsupported")
    rows = payload["tags"]
    if not isinstance(rows, list):
        raise ValueError("card-tags tags must be an array")
    mapping = {}
    seen_ids = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {"card_tag", "card_id"}:
            raise ValueError(f"card-tags tags[{index}] has invalid fields")
        tag = row["card_tag"]
        card_id = row["card_id"]
        if not isinstance(tag, str) or re.fullmatch(CARD_TAG, tag) is None:
            raise ValueError(f"card-tags tags[{index}].card_tag is invalid")
        if not isinstance(card_id, str) or re.fullmatch(CARD_ID, card_id) is None:
            raise ValueError(f"card-tags tags[{index}].card_id is invalid")
        if tag in mapping:
            raise ValueError(f"card-tags contains duplicate tag {tag}")
        if card_id in seen_ids:
            raise ValueError(f"card-tags contains duplicate card_id {card_id}")
        mapping[tag] = card_id
        seen_ids.add(card_id)
    return mapping



def normalize_citation_placement(document_text):
    """Move model-facing post-full-stop card markers before the full stop for rendering."""
    def replace(match):
        disposition = re.sub(r"[ \t]+(?=\[card:)", "", match.group("disposition"))
        return f" {disposition}."

    return LEGACY_DISPOSITION_AFTER_FULL_STOP.sub(replace, document_text)

def render_document(body, references):
    lines = [body.rstrip()]
    if references:
        lines.extend(["", REFERENCES_HEADING, ""])
        lines.extend(f"{number}. {display}" for number, display in references.items())
    return "\n".join(lines).rstrip() + "\n"


def _line_context(text, offset):
    line_number = text.count("\n", 0, offset) + 1
    line_start = text.rfind("\n", 0, offset) + 1
    line_end = text.find("\n", offset)
    if line_end == -1:
        line_end = len(text)
    return line_number, text[line_start:line_end].strip()


def _upstream_error(message):
    return (
        message
        + " This is a deterministic Step 5 evidence/card-tag artifact problem, not a "
          "report-final.md authoring error. Do not edit report-final.md or inspect this "
          "validator to fix it; rerun/fix the upstream deterministic Step 5 output."
    )


def validate(
    document_text,
    evidence_text,
    card_tags_text,
    *,
    source="report document",
    require_citation_after_full_stop=False,
):
    """Validate runtime card-tag markers without modifying the document."""
    if REFERENCES_HEADING in document_text.splitlines():
        line_number = document_text.splitlines().index(REFERENCES_HEADING) + 1
        raise ValueError(
            f"{source} line {line_number} contains a model-written '## References' section. "
            "Delete that heading and all model-written bibliography entries; Step 6C creates the "
            "References section deterministically from runtime card tags."
        )
    numeric = REPORT_MARKER.search(document_text)
    if numeric:
        line_number, line = _line_context(document_text, numeric.start())
        raise ValueError(
            f"{source} line {line_number} contains model-generated numeric citation {numeric.group(0)!r}. "
            "Remove the numeric citation and restore the exact runtime card tag(s) from report-draft.md "
            "after the full stop, e.g. 'Sentence. [card:a1b2c3]'. "
            f"Offending line: {line!r}"
        )
    try:
        _evidence_body, source_references = split_references(evidence_text, source="evidence")
        tag_to_source = parse_card_references(evidence_text, source_references)
        tag_to_card = parse_card_tags(card_tags_text)
    except ValueError as exc:
        raise ValueError(_upstream_error(str(exc))) from exc
    if set(tag_to_source) != set(tag_to_card):
        missing = sorted(set(tag_to_card) - set(tag_to_source))
        extra = sorted(set(tag_to_source) - set(tag_to_card))
        details = []
        if missing:
            details.append("missing from evidence: " + ", ".join(missing))
        if extra:
            details.append("unknown in evidence: " + ", ".join(extra))
        raise ValueError(_upstream_error("evidence/card-tags mismatch: " + "; ".join(details) + "."))

    for match in SOURCE_MARKER.finditer(document_text):
        tag = match.group(1)
        if tag not in tag_to_source:
            line_number, line = _line_context(document_text, match.start())
            raise ValueError(
                f"{source} line {line_number} cites unknown runtime card tag [card:{tag}]. "
                "Replace that marker with the exact marker(s) present on the corresponding assertion "
                "in report-draft.md; do not invent or translate tags. "
                f"Offending line: {line!r}"
            )
    residual_text = SOURCE_MARKER.sub(lambda m: " " * len(m.group(0)), document_text)
    malformed = CARD_MARKER_LIKE.search(residual_text)
    if malformed:
        line_number, line = _line_context(document_text, malformed.start())
        bad = document_text[malformed.start():malformed.end()]
        raise ValueError(
            f"{source} line {line_number} contains malformed card marker {bad!r}. "
            "Replace it with the exact lowercase runtime marker copied from the "
            "corresponding assertion in report-draft.md, e.g. '[card:a1b2c3]'. "
            f"Offending line: {line!r}"
        )
    legacy_offset = document_text.find("(refs:")
    if legacy_offset != -1:
        line_number, line = _line_context(document_text, legacy_offset)
        raise ValueError(
            f"{source} line {line_number} contains legacy '(refs: ...)' citation syntax. "
            "Delete that legacy marker and restore the exact terminal disposition from report-draft.md: "
            "'[card:xxxxxx]' marker(s) or '(no citation required)' after the full stop. "
            f"Offending line: {line!r}"
        )
    if require_citation_after_full_stop:
        for match in SENTENCE_ENDING_FULL_STOP.finditer(document_text):
            suffix = document_text[match.end():]
            if CITATION_DISPOSITION_AFTER_FULL_STOP.match(suffix) is None:
                line_number, line = _line_context(document_text, match.start())
                following = suffix[:40].split("\n", 1)[0]
                raise ValueError(
                    f"{source} line {line_number} has a sentence-ending full stop followed by "
                    f"{following!r}, not by the required citation disposition. Fix this sentence so the "
                    "full stop is followed immediately by exactly one space and either adjacent exact "
                    "runtime card tags or '(no citation required)': 'Sentence. [card:a1b2c3]' or "
                    "'Sentence. (no citation required)'. If a marker is currently before the full stop, "
                    "move it after the full stop. Restore markers from report-draft.md only. "
                    f"Offending line: {line!r}"
                )
    return document_text


def render(
    report_text,
    evidence_text,
    card_tags_text,
    *,
    require_citation_after_full_stop=True,
):
    """Canonicalize, resolve card-tag markers, and append primary entries.

    Some workflow contracts require a citation disposition after every sentence-ending
    full stop, while structured statement contracts bind one disposition to a complete
    multi-sentence statement. The caller selects that placement rule; all marker,
    evidence and card-tag validation remains shared.
    """
    validate(
        report_text,
        evidence_text,
        card_tags_text,
        source="final report",
        require_citation_after_full_stop=require_citation_after_full_stop,
    )
    report_text = normalize_citation_placement(report_text)
    _evidence_body, source_references = split_references(evidence_text, source="evidence")
    tag_to_source = parse_card_references(evidence_text, source_references)
    report_number_by_source = {}

    def replace_marker(match):
        source_number = tag_to_source[match.group(1)]
        if source_number not in report_number_by_source:
            report_number_by_source[source_number] = len(report_number_by_source) + 1
        return f"[{report_number_by_source[source_number]}]"

    rendered = SOURCE_MARKER.sub(replace_marker, report_text)
    rendered = ADJACENT_REPORT_MARKERS.sub(
        lambda match: "[" + format_citation_numbers(
            int(number)
            for marker in REPORT_MARKER.findall(match.group(0))
            for number in marker.split(",")
        ) + "]",
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
    validate_parser.add_argument("--evidence", type=Path, required=True)
    validate_parser.add_argument("--card-tags", type=Path, required=True)
    validate_parser.add_argument(
        "--require-citation-after-full-stop",
        action="store_true",
        help=(
            "require each sentence-ending full stop to be followed by one space and "
            "one or more runtime card tags or '(no citation required)', e.g. "
            "'Sentence. [card:a1b2c3]'"
        ),
    )
    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("--report", type=Path, required=True)
    render_parser.add_argument("--evidence", type=Path, required=True)
    render_parser.add_argument("--card-tags", type=Path, required=True)
    render_parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "validate":
            validate(
                args.report.read_text(encoding="utf-8"),
                args.evidence.read_text(encoding="utf-8"),
                args.card_tags.read_text(encoding="utf-8"),
                require_citation_after_full_stop=args.require_citation_after_full_stop,
            )
            output = args.report
        else:
            result = render(
                args.report.read_text(encoding="utf-8"),
                args.evidence.read_text(encoding="utf-8"),
                args.card_tags.read_text(encoding="utf-8"),
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