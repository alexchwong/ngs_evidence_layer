"""Adaptive microtask scheduler.

Initial domain batches cheaply fill all deterministic decision cells. Python
then identifies high-impact cells and sends only those cells through targeted
review terraces. Reviews return keep/replace patches; Python applies them.
"""
from __future__ import annotations

import json
import yaml

from scripts.core.validated_model_task import ValidationIssue, fail
from workflows.terraced_v3 import layout, runtime
from workflows.terraced_v3.schedulers import common

SCHEDULER_ID = "adaptive-microtask"
DESCRIPTION = "Initial domain batches followed by targeted review only for high-impact decision cells."


def _high_impact(domain: str, doc: dict) -> list[tuple[str, dict]]:
    rows: list[tuple[str, dict]] = []
    if domain == "prognosis":
        for row in doc["decisions"]:
            if row["effect"] != "neither":
                rows.append((f"{row['variant_id']}|{row['diagnosis_id']}", row))
    elif domain == "treatment":
        for row in doc["decisions"]:
            if row["drug_target"] or row["drug_resistance"]:
                rows.append((f"{row['gene']}|{row['diagnosis_id']}", row))
    elif domain == "biomarker":
        for row in doc["decisions"]:
            if row["mrd_usable"]:
                rows.append((f"{row['variant_id']}|{row['diagnosis_id']}", row))
    elif domain == "germline":
        for row in doc["variant_decisions"]:
            if row["potentially_germline"]:
                rows.append((row["variant_id"], row))
        cp = doc["clinical_picture"]
        if cp["supportive"] is not False:
            rows.append(("clinical_picture", cp))
    return rows


def _single_doc(domain: str, row: dict) -> tuple[dict, dict]:
    if domain == "prognosis":
        return {"decisions": [row]}, {"required_pairs": [(row["variant_id"], row["diagnosis_id"])]}
    if domain == "treatment":
        return {"decisions": [row]}, {"required_pairs": [(row["gene"], row["diagnosis_id"])]}
    if domain == "biomarker":
        return {"decisions": [row]}, {"required_pairs": [(row["variant_id"], row["diagnosis_id"])]}
    if domain == "germline" and "variant_id" in row:
        return {"variant_decisions": [row], "clinical_picture": {"supportive": False, "surface": False, "fact": None, "reason": None, "candidate_card_tags": []}}, {"required_variants": [row["variant_id"]]}
    raise ValueError("clinical_picture requires full germline validation context")


def _validate_review(text: str, *, domain: str, key: str, current: dict, evidence: common.EvidenceView, case: dict) -> str:
    doc = runtime.parse_yaml_mapping(text, "adaptive cell review")
    issues: list[ValidationIssue] = []
    if set(doc) != {"action", "reason", "replacement"}:
        issues.append(ValidationIssue("Top level", f"received fields {sorted(doc)}", "return exactly action, reason, replacement"))
    if doc.get("action") not in {"keep", "replace"}:
        issues.append(ValidationIssue("action", f"invalid value {doc.get('action')!r}", "use keep or replace"))
    if not isinstance(doc.get("reason"), str) or not doc["reason"].strip():
        issues.append(ValidationIssue("reason", "blank or not a string", "state briefly why the cell should be kept or replaced"))
    if doc.get("action") == "keep" and doc.get("replacement") is not None:
        issues.append(ValidationIssue("replacement", "must be null when action=keep", "set replacement: null"))
    if doc.get("action") == "replace" and not isinstance(doc.get("replacement"), dict):
        issues.append(ValidationIssue("replacement", f"expected mapping, received {type(doc.get('replacement')).__name__}", "return the complete replacement decision row"))
    fail("adaptive cell review", issues)
    if doc["action"] == "replace":
        replacement = doc["replacement"]
        if domain != "germline" or key != "clinical_picture":
            single, spec = _single_doc(domain, replacement)
            runtime.validate_domain_text(yaml.safe_dump(single, sort_keys=False), domain=domain, spec=spec, permitted_tags=evidence.permitted_tags)
            old_scope = _scope_key(domain, current)
            new_scope = _scope_key(domain, replacement)
            if old_scope != new_scope:
                raise ValueError(f"adaptive review replacement changed protected cell scope from {old_scope!r} to {new_scope!r}")
        else:
            dummy = [{"variant_id": v["variant_id"], "potentially_germline": False, "surface": False, "fact": None, "reason": None, "candidate_card_tags": []} for v in case.get("variants") or []]
            runtime.validate_domain_text(yaml.safe_dump({"variant_decisions": dummy, "clinical_picture": replacement}, sort_keys=False), domain="germline", spec={"required_variants": [v["variant_id"] for v in case.get("variants") or []]}, permitted_tags=evidence.permitted_tags)
    return "adaptive cell review validated"


