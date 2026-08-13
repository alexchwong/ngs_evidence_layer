#!/usr/bin/env python3
"""Single source of truth for closed disease terminology and retrieval relations.

Every evidence-card disease is defined once in ``schema/disease_vocabulary.json``
under ``terms``. Canonical names, reviewed source aliases, taxonomic parents, broad
case-major retrieval categories, and directional category-specific retrieval
relationships are co-located on that term. Runtime views are derived here; the
committed package schema contains no duplicate disease enum.
"""
import copy
import json
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"
VOCAB_PATH = SCHEMA_DIR / "disease_vocabulary.json"
PACKAGE_SCHEMA_PATH = SCHEMA_DIR / "ingestion_package_schema.json"

_VOCAB = json.loads(VOCAB_PATH.read_text(encoding="utf-8"))
TERMS = list(_VOCAB["terms"])
DISEASES = [term["name"] for term in TERMS]
DISEASE_SET = set(DISEASES)
SOURCE_DISEASE_ALIASES = {
    alias: term["name"]
    for term in TERMS
    for alias in term.get("aliases", [])
}
_NORMALIZED_SOURCE_DISEASE_ALIASES = {
    alias.strip().casefold(): target
    for alias, target in SOURCE_DISEASE_ALIASES.items()
    if isinstance(alias, str) and alias.strip() and isinstance(target, str)
}
CASE_ONLY_DISEASES = list(_VOCAB.get("case_only_diseases", []))
CASE_ONLY_DISEASE_SET = set(CASE_ONLY_DISEASES)
CASE_DISEASES = DISEASES + CASE_ONLY_DISEASES
CASE_DISEASE_SET = set(CASE_DISEASES)
_NORMALIZED_CASE_DISEASES = {
    disease.strip().casefold(): disease
    for disease in CASE_DISEASES
    if isinstance(disease, str) and disease.strip()
}
CASE_ONLY_USAGE = dict(_VOCAB.get("case_only_usage", {}))
_CASE_MAJOR_CATEGORY_MAP = _VOCAB.get("case_major_categories", {})
CASE_MAJOR_CATEGORIES = list(_CASE_MAJOR_CATEGORY_MAP)
CASE_MAJOR_CATEGORY_SET = set(CASE_MAJOR_CATEGORIES)
CASE_MAJOR_CATEGORY_DISEASES = {
    category: list(diseases)
    for category, diseases in _CASE_MAJOR_CATEGORY_MAP.items()
}
TERM_CASE_MAJOR_CATEGORIES = {
    disease: [
        category for category in CASE_MAJOR_CATEGORIES
        if disease in CASE_MAJOR_CATEGORY_DISEASES.get(category, [])
    ]
    for disease in DISEASES
}
UMBRELLA = {
    term["name"]: list(term.get("parents", []))
    for term in TERMS
    if term.get("parents")
}
RETRIEVAL_RELATED = {
    term["name"]: {
        category: list(targets)
        for category, targets in term.get("retrieval_related", {}).items()
    }
    for term in TERMS
    if term.get("retrieval_related")
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


def bind_disease_vocabulary(schema):
    """Return a copy of the package schema with the canonical disease enum bound.

    The committed ingestion schema is structural only. Binding at validation time
    keeps JSON Schema enforcement strict without maintaining a second disease list.
    """
    bound = copy.deepcopy(schema)
    disease = bound.get("$defs", {}).get("disease")
    if not isinstance(disease, dict):
        raise ValueError("package schema $defs.disease must be an object")
    disease["enum"] = list(DISEASES)
    return bound


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


def canonical_case_disease(term):
    """Resolve a case disease from a canonical name or configured source alias.

    Matching ignores surrounding whitespace and letter case only. No fuzzy
    matching, stemming, punctuation rewriting, or nearest-term mapping is
    performed. Case-only values are accepted by canonical name. ``None`` means
    the supplied term cannot be deterministically resolved.
    """
    if not isinstance(term, str):
        return None
    normalized = term.strip()
    if not normalized:
        return None
    canonical = _NORMALIZED_CASE_DISEASES.get(normalized.casefold())
    if canonical is not None:
        return canonical
    return _NORMALIZED_SOURCE_DISEASE_ALIASES.get(normalized.casefold())


def case_major_categories_for_disease(disease):
    """Return broad reporting-retrieval categories for one canonical disease.

    This relation is intentionally separate from taxonomic ``parents`` and from
    category-specific ``retrieval_related``. It is used to create a broad
    diagnosis search space before integrated diagnosis is adjudicated.
    """
    if disease == NO_HAEMATOLOGICAL_MALIGNANCY:
        return [NO_HAEMATOLOGICAL_MALIGNANCY]
    return list(TERM_CASE_MAJOR_CATEGORIES.get(disease, []))


def diseases_for_case_major_category(category):
    """Return canonical evidence-card diseases belonging to one major category."""
    if category not in CASE_MAJOR_CATEGORY_SET:
        return []
    return [
        disease for disease in DISEASES
        if category in TERM_CASE_MAJOR_CATEGORIES.get(disease, [])
    ]


def disease_matches_case_major_category(disease, category):
    """Return whether a canonical/case-only disease is in a major retrieval bucket."""
    return category in case_major_categories_for_disease(disease)


def preferred_case_major_category(disease):
    """Return the first configured major category for backward-compatible callers."""
    categories = case_major_categories_for_disease(disease)
    return categories[0] if categories else None


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
    parent/ancestor relationships are not consulted.
    """
    return list(RETRIEVAL_RELATED.get(disease, {}).get(category, []))


def missing_umbrellas(diseases):
    """Backward-compatible alias for ancestors absent from an expanded tag set."""
    tagged = set(diseases)
    return [disease for disease in disease_ancestors(diseases) if disease not in tagged]


def check_vocabulary_consistency():
    """Fail loudly if term definitions, relationships, or structural schema are invalid."""
    problems = []
    schema = json.loads(PACKAGE_SCHEMA_PATH.read_text(encoding="utf-8"))
    disease_schema = schema.get("$defs", {}).get("disease")
    if not isinstance(disease_schema, dict):
        problems.append("ingestion package schema $defs.disease must be an object")
    elif "enum" in disease_schema:
        problems.append(
            "ingestion_package_schema.json must not contain a disease enum; bind it from disease_vocabulary.json at validation time"
        )

    if not isinstance(TERMS, list) or not TERMS:
        problems.append("disease vocabulary terms must be a non-empty array")
        return problems

    names = []
    for index, term in enumerate(TERMS):
        if not isinstance(term, dict):
            problems.append(f"disease term {index} must be an object")
            continue
        name = term.get("name")
        if not isinstance(name, str) or not name.strip():
            problems.append(f"disease term {index} has no non-empty name")
            continue
        names.append(name)
        aliases = term.get("aliases", [])
        parents = term.get("parents", [])
        related = term.get("retrieval_related", {})
        if not isinstance(aliases, list):
            problems.append(f"disease term {name!r} aliases must be an array")
        if not isinstance(parents, list):
            problems.append(f"disease term {name!r} parents must be an array")
        if not isinstance(related, dict):
            problems.append(f"disease term {name!r} retrieval_related must be an object")

    if len(names) != len(set(names)):
        problems.append("disease vocabulary contains duplicate canonical term names")
    if not isinstance(_CASE_MAJOR_CATEGORY_MAP, dict) or not CASE_MAJOR_CATEGORIES:
        problems.append("case_major_categories must be a non-empty object")
    for category, diseases in CASE_MAJOR_CATEGORY_DISEASES.items():
        if not isinstance(category, str) or not category.strip():
            problems.append("case_major_categories keys must be non-empty strings")
        if not isinstance(diseases, list):
            problems.append(f"case_major_categories[{category!r}] must be an array")
            continue
        if len(diseases) != len(set(diseases)):
            problems.append(f"case_major_categories[{category!r}] contains duplicate diseases")
        for disease in diseases:
            if disease not in DISEASE_SET:
                problems.append(
                    f"case_major_categories[{category!r}] contains non-canonical disease {disease!r}"
                )

    normalized_aliases = set()
    canonical_casefold = {disease.casefold() for disease in DISEASES}
    for term in TERMS:
        if not isinstance(term, dict) or not isinstance(term.get("name"), str):
            continue
        target = term["name"]
        aliases = term.get("aliases", [])
        if not isinstance(aliases, list):
            continue
        for alias in aliases:
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

    for disease, categories in TERM_CASE_MAJOR_CATEGORIES.items():
        if not categories:
            problems.append(f"disease term {disease!r} has no case_major_categories")
            continue
        if len(categories) != len(set(categories)):
            problems.append(f"disease term {disease!r} case_major_categories contains duplicates")
        for category in categories:
            if category not in CASE_MAJOR_CATEGORY_SET:
                problems.append(
                    f"disease term {disease!r} case_major_category {category!r} is not allowed"
                )

    overlap = DISEASE_SET & CASE_ONLY_DISEASE_SET
    if overlap:
        problems.append(
            "case-only diseases overlap evidence-card diseases: " + ", ".join(sorted(overlap))
        )
    for disease in CASE_ONLY_DISEASES:
        if disease not in CASE_ONLY_USAGE:
            problems.append(f"case-only disease {disease!r} has no usage rule")
        if disease not in CASE_MAJOR_CATEGORY_SET:
            problems.append(
                f"case-only disease {disease!r} must also be an allowed case_major_category"
            )
    for disease in CASE_ONLY_USAGE:
        if disease not in CASE_ONLY_DISEASE_SET:
            problems.append(f"case-only usage rule {disease!r} has no case-only disease")

    for term, parents in UMBRELLA.items():
        if len(parents) != len(set(parents)):
            problems.append(f"disease term {term!r} parents contains duplicates")
        for parent in parents:
            if parent not in DISEASE_SET:
                problems.append(
                    f"disease term {term!r} parent {parent!r} is not in the vocabulary"
                )
            if parent == term:
                problems.append(f"disease term {term!r} cannot be its own parent")
    for disease in UMBRELLA:
        try:
            disease_ancestors([disease])
        except ValueError as exc:
            problems.append(str(exc))

    for disease, categories in RETRIEVAL_RELATED.items():
        for category, targets in categories.items():
            if category not in DISEASE_NAMING_EXPECTED:
                problems.append(
                    f"retrieval_related[{disease!r}] category {category!r} is not disease-filtered"
                )
            if not isinstance(targets, list):
                problems.append(
                    f"retrieval_related[{disease!r}][{category!r}] must be an array"
                )
                continue
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
        f"{len(SOURCE_DISEASE_ALIASES)} source aliases, "
        f"{len(CASE_MAJOR_CATEGORIES)} case-major categories, "
        f"{len(CASE_ONLY_DISEASES)} case-only diseases, {len(CATEGORIES)} categories, "
        f"{len(EVIDENCE_TIERS)} evidence tiers, {relation_count} retrieval relations"
    )
