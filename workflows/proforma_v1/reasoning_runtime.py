"""Reasoning-workflow deterministic foundations.

This module is intentionally additive.  ``default.yaml`` does not import it.
The new ``reasoning.yaml`` transform aliases and later reasoning-specific
handlers may use it without changing default deterministic behaviour.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence
import copy
import json
import re

import yaml
from jsonschema import Draft202012Validator
from workflows.proforma_v1 import default_config
from scripts.core.syntax_repair.adapters import (
    WrongStructuredArtifactError,
    SyntaxParseError,
    adapter_for,
    classify_wrong_artifacts,
)


@dataclass(frozen=True)
class RepairRecord:
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class AuditIssue:
    code: str
    path: str
    message: str
    fix: str


@dataclass(frozen=True)
class AuditResult:
    repaired_text: str
    document: Any | None
    repairs: tuple[RepairRecord, ...]
    issues: tuple[AuditIssue, ...]

    @property
    def ok(self) -> bool:
        return not self.issues

    def feedback(self) -> str:
        return render_feedback(self.issues, self.repairs)


def delegated_transform(value: Any, *, context: dict | None = None, params: dict | None = None) -> Any:
    """Phase-1 identity marker for reasoning-owned deterministic boundaries."""
    return value


def batch_items(items: Sequence[Any] | Iterable[Any], limit: int) -> list[list[Any]]:
    """Split one logical reasoning operation into bounded physical batches."""
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        raise ValueError("reasoning batch limit must be a positive integer")
    rows = list(items)
    return [rows[i : i + limit] for i in range(0, len(rows), limit)]


def _path(parts: Iterable[Any]) -> str:
    out = "$"
    for part in parts:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            name = str(part)
            out += f".{name}" if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) else f"[{name!r}]"
    return out


def _repair_code(message: str) -> str:
    text = str(message).lower()
    if "bom" in text:
        return "remove_bom"
    if "line ending" in text:
        return "normalise_line_endings"
    if "code fence" in text or "fenced code" in text:
        return "strip_outer_markdown_fence"
    if "surrounding" in text and "prose" in text:
        return "strip_surrounding_prose"
    if "indentation tab" in text:
        return "expand_indentation_tabs"
    if "colon-space" in text:
        return "quote_colon_scalar"
    return "safe_serialization_cleanup"


def apply_safe_text_repairs(text: str, *, fmt: str) -> tuple[str, tuple[RepairRecord, ...]]:
    """Apply the shared deterministic YAML/JSON cleanup used by provider and self.

    The underlying adapter is deliberately serialization-only: BOMs, line
    endings, fences, clearly extraneous surrounding prose, indentation tabs and
    the narrow unquoted ``: `` scalar case.  It also raises
    :class:`WrongStructuredArtifactError` for an unmistakable Markdown document
    so that the originating model, not syntax repair, must regenerate it.
    """
    key = str(fmt).lower()
    if key not in {"yaml", "yml", "json"}:
        raise ValueError("reasoning structured format must be 'yaml' or 'json'")
    with classify_wrong_artifacts():
        candidate, messages = adapter_for(key).deterministic_cleanup(str(text))
    repairs = tuple(
        RepairRecord(code=_repair_code(message), path="$", message=message[0].upper() + message[1:] + ".")
        for message in messages
    )
    return candidate, repairs


def _parse(text: str, fmt: str) -> tuple[Any | None, list[AuditIssue]]:
    try:
        return adapter_for(fmt).parse(text), []
    except SyntaxParseError as exc:
        path = "$"
        if exc.line is not None:
            path = f"$ (line {exc.line}, column {exc.column or 1})"
        return None, [
            AuditIssue(
                code="parse_error",
                path=path,
                message=f"The artifact is not valid {fmt.upper()}: {exc}",
                fix="Repair the serialization only, preserving every clinical statement and supplied identifier.",
            )
        ]


def _matches_schema_type(value: Any, kind: str) -> bool:
    if kind == "null":
        return value is None
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "string":
        return isinstance(value, str)
    if kind == "array":
        return isinstance(value, list)
    if kind == "object":
        return isinstance(value, dict)
    return True


def _safe_schema_representation_repair(value: Any, schema: dict[str, Any], parts: tuple[Any, ...] = ()) -> tuple[Any, list[RepairRecord]]:
    """Repair only schema type/nesting mistakes that preserve scalar content.

    Missing keys, enums, clinical choices and semantic contradictions are never
    repaired here.  The deliberately narrow conversions are: quoted booleans,
    canonical quoted integers, one scalar/object wrapped as the required array,
    and a one-item list wrapper around an expected object.
    """
    current = copy.deepcopy(value)
    repairs: list[RepairRecord] = []
    raw_type = schema.get("type") if isinstance(schema, dict) else None
    allowed = [raw_type] if isinstance(raw_type, str) else list(raw_type or [])
    if allowed and not any(_matches_schema_type(current, kind) for kind in allowed):
        target = allowed[0] if len(allowed) == 1 else None
        replacement = current
        message = None
        if target == "boolean" and isinstance(current, str) and current.strip().lower() in {"true", "false"}:
            replacement = current.strip().lower() == "true"
            message = "Converted a quoted YAML boolean to the required boolean scalar without changing its token value"
        elif target == "integer" and isinstance(current, str) and re.fullmatch(r"-?(?:0|[1-9]\d*)", current):
            parsed = int(current)
            if str(parsed) == current:
                replacement = parsed
                message = "Converted a quoted canonical integer to the required integer scalar without changing its token value"
        elif target == "array" and not isinstance(current, (list, tuple)):
            replacement = [current]
            message = "Wrapped one existing value in the required one-item array without changing the value"
        elif target == "object" and isinstance(current, list) and len(current) == 1 and isinstance(current[0], dict):
            replacement = current[0]
            message = "Removed one accidental one-item list wrapper around the required mapping without changing its fields or values"
        if message is not None:
            current = replacement
            repairs.append(RepairRecord("schema_representation_repair", _path(parts), message + "."))

    if isinstance(current, dict) and isinstance(schema, dict):
        properties = schema.get("properties") or {}
        for key in list(current):
            child_schema = properties.get(key)
            if isinstance(child_schema, dict):
                child, child_repairs = _safe_schema_representation_repair(current[key], child_schema, parts + (key,))
                current[key] = child
                repairs.extend(child_repairs)
    elif isinstance(current, list) and isinstance(schema, dict) and isinstance(schema.get("items"), dict):
        item_schema = schema["items"]
        for index, child_value in enumerate(list(current)):
            child, child_repairs = _safe_schema_representation_repair(child_value, item_schema, parts + (index,))
            current[index] = child
            repairs.extend(child_repairs)
    return current, repairs


@dataclass(frozen=True)
class NormalizedReasoningArtifact:
    text: str
    document: Any
    repairs: tuple[RepairRecord, ...]


def normalize_reasoning_artifact(text: str, *, fmt: str, schema: dict[str, Any] | Path | None = None) -> NormalizedReasoningArtifact:
    """Normalize one reasoning model artifact without making clinical decisions."""
    original = str(text)
    try:
        repaired, text_repairs = apply_safe_text_repairs(original, fmt=fmt)
    except WrongStructuredArtifactError as exc:
        return NormalizedReasoningArtifact(
            original,
            {"__reasoning_wrong_artifact__": str(exc)},
            (),
        )
    document, parse_issues = _parse(repaired, fmt)
    if document is None:
        detail = parse_issues[0].message if parse_issues else f"unparseable {fmt}"
        return NormalizedReasoningArtifact(repaired, {"__reasoning_parse_error__": detail}, text_repairs)
    if schema is None:
        return NormalizedReasoningArtifact(repaired, document, text_repairs)
    schema_doc = json.loads(Path(schema).read_text(encoding="utf-8")) if isinstance(schema, Path) else schema
    Draft202012Validator.check_schema(schema_doc)
    if schema_doc.get("type") == "object" and not isinstance(document, dict):
        return NormalizedReasoningArtifact(
            repaired,
            {"__reasoning_wrong_artifact__": f"expected one YAML/JSON mapping but received {type(document).__name__}"},
            text_repairs,
        )
    document, shape_repairs = _safe_schema_representation_repair(document, schema_doc)
    repairs = text_repairs + tuple(shape_repairs)
    if shape_repairs:
        if str(fmt).lower() == "json":
            repaired = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        else:
            repaired = yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=110)
    return NormalizedReasoningArtifact(repaired, document, repairs)


def record_serialization_repair_messages(work: Path, step_id: str, messages: Iterable[str]) -> None:
    """Persist adapter cleanup that occurred inside the provider model runner."""
    repairs = [
        RepairRecord(
            code=_repair_code(str(message)),
            path="$",
            message=str(message)[0].upper() + str(message)[1:] + ".",
        )
        for message in messages
        if str(message)
    ]
    record_serialization_repairs(work, step_id, repairs)


def record_serialization_repairs(work: Path, step_id: str, repairs: Iterable[RepairRecord]) -> None:
    """Persist every automatic reasoning serialization repair for auditability."""
    rows = list(repairs)
    if not rows:
        return
    path = Path(work) / "logs" / "reasoning-serialization-repairs.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if path.is_file():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        existing = list(loaded.get("repairs") or []) if isinstance(loaded, dict) else []
    for row in rows:
        item = {"step_id": str(step_id), "code": row.code, "path": row.path, "message": row.message}
        if item not in existing:
            existing.append(item)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump({"repairs": existing}, sort_keys=False, allow_unicode=True, width=110), encoding="utf-8")
    tmp.replace(path)


def _schema_issues(document: Any, schema: dict[str, Any]) -> list[AuditIssue]:
    validator = Draft202012Validator(schema)
    rows: list[AuditIssue] = []
    errors = sorted(
        validator.iter_errors(document),
        key=lambda err: ([str(x) for x in err.absolute_path], err.validator, err.message),
    )
    for err in errors:
        rows.append(
            AuditIssue(
                code=f"schema_{err.validator}",
                path=_path(err.absolute_path),
                message=err.message,
                fix="Return a complete artifact that satisfies the declared output contract at this location.",
            )
        )
    return rows


def _walk(value: Any, parts: tuple[Any, ...] = ()):
    yield parts, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(child, parts + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, parts + (index,))


def _reference_issues(
    document: Any,
    *,
    case_fact_ids: set[str] | None,
    variant_ids: set[str] | None,
) -> list[AuditIssue]:
    rows: list[AuditIssue] = []
    for parts, value in _walk(document):
        if not parts or not isinstance(value, list):
            continue
        field = parts[-1]
        if field == "case_fact_ids" and case_fact_ids is not None:
            for index, fact_id in enumerate(value):
                if isinstance(fact_id, str) and fact_id not in case_fact_ids:
                    rows.append(
                        AuditIssue(
                            code="unknown_case_fact_id",
                            path=_path(parts + (index,)),
                            message=f"Case fact {fact_id!r} is not present in the supplied structured case.",
                            fix="Reference an existing supplied case fact ID, or remove this unsupported reference; do not invent a patient fact.",
                        )
                    )
        if field == "variant_ids" and variant_ids is not None:
            for index, variant_id in enumerate(value):
                if isinstance(variant_id, str) and variant_id not in variant_ids:
                    rows.append(
                        AuditIssue(
                            code="unknown_variant_id",
                            path=_path(parts + (index,)),
                            message=f"Variant {variant_id!r} is not present in the supplied variant registry.",
                            fix="Reference an existing supplied variant ID, or remove this unsupported reference; do not invent a variant.",
                        )
                    )
    return rows


def _duplicate_id_issues(document: Any) -> list[AuditIssue]:
    if not isinstance(document, dict):
        return []
    rows: list[AuditIssue] = []
    collections = {
        "rules": "rule_id",
        "derived_states": "state_id",
        "criteria": "criterion_id",
        "logic": "logic_id",
    }
    for collection, field in collections.items():
        values = document.get(collection)
        if not isinstance(values, list):
            continue
        seen: dict[str, int] = {}
        for index, row in enumerate(values):
            if not isinstance(row, dict):
                continue
            identifier = row.get(field)
            if not isinstance(identifier, str):
                continue
            if identifier in seen:
                rows.append(
                    AuditIssue(
                        code="duplicate_reasoning_id",
                        path=f"$.{collection}[{index}].{field}",
                        message=f"{field} {identifier!r} duplicates $.{collection}[{seen[identifier]}].{field}.",
                        fix="Give every reasoning object a unique stable ID and update its references consistently.",
                    )
                )
            else:
                seen[identifier] = index
    return rows


def audit_atomic_artifact(
    text: str,
    *,
    fmt: str,
    schema: dict[str, Any] | Path,
    case_fact_ids: Iterable[str] | None = None,
    variant_ids: Iterable[str] | None = None,
) -> AuditResult:
    """Safely repair serialization then collect every discoverable deterministic issue.

    Validation is deliberately exhaustive after parsing: JSON-Schema defects,
    duplicate stable IDs and unknown patient/variant references are accumulated
    before feedback is returned.  If the document cannot be parsed after safe
    repair, downstream checks cannot be evaluated and the parse defect is
    reported explicitly rather than fabricating further errors.
    """
    try:
        repaired, repairs = apply_safe_text_repairs(text, fmt=fmt)
    except WrongStructuredArtifactError as exc:
        issue = AuditIssue(
            code="wrong_artifact_type",
            path="$",
            message=str(exc),
            fix=f"Return exactly one {fmt.upper()} mapping conforming to the declared output contract; do not return Markdown headings, tables, document separators, or prose outside the mapping.",
        )
        return AuditResult(str(text), None, (), (issue,))
    document, issues = _parse(repaired, fmt)
    if document is None:
        return AuditResult(repaired, None, repairs, tuple(issues))
    if isinstance(schema, Path):
        schema = json.loads(schema.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    document, shape_repairs = _safe_schema_representation_repair(document, schema)
    if shape_repairs:
        repairs = repairs + tuple(shape_repairs)
        repaired = (
            json.dumps(document, indent=2, ensure_ascii=False) + "\n"
            if str(fmt).lower() == "json"
            else yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=110)
        )
    issues.extend(_schema_issues(document, schema))
    issues.extend(_duplicate_id_issues(document))
    issues.extend(
        _reference_issues(
            document,
            case_fact_ids=set(case_fact_ids) if case_fact_ids is not None else None,
            variant_ids=set(variant_ids) if variant_ids is not None else None,
        )
    )
    return AuditResult(repaired, document, repairs, tuple(issues))


def render_feedback(issues: Iterable[AuditIssue], repairs: Iterable[RepairRecord] = ()) -> str:
    """Render complete deterministic feedback in plain English for model redo."""
    issue_rows = list(issues)
    repair_rows = list(repairs)
    lines: list[str] = []
    if repair_rows:
        lines.append("Deterministic syntax repairs already applied:")
        for row in repair_rows:
            lines.append(f"- {row.path}: {row.message}")
        lines.append("")
    if not issue_rows:
        lines.append("No deterministic problems were found.")
        return "\n".join(lines) + "\n"
    lines.append(f"The artifact has {len(issue_rows)} deterministic problem{'s' if len(issue_rows) != 1 else ''}. Fix all of them in one complete redo:")
    for index, row in enumerate(issue_rows, start=1):
        lines.extend(
            [
                f"{index}. {row.path}",
                f"   What is wrong: {row.message}",
                f"   What to fix: {row.fix}",
            ]
        )
    lines.append("")
    lines.append("Return the complete corrected artifact, not a patch. Preserve unrelated clinical decisions and all supplied facts/IDs exactly.")
    return "\n".join(lines) + "\n"

# ---------------------------------------------------------------------------
# Phase 2: atomic diagnosis runtime
# ---------------------------------------------------------------------------

DIAGNOSTIC_AUTHORITIES = ("who5", "icc", "second_diagnosis")
_AUTHORITY_PREFIX = {"who5": "W-", "icc": "I-", "second_diagnosis": "S-"}


def _workflow_context(context: dict):
    ctx = context.get("__workflow_context__") if isinstance(context, dict) else None
    if ctx is None:
        raise ValueError("reasoning transform requires workflow context")
    return ctx


def _work(context: dict) -> Path:
    value = context.get("__work__") if isinstance(context, dict) else None
    if value is None and isinstance(context, dict):
        workflow_context = context.get("__workflow_context__")
        value = getattr(workflow_context, "work", None)
    if value is None:
        raise ValueError("reasoning transform requires work directory")
    return Path(value)


def _load_diagnostic_schema(name: str) -> dict:
    path = Path(__file__).resolve().parent / "schemas" / "reasoning" / name
    return json.loads(path.read_text(encoding="utf-8"))


def _contract_issues(value: Any, schema_name: str) -> list[AuditIssue]:
    if isinstance(value, dict) and value.get("__reasoning_wrong_artifact__"):
        return [AuditIssue(
            "wrong_artifact_type", "$",
            str(value.get("__reasoning_wrong_artifact__")),
            "return exactly one YAML mapping conforming to the declared output contract; do not return Markdown headings, tables, document separators, or prose outside the mapping",
        )]
    if isinstance(value, dict) and value.get("__reasoning_parse_error__"):
        return [AuditIssue(
            "malformed_structured_output", "$",
            f"model output could not be parsed as structured YAML/JSON: {value.get('__reasoning_parse_error__')}",
            "return one parseable structured artifact; trivial fences, tabs and other unambiguous serialization defects are repaired deterministically before this audit",
        )]
    return _schema_issues(value, _load_diagnostic_schema(schema_name))


def _yaml(value: Any) -> str:
    return yaml.safe_dump(value, sort_keys=False, allow_unicode=True, width=110)


def _read_owner_artifact(ctx, authority: str) -> dict:
    key = {
        "who5": "diagnosis_who_owner",
        "icc": "diagnosis_icc_owner",
        "second_diagnosis": "diagnosis_second_owner",
    }[authority]
    value = ctx.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"missing diagnostic owner artifact for {authority}: {key}")
    return value


def _owner_pack_key(authority: str) -> str:
    return {
        "who5": "diagnosis_who_pack",
        "icc": "diagnosis_icc_pack",
        "second_diagnosis": "diagnosis_second_pack",
    }[authority]


def _owner_artifact_key(authority: str) -> str:
    return {
        "who5": "diagnosis_who_owner",
        "icc": "diagnosis_icc_owner",
        "second_diagnosis": "diagnosis_second_owner",
    }[authority]


def _authority_from_step(step_id: str) -> str:
    if ".who" in step_id:
        return "who5"
    if ".icc" in step_id:
        return "icc"
    if ".second" in step_id:
        return "second_diagnosis"
    raise ValueError(f"cannot infer diagnostic authority from step {step_id!r}")


def _case_fact_registry(case: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in case.get("case_facts") or []:
        if not isinstance(row, dict):
            continue
        fid = str(row.get("fact_id") or "").strip()
        if fid:
            out[fid] = dict(row)
    return out


def _source_label_for_card(card: dict) -> str | None:
    """Return a deterministic FirstAuthor et al., YEAR label from card metadata.

    Prefer explicit citation metadata when present; fall back to the canonical
    publication/card key.  This is presentation metadata only and never model
    generated.
    """
    import re
    if not isinstance(card, dict):
        return None
    author = card.get("first_author") or card.get("author") or card.get("authors")
    if isinstance(author, list) and author:
        author = author[0]
    if isinstance(author, str) and author.strip():
        author = author.strip().split(",", 1)[0].split()[0]
    else:
        author = None
    year = card.get("year") or card.get("publication_year")
    if year is not None:
        m = re.search(r"(?:19|20)\d{2}", str(year))
        year = m.group(0) if m else None
    if author and year:
        return f"{author} et al., {year}"
    key = str(card.get("publication_key") or card.get("card_id") or "")
    m = re.search(r"(?:^|/)([A-Za-z][A-Za-z-]*)-((?:19|20)\d{2})(?:-|$)", key)
    if m:
        surname = m.group(1).replace("-", " ").title().replace(" ", "-")
        return f"{surname} et al., {m.group(2)}"
    return None


def _candidate_card_envelope(cards: list[dict], manifest: dict) -> list[dict]:
    from workflows.proforma_v1 import card_identity

    tag_by_id = card_identity.tag_by_id(manifest)
    out = []
    for card in cards:
        cid = card.get("card_id")
        token = tag_by_id.get(cid)
        if not token:
            continue
        compact = {
            "card_tag": f"[card:{token}]",
            "card_id": cid,
            "publication_key": card.get("publication_key"),
        }
        for key in (
            "title", "scope", "disease", "diseases", "gene", "genes", "claim",
            "claims", "evidence", "evidence_text", "quote", "quotes", "interpretation",
            "classification", "framework", "frameworks", "notes",
        ):
            value = card.get(key)
            if value not in (None, "", [], {}):
                compact[key] = value
        # Preserve the complete canonical card payload for auditability. The
        # selected convenience fields above keep common content readable, while
        # ``card`` prevents a schema evolution from silently hiding evidence.
        compact["card"] = {k: v for k, v in card.items() if k not in {"card_id"}}
        out.append(compact)
    return out


def prepare_diagnostic_owner(context: dict, params: dict) -> dict:
    """Build one immutable owner pack from structured case + authority card pool."""
    authority = str(params.get("authority") or _authority_from_step(str(params.get("step_id") or "")))
    if authority not in DIAGNOSTIC_AUTHORITIES:
        raise ValueError(f"unsupported diagnostic authority {authority!r}")
    work = _work(context)
    from workflows.proforma_v1 import runtime, self_runtime as sr, step as staged

    case, registry = sr.load_case_registry(work)
    _all_cards, eligible, _digest, manifest = sr.corpus_state(work)
    genes = runtime.case_genes(case)
    history = list(case.get("bootstrap_cmcs") or [])
    if authority == "who5":
        cards = staged._diagnostic_cards(eligible, genes, history, "who5")
    elif authority == "icc":
        cards = staged._diagnostic_cards(eligible, genes, history, "icc")
    else:
        who_cards = staged._diagnostic_cards(eligible, genes, history, "who5")
        icc_cards = staged._diagnostic_cards(eligible, genes, history, "icc")
        by_id = {c.get("card_id"): c for c in [*who_cards, *icc_cards] if c.get("card_id")}
        cards = list(by_id.values())
    return {
        "authority": authority,
        "structured_case": case,
        "case_fact_registry": _case_fact_registry(case),
        "variant_registry": registry,
        "candidate_cards": _candidate_card_envelope(cards, manifest),
        "instructions": {
            "patient_facts_are_immutable": True,
            "rules_require_literature_evidence": True,
            "card_assignments_must_use_candidate_cards": True,
        },
    }


def _walk_id_rows(document: dict):
    for key, field in (("rules", "rule_id"), ("derived_states", "state_id"), ("criteria", "criterion_id"), ("logic", "logic_id")):
        for index, row in enumerate(document.get(key) or []):
            if isinstance(row, dict):
                yield key, index, field, row.get(field)
    proposal = document.get("proposal")
    if isinstance(proposal, dict):
        yield "proposal", None, "proposal_id", proposal.get("proposal_id")


def _internal_reference_issues(document: dict, authority: str, candidate_tags: set[str]) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    rules = {str(x.get("rule_id")) for x in document.get("rules") or [] if isinstance(x, dict) and x.get("rule_id")}
    states = {str(x.get("state_id")) for x in document.get("derived_states") or [] if isinstance(x, dict) and x.get("state_id")}
    criteria = {str(x.get("criterion_id")) for x in document.get("criteria") or [] if isinstance(x, dict) and x.get("criterion_id")}
    logic = {str(x.get("logic_id")) for x in document.get("logic") or [] if isinstance(x, dict) and x.get("logic_id")}
    prefix = _AUTHORITY_PREFIX[authority]
    if document.get("authority") != authority:
        issues.append(AuditIssue("wrong_authority", "$.authority", f"owner returned authority {document.get('authority')!r}, expected {authority!r}", f"set authority to {authority!r}; do not answer for another classifier"))
    proposal = document.get("proposal") or {}
    if authority in {"who5", "icc"} and proposal.get("kind") != "diagnosis":
        issues.append(AuditIssue("wrong_proposal_kind", "$.proposal.kind", "primary classifier owner must return kind 'diagnosis'", "set kind to diagnosis"))
    if authority == "who5" and not isinstance(proposal.get("schema_disease"), str):
        issues.append(AuditIssue("missing_who_schema_disease", "$.proposal.schema_disease", "WHO5 proposal requires a schema_disease", "return the WHO5 schema disease supported by the supplied case and rules"))
    if authority in {"who5", "icc"} and proposal.get("status") != "established":
        issues.append(AuditIssue("invalid_primary_status", "$.proposal.status", "WHO5/ICC owner proposal status must be 'established'", "set status to established; uncertainty belongs in criterion/root status, not a signal bucket"))
    if authority == "second_diagnosis" and proposal.get("kind") != "second_diagnosis":
        issues.append(AuditIssue("wrong_proposal_kind", "$.proposal.kind", "second-diagnosis owner must return kind 'second_diagnosis'", "set kind to second_diagnosis"))
    requires_root = proposal.get("diagnostic_effect") in {"refined", "superseded"} or (authority == "second_diagnosis" and proposal.get("status") == "established")
    if requires_root and document.get("root_id") is None:
        issues.append(AuditIssue("missing_defining_root", "$.root_id", "this proposal changes/establishes a diagnosis but has no defining root", "set root_id to the criterion or logic group that must be met for the proposal"))

    for key, index, field, value in _walk_id_rows(document):
        if isinstance(value, str) and value and not value.startswith(prefix):
            loc = f"$.{key}.{field}" if index is None else f"$.{key}[{index}].{field}"
            issues.append(AuditIssue(
                "wrong_reasoning_namespace", loc,
                f"ID {value!r} is outside the {authority} namespace {prefix!r}",
                f"rename this stable ID with the {prefix} prefix and update all references",
            ))

    for i, criterion in enumerate(document.get("criteria") or []):
        if not isinstance(criterion, dict):
            continue
        for rid in criterion.get("rule_ids") or []:
            if rid not in rules:
                issues.append(AuditIssue("unknown_rule_id", f"$.criteria[{i}].rule_ids", f"unknown rule ID {rid!r}", "reference a rule_id declared in this owner artifact"))
        for sid in criterion.get("state_ids") or []:
            if sid not in states:
                issues.append(AuditIssue("unknown_state_id", f"$.criteria[{i}].state_ids", f"unknown state ID {sid!r}", "reference a state_id declared in this owner artifact"))
    known_logic_members = criteria | logic
    graph: dict[str, list[str]] = {}
    for i, row in enumerate(document.get("logic") or []):
        if not isinstance(row, dict):
            continue
        lid = row.get("logic_id")
        graph[str(lid)] = [str(x) for x in row.get("members") or []]
        for member in row.get("members") or []:
            if member not in known_logic_members:
                issues.append(AuditIssue("unknown_logic_member", f"$.logic[{i}].members", f"unknown logic member {member!r}", "reference a criterion_id or logic_id declared in this owner artifact"))
    root = document.get("root_id")
    if root is not None and root not in known_logic_members:
        issues.append(AuditIssue("unknown_root_id", "$.root_id", f"root_id {root!r} does not resolve", "reference a declared criterion_id or logic_id, or use null when no root is required"))

    # Cycle check over logic-to-logic edges only.
    visiting: set[str] = set(); visited: set[str] = set()
    def visit(node: str, trail: list[str]):
        if node in visited:
            return
        if node in visiting:
            cycle = " -> ".join([*trail, node])
            issues.append(AuditIssue("logic_cycle", "$.logic", f"logic graph contains a cycle: {cycle}", "make the logic graph acyclic"))
            return
        visiting.add(node)
        for member in graph.get(node, []):
            if member in logic:
                visit(member, [*trail, node])
        visiting.discard(node); visited.add(node)
    for node in logic:
        visit(node, [])

    for i, rule in enumerate(document.get("rules") or []):
        if not isinstance(rule, dict):
            continue
        if rule.get("evidence_required") is not True:
            issues.append(AuditIssue("diagnostic_rule_requires_evidence", f"$.rules[{i}].evidence_required", "diagnostic literature/framework rules cannot bypass evidence review", "set evidence_required to true; raw patient facts belong in case_fact_ids, not in rules"))
        tags = rule.get("evidence_card_tags") or []
        for tag in tags:
            if tag not in candidate_tags:
                issues.append(AuditIssue(
                    "card_outside_owner_envelope", f"$.rules[{i}].evidence_card_tags",
                    f"card tag {tag!r} was not supplied to the {authority} owner",
                    "remove it and use only a genuinely supporting card from the supplied candidate_cards; use an empty list if none applies",
                ))
    return issues


def validate_diagnostic_owner(context: dict, params: dict) -> dict:
    authority = str(params.get("authority") or _authority_from_step(str(params.get("step_id") or "")))
    ctx = _workflow_context(context)
    owner = _read_owner_artifact(ctx, authority)
    pack = ctx.get(_owner_pack_key(authority))
    if not isinstance(pack, dict):
        raise ValueError(f"missing owner pack for {authority}")
    schema = _load_diagnostic_schema("diagnostic_owner.json")
    sentinel_issues = _contract_issues(owner, "diagnostic_owner.json") if (
        isinstance(owner, dict) and (owner.get("__reasoning_parse_error__") or owner.get("__reasoning_wrong_artifact__"))
    ) else []
    if sentinel_issues:
        return {
            "authority": authority,
            "status": "fail",
            "issue_count": len(sentinel_issues),
            "feedback": render_feedback(sentinel_issues),
            "issues": [issue.__dict__ for issue in sentinel_issues],
        }
    result = audit_atomic_artifact(
        _yaml(owner), fmt="yaml", schema=schema,
        case_fact_ids=set((pack.get("case_fact_registry") or {}).keys()),
        variant_ids=set((pack.get("variant_registry") or {}).keys()),
    )
    issues = list(result.issues)
    candidate_tags = {str(row.get("card_tag")) for row in pack.get("candidate_cards") or [] if row.get("card_tag")}
    if isinstance(result.document, dict):
        issues.extend(_internal_reference_issues(result.document, authority, candidate_tags))
        proposal = result.document.get("proposal") or {}
        expected_variants = set((pack.get("variant_registry") or {}).keys())
        assessments = proposal.get("variant_assessments") or []
        assessed = [row.get("variant_id") for row in assessments if isinstance(row, dict)]
        missing = sorted(expected_variants - set(assessed))
        duplicate = sorted({vid for vid in assessed if assessed.count(vid) > 1})
        extra = sorted(set(assessed) - expected_variants)
        if missing:
            issues.append(AuditIssue("missing_variant_assessment", "$.proposal.variant_assessments", f"variant assessment(s) missing for {', '.join(missing)}", "return exactly one assessment for every supplied variant"))
        if duplicate:
            issues.append(AuditIssue("duplicate_variant_assessment", "$.proposal.variant_assessments", f"variant assessment(s) duplicated for {', '.join(duplicate)}", "return exactly one assessment for every supplied variant"))
        if extra:
            issues.append(AuditIssue("unknown_variant_assessment", "$.proposal.variant_assessments", f"assessment(s) reference unknown variant(s) {', '.join(extra)}", "remove assessments for variants not in the supplied registry"))
        if authority in {"who5", "icc"}:
            proposed_primary = set(proposal.get("variant_ids") or [])
            assessed_primary = {row.get("variant_id") for row in assessments if isinstance(row, dict) and row.get("classification") == "diagnostic_for_primary"}
            if proposed_primary != assessed_primary:
                issues.append(AuditIssue("diagnostic_variant_mismatch", "$.proposal.variant_ids", f"proposal.variant_ids {sorted(proposed_primary)} does not match diagnostic_for_primary assessments {sorted(assessed_primary)}", "make the proposal variant list and per-variant diagnostic_for_primary classifications agree exactly"))
        if authority == "second_diagnosis" and proposal.get("status") == "none" and proposal.get("variant_ids"):
            issues.append(AuditIssue("second_diagnosis_none_has_variants", "$.proposal.variant_ids", "a second-diagnosis status of none still lists diagnostic variants", "use an empty variant_ids list when no second diagnosis is proposed"))
        for index, row in enumerate(assessments):
            if not isinstance(row, dict):
                continue
            other = row.get("other_pathology")
            classification = row.get("classification")
            if classification == "diagnostic_for_other_pathology" and not isinstance(other, str):
                issues.append(AuditIssue("missing_other_pathology", f"$.proposal.variant_assessments[{index}].other_pathology", "diagnostic_for_other_pathology assessment has no pathology label", "supply the proposed other pathology label"))
            if classification != "diagnostic_for_other_pathology" and other is not None:
                issues.append(AuditIssue("unexpected_other_pathology", f"$.proposal.variant_assessments[{index}].other_pathology", "other_pathology must be null unless classification is diagnostic_for_other_pathology", "set other_pathology to null or correct the classification"))
    feedback = render_feedback(issues, result.repairs)
    return {
        "authority": authority,
        "status": "pass" if not issues else "fail",
        "issue_count": len(issues),
        "feedback": feedback,
        "issues": [issue.__dict__ for issue in issues],
    }


def build_diagnostic_registry(context: dict, params: dict) -> dict:
    ctx = _workflow_context(context)
    owners = {authority: _read_owner_artifact(ctx, authority) for authority in DIAGNOSTIC_AUTHORITIES}
    rules = []
    states = []
    criteria = []
    logic = []
    proposals = {}
    for authority, owner in owners.items():
        proposals[authority] = owner.get("proposal")
        for row in owner.get("rules") or []:
            rules.append({"authority": authority, **row})
        for row in owner.get("derived_states") or []:
            states.append({"authority": authority, **row})
        for row in owner.get("criteria") or []:
            criteria.append({"authority": authority, **row})
        for row in owner.get("logic") or []:
            logic.append({"authority": authority, **row})
    return {
        "schema_version": 1,
        "proposals": proposals,
        "rules": rules,
        "derived_states": states,
        "criteria": criteria,
        "logic": logic,
        "roots": {a: owners[a].get("root_id") for a in DIAGNOSTIC_AUTHORITIES},
        "reasons": {a: owners[a].get("reason") for a in DIAGNOSTIC_AUTHORITIES},
    }


def collect_diagnostic_owner_assignments(context: dict, params: dict) -> dict:
    ctx = _workflow_context(context)
    registry = ctx.get("diagnostic_atomic_registry") or {}
    pairs = []
    rescue = []
    for rule in registry.get("rules") or []:
        if not rule.get("evidence_required"):
            continue
        authority = rule["authority"]
        pack = ctx.get(_owner_pack_key(authority)) or {}
        card_by_tag = {row.get("card_tag"): row for row in pack.get("candidate_cards") or []}
        tags = [tag for tag in rule.get("evidence_card_tags") or [] if tag in card_by_tag]
        if tags:
            for tag in tags:
                pairs.append({
                    "authority": authority,
                    "rule_id": rule["rule_id"],
                    "statement": rule["statement"],
                    "card_tag": tag,
                    "card": card_by_tag[tag],
                    "source": "owner",
                })
        else:
            rescue.append({
                "authority": authority,
                "rule_id": rule["rule_id"],
                "statement": rule["statement"],
                "candidate_cards": list(card_by_tag.values()),
            })
    return {"pairs": pairs, "rescue_items": rescue}


def prepare_diagnostic_rescue(context: dict, params: dict) -> list[dict]:
    ctx = _workflow_context(context)
    state = ctx.get("diagnostic_owner_assignments") or {}
    return list(state.get("rescue_items") or [])


def validate_diagnostic_rescue(context: dict, params: dict) -> dict:
    ctx = _workflow_context(context)
    rescue_items = ctx.get("diagnostic_rescue_items") or []
    output = ctx.get("diagnostic_rescue_assignments")
    if not rescue_items:
        return {"status": "pass", "issue_count": 0, "feedback": "No rescue matching was required.\n", "issues": []}
    issues: list[AuditIssue] = []
    if output is not None:
        issues.extend(_contract_issues(output, "diagnostic_evidence_assignment.json"))
    if not isinstance(output, dict):
        issues.append(AuditIssue("missing_rescue_output", "$", "rescue matching output is missing", "return one assignment row for every supplied rescue rule"))
        rows = []
    else:
        rows = output.get("assignments") or []
    by_rule = {item["rule_id"]: item for item in rescue_items}
    seen: set[str] = set()
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            issues.append(AuditIssue("invalid_assignment_row", f"$.assignments[{i}]", "assignment row is not a mapping", "return rule_id and card_tags")); continue
        rid = row.get("rule_id")
        if rid not in by_rule:
            issues.append(AuditIssue("unknown_rescue_rule", f"$.assignments[{i}].rule_id", f"unknown rescue rule {rid!r}", "use one of the supplied rescue rule IDs")); continue
        if rid in seen:
            issues.append(AuditIssue("duplicate_rescue_rule", f"$.assignments[{i}].rule_id", f"rule {rid!r} appears more than once", "return exactly one row per rescue rule"))
        seen.add(rid)
        allowed = {c.get("card_tag") for c in by_rule[rid].get("candidate_cards") or []}
        for tag in row.get("card_tags") or []:
            if tag not in allowed:
                issues.append(AuditIssue("rescue_card_outside_envelope", f"$.assignments[{i}].card_tags", f"card {tag!r} is outside the rule's candidate envelope", "remove the card or choose a genuinely supporting supplied candidate card"))
    for rid in sorted(set(by_rule) - seen):
        issues.append(AuditIssue("missing_rescue_rule", "$.assignments", f"no assignment row was returned for {rid}", "return one row for this rule; card_tags may be empty when no supplied card supports it"))
    return {"status": "pass" if not issues else "fail", "issue_count": len(issues), "feedback": render_feedback(issues), "issues": [x.__dict__ for x in issues]}


def merge_diagnostic_assignments(context: dict, params: dict) -> dict:
    ctx = _workflow_context(context)
    state = ctx.get("diagnostic_owner_assignments") or {}
    pairs = list(state.get("pairs") or [])
    rescue_items = {row["rule_id"]: row for row in state.get("rescue_items") or []}
    rescue = ctx.get("diagnostic_rescue_assignments") or {"assignments": []}
    for row in rescue.get("assignments") or []:
        rid = row.get("rule_id")
        item = rescue_items.get(rid)
        if not item:
            continue
        card_by_tag = {c.get("card_tag"): c for c in item.get("candidate_cards") or []}
        for tag in row.get("card_tags") or []:
            if tag in card_by_tag:
                pairs.append({
                    "authority": item["authority"], "rule_id": rid, "statement": item["statement"],
                    "card_tag": tag, "card": card_by_tag[tag], "source": "rescue",
                })
    assigned = {row["rule_id"] for row in pairs}
    all_rules = [row for row in (ctx.get("diagnostic_atomic_registry") or {}).get("rules") or [] if row.get("evidence_required")]
    unassigned = [row["rule_id"] for row in all_rules if row["rule_id"] not in assigned]
    return {"pairs": pairs, "unassigned_rule_ids": unassigned}


def prepare_diagnostic_evidence_audit(context: dict, params: dict) -> list[dict]:
    ctx = _workflow_context(context)
    return [
        {
            "authority": row["authority"], "rule_id": row["rule_id"], "statement": row["statement"],
            "card_tag": row["card_tag"], "card": row["card"],
        }
        for row in (ctx.get("diagnostic_assignments") or {}).get("pairs") or []
    ]


def validate_diagnostic_evidence_audit(context: dict, params: dict) -> dict:
    ctx = _workflow_context(context)
    expected = ctx.get("diagnostic_evidence_audit_items") or []
    output = ctx.get("diagnostic_evidence_audit") or {}
    rows = output.get("audits") or [] if isinstance(output, dict) else []
    issues: list[AuditIssue] = []
    if output:
        issues.extend(_contract_issues(output, "diagnostic_evidence_audit.json"))
    expected_keys = {(x["rule_id"], x["card_tag"]) for x in expected}
    seen: set[tuple[str, str]] = set()
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            issues.append(AuditIssue("invalid_audit_row", f"$.audits[{i}]", "audit row is not a mapping", "return rule_id, card_tag, supports_rule and comments")); continue
        key = (row.get("rule_id"), row.get("card_tag"))
        if key not in expected_keys:
            issues.append(AuditIssue("unknown_audit_pair", f"$.audits[{i}]", f"unexpected rule/card pair {key!r}", "audit only the supplied rule/card pairs")); continue
        if key in seen:
            issues.append(AuditIssue("duplicate_audit_pair", f"$.audits[{i}]", f"rule/card pair {key!r} appears more than once", "return exactly one audit row per pair"))
        seen.add(key)
    for key in sorted(expected_keys - seen):
        issues.append(AuditIssue("missing_audit_pair", "$.audits", f"no audit row was returned for rule/card pair {key!r}", "audit this pair before returning the artifact"))
    return {"status": "pass" if not issues else "fail", "issue_count": len(issues), "feedback": render_feedback(issues), "issues": [x.__dict__ for x in issues]}


def build_diagnostic_disputes(context: dict, params: dict) -> list[dict]:
    ctx = _workflow_context(context)
    items = {(x["rule_id"], x["card_tag"]): x for x in ctx.get("diagnostic_evidence_audit_items") or []}
    audit = ctx.get("diagnostic_evidence_audit") or {}
    disputes = []
    for row in audit.get("audits") or []:
        if row.get("supports_rule") is False:
            item = items.get((row.get("rule_id"), row.get("card_tag")))
            if item:
                disputes.append({**item, "audit_comments": row.get("comments") or []})
    return disputes


def finalize_diagnostic_evidence(context: dict, params: dict) -> dict:
    ctx = _workflow_context(context)
    audit = ctx.get("diagnostic_evidence_audit") or {}
    adjud = ctx.get("diagnostic_evidence_adjudication") or {"adjudications": []}
    adjud_by = {(r.get("rule_id"), r.get("card_tag")): r for r in adjud.get("adjudications") or []}
    pairs = []
    rule_support: dict[str, bool] = {}
    for row in audit.get("audits") or []:
        key = (row.get("rule_id"), row.get("card_tag"))
        final = bool(row.get("supports_rule"))
        if not final and key in adjud_by:
            final = bool(adjud_by[key].get("supports_rule"))
        pairs.append({"rule_id": key[0], "card_tag": key[1], "supports_rule": final})
        rule_support[key[0]] = bool(rule_support.get(key[0])) or final
    registry = ctx.get("diagnostic_atomic_registry") or {}
    for rule in registry.get("rules") or []:
        if not rule.get("evidence_required"):
            rule_support.setdefault(rule["rule_id"], True)
        else:
            rule_support.setdefault(rule["rule_id"], False)
    return {"pairs": pairs, "rule_support": rule_support}


def prepare_diagnostic_reasoning_audit(context: dict, params: dict) -> dict:
    ctx = _workflow_context(context)
    registry = ctx.get("diagnostic_atomic_registry") or {}
    evidence = ctx.get("diagnostic_evidence_decisions") or {}
    support = evidence.get("rule_support") or {}
    packs = {a: ctx.get(_owner_pack_key(a)) or {} for a in DIAGNOSTIC_AUTHORITIES}
    # Owners reason with source-facing IDs (V1, V2, ...), while the compiled
    # graph deliberately uses canonical internal IDs (v01, v02, ...).  The
    # reasoning auditor therefore needs the canonical registry, not the
    # model-facing owner-pack projection.
    try:
        from workflows.proforma_v1 import self_runtime as sr
        _case, internal_variants = sr.load_case_registry(_work(context))
    except Exception:
        internal_variants = {}
    items = []
    for authority in DIAGNOSTIC_AUTHORITIES:
        owner = _read_owner_artifact(ctx, authority)
        facts = packs[authority].get("case_fact_registry") or {}
        variants = internal_variants
        states = {s.get("state_id"): s for s in owner.get("derived_states") or []}
        for state in states.values():
            items.append({
                "item_type": "derived_state", "authority": authority, "state": state,
                "case_facts": [facts[x] for x in state.get("case_fact_ids") or [] if x in facts],
                "variants": {x: variants[x] for x in state.get("variant_ids") or [] if x in variants},
            })
        for criterion in owner.get("criteria") or []:
            approved = [rid for rid in criterion.get("rule_ids") or [] if support.get(rid)]
            if len(approved) != len(criterion.get("rule_ids") or []):
                continue
            rules = [r for r in registry.get("rules") or [] if r.get("rule_id") in approved]
            items.append({
                "item_type": "criterion", "authority": authority, "criterion": criterion,
                "rules": rules,
                "case_facts": [facts[x] for x in criterion.get("case_fact_ids") or [] if x in facts],
                "variants": {x: variants[x] for x in criterion.get("variant_ids") or [] if x in variants},
                "derived_states": [states[x] for x in criterion.get("state_ids") or [] if x in states],
            })
    return items


def validate_diagnostic_reasoning_audit(context: dict, params: dict) -> dict:
    ctx = _workflow_context(context)
    prepared = ctx.get("diagnostic_reasoning_items") or []
    output = ctx.get("diagnostic_reasoning_audit") or {}
    expected_states = {x["state"]["state_id"] for x in prepared if x.get("item_type") == "derived_state"}
    expected_criteria = {x["criterion"]["criterion_id"] for x in prepared if x.get("item_type") == "criterion"}
    state_rows = output.get("derived_states") or [] if isinstance(output, dict) else []
    criterion_rows = output.get("criteria") or [] if isinstance(output, dict) else []
    issues: list[AuditIssue] = []
    if output:
        issues.extend(_contract_issues(output, "reasoning_audit.json"))
    def check(rows, expected, field, base):
        seen = set()
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                issues.append(AuditIssue("invalid_reasoning_row", f"$.{base}[{i}]", "reasoning row is not a mapping", f"return a valid {base} row")); continue
            value = row.get(field)
            if value not in expected:
                issues.append(AuditIssue("unknown_reasoning_id", f"$.{base}[{i}].{field}", f"unexpected ID {value!r}", "assess only the supplied reasoning items")); continue
            if value in seen:
                issues.append(AuditIssue("duplicate_reasoning_result", f"$.{base}[{i}].{field}", f"ID {value!r} appears more than once", "return exactly one result for each supplied item"))
            seen.add(value)
        for missing in sorted(expected - seen):
            issues.append(AuditIssue("missing_reasoning_result", f"$.{base}", f"no result was returned for {missing}", "assess this supplied item before returning the artifact"))
    check(state_rows, expected_states, "state_id", "derived_states")
    check(criterion_rows, expected_criteria, "criterion_id", "criteria")
    return {"status": "pass" if not issues else "fail", "issue_count": len(issues), "feedback": render_feedback(issues), "issues": [x.__dict__ for x in issues]}


def _logic_status(operator: str, statuses: list[str]) -> str:
    if operator == "all_of":
        if any(x == "not_met" for x in statuses): return "not_met"
        if statuses and all(x == "met" for x in statuses): return "met"
        return "unknown"
    if operator == "any_of":
        if any(x == "met" for x in statuses): return "met"
        if statuses and all(x == "not_met" for x in statuses): return "not_met"
        return "unknown"
    return "unknown"


def evaluate_diagnoses(context: dict, params: dict) -> dict:
    ctx = _workflow_context(context)
    evidence = ctx.get("diagnostic_evidence_decisions") or {}
    support = evidence.get("rule_support") or {}
    reasoning = ctx.get("diagnostic_reasoning_audit") or {}
    criterion_results = {r.get("criterion_id"): r.get("status") for r in reasoning.get("criteria") or []}
    state_results = {r.get("state_id"): r for r in reasoning.get("derived_states") or [] if isinstance(r, dict)}
    owners = {a: _read_owner_artifact(ctx, a) for a in DIAGNOSTIC_AUTHORITIES}
    owner_status = {}; feedback = {}; detail = {}
    for authority, owner in owners.items():
        criterion_status = {}
        problems = []
        owner_states = {s.get("state_id"): s for s in owner.get("derived_states") or [] if isinstance(s, dict)}
        owner_rules = {r.get("rule_id"): r for r in owner.get("rules") or [] if isinstance(r, dict)}
        reasoning_rows = {r.get("criterion_id"): r for r in reasoning.get("criteria") or [] if isinstance(r, dict)}
        for criterion in owner.get("criteria") or []:
            cid = criterion.get("criterion_id")
            unsupported = [rid for rid in criterion.get("rule_ids") or [] if not support.get(rid, False)]
            bad_states = []
            for sid in criterion.get("state_ids") or []:
                proposed = (owner_states.get(sid) or {}).get("proposed_value")
                audited = state_results.get(sid) or {}
                if audited.get("status") != "supported" or audited.get("value") != proposed:
                    bad_states.append(sid)
            if unsupported:
                status = "unknown"
                details = "; ".join(f"{rid}: {(owner_rules.get(rid) or {}).get('statement', 'rule text unavailable')}" for rid in unsupported)
                problems.append(f"{cid}: literature rule support failed ({details}). Remove/rewrite unsupported rules or assign genuinely supporting supplied evidence; do not preserve the same conclusion by weakening the criterion.")
            elif bad_states:
                status = "unknown"
                details = "; ".join(f"{sid}: {(owner_states.get(sid) or {}).get('label')} proposed={(owner_states.get(sid) or {}).get('proposed_value')!r}" for sid in bad_states)
                problems.append(f"{cid}: required derived state support failed ({details}). Reassess the patient-specific state from the supplied facts before applying the rule.")
            else:
                status = criterion_results.get(cid, "unknown")
                if status != "met":
                    comments = "; ".join((reasoning_rows.get(cid) or {}).get("comments") or [])
                    suffix = f" Auditor comments: {comments}" if comments else ""
                    problems.append(f"{cid}: patient applicability was {status}, not met.{suffix} Reassess the proposal against the supplied patient facts; do not alter those facts.")
            criterion_status[cid] = status
        logic_status = {}
        pending = list(owner.get("logic") or [])
        for _ in range(len(pending) + 1):
            progressed = False
            for row in list(pending):
                members = row.get("members") or []
                if all(m in criterion_status or m in logic_status for m in members):
                    statuses = [criterion_status.get(m, logic_status.get(m, "unknown")) for m in members]
                    logic_status[row["logic_id"]] = _logic_status(row.get("operator"), statuses)
                    pending.remove(row); progressed = True
            if not progressed: break
        for row in pending:
            logic_status[row.get("logic_id")] = "unknown"
            problems.append(f"{row.get('logic_id')}: logic could not be fully evaluated from audited members.")
        root = owner.get("root_id")
        root_status = criterion_status.get(root, logic_status.get(root, "unknown")) if root else None
        proposal = owner.get("proposal") or {}
        requires_root = (
            proposal.get("diagnostic_effect") in {"refined", "superseded"}
            or (authority == "second_diagnosis" and proposal.get("status") == "established")
        )
        passed = (root_status == "met") if requires_root else (root_status != "not_met" if root else True)
        owner_status[authority] = "pass" if passed else "fail"
        if not passed and not problems:
            problems.append(f"The defining diagnostic root {root!r} evaluated as {root_status or 'unknown'}, not met.")
        feedback[authority] = (
            "No semantic correction is required.\n" if passed else
            "The proposed diagnosis is not supported by the complete audited reasoning graph. Fix all of the following in one redo without altering supplied patient facts:\n- " + "\n- ".join(problems) + "\n"
        )
        detail[authority] = {"criterion_status": criterion_status, "logic_status": logic_status, "root_id": root, "root_status": root_status, "problems": problems}
    return {"owner_status": owner_status, "feedback": feedback, "detail": detail}


def owner_review(context: dict, params: dict) -> dict:
    authority = str(params.get("authority") or _authority_from_step(str(params.get("step_id") or "")))
    ctx = _workflow_context(context)
    evaluation = ctx.get("diagnostic_evaluation") or {}
    return {
        "authority": authority,
        "status": (evaluation.get("owner_status") or {}).get(authority, "fail"),
        "feedback": (evaluation.get("feedback") or {}).get(authority, "Diagnostic evaluation did not produce feedback.\n"),
    }


def _fallback_variant_assessments(registry: dict) -> list[dict]:
    return [
        {"variant_id": vid, "classification": "nonspecific", "other_pathology": None, "reason": "No audited diagnosis-defining conclusion was committed for this variant."}
        for vid in sorted(registry)
    ]


def finalize_reasoning_diagnosis(context: dict, params: dict) -> dict:
    """Commit audited owner results; fail closed to supplied provisional disease.

    This also emits WHO/ICC compatibility artifacts so the still-default PTBG
    tail can be exercised during Phase 2. Phase 3 replaces that compatibility
    bridge with native reasoning PTBG inputs.
    """
    ctx = _workflow_context(context)
    work = _work(context)
    from workflows.proforma_v1 import runtime, step as staged

    who = _read_owner_artifact(ctx, "who5")
    icc = _read_owner_artifact(ctx, "icc")
    second = _read_owner_artifact(ctx, "second_diagnosis")
    evaluation = ctx.get("diagnostic_evaluation") or {}
    statuses = evaluation.get("owner_status") or {}
    who_pack = ctx.get("diagnosis_who_pack") or {}
    case = who_pack.get("structured_case") or {}
    registry = who_pack.get("variant_registry") or {}
    provisional = str(case.get("provisional_disease") or "myeloid neoplasm, unspecified")
    bootstrap = [str(x) for x in case.get("bootstrap_cmcs") or [] if str(x).strip()]
    fallback_schema = runtime.vocab.canonical_case_disease(provisional)
    if not fallback_schema and len(bootstrap) == 1:
        fallback_schema = bootstrap[0]
    if statuses.get("who5") != "pass" and not fallback_schema:
        raise ValueError("audited WHO diagnosis was not supported and the supplied provisional diagnosis cannot be deterministically mapped to a schema disease")
    if statuses.get("who5") != "pass" and case.get("morphologic_diagnosis_origin") not in {None, "supplied"}:
        raise ValueError("audited WHO diagnosis was not supported and the starting diagnosis was inferred; no deterministic fallback diagnosis is available")
    fallback_schema = fallback_schema or "no_haematological_malignancy"

    def legacy(owner, authority):
        proposal = owner.get("proposal") or {}
        passed = statuses.get(authority) == "pass"
        if passed:
            result = {
                "diagnosis": proposal.get("label") or provisional,
                "variants": list(proposal.get("variant_ids") or []),
                "diagnostic_effect": proposal.get("diagnostic_effect") or "unchanged",
                "reason": owner.get("reason") or "Audited atomic diagnostic reasoning.",
                "variant_assessments": list(proposal.get("variant_assessments") or _fallback_variant_assessments(registry)),
            }
            if authority == "who5":
                result["schema_disease"] = proposal.get("schema_disease") or fallback_schema
            elif proposal.get("schema_disease") == "no_haematological_malignancy":
                result["schema_disease"] = "no_haematological_malignancy"
            return result
        result = {
            "diagnosis": provisional,
            "variants": [],
            "diagnostic_effect": "unchanged",
            "reason": "The proposed molecular refinement was not committed because its audited diagnostic reasoning was not fully supported.",
            "variant_assessments": _fallback_variant_assessments(registry),
        }
        if authority == "who5": result["schema_disease"] = fallback_schema
        elif fallback_schema == "no_haematological_malignancy": result["schema_disease"] = fallback_schema
        return result

    who_legacy = legacy(who, "who5")
    icc_legacy = legacy(icc, "icc")
    concurrent = []
    second_proposal = second.get("proposal") or {}
    if statuses.get("second_diagnosis") == "pass" and second_proposal.get("status") == "established":
        second_variants = list(second_proposal.get("variant_ids") or [])
        concurrent.append({
            "variant_id": second_variants[0] if second_variants else None,
            "other_pathology": second_proposal.get("label"),
            "reason": second.get("reason"),
        })
        # Temporary Phase-2 compatibility projection for the unchanged PTBG tail:
        # legacy finalize_diagnosis derives concurrent pathology from WHO variant
        # assessments. Preserve the independently audited second diagnosis there
        # only when doing so does not overwrite a primary-diagnostic assignment.
        by_variant = {row.get("variant_id"): row for row in who_legacy.get("variant_assessments") or [] if isinstance(row, dict)}
        for vid in second_variants:
            row = by_variant.get(vid)
            if row is not None and row.get("classification") != "diagnostic_for_primary":
                row["classification"] = "diagnostic_for_other_pathology"
                row["other_pathology"] = second_proposal.get("label")
                row["reason"] = second.get("reason") or row.get("reason")
    relationship = "same" if str(who_legacy["diagnosis"]).strip().lower() == str(icc_legacy["diagnosis"]).strip().lower() else "different"
    diagnosis = {"who5": who_legacy, "icc": icc_legacy, "concurrent_pathology": concurrent, "relationship": relationship}
    for authority, label in (("who5", "WHO5"), ("icc", "ICC"), ("second_diagnosis", "second diagnosis")):
        if statuses.get(authority) == "pass":
            continue
        owner = {"who5": who, "icc": icc, "second_diagnosis": second}[authority]
        issue_key = f"reasoning-{authority}-unsupported"
        staged._semantic_dissent(
            work, issue_key=issue_key, stage=f"Reasoning {label} audit",
            reviewed_text=f"Proposed {label}: {(owner.get('proposal') or {}).get('label')}",
            dissent_reason=(evaluation.get("feedback") or {}).get(authority) or "The atomic reasoning graph did not support the proposal.",
            action_recommended="Do not commit the unsupported proposal; use the deterministic fallback or suppress the unestablished second diagnosis.",
        )
        staged._semantic_dissent_address(
            work, issue_key=issue_key, stage="Reasoning diagnostic finalization",
            action="Reject unsupported diagnostic proposal after the bounded owner redo was exhausted.",
            outcome=(f"Committed fallback diagnosis: {who_legacy.get('diagnosis')}" if authority == "who5" else f"Final status: {statuses.get(authority)}"),
            status="resolved",
        )

    def write_compat(group, name, value):
        path = staged._existing_or_new(work, group, name)
        path.write_text(yaml.safe_dump(value, sort_keys=False, allow_unicode=True, width=110), encoding="utf-8")
    write_compat("diagnosis_who5_pass_1", "who5.yaml", who_legacy)
    write_compat("diagnosis_icc", "icc.yaml", icc_legacy)
    write_compat("diagnosis", "diagnosis-final.yaml", diagnosis)
    return diagnosis


def run_diagnostic_transform(name: str, context: dict, params: dict) -> Any:
    dispatch = {
        "reasoning_prepare_diagnostic_owner": prepare_diagnostic_owner,
        "reasoning_validate_diagnostic_owner": validate_diagnostic_owner,
        "reasoning_build_diagnostic_registry": build_diagnostic_registry,
        "reasoning_collect_diagnostic_owner_assignments": collect_diagnostic_owner_assignments,
        "reasoning_prepare_diagnostic_rescue": prepare_diagnostic_rescue,
        "reasoning_validate_diagnostic_rescue": validate_diagnostic_rescue,
        "reasoning_merge_diagnostic_assignments": merge_diagnostic_assignments,
        "reasoning_prepare_diagnostic_evidence_audit": prepare_diagnostic_evidence_audit,
        "reasoning_validate_diagnostic_evidence_audit": validate_diagnostic_evidence_audit,
        "reasoning_build_diagnostic_disputes": build_diagnostic_disputes,
        "reasoning_finalize_diagnostic_evidence": finalize_diagnostic_evidence,
        "reasoning_prepare_diagnostic_reasoning_audit": prepare_diagnostic_reasoning_audit,
        "reasoning_validate_diagnostic_reasoning_audit": validate_diagnostic_reasoning_audit,
        "reasoning_evaluate_diagnoses": evaluate_diagnoses,
        "reasoning_owner_review": owner_review,
        "reasoning_finalize_atomic_diagnosis": finalize_reasoning_diagnosis,
    }
    try:
        fn = dispatch[name]
    except KeyError as exc:
        raise ValueError(f"unknown reasoning diagnostic transform {name!r}") from exc
    return fn(context, params)

# Adjudication completeness validator is defined after the main dispatcher for
# readability; the dispatcher is extended below by name aliasing in transforms.
def validate_diagnostic_adjudication(context: dict, params: dict) -> dict:
    ctx = _workflow_context(context)
    disputes = ctx.get("diagnostic_evidence_disputes") or []
    output = ctx.get("diagnostic_evidence_adjudication") or {}
    rows = output.get("adjudications") or [] if isinstance(output, dict) else []
    expected = {(x.get("rule_id"), x.get("card_tag")) for x in disputes}
    issues: list[AuditIssue] = []
    if output:
        issues.extend(_contract_issues(output, "diagnostic_evidence_adjudication.json"))
    seen = set()
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            issues.append(AuditIssue("invalid_adjudication_row", f"$.adjudications[{i}]", "adjudication row is not a mapping", "return rule_id, card_tag, supports_rule and reason")); continue
        key = (row.get("rule_id"), row.get("card_tag"))
        if key not in expected:
            issues.append(AuditIssue("unknown_adjudication_pair", f"$.adjudications[{i}]", f"unexpected dispute pair {key!r}", "adjudicate only the supplied disputes")); continue
        if key in seen:
            issues.append(AuditIssue("duplicate_adjudication_pair", f"$.adjudications[{i}]", f"dispute pair {key!r} appears more than once", "return exactly one adjudication per dispute"))
        seen.add(key)
    for key in sorted(expected - seen):
        issues.append(AuditIssue("missing_adjudication_pair", "$.adjudications", f"no adjudication was returned for {key!r}", "adjudicate this disputed pair before returning the artifact"))
    return {"status": "pass" if not issues else "fail", "issue_count": len(issues), "feedback": render_feedback(issues), "issues": [x.__dict__ for x in issues]}

# Extend the dispatcher without duplicating the large function above.
_run_diagnostic_transform_base = run_diagnostic_transform
def run_diagnostic_transform(name: str, context: dict, params: dict) -> Any:
    if name == "reasoning_validate_diagnostic_adjudication":
        return validate_diagnostic_adjudication(context, params)
    return _run_diagnostic_transform_base(name, context, params)

# ---------------------------------------------------------------------------
# Phase 3: atomic PTBG, decision provenance and human-facing dissent
# ---------------------------------------------------------------------------
PTBG_DOMAINS = ("prognosis", "treatment", "biomarker", "germline")
PTBG_PREFIX = {"prognosis": "P-", "treatment": "T-", "biomarker": "B-", "germline": "G-"}
TERMINAL_DISPOSITIONS = ("kept", "revised", "dropped", "unresolved", "not_reportable")


def _ptbg_domain_from_step(step_id: str) -> str:
    text = str(step_id or "")
    for domain in PTBG_DOMAINS:
        if text == domain or text.startswith(domain + ".") or f".{domain}." in text:
            return domain
    raise ValueError(f"cannot infer PTBG domain from step {step_id!r}")


def _ptbg_pack_key(domain: str) -> str:
    return f"{domain}_reasoning_pack"


def _ptbg_owner_key(domain: str) -> str:
    return f"{domain}_reasoning_owner"


def _ptbg_review_key(domain: str) -> str:
    return f"{domain}_reasoning_review"


def _fact_scalar(row: dict | None):
    if not isinstance(row, dict):
        return None
    for key in ("value", "fact", "text", "statement", "result", "description"):
        if key in row:
            return row.get(key)
    return None


def _ptbg_owner(context: dict, domain: str) -> dict:
    ctx = _workflow_context(context)
    value = ctx.get(_ptbg_owner_key(domain))
    return value if isinstance(value, dict) else {}


def prepare_ptbg_owner(context: dict, params: dict) -> dict:
    """Prepare one domain owner without importing any other PTBG owner's prose."""
    ctx = _workflow_context(context)
    domain = str(params.get("domain") or _ptbg_domain_from_step(str(params.get("step_id") or "")))
    if domain not in PTBG_DOMAINS:
        raise ValueError(f"unsupported PTBG domain {domain!r}")
    work = _work(context)
    from workflows.proforma_v1 import runtime, self_runtime as sr, step as staged

    case, registry = sr.load_case_registry(work)
    _all_cards, eligible, _digest, manifest = sr.corpus_state(work)
    diagnosis = ctx.get("diagnosis") or {}
    disease = ((diagnosis.get("who5") or {}).get("schema_disease") if isinstance(diagnosis, dict) else None)
    if not disease:
        path = sr.output_path(work, "diagnosis", "diagnosis-final.yaml")
        if path.is_file():
            diagnosis = sr.read_yaml(path)
            disease = (diagnosis.get("who5") or {}).get("schema_disease")
    if not disease:
        raise ValueError(f"{domain} owner requires an authoritative WHO5 schema disease")
    cards = staged._draw_domain_cards(eligible, domain, runtime.case_genes(case), [disease])
    return {
        "domain": domain,
        "structured_case": case,
        "case_fact_registry": _case_fact_registry(case),
        "variant_registry": registry,
        "authoritative_diagnosis": {
            "who5": (diagnosis.get("who5") or {}),
            "icc": (diagnosis.get("icc") or {}),
            "concurrent_pathology": list(diagnosis.get("concurrent_pathology") or []),
        },
        "candidate_cards": _candidate_card_envelope(cards, manifest),
        "instructions": {
            "patient_facts_are_immutable": True,
            "literature_rules_require_audited_evidence": True,
            "direct_applicability_requires_exact_fact_value": True,
            "derived_states_are_optional": True,
        },
    }


