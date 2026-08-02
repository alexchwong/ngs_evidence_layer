#!/usr/bin/env python3
"""Combine accepted ingestion packages into one deterministic corpus.

Quotes are validated from the accepted package but deliberately absent from
everything this script writes. The corpus is the distributable artefact; a build
that copied quote text into it would quietly turn a private audit trail into a
published one.

The audit gate is enforced here rather than trusted: a card whose Phase 3 verdict
is absent or failed does not enter the corpus. Ingestion hallucination is the
fatal failure mode, and the audit is the only thing standing between an
interpretation that drifted beyond its quote and a clinician reading it as
evidence.

Usage:
  build_corpus.py --input-index input/demo/index/papers.jsonl \\
      --markdown-dir input/demo/markdown --phase1-dir output/phase1 \\
      --package-dir output/phase3 --after-phase 3 --output-dir output/corpus
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import vocab  # noqa: E402


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = load_module("nel_validate", "validate_cards.py")
PACKAGE_SCHEMA = SCRIPTS.parent / "schema" / "ingestion_package_schema.json"


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def canonical_bytes(document):
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def atomic_write_json(document, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_bytes(document)
    handle_fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        with os.fdopen(handle_fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def load_index(path):
    records = []
    seen_ids = set()
    seen_paths = set()
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
        if not record.get("id") or not record.get("markdown_path"):
            raise ValueError(f"{path}:{line_no}: id and markdown_path are required")
        if record["id"] in seen_ids:
            raise ValueError(f"duplicate input id: {record['id']}")
        if record["markdown_path"] in seen_paths:
            raise ValueError(f"duplicate markdown_path: {record['markdown_path']}")
        seen_ids.add(record["id"])
        seen_paths.add(record["markdown_path"])
        records.append(record)
    return sorted(records, key=lambda item: item["id"])


def parse_skip_report(path, record):
    text = Path(path).read_text(encoding="utf-8")
    fields = {}
    for key in ("input_id", "markdown_path", "date", "reason"):
        match = re.search(rf"(?mi)^-\s*{key}:\s*`?([^`\n]+)`?\s*$", text)
        if match:
            fields[key] = match.group(1).strip()
    errors = []
    if fields.get("input_id") != record["id"]:
        errors.append(f"{path}: input_id does not match {record['id']}")
    if Path(fields.get("markdown_path", "")).name != Path(record["markdown_path"]).name:
        errors.append(f"{path}: markdown_path does not match the input index")
    if not fields.get("reason"):
        errors.append(f"{path}: a non-empty reason is required")
    if not fields.get("date"):
        errors.append(f"{path}: date is required")
    return fields, errors


def package_as_validation_views(package):
    """Adapt one accepted package to the existing card and quote validators."""
    cards = {
        key: package[key]
        for key in (
            "publication_key", "citation", "publication_type", "extraction_date",
            "extraction_model", "genes_covered", "diseases_covered", "census_entries", "cards",
        )
    }
    cards["schema_version"] = "2.0"
    quotes = {
        "schema_version": "2.0",
        "publication_key": package["publication_key"],
        "extraction_date": package["extraction_date"],
        "extraction_model": package["extraction_model"],
        "quotes": package["quotes"],
    }
    return cards, quotes


def validate_package_schema(package, package_path):
    schema = json.loads(PACKAGE_SCHEMA.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(package),
        key=lambda error: list(error.absolute_path),
    )
    return [
        f"{package_path}: ingestion package schema: "
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in errors
    ]


def validate_accepted_package(package_path, census_path, markdown_path):
    try:
        package = json.loads(Path(package_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"cannot read accepted package {package_path}: {exc}"], [], None
    errors = validate_package_schema(package, package_path)
    if errors:
        return None, errors, [], None
    cards, quotes = package_as_validation_views(package)
    with tempfile.TemporaryDirectory() as temporary:
        temporary = Path(temporary)
        card_path = temporary / "cards.json"
        quote_path = temporary / "quotes.json"
        atomic_write_json(cards, card_path)
        atomic_write_json(quotes, quote_path)
        document, validation_errors, warnings, report = VALIDATOR.validate(
            card_path, quote_path, census_path, markdown_path
        )
    return document, validation_errors, warnings, report


def check_audit(package, document):
    """Return (errors, summary). No verdict means no entry to the corpus."""
    errors = []
    audit = package.get("audit") or {}

    audit_model = audit.get("audit_model")
    extraction_model = document.get("extraction_model")
    if not audit_model:
        errors.append("audit file does not record audit_model")
    elif audit_model == extraction_model:
        errors.append(
            f"audit_model and extraction_model are both {audit_model!r}; the auditing "
            "model must differ from the authoring model"
        )
    if audit.get("extraction_model_reviewed") != extraction_model:
        errors.append("extraction_model_reviewed does not match extraction_model")

    verdicts = {}
    for result in audit.get("results", []):
        card_id = result.get("card_id")
        verdict = result.get("verdict")
        if verdict not in ("pass", "fail"):
            errors.append(f"{card_id}: audit verdict must be 'pass' or 'fail'")
        if verdict == "fail" and not result.get("reason"):
            errors.append(f"{card_id}: a failed card must carry a reason")
        verdicts[card_id] = verdict

    failed = []
    unaudited = []
    for card in document.get("cards", []):
        card_id = card["card_id"]
        if card_id not in verdicts:
            unaudited.append(card_id)
        elif verdicts[card_id] == "fail":
            failed.append(card_id)
    for card_id in verdicts:
        if card_id not in {card["card_id"] for card in document.get("cards", [])}:
            errors.append(f"{card_id}: audit verdict for a card that is not in the card file")

    for card_id in unaudited:
        errors.append(f"{card_id}: no audit verdict")
    for card_id in failed:
        errors.append(
            f"{card_id}: audit verdict is 'fail'; rewrite or delete the card, do not build "
            "around it"
        )

    summary = {
        "audit_model": audit_model,
        "audited": len(verdicts),
        "passed": sum(1 for verdict in verdicts.values() if verdict == "pass"),
        "failed": len(failed),
    }
    return errors, summary


def add(index, key, value):
    index[key].append(value)


def sorted_postings(mapping):
    return {key: sorted(set(values)) for key, values in sorted(mapping.items())}


def build(args):
    records = load_index(args.input_index)
    errors = list(vocab.check_vocabulary_consistency())
    publications = []
    skipped = {}
    pending = []
    seen_publication_keys = {}
    seen_card_ids = {}
    known_outputs = set()

    by_gene = defaultdict(list)
    by_disease = defaultdict(list)
    by_category = defaultdict(list)
    by_escalation = defaultdict(list)
    by_tier = defaultdict(list)
    by_year = defaultdict(list)
    by_type = defaultdict(list)
    paper_index = {}
    card_index = {}

    for record in records:
        markdown_name = Path(record["markdown_path"]).name
        markdown_path = args.markdown_dir / markdown_name
        stem = Path(markdown_name).stem
        census_path = args.phase1_dir / f"{stem}.phase1.json"
        package_path = args.package_dir / f"{stem}.phase{args.after_phase}.json"
        skip_path = args.reports_dir / f"{stem}.skipped.md"
        known_outputs.add(package_path.name)

        if not markdown_path.is_file():
            errors.append(f"{record['id']}: archived Markdown not found: {markdown_path}")
            continue
        if package_path.exists() and skip_path.exists():
            errors.append(f"{record['id']}: both an accepted package and a skip report exist")
            continue
        if skip_path.exists():
            fields, skip_errors = parse_skip_report(skip_path, record)
            errors.extend(skip_errors)
            skipped[record["id"]] = {
                "markdown_path": record["markdown_path"],
                "report_file": str(skip_path),
                "date": fields.get("date"),
                "reason": fields.get("reason"),
            }
            paper_index[record["id"]] = {
                "status": "skipped",
                "markdown_path": record["markdown_path"],
                "reason": fields.get("reason"),
            }
            continue
        if not package_path.exists():
            pending.append(record["id"])
            paper_index[record["id"]] = {
                "status": "pending",
                "markdown_path": record["markdown_path"],
            }
            continue

        package = json.loads(package_path.read_text(encoding="utf-8"))
        document, validation_errors, _warnings, extraction_report = validate_accepted_package(
            package_path, census_path if census_path.exists() else None, markdown_path
        )
        errors.extend(f"{record['id']}: {error}" for error in validation_errors)
        if document is None or validation_errors:
            continue

        if args.allow_unaudited:
            if package.get("audited") is not False or package.get("audit") is not None:
                errors.append(f"{record['id']}: provisional build requires an unaudited package")
                continue
            audit_summary = {"audit_model": None, "audited": 0, "passed": 0, "failed": 0}
        elif package.get("audited") is True and package.get("audit") is not None:
            audit_errors, audit_summary = check_audit(package, document)
            errors.extend(f"{record['id']}: {error}" for error in audit_errors)
            if audit_errors:
                continue
        else:
            errors.append(
                f"{record['id']}: accepted package is not audited; run Phase 3 with a "
                "different model, or build with --allow-unaudited and treat the corpus "
                "as provisional"
            )
            continue

        publication_key = document["publication_key"]
        if publication_key in seen_publication_keys:
            errors.append(
                f"duplicate publication_key {publication_key}: "
                f"{seen_publication_keys[publication_key]} and {record['id']}"
            )
        seen_publication_keys[publication_key] = record["id"]

        card_ids = []
        for card in sorted(document["cards"], key=lambda item: item["card_id"]):
            card_id = card["card_id"]
            if card_id in seen_card_ids:
                errors.append(
                    f"duplicate card_id {card_id}: {seen_card_ids[card_id]} and {record['id']}"
                )
            seen_card_ids[card_id] = record["id"]
            card_ids.append(card_id)
            metadata = {
                "input_id": record["id"],
                "publication_key": publication_key,
                "genes": sorted(set(card.get("genes", []))),
                "diseases": sorted(set(card.get("diseases") or [])),
                "category": card.get("category"),
                "evidence_tier": card.get("evidence_tier"),
                "escalates_to": card.get("escalates_to"),
            }
            card_index[card_id] = metadata
            for gene in metadata["genes"]:
                add(by_gene, gene, card_id)
            for disease in metadata["diseases"]:
                add(by_disease, disease, card_id)
            add(by_category, metadata["category"], card_id)
            add(by_tier, metadata["evidence_tier"], card_id)
            if metadata["escalates_to"]:
                add(by_escalation, metadata["escalates_to"], card_id)

        citation = document.get("citation", {})
        if citation.get("year") is not None:
            add(by_year, str(citation["year"]), publication_key)
        add(by_type, document.get("publication_type", "other"), publication_key)

        source = {
            "input_id": record["id"],
            "markdown_path": record["markdown_path"],
            "source_filename": record.get("source_filename"),
            "source_sha256": record.get("sha256"),
            "markdown_sha256": sha256_file(markdown_path),
            "doi_from_input_index": record.get("doi") or None,
            "card_file": str(package_path),
            "quote_file_present": True,
            "audit": audit_summary,
            "audited": not args.allow_unaudited,
            "provisional": args.allow_unaudited,
            "extraction": extraction_report or None,
        }
        publications.append({"source": source, "document": document})
        paper_index[record["id"]] = {
            "status": "completed",
            "markdown_path": record["markdown_path"],
            "publication_key": publication_key,
            "citation_display": citation.get("display"),
            "genes": sorted(set(document.get("genes_covered", []))),
            "diseases": sorted(set(document.get("diseases_covered", []))),
            "card_ids": card_ids,
            "census_entries": document.get("census_entries"),
            "cards": len(card_ids),
        }

    unexpected = sorted(
        path.name for path in args.package_dir.glob(f"*.phase{args.after_phase}.json")
        if path.name not in known_outputs
    )
    errors.extend(f"unindexed per-paper output: {name}" for name in unexpected)
    if pending and not args.allow_incomplete:
        errors.append(f"{len(pending)} indexed publication(s) are pending")
    if errors:
        raise ValueError("\n".join(errors))

    generated_at = args.generated_at or datetime.now(timezone.utc).isoformat()
    corpus = {
        "corpus_version": "1.0",
        "schema_version": "2.0",
        "generated_at": generated_at,
        "audited": not args.allow_unaudited,
        "provisional": args.allow_unaudited,
        "counts": {
            "indexed_papers": len(records),
            "completed_papers": len(publications),
            "skipped_papers": len(skipped),
            "pending_papers": len(pending),
            "cards": sum(len(item["document"]["cards"]) for item in publications),
            "census_entries": sum(
                item["document"].get("census_entries", 0) for item in publications
            ),
        },
        "publications": sorted(publications, key=lambda item: item["source"]["input_id"]),
    }
    corpus_hash = sha256_bytes(canonical_bytes(corpus))
    index = {
        "index_version": "1.0",
        "generated_at": generated_at,
        "audited": not args.allow_unaudited,
        "provisional": args.allow_unaudited,
        "corpus_sha256": corpus_hash,
        "counts": corpus["counts"],
        "papers": {key: paper_index[key] for key in sorted(paper_index)},
        "cards": {key: card_index[key] for key in sorted(card_index)},
        "by_gene": sorted_postings(by_gene),
        "by_disease": sorted_postings(by_disease),
        "by_category": sorted_postings(by_category),
        "by_escalates_to": sorted_postings(by_escalation),
        "by_evidence_tier": sorted_postings(by_tier),
        "by_year": sorted_postings(by_year),
        "by_publication_type": sorted_postings(by_type),
        "skipped": {key: skipped[key] for key in sorted(skipped)},
    }
    report = {
        "status": "ok",
        "generated_at": generated_at,
        "audited": not args.allow_unaudited,
        "provisional": args.allow_unaudited,
        "input_index": str(args.input_index),
        "counts": corpus["counts"],
        "pending_input_ids": sorted(pending),
        "corpus_sha256": corpus_hash,
        "extraction_ratio": (
            round(corpus["counts"]["cards"] / corpus["counts"]["census_entries"], 2)
            if corpus["counts"]["census_entries"] else None
        ),
    }
    return corpus, index, report


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--input-index", type=Path, required=True)
    parser.add_argument("--markdown-dir", type=Path, required=True)
    parser.add_argument("--phase1-dir", type=Path, default=Path("output/phase1"))
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--after-phase", type=int, choices=(2, 3), required=True)
    parser.add_argument("--reports-dir", type=Path, default=Path("output/reports"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--allow-incomplete", action="store_true",
                        help="build with publications still pending")
    parser.add_argument("--allow-unaudited", action="store_true",
                        help="build without Phase 3; the corpus is provisional")
    parser.add_argument("--generated-at", help=argparse.SUPPRESS)
    args = parser.parse_args()

    try:
        corpus, index, report = build(args)
        atomic_write_json(corpus, args.output_dir / "nel.corpus.json")
        atomic_write_json(index, args.output_dir / "nel.index.json")
        atomic_write_json(report, args.reports_dir / "build-report.json")
    except (OSError, ValueError) as exc:
        sys.exit(f"BUILD FAILED:\n{exc}")

    print(
        "OK: built "
        f"{report['counts']['completed_papers']} publication(s), "
        f"{report['counts']['cards']} card(s) from "
        f"{report['counts']['census_entries']} census entr(ies), "
        f"{report['counts']['skipped_papers']} skipped, "
        f"{report['counts']['pending_papers']} pending"
    )
    if report["extraction_ratio"] is not None:
        print(f"Corpus-wide extraction ratio: {report['extraction_ratio']}")
    if args.allow_unaudited:
        print("WARNING: built with --allow-unaudited. This corpus is provisional.")


if __name__ == "__main__":
    main()
