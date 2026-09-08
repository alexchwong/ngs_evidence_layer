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

import hashlib
import json
import re
import shutil
import tempfile
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
OWNER_CALL_IDS = {
    "who1": "diagnosis-who5-pass-01",
    "who2": "diagnosis-who5-pass-02",
    "icc": "diagnosis-icc",
    "prognosis": "prognosis",
    "treatment": "treatment",
    "biomarker": "biomarker",
    "germline": "germline",
}
OWNER_PREFIXES = {
    "who1": "DX-WHO",
    "who2": "DX-WHO",
    "icc": "DX-ICC",
    "prognosis": "PX",
    "treatment": "TX",
    "biomarker": "MRD",
    "germline": "GL",
}

DEFECT_TYPES = {
    "contradicts_supplied_finding",
    "asserts_unsupplied_finding",
    "rule_restriction_unmet",
    "internal_contradiction",
    "wrong_disease_context",
    "background_knowledge_error",
}
ADJUDICATION_BASES = {"supplied_finding", "background_knowledge", "internal"}
DOWNGRADES = {
    "germline": {
        "germline_suspicious": {"germline_uncertain", "germline_against"},
    },
    "diagnosis": {
        "diagnostic_for_other_pathology": {"nonspecific"},
        "diagnostic_for_primary": {"nonspecific"},
    },
    "prognosis": {},
    "treatment": {},
    "biomarker": {},
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
    prefix = OWNER_PREFIXES[owner]
    propositions = [{
        "id": f"{prefix}:primary",
        "conclusion": _text(row.get("diagnosis")),
        "premises": [],
        "integrative_reason": _text(row.get("reason")) or None,
    }]
    for assessment in row.get("variant_assessments") or []:
        if not isinstance(assessment, dict):
            continue
        variant = _text(assessment.get("variant_id"))
        registry_row = registry.get(variant) if isinstance(registry, dict) else {}
        propositions.append({
            "id": f"{prefix}:{variant}",
            "variant": variant,
            "gene": (registry_row or {}).get("gene"),
            "conclusion": assessment.get("classification"),
            "premises": [{
                "name": "other_pathology",
                "status": "null" if assessment.get("other_pathology") is None else assessment.get("other_pathology"),
                "reason": _text(assessment.get("reason")) or None,
            }],
            "integrative_reason": _text(assessment.get("reason")) or None,
        })
    return {
        "authority": owner,
        "patient_findings": _patient_findings(case, registry),
        "starting_morphologic_diagnosis": _text(case.get("provisional_disease")),
        "deterministic_flags": flags,
        "propositions": propositions,
    }


def _ptbg_packet(work: Path, ctx, owner: str) -> dict:
    from workflows.proforma_v1 import self_runtime as sr
    from workflows.proforma_v1 import domain_contract
    from workflows.proforma_v1 import step as staged

    case, registry = sr.load_case_registry(work)
    path = sr.output_path(work, f"{owner}_state", "model-classification.yaml")
    doc = sr.read_yaml(path) if path.is_file() else {}
    diagnosis_path = sr.output_path(work, "diagnosis", "diagnosis-final.yaml")
    diagnosis = sr.read_yaml(diagnosis_path) if diagnosis_path.is_file() else {}
    who5 = (diagnosis.get("who5") or {}) if isinstance(diagnosis, dict) else {}
    icc = (diagnosis.get("icc") or {}) if isinstance(diagnosis, dict) else {}

    grouped: dict[str, list[dict]] = {}
    for row in doc.get("classification") or []:
        if isinstance(row, dict) and _text(row.get("variant")):
            grouped.setdefault(_text(row.get("variant")), []).append(row)
    reviews = []
    transform_records: list[dict] = []
    ordered_variants = list(registry) if isinstance(registry, dict) else []
    ordered_variants.extend(sorted(set(grouped) - set(ordered_variants)))
    for variant in ordered_variants:
        rows = grouped.get(variant) or []
        if not rows:
            continue
        premises = domain_contract.premises(
            rows, owner, transform_records=transform_records
        )
        statuses = {premise.get("status") for premise in premises}
        conclusion = next(iter(statuses)) if len(statuses) == 1 else "multi"
        first = rows[0]
        proposition = {
            "id": f"{OWNER_PREFIXES[owner]}:{variant}",
            "variant": variant,
            "gene": first.get("gene") or (registry.get(variant) or {}).get("gene"),
            "conclusion": conclusion,
            "premises": premises,
            "integrative_reason": _text(first.get("reason")) or None if owner == "germline" else None,
        }
        if owner == "germline":
            proposition.update({
                "observed_event_type": first.get("observed_event_type"),
                "observed_vaf": first.get("observed_vaf"),
                "eligibility": first.get("eligibility"),
                "conclusion": first.get("bucket"),
            })
        reviews.append(proposition)
    if transform_records:
        staged._log_transforms(work, [dict(record, stage=f"audit.{owner}.packet") for record in transform_records])
    for row in sorted(
        (row for row in (doc.get("prognostic_frameworks") or []) if isinstance(row, dict)),
        key=lambda item: _text(item.get("name")).casefold(),
    ):
        if isinstance(row, dict):
            reviews.append({
                "id": f"PX:framework:{_text(row.get('name'))}",
                "conclusion": row.get("tier"),
                "premises": [],
                "integrative_reason": _text(row.get("reason")) or None,
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _archive_files_equal(left: Path, right: Path) -> bool:
    left_files = sorted(path.relative_to(left) for path in left.rglob("*") if path.is_file())
    right_files = sorted(path.relative_to(right) for path in right.rglob("*") if path.is_file())
    return left_files == right_files and all(
        (left / name).read_bytes() == (right / name).read_bytes() for name in left_files
    )


def _owner_output_paths(work: Path, owner: str) -> tuple[Path, Path | None]:
    from workflows.proforma_v1 import self_runtime as sr

    if owner in DIAGNOSIS_OWNERS:
        return sr.output_path(work, *DIAGNOSIS_ARTIFACTS[owner]), None
    return (
        sr.output_path(work, f"{owner}_state", "model-classification.yaml"),
        sr.output_path(work, f"{owner}_state", "proforma.yaml"),
    )


def _owner_prompt_paths(work: Path, ctx, owner: str) -> tuple[Path, Path | None]:
    from workflows.proforma_v1 import layout

    if ctx.executor == "provider":
        root = layout.model_step_dir(work, OWNER_CALL_IDS[owner], existing=True)
        return root / "prompt.md", root / "output.txt"
    slug = re.sub(r"[^a-z0-9]+", "_", OWNER_STEPS[owner].casefold()).strip("_")
    candidates = sorted(
        (work / "intermediates").glob(f"[0-9][0-9][0-9]_workflow_prompt_{slug}/rendered-prompt.md")
    )
    return (candidates[-1] if candidates else work / "intermediates" / f"*_workflow_prompt_{slug}" / "rendered-prompt.md"), None


def _archive_owner_cycle(work: Path, ctx, owner: str, cycle: int) -> Path:
    accepted, proforma = _owner_output_paths(work, owner)
    prompt, raw = _owner_prompt_paths(work, ctx, owner)
    required = [accepted, prompt, *([proforma] if proforma is not None else [])]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise V2Error(
            f"owner cycle archive {owner} cycle {cycle:02d} missing required source: {', '.join(missing)}"
        )

    parent = work / "audit_v2" / "owner-cycles" / owner
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / f"{cycle:02d}"
    temporary = Path(tempfile.mkdtemp(prefix=f".{cycle:02d}.", dir=parent))
    try:
        shutil.copyfile(accepted, temporary / "accepted-output.yaml")
        shutil.copyfile(prompt, temporary / "rendered-prompt.md")
        if proforma is not None:
            shutil.copyfile(proforma, temporary / "proforma.yaml")
        raw_available = bool(raw is not None and raw.is_file())
        if raw_available:
            shutil.copyfile(raw, temporary / "raw-output.txt")
        metadata = {
            "executor": ctx.executor,
            "owner": owner,
            "cycle": cycle,
            "accepted_output_sha256": _sha256(temporary / "accepted-output.yaml"),
            "prompt_sha256": _sha256(temporary / "rendered-prompt.md"),
            "raw_output_available": raw_available,
            "prompt_source": str(prompt.relative_to(work)) if prompt.is_relative_to(work) else str(prompt),
        }
        (temporary / "metadata.yaml").write_text(
            yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        if target.exists():
            if _archive_files_equal(temporary, target):
                return target
            raise V2Error(f"conflicting owner cycle archive for {owner} cycle {cycle:02d}")
        temporary.replace(target)
        temporary = None
        return target
    finally:
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)


def _validate_packet(ctx, packet: dict) -> None:
    from workflows.proforma_v1.engine import schema_validation as sv

    workflow = ctx.get("workflow")
    schema = sv.load_schema(workflow.asset_root / "schemas/default_reviewed_v2/owner_packet.json")
    try:
        sv.validate_doc(packet, schema, label="owner packet")
    except sv.StructuredValidationError as exc:
        raise V2Error(str(exc)) from exc
    ids: set[str] = set()
    for proposition in packet.get("propositions") or []:
        proposition_id = proposition.get("id")
        if proposition_id in ids:
            raise V2Error(f"owner packet has duplicate proposition id {proposition_id!r}")
        ids.add(proposition_id)
        names: set[str] = set()
        for premise in proposition.get("premises") or []:
            name = premise.get("name")
            if name in names:
                raise V2Error(
                    f"owner packet proposition {proposition_id!r} has duplicate premise {name!r}"
                )
            names.add(name)


def coherence_packet(value: Any, context: dict, params: dict) -> Any:
    """Build one clinical owner's coherence packet."""
    ctx = _ctx(context)
    work = _work(context)
    owner = _params_owner(params)
    cycle = int((ctx.get("review_cycles", {}) or {}).get(f"audit.{owner}.gate", 0))
    _archive_owner_cycle(work, ctx, owner, cycle)
    packet = (
        _diagnosis_packet(work, ctx, owner)
        if owner in DIAGNOSIS_OWNERS
        else _ptbg_packet(work, ctx, owner)
    )
    _validate_packet(ctx, packet)
    return packet


# --------------------------------------------------------------------------
# phase 2 -- addressable disputes and adjudicated correction gate
# --------------------------------------------------------------------------

def _normal_text(value: Any) -> str:
    return " ".join(_text(value).casefold().split())


def _packet_index(packet: dict) -> dict[str, dict]:
    return {
        proposition.get("id"): proposition
        for proposition in packet.get("propositions") or []
        if isinstance(proposition, dict) and proposition.get("id")
    }


def _dispute_flags(dispute: dict, packet: dict) -> list[str]:
    findings = [_normal_text(row) for row in packet.get("patient_findings") or []]
    flags: list[str] = []
    quote = _normal_text(dispute.get("finding_quote"))
    if quote:
        flags.append(
            "finding_quote_matched"
            if any(quote in finding for finding in findings)
            else "finding_quote_not_matched"
        )
    absent = _normal_text(dispute.get("absent_finding"))
    if absent and any(absent in finding for finding in findings):
        flags.append("absent_finding_appears_present")
    criticism = _text(dispute.get("criticism"))
    quantitative = bool(
        re.search(r"\d\s*%|\b\d+(?:\.\d+)?\s*[:/]\s*\d+\b|\bexpected\b", criticism, re.I)
    )
    if dispute.get("defect_type") == "background_knowledge_error" or (
        quantitative and not any(_normal_text(criticism) in finding for finding in findings)
    ):
        flags.append("background_knowledge_claim")
    return flags


def _record_unusable_audit(work: Path, owner: str, reason: str) -> None:
    from workflows.proforma_v1.engine import dissent as workflow_dissent

    key = f"reviewed-v2-unusable:{owner}"
    workflow_dissent.raise_issue(
        work,
        issue_key=key,
        stage=f"reasoning audit ({owner})",
        reviewed_text=f"{owner} clinical assessment",
        dissent_reason=[reason],
        action_recommended=["No owner reassessment was requested because the independent review was unusable."],
    )
    workflow_dissent.address(
        work,
        issue_key=key,
        stage=f"reasoning audit ({owner})",
        action=["The clinical assessment was retained without a valid independent review."],
        status="retained_without_review",
    )


def _previously_rejected_disputes(work: Path, owner: str) -> set[tuple[str, str, str]]:
    """Return exact dispute identities already rejected by the adjudicator.

    This is deliberately text-exact after whitespace/case normalization.  It is
    not a semantic-similarity check: Python may suppress only the same criticism
    against the same owner-authored proposition/premise after an independent
    adjudicator has already rejected it.
    """
    history = _side_record(Path(work), f"{owner}-history.yaml")
    rejected: set[tuple[str, str, str]] = set()
    for cycle in history.get("cycles") or []:
        for row in ((cycle.get("adjudication") or {}).get("rejected_items") or []):
            proposition_id = _text(row.get("proposition_id"))
            premise = _text(row.get("premise"))
            criticism = _normal_text(row.get("criticism"))
            if proposition_id and premise and criticism:
                rejected.add((proposition_id, premise, criticism))
    return rejected


def v2_dispute_filter(value: Any, context: dict, params: dict) -> list[dict]:
    """Retain only structurally addressable disputes; never judge clinical truth."""
    from collections import Counter
    from workflows.proforma_v1.engine import schema_validation as sv

    ctx = _ctx(context)
    work = _work(context)
    owner = _params_owner(params)
    verdict = _artifact(ctx, f"audit.{owner}.coherence", f"v2_{owner}_coherence")
    packet = _artifact(ctx, f"audit.{owner}.packet", f"v2_{owner}_packet") or {}
    record = {
        "owner": owner,
        "state": "unusable",
        "retained_disputes": [],
        "discarded_disputes": [],
        "flags": [],
        "schema_violation": None,
    }
    try:
        schema = sv.load_schema(
            ctx.get("workflow").asset_root / "schemas/default_reviewed_v2/owner_coherence.json"
        )
        sv.validate_doc(verdict, schema, label="coherence verdict")
    except sv.StructuredValidationError as exc:
        record["schema_violation"] = str(exc)
        _write_side_record(work, f"{owner}-audit.yaml", record)
        _record_unusable_audit(work, owner, str(exc))
        return []

    disputes = verdict.get("disputes") or []
    propositions = _packet_index(packet)
    previously_rejected = _previously_rejected_disputes(work, owner)
    if len(disputes) > 2 * len(propositions):
        reason = f"dispute count {len(disputes)} exceeds 2 x proposition count {len(propositions)}"
        record["discarded_disputes"] = [
            {"dispute": dispute, "reasons": [reason]} for dispute in disputes
        ]
        _write_side_record(work, f"{owner}-audit.yaml", record)
        _record_unusable_audit(work, owner, reason)
        return []

    pairs = [
        (dispute.get("proposition_id"), dispute.get("premise"))
        for dispute in disputes
    ]
    duplicate_pairs = {pair for pair, count in Counter(pairs).items() if count > 1}
    retained = []
    all_flags: set[str] = set()
    for dispute in disputes:
        pair = (dispute.get("proposition_id"), dispute.get("premise"))
        reasons = []
        rejection_key = (
            _text(pair[0]),
            _text(pair[1]),
            _normal_text(dispute.get("criticism")),
        )
        if rejection_key in previously_rejected:
            reasons.append("exact same criticism for this proposition/premise was previously rejected by the adjudicator")
        proposition = propositions.get(pair[0])
        if pair in duplicate_pairs:
            reasons.append("duplicate proposition_id/premise pair; every duplicate was discarded")
        if proposition is None:
            reasons.append("unknown proposition_id")
        else:
            premise_names = {
                premise.get("name") for premise in proposition.get("premises") or []
                if isinstance(premise, dict)
            }
            if pair[1] != "integrative_reason" and pair[1] not in premise_names:
                reasons.append("premise is not owner-authored for this proposition")
        defect_type = dispute.get("defect_type")
        if defect_type in {"contradicts_supplied_finding", "rule_restriction_unmet"} and not _text(dispute.get("finding_quote")):
            reasons.append("finding_quote is required for this defect type")
        if defect_type == "asserts_unsupplied_finding" and not _text(dispute.get("absent_finding")):
            reasons.append("absent_finding is required for this defect type")
        related = dispute.get("related_proposition_id")
        if defect_type == "internal_contradiction":
            if related not in propositions or related == pair[0]:
                reasons.append("internal contradiction requires a different known related_proposition_id")
        elif related is not None:
            reasons.append("related_proposition_id must be null for this defect type")
        if reasons:
            record["discarded_disputes"].append({"dispute": dispute, "reasons": reasons})
            continue
        flags = _dispute_flags(dispute, packet)
        all_flags.update(flags)
        retained.append({
            "proposition_id": pair[0],
            "premise": pair[1],
            "defect_type": defect_type,
            "criticism": _text(dispute.get("criticism")),
            "flags": flags,
        })

    record["retained_disputes"] = retained
    record["flags"] = sorted(all_flags)
    if not disputes:
        record["state"] = "sound"
    elif retained:
        record["state"] = "disputed"
    else:
        reason = "auditor raised disputes but none was addressable"
        _record_unusable_audit(work, owner, reason)
    _write_side_record(work, f"{owner}-audit.yaml", record)
    return retained


def _owner_attempts(ctx, gate_step_id: str) -> int:
    """Owner attempts consumed so far for this clinical object.

    Keyed strictly on the reviewing step id, which maps one-to-one onto the
    owner step id for the run.  It is deliberately NOT keyed on the emitted
    conclusion: a correction that changes the conclusion must consume the same
    budget, or the bound silently disappears.
    """
    cycles = ctx.get("review_cycles", {}) or {}
    return int(cycles.get(gate_step_id, 0)) + 1


def _clear_adjudication(ctx, owner: str, reason: str) -> None:
    from workflows.proforma_v1.engine import artifacts as workflow_artifacts

    step = ctx.get("workflow").step(f"audit.{owner}.adjudicate")
    workflow_artifacts.generic_output_path(ctx.work, step, create=False).unlink(missing_ok=True)
    ctx.data.pop(f"v2_{owner}_adjudication", None)
    feedback = dict(ctx.get("self_validation_feedback", {}) or {})
    feedback[step.id] = (
        "The previous adjudication artifact was rejected by deterministic validation. "
        "Return the complete adjudication again, one entry per supplied dispute, "
        "in the same order. Problem: " + reason
    )
    ctx.put("self_validation_feedback", feedback)


def _adjudication_error(ctx, owner: str, cycle: int, reason: str) -> None:
    from workflows.proforma_v1.engine.workflow_runner import raise_terminal_failure

    name = f"{owner}-adjudication-attempts.yaml"
    previous = _side_record(Path(ctx.work), name)
    attempts = int(previous.get("attempts", 0)) + 1 if previous.get("cycle") == cycle else 1
    record = {"owner": owner, "cycle": cycle, "attempts": attempts, "last_error": reason}
    _write_side_record(Path(ctx.work), name, record)
    if attempts >= MAX_OWNER_ATTEMPTS:
        raise_terminal_failure(
            ctx,
            reviewer=f"audit.{owner}.adjudicate",
            message=(
                f"default_reviewed_v2: {owner} adjudication cycle {cycle} was rejected "
                f"{attempts} times; last validation error: {reason}"
            ),
        )
    _clear_adjudication(ctx, owner, reason)
    raise V2Error(f"{owner} adjudication rejected: {reason}")


def canonicalize_adjudication_document(doc: Any) -> tuple[Any, list[dict]]:
    """Fill only adjudication fields whose null value is fixed by ``upheld``.

    This is representation canonicalization, not adjudication.  Python never
    chooses or changes ``upheld``.  Once that boolean exists, the schema already
    fixes the mutually-exclusive unused fields to literal null, so adding an
    omitted null does not alter the model's semantic decision.
    """
    if not isinstance(doc, dict):
        return doc, []
    rows = doc.get("adjudications")
    if not isinstance(rows, list):
        return doc, []
    records: list[dict] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        upheld = row.get("upheld")
        if upheld is True and "rejection_reason" not in row:
            row["rejection_reason"] = None
            records.append({
                "transform": "inject_adjudication_null",
                "path": f"adjudications[{index}].rejection_reason",
                "from": "<missing>",
                "to": None,
            })
        elif upheld is False:
            for field in ("basis", "restated_criticism"):
                if field not in row:
                    row[field] = None
                    records.append({
                        "transform": "inject_adjudication_null",
                        "path": f"adjudications[{index}].{field}",
                        "from": "<missing>",
                        "to": None,
                    })
    return doc, records


def canonicalize_adjudication_text(text: str) -> tuple[str, list[dict]]:
    """Canonicalize omitted adjudication nulls in one parsed YAML document."""
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError:
        return text, []
    doc, records = canonicalize_adjudication_document(doc)
    if not records:
        return text, []
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=110), records


def validate_adjudication_document(
    ctx, owner: str, doc: dict, *, packet: dict | None = None, disputes: list[dict] | None = None
) -> dict:
    """Apply the complete adjudication contract without retry side effects.

    The same function is used at the model-output boundary and again at the
    correction gate.  This prevents an artifact from being marked accepted and
    later rejected unchanged by a stricter validator.
    """
    from collections import Counter
    from workflows.proforma_v1.engine import schema_validation as sv

    packet = packet if packet is not None else (_artifact(ctx, f"audit.{owner}.packet", f"v2_{owner}_packet") or {})
    disputes = disputes if disputes is not None else (_artifact(ctx, f"audit.{owner}.disputes", f"v2_{owner}_disputes") or [])
    schema = sv.load_schema(
        ctx.get("workflow").asset_root / "schemas/default_reviewed_v2/dispute_adjudication.json"
    )
    sv.validate_doc(doc, schema, label="Adjudication")
    rows = doc.get("adjudications") or []
    expected = [(row.get("proposition_id"), row.get("premise")) for row in disputes]
    actual = [(row.get("proposition_id"), row.get("premise")) for row in rows]
    duplicates = sorted(pair for pair, count in Counter(actual).items() if count > 1)
    if duplicates:
        raise V2Error(
            f"Adjudication repeats dispute pair(s) {duplicates}. Return exactly one adjudication row for each supplied dispute pair and preserve the other rows."
        )
    if Counter(actual) != Counter(expected):
        missing = list((Counter(expected) - Counter(actual)).elements())
        extra = list((Counter(actual) - Counter(expected)).elements())
        raise V2Error(
            "Adjudication must cover every supplied dispute exactly once and no others. "
            f"Missing={missing}; unexpected={extra}. Add or remove only the rows needed to match the supplied disputes."
        )
    packet_ids = set(_packet_index(packet))
    unknown = sorted({pair[0] for pair in actual} - packet_ids)
    if unknown:
        raise V2Error(
            f"Adjudication references proposition id(s) not present in the supplied coherence packet: {unknown}. Use the exact supplied proposition_id values; do not invent or rename IDs."
        )
    return doc


def _validated_adjudication(ctx, owner: str, packet: dict, disputes: list[dict]) -> dict:
    from workflows.proforma_v1.engine import schema_validation as sv

    cycle = int((ctx.get("review_cycles", {}) or {}).get(f"audit.{owner}.gate", 0))
    doc = _artifact(ctx, f"audit.{owner}.adjudicate", f"v2_{owner}_adjudication")
    if doc is None:
        raise V2Error(f"{owner} has addressable disputes but no adjudication artifact")
    try:
        validate_adjudication_document(ctx, owner, doc, packet=packet, disputes=disputes)
    except (sv.StructuredValidationError, V2Error) as exc:
        _adjudication_error(ctx, owner, cycle, str(exc))
    attempts_path = Path(ctx.work) / "audit_v2" / f"{owner}-adjudication-attempts.yaml"
    attempts_path.unlink(missing_ok=True)
    feedback = dict(ctx.get("self_validation_feedback", {}) or {})
    feedback.pop(f"audit.{owner}.adjudicate", None)
    ctx.put("self_validation_feedback", feedback)
    return doc


def _scoped_prior(packet: dict, upheld: list[dict]) -> list[dict]:
    challenged: dict[str, set[str]] = {}
    for row in upheld:
        challenged.setdefault(row["proposition_id"], set()).add(row["premise"])
    prior = []
    for proposition in packet.get("propositions") or []:
        copied = dict(proposition)
        names = challenged.get(proposition.get("id"), set())
        if names:
            copied["premises"] = [
                dict(premise) for premise in proposition.get("premises") or []
                if premise.get("name") not in names
            ]
            copied["integrative_reason"] = None
        else:
            copied["premises"] = [dict(premise) for premise in proposition.get("premises") or []]
        prior.append(copied)
    return prior


def _reason_hash(value: Any) -> str | None:
    text = _text(value)
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None


def _history_propositions(packet: dict) -> list[dict]:
    return [{
        "id": proposition.get("id"),
        "conclusion": proposition.get("conclusion"),
        "premise_statuses": {
            premise.get("name"): premise.get("status")
            for premise in proposition.get("premises") or []
        },
        "premise_reason_sha256": {
            premise.get("name"): _reason_hash(premise.get("reason"))
            for premise in proposition.get("premises") or []
        },
        "integrative_reason_sha256": _reason_hash(proposition.get("integrative_reason")),
    } for proposition in packet.get("propositions") or []]


def _record_history(work: Path, owner: str, cycle: int, packet: dict, audit: dict, adjudication: dict | None, gate_status: str) -> None:
    name = f"{owner}-history.yaml"
    document = _side_record(work, name) or {"owner": owner, "cycles": []}
    rows = adjudication.get("adjudications") or [] if isinstance(adjudication, dict) else []
    entry = {
        "cycle": cycle,
        "propositions": _history_propositions(packet),
        "audit": {
            "state": audit.get("state"),
            "addressable": len(audit.get("retained_disputes") or []),
            "discarded": len(audit.get("discarded_disputes") or []),
            "flags": audit.get("flags") or [],
        },
        "adjudication": {
            "state": "complete" if adjudication is not None else "not_required",
            "upheld": sum(row.get("upheld") is True for row in rows),
            "rejected": sum(row.get("upheld") is False for row in rows),
            # Persist the exact upheld challenge that caused a retry.  The next
            # accepted owner cycle must compare against this prior adjudication,
            # not against its own (usually now-sound) audit result.
            "upheld_items": [
                {
                    "proposition_id": row.get("proposition_id"),
                    "premise": row.get("premise"),
                    "restated_criticism": row.get("restated_criticism"),
                    "basis": row.get("basis"),
                    "flags": next((
                        dispute.get("flags") or []
                        for dispute in audit.get("retained_disputes") or []
                        if dispute.get("proposition_id") == row.get("proposition_id")
                        and dispute.get("premise") == row.get("premise")
                    ), []),
                }
                for row in rows if row.get("upheld") is True
            ],
            "rejected_items": [
                {
                    "proposition_id": row.get("proposition_id"),
                    "premise": row.get("premise"),
                    "criticism": next((
                        dispute.get("criticism")
                        for dispute in audit.get("retained_disputes") or []
                        if dispute.get("proposition_id") == row.get("proposition_id")
                        and dispute.get("premise") == row.get("premise")
                    ), None),
                    "rejection_reason": row.get("rejection_reason"),
                }
                for row in rows if row.get("upheld") is False
            ],
        },
        "gate_status": gate_status,
        "declined_comparisons": [],
    }
    cycles = document.setdefault("cycles", [])
    cycles[:] = [row for row in cycles if row.get("cycle") != cycle]
    cycles.append(entry)
    cycles.sort(key=lambda row: row.get("cycle", 0))
    _write_side_record(work, name, document)


def _record_correction_response(work: Path, owner: str, cycle: int, packet: dict) -> list[dict]:
    """Record how cycle ``N`` responded to the challenge that caused its retry.

    The causal challenge belongs to cycle ``N-1``.  Looking at the current
    cycle's upheld disputes loses successful corrections (and bad capitulations)
    because the current audit will commonly be sound after the owner changes its
    answer.
    """
    if cycle <= 0:
        return []
    history = _side_record(work, f"{owner}-history.yaml")
    previous = next((row for row in history.get("cycles") or [] if row.get("cycle") == cycle - 1), None)
    if previous is None:
        return []
    upheld = list(((previous.get("adjudication") or {}).get("upheld_items") or []))
    if not upheld:
        return []
    before_by_id = {row.get("id"): row for row in previous.get("propositions") or []}
    after_by_id = {row.get("id"): row for row in _history_propositions(packet)}
    output = _side_list_record(work, f"{owner}-correction-response.yaml")
    for item in upheld:
        proposition_id = item["proposition_id"]
        premise_name = item["premise"]
        before = before_by_id.get(proposition_id) or {}
        after = after_by_id.get(proposition_id) or {}
        row = {
            "proposition_id": proposition_id,
            "challenged_premise": premise_name,
            "cycle": cycle,
            "criticism": item.get("restated_criticism"),
            "adjudication_basis": item.get("basis"),
            "comparison_status": "matched",
            "packet_premise_before": premise_name,
            "packet_premise_after": premise_name,
            "premise_status_before": (before.get("premise_statuses") or {}).get(premise_name),
            "premise_status_after": (after.get("premise_statuses") or {}).get(premise_name),
            "conclusion_before": before.get("conclusion"),
            "conclusion_after": after.get("conclusion"),
            "premise_reason_sha256_before": (before.get("premise_reason_sha256") or {}).get(premise_name),
            "premise_reason_sha256_after": (after.get("premise_reason_sha256") or {}).get(premise_name),
            "flags": item.get("flags") or [],
        }
        if owner == "treatment" and premise_name.startswith("therapy:"):
            identity = premise_name.rsplit(":", 1)[0]
            row["challenged_premise"] = identity
            before_names = sorted(name for name in (before.get("premise_statuses") or {}) if name.rsplit(":", 1)[0] == identity)
            after_names = sorted(name for name in (after.get("premise_statuses") or {}) if name.rsplit(":", 1)[0] == identity)
            if len(before_names) == len(after_names) == 1:
                row["packet_premise_before"], row["packet_premise_after"] = before_names[0], after_names[0]
                row["premise_status_before"] = before["premise_statuses"].get(before_names[0])
                row["premise_status_after"] = after["premise_statuses"].get(after_names[0])
            else:
                row.update({
                    "comparison_status": "ambiguous",
                    "before_packet_premises": before_names,
                    "after_packet_premises": after_names,
                    "premise_status_before": None,
                    "premise_status_after": None,
                    "packet_premise_before": None,
                    "packet_premise_after": None,
                })
        row["premise_status_changed"] = (
            row["premise_status_before"] != row["premise_status_after"]
            if row["comparison_status"] == "matched" else None
        )
        row["conclusion_changed"] = row["conclusion_before"] != row["conclusion_after"]
        row["premise_reason_changed"] = row["premise_reason_sha256_before"] != row["premise_reason_sha256_after"]
        output.append(row)
    _write_side_record(work, f"{owner}-correction-response.yaml", output)
    return output



def _record_declined_comparisons(work: Path, owner: str, cycle: int, responses: list[dict]) -> None:
    declined = [
        {
            "proposition_id": row.get("proposition_id"),
            "challenged_premise": row.get("challenged_premise"),
            "comparison_status": row.get("comparison_status"),
            "before_packet_premises": row.get("before_packet_premises") or [],
            "after_packet_premises": row.get("after_packet_premises") or [],
            "reason": "cross-cycle premise identity was ambiguous; capitulation comparison declined",
        }
        for row in responses if row.get("comparison_status") != "matched"
    ]
    if not declined:
        return
    name = f"{owner}-history.yaml"
    document = _side_record(work, name)
    current = next((row for row in document.get("cycles") or [] if row.get("cycle") == cycle), None)
    if current is None:
        raise V2Error(f"cannot record declined comparison for {owner} cycle {cycle}: history entry missing")
    current["declined_comparisons"] = declined
    _write_side_record(work, name, document)

def _capitulation_guard(work: Path, owner: str, responses: list[dict]) -> None:
    from workflows.proforma_v1.engine import dissent as workflow_dissent

    domain = "diagnosis" if owner in DIAGNOSIS_OWNERS else owner
    for row in responses:
        if row.get("comparison_status") != "matched":
            continue
        downgraded = row.get("conclusion_after") in DOWNGRADES.get(domain, {}).get(row.get("conclusion_before"), set())
        background = row.get("adjudication_basis") == "background_knowledge" or "background_knowledge_claim" in (row.get("flags") or [])
        if not (downgraded and row.get("premise_status_changed") and background):
            continue
        key = f"reviewed-v2-capitulation:{owner}:{row.get('proposition_id')}:{row.get('challenged_premise')}"
        workflow_dissent.raise_issue(
            work,
            issue_key=key,
            stage=f"reasoning correction ({owner})",
            reviewed_text=f"{row.get('conclusion_before')} -> {row.get('conclusion_after')}",
            dissent_reason=[
                f"A background-knowledge criticism coincided with an explicit downgrade: {row.get('criticism')}",
                f"Basis: {row.get('adjudication_basis')}; cycle transition: {row.get('cycle') - 1} -> {row.get('cycle')}",
            ],
            action_recommended=["Human review of the downgrade is required."],
        )
        workflow_dissent.address(
            work, issue_key=key, stage=f"reasoning correction ({owner})",
            action=["The downgrade remains visible for human review."], status="retained_with_dissent",
        )


def correction_gate(value: Any, context: dict, params: dict) -> Any:
    """Require adjudication before an addressable dispute can disturb an owner."""
    ctx = _ctx(context)
    work = _work(context)
    owner = _params_owner(params)
    gate_step_id = f"audit.{owner}.gate"
    packet = _artifact(ctx, f"audit.{owner}.packet", f"v2_{owner}_packet") or {}
    disputes = _artifact(ctx, f"audit.{owner}.disputes", f"v2_{owner}_disputes") or []
    audit = _side_record(work, f"{owner}-audit.yaml")
    attempts = _owner_attempts(ctx, gate_step_id)
    state = audit.get("state")
    adjudication = None
    upheld = []
    if state == "disputed":
        if not disputes:
            raise V2Error(f"{owner} audit is disputed but has no retained disputes")
        adjudication = _validated_adjudication(ctx, owner, packet, disputes)
        dispute_by_pair = {(row["proposition_id"], row["premise"]): row for row in disputes}
        for row in adjudication.get("adjudications") or []:
            if row.get("upheld") is True:
                source = dispute_by_pair[(row["proposition_id"], row["premise"])]
                upheld.append({**row, "flags": source.get("flags") or []})
    status = "revision_required" if upheld else "pass"
    cycle = int((ctx.get("review_cycles", {}) or {}).get(gate_step_id, 0))
    # A correction response is caused by the *previous* cycle's upheld
    # adjudication.  Read it before writing the current cycle history.
    responses = _record_correction_response(work, owner, cycle, packet)
    _record_history(work, owner, cycle, packet, audit, adjudication, status)
    _record_declined_comparisons(work, owner, cycle, responses)
    _capitulation_guard(work, owner, responses)
    result: dict[str, Any] = {"status": status}
    if upheld:
        result["correction"] = {
            "items": [{
                "proposition_id": row["proposition_id"],
                "premise": row["premise"],
                "criticism": row["restated_criticism"],
            } for row in upheld],
            "prior_assessment": _scoped_prior(packet, upheld),
        }
    return result


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
    from workflows.proforma_v1.engine.workflow_runner import raise_terminal_failure

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
            # Owner artifacts are immutable once accepted.  Terminal disposition is
            # stored only in the side record and projected into downstream runtime
            # state; mutating the owner document here makes it fail its own schema.
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
        raise_terminal_failure(
            ctx,
            reviewer="audit.diagnosis.terminal",
            message=(
                "default_reviewed_v2: diagnosis reasoning remained unresolved after "
                f"{MAX_OWNER_ATTEMPTS} owner attempts ({', '.join(owners)})"
            ),
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
    from workflows.proforma_v1.engine.workflow_runner import raise_terminal_failure

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
            # Count the affected output for the terminal record, but do not mutate
            # the accepted owner artifact.  Downstream projection applies the
            # withholding after the normal owner schema has been validated.
            for bucket in domain_contract.contract(owner).buckets:
                rows = doc.get(bucket)
                if isinstance(rows, list):
                    withheld += len(rows)
            frameworks = doc.get("prognostic_frameworks")
            if isinstance(frameworks, list):
                withheld += len(frameworks)
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
        raise_terminal_failure(
            ctx,
            reviewer="audit.ptbg.terminal",
            message=(
                "default_reviewed_v2: PTBG reasoning remained unresolved after "
                f"{MAX_OWNER_ATTEMPTS} owner attempts ({', '.join(owners)})"
            ),
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

def _terminal_projected_diagnosis(work: Path, diagnosis: dict) -> dict:
    """Return downstream diagnosis with terminal withholding applied in memory.

    Accepted owner artifacts remain untouched and continue to satisfy their owner
    schemas.  This projection is a reporting/routing disposition, not a new owner
    clinical assessment.
    """
    import copy
    from workflows.proforma_v1 import self_runtime as sr

    terminal = _side_record(work, "diagnosis-terminal.yaml")
    applied = terminal.get("applied") if isinstance(terminal, dict) else None
    if not isinstance(applied, list):
        return diagnosis
    out = copy.deepcopy(diagnosis)
    case, _reg = sr.load_case_registry(work)
    morphologic = _text(case.get("provisional_disease"))
    reason = (
        "The proposed molecular/cytogenetic re-classification did not clear independent reasoning "
        "review within the permitted attempts and has been withheld. The supplied morphologic "
        "diagnosis is retained unchanged and this assessment requires human review."
    )
    for item in applied:
        if not isinstance(item, dict) or item.get("mode") != "withhold_affected_output":
            continue
        owner = item.get("owner")
        authority = "icc" if owner == "icc" else "who5" if owner in {"who1", "who2"} else None
        row = out.get(authority) if authority else None
        if not isinstance(row, dict):
            continue
        row["diagnosis"] = morphologic
        row["diagnostic_effect"] = "unchanged"
        row["variants"] = []
        if "variant_assessments" in row:
            row["variant_assessments"] = []
        row["reason"] = reason
    return out


def _terminal_projected_domains(work: Path, domains: dict) -> dict:
    """Return PTBG domains with terminal-withheld owners cleared in memory only."""
    import copy
    from workflows.proforma_v1 import domain_contract

    terminal = _side_record(work, "ptbg-terminal.yaml")
    applied = terminal.get("applied") if isinstance(terminal, dict) else None
    if not isinstance(applied, list):
        return domains
    out = copy.deepcopy(domains)
    for item in applied:
        if not isinstance(item, dict) or item.get("mode") != "withhold_affected_output":
            continue
        owner = item.get("owner")
        doc = out.get(owner)
        if not isinstance(doc, dict) or owner not in PTBG_OWNERS:
            continue
        for bucket in domain_contract.contract(owner).buckets:
            if isinstance(doc.get(bucket), list):
                doc[bucket] = []
        if isinstance(doc.get("prognostic_frameworks"), list):
            doc["prognostic_frameworks"] = []
    return out


def prepare_evidence_resolution(work: Path, sr, **kwargs):
    """Run evidence preparation against terminal-projected state without mutating owners."""
    diagnosis_terminal = _side_record(work, "diagnosis-terminal.yaml")
    ptbg_terminal = _side_record(work, "ptbg-terminal.yaml")
    if not diagnosis_terminal and not ptbg_terminal:
        return sr.prepare_evidence_resolution(work, **kwargs)

    original_finalize = sr.finalize_diagnosis
    original_accept_ptbg = sr.accept_ptbg

    def finalize_projected(inner_work):
        return _terminal_projected_diagnosis(Path(inner_work), original_finalize(inner_work))

    def accept_projected(inner_work, *args, **inner_kwargs):
        accepted = original_accept_ptbg(inner_work, *args, **inner_kwargs)
        return _terminal_projected_domains(Path(inner_work), accepted)

    sr.finalize_diagnosis = finalize_projected
    sr.accept_ptbg = accept_projected
    try:
        return sr.prepare_evidence_resolution(work, **kwargs)
    finally:
        sr.finalize_diagnosis = original_finalize
        sr.accept_ptbg = original_accept_ptbg


def _write_side_record(work: Path, name: str, payload: Any) -> Path:
    from workflows.proforma_v1 import self_runtime as sr
    return sr.write_yaml(sr.output_path(work, "audit_v2", name), payload)


def _side_record(work: Path, name: str) -> Any:
    from workflows.proforma_v1 import self_runtime as sr
    path = sr.output_path(work, "audit_v2", name)
    return sr.read_yaml(path) if path.is_file() else {}


def _side_list_record(work: Path, name: str) -> list:
    from workflows.proforma_v1 import self_runtime as sr
    path = sr.output_path(work, "audit_v2", name)
    if not path.is_file():
        return []
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    return value if isinstance(value, list) else []


# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------

TRANSFORMS = {
    "v2_coherence_packet": coherence_packet,
    "v2_dispute_filter": v2_dispute_filter,
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
