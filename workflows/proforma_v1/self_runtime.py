"""Additive native-self orchestration helpers for proforma-v1.

This module deliberately reuses the existing proforma-v1 contracts and deterministic
helpers without changing ``step.py`` or any module imported by ``step.py``.  The
self executor changes only model-call grouping and context boundaries.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import yaml

from workflows.proforma_v1 import card_identity, domain_contract, layout, model_context, runtime, schema_validation
from workflows.proforma_v1 import step as staged

SELF_PASS_ORDER = (
    "who1",
    "icc",
    "who2",
    "ptbg",
    "evidence_resolution",
    "evidence_audit",
    "evidence_adjudication",  # conditional
    "report_synthesis",
)

HERE = Path(__file__).resolve().parent
ADJUDICATION_PROMPT = HERE / "prompts" / "evidence_adjudicate.md"
ADJUDICATION_SCHEMA = HERE / "schemas" / "evidence_adjudicate.json"


def read_yaml(path: Path) -> dict:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected YAML mapping: {path}")
    return data


def write_yaml(path: Path, data: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=110), encoding="utf-8")
    return path


def write_json(path: Path, data: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def artifact(work: Path, group: str, name: str, *, new: bool = False) -> Path:
    return staged._artifact(Path(work), group, name, new=new)


def contract_path(name: str) -> Path:
    spec = staged.stage_spec.load(name)
    return HERE / "prompts" / spec.prompt


def output_path(work: Path, group: str, name: str) -> Path:
    return staged._existing_or_new(Path(work), group, name)


def case_path(work: Path) -> Path:
    return staged._case_json(Path(work))


def variants_path(work: Path) -> Path:
    return staged._variants_path(Path(work))


def accept_structured_case(work: Path) -> tuple[dict, dict]:
    """Validate only the machine-critical case contract and create canonical vNN IDs."""
    work = Path(work)
    path = case_path(work)
    if not path.is_file():
        raise ValueError(f"structured case output missing: {path}")
    text = path.read_text(encoding="utf-8")
    runtime.validate_case_text(text)
    case = runtime.normalize_case_variant_descriptions(runtime.read_json(path))
    case = runtime.materialize_ngs_no_variants_detected(
        case, layout.setup(work, "ngs-panel-scope.md").read_text(encoding="utf-8")
    )
    path.write_text(json.dumps(case, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    runtime.validate_case_text(path.read_text(encoding="utf-8"), require_gene_prefixed_description=True)
    reg = {
        f"v{i:02d}": {
            "variant_id": row["variant_id"],
            "gene": row["gene"],
            "description": row["description"],
        }
        for i, row in enumerate(case.get("variants") or [], 1)
    }
    write_yaml(variants_path(work), {"variants": reg})
    return case, reg


def load_case_registry(work: Path) -> tuple[dict, dict]:
    case, _ = accept_structured_case(work)
    reg_doc = read_yaml(variants_path(work))
    reg = reg_doc.get("variants") or {}
    if not isinstance(reg, dict):
        raise ValueError("variant registry must contain a variants mapping")
    return case, reg


def corpus_state(work: Path):
    all_cards, eligible, digest, manifest = staged.stage_corpus(Path(work))
    return all_cards, eligible, digest, manifest


def _write_pool(
    work: Path,
    group: str,
    cards: list[dict],
    manifest: dict,
    *,
    diagnosis_authority: str | None = None,
) -> tuple[Path, Path]:
    tag_by_id = card_identity.tag_by_id(manifest)
    md = output_path(work, group, "cards.md")
    rendered = (
        staged._render_diagnostic_cards(cards, tag_by_id, diagnosis_authority)
        if diagnosis_authority
        else staged._render_cards(cards, tag_by_id)
    )
    md.write_text(rendered, encoding="utf-8")
    js = output_path(work, group, "cards.json")
    write_json(js, {"card_ids": [c["card_id"] for c in cards], "runtime_tags": {c["card_id"]: tag_by_id[c["card_id"]] for c in cards}})
    return md, js


def prepare_who(work: Path, *, pass_number: int) -> dict:
    """Prepare WHO1 or authoritative WHO2 using the shared WHO5 contract."""
    work = Path(work)
    case, reg = load_case_registry(work)
    _all_cards, eligible, _digest, manifest = corpus_state(work)
    allowed = staged._allowed_diseases(work)
    genes = runtime.case_genes(case)
    bootstrap = list(case.get("bootstrap_cmcs") or [])
    if pass_number == 1:
        history = bootstrap
        group = "self_who1_input"
        out = output_path(work, "diagnosis_who5_pass_1", "who5.yaml")
    elif pass_number == 2:
        who1 = read_yaml(output_path(work, "diagnosis_who5_pass_1", "who5.yaml"))
        schema_validation.validate_who5_diagnosis(
            yaml.safe_dump(who1), allowed_diseases=allowed, valid_variants=set(reg)
        )
        history = list(bootstrap)
        for cmc in runtime.derive_cmcs(who1):
            if cmc not in history:
                history.append(cmc)
        group = "self_who2_input"
        out = output_path(work, "diagnosis_who5_pass_2", "who5.yaml")
    else:
        raise ValueError("WHO pass_number must be 1 or 2")
    cards = staged._diagnostic_cards(eligible, genes, history, "who5")
    cards_md, _ = _write_pool(work, group, cards, manifest, diagnosis_authority="who5")
    finite = output_path(work, group, "finite-membership.yaml")
    write_yaml(finite, staged._finite_membership_context(reg, cards, card_identity.tag_by_id(manifest)))
    context = output_path(work, group, "context.yaml")
    write_yaml(context, {
        "starting_morphologic_diagnosis": case.get("provisional_disease"),
        "morphologic_diagnosis_origin": case.get("morphologic_diagnosis_origin"),
        "structured_case": case,
        "variant_registry": reg,
        "allowed_schema_diseases": sorted(allowed),
        "retrieval_cmcs": history,
        "authoritative": pass_number == 2,
    })
    return {
        "pass": f"who{pass_number}",
        "contract": contract_path("diagnosis_who5"),
        "context": context,
        "finite_membership": finite,
        "cards": cards_md,
        "output": out,
    }


def accept_who(work: Path, *, pass_number: int) -> dict:
    case, reg = load_case_registry(work)
    allowed = staged._allowed_diseases(work)
    path = output_path(work, f"diagnosis_who5_pass_{pass_number}", "who5.yaml")
    if not path.is_file():
        raise ValueError(f"WHO output missing: {path}")
    cleaned = staged._sanitize_proforma_text(work, f"self-who{pass_number}", path.read_text(encoding="utf-8"))
    path.write_text(cleaned, encoding="utf-8")
    schema_validation.validate_who5_diagnosis(cleaned, allowed_diseases=allowed, valid_variants=set(reg))
    return read_yaml(path)


def prepare_icc(work: Path) -> dict:
    """Prepare isolated ICC. WHO1 is validated for routing only and never exposed."""
    work = Path(work)
    case, reg = load_case_registry(work)
    who1 = accept_who(work, pass_number=1)
    _all_cards, eligible, _digest, manifest = corpus_state(work)
    history = list(case.get("bootstrap_cmcs") or [])
    for cmc in runtime.derive_cmcs(who1):
        if cmc not in history:
            history.append(cmc)
    cards = staged._diagnostic_cards(eligible, runtime.case_genes(case), history, "icc")
    group = "self_icc_input"
    cards_md, _ = _write_pool(work, group, cards, manifest, diagnosis_authority="icc")
    finite = output_path(work, group, "finite-membership.yaml")
    write_yaml(finite, staged._finite_membership_context(reg, cards, card_identity.tag_by_id(manifest)))
    context = output_path(work, group, "context.yaml")
    # Deliberately contains no WHO diagnosis/result.
    write_yaml(context, {
        "starting_morphologic_diagnosis": case.get("provisional_disease"),
        "morphologic_diagnosis_origin": case.get("morphologic_diagnosis_origin"),
        "structured_case": case,
        "variant_registry": reg,
        "retrieval_cmcs": history,
        "isolation": "WHO1 conclusion intentionally withheld",
    })
    return {
        "pass": "icc",
        "contract": contract_path("diagnosis_icc"),
        "context": context,
        "finite_membership": finite,
        "cards": cards_md,
        "output": output_path(work, "diagnosis_icc", "icc.yaml"),
    }


def accept_icc(work: Path) -> dict:
    _case, reg = load_case_registry(work)
    path = output_path(work, "diagnosis_icc", "icc.yaml")
    if not path.is_file():
        raise ValueError(f"ICC output missing: {path}")
    cleaned = staged._sanitize_proforma_text(work, "self-icc", path.read_text(encoding="utf-8"))
    path.write_text(cleaned, encoding="utf-8")
    schema_validation.validate_icc_diagnosis(cleaned, valid_variants=set(reg))
    return read_yaml(path)


def finalize_diagnosis(work: Path) -> dict:
    who1 = accept_who(work, pass_number=1)
    icc = accept_icc(work)
    who2 = accept_who(work, pass_number=2)
    relationship = "same" if runtime.normalize_dx(who2["diagnosis"]) == runtime.normalize_dx(icc["diagnosis"]) else "different"
    diagnosis = {
        "who5": who2,
        "icc": icc,
        "second_diagnosis": {"diagnosis": None, "variants": [], "reason": None},
        "relationship": relationship,
        "self_execution": {"who5_first_pass": who1, "who5_authoritative_pass": 2},
    }
    write_yaml(output_path(work, "diagnosis", "diagnosis-final.yaml"), diagnosis)
    route = {
        "bootstrap_cmcs": load_case_registry(work)[0].get("bootstrap_cmcs") or [],
        "who5_authoritative_pass": 2,
        "final_cmcs": runtime.derive_cmcs(who2),
    }
    write_json(output_path(work, "diagnosis", "routing.json"), route)
    return diagnosis


def prepare_ptbg(work: Path) -> dict:
    """Prepare all four existing PTBG contracts for one model reasoning pass."""
    work = Path(work)
    case, reg = load_case_registry(work)
    diagnosis = finalize_diagnosis(work)
    _all_cards, eligible, _digest, manifest = corpus_state(work)
    disease = diagnosis["who5"]["schema_disease"]
    tag_by_id = card_identity.tag_by_id(manifest)
    outputs = {}
    genes = runtime.case_genes(case)
    for domain in ("prognosis", "treatment", "biomarker", "germline"):
        cards = staged._draw_domain_cards(eligible, domain, genes, [disease])
        staged._log_ptbg_retrieval(work, eligible, domain, genes, disease, cards)
        group = f"self_ptbg_{domain}_input"
        cards_md, _ = _write_pool(work, group, cards, manifest)
        skeleton = output_path(work, group, "output-contract.md")
        skeleton.write_text(
            domain_contract.skeleton(
                domain_contract.contract(domain), sorted(reg), registry=reg, applicable_disease=disease
            ),
            encoding="utf-8",
        )
        context = output_path(work, group, "context.yaml")
        write_yaml(context, {
            "structured_case": {k: case.get(k) for k in model_context.DOMAIN_CASE_FIELDS},
            "variant_registry": reg,
            "authoritative_framework_diagnoses": {
                "who5": {k: diagnosis["who5"].get(k) for k in ("schema_disease", "diagnosis", "variants", "diagnostic_effect", "reason")},
                "icc": {k: diagnosis["icc"].get(k) for k in ("diagnosis", "variants", "diagnostic_effect", "reason")},
            },
        })
        outputs[domain] = {
            "contract": contract_path(domain),
            "context": context,
            "cards": cards_md,
            "output_contract": skeleton,
            "output": output_path(work, f"{domain}_state", "model-classification.yaml"),
        }
    return {"pass": "ptbg", "domains": outputs}


def accept_ptbg(work: Path) -> dict[str, dict]:
    _case, reg = load_case_registry(work)
    domains = {}
    for domain in ("prognosis", "treatment", "biomarker", "germline"):
        model_path = output_path(work, f"{domain}_state", "model-classification.yaml")
        if not model_path.is_file():
            raise ValueError(f"{domain} model output missing: {model_path}")
        cleaned = staged._sanitize_proforma_text(work, f"self-{domain}", model_path.read_text(encoding="utf-8"))
        disease = finalize_diagnosis(work)["who5"]["schema_disease"]
        normalized, identity_records = domain_contract.normalize_model_output(
            cleaned, domain_contract.contract(domain), reg, disease
        )
        if identity_records:
            staged._log_transforms(work, [dict(record, stage=f"self-{domain}") for record in identity_records])
        model_path.write_text(normalized, encoding="utf-8")
        schema_validation.validate_domain(
            normalized, domain, set(reg), registry=reg, authoritative_disease=disease
        )
        flat = read_yaml(model_path)
        doc = domain_contract.pivot(flat, domain_contract.contract(domain))
        doc, merges = staged._consolidate_rows(domain, doc, reg)
        staged._log_transforms(work, merges)
        write_yaml(output_path(work, f"{domain}_state", "proforma.yaml"), doc)
        domains[domain] = doc
    return domains


def load_domains(work: Path) -> dict[str, dict]:
    return {d: read_yaml(output_path(work, f"{d}_state", "proforma.yaml")) for d in ("prognosis", "treatment", "biomarker", "germline")}


def _evidence_state_path(work: Path) -> Path:
    return output_path(work, "self_evidence", "state.yaml")


def prepare_evidence_resolution(work: Path) -> dict:
    """Build bounded candidate pools; no card is assigned to a reason here."""
    work = Path(work)
    case, reg = load_case_registry(work)
    diagnosis = finalize_diagnosis(work)
    domains = accept_ptbg(work)
    all_cards, eligible, digest, manifest = corpus_state(work)
    genes = runtime.case_genes(case)
    cmcs = list(case.get("bootstrap_cmcs") or [])
    for cmc in runtime.derive_cmcs(diagnosis["who5"]):
        if cmc not in cmcs:
            cmcs.append(cmc)
    cards_by_domain = {
        "diagnosis_who5": staged._diagnostic_cards(eligible, genes, cmcs, "who5"),
        "diagnosis_icc": staged._diagnostic_cards(eligible, genes, cmcs, "icc"),
    }
    disease = diagnosis["who5"]["schema_disease"]
    for domain in ("prognosis", "treatment", "biomarker", "germline"):
        cards_by_domain[domain] = staged._draw_domain_cards(eligible, domain, genes, [disease])
        staged._log_ptbg_retrieval(work, eligible, domain, genes, disease, cards_by_domain[domain])
    elements = staged._elements(diagnosis, domains, case)
    tag_by_id = card_identity.tag_by_id(manifest)
    catalog = {}
    items = []
    no_candidates = []
    for el in elements:
        candidates = staged._candidate_cards(el, cards_by_domain, reg)
        if not candidates:
            no_candidates.append(el["schema_id"])
            continue
        eid = f"E{len(items)+1:04d}"
        for card in candidates:
            catalog[card["card_id"]] = card
        items.append({
            "evidence_id": eid,
            "schema_id": el["schema_id"],
            "reason": el["reason"],
            "statement": el["statement"],
            "candidate_card_ids": [c["card_id"] for c in candidates],
            "candidate_card_tags": [f"[card:{tag_by_id[c['card_id']]}]" for c in candidates],
        })
    state = {
        "elements": elements,
        "items": items,
        "no_candidate_schema_ids": no_candidates,
        "catalog_card_ids": list(catalog),
        "authoritative_disease": disease,
        "corpus_sha256": digest,
    }
    write_yaml(_evidence_state_path(work), state)
    group = "self_evidence_resolution_input"
    public_rows = [{k: x[k] for k in ("evidence_id", "schema_id", "reason", "candidate_card_tags")} for x in items]
    public = output_path(work, group, "items.yaml")
    write_yaml(public, {"items": public_rows})
    cards_md = output_path(work, group, "candidate-cards-by-item.md")
    cards_md.write_text(
        staged._render_evidence_match_candidates(public_rows, items, catalog, tag_by_id),
        encoding="utf-8",
    )
    return {
        "pass": "evidence_resolution",
        "contract": contract_path("evidence_match"),
        "items": public,
        "cards": cards_md,
        "output": output_path(work, "evidence_matches", "self-resolution.yaml"),
    }


def _load_evidence_state(work: Path) -> dict:
    return read_yaml(_evidence_state_path(work))


def accept_evidence_resolution(work: Path) -> dict:
    state = _load_evidence_state(work)
    path = output_path(work, "evidence_matches", "self-resolution.yaml")
    if not path.is_file():
        raise ValueError(f"evidence-resolution output missing: {path}")
    items = [{"evidence_id": x["evidence_id"], "candidate_card_tags": x["candidate_card_tags"]} for x in state["items"]]
    schema_validation.validate_evidence_match_batch(path.read_text(encoding="utf-8"), items)
    return read_yaml(path)


def audit_targets(items: list[dict], matches: dict) -> list[dict]:
    """Audit selected cards; when resolver selected none, audit the full candidate set.

    This bounded asymmetry catches false-positive assignments and false-negative
    zero-card decisions without paying to exhaustively audit redundant unselected
    cards when at least one support card was already found.
    """
    mmap = {m["evidence_id"]: m for m in matches.get("matches") or []}
    out = []
    for item in items:
        selected = list((mmap.get(item["evidence_id"]) or {}).get("card_tags") or [])
        audit_tags = selected if selected else list(item.get("candidate_card_tags") or [])
        out.append({
            "evidence_id": item["evidence_id"],
            "schema_id": item["schema_id"],
            "reason": item["reason"],
            "resolution_card_tags": selected,
            "selected_card_tags": audit_tags,
            "audit_scope": "resolver_selected" if selected else "zero_card_full_candidate_check",
        })
    return out


def _assert_audit_targets_applicable(work: Path, state: dict, targets: list[dict]) -> None:
    """Re-check PTBG disease/domain scope immediately before semantic audit."""
    _case, reg = load_case_registry(work)
    disease = state.get("authoritative_disease") or finalize_diagnosis(work)["who5"]["schema_disease"]
    elements = {el["schema_id"]: el for el in state.get("elements") or []}
    all_cards, _eligible, _digest, manifest = corpus_state(work)
    by_id = {c["card_id"]: c for c in all_cards}
    id_by_tag = {f"[card:{tag}]": cid for cid, tag in card_identity.tag_by_id(manifest).items()}
    for target in targets:
        el = elements.get(target["schema_id"])
        if not el or el.get("domain") == "diagnosis":
            continue
        for tag in target.get("selected_card_tags") or []:
            cid = id_by_tag.get(tag)
            card = by_id.get(cid)
            if card is None:
                raise ValueError(f"evidence audit references unknown runtime card tag {tag}")
            staged._assert_ptbg_audit_card_applicable(card, el, reg, disease)


def prepare_evidence_audit(work: Path) -> dict:
    state = _load_evidence_state(work)
    matches = accept_evidence_resolution(work)
    targets = audit_targets(state["items"], matches)
    _assert_audit_targets_applicable(work, state, targets)
    group = "self_evidence_audit_input"
    item_path = output_path(work, group, "items.yaml")
    write_yaml(item_path, {"items": targets})
    tag_to_id = {}
    _all, _eligible, _digest, manifest = corpus_state(work)
    for cid, tag in card_identity.tag_by_id(manifest).items():
        tag_to_id[f"[card:{tag}]"] = cid
    needed = []
    state_catalog = set(state.get("catalog_card_ids") or [])
    all_cards, _, _, _ = corpus_state(work)
    by_id = {c["card_id"]: c for c in all_cards}
    for target in targets:
        for tag in target["selected_card_tags"]:
            cid = tag_to_id.get(tag)
            if cid in state_catalog and cid not in needed:
                needed.append(cid)
    cards_md, _ = _write_pool(work, group, [by_id[cid] for cid in needed], manifest)
    return {
        "pass": "evidence_audit",
        "contract": contract_path("evidence_audit"),
        "items": item_path,
        "cards": cards_md,
        "output": output_path(work, "evidence_audits", "self-audit.yaml"),
    }


def accept_evidence_audit(work: Path) -> tuple[dict, list[dict]]:
    state = _load_evidence_state(work)
    matches = accept_evidence_resolution(work)
    targets = audit_targets(state["items"], matches)
    path = output_path(work, "evidence_audits", "self-audit.yaml")
    if not path.is_file():
        raise ValueError(f"evidence-audit output missing: {path}")
    _assert_audit_targets_applicable(work, state, targets)
    validation_items = [{"evidence_id": x["evidence_id"], "selected_card_tags": x["selected_card_tags"]} for x in targets]
    schema_validation.validate_evidence_audit_batch(path.read_text(encoding="utf-8"), validation_items)
    return read_yaml(path), targets


def compare_evidence(items: list[dict], matches: dict, audits: dict, targets: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return (agreed assignments, disputes) without making any semantic decision."""
    mmap = {m["evidence_id"]: m for m in matches.get("matches") or []}
    amap = {a["evidence_id"]: {x["card_tag"]: x for x in a.get("card_audits") or []} for a in audits.get("audits") or []}
    target_map = {x["evidence_id"]: x for x in targets}
    agreed = []
    disputes = []
    for item in items:
        eid = item["evidence_id"]
        selected = set((mmap.get(eid) or {}).get("card_tags") or [])
        aud = amap.get(eid, {})
        for tag in target_map[eid]["selected_card_tags"]:
            row = aud[tag]
            audit_yes = bool(row["card_is_element_of_reason"])
            if tag in selected and audit_yes:
                agreed.append({"evidence_id": eid, "schema_id": item["schema_id"], "card_tag": tag, "audit": row})
            elif tag in selected and not audit_yes:
                disputes.append({
                    "evidence_id": eid, "schema_id": item["schema_id"], "reason": item["reason"],
                    "card_tag": tag, "dispute_type": "resolver_include_auditor_exclude",
                    "resolver_decision": "include", "auditor_decision": "exclude", "audit_comments": row.get("comments") or [],
                })
            elif tag not in selected and audit_yes:
                disputes.append({
                    "evidence_id": eid, "schema_id": item["schema_id"], "reason": item["reason"],
                    "card_tag": tag, "dispute_type": "resolver_zero_auditor_include",
                    "resolver_decision": "exclude", "auditor_decision": "include", "audit_comments": row.get("comments") or [],
                })
    return agreed, disputes


