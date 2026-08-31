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
import ingest_artifacts
import package_validation as validation
from phase_validation import card_deltas, phase2

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


def _resolve_lineage_file(working, kind, round_number, revision=None):
    if revision is not None:
        return ingest_artifacts.resolve_phase_for_round(
            working, kind, round_number, revision=revision
        )
    return ingest_artifacts.resolve_phase_any_revision_for_round(
        working, kind, round_number
    )


def _validate_original_history(paths, working, final, metadata, census, revision=None):
    errors = []
    warnings = []
    approved_round = (final.get("audit") or {}).get("approved_round")
    if not isinstance(approved_round, int):
        errors.append("final audit approved_round is missing or invalid")
        return errors, warnings, None, None, None
    try:
        provisional_path = _resolve_lineage_file(
            working, "provisional", approved_round, revision=revision
        )
        review_path = _resolve_lineage_file(
            working, "review", approved_round, revision=revision
        )
    except ValueError as exc:
        errors.append(str(exc))
        return errors, warnings, None, None, None
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

    identity = ingest_artifacts.phase_identity(provisional_path, "provisional")
    revision_id, attempt = identity if identity is not None else (revision, approved_round)
    phase2r_decisions_path = ingest_artifacts.resolve_decision_for_attempt(
        working, "phase2r", attempt, revision=revision_id
    )
    phase4_decisions_path = ingest_artifacts.resolve_decision_for_attempt(
        working, "phase4", attempt, revision=revision_id
    )
    if phase4_decisions_path is None and final.get("schema_version") == "5.1":
        errors.append(
            "schema 5.1 final package has no matching Phase 4 decision ledger; "
            "user-authorized provisional→final card deltas cannot be verified"
        )
        return errors, warnings, None, provisional_path, review_path

    provisional = validation.read_json(provisional_path, "approved provisional package")
    phase_1_errors, phase_1_warnings, _ = final_validation.validate_phase_files(
        phase=1,
        metadata_path=paths["metadata"],
        census_path=paths["census"],
    )
    errors.extend(f"phase 1: {error}" for error in phase_1_errors)
    warnings.extend(f"phase 1: {warning}" for warning in phase_1_warnings)
    provisional_errors, provisional_warnings = _validate_active_provisional(
        provisional=provisional,
        metadata=metadata,
        census=census,
        working=working,
        provisional_path=provisional_path,
    )
    errors.extend(f"provisional: {error}" for error in provisional_errors)
    warnings.extend(f"provisional: {warning}" for warning in provisional_warnings)
    phase_3_errors, phase_3_warnings, _ = final_validation.validate_phase_files(
        phase=3,
        provisional_path=provisional_path,
        review_path=review_path,
        phase2r_decisions_path=phase2r_decisions_path,
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
        decisions_path=phase4_decisions_path,
        phase2r_decisions_path=phase2r_decisions_path,
    )
    errors.extend(f"phase 4: {error}" for error in phase_4_errors)
    warnings.extend(f"phase 4: {warning}" for warning in phase_4_warnings)
    return errors, warnings, report, provisional_path, review_path



def _has_prior_phase4_handoff(working, provisional_path):
    """Return True when the active lineage has entered Phase 2R from Phase 4."""
    identity = ingest_artifacts.phase_identity(provisional_path, "provisional")
    if identity is None:
        return False
    revision, active_attempt = identity
    for path in Path(working).glob("paper.phase4-decisions*.json"):
        ledger_identity = ingest_artifacts.decision_identity(path, "phase4")
        if ledger_identity is None:
            continue
        ledger_revision, ledger_attempt = ledger_identity
        if ledger_revision != revision or ledger_attempt >= active_attempt:
            continue
        ledger = validation.read_json(path, "Phase 4 decision ledger")
        if ledger.get("purpose") == "phase2r_handoff":
            return True
    return False


