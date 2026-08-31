"""Deterministic prognosis report aggregation for proforma-v1.

The prognosis owner artifact remains variant-centric through evidence matching and
semantic audit.  This module runs only after evidence resolution, collapsing the
surviving evidence-backed propositions into report-sized clinical units.

No clinical inference is performed here:
- framework effects are grouped only by exact framework name + effect direction;
- multiple variants of one gene collapse to gene-level report scope;
- an ``other_evidence`` proposition is suppressed as a redundant framework
  restatement only when it shares accepted card evidence with a same-gene,
  same-direction framework proposition;
- otherwise independent prognosis propositions remain separate.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Iterable


_FRAMEWORK_EFFECT = {
    "framework_favorable": "favorable",
    "framework_adverse": "adverse",
    "framework_neutral": "neutral",
}
_OTHER_EFFECT = {
    "other_evidence_favorable": "favorable",
    "other_evidence_adverse": "adverse",
    "other_evidence_neutral": "neutral",
}
_EFFECT_WORD = {
    "favorable": "favorable",
    "adverse": "adverse",
    "neutral": "neutral",
}


def _ordered_unique(values: Iterable[str]) -> list[str]:
    out = []
    for value in values:
        if value and value not in out:
            out.append(value)
    return out


def _genes(registry: dict, variants: Iterable[str]) -> list[str]:
    genes = []
    for variant in variants or []:
        gene = (registry.get(variant) or {}).get("gene")
        if gene and gene not in genes:
            genes.append(gene)
    return genes


def _gene_subject(genes: Iterable[str]) -> str:
    genes = sorted(set(genes or []))
    if not genes:
        return "The molecular findings"
    if len(genes) == 1:
        return f"{genes[0]} mutation"
    if len(genes) == 2:
        return f"{genes[0]} and {genes[1]} mutations"
    return f"{', '.join(genes[:-1])}, and {genes[-1]} mutations"


def _card_tags(element: dict) -> list[str]:
    return _ordered_unique(
        evidence.get("card_tag")
        for evidence in (element.get("evidence") or [])
        if isinstance(evidence, dict)
    )


def _framework_name(element: dict) -> str | None:
    source = element.get("source") or {}
    if element.get("bucket") == "prognostic_framework":
        return source.get("name")
    return source.get("framework")


def _framework_summary_reason(disease: str, framework: str, tier: str | None, groups: list[dict]) -> str:
    clauses = []
    for group in groups:
        genes = group.get("genes") or []
        subject = _gene_subject(genes)
        verb = "confers" if len(set(genes)) == 1 else "confer"
        effect = _EFFECT_WORD[group["effect"]]
        clauses.append(f"{subject} {verb} {effect} prognosis in {disease} as per the {framework} prognostic framework")
    if tier is not None:
        prefix = f"The {framework} prognostic framework assigns a {tier} tier in {disease}"
        if clauses:
            return prefix + "; " + "; ".join(clauses) + "."
        return prefix + "."
    if clauses:
        return "; ".join(clauses) + "."
    return f"{framework} is an applicable prognostic framework for {disease}."


def _component_from_other(element: dict, registry: dict) -> dict:
    variants = list(element.get("variants") or [])
    return {
        "role": "other_prognostic_evidence",
        "effect": _OTHER_EFFECT[element["bucket"]],
        "reason": element.get("reason"),
        "variants": variants,
        "genes": _genes(registry, variants),
        "source": dict(element.get("source") or {}),
        "card_tags": _card_tags(element),
        "source_schema_ids": [element["schema_id"]],
    }


def aggregate(elements: list[dict], diagnosis: dict, registry: dict) -> tuple[list[dict], dict]:
    """Return ``(prognosis_blocks, trace)`` from evidence-resolved elements.

    ``elements`` must be the post-audit reportable elements.  Unsupported
    optional prognosis propositions should already have been removed upstream.
    """
    prognosis = [el for el in elements if el.get("domain") == "prognosis"]
    disease = str(((diagnosis.get("who5") or {}).get("schema_disease") or "the authoritative disease"))
    if not prognosis:
        return [], {
            "applicable_disease": disease,
            "framework_groups": [],
            "suppressed": [],
            "retained_other": [],
        }

    framework_headers: dict[str, list[dict]] = defaultdict(list)
    framework_effects: dict[tuple[str, str], list[dict]] = defaultdict(list)
    other_elements: list[dict] = []

    for element in prognosis:
        bucket = element.get("bucket")
        if bucket == "prognostic_framework":
            name = _framework_name(element)
            if name:
                framework_headers[name].append(element)
        elif bucket in _FRAMEWORK_EFFECT:
            name = _framework_name(element)
            if name:
                framework_effects[(name, _FRAMEWORK_EFFECT[bucket])].append(element)
        elif bucket in _OTHER_EFFECT:
            other_elements.append(element)
        else:
            raise ValueError(
                f"unsupported evidence-resolved prognosis bucket {bucket!r} in {element.get('schema_id')!r}"
            )

    framework_names = _ordered_unique(
        list(framework_headers)
        + [name for name, _effect in framework_effects]
    )

    blocks: list[dict] = []
    trace_frameworks = []
    # Used only for exact, deterministic redundancy suppression of other evidence.
    framework_gene_evidence: dict[tuple[str, str], set[str]] = defaultdict(set)

    for index, framework in enumerate(framework_names, 1):
        header_rows = list(framework_headers.get(framework) or [])
        header = header_rows[0] if header_rows else None
        tier = ((header or {}).get("source") or {}).get("tier")
        effect_groups = []
        component_tags = []
        source_ids = []

        if header_rows:
            for row in header_rows:
                source_ids.append(row["schema_id"])
                component_tags.extend(_card_tags(row))

        for effect in ("adverse", "favorable", "neutral"):
            rows = framework_effects.get((framework, effect), [])
            if not rows:
                continue
            variants = _ordered_unique(v for row in rows for v in (row.get("variants") or []))
            genes = _genes(registry, variants)
            tags = _ordered_unique(tag for row in rows for tag in _card_tags(row))
            ids = [row["schema_id"] for row in rows]
            effect_groups.append({
                "effect": effect,
                "genes": sorted(genes),
                "variants": variants,
                "card_tags": tags,
                "source_schema_ids": ids,
            })
            component_tags.extend(tags)
            source_ids.extend(ids)
            for row in rows:
                row_tags = set(_card_tags(row))
                for gene in _genes(registry, row.get("variants") or []):
                    framework_gene_evidence[(gene, effect)].update(row_tags)

        reason = _framework_summary_reason(disease, framework, tier, effect_groups)
        component = {
            "role": "prognostic_framework_summary",
            "disease": disease,
            "framework": framework,
            "tier": tier,
            "effect_groups": effect_groups,
            "reason": reason,
            "variants": _ordered_unique(v for group in effect_groups for v in group["variants"]),
            "genes": sorted(set(g for group in effect_groups for g in group["genes"])),
            "card_tags": _ordered_unique(component_tags),
            "source_schema_ids": _ordered_unique(source_ids),
        }
        blocks.append({
            "block_id": f"PX-FRAMEWORK-{index:02d}",
            "domain": "prognosis",
            "kind": "framework_summary",
            "components": [component],
        })
        trace_frameworks.append({
            "framework": framework,
            "tier": tier,
            "effect_groups": deepcopy(effect_groups),
            "source_schema_ids": list(component["source_schema_ids"]),
            "card_tags": list(component["card_tags"]),
        })

    suppressed = []
    retained_other = []
    other_index = 0
    for element in other_elements:
        effect = _OTHER_EFFECT[element["bucket"]]
        genes = _genes(registry, element.get("variants") or [])
        tags = set(_card_tags(element))
        fully_covered_genes = []
        for gene in genes:
            framework_tags = framework_gene_evidence.get((gene, effect), set())
            if tags and tags.issubset(framework_tags):
                fully_covered_genes.append(gene)

        # Suppress only when the complete proposition scope is covered by a
        # same-direction framework proposition and *all* accepted cards for the
        # other-evidence proposition are already accepted for that framework
        # effect.  Any additional accepted card keeps the proposition independent.
        # Partial gene overlap is also retained to avoid rewriting free text.
        if genes and set(fully_covered_genes) == set(genes):
            suppressed.append({
                "schema_id": element["schema_id"],
                "reason": "redundant_framework_restatement",
                "effect": effect,
                "genes": genes,
                "card_tags": sorted(tags),
            })
            continue

        other_index += 1
        component = _component_from_other(element, registry)
        blocks.append({
            "block_id": f"PX-OTHER-{other_index:02d}",
            "domain": "prognosis",
            "kind": "other_evidence",
            "components": [component],
        })
        retained_other.append({
            "schema_id": element["schema_id"],
            "effect": effect,
            "genes": component["genes"],
            "variants": component["variants"],
            "card_tags": component["card_tags"],
        })

    input_ids = {el["schema_id"] for el in prognosis}
    represented_ids = set()
    for row in trace_frameworks:
        represented_ids.update(row.get("source_schema_ids") or [])
    represented_ids.update(row["schema_id"] for row in suppressed)
    represented_ids.update(row["schema_id"] for row in retained_other)
    if represented_ids != input_ids:
        missing = sorted(input_ids - represented_ids)
        extra = sorted(represented_ids - input_ids)
        raise ValueError(
            "prognosis report aggregation provenance mismatch: "
            f"missing={missing or []}, extra={extra or []}"
        )

    trace = {
        "applicable_disease": disease,
        "framework_groups": trace_frameworks,
        "suppressed": suppressed,
        "retained_other": retained_other,
    }
    return blocks, trace
