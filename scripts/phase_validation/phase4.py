#!/usr/bin/env python3
"""Deterministic Phase 4 validation using bundled canonical JSON assets."""
import argparse
import json
import re
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

try:
    from . import card_deltas
except ImportError:  # direct execution from bundled validator
    import card_deltas

BUNDLE_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = BUNDLE_ROOT / "schema"


def load_json_asset(filename):
    path = SCHEMA_DIR / filename
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeError(f"cannot read bundled schema asset {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid bundled JSON asset {path}: {exc}") from exc


REVIEW_SCHEMA = load_json_asset("review_schema.json")
DISEASE_VOCABULARY = load_json_asset("disease_vocabulary.json")
TERMS = list(DISEASE_VOCABULARY["terms"])
DISEASES = [term["name"] for term in TERMS]
UMBRELLA = {
    term["name"]: list(term.get("parents", []))
    for term in TERMS
    if term.get("parents")
}
DISEASE_TEXT_FORMS = {
    term["name"]: [term["name"], *term.get("aliases", [])]
    for term in TERMS
}


def bind_disease_vocabulary(schema):
    disease_schema = schema.get("$defs", {}).get("disease")
    if not isinstance(disease_schema, dict):
        raise RuntimeError("bundled ingestion package schema $defs.disease must be an object")
    if "enum" in disease_schema:
        raise RuntimeError(
            "bundled ingestion package schema must not contain a duplicate disease enum"
        )
    disease_schema["enum"] = list(DISEASES)
    return schema


PACKAGE_SCHEMA = bind_disease_vocabulary(
    load_json_asset("ingestion_package_schema.json")
)

DISEASE_DEPENDENT_CATEGORIES = {"diagnosis", "prognosis", "treatment", "biomarker"}
GENERIC_INTERPRETATION_PATTERNS = (
    "application remains dependent on the source-stated disease context",
    "does not provide a complete patient-level risk score in this passage",
    "the implication is alteration- and disease-specific and should not be generalized",
    "does not by itself establish germline origin, clonal chronology, or suitability as a stand-alone mrd marker",
)
REFERENCE_ENTRY_RE = re.compile(r"^\s*[-*]?\s*\d{1,4}\.\s+.+\b(?:19|20)\d{2}\s*;", re.IGNORECASE)



def read_json(path, label="JSON"):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read {label} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid {label} in {path}: {exc}") from exc


def disease_ancestors(diseases):
    requested = set(diseases)
    ancestors = set()
    def visit(disease, path):
        if disease in path:
            cycle = " -> ".join((*path, disease))
            raise ValueError(f"disease umbrella cycle: {cycle}")
        next_path = (*path, disease)
        for parent in UMBRELLA.get(disease, []):
            ancestors.add(parent)
            visit(parent, next_path)
    for disease in requested:
        visit(disease, ())
    ancestors -= requested
    return [disease for disease in DISEASES if disease in ancestors]


def normalise(text, markdown=False):
    text = str(text).replace("\r\n", "\n").replace("\r", "\n")
    if markdown:
        lines = []
        for line in text.splitlines():
            if re.match(r"^\s*\|?(?:\s*:?-+:?\s*\|)+\s*$", line):
                continue
            lines.append(line.replace("|", " "))
        text = "\n".join(lines)
    return re.sub(r"\s+", " ", text).strip()


def _contains_explicit_term(text, term):
    """Case-insensitive whole-term match with flexible internal whitespace."""
    pattern = re.escape(str(term).casefold()).replace(r"\ ", r"\s+")
    return re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", str(text).casefold()) is not None