def _validate_phase2r_delta_history(
    *, working, provisional_path, current_accepted_final=None, require_ledger=False
):
    """Re-check the active Phase 2R package against its user decision ledger."""
    errors = []
    identity = ingest_artifacts.phase_identity(provisional_path, "provisional")
    if identity is None:
        return errors
    revision, attempt = identity
    decisions_path = ingest_artifacts.resolve_decision_for_attempt(
        working, "phase2r", attempt, revision=revision
    )
    if decisions_path is None:
        if require_ledger:
            return [
                "active Phase 2R provisional has no matching user decision ledger; "
                "baseline→provisional card deltas cannot be verified"
            ]
        return errors
    ledger = validation.read_json(decisions_path, "Phase 2R decision ledger")
    provisional = validation.read_json(provisional_path, "Phase 2R provisional")
    baseline_name = ledger.get("baseline_filename")
    if baseline_name == "paper.final.json" and current_accepted_final is not None:
        baseline = current_accepted_final
    else:
        baseline_path = working / str(baseline_name)
        if not baseline_path.is_file():
            return [f"Phase 2R decision baseline file is missing: {baseline_name}"]
        baseline = validation.read_json(baseline_path, "Phase 2R baseline package")

    phase4_name = ledger.get("phase4_decisions_filename")
    if phase4_name:
        phase4_path = working / phase4_name
        if not phase4_path.is_file():
            errors.append(f"Phase 2R referenced Phase 4 decision ledger is missing: {phase4_name}")
        else:
            phase4_ledger = validation.read_json(phase4_path, "Phase 4 handoff decision ledger")
            review_name = phase4_ledger.get("review_filename")
            review_path = working / str(review_name)
            allowed_direct_ids = None
            if not review_path.is_file():
                errors.append(f"Phase 4 handoff review file is missing: {review_name}")
            else:
                review = validation.read_json(review_path, "Phase 4 handoff review")
                allowed_direct_ids = {
                    item.get("card_id") for item in review.get("card_results", [])
                    if item.get("verdict") == "fail"
                }
            errors.extend(
                f"Phase 4 handoff: {error}"
                for error in card_deltas.validate_ledger_against_baseline(
                    phase4_ledger, baseline, stage="phase4",
                    allowed_direct_ids=allowed_direct_ids,
                )
            )
            baseline = card_deltas.apply_card_decisions(baseline, phase4_ledger)
            baseline = card_deltas.apply_publication_type_decision(baseline, phase4_ledger)

    errors.extend(
        f"Phase 2R decisions: {error}"
        for error in card_deltas.validate_package_delta(
            baseline, provisional, ledger, stage="phase2r"
        )
    )
    return errors