def _ptbg_owner_reference_issues(document: dict, domain: str, pack: dict) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    prefix = PTBG_PREFIX[domain]
    facts = set((pack.get("case_fact_registry") or {}).keys())
    variants = set((pack.get("variant_registry") or {}).keys())
    envelope = {x.get("card_tag") for x in pack.get("candidate_cards") or [] if isinstance(x, dict)}
    all_ids: set[str] = set()

    def add_id(value, path, kind):
        value = str(value or "")
        if not value.startswith(prefix):
            issues.append(AuditIssue("wrong_reasoning_namespace", path, f"{kind} ID {value!r} does not use the {prefix} namespace", f"rename the ID with the {prefix} prefix and update its references"))
        if value in all_ids:
            issues.append(AuditIssue("duplicate_reasoning_id", path, f"ID {value!r} is used more than once", "use one unique stable ID for each atomic object"))
        all_ids.add(value)

    propositions = document.get("propositions") or [] if isinstance(document, dict) else []
    for pi, prop in enumerate(propositions):
        if not isinstance(prop, dict):
            continue
        base = f"$.propositions[{pi}]"
        add_id(prop.get("proposition_id"), f"{base}.proposition_id", "proposition")
        for vi, vid in enumerate(prop.get("variant_ids") or []):
            if vid not in variants:
                issues.append(AuditIssue("unknown_variant_id", f"{base}.variant_ids[{vi}]", f"variant ID {vid!r} is not present in the structured case", "reference only supplied variant IDs"))
        rules = {r.get("rule_id"): r for r in prop.get("rules") or [] if isinstance(r, dict)}
        states = {s.get("state_id"): s for s in prop.get("derived_states") or [] if isinstance(s, dict)}
        apps = {a.get("application_id"): a for a in prop.get("applications") or [] if isinstance(a, dict)}
        if prop.get("reportable"):
            if not any(bool((r or {}).get("evidence_required")) for r in prop.get("rules") or [] if isinstance(r,dict)):
                issues.append(AuditIssue("reportable_without_evidence_rule", f"{base}.rules", "reportable PTBG proposition has no evidence-required literature rule", "add at least one atomic evidence-required rule, or mark the proposition non-reportable"))
            if not (prop.get("conclusion") or {}).get("application_ids"):
                issues.append(AuditIssue("reportable_without_application", f"{base}.conclusion.application_ids", "reportable PTBG proposition has no patient-applicability node", "reference at least one direct or semantic application in the conclusion"))
        for ri, rule in enumerate(prop.get("rules") or []):
            if not isinstance(rule, dict): continue
            add_id(rule.get("rule_id"), f"{base}.rules[{ri}].rule_id", "rule")
            for ti, tag in enumerate(rule.get("proposed_card_tags") or []):
                if tag not in envelope:
                    issues.append(AuditIssue("card_outside_owner_envelope", f"{base}.rules[{ri}].proposed_card_tags[{ti}]", f"card {tag!r} is outside the frozen {domain} candidate envelope", "remove the card or choose only from the supplied candidate cards"))
        for si, state in enumerate(prop.get("derived_states") or []):
            if not isinstance(state, dict): continue
            add_id(state.get("state_id"), f"{base}.derived_states[{si}].state_id", "derived state")
            for fi, fid in enumerate(state.get("case_fact_ids") or []):
                if fid not in facts:
                    issues.append(AuditIssue("unknown_case_fact_id", f"{base}.derived_states[{si}].case_fact_ids[{fi}]", f"case fact {fid!r} was not supplied", "reference only immutable supplied case facts"))
            for vi, vid in enumerate(state.get("variant_ids") or []):
                if vid not in variants:
                    issues.append(AuditIssue("unknown_variant_id", f"{base}.derived_states[{si}].variant_ids[{vi}]", f"variant ID {vid!r} was not supplied", "reference only supplied variants"))
        for ai, app in enumerate(prop.get("applications") or []):
            if not isinstance(app, dict): continue
            apath = f"{base}.applications[{ai}]"
            add_id(app.get("application_id"), f"{apath}.application_id", "application")
            for rid in app.get("rule_ids") or []:
                if rid not in rules:
                    issues.append(AuditIssue("unknown_rule_id", f"{apath}.rule_ids", f"application references unknown rule {rid!r}", "reference a rule defined in the same proposition"))
            for sid in app.get("state_ids") or []:
                if sid not in states:
                    issues.append(AuditIssue("unknown_state_id", f"{apath}.state_ids", f"application references unknown derived state {sid!r}", "reference a derived state defined in the same proposition"))
            for fid in app.get("case_fact_ids") or []:
                if fid not in facts:
                    issues.append(AuditIssue("unknown_case_fact_id", f"{apath}.case_fact_ids", f"application references unknown case fact {fid!r}", "reference only supplied case facts"))
            direct = app.get("direct_match")
            if app.get("mode") == "direct":
                if not isinstance(direct, dict):
                    issues.append(AuditIssue("unsafe_direct_application", f"{apath}.direct_match", "direct application lacks an exact fact/value match", "supply one exact direct_match or change mode to semantic"))
                else:
                    fid = direct.get("case_fact_id")
                    if fid not in facts:
                        issues.append(AuditIssue("unknown_case_fact_id", f"{apath}.direct_match.case_fact_id", f"direct match references unknown fact {fid!r}", "reference one supplied case fact"))
                    if fid not in (app.get("case_fact_ids") or []):
                        issues.append(AuditIssue("direct_fact_not_declared", f"{apath}.direct_match.case_fact_id", f"direct fact {fid!r} is not listed in application.case_fact_ids", "add the same fact ID to case_fact_ids"))
                    if app.get("state_ids"):
                        issues.append(AuditIssue("unsafe_direct_application", f"{apath}.state_ids", "direct application depends on a derived state", "use semantic mode when a derived state is required"))
                    direct_rules=[rules.get(rid) for rid in app.get("rule_ids") or [] if rules.get(rid)]
                    if len(direct_rules)!=1 or not isinstance((direct_rules[0] or {}).get("direct_requirement"),dict):
                        issues.append(AuditIssue("unaudited_direct_requirement", f"{apath}.rule_ids", "direct application is not anchored to exactly one literature rule with an explicit direct_requirement", "use semantic mode, or make the exact fact-kind/value requirement part of one evidence-audited literature rule"))
                    else:
                        req=direct_rules[0]["direct_requirement"]; fact=facts.get(fid) or {}
                        if req.get("expected_value") != direct.get("expected_value"):
                            issues.append(AuditIssue("direct_requirement_mismatch", f"{apath}.direct_match.expected_value", "direct expected value differs from the evidence-audited rule requirement", "copy the exact expected_value from the rule direct_requirement or use semantic mode"))
                        if str(fact.get("kind") or "") != str(req.get("fact_kind") or ""):
                            issues.append(AuditIssue("direct_fact_kind_mismatch", f"{apath}.direct_match.case_fact_id", f"case fact kind {fact.get('kind')!r} differs from rule requirement kind {req.get('fact_kind')!r}", "select a supplied fact with the exact audited fact kind or use semantic mode"))
            elif direct is not None:
                issues.append(AuditIssue("semantic_application_has_direct_match", f"{apath}.direct_match", "semantic application supplies a direct_match", "set direct_match to null for semantic applicability"))
        conclusion = prop.get("conclusion") or {}
        for aid in conclusion.get("application_ids") or []:
            if aid not in apps:
                issues.append(AuditIssue("unknown_application_id", f"{base}.conclusion.application_ids", f"conclusion references unknown application {aid!r}", "reference an application defined in the same proposition"))
        framework = prop.get("framework")
        if isinstance(framework, dict) and framework.get("applicability_application_id") not in apps:
            issues.append(AuditIssue("unknown_application_id", f"{base}.framework.applicability_application_id", "framework applicability references an unknown application", "reference one application from this proposition"))
        worksheet=list(prop.get("worksheet") or [])
        for wi, row in enumerate(worksheet):
            if not isinstance(row, dict): continue
            aid=row.get("application_id"); status=row.get("status")
            if aid is not None and aid not in apps:
                issues.append(AuditIssue("unknown_application_id", f"{base}.worksheet[{wi}].application_id", "worksheet factor references an unknown application", "reference one application from this proposition, or use null when the factor is not supplied/not assessable or is represented by the separately audited predisposition-evidence rule"))
            if aid is None and row.get("factor")!="predisposition_evidence" and status not in {"not_supplied","not_assessable"}:
                issues.append(AuditIssue("germline_factor_missing_application", f"{base}.worksheet[{wi}].application_id", f"germline factor {row.get('factor')!r} is {status!r} but has no patient-applicability node", "reference the application that was used to interpret this supplied factor; reserve null for not_supplied/not_assessable factors"))
        if domain == "germline":
            allowed_buckets={"germline_suspicious","germline_against","germline_uncertain"}
            if prop.get("bucket") not in allowed_buckets:
                issues.append(AuditIssue("invalid_germline_bucket", f"{base}.bucket", f"germline bucket {prop.get('bucket')!r} is not one of the canonical germline assessment buckets", "use germline_suspicious, germline_against or germline_uncertain"))
            expected_factors=("predisposition_evidence","event_compatibility","age","vaf","personal_history","family_history","phenotype")
            factors=[row.get("factor") for row in worksheet if isinstance(row,dict)]
            missing=[factor for factor in expected_factors if factor not in factors]
            duplicate=sorted({factor for factor in factors if factor and factors.count(factor)>1})
            extra=sorted({factor for factor in factors if factor not in expected_factors})
            if missing:
                issues.append(AuditIssue("missing_germline_factors", f"{base}.worksheet", "germline worksheet omits factor(s): "+", ".join(missing), "return all canonical factors; use not_supplied or not_assessable instead of silently omitting a factor"))
            if duplicate:
                issues.append(AuditIssue("duplicate_germline_factors", f"{base}.worksheet", "germline worksheet repeats factor(s): "+", ".join(duplicate), "return exactly one row for each canonical germline factor"))
            if extra:
                issues.append(AuditIssue("unknown_germline_factors", f"{base}.worksheet", "germline worksheet contains unsupported factor(s): "+", ".join(extra), "use the canonical factor names only"))
    return issues


