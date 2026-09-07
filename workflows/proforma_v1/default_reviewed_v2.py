"""Deterministic support for the ``default_reviewed_v2`` audit overlay.

`default_reviewed_v2` is a clone of `default` plus a small coherence/revision
overlay.  It deliberately does **not** replace the shipped three-stage evidence
chain (match -> audit -> adjudicate): independent verification is retained
because it is the mechanism that suppresses evidence hallucination.

What this module owns is bookkeeping only:

* deterministic assembly of coherence packets from already-canonical artifacts;
* deterministic structural validation of shallow model output;
* deterministic derivation of revision targets from audit findings;
* deterministic patching of *named* owner fields and mechanically-required
  schema metadata.

It contains no disease rules, no framework rules, and no semantic matching.
Every model response is filed against the object Python supplied for review;
identity is never recovered from prose.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

# Statuses the coherence model may return.  Kept deliberately small.
COHERENCE_STATUSES = ("pass", "revision_required")
# Where a revision_required finding may be directed.
REVISION_SCOPES = ("reason", "conclusion")
# Authorities audited by the diagnosis coherence call.
DIAGNOSIS_AUTHORITIES = ("who1", "who2", "icc")
PTBG = ("prognosis", "treatment", "biomarker", "germline")

# Owner fields Python is permitted to patch.  Anything outside this set is a
# clinical conclusion and belongs to the owner model, not to the workflow.
PATCHABLE_DIAGNOSIS_FIELDS = ("reason",)
PATCHABLE_PTBG_FIELDS = ("reason",)


class V2Error(ValueError):
    """A deterministic v2 precondition was violated."""


# --------------------------------------------------------------------------
# context plumbing
# --------------------------------------------------------------------------

def _ctx(context: dict):
    ctx = context.get("__workflow_context__") if isinstance(context, dict) else None
    if ctx is None:
        raise V2Error("default_reviewed_v2 transform requires workflow context")
    return ctx


def _work(context: dict) -> Path:
    value = context.get("__work__") if isinstance(context, dict) else None
    if value is None:
        value = getattr(_ctx(context), "work", None)
    if value is None:
        raise V2Error("default_reviewed_v2 transform requires a work directory")
    return Path(value)


def _artifact(ctx, step_id: str, artifact_name: str):
    """Read a generic artifact from context, falling back to its persisted file."""
    value = ctx.get(artifact_name)
    if value is not None:
        return value
    workflow = ctx.get("workflow")
    if workflow is None:
        return None
    try:
        step = workflow.step(step_id)
    except KeyError:
        return None
    from workflows.proforma_v1.engine import artifacts as workflow_artifacts
    path = workflow_artifacts.generic_output_path(ctx.work, step, create=False)
    if not path.is_file():
        return None
    fmt = str((step.output or {}).get("format") or "yaml").lower()
    raw = path.read_text(encoding="utf-8")
    value = json.loads(raw) if fmt == "json" else yaml.safe_load(raw) if fmt == "yaml" else raw
    ctx.put(artifact_name, value)
    return value


def _text(value: Any) -> str:
    return str(value or "").strip()


def _reasons(value: Any) -> list[str]:
    """Split an owner reason into displayable lines without changing meaning.

    Splitting is on explicit line breaks only.  No sentence segmentation, no
    clause detection: this is presentation, not atomisation.
    """
    text = _text(value)
    if not text:
        return []
    return [line.strip(" -\t") for line in text.splitlines() if line.strip(" -\t")]


# --------------------------------------------------------------------------
# evidence context labels (annotation only)
# --------------------------------------------------------------------------

def evidence_context(schema_id: str) -> str:
    """Derive a routing label from the deterministic reportable-element address.

    This is derived from ``schema_id`` alone -- never from card text, gene names
    or any other semantic content.  It is currently an **annotation**: it is
    surfaced to the coherence step and to the audit record so framework and
    non-framework prognostic claims are visibly distinguished.

    It is NOT yet used to narrow candidate card pools.  Doing so requires
    framework attribution on prognosis cards, which the accepted-corpus card
    schema does not carry (cards expose card_id, locator, interpretation, genes,
    diseases, disease_ancestors, category, evidence_tier, secondary_citation).
    Splitting the pool without that field would require string-matching
    framework names against card interpretations, which is exactly the semantic
    linkage this workflow forbids.  See README for the corpus change required.
    """
    sid = _text(schema_id).upper()
    if sid == "DX-WHO5" or sid.startswith("DX-CONCURRENT"):
        return "diagnosis_who5"
    if sid == "DX-ICC":
        return "diagnosis_icc"
    if sid.startswith("PX-FRAMEWORK"):
        return "prognosis_framework"
    if sid.startswith("PX-OTHER_EVIDENCE"):
        return "prognosis_other"
    if sid.startswith("PX-"):
        return "prognosis_other"
    if sid.startswith("TX-"):
        return "treatment"
    if sid.startswith("MRD-"):
        return "biomarker"
    if sid.startswith("GL-"):
        return "germline"
    return "unclassified"


# --------------------------------------------------------------------------
# phase 1 -- diagnosis coherence packet (always built)
# --------------------------------------------------------------------------

def _patient_findings(case: dict) -> list[str]:
    findings: list[str] = []
    for fact in case.get("case_facts") or []:
        text = _text(fact if isinstance(fact, str) else fact.get("fact"))
        if text:
            findings.append(text)
    for variant in case.get("variants") or []:
        if not isinstance(variant, dict):
            continue
        text = _text(variant.get("description") or variant.get("gene"))
        if text:
            findings.append(text)
    if case.get("ngs_no_variants_detected"):
        findings.append("No reportable variants were detected on the assayed panel.")
    return findings


def diagnosis_coherence_packet(value: Any, context: dict, params: dict) -> Any:
    """Freeze conclusion and stated reasons as SEPARATE labelled fields.

    The conclusion is never rendered inside the same prose block as the reasons
    that may refute it.  A label/derivation contradiction is only reliably
    visible when the two are presented apart.
    """
    from workflows.proforma_v1 import self_runtime as sr

    ctx = _ctx(context)
    work = _work(context)
    case, _reg = sr.load_case_registry(work)

    sources: dict[str, dict] = {}
    who1 = ctx.get("diagnosis_who1")
    if who1 is None:
        who1 = sr.accept_who(work, pass_number=1)
    sources["who1"] = who1

    who2_path = sr.output_path(work, "diagnosis_who5_pass_2", "who5.yaml")
    if who2_path.is_file():
        sources["who2"] = ctx.get("diagnosis_who2") or sr.accept_who(work, pass_number=2)

    icc = ctx.get("diagnosis_icc")
    if icc is None:
        icc = sr.accept_icc(work)
    sources["icc"] = icc

    from workflows.proforma_v1.engine import transforms as engine_transforms

    reviews = []
    for authority in DIAGNOSIS_AUTHORITIES:
        row = sources.get(authority)
        if not isinstance(row, dict):
            continue
        reviews.append({
            "authority": authority,
            "conclusion": _text(row.get("diagnosis")),
            "stated_reasons": _reasons(row.get("reason")),
        })

    # Cheap deterministic prior only.  It is fed to the model as a hint and is
    # never a trigger: a reworded contradiction will not fire it, which is
    # precisely why the coherence call is unconditional.
    flags = engine_transforms._reviewed_text_coherence_flags({
        "who5": sources.get("who2") or sources.get("who1"),
        "icc": sources.get("icc"),
    })

    return {
        "patient_findings": _patient_findings(case),
        "reviews": reviews,
        "deterministic_flags": flags,
    }


# --------------------------------------------------------------------------
# phase 2 -- deterministic structural validation
# --------------------------------------------------------------------------

def _validate_review_rows(doc: Any, expected_keys: list[str], key_field: str) -> list[str]:
    """Deterministic facts only: parse, cardinality, membership, enums.

    Semantic disagreement is never a structural failure.
    """
    issues: list[str] = []
    if not isinstance(doc, dict):
        return ["coherence output is not a mapping"]
    rows = doc.get("reviews")
    if not isinstance(rows, list):
        return ["coherence output has no reviews list"]

    seen: list[str] = []
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            issues.append(f"review {index} is not a mapping")
            continue
        key = _text(row.get(key_field))
        if not key:
            issues.append(f"review {index} has no {key_field}")
            continue
        if key not in expected_keys:
            issues.append(f"review {index} names unsupplied {key_field} {key!r}")
        if key in seen:
            issues.append(f"duplicate review for {key_field} {key!r}")
        seen.append(key)
        status = _text(row.get("status"))
        if status not in COHERENCE_STATUSES:
            issues.append(f"review for {key!r} has unsupported status {status!r}")
        if status == "revision_required":
            scope = _text(row.get("scope"))
            if scope not in REVISION_SCOPES:
                issues.append(f"review for {key!r} has unsupported scope {scope!r}")
            if not [i for i in (row.get("issues") or []) if _text(i)]:
                issues.append(f"review for {key!r} requires revision but states no issue")

    missing = [key for key in expected_keys if key not in seen]
    if missing:
        issues.append(f"no review returned for: {', '.join(missing)}")
    return issues


def validate_diagnosis_coherence(value: Any, context: dict, params: dict) -> Any:
    """Structural gate for the single reviewed model step.

    A failure here discards the output and triggers exactly one clean
    regeneration from the original inputs.  The malformed output is never fed
    back to the model.
    """
    ctx = _ctx(context)
    packet = _artifact(ctx, "audit.dx.packet", "v2_dx_packet") or {}
    expected = [_text(row.get("authority")) for row in packet.get("reviews") or []]
    doc = _artifact(ctx, "audit.dx.coherence", "v2_dx_coherence")
    issues = _validate_review_rows(doc, expected, "authority")
    return {"status": "fail" if issues else "pass", "issues": issues}


# --------------------------------------------------------------------------
# phase 3 -- PTBG coherence, gated
# --------------------------------------------------------------------------

def _evidence_verdicts(work: Path, ctx) -> dict[str, str]:
    """Map reportable-element address -> worst observed evidence outcome."""
    from workflows.proforma_v1 import self_runtime as sr

    verdicts: dict[str, str] = {}
    elements_path = sr.output_path(work, "evidence_enriched", "reportable-elements.yaml")
    if not elements_path.is_file():
        return verdicts
    doc = sr.read_yaml(elements_path)
    for element in doc.get("elements") or []:
        if not isinstance(element, dict):
            continue
        sid = _text(element.get("schema_id"))
        if not sid:
            continue
        tags = element.get("evidence_card_tags") or element.get("card_tags") or []
        verdicts[sid] = "supported" if tags else "unsupported"
    return verdicts


def ptbg_coherence_packet(value: Any, context: dict, params: dict) -> Any:
    """Return [] when nothing needs PTBG coherence review.

    An empty artifact closes the ``has_items`` gate, so no model call is made.
    """
    from workflows.proforma_v1 import self_runtime as sr

    ctx = _ctx(context)
    work = _work(context)
    verdicts = _evidence_verdicts(work, ctx)
    unsupported = sorted(sid for sid, status in verdicts.items() if status != "supported")
    if not unsupported:
        return []

    domains = ctx.get("domains") or sr.load_domains(work)
    case, _reg = sr.load_case_registry(work)
    elements_path = sr.output_path(work, "evidence_enriched", "reportable-elements.yaml")
    elements = (sr.read_yaml(elements_path).get("elements") or []) if elements_path.is_file() else []
    by_id = {_text(e.get("schema_id")): e for e in elements if isinstance(e, dict)}

    rows = []
    for sid in unsupported:
        element = by_id.get(sid) or {}
        rows.append({
            "reference": sid,
            "domain": _text(element.get("domain")),
            "evidence_context": evidence_context(sid),
            "statement": _text(element.get("statement")),
            "stated_reason": _text(element.get("reason")),
            "evidence_outcome": verdicts.get(sid, "unsupported"),
        })
    return {
        "patient_findings": _patient_findings(case),
        "reviews": rows,
        "domains_present": [d for d in PTBG if domains.get(d)],
    }


def validate_ptbg_coherence(value: Any, context: dict, params: dict) -> Any:
    """Deterministic validation with visible failure and no retry.

    The single permitted review block is spent on the diagnosis coherence step.
    A structural failure here is recorded and surfaced; it never spirals.
    """
    ctx = _ctx(context)
    packet = _artifact(ctx, "audit.ptbg.packet", "v2_ptbg_packet")
    if not packet:
        return {"status": "skipped", "issues": []}
    expected = [_text(row.get("reference")) for row in packet.get("reviews") or []]
    doc = _artifact(ctx, "audit.ptbg.coherence", "v2_ptbg_coherence")
    issues = _validate_review_rows(doc, expected, "reference")
    return {"status": "audit_failed" if issues else "pass", "issues": issues}


# --------------------------------------------------------------------------
# phase 4 -- revision targets and commit
# --------------------------------------------------------------------------

def _dx_targets(ctx) -> list[dict]:
    validation = _artifact(ctx, "audit.dx.validate", "v2_dx_validation") or {}
    doc = _artifact(ctx, "audit.dx.coherence", "v2_dx_coherence") or {}
    packet = _artifact(ctx, "audit.dx.packet", "v2_dx_packet") or {}
    by_authority = {_text(r.get("authority")): r for r in packet.get("reviews") or []}
    if validation.get("status") != "pass":
        return []
    targets = []
    for row in doc.get("reviews") or []:
        if _text(row.get("status")) != "revision_required":
            continue
        authority = _text(row.get("authority"))
        scope = _text(row.get("scope"))
        source = by_authority.get(authority) or {}
        targets.append({
            "kind": "diagnosis",
            "authority": authority,
            "scope": scope,
            # A conclusion-level finding is NOT auto-applied.  Rewriting a
            # diagnosis label from a coherence judgement would let the overlay
            # silently change a clinical conclusion.  It is surfaced instead.
            "actionable": scope == "reason",
            "conclusion": _text(source.get("conclusion")),
            "stated_reasons": source.get("stated_reasons") or [],
            "issues": [i for i in (row.get("issues") or []) if _text(i)],
        })
    return targets


def dx_revision_targets(value: Any, context: dict, params: dict) -> Any:
    """Actionable diagnosis revision tasks; [] closes the gate."""
    ctx = _ctx(context)
    work = _work(context)
    targets = _dx_targets(ctx)
    _write_side_record(work, "dx-revision-targets.yaml", {"targets": targets})
    actionable = [t for t in targets if t.get("actionable")]
    for index, target in enumerate(actionable):
        target["index"] = index
    return actionable


def _ptbg_targets(ctx) -> list[dict]:
    validation = _artifact(ctx, "audit.ptbg.validate", "v2_ptbg_validation") or {}
    doc = _artifact(ctx, "audit.ptbg.coherence", "v2_ptbg_coherence") or {}
    packet = _artifact(ctx, "audit.ptbg.packet", "v2_ptbg_packet") or {}
    rows = packet.get("reviews") if isinstance(packet, dict) else []
    by_reference = {_text(r.get("reference")): r for r in rows or []}
    if validation.get("status") != "pass":
        return []
    targets = []
    for row in doc.get("reviews") or []:
        if _text(row.get("status")) != "revision_required":
            continue
        reference = _text(row.get("reference"))
        source = by_reference.get(reference) or {}
        targets.append({
            "kind": "ptbg",
            "reference": reference,
            "domain": _text(source.get("domain")),
            "evidence_context": _text(source.get("evidence_context")),
            "scope": "reason",
            "actionable": True,
            "statement": _text(source.get("statement")),
            "stated_reason": _text(source.get("stated_reason")),
            "issues": [i for i in (row.get("issues") or []) if _text(i)],
        })
    return targets


def ptbg_revision_targets(value: Any, context: dict, params: dict) -> Any:
    """Actionable PTBG revision tasks; [] closes the gate."""
    ctx = _ctx(context)
    work = _work(context)
    targets = _ptbg_targets(ctx)
    _write_side_record(work, "ptbg-revision-targets.yaml", {"targets": targets})
    for index, target in enumerate(targets):
        target["index"] = index
    return targets


def _write_side_record(work: Path, name: str, payload: Any) -> Path:
    from workflows.proforma_v1 import self_runtime as sr
    return sr.write_yaml(sr.output_path(work, "audit_v2", name), payload)


def _revision_rows(ctx, step_id: str, artifact_name: str) -> list[dict]:
    doc = _artifact(ctx, step_id, artifact_name) or {}
    rows = doc.get("revisions") if isinstance(doc, dict) else None
    return [row for row in (rows or []) if isinstance(row, dict)]


def _patch_diagnosis_reason(work: Path, authority: str, reason: str) -> bool:
    """Replace only the ``reason`` field of one diagnosis artifact."""
    from workflows.proforma_v1 import self_runtime as sr

    location = {
        "who1": ("diagnosis_who5_pass_1", "who5.yaml"),
        "who2": ("diagnosis_who5_pass_2", "who5.yaml"),
        "icc": ("diagnosis_icc", "icc.yaml"),
    }.get(authority)
    if location is None:
        return False
    path = sr.output_path(work, *location)
    if not path.is_file():
        return False
    doc = sr.read_yaml(path)
    doc["reason"] = reason
    sr.write_yaml(path, doc)
    return True


def resolve_ptbg_address(reference: str) -> tuple[str, str, int] | None:
    """Resolve ``PX-<BUCKET>-<NN>`` to (domain, bucket, zero-based index).

    Purely positional and deterministic.  No text matching of any kind.
    """
    prefix, _, tail = _text(reference).partition("-")
    bucket, _, index_text = tail.rpartition("-")
    domain = {"PX": "prognosis", "TX": "treatment", "MRD": "biomarker", "GL": "germline"}.get(prefix)
    if not domain or not bucket or not index_text.isdigit():
        return None
    position = int(index_text) - 1
    if position < 0:
        return None
    return domain, bucket.lower(), position


def _patch_ptbg_reason(work: Path, reference: str, reason: str | None) -> bool:
    """Replace or clear one reportable PTBG row addressed by ``schema_id``."""
    from workflows.proforma_v1 import self_runtime as sr

    address = resolve_ptbg_address(reference)
    if address is None:
        return False
    domain, bucket, position = address
    path = sr.output_path(work, f"{domain}_state", "proforma.yaml")
    if not path.is_file():
        return False
    doc = sr.read_yaml(path)
    rows = doc.get(bucket)
    if not isinstance(rows, list) or position >= len(rows):
        return False
    row = rows[position]
    if not isinstance(row, dict):
        return False
    if reason is None:
        # The evidence-bearing proposition is removed, so the card tags that
        # supported it are mechanically required to go with it.
        row["reason"] = None
        row["evidence_card_tags"] = []
    else:
        row["reason"] = reason
    sr.write_yaml(path, doc)
    _patch_reportable_element(work, reference, reason)
    return True


def _patch_reportable_element(work: Path, reference: str, reason: str | None) -> None:
    """Mirror a committed PTBG revision into the already-finalised elements.

    PTBG revision runs after ``evidence.finalize``, so the reportable element
    list is the artifact ``report.blocks`` consumes.  Addressing is by
    ``schema_id``; no element is matched by text.
    """
    from workflows.proforma_v1 import self_runtime as sr

    path = sr.output_path(work, "evidence_enriched", "reportable-elements.yaml")
    if not path.is_file():
        return
    doc = sr.read_yaml(path)
    elements = doc.get("elements")
    if not isinstance(elements, list):
        return
    changed = False
    for element in elements:
        if not isinstance(element, dict) or _text(element.get("schema_id")) != _text(reference):
            continue
        if reason is None:
            element["reason"] = None
            element["statement"] = None
            element["evidence_card_tags"] = []
            element["suppressed"] = True
            element["suppression_reason"] = "v2_coherence_removed"
        else:
            element["reason"] = reason
            element["statement"] = reason
        changed = True
    if changed:
        sr.write_yaml(path, doc)


def _audit_failures(ctx) -> list[dict]:
    failures = []
    dx = _artifact(ctx, "audit.dx.validate", "v2_dx_validation") or {}
    ptbg = _artifact(ctx, "audit.ptbg.validate", "v2_ptbg_validation") or {}
    if dx.get("status") == "fail":
        failures.append({"kind": "audit_failed", "phase": "diagnosis_coherence",
                         "issues": dx.get("issues") or []})
    if ptbg.get("status") == "audit_failed":
        failures.append({"kind": "audit_failed", "phase": "ptbg_coherence",
                         "issues": ptbg.get("issues") or []})
    return failures


def dx_commit(value: Any, context: dict, params: dict) -> Any:
    """Apply diagnosis reason revisions; surface everything else visibly."""
    ctx = _ctx(context)
    work = _work(context)
    targets = _artifact(ctx, "audit.dx.targets", "v2_dx_targets") or []
    by_index = {t.get("index"): t for t in targets if isinstance(t, dict)}

    applied, unresolved = [], []
    record = _side_record(work, "dx-revision-targets.yaml")
    for target in record.get("targets") or []:
        if target.get("scope") == "conclusion":
            unresolved.append({
                "kind": "diagnosis",
                "address": target.get("authority"),
                "reason": "coherence audit disputes the stated conclusion; the workflow "
                          "does not rewrite a clinical conclusion automatically",
                "issues": target.get("issues") or [],
            })

    for row in _revision_rows(ctx, "audit.dx.revise", "v2_dx_revisions"):
        target = by_index.get(row.get("index"))
        if target is None:
            unresolved.append({"kind": "unmapped", "reason": "revision names no supplied target index"})
            continue
        replacement = row.get("reason")
        if replacement is None:
            unresolved.append({
                "kind": "diagnosis",
                "address": target.get("authority"),
                "reason": "a diagnosis reason may be corrected but not removed",
            })
            continue
        ok = _patch_diagnosis_reason(work, _text(target.get("authority")), _text(replacement))
        (applied if ok else unresolved).append({
            "kind": "diagnosis",
            "address": target.get("authority"),
            "action": "rescoped" if ok else "unresolved_address",
        })

    dx = _artifact(ctx, "audit.dx.validate", "v2_dx_validation") or {}
    if dx.get("status") == "fail":
        unresolved.append({"kind": "audit_failed", "phase": "diagnosis_coherence",
                           "issues": dx.get("issues") or []})

    result = {"applied": applied, "unresolved": unresolved}
    _write_side_record(work, "dx-audit-commit.yaml", result)
    return result


def ptbg_commit(value: Any, context: dict, params: dict) -> Any:
    """Apply PTBG reason rescoping/removal and record the full audit outcome."""
    ctx = _ctx(context)
    work = _work(context)
    targets = _artifact(ctx, "audit.ptbg.targets", "v2_ptbg_targets") or []
    by_index = {t.get("index"): t for t in targets if isinstance(t, dict)}

    applied, unresolved = [], []
    for row in _revision_rows(ctx, "audit.ptbg.revise", "v2_ptbg_revisions"):
        target = by_index.get(row.get("index"))
        if target is None:
            unresolved.append({"kind": "unmapped", "reason": "revision names no supplied target index"})
            continue
        replacement = row.get("reason")
        replacement = None if replacement is None else _text(replacement)
        ok = _patch_ptbg_reason(work, _text(target.get("reference")), replacement)
        (applied if ok else unresolved).append({
            "kind": "ptbg",
            "address": target.get("reference"),
            "action": ("cleared" if replacement is None else "rescoped") if ok else "unresolved_address",
        })

    unresolved.extend(_audit_failures(ctx))
    result = {"applied": applied, "unresolved": unresolved}
    _write_side_record(work, "ptbg-audit-commit.yaml", result)
    return result


def _side_record(work: Path, name: str) -> dict:
    from workflows.proforma_v1 import self_runtime as sr
    path = sr.output_path(work, "audit_v2", name)
    return sr.read_yaml(path) if path.is_file() else {}


# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------

TRANSFORMS = {
    "v2_diagnosis_coherence_packet": diagnosis_coherence_packet,
    "v2_validate_diagnosis_coherence": validate_diagnosis_coherence,
    "v2_dx_revision_targets": dx_revision_targets,
    "v2_dx_commit": dx_commit,
    "v2_ptbg_coherence_packet": ptbg_coherence_packet,
    "v2_validate_ptbg_coherence": validate_ptbg_coherence,
    "v2_ptbg_revision_targets": ptbg_revision_targets,
    "v2_ptbg_commit": ptbg_commit,
}


def run(name: str, context: dict, params: dict) -> Any:
    handler = TRANSFORMS.get(name)
    if handler is None:
        raise V2Error(f"unknown default_reviewed_v2 transform {name!r}")
    return handler(None, context, params)
