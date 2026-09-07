"""Deterministic support for the ``default_reviewed_v2`` audit overlay.

``default_reviewed_v2`` is a clone of ``default`` plus a bounded clinical-owner
correction overlay.  Every clinical owner is audited immediately after it emits,
before anything downstream consumes its result.  When the audit finds a
reasoning defect the workflow returns that defect to the **same clinical owner**
that produced it, with plain-English criticism and the owner's normal task
inputs, and lets the owner reassess.  At most two corrections are permitted per
owner; after that a configured terminal policy applies.

What this module owns is bookkeeping only:

* deterministic assembly of coherence packets from already-canonical artifacts;
* deterministic structural validation of shallow model output;
* deterministic derivation of the correction packet handed back to an owner;
* deterministic retry accounting, terminal-policy enforcement and provenance;
* propagation of unresolved findings into the canonical semantic-dissent ledger.

It contains no disease rules, no framework rules, and no semantic matching.  It
never authors a clinical conclusion.  The single exception is the diagnosis
terminal policy, which — after the owner has had three attempts and still failed
reasoning verification — restores the *supplied morphologic diagnosis* rather
than leaving an unverified molecular re-classification in place.  That is a
deliberate, configured, recorded refusal to apply an unverified upgrade, not a
choice of replacement diagnosis: WHO5 routing selects the card pool for every
downstream owner, so unlike a PTBG proposition it cannot simply be withheld.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

# Clinical owners that carry a reasoning audit.  Each maps to the workflow step
# that produced the artifact and the artifact's on-disk location.
DIAGNOSIS_OWNERS = ("who1", "who2", "icc")
PTBG_OWNERS = ("prognosis", "treatment", "biomarker", "germline")
OWNERS = DIAGNOSIS_OWNERS + PTBG_OWNERS

DIAGNOSIS_ARTIFACTS = {
    "who1": ("diagnosis_who5_pass_1", "who5.yaml"),
    "who2": ("diagnosis_who5_pass_2", "who5.yaml"),
    "icc": ("diagnosis_icc", "icc.yaml"),
}
OWNER_STEPS = {
    "who1": "diagnosis.who1",
    "who2": "diagnosis.who2",
    "icc": "diagnosis.icc",
    "prognosis": "prognosis",
    "treatment": "treatment",
    "biomarker": "biomarker",
    "germline": "germline",
}

# Original attempt plus two corrections.  The runner enforces the cap through
# ``review.on_fail.max_cycles``; this constant is what the tests assert against
# and what the terminal record reports.
MAX_CORRECTIONS = 2
MAX_OWNER_ATTEMPTS = MAX_CORRECTIONS + 1

TERMINAL_MODES = ("withhold_affected_output", "issue_with_dissent", "fail_run")
DEFAULT_TERMINAL_POLICY = {
    "diagnosis": "withhold_affected_output",
    "ptbg": "withhold_affected_output",
    "surface_dissent": True,
    "fail_run_on_unresolved": False,
}


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


def _params_owner(params: dict) -> str:
    owner = str((params or {}).get("owner") or "").strip()
    if owner not in OWNERS:
        raise V2Error(f"default_reviewed_v2 step declares unknown owner {owner!r}")
    return owner


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
# terminal policy configuration
# --------------------------------------------------------------------------

def terminal_policy(settings: dict | None) -> dict:
    """Resolve and validate the configured terminal policy.

    Because this setting governs what reaches a clinical report, an unsupported
    or misspelled value fails loudly rather than silently falling back.
    """
    configured = ((settings or {}).get("reviewed_v2_terminal_policy") or {})
    if not isinstance(configured, dict):
        raise V2Error("reviewed_v2_terminal_policy must be a mapping")
    policy = dict(DEFAULT_TERMINAL_POLICY)
    unknown = sorted(set(configured) - set(DEFAULT_TERMINAL_POLICY))
    if unknown:
        raise V2Error(f"reviewed_v2_terminal_policy has unknown key(s) {unknown}")
    policy.update(configured)
    for scope in ("diagnosis", "ptbg"):
        mode = _text(policy.get(scope))
        if mode not in TERMINAL_MODES:
            raise V2Error(
                f"reviewed_v2_terminal_policy.{scope} is {mode!r}; expected one of {', '.join(TERMINAL_MODES)}"
            )
    # Diagnosis cannot simply be withheld: WHO5 routing selects the candidate
    # card pool for ICC and every PTBG owner, so an absent diagnosis leaves
    # nothing to route on.  The configured withhold mode is therefore realised
    # as "withhold the unverified re-classification", restoring the supplied
    # morphologic diagnosis, which is the state the run would have been in had
    # the owner proposed no change at all.
    for flag in ("surface_dissent", "fail_run_on_unresolved"):
        if not isinstance(policy.get(flag), bool):
            raise V2Error(f"reviewed_v2_terminal_policy.{flag} must be a boolean")
    return policy


def _settings(ctx) -> dict:
    return ctx.get("settings", {}) or {}


# --------------------------------------------------------------------------
# evidence context labels (annotation only)
# --------------------------------------------------------------------------

def evidence_context(schema_id: str) -> str:
    """Derive a routing label from the deterministic reportable-element address.

    This is derived from ``schema_id`` alone -- never from card text, gene names
    or any other semantic content.  It is an annotation surfaced to the audit
    record so framework and non-framework prognostic claims are visibly
    distinguished.  It is NOT used to narrow candidate card pools; doing so
    requires framework attribution on prognosis cards, which the accepted-corpus
    card schema does not carry.  See README for the corpus change required.
    """
    sid = _text(schema_id).upper()
    if sid == "DX-WHO5" or sid.startswith("DX-CONCURRENT"):
        return "diagnosis_who5"
    if sid == "DX-ICC":
        return "diagnosis_icc"
    if sid.startswith("PX-FRAMEWORK"):
        return "prognosis_framework"
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
# phase 1 -- coherence packets, one per clinical owner
# --------------------------------------------------------------------------

def _patient_findings(case: dict, registry: dict | None = None) -> list[str]:
    """Project the structured case into plain findings for the auditor.

    Structured case facts are stored under ``value``.  Reading a ``fact`` key
    here silently dropped every morphology, cytogenetic, FISH, LOH and blast
    finding, leaving the auditor judging conclusions against a case it could not
    see.  Variant rows carry VAF where the case supplied one.
    """
    findings: list[str] = []
    for fact in case.get("case_facts") or []:
        if isinstance(fact, str):
            text = _text(fact)
        elif isinstance(fact, dict):
            text = _text(fact.get("value") if fact.get("value") is not None else fact.get("fact"))
            kind = _text(fact.get("kind")).replace("_", " ")
            if text and kind:
                text = f"{kind}: {text}"
        else:
            text = ""
        if text:
            findings.append(text)
    for row in (registry or {}).values() if isinstance(registry, dict) else []:
        if not isinstance(row, dict):
            continue
        text = _text(row.get("description") or row.get("gene"))
        if not text:
            continue
        vaf = _text(row.get("vaf"))
        findings.append(f"{text} (VAF {vaf})" if vaf else text)
    if not registry:
        for variant in case.get("variants") or []:
            if isinstance(variant, dict):
                text = _text(variant.get("description") or variant.get("gene"))
                vaf = _text(variant.get("vaf"))
                if text:
                    findings.append(f"{text} (VAF {vaf})" if vaf else text)
    absent = [g for g in (case.get("ngs_no_variants_detected") or []) if _text(g)]
    if absent:
        # The former wording asserted that no reportable variants were detected
        # at all, which flatly contradicts any variant listed above it. This key
        # is the list of genes *without* a detected variant, not a null result.
        findings.append(
            f"No sequence variant detected in {len(absent)} further assayed gene(s): " + ", ".join(sorted(absent))
        )
    return findings


def _diagnosis_source(work: Path, ctx, owner: str) -> dict | None:
    from workflows.proforma_v1 import self_runtime as sr

    cached = ctx.get(f"diagnosis_{owner}")
    if isinstance(cached, dict):
        return cached
    group, name = DIAGNOSIS_ARTIFACTS[owner]
    path = sr.output_path(work, group, name)
    if not path.is_file():
        return None
    return sr.read_yaml(path)


def _diagnosis_packet(work: Path, ctx, owner: str) -> dict:
    from workflows.proforma_v1 import self_runtime as sr
    from workflows.proforma_v1.engine import transforms as engine_transforms

    case, registry = sr.load_case_registry(work)
    row = _diagnosis_source(work, ctx, owner)
    if not isinstance(row, dict):
        raise V2Error(f"diagnosis coherence packet found no {owner!r} artifact")

    flags = engine_transforms._reviewed_text_coherence_flags({
        "who5": row if owner in ("who1", "who2") else None,
        "icc": row if owner == "icc" else None,
    })
    return {
        "authority": owner,
        "patient_findings": _patient_findings(case, registry),
        "starting_morphologic_diagnosis": _text(case.get("provisional_disease")),
        # The conclusion is never rendered inside the same prose block as the
        # reasons that may refute it. A label/derivation contradiction is only
        # reliably visible when the two are presented apart.
        "conclusion": _text(row.get("diagnosis")),
        "stated_reasons": _reasons(row.get("reason")),
        "deterministic_flags": flags,
    }


def _ptbg_packet(work: Path, ctx, owner: str) -> dict:
    from workflows.proforma_v1 import self_runtime as sr
    from workflows.proforma_v1 import domain_contract

    case, registry = sr.load_case_registry(work)
    path = sr.output_path(work, f"{owner}_state", "proforma.yaml")
    doc = sr.read_yaml(path) if path.is_file() else {}
    diagnosis_path = sr.output_path(work, "diagnosis", "diagnosis-final.yaml")
    diagnosis = sr.read_yaml(diagnosis_path) if diagnosis_path.is_file() else {}
    who5 = (diagnosis.get("who5") or {}) if isinstance(diagnosis, dict) else {}
    icc = (diagnosis.get("icc") or {}) if isinstance(diagnosis, dict) else {}

    contract = domain_contract.contract(owner)
    reviews = []
    for bucket in contract.buckets:
        rows = doc.get(bucket)
        if not isinstance(rows, list):
            continue
        for index, row in enumerate(rows, 1):
            if not isinstance(row, dict):
                continue
            reviews.append({
                "reference": f"{bucket}-{index:02d}",
                "bucket": bucket,
                "statement": _text(row.get("statement") or row.get("reason")),
                "stated_reason": _text(row.get("reason")),
            })
    for index, row in enumerate(doc.get("prognostic_frameworks") or [], 1):
        if isinstance(row, dict):
            reviews.append({
                "reference": f"prognostic_frameworks-{index:02d}",
                "bucket": "prognostic_frameworks",
                "statement": _text(row.get("name")),
                "stated_reason": _text(row.get("reason")),
            })
    return {
        "domain": owner,
        "patient_findings": _patient_findings(case, registry),
        "authoritative_diagnosis": {
            "who5": _text(who5.get("diagnosis")),
            "icc": _text(icc.get("diagnosis")),
            "applicable_disease": _text(doc.get("applicable_disease")),
        },
        "propositions": reviews,
    }


def coherence_packet(value: Any, context: dict, params: dict) -> Any:
    """Build one clinical owner's coherence packet."""
    ctx = _ctx(context)
    work = _work(context)
    owner = _params_owner(params)
    packet = (
        _diagnosis_packet(work, ctx, owner)
        if owner in DIAGNOSIS_OWNERS
        else _ptbg_packet(work, ctx, owner)
    )
    return packet


