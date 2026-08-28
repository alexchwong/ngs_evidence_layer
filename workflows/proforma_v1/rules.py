"""Named relational rules referenced from proforma-v1 stage assets.

JSON Schema covers structure. These cover the constraints it cannot express:
relationships between a returned artifact and *runtime* data — the variant
registry, the supplied evidence item IDs, the deterministic block list.

Each rule is a function `(doc, context, params) -> list[ValidationIssue]`.
A stage asset names it and supplies parameters; nothing is executed that is not
in `REGISTRY`, and `stage_spec` refuses to load an asset naming an unknown rule.

The same `one_row_per_id` implementation now serves seven stages. That is the
point: identical defects should produce identical feedback wherever they occur.
"""
from __future__ import annotations

import re

from scripts.core.validated_model_task import ValidationIssue
from workflows.proforma_v1 import issues as iss


def _field(doc, path: str):
    """Resolve a shallow field path: 'a', 'a[]', 'a[].b'."""
    cur = doc
    for part in path.replace("[]", "").split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _source(context, name: str):
    """Resolve a named runtime source from the stage context."""
    if name == "registry":
        return sorted(context.get("variants") or [])
    if name == "items":
        return [row["evidence_id"] for row in context.get("items") or []]
    if name == "blocks":
        return list(context.get("blocks") or [])
    return list(context.get(name) or [])


# --- rules -------------------------------------------------------------------

def one_row_per_id(doc, context, params):
    return iss.one_row_per_id(
        _field(doc, params["field"]),
        _source(context, params["source"]),
        id_field=params["id_field"],
        path=params["field"],
    )


def rows_per_id(doc, context, params):
    """At least N rows per supplied ID; used where a variant may repeat."""
    rows = _field(doc, params["field"])
    expected = _source(context, params["source"])
    minimum = int(params.get("minimum", 1))
    if not isinstance(rows, list):
        return iss.one_row_per_id(rows, expected, id_field=params["id_field"], path=params["field"])
    seen = {}
    out = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            out.append(
                ValidationIssue(
                    f"{params['field']}[{i}]",
                    f"expected a mapping; received {iss.type_name(row)}",
                    "return one mapping per row",
                    repair_class="content",
                    received=iss.preview(row),
                )
            )
            continue
        vid = row.get(params["id_field"])
        if not isinstance(vid, str) or vid not in expected:
            out.append(
                ValidationIssue(
                    f"{params['field']}[{i}].{params['id_field']}",
                    f"{iss.preview(vid)!r} is not a supplied ID",
                    f"use one of the supplied IDs {expected}",
                    repair_class="content",
                    received=iss.preview(vid),
                    expected=str(expected),
                )
            )
            continue
        seen[vid] = seen.get(vid, 0) + 1
    short = [v for v in expected if seen.get(v, 0) < minimum]
    if short:
        out.append(
            ValidationIssue(
                params["field"],
                f"fewer than {minimum} row(s) for {short}",
                f"return at least {minimum} row for every supplied {params['id_field']}",
                repair_class="content",
                received=f"rows for {sorted(seen)}",
                expected=str(expected),
            )
        )
    return out


def enum(doc, context, params):
    allowed = context.get(params.get("values_from") or "") or params.get("values") or []
    label = params.get("label", "value")
    path = params["field"]
    if path.endswith("[]"):
        values = _field(doc, path) or []
        out = []
        for i, value in enumerate(values if isinstance(values, list) else []):
            out += iss.enum_field(value, allowed, f"{path[:-2]}[{i}]", label=label)
        return out
    if "[]." in path:
        head, tail = path.split("[].", 1)
        rows = _field(doc, head) or []
        out = []
        for i, row in enumerate(rows if isinstance(rows, list) else []):
            if isinstance(row, dict):
                out += iss.enum_field(row.get(tail), allowed, f"{head}[{i}].{tail}", label=label)
        return out
    return iss.enum_field(_field(doc, path), allowed, path, label=label)


def id_subset(doc, context, params):
    _, found = iss.id_list(
        _field(doc, params["field"]), params["field"], set(_source(context, params["source"])), allow_empty=True
    )
    return found