def validate_ptbg_owner(context: dict, params: dict) -> dict:
    ctx = _workflow_context(context)
    domain = str(params.get("domain") or _ptbg_domain_from_step(str(params.get("step_id") or "")))
    output = _ptbg_owner(context, domain)
    pack = ctx.get(_ptbg_pack_key(domain)) or {}
    issues: list[AuditIssue] = []
    issues.extend(_contract_issues(output, "ptbg_owner.json"))
    if isinstance(output, dict):
        if output.get("domain") != domain:
            issues.append(AuditIssue("wrong_ptbg_domain", "$.domain", f"owner returned {output.get('domain')!r} for the {domain} step", f"set domain to {domain!r}"))
        issues.extend(_ptbg_owner_reference_issues(output, domain, pack))
    return {"status": "pass" if not issues else "fail", "issue_count": len(issues), "feedback": render_feedback(issues), "issues": [x.__dict__ for x in issues]}


def build_ptbg_registry(context: dict, params: dict) -> dict:
    ctx = _workflow_context(context)
    propositions=[]; rules=[]; states=[]; applications=[]
    for domain in PTBG_DOMAINS:
        owner = _ptbg_owner(context, domain)
        for prop in owner.get("propositions") or []:
            p = {**prop, "domain": domain}
            propositions.append(p)
            pid = prop.get("proposition_id")
            for rule in prop.get("rules") or []:
                rules.append({**rule, "domain": domain, "proposition_id": pid})
            for state in prop.get("derived_states") or []:
                states.append({**state, "domain": domain, "proposition_id": pid})
            for app in prop.get("applications") or []:
                applications.append({**app, "domain": domain, "proposition_id": pid})
    return {"propositions": propositions, "rules": rules, "derived_states": states, "applications": applications}


def collect_ptbg_owner_assignments(context: dict, params: dict) -> dict:
    ctx = _workflow_context(context)
    registry = ctx.get("ptbg_atomic_registry") or {}
    pairs=[]; rescue=[]
    for rule in registry.get("rules") or []:
        tags=list(dict.fromkeys(rule.get("proposed_card_tags") or []))
        if rule.get("evidence_required") and not tags:
            rescue.append({"rule_id": rule.get("rule_id"), "domain": rule.get("domain"), "proposition_id": rule.get("proposition_id")})
        for tag in tags:
            pairs.append({"rule_id": rule.get("rule_id"), "card_tag": tag, "source": "owner"})
    return {"pairs": pairs, "rescue_items": rescue}