# --------------------------------------------------------------------------
# phase 2 -- structural validation and the correction gate
# --------------------------------------------------------------------------

def _structural_issues(doc: Any) -> list[str]:
    """Deterministic facts only: shape, types, and the presence of a brief.

    Semantic disagreement is never a structural failure.
    """
    if not isinstance(doc, dict):
        return ["coherence output is not a mapping"]
    issues: list[str] = []
    unknown = sorted(set(doc) - {"conclusion_supported", "reason_defective", "correction_brief"})
    if unknown:
        issues.append(f"coherence output has unknown key(s) {unknown}")
    for field in ("conclusion_supported", "reason_defective"):
        if not isinstance(doc.get(field), bool):
            issues.append(f"coherence output field {field!r} must be a boolean")
    defective = doc.get("conclusion_supported") is False or doc.get("reason_defective") is True
    brief = _text(doc.get("correction_brief"))
    if defective and not brief:
        issues.append("coherence output reports a defect but supplies no correction_brief")
    return issues


def _owner_attempts(ctx, gate_step_id: str) -> int:
    """Owner attempts consumed so far for this clinical object.

    Keyed strictly on the reviewing step id, which maps one-to-one onto the
    owner step id for the run.  It is deliberately NOT keyed on the emitted
    conclusion: a correction that changes the conclusion must consume the same
    budget, or the bound silently disappears.
    """
    cycles = ctx.get("review_cycles", {}) or {}
    return int(cycles.get(gate_step_id, 0)) + 1


