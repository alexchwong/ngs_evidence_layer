#!/usr/bin/env python3
"""Build the distributable corpus from independently accepted final packages."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
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


def atomic_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
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


def acceptance_version_provenance(envelope):
    """Return original, complete, and latest acceptance-version provenance."""
    original = envelope["accepted_in_version"]
    history = []

    def append_version(version, label):
        if not isinstance(version, str) or not version:
            raise ValueError(f"accepted package has an invalid {label}")
        if version not in history:
            history.append(version)

    append_version(original, "accepted_in_version")
    recorded_history = envelope.get("version_history") or []
    if not isinstance(recorded_history, list):
        raise ValueError("accepted package version_history is not an array")
    for version in recorded_history:
        append_version(version, "version_history entry")

    latest_overwrite = envelope.get("latest_version")
    if latest_overwrite is not None:
        append_version(latest_overwrite, "latest_version")

    modifications = []
    for field in ("supplements", "revisions", "redos"):
        entries = envelope.get(field) or []
        if not isinstance(entries, list):
            raise ValueError(f"accepted package {field} is not an array")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"accepted package {field} contains a non-object entry")
            try:
                accepted_time = datetime.fromisoformat(entry.get("accepted_at"))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"accepted package {field} entry has an invalid accepted_at"
                ) from exc
            modifications.append((accepted_time, field, entry))
    for _accepted_time, field, entry in sorted(
        modifications, key=lambda item: (item[0], item[1])
    ):
        append_version(entry.get("accepted_in_version"), f"{field} accepted_in_version")

    return {
        "accepted_in_version": original,
        "acceptance_version_history": history,
        "latest_accepted_in_version": history[-1],
    }


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
    envelope["schema_version"] = "1.2"
    envelope["accepted_at"] = accepted_at
    envelope["accepted_at_source"] = "file-mtime"
    atomic_json(final_path, envelope)


def markdown_quote(text):
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


def render_cards_markdown(document):
    lines = [
        f"# {document['citation']['display']}",
        "",
        f"**Publication key:** `{document['publication_key']}`",
        "",
    ]
    for card in document["cards"]:
        lines.extend(
            [
                f"## {card['card_id']}",
                "",
                f"**Category:** {card['category']}",
                "",
                f"**Genes:** {', '.join(card['genes'])}",
                "",
                f"**Diseases:** {', '.join(card['diseases']) or '—'}",
                "",
                f"**Evidence tier:** {card['evidence_tier']}",
                "",
                f"**Locator:** {card['locator']}",
                "",
            ]
        )
        if card.get("secondary_citation"):
            lines.extend(
                [
                    f"**Secondary citation:** {card['secondary_citation']['display']}",
                    "",
                ]
            )
        lines.extend(["### Interpretation", "", card["interpretation"], ""])
    return "\n".join(lines).rstrip() + "\n"


def render_evidence_markdown(document, evidence_by_card):
    sections = []
    for card in document["cards"]:
        evidence = evidence_by_card[card["card_id"]]
        lines = [
            f"# {card['card_id']}",
            "",
            "## Interpretation",
            "",
            card["interpretation"],
            "",
            "## Evidence",
            "",
        ]
        for fragment in evidence["fragments"]:
            lines.extend(
                [
                    f"**{fragment['fragment_id']} · {fragment['role']} · {fragment['locator']}**",
                    "",
                    markdown_quote(fragment["quote"]),
                    "",
                ]
            )
        sections.append("\n".join(lines).rstrip())
    return "\n\n---\n\n".join(sections) + ("\n" if sections else "")


def build_markdown_documents(corpus, accept_dir):
    cards_documents = {}
    evidence_documents = {}
    for publication in corpus["publications"]:
        document = publication["document"]
        publication_key = document["publication_key"]
        envelope = validation.read_json(
            accept_dir / f"{publication_key}.final.json", "accepted package"
        )
        package = envelope["final"]
        package_cards = {card["card_id"]: card for card in package["cards"]}
        evidence_by_card = {item["card_id"]: item for item in package["evidence"]}
        for card in document["cards"]:
            card_id = card["card_id"]
            accepted_card = package_cards.get(card_id)
            if accepted_card is None:
                raise ValueError(f"accepted package is missing incorporated card {card_id}")
            if accepted_card["interpretation"] != card["interpretation"]:
                raise ValueError(f"accepted package interpretation differs for {card_id}")
            if card_id not in evidence_by_card:
                raise ValueError(f"accepted package is missing evidence for {card_id}")
        filename = f"{publication_key}.md"
        cards_documents[filename] = render_cards_markdown(document)
        evidence_documents[filename] = render_evidence_markdown(
            document, evidence_by_card
        )
    return cards_documents, evidence_documents


def replace_markdown_documents(directory, documents):
    """Replace generated Markdown only after the complete new view is staged."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if not documents:
        return

    staging = Path(
        tempfile.mkdtemp(prefix=f".{directory.name}.new.", dir=directory.parent)
    )
    backup = None
    try:
        for path in directory.iterdir():
            if path.is_file() and path.suffix == ".md":
                continue
            destination = staging / path.name
            if path.is_dir():
                shutil.copytree(path, destination)
            else:
                shutil.copy2(path, destination)

        for filename, text in sorted(documents.items()):
            if Path(filename).name != filename:
                raise ValueError(f"unsafe Markdown output filename: {filename}")
            atomic_text(staging / filename, text)

        backup = Path(
            tempfile.mkdtemp(prefix=f".{directory.name}.old.", dir=directory.parent)
        )
        backup.rmdir()
        os.replace(directory, backup)
        try:
            os.replace(staging, directory)
        except Exception:
            os.replace(backup, directory)
            backup = None
            raise
        shutil.rmtree(backup)
        backup = None
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if backup is not None and backup.exists():
            shutil.rmtree(backup)


