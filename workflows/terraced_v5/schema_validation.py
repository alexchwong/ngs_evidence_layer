"""Deterministic structural validators for terraced-v5 prototype proformas.

These validators deliberately avoid clinical-semantic judgments.  They collect
*all* detectable structural defects in one pass.  Representation-only defects
that can be repaired without changing informational content are tagged
``repair_class='serialization'`` so the generic syntax-only repair path can fix
those before the originating clinical task is asked to reconsider anything.
"""
from __future__ import annotations

from typing import Any
import re
import yaml

from scripts.core.validated_model_task import ValidationIssue, fail


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "mapping"
    if isinstance(value, list):
        return "list"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return type(value).__name__


def _preview(value: Any, limit: int = 180) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _scalar_like(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _single_scalar_mapping(value: Any) -> bool:
    """True only for a mapping that can losslessly be reserialized as one scalar.

    The common YAML failure is an unquoted ``": "`` inside prose, which parses
    one intended string as ``{left: right}``.  Larger/nested mappings are real
    schema choices and must go back to the originating task rather than the
    syntax-only model.
    """
    if not isinstance(value, dict) or len(value) != 1:
        return False
    key, val = next(iter(value.items()))
    return _scalar_like(key) and _scalar_like(val)


def _list_item_kind(item_hint: str) -> str:
    hint = item_hint.lower()
    if "mapping" in hint or "object" in hint:
        return "mapping"
    if "string" in hint or "id" in hint:
        return "string"
    return "unknown"


def _boolean_serialization_only(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower() in {"true", "false", "yes", "no"}


def _doc(text: str, context: str, issues: list[ValidationIssue]) -> dict:
    try:
        value = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        # Parser failures normally never reach this validator because the shared
        # syntax-repair module runs first, but keep the diagnostic actionable.
        issues.append(
            ValidationIssue(
                context,
                f"YAML parser error: {exc}",
                "repair YAML serialization only and return one top-level mapping",
                repair_class="serialization",
            )
        )
        return {}
    if not isinstance(value, dict):
        can_reserialize = isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict)
        issues.append(
            ValidationIssue(
                context,
                f"expected top-level mapping; received {_type_name(value)}",
                "remove the extra one-item list wrapper without changing any field or value" if can_reserialize else "return the required top-level mapping in the proforma shape; this value cannot be safely repaired by syntax-only reserialization",
                repair_class="serialization" if can_reserialize else "content",
                received=_preview(value),
                expected="mapping/object",
            )
        )
        return {}
    return value


def _mapping(value: Any, path: str, issues: list[ValidationIssue]) -> dict | None:
    if isinstance(value, dict):
        return value
    can_reserialize = isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict)
    issues.append(
        ValidationIssue(
            path,
            f"expected mapping; received {_type_name(value)}",
            (
                "remove the extra list wrapper so the existing single mapping is represented directly; do not change any field or value"
                if can_reserialize
                else "return the required mapping with the schema fields shown in the proforma; this cannot be repaired safely by syntax-only reserialization"
            ),
            repair_class="serialization" if can_reserialize else "content",
            received=_preview(value),
            expected="mapping/object",
        )
    )
    return None


def _list(value: Any, path: str, issues: list[ValidationIssue], *, allow_empty: bool = True, item_hint: str = "items") -> list | None:
    if isinstance(value, list):
        if not value and not allow_empty:
            issues.append(
                ValidationIssue(
                    path,
                    "list is empty",
                    f"return one or more {item_hint}",
                    repair_class="content",
                    received="[]",
                    expected=f"non-empty list of {item_hint}",
                )
            )
        return value
    kind = _list_item_kind(item_hint)
    can_reserialize = False
    if kind == "mapping" and isinstance(value, dict):
        can_reserialize = True  # one mapping with a missing list marker
    elif kind == "string" and isinstance(value, str):
        can_reserialize = True  # one scalar with a missing list marker
    elif kind == "string" and _single_scalar_mapping(value):
        can_reserialize = True  # one prose scalar split at an unquoted ': '
    issues.append(
        ValidationIssue(
            path,
            f"expected list; received {_type_name(value)}",
            (
                "repair YAML list serialization only (for example add the missing list marker/brackets) while preserving every existing scalar exactly"
                if can_reserialize
                else f"return a list of {item_hint} in the exact proforma shape; this value cannot be losslessly repaired as syntax only"
            ),
            repair_class="serialization" if can_reserialize else "content",
            received=_preview(value),
            expected=f"{'non-empty ' if not allow_empty else ''}list of {item_hint}",
        )
    )
    return None


def _exact(row: dict | None, keys: set[str], path: str, issues: list[ValidationIssue]) -> None:
    if not isinstance(row, dict):
        return
    missing = sorted(keys - set(row))
    extra = sorted(set(row) - keys)
    if missing or extra:
        parts = []
        if missing:
            parts.append(f"missing fields {missing}")
        if extra:
            parts.append(f"unexpected fields {extra}")
        issues.append(
            ValidationIssue(
                path,
                "; ".join(parts),
                f"return exactly these fields: {sorted(keys)}; preserve values of unrelated valid fields",
                repair_class="content",
                received=str(sorted(row)),
                expected=str(sorted(keys)),
            )
        )