def correction_gate(value: Any, context: dict, params: dict) -> Any:
    """Decide whether one clinical owner must reassess, and assemble the brief.

    The returned artifact carries the review verdict and the correction packet
    the owner will receive.  The auditor's routing judgements
    (``conclusion_supported`` / ``reason_defective``) are deliberately kept out
    of it and written to a side record instead: telling an owner that a reviewer
    found its conclusion unsupported is functionally an instruction to change
    that conclusion, which is the anchoring failure this design avoids.
    """
    ctx = _ctx(context)
    work = _work(context)
    owner = _params_owner(params)
    gate_step_id = f"audit.{owner}.gate"

    verdict = _artifact(ctx, f"audit.{owner}.coherence", f"v2_{owner}_coherence") or {}
    packet = _artifact(ctx, f"audit.{owner}.packet", f"v2_{owner}_packet") or {}
    issues = _structural_issues(verdict)

    attempts = _owner_attempts(ctx, gate_step_id)
    conclusion_supported = verdict.get("conclusion_supported")
    reason_defective = verdict.get("reason_defective")
    defective = conclusion_supported is False or reason_defective is True

    # A structurally invalid audit response is not evidence of a clinical
    # defect. It is surfaced, and the owner is not disturbed on the strength of
    # an unreadable verdict.
    status = "pass"
    if issues:
        status = "audit_failed"
    elif defective:
        status = "revision_required"

    previous = None
    if status == "revision_required":
        previous = (
            _diagnosis_source(work, ctx, owner)
            if owner in DIAGNOSIS_OWNERS
            else _ptbg_previous(work, owner)
        )

    record = {
        "owner": owner,
        "owner_step": OWNER_STEPS[owner],
        "status": status,
        "owner_attempts_used": attempts,
        "max_owner_attempts": MAX_OWNER_ATTEMPTS,
        "conclusion_supported": conclusion_supported,
        "reason_defective": reason_defective,
        "structural_issues": issues,
    }
    _write_side_record(work, f"{owner}-audit.yaml", record)

    result: dict[str, Any] = {"status": status}
    if status == "revision_required":
        result["correction"] = {
            "correction_brief": _text(verdict.get("correction_brief")),
            "previous_output": previous,
        }
    return result


