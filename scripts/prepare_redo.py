#!/usr/bin/env python3
"""Restore an accepted publication into work/ for census, provisional, or card review."""
import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

import ingest_artifacts


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
    archived = []
    redo_dir = archive_source / "redo"
    if redo_dir.is_dir():
        for item in redo_dir.iterdir():
            if item.is_dir() and re.fullmatch(r"[0-9]{3}", item.name):
                archived.append(int(item.name))
    return max(recorded + archived + [0]) + 1


def _next_card_revision(envelope, archive_source):
    recorded = [
        item.get("revision", 0)
        for item in (envelope.get("redos") or [])
        if isinstance(item, dict) and item.get("mode") == "cards"
    ]
    archived = []
    redo_dir = archive_source / "redo"
    if redo_dir.is_dir():
        for snapshot in redo_dir.iterdir():
            marker_path = snapshot / "replacement.redo.json"
            if not marker_path.is_file():
                continue
            try:
                marker = read_json(marker_path, "archived redo marker")
            except ValueError:
                continue
            if marker.get("mode") == "cards" and isinstance(marker.get("revision"), int):
                archived.append(marker["revision"])
    return max(recorded + archived + [0]) + 1


def _copy_source(archive_source, work_destination):
    source = archive_source / "paper.md"
    if not source.is_file():
        raise ValueError(f"archived source Markdown not found: {source}")
    shutil.copy2(source, work_destination / "paper.md")


def _restore_census(archive_source, work_destination, accepted_census):
    archived = ingest_artifacts.resolve_census(archive_source)
    if archived is None:
        # Compatibility fallback for unusually old/incomplete archives.
        destination = work_destination / ingest_artifacts.CENSUS_LEGACY
        destination.write_text(
            json.dumps(accepted_census, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return destination
    archived_document = read_json(archived, "archived census")
    if canonical_sha256(archived_document) != canonical_sha256(accepted_census):
        raise ValueError(
            f"archived active census {archived.name} does not match the accepted census"
        )
    destination = work_destination / archived.name
    shutil.copy2(archived, destination)
    return destination


def _restore_final(archive_source, work_destination, accepted_final):
    destination = work_destination / "paper.final.json"
    accepted_hash = canonical_sha256(accepted_final)
    candidates = []
    top_level = archive_source / "paper.final.json"
    if top_level.is_file():
        candidates.append(top_level)
    candidates.extend(
        path for path in sorted(archive_source.rglob("paper.final.json"))
        if path != top_level and "redo" not in path.relative_to(archive_source).parts
    )
    for archived in candidates:
        try:
            archived_document = read_json(archived, "archived final package")
        except ValueError:
            continue
        if canonical_sha256(archived_document) == accepted_hash:
            shutil.copy2(archived, destination)
            return destination
    # Compatibility fallback: some old Phase 5 archives did not leave the current
    # accepted final at the archive root. The accepted envelope remains authoritative.
    destination.write_text(
        json.dumps(accepted_final, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return destination


def prepare(args):
    mode = args.mode
    if mode not in {"census", "provisional", "cards"}:
        raise ValueError("mode must be census, provisional, or cards")
    work_destination = args.work_dir / args.publication_key
    if work_destination.exists():
        raise ValueError(f"working folder already exists: {work_destination}")

    archive_source, envelope, census, metadata, base_final = _accepted_state(args)
    redo_sequence = _next_redo_sequence(envelope, archive_source)
    revision = _next_card_revision(envelope, archive_source) if mode == "cards" else None
    next_census_attempt = ingest_artifacts.next_census_attempt(archive_source)
    next_provisional_attempt = ingest_artifacts.next_phase_attempt(
        archive_source, "provisional", revision=None
    )
    next_review_attempt = ingest_artifacts.next_phase_attempt(
        archive_source, "review", revision=None
    )
    if revision is not None:
        next_provisional_attempt = 1
        next_review_attempt = 1

    try:
        work_destination.mkdir(parents=True)
        _copy_source(archive_source, work_destination)
        (work_destination / "metadata.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        census_path = None
        if mode in {"provisional", "cards"}:
            census_path = _restore_census(archive_source, work_destination, census)
        if mode == "cards":
            _restore_final(archive_source, work_destination, base_final)

        next_outputs = {}
        if mode == "census":
            next_outputs["census"] = ingest_artifacts.census_name(next_census_attempt)
        if mode in {"census", "provisional"}:
            next_outputs["provisional"] = ingest_artifacts.provisional_name(
                next_provisional_attempt
            )
            next_outputs["review"] = ingest_artifacts.review_name(
                max(next_review_attempt, next_provisional_attempt)
            )
        else:
            next_outputs["provisional"] = ingest_artifacts.provisional_name(
                next_provisional_attempt, revision=revision
            )
            next_outputs["review"] = ingest_artifacts.review_name(
                next_review_attempt, revision=revision
            )
            next_outputs["phase2r_decisions"] = ingest_artifacts.decision_name(
                "phase2r", next_provisional_attempt, revision=revision
            )

        marker = {
            "schema_version": "2.0",
            "publication_key": args.publication_key,
            "paper_id": metadata.get("paper_id"),
            "mode": mode,
            "redo": redo_sequence,
            "base_final_sha256": canonical_sha256(base_final),
            "base_census_sha256": canonical_sha256(census),
            "base_metadata_sha256": canonical_sha256(metadata),
            "next_outputs": next_outputs,
        }
        if census_path is not None:
            marker["census_filename"] = census_path.name
        if revision is not None:
            marker["revision"] = revision
            marker["base_round"] = base_final.get("round")
        (work_destination / "redo.json").write_text(
            json.dumps(marker, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    except Exception:
        shutil.rmtree(work_destination, ignore_errors=True)
        raise
    return work_destination, marker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("census", "provisional", "cards"))
    parser.add_argument("--key", dest="publication_key", required=True)
    parser.add_argument("--work-dir", type=Path, default=Path("work"))
    parser.add_argument("--accept-dir", type=Path, default=Path("accept"))
    parser.add_argument("--archive-dir", type=Path, default=Path("archive"))
    args = parser.parse_args()
    try:
        work, marker = prepare(args)
    except (OSError, ValueError) as exc:
        sys.exit(f"REDO PREPARE FAILED:\n{exc}")
    print(f"REDO READY: {args.publication_key}")
    print(f"Mode: {args.mode}")
    print(f"Redo: {marker['redo']:03d}")
    if args.mode == "cards":
        print(f"Accepted-card revision: {marker['revision']:03d}")
    for phase, filename in marker["next_outputs"].items():
        print(f"Next {phase}: {filename}")
    print(f"Work: {work}")


if __name__ == "__main__":
    main()