def _text(value: Any, path: str, issues: list[ValidationIssue]) -> bool:
    if isinstance(value, str):
        if value.strip():
            return True
        issues.append(
            ValidationIssue(
                path,
                "string is blank",
                "return the required non-empty text",
                repair_class="content",
                received=repr(value),
                expected="non-empty string",
            )
        )
        return False

    # Non-null content in the wrong YAML container/scalar type is often a pure
    # serialization error.  The motivating case is an unquoted ': ' turning a
    # reason into a one-entry mapping.  The generic syntax repairer can restore
    # the intended scalar without changing any lexical content.
    if value is not None:
        hint = "quote or reserialize the existing value as one string without changing any words"
        can_reserialize = _single_scalar_mapping(value) or isinstance(value, (bool, int, float)) or (isinstance(value, list) and len(value) == 1 and isinstance(value[0], str))
        if _single_scalar_mapping(value):
            hint += "; an unquoted ': ' in a YAML scalar commonly causes this mapping parse"
        if not can_reserialize:
            hint = "return the required non-empty string; the received structured value cannot be losslessly converted by syntax-only repair"
        issues.append(
            ValidationIssue(
                path,
                f"expected non-empty string; YAML parsed {_type_name(value)} instead",
                hint,
                repair_class="serialization" if can_reserialize else "content",
                received=_preview(value),
                expected="non-empty string",
            )
        )
        return False

    issues.append(
        ValidationIssue(
            path,
            "required text is null/missing",
            "supply the required clinical text",
            repair_class="content",
            received="null",
            expected="non-empty string",
        )
    )
    return False


def _enum(value: Any, allowed: set[str], path: str, issues: list[ValidationIssue]) -> None:
    if value not in allowed:
        issues.append(
            ValidationIssue(
                path,
                f"invalid value {value!r}",
                f"use exactly one of {sorted(allowed)}",
                repair_class="content",
                received=_preview(value),
                expected=str(sorted(allowed)),
            )
        )


def _reasons(value: Any, path: str, issues: list[ValidationIssue]) -> None:
    rows = _list(value, path, issues, allow_empty=False, item_hint="reason strings")
    if rows is None:
        return
    for i, item in enumerate(rows):
        _text(item, f"{path}[{i}]", issues)


def validate_diagnosis(text: str, *, allowed_diseases: set[str]) -> str:
    issues: list[ValidationIssue] = []
    d = _doc(text, "diagnosis proforma", issues)
    _exact(d, {"who5", "icc", "concordance", "concurrent_second_diagnosis"}, "diagnosis", issues)

    who = _mapping(d.get("who5"), "who5", issues) if "who5" in d else None
    if who is not None:
        _exact(who, {"diagnoses"}, "who5", issues)
        rows = _list(who.get("diagnoses"), "who5.diagnoses", issues, allow_empty=False, item_hint="diagnosis mappings")
        if rows is not None:
            for i, raw_row in enumerate(rows):
                path = f"who5.diagnoses[{i}]"
                row = _mapping(raw_row, path, issues)
                if row is None:
                    continue
                _exact(row, {"schema_disease", "status", "diagnosis", "reasons"}, path, issues)
                disease = row.get("schema_disease")
                if disease not in allowed_diseases:
                    issues.append(
                        ValidationIssue(
                            f"{path}.schema_disease",
                            f"unknown value {disease!r}",
                            "use one exact supplied allowed schema disease",
                            repair_class="content",
                            received=_preview(disease),
                            expected=f"one of {sorted(allowed_diseases)}",
                        )
                    )
                _enum(row.get("status"), {"established", "indeterminate"}, f"{path}.status", issues)
                _text(row.get("diagnosis"), f"{path}.diagnosis", issues)
                _reasons(row.get("reasons"), f"{path}.reasons", issues)

    icc = _mapping(d.get("icc"), "icc", issues) if "icc" in d else None
    if icc is not None:
        _exact(icc, {"diagnoses"}, "icc", issues)
        rows = _list(icc.get("diagnoses"), "icc.diagnoses", issues, allow_empty=False, item_hint="diagnosis mappings")
        if rows is not None:
            for i, raw_row in enumerate(rows):
                path = f"icc.diagnoses[{i}]"
                row = _mapping(raw_row, path, issues)
                if row is None:
                    continue
                _exact(row, {"status", "diagnosis", "reasons"}, path, issues)
                _enum(row.get("status"), {"established", "indeterminate"}, f"{path}.status", issues)
                _text(row.get("diagnosis"), f"{path}.diagnosis", issues)
                _reasons(row.get("reasons"), f"{path}.reasons", issues)

    con = _mapping(d.get("concordance"), "concordance", issues) if "concordance" in d else None
    if con is not None:
        _exact(con, {"answer", "reasons"}, "concordance", issues)
        _text(con.get("answer"), "concordance.answer", issues)
        _reasons(con.get("reasons"), "concordance.reasons", issues)

    sec = _mapping(d.get("concurrent_second_diagnosis"), "concurrent_second_diagnosis", issues) if "concurrent_second_diagnosis" in d else None
    if sec is not None:
        _exact(sec, {"answer", "reasons"}, "concurrent_second_diagnosis", issues)
        _text(sec.get("answer"), "concurrent_second_diagnosis.answer", issues)
        _reasons(sec.get("reasons"), "concurrent_second_diagnosis.reasons", issues)

    fail("diagnosis proforma", issues)
    return "diagnosis proforma structurally valid"


