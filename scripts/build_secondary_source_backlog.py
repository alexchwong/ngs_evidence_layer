#!/usr/bin/env python3
"""Build a curator backlog from removed Phase 3-failed secondary-source cards."""
import argparse
import copy
import json
import os
import re
import tempfile
import unicodedata
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import ingest_artifacts


DEFAULT_ARCHIVE_DIR = Path("archive")
DEFAULT_CORPUS = Path("output/corpus/nel.corpus.json")
DEFAULT_OUTPUT_DIR = Path("curation")


def read_json(path, label="JSON"):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read {label} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid {label} in {path}: {exc}") from exc


def canonical_bytes(document):
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def normalize_doi(value):
    text = str(value or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    return text


def normalize_title(value):
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def title_year_identity(citation):
    title = normalize_title(citation.get("title"))
    year = citation.get("year")
    if title and isinstance(year, int):
        return title, year
    return None


def citation_identity(citation):
    doi = normalize_doi(citation.get("doi"))
    if doi:
        return "doi", doi
    title_year = title_year_identity(citation)
    if title_year:
        return "title_year", *title_year
    display = " ".join(str(citation.get("display") or "").casefold().split())
    return "display", display


def corpus_identities(corpus):
    dois = set()
    titles = set()
    for publication in corpus.get("publications", []):
        citation = publication.get("document", {}).get("citation", {})
        doi = normalize_doi(citation.get("doi"))
        if doi:
            dois.add(doi)
        title_year = title_year_identity(citation)
        if title_year:
            titles.add(title_year)
    return dois, titles


def source_is_in_corpus(citation, doi_set, title_year_set):
    doi = normalize_doi(citation.get("doi"))
    if doi and doi in doi_set:
        return True
    title_year = title_year_identity(citation)
    return bool(title_year and title_year in title_year_set)


def citation_score(citation):
    populated = sum(
        bool(citation.get(field))
        for field in ("authors", "title", "journal", "year", "volume", "issue", "pages", "display", "doi")
    )
    return populated, len(str(citation.get("display") or "")), json.dumps(citation, sort_keys=True, ensure_ascii=False)


def representative_citation(citations):
    return copy.deepcopy(max(citations, key=citation_score))


def archive_candidate(folder):
    metadata_path = folder / "metadata.json"
    final_path = folder / "paper.final.json"
    if not metadata_path.is_file() or not final_path.is_file():
        missing = [
            name for name, path in (("metadata", metadata_path), ("final", final_path))
            if not path.is_file()
        ]
        return None, f"missing {', '.join(missing)}"
    try:
        final = read_json(final_path, "final")
        approved_round = (final.get("audit") or {}).get("approved_round")
        if isinstance(approved_round, int):
            provisional_path = ingest_artifacts.resolve_phase_any_revision_for_round(
                folder, "provisional", approved_round
            )
            review_path = ingest_artifacts.resolve_phase_any_revision_for_round(
                folder, "review", approved_round
            )
        else:
            # Compatibility for old curator fixtures and very early archives.
            provisional_path = folder / "paper.provisional-001.json"
            review_path = folder / "paper.review-001.json"
        required = {
            "metadata": metadata_path,
            "provisional": provisional_path,
            "review": review_path,
            "final": final_path,
        }
        missing = [
            name for name, path in required.items()
            if path is None or not path.is_file()
        ]
        if missing:
            return None, f"missing {', '.join(missing)}"
        loaded = {name: (final if name == "final" else read_json(path, name)) for name, path in required.items()}
    except ValueError as exc:
        return None, str(exc)
    return loaded, None


def extract_removed_secondary_cards(folder, loaded):
    metadata = loaded["metadata"]
    provisional = loaded["provisional"]
    review = loaded["review"]
    final = loaded["final"]

    provisional_cards = {card.get("card_id"): card for card in provisional.get("cards", [])}
    final_ids = {card.get("card_id") for card in final.get("cards", [])}
    source_publication = {
        "publication_key": metadata.get("publication_key") or folder.name,
        "citation": copy.deepcopy(metadata.get("citation") or {}),
    }

    candidates = []
    for result in review.get("card_results", []):
        if result.get("verdict") != "fail":
            continue
        card_id = result.get("card_id")
        card = provisional_cards.get(card_id)
        if not card or card_id in final_ids:
            continue
        secondary = card.get("secondary_citation")
        if not isinstance(secondary, dict):
            continue
        details = result.get("details") or {}
        candidates.append(
            {
                "secondary_citation": copy.deepcopy(secondary),
                "source_publication": source_publication,
                "card": {
                    key: copy.deepcopy(card.get(key))
                    for key in (
                        "card_id",
                        "category",
                        "genes",
                        "diseases",
                        "interpretation",
                        "locator",
                        "evidence_tier",
                    )
                },
                "review": {
                    key: copy.deepcopy(details.get(key))
                    for key in ("failure_type", "reason", "defensibility", "suggested_action")
                    if details.get(key) is not None
                },
            }
        )
    return candidates


def candidate_sort_key(candidate):
    source = candidate["source_publication"]
    citation = source.get("citation") or {}
    return (
        normalize_title(citation.get("title")),
        citation.get("year") or 0,
        source.get("publication_key") or "",
        candidate["card"].get("card_id") or "",
    )


def group_sort_key(group):
    citation = group["secondary_citation"]
    return (-group["card_count"], citation.get("year") or 0, normalize_title(citation.get("title")), citation.get("display") or "")


def build_backlog(archive_dir=DEFAULT_ARCHIVE_DIR, corpus_path=DEFAULT_CORPUS):
    archive_dir = Path(archive_dir)
    corpus_path = Path(corpus_path)
    if not archive_dir.is_dir():
        raise ValueError(f"archive directory not found: {archive_dir}")
    corpus = read_json(corpus_path, "corpus")
    doi_set, title_year_set = corpus_identities(corpus)

    candidates = []
    skipped = []
    scanned = 0
    for folder in sorted(path for path in archive_dir.iterdir() if path.is_dir()):
        loaded, error = archive_candidate(folder)
        if loaded is None:
            # Non-publication support folders are ignored only when they contain no
            # Phase 1-4 artefact names; otherwise surface an incomplete archive.
            if not any(folder.glob("paper.*.json")) and not (folder / "metadata.json").exists():
                continue
            skipped.append({"archive": folder.name, "reason": error})
            continue
        scanned += 1
        candidates.extend(extract_removed_secondary_cards(folder, loaded))

    grouped = defaultdict(list)
    excluded_cards = 0
    excluded_sources = set()
    for candidate in candidates:
        citation = candidate["secondary_citation"]
        if source_is_in_corpus(citation, doi_set, title_year_set):
            excluded_cards += 1
            excluded_sources.add(citation_identity(citation))
            continue
        grouped[citation_identity(citation)].append(candidate)

    sources = []
    for identity, group_candidates in grouped.items():
        group_candidates.sort(key=candidate_sort_key)
        citation = representative_citation([item["secondary_citation"] for item in group_candidates])
        source_publications = {
            item["source_publication"]["publication_key"] for item in group_candidates
        }
        sources.append(
            {
                "source_id": list(identity),
                "secondary_citation": citation,
                "card_count": len(group_candidates),
                "referenced_by_publications": len(source_publications),
                "removed_cards": [
                    {
                        "source_publication": item["source_publication"],
                        "card": item["card"],
                        "review": item["review"],
                    }
                    for item in group_candidates
                ],
            }
        )
    sources.sort(key=group_sort_key)

    return {
        "schema_version": "1.0",
        "corpus_generated_at": corpus.get("generated_at"),
        "counts": {
            "archive_publications_scanned": scanned,
            "removed_secondary_cards_found": len(candidates),
            "outstanding_source_papers": len(sources),
            "outstanding_removed_cards": sum(source["card_count"] for source in sources),
            "source_papers_already_in_corpus": len(excluded_sources),
            "removed_cards_excluded_already_in_corpus": excluded_cards,
            "archive_folders_skipped": len(skipped),
        },
        "sources": sources,
        "skipped_archives": skipped,
    }


def one_line(value):
    return " ".join(str(value or "").split())


def citation_label(citation):
    display = one_line(citation.get("display"))
    if display:
        return display
    title = one_line(citation.get("title")) or "Untitled source"
    year = citation.get("year")
    return f"{title} ({year})" if year else title


def render_markdown(backlog):
    counts = backlog["counts"]
    lines = [
        "# Secondary-source curation backlog",
        "",
        (
            f"Outstanding: **{counts['outstanding_source_papers']} source papers** supporting "
            f"**{counts['outstanding_removed_cards']} removed cards**. "
            f"Excluded because the cited source is already in the corpus: "
            f"**{counts['removed_cards_excluded_already_in_corpus']} cards**."
        ),
        "",
    ]
    if not backlog["sources"]:
        lines.extend(["No outstanding secondary-source papers were found.", ""])
    for source in backlog["sources"]:
        citation = source["secondary_citation"]
        title = one_line(citation.get("title")) or citation_label(citation)
        year = citation.get("year")
        heading = f"## {title}" + (f" ({year})" if year else "")
        lines.extend(
            [
                heading,
                "",
                f"**Candidate source:** {citation_label(citation)}",
                "",
                (
                    f"Referenced by **{source['card_count']} removed cards** from "
                    f"**{source['referenced_by_publications']} curated papers**."
                ),
                "",
            ]
        )
        for item in source["removed_cards"]:
            origin = item["source_publication"]
            origin_citation = origin.get("citation") or {}
            lines.extend(
                [
                    f"### {origin.get('publication_key') or 'unknown publication'}",
                    "",
                    f"- Curated paper: {citation_label(origin_citation)}",
                    f"- Card: `{one_line(item['card'].get('card_id'))}`",
                    f"- Category: {one_line(item['card'].get('category'))}",
                    f"- Genes: {', '.join(item['card'].get('genes') or [])}",
                    f"- Diseases: {', '.join(item['card'].get('diseases') or []) or 'none'}",
                    f"- Interpretation: {one_line(item['card'].get('interpretation'))}",
                ]
            )
            review = item.get("review") or {}
            if review.get("failure_type"):
                lines.append(f"- Phase 3 failure: `{one_line(review['failure_type'])}` — {one_line(review.get('reason'))}")
            elif review.get("reason"):
                lines.append(f"- Phase 3 failure: {one_line(review['reason'])}")
            if review.get("defensibility"):
                lines.append(f"- Defensibility: {one_line(review['defensibility'])}")
            action = review.get("suggested_action") or {}
            if action:
                lines.append(
                    f"- Suggested action: `{one_line(action.get('category'))}` — {one_line(action.get('detail'))}"
                )
            lines.append("")
    if backlog["skipped_archives"]:
        lines.extend(["## Skipped archive folders", ""])
        for skipped in backlog["skipped_archives"]:
            lines.append(f"- `{skipped['archive']}`: {one_line(skipped['reason'])}")
        lines.append("")
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-dir", type=Path, default=DEFAULT_ARCHIVE_DIR)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        backlog = build_backlog(args.archive_dir, args.corpus)
        json_path = args.output_dir / "secondary-source-backlog.json"
        markdown_path = args.output_dir / "secondary-source-backlog.md"
        atomic_write(json_path, canonical_bytes(backlog))
        atomic_write(markdown_path, render_markdown(backlog).encode("utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"SECONDARY-SOURCE BACKLOG FAILED: {exc}")

    counts = backlog["counts"]
    print(
        "Backlog: "
        f"{counts['outstanding_source_papers']} source papers / "
        f"{counts['outstanding_removed_cards']} removed cards; "
        f"excluded {counts['removed_cards_excluded_already_in_corpus']} cards already represented in corpus"
    )
    if counts["archive_folders_skipped"]:
        print(f"Warning: skipped {counts['archive_folders_skipped']} incomplete archive folders")
    print(f"Wrote {json_path}")
    print(f"Wrote {markdown_path}")


if __name__ == "__main__":
    main()
