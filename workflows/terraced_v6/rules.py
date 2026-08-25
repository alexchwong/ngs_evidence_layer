"""Named relational rules referenced from terraced-v6 stage assets.

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
from workflows.terraced_v6 import issues as iss


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


def references_exist(doc, context, params):
    """Each row's value must be one of that row's own supplied candidates."""
    rows = _field(doc, params["field"])
    by_id = {row["evidence_id"]: row for row in context.get("items") or []}
    out = []
    for i, row in enumerate(rows if isinstance(rows, list) else []):
        if not isinstance(row, dict):
            continue
        item = by_id.get(row.get("evidence_id"))
        if item is None or row.get(params["value_field"]) is None:
            continue
        out += iss.enum_field(
            row.get(params["value_field"]),
            item.get(params["source"]) or [],
            f"{params['field']}[{i}].{params['value_field']}",
            label="candidate card tag" if params["value_field"] == "card_tag" else "candidate card",
        )
    return out



def null_evidence_match_contract(doc, context, params):
    """A no-support match must leave card/source/quote all null."""
    out = []
    for i, row in enumerate(doc.get("matches") or []):
        if not isinstance(row, dict) or row.get("card_tag") is not None:
            continue
        if row.get("source") is not None or row.get("quote") is not None:
            out.append(
                ValidationIssue(
                    f"matches[{i}]",
                    "card_tag is null but source/quote are populated",
                    "when declaring no citation support, return card_tag: null, source: null and quote: null",
                    repair_class="content",
                    received=f"source={iss.preview(row.get('source'))} quote={iss.preview(row.get('quote'))}",
                    expected="card_tag/source/quote all null",
                )
            )
    return out


def audit_feedback_when_needed(doc, context, params):
    """Failed/warning audits must explain why, because matcher retries consume it."""
    out = []
    for i, row in enumerate(doc.get("audits") or []):
        if not isinstance(row, dict):
            continue
        needs = row.get("quote_supports_statement") is False or row.get("quote_supports_reason") is False or row.get("risk") == "warning"
        comments = row.get("comments")
        if needs and isinstance(comments, list) and not any(isinstance(x, str) and x.strip() for x in comments):
            out.append(
                ValidationIssue(
                    f"audits[{i}].comments",
                    "support failed or a warning was raised without explanatory feedback",
                    "state concisely why the selected card is inappropriate or what the warning is, so the next matcher can choose better evidence",
                    repair_class="content",
                    received=iss.preview(comments),
                    expected="one or more actionable audit comments",
                )
            )
    return out

def exclusive_with(doc, context, params):
    """A variant in a solitary bucket must not appear in any other bucket."""
    rows = _field(doc, params["field"])
    solitary = params.get("buckets") or context.get("__spec_solitary_buckets") or []
    seen = {}
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and isinstance(row.get(params["id_field"]), str):
            seen.setdefault(row[params["id_field"]], []).append(row.get("bucket"))
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


def prognostic_score_not_null_excuse(doc, context, params):
    score = doc.get("prognostic_score")
    if not isinstance(score, dict):
        return []
    out = list(iss.exact_keys(score, {"name", "result", "reason"}, "prognostic_score"))
    for key in ("name", "result", "reason"):
        out += iss.text_field(score.get(key), f"prognostic_score.{key}")
    combined = " ".join(str(score.get(k)) for k in ("name", "result", "reason"))
    if _NOT_CALCULABLE.search(combined):
        out.append(
            ValidationIssue(
                "prognostic_score",
                "reports an inability to calculate a score",
                "use null instead; do not report that a score could not be calculated",
                repair_class="content",
                received=iss.preview(combined),
                expected="null",
            )
        )
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
    "references_exist": references_exist,
    "null_evidence_match_contract": null_evidence_match_contract,
    "audit_feedback_when_needed": audit_feedback_when_needed,
    "exclusive_with": exclusive_with,
    "prognostic_score_not_null_excuse": prognostic_score_not_null_excuse,
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