def _ptbg_previous(work: Path, owner: str) -> dict | None:
    from workflows.proforma_v1 import self_runtime as sr
    path = sr.output_path(work, f"{owner}_state", "proforma.yaml")
    return sr.read_yaml(path) if path.is_file() else None


# --------------------------------------------------------------------------
# phase 3 -- terminal policy
# --------------------------------------------------------------------------

def _terminal_owners(ctx, owners: tuple[str, ...]) -> list[str]:
    """Owners whose bounded correction budget was exhausted without passing."""
    values = ctx.get("review_terminal", {}) or {}
    out = []
    for owner in owners:
        row = values.get(f"audit.{owner}.gate")
        if isinstance(row, str):
            row = {"action": row}
        if isinstance(row, dict) and row.get("action"):
            out.append(owner)
    return out


def _raise_terminal_dissent(work: Path, *, owner: str, stage: str, reviewed_text: str, brief: str, outcome: str) -> None:
    from workflows.proforma_v1.engine import dissent as workflow_dissent

    key = f"reviewed-v2-terminal:{owner}"
    workflow_dissent.raise_issue(
        work,
        issue_key=key,
        stage=stage,
        reviewed_text=reviewed_text or f"{owner} clinical assessment",
        dissent_reason=[
            brief or "An independent reasoning review identified a defect that the clinical owner did not resolve.",
            f"The clinical owner was asked to reassess and did not clear the finding within "
            f"{MAX_OWNER_ATTEMPTS} attempts.",
        ],
        action_recommended=["Human review of this clinical assessment is required."],
    )
    workflow_dissent.address(
        work, issue_key=key, stage=stage, action=[outcome], status="retained_with_dissent",
    )