def interpretation_surfacing_errors(package, card_ids=None):
    """Require schema-5.1 cards in scope to surface tagged genes and diseases."""
    if package.get("schema_version") != "5.1":
        return []
    selected = None if card_ids is None else set(card_ids)
    errors = []
    for card in package.get("cards", []):
        card_id = card.get("card_id", "<unknown card>")
        if selected is not None and card_id not in selected:
            continue
        interpretation = card.get("interpretation", "")
        missing_genes = [
            gene for gene in card.get("genes", [])
            if not _contains_explicit_term(interpretation, gene)
        ]
        missing_diseases = []
        for disease in card.get("diseases", []):
            forms = DISEASE_TEXT_FORMS.get(disease, [disease])
            if not any(_contains_explicit_term(interpretation, form) for form in forms):
                missing_diseases.append(disease)
        if missing_genes:
            errors.append(
                f"{card_id}: interpretation must explicitly name every tagged gene; "
                f"missing: {', '.join(missing_genes)}"
            )
        if missing_diseases:
            errors.append(
                f"{card_id}: interpretation must explicitly identify every tagged disease "
                f"by canonical name or accepted source alias; missing: {', '.join(missing_diseases)}"
            )
    return errors


def schema_errors(document, schema, label):
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(document),
        key=lambda error: list(error.absolute_path),
    )
    return [
        f"{label} schema: {'/'.join(str(p) for p in error.absolute_path) or '<root>'}: "
        f"{error.message}" for error in errors
    ]


def load_delta_carry_context(phase2r_decisions_path):
    if phase2r_decisions_path is None:
        return None, None, None
    path = Path(phase2r_decisions_path)
    ledger = read_json(path, "Phase 2R decision ledger")
    phase4_name = ledger.get("phase4_decisions_filename")
    if not phase4_name:
        return ledger, None, None
    phase4_path = path.parent / phase4_name
    if not phase4_path.is_file():
        raise ValueError(f"Phase 2R references missing Phase 4 decision ledger: {phase4_name}")
    phase4_ledger = read_json(phase4_path, "Phase 4 handoff decision ledger")
    review_name = phase4_ledger.get("review_filename")
    prior_review_path = path.parent / str(review_name)
    if not prior_review_path.is_file():
        raise ValueError(f"Phase 4 handoff references missing prior review: {review_name}")
    prior_review = read_json(prior_review_path, "prior Phase 3 review")
    return ledger, phase4_ledger, prior_review


