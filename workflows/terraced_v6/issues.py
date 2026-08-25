"""Reusable deterministic issue builders for terraced-v6 validators.

Every v6 validator accumulates `ValidationIssue` objects and raises once, so a
single repair turn carries every defect. These helpers exist so that the four
PTBG proformas, the two batch stages and the two writer stages express the same
contract in the same words: identical defects should produce identical feedback
regardless of which stage found them.

Nothing here calls a model or makes a clinical judgement. Each function returns
issues; the caller decides when to raise.
"""
from __future__ import annotations

import difflib
import json

import yaml

from scripts.core.validated_model_task import ValidationIssue

# An enum whose domain runs to hundreds of values must never be enumerated back
# to the model: the list dwarfs the rest of the feedback, costs more tokens than
# the artifact under repair, and buries the one thing the model needs (what it
# said, and the nearest legal value).
MAX_LISTED_ENUM_VALUES = 12
NEAREST_MATCHES = 5


def type_name(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, dict):
        return "mapping"
    if isinstance(v, list):
        return "list"
    if isinstance(v, str):
        return "string"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, float):
        return "number"
    return type(v).__name__


def preview(v, limit: int = 160) -> str:
    text = v if isinstance(v, str) else repr(v)
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _single_mapping_list(v) -> bool:
    return isinstance(v, list) and len(v) == 1 and isinstance(v[0], dict)


