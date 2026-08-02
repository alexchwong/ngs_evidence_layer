#!/usr/bin/env python3
"""Build the distributable corpus from independently accepted final packages."""
import argparse
import hashlib
import json
import os
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import package_validation as validation


def canonical_bytes(document):
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def atomic_json(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(canonical_bytes(document))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def postings(mapping):
    return {key: sorted(set(values)) for key, values in sorted(mapping.items())}


def add(mapping, key, value):
    mapping[key].append(value)


def load_pair(final_path, census_path):
    envelope = validation.read_json(final_path, "accepted package")
    census = validation.read_json(census_path, "accepted census")
    errors = validation.schema_errors(
        envelope, "accepted_package_schema.json", "accepted package"
    )
    if errors:
        raise ValueError("\n".join(errors))
    metadata = envelope["metadata"]
    final = envelope["final"]
    errors.extend(validation.validate_census(census, metadata))
    package_errors, warnings, report = validation.validate_package(
        final, metadata, census, source_text=None, require_final=True
    )
    errors.extend(package_errors)
    if errors:
        raise ValueError("\n".join(errors))
    return envelope, census, warnings, report


def build(args):
    final_paths = sorted(args.accept_dir.glob("*.final.json"))
    census_paths = {path.name.removesuffix(".census.json"): path for path in args.accept_dir.glob("*.census.json")}
    final_ids = {path.name.removesuffix(".final.json") for path in final_paths}
    rejected = {}
    accepted = []

    for orphan in sorted(set(census_paths) - final_ids):
        rejected[orphan] = ["accepted census has no paired final package"]
    for final_path in final_paths:
        paper_id = final_path.name.removesuffix(".final.json")
        census_path = census_paths.get(paper_id)
        if census_path is None:
            rejected[paper_id] = ["accepted final package has no paired census"]
            continue
        try:
            envelope, census, warnings, report = load_pair(final_path, census_path)
        except (OSError, ValueError) as exc:
            rejected[paper_id] = str(exc).splitlines()
            continue
        if envelope["metadata"]["paper_id"] != paper_id:
            rejected[paper_id] = ["accepted filename does not match metadata paper_id"]
            continue
        accepted.append((paper_id, envelope, census, warnings, report))

    key_owners = {}
    card_owners = {}
    global_errors = []
    for paper_id, envelope, _census, _warnings, _report in accepted:
        key = envelope["metadata"]["publication_key"]
        if key in key_owners:
            global_errors.append(f"duplicate publication_key {key}: {key_owners[key]} and {paper_id}")
        key_owners[key] = paper_id
        for card in envelope["final"]["cards"]:
            card_id = card["card_id"]
            if card_id in card_owners:
                global_errors.append(f"duplicate card_id {card_id}: {card_owners[card_id]} and {paper_id}")
            card_owners[card_id] = paper_id
    if global_errors:
        raise ValueError("\n".join(global_errors))

    by_gene, by_disease, by_category = defaultdict(list), defaultdict(list), defaultdict(list)
    by_escalation, by_tier, by_year, by_type = (defaultdict(list) for _ in range(4))
    publications, paper_index, card_index = [], {}, {}
    census_total = 0
    for paper_id, envelope, census, warnings, report in accepted:
        metadata, package = envelope["metadata"], envelope["final"]
        cards = sorted(package["cards"], key=lambda card: card["card_id"])
        document = {
            "publication_key": metadata["publication_key"],
            "citation": metadata["citation"],
            "publication_type": metadata["publication_type"],
            "extraction_date": package["extraction_date"],
            "extraction_model": package["extraction_model"],
            "genes_covered": package["genes_covered"],
            "diseases_covered": package["diseases_covered"],
            "census_entries": package["census_entries"],
            "cards": cards,
        }
        card_ids = []
        for card in cards:
            card_id = card["card_id"]
            card_ids.append(card_id)
            card_index[card_id] = {
                "input_id": paper_id, "publication_key": metadata["publication_key"],
                "genes": sorted(card["genes"]), "diseases": sorted(card["diseases"]),
                "category": card["category"], "evidence_tier": card["evidence_tier"],
                "escalates_to": card["escalates_to"],
            }
            for gene in card["genes"]: add(by_gene, gene, card_id)
            for disease in card["diseases"]: add(by_disease, disease, card_id)
            add(by_category, card["category"], card_id)
            add(by_tier, card["evidence_tier"], card_id)
            if card["escalates_to"]: add(by_escalation, card["escalates_to"], card_id)
        year = metadata["citation"].get("year")
        if year is not None: add(by_year, str(year), metadata["publication_key"])
        add(by_type, metadata["publication_type"], metadata["publication_key"])
        source = {
            "input_id": paper_id, "source_filename": metadata["source_filename"],
            "source_sha256": metadata["source_sha256"], "markdown_sha256": metadata["markdown_sha256"],
            "acceptance_path": envelope["acceptance_path"],
            "audit": package["audit"], "extraction": report, "warnings": warnings,
        }
        publications.append({"source": source, "document": document})
        paper_index[paper_id] = {
            "status": "completed", "publication_key": metadata["publication_key"],
            "citation_display": metadata["citation"]["display"], "genes": sorted(package["genes_covered"]),
            "diseases": sorted(package["diseases_covered"]), "card_ids": card_ids,
            "census_entries": len(census["entries"]), "cards": len(card_ids),
        }
        census_total += len(census["entries"])

    generated_at = args.generated_at or datetime.now(timezone.utc).isoformat()
    counts = {"completed_papers": len(publications), "rejected_papers": len(rejected), "cards": len(card_index), "census_entries": census_total}
    corpus = {"corpus_version": "1.1", "schema_version": "3.0", "generated_at": generated_at, "counts": counts, "publications": sorted(publications, key=lambda item: item["source"]["input_id"])}
    digest = hashlib.sha256(canonical_bytes(corpus)).hexdigest()
    index = {
        "index_version": "1.1", "generated_at": generated_at, "corpus_sha256": digest, "counts": counts,
        "papers": {key: paper_index[key] for key in sorted(paper_index)},
        "cards": {key: card_index[key] for key in sorted(card_index)},
        "by_gene": postings(by_gene), "by_disease": postings(by_disease), "by_category": postings(by_category),
        "by_escalates_to": postings(by_escalation), "by_evidence_tier": postings(by_tier),
        "by_year": postings(by_year), "by_publication_type": postings(by_type),
        "rejected": {key: rejected[key] for key in sorted(rejected)},
    }
    report = {
        "status": "ok", "generated_at": generated_at, "counts": counts,
        "rejected": index["rejected"], "corpus_sha256": digest,
        "extraction_ratio": round(counts["cards"] / census_total, 2) if census_total else None,
    }
    return corpus, index, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accept-dir", type=Path, default=Path("accept"))
    parser.add_argument("--output-dir", type=Path, default=Path("output/corpus"))
    parser.add_argument("--report", type=Path, default=Path("output/reports/build-report.json"))
    parser.add_argument("--generated-at", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        corpus, index, report = build(args)
        atomic_json(args.output_dir / "nel.corpus.json", corpus)
        atomic_json(args.output_dir / "nel.index.json", index)
        atomic_json(args.report, report)
    except (OSError, ValueError) as exc:
        sys.exit(f"INCORPORATION FAILED:\n{exc}")
    print(f"INCORPORATED: {report['counts']['completed_papers']} paper(s), {report['counts']['cards']} card(s)")
    print(f"Rejected: {report['counts']['rejected_papers']}")


if __name__ == "__main__":
    main()