def _validate_active_provisional(
    *, provisional, metadata, census, working, provisional_path
):
    """Replay current Phase 2 package policy without rechecking superseded quotes.

    Confirmation deliberately validates source quotes on the final package only: Phase 4
    may correct a bad provisional quote. All other package policy is owned by the current
    Phase 2 validator, including schema-5.1 interpretation surfacing. In Phase 2R, that
    newer policy applies only to cards authorized as changed by the matching ledger.
    """
    errors, warnings, _ = validation.validate_package(
        provisional,
        metadata,
        census,
        source_text=None,
        require_final=False,
    )
    identity = ingest_artifacts.phase_identity(provisional_path, "provisional")
    revision, attempt = identity if identity is not None else (None, None)
    decisions_path = (
        ingest_artifacts.resolve_decision_for_attempt(
            working, "phase2r", attempt, revision=revision
        )
        if attempt is not None
        else None
    )
    if decisions_path is None:
        surfacing_scope = None
    else:
        ledger = validation.read_json(decisions_path, "Phase 2R decision ledger")
        surfacing_scope = card_deltas.changed_card_ids(ledger)
    errors.extend(
        phase2.interpretation_surfacing_errors(provisional, surfacing_scope)
    )
    return errors, warnings


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
    *, marker, working, paths, metadata, census, final_destination,
    census_destination, archive_root,
):
    errors = []
    schema_version = marker.get("schema_version")
    if schema_version in {"2.0", "2.1"}:
        mode = marker.get("mode")
        if mode not in {"census", "provisional", "cards"}:
            errors.append("redo.json mode must be census, provisional, or cards")
        start_phase = 1 if mode == "census" else 2
    elif schema_version == "1.0":
        # Compatibility for a Phase 1/2 redo prepared by the legacy CLI.
        start_phase = marker.get("start_phase")
        if start_phase not in {1, 2}:
            errors.append("legacy redo.json start_phase must be 1 or 2")
        mode = "census" if start_phase == 1 else "provisional"
    else:
        errors.append("redo.json has unsupported schema_version")
        mode = None
        start_phase = None

    baseline_source = marker.get("baseline_source", "accepted")
    if schema_version == "2.1" and baseline_source not in {"accepted", "archive"}:
        errors.append("redo.json baseline_source must be accepted or archive")
    if schema_version != "2.1":
        baseline_source = "accepted"

    if marker.get("publication_key") != metadata.get("publication_key"):
        errors.append("redo.json publication_key does not match metadata")
    if marker.get("paper_id") != metadata.get("paper_id"):
        errors.append("redo.json paper_id does not match metadata")
    redo_number = marker.get("redo")
    if not isinstance(redo_number, int) or redo_number < 1:
        errors.append("redo.json redo must be a positive integer")
    revision = marker.get("revision") if mode == "cards" else None
    if mode == "cards" and (not isinstance(revision, int) or revision < 1):
        errors.append("cards redo requires a positive accepted-card revision number")

    if not archive_root.is_dir():
        errors.append(f"redo archive folder is missing or invalid: {archive_root}")
        return errors, None

    if baseline_source == "accepted":
        if not final_destination.is_file() or not census_destination.is_file():
            errors.append("accepted-baseline redo requires the complete current accepted pair")
            return errors, None
        current_envelope = validation.read_json(final_destination, "current accepted package")
        current_census = validation.read_json(census_destination, "current accepted census")
        current_metadata = current_envelope.get("metadata") or {}
        current_final = current_envelope.get("final") or {}
        if current_envelope.get("acceptance_path") != "confirmed":
            errors.append("redo requires a deterministically confirmed current accepted package")
    else:
        if final_destination.exists() or census_destination.exists():
            errors.append(
                "archive-baseline redo requires accepted destinations to remain absent after preparation"
            )
        archived_metadata_path = archive_root / "metadata.json"
        archived_final_path = archive_root / "paper.final.json"
        archived_census_path = ingest_artifacts.resolve_census(archive_root)
        missing_baseline = [
            str(path)
            for path in (archived_metadata_path, archived_final_path)
            if not path.is_file()
        ]
        if archived_census_path is None:
            missing_baseline.append(str(archive_root / "paper census (legacy or versioned)"))
        if missing_baseline:
            errors.append("archive redo baseline is incomplete:\n" + "\n".join(missing_baseline))
            return errors, None
        current_envelope = {}
        current_metadata = validation.read_json(archived_metadata_path, "current archived metadata")
        current_final = validation.read_json(archived_final_path, "current archived final")
        current_census = validation.read_json(archived_census_path, "current archived census")

    if current_metadata.get("publication_key") != marker.get("publication_key"):
        errors.append(f"current {baseline_source} publication_key differs from redo.json")
    if current_metadata.get("paper_id") != marker.get("paper_id"):
        errors.append(f"current {baseline_source} metadata paper_id differs from redo.json")
    if current_final.get("paper_id") != marker.get("paper_id"):
        errors.append(f"current {baseline_source} final paper_id differs from redo.json")
    if current_census.get("paper_id") != marker.get("paper_id"):
        errors.append(f"current {baseline_source} census paper_id differs from redo.json")

    expected_hashes = {
        "base_final_sha256": canonical_sha256(current_final),
        "base_census_sha256": canonical_sha256(current_census),
        "base_metadata_sha256": canonical_sha256(current_metadata),
    }
    for field, expected in expected_hashes.items():
        if marker.get(field) != expected:
            errors.append(
                f"redo baseline is stale: {field} does not match current {baseline_source} state"
            )
    if canonical_sha256(metadata) != marker.get("base_metadata_sha256"):
        errors.append("metadata.json changed after redo preparation")

    archived_source = archive_root / "paper.md"
    if not archived_source.is_file():
        errors.append("current archive has no paper.md")
    elif paths["source"].read_bytes() != archived_source.read_bytes():
        errors.append("paper.md changed after redo preparation or no longer matches current archive")

    if mode in {"provisional", "cards"} and canonical_sha256(census) != marker.get("base_census_sha256"):
        errors.append(f"{mode} redo must preserve the accepted census exactly")

    if schema_version == "1.0":
        base_final_path = working / "paper.base.final.json"
        base_census_path = working / "paper.base.census.json"
        if not base_final_path.is_file() or not base_census_path.is_file():
            errors.append("legacy redo requires paper.base.final.json and paper.base.census.json")
        else:
            if canonical_sha256(validation.read_json(base_final_path, "redo base final")) != marker.get("base_final_sha256"):
                errors.append("paper.base.final.json does not match redo.json")
            if canonical_sha256(validation.read_json(base_census_path, "redo base census")) != marker.get("base_census_sha256"):
                errors.append("paper.base.census.json does not match redo.json")

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
        "mode": mode,
        "start_phase": start_phase,
        "base_final_sha256": marker.get("base_final_sha256"),
        "base_census_sha256": marker.get("base_census_sha256"),
        "base_metadata_sha256": marker.get("base_metadata_sha256"),
        "baseline_source": baseline_source,
    }
    if revision is not None:
        report["revision"] = revision
    return errors, report


