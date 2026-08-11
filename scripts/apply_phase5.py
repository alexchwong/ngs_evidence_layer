#!/usr/bin/env python3
"""Apply a reviewed Phase 5 revision asset to the frozen local final package."""
import argparse
import copy
import json
import os
import re
import sys
import tempfile
from pathlib import Path

import package_validation as validation
import phase5_chat_validation as chat_validation

CARD_TOKEN_RE = re.compile(r"^(?:C)?(\d{4})$", re.IGNORECASE)


def read_json(path, label="JSON"):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read {label} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid {label} in {path}: {exc}") from exc


def _maps(items, key="card_id"):
    return {item.get(key): item for item in items}


def _parse_card_tokens(value):
    tokens = []
    for raw in str(value).split(","):
        token = raw.strip()
        match = CARD_TOKEN_RE.fullmatch(token)
        if not match:
            raise ValueError("--cards must be a comma-separated list of four-digit card IDs")
        short_id = match.group(1)
        if short_id in tokens:
            raise ValueError(f"duplicate --cards value: {short_id}")
        tokens.append(short_id)
    if not tokens:
        raise ValueError("--cards requires at least one card ID")
    return tokens


def _replace_by_card_id(items, replacements, label):
    result = []
    seen = set()
    for item in items:
        card_id = item.get("card_id")
        if card_id in replacements:
            result.append(copy.deepcopy(replacements[card_id]))
            seen.add(card_id)
        else:
            result.append(copy.deepcopy(item))
    missing = sorted(set(replacements) - seen)
    if missing:
        raise ValueError(f"cannot replace missing {label}: " + ", ".join(missing))
    return result


def _remove_by_card_id(items, removals, label):
    result = []
    seen = set()
    for item in items:
        card_id = item.get("card_id")
        if card_id in removals:
            seen.add(card_id)
        else:
            result.append(copy.deepcopy(item))
    missing = sorted(set(removals) - seen)
    if missing:
        raise ValueError(f"cannot delete missing {label}: " + ", ".join(missing))
    return result


def _refresh_derived_fields(final):
    final["genes_covered"] = sorted(
        {gene for card in final.get("cards", []) for gene in card.get("genes", [])}
    )
    final["diseases_covered"] = sorted(
        {disease for card in final.get("cards", []) for disease in card.get("diseases", [])}
    )


def _atomic_write_json(path, document):
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


