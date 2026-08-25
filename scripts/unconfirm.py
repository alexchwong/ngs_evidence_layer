#!/usr/bin/env python3
"""Reverse a confirmation operation, restoring the archive to the work folder."""
import argparse
import shutil
import sys
from pathlib import Path


def unconfirm(args):
    """Reverse a confirmation by restoring archive to work folder.

    This operation:
    1. Copies archive/<publication_key>/ back to work/<publication_key>/
    2. Removes accept/<publication_key>.final.json and .census.json if they exist

    The archive folder is preserved as the source of truth.
    """
    archive_source = args.archive_dir / args.publication_key
    work_destination = args.work_dir / args.publication_key
    accept_final = args.accept_dir / f"{args.publication_key}.final.json"
    accept_census = args.accept_dir / f"{args.publication_key}.census.json"

    # Validate inputs
    if not archive_source.is_dir():
        raise ValueError(f"archive folder not found: {archive_source}")
    if work_destination.exists():
        raise ValueError(f"working folder already exists: {work_destination}")

    accept_files_exist = accept_final.is_file() or accept_census.is_file()
    accept_files_found = []
    if accept_final.is_file():
        accept_files_found.append(accept_final)
    if accept_census.is_file():
        accept_files_found.append(accept_census)

    if args.dry_run:
        print(f"DRY RUN: Would restore {archive_source} -> {work_destination}")
        if accept_files_found:
            for path in accept_files_found:
                print(f"DRY RUN: Would remove {path}")
        else:
            print("DRY RUN: No accept files found (already removed?)")
        return {
            "restored": work_destination,
            "removed": accept_files_found,
            "dry_run": True,
        }

    # Step 1: Restore archive to work folder
    work_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(archive_source, work_destination)

    # Step 2: Remove accept files if they exist
    removed = []
    if accept_final.is_file():
        accept_final.unlink()
        removed.append(accept_final)
    if accept_census.is_file():
        accept_census.unlink()
        removed.append(accept_census)

    return {
        "restored": work_destination,
        "removed": removed,
        "dry_run": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", dest="publication_key", required=True)
    parser.add_argument("--work-dir", type=Path, default=Path("work"))
    parser.add_argument("--accept-dir", type=Path, default=Path("accept"))
    parser.add_argument("--archive-dir", type=Path, default=Path("archive"))
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would happen without making changes",
    )
    args = parser.parse_args()
    try:
        result = unconfirm(args)
    except (OSError, ValueError) as exc:
        sys.exit(f"UNCONFIRM FAILED:\n{exc}")

    if result["dry_run"]:
        print(f"UNCONFIRM DRY RUN: {args.publication_key}")
    else:
        print(f"UNCONFIRMED: {args.publication_key}")
        print(f"Restored: {result['restored']}")
        if result["removed"]:
            print(f"Removed: {', '.join(str(p) for p in result['removed'])}")
        else:
            print("Note: No accept files were found (already removed?)")


if __name__ == "__main__":
    main()