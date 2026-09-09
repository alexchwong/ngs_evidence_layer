"""Allow-listed, meaning-preserving normalization for structured model artifacts.

This module sits between serialization repair and semantic/content repair.  It may
repair only structural conventions whose intended value is already explicit in the
artifact itself.  It must not infer a clinical decision, invent evidence, change an
enum choice, or supply missing informational text.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

import yaml

_CARD_TAG_RE = re.compile(r"\[card:[0-9a-f]{12}\]")
_CARD_TAG_FIELDS = {
    "card_tag",
    "card_tags",
    "evidence_card_tags",
    "other_evidence_card_tags",
}
_LIST_TAG_FIELDS = {
    "card_tags",
    "evidence_card_tags",
    "other_evidence_card_tags",
}

# Deliberately small.  Add aliases only when both spellings have one unambiguous
# schema meaning.  Never perform generic camelCase -> snake_case conversion.
_FIELD_ALIASES = {
    "predispositionEvidence": "predisposition_evidence",
    "evidenceCardTags": "evidence_card_tags",
    "otherEvidenceCardTags": "other_evidence_card_tags",
    "observedEventType": "observed_event_type",
    "observedVaf": "observed_vaf",
    "eventCompatibility": "event_compatibility",
    "personalHistory": "personal_history",
    "familyHistory": "family_history",
}

_SKIP_NULL_FIELDS = (
    "predisposition_evidence",
    "event_compatibility",
    "age",
    "vaf",
    "personal_history",
    "family_history",
    "phenotype",
    "bucket",
)


@dataclass(frozen=True)
class RepairRecord:
    path: str
    transform: str
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        row = {"path": self.path, "transform": self.transform}
        if self.detail:
            row["detail"] = self.detail
        return row


def _path(parent: str, key: object) -> str:
    if isinstance(key, int):
        return f"{parent}[{key}]" if parent else f"[{key}]"
    return f"{parent}.{key}" if parent else str(key)


def _exact_tag_from_rendered(value: str) -> str | None:
    tags = list(dict.fromkeys(_CARD_TAG_RE.findall(value)))
    return tags[0] if len(tags) == 1 else None


def _normalize_tag_value(value: Any, *, list_field: bool, path: str, records: list[RepairRecord]) -> Any:
    if list_field:
        if isinstance(value, str):
            tag = _exact_tag_from_rendered(value)
            if tag is not None:
                records.append(RepairRecord(path, "card_tag_scalar_to_list", tag))
                return [tag]
            return value
        if isinstance(value, list):
            out: list[Any] = []
            changed = False
            for i, item in enumerate(value):
                if isinstance(item, str):
                    tag = _exact_tag_from_rendered(item)
                    if tag is not None and tag != item.strip():
                        records.append(RepairRecord(_path(path, i), "extract_exact_card_tag", tag))
                        item = tag
                        changed = True
                out.append(item)
            # Deduplicating identical opaque evidence identifiers changes no proposition.
            if all(isinstance(item, str) and _CARD_TAG_RE.fullmatch(item) for item in out):
                deduped = list(dict.fromkeys(out))
                if deduped != out:
                    records.append(RepairRecord(path, "deduplicate_identical_card_tags"))
                    out = deduped
                    changed = True
            return out if changed else value
        return value

    if isinstance(value, str):
        tag = _exact_tag_from_rendered(value)
        if tag is not None and tag != value.strip():
            records.append(RepairRecord(path, "extract_exact_card_tag", tag))
            return tag
    return value


def _walk(value: Any, path: str, records: list[RepairRecord]) -> Any:
    if isinstance(value, list):
        return [_walk(item, _path(path, i), records) for i, item in enumerate(value)]
    if not isinstance(value, dict):
        return value

    out: dict[Any, Any] = {}
    for key, item in value.items():
        canonical = _FIELD_ALIASES.get(key, key)
        target_path = _path(path, canonical)
        if canonical != key:
            # If both spellings are present, preserving both and failing validation is safer
            # than guessing which value the author intended.
            if canonical in value:
                out[key] = _walk(item, _path(path, key), records)
                continue
            records.append(RepairRecord(_path(path, key), "canonicalize_field_alias", str(canonical)))
        normalized = _walk(item, target_path, records)
        if canonical in _CARD_TAG_FIELDS:
            normalized = _normalize_tag_value(
                normalized,
                list_field=canonical in _LIST_TAG_FIELDS,
                path=target_path,
                records=records,
            )
        out[canonical] = normalized

    # The skip decision itself explicitly states that no predisposition evidence is
    # being assessed.  Filling contract-mandated null/empty structural fields therefore
    # records that already-made decision rather than making a new one.
    if out.get("eligibility") == "skip_no_predisposition_evidence":
        for key in _SKIP_NULL_FIELDS:
            if key not in out:
                out[key] = None
                records.append(RepairRecord(_path(path, key), "materialize_skip_null"))
        if "evidence_card_tags" not in out:
            out["evidence_card_tags"] = []
            records.append(RepairRecord(_path(path, "evidence_card_tags"), "materialize_skip_empty_tags"))

    return out


def normalize_document(document: Any) -> tuple[Any, list[dict[str, str]]]:
    records: list[RepairRecord] = []
    normalized = _walk(document, "", records)
    return normalized, [record.as_dict() for record in records]


def normalize_text(text: str, *, format_name: str) -> tuple[str, list[dict[str, str]]]:
    """Normalize an already parseable YAML/JSON artifact.

    Parsing failures are intentionally left to the serialization-repair layer.
    """
    fmt = str(format_name or "").strip().lower()
    try:
        if fmt == "json":
            document = json.loads(text)
        elif fmt in {"yaml", "yml"}:
            document = yaml.safe_load(text)
        else:
            return text, []
    except (json.JSONDecodeError, yaml.YAMLError):
        return text, []

    normalized, records = normalize_document(document)
    if not records:
        return text, []
    if fmt == "json":
        rendered = json.dumps(normalized, indent=2, ensure_ascii=False) + "\n"
    else:
        rendered = yaml.safe_dump(normalized, sort_keys=False, allow_unicode=True, width=110)
    return rendered, records
