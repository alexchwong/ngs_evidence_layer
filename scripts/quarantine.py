#!/usr/bin/env python3
"""Hold work papers outside the acceptance pipeline or return them for review."""
import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


AUDIT_FILENAME = "quarantine.json"


def _validate_key(publication_key):
    if (
        not publication_key
        or publication_key in {".", ".."}
        or Path(publication_key).name != publication_key
        or "/" in publication_key
        or "\\" in publication_key
    ):
        raise ValueError(f"unsafe publication key: {publication_key!r}")


def _exists(path):
    """Include broken symlinks when checking for state collisions."""
    return os.path.lexists(path)


def _read_json(path, label):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read {label} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {label} {path}: {exc}") from exc


def _validate_source(source, publication_key):
    if not _exists(source):
        raise ValueError(f"paper folder not found: {source}")
    if source.is_symlink() or not source.is_dir():
        raise ValueError(f"paper folder is not a real directory: {source}")
    metadata_path = source / "metadata.json"
    if not metadata_path.is_file() or metadata_path.is_symlink():
        raise ValueError(f"paper folder has no regular metadata.json: {source}")
    metadata = _read_json(metadata_path, "metadata")
    if metadata.get("publication_key") != publication_key:
        raise ValueError("metadata publication_key does not match --key")


def _atomic_json(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def _audit_for(source, publication_key):
    audit_path = source / AUDIT_FILENAME
    if _exists(audit_path):
        if audit_path.is_symlink() or not audit_path.is_file():
            raise ValueError(f"quarantine audit is not a regular file: {audit_path}")
        audit = _read_json(audit_path, "quarantine audit")
        if audit.get("schema_version") != 1:
            raise ValueError(f"unsupported quarantine audit schema: {audit_path}")
        if audit.get("publication_key") != publication_key:
            raise ValueError("quarantine audit publication_key does not match --key")
        if not isinstance(audit.get("events"), list):
            raise ValueError(f"quarantine audit events must be an array: {audit_path}")
        return audit
    return {
        "schema_version": 1,
        "publication_key": publication_key,
        "status": "active-work",
        "events": [],
    }


def _transition(source, destination, audit, event, status):
    if _exists(destination):
        raise ValueError(f"destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    audit_path = source / AUDIT_FILENAME
    original = audit_path.read_bytes() if _exists(audit_path) else None
    updated = dict(audit)
    updated["status"] = status
    updated["events"] = [*audit["events"], event]
    _atomic_json(audit_path, updated)
    try:
        os.replace(source, destination)
    except Exception:
        if original is None:
            audit_path.unlink(missing_ok=True)
        else:
            descriptor, temporary = tempfile.mkstemp(
                prefix=f".{audit_path.name}.restore.", dir=audit_path.parent
            )
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(original)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, audit_path)
            finally:
                Path(temporary).unlink(missing_ok=True)
        raise
    return destination


def quarantine_paper(
    publication_key,
    reason,
    *,
    work_dir=Path("work"),
    quarantine_dir=Path("quarantine"),
    accept_dir=Path("accept"),
    event_time=None,
):
    """Move work/<key> to quarantine/<key>, preserving all processing history."""
    _validate_key(publication_key)
    if not reason or not reason.strip():
        raise ValueError("a non-empty quarantine reason is required")
    accepted = (
        accept_dir / f"{publication_key}.final.json",
        accept_dir / f"{publication_key}.census.json",
    )
    collisions = [path for path in accepted if _exists(path)]
    if collisions:
        raise ValueError(
            "paper already has accepted state and cannot be quarantined:\n"
            + "\n".join(str(path) for path in collisions)
        )
    source = work_dir / publication_key
    destination = quarantine_dir / publication_key
    _validate_source(source, publication_key)
    audit = _audit_for(source, publication_key)
    if audit["status"] not in {"active-work", "returned-to-work"}:
        raise ValueError(f"paper is not in an active work audit state: {audit['status']!r}")
    event = {
        "action": "quarantined",
        "at": event_time or datetime.now(timezone.utc).isoformat(),
        "reason": reason.strip(),
    }
    return _transition(source, destination, audit, event, "quarantined")


def return_to_work(
    publication_key,
    *,
    work_dir=Path("work"),
    quarantine_dir=Path("quarantine"),
    review_note=None,
    event_time=None,
):
    """Move quarantine/<key> back to work/<key> with its complete history."""
    _validate_key(publication_key)
    source = quarantine_dir / publication_key
    destination = work_dir / publication_key
    _validate_source(source, publication_key)
    audit = _audit_for(source, publication_key)
    if audit["status"] != "quarantined":
        raise ValueError(f"paper is not marked quarantined: {audit['status']!r}")
    event = {
        "action": "returned-to-work",
        "at": event_time or datetime.now(timezone.utc).isoformat(),
    }
    if review_note and review_note.strip():
        event["note"] = review_note.strip()
    return _transition(source, destination, audit, event, "returned-to-work")


def list_quarantined(*, quarantine_dir=Path("quarantine")):
    """Return quarantine audit records ordered by publication key."""
    if not _exists(quarantine_dir):
        return []
    if quarantine_dir.is_symlink() or not quarantine_dir.is_dir():
        raise ValueError(f"quarantine root is not a real directory: {quarantine_dir}")
    records = []
    for source in sorted(quarantine_dir.iterdir()):
        if source.name.startswith("."):
            continue
        _validate_key(source.name)
        _validate_source(source, source.name)
        audit = _audit_for(source, source.name)
        if audit["status"] != "quarantined":
            raise ValueError(f"paper is not marked quarantined: {source}")
        records.append(audit)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    hold = commands.add_parser("hold", help="move a work paper into quarantine")
    hold.add_argument("--key", dest="publication_key", required=True)
    hold.add_argument("--reason", default="Out of scope for the corpus")
    hold.add_argument("--work-dir", type=Path, default=Path("work"))
    hold.add_argument("--quarantine-dir", type=Path, default=Path("quarantine"))
    hold.add_argument("--accept-dir", type=Path, default=Path("accept"))

    review = commands.add_parser("review", help="return a quarantined paper to work")
    review.add_argument("--key", dest="publication_key", required=True)
    review.add_argument("--note")
    review.add_argument("--work-dir", type=Path, default=Path("work"))
    review.add_argument("--quarantine-dir", type=Path, default=Path("quarantine"))

    listing = commands.add_parser("list", help="list quarantined papers")
    listing.add_argument("--quarantine-dir", type=Path, default=Path("quarantine"))

    args = parser.parse_args()
    try:
        if args.command == "hold":
            destination = quarantine_paper(
                args.publication_key,
                args.reason,
                work_dir=args.work_dir,
                quarantine_dir=args.quarantine_dir,
                accept_dir=args.accept_dir,
            )
            print(f"QUARANTINED: {args.publication_key}")
            print(f"Moved to: {destination}")
        elif args.command == "review":
            destination = return_to_work(
                args.publication_key,
                work_dir=args.work_dir,
                quarantine_dir=args.quarantine_dir,
                review_note=args.note,
            )
            print(f"RETURNED FOR REVIEW: {args.publication_key}")
            print(f"Moved to: {destination}")
        else:
            records = list_quarantined(quarantine_dir=args.quarantine_dir)
            for record in records:
                latest = record["events"][-1]
                print(
                    f"{record['publication_key']}\t{latest['at']}\t"
                    f"{latest.get('reason', '')}"
                )
            print(f"Quarantined papers: {len(records)}")
    except (OSError, ValueError) as exc:
        sys.exit(f"QUARANTINE FAILED:\n{exc}")


if __name__ == "__main__":
    main()