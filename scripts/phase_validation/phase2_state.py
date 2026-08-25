#!/usr/bin/env python3
"""Validate Phase 2 semantic/authoring checkpoints and diff repaired census input."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

try:
    from . import phase2
except ImportError:  # direct execution from bundled validator
    import phase2

BUNDLE_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = BUNDLE_ROOT / "schema" / "phase2_state_schema.json"
CARD_SUFFIX_RE = re.compile(r"-C(?P<number>[0-9]{4,})$")
CENSUS_VERSION_RE = re.compile(r"^paper\.census-v(?P<attempt>[0-9]{3})\.json$")


def read_json(path, label="JSON"):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read {label} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid {label} in {path}: {exc}") from exc


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def schema_errors(state):
    schema = read_json(SCHEMA_PATH, "Phase 2 state schema")
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(state),
        key=lambda error: list(error.absolute_path),
    )
    return [
        "state schema: "
        + ("/".join(str(p) for p in error.absolute_path) or "<root>")
        + f": {error.message}"
        for error in errors
    ]


def census_attempt(path):
    name = Path(path).name
    if name == "paper.census.json":
        return 1
    match = CENSUS_VERSION_RE.fullmatch(name)
    return int(match.group("attempt")) if match else None


def expected_checkpoint_name(prior_census_path):
    attempt = census_attempt(prior_census_path)
    if attempt is None:
        return None
    return f"paper.phase2-state-v{attempt:03d}.json"


def census_entry_map(census):
    return {
        entry.get("claim_id"): entry
        for entry in census.get("entries", [])
        if isinstance(entry, dict) and isinstance(entry.get("claim_id"), str)
    }


def census_delta(prior_census, current_census):
    prior = census_entry_map(prior_census)
    current = census_entry_map(current_census)
    prior_ids = set(prior)
    current_ids = set(current)
    added = sorted(current_ids - prior_ids)
    removed = sorted(prior_ids - current_ids)
    modified = sorted(
        claim_id for claim_id in prior_ids & current_ids
        if prior[claim_id] != current[claim_id]
    )
    unchanged = sorted((prior_ids & current_ids) - set(modified))
    return {
        "added_claim_ids": added,
        "modified_claim_ids": modified,
        "removed_claim_ids": removed,
        "unchanged_claim_ids": unchanged,
    }


def semantic_review_map(state):
    return {
        item.get("claim_id"): item
        for item in state.get("census_semantic_review", {}).get("claim_reviews", [])
        if isinstance(item, dict) and isinstance(item.get("claim_id"), str)
    }


def semantic_recheck_claim_ids(state, prior_census, current_census):
    delta = census_delta(prior_census, current_census)
    current_ids = set(census_entry_map(current_census))
    reviews = semantic_review_map(state)
    prior_defective = {
        claim_id for claim_id, review in reviews.items()
        if review.get("status") == "defect"
    }
    return sorted(
        (set(delta["added_claim_ids"]) | set(delta["modified_claim_ids"]) | prior_defective)
        & current_ids
    )


def state_errors(state, metadata, prior_census, current_census, source_text, state_path, prior_census_path):
    errors = schema_errors(state)
    if errors:
        return errors

    paper_id = metadata.get("paper_id")
    if state.get("paper_id") != paper_id:
        errors.append("state paper_id does not match metadata")
    if prior_census.get("paper_id") != paper_id:
        errors.append("prior census paper_id does not match metadata")
    if current_census is not None and current_census.get("paper_id") != paper_id:
        errors.append("current census paper_id does not match metadata")

    expected_state = expected_checkpoint_name(prior_census_path)
    if expected_state is not None and Path(state_path).name != expected_state:
        errors.append(
            f"checkpoint filename must match its source census attempt: expected {expected_state}"
        )

    source_census = state["source_census"]
    if source_census.get("filename") != Path(prior_census_path).name:
        errors.append("state source_census.filename does not match --prior-census")
    if source_census.get("sha256") != sha256_file(prior_census_path):
        errors.append("state source_census.sha256 does not match --prior-census bytes")

    # The semantic checkpoint must prove that the complete source census was inspected.
    prior_claim_ids = set(census_entry_map(prior_census))
    reviews = state["census_semantic_review"]["claim_reviews"]
    review_ids = [item.get("claim_id") for item in reviews]
    if len(review_ids) != len(set(review_ids)):
        errors.append("census_semantic_review.claim_reviews contains duplicate claim_id values")
    if set(review_ids) != prior_claim_ids:
        missing = sorted(prior_claim_ids - set(review_ids))
        extra = sorted(set(review_ids) - prior_claim_ids)
        detail = []
        if missing:
            detail.append("missing " + ", ".join(missing))
        if extra:
            detail.append("unknown " + ", ".join(extra))
        errors.append(
            "census_semantic_review.claim_reviews must cover the source census exactly: "
            + "; ".join(detail)
        )

    # Scope/publication changes can alter the meaning or eligibility of every prior semantic result.
    if current_census is not None:
        for field in ("category_scope", "publication_type", "publication_type_basis"):
            if prior_census.get(field) != current_census.get(field):
                errors.append(
                    f"current census changed top-level {field}; delta-only Phase 2 resume is unsafe and a full Phase 2 semantic census audit is required"
                )

    stage = state["checkpoint_stage"]
    if stage == "census_semantic_gate":
        unexpected = sorted(
            key for key in (
                "candidate_package",
                "census_dispositions",
                "allocated_card_ids",
                "next_card_number",
                "pending_human_requests",
            ) if key in state
        )
        if unexpected:
            errors.append(
                "census_semantic_gate checkpoint must not contain card-authoring fields: "
                + ", ".join(unexpected)
            )
    else:
        # Authoring checkpoints are only safe after the source census semantic gate passed.
        defective = sorted(
            item.get("claim_id") for item in reviews if item.get("status") == "defect"
        )
        if defective:
            errors.append(
                "authoring checkpoint cannot contain semantically defective source-census claims: "
                + ", ".join(defective)
            )
        if state["census_semantic_review"].get("unmapped_defects"):
            errors.append("authoring checkpoint cannot contain unresolved unmapped census defects")

        candidate = state["candidate_package"]
        if candidate.get("schema_version") != "5.1":
            errors.append("candidate_package must use schema_version 5.1")
        if "human_decisions" not in candidate:
            errors.append("candidate_package must contain human_decisions (use [] when none are effective yet)")
        package_errors, _, _ = phase2.validate_package(
            candidate, metadata, prior_census, source_text=source_text, require_final=False
        )
        errors.extend(f"candidate_package: {error}" for error in package_errors)

        dispositions = state["census_dispositions"]
        disposition_ids = [item.get("claim_id") for item in dispositions]
        if len(disposition_ids) != len(set(disposition_ids)):
            errors.append("census_dispositions contains duplicate claim_id values")
        if set(disposition_ids) != prior_claim_ids:
            missing = sorted(prior_claim_ids - set(disposition_ids))
            extra = sorted(set(disposition_ids) - prior_claim_ids)
            detail = []
            if missing:
                detail.append("missing " + ", ".join(missing))
            if extra:
                detail.append("unknown " + ", ".join(extra))
            errors.append("census_dispositions must cover the source census exactly: " + "; ".join(detail))

        current_card_ids = {
            card.get("card_id") for card in candidate.get("cards", []) if isinstance(card, dict)
        }
        decisions = {
            item.get("decision_id"): item
            for item in candidate.get("human_decisions", [])
            if isinstance(item, dict)
        }
        for disposition in dispositions:
            claim_id = disposition.get("claim_id", "<unknown claim>")
            status = disposition.get("status")
            card_ids = set(disposition.get("card_ids", []))
            if status in {"carded", "covered"}:
                unknown_cards = sorted(card_ids - current_card_ids)
                if unknown_cards:
                    errors.append(
                        f"{claim_id}: {status} disposition references cards absent from candidate_package: "
                        + ", ".join(unknown_cards)
                    )
            elif status == "human_ruled":
                decision_id = disposition.get("human_decision_id")
                decision = decisions.get(decision_id)
                if decision is None:
                    errors.append(f"{claim_id}: human_ruled disposition references unknown decision {decision_id!r}")
                else:
                    if claim_id not in decision.get("claim_ids", []):
                        errors.append(
                            f"{claim_id}: human_ruled disposition decision {decision_id} does not reference this claim"
                        )
                    allowed_after = set(decision.get("after_card_ids", []))
                    if not card_ids <= allowed_after:
                        errors.append(
                            f"{claim_id}: human_ruled card_ids must be a subset of {decision_id}.after_card_ids"
                        )

        pending_ids = [item.get("request_id") for item in state.get("pending_human_requests", [])]
        if len(pending_ids) != len(set(pending_ids)):
            errors.append("pending_human_requests contains duplicate request_id values")

        allocated = set(state["allocated_card_ids"])
        required_allocated = set(current_card_ids)
        for decision in candidate.get("human_decisions", []):
            if isinstance(decision, dict):
                required_allocated.update(decision.get("before_card_ids", []))
                required_allocated.update(decision.get("after_card_ids", []))
        missing_allocated = sorted(required_allocated - allocated)
        if missing_allocated:
            errors.append(
                "allocated_card_ids must include all current and historically referenced Phase 2 card IDs: "
                + ", ".join(missing_allocated)
            )

        prefix = metadata.get("publication_key", "") + "-C"
        numbered = []
        for card_id in allocated:
            if card_id.startswith(prefix):
                match = CARD_SUFFIX_RE.search(card_id)
                if match:
                    numbered.append(int(match.group("number")))
        if numbered and state["next_card_number"] <= max(numbered):
            errors.append(
                f"next_card_number must be greater than every allocated card suffix; found {state['next_card_number']} with max C{max(numbered):04d}"
            )

    critique_name = state["review_state"]["critique_filename"]
    attempt = census_attempt(prior_census_path)
    if attempt is not None:
        expected_critique = f"paper.census-critique-v{attempt:03d}.md"
        if critique_name != expected_critique:
            errors.append(
                f"review_state.critique_filename must match source census attempt: expected {expected_critique}"
            )

    if current_census is not None:
        delta = census_delta(prior_census, current_census)
        semantic_recheck = semantic_recheck_claim_ids(state, prior_census, current_census)
        unmapped = state["census_semantic_review"].get("unmapped_defects", [])
        if not any(delta[key] for key in ("added_claim_ids", "modified_claim_ids", "removed_claim_ids")) and not semantic_recheck and not unmapped:
            errors.append("repaired census has no entry-level or recorded semantic delta from the checkpoint source census")
    return errors


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--prior-census", type=Path, required=True)
    parser.add_argument("--current-census", type=Path)
    parser.add_argument("--state", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        metadata = read_json(args.metadata, "metadata")
        prior_census = read_json(args.prior_census, "prior census")
        current_census = read_json(args.current_census, "current census") if args.current_census else None
        state = read_json(args.state, "Phase 2 checkpoint")
        source_text = args.source.read_text(encoding="utf-8")
        errors = state_errors(
            state,
            metadata,
            prior_census,
            current_census,
            source_text,
            args.state,
            args.prior_census,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        sys.exit(f"PHASE 2 STATE VALIDATION FAILED:\n{exc}")
    if errors:
        sys.exit("PHASE 2 STATE VALIDATION FAILED:\n" + "\n".join(errors))
    report = {
        "valid": True,
        "phase": 2,
        "checkpoint": True,
        "checkpoint_stage": state["checkpoint_stage"],
    }
    if current_census is not None:
        report["resume_delta"] = census_delta(prior_census, current_census)
        report["semantic_recheck_claim_ids"] = semantic_recheck_claim_ids(
            state, prior_census, current_census
        )
        report["unmapped_defects_to_recheck"] = state["census_semantic_review"].get(
            "unmapped_defects", []
        )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