def apply_revision(args):
    working = args.work_dir / args.publication_key
    if not working.is_dir():
        raise ValueError(f"working folder not found: {working}")
    paths = {
        "marker": working / "phase5.json",
        "targets": working / "paper.phase5-targets.json",
        "base_final": working / "paper.base.final.json",
        "base_census": working / "paper.base.census.json",
        "current_final": working / "paper.final.json",
        "source": working / "paper.md",
        "metadata": working / "metadata.json",
        "census": working / "paper.census.json",
        "provisional": working / "paper.phase5-provisional.json",
        "review": working / "paper.phase5-review.json",
        "asset": working / "paper.phase5-revision.json",
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise ValueError("required Phase 5 revision files missing:\n" + "\n".join(missing))
    marker = read_json(paths["marker"], "Phase 5 marker")
    targets = read_json(paths["targets"], "Phase 5 targets")
    base_final = read_json(paths["base_final"], "base final")
    base_census = read_json(paths["base_census"], "base census")
    current_final = read_json(paths["current_final"], "current working final")
    provisional = read_json(paths["provisional"], "Phase 5 provisional")
    review = read_json(paths["review"], "Phase 5 review")
    asset = read_json(paths["asset"], "Phase 5 revision asset")
    paper_text = paths["source"].read_text(encoding="utf-8")
    metadata = read_json(paths["metadata"], "metadata")
    census = read_json(paths["census"], "census")
    if marker.get("mode") != "revision":
        raise ValueError("apply_phase5.py only applies Phase 5 revision mode")
    if marker.get("publication_key") != args.publication_key:
        raise ValueError("phase5 publication_key does not match --key")
    if marker.get("base_final_sha256") != chat_validation.canonical_sha256(base_final):
        raise ValueError("paper.base.final.json does not match phase5 base_final_sha256")
    if marker.get("base_census_sha256") != chat_validation.canonical_sha256(base_census):
        raise ValueError("paper.base.census.json does not match phase5 base_census_sha256")
    if current_final != base_final:
        raise ValueError(
            "paper.final.json changed before deterministic Phase 5 application; restore the prepared baseline"
        )
    accepted_final_path = args.accept_dir / f"{args.publication_key}.final.json"
    accepted_census_path = args.accept_dir / f"{args.publication_key}.census.json"
    if not accepted_final_path.is_file() or not accepted_census_path.is_file():
        raise ValueError("current accepted final/census pair is required")
    accepted_envelope = read_json(accepted_final_path, "current accepted package")
    accepted_census = read_json(accepted_census_path, "current accepted census")
    if accepted_envelope.get("final") != base_final:
        raise ValueError("accepted final changed since Phase 5 preparation")
    if accepted_census != base_census:
        raise ValueError("accepted census changed since Phase 5 preparation")
    errors = chat_validation.validate_revision_provisional(
        marker, targets, provisional, paper_text
    )
    errors.extend(
        chat_validation.validate_revision_asset(marker, targets, provisional, review, asset)
    )
    if errors:
        raise ValueError("\n".join(errors))

    target_map = _maps(targets.get("targets", []))
    base_cards = _maps(base_final.get("cards", []))
    base_evidence = _maps(base_final.get("evidence", []))
    replacement_cards = {}
    replacement_evidence = {}
    revised_ids = []
    for revision in asset.get("revisions", []):
        card_id = revision["card_id"]
        target = target_map.get(card_id)
        if target is None:
            raise ValueError(f"off-target revision: {card_id}")
        if chat_validation.canonical_sha256(base_cards.get(card_id)) != target.get("card_sha256"):
            raise ValueError(f"{card_id}: base card no longer matches prepared target hash")
        if chat_validation.canonical_sha256(base_evidence.get(card_id)) != target.get("evidence_sha256"):
            raise ValueError(f"{card_id}: base evidence no longer matches prepared target hash")
        replacement_cards[card_id] = revision["replacement_card"]
        replacement_evidence[card_id] = revision["replacement_evidence"]
        revised_ids.append(card_id)

    deleted_ids = []
    for deletion in asset.get("deletions", []):
        card_id = deletion["card_id"]
        target = target_map.get(card_id)
        if target is None:
            raise ValueError(f"off-target deletion: {card_id}")
        if chat_validation.canonical_sha256(base_cards.get(card_id)) != target.get("card_sha256"):
            raise ValueError(f"{card_id}: base card no longer matches prepared target hash")
        if chat_validation.canonical_sha256(base_evidence.get(card_id)) != target.get("evidence_sha256"):
            raise ValueError(f"{card_id}: base evidence no longer matches prepared target hash")
        deleted_ids.append(card_id)

    expected_ids = set(revised_ids) | set(deleted_ids)
    requested_ids = {
        f"{args.publication_key}-C{short_id}" for short_id in _parse_card_tokens(args.cards)
    }
    if requested_ids != expected_ids:
        expected = ",".join(sorted(card_id.rsplit("C", 1)[-1] for card_id in expected_ids))
        requested = ",".join(sorted(card_id.rsplit("C", 1)[-1] for card_id in requested_ids))
        raise ValueError(
            "--cards must exactly match cards modified or deleted by the reviewed Phase 5 asset; "
            f"expected [{expected}], received [{requested}]"
        )

    deleted = set(deleted_ids)
    final = copy.deepcopy(base_final)
    final["cards"] = _remove_by_card_id(
        _replace_by_card_id(base_final.get("cards", []), replacement_cards, "card"),
        deleted,
        "card",
    )
    final["evidence"] = _remove_by_card_id(
        _replace_by_card_id(base_final.get("evidence", []), replacement_evidence, "evidence"),
        deleted,
        "evidence",
    )
    final_audit = copy.deepcopy(base_final.get("audit") or {})
    final_audit["results"] = _remove_by_card_id(
        final_audit.get("results", []), deleted, "audit result"
    )
    final["audit"] = final_audit
    _refresh_derived_fields(final)

    final_cards = _maps(final.get("cards", []))
    final_evidence = _maps(final.get("evidence", []))
    for card_id in base_cards:
        if card_id in deleted:
            if card_id in final_cards or card_id in final_evidence:
                raise ValueError(f"{card_id}: deleted card/evidence still present")
        elif card_id in replacement_cards:
            if final_cards[card_id] != replacement_cards[card_id]:
                raise ValueError(f"{card_id}: final card does not equal reviewed replacement")
            if final_evidence[card_id] != replacement_evidence[card_id]:
                raise ValueError(f"{card_id}: final evidence does not equal reviewed replacement")
        else:
            if final_cards[card_id] != base_cards[card_id]:
                raise ValueError(f"off-target card changed during application: {card_id}")
            if final_evidence[card_id] != base_evidence[card_id]:
                raise ValueError(f"off-target evidence changed during application: {card_id}")

    allowed_top_level_changes = {"cards", "evidence", "audit", "genes_covered", "diseases_covered"}
    for field in set(base_final) - allowed_top_level_changes:
        if final.get(field) != base_final.get(field):
            raise ValueError(f"off-target top-level final field changed: {field}")
    base_audit = base_final.get("audit") or {}
    for field in set(base_audit) - {"results"}:
        if final_audit.get(field) != base_audit.get(field):
            raise ValueError(f"off-target final audit field changed: {field}")
    expected_audit_results = {
        card_id: result
        for card_id, result in _maps(base_audit.get("results", [])).items()
        if card_id not in deleted
    }
    if _maps(final_audit.get("results", [])) != expected_audit_results:
        raise ValueError("final audit results changed outside deleted cards")

    package_errors, _warnings, _report = validation.validate_package(
        final, metadata, census, source_text=paper_text, require_final=True
    )
    if package_errors:
        raise ValueError("revised final package failed validation:\n" + "\n".join(package_errors))
    _atomic_write_json(paths["current_final"], final)
    return working, revised_ids, deleted_ids


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", dest="publication_key", required=True)
    parser.add_argument(
        "--cards",
        required=True,
        help="comma-separated four-digit existing card IDs actually modified or deleted",
    )
    parser.add_argument("--work-dir", type=Path, default=Path("work"))
    parser.add_argument("--accept-dir", type=Path, default=Path("accept"))
    args = parser.parse_args()
    try:
        working, revised_ids, deleted_ids = apply_revision(args)
    except (OSError, ValueError, KeyError) as exc:
        sys.exit(f"PHASE 5 APPLY FAILED:\n{exc}")
    print(f"PHASE 5 REVISION APPLIED: {args.publication_key}")
    print("Modified: " + (", ".join(revised_ids) or "none"))
    print("Deleted: " + (", ".join(deleted_ids) or "none"))
    print(f"Final: {working / 'paper.final.json'}")


if __name__ == "__main__":
    main()
