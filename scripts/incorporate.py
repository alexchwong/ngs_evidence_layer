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
import vocab


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


def normalize_accepted_at(final_path):
    """Persist a stable mtime-derived acceptance time for a legacy manual drop."""
    envelope = validation.read_json(final_path, "accepted package")
    if "accepted_at" in envelope:
        return
    if envelope.get("acceptance_path") != "manual-or-unverified":
        raise ValueError("accepted_at is missing from a non-manual accepted package")
    accepted_at = datetime.fromtimestamp(final_path.stat().st_mtime, timezone.utc).isoformat()
    envelope["schema_version"] = "1.1"
    envelope["accepted_at"] = accepted_at
    envelope["accepted_at_source"] = "file-mtime"
    atomic_json(final_path, envelope)


def build(args):
    final_paths = sorted(args.accept_dir.glob("*.final.json"))
    census_paths = {path.name.removesuffix(".census.json"): path for path in args.accept_dir.glob("*.census.json")}
    final_ids = {path.name.removesuffix(".final.json") for path in final_paths}
    rejected = {}
    accepted = []

    for orphan in sorted(set(census_paths) - final_ids):
        rejected[orphan] = ["accepted census has no paired final package"]
    for final_path in final_paths:
        publication_key = final_path.name.removesuffix(".final.json")
        census_path = census_paths.get(publication_key)
        if census_path is None:
            rejected[publication_key] = ["accepted final package has no paired census"]
            continue
        try:
            normalize_accepted_at(final_path)
            envelope, census, warnings, report = load_pair(final_path, census_path)
        except (OSError, ValueError) as exc:
            rejected[publication_key] = str(exc).splitlines()
            continue
        if envelope["metadata"]["publication_key"] != publication_key:
            rejected[publication_key] = ["accepted filename does not match metadata publication_key"]
            continue
        accepted.append((publication_key, envelope, census, warnings, report))

    key_groups = defaultdict(list)
    card_owners = {}
    global_errors = []
    for item in accepted:
        _publication_key, envelope, _census, _warnings, _report = item
        key = envelope["metadata"]["publication_key"]
        key_groups[key].append(item)
    selected = []
    for key, group in sorted(key_groups.items()):
        ranked = sorted(
            group,
            key=lambda item: (datetime.fromisoformat(item[1]["accepted_at"]), item[0]),
        )
        winner = ranked[0]
        winner_id = winner[0]
        selected.append(winner)
        for loser in ranked[1:]:
            loser_id = loser[0]
            rejected[loser_id] = [f"duplicate publication_key {key}: superseded by {winner_id}"]
            print(f"warning: duplicate publication_key {key}: {loser_id} superseded by {winner_id}", file=sys.stderr)
    for publication_key, envelope, _census, _warnings, _report in selected:
        for card in envelope["final"]["cards"]:
            card_id = card["card_id"]
            if card_id in card_owners:
                global_errors.append(f"duplicate card_id {card_id}: {card_owners[card_id]} and {publication_key}")
            card_owners[card_id] = publication_key
    if global_errors:
        raise ValueError("\n".join(global_errors))

    by_gene, by_disease, by_category = defaultdict(list), defaultdict(list), defaultdict(list)
    by_tier, by_year, by_type = (defaultdict(list) for _ in range(3))
    publications, paper_index, card_index = [], {}, {}
    census_total = 0
    for publication_key, envelope, census, warnings, report in selected:
        metadata, package = envelope["metadata"], envelope["final"]
        cards = sorted(package["cards"], key=lambda card: card["card_id"])
        document = {
            "publication_key": metadata["publication_key"],
            "citation": metadata["citation"],
            "publication_type": package["publication_type"],
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
            exact_diseases = list(card["diseases"])
            disease_ancestors = vocab.disease_ancestors(exact_diseases)
            card["disease_ancestors"] = disease_ancestors
            card_ids.append(card_id)
            card_index[card_id] = {
                "input_id": metadata["paper_id"], "publication_key": metadata["publication_key"],
                "genes": sorted(card["genes"]), "diseases": sorted(exact_diseases),
                "disease_ancestors": disease_ancestors,
                "category": card["category"], "evidence_tier": card["evidence_tier"],
            }
            for gene in card["genes"]: add(by_gene, gene, card_id)
            for disease in (*exact_diseases, *disease_ancestors):
                add(by_disease, disease, card_id)
            add(by_category, card["category"], card_id)
            add(by_tier, card["evidence_tier"], card_id)
        year = metadata["citation"].get("year")
        if year is not None: add(by_year, str(year), metadata["publication_key"])
        add(by_type, package["publication_type"], metadata["publication_key"])
        source = {
            "input_id": metadata["paper_id"], "source_filename": metadata["source_filename"],
            "source_sha256": metadata["source_sha256"], "markdown_sha256": metadata["markdown_sha256"],
            "acceptance_path": envelope["acceptance_path"],
            "audit": package["audit"], "extraction": report, "warnings": warnings,
        }
        publications.append({"source": source, "document": document})
        paper_index[publication_key] = {
            "status": "completed", "publication_key": metadata["publication_key"],
            "citation_display": metadata["citation"]["display"], "genes": sorted(package["genes_covered"]),
            "diseases": sorted(package["diseases_covered"]), "card_ids": card_ids,
            "census_entries": len(census["entries"]), "cards": len(card_ids),
        }
        census_total += len(census["entries"])

    generated_at = args.generated_at or datetime.now(timezone.utc).isoformat()
    counts = {"completed_papers": len(publications), "rejected_papers": len(rejected), "cards": len(card_index), "census_entries": census_total}
    corpus = {"corpus_version": "1.2", "schema_version": "3.1", "generated_at": generated_at, "counts": counts, "publications": sorted(publications, key=lambda item: item["source"]["input_id"])}
    digest = hashlib.sha256(canonical_bytes(corpus)).hexdigest()
    index = {
        "index_version": "1.2", "generated_at": generated_at, "corpus_sha256": digest, "counts": counts,
        "papers": {key: paper_index[key] for key in sorted(paper_index)},
        "cards": {key: card_index[key] for key in sorted(card_index)},
        "by_gene": postings(by_gene), "by_disease": postings(by_disease), "by_category": postings(by_category),
        "by_evidence_tier": postings(by_tier),
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