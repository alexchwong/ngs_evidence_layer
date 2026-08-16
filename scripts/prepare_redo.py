#!/usr/bin/env python3
"""Restore one accepted publication into work/ for a Phase 1, 2, or 5 redo."""
import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

CARD_TOKEN_RE = re.compile(r"^(?:C)?([0-9]{4})$")
HISTORY_DIRS = {"phase5", "phase5-revision", "redo", "versions"}


def read_json(path, label="JSON"):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read {label} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid {label} in {path}: {exc}") from exc


def canonical_sha256(document):
    payload = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def copy_archive_contents(source, destination):
    destination.mkdir(parents=True)
    for item in source.iterdir():
        if item.name in HISTORY_DIRS:
            continue
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def collect_existing_cards(accept_dir):
    cards = []
    for final_path in sorted(accept_dir.glob("*.final.json")):
        try:
            envelope = read_json(final_path, "accepted package")
            publication_key = envelope["metadata"]["publication_key"]
            package = envelope["final"]
        except (KeyError, ValueError):
            continue
        for card in package.get("cards", []):
            cards.append(
                {
                    "publication_key": publication_key,
                    "card_id": card.get("card_id"),
                    "interpretation": card.get("interpretation"),
                    "genes": card.get("genes", []),
                    "diseases": card.get("diseases", []),
                    "category": card.get("category"),
                }
            )
    return cards


def parse_card_tokens(value):
    if value is None:
        return []
    tokens = []
    seen = set()
    for raw in value.split(","):
        raw = raw.strip()
        match = CARD_TOKEN_RE.fullmatch(raw)
        if not match:
            raise ValueError(
                f"invalid --cards value {raw!r}; use comma-separated four-digit IDs such as 0001,0003,0005, or all"
            )
        short_id = match.group(1)
        if short_id in seen:
            raise ValueError(f"duplicate card in --cards: {short_id}")
        seen.add(short_id)
        tokens.append(short_id)
    if not tokens:
        raise ValueError("--cards must contain at least one card ID")
    return tokens


def all_card_tokens(publication_key, base_final):
    prefix = f"{publication_key}-C"
    tokens = []
    seen = set()
    for card in base_final.get("cards", []):
        card_id = card.get("card_id")
        if not isinstance(card_id, str) or not card_id.startswith(prefix):
            raise ValueError(f"accepted card has unexpected card_id: {card_id!r}")
        short_id = card_id[len(prefix) :]
        if not re.fullmatch(r"[0-9]{4}", short_id):
            raise ValueError(f"accepted card has unexpected card_id: {card_id!r}")
        if short_id in seen:
            raise ValueError(f"accepted final contains duplicate card ID: {card_id}")
        seen.add(short_id)
        tokens.append(short_id)
    if not tokens:
        raise ValueError("accepted final contains no cards to release for revision")
    return tokens


def _maps(items, key="card_id"):
    return {item.get(key): item for item in items}


def _full_card_id(publication_key, short_id):
    return f"{publication_key}-C{short_id}"


def build_revision_targets(publication_key, base_final, short_ids):
    cards = _maps(base_final.get("cards", []))
    evidence = _maps(base_final.get("evidence", []))
    targets = []
    for short_id in short_ids:
        card_id = _full_card_id(publication_key, short_id)
        if card_id not in cards:
            raise ValueError(f"requested card not found in accepted final: {short_id} ({card_id})")
        if card_id not in evidence:
            raise ValueError(f"requested card has no paired accepted evidence: {short_id} ({card_id})")
        targets.append(
            {
                "short_id": short_id,
                "card_id": card_id,
                "card_sha256": canonical_sha256(cards[card_id]),
                "evidence_sha256": canonical_sha256(evidence[card_id]),
                "card": cards[card_id],
                "evidence": evidence[card_id],
            }
        )
    return targets


def _accepted_state(args):
    archive_source = args.archive_dir / args.publication_key
    accepted_final_path = args.accept_dir / f"{args.publication_key}.final.json"
    accepted_census_path = args.accept_dir / f"{args.publication_key}.census.json"
    if not archive_source.is_dir():
        raise ValueError(f"archive folder not found: {archive_source}")
    if not accepted_final_path.is_file() or not accepted_census_path.is_file():
        raise ValueError("accepted final/census pair is required for redo")
    envelope = read_json(accepted_final_path, "accepted package")
    census = read_json(accepted_census_path, "accepted census")
    metadata = envelope.get("metadata") or {}
    base_final = envelope.get("final") or {}
    if metadata.get("publication_key") != args.publication_key:
        raise ValueError("accepted package publication_key does not match --key")
    if envelope.get("acceptance_path") != "confirmed":
        raise ValueError("redo requires a deterministically confirmed accepted package")
    if census.get("paper_id") != metadata.get("paper_id"):
        raise ValueError("accepted census paper_id does not match accepted metadata")
    return archive_source, envelope, census, metadata, base_final


def _next_redo_sequence(envelope, archive_source):
    recorded = [
        item.get("redo", 0)
        for item in (envelope.get("redos") or [])
        if isinstance(item, dict)
    ]
    redo_dir = archive_source / "redo"
    archived = []
    if redo_dir.is_dir():
        for item in redo_dir.iterdir():
            if item.is_dir() and re.fullmatch(r"[0-9]{3}", item.name):
                archived.append(int(item.name))
    return max(recorded + archived + [0]) + 1


