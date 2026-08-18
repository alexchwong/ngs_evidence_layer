#!/usr/bin/env python3
"""Shared deterministic card-delta validation for Phase 2R and Phase 4."""
import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

BUNDLE_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = BUNDLE_ROOT / "schema"


def _load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


DECISION_SCHEMA = _load_json(SCHEMA_DIR / "card_decision_schema.json")


def schema_errors(ledger, label="decision ledger"):
    errors = sorted(
        Draft202012Validator(DECISION_SCHEMA, format_checker=FormatChecker()).iter_errors(ledger),
        key=lambda error: list(error.absolute_path),
    )
    return [
        f"{label} schema: {'/'.join(str(p) for p in error.absolute_path) or '<root>'}: {error.message}"
        for error in errors
    ]


def index_package(package):
    cards = {card["card_id"]: card for card in package.get("cards", []) if isinstance(card, dict) and "card_id" in card}
    evidence = {item["card_id"]: item for item in package.get("evidence", []) if isinstance(item, dict) and "card_id" in item}
    return cards, evidence


def changed_card_ids(ledger):
    return [
        item["card_id"]
        for item in ledger.get("card_decisions", [])
        if item.get("decision") in {"add", "modify"}
    ]


def deleted_card_ids(ledger):
    return [
        item["card_id"]
        for item in ledger.get("card_decisions", [])
        if item.get("decision") == "delete"
    ]


def validate_ledger_against_baseline(ledger, baseline, *, stage=None, allowed_direct_ids=None):
    errors = schema_errors(ledger)
    if errors:
        return errors
    if stage is not None and ledger.get("stage") != stage:
        errors.append(f"decision ledger stage must be {stage}")
    if stage == "phase2r" and ledger.get("purpose") != "revise":
        errors.append("Phase 2R decision ledger purpose must be revise")
    if ledger.get("paper_id") != baseline.get("paper_id"):
        errors.append("decision ledger paper_id does not match baseline package")
    if ledger.get("baseline_round") != baseline.get("round"):
        errors.append("decision ledger baseline_round does not match baseline package round")

    cards, evidence = index_package(baseline)
    seen = set()
    added = set()
    for index, item in enumerate(ledger.get("card_decisions", []), start=1):
        decision = item["decision"]
        card_id = item["card_id"]
        label = f"decision {index} ({decision} {card_id})"
        if stage == "phase2r" and decision == "retain":
            errors.append(f"{label}: Phase 2R records only add, modify, or delete deltas; unchanged cards need no decision")
        if card_id in seen:
            errors.append(f"{label}: card_id appears in more than one decision")
        seen.add(card_id)
        if allowed_direct_ids is not None and decision in {"modify", "delete", "retain"} and card_id not in allowed_direct_ids:
            errors.append(f"{label}: Phase 4 may directly modify/delete only a Phase 3-failed card; route this card through Phase 2R")
        if decision == "add":
            if card_id in cards or card_id in added:
                errors.append(f"{label}: add card_id already exists in baseline")
            if stage == "phase4" and allowed_direct_ids is not None:
                related = item.get("related_card_id")
                if related not in allowed_direct_ids:
                    errors.append(
                        f"{label}: Phase 4 add must name related_card_id for a Phase 3-failed card; otherwise route the addition through Phase 2R"
                    )
            added.add(card_id)
        elif decision in {"modify", "delete", "retain"}:
            if card_id not in cards:
                errors.append(f"{label}: baseline has no such card")
        if decision in {"add", "modify"}:
            card = item.get("card") or {}
            ev = item.get("evidence") or {}
            if card.get("card_id") != card_id:
                errors.append(f"{label}: replacement card.card_id must equal decision card_id")
            if ev.get("card_id") != card_id:
                errors.append(f"{label}: replacement evidence.card_id must equal decision card_id")
            if decision == "modify" and card_id in cards and card == cards[card_id] and ev == evidence.get(card_id):
                errors.append(f"{label}: modify decision does not change card or evidence")
    return errors


def apply_card_decisions(baseline, ledger):
    """Return a deep-copied package with exactly the ledger's card/evidence deltas applied."""
    result = copy.deepcopy(baseline)
    cards = list(result.get("cards", []))
    evidence = list(result.get("evidence", []))
    card_positions = {card["card_id"]: index for index, card in enumerate(cards)}
    evidence_positions = {item["card_id"]: index for index, item in enumerate(evidence)}

    delete_ids = {item["card_id"] for item in ledger.get("card_decisions", []) if item["decision"] == "delete"}
    if delete_ids:
        cards = [card for card in cards if card.get("card_id") not in delete_ids]
        evidence = [item for item in evidence if item.get("card_id") not in delete_ids]
        card_positions = {card["card_id"]: index for index, card in enumerate(cards)}
        evidence_positions = {item["card_id"]: index for index, item in enumerate(evidence)}

    for item in ledger.get("card_decisions", []):
        decision = item["decision"]
        card_id = item["card_id"]
        if decision == "modify":
            cards[card_positions[card_id]] = copy.deepcopy(item["card"])
            evidence[evidence_positions[card_id]] = copy.deepcopy(item["evidence"])
        elif decision == "add":
            cards.append(copy.deepcopy(item["card"]))
            evidence.append(copy.deepcopy(item["evidence"]))
            card_positions[card_id] = len(cards) - 1
            evidence_positions[card_id] = len(evidence) - 1

    result["cards"] = cards
    result["evidence"] = evidence
    return result


def validate_package_delta(baseline, output, ledger, *, stage=None, allowed_direct_ids=None):
    errors = validate_ledger_against_baseline(
        ledger, baseline, stage=stage, allowed_direct_ids=allowed_direct_ids
    )
    if errors:
        return errors
    expected = apply_card_decisions(baseline, ledger)
    if output.get("cards") != expected.get("cards"):
        errors.append("card diff does not exactly match the user-authorized decision ledger")
    if output.get("evidence") != expected.get("evidence"):
        errors.append("evidence diff does not exactly match the user-authorized decision ledger")
    return errors


def apply_publication_type_decision(package, ledger):
    result = copy.deepcopy(package)
    decision = ledger.get("publication_type_decision")
    if decision:
        result["publication_type"] = decision["publication_type"]
        result["publication_type_basis"] = decision["publication_type_basis"]
    return result
