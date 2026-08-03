#!/usr/bin/env python3
"""Canonical, atomic storage for a corpus paper index and its CSV view."""
import csv
import io
import json
import os
import tempfile
from pathlib import Path

RECORD_FIELDS = (
    "id", "markdown_path", "source_filename", "sha256", "status", "citation",
    "citation_source", "citation_resolved_at", "publication_key", "parse",
)
CSV_FIELDS = (
    "id", "status", "source_filename", "markdown_path", "citation_source",
    "doi", "year", "first_author", "title", "publication_key", "error",
)
STATUSES = {"ingested", "citation-pending", "failed"}


def corpus_root(corpus, input_dir=Path("input")):
    return Path(input_dir) / corpus


def index_paths(corpus, input_dir=Path("input")):
    root = corpus_root(corpus, input_dir)
    return root / "index" / "papers.jsonl", root / "index" / "papers.csv"


def ordered(record):
    return {field: record.get(field) for field in RECORD_FIELDS}


def validate_records(records):
    ids, checksums, markdown_paths = set(), set(), set()
    for number, record in enumerate(records, 1):
        missing = [field for field in RECORD_FIELDS if field not in record]
        if missing:
            raise ValueError(f"index record {number} missing fields: {', '.join(missing)}")
        if record["status"] not in STATUSES:
            raise ValueError(f"index record {number} has invalid status: {record['status']}")
        for field, seen in (("id", ids), ("sha256", checksums)):
            value = record[field]
            if value in seen:
                raise ValueError(f"duplicate {field}: {value}")
            seen.add(value)
        path = record.get("markdown_path")
        if path:
            if path in markdown_paths:
                raise ValueError(f"duplicate markdown_path: {path}")
            markdown_paths.add(path)


def load(corpus, input_dir=Path("input")):
    jsonl_path, _csv_path = index_paths(corpus, input_dir)
    if not jsonl_path.exists():
        return []
    records = []
    for number, line in enumerate(jsonl_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{jsonl_path}:{number}: invalid JSON: {exc}") from exc
    validate_records(records)
    return records


def csv_text(records):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for record in records:
        citation = record.get("citation") or {}
        authors = citation.get("authors") or []
        writer.writerow({
            "id": record["id"],
            "status": record["status"],
            "source_filename": record["source_filename"],
            "markdown_path": record.get("markdown_path") or "",
            "citation_source": record.get("citation_source") or "",
            "doi": citation.get("doi", ""),
            "year": citation.get("year", ""),
            "first_author": authors[0] if authors else "",
            "title": citation.get("title", ""),
            "publication_key": record.get("publication_key") or "",
            "error": (record.get("parse") or {}).get("error", ""),
        })
    return output.getvalue()


def atomic_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def write(corpus, records, input_dir=Path("input")):
    validate_records(records)
    jsonl_path, csv_path = index_paths(corpus, input_dir)
    jsonl = "".join(json.dumps(ordered(record), ensure_ascii=False) + "\n" for record in records)
    atomic_text(jsonl_path, jsonl)
    atomic_text(csv_path, csv_text(records))


def replace(records, record):
    result = [existing for existing in records if existing["sha256"] != record["sha256"]]
    result.append(record)
    return sorted(result, key=lambda item: (item["source_filename"], item["id"]))