def _variant_list(value: Any, path: str, valid: set[str], issues: list[ValidationIssue], *, allow_empty: bool = False) -> list[str]:
    rows = _list(value, path, issues, allow_empty=allow_empty, item_hint="variant IDs")
    if rows is None:
        return []

    scalar_ids: list[str] = []
    seen: set[str] = set()
    duplicates: list[str] = []
    unknown: list[Any] = []
    for i, v in enumerate(rows):
        ipath = f"{path}[{i}]"
        if not isinstance(v, str):
            if v is not None:
                issues.append(
                    ValidationIssue(
                        ipath,
                        f"variant ID must be a string; received {_type_name(v)}",
                        "use one or more bare supplied variant ID strings at this list level (for example v01, v02); do not put effect mappings, reasons, therapies, or other fields in a variant-ID list",
                        repair_class="content",
                        received=_preview(v),
                        expected=f"one of {sorted(valid)}",
                    )
                )
            else:
                issues.append(
                    ValidationIssue(
                        ipath,
                        "variant ID is null",
                        "use one exact supplied variant ID",
                        repair_class="content",
                        received="null",
                        expected=f"one of {sorted(valid)}",
                    )
                )
            continue
        scalar_ids.append(v)
        if v in seen:
            duplicates.append(v)
        seen.add(v)
        if v not in valid:
            unknown.append(v)
    if duplicates:
        issues.append(
            ValidationIssue(
                path,
                f"duplicate variant IDs {sorted(set(duplicates))}",
                "list each referenced variant once in this entry",
                repair_class="content",
            )
        )
    if unknown:
        issues.append(
            ValidationIssue(
                path,
                f"unknown variant IDs {unknown}",
                "replace each unknown ID with the intended exact supplied variant ID",
                repair_class="content",
                received=str(unknown),
                expected=str(sorted(valid)),
            )
        )
    return [v for v in scalar_ids if v in valid]


def _effect_rows(doc: dict, bucket: str, valid: set[str], issues: list[ValidationIssue], extra: set[str] | None = None) -> set[str]:
    extra = extra or set()
    if bucket not in doc:
        return set()
    rows = _list(doc.get(bucket), bucket, issues, allow_empty=True, item_hint="effect mappings")
    covered: set[str] = set()
    if rows is None:
        return covered
    for i, raw_row in enumerate(rows):
        path = f"{bucket}[{i}]"
        row = _mapping(raw_row, path, issues)
        if row is None:
            continue
        _exact(row, {"variants", "reason", *extra}, path, issues)
        # Empty placeholder rows carry no semantic content. Treat them as an
        # empty bucket; core removes them deterministically after validation.
        if row.get("variants") == [] and not str(row.get("reason") or "").strip() and all(not str(row.get(field) or "").strip() for field in extra):
            continue
        covered.update(_variant_list(row.get("variants"), f"{path}.variants", valid, issues))
        _text(row.get("reason"), f"{path}.reason", issues)
        for field in sorted(extra):
            _text(row.get(field), f"{path}.{field}", issues)
    return covered


def _coverage(valid: set[str], positive: set[str], negative: Any, name: str, issues: list[ValidationIssue]) -> None:
    neg = set(_variant_list(negative, f"{name}.no_effect", valid, issues, allow_empty=True)) if negative is not None else set()
    overlap = positive & neg
    if overlap:
        issues.append(
            ValidationIssue(
                name,
                f"variants cannot be both effect and no_effect: {sorted(overlap)}",
                "remove each listed variant from no_effect or from all effect entries according to the intended clinical decision",
                repair_class="content",
            )
        )
    missing = valid - (positive | neg)
    if missing:
        issues.append(
            ValidationIssue(
                name,
                f"variant coverage incomplete; missing {sorted(missing)}",
                "discuss every supplied variant by adding each missing ID to one or more appropriate effect entries or to no_effect",
                repair_class="content",
                expected=f"coverage of all {sorted(valid)}",
            )
        )


def validate_prognosis(text: str, valid: set[str]) -> str:
    issues: list[ValidationIssue] = []
    d = _doc(text, "prognosis", issues)
    _exact(d, {"favorable", "adverse", "other", "uncertain", "no_effect", "overall"}, "prognosis", issues)
    positive: set[str] = set()
    for bucket in ("favorable", "adverse", "other", "uncertain"):
        positive |= _effect_rows(d, bucket, valid, issues)
    _coverage(valid, positive, d.get("no_effect"), "prognosis", issues)
    overall = None
    if "overall" in d and d.get("overall") is not None:
        overall = _mapping(d.get("overall"), "overall", issues)
    if overall is not None:
        _exact(overall, {"classification", "reason"}, "overall", issues)
        classification=overall.get("classification"); reason=overall.get("reason")
        _text(classification, "overall.classification", issues)
        _text(reason, "overall.reason", issues)
        combined=f"{classification or ''} {reason or ''}"
        if re.search(r"\b(?:not\s+calculable|cannot\s+be\s+calculated|unable\s+to\s+calculate|insufficient[^.;]{0,40}\b(?:calculate|score)|missing[^.;]{0,60}\b(?:variable|parameter))\b",combined,flags=re.IGNORECASE):
            issues.append(ValidationIssue(
                "overall",
                "overall contains a score-availability/not-calculable statement",
                "set overall: null; this workflow does not report inability to calculate an overall prognostic score",
                repair_class="content",
            ))
    fail("prognosis proforma", issues)
    return "prognosis proforma structurally valid"