def diagnosis_terminal(value: Any, context: dict, params: dict) -> Any:
    """Apply the configured terminal policy to unresolved diagnosis owners.

    ``withhold_affected_output`` withholds the *unverified re-classification*,
    restoring the supplied morphologic diagnosis and marking the change as not
    applied.  This is the only point in the overlay where Python touches a
    clinical conclusion, and it does so only after three owner attempts, only
    under an explicit configured policy, and only by declining a change the
    owner proposed — never by selecting a different one.
    """
    ctx = _ctx(context)
    work = _work(context)
    from workflows.proforma_v1 import self_runtime as sr
    from workflows.proforma_v1.engine.workflow_runner import TerminalWorkflowFailure

    policy = terminal_policy(_settings(ctx))
    owners = _terminal_owners(ctx, DIAGNOSIS_OWNERS)
    applied: list[dict] = []
    if not owners:
        _write_side_record(work, "diagnosis-terminal.yaml", {"policy": policy, "applied": applied})
        return {"policy": policy["diagnosis"], "applied": applied}

    case, _reg = sr.load_case_registry(work)
    morphologic = _text(case.get("provisional_disease"))
    for owner in owners:
        record = _side_record(work, f"{owner}-audit.yaml")
        brief = _text(record.get("correction_brief")) or _text(
            (_artifact(ctx, f"audit.{owner}.coherence", f"v2_{owner}_coherence") or {}).get("correction_brief")
        )
        group, name = DIAGNOSIS_ARTIFACTS[owner]
        path = sr.output_path(work, group, name)
        row = sr.read_yaml(path) if path.is_file() else {}
        previous = _text(row.get("diagnosis"))
        mode = policy["diagnosis"]
        outcome = ""
        if mode == "fail_run":
            outcome = "The run was stopped for human resolution."
        elif mode == "issue_with_dissent":
            outcome = "The disputed diagnosis was retained in the report with visible dissent."
        else:
            row["diagnosis"] = morphologic
            row["diagnostic_effect"] = "unchanged"
            row["variants"] = []
            row["reason"] = (
                "The proposed molecular/cytogenetic re-classification did not clear independent reasoning "
                "review within the permitted attempts and has been withheld. The supplied morphologic "
                "diagnosis is retained unchanged and this assessment requires human review."
            )
            row["reviewed_v2_terminal"] = {
                "withheld_diagnosis": previous,
                "restored": "supplied_morphologic_diagnosis",
                "owner_attempts": MAX_OWNER_ATTEMPTS,
            }
            sr.write_yaml(path, row)
            outcome = (
                f"The unverified re-classification to '{previous}' was withheld and the supplied "
                f"morphologic diagnosis '{morphologic}' was retained."
            )
        applied.append({"owner": owner, "mode": mode, "withheld": previous, "outcome": outcome, "brief": brief})
        if policy["surface_dissent"]:
            _raise_terminal_dissent(
                work, owner=owner, stage="reasoning correction (diagnosis)",
                reviewed_text=previous or morphologic, brief=brief, outcome=outcome,
            )
    _write_side_record(work, "diagnosis-terminal.yaml", {"policy": policy, "applied": applied})
    if policy["diagnosis"] == "fail_run" or policy["fail_run_on_unresolved"]:
        raise TerminalWorkflowFailure(
            "default_reviewed_v2: diagnosis reasoning remained unresolved after "
            f"{MAX_OWNER_ATTEMPTS} owner attempts ({', '.join(owners)})",
            reviewer="audit.diagnosis.terminal",
        )
    return {"policy": policy["diagnosis"], "applied": applied}


