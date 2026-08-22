"""Core scheduler primitives for terraced-v3 declarative scheduler YAML.

This module contains reusable execution primitives and validators. Scheduler
strategy/order belongs in schedulers/*/scheduler.yaml, never in scheduler-specific
Python modules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
import copy
import json
import re

import yaml

from scripts.core.validated_model_task import ValidationIssue, fail
from workflows.terraced_v3 import card_identity, layout, runtime

DOMAINS = ("prognosis", "treatment", "biomarker", "germline")


def task_specs(case: dict, diagnoses: list[dict]) -> dict[str, dict]:
    variants = case.get("variants") or []
    genes: list[str] = []
    for row in variants:
        gene = row["gene"]
        if gene not in genes:
            genes.append(gene)
    diagnosis_ids = [row["diagnosis_id"] for row in diagnoses]
    rows = [
        {"domain": "prognosis", "required_pairs": [(v["variant_id"], dx) for v in variants for dx in diagnosis_ids]},
        {"domain": "treatment", "required_pairs": [(g, dx) for g in genes for dx in diagnosis_ids]},
        {"domain": "biomarker", "required_pairs": [(v["variant_id"], dx) for v in variants for dx in diagnosis_ids]},
        {"domain": "germline", "required_variants": [v["variant_id"] for v in variants]},
    ]
    return {row["domain"]: row for row in rows}


@dataclass
class EvidenceView:
    domain: str
    cards: list[dict]
    manifest: dict
    permitted_tags: set[str]
    text: str


@dataclass
class SchedulerContext:
    work: Path
    case: dict
    diagnoses: list[dict]
    final_cmcs: list[str]
    pipeline_id: str
    call_model: Callable[..., None]
    ensure_evidence: Callable[[str], EvidenceView]
    read_text: Callable[[Path], str]
    write_text: Callable[[Path, str], Path]
    status: Callable[[str], None]
    phase: str = "ptbg"
    values: dict[str, Any] = field(default_factory=dict)
    ensure_diagnosis_evidence: Callable[[list[str]], EvidenceView] | None = None
    fact_guard: Callable[..., None] | None = None
    fact_commit: Callable[..., None] | None = None
    paraphrase_guard: Callable[..., None] | None = None

    @property
    def specs(self) -> dict[str, dict]:
        return task_specs(self.case, self.diagnoses) if self.diagnoses else {}


def dump(value: Any, render: str | None = None) -> str:
    if isinstance(value, EvidenceView):
        return value.text
    if render == "evidence_by_domain":
        return "\n\n".join(f"## {d}\n{value[d].text}" for d in DOMAINS)
    if render == "germline_evidence":
        return value["germline"].text
    if render == "json":
        return json.dumps(value, indent=2, ensure_ascii=False)
    if render == "yaml" or isinstance(value, (dict, list, tuple)):
        return yaml.safe_dump(value, sort_keys=False, allow_unicode=True, width=110).rstrip()
    if value is None:
        return "null"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def normalized_tags(doc: dict) -> set[str]:
    out: set[str] = set()
    for row in doc.get("evidence_items") or []:
        match = runtime.CARD_TAG_RE.fullmatch(row.get("card_tag") or "")
        if match:
            out.add(match.group(1))
    return out


def validate_normalized(text: str, *, evidence: EvidenceView, diagnosis_ids: set[str], **_: Any) -> str:
    doc = runtime.parse_yaml_mapping(text, "normalised evidence")
    issues: list[ValidationIssue] = []
    if set(doc) != {"evidence_items"}:
        issues.append(ValidationIssue("Top level", f"received fields {sorted(doc)}", "return exactly evidence_items"))
    rows = doc.get("evidence_items")
    if not isinstance(rows, list):
        issues.append(ValidationIssue("evidence_items", f"expected list, received {type(rows).__name__}", "return a list; use [] when no card is relevant")); rows = []
    tag_by_id = card_identity.tag_by_id(evidence.manifest)
    by_tag = {tag_by_id[c["card_id"]]: c for c in evidence.cards}
    seen: set[str] = set()
    for i, row in enumerate(rows):
        loc = f"evidence_items[{i}]"
        if not isinstance(row, dict):
            issues.append(ValidationIssue(loc, f"expected mapping, received {type(row).__name__}", "return card_tag, diagnosis_ids, normalized_claim")); continue
        expected = {"card_tag", "diagnosis_ids", "normalized_claim"}
        if set(row) != expected:
            issues.append(ValidationIssue(loc, f"received fields {sorted(row)}", f"return exactly {sorted(expected)}"))
        match = runtime.CARD_TAG_RE.fullmatch(row.get("card_tag") or "")
        if match is None or match.group(1) not in evidence.permitted_tags:
            issues.append(ValidationIssue(f"{loc}.card_tag", f"invalid or unsupplied tag {row.get('card_tag')!r}", "copy one exact supplied card tag")); continue
        raw = match.group(1)
        if raw in seen:
            issues.append(ValidationIssue(f"{loc}.card_tag", f"duplicate tag {row.get('card_tag')!r}", "normalise each included card once"))
        seen.add(raw)
        ids = row.get("diagnosis_ids")
        if not isinstance(ids, list) or any(x not in diagnosis_ids for x in ids):
            issues.append(ValidationIssue(f"{loc}.diagnosis_ids", f"invalid diagnosis scope {ids!r}", "use only settled diagnosis IDs; germline may use []"))
        else:
            card = by_tag.get(raw); card_scope = None if card is None else card.get("matched_diagnosis_ids")
            if ids and card_scope is not None and not set(ids).issubset(set(card_scope or [])):
                issues.append(ValidationIssue(f"{loc}.diagnosis_ids", f"scope {ids!r} exceeds card retrieval scope {card_scope!r}", "scope only to diagnosis IDs for which this card was retrieved"))
        if not isinstance(row.get("normalized_claim"), str) or not row["normalized_claim"].strip():
            issues.append(ValidationIssue(f"{loc}.normalized_claim", "blank or not a string", "state the clinically usable claim without deciding the patient"))
    fail("normalised evidence", issues)
    return "normalised evidence validated"


def _dummy_cp() -> dict:
    return {"supportive": False, "surface": False, "fact": None, "reason": None, "case_refs": [], "card_tags": []}


def _snapshot(snapshot_key: str, domain: str, facts: list[dict], *, commit: bool = True) -> dict:
    return {"snapshot_key": snapshot_key, "domain": domain, "facts": facts, "commit": commit}


def model_fact_snapshots(validator_name: str, doc: dict, *, item: Any, ctx: SchedulerContext) -> list[dict]:
    """Describe fact snapshots introduced by one validated model artifact.

    Snapshot keys define the deterministic reconciliation boundary.  Full-domain
    schedulers use one snapshot per domain; variant-centric tasks use one snapshot
    per variant so later variant calls cannot withdraw earlier variant facts.
    """
    if validator_name == "icc":
        return [_snapshot("diagnosis.icc", "diagnosis", runtime.facts_from_icc(doc))]
    if validator_name == "who5":
        return [_snapshot("diagnosis.who5", "diagnosis", runtime.facts_from_who5(doc))]
    if validator_name == "domain":
        domain=str(item)
        return [_snapshot(f"ptbg.{domain}", domain, runtime.facts_from_domain(domain, doc))]
    if validator_name == "variant_cross_domain":
        variant_id=doc["variant_id"]
        rows=[
            _snapshot(f"ptbg.prognosis.variant.{variant_id}", "prognosis", runtime.facts_from_domain("prognosis",doc["prognosis"])),
            _snapshot(f"ptbg.biomarker.variant.{variant_id}", "biomarker", runtime.facts_from_domain("biomarker",doc["biomarker"])),
        ]
        if doc.get("treatment") is not None:
            rows.append(_snapshot(f"ptbg.treatment.variant.{variant_id}", "treatment", runtime.facts_from_domain("treatment",doc["treatment"])))
        germ={"variant_decisions":[doc["germline_variant"]],"clinical_picture":_dummy_cp()}
        rows.append(_snapshot(f"ptbg.germline.variant.{variant_id}", "germline", runtime.facts_from_domain("germline",germ)))
        return rows
    if validator_name == "germline_clinical_picture":
        germ={
            "variant_decisions":[
                {"variant_id":v["variant_id"],"potentially_germline":False,"surface":False,"fact":None,"reason":None,"case_refs":[],"card_tags":[]}
                for v in ctx.case.get("variants") or []
            ],
            "clinical_picture":doc["clinical_picture"],
        }
        return [_snapshot("ptbg.germline.clinical-picture","germline",runtime.facts_from_domain("germline",germ))]
    if validator_name == "global_ledger":
        return [_snapshot(f"ptbg.{domain}",domain,runtime.facts_from_domain(domain,doc[domain])) for domain in DOMAINS]
    if validator_name == "global_patch":
        return [_snapshot(f"ptbg.{change['domain']}",change["domain"],runtime.facts_from_domain(change["domain"],change["replacement"])) for change in doc.get("changes") or []]
    if validator_name == "adaptive_cell_review":
        if doc.get("action") != "replace": return []
        domain=item["domain"]; replacement=doc["replacement"]
        if domain == "germline" and item["key"] == "clinical_picture":
            germ={
                "variant_decisions":[
                    {"variant_id":v["variant_id"],"potentially_germline":False,"surface":False,"fact":None,"reason":None,"case_refs":[],"card_tags":[]}
                    for v in ctx.case.get("variants") or []
                ],
                "clinical_picture":replacement,
            }
            facts=runtime.facts_from_domain("germline",germ)
        else:
            one,_spec=single_doc(domain,replacement)
            facts=runtime.facts_from_domain(domain,one)
        # A cell review is only a partial domain view: evidence-check any replacement
        # fact now, but reconcile the complete domain after reviews are applied.
        return [_snapshot(f"ptbg.{domain}",domain,facts,commit=False)]
    return []


def validate_variant(text: str, *, item: dict, ctx: SchedulerContext, evidence: dict[str, EvidenceView], include_treatment: bool, **_: Any) -> str:
    doc = runtime.parse_yaml_mapping(text, "variant-centric task")
    issues: list[ValidationIssue] = []
    expected = {"variant_id", "prognosis", "treatment", "biomarker", "germline_variant"}
    if set(doc) != expected:
        issues.append(ValidationIssue("Top level", f"received fields {sorted(doc)}", f"return exactly {sorted(expected)}"))
    if doc.get("variant_id") != item["variant_id"]:
        issues.append(ValidationIssue("variant_id", f"received {doc.get('variant_id')!r}", f"copy exact variant_id {item['variant_id']!r}"))
    fail("variant-centric task", issues)
    diagnosis_ids = [d["diagnosis_id"] for d in ctx.diagnoses]
    pair_spec = {"required_pairs": [(item["variant_id"], dx) for dx in diagnosis_ids]}
    runtime.validate_domain_text(yaml.safe_dump(doc.get("prognosis"), sort_keys=False), domain="prognosis", spec=pair_spec, permitted_tags=evidence["prognosis"].permitted_tags, permitted_case_refs=runtime.case_reference_ids(ctx.case))
    runtime.validate_domain_text(yaml.safe_dump(doc.get("biomarker"), sort_keys=False), domain="biomarker", spec=pair_spec, permitted_tags=evidence["biomarker"].permitted_tags, permitted_case_refs=runtime.case_reference_ids(ctx.case))
    if include_treatment:
        runtime.validate_domain_text(yaml.safe_dump(doc.get("treatment"), sort_keys=False), domain="treatment", spec={"required_pairs": [(item["gene"], dx) for dx in diagnosis_ids]}, permitted_tags=evidence["treatment"].permitted_tags, permitted_case_refs=runtime.case_reference_ids(ctx.case))
    elif doc.get("treatment") is not None:
        raise ValueError("variant-centric task treatment must be null because an earlier variant owns this gene's treatment decision")
    germ_doc = {"variant_decisions": [doc.get("germline_variant")], "clinical_picture": _dummy_cp()}
    runtime.validate_domain_text(yaml.safe_dump(germ_doc, sort_keys=False), domain="germline", spec={"required_variants": [item["variant_id"]]}, permitted_tags=evidence["germline"].permitted_tags, permitted_case_refs=runtime.case_reference_ids(ctx.case))
    return "variant-centric task validated"


def validate_clinical_picture(text: str, *, ctx: SchedulerContext, evidence: EvidenceView, **_: Any) -> str:
    doc = runtime.parse_yaml_mapping(text, "germline clinical-picture task")
    if set(doc) != {"clinical_picture"}:
        raise ValueError("germline clinical-picture task must return exactly clinical_picture")
    dummy = [{"variant_id": v["variant_id"], "potentially_germline": False, "surface": False, "fact": None, "reason": None, "case_refs": [], "card_tags": []} for v in ctx.case.get("variants") or []]
    runtime.validate_domain_text(yaml.safe_dump({"variant_decisions": dummy, "clinical_picture": doc["clinical_picture"]}, sort_keys=False), domain="germline", spec={"required_variants": [v["variant_id"] for v in ctx.case.get("variants") or []]}, permitted_tags=evidence.permitted_tags, permitted_case_refs=runtime.case_reference_ids(ctx.case))
    return "germline clinical-picture task validated"


def validate_global(text: str, *, ctx: SchedulerContext, evidence: dict[str, EvidenceView], **_: Any) -> str:
    doc = runtime.parse_yaml_mapping(text, "global hard-fact ledger")
    if set(doc) != set(DOMAINS):
        raise ValueError(f"global hard-fact ledger must return exactly {list(DOMAINS)}")
    for domain in DOMAINS:
        runtime.validate_domain_text(yaml.safe_dump(doc.get(domain), sort_keys=False), domain=domain, spec=ctx.specs[domain], permitted_tags=evidence[domain].permitted_tags, permitted_case_refs=runtime.case_reference_ids(ctx.case))
    return "global hard-fact ledger validated"


def validate_global_patch(text: str, *, ctx: SchedulerContext, evidence: dict[str, EvidenceView], **_: Any) -> str:
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
            issues.append(ValidationIssue(loc, "expected mapping", "return domain, reason, replacement")); continue
        if set(change) != {"domain", "reason", "replacement"}:
            issues.append(ValidationIssue(loc, f"received fields {sorted(change)}", "return exactly domain, reason, replacement"))
        domain = change.get("domain")
        if domain not in DOMAINS:
            issues.append(ValidationIssue(f"{loc}.domain", f"unknown domain {domain!r}", f"use one of {list(DOMAINS)}")); continue
        if domain in seen:
            issues.append(ValidationIssue(f"{loc}.domain", f"duplicate domain {domain!r}", "replace a domain at most once"))
        seen.add(domain)
        if not isinstance(change.get("reason"), str) or not change["reason"].strip():
            issues.append(ValidationIssue(f"{loc}.reason", "blank or not a string", "briefly state why replacement is required"))
    fail("global-ledger review patch", issues)
    for change in changes:
        if change.get("domain") in DOMAINS:
            d = change["domain"]
            runtime.validate_domain_text(yaml.safe_dump(change.get("replacement"), sort_keys=False), domain=d, spec=ctx.specs[d], permitted_tags=evidence[d].permitted_tags, permitted_case_refs=runtime.case_reference_ids(ctx.case))
    return "global-ledger review patch validated"


def scope_key(domain: str, row: dict):
    if domain in {"prognosis", "biomarker"}: return (row.get("variant_id"), row.get("diagnosis_id"))
    if domain == "treatment": return (row.get("gene"), row.get("diagnosis_id"))
    if domain == "germline" and "variant_id" in row: return row.get("variant_id")
    return "clinical_picture"


def single_doc(domain: str, row: dict) -> tuple[dict, dict]:
    if domain == "prognosis": return {"decisions": [row]}, {"required_pairs": [(row["variant_id"], row["diagnosis_id"])]}
    if domain == "treatment": return {"decisions": [row]}, {"required_pairs": [(row["gene"], row["diagnosis_id"])]}
    if domain == "biomarker": return {"decisions": [row]}, {"required_pairs": [(row["variant_id"], row["diagnosis_id"])]}
    if domain == "germline" and "variant_id" in row: return {"variant_decisions": [row], "clinical_picture": _dummy_cp()}, {"required_variants": [row["variant_id"]]}
    raise ValueError("clinical_picture requires full germline validation context")


def validate_cell_review(text: str, *, item: dict, ctx: SchedulerContext, evidence: EvidenceView, **_: Any) -> str:
    doc = runtime.parse_yaml_mapping(text, "adaptive cell review")
    issues: list[ValidationIssue] = []
    if set(doc) != {"action", "reason", "replacement"}:
        issues.append(ValidationIssue("Top level", f"received fields {sorted(doc)}", "return exactly action, reason, replacement"))
    if doc.get("action") not in {"keep", "replace"}: issues.append(ValidationIssue("action", f"invalid value {doc.get('action')!r}", "use keep or replace"))
    if not isinstance(doc.get("reason"), str) or not doc["reason"].strip(): issues.append(ValidationIssue("reason", "blank or not a string", "state briefly why the cell should be kept or replaced"))
    if doc.get("action") == "keep" and doc.get("replacement") is not None: issues.append(ValidationIssue("replacement", "must be null when action=keep", "set replacement: null"))
    if doc.get("action") == "replace" and not isinstance(doc.get("replacement"), dict): issues.append(ValidationIssue("replacement", "expected mapping", "return the complete replacement decision row"))
    fail("adaptive cell review", issues)
    if doc["action"] == "replace":
        replacement = doc["replacement"]; domain = item["domain"]; key = item["key"]; current = item["row"]
        if domain != "germline" or key != "clinical_picture":
            one, spec = single_doc(domain, replacement)
            runtime.validate_domain_text(yaml.safe_dump(one, sort_keys=False), domain=domain, spec=spec, permitted_tags=evidence.permitted_tags, permitted_case_refs=runtime.case_reference_ids(ctx.case))
            if scope_key(domain, current) != scope_key(domain, replacement):
                raise ValueError("adaptive review replacement changed protected cell scope")
        else:
            dummy = [{"variant_id": v["variant_id"], "potentially_germline": False, "surface": False, "fact": None, "reason": None, "case_refs": [], "card_tags": []} for v in ctx.case.get("variants") or []]
            runtime.validate_domain_text(yaml.safe_dump({"variant_decisions": dummy, "clinical_picture": replacement}, sort_keys=False), domain="germline", spec={"required_variants": [v["variant_id"] for v in ctx.case.get("variants") or []]}, permitted_tags=evidence.permitted_tags, permitted_case_refs=runtime.case_reference_ids(ctx.case))
    return "adaptive cell review validated"


def high_impact_cells(states: dict[str, dict]) -> list[dict]:
    rows: list[dict] = []
    for domain, doc in states.items():
        selected: list[tuple[str, dict]] = []
        if domain == "prognosis": selected = [(f"{r['variant_id']}|{r['diagnosis_id']}", r) for r in doc["decisions"] if r["effect"] != "neither"]
        elif domain == "treatment": selected = [(f"{r['gene']}|{r['diagnosis_id']}", r) for r in doc["decisions"] if r["drug_target"] or r["drug_resistance"]]
        elif domain == "biomarker": selected = [(f"{r['variant_id']}|{r['diagnosis_id']}", r) for r in doc["decisions"] if r["mrd_usable"]]
        elif domain == "germline":
            selected = [(r["variant_id"], r) for r in doc["variant_decisions"] if r["potentially_germline"]]
            if doc["clinical_picture"]["supportive"] is not False: selected.append(("clinical_picture", doc["clinical_picture"]))
        rows.extend({"domain": domain, "key": key, "row": row} for key, row in selected)
    return rows


def treatment_owner_map(case: dict) -> dict[str, str]:
    owners: dict[str, str] = {}
    for variant in case.get("variants") or []:
        owners.setdefault(variant["gene"], variant["variant_id"])
    return owners


def op_assemble_variant_outputs(*, ctx: SchedulerContext, inputs: dict, root: Path) -> dict[str, dict]:
    del root
    variants = inputs["variants"]
    cp_doc = inputs["clinical_picture"]
    cp = cp_doc["clinical_picture"]
    docs = {"prognosis": {"decisions": []}, "treatment": {"decisions": []}, "biomarker": {"decisions": []}, "germline": {"variant_decisions": [], "clinical_picture": cp}}
    for row in variants.values() if isinstance(variants, dict) else variants:
        docs["prognosis"]["decisions"].extend(row["prognosis"]["decisions"])
        if row["treatment"] is not None: docs["treatment"]["decisions"].extend(row["treatment"]["decisions"])
        docs["biomarker"]["decisions"].extend(row["biomarker"]["decisions"])
        docs["germline"]["variant_decisions"].append(row["germline_variant"])
    return docs


def op_apply_domain_patch(*, ctx: SchedulerContext, inputs: dict, root: Path) -> dict[str, dict]:
    del ctx
    docs = copy.deepcopy(inputs["initial"])
    for change in inputs["patch"]["changes"]: docs[change["domain"]] = change["replacement"]
    root.mkdir(parents=True, exist_ok=True)
    (root / "APPLIED.yaml").write_text(yaml.safe_dump(docs, sort_keys=False, allow_unicode=True, width=110), encoding="utf-8")
    return docs


def op_select_high_impact(*, ctx: SchedulerContext, inputs: dict, root: Path) -> list[dict]:
    del ctx, root
    return high_impact_cells(inputs["states"])


def _replace_cell(domain: str, doc: dict, key: str, replacement: dict) -> None:
    if domain in {"prognosis", "treatment", "biomarker"}:
        for i, row in enumerate(doc["decisions"]):
            if scope_key(domain, row) == scope_key(domain, replacement): doc["decisions"][i] = replacement; return
    elif domain == "germline" and key != "clinical_picture":
        for i, row in enumerate(doc["variant_decisions"]):
            if row["variant_id"] == replacement["variant_id"]: doc["variant_decisions"][i] = replacement; return
    elif domain == "germline" and key == "clinical_picture": doc["clinical_picture"] = replacement; return
    raise ValueError(f"could not apply adaptive replacement for {domain}:{key}")


def op_apply_cell_reviews(*, ctx: SchedulerContext, inputs: dict, root: Path) -> dict[str, dict]:
    del ctx
    docs = copy.deepcopy(inputs["initial"]); manifest = []
    reviews = inputs["reviews"]
    for cell_key, review in reviews.items():
        item = review["__item__"] if isinstance(review, dict) and "__item__" in review else None
        payload = review["__payload__"] if item else review
        if not item: raise ValueError(f"adaptive review {cell_key!r} missing cell metadata")
        manifest.append({"domain": item["domain"], "key": item["key"], "action": payload["action"], "reason": payload["reason"]})
        if payload["action"] == "replace": _replace_cell(item["domain"], docs[item["domain"]], item["key"], payload["replacement"])
    root.mkdir(parents=True, exist_ok=True)
    (root / "review-manifest.yaml").write_text(yaml.safe_dump({"reviews": manifest}, sort_keys=False, allow_unicode=True, width=110), encoding="utf-8")
    return docs


def op_publish_domains(*, ctx: SchedulerContext, inputs: dict, root: Path) -> dict[str, dict]:
    del root
    states = inputs["states"]
    scheduler_id=str(ctx.values.get("_scheduler_id") or "")
    for domain in DOMAINS:
        if domain not in states: raise ValueError(f"scheduler publish missing canonical domain {domain}")
        evidence = ctx.ensure_evidence(domain)
        text = yaml.safe_dump(states[domain], sort_keys=False, allow_unicode=True, width=110)
        runtime.validate_domain_text(text, domain=domain, spec=ctx.specs[domain], permitted_tags=evidence.permitted_tags, permitted_case_refs=runtime.case_reference_ids(ctx.case))
        if ctx.fact_commit is not None and scheduler_id != "variant-centric":
            ctx.fact_commit(
                snapshot_key=f"ptbg.{domain}",
                candidates=runtime.facts_from_domain(domain,states[domain]),
                source=f"scheduler:ptbg:{scheduler_id}:publish:{domain}",
            )
        ctx.write_text(layout.domain(ctx.work, domain, "FINAL_STATE.yaml", existing=False), text)
    return states



def op_publish_minimal_diagnosis(*, ctx: SchedulerContext, inputs: dict, root: Path) -> dict:
    del root
    who5 = inputs["who5"]
    final_cmcs = runtime.derive_cmcs(who5)
    history = []
    for cmc in list(ctx.case.get("bootstrap_cmcs") or []) + final_cmcs:
        if cmc not in history:
            history.append(cmc)
    routing = {
        "schema_version": 1,
        "final_cmcs": final_cmcs,
        "diagnostic_cmc_history": history,
        "passes": [{
            "pass": 1,
            "phase": "minimal",
            "who5_signature": runtime.who5_signature(who5),
            "derived_cmcs": final_cmcs,
            "new_cmc_evidence_added": [c for c in final_cmcs if c not in (ctx.case.get("bootstrap_cmcs") or [])],
            "cumulative_cmc_history": history,
        }],
    }
    return {"who5": who5, "routing": routing}


def op_prepare_paraphrase_items(*, ctx: SchedulerContext, inputs: dict, root: Path) -> list[dict]:
    del ctx
    plan=inputs["plan"]; facts=inputs["facts"]
    items=runtime.paraphrase_items(plan,facts)
    root.mkdir(parents=True,exist_ok=True)
    (root/"PARAPHRASE_ITEMS.yaml").write_text(yaml.safe_dump({"items":items},sort_keys=False,allow_unicode=True,width=110),encoding="utf-8")
    return items


def op_publish_summary(*, ctx: SchedulerContext, inputs: dict, root: Path) -> dict:
    del ctx
    plan=inputs["plan"]; paraphrases=inputs["paraphrases"]; facts=inputs["facts"]
    fact_map={f["fact_id"]:f for f in facts}
    by_id={}
    values=paraphrases.values() if isinstance(paraphrases,dict) else paraphrases
    for row in values:
        if not isinstance(row,dict) or "sentence_id" not in row:
            raise ValueError("paraphrase collection contains an invalid sentence result")
        by_id[row["sentence_id"]]=row["sentence"]
    rows=[]
    for planned in plan["sentences"]:
        sid=planned["sentence_id"]
        if sid not in by_id:
            raise ValueError(f"missing paraphrase for planned sentence {sid}")
        ids=list(planned["source_fact_ids"])
        tags=[]
        for fid in ids:
            for tag in fact_map[fid].get("card_tags") or []:
                if tag not in tags: tags.append(tag)
        rows.append({
            "sentence_id":sid,
            "domain":planned["domain"],
            "sentence":by_id[sid],
            "source_fact_ids":ids,
            "card_tags":tags,
        })
    doc={"dispositions":copy.deepcopy(plan["dispositions"]),"sentences":rows}
    runtime.validate_canonical_summary_doc(doc,facts)
    root.mkdir(parents=True,exist_ok=True)
    (root/"SUMMARY.yaml").write_text(yaml.safe_dump(doc,sort_keys=False,allow_unicode=True,width=110),encoding="utf-8")
    return {"summary":doc}


OPERATIONS = {
    "assemble_variant_outputs": op_assemble_variant_outputs,
    "apply_domain_patch": op_apply_domain_patch,
    "select_high_impact": op_select_high_impact,
    "apply_cell_reviews": op_apply_cell_reviews,
    "publish_domains": op_publish_domains,
    "publish_minimal_diagnosis": op_publish_minimal_diagnosis,
    "prepare_paraphrase_items": op_prepare_paraphrase_items,
    "publish_summary": op_publish_summary,
}