def validate_treatment(text: str, valid: set[str]) -> str:
    issues: list[ValidationIssue] = []
    d = _doc(text, "treatment", issues)
    _exact(d, {"drug_target", "drug_resistance", "other", "no_effect"}, "treatment", issues)
    positive = _effect_rows(d, "drug_target", valid, issues, {"therapy"})
    positive |= _effect_rows(d, "drug_resistance", valid, issues, {"therapy"})
    positive |= _effect_rows(d, "other", valid, issues)
    _coverage(valid, positive, d.get("no_effect"), "treatment", issues)
    fail("treatment proforma", issues)
    return "treatment proforma structurally valid"


def validate_biomarker(text: str, valid: set[str]) -> str:
    issues: list[ValidationIssue] = []
    d = _doc(text, "biomarker", issues)
    _exact(d, {"suitable_mrd", "unsuitable_mrd", "uncertain", "no_effect"}, "biomarker", issues)
    positive: set[str] = set()
    for bucket in ("suitable_mrd", "unsuitable_mrd", "uncertain"):
        positive |= _effect_rows(d, bucket, valid, issues)
    _coverage(valid, positive, d.get("no_effect"), "biomarker", issues)
    fail("biomarker proforma", issues)
    return "biomarker proforma structurally valid"


def validate_germline(text: str, valid: set[str]) -> str:
    issues: list[ValidationIssue] = []
    d = _doc(text, "germline", issues)
    _exact(d, {"suspect", "uncertain", "not_suspect", "clinical_support"}, "germline", issues)
    classes: dict[str, str] = {}

    for bucket in ("suspect", "uncertain"):
        if bucket not in d:
            continue
        rows = _list(d.get(bucket), bucket, issues, allow_empty=True, item_hint="germline classification mappings")
        if rows is None:
            continue
        for i, raw_row in enumerate(rows):
            path = f"{bucket}[{i}]"
            row = _mapping(raw_row, path, issues)
            if row is None:
                continue
            _exact(row, {"variants", "reason"}, path, issues)
            ids = _variant_list(row.get("variants"), f"{path}.variants", valid, issues)
            _text(row.get("reason"), f"{path}.reason", issues)
            for v in ids:
                if v in classes:
                    issues.append(
                        ValidationIssue(
                            "germline",
                            f"{v} classified more than once ({classes[v]} and {bucket})",
                            "place each variant in exactly one of suspect, uncertain, or not_suspect",
                            repair_class="content",
                        )
                    )
                else:
                    classes[v] = bucket

    not_suspect = _variant_list(d.get("not_suspect"), "not_suspect", valid, issues, allow_empty=True) if "not_suspect" in d else []
    for v in not_suspect:
        if v in classes:
            issues.append(
                ValidationIssue(
                    "germline",
                    f"{v} classified both {classes[v]} and not_suspect",
                    "place the variant in exactly one germline classification",
                    repair_class="content",
                )
            )
        else:
            classes[v] = "not_suspect"

    missing = valid - set(classes)
    if missing:
        issues.append(
            ValidationIssue(
                "germline",
                f"variant classification incomplete; missing {sorted(missing)}",
                "classify every supplied variant exactly once as suspect, uncertain, or not_suspect",
                repair_class="content",
                expected=f"classification of all {sorted(valid)}",
            )
        )

    support_rows = _list(d.get("clinical_support"), "clinical_support", issues, allow_empty=True, item_hint="clinical-support mappings") if "clinical_support" in d else []
    eligible = {v for v, cls in classes.items() if cls in {"suspect", "uncertain"}}
    seen: set[str] = set()
    if support_rows is not None:
        for i, raw_row in enumerate(support_rows):
            path = f"clinical_support[{i}]"
            row = _mapping(raw_row, path, issues)
            if row is None:
                continue
            _exact(row, {"variants", "support", "reason"}, path, issues)
            ids = _variant_list(row.get("variants"), f"{path}.variants", valid, issues)
            _enum(row.get("support"), {"present", "absent", "unknown"}, f"{path}.support", issues)
            _text(row.get("reason"), f"{path}.reason", issues)
            bad = set(ids) - eligible
            if bad:
                issues.append(
                    ValidationIssue(
                        path,
                        f"clinical_support includes non-suspect/non-uncertain variants {sorted(bad)}",
                        "assess clinical syndrome support only for variants classified suspect or uncertain",
                        repair_class="content",
                    )
                )
            seen.update(set(ids) & eligible)
    missing_support = eligible - seen
    if missing_support:
        issues.append(
            ValidationIssue(
                "clinical_support",
                f"missing suspect/uncertain variants {sorted(missing_support)}",
                "add one clinical-support assessment for every suspect or uncertain variant",
                repair_class="content",
            )
        )

    fail("germline proforma", issues)
    return "germline proforma structurally valid"


