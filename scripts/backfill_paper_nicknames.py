#!/usr/bin/env python3
"""Add a placeholder nickname to legacy accepted final packages."""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import package_validation as validation

PLACEHOLDER = "Nickname pending"
EXCLUDED_PUBLICATION_KEYS = {
    "arber-2022-blood-140-1200",
    "khoury-2022-leukemia-36-1703",
}


def atomic_json(path, document):
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


def backfill(accept_dir, dry_run=False):
    changed = 0
    excluded = 0
    unchanged = 0
    errors = []

    for accepted_path in sorted(accept_dir.glob("*.final.json")):
        publication_key = accepted_path.name.removesuffix(".final.json")
        if publication_key in EXCLUDED_PUBLICATION_KEYS:
            excluded += 1
            print(f"EXCLUDE {publication_key}")
            continue
        try:
            envelope = validation.read_json(accepted_path, "accepted package")
            final = envelope.get("final")
            if not isinstance(final, dict):
                raise ValueError("accepted package has no final object")
            if "paper_nickname" in final:
                unchanged += 1
                print(f"SKIP {publication_key}: paper_nickname already present")
                continue

            updated = dict(envelope)
            updated["final"] = {**final, "paper_nickname": PLACEHOLDER}
            schema_errors = validation.schema_errors(
                updated, "accepted_package_schema.json", "accepted package"
            )
            if schema_errors:
                raise ValueError("\n".join(schema_errors))

            if dry_run:
                print(f"WOULD ADD {publication_key}: {PLACEHOLDER}")
            else:
                atomic_json(accepted_path, updated)
                print(f"ADDED {publication_key}: {PLACEHOLDER}")
            changed += 1
        except (OSError, ValueError) as exc:
            errors.append(f"{publication_key}: {exc}")

    print(
        f"Summary: added={changed}; excluded={excluded}; "
        f"unchanged={unchanged}; errors={len(errors)}"
    )
    if errors:
        raise ValueError("\n".join(errors))
    return {
        "added": changed,
        "excluded": excluded,
        "unchanged": unchanged,
        "errors": len(errors),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accept-dir", type=Path, default=Path("accept"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        backfill(args.accept_dir, dry_run=args.dry_run)
    except (OSError, ValueError) as exc:
        sys.exit(f"PAPER NICKNAME BACKFILL FAILED:\n{exc}")


if __name__ == "__main__":
    main()