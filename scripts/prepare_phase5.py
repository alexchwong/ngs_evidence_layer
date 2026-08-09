#!/usr/bin/env python3
"""Restore one accepted publication into work/ for additive Phase 5 supplementation."""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path


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
        if item.name == "phase5":
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


def prepare(args):
    archive_source = args.archive_dir / args.publication_key
    work_destination = args.work_dir / args.publication_key
    accepted_final_path = args.accept_dir / f"{args.publication_key}.final.json"
    accepted_census_path = args.accept_dir / f"{args.publication_key}.census.json"

    if work_destination.exists():
        raise ValueError(f"working folder already exists: {work_destination}")
    if not archive_source.is_dir():
        raise ValueError(f"archive folder not found: {archive_source}")
    if not accepted_final_path.is_file() or not accepted_census_path.is_file():
        raise ValueError("accepted final/census pair is required for Phase 5")

    envelope = read_json(accepted_final_path, "accepted package")
    census = read_json(accepted_census_path, "accepted census")
    metadata = envelope.get("metadata") or {}
    base_final = envelope.get("final") or {}
    if metadata.get("publication_key") != args.publication_key:
        raise ValueError("accepted package publication_key does not match --key")
    if envelope.get("acceptance_path") != "confirmed":
        raise ValueError("Phase 5 requires a deterministically confirmed accepted package")
    if census.get("paper_id") != metadata.get("paper_id"):
        raise ValueError("accepted census paper_id does not match accepted metadata")

    previous = envelope.get("supplements") or []
    supplement_number = max(
        [item.get("supplement", 0) for item in previous if isinstance(item, dict)] or [0]
    ) + 1

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
            "schema_version": "1.0",
            "phase": 5,
            "publication_key": args.publication_key,
            "supplement": supplement_number,
            "base_final_sha256": canonical_sha256(base_final),
            "base_census_sha256": canonical_sha256(census),
        }
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
    except Exception:
        shutil.rmtree(work_destination, ignore_errors=True)
        raise

    return work_destination, supplement_number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", dest="publication_key", required=True)
    parser.add_argument("--work-dir", type=Path, default=Path("work"))
    parser.add_argument("--accept-dir", type=Path, default=Path("accept"))
    parser.add_argument("--archive-dir", type=Path, default=Path("archive"))
    args = parser.parse_args()
    try:
        work, supplement = prepare(args)
    except (OSError, ValueError) as exc:
        sys.exit(f"PHASE 5 PREPARE FAILED:\n{exc}")
    print(f"PHASE 5 READY: {args.publication_key}")
    print(f"Supplement: {supplement:03d}")
    print(f"Work: {work}")


if __name__ == "__main__":
    main()