def prepare_ptbg_rescue(context: dict, params: dict) -> list[dict]:
    ctx = _workflow_context(context)
    state = ctx.get("ptbg_owner_assignments") or {}
    registry = {r.get("rule_id"): r for r in (ctx.get("ptbg_atomic_registry") or {}).get("rules") or []}
    out=[]
    for item in state.get("rescue_items") or []:
        rule=registry.get(item.get("rule_id")) or {}
        pack=ctx.get(_ptbg_pack_key(str(item.get("domain")))) or {}
        out.append({"rule_id": item.get("rule_id"), "domain": item.get("domain"), "statement": rule.get("statement"), "direct_requirement": rule.get("direct_requirement"), "candidate_cards": pack.get("candidate_cards") or []})
    return out


def _validate_assignment_rows(output: dict, expected_ids: set[str], envelope_by_rule: dict[str,set[str]]) -> list[AuditIssue]:
    issues=[]; rows=output.get("assignments") or [] if isinstance(output,dict) else []; seen=set()
    for i,row in enumerate(rows):
        if not isinstance(row,dict):
            issues.append(AuditIssue("invalid_assignment_row",f"$.assignments[{i}]","assignment row is not a mapping","return rule_id and card_tags")); continue
        rid=row.get("rule_id")
        if rid not in expected_ids:
            issues.append(AuditIssue("unknown_rule_id",f"$.assignments[{i}].rule_id",f"unexpected rule {rid!r}","return assignments only for supplied rescue rules")); continue
        if rid in seen: issues.append(AuditIssue("duplicate_assignment",f"$.assignments[{i}].rule_id",f"rule {rid!r} appears more than once","return exactly one assignment row per rule"))
        seen.add(rid)
        allowed=envelope_by_rule.get(rid,set())
        for j,tag in enumerate(row.get("card_tags") or []):
            if tag not in allowed: issues.append(AuditIssue("card_outside_owner_envelope",f"$.assignments[{i}].card_tags[{j}]",f"card {tag!r} is outside the supplied candidate envelope","use only supplied candidate cards"))
    for rid in sorted(expected_ids-seen): issues.append(AuditIssue("missing_assignment", "$.assignments", f"no assignment row was returned for {rid}", "return one row, using [] when no card supports the rule"))
    return issues


def validate_ptbg_rescue(context: dict, params: dict) -> dict:
    ctx=_workflow_context(context); prepared=ctx.get("ptbg_rescue_items") or []; output=ctx.get("ptbg_rescue_assignments") or {}
    expected={x.get("rule_id") for x in prepared}; envelopes={x.get("rule_id"):{c.get("card_tag") for c in x.get("candidate_cards") or [] if isinstance(c,dict)} for x in prepared}
    issues=_contract_issues(output,"diagnostic_evidence_assignment.json") if output else []
    issues.extend(_validate_assignment_rows(output,expected,envelopes))
    return {"status":"pass" if not issues else "fail","issue_count":len(issues),"feedback":render_feedback(issues),"issues":[x.__dict__ for x in issues]}


def merge_ptbg_assignments(context: dict, params: dict) -> dict:
    ctx=_workflow_context(context); state=ctx.get("ptbg_owner_assignments") or {}; rescue=ctx.get("ptbg_rescue_assignments") or {"assignments":[]}
    pairs=list(state.get("pairs") or []); registry={r.get("rule_id"):r for r in (ctx.get("ptbg_atomic_registry") or {}).get("rules") or []}
    for row in rescue.get("assignments") or []:
        for tag in row.get("card_tags") or []: pairs.append({"rule_id":row.get("rule_id"),"card_tag":tag,"source":"rescue"})
    by_rule={}
    for pair in pairs:
        by_rule.setdefault(pair["rule_id"],[])
        if pair["card_tag"] not in by_rule[pair["rule_id"]]: by_rule[pair["rule_id"]].append(pair["card_tag"])
    for rid,rule in registry.items(): by_rule.setdefault(rid,[])
    return {"pairs":pairs,"card_tags_by_rule":by_rule}


def _ptbg_card_catalog(ctx) -> dict[str,dict]:
    out={}
    for domain in PTBG_DOMAINS:
        for card in (ctx.get(_ptbg_pack_key(domain)) or {}).get("candidate_cards") or []:
            if isinstance(card,dict) and card.get("card_tag"): out[card["card_tag"]]=card
    return out


def prepare_ptbg_evidence_audit(context: dict, params: dict) -> list[dict]:
    ctx=_workflow_context(context); assignments=ctx.get("ptbg_assignments") or {}; rules={r.get("rule_id"):r for r in (ctx.get("ptbg_atomic_registry") or {}).get("rules") or []}; cards=_ptbg_card_catalog(ctx)
    out=[]
    for pair in assignments.get("pairs") or []:
        rule=rules.get(pair.get("rule_id")) or {}
        out.append({"rule_id":pair.get("rule_id"),"domain":rule.get("domain"),"statement":rule.get("statement"),"direct_requirement":rule.get("direct_requirement"),"card_tag":pair.get("card_tag"),"card":cards.get(pair.get("card_tag"))})
    return out


def _validate_audit_rows(output: dict, expected: set[tuple[str,str]]) -> list[AuditIssue]:
    issues=[]; rows=output.get("audits") or [] if isinstance(output,dict) else []; seen=set()
    for i,row in enumerate(rows):
        if not isinstance(row,dict): issues.append(AuditIssue("invalid_audit_row",f"$.audits[{i}]","audit row is not a mapping","return rule_id, card_tag, supports_rule and comments")); continue
        key=(row.get("rule_id"),row.get("card_tag"))
        if key not in expected: issues.append(AuditIssue("unknown_audit_pair",f"$.audits[{i}]",f"unexpected rule/card pair {key!r}","audit only the supplied pairs")); continue
        if key in seen: issues.append(AuditIssue("duplicate_audit_pair",f"$.audits[{i}]",f"pair {key!r} appears more than once","return exactly one audit row per supplied pair"))
        seen.add(key)
    for key in sorted(expected-seen): issues.append(AuditIssue("missing_audit_pair","$.audits",f"no audit row was returned for {key!r}","audit this supplied rule/card pair before returning"))
    return issues


def validate_ptbg_evidence_audit(context: dict, params: dict) -> dict:
    ctx=_workflow_context(context); prepared=ctx.get("ptbg_evidence_audit_items") or []; output=ctx.get("ptbg_evidence_audit") or {}
    expected={(x.get("rule_id"),x.get("card_tag")) for x in prepared}; issues=_contract_issues(output,"diagnostic_evidence_audit.json") if output else []
    issues.extend(_validate_audit_rows(output,expected))
    return {"status":"pass" if not issues else "fail","issue_count":len(issues),"feedback":render_feedback(issues),"issues":[x.__dict__ for x in issues]}


def build_ptbg_disputes(context: dict, params: dict) -> list[dict]:
    ctx=_workflow_context(context); items={(x.get("rule_id"),x.get("card_tag")):x for x in ctx.get("ptbg_evidence_audit_items") or []}; audit=ctx.get("ptbg_evidence_audit") or {}
    out=[]
    for row in audit.get("audits") or []:
        if row.get("supports_rule") is False and (row.get("rule_id"),row.get("card_tag")) in items:
            out.append({**items[(row.get("rule_id"),row.get("card_tag"))],"audit_comments":row.get("comments") or []})
    return out


def validate_ptbg_adjudication(context: dict, params: dict) -> dict:
    ctx=_workflow_context(context); disputes=ctx.get("ptbg_evidence_disputes") or []; output=ctx.get("ptbg_evidence_adjudication") or {}
    expected={(x.get("rule_id"),x.get("card_tag")) for x in disputes}; rows=output.get("adjudications") or [] if isinstance(output,dict) else []; issues=_contract_issues(output,"diagnostic_evidence_adjudication.json") if output else []; seen=set()
    for i,row in enumerate(rows):
        if not isinstance(row,dict): issues.append(AuditIssue("invalid_adjudication_row",f"$.adjudications[{i}]","adjudication row is not a mapping","return one valid row per dispute")); continue
        key=(row.get("rule_id"),row.get("card_tag"))
        if key not in expected: issues.append(AuditIssue("unknown_adjudication_pair",f"$.adjudications[{i}]",f"unexpected dispute pair {key!r}","adjudicate only supplied disputes")); continue
        if key in seen: issues.append(AuditIssue("duplicate_adjudication_pair",f"$.adjudications[{i}]",f"pair {key!r} appears more than once","return exactly one row per dispute"))
        seen.add(key)
    for key in sorted(expected-seen): issues.append(AuditIssue("missing_adjudication_pair","$.adjudications",f"no adjudication was returned for {key!r}","adjudicate this dispute"))
    return {"status":"pass" if not issues else "fail","issue_count":len(issues),"feedback":render_feedback(issues),"issues":[x.__dict__ for x in issues]}


def finalize_ptbg_evidence(context: dict, params: dict) -> dict:
    ctx=_workflow_context(context); audit=ctx.get("ptbg_evidence_audit") or {}; adjud=ctx.get("ptbg_evidence_adjudication") or {"adjudications":[]}; adjud_by={(x.get("rule_id"),x.get("card_tag")):x for x in adjud.get("adjudications") or []}; registry=ctx.get("ptbg_atomic_registry") or {}
    pairs=[]; supported={}; accepted={}
    for row in audit.get("audits") or []:
        key=(row.get("rule_id"),row.get("card_tag")); final=bool(row.get("supports_rule"))
        if not final and key in adjud_by: final=bool(adjud_by[key].get("supports_rule"))
        pairs.append({"rule_id":key[0],"card_tag":key[1],"supports_rule":final}); supported[key[0]]=bool(supported.get(key[0])) or final
        if final: accepted.setdefault(key[0],[]); accepted[key[0]].append(key[1])
    for rule in registry.get("rules") or []:
        rid=rule.get("rule_id")
        if not rule.get("evidence_required"): supported.setdefault(rid,True)
        else: supported.setdefault(rid,False)
        accepted.setdefault(rid,[])
    return {"pairs":pairs,"rule_support":supported,"accepted_card_tags_by_rule":accepted}


def evaluate_ptbg_direct_applications(context: dict, params: dict) -> list[dict]:
    """Resolve only exact fact/value applications and evidence-blocked applications."""
    ctx=_workflow_context(context); registry=ctx.get("ptbg_atomic_registry") or {}; evidence=ctx.get("ptbg_evidence_decisions") or {}; support=evidence.get("rule_support") or {}; facts={}
    for domain in PTBG_DOMAINS: facts.update((ctx.get(_ptbg_pack_key(domain)) or {}).get("case_fact_registry") or {})
    direct=[]
    for app in registry.get("applications") or []:
        rid_list=list(app.get("rule_ids") or [])
        if not all(support.get(rid,False) for rid in rid_list):
            direct.append({"application_id":app.get("application_id"),"status":"unknown","case_fact_ids":list(app.get("case_fact_ids") or []),"comments":["One or more required literature rules lacked audited support."]}); continue
        if app.get("mode")!="direct": continue
        match=app.get("direct_match") or {}; fid=match.get("case_fact_id"); actual=_fact_scalar(facts.get(fid)); expected=match.get("expected_value"); status="met" if actual==expected else "not_met"
        direct.append({"application_id":app.get("application_id"),"status":status,"case_fact_ids":[fid] if fid else [],"comments":[f"Deterministic exact comparison: supplied value {actual!r}; expected {expected!r}."]})
    return direct


def prepare_ptbg_reasoning_audit(context: dict, params: dict) -> list[dict]:
    ctx=_workflow_context(context); registry=ctx.get("ptbg_atomic_registry") or {}; evidence=ctx.get("ptbg_evidence_decisions") or {}; support=evidence.get("rule_support") or {}; facts={}
    for domain in PTBG_DOMAINS: facts.update((ctx.get(_ptbg_pack_key(domain)) or {}).get("case_fact_registry") or {})
    states={s.get("state_id"):s for s in registry.get("derived_states") or []}; rules={r.get("rule_id"):r for r in registry.get("rules") or []}
    items=[]
    for state in states.values():
        items.append({"item_type":"derived_state","domain":state.get("domain"),"state":state,"case_facts":[facts[f] for f in state.get("case_fact_ids") or [] if f in facts]})
    for app in registry.get("applications") or []:
        rid_list=list(app.get("rule_ids") or [])
        if app.get("mode")!="semantic" or not all(support.get(rid,False) for rid in rid_list): continue
        items.append({"item_type":"application","domain":app.get("domain"),"application":app,"rules":[rules[r] for r in rid_list if r in rules],"case_facts":[facts[f] for f in app.get("case_fact_ids") or [] if f in facts],"derived_states":[states[s] for s in app.get("state_ids") or [] if s in states]})
    return items


def validate_ptbg_reasoning_audit(context: dict, params: dict) -> dict:
    ctx=_workflow_context(context); prepared=ctx.get("ptbg_reasoning_items") or []; output=ctx.get("ptbg_reasoning_audit") or {}
    expected_states={x["state"]["state_id"] for x in prepared if x.get("item_type")=="derived_state"}; expected_apps={x["application"]["application_id"] for x in prepared if x.get("item_type")=="application"}; issues=_contract_issues(output,"reasoning_audit.json") if output else []
    def check(rows,expected,field,base):
        seen=set()
        for i,row in enumerate(rows):
            if not isinstance(row,dict): issues.append(AuditIssue("invalid_reasoning_row",f"$.{base}[{i}]","reasoning row is not a mapping",f"return a valid {base} row")); continue
            value=row.get(field)
            if value not in expected: issues.append(AuditIssue("unknown_reasoning_id",f"$.{base}[{i}].{field}",f"unexpected ID {value!r}","assess only supplied items")); continue
            if value in seen: issues.append(AuditIssue("duplicate_reasoning_result",f"$.{base}[{i}].{field}",f"ID {value!r} appears more than once","return exactly one result per item"))
            seen.add(value)
        for missing in sorted(expected-seen): issues.append(AuditIssue("missing_reasoning_result",f"$.{base}",f"no result was returned for {missing}","assess this supplied item"))
    check(output.get("derived_states") or [] if isinstance(output,dict) else [],expected_states,"state_id","derived_states")
    # PTBG application IDs are carried in the generic reasoning schema's criterion_id field.
    check(output.get("criteria") or [] if isinstance(output,dict) else [],expected_apps,"criterion_id","criteria")
    return {"status":"pass" if not issues else "fail","issue_count":len(issues),"feedback":render_feedback(issues),"issues":[x.__dict__ for x in issues]}


def evaluate_ptbg(context: dict, params: dict) -> dict:
    ctx=_workflow_context(context); registry=ctx.get("ptbg_atomic_registry") or {}; evidence=ctx.get("ptbg_evidence_decisions") or {}; support=evidence.get("rule_support") or {}; audit=ctx.get("ptbg_reasoning_audit") or {"derived_states":[],"criteria":[]}
    state_status={r.get("state_id"):r.get("status") for r in audit.get("derived_states") or []}; app_status={r.get("criterion_id"):r.get("status") for r in audit.get("criteria") or []}
    app_comments={r.get("criterion_id"):r.get("comments") or [] for r in audit.get("criteria") or []}
    for row in ctx.get("ptbg_direct_applications") or []: app_status[row.get("application_id")]=row.get("status"); app_comments[row.get("application_id")]=row.get("comments") or []
    applications={a.get("application_id"):a for a in registry.get("applications") or []}
    for aid,app in applications.items():
        if any(not support.get(rid,False) for rid in app.get("rule_ids") or []): app_status[aid]="unknown"
        if app_status.get(aid)=="met" and any(state_status.get(sid)!="supported" for sid in app.get("state_ids") or []):
            app_status[aid]="unknown"; app_comments.setdefault(aid,[]).append("A required derived state was not independently supported.")
    results=[]; by_domain={d:[] for d in PTBG_DOMAINS}
    for prop in registry.get("propositions") or []:
        ids=list((prop.get("conclusion") or {}).get("application_ids") or []); statuses=[app_status.get(a,"unknown") for a in ids]; root=_logic_status((prop.get("conclusion") or {}).get("operator") or "all_of",statuses) if ids else "met"
        rule_ids=[r.get("rule_id") for r in registry.get("rules") or [] if r.get("proposition_id")==prop.get("proposition_id")]; evidence_ok=all(support.get(rid,False) for rid in rule_ids if next((r for r in registry.get("rules") or [] if r.get("rule_id")==rid and r.get("evidence_required")),None))
        if not prop.get("reportable"): disposition="not_reportable"; reason="Owner marked the proposition as non-reportable."
        elif not evidence_ok: disposition="dropped"; reason="At least one required literature rule lacked audited supporting evidence."
        elif root=="met": disposition="kept"; reason="All deterministic/evidence and patient-applicability gates required by the proposition were met."
        elif root=="not_met": disposition="dropped"; reason="The audited patient applicability did not satisfy the proposition's conclusion logic."
        else: disposition="unresolved"; reason="The audited patient applicability remained indeterminate."
        row={"proposition_id":prop.get("proposition_id"),"domain":prop.get("domain"),"status":root,"disposition":disposition,"reason":reason,"application_status":{a:app_status.get(a,"unknown") for a in ids},"rule_ids":rule_ids}
        results.append(row); by_domain[prop.get("domain")].append(row)
    return {"propositions":results,"by_domain":by_domain,"state_status":state_status,"application_status":app_status,"application_comments":app_comments}


def ptbg_owner_review(context: dict, params: dict) -> dict:
    ctx=_workflow_context(context); domain=str(params.get("domain") or _ptbg_domain_from_step(str(params.get("step_id") or ""))); evaluation=ctx.get("ptbg_evaluation") or {}; rows=(evaluation.get("by_domain",{}) or {}).get(domain,[])
    problems=[r for r in rows if r.get("disposition") in {"dropped","unresolved"}]
    if not problems: return {"status":"pass","feedback":"","issues":[]}
    comments=evaluation.get("application_comments") or {}; rule_support=(ctx.get("ptbg_evidence_decisions") or {}).get("rule_support") or {}
    issues=[]
    for row in problems:
        details=[]
        for aid,status in (row.get("application_status") or {}).items():
            if status=="met": continue
            note=" ".join(str(x).strip() for x in (comments.get(aid) or []) if str(x).strip())
            details.append(f"application {aid} was {status}"+(f": {note}" if note else ""))
        missing=[rid for rid in row.get("rule_ids") or [] if not rule_support.get(rid,False)]
        if missing: details.append("literature rule(s) without audited support: "+", ".join(missing))
        why=f"{row.get('proposition_id')} would be {row.get('disposition')}: {row.get('reason')}"
        if details: why += " Specific audit findings: " + "; ".join(details) + "."
        issues.append(AuditIssue(
            "unsupported_ptbg_proposition", f"$.{domain}.{row.get('proposition_id')}", why,
            "revise or remove this proposition so it agrees with the listed audited rule/applicability findings; do not alter immutable patient facts",
        ))
    return {"status":"fail","feedback":render_feedback(issues),"issues":[x.__dict__ for x in issues]}


def _accepted_card_rows(ctx, tags: list[str]) -> list[dict]:
    catalog=_ptbg_card_catalog(ctx)
    # Diagnostic owner packs use the same compact-card representation.
    for key in ("diagnosis_who_pack","diagnosis_icc_pack","diagnosis_second_pack"):
        for card in (ctx.get(key) or {}).get("candidate_cards") or []:
            if isinstance(card,dict) and card.get("card_tag"): catalog.setdefault(card["card_tag"],card)
    out=[]
    for tag in tags:
        card=catalog.get(tag) or {}; cid=card.get("card_id")
        if cid:
            row={"card_tag":tag,"card_id":cid}
            label=card.get("source_label") or _source_label_for_card(card)
            if label: row["source_label"]=label
            out.append(row)
    return out


def finalize_atomic_evidence(context: dict, params: dict) -> list[dict]:
    """Project only audited/kept reasoning propositions into legacy report elements."""
    ctx=_workflow_context(context); work=_work(context); diagnosis=ctx.get("diagnosis") or {}; elements=[]
    diagnostic_registry=ctx.get("diagnostic_atomic_registry") or {}; diagnostic_decisions=ctx.get("diagnostic_evidence_decisions") or {}; diagnostic_eval=ctx.get("diagnostic_evaluation") or {}; diagnostic_pairs=diagnostic_decisions.get("pairs") or []
    rules_by_authority={a:[] for a in ("who5","icc","second_diagnosis")}
    for rule in diagnostic_registry.get("rules") or []: rules_by_authority.setdefault(rule.get("authority"),[]).append(rule.get("rule_id"))
    tags_by_rule={}
    for pair in diagnostic_pairs:
        if pair.get("supports_rule"): tags_by_rule.setdefault(pair.get("rule_id"),[]).append(pair.get("card_tag"))
    def authority_tags(authority):
        out=[]
        for rid in rules_by_authority.get(authority,[]):
            for tag in tags_by_rule.get(rid,[]):
                if tag not in out: out.append(tag)
        return out
    # The committed framework diagnoses are always reportable. When an owner
    # proposal fails its bounded reasoning review, ``diagnosis`` already contains
    # the deterministic supplied-diagnosis fallback. Keep that fallback visible
    # without fabricating literature support for the rejected molecular proposal.
    for authority, schema_id, bucket in (("who5","DX-WHO5","who5"),("icc","DX-ICC","icc")):
        src=diagnosis.get(bucket) or {}
        if not src: continue
        passed=(diagnostic_eval.get("owner_status") or {}).get(authority)=="pass"
        tags=authority_tags(authority) if passed else []
        fallback_reason=(
            src.get("reason")
            or ("Audited WHO5 diagnosis." if authority=="who5" else "Audited ICC diagnosis.")
        )
        elements.append({"schema_id":schema_id,"domain":"diagnosis","bucket":bucket,"reason":fallback_reason,"variants":src.get("variants") or [],"source":src,"evidence":_accepted_card_rows(ctx,tags)})
    second_tags=authority_tags("second_diagnosis")
    for i,src in enumerate(diagnosis.get("concurrent_pathology") or [],1): elements.append({"schema_id":f"DX-CONCURRENT-{i}","domain":"diagnosis","bucket":"concurrent_pathology","reason":src.get("reason") or "Audited concurrent pathology.","variants":[src.get("variant_id")] if src.get("variant_id") else [],"source":src,"evidence":_accepted_card_rows(ctx,second_tags)})

    registry=ctx.get("ptbg_atomic_registry") or {}; evaluation=ctx.get("ptbg_evaluation") or {}; eval_by={r.get("proposition_id"):r for r in evaluation.get("propositions") or []}; evidence=ctx.get("ptbg_evidence_decisions") or {}; accepted=evidence.get("accepted_card_tags_by_rule") or {}
    rules_by_prop={}
    for rule in registry.get("rules") or []: rules_by_prop.setdefault(rule.get("proposition_id"),[]).append(rule)
    prefix={"prognosis":"PX","treatment":"TX","biomarker":"MRD","germline":"GL"}
    for prop in registry.get("propositions") or []:
        erow=eval_by.get(prop.get("proposition_id")) or {}
        if erow.get("disposition") not in {"kept","revised"}: continue
        tags=[]
        for rule in rules_by_prop.get(prop.get("proposition_id"),[]):
            for tag in accepted.get(rule.get("rule_id"),[]):
                if tag not in tags: tags.append(tag)
        domain=prop.get("domain"); sid=f"{prefix.get(domain,'EL')}-{prop.get('proposition_id')}"
        source={"text":prop.get("text"),"reason":prop.get("reason"),"bucket":prop.get("bucket"),"framework":prop.get("framework"),"worksheet":prop.get("worksheet")}
        elements.append({"schema_id":sid,"domain":domain,"bucket":prop.get("bucket"),"reason":prop.get("reason") or prop.get("text"),"variants":prop.get("variant_ids") or [],"source":source,"evidence":_accepted_card_rows(ctx,tags)})
    # Compatibility artifact keeps existing report/citation infrastructure unchanged.
    try:
        from workflows.proforma_v1 import self_runtime as sr
        sr.write_yaml(sr.output_path(work,"evidence_enriched","reportable-elements.yaml"),{"elements":elements})
    except Exception:
        pass
    ctx.put("supported",elements)
    return elements


def _decision_rules_for(owner_rules: list[dict], evidence: dict) -> list[dict]:
    support=evidence.get("rule_support") or {}; accepted=evidence.get("accepted_card_tags_by_rule") or {}
    out=[]
    for rule in owner_rules:
        rid=rule.get("rule_id"); out.append({"rule_id":rid,"statement":str(rule.get("statement") or ""),"supported":bool(support.get(rid,not rule.get("evidence_required"))),"accepted_card_tags":list(accepted.get(rid) or [])})
    return out