def confirm(args):
    working = args.work_dir / args.publication_key
    if not working.is_dir():
        raise ValueError(f"working folder not found: {working}")
    census_path = ingest_artifacts.resolve_census(working)
    paths = {
        "metadata": working / "metadata.json",
        "census": census_path,
        "source": working / "paper.md",
        "final": working / "paper.final.json",
    }
    missing = [
        str(path) if path is not None else "paper census (legacy or versioned)"
        for path in paths.values()
        if path is None or not path.is_file()
    ]
    if missing:
        raise ValueError("required working files missing:\n" + "\n".join(missing))

    metadata = validation.read_json(paths["metadata"], "metadata")
    census = validation.read_json(paths["census"], "census")
    final = validation.read_json(paths["final"], "final package")
    errors = []
    warnings = []
    if metadata.get("publication_key") != args.publication_key:
        errors.append("metadata publication_key does not match --key")

    redo_path = working / "redo.json"
    is_redo = redo_path.is_file()
    redo_marker = validation.read_json(redo_path, "redo marker") if is_redo else None
    revision = redo_marker.get("revision") if is_redo and redo_marker.get("mode") == "cards" else None

    original_errors, original_warnings, report, active_provisional_path, _ = _validate_original_history(
        paths, working, final, metadata, census, revision=revision
    )
    errors.extend(original_errors)
    warnings.extend(original_warnings)

    final_destination = args.accept_dir / f"{args.publication_key}.final.json"
    census_destination = args.accept_dir / f"{args.publication_key}.census.json"
    archive_root = args.archive_dir / args.publication_key
    overwrite = getattr(args, "overwrite", False)
    redo_report = None

    if is_redo:
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
            path for path in (final_destination, census_destination, archive_root) if path.exists()
        ]
        if collisions and not overwrite:
            errors.append("destination already exists:\n" + "\n".join(str(path) for path in collisions))
        elif overwrite:
            required_destinations = (final_destination, census_destination, archive_root)
            missing_destinations = [str(path) for path in required_destinations if not path.exists()]
            if missing_destinations:
                errors.append(
                    "--overwrite requires the complete current accepted/archive set; missing:\n"
                    + "\n".join(missing_destinations)
                )
            elif not final_destination.is_file() or not census_destination.is_file() or not archive_root.is_dir():
                errors.append("--overwrite destinations have unexpected file types")
    if not errors and active_provisional_path is not None:
        current_accepted_final = None
        if is_redo:
            if redo_marker.get("baseline_source", "accepted") == "archive":
                current_accepted_final = validation.read_json(
                    archive_root / "paper.final.json", "current archived final"
                )
            elif final_destination.is_file():
                current_envelope_for_delta = validation.read_json(
                    final_destination, "current accepted package"
                )
                current_accepted_final = current_envelope_for_delta.get("final") or None
        require_phase2r_ledger = bool(
            is_redo and redo_marker.get("mode") == "cards"
        ) or _has_prior_phase4_handoff(working, active_provisional_path)
        errors.extend(
            _validate_phase2r_delta_history(
                working=working,
                provisional_path=active_provisional_path,
                current_accepted_final=current_accepted_final,
                require_ledger=require_phase2r_ledger,
            )
        )

    if errors:
        raise ValueError("\n".join(errors))

    accepted_version = read_nel_version()
    previous_accepted = None
    version_history = None
    previous_version = None
    if overwrite:
        previous_accepted = validation.read_json(final_destination, "current accepted package")
        previous_version = previous_accepted.get("latest_version") or previous_accepted.get("accepted_in_version")
        if not isinstance(previous_version, str) or not previous_version:
            raise ValueError("current accepted package has no prior version")
        _safe_version_directory(previous_version, "previous accepted version")
        _safe_version_directory(accepted_version, "current NEL version")
        version_history = list(previous_accepted.get("version_history") or [previous_version])
        if not all(isinstance(version, str) and version for version in version_history):
            raise ValueError("current accepted package has an invalid version_history")
        if len(version_history) != len(set(version_history)):
            raise ValueError("current accepted package version_history contains duplicates")
        if previous_version not in version_history:
            raise ValueError("current accepted package latest_version is absent from version_history")
        if accepted_version in version_history:
            raise ValueError(f"current NEL version is already present in version history: {accepted_version}")
        version_history.append(accepted_version)

    args.accept_dir.mkdir(parents=True, exist_ok=True)
    args.archive_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{args.publication_key}.", dir=args.accept_dir))
    staged_final = staging / final_destination.name
    staged_census = staging / census_destination.name
    archive_destination = archive_root

    if is_redo:
        baseline_source = redo_report["baseline_source"]
        current_envelope = (
            validation.read_json(final_destination, "current accepted package")
            if baseline_source == "accepted"
            else {}
        )
        accepted_at = datetime.now(timezone.utc).isoformat()
        redos = list(current_envelope.get("redos") or [])
        redo_record = {
            "redo": redo_report["redo"],
            "start_phase": redo_report["start_phase"],
            "accepted_at": accepted_at,
            "accepted_in_version": accepted_version,
            "base_final_sha256": redo_report["base_final_sha256"],
            "base_census_sha256": redo_report["base_census_sha256"],
            "base_metadata_sha256": redo_report["base_metadata_sha256"],
            "baseline_source": baseline_source,
        }
        if redo_report.get("mode"):
            redo_record["mode"] = redo_report["mode"]
        if redo_report.get("revision") is not None:
            redo_record["revision"] = redo_report["revision"]
        redos.append(redo_record)
        accepted = dict(current_envelope)
        accepted.update({
            "schema_version": "1.5",
            "acceptance_path": "confirmed",
            "accepted_at": accepted_at,
            "accepted_at_source": "confirm",
            "accepted_in_version": current_envelope.get("accepted_in_version", accepted_version),
            "metadata": metadata,
            "final": final,
            "redos": redos,
        })
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

    staged_final.write_text(json.dumps(accepted, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    shutil.copyfile(paths["census"], staged_census)
    replacing_existing = overwrite or (
        is_redo and redo_report["baseline_source"] == "accepted"
    )
    old_final_bytes = final_destination.read_bytes() if replacing_existing else None
    old_census_bytes = census_destination.read_bytes() if replacing_existing else None
    staged_archive = None
    archive_backup = None
    replace_archive = overwrite or is_redo

    if overwrite:
        archive_staging_root = Path(tempfile.mkdtemp(prefix=f".{args.publication_key}.archive.", dir=args.archive_dir))
        staged_archive = archive_staging_root / args.publication_key
        _copy_directory_contents(working, staged_archive)
        archived_metadata_path = staged_archive / "metadata.json"
        archived_metadata = validation.read_json(archived_metadata_path, "staged archive metadata")
        archived_metadata["version_history"] = version_history
        archived_metadata["latest_version"] = accepted_version
        archived_metadata_path.write_text(
            json.dumps(archived_metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        existing_versions = archive_root / "versions"
        if existing_versions.is_dir():
            shutil.copytree(existing_versions, staged_archive / "versions")
        previous_snapshot = staged_archive / "versions" / previous_version
        if previous_snapshot.exists():
            raise ValueError(f"archive version snapshot already exists: {previous_snapshot}")
        _copy_directory_contents(archive_root, previous_snapshot, excluded={"versions"})
    elif is_redo:
        archive_staging_root = Path(tempfile.mkdtemp(prefix=f".{args.publication_key}.archive.", dir=args.archive_dir))
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
        if redo_report["baseline_source"] == "accepted":
            shutil.copy2(final_destination, redo_snapshot / "accepted.final.json")
            shutil.copy2(census_destination, redo_snapshot / "accepted.census.json")
        (redo_snapshot / "replacement.redo.json").write_text(
            json.dumps(redo_marker, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
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
        if replace_archive:
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

    operation = "redo" if is_redo else "standard"
    return warnings, report, archive_destination, operation, redo_report


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
    if operation == "redo":
        detail = f"Redo: {operation_report['redo']:03d}; mode: {operation_report['mode']}"
        if operation_report.get("revision") is not None:
            detail += f"; accepted-card revision: {operation_report['revision']:03d}"
        print(detail)
    print(f"Cards: {report['cards']}; census ratio: {report['ratio']}")
    print(f"Accepted: {args.accept_dir}")
    print(f"Archived: {archive}")


if __name__ == "__main__":
    main()