def parse(text: str, *, fmt: str, context: str):
    """Parse a candidate artifact. Returns ``(doc, issues)``; doc is {} on failure."""
    try:
        doc = yaml.safe_load(text) if fmt == "yaml" else json.loads(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        return {}, [
            ValidationIssue(
                context,
                f"invalid {fmt.upper()}: {preview(exc)}",
                f"return one well-formed {fmt.upper()} document and nothing else",
                repair_class="serialization",
            )
        ]
    if not isinstance(doc, dict):
        wrapped = _single_mapping_list(doc)
        return {}, [
            ValidationIssue(
                context,
                f"expected a top-level mapping; received {type_name(doc)}",
                "remove the extra one-item list wrapper without changing fields or values"
                if wrapped
                else "return the required top-level mapping",
                repair_class="serialization" if wrapped else "content",
                received=preview(doc),
                expected="mapping/object",
            )
        ]
    return doc, []


def exact_keys(doc, expected, path: str) -> list[ValidationIssue]:
    """Require exactly the named keys — no more, no fewer."""
    if not isinstance(doc, dict):
        return [
            ValidationIssue(
                path,
                f"expected a mapping; received {type_name(doc)}",
                f"return a mapping with exactly {sorted(expected)}",
                repair_class="content",
                received=preview(doc),
            )
        ]
    missing = sorted(set(expected) - set(doc))
    extra = sorted(set(doc) - set(expected))
    if not missing and not extra:
        return []
    bits = []
    if missing:
        bits.append(f"missing {missing}")
    if extra:
        bits.append(f"unexpected {extra}")
    return [
        ValidationIssue(
            path,
            "; ".join(bits),
            f"return exactly the keys {sorted(expected)}",
            repair_class="content",
            received=str(sorted(doc)),
            expected=str(sorted(expected)),
        )
    ]


def text_field(value, path: str, *, nullable: bool = False) -> list[ValidationIssue]:
    if nullable and value is None:
        return []
    if isinstance(value, str) and value.strip():
        return []
    repairable = isinstance(value, (bool, int, float)) or (
        isinstance(value, list) and len(value) == 1 and isinstance(value[0], str)
    )
    return [
        ValidationIssue(
            path,
            f"expected a non-empty string{' or null' if nullable else ''}; received {type_name(value)}",
            "reserialize the existing value as one quoted string without changing its words"
            if repairable
            else "supply non-empty text",
            repair_class="serialization" if repairable else "content",
            received=preview(value),
            expected="non-empty string",
        )
    ]


def enum_field(value, allowed, path: str, *, label: str = "value") -> list[ValidationIssue]:
    """Validate a closed vocabulary without dumping the vocabulary back.

    When the allowed set is small the full list is the most useful thing to show.
    When it is large, the nearest legal values to what the model actually said
    are far more useful — and are what lets a small model fix the field in one
    turn instead of re-reading several thousand tokens of enum.
    """
    allowed = list(allowed)
    if value in allowed:
        return []
    received = preview(value)
    if len(allowed) <= MAX_LISTED_ENUM_VALUES:
        expected = str(sorted(allowed))
        fix = f"use one exact {label} from {sorted(allowed)}"
    else:
        near = difflib.get_close_matches(
            str(value or ""), [str(a) for a in allowed], n=NEAREST_MATCHES, cutoff=0.4
        )
        if near:
            expected = f"one of these nearest allowed values: {near}"
            fix = (
                f"replace it with the exact allowed {label} it was meant to be — "
                f"most likely one of {near}"
            )
        else:
            expected = f"an exact value from the supplied {label} vocabulary ({len(allowed)} values)"
            fix = (
                f"use one exact {label} copied verbatim from the allowed-vocabulary block "
                "supplied in the task context"
            )
    return [
        ValidationIssue(
            path,
            f"{received!r} is not an allowed {label}",
            fix,
            repair_class="content",
            received=received,
            expected=expected,
        )
    ]


def id_list(value, path: str, valid, *, allow_empty: bool = False) -> tuple[set, list[ValidationIssue]]:
    """Validate a list of canonical IDs. Returns ``(accepted_ids, issues)``."""
    if not isinstance(value, list):
        return set(), [
            ValidationIssue(
                path,
                f"expected a list of IDs; received {type_name(value)}",
                "wrap the ID(s) in a list" if isinstance(value, str) else "return a list of supplied IDs",
                repair_class="serialization" if isinstance(value, str) else "content",
                received=preview(value),
                expected="list of IDs",
            )
        ]
    issues = []
    if not value and not allow_empty:
        issues.append(
            ValidationIssue(path, "list is empty", "name at least one supplied ID", repair_class="content")
        )
    unknown = [x for x in value if not isinstance(x, str) or x not in valid]
    if unknown:
        issues.append(
            ValidationIssue(
                path,
                f"contains ID(s) that were not supplied: {[preview(u, 40) for u in unknown]}",
                f"use only the supplied IDs {sorted(valid)}",
                repair_class="content",
                received=preview(value),
                expected=str(sorted(valid)),
            )
        )
    seen, dupes = set(), []
    for x in value:
        if isinstance(x, str):
            (dupes.append(x) if x in seen else seen.add(x))
    if dupes:
        issues.append(
            ValidationIssue(
                path,
                f"repeats ID(s) {sorted(set(dupes))}",
                "list each ID once",
                repair_class="content",
                received=preview(value),
            )
        )
    return {x for x in value if isinstance(x, str) and x in valid}, issues


def one_row_per_id(rows, expected_ids, *, id_field: str, path: str) -> list[ValidationIssue]:
    """Require exactly one row per supplied ID, in the supplied order.

    This single rule covers the evidence-match, evidence-audit, report-writer,
    preservation and (after Phase 4) PTBG proforma contracts. Reporting the exact
    missing / duplicate / unexpected sets converts a technically correct row-count
    error into something a model can act on without guessing.
    """
    expected_ids = list(expected_ids)
    if not isinstance(rows, list):
        return [
            ValidationIssue(
                path,
                f"expected a list of {len(expected_ids)} row(s); received {type_name(rows)}",
                f"return exactly one row for each of {expected_ids}",
                repair_class="content",
                received=preview(rows),
                expected=f"list of {len(expected_ids)} rows",
            )
        ]
    got = [r.get(id_field) if isinstance(r, dict) else None for r in rows]
    scalar = [g for g in got if isinstance(g, str)]
    missing = [e for e in expected_ids if e not in scalar]
    unexpected = sorted({g for g in scalar if g not in expected_ids})
    duplicates = sorted({g for g in scalar if scalar.count(g) > 1})
    issues = []
    if missing or unexpected or duplicates:
        bits = []
        if missing:
            bits.append(f"missing {missing}")
        if duplicates:
            bits.append(f"duplicated {duplicates}")
        if unexpected:
            bits.append(f"unexpected {unexpected}")
        issues.append(
            ValidationIssue(
                path,
                "; ".join(bits),
                f"return exactly one row for every supplied {id_field} and no other rows",
                repair_class="content",
                received=f"{len(rows)} row(s): {preview(scalar)}",
                expected=f"{len(expected_ids)} row(s): {expected_ids}",
            )
        )
    elif scalar != expected_ids:
        issues.append(
            ValidationIssue(
                path,
                "rows are not in the supplied order",
                f"return the rows in the supplied order {expected_ids}",
                repair_class="serialization",
                received=preview(scalar),
                expected=str(expected_ids),
            )
        )
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            issues.append(
                ValidationIssue(
                    f"{path}[{i}]",
                    f"expected a mapping; received {type_name(row)}",
                    "return one mapping per row",
                    repair_class="content",
                    received=preview(row),
                )
            )
    return issues


def bool_field(value, path: str) -> list[ValidationIssue]:
    if isinstance(value, bool):
        return []
    repairable = isinstance(value, str) and value.strip().lower() in {"true", "false", "yes", "no"}
    return [
        ValidationIssue(
            path,
            f"expected true or false; received {type_name(value)}",
            "reserialize the existing value as an unquoted boolean"
            if repairable
            else "use true or false",
            repair_class="serialization" if repairable else "content",
            received=preview(value),
            expected="true | false",
        )
    ]