def evidence_match_tags_exist(doc, context, params):
    """Every selected tag must come from that evidence item's candidates."""
    by_id = {row["evidence_id"]: row for row in context.get("items") or []}
    out = []
    for i, row in enumerate(doc.get("matches") or []):
        if not isinstance(row, dict):
            continue
        item = by_id.get(row.get("evidence_id"))
        if item is None:
            continue
        for j, tag in enumerate(row.get("card_tags") or []):
            allowed = item.get("candidate_card_tags") or []
            if tag not in allowed:
                out.append(
                    ValidationIssue(
                        f"matches[{i}].card_tags[{j}]",
                        f"{tag!r} was not supplied as a candidate for {row.get('evidence_id')}",
                        f"remove this tag from {row.get('evidence_id')} and preserve otherwise valid selections; select only exact tags supplied under this evidence item",
                        repair_class="content",
                        received=iss.preview(tag),
                        expected=f"one of this item's {len(allowed)} supplied candidate tag(s)",
                    )
                )
    return out


def evidence_audit_cards_exact(doc, context, params):
    """Audit exactly the selected card tags once for each evidence item."""
    by_id = {row["evidence_id"]: row for row in context.get("items") or []}
    out = []
    for i, row in enumerate(doc.get("audits") or []):
        if not isinstance(row, dict):
            continue
        item = by_id.get(row.get("evidence_id"))
        if item is None:
            continue
        expected = list(item.get("selected_card_tags") or [])
        audits = row.get("card_audits")
        if not isinstance(audits, list):
            continue
        seen = [x.get("card_tag") for x in audits if isinstance(x, dict)]
        missing = [x for x in expected if x not in seen]
        unexpected = [x for x in seen if x not in expected]
        duplicates = sorted({x for x in seen if x is not None and seen.count(x) > 1})
        if missing or unexpected or duplicates:
            parts = []
            if missing: parts.append(f"missing {missing}")
            if unexpected: parts.append(f"unexpected {unexpected}")
            if duplicates: parts.append(f"duplicate {duplicates}")
            out.append(
                ValidationIssue(
                    f"audits[{i}].card_audits",
                    "; ".join(parts),
                    "return exactly one card audit for every selected card tag and no others",
                    repair_class="content",
                    received=f"card tags {seen}",
                    expected=f"card tags {expected}",
                )
            )
    return out

def audit_feedback_when_needed(doc, context, params):
    """Failed/warning card audits must explain why for matcher retries."""
    out = []
    for i, row in enumerate(doc.get("audits") or []):
        if not isinstance(row, dict):
            continue
        for j, audit in enumerate(row.get("card_audits") or []):
            if not isinstance(audit, dict):
                continue
            needs = audit.get("card_is_element_of_reason") is False or audit.get("risk") == "warning"
            comments = audit.get("comments")
            if needs and isinstance(comments, list) and not any(isinstance(x, str) and x.strip() for x in comments):
                out.append(
                    ValidationIssue(
                        f"audits[{i}].card_audits[{j}].comments",
                        "card/reason membership failed or a warning was raised without explanatory feedback",
                        "state concisely why the card is not an element of the reason or what the warning is, so the next matcher can choose better evidence",
                        repair_class="content",
                        received=iss.preview(comments),
                        expected="one or more actionable audit comments",
                    )
                )
    return out

def exclusive_with(doc, context, params):
    """A variant in a solitary category must not appear in any other category."""
    rows = _field(doc, params["field"])
    solitary = params.get("buckets") or context.get("__spec_solitary_buckets") or []
    category_field = params.get("category_field", "bucket")
    seen = {}
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and isinstance(row.get(params["id_field"]), str):
            seen.setdefault(row[params["id_field"]], []).append(row.get(category_field))
    out = []
    for bucket in solitary:
        for vid, buckets in seen.items():
            others = sorted({b for b in buckets if b != bucket})
            if bucket in buckets and others:
                out.append(
                    ValidationIssue(
                        params["field"],
                        f"{vid} appears in {bucket} and also in {others}",
                        f"a variant in {bucket} must not appear in any other bucket; "
                        f"remove either the {bucket} row or the other row(s)",
                        repair_class="content",
                        received=f"{vid}: {buckets}",
                        expected=f"{vid} in {bucket} alone, or not in {bucket} at all",
                    )
                )
    for vid, buckets in seen.items():
        dupes = sorted({b for b in buckets if buckets.count(b) > 1})
        if dupes:
            out.append(
                ValidationIssue(
                    params["field"],
                    f"{vid} has more than one row in bucket(s) {dupes}",
                    "merge them into one row, or use a different bucket for the distinct implication",
                    repair_class="content",
                    received=f"{vid}: {buckets}",
                )
            )
    return out


_NOT_CALCULABLE = re.compile(
    r"not\s+calculable|cannot\s+be\s+calculated|unable\s+to\s+calculate|insufficient.*(?:score|calculate)",
    re.I,
)