def validate_review(review, provisional, phase2r_ledger=None, phase4_ledger=None, prior_review=None):
    """Validate a Phase 3 review against its Phase 2 package.

    In Phase 2R delta mode, unchanged cards are carried forward rather than
    substantively re-audited under the current interpretation standard.
    """
    errors = schema_errors(review, REVIEW_SCHEMA, "review")
    if errors:
        return errors

    if provisional.get("schema_version") == "5.1" and review.get("schema_version") != "5.1":
        errors.append("a 5.1 provisional requires a 5.1 Phase 3 review")
    if review["paper_id"] != provisional.get("paper_id"):
        errors.append("review paper_id does not match provisional package")
    if review["round"] != provisional.get("round"):
        errors.append("review round does not match provisional package")
    if review["extraction_model_reviewed"] != provisional.get("extraction_model"):
        errors.append("review extraction_model_reviewed does not match provisional extraction_model")
    if review["reviewer_model"] == provisional.get("extraction_model"):
        errors.append("reviewer model must differ from provisional extraction model")

    card_results = review["card_results"]
    result_ids = [result["card_id"] for result in card_results]
    provisional_ids = [card.get("card_id") for card in provisional.get("cards", [])]
    passed = [result for result in card_results if result["verdict"] == "pass"]
    failed = [result for result in card_results if result["verdict"] == "fail"]
    if review["audit"]["cards_total"] != len(provisional.get("cards", [])):
        errors.append("review cards_total does not match provisional cards")
    if review["audit"]["cards_passed"] != len(passed):
        errors.append("review cards_passed does not match card_results")
    if review["audit"]["cards_failed"] != len(failed):
        errors.append("review cards_failed does not match card_results")
    if len(result_ids) != len(set(result_ids)):
        errors.append("review contains duplicate card IDs")
    unknown_ids = sorted(set(result_ids) - set(provisional_ids))
    if unknown_ids:
        errors.append("review references unknown provisional cards: " + ", ".join(unknown_ids))
    missing_ids = sorted(set(provisional_ids) - set(result_ids))
    if missing_ids:
        errors.append("review omits provisional cards: " + ", ".join(missing_ids))
    if result_ids != provisional_ids:
        errors.append("review card_results must preserve provisional card order")

    if phase2r_ledger is None:
        if review.get("review_scope") not in {None, "full"}:
            errors.append("review_scope delta requires the matching Phase 2R decision ledger")
        if provisional.get("schema_version") == "5.1" and review.get("review_scope") != "full":
            errors.append("a 5.1 full review must set review_scope to full")
        for result in card_results:
            basis = result.get("review_basis")
            if provisional.get("schema_version") == "5.1" and basis != "phase3":
                errors.append(f"{result['card_id']}: a 5.1 full review must use review_basis phase3")
            elif provisional.get("schema_version") != "5.1" and basis not in {None, "phase3"}:
                errors.append(f"{result['card_id']}: full review cannot use carried_forward review_basis")
    else:
        errors.extend(
            f"Phase 2R decisions: {error}"
            for error in card_deltas.schema_errors(phase2r_ledger)
        )
        changed = set(card_deltas.changed_card_ids(phase2r_ledger))
        if review.get("review_scope") != "delta":
            errors.append("Phase 2R review must set review_scope to delta")
        prior_by_id = {item.get("card_id"): item for item in (prior_review or {}).get("card_results", [])}
        phase4_direct = {item.get("card_id"): item.get("decision") for item in (phase4_ledger or {}).get("card_decisions", [])}
        for result in card_results:
            card_id = result["card_id"]
            if card_id in changed:
                if result.get("review_basis") != "phase3":
                    errors.append(f"{card_id}: added/modified Phase 2R card must use review_basis phase3")
                continue
            if result.get("review_basis") != "carried_forward":
                errors.append(f"{card_id}: unchanged Phase 2R card must use review_basis carried_forward")
            if phase4_ledger is None:
                expected_verdict = "pass"
                expected_details = None
            elif card_id in phase4_direct:
                expected_verdict = "pass"
                expected_details = None
            else:
                prior = prior_by_id.get(card_id)
                if prior is None:
                    errors.append(f"{card_id}: cannot determine carried-forward verdict from the prior Phase 3 review")
                    continue
                expected_verdict = prior.get("verdict")
                expected_details = prior.get("details")
            if result.get("verdict") != expected_verdict:
                errors.append(f"{card_id}: carried-forward verdict must remain {expected_verdict}")
            if expected_verdict == "fail" and result.get("details") != expected_details:
                errors.append(f"{card_id}: carried-forward failure details must exactly match the prior Phase 3 review")
            if expected_verdict == "pass" and "details" in result:
                errors.append(f"{card_id}: carried-forward pass must not contain failure details")

    publication_verdict = review["audit"]["publication_type_verdict"]
    if publication_verdict["package_value"] != provisional.get("publication_type"):
        errors.append("review publication package_value does not match provisional publication_type")
    if publication_verdict["verdict"] == "pass" and publication_verdict["auditor_value"] != publication_verdict["package_value"]:
        errors.append("passing publication verdict must retain the package value")
    return errors


def human_decision_errors(package, census):
    """Validate Phase 2 human-decision provenance against the current package/census."""
    decisions = package.get("human_decisions")
    if decisions is None:
        return []
    errors = []
    known_claim_ids = {
        entry.get("claim_id") for entry in census.get("entries", [])
        if isinstance(entry, dict)
    }
    seen_decision_ids = set()
    seen_after_card_ids = set()
    for index, decision in enumerate(decisions, start=1):
        decision_id = decision.get("decision_id")
        label = decision_id or f"human_decisions[{index - 1}]"
        if decision_id in seen_decision_ids:
            errors.append(f"{label}: duplicate human decision_id")
        seen_decision_ids.add(decision_id)

        unknown_claims = sorted(set(decision.get("claim_ids", [])) - known_claim_ids)
        if unknown_claims:
            errors.append(
                f"{label}: human decision references unknown census claim_ids: "
                + ", ".join(unknown_claims)
            )

        after_ids = decision.get("after_card_ids", [])
        overlapping = sorted(set(after_ids) & seen_after_card_ids)
        if overlapping:
            errors.append(
                f"{label}: an approved card may be governed by only one effective human decision: "
                + ", ".join(overlapping)
            )
        seen_after_card_ids.update(after_ids)

        action = decision.get("action")
        before_ids = decision.get("before_card_ids", [])
        if action in {"retain", "modify"} and set(before_ids) != set(after_ids):
            errors.append(
                f"{label}: {action} must preserve the same card IDs before and after; "
                "use split/merge/add/delete when card identity changes"
            )
    return errors


