"""Variant-centric scheduler.

A model task considers prognosis, treatment, MRD and germline implications for
one detected variant together. Treatment is emitted only by the first variant
for each gene so the canonical downstream contract remains gene × diagnosis.
The case-level germline phenotype is decided separately.
"""
from __future__ import annotations

import json
import yaml

from scripts.core.validated_model_task import ValidationIssue, fail
from workflows.terraced_v3 import layout, runtime
from workflows.terraced_v3.schedulers import common

SCHEDULER_ID = "variant-centric"
DESCRIPTION = "One cross-domain task per detected variant, plus a case-level germline phenotype task."


def _dummy_cp() -> dict:
    return {"supportive": False, "surface": False, "fact": None, "reason": None, "candidate_card_tags": []}


def _validate_variant(text: str, *, variant: dict, diagnosis_ids: list[str], include_treatment: bool, evidence: dict[str, common.EvidenceView]) -> str:
    doc = runtime.parse_yaml_mapping(text, "variant-centric task")
    issues: list[ValidationIssue] = []
    expected = {"variant_id", "prognosis", "treatment", "biomarker", "germline_variant"}
    if set(doc) != expected:
        issues.append(ValidationIssue("Top level", f"received fields {sorted(doc)}", f"return exactly {sorted(expected)}"))
    if doc.get("variant_id") != variant["variant_id"]:
        issues.append(ValidationIssue("variant_id", f"received {doc.get('variant_id')!r}", f"copy exact variant_id {variant['variant_id']!r}"))
    fail("variant-centric task", issues)
    pair_spec = {"required_pairs": [(variant["variant_id"], dx) for dx in diagnosis_ids]}
    runtime.validate_domain_text(yaml.safe_dump(doc.get("prognosis"), sort_keys=False), domain="prognosis", spec=pair_spec, permitted_tags=evidence["prognosis"].permitted_tags)
    runtime.validate_domain_text(yaml.safe_dump(doc.get("biomarker"), sort_keys=False), domain="biomarker", spec=pair_spec, permitted_tags=evidence["biomarker"].permitted_tags)
    if include_treatment:
        tx_spec = {"required_pairs": [(variant["gene"], dx) for dx in diagnosis_ids]}
        runtime.validate_domain_text(yaml.safe_dump(doc.get("treatment"), sort_keys=False), domain="treatment", spec=tx_spec, permitted_tags=evidence["treatment"].permitted_tags)
    elif doc.get("treatment") is not None:
        raise ValueError("variant-centric task treatment must be null because this gene's treatment decision is owned by an earlier variant")
    germ_doc = {"variant_decisions": [doc.get("germline_variant")], "clinical_picture": _dummy_cp()}
    runtime.validate_domain_text(yaml.safe_dump(germ_doc, sort_keys=False), domain="germline", spec={"required_variants": [variant["variant_id"]]}, permitted_tags=evidence["germline"].permitted_tags)
    return "variant-centric task validated"


def _validate_clinical_picture(text: str, *, variants: list[dict], permitted_tags: set[str]) -> str:
    doc = runtime.parse_yaml_mapping(text, "germline clinical-picture task")
    if set(doc) != {"clinical_picture"}:
        raise ValueError("germline clinical-picture task must return exactly clinical_picture")
    dummy = [
        {"variant_id": v["variant_id"], "potentially_germline": False, "surface": False, "fact": None, "reason": None, "candidate_card_tags": []}
        for v in variants
    ]
    runtime.validate_domain_text(yaml.safe_dump({"variant_decisions": dummy, "clinical_picture": doc["clinical_picture"]}, sort_keys=False), domain="germline", spec={"required_variants": [v["variant_id"] for v in variants]}, permitted_tags=permitted_tags)
    return "germline clinical-picture task validated"


