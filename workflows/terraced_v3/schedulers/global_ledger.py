"""Global-ledger scheduler.

One model fills all downstream hard-fact domains at once. A blind-to-prose
adversarial review may replace whole domain documents via a validated patch;
Python applies the patch deterministically.
"""
from __future__ import annotations

import json
import yaml

from scripts.core.validated_model_task import ValidationIssue, fail
from workflows.terraced_v3 import layout, runtime
from workflows.terraced_v3.schedulers import common

SCHEDULER_ID = "global-ledger"
DESCRIPTION = "Fill the complete downstream ledger globally, then apply a validated adversarial domain patch."


def _validate_global(text: str, *, ctx: common.SchedulerContext, evidence: dict[str, common.EvidenceView]) -> str:
    doc = runtime.parse_yaml_mapping(text, "global hard-fact ledger")
    issues: list[ValidationIssue] = []
    if set(doc) != set(common.DOMAINS):
        issues.append(ValidationIssue("Top level", f"received fields {sorted(doc)}", f"return exactly {list(common.DOMAINS)}"))
    fail("global hard-fact ledger", issues)
    for domain in common.DOMAINS:
        runtime.validate_domain_text(yaml.safe_dump(doc.get(domain), sort_keys=False), domain=domain, spec=ctx.specs[domain], permitted_tags=evidence[domain].permitted_tags)
    return "global hard-fact ledger validated"


def _validate_patch(text: str, *, ctx: common.SchedulerContext, evidence: dict[str, common.EvidenceView]) -> str:
    doc = runtime.parse_yaml_mapping(text, "global-ledger review patch")
    issues: list[ValidationIssue] = []
    if set(doc) != {"changes"}:
        issues.append(ValidationIssue("Top level", f"received fields {sorted(doc)}", "return exactly changes"))
    changes = doc.get("changes")
    if not isinstance(changes, list):
        issues.append(ValidationIssue("changes", f"expected list, received {type(changes).__name__}", "return [] or one replacement per changed domain")); changes = []
    seen = set()
    for i, change in enumerate(changes):
        loc = f"changes[{i}]"
        if not isinstance(change, dict):
            issues.append(ValidationIssue(loc, f"expected mapping, received {type(change).__name__}", "return domain, reason, replacement")); continue
        expected = {"domain", "reason", "replacement"}
        if set(change) != expected:
            issues.append(ValidationIssue(loc, f"received fields {sorted(change)}", f"return exactly {sorted(expected)}"))
        domain = change.get("domain")
        if domain not in common.DOMAINS:
            issues.append(ValidationIssue(f"{loc}.domain", f"unknown domain {domain!r}", f"use one of {list(common.DOMAINS)}")); continue
        if domain in seen:
            issues.append(ValidationIssue(f"{loc}.domain", f"duplicate domain {domain!r}", "replace a domain at most once"))
        seen.add(domain)
        if not isinstance(change.get("reason"), str) or not change["reason"].strip():
            issues.append(ValidationIssue(f"{loc}.reason", "blank or not a string", "briefly state why the replacement is required"))
    fail("global-ledger review patch", issues)
    for change in changes:
        domain = change.get("domain")
        if domain in common.DOMAINS:
            runtime.validate_domain_text(yaml.safe_dump(change.get("replacement"), sort_keys=False), domain=domain, spec=ctx.specs[domain], permitted_tags=evidence[domain].permitted_tags)
    return "global-ledger review patch validated"


