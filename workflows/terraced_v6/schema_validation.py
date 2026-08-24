"""Deterministic validators for terraced-v6 model artifacts.

Every validator accumulates issues and raises once, so a single repair turn
carries every defect the model must fix. None of these call a model, implement
retry behaviour, or track stagnation — that is the runner's job.

The four PTBG proformas are not implemented here: their contract lives in
`domain_contract.py`, which owns the bucket vocabulary that used to be repeated
across this module, `step._consolidate_rows`, `step._elements` and the
reportability defaults.
"""
from __future__ import annotations

from scripts.core.validated_model_task import ValidationIssue, fail
from workflows.terraced_v6 import domain_contract
from workflows.terraced_v6 import issues as iss


def _parsed(text, context, keys):
    doc, problems = iss.parse(text, fmt="yaml", context=context)
    if problems:
        fail(context, problems)
    return doc, list(iss.exact_keys(doc, keys, context))


# --- diagnosis ---------------------------------------------------------------

def validate_who5_diagnosis(text, *, allowed_diseases, valid_variants):
    ctx = "WHO5 diagnosis"
    doc, problems = _parsed(text, ctx, {"schema_disease", "diagnosis", "variants", "reason"})
    problems += iss.enum_field(
        doc.get("schema_disease"), allowed_diseases, "schema_disease", label="schema disease"
    )
    problems += iss.text_field(doc.get("diagnosis"), "diagnosis")
    _, variant_issues = iss.id_list(doc.get("variants"), "variants", valid_variants, allow_empty=True)
    problems += variant_issues
    problems += iss.text_field(doc.get("reason"), "reason")
    fail(ctx, problems)
    return "WHO5 diagnosis valid"


def validate_icc_diagnosis(text, *, valid_variants):
    ctx = "ICC diagnosis"
    doc, problems = _parsed(text, ctx, {"diagnosis", "variants", "reason"})
    problems += iss.text_field(doc.get("diagnosis"), "diagnosis")
    _, variant_issues = iss.id_list(doc.get("variants"), "variants", valid_variants, allow_empty=True)
    problems += variant_issues
    problems += iss.text_field(doc.get("reason"), "reason")
    fail(ctx, problems)
    return "ICC diagnosis valid"


def validate_second_diagnosis(text, *, valid_variants):
    ctx = "second diagnosis"
    doc, problems = _parsed(text, ctx, {"diagnosis", "variants", "reason"})
    if doc.get("diagnosis") is None:
        if doc.get("variants") not in ([], None) or doc.get("reason") is not None:
            problems.append(
                ValidationIssue(
                    ctx,
                    "diagnosis is null but variants/reason are populated",
                    "when there is no independent concurrent diagnosis, return diagnosis: null, "
                    "variants: [] and reason: null",
                    repair_class="content",
                    received=f"variants={iss.preview(doc.get('variants'))} reason={iss.preview(doc.get('reason'))}",
                    expected="variants: [] and reason: null",
                )
            )
    else:
        problems += iss.text_field(doc.get("diagnosis"), "diagnosis")
        _, variant_issues = iss.id_list(doc.get("variants"), "variants", valid_variants, allow_empty=True)
        problems += variant_issues
        problems += iss.text_field(doc.get("reason"), "reason")
    fail(ctx, problems)
    return "second diagnosis valid"


# --- PTBG owner proformas (flat one-row-per-variant contract) ----------------

def validate_domain(text, domain, valid_variants):
    return domain_contract.validate(text, domain_contract.contract(domain), valid_variants)


def validate_prognosis(text, valid):
    return validate_domain(text, "prognosis", valid)


def validate_treatment(text, valid):
    return validate_domain(text, "treatment", valid)


def validate_biomarker(text, valid):
    return validate_domain(text, "biomarker", valid)


def validate_germline(text, valid):
    return validate_domain(text, "germline", valid)


# --- batch stages ------------------------------------------------------------