def build_card_outputs(corpus_path, report_path):
    """Run every card-output builder against the newly incorporated corpus."""
    scripts_dir = Path(__file__).resolve().parent
    output_dir = report_path.parent
    for builder in sorted(scripts_dir.glob("build_card_*.py")):
        output_name = builder.stem.removeprefix("build_").replace("_", "-") + ".html"
        try:
            subprocess.run(
                [
                    sys.executable,
                    str(builder),
                    "--corpus",
                    str(corpus_path),
                    "--output",
                    str(output_dir / output_name),
                ],
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            raise ValueError(f"{builder.name} failed with exit status {exc.returncode}") from exc


def build(args):
    final_paths = sorted(args.accept_dir.glob("*.final.json"))
    census_paths = {
        path.name.removesuffix(".census.json"): path
        for path in args.accept_dir.glob("*.census.json")
    }
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
            rejected[publication_key] = [
                "accepted filename does not match metadata publication_key"
            ]
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
            rejected[loser_id] = [
                f"duplicate publication_key {key}: superseded by {winner_id}"
            ]
            print(
                f"warning: duplicate publication_key {key}: "
                f"{loser_id} superseded by {winner_id}",
                file=sys.stderr,
            )
    for publication_key, envelope, _census, _warnings, _report in selected:
        for card in envelope["final"]["cards"]:
            card_id = card["card_id"]
            if card_id in card_owners:
                global_errors.append(
                    f"duplicate card_id {card_id}: "
                    f"{card_owners[card_id]} and {publication_key}"
                )
            card_owners[card_id] = publication_key
    if global_errors:
        raise ValueError("\n".join(global_errors))
    by_gene, by_disease, by_category = (
        defaultdict(list),
        defaultdict(list),
        defaultdict(list),
    )
    by_tier, by_year, by_type = (defaultdict(list) for _ in range(3))
    by_accepted_in_version = defaultdict(list)
    publications, paper_index, card_index = [], {}, {}
    census_total = 0
    for publication_key, envelope, census, warnings, report in selected:
        metadata, package = envelope["metadata"], envelope["final"]
        acceptance_provenance = acceptance_version_provenance(envelope)
        latest_accepted_in_version = acceptance_provenance[
            "latest_accepted_in_version"
        ]
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
        if package.get("paper_nickname") is not None:
            document["paper_nickname"] = package["paper_nickname"]
        card_ids = []
        for card in cards:
            card_id = card["card_id"]
            exact_diseases = list(card["diseases"])
            disease_ancestors = vocab.disease_ancestors(exact_diseases)
            card["disease_ancestors"] = disease_ancestors
            card_ids.append(card_id)
            card_index[card_id] = {
                "input_id": metadata["paper_id"],
                "publication_key": metadata["publication_key"],
                "genes": sorted(card["genes"]),
                "diseases": sorted(exact_diseases),
                "disease_ancestors": disease_ancestors,
                "category": card["category"],
                "evidence_tier": card["evidence_tier"],
            }
            for gene in card["genes"]:
                add(by_gene, gene, card_id)
            for disease in (*exact_diseases, *disease_ancestors):
                add(by_disease, disease, card_id)
            add(by_category, card["category"], card_id)
            add(by_tier, card["evidence_tier"], card_id)
        year = metadata["citation"].get("year")
        if year is not None:
            add(by_year, str(year), metadata["publication_key"])
        add(by_type, package["publication_type"], metadata["publication_key"])
        add(
            by_accepted_in_version,
            latest_accepted_in_version,
            metadata["publication_key"],
        )
        source = {
            "input_id": metadata["paper_id"],
            "source_filename": metadata["source_filename"],
            "source_sha256": metadata["source_sha256"],
            "markdown_sha256": metadata["markdown_sha256"],
            "acceptance_path": envelope["acceptance_path"],
            "audit": package["audit"],
            "extraction": report,
            "warnings": warnings,
        }
        publications.append({"source": source, "document": document})
        paper_index[publication_key] = {
            "status": "completed",
            "publication_key": metadata["publication_key"],
            **acceptance_provenance,
            "citation_display": metadata["citation"]["display"],
            "genes": sorted(package["genes_covered"]),
            "diseases": sorted(package["diseases_covered"]),
            "card_ids": card_ids,
            "census_entries": len(census["entries"]),
            "cards": len(card_ids),
        }
        if package.get("paper_nickname") is not None:
            paper_index[publication_key]["paper_nickname"] = package["paper_nickname"]
        census_total += len(census["entries"])
    generated_at = args.generated_at or datetime.now(timezone.utc).isoformat()
    counts = {
        "completed_papers": len(publications),
        "rejected_papers": len(rejected),
        "cards": len(card_index),
        "census_entries": census_total,
    }
    corpus = {
        "corpus_version": "1.2",
        "schema_version": "3.1",
        "generated_at": generated_at,
        "counts": counts,
        "publications": sorted(
            publications, key=lambda item: item["source"]["input_id"]
        ),
    }
    digest = hashlib.sha256(canonical_bytes(corpus)).hexdigest()
    index = {
        "index_version": "1.4",
        "generated_at": generated_at,
        "corpus_sha256": digest,
        "counts": counts,
        "papers": {key: paper_index[key] for key in sorted(paper_index)},
        "cards": {key: card_index[key] for key in sorted(card_index)},
        "by_gene": postings(by_gene),
        "by_disease": postings(by_disease),
        "by_category": postings(by_category),
        "by_evidence_tier": postings(by_tier),
        "by_year": postings(by_year),
        "by_publication_type": postings(by_type),
        "by_accepted_in_version": postings(by_accepted_in_version),
        "rejected": {key: rejected[key] for key in sorted(rejected)},
    }
    report = {
        "status": "ok",
        "generated_at": generated_at,
        "counts": counts,
        "rejected": index["rejected"],
        "corpus_sha256": digest,
        "extraction_ratio": (
            round(counts["cards"] / census_total, 2) if census_total else None
        ),
    }
    return corpus, index, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accept-dir", type=Path, default=Path("accept"))
    parser.add_argument("--output-dir", type=Path, default=Path("output/corpus"))
    parser.add_argument("--cards-dir", type=Path, default=Path("cards"))
    parser.add_argument("--evidence-dir", type=Path, default=Path("evidence"))
    parser.add_argument(
        "--report", type=Path, default=Path("output/reports/build-report.json")
    )
    parser.add_argument("--generated-at", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        corpus, index, report = build(args)
        cards_documents, evidence_documents = build_markdown_documents(
            corpus, args.accept_dir
        )
        atomic_json(args.output_dir / "nel.corpus.json", corpus)
        atomic_json(args.output_dir / "nel.index.json", index)
        atomic_json(args.report, report)
        replace_markdown_documents(args.cards_dir, cards_documents)
        replace_markdown_documents(args.evidence_dir, evidence_documents)
        build_card_outputs(args.output_dir / "nel.corpus.json", args.report)
    except (OSError, ValueError) as exc:
        sys.exit(f"INCORPORATION FAILED:\n{exc}")
    print(
        f"INCORPORATED: {report['counts']['completed_papers']} paper(s), "
        f"{report['counts']['cards']} card(s)"
    )
    print(f"Rejected: {report['counts']['rejected_papers']}")


if __name__ == "__main__":
    main()
