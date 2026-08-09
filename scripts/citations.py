#!/usr/bin/env python3
"""Repair unresolved corpus citations through verified DOI or manual workflows."""
import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import index_store
import make_key
import parse_pdfs

MANUAL_FIELDS = ("paper_id", "authors", "title", "journal", "year", "volume", "issue", "pages", "doi")


def timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def pending(records):
    return [record for record in records if record["status"] == "citation-pending"]


def markdown_path(record, corpus, input_dir):
    return Path(input_dir) / corpus / record["markdown_path"]


def title_context(text):
    lines = text.splitlines()
    title_index = next((index for index, line in enumerate(lines) if re.match(r"^#{1,6}\s+\S", line)), None)
    if title_index is None:
        title_index = next((index for index, line in enumerate(lines) if line.strip()), 0)
    title = re.sub(r"^#{1,6}\s+", "", lines[title_index].strip()) if lines else ""
    body = "\n".join(lines[title_index + 1:]).strip()[:1200]
    return title, body


def request(args, records):
    rows = pending(records)
    if not rows:
        raise ValueError("no citation-pending papers")
    lines = [
        "# DOI recovery request", "",
        "Search for each paper. Return a JSON array only, with `paper_id`, `title_seen`, and `doi`.",
        "Return an empty DOI rather than guessing when it cannot be verified against the title.", "",
    ]
    for record in rows:
        text = markdown_path(record, args.corpus, args.input_dir).read_text(encoding="utf-8")
        title, body = title_context(text)
        lines.extend([
            f"## {record['id']}", "", f"Title candidate: {title}",
            f"Detected DOI: {(record.get('parse') or {}).get('doi_detected', '')}", "",
            "Body excerpt:", "", body, "",
        ])
    output = args.input_dir / args.corpus / "citations" / f"request-{timestamp()}.md"
    index_store.atomic_text(output, "\n".join(lines).rstrip() + "\n")
    print(output)


def tokens(value):
    return set(re.findall(r"[a-z0-9]+", value.lower()))


def similarity(left, right):
    first, second = tokens(left), tokens(right)
    return len(first & second) / len(first | second) if first | second else 0.0


def source_publication_key(record):
    """Canonical corpus key; citation repair must never rename a source paper."""
    return make_key.build_source_key(record.get("source_filename"))


def apply_response(args, records):
    try:
        response = json.loads(args.response.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unreadable or malformed response: {exc}") from exc
    if not isinstance(response, list) or any(not isinstance(row, dict) for row in response):
        raise ValueError("response must be a JSON array of objects")
    by_id = {record["id"]: record for record in records}
    failures = 0
    seen_ids = set()
    for row in response:
        paper_id, doi, seen = row.get("paper_id"), str(row.get("doi", "")).strip(), str(row.get("title_seen", ""))
        record = by_id.get(paper_id)
        reason = ""
        if record is None:
            reason = "unknown paper_id"
        elif paper_id in seen_ids:
            reason = "duplicate paper_id in response"
        elif record["status"] != "citation-pending":
            reason = "paper is not citation-pending"
        elif not doi:
            reason = "blank DOI"
        else:
            try:
                citation = parse_pdfs.crossref_citation(doi, args.mailto)
                if similarity(citation["title"], seen) < 0.6:
                    raise ValueError("Crossref title does not match title_seen")
                detected = (record.get("parse") or {}).get("doi_detected", "")
                if detected and detected.lower() != doi.lower():
                    print(f"warning: {paper_id}: returned DOI contradicts detected DOI", file=sys.stderr)
                record.update(
                    citation=citation, citation_source="model-supplied-doi",
                    citation_resolved_at=datetime.now(timezone.utc).isoformat(),
                    publication_key=source_publication_key(record), status="ingested",
                )
                record["parse"]["error"] = ""
            except Exception as exc:
                reason = str(exc)
        if reason:
            failures += 1
            print(f"rejected {paper_id}: {reason}")
        else:
            print(f"applied {paper_id}")
        seen_ids.add(paper_id)
    index_store.write(args.corpus, records, args.input_dir)
    return 1 if failures else 0


def manual_export(args, records):
    output = args.output or args.input_dir / args.corpus / "citations" / f"manual-{timestamp()}.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = [dict.fromkeys(MANUAL_FIELDS, "") | {"paper_id": record["id"]} for record in pending(records)]
    stream = __import__("io").StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=MANUAL_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    index_store.atomic_text(output, stream.getvalue())
    print(output)


def manual_apply(args, records):
    try:
        with args.csv.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != MANUAL_FIELDS:
                raise ValueError("manual CSV columns do not match the required worksheet")
            rows = list(reader)
    except OSError as exc:
        raise ValueError(f"cannot read manual CSV: {exc}") from exc
    by_id = {record["id"]: record for record in records}
    seen = set()
    prepared = []
    errors = []
    for number, row in enumerate(rows, 2):
        paper_id = row["paper_id"].strip()
        record = by_id.get(paper_id)
        authors = [author.strip() for author in row["authors"].split(";")]
        if not paper_id or paper_id in seen:
            errors.append(f"row {number}: blank or duplicate paper_id")
        elif record is None or record["status"] != "citation-pending":
            errors.append(f"row {number}: unknown or non-pending paper_id")
        elif not authors or any(not author for author in authors):
            errors.append(f"row {number}: authors must be a non-empty semicolon-separated list")
        elif not row["title"].strip():
            errors.append(f"row {number}: title is required")
        else:
            try:
                year = int(row["year"])
                if not 1950 <= year <= 2100:
                    raise ValueError
            except ValueError:
                errors.append(f"row {number}: malformed year")
            else:
                citation = {
                    "authors": authors, "title": row["title"].strip(), "journal": row["journal"].strip(),
                    "year": year, "volume": row["volume"].strip(), "issue": row["issue"].strip(),
                    "pages": row["pages"].strip(), "doi": row["doi"].strip(),
                }
                prepared.append((record, citation))
        seen.add(paper_id)
    if errors:
        raise ValueError("\n".join(errors))
    resolved_at = datetime.now(timezone.utc).isoformat()
    for record, citation in prepared:
        record.update(
            citation=citation, citation_source="operator", citation_resolved_at=resolved_at,
            publication_key=source_publication_key(record), status="ingested",
        )
        record["parse"]["error"] = ""
    index_store.write(args.corpus, records, args.input_dir)
    print(f"applied {len(prepared)} manual citation(s)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("input"))
    parser.add_argument("--mailto", default=os.environ.get("NEL_CROSSREF_MAILTO", "noreply@example.org"))
    subparsers = parser.add_subparsers(dest="command", required=True)
    request_parser = subparsers.add_parser("request"); request_parser.add_argument("--corpus", required=True)
    apply_parser = subparsers.add_parser("apply"); apply_parser.add_argument("--corpus", required=True); apply_parser.add_argument("--response", type=Path, required=True)
    export_parser = subparsers.add_parser("manual-export"); export_parser.add_argument("--corpus", required=True); export_parser.add_argument("--output", type=Path)
    manual_parser = subparsers.add_parser("manual-apply"); manual_parser.add_argument("--corpus", required=True); manual_parser.add_argument("--csv", type=Path, required=True)
    args = parser.parse_args()
    try:
        records = index_store.load(args.corpus, args.input_dir)
        if args.command == "request": request(args, records)
        elif args.command == "apply": return apply_response(args, records)
        elif args.command == "manual-export": manual_export(args, records)
        else: manual_apply(args, records)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"CITATION REPAIR FAILED: {exc}", file=sys.stderr)
        return 2 if args.command == "apply" and "response" in str(exc).lower() else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