def validate_package(package, metadata, census, source_text=None, require_final=False):
    errors = schema_errors(package, PACKAGE_SCHEMA, "package")
    warnings = []
    if errors:
        return errors, warnings, None

    errors.extend(human_decision_errors(package, census))

    if package["paper_id"] != metadata["paper_id"]:
        errors.append("package paper_id does not match metadata")
    if package["census_entries"] != len(census.get("entries", [])):
        errors.append("package census_entries does not match census")
    nickname = package.get("paper_nickname")
    if require_final:
        if not isinstance(nickname, str) or not nickname.strip():
            errors.append("final package requires paper_nickname")
        elif nickname != nickname.strip() or any(char in nickname for char in "\r\n\t"):
            errors.append("paper_nickname must be a trimmed single-line string")
    elif "paper_nickname" in package:
        errors.append("provisional package must not contain paper_nickname")
    if not require_final and package["publication_type_verified_by_phase3"]:
        errors.append("provisional publication type cannot already be verified by Phase 3")
    if package["round"] == 1 and not require_final:
        if package["publication_type"] != census.get("publication_type"):
            errors.append("first-round package publication_type does not match census")
        if package["publication_type_basis"] != census.get("publication_type_basis"):
            errors.append("first-round package publication_type_basis does not match census")

    card_ids = [card["card_id"] for card in package["cards"]]
    evidence_ids = [evidence["card_id"] for evidence in package["evidence"]]
    if len(card_ids) != len(set(card_ids)):
        errors.append("package contains duplicate card_id values")
    if len(evidence_ids) != len(set(evidence_ids)):
        errors.append("package contains more than one evidence bundle for the same card")
    missing_evidence = sorted(set(card_ids) - set(evidence_ids))
    unknown_evidence = sorted(set(evidence_ids) - set(card_ids))
    if missing_evidence:
        errors.append("cards with no evidence bundle: " + ", ".join(missing_evidence))
    if unknown_evidence:
        errors.append("evidence bundles for unknown cards: " + ", ".join(unknown_evidence))

    prefix = metadata["publication_key"] + "-"
    for card in package["cards"]:
        card_id = card["card_id"]
        if not card_id.startswith(prefix):
            errors.append(f"{card_id}: card_id must begin with {prefix}")
        if card["category"] in DISEASE_DEPENDENT_CATEGORIES and not card["diseases"]:
            errors.append(f"{card_id}: {card['category']} card requires at least one disease")
        interpretation = normalise(card["interpretation"]).lower()
        if any(pattern in interpretation for pattern in GENERIC_INTERPRETATION_PATTERNS):
            warnings.append(f"{card_id}: interpretation contains generic category boilerplate; review direct evidence support")
        if "disease_ancestors" in card:
            expected_ancestors = disease_ancestors(card["diseases"])
            if set(card["disease_ancestors"]) != set(expected_ancestors):
                errors.append(
                    f"{card_id}: disease_ancestors must contain exactly the transitive "
                    f"ancestors {expected_ancestors}"
                )
            overlap = sorted(set(card["diseases"]) & set(card["disease_ancestors"]))
            if overlap:
                errors.append(
                    f"{card_id}: exact diseases and disease_ancestors overlap: "
                    + ", ".join(overlap)
                )

    source = normalise(source_text, markdown=True) if source_text is not None else None
    for evidence in package["evidence"]:
        card_id = evidence["card_id"]
        fragments = evidence["fragments"]
        fragment_ids = [fragment["fragment_id"] for fragment in fragments]
        fragment_id_set = set(fragment_ids)
        if len(fragment_ids) != len(fragment_id_set):
            errors.append(f"{card_id}: evidence bundle contains duplicate fragment_id values")
        if sum(len(fragment["quote"].split()) for fragment in fragments) > 400:
            errors.append(f"{card_id}: evidence bundle exceeds 400 words")

        roles = {fragment["role"] for fragment in fragments}
        if evidence["evidence_type"] in {"contiguous_text", "composite_text"} and "claim" not in roles:
            errors.append(f"{card_id}: text evidence requires a claim fragment")
        if evidence["evidence_type"] == "contiguous_text" and fragments[0]["role"] != "claim":
            errors.append(f"{card_id}: contiguous text fragment must have role claim")
        if evidence["evidence_type"] == "table_relation" and "cell" not in roles:
            errors.append(f"{card_id}: table evidence requires at least one cell fragment")

        referenced_ids = {
            fragment_id
            for mapped_ids in evidence["support_map"].values()
            for fragment_id in mapped_ids
        }
        dangling_support = sorted(referenced_ids - fragment_id_set)
        if dangling_support:
            errors.append(f"{card_id}: support_map references unknown fragments: " + ", ".join(dangling_support))

        if evidence["evidence_type"] == "table_relation":
            fragments_by_id = {fragment["fragment_id"]: fragment for fragment in fragments}
            relation_references = set()
            for relation in evidence["table_relations"]:
                relation_references.add(relation["value_fragment_id"])
                relation_references.update(relation["header_fragment_ids"])
                relation_references.update(relation["qualifier_fragment_ids"])
                value = fragments_by_id.get(relation["value_fragment_id"])
                if value and value["role"] != "cell":
                    errors.append(f"{card_id}: table value {value['fragment_id']} must have role cell")
                for header_id in relation["header_fragment_ids"]:
                    header = fragments_by_id.get(header_id)
                    if header and header["role"] not in {"column_header", "row_header"}:
                        errors.append(f"{card_id}: table header {header_id} has invalid role {header['role']}")
                for qualifier_id in relation["qualifier_fragment_ids"]:
                    qualifier = fragments_by_id.get(qualifier_id)
                    if qualifier and qualifier["role"] not in {"legend", "footnote"}:
                        errors.append(f"{card_id}: table qualifier {qualifier_id} has invalid role {qualifier['role']}")
            dangling_relations = sorted(relation_references - fragment_id_set)
            if dangling_relations:
                errors.append(f"{card_id}: table relations reference unknown fragments: " + ", ".join(dangling_relations))

        for fragment in fragments:
            fragment_label = f"{card_id}/{fragment['fragment_id']}"
            quote_text = fragment["quote"]
            if REFERENCE_ENTRY_RE.search(quote_text):
                errors.append(f"{fragment_label}: fragment appears to be a bibliographic reference-list entry")
            normalized = normalise(quote_text, markdown=True)
            if source is not None and normalized not in source:
                errors.append(f"{fragment_label}: fragment not found verbatim in paper.md")

    covered_genes = sorted({gene for card in package["cards"] for gene in card["genes"]})
    covered_diseases = sorted({disease for card in package["cards"] for disease in card["diseases"]})
    if sorted(package["genes_covered"]) != covered_genes:
        errors.append("genes_covered does not equal genes represented by cards")
    if sorted(package["diseases_covered"]) != covered_diseases:
        errors.append("diseases_covered does not equal diseases represented by cards")

    audit = package["audit"]
    if require_final and audit is None:
        errors.append("final package requires audit metadata")
    if require_final and not package["publication_type_verified_by_phase3"]:
        errors.append("final package publication type must be verified by Phase 3")
    if not require_final and audit is not None:
        errors.append("provisional package audit must be null")
    if audit is not None:
        if audit["approved_round"] != package["round"]:
            errors.append("audit approved_round does not match package round")
        if audit["audit_model"] == package["extraction_model"]:
            errors.append("audit model must differ from extraction model")
        if audit["extraction_model_reviewed"] != package["extraction_model"]:
            errors.append("extraction_model_reviewed does not match extraction_model")
        if audit["publication_type_verdict"]["verdict"] != "pass":
            errors.append("failed publication_type verdict blocks acceptance")
        if not audit["publication_type_verdict"]["verified_by_phase3"]:
            errors.append("audit must mark publication type as verified by Phase 3")
        verdict_ids = [result["card_id"] for result in audit["results"]]
        if len(verdict_ids) != len(set(verdict_ids)):
            errors.append("audit contains duplicate card verdicts")
        if set(verdict_ids) != set(card_ids):
            errors.append("audit must contain exactly one verdict for every card")
        failed = [result["card_id"] for result in audit["results"] if result["verdict"] == "fail"]
        if failed:
            errors.append("failed cards block acceptance: " + ", ".join(failed))

    report = {
        "cards": len(card_ids),
        "census_entries": len(census.get("entries", [])),
        "ratio": round(len(card_ids) / len(census["entries"]), 2) if census.get("entries") else None,
        "census_claims": len(census.get("entries", [])),
    }
    return errors, warnings, report


