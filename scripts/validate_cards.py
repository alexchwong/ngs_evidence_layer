#!/usr/bin/env python3
"""Validate one publication's cards against schema, vocabulary, census and source.

Three things are checked that no model should be trusted to self-report:

  1. the quote is present in the source Markdown, character for character after
     typographic and table-markup folding;
  2. every card has exactly one quote and every quote has exactly one card, so a
     card cannot reach the corpus unquoted;
  3. the card set reconciles against the census, so under-extraction is a number
     rather than an impression.

What this script cannot check is whether the interpretation says more than its
quote supports. That is Phase 3, and it needs a different model, not a regex.

Usage:
  validate_cards.py cards.json --quotes quotes.json --census census.json \\
      --source input/<corpus>/markdown/<stem>.md
"""
import argparse
import html
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vocab  # noqa: E402

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - environment-dependent
    Draft202012Validator = None

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"
CARD_SCHEMA = SCHEMA_DIR / "card_schema.json"
QUOTE_SCHEMA = SCHEMA_DIR / "quote_schema.json"
CENSUS_SCHEMA = SCHEMA_DIR / "census_schema.json"

MAX_QUOTE_WORDS = 400
MIN_INTERPRETATION_WORDS = 12
RULE_ID = re.compile(r"\bR[1-5]\.\d{1,2}\b")
DISPOSITION = re.compile(r"\(([^()]*\bper\b[^()]*)\)\.?\s*$")


