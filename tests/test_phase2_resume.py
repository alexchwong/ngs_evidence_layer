import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "work" / "aaaaaaaa-0000-0000-0000-000000000001"
sys.path.insert(0, str(ROOT / "scripts"))

import ingest_artifacts
from scripts.phase_validation import phase2_state


def read(name):
    return json.loads((FIXTURE / name).read_text(encoding="utf-8"))


def semantic_reviews(census, *, defect_ids=()):
    defect_ids = set(defect_ids)
    return [
        {
            "claim_id": entry["claim_id"],
            "status": "defect" if entry["claim_id"] in defect_ids else "passed",
            "defect_summary": "Needs semantic repair." if entry["claim_id"] in defect_ids else None,
        }
        for entry in census["entries"]
    ]


def checkpoint(tmp_path):
    metadata = read("metadata.json")
    census = read("paper.census.json")
    provisional = read("paper.provisional-001.json")
    provisional["schema_version"] = "5.1"
    provisional["human_decisions"] = []

    prior_path = tmp_path / "paper.census.json"
    prior_path.write_text(json.dumps(census, indent=2), encoding="utf-8")
    source_path = tmp_path / "paper.md"
    source_path.write_text((FIXTURE / "paper.md").read_text(encoding="utf-8"), encoding="utf-8")
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    card_ids = [card["card_id"] for card in provisional["cards"]]
    dispositions = [
        {
            "claim_id": entry["claim_id"],
            "status": "covered",
            "card_ids": [card_ids[0]],
            "reason": None,
            "human_decision_id": None,
        }
        for entry in census["entries"]
    ]
    state = {
        "schema_version": "1.1",
        "checkpoint_stage": "authoring",
        "paper_id": metadata["paper_id"],
        "source_census": {
            "filename": prior_path.name,
            "sha256": hashlib.sha256(prior_path.read_bytes()).hexdigest(),
        },
        "census_semantic_review": {
            "claim_reviews": semantic_reviews(census),
            "unmapped_defects": [],
        },
        "candidate_package": provisional,
        "census_dispositions": dispositions,
        "allocated_card_ids": card_ids,
        "next_card_number": 9,
        "pending_human_requests": [
            {
                "request_id": "P001",
                "requested_action": "add",
                "human_instruction": "Add the missing paper-supported claim.",
                "human_reason": "Clinically useful for reporting.",
            }
        ],
        "review_state": {
            "census_semantic_baseline_complete": True,
            "approval_valid": False,
            "awaiting": "phase1_repair",
            "critique_filename": "paper.census-critique-v001.md",
        },
    }
    state_path = tmp_path / "paper.phase2-state-v001.json"
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return metadata, census, provisional, state, metadata_path, source_path, prior_path, state_path


def semantic_gate_checkpoint(tmp_path, *, defect_claim_index=0, unmapped_defects=None):
    metadata = read("metadata.json")
    census = read("paper.census.json")
    prior_path = tmp_path / "paper.census.json"
    prior_path.write_text(json.dumps(census, indent=2), encoding="utf-8")
    source_path = tmp_path / "paper.md"
    source_path.write_text((FIXTURE / "paper.md").read_text(encoding="utf-8"), encoding="utf-8")
    defect_id = census["entries"][defect_claim_index]["claim_id"]
    state = {
        "schema_version": "1.1",
        "checkpoint_stage": "census_semantic_gate",
        "paper_id": metadata["paper_id"],
        "source_census": {
            "filename": prior_path.name,
            "sha256": hashlib.sha256(prior_path.read_bytes()).hexdigest(),
        },
        "census_semantic_review": {
            "claim_reviews": semantic_reviews(census, defect_ids={defect_id}),
            "unmapped_defects": list(unmapped_defects or []),
        },
        "review_state": {
            "census_semantic_baseline_complete": True,
            "approval_valid": False,
            "awaiting": "phase1_repair",
            "critique_filename": "paper.census-critique-v001.md",
        },
    }
    state_path = tmp_path / "paper.phase2-state-v001.json"
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return metadata, census, state, source_path, prior_path, state_path, defect_id


def test_ingest_artifacts_phase2_state_naming_and_resolution(tmp_path):
    prior = tmp_path / "paper.census-v004.json"
    prior.write_text("{}", encoding="utf-8")
    assert ingest_artifacts.phase2_state_name(4) == "paper.phase2-state-v004.json"
    assert ingest_artifacts.phase2_state_attempt(tmp_path / "paper.phase2-state-v004.json") == 4
    state = tmp_path / "paper.phase2-state-v004.json"
    state.write_text("{}", encoding="utf-8")
    assert ingest_artifacts.resolve_phase2_state_for_census(tmp_path, prior) == state


def test_checkpoint_validates_before_phase1_roundtrip(tmp_path):
    metadata, census, _provisional, state, _metadata_path, source_path, prior_path, state_path = checkpoint(tmp_path)
    errors = phase2_state.state_errors(
        state,
        metadata,
        census,
        None,
        source_path.read_text(encoding="utf-8"),
        state_path,
        prior_path,
    )
    assert errors == []


def test_resume_diff_reviews_only_actual_entry_delta(tmp_path):
    metadata, census, _provisional, state, _metadata_path, source_path, prior_path, state_path = checkpoint(tmp_path)
    repaired = copy.deepcopy(census)
    new_entry = copy.deepcopy(repaired["entries"][0])
    new_entry["claim_id"] = "CLAIM-NEW"
    new_entry["summary"] = new_entry["summary"] + " Additional source-supported assertion."
    repaired["entries"].append(new_entry)

    errors = phase2_state.state_errors(
        state,
        metadata,
        census,
        repaired,
        source_path.read_text(encoding="utf-8"),
        state_path,
        prior_path,
    )
    assert errors == []
    delta = phase2_state.census_delta(census, repaired)
    assert delta["added_claim_ids"] == ["CLAIM-NEW"]
    assert delta["modified_claim_ids"] == []
    assert delta["removed_claim_ids"] == []
    assert set(delta["unchanged_claim_ids"]) == {entry["claim_id"] for entry in census["entries"]}