def applicable_disease_exact(doc, context, params):
    """The PTB owner artifact is anchored to the authoritative WHO5 disease."""
    expected = context.get("authoritative_disease")
    if not expected or doc.get("applicable_disease") == expected:
        return []
    return [
        ValidationIssue(
            "applicable_disease",
            f"does not match the authoritative WHO5 disease {expected!r}",
            f"use exactly {expected!r}; disease identity is supplied context, not a model decision",
            repair_class="content",
            received=iss.preview(doc.get("applicable_disease")),
            expected=expected,
        )
    ]


def gene_matches_registry(doc, context, params):
    """Verify the deterministically injected gene against the canonical variant registry."""
    registry = context.get("registry") or {}
    out = []
    for i, row in enumerate(doc.get("classification") or []):
        if not isinstance(row, dict):
            continue
        vid = row.get("variant")
        canonical = (registry.get(vid) or {}).get("gene") if isinstance(registry, dict) else None
        if canonical and row.get("gene") != canonical:
            out.append(
                ValidationIssue(
                    f"classification[{i}].gene",
                    f"does not match canonical gene {canonical!r} for {vid}",
                    f"use exactly {canonical!r}",
                    repair_class="content",
                    received=iss.preview(row.get("gene")),
                    expected=canonical,
                )
            )
    return out


def prognosis_contract(doc, context, params):
    """Relational rules for model-selected prognosis frameworks and variant effects."""
    out = []
    frameworks = doc.get("prognostic_frameworks") or []
    names = []
    for i, framework in enumerate(frameworks if isinstance(frameworks, list) else []):
        if not isinstance(framework, dict):
            continue
        name = framework.get("name")
        if isinstance(name, str):
            if name in names:
                out.append(ValidationIssue(
                    f"prognostic_frameworks[{i}].name",
                    f"duplicates prognostic framework {name!r}",
                    "list each applicable prognostic framework once",
                    repair_class="content", received=name, expected="unique framework name",
                ))
            names.append(name)
        combined = " ".join(str(framework.get(k) or "") for k in ("tier", "reason"))
        if _NOT_CALCULABLE.search(combined):
            out.append(ValidationIssue(
                f"prognostic_frameworks[{i}].tier",
                "reports an inability to calculate/assign the framework tier",
                "use tier: null instead; identifying a framework does not require assigning its tier",
                repair_class="content", received=iss.preview(framework.get("tier")), expected="string | null",
            ))
    allowed_names = set(names)
    for i, row in enumerate(doc.get("classification") or []):
        if not isinstance(row, dict):
            continue
        seen = set()
        effects = []
        for j, fx in enumerate(row.get("framework_effects") or []):
            if not isinstance(fx, dict):
                continue
            framework = fx.get("framework")
            if framework not in allowed_names:
                out.append(ValidationIssue(
                    f"classification[{i}].framework_effects[{j}].framework",
                    "does not name one of this artifact's selected prognostic frameworks",
                    "copy the exact framework name from prognostic_frameworks, or remove this framework-effect row",
                    repair_class="content", received=iss.preview(framework), expected=str(names),
                ))
            if framework in seen:
                out.append(ValidationIssue(
                    f"classification[{i}].framework_effects[{j}].framework",
                    f"duplicates framework {framework!r} for this variant",
                    "return at most one effect for this variant under each named framework",
                    repair_class="content", received=iss.preview(framework), expected="unique framework per variant",
                ))
            seen.add(framework)
            effects.append(fx.get("effect"))
        other = row.get("other_evidence_effect")
        other_reason = row.get("other_evidence_reason")
        # ``no_evidence`` is a non-reportable state. Runtime normalization owns
        # removal of any redundant model-supplied reason, so validation should
        # not spend a model retry on form hygiene that Python can resolve.
        if other != "no_evidence" and (not isinstance(other_reason, str) or not other_reason.strip()):
            out.append(ValidationIssue(
                f"classification[{i}].other_evidence_reason",
                "is missing despite a positive/neutral other-evidence classification",
                "give one concise same-disease prognostic proposition",
                repair_class="content", received=iss.preview(other_reason), expected="non-empty string",
            ))
        # Framework-specific and independent literature evidence are separate
        # evidence channels and may legitimately point in different directions.
        # Deterministic validation therefore does not force concordance between
        # them; evidence review decides whether each proposition is supported.
    return out

def issue_null_when_preserved(doc, context, params):
    out = []
    for i, row in enumerate(doc.get("audits") or []):
        if not isinstance(row, dict):
            continue
        if row.get("preserved") is True and row.get("issue") is not None:
            out.append(
                ValidationIssue(
                    f"audits[{i}].issue",
                    "populated even though preserved is true",
                    "use null for issue when preserved is true",
                    repair_class="content",
                    received=iss.preview(row.get("issue")),
                    expected="null",
                )
            )
        elif row.get("preserved") is False:
            out += iss.text_field(row.get("issue"), f"audits[{i}].issue")
    return out


