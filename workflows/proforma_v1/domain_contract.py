"""Model-facing PTBG contracts and deterministic projection for proforma-v1.

The owner outputs stay variant-centric.  Python injects deterministic identity
(`applicable_disease` and, where shown, `gene`) and projects the model-facing
rows into the bucketed internal shape consumed by evidence resolution/reporting.
Framework selection itself is never deterministic: prognosis may return zero,
one, or several applicable frameworks.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import json

import yaml

from workflows.proforma_v1 import stage_spec


_CATEGORY_FIELD = {
    "treatment": "treatment_category",
    "biomarker": "mrd_status",
    "germline": "bucket",
}


@dataclass(frozen=True)
class DomainContract:
    domain: str
    label: str
    buckets: tuple[str, ...]
    therapy_buckets: tuple[str, ...] = ()
    solitary_buckets: tuple[str, ...] = ()
    multi_row: bool = False
    extra_keys: tuple[str, ...] = ()
    guidance: tuple[str, ...] = field(default_factory=tuple)

    @property
    def category_field(self) -> str | None:
        return _CATEGORY_FIELD.get(self.domain)


def _from_spec(stage: str) -> DomainContract:
    spec = stage_spec.load(stage)
    return DomainContract(
        domain=spec.stage,
        label=spec.label,
        buckets=spec.buckets,
        therapy_buckets=spec.therapy_buckets,
        solitary_buckets=spec.solitary_buckets,
        multi_row=spec.multi_row,
        extra_keys=spec.extra_keys,
        guidance=spec.guidance,
    )


CONTRACTS = {name: _from_spec(name) for name in stage_spec.domains()}
PROGNOSIS = CONTRACTS["prognosis"]
TREATMENT = CONTRACTS["treatment"]
BIOMARKER = CONTRACTS["biomarker"]
GERMLINE = CONTRACTS["germline"]


def contract(domain: str) -> DomainContract:
    try:
        return CONTRACTS[domain]
    except KeyError:
        raise ValueError(f"unknown proforma-v1 domain {domain!r}") from None


def _gene(registry, vid):
    row = (registry or {}).get(vid) or {}
    return row.get("gene") if isinstance(row, dict) else None


def _prognosis_skeleton(variant_ids, registry, disease) -> str:
    lines = [
        "## Return exactly this YAML for the prognosis proforma, and nothing else.",
        "",
        "## `applicable_disease` is deterministic and must remain the supplied authoritative WHO5 disease.",
        "## Identify zero, one, or multiple prognostic frameworks that genuinely apply to that disease.",
        "## Do not choose a framework because a card from another disease mentions a familiar gene or framework.",
        "## `tier` belongs to its framework. Populate it only when that framework can be assigned entirely from the supplied genetic/cytogenetic findings; otherwise use null.",
        "## For each variant, `framework_effects` contains only effects explicitly defined by one of the named frameworks. Use [] when the variant is not classified by any named framework.",
        "## `other_evidence_effect` may use any prognostic evidence explicitly applicable to the same disease, whether or not the gene belongs to a named framework.",
        "## When framework evidence and other evidence both classify the same variant, keep their direction concordant unless distinct named frameworks themselves legitimately differ.",
        "## One row per supplied variant, in order. Do not add, remove or reorder rows.",
    ]
    lines += ["", "```yaml", f"applicable_disease: {json.dumps(str(disease), ensure_ascii=False)}"]
    lines += [
        "prognostic_frameworks:",
        "  - name: \"<framework name>\"",
        "    tier: null",
        "    reason: \"<one concise proposition supporting framework applicability and, when tier is populated, the tier assignment; use prognostic_frameworks: [] when none can be identified>\"",
        "  # Add another item for each additional applicable framework.",
        "classification:",
    ]
    for vid in variant_ids:
        gene = _gene(registry, vid) or "<deterministically injected gene>"
        lines += [
            f"  - variant: {vid}",
            f"    gene: {gene}",
            "    framework_effects:",
            "      - framework: \"<exact name from prognostic_frameworks; use framework_effects: [] when none>\"",
            "        effect: <favorable|adverse|neutral>",
            "        reason: \"<one concise framework-specific proposition>\"",
            "    other_evidence_effect: <favorable|adverse|neutral|no_evidence>",
            "    other_evidence_reason: \"<one concise same-disease proposition; use null when no_evidence>\"",
        ]
    lines += ["```"]
    return "\n".join(lines)


def skeleton(c: DomainContract, variant_ids, *, registry=None, applicable_disease=None) -> str:
    """Render the exact model-facing owner artifact with deterministic identities prefilled."""
    ordered = list(variant_ids)
    disease = applicable_disease or "<authoritative WHO5 schema_disease>"
    if c.domain == "prognosis":
        return _prognosis_skeleton(ordered, registry or {}, disease)

    category = c.category_field or "bucket"
    choices = "|".join(c.buckets)
    lines = [f"## Return exactly this YAML for the {c.label} proforma, and nothing else.", ""]
    if c.domain in {"treatment", "biomarker"}:
        lines.append("## `applicable_disease` is deterministic and must remain the supplied authoritative WHO5 disease.")
    if c.multi_row:
        lines.append(
            "## Every supplied variant must appear at least once. Add a row only for a second, genuinely distinct implication. Do not change any `variant` value."
        )
    else:
        lines.append("## One row per variant, in order. Do not add, remove or reorder rows, and do not change any `variant` value.")
    for line in c.guidance:
        lines.append(f"## {line}")
    lines += ["", "```yaml"]
    if c.domain in {"treatment", "biomarker"}:
        lines.append(f"applicable_disease: {json.dumps(str(disease), ensure_ascii=False)}")
    lines.append("classification:")
    for vid in ordered:
        lines.append(f"  - variant: {vid}")
        if c.domain in {"treatment", "biomarker"}:
            lines.append(f"    gene: {_gene(registry or {}, vid) or '<deterministically injected gene>'}")
        lines.append(f"    {category}: <{choices}>")
        if c.therapy_buckets:
            lines.append(
                "    therapy: \"<named therapy; omit this field only for "
                f"{c.solitary_buckets[0] if c.solitary_buckets else 'non-therapeutic'} rows>\""
            )
        lines.append(f"    reason: \"<one concise report-ready {c.label} proposition>\"")
    lines.append("```")
    return "\n".join(lines)


def normalize_model_output(text: str, c: DomainContract, registry: dict, applicable_disease: str | None):
    """Inject deterministic disease/gene identity without repairing clinical reasoning.

    Returns ``(yaml_text, transform_records)``. Unknown variant IDs are left alone
    so ordinary validation can reject them.
    """
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError:
        return text, []
    if not isinstance(doc, dict):
        return text, []
    records = []
    if c.domain in {"prognosis", "treatment", "biomarker"} and applicable_disease:
        if doc.get("applicable_disease") != applicable_disease:
            records.append({
                "transform": "inject_authoritative_disease",
                "path": "applicable_disease",
                "from": doc.get("applicable_disease"),
                "to": applicable_disease,
            })
        doc["applicable_disease"] = applicable_disease
    if c.domain in {"prognosis", "treatment", "biomarker"}:
        rows = doc.get("classification")
        if isinstance(rows, list):
            for i, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                vid = row.get("variant")
                gene = _gene(registry, vid)
                if not gene:
                    continue
                if row.get("gene") != gene:
                    records.append({
                        "transform": "inject_canonical_gene",
                        "path": f"classification[{i}].gene",
                        "from": row.get("gene"),
                        "to": gene,
                    })
                row["gene"] = gene
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=110), records


def validate(text: str, c: DomainContract, context: dict) -> str:
    from workflows.proforma_v1 import stage_validation

    return stage_validation.validate(c.domain, text, context)


def _base_entry(row):
    entry = {"variants": [row.get("variant")], "reason": row.get("reason")}
    if row.get("gene"):
        entry["gene"] = row.get("gene")
    return entry


def pivot(doc: dict, c: DomainContract) -> dict:
    """Project model-facing variant rows into the stable internal bucket shape."""
    if c.domain == "prognosis":
        out = {bucket: [] for bucket in c.buckets}
        out["applicable_disease"] = doc.get("applicable_disease")
        out["prognostic_frameworks"] = list(doc.get("prognostic_frameworks") or [])
        for row in doc.get("classification") or []:
            if not isinstance(row, dict):
                continue
            vid = row.get("variant")
            gene = row.get("gene")
            framework_effects = row.get("framework_effects") or []
            for effect_row in framework_effects:
                if not isinstance(effect_row, dict):
                    continue
                effect = effect_row.get("effect")
                bucket = f"framework_{effect}"
                if bucket not in out:
                    continue
                entry = {
                    "variants": [vid],
                    "gene": gene,
                    "framework": effect_row.get("framework"),
                    "reason": effect_row.get("reason"),
                }
                out[bucket].append(entry)
            other = row.get("other_evidence_effect")
            if other in {"favorable", "adverse", "neutral"}:
                out[f"other_evidence_{other}"].append({
                    "variants": [vid],
                    "gene": gene,
                    "reason": row.get("other_evidence_reason"),
                })
            elif other == "no_evidence" and not framework_effects:
                out["no_prognostic_evidence"].append({
                    "variants": [vid],
                    "gene": gene,
                    "reason": "No disease-applicable prognostic evidence was identified for this variant.",
                })
        return out

    out = {bucket: [] for bucket in c.buckets}
    if c.domain in {"treatment", "biomarker"}:
        out["applicable_disease"] = doc.get("applicable_disease")
    category = c.category_field or "bucket"
    for row in doc.get("classification") or []:
        if not isinstance(row, dict):
            continue
        bucket = row.get(category)
        if bucket not in out:
            continue
        entry = _base_entry(row)
        if bucket in c.therapy_buckets:
            entry["therapy"] = row.get("therapy")
        out[bucket].append(entry)
    for key in c.extra_keys:
        out[key] = doc.get(key)
    return out


def render_pivoted(doc: dict, c: DomainContract) -> str:
    return yaml.safe_dump(pivot(doc, c), sort_keys=False, allow_unicode=True, width=110)