def prepare_evidence_adjudication(work: Path) -> dict:
    state = _load_evidence_state(work)
    matches = accept_evidence_resolution(work)
    audits, targets = accept_evidence_audit(work)
    agreed, disputes = compare_evidence(state["items"], matches, audits, targets)
    write_yaml(output_path(work, "self_evidence", "agreed.yaml"), {"assignments": agreed})
    crop = output_path(work, "self_evidence_adjudication_input", "disputes.yaml")
    write_yaml(crop, {"disputes": disputes})
    if not disputes:
        return {"pass": "evidence_adjudication", "required": False, "disputes": crop}
    # Card text is deliberately cropped to disputed cards only.
    all_cards, _eligible, _digest, manifest = corpus_state(work)
    tag_by_id = card_identity.tag_by_id(manifest)
    id_by_tag = {f"[card:{tag}]": cid for cid, tag in tag_by_id.items()}
    by_id = {c["card_id"]: c for c in all_cards}
    ids = []
    for row in disputes:
        cid = id_by_tag[row["card_tag"]]
        if cid not in ids:
            ids.append(cid)
    cards_md, _ = _write_pool(work, "self_evidence_adjudication_input", [by_id[cid] for cid in ids], manifest)
    return {
        "pass": "evidence_adjudication",
        "required": True,
        "contract": ADJUDICATION_PROMPT,
        "disputes": crop,
        "cards": cards_md,
        "output": output_path(work, "evidence_adjudication", "adjudication.yaml"),
    }