def run(ctx: common.SchedulerContext) -> None:
    if all(layout.domain(ctx.work, d, "FINAL_STATE.yaml").is_file() for d in common.DOMAINS):
        return
    evidence = {domain: ctx.ensure_evidence(domain) for domain in common.DOMAINS}
    root = layout.scheduler_dir(ctx.work, "variant-centric", existing=False)
    diagnosis_ids = [d["diagnosis_id"] for d in ctx.diagnoses]
    first_variant_for_gene: dict[str, str] = {}
    for variant in ctx.case.get("variants") or []:
        first_variant_for_gene.setdefault(variant["gene"], variant["variant_id"])
    outputs = []
    for variant in ctx.case.get("variants") or []:
        include_tx = first_variant_for_gene[variant["gene"]] == variant["variant_id"]
        output = root / f"{variant['variant_id']}.yaml"
        if not output.is_file():
            ev_text = "\n\n".join(f"## {d}\n{evidence[d].text}" for d in common.DOMAINS)
            prompt = f"""# Terraced-v3 variant-centric task

Consider this one detected variant across the four downstream clinical questions. Keep every decision disease-scoped. Return hard decisions plus reportable fact/reason only where surfaced. Candidate card tags must come from the matching domain evidence section.

Variant: `{variant['variant_id']}` / `{variant['gene']}` / `{variant['description']}`
Treatment owner for this gene: `{str(include_tx).lower()}`. If false, return `treatment: null`.

Return YAML only with exactly:
```yaml
variant_id: {variant['variant_id']}
prognosis:
  decisions: []
treatment: null
biomarker:
  decisions: []
germline_variant:
  variant_id: {variant['variant_id']}
  potentially_germline: false
  surface: false
  fact: null
  reason: null
  candidate_card_tags: []
```
The prognosis/biomarker decision rows use the standard terraced-v3 contracts for this variant × every settled diagnosis. When treatment owner is true, treatment contains the standard treatment `decisions` mapping for `{variant['gene']}` × every settled diagnosis.

# Structured case
```json
{json.dumps(ctx.case, indent=2, ensure_ascii=False)}
```

# Settled WHO5 diagnoses
```yaml
{yaml.safe_dump({'diagnoses': ctx.diagnoses, 'final_cmcs': ctx.final_cmcs}, sort_keys=False, allow_unicode=True).rstrip()}
```

# Evidence by domain
{ev_text}
"""
            ctx.call_yaml(
                call_id=f"variant-{variant['variant_id']}", prompt=prompt, output=output,
                validator=lambda t, v=variant, tx=include_tx: _validate_variant(t, variant=v, diagnosis_ids=diagnosis_ids, include_treatment=tx, evidence=evidence),
            )
        outputs.append(runtime.parse_yaml_mapping(ctx.read_text(output), "variant-centric output"))

    cp_output = root / "germline-clinical.yaml"
    if not cp_output.is_file():
        prompt = f"""# Terraced-v3 germline clinical-picture task

Decide only whether the supplied age, phenotype and family history support a germline predisposition syndrome. Do not use tumour-only VAF to prove or exclude constitutional origin. Use only the supplied case and germline evidence.

Return YAML only:
```yaml
clinical_picture:
  supportive: false
  surface: false
  fact: null
  reason: null
  candidate_card_tags: []
```
`supportive` must be true, false, or uncertain.

# Structured case
```json
{json.dumps(ctx.case, indent=2, ensure_ascii=False)}
```

# Germline evidence
{evidence['germline'].text}
"""
        ctx.call_yaml(call_id="variant-germline-clinical", prompt=prompt, output=cp_output, validator=lambda t: _validate_clinical_picture(t, variants=ctx.case.get("variants") or [], permitted_tags=evidence["germline"].permitted_tags))
    cp = runtime.parse_yaml_mapping(ctx.read_text(cp_output), "germline clinical picture")["clinical_picture"]

    docs = {"prognosis": {"decisions": []}, "treatment": {"decisions": []}, "biomarker": {"decisions": []}, "germline": {"variant_decisions": [], "clinical_picture": cp}}
    for row in outputs:
        docs["prognosis"]["decisions"].extend(row["prognosis"]["decisions"])
        if row["treatment"] is not None:
            docs["treatment"]["decisions"].extend(row["treatment"]["decisions"])
        docs["biomarker"]["decisions"].extend(row["biomarker"]["decisions"])
        docs["germline"]["variant_decisions"].append(row["germline_variant"])
    for domain, doc in docs.items():
        text = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=110)
        runtime.validate_domain_text(text, domain=domain, spec=ctx.specs[domain], permitted_tags=evidence[domain].permitted_tags)
        ctx.write_text(layout.domain(ctx.work, domain, "FINAL_STATE.yaml", existing=False), text)