def normalise(text, markdown=False):
    """Fold typography and whitespace; optionally strip Markdown table markup."""
    text = html.unescape(unicodedata.normalize("NFKC", text))
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = re.sub(r"[\u2010-\u2015]", "-", text)
    if markdown:
        text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"!\[[^]]*]\([^)]*\)", " ", text)
        text = text.replace("|", " ")
        text = re.sub(r"(?m)^\s*:?-{3,}:?(?:\s+:?-{3,}:?)*\s*$", " ", text)
        text = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", text)
        text = text.replace("**", "").replace("__", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def schema_errors(document, schema_path, label):
    if Draft202012Validator is None:
        raise ValueError(
            "jsonschema not installed: python3 -m pip install -r requirements.txt"
        )
    schema = load_json(schema_path)
    errors = []
    for error in Draft202012Validator(schema).iter_errors(document):
        location = "/".join(str(part) for part in error.path) or "<root>"
        errors.append(f"{label} schema: {location}: {error.message}")
    return errors


def check_cards(document):
    """Vocabulary, identity and authoring checks internal to the card file."""
    errors = []
    warnings = []
    key = document.get("publication_key", "")
    covered_genes = set(document.get("genes_covered", []))
    covered_diseases = set(document.get("diseases_covered", []))
    seen_ids = set()

    for index, card in enumerate(document.get("cards", [])):
        card_id = card.get("card_id", "")
        tag = card_id or f"index {index}"

        if key and not card_id.startswith(f"{key}-"):
            errors.append(f"{tag}: card_id does not begin with publication_key plus '-'")
        if card_id in seen_ids:
            errors.append(f"{tag}: duplicate card_id")
        seen_ids.add(card_id)

        for gene in card.get("genes", []):
            if covered_genes and gene not in covered_genes:
                errors.append(f"{tag}: gene {gene} absent from genes_covered")

        diseases = card.get("diseases") or []
        for disease in diseases:
            if covered_diseases and disease not in covered_diseases:
                errors.append(f"{tag}: disease {disease} absent from diseases_covered")
        for umbrella in vocab.missing_umbrellas(diseases):
            errors.append(
                f"{tag}: specific entity tagged without its umbrella; add {umbrella!r} "
                "or a query on the umbrella will never see this card"
            )

        category = card.get("category")
        if category in vocab.DISEASE_NAMING_EXPECTED and not diseases:
            warnings.append(
                f"{tag}: {category} card names no disease; confirm the source really "
                "makes the claim without a disease context"
            )

        escalates_to = card.get("escalates_to")
        if escalates_to is not None:
            if category != "diagnosis":
                errors.append(
                    f"{tag}: escalates_to is set on a {category} card; it belongs only "
                    "on diagnosis cards"
                )
            if escalates_to not in vocab.DISEASE_SET:
                errors.append(f"{tag}: escalates_to {escalates_to!r} is outside the vocabulary")

        interpretation = card.get("interpretation", "")
        if len(interpretation.split()) < MIN_INTERPRETATION_WORDS:
            errors.append(f"{tag}: interpretation too short to stand alone without the source")

        disposition = DISPOSITION.search(interpretation)
        if disposition and not RULE_ID.search(disposition.group(1)):
            errors.append(
                f"{tag}: trailing disposition does not cite a rule ID in R<n>.<n> form"
            )

        secondary = card.get("secondary_citation")
        if secondary is not None and not secondary.get("display"):
            errors.append(f"{tag}: secondary_citation has no display string")
        if secondary is not None and card.get("evidence_tier") == "guideline criterion":
            warnings.append(
                f"{tag}: guideline criterion resting on a secondary citation; confirm the "
                "tier describes the analysis rather than the document"
            )

    return errors, warnings


def check_quotes(document, quotes_doc, source_text):
    errors = []
    warnings = []
    card_ids = [card.get("card_id") for card in document.get("cards", [])]
    cards_by_id = {
        card.get("card_id"): card for card in document.get("cards", [])
    }
    quote_map = {}
    for entry in quotes_doc.get("quotes", []):
        card_id = entry.get("card_id")
        if card_id in quote_map:
            errors.append(f"{card_id}: more than one quote for the same card")
        quote_map[card_id] = entry

    if quotes_doc.get("publication_key") != document.get("publication_key"):
        errors.append("quote file publication_key does not match the card file")

    for card_id in card_ids:
        if card_id not in quote_map:
            errors.append(f"{card_id}: no quote in the quote file")
    for card_id in quote_map:
        if card_id not in card_ids:
            errors.append(f"{card_id}: quote has no matching card")

    source = normalise(source_text, markdown=True) if source_text is not None else None
    seen = {}
    for card in document.get("cards", []):
        card_id = card.get("card_id")
        entry = quote_map.get(card_id)
        if entry is None:
            continue
        quote = entry.get("quote", "")
        words = len(quote.split())
        if words > MAX_QUOTE_WORDS:
            errors.append(f"{card_id}: quote is {words} words, cap {MAX_QUOTE_WORDS}")
        if quote.count("...") + quote.count("\u2026") > 1:
            errors.append(f"{card_id}: multiple ellipses suggest stitched text")
        if entry.get("locator") != card.get("locator"):
            errors.append(f"{card_id}: quote locator differs from card locator")
        folded = normalise(quote, markdown=True)
        if source is not None and folded not in source:
            errors.append(f"{card_id}: quote not found in the normalised source Markdown")
        if folded in seen:
            first_card_id = seen[folded]
            first_category = cards_by_id.get(first_card_id, {}).get("category")
            category = card.get("category")
            role_note = (
                f"different categories ({first_category}, {category}) may be legitimate"
                if first_category != category
                else f"both cards use category {category}"
            )
            warnings.append(
                f"{card_id}: quote is identical to {first_card_id}; {role_note}. Review "
                "whether the cards express independent claims; otherwise merge a redundant "
                "card or narrow each quote to the minimum claim-specific passage"
            )
        else:
            seen[folded] = card_id
    return errors, warnings


def check_census(document, census):
    """Reconcile the card set against the census and report the extraction ratio."""
    errors = []
    warnings = []
    census_genes = {entry["gene"] for entry in census.get("entries", [])}
    declared = document.get("census_entries")
    actual = len(census.get("entries", []))
    if declared != actual:
        errors.append(
            f"census_entries is {declared} but the census file holds {actual} entries"
        )

    carded_genes = set()
    carded_pairs = set()
    for card in document.get("cards", []):
        for gene in card.get("genes", []):
            carded_genes.add(gene)
            carded_pairs.add((gene, card.get("category")))

    unknown = sorted(carded_genes - census_genes)
    for gene in unknown:
        errors.append(
            f"card gene {gene} is absent from the census; the census is the completeness "
            "contract, so re-run Phase 1 rather than patching the card file"
        )

    uncarded = sorted(census_genes - carded_genes)
    census_pairs = {
        (entry["gene"], category)
        for entry in census.get("entries", [])
        for category in entry.get("categories", [])
    }
    missed_pairs = sorted(census_pairs - carded_pairs)
    return errors, warnings, {
        "census_entries": actual,
        "cards": len(document.get("cards", [])),
        "ratio": round(len(document.get("cards", [])) / actual, 2) if actual else None,
        "census_gene_category_pairs": len(census_pairs),
        "carded_gene_category_pairs": len(census_pairs & carded_pairs),
        "genes_with_no_card": uncarded,
        "gene_category_pairs_with_no_card": [
            {"gene": gene, "category": category} for gene, category in missed_pairs
        ],
    }


def validate(card_path, quotes_path=None, census_path=None, source_path=None):
    errors = []
    warnings = []
    report = {}

    errors.extend(f"vocabulary: {issue}" for issue in vocab.check_vocabulary_consistency())

    try:
        document = load_json(card_path)
    except ValueError as exc:
        return None, [str(exc)], warnings, report

    try:
        errors.extend(schema_errors(document, CARD_SCHEMA, "cards"))
    except ValueError as exc:
        return document, errors + [str(exc)], warnings, report

    card_errors, card_warnings = check_cards(document)
    errors.extend(card_errors)
    warnings.extend(card_warnings)

    source_text = None
    if source_path:
        try:
            source_text = Path(source_path).read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"cannot read source Markdown {source_path}: {exc}")

    if quotes_path:
        try:
            quotes_doc = load_json(quotes_path)
            errors.extend(schema_errors(quotes_doc, QUOTE_SCHEMA, "quotes"))
            quote_errors, quote_warnings = check_quotes(document, quotes_doc, source_text)
            errors.extend(quote_errors)
            warnings.extend(quote_warnings)
        except ValueError as exc:
            errors.append(str(exc))
    else:
        errors.append("--quotes is required: an unquoted card cannot be audited")

    if census_path:
        try:
            census = load_json(census_path)
            errors.extend(schema_errors(census, CENSUS_SCHEMA, "census"))
            census_errors, census_warnings, report = check_census(document, census)
            errors.extend(census_errors)
            warnings.extend(census_warnings)
        except ValueError as exc:
            errors.append(str(exc))
    else:
        errors.append("--census is required: without it under-extraction is invisible")

    return document, errors, warnings, report


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("card_file", type=Path)
    parser.add_argument("--quotes", type=Path)
    parser.add_argument("--census", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--report", type=Path, help="write the run report as JSON")
    args = parser.parse_args()

    document, errors, warnings, report = validate(
        args.card_file, args.quotes, args.census, args.source
    )

    for warning in warnings:
        print("  warning:", warning)

    if report:
        print(
            f"Extraction: {report['cards']} card(s) from {report['census_entries']} "
            f"census entr(ies), ratio {report['ratio']}"
        )
        print(
            f"Gene x category coverage: {report['carded_gene_category_pairs']}"
            f"/{report['census_gene_category_pairs']}"
        )
        if report["genes_with_no_card"]:
            print("Census genes with no card, each needing a stated reason:")
            for gene in report["genes_with_no_card"]:
                print("  -", gene)
            print(
                "  A low ratio is a signal that the gate was applied too tightly, "
                "not a sign of a clean run."
            )
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )

    if errors:
        print(f"FAILED: {len(errors)} problem(s)")
        for error in errors:
            print("  -", error)
        sys.exit(1)

    print(f"OK: {len(document.get('cards', []))} card(s) validated")


if __name__ == "__main__":
    main()