def validate_adjudication(doc: dict, disputes: list[dict]) -> None:
    rows = doc.get("adjudications")
    if not isinstance(rows, list):
        raise ValueError("evidence adjudication requires adjudications list")
    expected = [(d["evidence_id"], d["card_tag"]) for d in disputes]
    actual = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {"evidence_id", "card_tag", "decision", "reason"}:
            raise ValueError(f"adjudications[{i}] must contain exactly evidence_id, card_tag, decision, reason")
        if row["decision"] not in {"include", "exclude"}:
            raise ValueError(f"adjudications[{i}].decision must be include or exclude")
        if not isinstance(row["reason"], str) or not row["reason"].strip():
            raise ValueError(f"adjudications[{i}].reason must be non-empty")
        actual.append((row["evidence_id"], row["card_tag"]))
    if actual != expected:
        raise ValueError(f"adjudication rows must exactly preserve dispute order {expected}; received {actual}")


def _record_disputes(work: Path, disputes: list[dict], adjudications: dict | None) -> None:
    amap = {(x["evidence_id"], x["card_tag"]): x for x in (adjudications or {}).get("adjudications") or []}
    for row in disputes:
        issue = f"evidence-dispute:{row['evidence_id']}:{row['card_tag']}"
        staged._semantic_dissent(
            work,
            issue_key=issue,
            stage="evidence audit comparison",
            reviewed_text=f"Reason: {row['reason']}\nCard: {row['card_tag']}",
            dissent_reason=[f"Resolver: {row['resolver_decision']}; auditor: {row['auditor_decision']}." , *(row.get("audit_comments") or [])],
            action_recommended="Adjudicate only this cropped reason/card membership disagreement.",
        )
        decision = amap.get((row["evidence_id"], row["card_tag"]))
        if decision:
            staged._semantic_dissent_address(
                work,
                issue_key=issue,
                stage="evidence adjudication",
                action=f"Adjudicator decided to {decision['decision']} the disputed card.",
                outcome=decision["reason"],
                status="resolved",
            )


