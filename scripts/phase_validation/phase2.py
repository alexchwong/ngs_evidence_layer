#!/usr/bin/env python3
"""Self-contained deterministic validation for the Phase 2 provisional package."""
import argparse
import json
import re
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

PACKAGE_SCHEMA = json.loads(r'''{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://local/ngs_evidence_layer/ingestion_package_schema.json","title":"Phase 2 provisional or Phase 4 final evidence package","type":"object","required":["schema_version","paper_id","round","extraction_date","extraction_model","publication_type","publication_type_basis","publication_type_verified_by_phase3","genes_covered","diseases_covered","census_entries","cards","evidence","audit"],"additionalProperties":false,"properties":{"schema_version":{"const":"5.0"},"paper_id":{"type":"string","format":"uuid"},"round":{"type":"integer","minimum":1},"extraction_date":{"type":"string","format":"date"},"extraction_model":{"type":"string","minLength":1},"publication_type":{"enum":["guideline","consensus statement","primary study","systematic review","narrative review","other"]},"publication_type_basis":{"type":"string","minLength":1},"publication_type_verified_by_phase3":{"type":"boolean"},"genes_covered":{"type":"array","uniqueItems":true,"items":{"$ref":"#/$defs/gene"}},"diseases_covered":{"type":"array","uniqueItems":true,"items":{"$ref":"#/$defs/disease"}},"census_entries":{"type":"integer","minimum":0},"cards":{"type":"array","items":{"$ref":"#/$defs/card"}},"evidence":{"type":"array","items":{"$ref":"#/$defs/evidence"}},"audit":{"anyOf":[{"type":"null"},{"$ref":"#/$defs/audit"}]}},"$defs":{"gene":{"type":"string","pattern":"^[A-Z0-9][A-Z0-9\\-]*$"},"disease":{"enum":["CHIP","CCUS","MDS","MDS/AML","AML","APL","MDS/MPN","MDS/MPN-U","CMML","aCML","MDS/MPN-SF3B1-T","JMML","MPN","MPN-U","PV","ET","PMF","post-PV/post-ET MF","MPN blast phase","CML","CNL","CEL","mastocytosis","myeloid/lymphoid neoplasm with eosinophilia and TK fusion","BPDCN","germline predisposition syndrome","myeloid neoplasm, unspecified","lymphoid neoplasm","acute leukaemia of ambiguous lineage","histiocytic/dendritic neoplasm","haematological malignancy, other"]},"citation":{"type":"object","required":["display"],"additionalProperties":false,"properties":{"authors":{"type":"array","items":{"type":"string"}},"title":{"type":"string"},"journal":{"type":"string"},"year":{"type":"integer","minimum":1950,"maximum":2100},"volume":{"type":"string"},"issue":{"type":"string"},"pages":{"type":"string"},"display":{"type":"string","minLength":1},"citation_incomplete":{"type":"array","uniqueItems":true,"items":{"type":"string"}}}},"card":{"type":"object","required":["card_id","locator","interpretation","genes","diseases","category","evidence_tier","secondary_citation"],"additionalProperties":false,"properties":{"card_id":{"type":"string","minLength":1},"locator":{"type":"string","minLength":1},"interpretation":{"type":"string","minLength":1},"genes":{"type":"array","minItems":1,"uniqueItems":true,"items":{"$ref":"#/$defs/gene"}},"diseases":{"type":"array","uniqueItems":true,"items":{"$ref":"#/$defs/disease"}},"disease_ancestors":{"type":"array","uniqueItems":true,"items":{"$ref":"#/$defs/disease"}},"category":{"enum":["diagnosis","prognosis","treatment","biomarker","germline"]},"evidence_tier":{"enum":["guideline criterion","multivariable-adjusted","univariable or descriptive","restated secondary"]},"secondary_citation":{"anyOf":[{"type":"null"},{"$ref":"#/$defs/citation"}]}},"allOf":[{"if":{"properties":{"category":{"enum":["diagnosis","prognosis","treatment","biomarker"]}},"required":["category"]},"then":{"properties":{"diseases":{"minItems":1}}}}]},"fragment":{"type":"object","required":["fragment_id","role","quote","locator"],"additionalProperties":false,"properties":{"fragment_id":{"type":"string","pattern":"^F[0-9]{2}$"},"role":{"enum":["claim","scope_heading","column_header","row_header","cell","legend","footnote"]},"quote":{"type":"string","minLength":1},"locator":{"type":"string","minLength":1}}},"support_map":{"type":"object","minProperties":1,"additionalProperties":false,"properties":{"gene":{"$ref":"#/$defs/fragment_ids"},"disease":{"$ref":"#/$defs/fragment_ids"},"role":{"$ref":"#/$defs/fragment_ids"},"population":{"$ref":"#/$defs/fragment_ids"},"effect":{"$ref":"#/$defs/fragment_ids"},"qualifier":{"$ref":"#/$defs/fragment_ids"}}},"fragment_ids":{"type":"array","minItems":1,"uniqueItems":true,"items":{"type":"string","pattern":"^F[0-9]{2}$"}},"table_relation":{"type":"object","required":["value_fragment_id","header_fragment_ids","qualifier_fragment_ids"],"additionalProperties":false,"properties":{"value_fragment_id":{"type":"string","pattern":"^F[0-9]{2}$"},"header_fragment_ids":{"$ref":"#/$defs/fragment_ids"},"qualifier_fragment_ids":{"type":"array","uniqueItems":true,"items":{"type":"string","pattern":"^F[0-9]{2}$"}}}},"evidence":{"oneOf":[{"type":"object","required":["card_id","evidence_type","fragments","support_map"],"additionalProperties":false,"properties":{"card_id":{"type":"string","minLength":1},"evidence_type":{"const":"contiguous_text"},"fragments":{"type":"array","minItems":1,"maxItems":1,"items":{"$ref":"#/$defs/fragment"}},"support_map":{"$ref":"#/$defs/support_map"}}},{"type":"object","required":["card_id","evidence_type","fragments","support_map"],"additionalProperties":false,"properties":{"card_id":{"type":"string","minLength":1},"evidence_type":{"const":"composite_text"},"fragments":{"type":"array","minItems":2,"maxItems":6,"items":{"$ref":"#/$defs/fragment"}},"support_map":{"$ref":"#/$defs/support_map"}}},{"type":"object","required":["card_id","evidence_type","fragments","support_map","table_relations"],"additionalProperties":false,"properties":{"card_id":{"type":"string","minLength":1},"evidence_type":{"const":"table_relation"},"fragments":{"type":"array","minItems":2,"maxItems":12,"items":{"$ref":"#/$defs/fragment"}},"support_map":{"$ref":"#/$defs/support_map"},"table_relations":{"type":"array","minItems":1,"items":{"$ref":"#/$defs/table_relation"}}}}]},"audit":{"type":"object","required":["audit_date","audit_model","extraction_model_reviewed","approved_round","publication_type_verdict","results"],"additionalProperties":false,"properties":{"audit_date":{"type":"string","format":"date"},"audit_model":{"type":"string","minLength":1},"extraction_model_reviewed":{"type":"string","minLength":1},"approved_round":{"type":"integer","minimum":1},"publication_type_verdict":{"type":"object","required":["verdict","verified_by_phase3"],"additionalProperties":false,"properties":{"verdict":{"enum":["pass","fail"]},"verified_by_phase3":{"const":true},"reason":{"type":"string","minLength":1}},"allOf":[{"if":{"properties":{"verdict":{"const":"fail"}},"required":["verdict"]},"then":{"required":["reason"]}}]},"results":{"type":"array","items":{"type":"object","required":["card_id","verdict"],"additionalProperties":false,"properties":{"card_id":{"type":"string","minLength":1},"verdict":{"enum":["pass","fail"]},"reason":{"type":"string","minLength":1}},"allOf":[{"if":{"properties":{"verdict":{"const":"fail"}},"required":["verdict"]},"then":{"required":["reason"]}}]}}}}}}''')
UMBRELLA = json.loads(r'''{"MDS/AML":["MDS","AML"],"APL":["AML"],"MDS/MPN":["MDS","MPN"],"MDS/MPN-U":["MDS/MPN"],"CMML":["MDS/MPN"],"aCML":["MDS/MPN"],"MDS/MPN-SF3B1-T":["MDS/MPN"],"MPN-U":["MPN"],"PV":["MPN"],"ET":["MPN"],"PMF":["MPN"],"post-PV/post-ET MF":["MPN"],"MPN blast phase":["MPN"],"CML":["MPN"],"CNL":["MPN"],"CEL":["MPN"],"JMML":["MPN"],"BPDCN":["histiocytic/dendritic neoplasm"]}''')
DISEASES = list(PACKAGE_SCHEMA["$defs"]["disease"]["enum"])
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
    if package["round"] == 1 and not require_final:
        if package["publication_type"] != census.get("publication_type"):
            errors.append("first-round package publication_type does not match census")
        if package["publication_type_basis"] != census.get("publication_type_basis"):
            errors.append("first-round package publication_type_basis does not match census")
        if package["publication_type_verified_by_phase3"]:
            errors.append("first-round provisional publication type cannot already be verified")

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

    census_pairs = {
        (entry["gene"], category)
        for entry in census.get("entries", []) for category in entry.get("categories", [])
    }
    card_pairs = {
        (gene, card["category"])
        for card in package["cards"] for gene in card["genes"]
    }
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
        "gene_category_pairs_with_no_card": [
            {"gene": gene, "category": category}
            for gene, category in sorted(census_pairs - card_pairs)
        ],
    }
    return errors, warnings, report


def validate_phase_files(*, metadata_path, census_path, source_path, provisional_path):
    metadata = read_json(metadata_path, "metadata")
    census = read_json(census_path, "census")
    provisional = read_json(provisional_path, "provisional package")
    source_text = Path(source_path).read_text(encoding="utf-8")
    package_errors, warnings, report = validate_package(
        provisional, metadata, census, source_text=source_text, require_final=False
    )
    phase_report = {"phase": 2}
    phase_report.update(report or {})
    return [f"provisional: {error}" for error in package_errors], warnings, phase_report


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--provisional", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        errors, warnings, report = validate_phase_files(
            metadata_path=args.metadata,
            census_path=args.census,
            source_path=args.source,
            provisional_path=args.provisional,
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