def build_decision_ledger(context: dict, params: dict) -> dict:
    ctx=_workflow_context(context); decisions=[]; facts={}; case=None; registry_variants={}
    for domain in PTBG_DOMAINS:
        pack=ctx.get(_ptbg_pack_key(domain)) or {}; case=case or pack.get("structured_case"); facts.update(pack.get("case_fact_registry") or {}); registry_variants.update(pack.get("variant_registry") or {})
    if not case:
        pack=ctx.get("diagnosis_who_pack") or {}; case=pack.get("structured_case"); facts.update(pack.get("case_fact_registry") or {}); registry_variants.update(pack.get("variant_registry") or {})
    referenced=set()
    # Diagnostic decisions.
    deval=ctx.get("diagnostic_evaluation") or {}; dreason=ctx.get("diagnostic_reasoning_audit") or {}; devidence=ctx.get("diagnostic_evidence_decisions") or {}; dregistry=ctx.get("diagnostic_atomic_registry") or {}
    for authority,key,label in (("who5","diagnosis_who_owner","WHO5 diagnosis"),("icc","diagnosis_icc_owner","ICC diagnosis"),("second_diagnosis","diagnosis_second_owner","Second diagnosis")):
        owner=ctx.get(key) or {}; proposal=owner.get("proposal") or {}; status=(deval.get("owner_status") or {}).get(authority); prop_status=proposal.get("status")
        if authority=="second_diagnosis" and prop_status in {"none","not_established"}: disposition="not_reportable"
        else: disposition="kept" if status=="pass" else "dropped"
        ids=[]
        for row in owner.get("criteria") or []: ids.extend(row.get("case_fact_ids") or [])
        for row in owner.get("derived_states") or []: ids.extend(row.get("case_fact_ids") or [])
        ids=list(dict.fromkeys(ids)); referenced.update(ids)
        rules=[r for r in dregistry.get("rules") or [] if r.get("authority")==authority]
        accepted={}
        for pair in devidence.get("pairs") or []:
            if pair.get("supports_rule"): accepted.setdefault(pair.get("rule_id"),[]).append(pair.get("card_tag"))
        ev={"rule_support":devidence.get("rule_support") or {},"accepted_card_tags_by_rule":accepted}
        reason=((deval.get("feedback") or {}).get(authority) if status!="pass" else owner.get("reason")) or "Audited diagnostic decision."
        diagnostic_variants=list(dict.fromkeys([*(proposal.get("variant_ids") or []), *[r.get("variant_id") for r in proposal.get("variant_assessments") or [] if isinstance(r,dict) and r.get("variant_id")]]))
        for vid in diagnostic_variants:
            if vid in registry_variants:
                referenced.add(vid); facts.setdefault(vid,{"fact_id":vid,"kind":"variant","value":registry_variants[vid].get("description") or registry_variants[vid].get("gene")})
        decisions.append({"decision_id":proposal.get("proposal_id") or f"DX-{authority}","kind":"diagnosis","domain":"diagnosis","owner":authority,"proposition":proposal.get("label") or label,"disposition":disposition,"case_fact_ids":ids,"variant_ids":diagnostic_variants,"rules":_decision_rules_for(rules,ev),"reason":str(reason)})
    # Diagnostic derived states have their own terminal disposition.
    dstate={r.get("state_id"):r for r in dreason.get("derived_states") or []}
    for state in dregistry.get("derived_states") or []:
        row=dstate.get(state.get("state_id")) or {}; status=row.get("status","indeterminate"); disposition={"supported":"kept","unsupported":"dropped","indeterminate":"unresolved"}.get(status,"unresolved"); ids=list(state.get("case_fact_ids") or []); referenced.update(ids)
        state_variants=list(dict.fromkeys(state.get("variant_ids") or []))
        for vid in state_variants:
            if vid in registry_variants:
                referenced.add(vid); facts.setdefault(vid,{"fact_id":vid,"kind":"variant","value":registry_variants[vid].get("description") or registry_variants[vid].get("gene")})
        decisions.append({"decision_id":state.get("state_id"),"kind":"derived_state","domain":"diagnosis","owner":state.get("authority") or "diagnosis","proposition":f"{state.get('label')}: {row.get('value',state.get('proposed_value'))}","disposition":disposition,"case_fact_ids":ids,"variant_ids":state_variants,"rules":[],"reason":" ".join(row.get("comments") or []) or state.get("reason") or "Audited diagnostic derived state."})

    preg=ctx.get("ptbg_atomic_registry") or {}; peval=ctx.get("ptbg_evaluation") or {}; pev=ctx.get("ptbg_evidence_decisions") or {}; pby={r.get("proposition_id"):r for r in peval.get("propositions") or []}; rules_by_prop={}
    for r in preg.get("rules") or []: rules_by_prop.setdefault(r.get("proposition_id"),[]).append(r)
    review_cycles=ctx.get("review_cycles",{}) or {}
    for prop in preg.get("propositions") or []:
        row=pby.get(prop.get("proposition_id")) or {}; disposition=row.get("disposition") or "unresolved"; domain=prop.get("domain")
        if disposition=="kept" and (int(review_cycles.get(f"{domain}.review",0) or 0)>0 or int(review_cycles.get(f"{domain}.validate",0) or 0)>0): disposition="revised"
        ids=[]
        for app in prop.get("applications") or []: ids.extend(app.get("case_fact_ids") or [])
        for state in prop.get("derived_states") or []: ids.extend(state.get("case_fact_ids") or [])
        ids=list(dict.fromkeys(ids)); referenced.update(ids)
        detail=[]
        for aid in (prop.get("conclusion") or {}).get("application_ids") or []:
            for comment in (peval.get("application_comments") or {}).get(aid,[]) or []:
                text=str(comment).strip()
                if text and text not in detail: detail.append(text)
        for factor in prop.get("worksheet") or []:
            if not isinstance(factor,dict): continue
            text=str(factor.get("reason") or "").strip(); status=str(factor.get("status") or "").strip(); label=str(factor.get("factor") or "factor")
            rendered=(f"{label}={status}: {text}" if status else f"{label}: {text}").strip()
            if rendered and rendered not in detail: detail.append(rendered)
        base_reason=row.get("reason") or prop.get("reason") or "Audited PTBG proposition."
        full_reason=str(base_reason)+(f" Details: {' '.join(detail)}" if detail else "")
        proposition_variants=list(dict.fromkeys(prop.get("variant_ids") or []))
        for vid in proposition_variants:
            if vid in registry_variants:
                referenced.add(vid); facts.setdefault(vid,{"fact_id":vid,"kind":"variant","value":registry_variants[vid].get("description") or registry_variants[vid].get("gene")})
        decisions.append({"decision_id":prop.get("proposition_id"),"kind":"proposition","domain":domain,"owner":domain,"proposition":prop.get("text") or prop.get("reason"),"disposition":disposition,"case_fact_ids":ids,"variant_ids":proposition_variants,"rules":_decision_rules_for(rules_by_prop.get(prop.get("proposition_id"),[]),pev),"reason":full_reason})
    pstate={r.get("state_id"):r for r in (ctx.get("ptbg_reasoning_audit") or {}).get("derived_states") or []}
    for state in preg.get("derived_states") or []:
        row=pstate.get(state.get("state_id")) or {}; status=row.get("status","indeterminate"); disposition={"supported":"kept","unsupported":"dropped","indeterminate":"unresolved"}.get(status,"unresolved"); ids=list(state.get("case_fact_ids") or []); referenced.update(ids)
        state_variants=list(dict.fromkeys(state.get("variant_ids") or []))
        for vid in state_variants:
            if vid in registry_variants:
                referenced.add(vid); facts.setdefault(vid,{"fact_id":vid,"kind":"variant","value":registry_variants[vid].get("description") or registry_variants[vid].get("gene")})
        decisions.append({"decision_id":state.get("state_id"),"kind":"derived_state","domain":state.get("domain") or "ptbg","owner":state.get("domain") or "ptbg","proposition":f"{state.get('label')}: {row.get('value',state.get('proposed_value'))}","disposition":disposition,"case_fact_ids":ids,"variant_ids":state_variants,"rules":[],"reason":" ".join(row.get("comments") or []) or state.get("reason") or "Audited derived state."})

    fact_rows=[facts[f] for f in sorted(referenced) if f in facts]
    counts={d:sum(1 for row in decisions if row.get("disposition")==d) for d in TERMINAL_DISPOSITIONS}
    ledger={"decisions":decisions,"facts_considered":fact_rows,"counts":counts}
    problems=_contract_issues(ledger,"decision_ledger.json")
    if problems: raise ValueError("deterministic decision ledger invalid:\n"+render_feedback(problems))
    work=_work(context); (work/"decision-ledger.yaml").write_text(yaml.safe_dump(ledger,sort_keys=False,allow_unicode=True,width=110),encoding="utf-8")
    return ledger


def validate_dissent_summary(context: dict, params: dict) -> dict:
    ctx=_workflow_context(context); ledger=ctx.get("decision_ledger") or {}; output=ctx.get("dissent_summary") or {"summary":"","highlights":[]}; issues=_contract_issues(output,"dissent_summary.json") if output else []
    by_id={r.get("decision_id"):r for r in ledger.get("decisions") or []}; seen=set()
    for i,row in enumerate(output.get("highlights") or [] if isinstance(output,dict) else []):
        if not isinstance(row,dict): continue
        did=row.get("decision_id")
        if did not in by_id: issues.append(AuditIssue("unknown_decision_id",f"$.highlights[{i}].decision_id",f"summary references unknown decision {did!r}","reference only IDs from the immutable decision ledger")); continue
        if row.get("disposition")!=by_id[did].get("disposition"): issues.append(AuditIssue("changed_ledger_disposition",f"$.highlights[{i}].disposition",f"summary says {row.get('disposition')!r} but ledger says {by_id[did].get('disposition')!r}","copy the ledger disposition exactly; do not reinterpret it"))
        if did in seen: issues.append(AuditIssue("duplicate_summary_highlight",f"$.highlights[{i}].decision_id",f"decision {did!r} is highlighted more than once","use at most one highlight per decision"))
        seen.add(did)
    return {"status":"pass" if not issues else "fail","issue_count":len(issues),"feedback":render_feedback(issues),"issues":[x.__dict__ for x in issues]}


def reasoning_report_blocks(context: dict, params: dict) -> list[dict]:
    ctx=_workflow_context(context); elements=ctx.get("evidence_enriched") or ctx.get("supported") or []; blocks=[]
    diagnosis_components=[]
    for el in elements:
        if el.get("domain")!="diagnosis": continue
        src=el.get("source") or {}; role="who5" if el.get("schema_id")=="DX-WHO5" else "icc" if el.get("schema_id")=="DX-ICC" else "concurrent_pathology"
        component={"role":role,"reason":el.get("reason"),"variants":el.get("variants") or [],"card_tags":[e.get("card_tag") for e in el.get("evidence") or [] if e.get("card_tag")]}
        if role in {"who5","icc"}: component["diagnosis"]=src.get("diagnosis")
        else: component["pathology"]=src.get("other_pathology")
        diagnosis_components.append(component)
    if diagnosis_components: blocks.append({"block_id":"DX","domain":"diagnosis","components":diagnosis_components})
    for el in elements:
        if el.get("domain")=="diagnosis": continue
        src=el.get("source") or {}; blocks.append({"block_id":el.get("schema_id"),"domain":el.get("domain"),"components":[{"role":el.get("bucket"),"reason":el.get("reason"),"variants":el.get("variants") or [],"source":src,"card_tags":[e.get("card_tag") for e in el.get("evidence") or [] if e.get("card_tag")]}]})
    work=_work(context)
    try:
        from workflows.proforma_v1 import self_runtime as sr, schema_validation
        sr.write_yaml(sr.output_path(work,"report_blocks","report-blocks.yaml"),{"blocks":blocks}); schema_validation.validate_report_source_blocks(blocks)
    except Exception:
        pass
    ctx.put("blocks",blocks)
    return blocks


def _decision_text(row: dict) -> str:
    return " ".join(str(row.get("proposition") or "").split())


def render_reasoning_dissent(ledger: dict, summary: dict | None = None) -> str:
    lines=["# Decision review",""]
    if summary and str(summary.get("summary") or "").strip():
        lines += ["## Plain-English summary","",str(summary.get("summary")).strip(),""]
    counts=ledger.get("counts") or {}; lines += ["## Outcome overview","",f"Kept: {counts.get('kept',0)} · Revised: {counts.get('revised',0)} · Dropped: {counts.get('dropped',0)} · Unresolved: {counts.get('unresolved',0)} · Not reportable: {counts.get('not_reportable',0)}",""]
    lines += ["## Facts considered",""]
    facts=ledger.get("facts_considered") or []
    if facts:
        for fact in facts:
            value=_fact_scalar(fact); label=fact.get("fact_id"); kind=fact.get("kind")
            lines.append(f"- **{label}**"+(f" ({kind})" if kind else "")+f": {value}")
    else: lines.append("- No explicit case-fact IDs were required by the reviewed propositions.")
    lines.append("")
    groups=[("Considered and kept",{"kept","revised"}),("Dropped",{"dropped"}),("Unresolved",{"unresolved"}),("Not reportable",{"not_reportable"})]
    for title,wanted in groups:
        rows=[r for r in ledger.get("decisions") or [] if r.get("disposition") in wanted]
        lines += [f"## {title}",""]
        if not rows: lines.append("None."); lines.append(""); continue
        for row in rows:
            lines += [f"### {row.get('decision_id')} — {str(row.get('disposition')).replace('_',' ').title()}","",f"**{row.get('domain')} / {row.get('owner')}** — {_decision_text(row)}","",f"**Reason:** {row.get('reason')}"]
            if row.get("case_fact_ids"): lines.append("\n**Facts used:** "+", ".join(row.get("case_fact_ids") or []))
            if row.get("variant_ids"): lines.append("\n**Variants considered:** "+", ".join(row.get("variant_ids") or []))
            if row.get("rules"):
                lines.append("\n**Literature rules considered:**")
                for rule in row.get("rules") or []:
                    tags=", ".join(rule.get("accepted_card_tags") or []) or "no accepted card"
                    lines.append(f"- {rule.get('rule_id')}: {rule.get('statement')} — {'supported' if rule.get('supported') else 'not supported'}; {tags}")
            lines.append("")
    return "\n".join(lines).rstrip()+"\n"


def finalize_reasoning_report(context: dict, params: dict) -> dict:
    ctx=_workflow_context(context); work=_work(context); summary=ctx.get("dissent_summary") or {}; validation=ctx.get("dissent_summary_validation") or {}; usable=summary if validation.get("status")=="pass" else None
    report_path=None
    try:
        from workflows.proforma_v1 import self_runtime as sr
        report_path=sr.finalize_report(work)
    finally:
        ledger=ctx.get("decision_ledger") or {}; (work/"dissent.md").write_text(render_reasoning_dissent(ledger,usable),encoding="utf-8")
    payload_path=work/"report-final.json"
    if payload_path.is_file():
        try: payload=json.loads(payload_path.read_text(encoding="utf-8"))
        except Exception: payload={}
        payload["reasoning_decision_ledger"]="decision-ledger.yaml"; payload["dissent_summary_status"]="accepted" if usable else "deterministic_fallback"
        payload_path.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    try:
        from workflows.proforma_v1 import self_runtime as sr
        sr.package_debug_bundle(work)
    except Exception:
        pass
    return {"report":str(report_path or work/"report-final.md"),"dissent":str(work/"dissent.md"),"decision_ledger":str(work/"decision-ledger.yaml")}


def run_ptbg_transform(name: str, context: dict, params: dict) -> Any:
    dispatch={
        "reasoning_prepare_ptbg_owner":prepare_ptbg_owner,
        "reasoning_validate_ptbg_owner":validate_ptbg_owner,
        "reasoning_build_ptbg_registry":build_ptbg_registry,
        "reasoning_collect_ptbg_owner_assignments":collect_ptbg_owner_assignments,
        "reasoning_prepare_ptbg_rescue":prepare_ptbg_rescue,
        "reasoning_validate_ptbg_rescue":validate_ptbg_rescue,
        "reasoning_merge_ptbg_assignments":merge_ptbg_assignments,
        "reasoning_prepare_ptbg_evidence_audit":prepare_ptbg_evidence_audit,
        "reasoning_validate_ptbg_evidence_audit":validate_ptbg_evidence_audit,
        "reasoning_build_ptbg_disputes":build_ptbg_disputes,
        "reasoning_validate_ptbg_adjudication":validate_ptbg_adjudication,
        "reasoning_finalize_ptbg_evidence":finalize_ptbg_evidence,
        "reasoning_evaluate_ptbg_direct_applications":evaluate_ptbg_direct_applications,
        "reasoning_prepare_ptbg_reasoning_audit":prepare_ptbg_reasoning_audit,
        "reasoning_validate_ptbg_reasoning_audit":validate_ptbg_reasoning_audit,
        "reasoning_evaluate_ptbg":evaluate_ptbg,
        "reasoning_ptbg_owner_review":ptbg_owner_review,
        "reasoning_finalize_atomic_evidence":finalize_atomic_evidence,
        "reasoning_build_decision_ledger":build_decision_ledger,
        "reasoning_validate_dissent_summary":validate_dissent_summary,
        "reasoning_report_blocks":reasoning_report_blocks,
        "reasoning_finalize_report":finalize_reasoning_report,
    }
    try: fn=dispatch[name]
    except KeyError as exc: raise ValueError(f"unknown reasoning PTBG/provenance transform {name!r}") from exc
    return fn(context,params)

# ---------------------------------------------------------------------------
# Phase 4: judgement-separated reasoning architecture
# Models reason first; evidence matching is a separate judgement; Python owns
# all internal identifiers, graph objects, reference aliases and serialization.
# ---------------------------------------------------------------------------

_DIAGNOSTIC_REASONING_KEYS = {
    "who5": "diagnosis_who_reasoning",
    "icc": "diagnosis_icc_reasoning",
    "second_diagnosis": "diagnosis_second_reasoning",
}
_DIAGNOSTIC_EM_KEYS = {
    "who5": "diagnosis_who_evidence_match",
    "icc": "diagnosis_icc_evidence_match",
    "second_diagnosis": "diagnosis_second_evidence_match",
}
_DIAGNOSTIC_EM_ITEM_KEYS = {
    "who5": "diagnosis_who_evidence_match_items",
    "icc": "diagnosis_icc_evidence_match_items",
    "second_diagnosis": "diagnosis_second_evidence_match_items",
}
_PTBG_REASONING_KEYS = {domain: f"{domain}_reasoning" for domain in PTBG_DOMAINS}
_PTBG_EM_KEYS = {domain: f"{domain}_evidence_match" for domain in PTBG_DOMAINS}
_PTBG_EM_ITEM_KEYS = {domain: f"{domain}_evidence_match_items" for domain in PTBG_DOMAINS}


def _reference_material(cards: list[dict]) -> list[dict]:
    """Project corpus cards to clinical content with all evidence identifiers removed."""
    out: list[dict] = []
    seen: set[str] = set()
    for card in cards:
        if not isinstance(card, dict):
            continue
        text = None
        for key in ("interpretation", "claim", "evidence_text", "scope", "notes"):
            value = card.get(key)
            if isinstance(value, str) and value.strip():
                text = value.strip()
                break
        if not text or text in seen:
            continue
        seen.add(text)
        row = {"text": text}
        for key in ("diseases", "genes", "framework", "frameworks"):
            value = card.get(key)
            if value not in (None, "", [], {}):
                row[key] = value
        out.append(row)
    return out