def finalize_evidence(work: Path) -> list[dict]:
    """Apply agreement/adjudication deterministically and build supported elements."""
    work = Path(work)
    state = _load_evidence_state(work)
    matches = accept_evidence_resolution(work)
    audits, targets = accept_evidence_audit(work)
    agreed, disputes = compare_evidence(state["items"], matches, audits, targets)
    adjudications = None
    if disputes:
        apath = output_path(work, "evidence_adjudication", "adjudication.yaml")
        if not apath.is_file():
            raise ValueError(f"evidence disagreements require adjudication output: {apath}")
        adjudications = read_yaml(apath)
        validate_adjudication(adjudications, disputes)
    _record_disputes(work, disputes, adjudications)

    all_cards, _eligible, _digest, manifest = corpus_state(work)
    by_id = {c["card_id"]: c for c in all_cards}
    id_by_tag = {f"[card:{tag}]": cid for cid, tag in card_identity.tag_by_id(manifest).items()}
    assignment_rows = list(agreed)
    if adjudications:
        dmap = {(d["evidence_id"], d["card_tag"]): d for d in disputes}
        for row in adjudications["adjudications"]:
            if row["decision"] == "include":
                d = dmap[(row["evidence_id"], row["card_tag"])]
                assignment_rows.append({
                    "evidence_id": row["evidence_id"], "schema_id": d["schema_id"], "card_tag": row["card_tag"],
                    "audit": {"card_is_element_of_reason": d["auditor_decision"] == "include", "risk": "none", "comments": d.get("audit_comments") or []},
                    "adjudication": row,
                })
    assignments: dict[str, list[dict]] = {}
    for row in assignment_rows:
        assignments.setdefault(row["evidence_id"], []).append(row)

    item_by_schema = {x["schema_id"]: x for x in state["items"]}
    eid_by_schema = {x["schema_id"]: x["evidence_id"] for x in state["items"]}
    keep = []
    for el in state["elements"]:
        eid = eid_by_schema.get(el["schema_id"])
        rows = assignments.get(eid, []) if eid else []
        if rows:
            clone = dict(el)
            clone["evidence"] = []
            for row in rows:
                cid = id_by_tag[row["card_tag"]]
                evidence = staged._accepted_evidence(by_id[cid], row["card_tag"], row["audit"], 1)
                if row.get("adjudication"):
                    evidence["adjudication"] = row["adjudication"]
                clone["evidence"].append(evidence)
                if row["audit"].get("risk") == "warning":
                    issue = f"evidence-warning:{el['schema_id']}:{row['card_tag']}"
                    staged._semantic_dissent(
                        work, issue_key=issue, stage="evidence audit", reviewed_text=el["reason"],
                        dissent_reason=row["audit"].get("comments") or ["Evidence fidelity/context warning."],
                        action_recommended="Retain this supported card/reason match with dissent visible for review.",
                    )
                    staged._semantic_dissent_address(
                        work, issue_key=issue, stage="evidence resolution", action="Retain supported card/reason match.",
                        outcome="Membership passed; warning remains visible.", status="retained_with_dissent",
                    )
            keep.append(clone)
            continue
        reason = "No candidate evidence card was available for this reportable proposition." if el["schema_id"] in state.get("no_candidate_schema_ids", []) else "Two-pass evidence review did not establish a supported card for this proposition."
        resolved = staged._resolve_no_citation_support(work, el, attempt=1, reason=reason)
        if resolved is not None:
            keep.append(resolved)

    order = {el["schema_id"]: i for i, el in enumerate(state["elements"])}
    keep.sort(key=lambda el: order.get(el["schema_id"], len(order)))
    write_yaml(output_path(work, "evidence_enriched", "reportable-elements.yaml"), {"elements": keep})
    diagnosis = finalize_diagnosis(work)
    _case, reg = load_case_registry(work)
    staged.stage_blocks(work, diagnosis, keep, reg)
    staged._write_dissent(work)
    return keep


