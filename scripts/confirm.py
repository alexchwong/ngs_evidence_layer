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

import final_validation
import package_validation as validation

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "release" / "VERSION"


def read_nel_version():
    try:
        lines = [
            line.strip()
            for line in VERSION_FILE.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except OSError as exc:
        raise ValueError(f"cannot read NEL version from {VERSION_FILE}: {exc}") from exc
    if len(lines) != 1:
        raise ValueError(f"{VERSION_FILE} must contain exactly one non-empty version line")
    return lines[0]



def confirm(args):
    working = args.work_dir / args.publication_key
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
    errors = []
    if metadata.get("publication_key") != args.publication_key:
        errors.append("metadata publication_key does not match --key")
    approved_round = (final.get("audit") or {}).get("approved_round")
    provisional_path = (
        working / f"paper.provisional-{approved_round:03d}.json"
        if isinstance(approved_round, int)
        else None
    )
    review_path = (
        working / f"paper.review-{approved_round:03d}.json"
        if isinstance(approved_round, int)
        else None
    )
    if provisional_path is None or not provisional_path.is_file():
        errors.append(
            "final audit approved_round does not identify an existing provisional file"
        )
    if review_path is None or not review_path.is_file():
        errors.append(
            "final audit approved_round does not identify an existing Phase 3 review"
        )
    if errors:
        raise ValueError("\n".join(errors))
    provisional = validation.read_json(
        provisional_path, "approved provisional package"
    )

    warnings = []
    report = None

    phase_1_errors, phase_1_warnings, _phase_1_report = (
        final_validation.validate_phase_files(
            phase=1,
            metadata_path=paths["metadata"],
            census_path=paths["census"],
        )
    )
    errors.extend(f"phase 1: {error}" for error in phase_1_errors)
    warnings.extend(f"phase 1: {warning}" for warning in phase_1_warnings)
    # The approved provisional is immutable history. Confirmation still checks
    # its schema and internal structure, but does not source-validate its quotes:
    # Phase 4 may have corrected a source defect in paper.final.json.
    provisional_errors, provisional_warnings, _provisional_report = (
        validation.validate_package(
            provisional,
            metadata,
            census,
            source_text=None,
            require_final=False,
        )
    )
    errors.extend(f"provisional: {error}" for error in provisional_errors)
    warnings.extend(
        f"provisional: {warning}" for warning in provisional_warnings
    )
    phase_3_errors, phase_3_warnings, _phase_3_report = (
        final_validation.validate_phase_files(
            phase=3,
            provisional_path=provisional_path,
            review_path=review_path,
        )
    )
    errors.extend(f"phase 3: {error}" for error in phase_3_errors)
    warnings.extend(f"phase 3: {warning}" for warning in phase_3_warnings)
    phase_4_errors, phase_4_warnings, report = (
        final_validation.validate_phase_files(
            phase=4,
            metadata_path=paths["metadata"],
            census_path=paths["census"],
            source_path=paths["source"],
            provisional_path=provisional_path,
            review_path=review_path,
            final_path=paths["final"],
        )
    )
    errors.extend(f"phase 4: {error}" for error in phase_4_errors)
    warnings.extend(f"phase 4: {warning}" for warning in phase_4_warnings)
    if errors:
        raise ValueError("\n".join(errors))

    accepted_version = read_nel_version()

    final_destination = args.accept_dir / f"{args.publication_key}.final.json"
    census_destination = args.accept_dir / f"{args.publication_key}.census.json"
    archive_destination = args.archive_dir / args.publication_key
    collisions = [
        path
        for path in (final_destination, census_destination, archive_destination)
        if path.exists()
    ]
    if collisions:
        raise ValueError(
            "destination already exists:\n" + "\n".join(str(path) for path in collisions)
        )
    args.accept_dir.mkdir(parents=True, exist_ok=True)
    args.archive_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{args.publication_key}.", dir=args.accept_dir)
    )
    staged_final = staging / final_destination.name
    staged_census = staging / census_destination.name
    accepted = {
        "schema_version": "1.2",
        "acceptance_path": "confirmed",
        "accepted_at": datetime.now(timezone.utc).isoformat(),
        "accepted_at_source": "confirm",
        "accepted_in_version": accepted_version,
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
    parser.add_argument("--key", dest="publication_key", required=True)
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
    print(f"CONFIRMED: {args.publication_key}")
    print(f"Cards: {report['cards']}; census ratio: {report['ratio']}")
    print(f"Accepted: {args.accept_dir}")
    print(f"Archived: {archive}")


if __name__ == "__main__":
    main()
