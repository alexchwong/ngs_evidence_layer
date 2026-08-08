#!/usr/bin/env python3
"""Stamp legacy accepted packages as accepted in NEL 0.1.5."""
import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import package_validation as validation

LEGACY_VERSION = "0.1.5"
ACCEPTED_SCHEMA_VERSION = "1.2"


def atomic_json(path, document):
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


def migrated_package(package, publication_key, accepted_path=None):
    metadata = package.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("accepted package has no metadata object")
    if metadata.get("publication_key") != publication_key:
        raise ValueError("accepted filename does not match metadata publication_key")

    updated = dict(package)
    updated_metadata = dict(metadata)

    top_level = updated.get("accepted_in_version")
    nested = updated_metadata.pop("accepted_in_version", None)
    if top_level is not None and nested is not None and top_level != nested:
        raise ValueError(
            f"conflicting acceptance versions: top-level={top_level!r}, metadata={nested!r}"
        )

    accepted_in_version = (
        top_level if top_level is not None else nested if nested is not None else LEGACY_VERSION
    )
    updated["accepted_in_version"] = accepted_in_version
    updated["schema_version"] = ACCEPTED_SCHEMA_VERSION
    updated["metadata"] = updated_metadata

    if "accepted_at" not in updated:
        if updated.get("acceptance_path") != "manual-or-unverified":
            raise ValueError("accepted_at is missing from a non-manual accepted package")
        if accepted_path is None:
            raise ValueError("cannot derive accepted_at without accepted package path")
        updated["accepted_at"] = datetime.fromtimestamp(
            accepted_path.stat().st_mtime, timezone.utc
        ).isoformat()
        updated["accepted_at_source"] = "file-mtime"

    metadata_errors = validation.validate_metadata(updated_metadata)
    if metadata_errors:
        raise ValueError("metadata invalid after migration:\n" + "\n".join(metadata_errors))
    package_errors = validation.schema_errors(
        updated, "accepted_package_schema.json", "accepted package"
    )
    if package_errors:
        raise ValueError("\n".join(package_errors))

    changed = updated != package
    return updated, changed, accepted_in_version


def backfill(accept_dir, dry_run=False):
    changed = 0
    unchanged = 0
    errors = []

    for accepted_path in sorted(accept_dir.glob("*.final.json")):
        publication_key = accepted_path.name.removesuffix(".final.json")
        try:
            package = validation.read_json(accepted_path, "accepted package")
            updated, needs_write, version = migrated_package(
                package, publication_key, accepted_path
            )
            if not needs_write:
                unchanged += 1
                print(f"SKIP {publication_key}: already {version}")
                continue
            if dry_run:
                print(f"WOULD STAMP {publication_key}: {version}")
            else:
                atomic_json(accepted_path, updated)
                print(f"STAMPED {publication_key}: {version}")
            changed += 1
        except (OSError, ValueError) as exc:
            errors.append(f"{publication_key}: {exc}")

    print(f"Summary: stamped={changed}; unchanged={unchanged}; errors={len(errors)}")
    if errors:
        raise ValueError("\n".join(errors))
    return {"stamped": changed, "unchanged": unchanged, "errors": len(errors)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accept-dir", type=Path, default=Path("accept"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        backfill(args.accept_dir, dry_run=args.dry_run)
    except (OSError, ValueError) as exc:
        sys.exit(f"BACKFILL FAILED:\n{exc}")


if __name__ == "__main__":
    main()
