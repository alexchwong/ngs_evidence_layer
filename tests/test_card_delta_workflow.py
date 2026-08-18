import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHASE_VALIDATION = ROOT / "scripts" / "phase_validation"
SCRIPTS = ROOT / "scripts"
for folder in (SCRIPTS, PHASE_VALIDATION):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import card_deltas  # noqa: E402
import confirm  # noqa: E402


PAPER_ID = "11111111-1111-1111-1111-111111111111"


def card(card_id, interpretation):
    return {
        "card_id": card_id,
        "interpretation": interpretation,
    }


def evidence(card_id, text):
    return {
        "card_id": card_id,
        "text": text,
    }


def baseline_package():
    return {
        "paper_id": PAPER_ID,
        "round": 3,
        "cards": [card("paper-C0001", "one"), card("paper-C0002", "two")],
        "evidence": [evidence("paper-C0001", "e1"), evidence("paper-C0002", "e2")],
    }


def phase2r_modify_ledger():
    return {
        "schema_version": "1.0",
        "stage": "phase2r",
        "purpose": "revise",
        "paper_id": PAPER_ID,
        "baseline_filename": "paper.final.json",
        "baseline_round": 3,
        "output_filename": "paper.provisional-rev001-v001.json",
        "user_finalized": True,
        "card_decisions": [
            {
                "decision": "modify",
                "card_id": "paper-C0001",
                "user_instruction": "Clarify the conclusion.",
                "card": card("paper-C0001", "one revised"),
                "evidence": evidence("paper-C0001", "e1 revised"),
            }
        ],
    }


