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
import validate_phase5

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


def _restore_bytes(path, payload):
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.restore.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def _validate_original_history(paths, working, final, metadata, census):
    errors = []
    warnings = []
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
        return errors, warnings, None, provisional_path, review_path
    provisional = validation.read_json(provisional_path, "approved provisional package")
    phase_1_errors, phase_1_warnings, _ = final_validation.validate_phase_files(
        phase=1,
        metadata_path=paths["metadata"],
        census_path=paths["census"],
    )
    errors.extend(f"phase 1: {error}" for error in phase_1_errors)
    warnings.extend(f"phase 1: {warning}" for warning in phase_1_warnings)
    provisional_errors, provisional_warnings, _ = validation.validate_package(
        provisional,
        metadata,
        census,
        source_text=None,
        require_final=False,
    )
    errors.extend(f"provisional: {error}" for error in provisional_errors)
    warnings.extend(f"provisional: {warning}" for warning in provisional_warnings)
    phase_3_errors, phase_3_warnings, _ = final_validation.validate_phase_files(
        phase=3,
        provisional_path=provisional_path,
        review_path=review_path,
    )
    errors.extend(f"phase 3: {error}" for error in phase_3_errors)
    warnings.extend(f"phase 3: {warning}" for warning in phase_3_warnings)
    phase_4_errors, phase_4_warnings, report = final_validation.validate_phase_files(
        phase=4,
        metadata_path=paths["metadata"],
        census_path=paths["census"],
        source_path=paths["source"],
        provisional_path=provisional_path,
        review_path=review_path,
        final_path=paths["final"],
    )
    errors.extend(f"phase 4: {error}" for error in phase_4_errors)
    warnings.extend(f"phase 4: {warning}" for warning in phase_4_warnings)
    return errors, warnings, report, provisional_path, review_path


