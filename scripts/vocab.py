#!/usr/bin/env python3
"""Single source of truth for closed disease vocabularies and retrieval relations.
Evidence-card diseases, case-only disease options, taxonomy, categories and evidence
ranks live in ``schema/disease_vocabulary.json``. Explicit source aliases live in
``schema/source_disease_aliases.json``; they may map source wording to a canonical
evidence-card disease but do not extend the output vocabulary. ``umbrella`` remains
taxonomy only. ``retrieval_related`` is a separate, directional, category-specific
relation used only by case retrieval.
"""
import json
from pathlib import Path
SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"
VOCAB_PATH = SCHEMA_DIR / "disease_vocabulary.json"
SOURCE_DISEASE_ALIASES_PATH = SCHEMA_DIR / "source_disease_aliases.json"
PACKAGE_SCHEMA_PATH = SCHEMA_DIR / "ingestion_package_schema.json"
_VOCAB = json.loads(VOCAB_PATH.read_text(encoding="utf-8"))
DISEASES = list(_VOCAB["diseases"])
DISEASE_SET = set(DISEASES)
SOURCE_DISEASE_ALIASES = dict(
    json.loads(SOURCE_DISEASE_ALIASES_PATH.read_text(encoding="utf-8"))
)
_NORMALIZED_SOURCE_DISEASE_ALIASES = {
    alias.strip().casefold(): target
    for alias, target in SOURCE_DISEASE_ALIASES.items()
    if isinstance(alias, str) and alias.strip() and isinstance(target, str)
}
CASE_ONLY_DISEASES = list(_VOCAB.get("case_only_diseases", []))
CASE_ONLY_DISEASE_SET = set(CASE_ONLY_DISEASES)
CASE_DISEASES = DISEASES + CASE_ONLY_DISEASES
CASE_DISEASE_SET = set(CASE_DISEASES)
CASE_ONLY_USAGE = dict(_VOCAB.get("case_only_usage", {}))
UMBRELLA = {k: list(v) for k, v in _VOCAB["umbrella"].items()}
RETRIEVAL_RELATED = {
    disease: {category: list(targets) for category, targets in categories.items()}
    for disease, categories in _VOCAB.get("retrieval_related", {}).items()
}
CATEGORIES = list(_VOCAB["categories"])
EVIDENCE_TIERS = list(_VOCAB["evidence_tiers_strongest_first"])
PUBLICATION_TYPES = list(_VOCAB["publication_types"])
DISEASE_NAMING_EXPECTED = set(_VOCAB["disease_naming_expected"])
# Render and truncation order. Strongest tier first; truncation eats the tail.
TIER_RANK = {tier: i for i, tier in enumerate(EVIDENCE_TIERS)}
CATEGORY_RANK = {category: i for i, category in enumerate(CATEGORIES)}
UNSPECIFIED_DISEASE = "myeloid neoplasm, unspecified"
NO_HAEMATOLOGICAL_MALIGNANCY = "no_haematological_malignancy"


def canonical_source_disease(term):
    """Resolve a canonical disease or an exact configured source alias.
    Alias matching ignores surrounding whitespace and letter case only. It does not
    perform fuzzy matching, stemming, punctuation changes, or nearest-term mapping.
    ``None`` means the source term is outside the controlled vocabulary and aliases.
    """
    if not isinstance(term, str):
        return None
    normalized = term.strip()
    if normalized in DISEASE_SET:
        return normalized
    return _NORMALIZED_SOURCE_DISEASE_ALIASES.get(normalized.casefold())


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


def retrieval_related_diseases(disease, category):
    """Return direct related diseases configured for one case disease/category.

    This relation is intentionally non-transitive and directional. Taxonomic
    ``umbrella`` ancestors are not consulted.
    """
    return list(RETRIEVAL_RELATED.get(disease, {}).get(category, []))


def missing_umbrellas(diseases):
    """Backward-compatible alias for ancestors absent from an expanded tag set."""
    tagged = set(diseases)
    return [disease for disease in disease_ancestors(diseases) if disease not in tagged]


def check_vocabulary_consistency():
    """Fail loudly if schemas or configured relationships drift from the vocabulary."""
    schema = json.loads(PACKAGE_SCHEMA_PATH.read_text(encoding="utf-8"))
    enum = schema["$defs"]["disease"]["enum"]
    problems = []
    if list(enum) != DISEASES:
        problems.append(
            "ingestion_package_schema.json disease enum differs from disease_vocabulary.json"
        )
    normalized_aliases = set()
    canonical_casefold = {disease.casefold() for disease in DISEASES}
    for alias, target in SOURCE_DISEASE_ALIASES.items():
        if not isinstance(alias, str) or not alias.strip():
            problems.append("source disease aliases must be non-empty strings")
            continue
        normalized_alias = alias.strip().casefold()
        if normalized_alias in normalized_aliases:
            problems.append(
                f"source disease alias {alias!r} duplicates another alias after normalization"
            )
        normalized_aliases.add(normalized_alias)
        if normalized_alias in canonical_casefold:
            problems.append(
                f"source disease alias {alias!r} collides with a canonical disease"
            )
        if target not in DISEASE_SET:
            problems.append(
                f"source disease alias {alias!r} targets non-canonical disease {target!r}"
            )
    overlap = DISEASE_SET & CASE_ONLY_DISEASE_SET
    if overlap:
        problems.append(
            "case-only diseases overlap evidence-card diseases: " + ", ".join(sorted(overlap))
        )
    for disease in CASE_ONLY_DISEASES:
        if disease not in CASE_ONLY_USAGE:
            problems.append(f"case-only disease {disease!r} has no usage rule")
    for disease in CASE_ONLY_USAGE:
        if disease not in CASE_ONLY_DISEASE_SET:
            problems.append(f"case-only usage rule {disease!r} has no case-only disease")
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
    for disease, categories in RETRIEVAL_RELATED.items():
        if disease not in DISEASE_SET:
            problems.append(
                f"retrieval_related key {disease!r} is not an evidence-card disease"
            )
        if not isinstance(categories, dict):
            problems.append(f"retrieval_related[{disease!r}] must be an object")
            continue
        for category, targets in categories.items():
            if category not in DISEASE_NAMING_EXPECTED:
                problems.append(
                    f"retrieval_related[{disease!r}] category {category!r} is not disease-filtered"
                )
            if len(targets) != len(set(targets)):
                problems.append(
                    f"retrieval_related[{disease!r}][{category!r}] contains duplicates"
                )
            for target in targets:
                if target not in DISEASE_SET:
                    problems.append(
                        f"retrieval_related target {target!r} is not an evidence-card disease"
                    )
                if target == disease:
                    problems.append(
                        f"retrieval_related[{disease!r}][{category!r}] contains itself"
                    )
    return problems


if __name__ == "__main__":
    issues = check_vocabulary_consistency()
    if issues:
        for issue in issues:
            print("  -", issue)
        raise SystemExit(1)
    relation_count = sum(
        len(targets)
        for categories in RETRIEVAL_RELATED.values()
        for targets in categories.values()
    )
    print(
        f"OK: {len(DISEASES)} evidence-card diseases, "
        f"{len(CASE_ONLY_DISEASES)} case-only diseases, {len(CATEGORIES)} categories, "
        f"{len(EVIDENCE_TIERS)} evidence tiers, {relation_count} retrieval relations"
    )
