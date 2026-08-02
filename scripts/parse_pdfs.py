#!/usr/bin/env python3
"""Convert private PDF inputs to indexed Markdown evidence sources."""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import index_store
import make_key

PAPER_NAMESPACE = uuid.UUID("6f1c2a34-8d5b-4e77-9a03-5c7e2b8f1d94")
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)


def now():
    return datetime.now(timezone.utc).isoformat()


def paper_uuid(sha256_hex):
    return str(uuid.uuid5(PAPER_NAMESPACE, sha256_hex))


def safe_stem(value):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return cleaned or "paper"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def detect_doi(markdown):
    region = markdown[:4000] + "\n" + markdown[-2000:]
    match = DOI_RE.search(region)
    return match.group(0).rstrip(".,;)]}") if match else ""


def table_warnings(markdown):
    warnings = []
    lines = markdown.splitlines()
    delimiter = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")
    for index, line in enumerate(lines):
        if not delimiter.match(line) or index == 0:
            continue
        expected = len(lines[index - 1].strip().strip("|").split("|"))
        row = index + 1
        while row < len(lines) and "|" in lines[row] and lines[row].strip():
            actual = len(lines[row].strip().strip("|").split("|"))
            if actual != expected:
                warnings.append(f"table near line {index + 1}: expected {expected} cells, found {actual} at line {row + 1}")
            row += 1
    return warnings


def crossref_fetch(url, headers):
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def crossref_citation(doi, mailto, fetch=crossref_fetch):
    if not mailto:
        raise ValueError("Crossref lookup requires --mailto or NEL_CROSSREF_MAILTO")
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
    payload = fetch(url, {"User-Agent": f"ngs-evidence-layer/0.1.2 (mailto:{mailto})"})
    message = payload.get("message", payload)
    authors = []
    for author in message.get("author", []):
        family = author.get("family", "").strip()
        initials = "".join(part[0] for part in author.get("given", "").split() if part)
        if family:
            authors.append(f"{family} {initials}".strip())
    date_parts = message.get("issued", {}).get("date-parts", [[]])
    citation = {
        "authors": authors, "title": (message.get("title") or [""])[0],
        "journal": (message.get("container-title") or [""])[0],
        "year": date_parts[0][0] if date_parts and date_parts[0] else None,
        "volume": message.get("volume", ""), "issue": message.get("issue", ""),
        "pages": message.get("page", ""), "doi": doi.lower(),
    }
    if not citation["authors"] or not citation["title"] or not citation["year"]:
        raise ValueError("Crossref record lacks required authors, title, or year")
    return citation


def convert_batch(paths, output_dir, quiet=False):
    import opendataloader_pdf
    opendataloader_pdf.convert(
        input_path=[str(path) for path in paths], output_dir=str(output_dir),
        format="markdown", reading_order="xycut", keep_line_breaks=False,
        use_struct_tree=False, image_output="off", quiet=quiet,
    )


def parser_version():
    try:
        return version("opendataloader-pdf")
    except PackageNotFoundError:
        return "unknown"


def reparse_conflicts(paper_id, work_dir, accept_dir, archive_dir):
    candidates = [work_dir / paper_id, archive_dir / paper_id,
                  accept_dir / f"{paper_id}.final.json", accept_dir / f"{paper_id}.census.json"]
    return [path for path in candidates if path.exists()]


