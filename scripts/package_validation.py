#!/usr/bin/env python3
"""Shared deterministic validation for v0.1.1 working and accepted artefacts."""
import copy
import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "schema"
UMBRELLAS = {
    "APL": "AML", "PV": "MPN-U", "ET": "MPN-U", "PMF": "MPN-U",
    "post-PV/post-ET MF": "MPN-U", "CNL": "MPN-U", "CEL": "MPN-U",
}


def read_json(path, label="JSON"):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read {label} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid {label} in {path}: {exc}") from exc


def schema_errors(document, schema_name, label):
    schema = read_json(SCHEMAS / schema_name, "schema")
    resources = []
    for path in SCHEMAS.glob("*_schema.json"):
        referenced_schema = read_json(path, "schema")
        if "$id" in referenced_schema:
            resources.append((referenced_schema["$id"], Resource.from_contents(referenced_schema)))
    registry = Registry().with_resources(resources)
    errors = sorted(
        Draft202012Validator(
            schema,
            registry=registry,
            format_checker=FormatChecker(),
        ).iter_errors(document),
        key=lambda error: list(error.absolute_path),
    )
    return [
        f"{label} schema: {'/'.join(str(p) for p in error.absolute_path) or '<root>'}: "
        f"{error.message}" for error in errors
    ]


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


def validate_metadata(metadata):
    return schema_errors(metadata, "metadata_schema.json", "metadata")


def validate_census(census, metadata=None):
    errors = schema_errors(census, "census_schema.json", "census")
    entry_ids = [entry.get("entry_id") for entry in census.get("entries", [])]
    genes = [entry.get("gene") for entry in census.get("entries", [])]
    if len(entry_ids) != len(set(entry_ids)):
        errors.append("census contains duplicate entry_id values")
    if len(genes) != len(set(genes)):
        errors.append("census contains duplicate gene entries")
    if metadata and census.get("paper_id") != metadata.get("paper_id"):
        errors.append("census paper_id does not match metadata")
    return errors


def extraction_view(package):
    result = copy.deepcopy(package)
    result["audit"] = None
    return result


def validate_package(package, metadata, census, source_text=None, require_final=False):
    errors = schema_errors(package, "ingestion_package_schema.json", "package")
    warnings = []
    if errors:
        return errors, warnings, None

    if package["paper_id"] != metadata["paper_id"]:
        errors.append("package paper_id does not match metadata")
    if package["census_entries"] != len(census.get("entries", [])):
        errors.append("package census_entries does not match census")

    card_ids = [card["card_id"] for card in package["cards"]]
    quote_ids = [quote["card_id"] for quote in package["quotes"]]
    if len(card_ids) != len(set(card_ids)):
        errors.append("package contains duplicate card_id values")
    if len(quote_ids) != len(set(quote_ids)):
        errors.append("package contains more than one quote for the same card")
    missing_quotes = sorted(set(card_ids) - set(quote_ids))
    unknown_quotes = sorted(set(quote_ids) - set(card_ids))
    if missing_quotes:
        errors.append("cards with no quote: " + ", ".join(missing_quotes))
    if unknown_quotes:
        errors.append("quotes for unknown cards: " + ", ".join(unknown_quotes))

    prefix = metadata["publication_key"] + "-"
    for card in package["cards"]:
        card_id = card["card_id"]
        if not card_id.startswith(prefix):
            errors.append(f"{card_id}: card_id must begin with {prefix}")
        if card["category"] != "diagnosis" and card.get("escalates_to") is not None:
            errors.append(f"{card_id}: escalates_to is allowed only on diagnosis cards")
        for disease in card["diseases"]:
            umbrella = UMBRELLAS.get(disease)
            if umbrella and umbrella not in card["diseases"]:
                errors.append(f"{card_id}: disease {disease} requires umbrella tag {umbrella}")

    quote_texts = {}
    source = normalise(source_text, markdown=True) if source_text is not None else None
    for quote in package["quotes"]:
        card_id = quote["card_id"]
        if len(quote["quote"].split()) > 400:
            errors.append(f"{card_id}: quote exceeds 400 words")
        if source is not None and normalise(quote["quote"], markdown=True) not in source:
            errors.append(f"{card_id}: quote not found verbatim in paper.md")
        duplicate = quote_texts.get(normalise(quote["quote"]))
        if duplicate:
            warnings.append(f"{card_id}: quote is identical to {duplicate}; review independent utility")
        quote_texts[normalise(quote["quote"])] = card_id

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
    if not require_final and audit is not None:
        errors.append("provisional package audit must be null")
    if audit is not None:
        if audit["approved_round"] != package["round"]:
            errors.append("audit approved_round does not match package round")
        if audit["audit_model"] == package["extraction_model"]:
            errors.append("audit model must differ from extraction model")
        if audit["extraction_model_reviewed"] != package["extraction_model"]:
            errors.append("extraction_model_reviewed does not match extraction_model")
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


def validate_final_against_provisional(final, provisional):
    errors = []
    if final.get("round") != provisional.get("round"):
        errors.append("final and approved provisional rounds differ")
    if extraction_view(final) != extraction_view(provisional):
        errors.append("Phase 3 changed extraction content; only audit may change")
    return errors