def validate_final_against_provisional(final, provisional):
    """Validate Phase 4 identity and lineage while allowing authorized card deltas."""
    errors = []
    if final.get("round") != provisional.get("round"):
        errors.append("final and approved provisional rounds differ")
    if final.get("paper_id") != provisional.get("paper_id"):
        errors.append("final and approved provisional paper_id values differ")
    if final.get("extraction_model") != provisional.get("extraction_model"):
        errors.append("final and approved provisional extraction_model values differ")
    if ("human_decisions" in final) != ("human_decisions" in provisional) or final.get("human_decisions") != provisional.get("human_decisions"):
        errors.append(
            "final must preserve Phase 2 human_decisions provenance exactly from the approved provisional"
        )
    return errors


def validate_review_files(*, provisional_path, review_path, phase2r_decisions_path=None):
    provisional = read_json(provisional_path, "provisional package")
    review = read_json(review_path, "Phase 3 review")
    phase2r_ledger, phase4_ledger, prior_review = load_delta_carry_context(phase2r_decisions_path)
    errors = [
        f"review: {error}"
        for error in validate_review(
            review, provisional, phase2r_ledger, phase4_ledger, prior_review
        )
    ]
    return errors, [], {
        "phase": 3,
        "cards": len(provisional.get("cards", [])),
        "review_results": len(review.get("card_results", [])),
        "review_scope": review.get("review_scope", "full"),
    }