def _diagnosis_criteria(
    value: Any,
    path: str,
    issues: list[ValidationIssue],
    *,
    valid_variants: set[str] | None = None,
    case_fact_ids: set[str] | None = None,
    observed_case_fact_ids: set[str] | None = None,
    panel_genes: set[str] | None = None,
    detected_genes: set[str] | None = None,
    allowed_card_ids: set[str] | None = None,
    closed_gene_sets: dict[str, set[str]] | None = None,
) -> None:
    """Validate compact model-facing diagnostic criterion checks.

    The model emits subject IDs only.  Result status is deterministic workflow
    state and is expanded by core after this structural/semantic validation.
    """
    rows = _list(value, path, issues, allow_empty=False, item_hint="diagnostic criterion mappings")
    if rows is None:
        return
    valid_variants = set(valid_variants or set())
    case_fact_ids = set(case_fact_ids or set())
    observed_case_fact_ids = set(observed_case_fact_ids or set())
    panel_genes = set(panel_genes or set())
    detected_genes = set(detected_genes or set())
    allowed_card_ids = set(allowed_card_ids or set())
    closed_gene_sets = dict(closed_gene_sets or {})
    buckets = ("positive_supportive", "negative_supportive", "indeterminate", "not_contributory")

    for i, raw in enumerate(rows):
        cpath = f"{path}[{i}]"
        row = _mapping(raw, cpath, issues)
        if row is None:
            continue
        _exact(row, {"authority_card_id", "criterion_type", "criterion", "reason", "checks"}, cpath, issues)
        card_id = row.get("authority_card_id")
        if allowed_card_ids and card_id not in allowed_card_ids:
            issues.append(ValidationIssue(
                f"{cpath}.authority_card_id", f"unknown authority card {card_id!r}",
                "use one exact supplied authority card ID that contains this diagnostic rule",
                repair_class="content", received=_preview(card_id), expected=str(sorted(allowed_card_ids)),
            ))
        ctype = row.get("criterion_type")
        _enum(ctype, {"molecular_membership", "other"}, f"{cpath}.criterion_type", issues)
        _text(row.get("criterion"), f"{cpath}.criterion", issues)
        _text(row.get("reason"), f"{cpath}.reason", issues)
        checks = _mapping(row.get("checks"), f"{cpath}.checks", issues)
        if checks is None:
            continue
        _exact(checks, set(buckets), f"{cpath}.checks", issues)
        seen: dict[str, str] = {}
        by_bucket: dict[str, list[str]] = {b: [] for b in buckets}
        for bucket in buckets:
            vals = _list(checks.get(bucket), f"{cpath}.checks.{bucket}", issues, allow_empty=True, item_hint="subject IDs")
            if vals is None:
                continue
            for j, raw_subject in enumerate(vals):
                qpath = f"{cpath}.checks.{bucket}[{j}]"
                if not isinstance(raw_subject, str) or not raw_subject.strip():
                    issues.append(ValidationIssue(
                        qpath, f"expected compact subject string; received {_type_name(raw_subject)}",
                        "return only the subject ID/name here; core derives result_status deterministically",
                        repair_class="content", received=_preview(raw_subject), expected="subject string",
                    ))
                    continue
                subject = raw_subject.strip()
                if subject != raw_subject:
                    issues.append(ValidationIssue(
                        qpath, "subject has surrounding whitespace",
                        "return the same subject without surrounding whitespace", repair_class="serialization",
                    ))
                if subject in seen:
                    issues.append(ValidationIssue(
                        qpath, f"subject {subject!r} already appears in {seen[subject]}",
                        "classify each subject exactly once within this criterion", repair_class="content",
                    ))
                else:
                    seen[subject] = bucket
                by_bucket[bucket].append(subject)

                if subject in panel_genes and subject in detected_genes:
                    issues.append(ValidationIssue(
                        qpath, f"detected panel gene {subject!r} was referenced by gene symbol",
                        "use the supplied internal variant ID for a detected NGS positive; reserve bare gene symbols for authority-relevant unreported panel genes",
                        repair_class="content",
                    ))
                if bucket == "positive_supportive":
                    if subject in panel_genes and subject not in detected_genes:
                        issues.append(ValidationIssue(
                            qpath, f"unreported panel gene {subject!r} cannot be positive_supportive",
                            "move it only to negative_supportive when the authority card explicitly requires its negative status, otherwise omit it",
                            repair_class="content",
                        ))
                    elif subject not in valid_variants and subject not in case_fact_ids:
                        issues.append(ValidationIssue(
                            qpath, f"unsupplied subject {subject!r} cannot be positive_supportive",
                            "use a detected variant ID or supplied case-fact ID for positive support", repair_class="content",
                        ))
                elif bucket == "negative_supportive" and subject in valid_variants:
                    issues.append(ValidationIssue(
                        qpath, f"detected positive variant {subject!r} cannot be negative_supportive",
                        "use negative_supportive only for authority-relevant negative results", repair_class="content",
                    ))
                elif bucket == "indeterminate" and subject in observed_case_fact_ids:
                    issues.append(ValidationIssue(
                        qpath, f"supplied non-pending case fact {subject!r} cannot be indeterminate",
                        "the result is observed; classify its criterion contribution as positive_supportive, negative_supportive, or not_contributory according to the supplied authority rule",
                        repair_class="content",
                    ))

        if ctype == "molecular_membership":
            closed = closed_gene_sets.get(card_id or "")
            if not closed:
                issues.append(ValidationIssue(
                    f"{cpath}.criterion_type",
                    "molecular_membership requires an authority card that explicitly defines a finite qualifying gene set",
                    "use criterion_type: other unless the supplied card is marked as a closed gene set",
                    repair_class="content",
                ))
            accounted = set(seen)
            missing = valid_variants - accounted
            extras = accounted - valid_variants
            if missing:
                issues.append(ValidationIssue(
                    f"{cpath}.checks", f"molecular membership check omitted detected variants {sorted(missing)}",
                    "classify every supplied detected variant exactly once for this finite gene-set criterion",
                    repair_class="content",
                ))
            if extras:
                issues.append(ValidationIssue(
                    f"{cpath}.checks", f"molecular membership check included non-variant subjects {sorted(extras)}",
                    "for molecular_membership classify detected variant IDs only; express any separate negative dependency as its own criterion",
                    repair_class="content",
                ))


