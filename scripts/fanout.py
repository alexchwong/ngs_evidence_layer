#!/usr/bin/env python3
"""Create independent v0.1.2 working folders from one indexed input corpus."""
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import make_key
import package_validation as validation

ROOT = Path(__file__).resolve().parent.parent


def load_index(path):
    records = []
    seen_ids = set()
    seen_paths = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
        required = {"id", "markdown_path", "source_filename", "status", "citation", "citation_source"}
        missing = sorted(required - set(record))
        if missing:
            raise ValueError(f"{path}:{line_number}: missing fields: {', '.join(missing)}")
        if record["id"] in seen_ids:
            raise ValueError(f"duplicate paper id: {record['id']}")
        if record["markdown_path"] in seen_paths:
            raise ValueError(f"duplicate markdown_path: {record['markdown_path']}")
        if record["status"] != "ingested":
            reason = (record.get("parse") or {}).get("error", "")
            if record["status"] == "citation-pending":
                reason = reason or "awaiting citation repair"
            raise ValueError(f"{record['id']}: status {record['status']!r} is not eligible: {reason}")
        citation = record["citation"]
        if not citation.get("authors") or not citation.get("title") or not citation.get("year"):
            raise ValueError(f"{record['id']}: ingested citation lacks authors, title, or year")
        suffix = f"--{record['id'][:8]}.md"
        if not Path(record["markdown_path"]).name.endswith(suffix):
            raise ValueError(f"{record['id']}: Markdown filename must end with {suffix}")
        seen_ids.add(record["id"])
        seen_paths.add(record["markdown_path"])
        records.append(record)
    if not records:
        raise ValueError(f"{path}: no indexed publications")
    return records


def metadata_for(record, corpus, source, created_at):
    built = make_key.build_citation(record["citation"])
    citation = dict(built["citation"])
    citation["doi"] = record["citation"].get("doi", "")
    return {
        "schema_version": "1.1",
        "paper_id": record["id"],
        "corpus": corpus,
        "stem": source.stem,
        "publication_key": built["publication_key"],
        "citation": citation,
        "citation_source": record["citation_source"],
        "citation_resolved_at": record.get("citation_resolved_at"),
        "source_filename": record["source_filename"],
        "source_sha256": record.get("sha256"),
        "markdown_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "created_at": created_at,
    }


def fanout(args):
    input_root = args.input_dir / args.corpus
    index_path = input_root / "index" / "papers.jsonl"
    if not index_path.is_file():
        raise ValueError(f"input corpus index not found: {index_path}")
    records = load_index(index_path)
    if args.publication_key:
        records = [record for record in records if record.get("publication_key") == args.publication_key]
        if not records:
            raise ValueError(f"publication key not found: {args.publication_key}")

    created_at = args.created_at or datetime.now(timezone.utc).isoformat()
    planned = []
    keys = {}
    for record in records:
        source = input_root / record["markdown_path"]
        if not source.is_file():
            raise ValueError(f"{record['id']}: indexed Markdown not found: {source}")
        metadata = metadata_for(record, args.corpus, source, created_at)
        stored_key = record.get("publication_key")
        if stored_key and stored_key != metadata["publication_key"]:
            raise ValueError(
                f"{record['id']}: stored publication_key {stored_key} does not match "
                f"computed {metadata['publication_key']}"
            )
        errors = validation.validate_metadata(metadata)
        if errors:
            raise ValueError("\n".join(errors))
        key = metadata["publication_key"]
        if key in keys:
            raise ValueError(f"duplicate publication_key {key}: {keys[key]} and {record['id']}")
        keys[key] = record["id"]
        planned.append((record, source, metadata))

    args.work_dir.mkdir(parents=True, exist_ok=True)
    created = []
    skipped = []
    staging = Path(tempfile.mkdtemp(prefix=".fanout-", dir=args.work_dir))
    try:
        for record, source, metadata in planned:
            key = metadata["publication_key"]
            destination = args.work_dir / key
            if destination.exists():
                existing_metadata_path = destination / "metadata.json"
                if not existing_metadata_path.is_file():
                    raise ValueError(f"existing work folder has no metadata: {destination}")
                existing_metadata = validation.read_json(existing_metadata_path, "existing metadata")
                if existing_metadata.get("paper_id") != record["id"]:
                    raise ValueError(
                        f"{key}: existing work folder belongs to paper_id "
                        f"{existing_metadata.get('paper_id')}, not {record['id']}"
                    )
                skipped.append(key)
                continue
            staged = staging / key
            staged.mkdir()
            shutil.copyfile(source, staged / "paper.md")
            (staged / "metadata.json").write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        for _record, _source, metadata in planned:
            key = metadata["publication_key"]
            staged = staging / key
            if staged.exists():
                os.replace(staged, args.work_dir / key)
                created.append(key)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return created, skipped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--key", dest="publication_key")
    parser.add_argument("--input-dir", type=Path, default=Path("input"))
    parser.add_argument("--work-dir", type=Path, default=Path("work"))
    parser.add_argument("--created-at", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        created, skipped = fanout(args)
    except (OSError, ValueError) as exc:
        sys.exit(f"FAN-OUT FAILED:\n{exc}")
    print(f"Created {len(created)} working folder(s); left {len(skipped)} existing folder(s) unchanged.")
    for publication_key in created:
        print(f"created: {args.work_dir / publication_key}")
    for publication_key in skipped:
        print(f"unchanged: {args.work_dir / publication_key}")


if __name__ == "__main__":
    main()