def validate_phase4_decisions(*, provisional, review, final, ledger, provisional_filename, review_filename, final_filename):
    errors = []
    failed_ids = {result["card_id"] for result in review.get("card_results", []) if result.get("verdict") == "fail"}
    if ledger.get("purpose") != "finalize":
        errors.append("Phase 4 finalization requires a decision ledger with purpose finalize")
    if ledger.get("baseline_filename") != provisional_filename:
        errors.append("Phase 4 decision ledger baseline_filename does not match the approved provisional")
    if ledger.get("review_filename") != review_filename:
        errors.append("Phase 4 decision ledger review_filename does not match the active Phase 3 review")
    if ledger.get("output_filename") != final_filename:
        errors.append("Phase 4 decision ledger output_filename does not match paper.final.json")
    if ledger.get("paper_nickname") != final.get("paper_nickname"):
        errors.append("final paper_nickname does not match the user-finalized Phase 4 decision ledger")
    errors.extend(
        card_deltas.validate_package_delta(
            provisional, final, ledger, stage="phase4", allowed_direct_ids=failed_ids
        )
    )
    decisions_by_id = {item.get("card_id"): item.get("decision") for item in ledger.get("card_decisions", [])}
    unresolved_failed = sorted(card_id for card_id in failed_ids if card_id not in decisions_by_id)
    if unresolved_failed:
        errors.append(
            "Phase 4 decision ledger does not explicitly adjudicate every Phase 3-failed card: "
            + ", ".join(unresolved_failed)
        )
    if any(item.get("decision") == "add" for item in ledger.get("card_decisions", [])) and not failed_ids:
        errors.append("Phase 4 may not directly add cards when Phase 3 had no failed card; route additions through Phase 2R")

    publication = ledger.get("publication_type_decision")
    publication_verdict = (review.get("audit") or {}).get("publication_type_verdict") or {}
    if publication is None:
        if publication_verdict.get("verdict") == "fail":
            errors.append("Phase 4 decision ledger must explicitly adjudicate the failed publication type")
        if final.get("publication_type") != provisional.get("publication_type") or final.get("publication_type_basis") != provisional.get("publication_type_basis"):
            errors.append("publication type changed without a user-finalized Phase 4 publication_type_decision")
    else:
        if publication.get("decision") == "modify" and publication_verdict.get("verdict") != "fail":
            errors.append("Phase 4 may modify publication type only when Phase 3 failed it")
        if final.get("publication_type") != publication.get("publication_type"):
            errors.append("final publication_type does not match the Phase 4 decision ledger")
        if final.get("publication_type_basis") != publication.get("publication_type_basis"):
            errors.append("final publication_type_basis does not match the Phase 4 decision ledger")

    direct = {item["card_id"]: item["decision"] for item in ledger.get("card_decisions", [])}
    review_by_id = {item["card_id"]: item for item in review.get("card_results", [])}
    audit_by_id = {item["card_id"]: item for item in (final.get("audit") or {}).get("results", [])}
    for card in final.get("cards", []):
        card_id = card.get("card_id")
        audit_item = audit_by_id.get(card_id, {})
        if card_id in direct and direct[card_id] in {"modify", "retain"}:
            expected_basis = "phase4_adjudicated"
        elif card_id not in review_by_id:
            expected_basis = "phase4_adjudicated"
        else:
            expected_basis = review_by_id[card_id].get("review_basis", "phase3")
        if audit_item.get("review_basis") != expected_basis:
            errors.append(f"{card_id}: final audit review_basis must be {expected_basis}")
    return errors


