#!/usr/bin/env python3
"""Single source of truth for the closed vocabularies.

Every script that names a disease, a category or an evidence tier loads it from
here. Duplicating the lists inline is how the retriever and the validator end up
disagreeing about what a legal disease is, which surfaces as cards that validate
and then never retrieve.

The data lives in schema/disease_vocabulary.json; the enum in the merged ingestion
package schema is checked against it by check_vocabulary_consistency().
"""
import json
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"
VOCAB_PATH = SCHEMA_DIR / "disease_vocabulary.json"
PACKAGE_SCHEMA_PATH = SCHEMA_DIR / "ingestion_package_schema.json"

_VOCAB = json.loads(VOCAB_PATH.read_text(encoding="utf-8"))

DISEASES = list(_VOCAB["diseases"])
DISEASE_SET = set(DISEASES)
UMBRELLA = {k: list(v) for k, v in _VOCAB["umbrella"].items()}
CATEGORIES = list(_VOCAB["categories"])
EVIDENCE_TIERS = list(_VOCAB["evidence_tiers_strongest_first"])
PUBLICATION_TYPES = list(_VOCAB["publication_types"])
DISEASE_NAMING_EXPECTED = set(_VOCAB["disease_naming_expected"])

# Render and truncation order. Strongest tier first; truncation eats the tail.
TIER_RANK = {tier: i for i, tier in enumerate(EVIDENCE_TIERS)}
CATEGORY_RANK = {category: i for i, category in enumerate(CATEGORIES)}

UNSPECIFIED_DISEASE = "myeloid neoplasm, unspecified"


def disease_ancestors(diseases):
    """Return all broader taxonomic ancestors in canonical vocabulary order.

    Card ``diseases`` are exact clinical applicability values. Ancestors are
    derived separately for broad corpus indexing so that, for example, a CMML
    card can be discovered under MDS/MPN, MDS, and MPN without becoming
    clinically applicable to every generic MDS or MPN case.
    """
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


def missing_umbrellas(diseases):
    """Backward-compatible alias for ancestors absent from an expanded tag set."""
    tagged = set(diseases)
    return [disease for disease in disease_ancestors(diseases) if disease not in tagged]


def check_vocabulary_consistency():
    """Fail loudly if the JSON Schema enum has drifted from the vocabulary file."""
    schema = json.loads(PACKAGE_SCHEMA_PATH.read_text(encoding="utf-8"))
    enum = schema["$defs"]["disease"]["enum"]
    problems = []
    if list(enum) != DISEASES:
        problems.append(
            "ingestion_package_schema.json disease enum differs from disease_vocabulary.json"
        )
    for term in UMBRELLA:
        if term not in DISEASE_SET:
            problems.append(f"umbrella key {term!r} is not in the disease vocabulary")
    for parents in UMBRELLA.values():
        for parent in parents:
            if parent not in DISEASE_SET:
                problems.append(f"umbrella target {parent!r} is not in the vocabulary")
    for disease in UMBRELLA:
        try:
            disease_ancestors([disease])
        except ValueError as exc:
            problems.append(str(exc))
    return problems


if __name__ == "__main__":
    issues = check_vocabulary_consistency()
    if issues:
        for issue in issues:
            print("  -", issue)
        raise SystemExit(1)
    print(
        f"OK: {len(DISEASES)} diseases, {len(CATEGORIES)} categories, "
        f"{len(EVIDENCE_TIERS)} evidence tiers"
    )
