"""Evidence-first scheduler.

Each domain first normalises the supplied evidence without making patient-level
clinical decisions. A second model call adjudicates the patient using only the
structured case, settled WHO5 state and the normalised evidence table.
"""
from __future__ import annotations

import yaml

from scripts.core.validated_model_task import ValidationIssue, fail
from workflows.terraced_v3 import card_identity, layout, runtime
from workflows.terraced_v3.schedulers import common

SCHEDULER_ID = "evidence-first"
DESCRIPTION = "Normalise relevant cards first, then independently adjudicate each clinical domain."


def _validate_normalized(text: str, evidence: common.EvidenceView, diagnosis_ids: set[str]) -> str:
    doc = runtime.parse_yaml_mapping(text, "normalised evidence")
    issues: list[ValidationIssue] = []
    if set(doc) != {"evidence_items"}:
        issues.append(ValidationIssue("Top level", f"received fields {sorted(doc)}", "return exactly evidence_items"))
    rows = doc.get("evidence_items")
    if not isinstance(rows, list):
        issues.append(ValidationIssue("evidence_items", f"expected list, received {type(rows).__name__}", "return a list; use [] when no card is relevant"))
        rows = []
    by_tag = {}
    tag_by_id = card_identity.tag_by_id(evidence.manifest)
    for card in evidence.cards:
        by_tag[tag_by_id[card["card_id"]]] = card
    seen = set()
    for i, row in enumerate(rows):
        loc = f"evidence_items[{i}]"
        if not isinstance(row, dict):
            issues.append(ValidationIssue(loc, f"expected mapping, received {type(row).__name__}", "return card_tag, diagnosis_ids, normalized_claim")); continue
        expected = {"card_tag", "diagnosis_ids", "normalized_claim"}
        if set(row) != expected:
            issues.append(ValidationIssue(loc, f"received fields {sorted(row)}", f"return exactly {sorted(expected)}"))
        tag = row.get("card_tag")
        raw = runtime.CARD_TAG_RE.fullmatch(tag or "")
        if raw is None or raw.group(1) not in evidence.permitted_tags:
            issues.append(ValidationIssue(f"{loc}.card_tag", f"invalid or unsupplied tag {tag!r}", "copy one exact supplied card tag"))
            continue
        tag_raw = raw.group(1)
        if tag_raw in seen:
            issues.append(ValidationIssue(f"{loc}.card_tag", f"duplicate tag {tag!r}", "normalise each included card once"))
        seen.add(tag_raw)
        ids = row.get("diagnosis_ids")
        if not isinstance(ids, list) or any(x not in diagnosis_ids for x in ids):
            issues.append(ValidationIssue(f"{loc}.diagnosis_ids", f"invalid diagnosis scope {ids!r}", "use only supplied settled diagnosis IDs; germline may use []"))
        else:
            card = by_tag.get(tag_raw)
            card_scope = None if card is None else card.get("matched_diagnosis_ids")
            if ids and card_scope is not None and not set(ids).issubset(set(card_scope or [])):
                issues.append(ValidationIssue(f"{loc}.diagnosis_ids", f"scope {ids!r} exceeds card retrieval scope {card_scope!r}", "scope the normalised claim only to diagnosis IDs for which this card was retrieved"))
        claim = row.get("normalized_claim")
        if not isinstance(claim, str) or not claim.strip():
            issues.append(ValidationIssue(f"{loc}.normalized_claim", "blank or not a string", "state the clinically usable claim from the card without deciding the patient"))
    fail("normalised evidence", issues)
    return "normalised evidence validated"


def run(ctx: common.SchedulerContext) -> None:
    diagnosis_ids = {d["diagnosis_id"] for d in ctx.diagnoses}
    for domain, spec in ctx.specs.items():
        existing_output = layout.domain(ctx.work, domain, "FINAL_STATE.yaml")
        if existing_output.is_file():
            continue
        evidence = ctx.ensure_evidence(domain)
        output = layout.domain(ctx.work, domain, "FINAL_STATE.yaml", existing=False)
        norm = layout.domain_dir(ctx.work, domain, existing=False) / "call_01_evidence" / "NORMALIZED.yaml"
        norm.parent.mkdir(parents=True, exist_ok=True)
        normalise_prompt = f"""# Terraced-v3 evidence normalisation — {domain}

Do not make a patient-level clinical decision. From the supplied raw cards, retain only evidence that may materially inform this {domain} task and rewrite each retained card as one concise clinically usable claim. Preserve qualifiers and disease scope. Do not combine cards. Do not add outside knowledge.

Return YAML only:
```yaml
evidence_items:
  - card_tag: "[card:0123456789ab]"
    diagnosis_ids: [DX1]
    normalized_claim: "..."
```
For germline evidence, diagnosis_ids should normally be []. Use [] when no supplied card is relevant.

# Settled diagnoses
```yaml
{yaml.safe_dump({'diagnoses': ctx.diagnoses}, sort_keys=False, allow_unicode=True).rstrip()}
```

# Raw evidence
{evidence.text}
"""
        ctx.call_yaml(
            call_id=f"{domain}-evidence-normalize",
            prompt=normalise_prompt,
            output=norm,
            validator=lambda t, e=evidence: _validate_normalized(t, e, diagnosis_ids),
        )
        norm_doc = runtime.parse_yaml_mapping(ctx.read_text(norm), "normalised evidence")
        normalized_tags = {runtime.CARD_TAG_RE.fullmatch(r["card_tag"]).group(1) for r in norm_doc["evidence_items"]}
        normalized_text = yaml.safe_dump(norm_doc, sort_keys=False, allow_unicode=True, width=110)
        context = ctx.base_context(spec, "# Normalised evidence table\n```yaml\n" + normalized_text + "```\n")
        prompt = (
            ctx.domain_task_prompt
            + "\n\n# Evidence-first adjudication\nThe raw cards have already been normalised in an independent pass. Use only the normalised evidence table below; do not infer omitted raw-card content.\n\n"
            + common.contract(domain, ctx.case, ctx.diagnoses)
            + "\n\n"
            + context
        )
        call_dir = layout.domain_dir(ctx.work, domain, existing=False) / "call_02_adjudication"
        call_dir.mkdir(parents=True, exist_ok=True)
        ctx.write_text(call_dir / "INPUT_normalized.yaml", normalized_text)
        ctx.call_yaml(
            call_id=f"{domain}-evidence-adjudicate",
            prompt=prompt,
            output=output,
            validator=lambda t, d=domain, s=spec, p=normalized_tags: runtime.validate_domain_text(t, domain=d, spec=s, permitted_tags=p),
        )