def run(ctx: common.SchedulerContext) -> None:
    if all(layout.domain(ctx.work, d, "FINAL_STATE.yaml").is_file() for d in common.DOMAINS):
        return
    evidence = {domain: ctx.ensure_evidence(domain) for domain in common.DOMAINS}
    root = layout.scheduler_dir(ctx.work, "global-ledger", existing=False)
    initial = root / "INITIAL.yaml"
    if not initial.is_file():
        contracts = "\n\n".join(common.contract(d, ctx.case, ctx.diagnoses) for d in common.DOMAINS)
        evidence_text = "\n\n".join(f"## {d}\n{evidence[d].text}" for d in common.DOMAINS)
        scopes = {d: {k: v for k, v in ctx.specs[d].items() if k.startswith("required_")} for d in common.DOMAINS}
        prompt = f"""# Terraced-v3 global hard-fact ledger

Fill all four downstream clinical domains in one coherent pass. Keep every decision explicitly disease-scoped. Do not write final report prose beyond surfaced fact fields. Candidate card tags must come from the matching evidence domain.

Return YAML only with exactly four top-level keys: prognosis, treatment, biomarker, germline. Each value must be the complete standard terraced-v3 domain artifact.

{contracts}

# Structured immutable case
```json
{json.dumps(ctx.case, indent=2, ensure_ascii=False)}
```

# Settled WHO5 diagnoses and final CMCs
```yaml
{yaml.safe_dump({'diagnoses': ctx.diagnoses, 'final_cmcs': ctx.final_cmcs}, sort_keys=False, allow_unicode=True).rstrip()}
```

# Required scopes
```yaml
{yaml.safe_dump(scopes, sort_keys=False, allow_unicode=True).rstrip()}
```

# Evidence by domain
{evidence_text}
"""
        ctx.call_yaml(call_id="global-ledger-initial", prompt=prompt, output=initial, validator=lambda t: _validate_global(t, ctx=ctx, evidence=evidence))
    initial_doc = runtime.parse_yaml_mapping(ctx.read_text(initial), "global ledger")

    review = root / "REVIEW_PATCH.yaml"
    if not review.is_file():
        evidence_text = "\n\n".join(f"## {d}\n{evidence[d].text}" for d in common.DOMAINS)
        prompt = f"""# Terraced-v3 global-ledger adversarial review

Review the complete validated downstream hard-fact ledger against the immutable case, settled WHO5 diagnoses and supplied evidence. Focus on clinically material errors, disease-scope transfer, overcalling, missed positive implications, and incorrect fact/reason wording. Do not rewrite domains that are already correct.

Return a PATCH only:
```yaml
changes:
  - domain: prognosis
    reason: "why the validated domain must change"
    replacement:
      decisions: []
```
Each replacement must be the COMPLETE standard artifact for that domain. Use `changes: []` when no material correction is warranted. Python will apply replacements deterministically.

# Initial validated ledger
```yaml
{yaml.safe_dump(initial_doc, sort_keys=False, allow_unicode=True, width=110).rstrip()}
```

# Structured case
```json
{json.dumps(ctx.case, indent=2, ensure_ascii=False)}
```

# Settled WHO5 diagnoses
```yaml
{yaml.safe_dump({'diagnoses': ctx.diagnoses, 'final_cmcs': ctx.final_cmcs}, sort_keys=False, allow_unicode=True).rstrip()}
```

# Evidence by domain
{evidence_text}
"""
        ctx.call_yaml(call_id="global-ledger-review", prompt=prompt, output=review, validator=lambda t: _validate_patch(t, ctx=ctx, evidence=evidence))
    patch = runtime.parse_yaml_mapping(ctx.read_text(review), "global review patch")
    final_docs = {d: initial_doc[d] for d in common.DOMAINS}
    for change in patch["changes"]:
        final_docs[change["domain"]] = change["replacement"]
    ctx.write_text(root / "APPLIED.yaml", yaml.safe_dump(final_docs, sort_keys=False, allow_unicode=True, width=110))
    for domain in common.DOMAINS:
        text = yaml.safe_dump(final_docs[domain], sort_keys=False, allow_unicode=True, width=110)
        runtime.validate_domain_text(text, domain=domain, spec=ctx.specs[domain], permitted_tags=evidence[domain].permitted_tags)
        ctx.write_text(layout.domain(ctx.work, domain, "FINAL_STATE.yaml", existing=False), text)
