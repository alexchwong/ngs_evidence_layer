"""Deterministic validators for proforma-v1 model artifacts.

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
from workflows.proforma_v1 import domain_contract
from workflows.proforma_v1 import issues as iss


def _parsed(text, context, keys):
    doc, problems = iss.parse(text, fmt="yaml", context=context)
    if problems:
        fail(context, problems)
    return doc, list(iss.exact_keys(doc, keys, context))


# --- diagnosis ---------------------------------------------------------------

def validate_who5_diagnosis(text, *, allowed_diseases, valid_variants):
    ctx = "WHO5 diagnosis"
    doc, problems = _parsed(text, ctx, {"schema_disease", "diagnosis", "diagnostic_effect", "variants", "reason"})
    problems += iss.enum_field(
        doc.get("schema_disease"), allowed_diseases, "schema_disease", label="schema disease"
    )
    problems += iss.text_field(doc.get("diagnosis"), "diagnosis")
    problems += iss.enum_field(doc.get("diagnostic_effect"), ("unchanged", "refined", "superseded"), "diagnostic_effect", label="diagnostic effect")
    _, variant_issues = iss.id_list(doc.get("variants"), "variants", valid_variants, allow_empty=True)
    problems += variant_issues
    problems += iss.text_field(doc.get("reason"), "reason")
    fail(ctx, problems)
    return "WHO5 diagnosis valid"


def validate_icc_diagnosis(text, *, valid_variants):
    ctx = "ICC diagnosis"
    doc, problems = _parsed(text, ctx, {"diagnosis", "diagnostic_effect", "variants", "reason"})
    problems += iss.text_field(doc.get("diagnosis"), "diagnosis")
    problems += iss.enum_field(doc.get("diagnostic_effect"), ("unchanged", "refined", "superseded"), "diagnostic_effect", label="diagnostic effect")
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

def validate_domain(text, domain, valid_variants, *, registry=None, authoritative_disease=None):
    context = {
        "variants": sorted(valid_variants),
        "registry": registry or {},
        "authoritative_disease": authoritative_disease,
    }
    return domain_contract.validate(text, domain_contract.contract(domain), context)


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
            problems += iss.exact_keys(row, {"evidence_id", "card_tags"}, path)
            tags = row.get("card_tags")
            if not isinstance(tags, list):
                problems.append(
                    ValidationIssue(
                        f"{path}.card_tags",
                        f"expected a list; received {iss.type_name(tags)}",
                        "return card_tags as a list, using [] when no candidate card is an element of the reason",
                        repair_class="serialization" if isinstance(tags, str) else "content",
                        received=iss.preview(tags),
                        expected="list of candidate card tags",
                    )
                )
                continue
            if len(tags) != len(set(x for x in tags if isinstance(x, str))):
                problems.append(
                    ValidationIssue(
                        f"{path}.card_tags",
                        "contains duplicate card tags",
                        "list each selected card tag once",
                        repair_class="content",
                        received=iss.preview(tags),
                        expected="unique candidate card tags",
                    )
                )
            item = by_id.get(row.get("evidence_id"))
            for j, tag in enumerate(tags):
                if item is not None and tag not in item["candidate_card_tags"]:
                    problems.append(
                        ValidationIssue(
                            f"{path}.card_tags[{j}]",
                            f"{tag!r} was not supplied as a candidate for {row.get('evidence_id')}",
                            f"remove this tag from {row.get('evidence_id')} and preserve otherwise valid selections; select only exact tags supplied under this evidence item",
                            repair_class="content",
                            received=iss.preview(tag),
                            expected=f"one of this item's {len(item['candidate_card_tags'])} supplied candidate tag(s)",
                        )
                    )
    fail(ctx, problems)
    return "evidence matches valid"


def validate_evidence_audit_batch(text, items):
    ctx = "evidence audit"
    doc, problems = _parsed(text, ctx, {"audits"})
    rows = doc.get("audits")
    expected = [x["evidence_id"] for x in items]
    problems += iss.one_row_per_id(rows, expected, id_field="evidence_id", path="audits")
    by_id = {x["evidence_id"]: x for x in items}
    if isinstance(rows, list):
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            path = f"audits[{i}]"
            problems += iss.exact_keys(row, {"evidence_id", "card_audits"}, path)
            card_audits = row.get("card_audits")
            if not isinstance(card_audits, list):
                problems.append(
                    ValidationIssue(
                        f"{path}.card_audits",
                        f"expected a list; received {iss.type_name(card_audits)}",
                        "return one card_audits list containing one audit for every selected card tag",
                        repair_class="serialization" if isinstance(card_audits, str) else "content",
                        received=iss.preview(card_audits),
                        expected="list of card audit mappings",
                    )
                )
                continue
            item = by_id.get(row.get("evidence_id")) or {}
            selected = list(item.get("selected_card_tags") or [])
            seen = [x.get("card_tag") for x in card_audits if isinstance(x, dict)]
            missing = [x for x in selected if x not in seen]
            unexpected = [x for x in seen if x not in selected]
            duplicates = sorted({x for x in seen if x is not None and seen.count(x) > 1})
            if missing or unexpected or duplicates:
                parts = []
                if missing: parts.append(f"missing {missing}")
                if unexpected: parts.append(f"unexpected {unexpected}")
                if duplicates: parts.append(f"duplicate {duplicates}")
                problems.append(
                    ValidationIssue(
                        f"{path}.card_audits",
                        "; ".join(parts),
                        "return exactly one card audit for every selected card tag and no others",
                        repair_class="content",
                        received=f"card tags {seen}",
                        expected=f"card tags {selected}",
                    )
                )
            for j, audit in enumerate(card_audits):
                if not isinstance(audit, dict):
                    continue
                apath = f"{path}.card_audits[{j}]"
                problems += iss.exact_keys(audit, {"card_tag", "card_is_element_of_reason", "risk", "comments"}, apath)
                problems += iss.bool_field(audit.get("card_is_element_of_reason"), f"{apath}.card_is_element_of_reason")
                problems += iss.enum_field(audit.get("risk"), ("none", "warning"), f"{apath}.risk", label="risk level")
                comments = audit.get("comments")
                if not isinstance(comments, list) or any(not isinstance(x, str) for x in comments):
                    problems.append(
                        ValidationIssue(
                            f"{apath}.comments",
                            f"expected a list of strings; received {iss.type_name(comments)}",
                            "return comments as a list of strings, using [] when there is nothing to note",
                            repair_class="serialization" if isinstance(comments, str) else "content",
                            received=iss.preview(comments),
                            expected="list of strings",
                        )
                    )
                elif (audit.get("card_is_element_of_reason") is False or audit.get("risk") == "warning") and not any(x.strip() for x in comments):
                    problems.append(
                        ValidationIssue(
                            f"{apath}.comments",
                            "card/reason membership failed or a warning was raised without explanatory feedback",
                            "state concisely why the card is not an element of the reason or what the warning is, so the next matcher can choose better evidence",
                            repair_class="content",
                            received=iss.preview(comments),
                            expected="one or more actionable audit comments",
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