def validate_phase_files(
    *, metadata_path, census_path, source_path, provisional_path, review_path, final_path,
    decisions_path=None, phase2r_decisions_path=None,
):
    metadata = read_json(metadata_path, "metadata")
    census = read_json(census_path, "census")
    provisional = read_json(provisional_path, "approved provisional package")
    review = read_json(review_path, "Phase 3 review")
    final = read_json(final_path, "final package")
    phase2r_ledger, phase4_ledger, prior_review = load_delta_carry_context(phase2r_decisions_path)
    errors = [
        f"review: {error}"
        for error in validate_review(
            review, provisional, phase2r_ledger, phase4_ledger, prior_review
        )
    ]
    errors.extend(
        f"final lineage: {error}"
        for error in validate_final_against_provisional(final, provisional)
    )
    approved_round = (final.get("audit") or {}).get("approved_round")
    if approved_round != provisional.get("round"):
        errors.append("final audit approved_round does not match provisional round")
    if approved_round != review.get("round"):
        errors.append("final audit approved_round does not match review round")
    audit = final.get("audit") or {}
    if audit.get("audit_model") != review.get("reviewer_model"):
        errors.append("final audit_model does not match Phase 3 reviewer_model")
    if audit.get("extraction_model_reviewed") != provisional.get("extraction_model"):
        errors.append("final extraction_model_reviewed does not match provisional extraction_model")
    if review.get("reviewer_model") == provisional.get("extraction_model"):
        errors.append("Phase 3 reviewer model must differ from Phase 2 extraction model")

    surfacing_scope = {
        item.get("card_id")
        for item in review.get("card_results", [])
        if item.get("review_basis", "phase3") == "phase3"
    }
    if decisions_path is None:
        if final.get("schema_version") == "5.1":
            errors.append("Phase 4 schema 5.1 requires --decisions so every final card delta is user-authorized")
    else:
        ledger = read_json(decisions_path, "Phase 4 decision ledger")
        errors.extend(
            f"Phase 4 decisions: {error}" for error in validate_phase4_decisions(
                provisional=provisional, review=review, final=final, ledger=ledger,
                provisional_filename=Path(provisional_path).name,
                review_filename=Path(review_path).name,
                final_filename=Path(final_path).name,
            )
        )
        surfacing_scope.update(card_deltas.changed_card_ids(ledger))

    errors.extend(
        f"final: {error}"
        for error in interpretation_surfacing_errors(final, surfacing_scope)
    )

    source_text = Path(source_path).read_text(encoding="utf-8")
    final_errors, warnings, report = validate_package(
        final, metadata, census, source_text=source_text, require_final=True
    )
    errors.extend(f"final: {error}" for error in final_errors)
    phase_report = {"phase": 4}
    phase_report.update(report or {})
    return errors, warnings, phase_report