def validate_evidence_match_batch(text, items):
    ctx = "evidence match"
    doc, problems = _parsed(text, ctx, {"matches"})
    rows = doc.get("matches")
    expected = [x["evidence_id"] for x in items]
    problems += iss.one_row_per_id(rows, expected, id_field="evidence_id", path="matches")
    by_id = {x["evidence_id"]: x for x in items}
    if isinstance(rows, list):
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            path = f"matches[{i}]"
            problems += iss.exact_keys(row, {"evidence_id", "card_id", "source", "quote"}, path)
            item = by_id.get(row.get("evidence_id"))
            if item is not None:
                problems += iss.enum_field(
                    row.get("card_id"), item["candidate_card_ids"], f"{path}.card_id", label="candidate card"
                )
            problems += iss.text_field(row.get("source"), f"{path}.source")
            problems += iss.text_field(row.get("quote"), f"{path}.quote")
    fail(ctx, problems)
    return "evidence matches valid"


def validate_evidence_audit_batch(text, items):
    ctx = "evidence audit"
    doc, problems = _parsed(text, ctx, {"audits"})
    rows = doc.get("audits")
    expected = [x["evidence_id"] for x in items]
    problems += iss.one_row_per_id(rows, expected, id_field="evidence_id", path="audits")
    if isinstance(rows, list):
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            path = f"audits[{i}]"
            problems += iss.exact_keys(
                row,
                {"evidence_id", "quote_supports_statement", "quote_supports_reason", "risk", "comments"},
                path,
            )
            problems += iss.bool_field(row.get("quote_supports_statement"), f"{path}.quote_supports_statement")
            problems += iss.bool_field(row.get("quote_supports_reason"), f"{path}.quote_supports_reason")
            problems += iss.enum_field(row.get("risk"), ("none", "warning"), f"{path}.risk", label="risk level")
            comments = row.get("comments")
            if not isinstance(comments, list) or any(not isinstance(x, str) for x in comments):
                problems.append(
                    ValidationIssue(
                        f"{path}.comments",
                        f"expected a list of strings; received {iss.type_name(comments)}",
                        "return comments as a list of strings, using [] when there is nothing to note",
                        repair_class="serialization" if isinstance(comments, str) else "content",
                        received=iss.preview(comments),
                        expected="list of strings",
                    )
                )
    fail(ctx, problems)
    return "evidence audits valid"


# --- writer stages -----------------------------------------------------------

def validate_report_write(text, blocks):
    ctx = "report writer"
    doc, problems = _parsed(text, ctx, {"blocks"})
    rows = doc.get("blocks")
    expected = [b["block_id"] for b in blocks]
    problems += iss.one_row_per_id(rows, expected, id_field="block_id", path="blocks")
    if isinstance(rows, list):
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            path = f"blocks[{i}]"
            problems += iss.exact_keys(row, {"block_id", "text"}, path)
            problems += iss.text_field(row.get("text"), f"{path}.text")
    fail(ctx, problems)
    return "report writer output valid"


def validate_preservation(text, blocks):
    ctx = "preservation audit"
    doc, problems = _parsed(text, ctx, {"audits"})
    rows = doc.get("audits")
    expected = [b["block_id"] for b in blocks]
    problems += iss.one_row_per_id(rows, expected, id_field="block_id", path="audits")
    if isinstance(rows, list):
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            path = f"audits[{i}]"
            problems += iss.exact_keys(row, {"block_id", "preserved", "issue"}, path)
            problems += iss.bool_field(row.get("preserved"), f"{path}.preserved")
            if row.get("preserved") is True:
                if row.get("issue") is not None:
                    problems.append(
                        ValidationIssue(
                            f"{path}.issue",
                            "populated even though preserved is true",
                            "use null for issue when preserved is true",
                            repair_class="content",
                            received=iss.preview(row.get("issue")),
                            expected="null",
                        )
                    )
            elif row.get("preserved") is False:
                problems += iss.text_field(row.get("issue"), f"{path}.issue")
    fail(ctx, problems)
    return "preservation audit valid"