def prepare_report(work: Path) -> dict:
    work = Path(work)
    elements_path = output_path(work, "evidence_enriched", "reportable-elements.yaml")
    if not elements_path.is_file():
        finalize_evidence(work)
    blocks_path = output_path(work, "report_blocks", "report-blocks.yaml")
    blocks = read_yaml(blocks_path).get("blocks") or []
    case, reg = load_case_registry(work)
    context = output_path(work, "self_report_input", "context.yaml")
    write_yaml(context, {"structured_case": case, "variant_registry": reg, "deterministic_report_blocks": blocks})
    return {
        "pass": "report_synthesis",
        "contract": contract_path("report_write"),
        "case": layout.input(work, "case.md"),
        "context": context,
        "output": output_path(work, "report_write", "report-write.yaml"),
    }


def finalize_report(work: Path) -> Path:
    work = Path(work)
    blocks = read_yaml(output_path(work, "report_blocks", "report-blocks.yaml")).get("blocks") or []
    report_path = output_path(work, "report_write", "report-write.yaml")
    if not report_path.is_file():
        raise ValueError(f"report synthesis output missing: {report_path}")
    schema_validation.validate_report_write(report_path.read_text(encoding="utf-8"), blocks)
    rendered = read_yaml(report_path)["blocks"]
    text_by_id = {x["block_id"]: x["text"] for x in rendered}
    final = []
    for block in blocks:
        tags = []
        for comp in block.get("components") or []:
            for tag in comp.get("card_tags") or []:
                if tag not in tags:
                    tags.append(tag)
        final.append({
            "block_id": block["block_id"],
            "domain": block["domain"],
            "text": runtime.ensure_sentence(text_by_id[block["block_id"]]),
            "card_tags": tags,
        })
    write_yaml(output_path(work, "report_write", "report-final-blocks.yaml"), {"blocks": final})
    case, _reg = load_case_registry(work)
    elements = read_yaml(output_path(work, "evidence_enriched", "reportable-elements.yaml"))["elements"]
    all_cards, _eligible, digest, manifest = corpus_state(work)
    staged.stage_final(work, case, final, elements, all_cards, digest, manifest)
    return work / "report-final.md"


