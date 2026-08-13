#!/usr/bin/env python3
"""Render accepted or in-progress corpus publications into human-readable Markdown."""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INDEX = ROOT / "output" / "corpus" / "nel.index.json"
DEFAULT_CORPUS = ROOT / "output" / "corpus" / "nel.corpus.json"
DEFAULT_WORK_DIR = ROOT / "work"
DEFAULT_ACCEPT_DIR = ROOT / "accept"
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


def acceptance_version_provenance(envelope):
    """Return original, complete, and latest acceptance-version provenance."""
    original = envelope.get("accepted_in_version")
    if not isinstance(original, str) or not original:
        raise ValueError("accepted package has no accepted_in_version")

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
            accepted_at = entry.get("accepted_at")
            try:
                accepted_time = datetime.fromisoformat(accepted_at)
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


def package_publication_inputs(
    publication_key, metadata, final, label, acceptance_provenance=None
):
    if not isinstance(metadata, dict):
        raise ValueError(f"{label} metadata is not an object")
    if not isinstance(final, dict):
        raise ValueError(f"{label} final package is not an object")
    metadata_key = metadata.get("publication_key")
    if metadata_key != publication_key:
        raise ValueError(
            f"{label} metadata publication_key does not match --key: {metadata_key!r}"
        )
    cards = final.get("cards")
    if not isinstance(cards, list):
        raise ValueError(f"{label} final package has no cards array")
    card_ids = [card.get("card_id") for card in cards if isinstance(card, dict)]
    if len(card_ids) != len(cards) or any(not card_id for card_id in card_ids):
        raise ValueError(f"{label} final package contains a card without a card_id")
    citation = metadata.get("citation") or {}
    paper = {
        "citation_display": citation.get("display"),
        "card_ids": card_ids,
    }
    if acceptance_provenance is not None:
        paper.update(acceptance_provenance)
    index = {"papers": {publication_key: paper}}
    return index, final


def work_publication_inputs(publication_key, work_dir=DEFAULT_WORK_DIR):
    working = Path(work_dir) / publication_key
    metadata = read_json(working / "metadata.json", "working metadata")
    final = read_json(working / "paper.final.json", "working final package")
    return package_publication_inputs(publication_key, metadata, final, "working")


def accepted_publication_inputs(publication_key, accept_dir=DEFAULT_ACCEPT_DIR):
    envelope = read_json(
        Path(accept_dir) / f"{publication_key}.final.json", "accepted package"
    )
    if not isinstance(envelope, dict):
        raise ValueError("accepted package is not an object")
    return package_publication_inputs(
        publication_key,
        envelope.get("metadata"),
        envelope.get("final"),
        "accepted",
        acceptance_version_provenance(envelope),
    )


def _inline_list(values):
    values = values or []
    return ", ".join(str(value) for value in values) if values else "—"


def _secondary_citation(value):
    if not value:
        return "—"
    if isinstance(value, dict):
        return value.get("display") or json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _paper_acceptance_provenance(paper):
    original = paper.get("accepted_in_version")
    history = paper.get("acceptance_version_history")
    if not isinstance(history, list) or not history:
        history = [original] if original else []
    latest = paper.get("latest_accepted_in_version") or (history[-1] if history else None)
    return original or "—", history, latest or "—"


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

    accepted_in, version_history, latest_accepted = _paper_acceptance_provenance(paper)
    rendered_history = " → ".join(str(version) for version in version_history) or "—"
    lines = [
        f"# {publication_key}",
        "",
        str(paper.get("citation_display") or "Citation unavailable."),
        "",
        f"**Cards:** {len(requested_ids)}  ",
        f"**Accepted in:** {accepted_in}  ",
        f"**Version history:** {rendered_history}  ",
        f"**Latest version accepted:** {latest_accepted}",
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
        "| Publication key | Cards | Accepted in | Version history | Latest version accepted | Citation |",
        "|---|---:|---|---|---|---|",
    ]
    for key in sorted(papers):
        paper = papers[key]
        citation = str(paper.get("citation_display") or "—").replace("|", "\\|")
        accepted_in, version_history, latest_accepted = _paper_acceptance_provenance(paper)
        rendered_history = " → ".join(str(version) for version in version_history) or "—"
        lines.append(
            f"| `{key}` | {len(paper.get('card_ids') or [])} | "
            f"{accepted_in} | {rendered_history} | {latest_accepted} | {citation} |"
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
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--from-work",
        action="store_true",
        help="render work/<publication-key>/paper.final.json instead of the accepted paper",
    )
    source.add_argument(
        "--from-accept",
        action="store_true",
        help="render accept/<publication-key>.final.json instead of the incorporated paper",
    )
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR, help=argparse.SUPPRESS)
    parser.add_argument(
        "--accept-dir", type=Path, default=DEFAULT_ACCEPT_DIR, help=argparse.SUPPRESS
    )
    args = parser.parse_args(argv)
    if (args.from_work or args.from_accept) and args.list:
        parser.error("--from-work and --from-accept require --key")
    try:
        if args.list:
            index = read_json(args.index, "corpus index")
            output = _write_or_print(render_index(index), args.dest, "index.md")
        else:
            if args.from_work:
                index, corpus = work_publication_inputs(
                    args.publication_key, args.work_dir
                )
            elif args.from_accept:
                index, corpus = accepted_publication_inputs(
                    args.publication_key, args.accept_dir
                )
            else:
                index = read_json(args.index, "corpus index")
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