def null_diagnosis_contract(doc, context, params):
    if doc.get("diagnosis") is not None:
        return []
    if doc.get("variants") in ([], None) and doc.get("reason") is None:
        return []
    return [
        ValidationIssue(
            "second diagnosis",
            "diagnosis is null but variants/reason are populated",
            "when there is no independent concurrent diagnosis, return diagnosis: null, "
            "variants: [] and reason: null",
            repair_class="content",
            received=f"variants={iss.preview(doc.get('variants'))} reason={iss.preview(doc.get('reason'))}",
            expected="variants: [] and reason: null",
        )
    ]


def sequential_ids(doc, context, params):
    rows = _field(doc, params["field"])
    prefix = params["prefix"]
    out = []
    for i, row in enumerate(rows if isinstance(rows, list) else [], 1):
        if not isinstance(row, dict):
            continue
        want = f"{prefix}{i}"
        if row.get(params["id_field"]) != want:
            out.append(
                ValidationIssue(
                    f"{params['field']}[{i-1}].{params['id_field']}",
                    f"received {iss.preview(row.get(params['id_field']))!r}",
                    f"use the sequential stable ID {want}",
                    repair_class="content",
                    received=iss.preview(row.get(params["id_field"])),
                    expected=want,
                )
            )
    return out


def gene_prefixed_descriptions(doc, context, params):
    if not context.get("require_gene_prefix"):
        return []
    out = []
    for i, row in enumerate(doc.get("variants") or []):
        if not isinstance(row, dict):
            continue
        gene, desc = row.get("gene"), row.get("description")
        uppercase_ok = isinstance(gene, str) and bool(gene) and gene == gene.upper()
        # Only ask for the prefix once the symbol itself is right, otherwise the
        # two issues give the model contradictory instructions in the same turn.
        if uppercase_ok and gene.strip() and isinstance(desc, str) and desc.strip():
            if not desc.strip().startswith(gene.strip()):
                out.append(
                    ValidationIssue(
                        f"variants[{i}].description",
                        f"does not begin with the gene symbol {gene!r}",
                        f"prefix the unchanged variant description with the exact gene {gene!r}",
                        repair_class="content",
                        received=iss.preview(desc),
                        expected=f"{gene} + the complete reported variant description",
                    )
                )
        if isinstance(gene, str) and gene and gene != gene.upper():
            out.append(
                ValidationIssue(
                    f"variants[{i}].gene",
                    f"gene symbol {gene!r} is not uppercase",
                    "use the uppercase reported gene symbol",
                    repair_class="content",
                    received=gene,
                    expected=gene.upper(),
                )
            )
    return out


def single_physical_line(doc, context, params):
    value = _field(doc, params["field"])
    if not isinstance(value, str) or ("\n" not in value and value == value.strip()):
        return []
    return [
        ValidationIssue(
            params["field"],
            "must be one clean physical line",
            "reserialize the same text on one physical line without changing its words",
            repair_class="serialization",
            received=iss.preview(value),
            expected="one physical-line string",
        )
    ]


REGISTRY = {
    "one_row_per_id": one_row_per_id,
    "rows_per_id": rows_per_id,
    "enum": enum,
    "id_subset": id_subset,
    "evidence_match_tags_exist": evidence_match_tags_exist,
    "evidence_audit_cards_exact": evidence_audit_cards_exact,
    "audit_feedback_when_needed": audit_feedback_when_needed,
    "exclusive_with": exclusive_with,
    "applicable_disease_exact": applicable_disease_exact,
    "gene_matches_registry": gene_matches_registry,
    "prognosis_contract": prognosis_contract,
    "issue_null_when_preserved": issue_null_when_preserved,
    "null_diagnosis_contract": null_diagnosis_contract,
    "sequential_ids": sequential_ids,
    "gene_prefixed_descriptions": gene_prefixed_descriptions,
    "single_physical_line": single_physical_line,
}


def apply(spec, doc, context) -> list[ValidationIssue]:
    """Run every rule a stage asset declares, in asset order."""
    enriched = dict(context or {})
    enriched.setdefault("__spec_solitary_buckets", list(spec.solitary_buckets))
    out: list[ValidationIssue] = []
    for rule in spec.rules:
        params = {k: v for k, v in rule.items() if k != "rule"}
        if "values_from" in params and params["values_from"] == "buckets":
            enriched["buckets"] = list(spec.buckets)
        out += REGISTRY[rule["rule"]](doc, enriched, params)
    return out
