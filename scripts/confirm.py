#!/usr/bin/env python3
"""Validate one final paper package, accept it, and archive its complete history."""
import argparse
import hashlib
import json
import os
import re
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


def canonical_sha256(document):
    payload = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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


def _redo_required_files(working):
    return {
        "base final": working / "paper.base.final.json",
        "base census": working / "paper.base.census.json",
    }


def _copy_directory_contents(source, destination, excluded=()):
    excluded = set(excluded)
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if item.name in excluded:
            continue
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def _safe_version_directory(version, label):
    if (
        not isinstance(version, str)
        or not version
        or version in {".", ".."}
        or Path(version).name != version
    ):
        raise ValueError(f"{label} is not safe for an archive directory: {version!r}")
    return version


def _next_redo_sequence(envelope, archive_root):
    recorded = [
        item.get("redo", 0)
        for item in (envelope.get("redos") or [])
        if isinstance(item, dict)
    ]
    archived = []
    redo_dir = archive_root / "redo"
    if redo_dir.is_dir():
        for item in redo_dir.iterdir():
            if item.is_dir() and re.fullmatch(r"[0-9]{3}", item.name):
                archived.append(int(item.name))
    return max(recorded + archived + [0]) + 1


def _validate_redo(
    *,
    marker,
    working,
    paths,
    metadata,
    census,
    final_destination,
    census_destination,
    archive_root,
):
    errors = []
    required = _redo_required_files(working)
    missing = [str(path) for path in required.values() if not path.is_file()]
    if missing:
        errors.append("required redo files missing:\n" + "\n".join(missing))
        return errors, None
    if marker.get("schema_version") != "1.0":
        errors.append("redo.json has unsupported schema_version")
    if marker.get("publication_key") != metadata.get("publication_key"):
        errors.append("redo.json publication_key does not match metadata")
    if marker.get("paper_id") != metadata.get("paper_id"):
        errors.append("redo.json paper_id does not match metadata")
    start_phase = marker.get("start_phase")
    if start_phase not in {1, 2}:
        errors.append("redo.json start_phase must be 1 or 2")
    redo_number = marker.get("redo")
    if not isinstance(redo_number, int) or redo_number < 1:
        errors.append("redo.json redo must be a positive integer")
    required_destinations = (final_destination, census_destination, archive_root)
    missing_destinations = [str(path) for path in required_destinations if not path.exists()]
    if missing_destinations:
        errors.append(
            "redo requires the complete current accepted/archive set; missing:\n"
            + "\n".join(missing_destinations)
        )
        return errors, None
    if not final_destination.is_file() or not census_destination.is_file() or not archive_root.is_dir():
        errors.append("redo destinations have unexpected file types")
        return errors, None

    current_envelope = validation.read_json(final_destination, "current accepted package")
    current_census = validation.read_json(census_destination, "current accepted census")
    current_metadata = current_envelope.get("metadata") or {}
    current_final = current_envelope.get("final") or {}
    base_final = validation.read_json(required["base final"], "redo base final")
    base_census = validation.read_json(required["base census"], "redo base census")

    if current_envelope.get("acceptance_path") != "confirmed":
        errors.append("redo requires a deterministically confirmed current accepted package")
    if current_metadata.get("publication_key") != marker.get("publication_key"):
        errors.append("current accepted publication_key differs from redo.json")
    if current_metadata.get("paper_id") != marker.get("paper_id"):
        errors.append("current accepted paper_id differs from redo.json")
    if current_census.get("paper_id") != marker.get("paper_id"):
        errors.append("current accepted census paper_id differs from redo.json")

    expected_hashes = {
        "base_final_sha256": canonical_sha256(current_final),
        "base_census_sha256": canonical_sha256(current_census),
        "base_metadata_sha256": canonical_sha256(current_metadata),
    }
    for field, expected in expected_hashes.items():
        if marker.get(field) != expected:
            errors.append(f"redo baseline is stale: {field} does not match current accepted state")
    if canonical_sha256(base_final) != marker.get("base_final_sha256"):
        errors.append("paper.base.final.json does not match redo.json")
    if canonical_sha256(base_census) != marker.get("base_census_sha256"):
        errors.append("paper.base.census.json does not match redo.json")
    if canonical_sha256(metadata) != marker.get("base_metadata_sha256"):
        errors.append("metadata.json changed after redo preparation")

    archived_source = archive_root / "paper.md"
    if not archived_source.is_file():
        errors.append("current archive has no paper.md")
    elif paths["source"].read_bytes() != archived_source.read_bytes():
        errors.append("paper.md changed after redo preparation or no longer matches current archive")

    if start_phase == 2 and canonical_sha256(census) != marker.get("base_census_sha256"):
        errors.append("Phase 2 redo must preserve the accepted census exactly")

    if isinstance(redo_number, int):
        expected_redo = _next_redo_sequence(current_envelope, archive_root)
        if redo_number != expected_redo:
            errors.append(
                f"redo sequence is stale: redo.json requests {redo_number:03d}, current next redo is {expected_redo:03d}"
            )
        redo_destination = archive_root / "redo" / f"{redo_number:03d}"
        if redo_destination.exists():
            errors.append(f"redo archive destination already exists: {redo_destination}")

    report = {
        "redo": redo_number,
        "start_phase": start_phase,
        "base_final_sha256": marker.get("base_final_sha256"),
        "base_census_sha256": marker.get("base_census_sha256"),
        "base_metadata_sha256": marker.get("base_metadata_sha256"),
    }
    return errors, report