def _scope_key(domain: str, row: dict):
    if domain in {"prognosis", "biomarker"}:
        return (row.get("variant_id"), row.get("diagnosis_id"))
    if domain == "treatment":
        return (row.get("gene"), row.get("diagnosis_id"))
    if domain == "germline" and "variant_id" in row:
        return row.get("variant_id")
    return "clinical_picture"


def _replace_cell(domain: str, doc: dict, key: str, replacement: dict) -> None:
    if domain in {"prognosis", "treatment", "biomarker"}:
        rows = doc["decisions"]
        for i, row in enumerate(rows):
            if _scope_key(domain, row) == _scope_key(domain, replacement):
                rows[i] = replacement; return
    elif domain == "germline" and key != "clinical_picture":
        rows = doc["variant_decisions"]
        for i, row in enumerate(rows):
            if row["variant_id"] == replacement["variant_id"]:
                rows[i] = replacement; return
    elif domain == "germline" and key == "clinical_picture":
        doc["clinical_picture"] = replacement; return
    raise ValueError(f"could not apply adaptive replacement for {domain}:{key}")


def run(ctx: common.SchedulerContext) -> None:
    if all(layout.domain(ctx.work, d, "FINAL_STATE.yaml").is_file() for d in common.DOMAINS):
        return
    evidence = {domain: ctx.ensure_evidence(domain) for domain in common.DOMAINS}
    root = layout.scheduler_dir(ctx.work, "adaptive-microtask", existing=False)
    docs = {}
    for domain, spec in ctx.specs.items():
        initial = root / f"{domain}-initial.yaml"
        if not initial.is_file():
            context = ctx.base_context(spec, evidence[domain].text)
            prompt = ctx.domain_task_prompt + "\n\n" + common.contract(domain, ctx.case, ctx.diagnoses) + "\n\n# Adaptive scheduler initial batch\nFill all deterministic cells. High-impact cells may be independently reviewed later.\n\n" + context
            ctx.call_yaml(call_id=f"adaptive-{domain}-initial", prompt=prompt, output=initial, validator=lambda t, d=domain, s=spec, p=evidence[domain].permitted_tags: runtime.validate_domain_text(t, domain=d, spec=s, permitted_tags=p))
        docs[domain] = runtime.parse_yaml_mapping(ctx.read_text(initial), f"adaptive {domain} initial")

    review_manifest = []
    for domain in common.DOMAINS:
        for key, row in _high_impact(domain, docs[domain]):
            safe_key = "".join(ch if ch.isalnum() else "-" for ch in key)
            output = root / "reviews" / f"{domain}-{safe_key}.yaml"
            output.parent.mkdir(parents=True, exist_ok=True)
            if not output.is_file():
                prompt = f"""# Terraced-v3 adaptive targeted review

Review exactly one high-impact clinical decision cell. Do not reconsider unrelated cells. Compare the current validated cell against the immutable case, settled WHO5 disease context and the supplied {domain} evidence. Return `keep` when materially correct; otherwise return the complete corrected row. Candidate card tags must come from supplied evidence.

Return YAML only:
```yaml
action: keep
reason: "brief adjudication"
replacement: null
```
or use `action: replace` with the complete replacement row.

# Cell
`{domain}:{key}`
```yaml
{yaml.safe_dump(row, sort_keys=False, allow_unicode=True).rstrip()}
```

# Structured case
```json
{json.dumps(ctx.case, indent=2, ensure_ascii=False)}
```

# Settled WHO5 diagnoses
```yaml
{yaml.safe_dump({'diagnoses': ctx.diagnoses, 'final_cmcs': ctx.final_cmcs}, sort_keys=False, allow_unicode=True).rstrip()}
```

# Evidence
{evidence[domain].text}
"""
                ctx.call_yaml(call_id=f"adaptive-review-{domain}-{safe_key}", prompt=prompt, output=output, validator=lambda t, d=domain, k=key, r=row: _validate_review(t, domain=d, key=k, current=r, evidence=evidence[d], case=ctx.case))
            review = runtime.parse_yaml_mapping(ctx.read_text(output), "adaptive review")
            review_manifest.append({"domain": domain, "key": key, "action": review["action"], "reason": review["reason"]})
            if review["action"] == "replace":
                _replace_cell(domain, docs[domain], key, review["replacement"])
    ctx.write_text(root / "review-manifest.yaml", yaml.safe_dump({"reviews": review_manifest}, sort_keys=False, allow_unicode=True, width=110))
    for domain in common.DOMAINS:
        text = yaml.safe_dump(docs[domain], sort_keys=False, allow_unicode=True, width=110)
        runtime.validate_domain_text(text, domain=domain, spec=ctx.specs[domain], permitted_tags=evidence[domain].permitted_tags)
        ctx.write_text(layout.domain(ctx.work, domain, "FINAL_STATE.yaml", existing=False), text)