def validate_handoff_files(*, provisional_path, review_path, decisions_path, phase2r_decisions_path=None):
    provisional = read_json(provisional_path, "provisional package")
    review = read_json(review_path, "Phase 3 review")
    phase2r_ledger, prior_phase4_ledger, prior_review = load_delta_carry_context(phase2r_decisions_path)
    ledger = read_json(decisions_path, "Phase 4 handoff decision ledger")
    errors = [
        f"review: {error}"
        for error in validate_review(
            review, provisional, phase2r_ledger, prior_phase4_ledger, prior_review
        )
    ]
    failed_ids = {result["card_id"] for result in review.get("card_results", []) if result.get("verdict") == "fail"}
    errors.extend(
        f"Phase 4 handoff: {error}"
        for error in card_deltas.validate_ledger_against_baseline(
            ledger, provisional, stage="phase4", allowed_direct_ids=failed_ids
        )
    )
    if ledger.get("purpose") != "phase2r_handoff":
        errors.append("Phase 4 handoff decision ledger purpose must be phase2r_handoff")
    if ledger.get("baseline_filename") != Path(provisional_path).name:
        errors.append("Phase 4 handoff baseline_filename does not match active provisional")
    if ledger.get("review_filename") != Path(review_path).name:
        errors.append("Phase 4 handoff review_filename does not match active Phase 3 review")
    if not ledger.get("phase2r_requests"):
        errors.append("Phase 4 handoff requires at least one explicit phase2r_request")
    if any(item.get("decision") == "add" for item in ledger.get("card_decisions", [])) and not failed_ids:
        errors.append("Phase 4 may not directly add cards without a Phase 3 failure; route the addition through Phase 2R")
    return errors, [], {
        "phase": 4,
        "handoff": "phase2r",
        "requests": len(ledger.get("phase2r_requests", [])),
        "direct_decisions": len(ledger.get("card_decisions", [])),
    }

def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--review-only", action="store_true")
    mode.add_argument("--handoff-only", action="store_true")
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--census", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--provisional", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--final", type=Path)
    parser.add_argument("--decisions", type=Path)
    parser.add_argument("--phase2r-decisions", type=Path)
    args = parser.parse_args(argv)
    if args.handoff_only and args.decisions is None:
        parser.error("Phase 4 handoff validation requires --decisions")
    required = () if (args.review_only or args.handoff_only) else ("metadata", "census", "source", "final")
    missing = [name for name in required if getattr(args, name) is None]
    if missing:
        parser.error("Phase 4 exit validation requires " + ", ".join(f"--{name}" for name in missing))
    return args


def main(argv=None):
    args = parse_args(argv)
    try:
        if args.review_only:
            errors, warnings, report = validate_review_files(
                provisional_path=args.provisional, review_path=args.review,
                phase2r_decisions_path=args.phase2r_decisions,
            )
            label = "PHASE 4 ENTRY"
        elif args.handoff_only:
            errors, warnings, report = validate_handoff_files(
                provisional_path=args.provisional, review_path=args.review,
                decisions_path=args.decisions,
                phase2r_decisions_path=args.phase2r_decisions,
            )
            label = "PHASE 4 HANDOFF"
        else:
            errors, warnings, report = validate_phase_files(
                metadata_path=args.metadata,
                census_path=args.census,
                source_path=args.source,
                provisional_path=args.provisional,
                review_path=args.review,
                final_path=args.final,
                decisions_path=args.decisions,
                phase2r_decisions_path=args.phase2r_decisions,
            )
            label = "PHASE 4"
    except (OSError, ValueError) as exc:
        sys.exit(f"{label if 'label' in locals() else 'PHASE 4'} VALIDATION FAILED:\n{exc}")
    if errors:
        sys.exit(f"{label} VALIDATION FAILED:\n" + "\n".join(errors))
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(json.dumps({"valid": True, **report}, sort_keys=True))


if __name__ == "__main__":
    main()
