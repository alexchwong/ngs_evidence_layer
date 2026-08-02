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


def missing_umbrellas(diseases):
    """Umbrella tags a card claims a specific entity but omits.

    Umbrella tagging is what makes a query on AML see an APL card. A card tagged
    APL alone is invisible to the AML query, which is a silent retrieval hole
    rather than a visible error, so it is checked mechanically.
    """
    tagged = set(diseases)
    required = set()
    for disease in tagged:
        required.update(UMBRELLA.get(disease, []))
    return sorted(required - tagged)


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
