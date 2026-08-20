import copy
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "work" / "aaaaaaaa-0000-0000-0000-000000000001"
sys.path.insert(0, str(ROOT / "scripts"))


from scripts.phase_validation import phase2, phase4
import scripts.package_validation as package_validation


def read(name):
    return json.loads((FIXTURE / name).read_text(encoding="utf-8"))


def delete_decision(provisional, claim_id="CLAIM-001"):
    return {
        "decision_id": "H001",
        "action": "delete",
        "before_card_ids": [provisional["cards"][0]["card_id"]],
        "after_card_ids": [],
        "claim_ids": [claim_id],
        "human_instruction": "Delete this card.",
        "human_reason": "Not useful for NGS reporting.",
    }


def modify_decision(provisional, claim_id="CLAIM-001"):
    card_id = provisional["cards"][0]["card_id"]
    return {
        "decision_id": "H001",
        "action": "modify",
        "before_card_ids": [card_id],
        "after_card_ids": [card_id],
        "claim_ids": [claim_id],
        "human_instruction": "Keep the shorter interpretation.",
        "human_reason": None,
    }


def test_schema_accepts_human_decision_provenance():
    provisional = read("paper.provisional-001.json")
    provisional["human_decisions"] = [modify_decision(provisional)]
    errors = package_validation.schema_errors(
        provisional, "ingestion_package_schema.json", "package"
    )
    assert errors == []


def test_human_decision_claim_ids_must_exist():
    provisional = read("paper.provisional-001.json")
    census = read("paper.census.json")
    provisional["human_decisions"] = [delete_decision(provisional, "NO-SUCH-CLAIM")]
    errors = phase2.human_decision_errors(provisional, census)
    assert any("unknown census claim_ids" in error for error in errors)


def test_human_decision_after_cards_must_exist_in_approved_package():
    provisional = read("paper.provisional-001.json")
    census = read("paper.census.json")
    decision = modify_decision(provisional)
    decision["after_card_ids"] = ["missing-card"]
    provisional["human_decisions"] = [decision]
    errors = phase2.normal_human_decision_state_errors(provisional)
    assert any("after_card_ids must exist" in error for error in errors)


def test_historical_human_decisions_can_reference_cards_changed_later_by_phase2r():
    provisional = read("paper.provisional-001.json")
    census = read("paper.census.json")
    decision = modify_decision(provisional)
    provisional["human_decisions"] = [decision]
    provisional["cards"] = provisional["cards"][1:]
    # Generic package provenance validation keeps the old ruling readable; only a normal
    # Phase 2 emission requires every after_card_id to exist in the current card set.
    errors = phase2.human_decision_errors(provisional, census)
    assert errors == []


def test_phase4_entry_allows_phase3_failure_of_human_modified_surviving_card():
    provisional = read("paper.provisional-001.json")
    review = read("paper.review-001.json")
    reviewed_id = provisional["cards"][0]["card_id"]
    provisional["human_decisions"] = [modify_decision(provisional)]
    result = next(item for item in review["card_results"] if item["card_id"] == reviewed_id)
    result["verdict"] = "fail"
    result["details"] = {
        "failure_type": "other",
        "reason": "The surviving human-edited card still has a substantive defect.",
        "defensibility": "not_defensible",
        "suggested_action": {"category": "rewrite_interpretation", "detail": "Rewrite it."},
    }
    review["audit"]["cards_passed"] -= 1
    review["audit"]["cards_failed"] += 1
    errors = phase4.validate_review(review, provisional)
    assert errors == []


def test_phase4_requires_human_decisions_to_survive_unchanged():
    provisional = read("paper.provisional-001.json")
    provisional["human_decisions"] = [modify_decision(provisional)]
    final = copy.deepcopy(provisional)
    assert phase4.validate_final_against_provisional(final, provisional) == []
    final["human_decisions"] = []
    errors = phase4.validate_final_against_provisional(final, provisional)
    assert any("preserve Phase 2 human_decisions" in error for error in errors)


def test_normal_phase2_schema51_requires_human_decisions_field(tmp_path):
    provisional = read("paper.provisional-001.json")
    provisional["schema_version"] = "5.1"
    path = tmp_path / "paper.provisional-v001.json"
    path.write_text(json.dumps(provisional), encoding="utf-8")
    errors, _warnings, _report = phase2.validate_phase_files(
        metadata_path=FIXTURE / "metadata.json",
        census_path=FIXTURE / "paper.census.json",
        source_path=FIXTURE / "paper.md",
        provisional_path=path,
    )
    assert any("must contain human_decisions" in error for error in errors)

    provisional["human_decisions"] = []
    path.write_text(json.dumps(provisional), encoding="utf-8")
    errors, _warnings, _report = phase2.validate_phase_files(
        metadata_path=FIXTURE / "metadata.json",
        census_path=FIXTURE / "paper.census.json",
        source_path=FIXTURE / "paper.md",
        provisional_path=path,
    )
    assert not any("must contain human_decisions" in error for error in errors)


def test_phase_prompts_define_human_authority_boundary():
    phase2_prompt = (ROOT / "prompts" / "templates" / "phase2_prompt.md").read_text(encoding="utf-8")
    phase3_prompt = (ROOT / "prompts" / "templates" / "phase3_prompt.md").read_text(encoding="utf-8")
    phase4_prompt = (ROOT / "prompts" / "templates" / "phase4_prompt.md").read_text(encoding="utf-8")
    assert "human_reason" in phase2_prompt
    assert "Never invent a human reason" in phase2_prompt
    assert "human_ruled" in phase2_prompt
    assert "human `delete` is authoritative for card existence" in phase2_prompt
    assert "current `category`" in phase2_prompt
    assert "not as an automatic pass instruction" in phase3_prompt
    assert "review **every card present in the provisional**" in phase3_prompt
    assert "does not perform a whole-census coverage audit" in phase3_prompt
    assert "does not receive or audit the census" in phase3_prompt
    assert "was eligible for ordinary Phase 3 review" in phase4_prompt
    assert "Preserve `human_decisions` **byte-for-structure unchanged**" in phase4_prompt