def _source_variant_registry(internal_registry: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for internal_id, row in (internal_registry or {}).items():
        if not isinstance(row, dict):
            continue
        source_id = str(row.get("variant_id") or "").strip() or str(internal_id)
        projected = {k: v for k, v in row.items() if k != "variant_id"}
        projected["variant_id"] = source_id
        out[source_id] = projected
    return out


def _variant_aliases(internal_registry: dict) -> tuple[dict[str, str], dict[str, str]]:
    internal_by_source: dict[str, str] = {}
    source_by_internal: dict[str, str] = {}
    for internal_id, row in (internal_registry or {}).items():
        source_id = str((row or {}).get("variant_id") or "").strip() or str(internal_id)
        if source_id in internal_by_source and internal_by_source[source_id] != internal_id:
            raise ValueError(f"source variant ID {source_id!r} resolves to more than one internal variant")
        internal_by_source[source_id] = str(internal_id)
        source_by_internal[str(internal_id)] = source_id
    return internal_by_source, source_by_internal


def _diagnostic_cards_for(authority: str, work: Path) -> tuple[dict, dict, list[dict], dict]:
    from workflows.proforma_v1 import runtime, self_runtime as sr, step as staged
    case, registry = sr.load_case_registry(work)
    _all_cards, eligible, _digest, manifest = sr.corpus_state(work)
    genes = runtime.case_genes(case)
    history = list(case.get("bootstrap_cmcs") or [])
    if authority == "who5":
        cards = staged._diagnostic_cards(eligible, genes, history, "who5")
    elif authority == "icc":
        cards = staged._diagnostic_cards(eligible, genes, history, "icc")
    elif authority == "second_diagnosis":
        who_cards = staged._diagnostic_cards(eligible, genes, history, "who5")
        icc_cards = staged._diagnostic_cards(eligible, genes, history, "icc")
        cards = list({c.get("card_id"): c for c in [*who_cards, *icc_cards] if c.get("card_id")}.values())
    else:
        raise ValueError(f"unsupported diagnostic authority {authority!r}")
    return case, registry, cards, manifest


def prepare_diagnostic_reasoning(context: dict, params: dict) -> dict:
    authority = str(params.get("authority") or _authority_from_step(str(params.get("step_id") or "")))
    case, registry, cards, _manifest = _diagnostic_cards_for(authority, _work(context))
    return {
        "authority": authority,
        "structured_case": case,
        "case_fact_registry": _case_fact_registry(case),
        "variant_registry": _source_variant_registry(registry),
        "reference_material": _reference_material(cards),
        "instructions": {
            "patient_facts_are_immutable": True,
            "clinical_reasoning_only": True,
            "evidence_matching_is_separate": True,
            "internal_graph_is_python_owned": True,
        },
    }


def _diagnostic_reasoning(ctx, authority: str) -> dict:
    value = ctx.get(_DIAGNOSTIC_REASONING_KEYS[authority])
    return value if isinstance(value, dict) else {}


def _simple_reasoning_issues(document: dict, *, authority: str, case: dict, internal_registry: dict) -> list[AuditIssue]:
    issues = _contract_issues(document, "diagnostic_reasoning.json") if isinstance(document, dict) else [
        AuditIssue("missing_reasoning_output", "$", "clinical reasoning output is missing", "return the complete clinical reasoning YAML mapping")
    ]
    if not isinstance(document, dict):
        return issues
    if document.get("authority") != authority:
        issues.append(AuditIssue("wrong_authority", "$.authority", f"returned {document.get('authority')!r}, expected {authority!r}", f"set authority to {authority!r}"))
    facts = set(_case_fact_registry(case))
    internal_by_source, _ = _variant_aliases(internal_registry)
    source_variants = set(internal_by_source)
    diagnosis = document.get("diagnosis") or {}
    if authority in {"who5", "icc"} and diagnosis.get("status") != "established":
        issues.append(AuditIssue("invalid_primary_status", "$.diagnosis.status", "WHO5/ICC diagnosis status must be established", "set status to established"))
    if authority == "who5" and not isinstance(diagnosis.get("schema_disease"), str):
        issues.append(AuditIssue("missing_who_schema_disease", "$.diagnosis.schema_disease", "WHO5 requires a schema disease", "return the supported WHO5 schema disease"))
    assessments = diagnosis.get("variant_assessments") or []
    assessed = [row.get("variant_id") for row in assessments if isinstance(row, dict)]
    for source in sorted(source_variants - set(assessed)):
        issues.append(AuditIssue("missing_variant_assessment", "$.diagnosis.variant_assessments", f"no assessment was returned for supplied variant {source}", "return one assessment for every supplied variant"))
    for source in sorted(set(assessed) - source_variants):
        issues.append(AuditIssue("unknown_variant_assessment", "$.diagnosis.variant_assessments", f"assessment references unknown source variant {source}", "use the supplied source-facing variant IDs"))
    for source in sorted({x for x in assessed if x and assessed.count(x) > 1}):
        issues.append(AuditIssue("duplicate_variant_assessment", "$.diagnosis.variant_assessments", f"variant {source} is assessed more than once", "return exactly one assessment per variant"))
    supporting = 0
    for i, row in enumerate(document.get("reasoning") or []):
        if not isinstance(row, dict):
            continue
        for j, fid in enumerate(row.get("case_fact_ids") or []):
            if fid not in facts:
                issues.append(AuditIssue("unknown_case_fact_id", f"$.reasoning[{i}].case_fact_ids[{j}]", f"case fact {fid!r} was not supplied", "reference only supplied C... fact IDs"))
        for j, vid in enumerate(row.get("variant_ids") or []):
            if vid not in source_variants:
                issues.append(AuditIssue("unknown_variant_id", f"$.reasoning[{i}].variant_ids[{j}]", f"source variant {vid!r} was not supplied", "reference only supplied source-facing variant IDs such as V1"))
        if row.get("supports_conclusion") is True:
            supporting += 1
            if row.get("assessment") != "met":
                issues.append(AuditIssue("non_supporting_conclusion_item", f"$.reasoning[{i}].supports_conclusion", f"this conclusion-supporting reasoning point has assessment {row.get('assessment')!r}, not met", "phrase the supporting proposition so it is met when it supports the proposed conclusion, or set supports_conclusion to false"))
    requires_root = diagnosis.get("diagnostic_effect") in {"refined", "superseded"} or (authority == "second_diagnosis" and diagnosis.get("status") == "established")
    if requires_root and not supporting:
        issues.append(AuditIssue("missing_conclusion_basis", "$.reasoning", "the diagnosis changes/establishes a diagnosis but no reasoning point is marked as supporting the conclusion", "mark the minimal defining reasoning point(s) with supports_conclusion: true"))
    return issues

def validate_diagnostic_reasoning_v2(context: dict, params: dict) -> dict:
    authority = str(params.get("authority") or _authority_from_step(str(params.get("step_id") or "")))
    ctx = _workflow_context(context)
    case, registry, _cards, _manifest = _diagnostic_cards_for(authority, _work(context))
    output = _diagnostic_reasoning(ctx, authority)
    issues = _simple_reasoning_issues(output, authority=authority, case=case, internal_registry=registry)
    return {"authority": authority, "status": "pass" if not issues else "fail", "issue_count": len(issues), "feedback": render_feedback(issues), "issues": [x.__dict__ for x in issues]}


def prepare_diagnostic_evidence_match(context: dict, params: dict) -> list[dict]:
    authority = str(params.get("authority") or _authority_from_step(str(params.get("step_id") or "")))
    ctx = _workflow_context(context)
    owner = _diagnostic_reasoning(ctx, authority)
    _case, _registry, cards, manifest = _diagnostic_cards_for(authority, _work(context))
    envelope = _candidate_card_envelope(cards, manifest)
    return [
        {
            "authority": authority,
            "reasoning_id": f"R{i}",
            "rule": row.get("rule"),
            "candidate_cards": envelope,
        }
        for i, row in enumerate(owner.get("reasoning") or [], 1) if isinstance(row, dict)
    ]

def _validate_simple_em(output: Any, match_items: list[dict]) -> list[AuditIssue]:
    issues = _contract_issues(output, "evidence_match.json") if isinstance(output, dict) else [
        AuditIssue("missing_evidence_match", "$", "evidence matching output is missing", "return one assignment row for each supplied reasoning item")
    ]
    if not isinstance(output, dict):
        return issues
    expected = {str(row.get("reasoning_id")): row for row in match_items}
    seen: set[str] = set()
    for i, row in enumerate(output.get("assignments") or []):
        if not isinstance(row, dict):
            continue
        rid = str(row.get("reasoning_id") or "")
        if rid not in expected:
            issues.append(AuditIssue("unknown_reasoning_id", f"$.assignments[{i}].reasoning_id", f"unexpected reasoning ID {rid!r}", "match only the supplied reasoning items")); continue
        if rid in seen:
            issues.append(AuditIssue("duplicate_reasoning_assignment", f"$.assignments[{i}].reasoning_id", f"reasoning item {rid} appears more than once", "return exactly one assignment row per reasoning item"))
        seen.add(rid)
        allowed = {c.get("card_tag") for c in expected[rid].get("candidate_cards") or [] if isinstance(c, dict)}
        for j, tag in enumerate(row.get("card_tags") or []):
            if tag not in allowed:
                issues.append(AuditIssue("card_outside_owner_envelope", f"$.assignments[{i}].card_tags[{j}]", f"card {tag!r} is outside the supplied candidate envelope", "use only supplied card tags"))
    for rid in sorted(set(expected) - seen):
        issues.append(AuditIssue("missing_reasoning_assignment", "$.assignments", f"no evidence assignment was returned for {rid}", "return one row for this reasoning item; use card_tags: [] if no supplied card supports it"))
    return issues


def validate_diagnostic_evidence_match(context: dict, params: dict) -> dict:
    authority = str(params.get("authority") or _authority_from_step(str(params.get("step_id") or "")))
    ctx = _workflow_context(context)
    items = ctx.get(_DIAGNOSTIC_EM_ITEM_KEYS[authority]) or []
    output = ctx.get(_DIAGNOSTIC_EM_KEYS[authority]) or {}
    issues = _validate_simple_em(output, items)
    return {"authority": authority, "status": "pass" if not issues else "fail", "issue_count": len(issues), "feedback": render_feedback(issues), "issues": [x.__dict__ for x in issues]}


def _compile_diagnostic_owner(authority: str, reasoning: dict, internal_registry: dict) -> dict:
    prefix = _AUTHORITY_PREFIX[authority]
    internal_by_source, _ = _variant_aliases(internal_registry)
    diagnosis = reasoning.get("diagnosis") or {}
    rows = [x for x in reasoning.get("reasoning") or [] if isinstance(x, dict)]
    rules = []
    criteria = []
    supporting_criteria = []
    for i, row in enumerate(rows, 1):
        rule_id = f"{prefix}RULE-{i:03d}"
        criterion_id = f"{prefix}CRITERION-{i:03d}"
        rules.append({"rule_id": rule_id, "statement": row.get("rule"), "evidence_required": True, "evidence_card_tags": []})
        criteria.append({
            "criterion_id": criterion_id,
            "rule_ids": [rule_id],
            "case_fact_ids": list(row.get("case_fact_ids") or []),
            "variant_ids": [internal_by_source[x] for x in row.get("variant_ids") or []],
            "state_ids": [],
            "proposed_status": row.get("assessment"),
        })
        if row.get("supports_conclusion") is True:
            supporting_criteria.append(criterion_id)
    conclusion = reasoning.get("conclusion") or {}
    logic = []
    if len(supporting_criteria) == 1:
        root_id = supporting_criteria[0]
    elif len(supporting_criteria) > 1:
        root_id = f"{prefix}LOGIC-001"
        logic.append({"logic_id": root_id, "operator": conclusion.get("operator") or "all_of", "members": supporting_criteria})
    else:
        root_id = None
    assessments = []
    for row in diagnosis.get("variant_assessments") or []:
        source = row.get("variant_id")
        assessments.append({
            "variant_id": internal_by_source[source],
            "classification": row.get("classification"),
            "other_pathology": row.get("other_pathology"),
            "reason": row.get("reason"),
        })
    if authority in {"who5", "icc"}:
        diagnostic_variants = [x["variant_id"] for x in assessments if x.get("classification") == "diagnostic_for_primary"]
        kind = "diagnosis"
        status = "established"
    else:
        diagnostic_variants = [x["variant_id"] for x in assessments if x.get("classification") == "diagnostic_for_other_pathology"]
        kind = "second_diagnosis"
        status = diagnosis.get("status")
        if status == "none":
            diagnostic_variants = []
    owner = {
        "authority": authority,
        "proposal": {
            "proposal_id": f"{prefix}PROPOSAL-001",
            "label": diagnosis.get("label"),
            "kind": kind,
            "schema_disease": diagnosis.get("schema_disease"),
            "diagnostic_effect": diagnosis.get("diagnostic_effect"),
            "variant_ids": diagnostic_variants,
            "variant_assessments": assessments,
            "status": status,
        },
        "rules": rules,
        "derived_states": [],
        "criteria": criteria,
        "logic": logic,
        "root_id": root_id,
        "reason": reasoning.get("reason"),
    }
    problems = _contract_issues(owner, "diagnostic_owner.json")
    if problems:
        raise ValueError("Python diagnostic compiler produced an invalid internal owner artifact:\n" + render_feedback(problems))
    return owner

def compile_diagnostic_reasoning(context: dict, params: dict) -> dict:
    authority = str(params.get("authority") or _authority_from_step(str(params.get("step_id") or "")))
    ctx = _workflow_context(context)
    _case, registry, _cards, _manifest = _diagnostic_cards_for(authority, _work(context))
    return _compile_diagnostic_owner(authority, _diagnostic_reasoning(ctx, authority), registry)


def _diag_atomic_rule_map(ctx, authority: str) -> dict[str, str]:
    reasoning = _diagnostic_reasoning(ctx, authority)
    owner = _read_owner_artifact(ctx, authority)
    atomic = [x for x in owner.get("rules") or [] if isinstance(x, dict)]
    return {f"R{i}": str(rule.get("rule_id")) for i, rule in enumerate(atomic, 1)}

def merge_diagnostic_evidence_matches(context: dict, params: dict) -> dict:
    ctx = _workflow_context(context)
    pairs = []
    unassigned = []
    for authority in DIAGNOSTIC_AUTHORITIES:
        mapping = _diag_atomic_rule_map(ctx, authority)
        items = {x.get("reasoning_id"): x for x in (ctx.get(_DIAGNOSTIC_EM_ITEM_KEYS[authority]) or [])}
        output = ctx.get(_DIAGNOSTIC_EM_KEYS[authority]) or {"assignments": []}
        assigned_atomic: set[str] = set()
        for row in output.get("assignments") or []:
            rid = row.get("reasoning_id"); atomic = mapping.get(rid); item = items.get(rid) or {}
            if not atomic:
                continue
            cards = {c.get("card_tag"): c for c in item.get("candidate_cards") or [] if isinstance(c, dict)}
            for tag in row.get("card_tags") or []:
                if tag in cards:
                    assigned_atomic.add(atomic)
                    rule = next((r for r in _read_owner_artifact(ctx, authority).get("rules") or [] if r.get("rule_id") == atomic), {})
                    pairs.append({"authority": authority, "rule_id": atomic, "statement": rule.get("statement"), "card_tag": tag, "card": cards[tag], "source": "evidence_match"})
        for atomic in mapping.values():
            if atomic not in assigned_atomic:
                unassigned.append(atomic)
    return {"pairs": pairs, "unassigned_rule_ids": unassigned}


def diagnostic_em_audit_review(context: dict, params: dict) -> dict:
    """Route only demonstrably bad card assignments back to the matching pass."""
    authority = str(params.get("authority") or _authority_from_step(str(params.get("step_id") or "")))
    ctx = _workflow_context(context)
    mapping = _diag_atomic_rule_map(ctx, authority)
    atomic_to_simple = {v: k for k, v in mapping.items()}
    audit = ctx.get("diagnostic_evidence_audit") or {}
    bad = [row for row in audit.get("audits") or [] if row.get("rule_id") in atomic_to_simple and row.get("supports_rule") is False]
    issues = [
        AuditIssue(
            "unsupported_card_assignment", f"$.assignments.{atomic_to_simple.get(row.get('rule_id'))}",
            f"Evidence auditor rejected {row.get('card_tag')} for {atomic_to_simple.get(row.get('rule_id'))}: {'; '.join(row.get('comments') or []) or 'card does not support the stated rule'}",
            "rematch this unchanged reasoning rule using only genuinely supporting supplied cards; use [] if none support it",
        ) for row in bad
    ]
    return {"authority": authority, "status": "pass" if not issues else "fail", "feedback": render_feedback(issues), "issues": [x.__dict__ for x in issues]}


def _ptbg_cards_for(domain: str, context: dict) -> tuple[dict, dict, list[dict], dict, dict]:
    ctx = _workflow_context(context)
    work = _work(context)
    from workflows.proforma_v1 import runtime, self_runtime as sr, step as staged
    case, registry = sr.load_case_registry(work)
    _all_cards, eligible, _digest, manifest = sr.corpus_state(work)
    diagnosis = ctx.get("diagnosis") or {}
    disease = ((diagnosis.get("who5") or {}).get("schema_disease") if isinstance(diagnosis, dict) else None)
    if not disease:
        path = sr.output_path(work, "diagnosis", "diagnosis-final.yaml")
        if path.is_file():
            diagnosis = sr.read_yaml(path)
            disease = (diagnosis.get("who5") or {}).get("schema_disease")
    if not disease:
        raise ValueError(f"{domain} reasoning requires an authoritative WHO5 schema disease")
    cards = staged._draw_domain_cards(eligible, domain, runtime.case_genes(case), [disease])
    return case, registry, cards, manifest, diagnosis


def prepare_ptbg_reasoning(context: dict, params: dict) -> dict:
    domain = str(params.get("domain") or _ptbg_domain_from_step(str(params.get("step_id") or "")))
    case, registry, cards, _manifest, diagnosis = _ptbg_cards_for(domain, context)
    return {
        "domain": domain,
        "structured_case": case,
        "case_fact_registry": _case_fact_registry(case),
        "variant_registry": _source_variant_registry(registry),
        "authoritative_diagnosis": {
            "who5": diagnosis.get("who5") or {},
            "icc": diagnosis.get("icc") or {},
            "concurrent_pathology": list(diagnosis.get("concurrent_pathology") or []),
        },
        "reference_material": _reference_material(cards),
        "instructions": {
            "patient_facts_are_immutable": True,
            "clinical_reasoning_only": True,
            "evidence_matching_is_separate": True,
            "internal_graph_is_python_owned": True,
        },
    }


def _ptbg_reasoning(ctx, domain: str) -> dict:
    value = ctx.get(_PTBG_REASONING_KEYS[domain])
    return value if isinstance(value, dict) else {}


def _simple_ptbg_issues(document: dict, *, domain: str, case: dict, internal_registry: dict) -> list[AuditIssue]:
    issues = _contract_issues(document, "ptbg_reasoning.json") if isinstance(document, dict) else [AuditIssue("missing_reasoning_output", "$", "clinical reasoning output is missing", "return the complete clinical reasoning YAML mapping")]
    if not isinstance(document, dict):
        return issues
    if document.get("domain") != domain:
        issues.append(AuditIssue("wrong_ptbg_domain", "$.domain", f"returned {document.get('domain')!r}, expected {domain!r}", f"set domain to {domain!r}"))
    facts = set(_case_fact_registry(case)); internal_by_source, _ = _variant_aliases(internal_registry); sources = set(internal_by_source)
    for pi, prop in enumerate(document.get("propositions") or []):
        if not isinstance(prop, dict):
            continue
        base = f"$.propositions[{pi}]"
        for vi, vid in enumerate(prop.get("variant_ids") or []):
            if vid not in sources:
                issues.append(AuditIssue("unknown_variant_id", f"{base}.variant_ids[{vi}]", f"source variant {vid!r} was not supplied", "reference only source-facing supplied variants"))
        supporting = 0
        for ri, row in enumerate(prop.get("reasoning") or []):
            if not isinstance(row, dict):
                continue
            for fid in row.get("case_fact_ids") or []:
                if fid not in facts:
                    issues.append(AuditIssue("unknown_case_fact_id", f"{base}.reasoning[{ri}].case_fact_ids", f"case fact {fid!r} was not supplied", "reference only supplied C... fact IDs"))
            for vid in row.get("variant_ids") or []:
                if vid not in sources:
                    issues.append(AuditIssue("unknown_variant_id", f"{base}.reasoning[{ri}].variant_ids", f"source variant {vid!r} was not supplied", "reference only source-facing supplied variants"))
            if row.get("supports_conclusion") is True:
                supporting += 1
                if row.get("assessment") != "met":
                    issues.append(AuditIssue("non_supporting_conclusion_item", f"{base}.reasoning[{ri}].supports_conclusion", f"this conclusion-supporting reasoning point has assessment {row.get('assessment')!r}, not met", "phrase the supporting proposition so it is met when it supports the proposition, or set supports_conclusion to false"))
        if prop.get("reportable") and not supporting:
            issues.append(AuditIssue("reportable_without_reasoning", f"{base}.reasoning", "reportable proposition has no reasoning point marked as supporting its conclusion", "mark the minimal supporting reasoning point(s) with supports_conclusion: true"))
        if domain == "germline" and prop.get("bucket") not in {"germline_suspicious", "germline_against", "germline_uncertain"}:
            issues.append(AuditIssue("invalid_germline_bucket", f"{base}.bucket", f"unsupported germline bucket {prop.get('bucket')!r}", "use germline_suspicious, germline_against or germline_uncertain"))
    return issues

def validate_ptbg_reasoning_v2(context: dict, params: dict) -> dict:
    domain = str(params.get("domain") or _ptbg_domain_from_step(str(params.get("step_id") or "")))
    ctx = _workflow_context(context)
    case, registry, _cards, _manifest, _diagnosis = _ptbg_cards_for(domain, context)
    issues = _simple_ptbg_issues(_ptbg_reasoning(ctx, domain), domain=domain, case=case, internal_registry=registry)
    return {"domain": domain, "status": "pass" if not issues else "fail", "issue_count": len(issues), "feedback": render_feedback(issues), "issues": [x.__dict__ for x in issues]}


def prepare_ptbg_evidence_match(context: dict, params: dict) -> list[dict]:
    return prepare_ptbg_evidence_match_v2(context, params)

def validate_ptbg_evidence_match(context: dict, params: dict) -> dict:
    domain = str(params.get("domain") or _ptbg_domain_from_step(str(params.get("step_id") or "")))
    ctx = _workflow_context(context)
    items = ctx.get(_PTBG_EM_ITEM_KEYS[domain]) or []
    output = ctx.get(_PTBG_EM_KEYS[domain]) or {}
    issues = _validate_simple_em(output, items)
    return {
        "domain": domain,
        "status": "pass" if not issues else "fail",
        "issue_count": len(issues),
        "feedback": render_feedback(issues),
        "issues": [x.__dict__ for x in issues],
    }


def _ptbg_flat_rows(reasoning: dict):
    rows=[]
    n=0
    for pi, prop in enumerate(reasoning.get("propositions") or [],1):
        for local in prop.get("reasoning") or []:
            if not isinstance(local,dict): continue
            n+=1; rows.append((f"R{n}",pi,local))
    return rows


def prepare_ptbg_evidence_match_v2(context: dict, params: dict) -> list[dict]:
    domain = str(params.get("domain") or _ptbg_domain_from_step(str(params.get("step_id") or "")))
    ctx = _workflow_context(context)
    reasoning = _ptbg_reasoning(ctx, domain)
    _case, _registry, cards, manifest, _diagnosis = _ptbg_cards_for(domain, context)
    envelope = _candidate_card_envelope(cards, manifest)
    return [
        {
            "domain": domain,
            "proposition_index": pi,
            "reasoning_id": flat_id,
            "rule": row.get("rule"),
            "candidate_cards": envelope,
        }
        for flat_id, pi, row in _ptbg_flat_rows(reasoning)
    ]

def _compile_ptbg_owner(domain: str, reasoning: dict, internal_registry: dict) -> dict:
    prefix = PTBG_PREFIX[domain]
    internal_by_source, _ = _variant_aliases(internal_registry)
    propositions = []
    for pi, prop in enumerate(reasoning.get("propositions") or [], 1):
        pid = f"{prefix}PROPOSITION-{pi:03d}"
        local_rows = [x for x in prop.get("reasoning") or [] if isinstance(x, dict)]
        rules = []
        apps = []
        supporting_apps = []
        for ri, row in enumerate(local_rows, 1):
            rule_id = f"{prefix}RULE-{pi:03d}-{ri:03d}"
            app_id = f"{prefix}APPLICATION-{pi:03d}-{ri:03d}"
            rules.append({"rule_id": rule_id, "statement": row.get("rule"), "evidence_required": True, "proposed_card_tags": [], "direct_requirement": None})
            apps.append({"application_id": app_id, "rule_ids": [rule_id], "case_fact_ids": list(row.get("case_fact_ids") or []), "state_ids": [], "mode": "semantic", "direct_match": None, "proposed_status": row.get("assessment"), "reason": row.get("reason")})
            if row.get("supports_conclusion") is True:
                supporting_apps.append(app_id)
        framework_name = prop.get("framework")
        propositions.append({
            "proposition_id": pid,
            "bucket": prop.get("bucket"),
            "text": prop.get("text"),
            "reason": prop.get("reason"),
            "variant_ids": [internal_by_source[x] for x in prop.get("variant_ids") or []],
            "reportable": bool(prop.get("reportable")),
            "rules": rules,
            "derived_states": [],
            "applications": apps,
            "conclusion": {"operator": (prop.get("conclusion") or {}).get("operator") or "all_of", "application_ids": supporting_apps},
            "framework": ({"name": framework_name, "applicability_application_id": supporting_apps[0]} if framework_name and supporting_apps else None),
            "worksheet": [],
        })
    owner = {"domain": domain, "propositions": propositions}
    problems = _contract_issues(owner, "ptbg_owner.json")
    if problems:
        raise ValueError("Python PTBG compiler produced an invalid internal owner artifact:\n" + render_feedback(problems))
    return owner

def compile_ptbg_reasoning(context: dict, params: dict) -> dict:
    domain=str(params.get("domain") or _ptbg_domain_from_step(str(params.get("step_id") or ""))); _case,registry,_cards,_manifest,_diagnosis=_ptbg_cards_for(domain,context); ctx=_workflow_context(context)
    return _compile_ptbg_owner(domain,_ptbg_reasoning(ctx,domain),registry)


def _ptbg_atomic_rule_map(ctx,domain:str) -> dict[str,str]:
    reasoning=_ptbg_reasoning(ctx,domain); owner=_ptbg_owner({"__workflow_context__":ctx},domain); mapping={}; flat=_ptbg_flat_rows(reasoning); atomic=[]
    for prop in owner.get("propositions") or []: atomic.extend(prop.get("rules") or [])
    for (flat_id,_pi,_row),rule in zip(flat,atomic): mapping[flat_id]=rule.get("rule_id")
    return mapping


def merge_ptbg_evidence_matches(context: dict, params: dict) -> dict:
    ctx=_workflow_context(context); pairs=[]; by_rule={}
    for domain in PTBG_DOMAINS:
        mapping=_ptbg_atomic_rule_map(ctx,domain); items={x.get("reasoning_id"):x for x in ctx.get(_PTBG_EM_ITEM_KEYS[domain]) or []}; output=ctx.get(_PTBG_EM_KEYS[domain]) or {"assignments":[]}
        for row in output.get("assignments") or []:
            rid=row.get("reasoning_id"); atomic=mapping.get(rid); item=items.get(rid) or {}; cards={c.get("card_tag"):c for c in item.get("candidate_cards") or [] if isinstance(c,dict)}
            if not atomic: continue
            by_rule.setdefault(atomic,[])
            for tag in row.get("card_tags") or []:
                if tag in cards and tag not in by_rule[atomic]: by_rule[atomic].append(tag); pairs.append({"rule_id":atomic,"card_tag":tag,"source":"evidence_match"})
    registry=ctx.get("ptbg_atomic_registry") or {}
    for rule in registry.get("rules") or []: by_rule.setdefault(rule.get("rule_id"),[])
    return {"pairs":pairs,"card_tags_by_rule":by_rule}


def ptbg_em_audit_review(context: dict, params: dict) -> dict:
    domain=str(params.get("domain") or _ptbg_domain_from_step(str(params.get("step_id") or ""))); ctx=_workflow_context(context); mapping=_ptbg_atomic_rule_map(ctx,domain); atomic_to_simple={v:k for k,v in mapping.items()}; audit=ctx.get("ptbg_evidence_audit") or {}
    bad=[row for row in audit.get("audits") or [] if row.get("rule_id") in atomic_to_simple and row.get("supports_rule") is False]
    issues=[AuditIssue("unsupported_card_assignment",f"$.assignments.{atomic_to_simple.get(row.get('rule_id'))}",f"Evidence auditor rejected {row.get('card_tag')} for {atomic_to_simple.get(row.get('rule_id'))}: {'; '.join(row.get('comments') or []) or 'card does not support the stated rule'}","rematch this unchanged reasoning rule using only genuinely supporting supplied cards; use [] if none support it") for row in bad]
    return {"domain":domain,"status":"pass" if not issues else "fail","feedback":render_feedback(issues),"issues":[x.__dict__ for x in issues]}


# Preserve the Phase-3 evaluators but rewrite owner-facing feedback so retries
# never expose internal graph IDs.
_phase3_evaluate_diagnoses = evaluate_diagnoses
_phase3_ptbg_owner_review = ptbg_owner_review
_phase3_build_decision_ledger = build_decision_ledger


def evaluate_diagnoses_v2(context: dict, params: dict) -> dict:
    result = _phase3_evaluate_diagnoses(context, params)
    ctx = _workflow_context(context)
    for authority in DIAGNOSTIC_AUTHORITIES:
        if (result.get("owner_status") or {}).get(authority) == "pass":
            continue
        owner = _diagnostic_reasoning(ctx, authority)
        atomic = _read_owner_artifact(ctx, authority)
        simple_rows = [x for x in owner.get("reasoning") or [] if isinstance(x, dict)]
        mapping = {c.get("criterion_id"): (f"R{i}", simple) for i, (c, simple) in enumerate(zip(atomic.get("criteria") or [], simple_rows), 1) if isinstance(c, dict)}
        problems = []
        detail = (result.get("detail") or {}).get(authority) or {}
        crit_status = detail.get("criterion_status") or {}
        for criterion in atomic.get("criteria") or []:
            cid = criterion.get("criterion_id")
            status = crit_status.get(cid, "unknown")
            if status != "met":
                rid, simple = mapping.get(cid, ("reasoning item", {}))
                problems.append(f"{rid}: patient applicability was {status} for rule: {simple.get('rule')}. Reassess this clinical reasoning point from the supplied facts.")
        evidence = (ctx.get("diagnostic_evidence_decisions") or {}).get("rule_support") or {}
        for i, (rule, simple) in enumerate(zip(atomic.get("rules") or [], simple_rows), 1):
            if not evidence.get(rule.get("rule_id"), False):
                problems.append(f"R{i}: no supplied evidence survived audit for rule: {simple.get('rule')}. Revise or remove this unsupported clinical rule; do not invent evidence.")
        if not problems:
            problems = ["The proposed diagnosis did not survive the grouped evidence/reasoning audit. Reassess the minimal reasoning supporting the conclusion."]
        result.setdefault("feedback", {})[authority] = "Clinical reasoning requires revision. Fix the following without changing supplied patient facts:\n- " + "\n- ".join(dict.fromkeys(problems)) + "\n"
    return result

def ptbg_owner_review_v2(context: dict, params: dict) -> dict:
    raw=_phase3_ptbg_owner_review(context,params)
    if raw.get("status")=="pass": return raw
    domain=str(params.get("domain") or _ptbg_domain_from_step(str(params.get("step_id") or ""))); ctx=_workflow_context(context); reasoning=_ptbg_reasoning(ctx,domain); eval_rows=(ctx.get("ptbg_evaluation") or {}).get("by_domain",{}).get(domain,[]) or []
    problems=[]
    for simple,erow in zip(reasoning.get("propositions") or [],eval_rows):
        if erow.get("disposition") in {"dropped","unresolved"}: problems.append(f"Proposition '{simple.get('text')}': {erow.get('reason')} Reassess its clinical reasoning and patient applicability.")
    if not problems: problems=["One or more propositions did not survive the grouped PTBG evidence/reasoning audit."]
    issues=[AuditIssue("unsupported_ptbg_proposition",f"$.{domain}",p,"revise the clinical reasoning only; evidence matching will run separately") for p in problems]
    return {"status":"fail","feedback":render_feedback(issues),"issues":[x.__dict__ for x in issues]}


def build_decision_ledger_v2(context: dict, params: dict) -> dict:
    """Give the existing ledger builder the canonical internal variant registry."""
    ctx=_workflow_context(context); work=_work(context)
    try:
        from workflows.proforma_v1 import self_runtime as sr
        _case,internal=sr.load_case_registry(work)
    except Exception:
        internal={}
    saved={}
    keys=[_owner_pack_key(a) for a in DIAGNOSTIC_AUTHORITIES]+[_ptbg_pack_key(d) for d in PTBG_DOMAINS]
    for key in keys:
        pack=ctx.get(key)
        if isinstance(pack,dict): saved[key]=pack.get("variant_registry"); pack["variant_registry"]=internal
    try: return _phase3_build_decision_ledger(context,params)
    finally:
        for key,value in saved.items():
            pack=ctx.get(key)
            if isinstance(pack,dict): pack["variant_registry"]=value


def _accepted_card_rows_v2(ctx, tags: list[str]) -> list[dict]:
    catalog={}
    for key in [*_DIAGNOSTIC_EM_ITEM_KEYS.values(), *_PTBG_EM_ITEM_KEYS.values()]:
        for item in ctx.get(key) or []:
            for card in item.get("candidate_cards") or [] if isinstance(item,dict) else []:
                if isinstance(card,dict) and card.get("card_tag"): catalog.setdefault(card["card_tag"],card)
    out=[]
    for tag in tags:
        card=catalog.get(tag) or {}; cid=card.get("card_id")
        if cid: out.append({"card_tag":tag,"card_id":cid})
    return out

# Global lookup by finalization/ledger functions resolves this latest definition.
_accepted_card_rows = _accepted_card_rows_v2


# Final dispatchers for the judgement-separated workflow. Phase-3 names remain
# available for old reasoning artifacts, but the new workflow uses only these
# v2 transforms for owner/EM preparation and compilation.
_phase3_run_diagnostic_transform = run_diagnostic_transform
_phase3_run_ptbg_transform = run_ptbg_transform

def run_diagnostic_transform(name: str, context: dict, params: dict) -> Any:
    dispatch={
        "reasoning_prepare_diagnostic_reasoning":prepare_diagnostic_reasoning,
        "reasoning_validate_diagnostic_reasoning_v2":validate_diagnostic_reasoning_v2,
        "reasoning_prepare_diagnostic_evidence_match":prepare_diagnostic_evidence_match,
        "reasoning_validate_diagnostic_evidence_match":validate_diagnostic_evidence_match,
        "reasoning_compile_diagnostic_reasoning":compile_diagnostic_reasoning,
        "reasoning_merge_diagnostic_evidence_matches":merge_diagnostic_evidence_matches,
        "reasoning_diagnostic_em_audit_review":diagnostic_em_audit_review,
        "reasoning_evaluate_diagnoses_v2":evaluate_diagnoses_v2,
    }
    if name in dispatch: return dispatch[name](context,params)
    return _phase3_run_diagnostic_transform(name,context,params)


def run_ptbg_transform(name: str, context: dict, params: dict) -> Any:
    dispatch={
        "reasoning_prepare_ptbg_reasoning":prepare_ptbg_reasoning,
        "reasoning_validate_ptbg_reasoning_v2":validate_ptbg_reasoning_v2,
        "reasoning_prepare_ptbg_evidence_match_v2":prepare_ptbg_evidence_match_v2,
        "reasoning_validate_ptbg_evidence_match":validate_ptbg_evidence_match,
        "reasoning_compile_ptbg_reasoning":compile_ptbg_reasoning,
        "reasoning_merge_ptbg_evidence_matches":merge_ptbg_evidence_matches,
        "reasoning_ptbg_em_audit_review":ptbg_em_audit_review,
        "reasoning_ptbg_owner_review_v2":ptbg_owner_review_v2,
        "reasoning_build_decision_ledger_v2":build_decision_ledger_v2,
    }
    if name in dispatch: return dispatch[name](context,params)
    return _phase3_run_ptbg_transform(name,context,params)

# ===========================================================================
# Reasoning workflow hardening: domain contracts, conclusion coherence,
# compact evidence matching and concise report synthesis.
# ===========================================================================

_PTBG_REASONING_SCHEMAS = {
    "prognosis": "prognosis_reasoning.json",
    "treatment": "treatment_reasoning.json",
    "biomarker": "biomarker_reasoning.json",
    "germline": "germline_reasoning.json",
}
_PTBG_BUCKET_REPORTABLE = {
    "prognosis": {
        "framework_favorable": True, "framework_adverse": True, "framework_neutral": True,
        "other_evidence_favorable": True, "other_evidence_adverse": True,
        "other_evidence_neutral": True, "no_prognostic_evidence": False,
        "framework_assessment": True,
    },
    "treatment": {"drug_target": True, "drug_sensitive": True, "drug_resistant": True, "no_drug_implication": False},
    "biomarker": {"mrd_marker": True, "not_mrd_marker": False},
    "germline": {"germline_suspicious": True, "germline_against": False, "germline_uncertain": False},
}
_PROGNOSTIC_FRAMEWORK_LINE_RE = re.compile(r"^- ([^:]+): `([^`]+)`\s*$")


def _parse_prognostic_framework_preset(text: str) -> dict[str, tuple[str, ...]]:
    """Parse the versioned prognostic-framework module's deterministic preset."""
    parsed: dict[str, list[str]] = {}
    saw_bullet = False
    for line in text.splitlines():
        if not line.startswith("- "):
            continue
        saw_bullet = True
        match = _PROGNOSTIC_FRAMEWORK_LINE_RE.fullmatch(line)
        if match is None:
            raise ValueError(f"invalid prognostic framework preset line: {line!r}")
        disease, framework = (part.strip() for part in match.groups())
        if not disease or not framework:
            raise ValueError(f"invalid prognostic framework preset line: {line!r}")
        parsed.setdefault(disease, []).append(framework)
    if not saw_bullet or not parsed:
        raise ValueError("prognostic framework prompt module contains no parseable preset entries")
    return {disease: tuple(frameworks) for disease, frameworks in parsed.items()}


def _prognostic_framework_preset() -> dict[str, tuple[str, ...]]:
    spec = default_config.module_spec("prognostic_frameworks")
    if not spec["enabled"]:
        return {}
    path = default_config.module_asset_path("prognostic_frameworks")
    try:
        return _parse_prognostic_framework_preset(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read prognostic framework prompt module {path}: {exc}") from exc


def _source_label_for_card(card: dict) -> str | None:
    """Return a deterministic FirstAuthor et al., YEAR label from card metadata.

    Prefer explicit citation metadata when present; fall back to the canonical
    publication/card key.  This is presentation metadata only and never model
    generated.
    """
    import re
    if not isinstance(card, dict):
        return None
    author = card.get("first_author") or card.get("author") or card.get("authors")
    if isinstance(author, list) and author:
        author = author[0]
    if isinstance(author, str) and author.strip():
        author = author.strip().split(",", 1)[0].split()[0]
    else:
        author = None
    year = card.get("year") or card.get("publication_year")
    if year is not None:
        m = re.search(r"(?:19|20)\d{2}", str(year))
        year = m.group(0) if m else None
    if author and year:
        return f"{author} et al., {year}"
    key = str(card.get("publication_key") or card.get("card_id") or "")
    m = re.search(r"(?:^|/)([A-Za-z][A-Za-z-]*)-((?:19|20)\d{2})(?:-|$)", key)
    if m:
        surname = m.group(1).replace("-", " ").title().replace(" ", "-")
        return f"{surname} et al., {m.group(2)}"
    return None


def _candidate_card_envelope(cards: list[dict], manifest: dict) -> list[dict]:
    """Compact model-facing evidence envelope.

    The canonical full card remains persisted in corpus/card artifacts.  EM does
    not need a second embedded copy of it; sending that copy was the dominant
    source of prompt-token duplication in reasoning runs.
    """
    from workflows.proforma_v1 import card_identity
    tag_by_id = card_identity.tag_by_id(manifest)
    out = []
    for card in cards:
        cid = card.get("card_id")
        token = tag_by_id.get(cid)
        if not token:
            continue
        row = {"card_tag": f"[card:{token}]", "card_id": cid}
        source_label = _source_label_for_card(card)
        if source_label:
            row["source_label"] = source_label
        text = None
        for key in ("interpretation", "claim", "evidence_text", "scope", "notes"):
            value = card.get(key)
            if isinstance(value, str) and value.strip():
                text = value.strip(); break
        if text:
            row["text"] = text
        for key in ("disease", "diseases", "gene", "genes", "framework", "frameworks"):
            value = card.get(key)
            if value not in (None, "", [], {}):
                row[key] = value
        out.append(row)
    return out


def _em_pack(items: list[dict], envelope: list[dict]) -> dict:
    """Cards appear once per EM call rather than once per reasoning item."""
    return {"items": items, "candidate_cards": envelope}


def _em_items(pack: Any) -> list[dict]:
    if isinstance(pack, dict):
        return [x for x in (pack.get("items") or []) if isinstance(x, dict)]
    return [x for x in (pack or []) if isinstance(x, dict)]


def _em_cards(pack: Any) -> list[dict]:
    if isinstance(pack, dict):
        return [x for x in (pack.get("candidate_cards") or []) if isinstance(x, dict)]
    # Backward-compatible read of old repeated-envelope artifacts.
    for row in pack or []:
        if isinstance(row, dict) and isinstance(row.get("candidate_cards"), list):
            return [x for x in row.get("candidate_cards") or [] if isinstance(x, dict)]
    return []


def prepare_diagnostic_evidence_match(context: dict, params: dict) -> dict:
    authority = str(params.get("authority") or _authority_from_step(str(params.get("step_id") or "")))
    ctx = _workflow_context(context)
    owner = _diagnostic_reasoning(ctx, authority)
    _case, _registry, cards, manifest = _diagnostic_cards_for(authority, _work(context))
    items = [{"authority": authority, "reasoning_id": f"R{i}", "rule": row.get("rule")}
             for i, row in enumerate(owner.get("reasoning") or [], 1) if isinstance(row, dict)]
    return _em_pack(items, _candidate_card_envelope(cards, manifest))


def _validate_simple_em(output: Any, match_pack: Any) -> list[AuditIssue]:
    issues = _contract_issues(output, "evidence_match.json") if isinstance(output, dict) else [
        AuditIssue("missing_evidence_match", "$", "evidence matching output is missing", "return one assignment row for each supplied reasoning item")
    ]
    if not isinstance(output, dict):
        return issues
    items = _em_items(match_pack); cards = _em_cards(match_pack)
    allowed = {c.get("card_tag") for c in cards}
    expected = {str(row.get("reasoning_id")): row for row in items}
    seen = set()
    for i, row in enumerate(output.get("assignments") or []):
        if not isinstance(row, dict):
            continue
        rid = str(row.get("reasoning_id") or "")
        if rid not in expected:
            issues.append(AuditIssue("unknown_reasoning_id", f"$.assignments[{i}].reasoning_id", f"unexpected reasoning ID {rid!r}", "match only supplied reasoning items")); continue
        if rid in seen:
            issues.append(AuditIssue("duplicate_reasoning_assignment", f"$.assignments[{i}].reasoning_id", f"reasoning item {rid} appears more than once", "return exactly one assignment row per reasoning item"))
        seen.add(rid)
        for j, tag in enumerate(row.get("card_tags") or []):
            if tag not in allowed:
                issues.append(AuditIssue("card_outside_owner_envelope", f"$.assignments[{i}].card_tags[{j}]", f"card {tag!r} is outside the supplied candidate envelope", "use only supplied card tags"))
    for rid in sorted(set(expected) - seen):
        issues.append(AuditIssue("missing_reasoning_assignment", "$.assignments", f"no evidence assignment was returned for {rid}", "return one row for this reasoning item; use card_tags: [] if no supplied card supports it"))
    return issues


def _authoritative_disease(context: dict) -> str | None:
    ctx = _workflow_context(context)
    diagnosis = ctx.get("diagnosis") or {}
    return ((diagnosis.get("who5") or {}).get("schema_disease") if isinstance(diagnosis, dict) else None)


def _reasoning_points_for_domain(reasoning: dict, domain: str):
    """Yield (flat_id, proposition_key, reasoning_point, conclusion metadata)."""
    n = 0
    if domain == "prognosis":
        for fi, fw in enumerate(reasoning.get("frameworks") or [], 1):
            for row in fw.get("reasoning") or []:
                if isinstance(row, dict):
                    n += 1; yield f"R{n}", f"framework:{fi}", row, {"kind":"framework","framework":fw}
        for vi, va in enumerate(reasoning.get("variant_assessments") or [], 1):
            for ei, fx in enumerate(va.get("framework_effects") or [], 1):
                for row in fx.get("reasoning") or []:
                    if isinstance(row, dict):
                        n += 1; yield f"R{n}", f"variant:{vi}:framework:{ei}", row, {"kind":"framework_effect","variant":va,"effect":fx}
            other = va.get("other_evidence") or {}
            for row in other.get("reasoning") or []:
                if isinstance(row, dict):
                    n += 1; yield f"R{n}", f"variant:{vi}:other", row, {"kind":"other_evidence","variant":va,"other":other}
    elif domain == "treatment":
        for vi, va in enumerate(reasoning.get("variant_assessments") or [], 1):
            for ii, imp in enumerate(va.get("implications") or [], 1):
                for row in imp.get("reasoning") or []:
                    if isinstance(row, dict):
                        n += 1; yield f"R{n}", f"variant:{vi}:implication:{ii}", row, {"kind":"treatment","variant":va,"implication":imp}
    elif domain == "biomarker":
        for vi, va in enumerate(reasoning.get("variant_assessments") or [], 1):
            for row in va.get("reasoning") or []:
                if isinstance(row, dict):
                    n += 1; yield f"R{n}", f"variant:{vi}", row, {"kind":"biomarker","variant":va}
    elif domain == "germline":
        for vi, va in enumerate(reasoning.get("variant_assessments") or [], 1):
            for row in va.get("reasoning") or []:
                if isinstance(row, dict):
                    n += 1; yield f"R{n}", f"variant:{vi}", row, {"kind":"germline","variant":va}


def _simple_ptbg_issues(document: dict, *, domain: str, case: dict, internal_registry: dict) -> list[AuditIssue]:
    schema_name = _PTBG_REASONING_SCHEMAS[domain]
    issues = _contract_issues(document, schema_name) if isinstance(document, dict) else [AuditIssue("missing_reasoning_output", "$", "clinical reasoning output is missing", "return the complete clinical reasoning YAML mapping")]
    if not isinstance(document, dict):
        return issues
    facts = set(_case_fact_registry(case)); internal_by_source, _ = _variant_aliases(internal_registry); sources = set(internal_by_source)
    if document.get("domain") != domain:
        issues.append(AuditIssue("wrong_ptbg_domain", "$.domain", f"returned {document.get('domain')!r}, expected {domain!r}", f"set domain to {domain!r}"))

    # Exhaustive variant coverage is a deterministic completeness invariant.
    assessments = document.get("variant_assessments") or []
    assessed = [x.get("variant_id") for x in assessments if isinstance(x, dict)]
    for source in sorted(sources - set(assessed)):
        issues.append(AuditIssue("missing_variant_assessment", "$.variant_assessments", f"no {domain} assessment was returned for supplied variant {source}", "return one assessment for every supplied variant"))
    for source in sorted(set(assessed) - sources):
        issues.append(AuditIssue("unknown_variant_id", "$.variant_assessments", f"assessment references unknown source variant {source}", "use only supplied source-facing variant IDs"))
    for source in sorted({x for x in assessed if x and assessed.count(x)>1}):
        issues.append(AuditIssue("duplicate_variant_assessment", "$.variant_assessments", f"variant {source} appears more than once", "return exactly one variant assessment; treatment may contain multiple implications inside that assessment"))

    for flat_id, prop_key, row, _meta in _reasoning_points_for_domain(document, domain):
        for fid in row.get("case_fact_ids") or []:
            if fid not in facts:
                issues.append(AuditIssue("unknown_case_fact_id", f"$.{prop_key}.{flat_id}.case_fact_ids", f"case fact {fid!r} was not supplied", "reference only supplied C... fact IDs"))
        for vid in row.get("variant_ids") or []:
            if vid not in sources:
                issues.append(AuditIssue("unknown_variant_id", f"$.{prop_key}.{flat_id}.variant_ids", f"source variant {vid!r} was not supplied", "reference only supplied source-facing variants"))
        if row.get("supports_conclusion") is True and row.get("assessment") != "met":
            issues.append(AuditIssue("non_supporting_conclusion_item", f"$.{prop_key}.{flat_id}.supports_conclusion", "conclusion-supporting reasoning is not met", "set supports_conclusion true only for met reasoning that genuinely supports the conclusion"))

    if domain == "prognosis":
        disease = _authoritative_disease({"__workflow_context__": type("_", (), {"get": lambda self,k,d=None: None})()}) if False else None
        # Use the caller's authoritative disease when available via case bootstrap; validation wrapper adds exact preset check below.
        framework_names = [x.get("name") for x in document.get("frameworks") or [] if isinstance(x, dict) and x.get("applicable")]
        for va in assessments:
            for fx in va.get("framework_effects") or [] if isinstance(va, dict) else []:
                if fx.get("framework") not in framework_names:
                    issues.append(AuditIssue("unknown_framework_effect", "$.variant_assessments.framework_effects", f"framework effect names {fx.get('framework')!r}, which is not an applicable selected framework", "use an exact applicable framework name or remove this framework effect"))
            other = va.get("other_evidence") or {}
            if other.get("effect") == "no_evidence" and other.get("reason") not in (None, ""):
                issues.append(AuditIssue("reason_for_no_evidence", "$.variant_assessments.other_evidence.reason", "no_evidence should not carry a positive prognostic reason", "use reason: null for no_evidence"))
    elif domain == "treatment":
        for va in assessments:
            implications = va.get("implications") or [] if isinstance(va, dict) else []
            cats = [x.get("category") for x in implications if isinstance(x, dict)]
            if "no_drug_implication" in cats and len(cats) > 1:
                issues.append(AuditIssue("exclusive_no_drug_implication", "$.variant_assessments.implications", "no_drug_implication is combined with a positive treatment implication", "use no_drug_implication alone or remove it"))
            for imp in implications:
                if not isinstance(imp, dict): continue
                positive = imp.get("category") in {"drug_target","drug_sensitive","drug_resistant"}
                if positive and not str(imp.get("therapy") or "").strip():
                    issues.append(AuditIssue("missing_therapy", "$.variant_assessments.implications.therapy", "positive treatment implication has no named therapy", "name the therapy associated with this implication"))
                if imp.get("category") == "no_drug_implication" and imp.get("therapy") is not None:
                    issues.append(AuditIssue("therapy_on_no_implication", "$.variant_assessments.implications.therapy", "no_drug_implication must not name a therapy", "use therapy: null"))
    elif domain == "germline":
        for va in assessments:
            if not isinstance(va, dict): continue
            if va.get("eligibility") == "skip_no_predisposition_evidence":
                if va.get("bucket") is not None:
                    issues.append(AuditIssue("bucket_on_skipped_germline", "$.variant_assessments.bucket", "skipped germline finding has a bucket", "use bucket: null when eligibility is skip_no_predisposition_evidence"))
            else:
                factors=[va.get(k) for k in ("event_compatibility","age","vaf","personal_history","family_history","phenotype")]
                if any(x is None for x in factors):
                    issues.append(AuditIssue("incomplete_germline_worksheet", "$.variant_assessments", "eligible germline assessment does not complete every required patient-specific factor", "complete event compatibility, age, VAF, personal history, family history and phenotype"))
    return issues


def validate_ptbg_reasoning_v2(context: dict, params: dict) -> dict:
    domain = str(params.get("domain") or _ptbg_domain_from_step(str(params.get("step_id") or "")))
    ctx = _workflow_context(context); case, registry, _cards, _manifest, _diagnosis = _ptbg_cards_for(domain, context)
    doc = _ptbg_reasoning(ctx, domain)
    issues = _simple_ptbg_issues(doc, domain=domain, case=case, internal_registry=registry)
    if domain == "prognosis":
        preset = _prognostic_framework_preset()
        disease = _authoritative_disease(context)
        required = set(preset.get(str(disease), ())) if disease != "no_haematological_malignancy" else set()
        selected = {x.get("name") for x in doc.get("frameworks") or [] if isinstance(x, dict) and x.get("applicable") is True}
        for name in sorted(required - selected):
            issues.append(AuditIssue("missing_required_prognostic_framework", "$.frameworks", f"authoritative disease {disease!r} requires assessment of prognostic framework {name!r}", f"include {name!r} and assess applicability/tier from supplied findings; use tier: null if a tier cannot be assigned"))
        allowed=set(sum((list(v) for v in preset.values()), []))
        for i, row in enumerate(doc.get("frameworks") or []):
            if isinstance(row,dict) and row.get("name") not in allowed:
                issues.append(AuditIssue("unknown_prognostic_framework", f"$.frameworks[{i}].name", f"{row.get('name')!r} is not an accepted framework", "use only the accepted disease-to-framework preset"))
    return {"domain":domain,"status":"pass" if not issues else "fail","issue_count":len(issues),"feedback":render_feedback(issues),"issues":[x.__dict__ for x in issues]}


def prepare_ptbg_evidence_match_v2(context: dict, params: dict) -> dict:
    domain = str(params.get("domain") or _ptbg_domain_from_step(str(params.get("step_id") or "")))
    ctx=_workflow_context(context); reasoning=_ptbg_reasoning(ctx,domain)
    _case,_registry,cards,manifest,_diagnosis=_ptbg_cards_for(domain,context)
    items=[{"domain":domain,"reasoning_id":rid,"rule":row.get("rule")} for rid,_key,row,_meta in _reasoning_points_for_domain(reasoning,domain)]
    return _em_pack(items,_candidate_card_envelope(cards,manifest))


def _ptbg_flat_rows(reasoning: dict, domain: str | None = None):
    domain = domain or str(reasoning.get("domain") or "")
    return [(rid, key, row) for rid,key,row,_meta in _reasoning_points_for_domain(reasoning,domain)]


def _ptbg_proposition_specs(reasoning: dict, domain: str):
    """Clinical conclusions projected to generic internal proposition specs.

    Reportability is deterministic from the domain/category; the model never
    owns that policy decision.
    """
    specs=[]
    if domain=="prognosis":
        for fi,fw in enumerate(reasoning.get("frameworks") or [],1):
            if not isinstance(fw,dict) or not fw.get("applicable"): continue
            tier=fw.get("tier")
            text=f"{fw.get('name')}" + (f" risk tier: {tier}" if tier else " is the applicable prognostic framework")
            specs.append({"key":f"framework:{fi}","bucket":"framework_assessment","text":text,"reason":fw.get("reason"),"variant_ids":[],"framework":fw.get("name"),"reasoning":fw.get("reasoning") or [],"reportable":True})
        for vi,va in enumerate(reasoning.get("variant_assessments") or [],1):
            vid=va.get("variant_id")
            for ei,fx in enumerate(va.get("framework_effects") or [],1):
                effect=fx.get("effect"); bucket=f"framework_{effect}"
                specs.append({"key":f"variant:{vi}:framework:{ei}","bucket":bucket,"text":fx.get("reason"),"reason":fx.get("reason"),"variant_ids":[vid],"framework":fx.get("framework"),"reasoning":fx.get("reasoning") or [],"reportable":True})
            other=va.get("other_evidence") or {}; effect=other.get("effect")
            bucket="no_prognostic_evidence" if effect=="no_evidence" else f"other_evidence_{effect}"
            specs.append({"key":f"variant:{vi}:other","bucket":bucket,"text":other.get("reason") or f"No disease-applicable prognostic evidence identified for {vid}","reason":other.get("reason") or "No disease-applicable prognostic evidence was identified.","variant_ids":[vid],"framework":None,"reasoning":other.get("reasoning") or [],"reportable":bool(_PTBG_BUCKET_REPORTABLE[domain].get(bucket,False))})
    elif domain=="treatment":
        for vi,va in enumerate(reasoning.get("variant_assessments") or [],1):
            vid=va.get("variant_id")
            for ii,imp in enumerate(va.get("implications") or [],1):
                therapy=imp.get("therapy"); text=(f"{therapy}: {imp.get('reason')}" if therapy else imp.get("reason"))
                bucket=imp.get("category")
                specs.append({"key":f"variant:{vi}:implication:{ii}","bucket":bucket,"text":text,"reason":imp.get("reason"),"variant_ids":[vid],"framework":None,"reasoning":imp.get("reasoning") or [],"reportable":bool(_PTBG_BUCKET_REPORTABLE[domain].get(bucket,False))})
    elif domain=="biomarker":
        for vi,va in enumerate(reasoning.get("variant_assessments") or [],1):
            bucket=va.get("status"); specs.append({"key":f"variant:{vi}","bucket":bucket,"text":va.get("reason"),"reason":va.get("reason"),"variant_ids":[va.get("variant_id")],"framework":None,"reasoning":va.get("reasoning") or [],"reportable":bool(_PTBG_BUCKET_REPORTABLE[domain].get(bucket,False))})
    elif domain=="germline":
        for vi,va in enumerate(reasoning.get("variant_assessments") or [],1):
            if va.get("eligibility")!="assess" or not va.get("bucket"): continue
            bucket=va.get("bucket"); worksheet=[]
            predisposition=va.get("predisposition_evidence")
            if isinstance(predisposition,str) and predisposition.strip():
                worksheet.append({"factor":"predisposition_evidence","status":"supportive","reason":predisposition.strip()})
            for factor in ("event_compatibility","age","vaf","personal_history","family_history","phenotype"):
                row=va.get(factor)
                if isinstance(row,dict): worksheet.append({"factor":factor,"status":row.get("status"),"reason":row.get("reason")})
            specs.append({"key":f"variant:{vi}","bucket":bucket,"text":va.get("reason"),"reason":va.get("reason"),"variant_ids":[va.get("variant_id")],"framework":None,"reasoning":va.get("reasoning") or [],"reportable":bool(_PTBG_BUCKET_REPORTABLE[domain].get(bucket,False)),"worksheet":worksheet})
    return specs


def _compile_ptbg_owner(domain: str, reasoning: dict, internal_registry: dict) -> dict:
    prefix=PTBG_PREFIX[domain]; internal_by_source,_=_variant_aliases(internal_registry); propositions=[]
    flat_counter=0
    for pi,spec in enumerate(_ptbg_proposition_specs(reasoning,domain),1):
        pid=f"{prefix}PROPOSITION-{pi:03d}"; rules=[]; apps=[]; supporting=[]
        for ri,row in enumerate([x for x in spec.get("reasoning") or [] if isinstance(x,dict)],1):
            flat_counter += 1
            rule_id=f"{prefix}RULE-{pi:03d}-{ri:03d}"; app_id=f"{prefix}APPLICATION-{pi:03d}-{ri:03d}"
            rules.append({"rule_id":rule_id,"statement":row.get("rule"),"evidence_required":True,"proposed_card_tags":[],"direct_requirement":None})
            apps.append({"application_id":app_id,"rule_ids":[rule_id],"case_fact_ids":list(row.get("case_fact_ids") or []),"state_ids":[],"mode":"semantic","direct_match":None,"proposed_status":row.get("assessment"),"reason":row.get("reason")})
            if row.get("supports_conclusion") is True: supporting.append(app_id)
        worksheet=[]
        for wi,row in enumerate([x for x in spec.get("worksheet") or [] if isinstance(x,dict)],1):
            status=row.get("status"); aid=None
            # Germline factor interpretation is already a clinical owner judgement.
            # Python only gives supplied/interpretable factors a machine application ID;
            # missing/unassessable factors remain explicitly null.
            if row.get("factor") != "predisposition_evidence" and status not in {"not_supplied","not_assessable"}:
                aid=f"{prefix}APPLICATION-{pi:03d}-F{wi:02d}"
                apps.append({"application_id":aid,"rule_ids":[],"case_fact_ids":[],"state_ids":[],"mode":"semantic","direct_match":None,"proposed_status":"not_met" if status=="discordant" else "met","reason":row.get("reason")})
            worksheet.append({"factor":row.get("factor"),"application_id":aid,"status":status,"reason":row.get("reason")})
        variants=[internal_by_source[x] for x in spec.get("variant_ids") or [] if x in internal_by_source]
        framework=spec.get("framework")
        propositions.append({"proposition_id":pid,"bucket":spec.get("bucket"),"text":spec.get("text") or spec.get("reason"),"reason":spec.get("reason"),"variant_ids":variants,"reportable":bool(spec.get("reportable")),"rules":rules,"derived_states":[],"applications":apps,"conclusion":{"operator":"all_of","application_ids":supporting},"framework":({"name":framework,"applicability_application_id":supporting[0]} if framework and supporting else None),"worksheet":worksheet})
    owner={"domain":domain,"propositions":propositions}; problems=_contract_issues(owner,"ptbg_owner.json")
    if problems: raise ValueError("Python PTBG compiler produced an invalid internal owner artifact:\n"+render_feedback(problems))
    return owner


def _ptbg_atomic_rule_map(ctx, domain: str) -> dict[str,str]:
    reasoning=_ptbg_reasoning(ctx,domain); owner=_ptbg_owner({"__workflow_context__":ctx},domain); mapping={}
    flat=[rid for rid,_key,_row,_meta in _reasoning_points_for_domain(reasoning,domain)]; atomic=[]
    for prop in owner.get("propositions") or []: atomic.extend(prop.get("rules") or [])
    for rid,rule in zip(flat,atomic): mapping[rid]=rule.get("rule_id")
    return mapping


def merge_diagnostic_evidence_matches(context: dict, params: dict) -> dict:
    ctx=_workflow_context(context); pairs=[]; by_rule={}
    for authority in DIAGNOSTIC_AUTHORITIES:
        mapping=_diagnostic_atomic_rule_map(ctx,authority); pack=ctx.get(_DIAGNOSTIC_EM_ITEM_KEYS[authority]) or {}; cards={c.get("card_tag"):c for c in _em_cards(pack)}
        output=ctx.get(_DIAGNOSTIC_EM_KEYS[authority]) or {"assignments":[]}
        for row in output.get("assignments") or []:
            atomic=mapping.get(row.get("reasoning_id"));
            if not atomic: continue
            by_rule.setdefault(atomic,[])
            for tag in row.get("card_tags") or []:
                if tag in cards and tag not in by_rule[atomic]: by_rule[atomic].append(tag); pairs.append({"rule_id":atomic,"card_tag":tag,"source":"evidence_match"})
    registry=ctx.get("diagnostic_atomic_registry") or {}
    for rule in registry.get("rules") or []: by_rule.setdefault(rule.get("rule_id"),[])
    return {"pairs":pairs,"card_tags_by_rule":by_rule}


def merge_ptbg_evidence_matches(context: dict, params: dict) -> dict:
    ctx=_workflow_context(context); pairs=[]; by_rule={}
    for domain in PTBG_DOMAINS:
        mapping=_ptbg_atomic_rule_map(ctx,domain); pack=ctx.get(_PTBG_EM_ITEM_KEYS[domain]) or {}; cards={c.get("card_tag"):c for c in _em_cards(pack)}
        output=ctx.get(_PTBG_EM_KEYS[domain]) or {"assignments":[]}
        for row in output.get("assignments") or []:
            atomic=mapping.get(row.get("reasoning_id"));
            if not atomic: continue
            by_rule.setdefault(atomic,[])
            for tag in row.get("card_tags") or []:
                if tag in cards and tag not in by_rule[atomic]: by_rule[atomic].append(tag); pairs.append({"rule_id":atomic,"card_tag":tag,"source":"evidence_match"})
    registry=ctx.get("ptbg_atomic_registry") or {}
    for rule in registry.get("rules") or []: by_rule.setdefault(rule.get("rule_id"),[])
    return {"pairs":pairs,"card_tags_by_rule":by_rule}


def _accepted_card_rows_v2(ctx, tags: list[str]) -> list[dict]:
    catalog={}
    for key in [*_DIAGNOSTIC_EM_ITEM_KEYS.values(), *_PTBG_EM_ITEM_KEYS.values()]:
        for card in _em_cards(ctx.get(key) or {}):
            if card.get("card_tag"): catalog.setdefault(card["card_tag"],card)
    return [{"card_tag":tag,"card_id":catalog[tag].get("card_id")} for tag in tags if tag in catalog and catalog[tag].get("card_id")]
_accepted_card_rows = _accepted_card_rows_v2


def prepare_diagnostic_reasoning_audit(context: dict, params: dict) -> list[dict]:
    ctx=_workflow_context(context); registry=ctx.get("diagnostic_atomic_registry") or {}; evidence=ctx.get("diagnostic_evidence_decisions") or {}; support=evidence.get("rule_support") or {}
    packs={a:ctx.get(_owner_pack_key(a)) or {} for a in DIAGNOSTIC_AUTHORITIES}
    try:
        from workflows.proforma_v1 import self_runtime as sr
        _case,internal_variants=sr.load_case_registry(_work(context))
    except Exception: internal_variants={}
    items=[]
    for authority in DIAGNOSTIC_AUTHORITIES:
        owner=_read_owner_artifact(ctx,authority); facts=packs[authority].get("case_fact_registry") or {}; states={s.get("state_id"):s for s in owner.get("derived_states") or []}
        for state in states.values():
            items.append({"item_type":"derived_state","authority":authority,"state":state,"case_facts":[facts[x] for x in state.get("case_fact_ids") or [] if x in facts],"variants":{x:internal_variants[x] for x in state.get("variant_ids") or [] if x in internal_variants}})
        for criterion in owner.get("criteria") or []:
            approved=[rid for rid in criterion.get("rule_ids") or [] if support.get(rid)]
            if len(approved)!=len(criterion.get("rule_ids") or []): continue
            rules=[r for r in registry.get("rules") or [] if r.get("rule_id") in approved]
            items.append({"item_type":"criterion","authority":authority,"criterion":criterion,"rules":rules,"case_facts":[facts[x] for x in criterion.get("case_fact_ids") or [] if x in facts],"variants":{x:internal_variants[x] for x in criterion.get("variant_ids") or [] if x in internal_variants},"derived_states":[states[x] for x in criterion.get("state_ids") or [] if x in states]})
        simple=_diagnostic_reasoning(ctx,authority)
        items.append({"item_type":"conclusion","authority":authority,"conclusion_id":authority,"proposed_conclusion":(owner.get("proposal") or {}).get("label"),"owner_reasoning":simple,"instruction":"Assess whether the proposed final conclusion follows from and is consistent with the owner's own reasoning."})
    return items


def _validate_reasoning_audit_with_conclusions(output: dict, prepared: list[dict], *, criterion_kind: str) -> list[AuditIssue]:
    issues=_contract_issues(output,"reasoning_audit.json") if output else []
    expected_states={x["state"]["state_id"] for x in prepared if x.get("item_type")=="derived_state"}
    if criterion_kind=="criterion": expected_criteria={x["criterion"]["criterion_id"] for x in prepared if x.get("item_type")=="criterion"}
    else: expected_criteria={x["application"]["application_id"] for x in prepared if x.get("item_type")=="application"}
    expected_conclusions={x.get("conclusion_id") for x in prepared if x.get("item_type")=="conclusion"}
    def check(rows,expected,field,base):
        seen=set()
        for i,row in enumerate(rows or []):
            if not isinstance(row,dict): issues.append(AuditIssue("invalid_reasoning_row",f"$.{base}[{i}]","reasoning row is not a mapping",f"return a valid {base} row")); continue
            value=row.get(field)
            if value not in expected: issues.append(AuditIssue("unknown_reasoning_id",f"$.{base}[{i}].{field}",f"unexpected ID {value!r}","assess only supplied items")); continue
            if value in seen: issues.append(AuditIssue("duplicate_reasoning_result",f"$.{base}[{i}].{field}",f"ID {value!r} appears more than once","return exactly one result per item"))
            seen.add(value)
        for missing in sorted(expected-seen): issues.append(AuditIssue("missing_reasoning_result",f"$.{base}",f"no result was returned for {missing}","assess this supplied item"))
    if isinstance(output,dict):
        check(output.get("derived_states") or [],expected_states,"state_id","derived_states")
        check(output.get("criteria") or [],expected_criteria,"criterion_id","criteria")
        check(output.get("conclusions") or [],expected_conclusions,"conclusion_id","conclusions")
    return issues


def validate_diagnostic_reasoning_audit(context: dict, params: dict) -> dict:
    ctx=_workflow_context(context); prepared=ctx.get("diagnostic_reasoning_items") or []; output=ctx.get("diagnostic_reasoning_audit") or {}
    issues=_validate_reasoning_audit_with_conclusions(output,prepared,criterion_kind="criterion")
    return {"status":"pass" if not issues else "fail","issue_count":len(issues),"feedback":render_feedback(issues),"issues":[x.__dict__ for x in issues]}


def prepare_ptbg_reasoning_audit(context: dict, params: dict) -> list[dict]:
    ctx=_workflow_context(context); registry=ctx.get("ptbg_atomic_registry") or {}; evidence=ctx.get("ptbg_evidence_decisions") or {}; support=evidence.get("rule_support") or {}; facts=_ptbg_case_facts(ctx)
    states={s.get("state_id"):s for s in registry.get("derived_states") or []}; rules={r.get("rule_id"):r for r in registry.get("rules") or []}; items=[]
    for state in states.values(): items.append({"item_type":"derived_state","domain":state.get("domain"),"state":state,"case_facts":[facts[f] for f in state.get("case_fact_ids") or [] if f in facts]})
    for app in registry.get("applications") or []:
        rid_list=list(app.get("rule_ids") or [])
        if app.get("mode")!="semantic" or not all(support.get(rid,False) for rid in rid_list): continue
        items.append({"item_type":"application","domain":app.get("domain"),"application":app,"rules":[rules[r] for r in rid_list if r in rules],"case_facts":[facts[f] for f in app.get("case_fact_ids") or [] if f in facts],"derived_states":[states[s] for s in app.get("state_ids") or [] if s in states]})
    for domain in PTBG_DOMAINS:
        owner=_ptbg_owner({"__workflow_context__":ctx},domain); source=_ptbg_reasoning(ctx,domain)
        for prop in owner.get("propositions") or []:
            items.append({"item_type":"conclusion","domain":domain,"conclusion_id":prop.get("proposition_id"),"proposed_conclusion":{"bucket":prop.get("bucket"),"text":prop.get("text"),"framework":prop.get("framework"),"reportable":prop.get("reportable")},"owner_reasoning":source,"instruction":"Assess whether this final conclusion follows from and is consistent with the domain-specific clinical reasoning contract."})
    return items


def validate_ptbg_reasoning_audit(context: dict, params: dict) -> dict:
    ctx=_workflow_context(context); prepared=ctx.get("ptbg_reasoning_items") or []; output=ctx.get("ptbg_reasoning_audit") or {}
    issues=_validate_reasoning_audit_with_conclusions(output,prepared,criterion_kind="application")
    return {"status":"pass" if not issues else "fail","issue_count":len(issues),"feedback":render_feedback(issues),"issues":[x.__dict__ for x in issues]}


_phase3_evaluate_diagnoses_with_no_conclusion = _phase3_evaluate_diagnoses

def evaluate_diagnoses_v2(context: dict, params: dict) -> dict:
    result=_phase3_evaluate_diagnoses_with_no_conclusion(context,params); ctx=_workflow_context(context)
    conclusion_rows={r.get("conclusion_id"):r for r in (ctx.get("diagnostic_reasoning_audit") or {}).get("conclusions") or [] if isinstance(r,dict)}
    for authority in DIAGNOSTIC_AUTHORITIES:
        crow=conclusion_rows.get(authority) or {}; coherent=crow.get("status")=="coherent"
        if not coherent:
            result.setdefault("owner_status",{})[authority]="fail"
            comments="; ".join(crow.get("comments") or []) or "Final diagnosis was not confirmed coherent with the owner's audited reasoning."
            result.setdefault("feedback",{})[authority]=f"Clinical conclusion requires revision. The final {authority} conclusion must follow from the reasoning. {comments}\n"
            result.setdefault("detail",{}).setdefault(authority,{})["conclusion_status"]=crow.get("status","missing")
        elif isinstance((result.get("detail") or {}).get(authority),dict):
            result["detail"][authority]["conclusion_status"]="coherent"
        if (result.get("owner_status") or {}).get(authority)=="pass": continue
        # Preserve existing detailed feedback when failure is not solely coherence.
        if authority in (result.get("feedback") or {}) and "Clinical conclusion requires revision" in result["feedback"][authority]: continue
        owner=_diagnostic_reasoning(ctx,authority); atomic=_read_owner_artifact(ctx,authority); simple_rows=[x for x in owner.get("reasoning") or [] if isinstance(x,dict)]; mapping={c.get("criterion_id"):(f"R{i}",simple) for i,(c,simple) in enumerate(zip(atomic.get("criteria") or [],simple_rows),1) if isinstance(c,dict)}; problems=[]; detail=(result.get("detail") or {}).get(authority) or {}; crit_status=detail.get("criterion_status") or {}
        for criterion in atomic.get("criteria") or []:
            cid=criterion.get("criterion_id"); status=crit_status.get(cid,"unknown")
            if status!="met": rid,simple=mapping.get(cid,("reasoning item",{})); problems.append(f"{rid}: patient applicability was {status} for rule: {simple.get('rule')}. Reassess this clinical reasoning point from the supplied facts.")
        evidence=(ctx.get("diagnostic_evidence_decisions") or {}).get("rule_support") or {}
        for i,(rule,simple) in enumerate(zip(atomic.get("rules") or [],simple_rows),1):
            if not evidence.get(rule.get("rule_id"),False): problems.append(f"R{i}: no supplied evidence survived audit for rule: {simple.get('rule')}. Revise or remove this unsupported clinical rule; do not invent evidence.")
        if problems: result.setdefault("feedback",{})[authority]="Clinical reasoning requires revision. Fix the following without changing supplied patient facts:\n- "+"\n- ".join(dict.fromkeys(problems))+"\n"
    return result


_phase3_evaluate_ptbg_no_conclusion = evaluate_ptbg

def evaluate_ptbg(context: dict, params: dict) -> dict:
    result=_phase3_evaluate_ptbg_no_conclusion(context,params); ctx=_workflow_context(context); conclusions={r.get("conclusion_id"):r for r in (ctx.get("ptbg_reasoning_audit") or {}).get("conclusions") or [] if isinstance(r,dict)}
    for row in result.get("propositions") or []:
        cid=row.get("proposition_id"); crow=conclusions.get(cid) or {}
        if crow.get("status")!="coherent":
            row["status"]="unknown"; row["disposition"]="dropped" if crow.get("status")=="incoherent" else "unresolved"; row["reason"]="Final clinical conclusion did not pass conclusion-coherence audit. " + ("; ".join(crow.get("comments") or []) or "Conclusion coherence was indeterminate.")
    by_domain={d:[] for d in PTBG_DOMAINS}
    for row in result.get("propositions") or []: by_domain.setdefault(row.get("domain"),[]).append(row)
    result["by_domain"]=by_domain
    return result


def ptbg_owner_review_v2(context: dict, params: dict) -> dict:
    domain=str(params.get("domain") or _ptbg_domain_from_step(str(params.get("step_id") or ""))); ctx=_workflow_context(context); evaluation=ctx.get("ptbg_evaluation") or {}; rows=(evaluation.get("by_domain",{}) or {}).get(domain,[]); bad=[r for r in rows if r.get("disposition") in {"dropped","unresolved"}]
    if not bad: return {"status":"pass","feedback":"","issues":[]}
    issues=[]
    for row in bad:
        issues.append(AuditIssue("unsupported_ptbg_proposition",f"$.{domain}.{row.get('proposition_id')}",f"Proposition '{row.get('proposition_id')}' failed: {row.get('reason')}","revise the clinical conclusion/reasoning only; evidence matching will run separately"))
    return {"status":"fail","feedback":render_feedback(issues),"issues":[x.__dict__ for x in issues]}


def _diagnostic_atomic_rule_map(ctx,authority:str) -> dict[str,str]:
    reasoning=_diagnostic_reasoning(ctx,authority); owner=_read_owner_artifact(ctx,authority); mapping={}; atomic=owner.get("rules") or []
    for i,(simple,rule) in enumerate(zip([x for x in reasoning.get("reasoning") or [] if isinstance(x,dict)],atomic),1): mapping[f"R{i}"]=rule.get("rule_id")
    return mapping


def reasoning_report_blocks(context: dict, params: dict) -> list[dict]:
    """Build report blocks from accepted conclusions, not audit narratives."""
    ctx=_workflow_context(context); elements=ctx.get("evidence_enriched") or ctx.get("supported") or []; blocks=[]
    diagnosis_components=[]
    for el in elements:
        if el.get("domain")!="diagnosis": continue
        src=el.get("source") or {}; role="who5" if el.get("schema_id")=="DX-WHO5" else "icc" if el.get("schema_id")=="DX-ICC" else "concurrent_pathology"
        tags=[e.get("card_tag") for e in el.get("evidence") or [] if e.get("card_tag")]
        if role in {"who5","icc"}:
            diagnosis=src.get("diagnosis")
            framework="WHO5" if role=="who5" else "ICC"
            diagnosis_components.append({"role":role,"diagnosis":diagnosis,"reason":f"The {framework} diagnosis is {diagnosis}.","variants":src.get("variants") or [],"card_tags":tags})
        else:
            pathology=src.get("other_pathology")
            diagnosis_components.append({"role":role,"pathology":pathology,"reason":f"Concurrent pathology: {pathology}.","variants":el.get("variants") or [],"card_tags":tags})
    if diagnosis_components: blocks.append({"block_id":"DX","domain":"diagnosis","components":diagnosis_components})
    for el in elements:
        if el.get("domain")=="diagnosis": continue
        src=el.get("source") or {}
        # PTBG report blocks contain the accepted clinical conclusion only.
        concise=src.get("text") or src.get("reason") or el.get("reason")
        evidence_rows=[e for e in el.get("evidence") or [] if isinstance(e,dict)]
        if el.get("domain")=="prognosis" and str(el.get("bucket") or "").startswith("other_evidence_"):
            labels=[]
            for e in evidence_rows:
                label=e.get("source_label")
                if label and label not in labels: labels.append(label)
            if labels:
                # Non-framework prognosis must identify the supporting study;
                # keep the prose concise and avoid dumping multiple authors.
                concise=f"{labels[0]} reported: {concise}"
                src=dict(src); src["source_label"]=labels[0]
        blocks.append({"block_id":el.get("schema_id"),"domain":el.get("domain"),"components":[{"role":el.get("bucket"),"reason":concise,"variants":el.get("variants") or [],"source":src,"card_tags":[e.get("card_tag") for e in evidence_rows if e.get("card_tag")]}]})
    work=_work(context)
    try:
        from workflows.proforma_v1 import self_runtime as sr, schema_validation
        sr.write_yaml(sr.output_path(work,"report_blocks","report-blocks.yaml"),{"blocks":blocks}); schema_validation.validate_report_source_blocks(blocks)
    except Exception: pass
    if hasattr(ctx,"put"):
        ctx.put("blocks",blocks)
    else:
        ctx["blocks"]=blocks
    return blocks


def merge_diagnostic_evidence_matches(context: dict, params: dict) -> dict:
    ctx=_workflow_context(context); pairs=[]; by_rule={}
    for authority in DIAGNOSTIC_AUTHORITIES:
        mapping=_diagnostic_atomic_rule_map(ctx,authority); pack=ctx.get(_DIAGNOSTIC_EM_ITEM_KEYS[authority]) or {}; cards={c.get("card_tag"):c for c in _em_cards(pack)}; owner=_read_owner_artifact(ctx,authority); rules={r.get("rule_id"):r for r in owner.get("rules") or []}
        output=ctx.get(_DIAGNOSTIC_EM_KEYS[authority]) or {"assignments":[]}
        for row in output.get("assignments") or []:
            atomic=mapping.get(row.get("reasoning_id"));
            if not atomic: continue
            by_rule.setdefault(atomic,[])
            for tag in row.get("card_tags") or []:
                if tag in cards and tag not in by_rule[atomic]:
                    by_rule[atomic].append(tag); pairs.append({"authority":authority,"rule_id":atomic,"statement":(rules.get(atomic) or {}).get("statement"),"card_tag":tag,"card":cards[tag],"source":"evidence_match"})
    registry=ctx.get("diagnostic_atomic_registry") or {}
    for rule in registry.get("rules") or []: by_rule.setdefault(rule.get("rule_id"),[])
    return {"pairs":pairs,"card_tags_by_rule":by_rule,"unassigned_rule_ids":[rid for rid,tags in by_rule.items() if not tags]}


def _ptbg_card_catalog(ctx) -> dict[str,dict]:
    out={}
    for domain in PTBG_DOMAINS:
        for card in _em_cards(ctx.get(_PTBG_EM_ITEM_KEYS[domain]) or {}):
            if card.get("card_tag"): out[card["card_tag"]]=card
    return out


def _owner_redo_state(ctx) -> dict:
    value=ctx.get("clinical_owner_redo_used") or {}
    return dict(value) if isinstance(value,dict) else {}


def _consume_owner_redo(ctx, owner: str) -> bool:
    """Return True once for each owner; false thereafter.

    This makes the bounded clinical redo global to the owner rather than local
    to each review node. Evidence-matcher retries have their own budget and do
    not consume this clinical-owner budget.
    """
    state=_owner_redo_state(ctx)
    if state.get(owner): return False
    state[owner]=True; ctx.put("clinical_owner_redo_used",state); return True


_prev_validate_diagnostic_reasoning_v2 = validate_diagnostic_reasoning_v2

def validate_diagnostic_reasoning_v2(context: dict, params: dict) -> dict:
    result=_prev_validate_diagnostic_reasoning_v2(context,params)
    if result.get("status")!="pass":
        authority=str(params.get("authority") or _authority_from_step(str(params.get("step_id") or ""))); _consume_owner_redo(_workflow_context(context),authority)
    return result


_prev_validate_ptbg_reasoning_v2 = validate_ptbg_reasoning_v2

def validate_ptbg_reasoning_v2(context: dict, params: dict) -> dict:
    result=_prev_validate_ptbg_reasoning_v2(context,params)
    if result.get("status")!="pass":
        domain=str(params.get("domain") or _ptbg_domain_from_step(str(params.get("step_id") or ""))); _consume_owner_redo(_workflow_context(context),domain)
    return result


_prev_evaluate_diagnoses_v2 = evaluate_diagnoses_v2

def evaluate_diagnoses_v2(context: dict, params: dict) -> dict:
    result=_prev_evaluate_diagnoses_v2(context,params); ctx=_workflow_context(context)
    for authority in DIAGNOSTIC_AUTHORITIES:
        if (result.get("owner_status") or {}).get(authority)=="pass": continue
        if not _consume_owner_redo(ctx,authority):
            result.setdefault("redo_exhausted",{})[authority]=True
    return result


_prev_ptbg_owner_review_v2 = ptbg_owner_review_v2

def ptbg_owner_review_v2(context: dict, params: dict) -> dict:
    raw=_prev_ptbg_owner_review_v2(context,params)
    if raw.get("status")=="pass": return raw
    domain=str(params.get("domain") or _ptbg_domain_from_step(str(params.get("step_id") or ""))); ctx=_workflow_context(context)
    if _consume_owner_redo(ctx,domain): return raw
    # The evaluation already marks the proposition dropped/unresolved. Returning
    # pass here means "no more clinical calls"; finalization carries the failed
    # decision into dissent and suppresses it from the clinical report.
    ctx.put(f"{domain}__redo_exhausted",True)
    return {"status":"pass","feedback":raw.get("feedback","")+"\nClinical owner redo budget exhausted; preserve the failed proposition in dissent and do not call the owner again.","issues":raw.get("issues") or [],"redo_exhausted":True}


def owner_review(context: dict, params: dict) -> dict:
    authority=str(params.get("authority") or _authority_from_step(str(params.get("step_id") or ""))); ctx=_workflow_context(context); evaluation=ctx.get("diagnostic_evaluation") or {}; status=(evaluation.get("owner_status") or {}).get(authority,"fail"); feedback=(evaluation.get("feedback") or {}).get(authority,"Diagnostic evaluation did not produce feedback.\n")
    if status=="pass": return {"authority":authority,"status":"pass","feedback":feedback}
    if _consume_owner_redo(ctx,authority): return {"authority":authority,"status":"fail","feedback":feedback}
    ctx.put(f"{authority}__redo_exhausted",True)
    return {"authority":authority,"status":"pass","feedback":feedback+"\nClinical owner redo budget exhausted; preserve the failed proposal in dissent and use deterministic fallback/suppression.","redo_exhausted":True}

# Test/lightweight-context compatible redo-state writers.
def _ctx_store(ctx, key: str, value: Any) -> None:
    put=getattr(ctx,"put",None)
    if callable(put): put(key,value)
    elif isinstance(ctx,dict): ctx[key]=value
    else: setattr(ctx,key,value)


def _consume_owner_redo(ctx, owner: str) -> bool:
    state=_owner_redo_state(ctx)
    if state.get(owner): return False
    state[owner]=True; _ctx_store(ctx,"clinical_owner_redo_used",state); return True