def ptbg_terminal(value: Any, context: dict, params: dict) -> Any:
    """Apply the configured terminal policy to unresolved PTBG owners.

    A PTBG proposition, unlike a diagnosis, is genuinely optional output: the
    run does not route on it.  ``withhold_affected_output`` therefore clears the
    affected domain's propositions before the evidence chain consumes them, so
    a disputed claim is never treated downstream as accepted clinical truth.
    """
    ctx = _ctx(context)
    work = _work(context)
    from workflows.proforma_v1 import self_runtime as sr
    from workflows.proforma_v1 import domain_contract
    from workflows.proforma_v1.engine.workflow_runner import TerminalWorkflowFailure

    policy = terminal_policy(_settings(ctx))
    owners = _terminal_owners(ctx, PTBG_OWNERS)
    applied: list[dict] = []
    for owner in owners:
        record = _side_record(work, f"{owner}-audit.yaml")
        brief = _text(record.get("correction_brief")) or _text(
            (_artifact(ctx, f"audit.{owner}.coherence", f"v2_{owner}_coherence") or {}).get("correction_brief")
        )
        mode = policy["ptbg"]
        path = sr.output_path(work, f"{owner}_state", "proforma.yaml")
        doc = sr.read_yaml(path) if path.is_file() else {}
        withheld = 0
        if mode == "withhold_affected_output":
            for bucket in domain_contract.contract(owner).buckets:
                rows = doc.get(bucket)
                if isinstance(rows, list) and rows:
                    withheld += len(rows)
                    doc[bucket] = []
            frameworks = doc.get("prognostic_frameworks")
            if isinstance(frameworks, list) and frameworks:
                withheld += len(frameworks)
                doc["prognostic_frameworks"] = []
            doc["reviewed_v2_terminal"] = {
                "withheld_propositions": withheld,
                "owner_attempts": MAX_OWNER_ATTEMPTS,
            }
            sr.write_yaml(path, doc)
            outcome = f"{withheld} unresolved {owner} proposition(s) were withheld from the report."
        elif mode == "fail_run":
            outcome = "The run was stopped for human resolution."
        else:
            outcome = f"Unresolved {owner} propositions were retained in the report with visible dissent."
        applied.append({"owner": owner, "mode": mode, "withheld": withheld, "outcome": outcome, "brief": brief})
        if policy["surface_dissent"]:
            _raise_terminal_dissent(
                work, owner=owner, stage=f"reasoning correction ({owner})",
                reviewed_text=f"{owner} assessment", brief=brief, outcome=outcome,
            )
    _write_side_record(work, "ptbg-terminal.yaml", {"policy": policy, "applied": applied})
    if owners and (policy["ptbg"] == "fail_run" or policy["fail_run_on_unresolved"]):
        raise TerminalWorkflowFailure(
            "default_reviewed_v2: PTBG reasoning remained unresolved after "
            f"{MAX_OWNER_ATTEMPTS} owner attempts ({', '.join(owners)})",
            reviewer="audit.ptbg.terminal",
        )
    return {"policy": policy["ptbg"], "applied": applied}