def prepare_full_redo(args):
    if getattr(args, "cards", None) is not None:
        raise ValueError("--cards is valid only with --phase 5")
    if args.phase not in {1, 2}:
        raise ValueError("full redo start phase must be 1 or 2")
    work_destination = args.work_dir / args.publication_key
    if work_destination.exists():
        raise ValueError(f"working folder already exists: {work_destination}")
    archive_source, envelope, census, metadata, base_final = _accepted_state(args)
    source_path = archive_source / "paper.md"
    if not source_path.is_file():
        raise ValueError(f"archived source Markdown not found: {source_path}")
    sequence = _next_redo_sequence(envelope, archive_source)
    try:
        work_destination.mkdir(parents=True)
        shutil.copy2(source_path, work_destination / "paper.md")
        (work_destination / "metadata.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        if args.phase == 2:
            (work_destination / "paper.census.json").write_text(
                json.dumps(census, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        (work_destination / "paper.base.final.json").write_text(
            json.dumps(base_final, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (work_destination / "paper.base.census.json").write_text(
            json.dumps(census, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        marker = {
            "schema_version": "1.0",
            "publication_key": args.publication_key,
            "paper_id": metadata.get("paper_id"),
            "start_phase": args.phase,
            "redo": sequence,
            "base_final_sha256": canonical_sha256(base_final),
            "base_census_sha256": canonical_sha256(census),
            "base_metadata_sha256": canonical_sha256(metadata),
        }
        (work_destination / "redo.json").write_text(
            json.dumps(marker, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    except Exception:
        shutil.rmtree(work_destination, ignore_errors=True)
        raise
    return work_destination, sequence


def prepare_phase5(args):
    work_destination = args.work_dir / args.publication_key
    if work_destination.exists():
        raise ValueError(f"working folder already exists: {work_destination}")
    archive_source, envelope, census, metadata, base_final = _accepted_state(args)
    cards_arg = getattr(args, "cards", None)
    if isinstance(cards_arg, str) and cards_arg.strip().casefold() == "all":
        short_ids = all_card_tokens(args.publication_key, base_final)
    else:
        short_ids = parse_card_tokens(cards_arg)
    revision_mode = cards_arg is not None
    if revision_mode:
        previous = envelope.get("revisions") or []
        sequence = max(
            [item.get("revision", 0) for item in previous if isinstance(item, dict)] or [0]
        ) + 1
        targets = build_revision_targets(args.publication_key, base_final, short_ids)
    else:
        previous = envelope.get("supplements") or []
        sequence = max(
            [item.get("supplement", 0) for item in previous if isinstance(item, dict)] or [0]
        ) + 1
        targets = None
    try:
        copy_archive_contents(archive_source, work_destination)
        (work_destination / "metadata.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (work_destination / "paper.census.json").write_text(
            json.dumps(census, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (work_destination / "paper.final.json").write_text(
            json.dumps(base_final, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (work_destination / "paper.base.final.json").write_text(
            json.dumps(base_final, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (work_destination / "paper.base.census.json").write_text(
            json.dumps(census, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        marker = {
            "schema_version": "1.1" if revision_mode else "1.0",
            "phase": 5,
            "mode": "revision" if revision_mode else "additive",
            "publication_key": args.publication_key,
            "base_final_sha256": canonical_sha256(base_final),
            "base_census_sha256": canonical_sha256(census),
        }
        if revision_mode:
            marker["revision"] = sequence
            marker["target_card_ids"] = [target["card_id"] for target in targets]
            marker["targets"] = [
                {
                    "short_id": target["short_id"],
                    "card_id": target["card_id"],
                    "card_sha256": target["card_sha256"],
                    "evidence_sha256": target["evidence_sha256"],
                }
                for target in targets
            ]
        else:
            marker["supplement"] = sequence
        (work_destination / "phase5.json").write_text(
            json.dumps(marker, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        existing_cards = {
            "schema_version": "1.0",
            "target_publication_key": args.publication_key,
            "cards": collect_existing_cards(args.accept_dir),
        }
        (work_destination / "phase5.existing-cards.json").write_text(
            json.dumps(existing_cards, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if revision_mode:
            target_document = {
                "schema_version": "1.0",
                "phase": 5,
                "mode": "revision",
                "publication_key": args.publication_key,
                "paper_id": metadata.get("paper_id"),
                "target_card_ids": [target["card_id"] for target in targets],
                "targets": targets,
            }
            (work_destination / "paper.phase5-targets.json").write_text(
                json.dumps(target_document, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    except Exception:
        shutil.rmtree(work_destination, ignore_errors=True)
        raise
    return work_destination, sequence


def prepare(args):
    if args.phase in {1, 2}:
        return prepare_full_redo(args)
    if args.phase == 5:
        return prepare_phase5(args)
    raise ValueError("--phase must be 1, 2, or 5")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", dest="publication_key", required=True)
    parser.add_argument("--phase", type=int, choices=(1, 2, 5), required=True)
    parser.add_argument(
        "--cards",
        help="Phase 5 only: comma-separated four-digit accepted card IDs, or 'all' (revision mode)",
    )
    parser.add_argument("--work-dir", type=Path, default=Path("work"))
    parser.add_argument("--accept-dir", type=Path, default=Path("accept"))
    parser.add_argument("--archive-dir", type=Path, default=Path("archive"))
    args = parser.parse_args()
    try:
        work, sequence = prepare(args)
    except (OSError, ValueError) as exc:
        sys.exit(f"REDO PREPARE FAILED:\n{exc}")
    if args.phase == 5:
        marker = read_json(work / "phase5.json", "Phase 5 marker")
        print(f"PHASE 5 READY: {args.publication_key}")
        if marker.get("mode") == "revision":
            print(f"Revision: {sequence:03d}")
            print("Cards: " + ",".join(target["short_id"] for target in marker["targets"]))
        else:
            print(f"Supplement: {sequence:03d}")
    else:
        print(f"REDO READY: {args.publication_key}")
        print(f"Start phase: {args.phase}")
        print(f"Redo: {sequence:03d}")
    print(f"Work: {work}")


if __name__ == "__main__":
    main()