def _phase5_schema_version(current_envelope, mode):
    if current_envelope.get("schema_version") == "1.5" or current_envelope.get("redos"):
        return "1.5"
    if mode == "revision" or current_envelope.get("revisions"):
        return "1.4"
    return "1.3"


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
    redo_path = working / "redo.json"
    is_phase5 = phase5_path.is_file()
    is_redo = redo_path.is_file()
    if is_phase5 and is_redo:
        errors.append("working folder cannot contain both phase5.json and redo.json")
    phase5_marker = validation.read_json(phase5_path, "Phase 5 marker") if is_phase5 else None
    redo_marker = validation.read_json(redo_path, "redo marker") if is_redo else None
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
    overwrite = getattr(args, "overwrite", False)
    phase5_report = None
    redo_report = None

    if is_phase5:
        if overwrite:
            errors.append("--overwrite cannot be used for Phase 5 confirmation")
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
    elif is_redo:
        if overwrite:
            errors.append("--overwrite cannot be used for redo confirmation")
        if not errors:
            redo_errors, redo_report = _validate_redo(
                marker=redo_marker,
                working=working,
                paths=paths,
                metadata=metadata,
                census=census,
                final_destination=final_destination,
                census_destination=census_destination,
                archive_root=archive_root,
            )
            errors.extend(f"redo: {error}" for error in redo_errors)
    else:
        collisions = [
            path
            for path in (final_destination, census_destination, archive_root)
            if path.exists()
        ]
        if collisions and not overwrite:
            errors.append(
                "destination already exists:\n" + "\n".join(str(path) for path in collisions)
            )
        elif overwrite:
            required_destinations = (final_destination, census_destination, archive_root)
            missing_destinations = [
                str(path) for path in required_destinations if not path.exists()
            ]
            if missing_destinations:
                errors.append(
                    "--overwrite requires the complete current accepted/archive set; missing:\n"
                    + "\n".join(missing_destinations)
                )
            elif not final_destination.is_file() or not census_destination.is_file() or not archive_root.is_dir():
                errors.append("--overwrite destinations have unexpected file types")
    if errors:
        raise ValueError("\n".join(errors))

    accepted_version = read_nel_version()
    previous_accepted = None
    version_history = None
    previous_version = None
    if overwrite:
        previous_accepted = validation.read_json(
            final_destination, "current accepted package"
        )
        previous_version = (
            previous_accepted.get("latest_version")
            or previous_accepted.get("accepted_in_version")
        )
        if not isinstance(previous_version, str) or not previous_version:
            raise ValueError("current accepted package has no prior version")
        _safe_version_directory(previous_version, "previous accepted version")
        _safe_version_directory(accepted_version, "current NEL version")
        version_history = list(
            previous_accepted.get("version_history") or [previous_version]
        )
        if not all(isinstance(version, str) and version for version in version_history):
            raise ValueError("current accepted package has an invalid version_history")
        if len(version_history) != len(set(version_history)):
            raise ValueError("current accepted package version_history contains duplicates")
        if previous_version not in version_history:
            raise ValueError("current accepted package latest_version is absent from version_history")
        if accepted_version in version_history:
            raise ValueError(
                f"current NEL version is already present in version history: {accepted_version}"
            )
        version_history.append(accepted_version)

    args.accept_dir.mkdir(parents=True, exist_ok=True)
    args.archive_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{args.publication_key}.", dir=args.accept_dir))
    staged_final = staging / final_destination.name
    staged_census = staging / census_destination.name
    archive_destination = archive_root
    current_envelope = None

    if is_phase5:
        current_envelope = validation.read_json(final_destination, "current accepted package")
        accepted = dict(current_envelope)
        accepted_at = datetime.now(timezone.utc).isoformat()
        accepted["schema_version"] = _phase5_schema_version(current_envelope, phase5_mode)
        if phase5_mode == "revision":
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
    elif is_redo:
        current_envelope = validation.read_json(final_destination, "current accepted package")
        accepted_at = datetime.now(timezone.utc).isoformat()
        redos = list(current_envelope.get("redos") or [])
        redos.append(
            {
                "redo": redo_report["redo"],
                "start_phase": redo_report["start_phase"],
                "accepted_at": accepted_at,
                "accepted_in_version": accepted_version,
                "base_final_sha256": redo_report["base_final_sha256"],
                "base_census_sha256": redo_report["base_census_sha256"],
                "base_metadata_sha256": redo_report["base_metadata_sha256"],
            }
        )
        accepted = {
            "schema_version": "1.5",
            "acceptance_path": "confirmed",
            "accepted_at": accepted_at,
            "accepted_at_source": "confirm",
            "accepted_in_version": current_envelope["accepted_in_version"],
            "metadata": metadata,
            "final": final,
            "redos": redos,
        }
        for field in ("version_history", "latest_version"):
            if field in current_envelope:
                accepted[field] = current_envelope[field]
        envelope_errors = validation.schema_errors(
            accepted, "accepted_package_schema.json", "accepted package"
        )
        if envelope_errors:
            raise ValueError("\n".join(envelope_errors))
    else:
        accepted_metadata = dict(metadata)
        if overwrite:
            accepted_metadata["version_history"] = version_history
            accepted_metadata["latest_version"] = accepted_version
        accepted = {
            "schema_version": "1.2",
            "acceptance_path": "confirmed",
            "accepted_at": datetime.now(timezone.utc).isoformat(),
            "accepted_at_source": "confirm",
            "accepted_in_version": accepted_version,
            "metadata": accepted_metadata,
            "final": final,
        }
        if overwrite:
            accepted["version_history"] = version_history
            accepted["latest_version"] = accepted_version

    staged_final.write_text(
        json.dumps(accepted, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    shutil.copyfile(paths["census"], staged_census)
    replacing_existing = is_phase5 or is_redo or overwrite
    old_final_bytes = final_destination.read_bytes() if replacing_existing else None
    old_census_bytes = census_destination.read_bytes() if replacing_existing else None
    staged_archive = None
    archive_backup = None
    replace_archive = overwrite or is_redo

    if overwrite:
        archive_staging_root = Path(
            tempfile.mkdtemp(prefix=f".{args.publication_key}.archive.", dir=args.archive_dir)
        )
        staged_archive = archive_staging_root / args.publication_key
        _copy_directory_contents(working, staged_archive)
        archived_metadata_path = staged_archive / "metadata.json"
        archived_metadata = validation.read_json(archived_metadata_path, "staged archive metadata")
        archived_metadata["version_history"] = version_history
        archived_metadata["latest_version"] = accepted_version
        archived_metadata_path.write_text(
            json.dumps(archived_metadata, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        existing_versions = archive_root / "versions"
        if existing_versions.is_dir():
            shutil.copytree(existing_versions, staged_archive / "versions")
        previous_snapshot = staged_archive / "versions" / previous_version
        if previous_snapshot.exists():
            raise ValueError(f"archive version snapshot already exists: {previous_snapshot}")
        _copy_directory_contents(archive_root, previous_snapshot, excluded={"versions"})
    elif is_redo:
        archive_staging_root = Path(
            tempfile.mkdtemp(prefix=f".{args.publication_key}.archive.", dir=args.archive_dir)
        )
        staged_archive = archive_staging_root / args.publication_key
        _copy_directory_contents(
            working,
            staged_archive,
            excluded={"redo.json", "paper.base.final.json", "paper.base.census.json"},
        )
        existing_redos = archive_root / "redo"
        if existing_redos.is_dir():
            shutil.copytree(existing_redos, staged_archive / "redo")
        redo_snapshot = staged_archive / "redo" / f"{redo_report['redo']:03d}"
        if redo_snapshot.exists():
            raise ValueError(f"redo archive destination already exists: {redo_snapshot}")
        _copy_directory_contents(archive_root, redo_snapshot, excluded={"redo"})
        shutil.copy2(final_destination, redo_snapshot / "accepted.final.json")
        shutil.copy2(census_destination, redo_snapshot / "accepted.census.json")
        (redo_snapshot / "replacement.redo.json").write_text(
            json.dumps(redo_marker, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    if replace_archive:
        archive_backup = archive_root.with_name(f".{archive_root.name}.confirm-backup")
        if archive_backup.exists():
            raise ValueError(f"stale archive confirmation backup exists: {archive_backup}")

    replaced_final = False
    replaced_census = False
    archive_backed_up = False
    replaced_archive = False
    try:
        if is_phase5:
            archive_destination.parent.mkdir(parents=True, exist_ok=True)
        elif replace_archive:
            os.replace(archive_root, archive_backup)
            archive_backed_up = True
            os.replace(staged_archive, archive_root)
            replaced_archive = True
        os.replace(staged_final, final_destination)
        replaced_final = True
        os.replace(staged_census, census_destination)
        replaced_census = True
        if replace_archive:
            shutil.rmtree(working, ignore_errors=True)
            shutil.rmtree(archive_backup, ignore_errors=True)
        else:
            shutil.move(str(working), str(archive_destination))
    except Exception:
        if replaced_final:
            if replacing_existing:
                _restore_bytes(final_destination, old_final_bytes)
            else:
                final_destination.unlink(missing_ok=True)
        if replaced_census:
            if replacing_existing:
                _restore_bytes(census_destination, old_census_bytes)
            else:
                census_destination.unlink(missing_ok=True)
        if replace_archive and archive_backed_up:
            if replaced_archive:
                shutil.rmtree(archive_root, ignore_errors=True)
            os.replace(archive_backup, archive_root)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        if staged_archive is not None:
            shutil.rmtree(staged_archive.parent, ignore_errors=True)

    operation = "phase5" if is_phase5 else "redo" if is_redo else "standard"
    operation_report = phase5_report if is_phase5 else redo_report if is_redo else None
    return warnings, report, archive_destination, operation, operation_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", dest="publication_key", required=True)
    parser.add_argument("--work-dir", type=Path, default=Path("work"))
    parser.add_argument("--accept-dir", type=Path, default=Path("accept"))
    parser.add_argument("--archive-dir", type=Path, default=Path("archive"))
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace the current accepted/archive contents while preserving version history; not used for redo.json workflows",
    )
    args = parser.parse_args()
    try:
        warnings, report, archive, operation, operation_report = confirm(args)
    except (OSError, ValueError) as exc:
        sys.exit(f"CONFIRM FAILED:\n{exc}")
    for warning in warnings:
        print(f"warning: {warning}")
    print(f"CONFIRMED: {args.publication_key}")
    if operation == "phase5":
        if operation_report.get("mode") == "revision":
            print(
                f"Phase 5 revision: {operation_report['revision']:03d}; "
                f"revised cards: {len(operation_report['revised_card_ids'])}"
            )
        else:
            print(
                f"Phase 5 supplement: {operation_report['supplement']:03d}; "
                f"added cards: {len(operation_report['added_card_ids'])}"
            )
    elif operation == "redo":
        print(
            f"Redo: {operation_report['redo']:03d}; "
            f"started from Phase {operation_report['start_phase']}"
        )
    print(f"Cards: {report['cards']}; census ratio: {report['ratio']}")
    print(f"Accepted: {args.accept_dir}")
    print(f"Archived: {archive}")


if __name__ == "__main__":
    main()