def validate_who5_diagnosis(
    text: str,
    *,
    allowed_diseases: set[str],
    valid_variants: set[str] | None = None,
    variant_genes: dict[str, str] | None = None,
    case_fact_ids: set[str] | None = None,
    observed_case_fact_ids: set[str] | None = None,
    panel_genes: set[str] | None = None,
    allowed_card_ids: set[str] | None = None,
    closed_gene_sets: dict[str, set[str]] | None = None,
) -> str:
    issues: list[ValidationIssue] = []
    d = _doc(text, "WHO5 diagnosis", issues)
    _exact(d, {"diagnoses"}, "who5", issues)
    rows = _list(d.get("diagnoses"), "diagnoses", issues, allow_empty=False, item_hint="WHO5 diagnosis mappings") if "diagnoses" in d else []
    detected_genes = set((variant_genes or {}).values())
    if rows is not None:
        for i, raw_row in enumerate(rows):
            path = f"diagnoses[{i}]"
            row = _mapping(raw_row, path, issues)
            if row is None:
                continue
            _exact(row, {"schema_disease", "status", "diagnosis", "criteria"}, path, issues)
            disease = row.get("schema_disease")
            if disease not in allowed_diseases:
                issues.append(ValidationIssue(
                    f"{path}.schema_disease", f"unknown value {disease!r}",
                    "use one exact supplied allowed schema disease", repair_class="content",
                    received=_preview(disease), expected=f"one of {sorted(allowed_diseases)}",
                ))
            _enum(row.get("status"), {"established", "conditional", "indeterminate"}, f"{path}.status", issues)
            _text(row.get("diagnosis"), f"{path}.diagnosis", issues)
            _diagnosis_criteria(
                row.get("criteria"), f"{path}.criteria", issues,
                valid_variants=valid_variants, case_fact_ids=case_fact_ids, observed_case_fact_ids=observed_case_fact_ids, panel_genes=panel_genes,
                detected_genes=detected_genes, allowed_card_ids=allowed_card_ids, closed_gene_sets=closed_gene_sets,
            )
    fail("WHO5 diagnosis", issues)
    return "WHO5 diagnosis structurally valid"


def validate_icc_diagnosis(
    text: str,
    *,
    valid_variants: set[str] | None = None,
    variant_genes: dict[str, str] | None = None,
    case_fact_ids: set[str] | None = None,
    observed_case_fact_ids: set[str] | None = None,
    panel_genes: set[str] | None = None,
    allowed_card_ids: set[str] | None = None,
    closed_gene_sets: dict[str, set[str]] | None = None,
) -> str:
    issues: list[ValidationIssue] = []
    d = _doc(text, "ICC diagnosis", issues)
    _exact(d, {"diagnoses", "comparison_with_who5"}, "icc", issues)
    rows = _list(d.get("diagnoses"), "diagnoses", issues, allow_empty=False, item_hint="ICC diagnosis mappings") if "diagnoses" in d else []
    detected_genes = set((variant_genes or {}).values())
    if rows is not None:
        for i, raw_row in enumerate(rows):
            path = f"diagnoses[{i}]"
            row = _mapping(raw_row, path, issues)
            if row is None:
                continue
            _exact(row, {"status", "diagnosis", "criteria"}, path, issues)
            _enum(row.get("status"), {"established", "conditional", "indeterminate"}, f"{path}.status", issues)
            _text(row.get("diagnosis"), f"{path}.diagnosis", issues)
            _diagnosis_criteria(
                row.get("criteria"), f"{path}.criteria", issues,
                valid_variants=valid_variants, case_fact_ids=case_fact_ids, observed_case_fact_ids=observed_case_fact_ids, panel_genes=panel_genes,
                detected_genes=detected_genes, allowed_card_ids=allowed_card_ids, closed_gene_sets=closed_gene_sets,
            )
    comp = _mapping(d.get("comparison_with_who5"), "comparison_with_who5", issues) if "comparison_with_who5" in d else None
    if comp is not None:
        _exact(comp, {"significantly_different", "explanation"}, "comparison_with_who5", issues)
        value = comp.get("significantly_different")
        if not isinstance(value, bool):
            issues.append(ValidationIssue(
                "comparison_with_who5.significantly_different",
                f"expected boolean; received {_type_name(value)}",
                "serialize the existing true/false decision as a YAML boolean" if _boolean_serialization_only(value) else "return the required true/false decision",
                repair_class="serialization" if _boolean_serialization_only(value) else "content",
                received=_preview(value), expected="true or false",
            ))
        _text(comp.get("explanation"), "comparison_with_who5.explanation", issues)
    fail("ICC diagnosis", issues)
    return "ICC diagnosis structurally valid"