class CardDeltaWorkflowTests(unittest.TestCase):
    def test_phase2r_exact_authorized_delta_passes(self):
        baseline = baseline_package()
        ledger = phase2r_modify_ledger()
        output = card_deltas.apply_card_decisions(baseline, ledger)
        self.assertEqual(
            card_deltas.validate_package_delta(baseline, output, ledger, stage="phase2r"),
            [],
        )

    def test_phase2r_rejects_unapproved_change_to_other_card(self):
        baseline = baseline_package()
        ledger = phase2r_modify_ledger()
        output = card_deltas.apply_card_decisions(baseline, ledger)
        output["cards"][1]["interpretation"] = "unauthorized rewrite"
        errors = card_deltas.validate_package_delta(
            baseline, output, ledger, stage="phase2r"
        )
        self.assertTrue(
            any("does not exactly match the user-authorized decision ledger" in error for error in errors),
            errors,
        )

    def test_phase2r_rejects_retain_as_a_delta(self):
        baseline = baseline_package()
        ledger = phase2r_modify_ledger()
        ledger["card_decisions"] = [
            {
                "decision": "retain",
                "card_id": "paper-C0001",
                "user_instruction": "Leave it unchanged.",
            }
        ]
        errors = card_deltas.validate_ledger_against_baseline(
            ledger, baseline, stage="phase2r"
        )
        self.assertTrue(any("Phase 2R records only add, modify, or delete" in error for error in errors), errors)

    def test_confirm_rechecks_phase2r_decision_diff(self):
        baseline = baseline_package()
        ledger = phase2r_modify_ledger()
        with tempfile.TemporaryDirectory() as tmp:
            working = Path(tmp)
            provisional_path = working / "paper.provisional-rev001-v001.json"
            ledger_path = working / "paper.phase2r-decisions-rev001-v001.json"
            output = card_deltas.apply_card_decisions(baseline, ledger)
            output["cards"][1]["interpretation"] = "unauthorized rewrite"
            provisional_path.write_text(json.dumps(output), encoding="utf-8")
            ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
            errors = confirm._validate_phase2r_delta_history(
                working=working,
                provisional_path=provisional_path,
                current_accepted_final=baseline,
            )
        self.assertTrue(
            any("user-authorized decision ledger" in error for error in errors),
            errors,
        )


    def test_phase2r_rejects_non_revise_purpose(self):
        baseline = baseline_package()
        ledger = phase2r_modify_ledger()
        ledger["purpose"] = "finalize"
        errors = card_deltas.validate_ledger_against_baseline(
            ledger, baseline, stage="phase2r"
        )
        self.assertTrue(any("purpose must be revise" in error for error in errors), errors)

    def test_confirm_requires_phase2r_ledger_when_lineage_requires_it(self):
        baseline = baseline_package()
        with tempfile.TemporaryDirectory() as tmp:
            working = Path(tmp)
            provisional_path = working / "paper.provisional-rev001-v001.json"
            provisional_path.write_text(json.dumps(baseline), encoding="utf-8")
            errors = confirm._validate_phase2r_delta_history(
                working=working,
                provisional_path=provisional_path,
                current_accepted_final=baseline,
                require_ledger=True,
            )
        self.assertTrue(any("no matching user decision ledger" in error for error in errors), errors)

    def test_phase4_cannot_directly_modify_phase3_passed_card(self):
        baseline = baseline_package()
        ledger = {
            "schema_version": "1.0",
            "stage": "phase4",
            "purpose": "finalize",
            "paper_id": PAPER_ID,
            "baseline_filename": "paper.provisional-v003.json",
            "baseline_round": 3,
            "review_filename": "paper.review-v003.json",
            "output_filename": "paper.final.json",
            "user_finalized": True,
            "card_decisions": [
                {
                    "decision": "modify",
                    "card_id": "paper-C0002",
                    "user_instruction": "Change a card that passed Phase 3.",
                    "card": card("paper-C0002", "two revised"),
                    "evidence": evidence("paper-C0002", "e2 revised"),
                }
            ],
        }
        errors = card_deltas.validate_ledger_against_baseline(
            ledger, baseline, stage="phase4", allowed_direct_ids={"paper-C0001"}
        )
        self.assertTrue(any("route this card through Phase 2R" in error for error in errors), errors)

    def test_phase4_unrelated_add_must_route_through_phase2r(self):
        baseline = baseline_package()
        ledger = {
            "schema_version": "1.0",
            "stage": "phase4",
            "purpose": "finalize",
            "paper_id": PAPER_ID,
            "baseline_filename": "paper.provisional-v003.json",
            "baseline_round": 3,
            "review_filename": "paper.review-v003.json",
            "output_filename": "paper.final.json",
            "user_finalized": True,
            "card_decisions": [
                {
                    "decision": "add",
                    "card_id": "paper-C0003",
                    "user_instruction": "Add a new unrelated card.",
                    "card": card("paper-C0003", "three"),
                    "evidence": evidence("paper-C0003", "e3"),
                }
            ],
        }
        errors = card_deltas.validate_ledger_against_baseline(
            ledger, baseline, stage="phase4", allowed_direct_ids={"paper-C0001"}
        )
        self.assertTrue(any("related_card_id" in error and "Phase 2R" in error for error in errors), errors)

    def test_phase4_handoff_can_request_passed_card_without_changing_it(self):
        baseline = baseline_package()
        ledger = {
            "schema_version": "1.0",
            "stage": "phase4",
            "purpose": "phase2r_handoff",
            "paper_id": PAPER_ID,
            "baseline_filename": "paper.provisional-v003.json",
            "baseline_round": 3,
            "review_filename": "paper.review-v003.json",
            "user_finalized": True,
            "card_decisions": [],
            "phase2r_requests": [
                {
                    "action": "modify",
                    "card_id": "paper-C0002",
                    "user_instruction": "Reconsider this passed card in Phase 2R.",
                }
            ],
        }
        self.assertEqual(
            card_deltas.validate_ledger_against_baseline(
                ledger, baseline, stage="phase4", allowed_direct_ids={"paper-C0001"}
            ),
            [],
        )
        self.assertEqual(card_deltas.apply_card_decisions(baseline, ledger), baseline)


if __name__ == "__main__":
    unittest.main()
