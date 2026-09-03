from copy import deepcopy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "phase_validation"))
import card_deltas


PAPER_ID = "11111111-1111-4111-8111-111111111111"
CARD_ID = "example-paper-C0001"


def _baseline():
    return {
        "paper_id": PAPER_ID,
        "round": 1,
        "cards": [
            {
                "card_id": CARD_ID,
                "category": "diagnosis",
                "genes": ["JAK2"],
                "diseases": ["MPN"],
                "interpretation": "JAK2 supports an MPN diagnosis.",
            }
        ],
        "evidence": [
            {
                "card_id": CARD_ID,
                "evidence_type": "contiguous_text",
                "fragments": [
                    {"fragment_id": "F1", "role": "claim", "quote": "bad extracted quote"}
                ],
                "support_map": {"interpretation": ["F1"]},
                "table_relations": [],
            }
        ],
    }


def _ledger(card, evidence):
    return {
        "schema_version": "1.0",
        "stage": "phase4",
        "purpose": "finalize",
        "paper_id": PAPER_ID,
        "baseline_filename": "paper.provisional-001.json",
        "baseline_round": 1,
        "output_filename": "paper.final.json",
        "review_filename": "paper.review-001.json",
        "user_finalized": True,
        "paper_nickname": "Example paper",
        "card_decisions": [
            {
                "decision": "modify",
                "card_id": CARD_ID,
                "user_instruction": "Repair the non-verbatim evidence only.",
                "card": card,
                "evidence": evidence,
            }
        ],
    }


def test_phase4_allows_evidence_only_modify_on_phase3_passed_card():
    baseline = _baseline()
    repaired_evidence = deepcopy(baseline["evidence"][0])
    repaired_evidence["fragments"][0]["quote"] = "source-verbatim replacement"
    ledger = _ledger(deepcopy(baseline["cards"][0]), repaired_evidence)

    errors = card_deltas.validate_ledger_against_baseline(
        ledger,
        baseline,
        stage="phase4",
        allowed_direct_ids=set(),
    )

    assert errors == []


def test_phase4_still_rejects_semantic_modify_on_phase3_passed_card():
    baseline = _baseline()
    changed_card = deepcopy(baseline["cards"][0])
    changed_card["interpretation"] = "Changed semantic interpretation."
    repaired_evidence = deepcopy(baseline["evidence"][0])
    repaired_evidence["fragments"][0]["quote"] = "source-verbatim replacement"
    ledger = _ledger(changed_card, repaired_evidence)

    errors = card_deltas.validate_ledger_against_baseline(
        ledger,
        baseline,
        stage="phase4",
        allowed_direct_ids=set(),
    )

    assert any("evidence-only source-fidelity repair" in error for error in errors)
    assert any("route this card through Phase 2R" in error for error in errors)


def test_phase4_evidence_only_modify_must_actually_change_evidence():
    baseline = _baseline()
    ledger = _ledger(
        deepcopy(baseline["cards"][0]),
        deepcopy(baseline["evidence"][0]),
    )

    errors = card_deltas.validate_ledger_against_baseline(
        ledger,
        baseline,
        stage="phase4",
        allowed_direct_ids=set(),
    )

    assert any("modify decision does not change card or evidence" in error for error in errors)