DEBUG_ZIP_NAME = "ngs-report-debug.zip"
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def package_debug_bundle(work: Path) -> Path:
    """Package the native-self run deterministically without changing shared workflow metadata.

    Every regular run artifact is included except ZIP files, so the debug bundle
    cannot recursively contain itself or the external-marking bundle.
    """
    work = Path(work).resolve()
    if not work.is_dir():
        raise ValueError(f"work directory not found: {work}")
    output = work / DEBUG_ZIP_NAME
    files = sorted(
        p for p in work.rglob("*")
        if p.is_file() and p.suffix.lower() != ".zip"
    )
    if not files:
        raise ValueError(f"no run artifacts available to package: {work}")
    with zipfile.ZipFile(output, "w") as zf:
        for path in files:
            info = zipfile.ZipInfo(path.relative_to(work).as_posix(), _ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, path.read_bytes())
    return output


def final_artifacts(work: Path) -> dict[str, Path | None]:
    """Return only final artifacts that actually exist for deterministic CLI reporting."""
    work = Path(work).resolve()
    state = staged._load_run_state(work)
    mode = state.get("mode")
    case_id = state.get("validation_case")
    marking = None
    if mode in staged.VALIDATION_MODES and case_id:
        candidate = work / f"{staged.MARKING_PREFIX[mode]}-{case_id}.zip"
        marking = candidate if candidate.is_file() else None
    report = work / "report-final.md"
    report_json = work / "report-final.json"
    dissent = work / "dissent.md"
    debug = work / DEBUG_ZIP_NAME
    return {
        "REPORT": report if report.is_file() else None,
        "REPORT_JSON": report_json if report_json.is_file() else None,
        "MARKING_ZIP": marking,
        "DEBUG_ZIP": debug if debug.is_file() else None,
        "DISSENT": dissent if dissent.is_file() else None,
    }
