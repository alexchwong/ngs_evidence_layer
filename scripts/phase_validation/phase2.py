#!/usr/bin/env python3
"""Deterministic validation for Phase 2 using bundled canonical JSON assets."""
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


DISEASE_VOCABULARY = load_json_asset("disease_vocabulary.json")
TERMS = list(DISEASE_VOCABULARY["terms"])
DISEASES = [term["name"] for term in TERMS]
UMBRELLA = {
    term["name"]: list(term.get("parents", []))
    for term in TERMS
    if term.get("parents")
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


def schema_errors(document, label="package"):
    errors = sorted(
        Draft202012Validator(PACKAGE_SCHEMA, format_checker=FormatChecker()).iter_errors(document),
        key=lambda error: list(error.absolute_path),
    )
    return [
        f"{label} schema: {'/'.join(str(p) for p in error.absolute_path) or '<root>'}: "
        f"{error.message}" for error in errors
    ]


def validate_package(package, metadata, census, source_text=None, require_final=False):
    errors = schema_errors(package, "package")
    warnings = []
    if errors:
        return errors, warnings, None

    if package["paper_id"] != metadata["paper_id"]:
        errors.append("package paper_id does not match metadata")
    if package["census_entries"] != len(census.get("entries", [])):
        errors.append("package census_entries does not match census")
    if "paper_nickname" in package:
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

    bundle_texts = {}
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

        normalized_fragments = []
        for fragment in fragments:
            fragment_label = f"{card_id}/{fragment['fragment_id']}"
            quote_text = fragment["quote"]
            if REFERENCE_ENTRY_RE.search(quote_text):
                errors.append(f"{fragment_label}: fragment appears to be a bibliographic reference-list entry")
            normalized = normalise(quote_text, markdown=True)
            if source is not None and normalized not in source:
                errors.append(f"{fragment_label}: fragment not found verbatim in paper.md")
            normalized_fragments.append(normalized)
        normalized_bundle = " || ".join(normalized_fragments)
        duplicate = bundle_texts.get(normalized_bundle)
        if duplicate:
            warnings.append(f"{card_id}: evidence is identical to {duplicate}; review independent utility")
        bundle_texts[normalized_bundle] = card_id

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


def validate_phase_files(
    *, metadata_path, census_path, source_path, provisional_path,
    base_final_path=None, base_provisional_path=None, base_review_path=None,
    decisions_path=None, phase4_decisions_path=None,
):
    metadata = read_json(metadata_path, "metadata")
    census = read_json(census_path, "census")
    provisional = read_json(provisional_path, "provisional package")
    source_text = Path(source_path).read_text(encoding="utf-8")
    package_errors, warnings, report = validate_package(
        provisional, metadata, census, source_text=source_text, require_final=False
    )

    expected_publication = census
    expected_label = "census"
    review_baseline = None
    if base_final_path is not None and base_provisional_path is not None:
        package_errors.append("Phase 2R must use either --base-final or --base-provisional, not both")
    elif base_final_path is not None:
        review_baseline = read_json(base_final_path, "accepted final package")
        expected_publication = review_baseline
        expected_label = "accepted final"
    elif base_provisional_path is not None:
        review_baseline = read_json(base_provisional_path, "Phase 2R baseline provisional")
        expected_publication = review_baseline
        expected_label = "Phase 2R baseline provisional"
        if phase4_decisions_path is not None:
            phase4_ledger = read_json(phase4_decisions_path, "Phase 4 decision ledger")
            allowed_direct_ids = None
            if base_review_path is not None:
                base_review = read_json(base_review_path, "Phase 4 active review")
                if phase4_ledger.get("review_filename") != Path(base_review_path).name:
                    package_errors.append("Phase 4 handoff review_filename does not match --base-review")
                allowed_direct_ids = {
                    item.get("card_id") for item in base_review.get("card_results", [])
                    if item.get("verdict") == "fail"
                }
            else:
                package_errors.append("Phase 4 handoff requires --base-review")
            package_errors.extend(
                f"Phase 4 handoff: {error}"
                for error in card_deltas.validate_ledger_against_baseline(
                    phase4_ledger, review_baseline, stage="phase4",
                    allowed_direct_ids=allowed_direct_ids,
                )
            )
            review_baseline = card_deltas.apply_card_decisions(review_baseline, phase4_ledger)
            review_baseline = card_deltas.apply_publication_type_decision(review_baseline, phase4_ledger)
            expected_publication = review_baseline
            expected_label = "Phase 4 current state"

    if review_baseline is not None:
        if provisional.get("schema_version") != "5.1":
            package_errors.append("Phase 2R provisional packages must use schema_version 5.1")
        if review_baseline.get("paper_id") != provisional.get("paper_id"):
            package_errors.append(f"{expected_label} paper_id does not match provisional package")
        baseline_round = review_baseline.get("round")
        if isinstance(baseline_round, int) and provisional.get("round") != baseline_round + 1:
            package_errors.append(
                f"Phase 2R provisional round must be baseline round + 1 ({baseline_round + 1}); "
                f"found {provisional.get('round')!r}"
            )
        if decisions_path is None:
            package_errors.append("Phase 2R requires --decisions so every card delta is user-authorized")
        else:
            ledger = read_json(decisions_path, "Phase 2R decision ledger")
            if ledger.get("baseline_filename") not in {
                Path(base_final_path).name if base_final_path else None,
                Path(base_provisional_path).name if base_provisional_path else None,
            }:
                package_errors.append("Phase 2R decision ledger baseline_filename does not match the supplied baseline file")
            if ledger.get("output_filename") != Path(provisional_path).name:
                package_errors.append("Phase 2R decision ledger output_filename does not match --provisional")
            if phase4_decisions_path is not None:
                if ledger.get("phase4_decisions_filename") != Path(phase4_decisions_path).name:
                    package_errors.append("Phase 2R decision ledger phase4_decisions_filename does not match --phase4-decisions")
            elif ledger.get("phase4_decisions_filename") is not None:
                package_errors.append("Phase 2R decision ledger names Phase 4 decisions but --phase4-decisions was not supplied")
            package_errors.extend(
                f"Phase 2R decisions: {error}"
                for error in card_deltas.validate_package_delta(
                    review_baseline, provisional, ledger, stage="phase2r"
                )
            )
            if not ledger.get("card_decisions"):
                warnings.append("Phase 2R decision ledger contains no card changes")

    if provisional.get("publication_type") != expected_publication.get("publication_type"):
        package_errors.append(
            f"provisional publication_type does not match {expected_label}"
        )
    if provisional.get("publication_type_basis") != expected_publication.get("publication_type_basis"):
        package_errors.append(
            f"provisional publication_type_basis does not match {expected_label}"
        )
    phase_report = {"phase": 2}
    phase_report.update(report or {})
    if decisions_path is not None:
        phase_report["review_mode"] = "phase2r"
    return [f"provisional: {error}" for error in package_errors], warnings, phase_report


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--provisional", type=Path, required=True)
    parser.add_argument("--base-final", type=Path)
    parser.add_argument("--base-provisional", type=Path)
    parser.add_argument("--base-review", type=Path)
    parser.add_argument("--decisions", type=Path)
    parser.add_argument("--phase4-decisions", type=Path)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        errors, warnings, report = validate_phase_files(
            metadata_path=args.metadata,
            census_path=args.census,
            source_path=args.source,
            provisional_path=args.provisional,
            base_final_path=args.base_final,
            base_provisional_path=args.base_provisional,
            base_review_path=args.base_review,
            decisions_path=args.decisions,
            phase4_decisions_path=args.phase4_decisions,
        )
    except (OSError, ValueError) as exc:
        sys.exit(f"PHASE 2 VALIDATION FAILED:\n{exc}")
    if errors:
        sys.exit("PHASE 2 VALIDATION FAILED:\n" + "\n".join(errors))
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(json.dumps({"valid": True, **report}, sort_keys=True))


if __name__ == "__main__":
    main()
