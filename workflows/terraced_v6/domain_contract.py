"""One-row-per-variant contracts for the four terraced-v6 PTBG proformas.

## Why the model-facing shape changed

The previous contract asked the owner model to emit four (or two, or three)
bucket lists, to cover every supplied variant exactly once across them, and to
merge variants sharing a proposition into one row. That is a coverage constraint,
an exclusivity constraint and a grouping constraint held simultaneously — and the
grouping half was *already redone in Python* immediately afterwards by
`step._consolidate_rows`, so the model's grouping effort was never load-bearing.

The model now returns one row per variant:

    classification:
      - variant: v01
        bucket: adverse
        reason: "..."

`skeleton()` hands it that list with every `variant:` pre-filled, so the task is
to fill two fields per row rather than to derive a partition. Coverage and
exclusivity defects become unrepresentable, and `one_row_per_id` — the same rule
already used by the batch and writer stages — is the whole structural check.

`pivot()` converts the flat list back into the legacy bucket-list artifact before
anything is written to disk, so evidence selection, reportability, block assembly
and `_consolidate_rows` are all untouched.

## Why the bucket names live here

`favorable/adverse/neutral/uncertain` previously appeared in seven places per
domain. This module is now the single definition; validators, consolidation,
reportability defaults and element assembly all read it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import yaml

from scripts.core.validated_model_task import ValidationIssue, fail
from workflows.terraced_v6 import issues as iss


@dataclass(frozen=True)
class DomainContract:
    domain: str
    label: str
    buckets: tuple[str, ...]
    # Buckets whose rows carry a named therapy. Empty for most domains.
    therapy_buckets: tuple[str, ...] = ()
    # Buckets that cannot coexist with any other bucket for the same variant.
    # Empty means the domain is a strict partition (one row per variant).
    solitary_buckets: tuple[str, ...] = ()
    # Whether a variant may legitimately appear in more than one row.
    multi_row: bool = False
    # Extra top-level keys beyond `classification`.
    extra_keys: tuple[str, ...] = ()
    guidance: tuple[str, ...] = field(default_factory=tuple)

    @property
    def row_keys_for(self):
        def _keys(bucket):
            return ("variant", "bucket", "therapy", "reason") if bucket in self.therapy_buckets else ("variant", "bucket", "reason")

        return _keys

    @property
    def top_level_keys(self):
        return ("classification", *self.extra_keys)


PROGNOSIS = DomainContract(
    domain="prognosis",
    label="prognosis",
    buckets=("favorable", "adverse", "neutral", "uncertain"),
    extra_keys=("prognostic_score",),
    guidance=(
        "`prognostic_score` is populated only when this workflow can actually assign the named "
        "score or risk group from the supplied information. Otherwise use null. Never state that "
        "a score is \"not calculable\".",
    ),
)

TREATMENT = DomainContract(
    domain="treatment",
    label="treatment",
    buckets=("drug_target", "drug_sensitive", "drug_resistant", "no_drug_implication"),
    therapy_buckets=("drug_target", "drug_sensitive", "drug_resistant"),
    solitary_buckets=("no_drug_implication",),
    multi_row=True,
    guidance=(
        "A variant may appear in more than one row when it carries genuinely distinct therapeutic "
        "implications — for example a target and a separate sensitivity — each with its own therapy.",
        "`no_drug_implication` is exclusive: a variant in that bucket must not appear in any other row.",
    ),
)

BIOMARKER = DomainContract(
    domain="biomarker",
    label="MRD",
    buckets=("mrd_marker", "not_mrd_marker"),
)

GERMLINE = DomainContract(
    domain="germline",
    label="germline",
    buckets=("germline_support", "germline_against", "germline_uncertain"),
    guidance=(
        "Every conclusion must integrate the molecular result with the supplied clinical context, "
        "not the molecular result alone.",
    ),
)

CONTRACTS = {c.domain: c for c in (PROGNOSIS, TREATMENT, BIOMARKER, GERMLINE)}


def contract(domain: str) -> DomainContract:
    try:
        return CONTRACTS[domain]
    except KeyError:
        raise ValueError(f"unknown terraced-v6 domain {domain!r}") from None


# --- model-facing skeleton ---------------------------------------------------

def skeleton(c: DomainContract, variant_ids) -> str:
    """Render the exact artifact to return, with every `variant` pre-filled.

    Shown to the model as the final block of the prompt. Recency matters
    disproportionately for a low-active-parameter model: a contract stated
    several thousand tokens before generation begins competes with everything
    written since.
    """
    choices = "|".join(c.buckets)
    lines = [
        f"## Return exactly this YAML for the {c.label} proforma, and nothing else.",
        "",
    ]
    if c.multi_row:
        lines.append(
            f"## Every supplied variant must appear at least once. Add a row when a variant has a "
            f"second, genuinely distinct implication. Do not change any `variant` value."
        )
    else:
        lines.append(
            "## One row per variant, in the order given. Do not add, remove or reorder rows, "
            "and do not change any `variant` value."
        )
    for line in c.guidance:
        lines.append(f"## {line}")
    lines += ["", "```yaml", "classification:"]
    for vid in variant_ids:
        lines.append(f"  - variant: {vid}")
        lines.append(f"    bucket: <{choices}>")
        if c.therapy_buckets:
            lines.append(
                "    therapy: \"<named therapy; omit this field only for "
                f"{c.solitary_buckets[0] if c.solitary_buckets else 'non-therapeutic'} rows>\""
            )
        lines.append(f"    reason: \"<one concise report-ready {c.label} proposition>\"")
    if "prognostic_score" in c.extra_keys:
        lines += [
            "prognostic_score: null",
            "# or, when the named score really is assignable from the supplied information:",
            "# prognostic_score:",
            "#   name: \"<framework>\"",
            "#   result: \"<risk group or score>\"",
            "#   reason: \"<one concise basis>\"",
        ]
    lines.append("```")
    return "\n".join(lines)


# --- validation --------------------------------------------------------------

def validate(text: str, c: DomainContract, valid_variants) -> str:
    """Validate the flat one-row-per-variant artifact, accumulating all defects."""
    ordered = sorted(valid_variants)
    doc, parse_issues = iss.parse(text, fmt="yaml", context=c.label)
    if parse_issues:
        fail(c.label, parse_issues)
    problems = list(iss.exact_keys(doc, set(c.top_level_keys), c.label))
    rows = doc.get("classification")

    if c.multi_row:
        problems += _validate_multi_row(rows, ordered, c)
    else:
        problems += iss.one_row_per_id(rows, ordered, id_field="variant", path="classification")

    if isinstance(rows, list):
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            path = f"classification[{i}]"
            bucket = row.get("bucket")
            problems += iss.enum_field(bucket, c.buckets, f"{path}.bucket", label="bucket")
            expected_keys = set(c.row_keys_for(bucket if bucket in c.buckets else ""))
            problems += iss.exact_keys(row, expected_keys, path)
            problems += iss.text_field(row.get("reason"), f"{path}.reason")
            if bucket in c.therapy_buckets:
                problems += iss.text_field(row.get("therapy"), f"{path}.therapy")

    if "prognostic_score" in c.extra_keys:
        problems += _validate_prognostic_score(doc.get("prognostic_score"))

    fail(c.label, problems)
    return f"{c.label} proforma valid"


def _validate_multi_row(rows, ordered, c: DomainContract) -> list[ValidationIssue]:
    if not isinstance(rows, list):
        return iss.one_row_per_id(rows, ordered, id_field="variant", path="classification")
    problems: list[ValidationIssue] = []
    seen = {}
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            problems.append(
                ValidationIssue(
                    f"classification[{i}]",
                    f"expected a mapping; received {iss.type_name(row)}",
                    "return one mapping per row",
                    repair_class="content",
                    received=iss.preview(row),
                )
            )
            continue
        vid = row.get("variant")
        if not isinstance(vid, str) or vid not in ordered:
            problems.append(
                ValidationIssue(
                    f"classification[{i}].variant",
                    f"{iss.preview(vid)!r} is not a supplied variant ID",
                    f"use one of the supplied IDs {ordered}",
                    repair_class="content",
                    received=iss.preview(vid),
                    expected=str(ordered),
                )
            )
            continue
        seen.setdefault(vid, []).append(row.get("bucket"))
    missing = [v for v in ordered if v not in seen]
    if missing:
        problems.append(
            ValidationIssue(
                "classification",
                f"no row for variant(s) {missing}",
                "return at least one row for every supplied variant",
                repair_class="content",
                received=f"rows for {sorted(seen)}",
                expected=str(ordered),
            )
        )
    for solitary in c.solitary_buckets:
        for vid, buckets in seen.items():
            others = [b for b in buckets if b != solitary]
            if solitary in buckets and others:
                problems.append(
                    ValidationIssue(
                        "classification",
                        f"{vid} appears in {solitary} and also in {sorted(set(others))}",
                        f"a variant in {solitary} must not appear in any other bucket; "
                        f"remove either the {solitary} row or the other row(s)",
                        repair_class="content",
                        received=f"{vid}: {buckets}",
                        expected=f"{vid} in {solitary} alone, or not in {solitary} at all",
                    )
                )
    for vid, buckets in seen.items():
        dupes = sorted({b for b in buckets if buckets.count(b) > 1})
        if dupes:
            problems.append(
                ValidationIssue(
                    "classification",
                    f"{vid} has more than one row in bucket(s) {dupes}",
                    "merge them into one row, or use a different bucket for the distinct implication",
                    repair_class="content",
                    received=f"{vid}: {buckets}",
                )
            )
    return problems


def _validate_prognostic_score(score) -> list[ValidationIssue]:
    import re

    if score is None:
        return []
    if not isinstance(score, dict):
        return [
            ValidationIssue(
                "prognostic_score",
                f"expected a mapping or null; received {iss.type_name(score)}",
                "use null when no named score is assignable",
                repair_class="content",
                received=iss.preview(score),
                expected="mapping | null",
            )
        ]
    problems = list(iss.exact_keys(score, {"name", "result", "reason"}, "prognostic_score"))
    for key in ("name", "result", "reason"):
        problems += iss.text_field(score.get(key), f"prognostic_score.{key}")
    combined = " ".join(str(score.get(k)) for k in ("name", "result", "reason"))
    if re.search(
        r"not\s+calculable|cannot\s+be\s+calculated|unable\s+to\s+calculate|insufficient.*(?:score|calculate)",
        combined,
        re.I,
    ):
        problems.append(
            ValidationIssue(
                "prognostic_score",
                "reports an inability to calculate a score",
                "use null instead; do not report that a score could not be calculated",
                repair_class="content",
                received=iss.preview(combined),
                expected="null",
            )
        )
    return problems


# --- pivot back to the stored bucket-list artifact ---------------------------

def pivot(doc: dict, c: DomainContract) -> dict:
    """Convert the flat classification list into the legacy bucket-list artifact.

    Everything downstream of the owner call — consolidation, reportability,
    evidence selection, block assembly — continues to read the bucket shape, so
    the contract change is contained entirely within the model boundary.
    """
    out = {bucket: [] for bucket in c.buckets}
    for row in doc.get("classification") or []:
        if not isinstance(row, dict):
            continue
        bucket = row.get("bucket")
        if bucket not in out:
            continue
        entry = {"variants": [row.get("variant")], "reason": row.get("reason")}
        if bucket in c.therapy_buckets:
            entry["therapy"] = row.get("therapy")
            entry = {"variants": entry["variants"], "therapy": entry["therapy"], "reason": entry["reason"]}
        out[bucket].append(entry)
    for key in c.extra_keys:
        out[key] = doc.get(key)
    return out


def render_pivoted(doc: dict, c: DomainContract) -> str:
    return yaml.safe_dump(pivot(doc, c), sort_keys=False, allow_unicode=True, width=110)