def test_resume_diff_detects_modified_and_removed_claims(tmp_path):
    metadata, census, _provisional, state, _metadata_path, source_path, prior_path, state_path = checkpoint(tmp_path)
    repaired = copy.deepcopy(census)
    modified_id = repaired["entries"][0]["claim_id"]
    removed_id = repaired["entries"][1]["claim_id"]
    repaired["entries"][0]["summary"] += " Repaired qualifier."
    repaired["entries"] = [entry for entry in repaired["entries"] if entry["claim_id"] != removed_id]

    errors = phase2_state.state_errors(
        state,
        metadata,
        census,
        repaired,
        source_path.read_text(encoding="utf-8"),
        state_path,
        prior_path,
    )
    assert errors == []
    delta = phase2_state.census_delta(census, repaired)
    assert delta["modified_claim_ids"] == [modified_id]
    assert delta["removed_claim_ids"] == [removed_id]


def test_scope_change_forces_full_phase2_instead_of_delta_resume(tmp_path):
    metadata, census, _provisional, state, _metadata_path, source_path, prior_path, state_path = checkpoint(tmp_path)
    repaired = copy.deepcopy(census)
    repaired["category_scope"] = ["diagnosis"]
    repaired["entries"].append({
        "claim_id": "CLAIM-NEW",
        "genes": ["NPM1"],
        "category": "diagnosis",
        "locator": "Results",
        "summary": "Additional source-supported assertion.",
    })
    errors = phase2_state.state_errors(
        state,
        metadata,
        census,
        repaired,
        source_path.read_text(encoding="utf-8"),
        state_path,
        prior_path,
    )
    assert any("delta-only Phase 2 resume is unsafe" in error for error in errors)


def test_semantic_gate_checkpoint_validates_without_card_state(tmp_path):
    metadata, census, state, source_path, prior_path, state_path, _defect_id = semantic_gate_checkpoint(tmp_path)
    errors = phase2_state.state_errors(
        state, metadata, census, None, source_path.read_text(encoding="utf-8"), state_path, prior_path
    )
    assert errors == []
    assert "candidate_package" not in state


def test_semantic_resume_rechecks_prior_defect_even_if_claim_unchanged(tmp_path):
    metadata, census, state, source_path, prior_path, state_path, defect_id = semantic_gate_checkpoint(tmp_path)
    repaired = copy.deepcopy(census)
    new_entry = copy.deepcopy(repaired["entries"][0])
    new_entry["claim_id"] = "CLAIM-NEW"
    new_entry["summary"] += " Added repair claim."
    repaired["entries"].append(new_entry)
    errors = phase2_state.state_errors(
        state, metadata, census, repaired, source_path.read_text(encoding="utf-8"), state_path, prior_path
    )
    assert errors == []
    assert phase2_state.semantic_recheck_claim_ids(state, census, repaired) == sorted([defect_id, "CLAIM-NEW"])


def test_semantic_resume_skips_unchanged_previously_passed_claims(tmp_path):
    metadata, census, state, source_path, prior_path, state_path, defect_id = semantic_gate_checkpoint(tmp_path)
    repaired = copy.deepcopy(census)
    for entry in repaired["entries"]:
        if entry["claim_id"] == defect_id:
            entry["summary"] += " Repaired semantic wording."
            break
    errors = phase2_state.state_errors(
        state, metadata, census, repaired, source_path.read_text(encoding="utf-8"), state_path, prior_path
    )
    assert errors == []
    assert phase2_state.semantic_recheck_claim_ids(state, census, repaired) == [defect_id]


def test_semantic_resume_preserves_targeted_unmapped_defects(tmp_path):
    metadata, census, state, source_path, prior_path, state_path, defect_id = semantic_gate_checkpoint(
        tmp_path, unmapped_defects=["Missing source-supported ELN classification assertion."]
    )
    # Even before an entry-level repair, the recorded unmapped defect remains targeted work.
    errors = phase2_state.state_errors(
        state, metadata, census, copy.deepcopy(census), source_path.read_text(encoding="utf-8"), state_path, prior_path
    )
    assert errors == []
    assert defect_id in phase2_state.semantic_recheck_claim_ids(state, census, census)
    assert state["census_semantic_review"]["unmapped_defects"] == [
        "Missing source-supported ELN classification assertion."
    ]


def test_phase2_prompt_requires_full_deterministic_but_delta_semantic_resume():
    prompt = (ROOT / "prompts" / "templates" / "phase2_prompt.md").read_text(encoding="utf-8")
    assert "full-census deterministic gate is mandatory" in prompt
    assert "do **not** repeat the complete census semantic audit" in prompt
    assert "`semantic_recheck_claim_ids`" in prompt
    assert "census_semantic_gate" in prompt
    assert "do **not** repeat the complete census semantic audit" in prompt
    assert "do not semantically re-review it" in prompt
    assert "Do not replace the supplied checkpoint with partially repaired state" in prompt
    assert "do not redraft the package from scratch" in prompt
    assert "pending_human_requests" in prompt
    assert "require a fresh `APPROVE`" in prompt
    assert "show **all current cards again**" in prompt