def validate_other_diagnosis(text: str) -> str:
    issues: list[ValidationIssue] = []
    d = _doc(text, "other diagnostic considerations", issues)
    _exact(d, {"concurrent_second_diagnosis"}, "other_diagnostic_considerations", issues)
    sec = _mapping(d.get("concurrent_second_diagnosis"), "concurrent_second_diagnosis", issues) if "concurrent_second_diagnosis" in d else None
    if sec is not None:
        _exact(sec, {"status", "answer", "reasons"}, "concurrent_second_diagnosis", issues)
        status=sec.get("status")
        _enum(status, {"none", "supported", "uncertain"}, "concurrent_second_diagnosis.status", issues)
        answer=sec.get("answer")
        reasons=sec.get("reasons")
        if status=="none":
            if answer not in (None, ""):
                issues.append(ValidationIssue("concurrent_second_diagnosis.answer", "status=none requires answer: null", "set answer: null without adding a diagnosis", repair_class="content", received=_preview(answer), expected="null"))
            if reasons != []:
                issues.append(ValidationIssue("concurrent_second_diagnosis.reasons", "status=none requires reasons: []", "return an empty reasons list", repair_class="content", received=_preview(reasons), expected="[]"))
        else:
            _text(answer, "concurrent_second_diagnosis.answer", issues)
            _reasons(reasons, "concurrent_second_diagnosis.reasons", issues)
    fail("other diagnostic considerations", issues)
    return "other diagnostic considerations structurally valid"


def validate_evidence_match_batch(text: str, items: list[dict]) -> str:
    issues: list[ValidationIssue] = []
    d = _doc(text, "batched evidence match", issues)
    _exact(d, {"matches"}, "evidence_match_batch", issues)
    rows = _list(d.get("matches"), "matches", issues, allow_empty=not items, item_hint="evidence-match mappings") if "matches" in d else []
    if rows is None:
        rows = []
    if len(rows) != len(items):
        issues.append(ValidationIssue(
            "matches", f"expected {len(items)} rows, received {len(rows)}",
            "return exactly one match row for every supplied evidence item, in the same order",
            repair_class="content", received=str(len(rows)), expected=str(len(items)),
        ))
    for i, raw in enumerate(rows):
        path = f"matches[{i}]"
        row = _mapping(raw, path, issues)
        if row is None:
            continue
        _exact(row, {"evidence_id", "card_id", "source", "quote"}, path, issues)
        if i >= len(items):
            continue
        expected = items[i]
        if row.get("evidence_id") != expected["evidence_id"]:
            issues.append(ValidationIssue(
                f"{path}.evidence_id", f"received {row.get('evidence_id')!r}",
                f"copy {expected['evidence_id']!r} exactly", repair_class="content",
                received=_preview(row.get("evidence_id")), expected=repr(expected["evidence_id"]),
            ))
        card_id = row.get("card_id")
        allowed = set(expected.get("candidate_card_ids") or [])
        if card_id not in allowed:
            issues.append(ValidationIssue(
                f"{path}.card_id", f"selected card {card_id!r} was not among this item's candidate cards",
                "select one exact candidate card ID for this evidence item", repair_class="content",
                received=_preview(card_id), expected=str(sorted(allowed)),
            ))
        _text(row.get("source"), f"{path}.source", issues)
        _text(row.get("quote"), f"{path}.quote", issues)
    fail("batched evidence match", issues)
    return "batched evidence match structurally valid"


def validate_evidence_audit_batch(text: str, items: list[dict]) -> str:
    issues: list[ValidationIssue] = []
    d = _doc(text, "batched evidence audit", issues)
    _exact(d, {"audits"}, "evidence_audit_batch", issues)
    rows = _list(d.get("audits"), "audits", issues, allow_empty=not items, item_hint="evidence-audit mappings") if "audits" in d else []
    if rows is None: rows=[]
    if len(rows) != len(items):
        issues.append(ValidationIssue("audits", f"expected {len(items)} rows, received {len(rows)}", "return exactly one audit row for every supplied evidence item, in the same order", repair_class="content"))
    for i, raw in enumerate(rows):
        path=f"audits[{i}]"; row=_mapping(raw,path,issues)
        if row is None: continue
        _exact(row,{"evidence_id","quote_supports_statement","quote_supports_reason","risk","comments"},path,issues)
        if i < len(items) and row.get("evidence_id") != items[i]["evidence_id"]:
            issues.append(ValidationIssue(f"{path}.evidence_id",f"received {row.get('evidence_id')!r}",f"copy {items[i]['evidence_id']!r} exactly",repair_class="content"))
        support_values=[]
        for field in ("quote_supports_statement","quote_supports_reason"):
            value=row.get(field); support_values.append(value)
            if not isinstance(value,bool):
                issues.append(ValidationIssue(f"{path}.{field}",f"expected boolean; received {_type_name(value)}","serialize the existing true/false decision as YAML boolean" if _boolean_serialization_only(value) else "return the required true/false decision",repair_class="serialization" if _boolean_serialization_only(value) else "content",received=_preview(value),expected="true or false"))
        _enum(row.get("risk"),{"none","warning"},f"{path}.risk",issues)
        comments=_list(row.get("comments"),f"{path}.comments",issues,allow_empty=True,item_hint="comment strings")
        good=[]
        if comments is not None:
            for j,c in enumerate(comments):
                if _text(c,f"{path}.comments[{j}]",issues): good.append(c)
        if (False in support_values or row.get("risk")=="warning") and comments is not None and not good:
            issues.append(ValidationIssue(f"{path}.comments","failed support check/warning requires actionable feedback but comments are empty","explain the exact unsupported relationship or warning without prescribing the replacement clinical answer",repair_class="content"))
    fail("batched evidence audit",issues); return "batched evidence audit structurally valid"


