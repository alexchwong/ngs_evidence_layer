#!/usr/bin/env python3
"""Derive publication keys and Vancouver display strings deterministically.

Corpus publication keys are human-readable identifiers derived from the original
source PDF filename. Bibliographic keys remain available for deduplicating secondary
citations that are not themselves corpus publications.

Two citation modes:

  primary    the publication being ingested. Authors, title and year are required,
             because a publication we are reading in full has no excuse for them.
  secondary  an upstream source cited by the publication but never itself ingested
             (decision 20). Built from whatever the publication's reference list
             supplies, which is frequently not much. Nothing is required beyond a
             single usable element; everything absent is named in
             citation_incomplete and carried, visible, into the reference list.
             This mode must not invent an author, a year or a journal to make the
             string look finished.
Usage:
  make_key.py --citation citation.json --source-filename paper.pdf
  make_key.py --authors "Dohner H" "Wei AH" --title "..." --journal Blood \\
              --year 2022 --volume 140 --issue 12 --pages 1345-1377 \\
              --source-filename 2022_dohner_eln_aml.pdf
  make_key.py --secondary --authors "Falini B" --title "Cytoplasmic nucleophosmin" \\
              --journal "N Engl J Med" --year 2005 --volume 352 --pages 254-266
"""
import argparse
import json
import re
import sys
from pathlib import Path
MAX_LISTED_AUTHORS = 6
CITATION_FIELDS = ("authors", "title", "journal", "year", "volume", "issue", "pages")


def slugify(value):
    if value is None or str(value).strip() == "":
        return "na"
    slug = re.sub(r"[^a-z0-9]+", "-", str(value).lower())
    return slug.strip("-") or "na"


def build_source_key(source_filename):
    """Return the canonical corpus key from the original source filename stem."""
    if source_filename is None or str(source_filename).strip() == "":
        raise ValueError("source_filename is required for a corpus publication key")
    stem = Path(str(source_filename)).stem
    key = slugify(stem)
    if key == "na":
        raise ValueError("source_filename must contain a usable filename stem")
    return key


def first_surname(authors):
    if not authors:
        return "na"
    parts = str(authors[0]).split()
    return parts[0] if parts else "na"


def start_page(pages):
    if not pages:
        return None
    return re.split(r"[-\u2013\u2014]", str(pages))[0].strip() or None


def build_display(citation):
    authors = citation.get("authors") or []
    if len(authors) > MAX_LISTED_AUTHORS:
        author_str = ", ".join(authors[:MAX_LISTED_AUTHORS]) + ", et al"
    else:
        author_str = ", ".join(authors)
    title = (citation.get("title") or "").rstrip(".")
    journal = citation.get("journal")
    year = citation.get("year")
    month = citation.get("month")
    volume = citation.get("volume")
    issue = citation.get("issue")
    pages = citation.get("pages")

    parts = []
    if author_str:
        parts.append(author_str + ".")
    if title:
        parts.append(title + ".")
    if journal:
        parts.append(str(journal).rstrip(".") + ".")
    tail = ""
    if year:
        tail = str(year)
        if month:
            tail += f" {month}"
        if volume:
            tail += f";{volume}"
            if issue:
                tail += f"({issue})"
            if pages:
                tail += f":{pages}"
        elif pages:
            tail += f":{pages}"
        tail += "."
    if tail:
        parts.append(tail)

    return " ".join(parts)


STOPWORDS = {
    "a", "an", "and", "as", "at", "by", "for", "from", "in", "of", "on",
    "or", "the", "to", "with", "recommendations", "guidelines", "guideline",
}


def title_slug(title, words=3):
    """First few significant title words, for disambiguating unpaginated works."""
    tokens = [
        token for token in re.findall(r"[a-z0-9]+", str(title or "").lower())
        if token not in STOPWORDS
    ]
    return "-".join(tokens[:words]) or "na"


def build_key(citation):
    """Build a bibliographic key, used for non-corpus secondary citations."""
    volume = slugify(citation.get("volume"))
    page = slugify(start_page(citation.get("pages")))
    stem = [
        slugify(first_surname(citation.get("authors"))),
        slugify(citation.get("year")),
        slugify(citation.get("journal")),
    ]
    # Unpaginated works -- many guidelines -- would otherwise collide on surname
    # and year alone. Fall back to significant title words.
    if volume == "na" and page == "na":
        return "-".join(stem + [title_slug(citation.get("title"))])
    return "-".join(stem + [volume, page])


def missing_elements(citation):
    absent = []
    for field in CITATION_FIELDS:
        if citation.get(field) in (None, "", []):
            absent.append(field)
    return absent


def build_citation(raw, secondary=False, source_filename=None):
    """Return {publication_key, citation} for a primary or secondary source.

    Primary corpus callers should supply source_filename; secondary citations use a
    bibliographic dedup key because no local source PDF exists.
    """
    if secondary:
        if not any(raw.get(field) not in (None, "", []) for field in CITATION_FIELDS):
            raise ValueError(
                "a secondary citation needs at least one element from the "
                "publication's reference list"
            )
    else:
        for field in ("authors", "title", "year"):
            if raw.get(field) in (None, "", []):
                raise ValueError("authors, title and year are required for a primary citation")
    citation = {field: raw[field] for field in CITATION_FIELDS if field in raw}
    display = build_display(raw)
    if not display:
        # Every reference-list entry must render as something, or a numbered
        # marker in the body points at a blank line.
        display = "[reference incomplete in source publication]"
    citation["display"] = display
    citation["citation_incomplete"] = missing_elements(raw)
    if secondary:
        publication_key = build_key(raw)
    elif source_filename is not None:
        publication_key = build_source_key(source_filename)
    else:
        # Backward-compatible helper behaviour. Corpus ingestion does not use this
        # fallback; parse, citation repair, and fan-out all use build_source_key().
        publication_key = build_key(raw)
    return {"publication_key": publication_key, "citation": citation}


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--citation", help="path to a JSON file of citation fields")
    parser.add_argument("--secondary", action="store_true",
                        help="build an upstream citation from partial reference-list data")
    parser.add_argument("--source-filename",
                        help="original PDF filename; defines the primary corpus publication key")
    parser.add_argument("--authors", nargs="+")
    parser.add_argument("--title")
    parser.add_argument("--journal")
    parser.add_argument("--year", type=int)
    parser.add_argument("--volume")
    parser.add_argument("--issue")
    parser.add_argument("--pages")
    args = parser.parse_args()
    if args.citation:
        raw = json.loads(Path(args.citation).read_text(encoding="utf-8"))
    else:
        raw = {key: value for key, value in {
            "authors": args.authors, "title": args.title, "journal": args.journal,
            "year": args.year, "volume": args.volume, "issue": args.issue,
            "pages": args.pages,
        }.items() if value not in (None, "", [])}
    try:
        result = build_citation(
            raw, secondary=args.secondary, source_filename=args.source_filename
        )
    except ValueError as exc:
        sys.exit(str(exc))
    if args.secondary:
        # A secondary source is never a corpus publication, so its key is only a
        # dedup handle for the reference list. Emit it, but emit the citation
        # object as the thing that goes on the card.
        print(json.dumps({
            "secondary_citation": result["citation"],
            "dedup_key": result["publication_key"],
        }, indent=2, ensure_ascii=False))
        return

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