def parse_one(source, args, records):
    checksum = sha256(source)
    paper_id = paper_uuid(checksum)
    stem = f"{safe_stem(source.stem)}--{paper_id[:8]}"
    existing = next((record for record in records if record["sha256"] == checksum), None)
    if existing and existing["status"] != "failed" and not args.force:
        return records, "skipped"
    if args.force and not args.allow_reparse:
        conflicts = reparse_conflicts(paper_id, args.work_dir, args.accept_dir, args.archive_dir)
        if conflicts:
            raise ValueError(f"{paper_id}: reparse blocked by existing state: " + ", ".join(map(str, conflicts)))
    markdown_rel = f"markdown/{stem}.md"
    parsed_at = now()
    parse = {
        "parser": "opendataloader-pdf", "parser_version": parser_version(),
        "parsed_at": parsed_at, "markdown_sha256": "", "archived_pdf": "",
        "doi_detected": "", "table_warnings": [], "error": "",
    }
    base = {
        "id": paper_id, "markdown_path": markdown_rel, "source_filename": source.name,
        "sha256": checksum, "status": "failed", "citation": {},
        "citation_source": None, "citation_resolved_at": None,
        "publication_key": None, "parse": parse,
    }
    if args.dry_run:
        return records, f"would parse {source} as {paper_id}"
    try:
        with tempfile.TemporaryDirectory(prefix="nel-pdf-") as temporary:
            temporary_path = Path(temporary)
            convert_batch([source], temporary_path, args.quiet)
            markdowns = list(temporary_path.rglob("*.md"))
            if len(markdowns) != 1:
                raise ValueError(f"converter produced {len(markdowns)} Markdown files")
            markdown = markdowns[0].read_text(encoding="utf-8")
            destination = args.input_dir / args.corpus / markdown_rel
            index_store.atomic_text(destination, markdown)
        parse["markdown_sha256"] = hashlib.sha256(markdown.encode()).hexdigest()
        parse["table_warnings"] = table_warnings(markdown)
        for warning in parse["table_warnings"]:
            print(f"warning: {paper_id}: {warning}", file=sys.stderr)
        parse["doi_detected"] = detect_doi(markdown)
        base["status"] = "citation-pending"
        if not parse["doi_detected"]:
            parse["error"] = "no DOI detected"
        else:
            try:
                citation = crossref_citation(parse["doi_detected"], args.mailto)
                base["citation"] = citation
                base["citation_source"] = "crossref-doi"
                base["citation_resolved_at"] = now()
                base["publication_key"] = make_key.build_key(citation)
                base["status"] = "ingested"
            except (ValueError, OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
                parse["error"] = str(exc)
        archive = args.pdf_dir / "archive" / args.corpus / source.name
        if not args.keep_source:
            archive.parent.mkdir(parents=True, exist_ok=True)
            if archive.exists():
                archive = archive.with_name(f"{archive.stem}--{paper_id[:8]}{archive.suffix}")
            shutil.move(str(source), archive)
            parse["archived_pdf"] = str(archive)
    except Exception as exc:
        parse["error"] = str(exc)
        base["markdown_path"] = ""
    for other in records:
        if base["publication_key"] and other.get("publication_key") == base["publication_key"] and other["sha256"] != checksum:
            print(f"warning: publication_key {base['publication_key']} collision: {other['id']} ({other['source_filename']}) and {paper_id} ({source.name})", file=sys.stderr)
    records = index_store.replace(records, base)
    index_store.write(args.corpus, records, args.input_dir)
    return records, base["status"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--allow-reparse", action="store_true")
    parser.add_argument("--keep-source", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--mailto", default=os.environ.get("NEL_CROSSREF_MAILTO"))
    parser.add_argument("--pdf-dir", type=Path, default=Path("pdf"))
    parser.add_argument("--input-dir", type=Path, default=Path("input"))
    parser.add_argument("--work-dir", type=Path, default=Path("work"))
    parser.add_argument("--accept-dir", type=Path, default=Path("accept"))
    parser.add_argument("--archive-dir", type=Path, default=Path("archive"))
    args = parser.parse_args()
    try:
        if shutil.which("java") is None:
            raise ValueError("Java 11+ is required for OpenDataLoader PDF")
        try:
            __import__("opendataloader_pdf")
        except ImportError as exc:
            raise ValueError("opendataloader-pdf is not installed") from exc
        sources = args.paths or sorted((args.pdf_dir / args.corpus).glob("*.pdf"))
        if not sources:
            raise ValueError("no PDF inputs found")
        if any(not path.is_file() or path.suffix.lower() != ".pdf" for path in sources):
            raise ValueError("all inputs must be existing PDF files")
        records = index_store.load(args.corpus, args.input_dir)
        outcomes = []
        for source in sources:
            records, outcome = parse_one(source, args, records)
            outcomes.append(outcome)
            if not args.quiet:
                print(f"{source}: {outcome}")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"PDF PARSE FAILED: {exc}", file=sys.stderr)
        return 2
    return 1 if any(outcome in {"failed", "citation-pending"} for outcome in outcomes) else 0


if __name__ == "__main__":
    sys.exit(main())