# --------------------------------------------------------------------------
# phase 4 -- finalization provenance guard
# --------------------------------------------------------------------------

def diagnosis_provenance(value: Any, context: dict, params: dict) -> Any:
    """Prove which artifact version was finalized, before the report is built.

    Identity only.  This asserts that the object being carried forward is the
    latest accepted owner artifact and records whether a terminal policy was
    invoked.  It makes no judgement about whether the clinical conclusion is
    correct.
    """
    ctx = _ctx(context)
    work = _work(context)
    from workflows.proforma_v1 import self_runtime as sr

    final_path = sr.output_path(work, "diagnosis", "diagnosis-final.yaml")
    if not final_path.is_file():
        raise V2Error("diagnosis provenance guard ran before diagnosis-final.yaml exists")
    final = sr.read_yaml(final_path)
    provenance = dict(final.get("provenance") or {})

    who1_path = sr.output_path(work, *DIAGNOSIS_ARTIFACTS["who1"])
    who1 = sr.read_yaml(who1_path) if who1_path.is_file() else {}
    who2_path = sr.output_path(work, *DIAGNOSIS_ARTIFACTS["who2"])
    live = sr.read_yaml(who2_path) if who2_path.is_file() else who1

    issues = []
    finalized = _text((final.get("who5") or {}).get("diagnosis"))
    if finalized != _text(live.get("diagnosis")):
        issues.append(
            "finalized WHO5 diagnosis does not match the latest accepted WHO owner artifact"
        )
    terminal = _side_record(work, "diagnosis-terminal.yaml")
    record = {
        "finalized_who5": finalized,
        "latest_owner_artifact": _text(live.get("diagnosis")),
        "routing_source": provenance.get("who5_routing_source"),
        "who1_artifact_sha256": provenance.get("who1_artifact_sha256"),
        "icc_artifact_sha256": provenance.get("icc_artifact_sha256"),
        "terminal_policy_invoked": bool(terminal.get("applied")),
        "terminal_applied": terminal.get("applied") or [],
        "issues": issues,
    }
    _write_side_record(work, "diagnosis-provenance.yaml", record)
    if issues:
        raise V2Error("; ".join(issues))
    return record


# --------------------------------------------------------------------------
# side records
# --------------------------------------------------------------------------

def _write_side_record(work: Path, name: str, payload: Any) -> Path:
    from workflows.proforma_v1 import self_runtime as sr
    return sr.write_yaml(sr.output_path(work, "audit_v2", name), payload)


def _side_record(work: Path, name: str) -> dict:
    from workflows.proforma_v1 import self_runtime as sr
    path = sr.output_path(work, "audit_v2", name)
    return sr.read_yaml(path) if path.is_file() else {}


# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------

TRANSFORMS = {
    "v2_coherence_packet": coherence_packet,
    "v2_correction_gate": correction_gate,
    "v2_diagnosis_terminal": diagnosis_terminal,
    "v2_ptbg_terminal": ptbg_terminal,
    "v2_diagnosis_provenance": diagnosis_provenance,
}


def run(name: str, context: dict, params: dict) -> Any:
    handler = TRANSFORMS.get(name)
    if handler is None:
        raise V2Error(f"unknown default_reviewed_v2 transform {name!r}")
    return handler(None, context, params)