def validate_statement_generation_batch(text: str, items: list[dict]) -> str:
    issues: list[ValidationIssue] = []
    d = _doc(text, "statement generation batch", issues)
    _exact(d, {"statements"}, "statement_generation_batch", issues)
    rows = _list(d.get("statements"), "statements", issues, allow_empty=not items, item_hint="statement mappings") if "statements" in d else []
    if rows is None:
        rows = []
    if len(rows) != len(items):
        issues.append(ValidationIssue("statements", f"expected {len(items)} rows, received {len(rows)}", "return exactly one statement row for every supplied proforma element, in the same order", repair_class="content"))
    for i, raw in enumerate(rows):
        path=f"statements[{i}]"; row=_mapping(raw,path,issues)
        if row is None: continue
        _exact(row,{"schema_id","statement"},path,issues)
        if i < len(items) and row.get("schema_id") != items[i]["schema_id"]:
            issues.append(ValidationIssue(f"{path}.schema_id",f"received {row.get('schema_id')!r}",f"copy {items[i]['schema_id']!r} exactly",repair_class="content"))
        sentence=row.get("statement")
        if _text(sentence,f"{path}.statement",issues):
            if "\n" in sentence:
                issues.append(ValidationIssue(f"{path}.statement","statement spans multiple physical lines","reserialize the same statement on one physical line without changing its words",repair_class="serialization",received=_preview(sentence),expected="one physical-line statement"))
            if i < len(items):
                for locked in items[i].get("locked_terms") or []:
                    if str(locked) not in sentence:
                        issues.append(ValidationIssue(
                            f"{path}.statement", f"missing locked provenance term {locked!r}",
                            f"preserve the exact validated term {locked!r}; do not replace it with a synonym or fallback label",
                            repair_class="content", expected=str(locked),
                        ))
    fail("statement generation batch",issues); return "statement generation batch structurally valid"


def validate_statement_audit_batch(text: str, items: list[dict]) -> str:
    issues: list[ValidationIssue] = []
    d=_doc(text,"statement audit batch",issues); _exact(d,{"audits"},"statement_audit_batch",issues)
    rows=_list(d.get("audits"),"audits",issues,allow_empty=not items,item_hint="statement-audit mappings") if "audits" in d else []
    if rows is None: rows=[]
    if len(rows)!=len(items): issues.append(ValidationIssue("audits",f"expected {len(items)} rows, received {len(rows)}","return exactly one audit row for every supplied statement, in the same order",repair_class="content"))
    for i,raw in enumerate(rows):
        path=f"audits[{i}]"; row=_mapping(raw,path,issues)
        if row is None: continue
        _exact(row,{"schema_id","statement_represents_proforma","reasoning_status","issues","negative_guidance"},path,issues)
        if i<len(items) and row.get("schema_id")!=items[i]["schema_id"]: issues.append(ValidationIssue(f"{path}.schema_id",f"received {row.get('schema_id')!r}",f"copy {items[i]['schema_id']!r} exactly",repair_class="content"))
        rep=row.get("statement_represents_proforma")
        if not isinstance(rep,bool):
            issues.append(ValidationIssue(f"{path}.statement_represents_proforma",f"expected boolean; received {_type_name(rep)}","serialize the existing true/false decision as YAML boolean" if _boolean_serialization_only(rep) else "return the required true/false decision",repair_class="serialization" if _boolean_serialization_only(rep) else "content",received=_preview(rep),expected="true or false"))
        status=row.get("reasoning_status"); _enum(status,{"supported","supported_if","unsupported"},f"{path}.reasoning_status",issues)
        for field in ("issues","negative_guidance"):
            vals=_list(row.get(field),f"{path}.{field}",issues,allow_empty=True,item_hint="strings")
            good=[]
            if vals is not None:
                for j,v in enumerate(vals):
                    if _text(v,f"{path}.{field}[{j}]",issues): good.append(v)
            if (rep is False or status=="unsupported") and field=="negative_guidance" and vals is not None and not good:
                issues.append(ValidationIssue(f"{path}.negative_guidance","failed semantic audit requires negative guidance","state the reasoning/representation mistake that must not be repeated; do not prescribe the replacement answer",repair_class="content"))
    fail("statement audit batch",issues); return "statement audit batch structurally valid"
