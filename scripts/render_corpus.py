#!/usr/bin/env python3
"""Render accepted corpus publications/cards into human-readable Markdown."""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INDEX = ROOT / "output" / "corpus" / "nel.index.json"
DEFAULT_CORPUS = ROOT / "output" / "corpus" / "nel.corpus.json"
CARD_SUFFIX_RE = re.compile(r"-C([0-9]{4})$")


def read_json(path, label):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read {label} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid {label} in {path}: {exc}") from exc


def short_card_id(card_id):
    match = CARD_SUFFIX_RE.search(str(card_id))
    return match.group(1) if match else str(card_id)


def _walk_card_objects(value):
    if isinstance(value, dict):
        if "card_id" in value and "interpretation" in value:
            yield value
        for child in value.values():
            yield from _walk_card_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_card_objects(child)


def corpus_card_map(corpus):
    cards = {}
    for card in _walk_card_objects(corpus):
        card_id = card.get("card_id")
        if card_id and card_id not in cards:
            cards[card_id] = card
    return cards


def _inline_list(values):
    values = values or []
    return ", ".join(str(value) for value in values) if values else "—"


def _secondary_citation(value):
    if not value:
        return "—"
    if isinstance(value, dict):
        return value.get("display") or json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def render_publication(publication_key, index, corpus):
    papers = index.get("papers") or {}
    paper = papers.get(publication_key)
    if paper is None:
        raise ValueError(f"publication key not found in corpus index: {publication_key}")
    card_map = corpus_card_map(corpus)
    requested_ids = paper.get("card_ids") or []
    missing = [card_id for card_id in requested_ids if card_id not in card_map]
    if missing:
        raise ValueError(
            "corpus cards missing for indexed publication: " + ", ".join(missing)
        )

    lines = [
        f"# {publication_key}",
        "",
        str(paper.get("citation_display") or "Citation unavailable."),
        "",
        f"**Cards:** {len(requested_ids)}  ",
        f"**Accepted in:** {paper.get('accepted_in_version', '—')}",
        "",
    ]
    for card_id in requested_ids:
        card = card_map[card_id]
        lines.extend(
            [
                f"## {short_card_id(card_id)}",
                "",
                f"**Full card ID:** `{card_id}`  ",
                f"**Category:** {card.get('category', '—')}  ",
                f"**Genes:** {_inline_list(card.get('genes'))}  ",
                f"**Diseases:** {_inline_list(card.get('diseases'))}  ",
                f"**Disease ancestors:** {_inline_list(card.get('disease_ancestors'))}  ",
                f"**Evidence tier:** {card.get('evidence_tier', '—')}",
                "",
                "### Interpretation",
                "",
                str(card.get("interpretation") or "—"),
                "",
                f"**Locator:** {card.get('locator') or '—'}",
                "",
                f"**Secondary citation:** {_secondary_citation(card.get('secondary_citation'))}",
                "",
                "---",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_index(index):
    papers = index.get("papers") or {}
    lines = [
        "# NEL corpus publications",
        "",
        "| Publication key | Cards | Accepted in | Citation |",
        "|---|---:|---|---|",
    ]
    for key in sorted(papers):
        paper = papers[key]
        citation = str(paper.get("citation_display") or "—").replace("|", "\\|")
        lines.append(
            f"| `{key}` | {len(paper.get('card_ids') or [])} | "
            f"{paper.get('accepted_in_version', '—')} | {citation} |"
        )
    return "\n".join(lines) + "\n"


def _write_or_print(content, dest, filename):
    if dest is None:
        print(content, end="")
        return None
    dest.mkdir(parents=True, exist_ok=True)
    output = dest / filename
    output.write_text(content, encoding="utf-8")
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--key", dest="publication_key")
    mode.add_argument("--list", action="store_true", help="render publication keys and citations")
    parser.add_argument("--dest", type=Path, help="destination directory; omit to print to stdout")
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    args = parser.parse_args(argv)
    try:
        index = read_json(args.index, "corpus index")
        if args.list:
            output = _write_or_print(render_index(index), args.dest, "index.md")
        else:
            corpus = read_json(args.corpus, "corpus")
            output = _write_or_print(
                render_publication(args.publication_key, index, corpus),
                args.dest,
                f"{args.publication_key}.md",
            )
    except (OSError, ValueError) as exc:
        sys.exit(f"RENDER CORPUS FAILED:\n{exc}")
    if output is not None:
        print(f"wrote {output}")


if __name__ == "__main__":
    main()