def _phase5_required_files(working, mode):
    required = {
        "base final": working / "paper.base.final.json",
        "base census": working / "paper.base.census.json",
        "Phase 5 provisional": working / "paper.phase5-provisional.json",
        "Phase 5 review": working / "paper.phase5-review.json",
    }
    if mode == "revision":
        required.update(
            {
                "Phase 5 targets": working / "paper.phase5-targets.json",
                "Phase 5 revision asset": working / "paper.phase5-revision.json",
            }
        )
    return required


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
    warnings = []
    if metadata.get("publication_key") != args.publication_key:
        errors.append("metadata publication_key does not match --key")

    phase5_path = working / "phase5.json"
    is_phase5 = phase5_path.is_file()
    phase5_marker = validation.read_json(phase5_path, "Phase 5 marker") if is_phase5 else None
    phase5_mode = (phase5_marker or {}).get("mode") or "additive"

    history_paths = dict(paths)
    history_final = final
    if is_phase5 and (working / "paper.base.final.json").is_file():
        history_paths["final"] = working / "paper.base.final.json"
        history_final = validation.read_json(history_paths["final"], "base final package")
    original_errors, original_warnings, report, _, _ = _validate_original_history(
        history_paths, working, history_final, metadata, census
    )
    errors.extend(original_errors)
    warnings.extend(original_warnings)
    final_destination = args.accept_dir / f"{args.publication_key}.final.json"
    census_destination = args.accept_dir / f"{args.publication_key}.census.json"
    archive_root = args.archive_dir / args.publication_key
    phase5_report = None

    if is_phase5:
        phase5_required = _phase5_required_files(working, phase5_mode)
        missing_phase5 = [str(path) for path in phase5_required.values() if not path.is_file()]
        if missing_phase5:
            errors.append("required Phase 5 files missing:\n" + "\n".join(missing_phase5))
        if not final_destination.is_file() or not census_destination.is_file():
            errors.append("Phase 5 requires the current accepted final/census pair")
        if not archive_root.is_dir():
            errors.append("Phase 5 requires the existing archive folder")
        if not errors:
            if phase5_mode == "revision":
                phase5_errors, phase5_warnings, phase5_report = (
                    validate_phase5.validate_phase5_revision_files(
                        metadata_path=paths["metadata"],
                        census_path=paths["census"],
                        source_path=paths["source"],
                        base_final_path=phase5_required["base final"],
                        base_census_path=phase5_required["base census"],
                        marker_path=phase5_path,
                        targets_path=phase5_required["Phase 5 targets"],
                        provisional_path=phase5_required["Phase 5 provisional"],
                        review_path=phase5_required["Phase 5 review"],
                        revision_path=phase5_required["Phase 5 revision asset"],
                        final_path=paths["final"],
                        accepted_final_path=final_destination,
                        accepted_census_path=census_destination,
                    )
                )
            else:
                phase5_errors, phase5_warnings, phase5_report = (
                    validate_phase5.validate_phase5_files(
                        metadata_path=paths["metadata"],
                        census_path=paths["census"],
                        source_path=paths["source"],
                        base_final_path=phase5_required["base final"],
                        base_census_path=phase5_required["base census"],
                        marker_path=phase5_path,
                        provisional_path=phase5_required["Phase 5 provisional"],
                        review_path=phase5_required["Phase 5 review"],
                        final_path=paths["final"],
                        accepted_final_path=final_destination,
                        accepted_census_path=census_destination,
                    )
                )
            errors.extend(f"phase 5: {error}" for error in phase5_errors)
            warnings.extend(f"phase 5: {warning}" for warning in phase5_warnings)
    else:
        collisions = [
            path
            for path in (final_destination, census_destination, archive_root)
            if path.exists()
        ]
        if collisions:
            errors.append(
                "destination already exists:\n" + "\n".join(str(path) for path in collisions)
            )
    if errors:
        raise ValueError("\n".join(errors))

    accepted_version = read_nel_version()
    args.accept_dir.mkdir(parents=True, exist_ok=True)
    args.archive_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{args.publication_key}.", dir=args.accept_dir))
    staged_final = staging / final_destination.name
    staged_census = staging / census_destination.name

    if is_phase5:
        current_envelope = validation.read_json(final_destination, "current accepted package")
        accepted = dict(current_envelope)
        accepted_at = datetime.now(timezone.utc).isoformat()
        if phase5_mode == "revision":
            accepted["schema_version"] = "1.4"
            revisions = list(current_envelope.get("revisions") or [])
            revisions.append(
                {
                    "phase": 5,
                    "revision": phase5_report["revision"],
                    "accepted_at": accepted_at,
                    "accepted_in_version": accepted_version,
                    "base_final_sha256": phase5_marker["base_final_sha256"],
                    "base_census_sha256": phase5_marker["base_census_sha256"],
                    "revised_card_ids": phase5_report["revised_card_ids"],
                    "extraction_model": phase5_report["phase5_extraction_model"],
                    "reviewer_model": phase5_report["phase5_reviewer_model"],
                }
            )
            accepted["revisions"] = revisions
            archive_destination = (
                archive_root / "phase5-revision" / f"{phase5_report['revision']:03d}"
            )
        else:
            accepted["schema_version"] = "1.4" if current_envelope.get("revisions") else "1.3"
            supplements = list(current_envelope.get("supplements") or [])
            supplements.append(
                {
                    "phase": 5,
                    "supplement": phase5_report["supplement"],
                    "accepted_at": accepted_at,
                    "accepted_in_version": accepted_version,
                    "base_final_sha256": phase5_marker["base_final_sha256"],
                    "base_census_sha256": phase5_marker["base_census_sha256"],
                    "added_card_ids": phase5_report["added_card_ids"],
                    "extraction_model": phase5_report["phase5_extraction_model"],
                    "reviewer_model": phase5_report["phase5_reviewer_model"],
                }
            )
            accepted["supplements"] = supplements
            archive_destination = (
                archive_root / "phase5" / f"{phase5_report['supplement']:03d}"
            )
        accepted["metadata"] = metadata
        accepted["final"] = final
        envelope_errors = validation.schema_errors(
            accepted, "accepted_package_schema.json", "accepted package"
        )
        if envelope_errors:
            raise ValueError("\n".join(envelope_errors))
        if archive_destination.exists():
            raise ValueError(f"Phase 5 archive destination already exists: {archive_destination}")
    else:
        accepted = {
            "schema_version": "1.2",
            "acceptance_path": "confirmed",
            "accepted_at": datetime.now(timezone.utc).isoformat(),
            "accepted_at_source": "confirm",
            "accepted_in_version": accepted_version,
            "metadata": metadata,
            "final": final,
        }
        archive_destination = archive_root

    staged_final.write_text(
        json.dumps(accepted, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    shutil.copyfile(paths["census"], staged_census)
    old_final_bytes = final_destination.read_bytes() if is_phase5 else None
    old_census_bytes = census_destination.read_bytes() if is_phase5 else None
    replaced_final = False
    replaced_census = False
    try:
        if is_phase5:
            archive_destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staged_final, final_destination)
        replaced_final = True
        os.replace(staged_census, census_destination)
        replaced_census = True
        shutil.move(str(working), str(archive_destination))
    except Exception:
        if is_phase5:
            if replaced_final:
                _restore_bytes(final_destination, old_final_bytes)
            if replaced_census:
                _restore_bytes(census_destination, old_census_bytes)
        else:
            if replaced_final:
                final_destination.unlink(missing_ok=True)
            if replaced_census:
                census_destination.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return warnings, report, archive_destination, is_phase5, phase5_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", dest="publication_key", required=True)
    parser.add_argument("--work-dir", type=Path, default=Path("work"))
    parser.add_argument("--accept-dir", type=Path, default=Path("accept"))
    parser.add_argument("--archive-dir", type=Path, default=Path("archive"))
    args = parser.parse_args()
    try:
        warnings, report, archive, is_phase5, phase5_report = confirm(args)
    except (OSError, ValueError) as exc:
        sys.exit(f"CONFIRM FAILED:\n{exc}")
    for warning in warnings:
        print(f"warning: {warning}")
    print(f"CONFIRMED: {args.publication_key}")
    if is_phase5:
        if phase5_report.get("mode") == "revision":
            print(
                f"Phase 5 revision: {phase5_report['revision']:03d}; "
                f"revised cards: {len(phase5_report['revised_card_ids'])}"
            )
        else:
            print(
                f"Phase 5 supplement: {phase5_report['supplement']:03d}; "
                f"added cards: {len(phase5_report['added_card_ids'])}"
            )
    print(f"Cards: {report['cards']}; census ratio: {report['ratio']}")
    print(f"Accepted: {args.accept_dir}")
    print(f"Archived: {archive}")


if __name__ == "__main__":
    main()
