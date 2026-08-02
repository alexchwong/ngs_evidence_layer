#!/usr/bin/env python3
"""Validate one final paper package, accept it, and archive its complete history."""
import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import package_validation as validation


def confirm(args):
    working = args.work_dir / args.paper_id
    if not working.is_dir():
        raise ValueError(f"working folder not found: {working}")
    paths = {
        "metadata": working / "metadata.json",
        "census": working / "paper.census.json",
        "source": working / "paper.md",
        "final": working / "paper.final.json",
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise ValueError("required working files missing:\n" + "\n".join(missing))

    metadata = validation.read_json(paths["metadata"], "metadata")
    census = validation.read_json(paths["census"], "census")
    final = validation.read_json(paths["final"], "final package")
    errors = validation.validate_metadata(metadata)
    errors.extend(validation.validate_census(census, metadata))
    if metadata.get("paper_id") != args.paper_id:
        errors.append("metadata paper_id does not match --id")
    approved_round = (final.get("audit") or {}).get("approved_round")
    provisional_path = working / f"paper.provisional-{approved_round:03d}.json" if isinstance(approved_round, int) else None
    provisional = None
    if provisional_path is None or not provisional_path.is_file():
        errors.append("final audit approved_round does not identify an existing provisional file")
    else:
        provisional = validation.read_json(provisional_path, "approved provisional package")
        provisional_errors, _warnings, _report = validation.validate_package(
            provisional, metadata, census, paths["source"].read_text(encoding="utf-8"), False
        )
        errors.extend(provisional_errors)
        errors.extend(validation.validate_final_against_provisional(final, provisional))
    final_errors, warnings, report = validation.validate_package(
        final, metadata, census, paths["source"].read_text(encoding="utf-8"), True
    )
    errors.extend(final_errors)
    if errors:
        raise ValueError("\n".join(errors))

    final_destination = args.accept_dir / f"{args.paper_id}.final.json"
    census_destination = args.accept_dir / f"{args.paper_id}.census.json"
    archive_destination = args.archive_dir / args.paper_id
    collisions = [path for path in (final_destination, census_destination, archive_destination) if path.exists()]
    if collisions:
        raise ValueError("destination already exists:\n" + "\n".join(str(path) for path in collisions))

    args.accept_dir.mkdir(parents=True, exist_ok=True)
    args.archive_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{args.paper_id}.", dir=args.accept_dir))
    staged_final = staging / final_destination.name
    staged_census = staging / census_destination.name
    accepted = {
        "schema_version": "1.1",
        "acceptance_path": "confirmed",
        "accepted_at": datetime.now(timezone.utc).isoformat(),
        "accepted_at_source": "confirm",
        "metadata": metadata,
        "final": final,
    }
    staged_final.write_text(
        json.dumps(accepted, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    shutil.copyfile(paths["census"], staged_census)
    moved = []
    try:
        os.replace(staged_final, final_destination)
        moved.append(final_destination)
        os.replace(staged_census, census_destination)
        moved.append(census_destination)
        shutil.move(str(working), str(archive_destination))
    except Exception:
        for destination in moved:
            destination.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return warnings, report, archive_destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", dest="paper_id", required=True)
    parser.add_argument("--work-dir", type=Path, default=Path("work"))
    parser.add_argument("--accept-dir", type=Path, default=Path("accept"))
    parser.add_argument("--archive-dir", type=Path, default=Path("archive"))
    args = parser.parse_args()
    try:
        warnings, report, archive = confirm(args)
    except (OSError, ValueError) as exc:
        sys.exit(f"CONFIRM FAILED:\n{exc}")
    for warning in warnings:
        print(f"warning: {warning}")
    print(f"CONFIRMED: {args.paper_id}")
    print(f"Cards: {report['cards']}; census ratio: {report['ratio']}")
    print(f"Accepted: {args.accept_dir}")
    print(f"Archived: {archive}")


if __name__ == "__main__":
    main()